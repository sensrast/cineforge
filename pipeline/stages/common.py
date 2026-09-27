from __future__ import annotations
import asyncio,time
from pyrogram.types import Message
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
    await message.click(row_i,col_i);return True
 return False
