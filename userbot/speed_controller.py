"""Runtime delays and Telegram-enforced FloodWait handling."""
from __future__ import annotations
import asyncio, inspect, logging
from collections.abc import Awaitable, Callable
from pyrogram.errors import FloodWait
from database.queries import Queries
log=logging.getLogger(__name__)
class SpeedController:
 def __init__(self,q:Queries): self.q=q
 async def delay(self,kind:str='action')->None:
  enabled=(await self.q.setting('limits_enabled','false')).lower()=='true'
  if not enabled:return
  key='delay_between_movies' if kind=='movie' else 'delay_between_actions'
  try: delay=max(0,float(await self.q.setting(key,'0')))
  except ValueError: delay=0
  if delay: await asyncio.sleep(delay)
 async def call(self,operation:Callable[[],Awaitable],qid:int|None=None):
  """Call a fresh coroutine factory, retrying exactly after Telegram FloodWait."""
  while True:
   try:
    result=operation();
    if not inspect.isawaitable(result): raise TypeError('operation must return awaitable')
    return await result
   except FloodWait as e:
    wait=int(e.value)+1; log.warning('FloodWait %ss',wait); await self.q.log(f'FloodWait {wait}s','WARNING',qid); await asyncio.sleep(wait)
