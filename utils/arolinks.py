from __future__ import annotations
import asyncio
import aiohttp
class AroLinks:
 def __init__(self,base_url:str,key:str): self.base_url,self.key=base_url,key
 async def shorten(self,url:str)->str:
  if not self.key:return url
  last='unknown error'
  for wait in (0,2,4):
   if wait: await asyncio.sleep(wait)
   try:
    timeout=aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as s:
     async with s.get(self.base_url,params={'api':self.key,'url':url,'format':'json'}) as r:
      data=await r.json(content_type=None)
      short=data.get('shortenedUrl') or data.get('shortened_url')
      if r.ok and short:return short
      last=str(data.get('message',data))
   except Exception as e:last=str(e)
  raise RuntimeError('AroLinks failed: '+last)
