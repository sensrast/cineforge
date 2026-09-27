"""Wait for owner join, then assign administrators."""
from __future__ import annotations
import asyncio
import logging
import time
from pyrogram.handlers import ChatMemberUpdatedHandler
from pyrogram.types import ChatPrivileges
from pipeline.context import PipelineContext
from utils.notifications import notify_control_bot
log = logging.getLogger(__name__)

OWNER_PRIVILEGES = ChatPrivileges(
    can_change_info=True,
    can_post_messages=True,
    can_edit_messages=True,
    can_delete_messages=True,
    can_invite_users=True,
    can_restrict_members=True,
    can_pin_messages=True,
    can_promote_members=True,
    can_manage_video_chats=True,
)
FILESTORE_PRIVILEGES = ChatPrivileges(
    can_post_messages=True,
    can_edit_messages=True,
    can_delete_messages=True,
    can_invite_users=True,
)

async def promote_after_join(ctx: PipelineContext, qid: int, channel_id: int, title: str = "channel") -> None:
    """Wait until the owner joins, promote them, then add the file-store bot as admin."""
    me = await ctx.client.get_me()
    if me.id != ctx.cfg.owner_id:
        deadline = time.monotonic() + ctx.cfg.owner_join_timeout
        joined = False
        while time.monotonic() < deadline:
            try:
                member = await ctx.speed.call(lambda: ctx.client.get_chat_member(channel_id, ctx.cfg.owner_id), qid)
                status = str(member.status).lower()
                if not any(word in status for word in ("left", "banned", "kicked")):
                    joined = True
                    break
            except Exception as exc:
                # USER_NOT_PARTICIPANT is expected until the invite is opened.
                if "participant" not in str(exc).lower() and "peer" not in str(exc).lower():
                    log.debug("Waiting for owner join: %s", exc)
            await asyncio.sleep(3)
        if not joined:
            raise TimeoutError(f"Owner did not join the new channel within {ctx.cfg.owner_join_timeout} seconds")
        await ctx.speed.call(
            lambda: ctx.client.promote_chat_member(channel_id, ctx.cfg.owner_id, OWNER_PRIVILEGES), qid,
        )

    await ctx.db.patch_state(qid, owner_promoted=1)
    await ctx.db.log("Owner joined and was promoted", "INFO", qid)

    # Telegram channels reject adding a bot as an ordinary participant
    # (USER_BOT). editAdmin/promote adds it directly with administrator rights.
    try:
        await ctx.speed.call(
            lambda: ctx.client.promote_chat_member(channel_id, ctx.cfg.filestore_bot, FILESTORE_PRIVILEGES), qid,
        )
        await ctx.db.log("File-store bot added directly as administrator", "INFO", qid)
    except Exception as exc:
        raise RuntimeError(f"Could not add @{ctx.cfg.filestore_bot} as channel administrator: {exc}") from exc

    if me.id != ctx.cfg.owner_id:
        await notify_control_bot(ctx.cfg.control_token, ctx.cfg.owner_id, f"✅ You are now an administrator of {title}.")


def register(ctx: PipelineContext) -> None:
    """Fast-path promotion handler; the orchestrator also polls reliably."""
    async def handler(client, event):
        member = event.new_chat_member
        if not member or not member.user or member.user.id != ctx.cfg.owner_id:
            return
        row = await ctx.db.created_by_channel(event.chat.id)
        if not row:
            return
        try:
            await ctx.speed.call(
                lambda: client.promote_chat_member(event.chat.id, ctx.cfg.owner_id, OWNER_PRIVILEGES),
                row["queue_id"],
            )
            await ctx.db.patch_state(row["queue_id"], owner_promoted=1)
        except Exception:
            log.exception("Event-driven owner promotion failed; polling stage will retry")

    ctx.client.add_handler(ChatMemberUpdatedHandler(handler), group=-100)
