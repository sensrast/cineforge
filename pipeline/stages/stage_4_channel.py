import time
from pipeline.context import PipelineContext
from userbot.speed_controller import DeferredFloodWait
from utils.notifications import notify_control_bot
from utils.github_store import persist_state
from utils.text_parser import format_template
from pipeline.channel_folder import ensure_created_channels_folder

async def run(ctx: PipelineContext, qid: int, movie: str, content_type: str = "movie") -> dict:
    """Create the channel and send only its invite link to the owner.

    Owner and file-store administrator promotion intentionally happen in Stage
    5, after the owner has joined through this invite.
    """
    try:blocked_until=int(await ctx.db.setting("channel_creation_cooldown_until","0"))
    except ValueError:blocked_until=0
    remaining=blocked_until-int(time.time())
    if remaining>0:raise DeferredFloodWait(remaining)

    enabled = (await ctx.db.setting("limits_enabled", "false")).lower() == "true"
    maximum = int(await ctx.db.setting("max_channels_per_day", "0"))
    if enabled and maximum > 0 and await ctx.db.count_today() >= maximum:
        raise RuntimeError("Daily channel limit reached")

    state=await ctx.db.state(qid)
    channel_id=int(state["channel_id"]) if state and state["channel_id"] else None
    if channel_id:
        # A long FloodWait may have happened after create_channel succeeded but
        # before invite export. Resume that same channel instead of duplicating it.
        channel=await ctx.speed.call(lambda:ctx.client.get_chat(channel_id),qid)
    else:
        channel = await ctx.speed.call(
            lambda: ctx.client.create_channel(
                format_template(ctx.cfg.channel_name, movie=movie, owner_username=ctx.cfg.owner_username),
                format_template(ctx.cfg.channel_description, movie=movie, owner_username=ctx.cfg.owner_username),
            ), qid,
        )
        channel_id=channel.id
        await ctx.db.patch_state(qid,channel_id=channel_id)
    # Resolve/cache the channel before member updates arrive.
    await ctx.speed.call(lambda: ctx.client.get_chat(channel_id), qid)
    invite = await ctx.speed.call(lambda: ctx.client.export_chat_invite_link(channel_id), qid)
    await ctx.db.patch_state(qid, channel_id=channel_id, invite_link=invite)
    await ctx.db.register_channel(qid, movie, channel.id, invite, content_type)
    await persist_state(ctx.db)
    await ensure_created_channels_folder(ctx,[channel.id],qid)

    # Send through the control bot, which already has a private chat with the
    # owner. An MTProto account cannot always resolve an arbitrary numeric user
    # ID, whereas the private control bot can deliver this reliably.
    await notify_control_bot(ctx.cfg.control_token, ctx.cfg.owner_id, invite)
    await ctx.db.log("Channel created; invite sent through control bot; waiting for owner to join", "INFO", qid)
    return {"channel_id": channel.id, "invite_link": invite}
