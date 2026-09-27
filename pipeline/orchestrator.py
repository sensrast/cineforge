"""Persistent, resumable, single-worker ten-stage pipeline."""
from __future__ import annotations
import asyncio
import json
import logging
from pipeline.context import PipelineContext
from utils.notifications import notify_control_bot
from pipeline.stages import (
    stage_1_search, stage_2_filter, stage_3_fetch, stage_4_channel, stage_5_promote,
    stage_6_copy, stage_7_batch, stage_8_shorten, stage_9_post,
    stage_10_catalog,
)
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

    @staticmethod
    def _json(row, key: str) -> list:
        try:
            return json.loads(row[key] or "[]")
        except (TypeError, json.JSONDecodeError):
            return []

    async def process(self, row: dict) -> None:
        qid, movie = row["id"], row["movie_name"]
        resume_at = max(1, int(row.get("current_stage") or 1))
        stage = resume_at
        try:
            state = await self.ctx.db.state(qid)
            if resume_at <= 1:
                stage = 1
                await self.ctx.db.set_stage(qid, stage, "searching")
                source = await stage_1_search.run(self.ctx, qid, movie)
            else:
                source = self._json(state, "source_messages_json")

            if resume_at <= 2:
                stage = 2
                await self.ctx.db.set_stage(qid, stage, "filtering")
                selected = await stage_2_filter.run(self.ctx, qid, source)
            else:
                selected = self._json(state, "filtered_files_json")

            if resume_at <= 3:
                stage = 3
                await self.ctx.db.set_stage(qid, stage, "fetching")
                fetched = await stage_3_fetch.run(self.ctx, qid, selected)
            else:
                fetched = self._json(state, "fetched_files_json")

            if resume_at <= 4:
                stage = 4
                await self.ctx.db.set_stage(qid, stage, "creating_channel")
                channel = await stage_4_channel.run(self.ctx, qid, movie)
            else:
                channel = {"channel_id": state["channel_id"], "invite_link": state["invite_link"]}

            if resume_at <= 5:
                stage = 5
                await self.ctx.db.set_stage(qid, stage, "assigning_channel_admins")
                await stage_5_promote.prepare_channel(
                    self.ctx, qid, channel["channel_id"], self.ctx.cfg.channel_name.format(movie=movie)
                )

            if resume_at <= 6:
                stage = 6
                await self.ctx.db.set_stage(qid, stage, "copying")
                copied = await stage_6_copy.run(self.ctx, qid, movie, channel["channel_id"], fetched)
            else:
                copied = self._json(state, "forwarded_message_ids_json")

            if resume_at <= 7:
                stage = 7
                await self.ctx.db.set_stage(qid, stage, "batching")
                batch = await stage_7_batch.run(self.ctx, qid, channel["channel_id"], copied)
            else:
                batch = state["batch_link"]

            if resume_at <= 8:
                stage = 8
                await self.ctx.db.set_stage(qid, stage, "shortening")
                batch_short = await stage_8_shorten.run(self.ctx, qid, batch)
            else:
                batch_short = state["shortened_link"] or batch

            if resume_at <= 9:
                stage = 9
                await self.ctx.db.set_stage(qid, stage, "posting")
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

            if (await self.ctx.db.setting("auto_catalog", "true")).lower() == "true" and resume_at <= 10:
                stage = 10
                await self.ctx.db.set_stage(qid, stage, "cataloging")
                await stage_10_catalog.run(self.ctx, qid, movie, channel["invite_link"], fetched[0]["source_message_id"])

            await self.ctx.db.complete(qid)
            await self.ctx.db.log(f"Completed {movie}", "INFO", qid)
            await notify_control_bot(self.ctx.cfg.control_token, self.ctx.cfg.owner_id, f'✅ Completed: {movie}\n{channel["invite_link"]}')
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Pipeline failed for %s", movie)
            await self.ctx.db.fail(qid, str(exc))
            await self.ctx.db.log(str(exc), "ERROR", qid)
            try:
                await notify_control_bot(self.ctx.cfg.control_token, self.ctx.cfg.owner_id, f"❌ Failed: {movie}\nStage {stage}/10\n{str(exc)[:700]}")
            except Exception:
                pass
