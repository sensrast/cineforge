"""Dedicated premium-source workflow for Famp Underground -> @YC_Premium."""
from __future__ import annotations
import asyncio,logging,re,time
from urllib.parse import urlparse,parse_qs
import aiohttp
from pyrogram.handlers import MessageHandler
from pipeline.context import PipelineContext
from pipeline.stages.stage_5_promote import generate_modern_provider_link,resolve_modern_source_post
from pipeline.stages.stage_10_catalog import run_premium_catalog
from utils.github_store import persist_state
from utils.notifications import notify_control_bot
from utils.safe_dialogs import iter_dialogs
log=logging.getLogger(__name__)
URL_RE=re.compile(r'https?://[^\s<>]+',re.I)
_TASKS:set[asyncio.Task]=set();_REGISTERED=False

def _spawn(coro,name):
 task=asyncio.create_task(coro,name=name);_TASKS.add(task);task.add_done_callback(_TASKS.discard);return task

def _urls(message)->list[str]:
 values=URL_RE.findall(message.text or message.caption or '')
 if message.reply_markup and getattr(message.reply_markup,'inline_keyboard',None):
  for row in message.reply_markup.inline_keyboard:
   for button in row:
    if button.url:values.append(button.url)
 return [value.rstrip(').,]') for value in values]

def _deep_link(url:str)->tuple[str,str]|None:
 parsed=urlparse(url)
 if parsed.netloc.lower() not in {'t.me','telegram.me'}:return None
 bot=parsed.path.strip('/').split('/')[0]
 payload=parse_qs(parsed.query).get('start',[''])[0]
 return (bot,payload) if bot and payload else None

async def _hydrate_source(ctx,chat_id:int)->None:
 try:await ctx.client.resolve_peer(int(chat_id));return
 except Exception:pass
 async for dialog in iter_dialogs(ctx.client,limit=2000):
  if int(dialog.chat.id)==int(chat_id):return
 raise RuntimeError(f'Private source peer is unavailable after reconnect: {chat_id}')

async def _latest_id(client,chat)->int:
 async for message in client.get_chat_history(chat,limit=1):return message.id
 return 0

async def _activate_url(ctx,url:str):
 deep=_deep_link(url)
 if deep:
  await ctx.client.send_message(deep[0],'/start '+deep[1]);return
 timeout=aiohttp.ClientTimeout(total=30)
 async with aiohttp.ClientSession(timeout=timeout) as session:
  async with session.get(url,allow_redirects=True) as response:
   final=str(response.url);await response.read()
 if final!=url and (deep:=_deep_link(final)):await ctx.client.send_message(deep[0],'/start '+deep[1])

async def _bypass(ctx,row,shortlink:str)->str:
 chat=int(row['ddbypass_chat_id']);before=await _latest_id(ctx.client,chat)
 await ctx.client.send_message(chat,shortlink)
 deadline=time.monotonic()+300
 while time.monotonic()<deadline:
  async for message in ctx.client.get_chat_history(chat,limit=30):
   if message.id<=before or message.outgoing:continue
   for url in _urls(message):
    if url!=shortlink:return url
  await asyncio.sleep(5)
 raise TimeoutError('DDBypass did not return a destination URL within 5 minutes')

