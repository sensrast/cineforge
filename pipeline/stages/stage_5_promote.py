"""Permanent owner-admin reconciliation and integration-bot administrator setup."""
from __future__ import annotations
import asyncio
import logging
from pyrogram.handlers import ChatMemberUpdatedHandler
from pyrogram.types import ChatPrivileges
from pipeline.context import PipelineContext
from utils.notifications import notify_control_bot,get_control_bot_identity,bot_api_request
from utils.github_store import persist_state
from utils.modern_admin import grant_control_bot_rights
log=logging.getLogger(__name__)

OWNER_PRIVILEGES=ChatPrivileges(
 can_manage_chat=True,can_change_info=True,can_post_messages=True,can_edit_messages=True,
 can_delete_messages=True,can_invite_users=True,can_restrict_members=True,can_pin_messages=True,
 can_promote_members=True,can_manage_video_chats=True,
)
FILESTORE_PRIVILEGES=ChatPrivileges(can_manage_chat=True,can_post_messages=True,can_edit_messages=True,can_delete_messages=True,can_invite_users=True)
CONTROL_PRIVILEGES=ChatPrivileges(can_manage_chat=True,can_post_messages=True,can_edit_messages=True,can_delete_messages=True,can_invite_users=True,can_promote_members=True)
_WATCHERS:set[asyncio.Task]=set()
_RECONCILER:asyncio.Task|None=None

async def _grant_modern_botapi_rights(ctx:PipelineContext,qid:int|None,channel_id:int,user_id:int,full:bool=False)->bool:
 payload={
  'chat_id':channel_id,'user_id':user_id,'can_manage_chat':True,'can_post_messages':True,
  'can_edit_messages':True,'can_delete_messages':True,'can_invite_users':True,
  'can_send_welcome_messages':True,'can_manage_direct_messages':True,
 }
 if full:payload.update({
  'can_change_info':True,'can_restrict_members':True,'can_pin_messages':True,
  'can_promote_members':True,'can_manage_video_chats':True,'can_manage_topics':True,
  'can_post_stories':True,'can_edit_stories':True,'can_delete_stories':True,
 })
 try:
  await bot_api_request(ctx.cfg.control_token,'promoteChatMember',payload);return True
 except Exception as exc:
  await ctx.db.log(f'Modern welcome-message permission pass was rejected: {exc}','WARNING',qid);return False

async def add_filestore_admin(ctx:PipelineContext,qid:int,channel_id:int)->int:
 bot=await ctx.speed.call(lambda:ctx.client.get_users(ctx.cfg.filestore_bot),qid)
 try:await ctx.speed.call(lambda:ctx.client.promote_chat_member(channel_id,bot.id,FILESTORE_PRIVILEGES),qid)
 except Exception as exc:
  if 'already' not in str(exc).lower() and 'admin' not in str(exc).lower():raise RuntimeError(f'Could not add @{ctx.cfg.filestore_bot} as channel administrator: {exc}') from exc
 await ctx.db.log('File-store bot added directly as administrator','INFO',qid);return bot.id

async def add_control_bot_admin(ctx:PipelineContext,qid:int,channel_id:int)->int:
 identity=await get_control_bot_identity(ctx.cfg.control_token);username=identity.get('username')
 if not username:raise RuntimeError('Control bot has no username and cannot be resolved by the userbot')
 bot=await ctx.speed.call(lambda:ctx.client.get_users(username),qid)
 try:await ctx.speed.call(lambda:ctx.client.promote_chat_member(channel_id,bot.id,CONTROL_PRIVILEGES),qid)
 except Exception as exc:
  if 'already' not in str(exc).lower() and 'admin' not in str(exc).lower():raise RuntimeError(f'Could not add @{username} as channel administrator: {exc}') from exc
 await ctx.db.log('Control bot added as administrator for inline-button posts','INFO',qid);return bot.id

async def _modernize_control_bot(ctx:PipelineContext,qid:int,channel_id:int,username:str)->bool:
 """Switch layers only while Pyrogram is offline; shared auth keys cannot mix layers."""
 await ctx.client.stop()
 try:
  result=await grant_control_bot_rights(ctx.cfg,[channel_id],username,ctx.cfg.owner_id)
  return bool(result.get(channel_id))
 finally:
  await ctx.client.start()
  # Restarting an in-memory Pyrogram client clears its peer cache. Rehydrate
  # every dialog so numeric channel IDs (including backup storage) remain usable.
  async for _dialog in ctx.client.get_dialogs(limit=500):
   pass

async def _find_owner(ctx:PipelineContext,channel_id:int):
 async for member in ctx.client.get_chat_members(channel_id,limit=500):
  if member.user and member.user.id==ctx.cfg.owner_id:return member
 return None

