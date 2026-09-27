from pyrogram.types import ChatPrivileges
from pipeline.context import PipelineContext
async def run(ctx:PipelineContext,qid:int,movie:str)->dict:
 enabled=(await ctx.db.setting('limits_enabled','false')).lower()=='true'; maximum=int(await ctx.db.setting('max_channels_per_day','0'))
 if enabled and maximum>0 and await ctx.db.count_today()>=maximum:raise RuntimeError('Daily channel limit reached')
 channel=await ctx.speed.call(lambda:ctx.client.create_channel(ctx.cfg.channel_name.format(movie=movie),ctx.cfg.channel_description.format(movie=movie,owner_username=ctx.cfg.owner_username)),qid)
 try:await ctx.speed.call(lambda:ctx.client.add_chat_members(channel.id,ctx.cfg.filestore_bot),qid)
 except Exception as e:
  if 'already' not in str(e).lower():raise
 await ctx.speed.call(lambda:ctx.client.promote_chat_member(channel.id,ctx.cfg.filestore_bot,ChatPrivileges(can_post_messages=True,can_edit_messages=True,can_delete_messages=True,can_invite_users=True)),qid)
 invite=await ctx.speed.call(lambda:ctx.client.export_chat_invite_link(channel.id),qid)
 await ctx.db.patch_state(qid,channel_id=channel.id,invite_link=invite)
 await ctx.db.register_channel(qid,movie,channel.id,invite)
 await ctx.speed.call(lambda:ctx.client.send_message(ctx.cfg.owner_id,f'🎬 New channel: **{channel.title}**\n\n{invite}\n\nJoin to receive administrator access.'),qid)
 return {'channel_id':channel.id,'invite_link':invite}