async def _request_content(ctx,row,source_link:str)->tuple[str,list[int]]:
 deep=_deep_link(source_link)
 if not deep:raise RuntimeError('Source post does not contain a Telegram bot start link')
 bot,payload=deep
 for attempt in range(2):
  before=await _latest_id(ctx.client,bot)
  await ctx.client.send_message(bot,'/start '+payload)
  deadline=time.monotonic()+max(60,ctx.cfg.flow_timeout);videos=[];refresh=None;last_video=None
  while time.monotonic()<deadline:
   async for message in ctx.client.get_chat_history(bot,limit=30):
    if message.id<=before or message.outgoing:continue
    if message.video or (message.document and (getattr(message.document,'mime_type','') or '').startswith('video/')):
     if message.id not in videos:videos.append(message.id);last_video=time.monotonic()
    urls=_urls(message)
    button_text=' '.join(button.text or '' for r in (message.reply_markup.inline_keyboard if message.reply_markup else []) for button in r).lower()
    body=(message.text or message.caption or '').lower()
    token_expired='token' in body and ('expired' in body or 'invalid' in body)
    external=next((url for url in urls if 't.me/' not in url.lower()),None)
    # Access bots often render “token expired” and “Click Here” in Unicode
    # small-cap glyphs, so ASCII keyword checks alone cannot identify them.
    if external and ('refresh' in button_text or 'token' in button_text or token_expired or not videos):
     refresh=external
   if videos and last_video and time.monotonic()-last_video>=8:return bot,sorted(videos)
   if refresh:break
   await asyncio.sleep(2)
  if videos:return bot,sorted(videos)
  if refresh and attempt==0:
   destination=await _bypass(ctx,row,refresh);await _activate_url(ctx,destination);await asyncio.sleep(2);continue
  raise RuntimeError('Content bot returned neither video files nor a usable refresh-token link')
 raise RuntimeError('Access-token refresh did not unlock the source post')

async def _store_videos(ctx,content_bot:str,video_ids:list[int])->str:
 provider='Premium_files_YC_bot';before=await _latest_id(ctx.client,provider)
 await ctx.client.send_message(provider,'/shortener');await asyncio.sleep(1)
 for message_id in video_ids:
  try:await ctx.client.forward_messages(provider,content_bot,message_id)
  except Exception as exc:
   if 'CHAT_FORWARDS_RESTRICTED' not in str(exc):raise
   await ctx.client.copy_message(provider,content_bot,message_id)
 return await generate_modern_provider_link(ctx,provider,before,180)

async def _nation_link(ctx,row,file_link:str)->str:
 provider='YC_NATION_BOT';before=await _latest_id(ctx.client,provider)
 await ctx.client.send_message(provider,'/genlink');await asyncio.sleep(1)
 await _hydrate_source(ctx,int(row['source_chat_id']))
 await ctx.client.copy_message(provider,int(row['source_chat_id']),int(row['source_message_id']),caption=file_link)
 return await generate_modern_provider_link(ctx,provider,before,180)

async def _publish_source_post(ctx,row,nation_link:str)->int:
 source=int(row['source_chat_id']);message_id=int(row['source_message_id']);destination=row['destination_chat']
 await _hydrate_source(ctx,source)
 message=await ctx.client.get_messages(source,message_id)
 if message.media_group_id:
  copied=await ctx.client.copy_media_group(destination,source,message_id,captions=nation_link)
  return int(copied[0].id)
 copied=await ctx.client.copy_message(destination,source,message_id,caption=nation_link)
 return int(copied.id)

