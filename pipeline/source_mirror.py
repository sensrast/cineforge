"""Isolated subscriber-channel mirror: historical import plus future media sync."""
from __future__ import annotations
import asyncio,logging,re
from pyrogram.handlers import MessageHandler
from pipeline.context import PipelineContext
from control.manual_upload import detect_quality,detect_episode,ORDER
from pipeline.stages.stage_5_promote import add_control_bot_admin,add_filestore_admin
from utils.notifications import send_channel_sticker,notify_control_bot
from utils.github_store import persist_state
log=logging.getLogger(__name__)
_TASKS:set[asyncio.Task]=set();_REGISTERED=False
CAPTION="""‣ {title} (S - {season})
╭────────────────────
┣Quality: {quality}
┣Episode: {episode:02d}
┣Audio: Hindi #O𝖿𝖿𝗂𝖼𝗂𝖺𝗅
╰────────────────────
‣ Powered By: @india_crunchyroll @YCAnime"""

def _media(message):return message.document or message.video

def _file_name(message):
 media=_media(message);return (getattr(media,'file_name',None) or message.caption or '') if media else ''

def _spawn(coro,name):
 task=asyncio.create_task(coro,name=name);_TASKS.add(task);task.add_done_callback(_TASKS.discard);return task

async def create_source(ctx:PipelineContext,source_chat_id:int,source_ref:str,title:str)->tuple[int,list[int],str]:
 existing=await ctx.db.db.fetchone('SELECT * FROM mirror_sources WHERE source_chat_id=?',(source_chat_id,))
 if existing:return int(existing['id']),await missing_seasons(ctx,int(existing['id'])),existing['invite_link'] or ''
 channel=await ctx.speed.call(lambda:ctx.client.create_channel(title,f'Mirrored media from {title}'),None)
 invite=await ctx.speed.call(lambda:ctx.client.export_chat_invite_link(channel.id),None)
 source_id=await ctx.db.db.execute("INSERT INTO mirror_sources(source_chat_id,source_ref,source_title,destination_chat_id,invite_link,status) VALUES(?,?,?,?,?,'scanning')",(source_chat_id,source_ref,title,channel.id,invite))
 await ctx.db.db.execute("INSERT OR IGNORE INTO created_channels(queue_id,movie_name,content_type,channel_id,invite_link) VALUES(NULL,?,'mirror',?,?)",(title,channel.id,invite))
 await add_control_bot_admin(ctx,None,channel.id);await add_filestore_admin(ctx,None,channel.id)
 await scan_history(ctx,source_id)
 seasons=await missing_seasons(ctx,source_id)
 await ctx.db.db.execute("UPDATE mirror_sources SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",('awaiting_stickers' if seasons else 'awaiting_end_sticker',source_id))
 await persist_state(ctx.db)
 await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f'✅ Mirror destination created for {title}:\n{invite}')
 return source_id,seasons,invite

async def scan_history(ctx:PipelineContext,source_id:int)->None:
 row=await ctx.db.db.fetchone('SELECT * FROM mirror_sources WHERE id=?',(source_id,));items=[]
 async for message in ctx.client.get_chat_history(int(row['source_chat_id'])):
  media=_media(message)
  if not media:continue
  text=_file_name(message)+' '+(message.caption or '')
  season,episode=detect_episode(text);quality=detect_quality(text)
  items.append({'message_id':message.id,'season':season,'episode':episode,'quality':quality,'file_size':int(getattr(media,'file_size',0) or 0),'file_name':_file_name(message)})
 items.reverse();current_season=1;current_episode=0;last_rank=-1
 for item in items:
  season=item['season'] or current_season;quality=item['quality'];rank=ORDER.get(quality,-1)
  if item['episode'] is not None:episode=item['episode']
  else:
   if current_episode==0:current_episode=1
   elif rank<0 or rank<=last_rank:current_episode+=1
   episode=current_episode
  current_season=season;current_episode=episode;last_rank=rank
  await ctx.db.db.execute("INSERT OR IGNORE INTO mirror_pending(source_id,source_message_id,season,episode,quality,file_size,file_name,added_at) VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",(source_id,item['message_id'],season,episode,quality,item['file_size'],item['file_name']))

async def missing_seasons(ctx:PipelineContext,source_id:int)->list[int]:
 rows=await ctx.db.db.fetchall('SELECT DISTINCT season FROM mirror_pending WHERE source_id=? ORDER BY season',(source_id,));saved={int(r['season']) for r in await ctx.db.db.fetchall('SELECT season FROM mirror_season_stickers WHERE source_id=?',(source_id,))}
 return [int(r['season']) for r in rows if int(r['season']) not in saved]