async def _promote_owner(ctx:PipelineContext,qid:int|None,channel_id:int,title:str,notify:bool=True)->bool:
 me=await ctx.client.get_me()
 if me.id==ctx.cfg.owner_id:return True
 member=await _find_owner(ctx,channel_id)
 if not member:return False
 # Always reapply privileges, even when Telegram already labels the owner as an
 # administrator. This repairs incomplete/expired admin-right assignments.
 modern_granted=await _grant_modern_botapi_rights(ctx,qid,channel_id,member.user.id,full=True)
 if not modern_granted:
  await ctx.speed.call(lambda:ctx.client.promote_chat_member(channel_id,member.user.id,OWNER_PRIVILEGES),qid)
 check=await bot_api_request(ctx.cfg.control_token,'getChatMember',{'chat_id':channel_id,'user_id':member.user.id})
 verified=bool(check.get('result',{}).get('can_send_welcome_messages'))
 row=await ctx.db.created_by_channel(channel_id);was_confirmed=bool(row and row['owner_admin_confirmed'])
 await ctx.db.db.execute('UPDATE created_channels SET owner_admin_confirmed=? WHERE channel_id=?',(int(verified),channel_id))
 if not verified:
  await ctx.db.log('Owner is admin but Manage Welcome Messages is still missing; reconciliation will retry','WARNING',qid)
  return False
 if qid is not None:await ctx.db.patch_state(qid,owner_promoted=1)
 await ctx.db.log('Owner membership detected; all administrator rights verified, including Manage Welcome Messages','INFO',qid)
 if notify and not was_confirmed:
  await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f'✅ You are now a full administrator of {title}.')
 return True

async def _one_shot_owner_check(ctx:PipelineContext,qid:int,channel_id:int,title:str)->None:
 try:await _promote_owner(ctx,qid,channel_id,title)
 except asyncio.CancelledError:raise
 except Exception:log.debug('Immediate owner promotion check failed; permanent reconciler will retry',exc_info=True)

async def _reconciliation_loop(ctx:PipelineContext)->None:
 """Forever repair owner rights on every accessible registered channel."""
 while True:
  changed=False
  try:
   rows=await ctx.db.db.fetchall('SELECT * FROM created_channels WHERE channel_id IS NOT NULL ORDER BY id')
   for row in rows:
    try:
     before=bool(row['owner_admin_confirmed'])
     promoted=await _promote_owner(ctx,row['queue_id'],int(row['channel_id']),row['movie_name'] or 'channel',notify=False)
     if promoted and not before:changed=True
    except asyncio.CancelledError:raise
    except Exception as exc:
     await ctx.db.log(f"Permanent owner-admin check failed for {row['movie_name']}: {exc}",'WARNING',row['queue_id'])
   if changed:await persist_state(ctx.db)
  except asyncio.CancelledError:raise
  except Exception:log.exception('Permanent owner-admin reconciliation pass failed')
  try:interval=max(15,int(await ctx.db.setting('owner_admin_reconcile_interval','60')))
  except ValueError:interval=60
  await asyncio.sleep(interval)

async def prepare_channel(ctx:PipelineContext,qid:int,channel_id:int,title:str)->None:
 filestore_id=await add_filestore_admin(ctx,qid,channel_id);control_id=await add_control_bot_admin(ctx,qid,channel_id)
 identity=await get_control_bot_identity(ctx.cfg.control_token);username=identity.get('username','')
 if not username or not await _modernize_control_bot(ctx,qid,channel_id,username):
  await ctx.db.log('Could not grant the control bot Layer-229 welcome-message rights; permanent reconciliation remains active','WARNING',qid)
 await _grant_modern_botapi_rights(ctx,qid,channel_id,control_id,full=True)
 await _grant_modern_botapi_rights(ctx,qid,channel_id,filestore_id)
 task=asyncio.create_task(_one_shot_owner_check(ctx,qid,channel_id,title),name=f'owner-promotion-{qid}')
 _WATCHERS.add(task);task.add_done_callback(_WATCHERS.discard)
 await ctx.db.log('Permanent owner promotion tracking active; pipeline continuing','INFO',qid)

async def stop_watchers()->None:
 global _RECONCILER
 tasks=list(_WATCHERS)
 if _RECONCILER:tasks.append(_RECONCILER)
 for task in tasks:task.cancel()
 if tasks:await asyncio.gather(*tasks,return_exceptions=True)
 _WATCHERS.clear();_RECONCILER=None

def register(ctx:PipelineContext)->None:
 global _RECONCILER
 async def handler(client,event):
  member=event.new_chat_member
  if not member or not member.user or member.user.id!=ctx.cfg.owner_id:return
  row=await ctx.db.created_by_channel(event.chat.id)
  if not row:return
  try:
   await _promote_owner(ctx,row['queue_id'],event.chat.id,event.chat.title or row['movie_name'] or 'channel')
   await persist_state(ctx.db)
  except Exception:log.exception('Event-driven owner promotion failed; permanent reconciler will retry')
 ctx.client.add_handler(ChatMemberUpdatedHandler(handler),group=-100)
 if not _RECONCILER or _RECONCILER.done():
  _RECONCILER=asyncio.create_task(_reconciliation_loop(ctx),name='permanent-owner-admin-reconciler')
