"""Layer-229 MTProto admin-right updates using the existing Pyrogram auth key."""
from __future__ import annotations
import asyncio
import base64
import struct
from telethon import TelegramClient
from telethon.crypto import AuthKey
from telethon.sessions import MemorySession
from telethon.tl.functions.channels import EditAdminRequest
from telethon.tl.types import InputChannel,InputUser,ChatAdminRights

_DC={1:'149.154.175.53',2:'149.154.167.51',3:'149.154.175.100',4:'149.154.167.91',5:'91.108.56.130'}
_client:TelegramClient|None=None
_lock=asyncio.Lock()

def _memory_session(pyrogram_session:str)->MemorySession:
 raw=base64.urlsafe_b64decode(pyrogram_session+'='*(-len(pyrogram_session)%4))
 dc_id,_api_id,_test_mode,auth_key,_user_id,_is_bot=struct.unpack('>BI?256sQ?',raw)
 session=MemorySession();session.set_dc(dc_id,_DC[dc_id],443);session.auth_key=AuthKey(auth_key)
 return session

async def _client_for(cfg)->TelegramClient:
 global _client
 async with _lock:
  if _client and _client.is_connected():return _client
  session_string=cfg.session_string
  if not session_string:raise RuntimeError('Userbot session is unavailable for modern admin rights')
  _client=TelegramClient(_memory_session(session_string),cfg.api_id,cfg.api_hash,receive_updates=False)
  await _client.connect()
  if not await _client.is_user_authorized():raise RuntimeError('Modern-rights MTProto session is not authorized')
  return _client

async def grant_all_admin_rights(cfg,channel_peer,user_peer)->None:
 """Grant every Layer-229 channel admin right, including welcome messages."""
 client=await _client_for(cfg)
 channel=InputChannel(channel_id=int(channel_peer.channel_id),access_hash=int(channel_peer.access_hash))
 user=InputUser(user_id=int(user_peer.user_id),access_hash=int(user_peer.access_hash))
 rights=ChatAdminRights(
  change_info=True,post_messages=True,edit_messages=True,delete_messages=True,
  ban_users=True,invite_users=True,pin_messages=True,add_admins=True,anonymous=False,
  manage_call=True,other=True,manage_topics=True,post_stories=True,edit_stories=True,
  delete_stories=True,manage_direct_messages=True,manage_ranks=True,
  manage_linked_peers=True,manage_welcome_messages=True,
 )
 await client(EditAdminRequest(channel=channel,user_id=user,admin_rights=rights,rank=''))

async def disconnect()->None:
 global _client
 async with _lock:
  if _client:
   await _client.disconnect();_client=None