async def save_season_sticker(ctx:PipelineContext,source_id:int,season:int,file_id:str)->list[int]:
 await ctx.db.db.execute('INSERT INTO mirror_season_stickers(source_id,season,sticker_file_id) VALUES(?,?,?) ON CONFLICT(source_id,season) DO UPDATE SET sticker_file_id=excluded.sticker_file_id',(source_id,season,file_id))
 missing=await missing_seasons(ctx,source_id)
 if not missing:
  await ctx.db.db.execute("UPDATE mirror_sources SET status=CASE WHEN end_sticker_file_id IS NULL THEN 'awaiting_end_sticker' ELSE 'syncing' END,updated_at=CURRENT_TIMESTAMP WHERE id=?",(source_id,))
  row=await ctx.db.db.fetchone('SELECT end_sticker_file_id FROM mirror_sources WHERE id=?',(source_id,))
  if row and row['end_sticker_file_id']:start_history(ctx,source_id)
 await persist_state(ctx.db);return missing

async def save_end_sticker(ctx:PipelineContext,source_id:int,file_id:str)->None:
 row=await ctx.db.db.fetchone('SELECT status,destination_chat_id FROM mirror_sources WHERE id=?',(source_id,))
 # A failed first pass may have left only season/header messages. Clear that
 # isolated destination so the retry truly starts at the first source media.
 if row and row['status']=='failed' and row['destination_chat_id']:
  ids=[]
  async for message in ctx.client.get_chat_history(int(row['destination_chat_id'])):ids.append(message.id)
  for index in range(0,len(ids),100):
   if ids[index:index+100]:await ctx.client.delete_messages(int(row['destination_chat_id']),ids[index:index+100])
 await ctx.db.db.execute("UPDATE mirror_sources SET end_sticker_file_id=?,status='syncing',current_season=0,current_episode=0,updated_at=CURRENT_TIMESTAMP WHERE id=?",(file_id,source_id))
 await persist_state(ctx.db);start_history(ctx,source_id)

async def _send_season_start(ctx,row,season:int):
 sticker=await ctx.db.db.fetchone('SELECT sticker_file_id FROM mirror_season_stickers WHERE source_id=? AND season=?',(row['id'],season))
 if not sticker:raise RuntimeError(f'Season {season} sticker is not configured')
 await send_channel_sticker(ctx.cfg.control_token,int(row['destination_chat_id']),sticker['sticker_file_id'])
 await ctx.client.send_message(int(row['destination_chat_id']),f'📺 Season {season}')

async def _send_season_end(ctx,row,season:int):
 sticker=row['end_sticker_file_id']
 if sticker:await send_channel_sticker(ctx.cfg.control_token,int(row['destination_chat_id']),sticker)
 await ctx.client.send_message(int(row['destination_chat_id']),f'✅ End of Season {season}')

async def _publish_episode(ctx,row,season:int,episode:int,items:list[dict]):
 # Preserve the source channel's exact oldest-to-newest message sequence.
 # Duplicate qualities are valid (alternate encodes/parts) and must not abort
 # the mirror. Only files without a label are inferred by relative size.
 ordered=sorted(items,key=lambda item:int(item['source_message_id']))
 unknown=sorted([item for item in ordered if not item.get('quality')],key=lambda item:(int(item.get('file_size') or 0),int(item['source_message_id'])))
 labels=['480p','720p','1080p','2160p']
 for index,item in enumerate(unknown):item['quality']=labels[min(index,len(labels)-1)]
 await ctx.client.send_message(int(row['destination_chat_id']),f'📺 Episode {episode:02d}')
 quality_stickers={q:await ctx.db.setting(f'sticker_{q}','') for q in ('480p','720p','1080p','2160p')}
 for item in ordered:
  quality=item['quality'];sticker=quality_stickers.get(quality)
  if sticker:await send_channel_sticker(ctx.cfg.control_token,int(row['destination_chat_id']),sticker)
  caption=CAPTION.format(title=row['source_title'],season=season,quality=quality,episode=episode)
  try:await ctx.client.copy_message(int(row['destination_chat_id']),int(row['source_chat_id']),int(item['source_message_id']),caption=caption)
  except Exception as exc:
   if 'forwards_restricted' in str(exc).lower() or 'protected' in str(exc).lower():raise RuntimeError('Source channel has protected content; Telegram does not allow copying it') from exc
   raise
  await ctx.db.db.execute('INSERT OR IGNORE INTO mirror_seen(source_id,source_message_id) VALUES(?,?)',(row['id'],item['source_message_id']))
  await ctx.db.db.execute('DELETE FROM mirror_pending WHERE source_id=? AND source_message_id=?',(row['id'],item['source_message_id']))

