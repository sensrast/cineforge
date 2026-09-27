"""Create the final inline-button post and remove temporary channel media."""
from __future__ import annotations
from datetime import datetime
from pipeline.context import PipelineContext
from utils.notifications import send_download_post

async def run(
    ctx: PipelineContext,
    qid: int,
    movie: str,
    channel_id: int,
    copied_files: list[dict],
    link: str,
) -> int:
    qualities = [item["quality"] for item in copied_files]
    text = (
        f"🎬 {movie}\n\n"
        f"🔊 Audio: Hindi\n"
        f"⚡ Available Qualities: {' | '.join(qualities)}\n"
        f"📅 Added: {datetime.now().strftime('%d %B %Y')}\n\n"
        "👇 Tap the button below to download 👇"
    )
    if ctx.cfg.owner_username:
        text += f"\n\n📢 Powered by @{ctx.cfg.owner_username}"

    # User accounts cannot reliably attach Bot API URL keyboards. The control
    # bot is promoted in Stage 5 and creates/pins the final post instead.
    post_id = await send_download_post(
        ctx.cfg.control_token,
        channel_id,
        text,
        link,
        ctx.cfg.tutorial_link,
    )
    await ctx.db.patch_state(qid, final_post_id=post_id)
    await ctx.db.log("Control bot created and pinned inline-button download post", "INFO", qid)

    # Batch creation has already completed in Stage 7. Delete only the copied
    # media messages after the durable batch link and final post both exist.
    media_ids = [int(item["channel_message_id"]) for item in copied_files]
    if media_ids:
        try:
            await ctx.speed.call(lambda: ctx.client.delete_messages(channel_id, media_ids), qid)
            await ctx.db.log(f"Deleted {len(media_ids)} temporary media messages from channel", "INFO", qid)
        except Exception as exc:
            # Preserve the successful download post even if cleanup is denied.
            await ctx.db.log(f"Media cleanup failed: {exc}", "WARNING", qid)
    return post_id
