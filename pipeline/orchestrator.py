"""Persistent, resumable, single-worker ten-stage pipeline."""
from __future__ import annotations
import asyncio
import json
import logging
import time
from pipeline.context import PipelineContext
from utils.notifications import notify_control_bot
from utils.github_store import persist_state
from utils.text_parser import normalize_title, format_template
from pipeline.stages import (
    stage_1_search, stage_2_filter, stage_3_fetch, stage_4_channel, stage_5_promote,
    stage_6_copy, stage_7_batch, stage_8_shorten, stage_9_post,
    stage_10_catalog,
)
from pipeline.backup_storage import backup_movie
from pipeline.promotion import run as run_promotion
from pipeline.cancellation import JobCancelled,checkpoint
from userbot.speed_controller import DeferredFloodWait
log = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self, ctx: PipelineContext):
        self.ctx = ctx
        self.stop_event = asyncio.Event()

    async def run_forever(self) -> None:
        while not self.stop_event.is_set():
            if (await self.ctx.db.setting("pipeline_paused", "false")).lower() == "true":
                await asyncio.sleep(2)
                continue
            row = await self.ctx.db.next_pending()
            if not row:
                await asyncio.sleep(2)
                continue
            await self.process(dict(row))
            await self.ctx.speed.delay("movie")

    async def _persist_state(self) -> None:
        """Durability outages must never terminate the queue worker."""
        try:
            await persist_state(self.ctx.db)
        except Exception:
            log.exception("Durable-state sync failed; local queue will continue and retry later")

    @staticmethod
    def _json(row, key: str) -> list:
        try:
            return json.loads(row[key] or "[]")
        except (TypeError, json.JSONDecodeError):
            return []

    async def process(self, row: dict) -> None:
        qid, movie = row["id"], row["movie_name"]
        content_type = row.get("content_type", "movie")
        resume_at = max(1, int(row.get("current_stage") or 1))
        stage = resume_at
        try:
            if resume_at <= 1 and not bool(row.get("force_rebuild", 0)):
                existing = await self.ctx.db.find_channel_by_movie(movie, content_type)
                if not existing and content_type == "movie":
                    # Recover movie channels created before durable registry support by
                    # scanning the userbot's existing channel dialogs.
                    expected = normalize_title(format_template(self.ctx.cfg.channel_name, movie=movie, owner_username=self.ctx.cfg.owner_username))
                    async for dialog in self.ctx.client.get_dialogs(limit=500):
                        chat = dialog.chat
                        if chat.title and normalize_title(chat.title) == expected and "channel" in str(chat.type).lower():
                            invite = await self.ctx.speed.call(lambda c=chat: self.ctx.client.export_chat_invite_link(c.id), qid)
                            await self.ctx.db.register_channel(qid, movie, chat.id, invite, content_type)
                            await self._persist_state()
                            existing = await self.ctx.db.find_channel_by_movie(movie, content_type)
                            break
                if existing:
                    try:
                        await self.ctx.speed.call(lambda: self.ctx.client.get_chat(existing["channel_id"]), qid)
                        invite = await self.ctx.speed.call(lambda: self.ctx.client.export_chat_invite_link(existing["channel_id"]), qid)
                        await checkpoint(self.ctx,qid)
                        await self.ctx.db.complete(qid)
                        await notify_control_bot(
                            self.ctx.cfg.control_token, self.ctx.cfg.owner_id,
                            f"ℹ️ Channel already exists for {movie}:\n{invite}",
                        )
                        await self.ctx.db.log("Duplicate request skipped; existing channel returned", "INFO", qid)
                        return
                    except Exception as exc:
                        text = str(exc).lower()
                        if any(marker in text for marker in ("channel_invalid", "channel_private", "peer_id_invalid", "peer id invalid", "not found", "deleted")):
                            await self.ctx.db.remove_channel(existing["channel_id"])
                            await self._persist_state()
                        else:
                            raise
            state = await self.ctx.db.state(qid)
            if resume_at <= 1:
                stage = 1
                await checkpoint(self.ctx,qid)
                await self.ctx.db.set_stage(qid, stage, "searching")
                source = await stage_1_search.run(self.ctx, qid, movie, content_type)
            else:
                source = self._json(state, "source_messages_json")

            if resume_at <= 2:
                stage = 2
                await checkpoint(self.ctx,qid)
                await self.ctx.db.set_stage(qid, stage, "filtering")
                selected = await stage_2_filter.run(self.ctx, qid, source)
            else:
                selected = self._json(state, "filtered_files_json")

            if resume_at <= 3:
                stage = 3
                await checkpoint(self.ctx,qid)
                await self.ctx.db.set_stage(qid, stage, "fetching")
                fetched = await stage_3_fetch.run(self.ctx, qid, selected)
            else:
                fetched = self._json(state, "fetched_files_json")

            if resume_at <= 4:
                stage = 4
                await checkpoint(self.ctx,qid)
                await self.ctx.db.set_stage(qid, stage, "creating_channel")
                channel = await stage_4_channel.run(self.ctx, qid, movie, content_type)
            else:
                channel = {"channel_id": state["channel_id"], "invite_link": state["invite_link"]}

            if resume_at <= 5:
                stage = 5
                await checkpoint(self.ctx,qid)
                await self.ctx.db.set_stage(qid, stage, "assigning_channel_admins")
                await stage_5_promote.prepare_channel(
                    self.ctx, qid, channel["channel_id"], format_template(self.ctx.cfg.channel_name, movie=movie, owner_username=self.ctx.cfg.owner_username)
                )

            if resume_at <= 6:
                stage = 6
                await checkpoint(self.ctx,qid)
                await self.ctx.db.set_stage(qid, stage, "copying")
                copied = await stage_6_copy.run(self.ctx, qid, movie, channel["channel_id"], fetched)
            else:
                copied = self._json(state, "forwarded_message_ids_json")

            if resume_at <= 7:
                stage = 7
                await checkpoint(self.ctx,qid)
                await self.ctx.db.set_stage(qid, stage, "batching")
                batch = await stage_7_batch.run(self.ctx, qid, channel["channel_id"], copied)
            else:
                batch = state["batch_link"]

            if resume_at <= 8:
                stage = 8
                await checkpoint(self.ctx,qid)
                await self.ctx.db.set_stage(qid, stage, "shortening")
                batch_short = await stage_8_shorten.run(self.ctx, qid, batch)
            else:
                batch_short = state["shortened_link"] or batch

            if resume_at <= 9:
                stage = 9
                await checkpoint(self.ctx,qid)
                await self.ctx.db.set_stage(qid, stage, "backing_up_and_posting")
                await backup_movie(self.ctx,qid,movie,channel["channel_id"],copied,batch)
                await stage_9_post.run(self.ctx, qid, movie, channel["channel_id"], copied, batch_short)

            # Jobs that previously failed in cataloging may have a legacy
            # userbot-authored post without a working inline keyboard. Repair
            # Stage 9 with the control bot before retrying Stage 10.
            if resume_at == 10:
                await stage_5_promote.add_control_bot_admin(
                    self.ctx, qid, channel["channel_id"]
                )
                await stage_9_post.run(
                    self.ctx, qid, movie, channel["channel_id"], copied, batch_short
                )

            latest_state=await self.ctx.db.state(qid)
            if ((await self.ctx.db.setting("auto_catalog", "true")).lower() == "true" and resume_at <= 10
                    and not bool(latest_state and latest_state["catalog_added"])):
                stage = 10
                await checkpoint(self.ctx,qid)
                await self.ctx.db.set_stage(qid, stage, "cataloging")
                await stage_10_catalog.run(self.ctx, qid, movie, channel["invite_link"], fetched[0]["source_message_id"])

            await checkpoint(self.ctx,qid)
            await self.ctx.db.set_stage(qid,10,"promoting")
            await run_promotion(self.ctx,qid,movie,channel["channel_id"],channel["invite_link"])
            await checkpoint(self.ctx,qid)
            await self.ctx.db.complete(qid)
            await self.ctx.db.finalize_channel(channel["channel_id"], batch, batch_short)
            await self.ctx.db.log(f"Completed {movie}", "INFO", qid)
            await notify_control_bot(self.ctx.cfg.control_token, self.ctx.cfg.owner_id, f'✅ Completed: {movie}\n{channel["invite_link"]}')
            await self._persist_state()
        except DeferredFloodWait as exc:
            reason=f"Telegram cooldown active for {exc.seconds}s; job automatically deferred at stage {stage}"
            await self.ctx.db.defer_floodwait(qid,exc.seconds,reason)
            if stage==4:
                await self.ctx.db.set_setting("channel_creation_cooldown_until",str(int(time.time())+exc.seconds))
            await self.ctx.db.log(reason,"WARNING",qid)
            await self._persist_state()
            try:
                hours,remainder=divmod(exc.seconds,3600);minutes,seconds=divmod(remainder,60)
                duration=(f"{hours}h {minutes}m" if hours else f"{minutes}m {seconds}s")
                await notify_control_bot(self.ctx.cfg.control_token,self.ctx.cfg.owner_id,
                    f"⏳ Telegram cooldown: {movie}\nStage {stage}/10 deferred for {duration}.\nThe worker will continue with other batch items and retry this movie automatically.")
            except Exception:pass
        except JobCancelled as exc:
            await self.ctx.db.log(str(exc),"INFO",qid);await self._persist_state()
            try:await notify_control_bot(self.ctx.cfg.control_token,self.ctx.cfg.owner_id,f"🛑 Cancelled: {movie}")
            except Exception:pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            text=str(exc).lower()
            # If Telegram has made the just-created source channel inaccessible,
            # resume from channel creation instead of leaving a batch item failed.
            # Earlier search/fetch results remain valid and are reused.
            state_now=await self.ctx.db.state(qid)
            broken_channel=(state_now['channel_id'] if state_now else None)
            if broken_channel and stage in (6,7) and ('channel_private' in text or 'channel private' in text):
                await self.ctx.db.remove_channel(int(broken_channel))
                await self.ctx.db.patch_state(
                    qid,channel_id=None,invite_link=None,owner_promoted=0,
                    forwarded_message_ids_json=[],batch_link=None,shortened_link=None,
                    final_post_id=None,backup_done=0,backup_message_ids_json=[],
                    catalog_added=0,promotion_done=0,promotion_link=None,
                    promotion_post_id=None,promotion_sticker_id=None,
                )
                await self.ctx.db.set_stage(qid,4,'pending')
                await self.ctx.db.log('Created channel became inaccessible; safely recreating it from the saved fetched files','WARNING',qid)
                await self._persist_state()
                try:await notify_control_bot(self.ctx.cfg.control_token,self.ctx.cfg.owner_id,f'♻️ Recreating inaccessible channel for {movie}; fetched files were preserved.')
                except Exception:pass
                return
            log.exception("Pipeline failed for %s", movie)
            await self.ctx.db.fail(qid, str(exc))
            await self.ctx.db.log(str(exc), "ERROR", qid)
            await self._persist_state()
            try:
                await notify_control_bot(self.ctx.cfg.control_token, self.ctx.cfg.owner_id, f"❌ Failed: {movie}\nStage {stage}/10\n{str(exc)[:700]}")
            except Exception:
                pass
