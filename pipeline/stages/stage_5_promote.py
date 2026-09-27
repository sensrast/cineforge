"""Non-blocking owner promotion and file-store administrator setup."""
from __future__ import annotations
import asyncio
import logging
import time
from pyrogram.enums import ChatMemberStatus
from pyrogram.handlers import ChatMemberUpdatedHandler
from pyrogram.types import ChatPrivileges
from pipeline.context import PipelineContext
from utils.notifications import notify_control_bot
log = logging.getLogger(__name__)

OWNER_PRIVILEGES = ChatPrivileges(
    can_change_info=True, can_post_messages=True, can_edit_messages=True,
    can_delete_messages=True, can_invite_users=True, can_restrict_members=True,
    can_pin_messages=True, can_promote_members=True, can_manage_video_chats=True,
)
FILESTORE_PRIVILEGES = ChatPrivileges(
    can_post_messages=True, can_edit_messages=True, can_delete_messages=True,
    can_invite_users=True,
)
_WATCHERS: set[asyncio.Task] = set()

async def add_filestore_admin(ctx: PipelineContext, qid: int, channel_id: int) -> None:
    """Resolve and add the file-store bot directly as a channel admin."""
    bot = await ctx.speed.call(lambda: ctx.client.get_users(ctx.cfg.filestore_bot), qid)
    try:
        await ctx.speed.call(
            lambda: ctx.client.promote_chat_member(channel_id, bot.id, FILESTORE_PRIVILEGES), qid,
        )
    except Exception as exc:
        if "already" not in str(exc).lower() and "admin" not in str(exc).lower():
            raise RuntimeError(f"Could not add @{ctx.cfg.filestore_bot} as channel administrator: {exc}") from exc
    await ctx.db.log("File-store bot added directly as administrator", "INFO", qid)

async def _find_owner(ctx: PipelineContext, channel_id: int):
    """Find the owner in channel participants and populate Pyrogram's peer cache."""
    async for member in ctx.client.get_chat_members(channel_id, limit=200):
        if member.user and member.user.id == ctx.cfg.owner_id:
            return member
    return None

async def _promote_owner(ctx: PipelineContext, qid: int, channel_id: int, title: str) -> bool:
    state = await ctx.db.state(qid)
    if state and state["owner_promoted"]:
        return True
    me = await ctx.client.get_me()
    if me.id == ctx.cfg.owner_id:
        await ctx.db.patch_state(qid, owner_promoted=1)
        return True
    member = await _find_owner(ctx, channel_id)
    if not member:
        return False
    if member.status not in {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR}:
        # Iterating members above caches the user's access hash, making the ID
        # resolvable even when the userbot had no prior private chat with them.
        await ctx.speed.call(
            lambda: ctx.client.promote_chat_member(channel_id, member.user.id, OWNER_PRIVILEGES), qid,
        )
    await ctx.db.patch_state(qid, owner_promoted=1)
    await ctx.db.log("Owner membership detected and administrator rights granted", "INFO", qid)
    await notify_control_bot(ctx.cfg.control_token, ctx.cfg.owner_id, f"✅ You are now an administrator of {title}.")
    return True

async def _owner_watcher(ctx: PipelineContext, qid: int, channel_id: int, title: str) -> None:
    """Promote the owner asynchronously without blocking content processing."""
    deadline = time.monotonic() + ctx.cfg.owner_join_timeout
    while time.monotonic() < deadline:
        try:
            if await _promote_owner(ctx, qid, channel_id, title):
                return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.debug("Background owner promotion check failed", exc_info=True)
        await asyncio.sleep(3)
    await ctx.db.log("Owner did not join before promotion watcher expired", "WARNING", qid)
    try:
        await notify_control_bot(
            ctx.cfg.control_token, ctx.cfg.owner_id,
            f"⚠️ Automatic admin promotion expired for {title}. Join the channel and use Retry if administrator access is still required.",
        )
    except Exception:
        log.exception("Could not notify owner about promotion timeout")

async def prepare_channel(ctx: PipelineContext, qid: int, channel_id: int, title: str) -> None:
    """Add the file-store bot and launch owner promotion without waiting."""
    await add_filestore_admin(ctx, qid, channel_id)
    task = asyncio.create_task(
        _owner_watcher(ctx, qid, channel_id, title),
        name=f"owner-promotion-{qid}",
    )
    _WATCHERS.add(task)
    task.add_done_callback(_WATCHERS.discard)
    await ctx.db.log("Owner promotion watcher started; pipeline continuing", "INFO", qid)


def register(ctx: PipelineContext) -> None:
    """Fast-path owner promotion on a membership update."""
    async def handler(client, event):
        member = event.new_chat_member
        if not member or not member.user or member.user.id != ctx.cfg.owner_id:
            return
        row = await ctx.db.created_by_channel(event.chat.id)
        if not row:
            return
        try:
            await _promote_owner(ctx, row["queue_id"], event.chat.id, event.chat.title or "channel")
        except Exception:
            log.exception("Event-driven owner promotion failed; background watcher will retry")

    ctx.client.add_handler(ChatMemberUpdatedHandler(handler), group=-100)
