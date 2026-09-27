"""Owner promotion event handler registration."""
from __future__ import annotations
import logging
from pyrogram.handlers import ChatMemberUpdatedHandler
from pyrogram.types import ChatPrivileges
from pipeline.context import PipelineContext
log=logging.getLogger(__name__)
def register(ctx:PipelineContext)->None:
 async def handler(client,event):
  member=event.new_chat_member
  if not member or not member.user or member.user.id!=ctx.cfg.owner_id:return
  row=await ctx.db.created_by_channel(event.chat.id)
  if not row:return
  try:
   privileges=ChatPrivileges(can_change_info=True,can_post_messages=True,can_edit_messages=True,can_delete_messages=True,can_invite_users=True,can_restrict_members=True,can_pin_messages=True,can_promote_members=True,can_manage_video_chats=True)
   await ctx.speed.call(lambda:client.promote_chat_member(event.chat.id,ctx.cfg.owner_id,privileges),row['queue_id'])
   await ctx.db.patch_state(row['queue_id'],owner_promoted=1)
   await client.send_message(ctx.cfg.owner_id,f'✅ Administrator access granted in **{event.chat.title}**')
  except Exception:log.exception('Owner promotion failed')
 ctx.client.add_handler(ChatMemberUpdatedHandler(handler), group=-100)