async def _process(ctx,job_id:int):
 row=await ctx.db.db.fetchone('SELECT j.*,s.source_chat_id,s.destination_chat,s.ddbypass_chat_id,s.catalog_title FROM premium_jobs j JOIN premium_sources s ON s.id=j.source_id WHERE j.id=?',(job_id,))
 if not row:return
 try:
  await ctx.db.db.execute("UPDATE premium_jobs SET status='processing',error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(job_id,));await persist_state(ctx.db)
  content_bot,videos=await _request_content(ctx,row,row['source_link'])
  await ctx.db.db.execute('UPDATE premium_jobs SET content_bot=?,video_count=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(content_bot,len(videos),job_id))
  file_link=row['file_link'] or await _store_videos(ctx,content_bot,videos)
  await ctx.db.db.execute('UPDATE premium_jobs SET file_link=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(file_link,job_id));await persist_state(ctx.db)
  nation_link=row['nation_link'] or await _nation_link(ctx,row,file_link)
  await ctx.db.db.execute('UPDATE premium_jobs SET nation_link=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(nation_link,job_id));await persist_state(ctx.db)
  destination_id=int(row['destination_message_id'] or 0) or await _publish_source_post(ctx,row,nation_link)
  await ctx.db.db.execute('UPDATE premium_jobs SET destination_message_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(destination_id,job_id))
  if not int(row['catalog_added'] or 0):
   await run_premium_catalog(ctx,row['catalog_title'],row['destination_chat'],int(row['source_chat_id']),int(row['source_message_id']),len(videos))
  await ctx.db.db.execute("UPDATE premium_jobs SET status='completed',catalog_added=1,error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(job_id,));await ctx.db.db.execute('UPDATE premium_sources SET last_source_message_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(row['source_message_id'],row['source_id']));await persist_state(ctx.db)
  await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f"✅ Premium source post completed: {nation_link}")
 except Exception as exc:
  log.exception('Premium source workflow failed');await ctx.db.db.execute("UPDATE premium_jobs SET status='failed',error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(str(exc)[:1000],job_id));await persist_state(ctx.db)
  try:await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f'❌ Premium source failed: {exc}')
  except Exception:pass

async def _queue_message(ctx,source_row,message):
 links=[url for url in _urls(message) if _deep_link(url)];anchor=message
 if message.media_group_id:
  try:
   group=await ctx.client.get_media_group(message.chat.id,message.id)
   anchor=next((item for item in group if _urls(item)),group[0]);links=[url for url in _urls(anchor) if _deep_link(url)]
  except Exception:pass
 if not links:
  await asyncio.sleep(2)  # allow a new album to finish before Layer-229 lookup
  modern=await resolve_modern_source_post(ctx,int(source_row['source_chat_id']),int(message.id))
  if not modern:return
  await _hydrate_source(ctx,int(source_row['source_chat_id']))
  anchor=await ctx.client.get_messages(int(source_row['source_chat_id']),int(modern['message_id']))
  links=[modern['link']]
 job_id=await ctx.db.db.execute("INSERT OR IGNORE INTO premium_jobs(source_id,source_message_id,media_group_id,source_link,status) VALUES(?,?,?,?, 'pending')",(source_row['id'],anchor.id,str(anchor.media_group_id or ''),links[0]))
 existing=await ctx.db.db.fetchone('SELECT id,status FROM premium_jobs WHERE source_id=? AND source_message_id=?',(source_row['id'],anchor.id))
 if existing and existing['status'] in ('pending','processing') and not any(t.get_name()==f"premium-{existing['id']}" for t in _TASKS):
  await persist_state(ctx.db);_spawn(_process(ctx,int(existing['id'])),f"premium-{existing['id']}")

async def register(ctx:PipelineContext):
 global _REGISTERED
 rows=await ctx.db.db.fetchall("SELECT * FROM premium_sources WHERE status='live'")
 # Older private source channels may sit beyond the first 500 dialogs. Hydrate
 # their access hashes explicitly before any numeric-ID history request.
 unresolved={int(row['source_chat_id']) for row in rows}
 for chat_id in list(unresolved):
  try:await ctx.client.resolve_peer(chat_id);unresolved.discard(chat_id)
  except Exception:pass
 if unresolved:
  async for dialog in iter_dialogs(ctx.client,limit=2000):
   unresolved.discard(int(dialog.chat.id))
   if not unresolved:break
 if unresolved:raise RuntimeError('Premium source channel is not present in the user session dialogs: '+','.join(map(str,unresolved)))
 if not _REGISTERED:
  async def handler(client,message):
   row=await ctx.db.db.fetchone("SELECT * FROM premium_sources WHERE source_chat_id=? AND status='live'",(message.chat.id,))
   if row:await _queue_message(ctx,row,message)
  ctx.client.add_handler(MessageHandler(handler),group=-80);_REGISTERED=True
 for row in rows:
  pending=await ctx.db.db.fetchall("SELECT id FROM premium_jobs WHERE source_id=? AND status IN ('pending','processing')",(row['id'],))
  for job in pending:_spawn(_process(ctx,int(job['id'])),f"premium-{job['id']}")
  if not pending and int(row['last_source_message_id'] or 0)==0:
   async for message in ctx.client.get_chat_history(int(row['source_chat_id']),limit=100):
    await _queue_message(ctx,row,message);break

async def stop():
 for task in list(_TASKS):task.cancel()
 if _TASKS:await asyncio.gather(*list(_TASKS),return_exceptions=True)
 _TASKS.clear()
