"""Network-safe Pyrogram dialog iterator for peer-cache hydration."""
from __future__ import annotations
from types import SimpleNamespace
from pyrogram import raw,types,utils

async def iter_dialogs(client,limit:int=500):
 """Yield lightweight dialogs without recursively fetching replied-to messages.

 Pyrogram 2.0.106's normal iterator crashes on empty channels and may call
 channels.GetMessages while parsing reply metadata from unrelated stale/private
 dialogs. CineForge only needs chat identity/title/type and a pagination anchor,
 so this parser intentionally performs no secondary message requests.
 """
 current=0;total=limit or (1<<31)-1;page_limit=min(100,total)
 offset_date=0;offset_id=0;offset_peer=raw.types.InputPeerEmpty();seen=set()
 while current<total:
  result=await client.invoke(raw.functions.messages.GetDialogs(
   offset_date=offset_date,offset_id=offset_id,offset_peer=offset_peer,
   limit=min(page_limit,total-current),hash=0),sleep_threshold=60)
  users={item.id:item for item in result.users};chats={item.id:item for item in result.chats}
  message_anchors={}
  for message in result.messages:
   if isinstance(message,raw.types.MessageEmpty):continue
   message_anchors[utils.get_peer_id(message.peer_id)]=SimpleNamespace(id=message.id,date=message.date)
  dialogs=[]
  for dialog in result.dialogs:
   if not isinstance(dialog,raw.types.Dialog):continue
   chat=types.Chat._parse_dialog(client,dialog.peer,users,chats)
   chat_id=utils.get_peer_id(dialog.peer)
   dialogs.append(SimpleNamespace(chat=chat,top_message=message_anchors.get(chat_id)))
  if not dialogs:return
  anchor=next((dialog for dialog in reversed(dialogs) if dialog.top_message is not None),None)
  for dialog in dialogs:
   if dialog.chat.id in seen:continue
   seen.add(dialog.chat.id);yield dialog;current+=1
   if current>=total:return
  if anchor is None:return
  offset_id=anchor.top_message.id
  offset_date=utils.datetime_to_timestamp(anchor.top_message.date)
  offset_peer=await client.resolve_peer(anchor.chat.id)