async def sync_history(ctx:PipelineContext,source_id:int):
 try:
  row=await ctx.db.db.fetchone('SELECT * FROM mirror_sources WHERE id=?',(source_id,))
  pending=[dict(x) for x in await ctx.db.db.fetchall('SELECT * FROM mirror_pending WHERE source_id=? ORDER BY source_message_id',(source_id,))]
  current_season=0;current_episode=0;buffer=[]
  for item in pending:
   season=int(item['season']);episode=int(item['episode'])
   if current_season==0:
    current_season=season;current_episode=episode;await _send_season_start(ctx,row,season)
   if (season,episode)!=(current_season,current_episode):
    if buffer:await _publish_episode(ctx,row,current_season,current_episode,buffer);buffer=[]
    if season!=current_season:
     await _send_season_end(ctx,row,current_season);await _send_season_start(ctx,row,season)
    current_season=season;current_episode=episode
   buffer.append(item)
  if buffer:await _publish_episode(ctx,row,current_season,current_episode,buffer)
  await ctx.db.db.execute("UPDATE mirror_sources SET status='live',current_season=?,current_episode=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(current_season,current_episode,source_id));await persist_state(ctx.db)
  await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f"✅ Historical mirror complete: {row['source_title']}\nFuture media will sync automatically.")
 except Exception as exc:
  log.exception('Historical source mirror failed');await ctx.db.db.execute("UPDATE mirror_sources SET status='failed',updated_at=CURRENT_TIMESTAMP WHERE id=?",(source_id,));await persist_state(ctx.db);await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f'❌ Mirror failed: {exc}')

def start_history(ctx,source_id):
 if not any(t.get_name()==f'mirror-history-{source_id}' for t in _TASKS):_spawn(sync_history(ctx,source_id),f'mirror-history-{source_id}')

async def _flush_future(ctx,source_id,season,episode):
 await asyncio.sleep(300)
 row=await ctx.db.db.fetchone('SELECT * FROM mirror_sources WHERE id=?',(source_id,));items=[dict(x) for x in await ctx.db.db.fetchall('SELECT * FROM mirror_pending WHERE source_id=? AND season=? AND episode=? ORDER BY file_size,id',(source_id,season,episode))]
 if not items:return
 sticker=await ctx.db.db.fetchone('SELECT 1 FROM mirror_season_stickers WHERE source_id=? AND season=?',(source_id,season))
 if not sticker:
  await ctx.db.db.execute("UPDATE mirror_sources SET status='awaiting_stickers' WHERE id=?",(source_id,));await persist_state(ctx.db);await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f'📤 Upload the Season {season} sticker from Source Mirror panel; files are safely pending.');return
 current=int(row['current_season'] or 0)
 if season!=current:
  if current:await _send_season_end(ctx,row,current)
  await _send_season_start(ctx,row,season)
 await _publish_episode(ctx,row,season,episode,items)
 await ctx.db.db.execute("UPDATE mirror_sources SET status='live',current_season=?,current_episode=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(season,episode,source_id));await persist_state(ctx.db)

async def _future_handler(ctx,client,message):
 media=_media(message)
 if not media:return
 row=await ctx.db.db.fetchone("SELECT * FROM mirror_sources WHERE source_chat_id=? AND status IN ('live','awaiting_stickers')",(message.chat.id,))
 if not row:return
 seen=await ctx.db.db.fetchone('SELECT 1 FROM mirror_seen WHERE source_id=? AND source_message_id=?',(row['id'],message.id))
 if seen:return
 text=_file_name(message)+' '+(message.caption or '');season,episode=detect_episode(text);quality=detect_quality(text);season=season or int(row['current_season'] or 1)
 if episode is None:
  pending=await ctx.db.db.fetchall('SELECT quality,episode FROM mirror_pending WHERE source_id=? AND season=? ORDER BY id',(row['id'],season));episode=int(row['current_episode'] or 0) or 1
  ranks=[ORDER.get(x['quality'],-1) for x in pending if int(x['episode'])==episode]
  if ranks and (ORDER.get(quality,-1)<0 or ORDER.get(quality,-1)<=max(ranks)):episode+=1
 await ctx.db.db.execute('INSERT OR IGNORE INTO mirror_pending(source_id,source_message_id,season,episode,quality,file_size,file_name) VALUES(?,?,?,?,?,?,?)',(row['id'],message.id,season,episode,quality,int(getattr(media,'file_size',0) or 0),_file_name(message)));await persist_state(ctx.db)
 name=f"mirror-flush-{row['id']}-{season}-{episode}"
 for task in list(_TASKS):
  if task.get_name()==name:task.cancel()
 _spawn(_flush_future(ctx,int(row['id']),season,episode),name)

async def register(ctx:PipelineContext):
 global _REGISTERED
 if not _REGISTERED:
  async def handler(client,message):await _future_handler(ctx,client,message)
  ctx.client.add_handler(MessageHandler(handler),group=-90);_REGISTERED=True
 rows=await ctx.db.db.fetchall("SELECT id,status FROM mirror_sources WHERE status IN ('syncing','live','awaiting_stickers')")
 for row in rows:
  if row['status']=='syncing':start_history(ctx,int(row['id']))
  pending=await ctx.db.db.fetchall('SELECT DISTINCT season,episode FROM mirror_pending WHERE source_id=?',(row['id'],))
  if row['status']=='live':
   for item in pending:_spawn(_flush_future(ctx,int(row['id']),int(item['season']),int(item['episode'])),f"mirror-flush-{row['id']}-{item['season']}-{item['episode']}")

async def stop():
 for task in list(_TASKS):task.cancel()
 if _TASKS:await asyncio.gather(*list(_TASKS),return_exceptions=True)
 _TASKS.clear()
