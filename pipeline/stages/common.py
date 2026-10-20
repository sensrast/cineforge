from __future__ import annotations
import asyncio,re,time
from pyrogram.types import Message
from utils.text_parser import extract_batch_link
async def newest_after(client,chat_id,after_id:int,timeout:int,predicate=None)->Message:
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  async for m in client.get_chat_history(chat_id,limit=12):
   if m.id>after_id and (predicate is None or predicate(m)): return m
  await asyncio.sleep(.75)
 raise TimeoutError(f'No expected response from @{str(chat_id).lstrip("@")} in {timeout}s')
async def latest_id(client,chat_id)->int:
 async for m in client.get_chat_history(chat_id,limit=1):return m.id
 return 0

def batch_link_from_message(message:Message)->str|None:
 link=extract_batch_link(message.text or message.caption or '')
 if link:return link
 markup=getattr(message,'reply_markup',None)
 for row in (getattr(markup,'inline_keyboard',None) or []):
  for button in row:
   link=extract_batch_link(getattr(button,'url',None) or '')
   if link:return link
 return None

def is_batch_processing(message:Message)->bool:
 text=(message.text or message.caption or '').lower()
 return bool(re.search(r'process(?:ing)?|generat(?:e|ing)|creat(?:e|ing).*batch|prepar(?:e|ing)|please\s+wait',text))

async def wait_for_batch_link(client,chat_id,after_id:int,timeout:int,processing_timeout:int=1200)->str:
 """Accept an intermediate Processing response and follow its later edit/link."""
 deadline=time.monotonic()+max(5,int(timeout));processing_seen=False
 while time.monotonic()<deadline:
  async for message in client.get_chat_history(chat_id,limit=50):
   if message.id<=after_id:continue
   link=batch_link_from_message(message)
   if link:return link
   if is_batch_processing(message) and not processing_seen:
    processing_seen=True
    # File bots can take several minutes to index large ranges. Once they
    # explicitly acknowledge the job, do not mistake that state for failure.
    deadline=max(deadline,time.monotonic()+max(int(timeout),int(processing_timeout)))
  await asyncio.sleep(1)
 state=' after its Processing acknowledgement' if processing_seen else ''
 raise TimeoutError(f'No batch link from @{str(chat_id).lstrip("@")} in time{state}')

def buttons(message:Message)->list[dict]:
 out=[]
 markup=message.reply_markup
 if markup and getattr(markup,'inline_keyboard',None):
  for row in markup.inline_keyboard:
   for b in row:out.append({'text':b.text or '', 'callback_data':b.callback_data.decode(errors='ignore') if isinstance(b.callback_data,bytes) else b.callback_data,'url':b.url})
 return out
async def click_matching(message:Message,patterns:list[str])->bool:
 import re
 markup=message.reply_markup
 if not markup:return False
 for row_i,row in enumerate(markup.inline_keyboard):
  for col_i,b in enumerate(row):
   if any(re.search(p,b.text or '',re.I) or re.search(p,str(b.callback_data or ''),re.I) for p in patterns):
            # Pyrogram coordinates are x=column, y=row.
            await message.click(col_i, row_i);return True
 return False
