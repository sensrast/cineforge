"""Briefly use MTProto layer 229 while Pyrogram is offline to grant new rights."""
from __future__ import annotations
import asyncio,base64,struct
from telethon import TelegramClient
from telethon.crypto import AuthKey
from telethon.sessions import MemorySession
from telethon.tl.functions.channels import EditAdminRequest
from telethon.tl.types import ChatAdminRights

_DC={1:'149.154.175.53',2:'149.154.167.51',3:'149.154.175.100',4:'149.154.167.91',5:'91.108.56.130'}
_lock=asyncio.Lock()

def _session(value:str)->MemorySession:
 raw=base64.urlsafe_b64decode(value+'='*(-len(value)%4));dc,_api,_test,key,_uid,_bot=struct.unpack('>BI?256sQ?',raw)
 result=MemorySession();result.set_dc(dc,_DC[dc],443);result.auth_key=AuthKey(key);return result

def _rights()->ChatAdminRights:
 return ChatAdminRights(change_info=True,post_messages=True,edit_messages=True,delete_messages=True,
  ban_users=True,invite_users=True,pin_messages=True,add_admins=True,manage_call=True,other=True,
  manage_topics=True,post_stories=True,edit_stories=True,delete_stories=True,
  manage_direct_messages=True,manage_ranks=True,manage_linked_peers=True,manage_welcome_messages=True)

async def grant_control_bot_rights(cfg,channel_ids:list[int],bot_username:str)->dict[int,bool]:
 """Run only while every Pyrogram connection using this auth key is stopped."""
 results={int(cid):False for cid in channel_ids}
 if not results:return results
 async with _lock:
  client=TelegramClient(_session(cfg.session_string),cfg.api_id,cfg.api_hash,receive_updates=False)
  try:
   await client.connect()
   if not await client.is_user_authorized():raise RuntimeError('Layer-229 session is not authorized')
   # A memory session has no entity cache. Dialog enumeration supplies channel access hashes.
   entities={}
   async for dialog in client.iter_dialogs():entities[int(dialog.id)]=dialog.input_entity
   bot=await client.get_input_entity('@'+bot_username.lstrip('@'))
   for cid in results:
    try:
     channel=entities.get(cid) or await client.get_input_entity(cid)
     await client(EditAdminRequest(channel=channel,user_id=bot,admin_rights=_rights(),rank=''))
     results[cid]=True
    except Exception:results[cid]=False
  finally:await client.disconnect()
 return results
