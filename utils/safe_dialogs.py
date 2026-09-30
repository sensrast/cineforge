"""Pyrogram dialog iterator tolerant of empty channels with no top message."""
from __future__ import annotations
from pyrogram import raw,types,utils

async def iter_dialogs(client,limit:int=500):
 """Equivalent to Client.get_dialogs, without dereferencing a missing top_message."""
 current=0;total=limit or (1<<31)-1;page_limit=min(100,total)
 offset_date=0;offset_id=0;offset_peer=raw.types.InputPeerEmpty()
 while current<total:
  result=await client.invoke(raw.functions.messages.GetDialogs(
   offset_date=offset_date,offset_id=offset_id,offset_peer=offset_peer,
   limit=min(page_limit,total-current),hash=0),sleep_threshold=60)
  users={item.id:item for item in result.users};chats={item.id:item for item in result.chats};messages={}
  for message in result.messages:
   if isinstance(message,raw.types.MessageEmpty):continue
   chat_id=utils.get_peer_id(message.peer_id)
   messages[chat_id]=await types.Message._parse(client,message,users,chats)
  dialogs=[]
  for dialog in result.dialogs:
   if isinstance(dialog,raw.types.Dialog):dialogs.append(types.Dialog._parse(client,dialog,messages,users,chats))
  if not dialogs:return
  # Pyrogram 2.0.106 assumes the final dialog always has a top message. Newly
  # created empty channels violate that assumption. Paginate from the last
  # dialog that actually has a message, or stop if this page contains none.
  anchor=next((dialog for dialog in reversed(dialogs) if dialog.top_message is not None),None)
  for dialog in dialogs:
   yield dialog;current+=1
   if current>=total:return
  if anchor is None:return
  offset_id=anchor.top_message.id
  offset_date=utils.datetime_to_timestamp(anchor.top_message.date)
  offset_peer=await client.resolve_peer(anchor.chat.id)
