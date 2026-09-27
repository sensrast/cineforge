from pipeline.context import PipelineContext
from utils.notifications import notify_control_bot
from utils.github_store import persist_state

async def run(ctx: PipelineContext, qid: int, movie: str) -> dict:
    """Create the channel and send only its invite link to the owner.

    Owner and file-store administrator promotion intentionally happen in Stage
    5, after the owner has joined through this invite.
    """
    enabled = (await ctx.db.setting("limits_enabled", "false")).lower() == "true"
    maximum = int(await ctx.db.setting("max_channels_per_day", "0"))
    if enabled and maximum > 0 and await ctx.db.count_today() >= maximum:
        raise RuntimeError("Daily channel limit reached")

    channel = await ctx.speed.call(
        lambda: ctx.client.create_channel(
            ctx.cfg.channel_name.format(movie=movie),
            ctx.cfg.channel_description.format(movie=movie, owner_username=ctx.cfg.owner_username),
        ), qid,
    )
    # Resolve/cache the newly created peer before member updates arrive.
    await ctx.speed.call(lambda: ctx.client.get_chat(channel.id), qid)
    invite = await ctx.speed.call(lambda: ctx.client.export_chat_invite_link(channel.id), qid)
    await ctx.db.patch_state(qid, channel_id=channel.id, invite_link=invite)
    await ctx.db.register_channel(qid, movie, channel.id, invite)
    await persist_state(ctx.db)

    # Send through the control bot, which already has a private chat with the
    # owner. An MTProto account cannot always resolve an arbitrary numeric user
    # ID, whereas the private control bot can deliver this reliably.
    await notify_control_bot(ctx.cfg.control_token, ctx.cfg.owner_id, invite)
    await ctx.db.log("Channel created; invite sent through control bot; waiting for owner to join", "INFO", qid)
    return {"channel_id": channel.id, "invite_link": invite}
