"""Create or update the final post and remove temporary channel media."""
from __future__ import annotations
import asyncio
from datetime import datetime
from pipeline.context import PipelineContext
from utils.notifications import send_download_post, edit_download_post, bot_api_request

async def _post_exists(ctx: PipelineContext, channel_id: int, message_id: int | None) -> bool:
    if not message_id:
        return False
    try:
        message = await ctx.client.get_messages(channel_id, int(message_id))
        return bool(message and message.id and not getattr(message, "empty", False))
    except Exception:
        return False

async def _remove_pin_notification(ctx: PipelineContext, qid: int, channel_id: int, post_id: int) -> None:
    """Delete Telegram's automatic 'pinned a message' service notification."""
    for _ in range(6):
        service_ids = []
        async for message in ctx.client.get_chat_history(channel_id, limit=8):
            if message.id >= post_id and message.id != post_id and (
                getattr(message, "service", None) or getattr(message, "pinned_message", None)
            ):
                service_ids.append(message.id)
        if service_ids:
            await ctx.speed.call(lambda: ctx.client.delete_messages(channel_id, service_ids), qid)
            await ctx.db.log("Deleted automatic pin notification message", "INFO", qid)
            return
        await asyncio.sleep(0.5)

async def run(
    ctx: PipelineContext,
    qid: int,
    movie: str,
    channel_id: int,
    copied_files: list[dict],
    link: str,
) -> int:
    quality_order = {"480p": 0, "720p": 1, "1080p": 2, "2160p": 3}
    qualities = sorted({item["quality"] for item in copied_files}, key=lambda q: quality_order.get(q, 99))
    episodes = {(item.get("season"), item.get("episode")) for item in copied_files if item.get("episode") is not None}
    text = (
        f"🎬 {movie}\n\n"
        f"🔊 Audio: Hindi\n"
        f"⚡ Available Qualities: {' | '.join(qualities)}\n"
        + (f"📺 Episodes: {len(episodes)}\n" if episodes else "")
        + f"📅 Added: {datetime.now().strftime('%d %B %Y')}\n\n"
        "👇 Tap the button below to download 👇"
    )
    if ctx.cfg.owner_username:
        text += f"\n\n📢 Powered by @{ctx.cfg.owner_username}"

    state = await ctx.db.state(qid)
    existing_id = int(state["final_post_id"]) if state and state["final_post_id"] else None
    if await _post_exists(ctx, channel_id, existing_id):
        try:
            await edit_download_post(
                ctx.cfg.control_token, channel_id, existing_id, text, link, ctx.cfg.tutorial_link,
            )
            post_id = existing_id
            await ctx.db.log("Existing download post updated in place; no duplicate sent", "INFO", qid)
        except Exception:
            # Migrate a legacy userbot-authored post that the control bot cannot
            # edit: remove it first, then create exactly one replacement.
            await bot_api_request(ctx.cfg.control_token, "deleteMessage", {
                "chat_id": channel_id, "message_id": existing_id,
            })
            post_id = await send_download_post(
                ctx.cfg.control_token, channel_id, text, link, ctx.cfg.tutorial_link,
            )
            await ctx.db.patch_state(qid, final_post_id=post_id)
            await _remove_pin_notification(ctx, qid, channel_id, post_id)
            await ctx.db.log("Legacy post replaced without leaving a duplicate", "INFO", qid)
    else:
        post_id = await send_download_post(
            ctx.cfg.control_token, channel_id, text, link, ctx.cfg.tutorial_link,
        )
        await ctx.db.patch_state(qid, final_post_id=post_id)
        await ctx.db.log("Control bot created and pinned inline-button download post", "INFO", qid)
        try:
            await _remove_pin_notification(ctx, qid, channel_id, post_id)
        except Exception as exc:
            await ctx.db.log(f"Pin-notification cleanup failed: {exc}", "WARNING", qid)

    # Also clean a notification left by an earlier attempt when this run only
    # edited the existing post.
    try:
        await _remove_pin_notification(ctx, qid, channel_id, post_id)
    except Exception as exc:
        await ctx.db.log(f"Pin-notification cleanup failed: {exc}", "WARNING", qid)

    # Stage 7 has already created the batch. Cleanup is idempotent on retries.
    media_ids = [int(item["channel_message_id"]) for item in copied_files]
    if media_ids:
        try:
            await ctx.speed.call(lambda: ctx.client.delete_messages(channel_id, media_ids), qid)
            await ctx.db.log(f"Deleted {len(media_ids)} temporary media messages from channel", "INFO", qid)
        except Exception as exc:
            await ctx.db.log(f"Media cleanup failed: {exc}", "WARNING", qid)
    return post_id
