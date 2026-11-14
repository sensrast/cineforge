"""Isolated subscriber-channel mirror: historical import plus future media sync."""
from __future__ import annotations
import asyncio,logging,os,re,tempfile,time
from pyrogram.handlers import MessageHandler
from pipeline.context import PipelineContext
from control.manual_upload import detect_quality,detect_episode,ORDER
from pipeline.stages.stage_5_promote import add_control_bot_admin,add_filestore_admin,wait_modern_batch_link as wait_modern_filestore_link,generate_modern_provider_link
from pipeline.stages.stage_10_catalog import run_mirror_anime
from pipeline.stages.common import ModernBatchResponseRequired,latest_id,wait_for_batch_link
from utils.notifications import send_channel_sticker,notify_control_bot,bot_api_request
from utils.github_store import persist_state
log=logging.getLogger(__name__)
_TASKS:set[asyncio.Task]=set();_REGISTERED=False
_HISTORY_LOCK=asyncio.Lock()
ANIME_FILESTORE_BOT='YcAnimefilesbot'
# Large season ranges need time to be committed by the file-store bot after it
# returns the deep link. Never delete the source channel range immediately.
BATCH_STORAGE_SETTLE_SECONDS=10
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

async def _sync_profile_photo(ctx:PipelineContext,source_chat_id:int,destination_chat_id:int):
 """Copy the small channel avatar; media files are never downloaded."""
 path=None
 try:
  chat=await ctx.client.get_chat(source_chat_id)
  if not chat.photo:return
  path=await ctx.client.download_media(chat.photo.big_file_id,file_name=os.path.join(tempfile.gettempdir(),f'mirror-{abs(source_chat_id)}.jpg'))
  if path:await ctx.client.set_chat_photo(destination_chat_id,photo=path)
 except Exception:log.warning('Could not copy source channel profile photo',exc_info=True)
 finally:
  if path:
   try:os.remove(path)
   except OSError:pass

def _display_title(title:str)->str:
 return re.sub(r'\s*(?:\(\s*(?:hindi\s+dubbed|in\s+hindi)\s*\)|(?:hindi\s+dubbed|in\s+hindi))(?:\s+available)?\s*$','',title or '',flags=re.I).strip()

def _channel_title(title:str)->str:
 if re.search(r'\bhindi\s+dubbed\b|\bin\s+hindi\b',title or '',re.I):return f'{_display_title(title)} In Hindi'
 return title.strip()

async def create_source(ctx:PipelineContext,source_chat_id:int,source_ref:str,title:str)->tuple[int,list[int],str]:
 existing=await ctx.db.db.fetchone('SELECT * FROM mirror_sources WHERE source_chat_id=?',(source_chat_id,))
 if existing:return int(existing['id']),await missing_seasons(ctx,int(existing['id'])),existing['invite_link'] or ''
 channel_title=_channel_title(title)
 channel=await ctx.speed.call(lambda:ctx.client.create_channel(channel_title,f'Mirrored media from {title}'),None)
 invite=await ctx.speed.call(lambda:ctx.client.export_chat_invite_link(channel.id),None)
 source_id=await ctx.db.db.execute("INSERT INTO mirror_sources(source_chat_id,source_ref,source_title,destination_chat_id,invite_link,status) VALUES(?,?,?,?,?,'scanning')",(source_chat_id,source_ref,title,channel.id,invite))
 await ctx.db.db.execute("INSERT OR IGNORE INTO created_channels(queue_id,movie_name,content_type,channel_id,invite_link) VALUES(NULL,?,'mirror',?,?)",(title,channel.id,invite))
 await add_control_bot_admin(ctx,None,channel.id);await add_filestore_admin(ctx,None,channel.id,ANIME_FILESTORE_BOT)
 await _sync_profile_photo(ctx,source_chat_id,channel.id)
 await scan_history(ctx,source_id)
 seasons=await missing_seasons(ctx,source_id)
 await ctx.db.db.execute("UPDATE mirror_sources SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",('awaiting_stickers' if seasons else 'awaiting_end_sticker',source_id))
 await persist_state(ctx.db)
 await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f'✅ Mirror destination created for {title}:\n{invite}')
 return source_id,seasons,invite

def _saved_template(value:str)->str:
 return (value or '').replace('\\\\n','\n').replace('\\n','\n').replace('\\\\_','\\_')

def _connected_episode(text:str,title:str)->tuple[int|None,int|None,int|None]:
 season,episode=detect_episode(text or '')
 if season is None:
  match=re.search(r'\bS(?:eason)?\s*[-: ]*\s*(\d{1,2})\b',text or '',re.I)
  if match:season=int(match.group(1))
 if episode is None:
  match=re.search(r'\bEpisode\s*[-: ]*\s*(\d{1,3})\b',text or '',re.I)
  if match:episode=int(match.group(1))
 overall=None
 for pattern in (r'\[\s*(\d{3})\s*\]',r'\b(?:episode|ep)\s*[:#-]?\s*E?(\d{3})\b',r'\bE(\d{3})\b'):
  match=re.search(pattern,text or '',re.I)
  if match:overall=int(match.group(1));break
 if overall is None and episode and episode>=100:overall=episode
 # Naruto Shippuden Season 18 starts at overall episode 373. This lets the
 # connected-channel scanner understand both E373 and S18E01 naming styles.
 if overall is None and 'naruto' in (title or '').lower() and season==18 and episode:
  overall=372+episode
 if overall and episode and episode>=100 and 'naruto' in (title or '').lower() and overall>=373:
  season,episode=18,overall-372
 return season,episode,overall

async def _process_connected_destination(ctx:PipelineContext,source_id:int)->None:
 try:
  row=await ctx.db.db.fetchone('SELECT * FROM mirror_sources WHERE id=?',(source_id,));channel=int(row['destination_chat_id'])
  target=int(row['sync_limit_episode'] or 0);caption_template=_saved_template(await ctx.db.setting('mirror_file_caption_template',CAPTION))
  final_template=_saved_template(await ctx.db.setting('mirror_final_post_template',''));total=int(await ctx.db.setting('mirror_total_episodes','500'))
  candidates=[]
  async for message in ctx.client.get_chat_history(channel):
   media=_media(message)
   if not media:continue
   text=(message.caption or '')+' '+_file_name(message);season,episode,overall=_connected_episode(text,row['source_title'])
   if overall==target:candidates.append({'message':message,'season':season or 18,'episode':episode or 1,'quality':detect_quality(text),'size':int(getattr(media,'file_size',0) or 0)})
  if not candidates:
   # The connected destination may be empty or one episode behind. In that
   # case copy only the explicitly confirmed episode from the source, never
   # the entire historical channel.
   source_items=[]
   async for message in ctx.client.get_chat_history(int(row['source_chat_id'])):
    media=_media(message)
    if not media:continue
    text=(message.caption or '')+' '+_file_name(message);season,episode,overall=_connected_episode(text,row['source_title'])
    if overall==target:source_items.append({'message':message,'season':season or 18,'episode':episode or max(1,target-372),'quality':detect_quality(text),'size':int(getattr(media,'file_size',0) or 0)})
   source_ranked=sorted(source_items,key=lambda item:(item['size'],item['message'].id));labels=['480p','720p','1080p','2160p']
   for index,item in enumerate(source_ranked):
    if not item['quality']:item['quality']=labels[min(index,len(labels)-1)]
   for item in sorted(source_ranked,key=lambda value:value['message'].id):
    caption=caption_template.format(title='Naruto',season=item['season'],episode=item['episode'],quality=item['quality'],overall_episode=target,total_episodes=total)
    copied=await ctx.client.copy_message(channel,int(row['source_chat_id']),item['message'].id,caption=caption)
    candidates.append({**item,'message':copied})
  if not candidates:raise RuntimeError(f'Episode {target} was found in neither the destination nor the source channel')
  ranked=sorted(candidates,key=lambda item:(item['size'],item['message'].id));labels=['480p','720p','1080p','2160p']
  for index,item in enumerate(ranked):
   if not item['quality']:item['quality']=labels[min(index,len(labels)-1)]
  for item in sorted(ranked,key=lambda value:value['message'].id):
   caption=caption_template.format(title='Naruto',season=item['season'],episode=item['episode'],quality=item['quality'],overall_episode=target,total_episodes=total)
   await ctx.client.edit_message_caption(channel,item['message'].id,caption=caption)
  ordered=sorted(ranked,key=lambda item:item['message'].id);before=await latest_id(ctx.client,ANIME_FILESTORE_BOT)
  await ctx.client.send_message(ANIME_FILESTORE_BOT,'/batch');await asyncio.sleep(2)
  await ctx.client.forward_messages(ANIME_FILESTORE_BOT,channel,ordered[0]['message'].id);await asyncio.sleep(2)
  await ctx.client.forward_messages(ANIME_FILESTORE_BOT,channel,ordered[-1]['message'].id)
  try:batch_link=await wait_for_batch_link(ctx.client,ANIME_FILESTORE_BOT,before,ctx.cfg.flow_timeout,1200)
  except ModernBatchResponseRequired:batch_link=await wait_modern_filestore_link(ctx,ANIME_FILESTORE_BOT,before,1200)
  season=int(ordered[0]['season']);episode=int(ordered[0]['episode'])
  final_text=final_template.format(title='Naruto Shippuden',season=season,episode=episode,overall_episode=target,total_episodes=total)
  result=await bot_api_request(ctx.cfg.control_token,'sendMessage',{'chat_id':channel,'text':final_text,'parse_mode':'Markdown','disable_web_page_preview':True,'reply_markup':{'inline_keyboard':[[{'text':'❐ 𝗪𝗮𝘁𝗰𝗵/𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 ❐','url':batch_link}]]}})
  final_id=int(result['message_id']);update_id=None
  image=await ctx.db.setting('mirror_updates_image','');updates=await ctx.db.setting('mirror_updates_channel','-1002072936982')
  if not image:raise RuntimeError('Anime Promotion Image is not configured in Settings → Source Mirror Profiles')
  provider=(await ctx.db.setting('promotion_link_provider','Yclinkproviderbot')).lstrip('@');temporary=await bot_api_request(ctx.cfg.control_token,'sendPhoto',{'chat_id':channel,'photo':image,'caption':f'Channel link 🔗 👇👇\n\n{row["invite_link"]}\n{row["invite_link"]}'})
  temporary_id=int(temporary['message_id']);await ctx.client.send_message('@'+provider,'/genlink');await asyncio.sleep(1);provider_before=await latest_id(ctx.client,'@'+provider)
  await ctx.client.forward_messages('@'+provider,channel,temporary_id)
  generated=await generate_modern_provider_link(ctx,provider,provider_before,max(120,ctx.cfg.flow_timeout))
  updates_template=_saved_template(await ctx.db.setting('mirror_updates_post_template','🍎 {title}\n\n🥳 season {season} episode {episode} Added ....!🌟'))
  summary=updates_template.format(title='Naruto Shippuden',season=season,episode=episode)
  updates_text=(f'<b>{summary.splitlines()[0]}</b>\n\n'
                f'<blockquote><b>{" ".join(summary.splitlines()[1:]).strip()}</b></blockquote>\n\n'
                f'<a href="{generated}">Click here to start and get episode</a>\n'
                f'<a href="{generated}">Click here to start and get episode</a>')
  update=await bot_api_request(ctx.cfg.control_token,'sendMessage',{'chat_id':updates,'text':updates_text,'parse_mode':'HTML','disable_web_page_preview':True});update_id=int(update['message_id'])
  try:await bot_api_request(ctx.cfg.control_token,'deleteMessage',{'chat_id':channel,'message_id':temporary_id})
  except Exception:pass
  await ctx.db.db.execute("UPDATE mirror_sources SET status='paused',current_season=?,current_episode=?,initial_batch_link=?,initial_final_post_id=?,initial_update_post_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(season,episode,batch_link,final_id,update_id,source_id));await persist_state(ctx.db)
  await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f'✅ Connected destination processed episode {target}. Future source episodes remain paused until your confirmation.')
 except Exception as exc:
  log.exception('Connected destination setup failed');await ctx.db.db.execute("UPDATE mirror_sources SET status='failed',updated_at=CURRENT_TIMESTAMP WHERE id=?",(source_id,));await persist_state(ctx.db);await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f'❌ Connected destination setup failed: {exc}')

async def process_connected_episode(ctx:PipelineContext,source_id:int,overall_episode:int)->None:
 row=await ctx.db.db.fetchone('SELECT connection_mode FROM mirror_sources WHERE id=?',(source_id,))
 if not row or row['connection_mode']!='existing':raise RuntimeError('This is not a connected-destination profile.')
 await ctx.db.db.execute("UPDATE mirror_sources SET sync_limit_episode=?,status='processing_existing',initial_batch_link=NULL,initial_final_post_id=NULL,initial_update_post_id=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(int(overall_episode),source_id));await persist_state(ctx.db)
 _spawn(_process_connected_destination(ctx,source_id),f'mirror-connected-{source_id}-{overall_episode}')

async def connect_existing_source(ctx:PipelineContext,source_chat_id:int,source_ref:str,title:str,destination_chat_id:int)->tuple[int,str]:
 existing=await ctx.db.db.fetchone('SELECT id FROM mirror_sources WHERE source_chat_id=?',(source_chat_id,))
 if existing:raise RuntimeError('This source is already connected. Remove its old Source Mirror profile first.')
 destination=await ctx.client.get_chat(destination_chat_id);invite=await ctx.client.export_chat_invite_link(destination_chat_id)
 target=int(await ctx.db.setting('mirror_initial_episode','373'))
 source_id=await ctx.db.db.execute("INSERT INTO mirror_sources(source_chat_id,source_ref,source_title,destination_chat_id,invite_link,status,connection_mode,sync_limit_episode) VALUES(?,?,?,?,?,'processing_existing','existing',?)",(source_chat_id,source_ref,title,destination_chat_id,invite,target))
 await add_control_bot_admin(ctx,None,destination_chat_id);await add_filestore_admin(ctx,None,destination_chat_id,ANIME_FILESTORE_BOT);await persist_state(ctx.db)
 _spawn(_process_connected_destination(ctx,source_id),f'mirror-connected-{source_id}')
 return source_id,invite

async def scan_history(ctx:PipelineContext,source_id:int)->None:
 row=await ctx.db.db.fetchone('SELECT * FROM mirror_sources WHERE id=?',(source_id,));items=[]
 async for message in ctx.client.get_chat_history(int(row['source_chat_id'])):
  media=_media(message)
  if not media:continue
  # Caption metadata wins over filenames: source filenames are sometimes stale
  # (for example "season 04" while the caption correctly says "S03").
  caption=message.caption or '';name=_file_name(message)
  season,episode=detect_episode(caption)
  if episode is None:season,episode=detect_episode(name)
  quality=detect_quality(caption) or detect_quality(name)
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

async def _send_season_start(ctx,row,season:int)->int:
 sticker=await ctx.db.db.fetchone('SELECT sticker_file_id FROM mirror_season_stickers WHERE source_id=? AND season=?',(row['id'],season))
 if not sticker:raise RuntimeError(f'Season {season} sticker is not configured')
 return await send_channel_sticker(ctx.cfg.control_token,int(row['destination_chat_id']),sticker['sticker_file_id'])

async def _send_season_end(ctx,row,season:int)->int:
 if not row['end_sticker_file_id']:raise RuntimeError('End-of-Season sticker is not configured')
 return await send_channel_sticker(ctx.cfg.control_token,int(row['destination_chat_id']),row['end_sticker_file_id'])

async def _create_season_batch(ctx,row,start_id:int,end_id:int)->tuple[str,float]:
 """Store one complete season and timestamp the final boundary forward."""
 chat=ANIME_FILESTORE_BOT;before=await latest_id(ctx.client,chat)
 await ctx.speed.call(lambda:ctx.client.send_message(chat,'/batch'),None)
 await asyncio.sleep(2)
 await ctx.speed.call(lambda:ctx.client.forward_messages(chat,int(row['destination_chat_id']),start_id),None)
 await asyncio.sleep(2)
 await ctx.speed.call(lambda:ctx.client.forward_messages(chat,int(row['destination_chat_id']),end_id),None)
 last_forwarded_at=time.monotonic()
 try:link=await wait_for_batch_link(ctx.client,chat,before,ctx.cfg.flow_timeout,1200)
 except ModernBatchResponseRequired:
  link=await wait_modern_filestore_link(ctx,chat,before,1200)
 return link,last_forwarded_at

def _season_post(title:str,season:int,last_episode:int)->str:
 return (f'✦ {_display_title(title)} ✦\n'
         '╔━━━━━━━━━━━━━━━━━━━━━╗\n'
         f'⌲ 𝗦𝗲𝗮𝘀𝗼𝗻 : {season}\n'
         f'❍ 𝗘𝗽𝗶𝘀𝗼𝗱𝗲: 1-{last_episode}\n'
         '〄 𝗔𝘂𝗱𝗶𝗼: Hindi\n'
         f'◎ 𝗧𝗼𝘁𝗮𝗹 𝗘𝗽𝗶𝘀𝗼𝗱𝗲𝘀: {last_episode}\n'
         '♡ 𝗣𝗼𝘄𝗲𝗿𝗲𝗱 𝗯𝘆: @YCAnime , @India_crunchyroll\n'
         '╚━━━━━━━━━━━━━━━━━━━━━╝')

async def _finalize_season(ctx,row,season:int,last_episode:int,start_id:int,end_id:int,batch_link:str,last_forwarded_at:float)->tuple[int,int,int]:
 channel=int(row['destination_chat_id'])
 # Use the mandatory storage window to create the compact final layout. These
 # new messages are after end_id, so deleting the temporary range cannot touch
 # them. Cleanup never begins until 10 seconds after forwarding the last item.
 sticker=await ctx.db.db.fetchone('SELECT sticker_file_id FROM mirror_season_stickers WHERE source_id=? AND season=?',(row['id'],season))
 final_start=await send_channel_sticker(ctx.cfg.control_token,channel,sticker['sticker_file_id'])
 result=await bot_api_request(ctx.cfg.control_token,'sendMessage',{
  'chat_id':channel,'text':_season_post(row['source_title'],season,last_episode),
  'reply_markup':{'inline_keyboard':[[{'text':'❐ 𝗪𝗮𝘁𝗰𝗵/𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 ❐','url':batch_link}]]},
  'disable_web_page_preview':True,
 })
 post_id=int(result['message_id'])
 final_end=await send_channel_sticker(ctx.cfg.control_token,channel,row['end_sticker_file_id'])
 remaining=BATCH_STORAGE_SETTLE_SECONDS-(time.monotonic()-last_forwarded_at)
 if remaining>0:await asyncio.sleep(remaining)
 ids=list(range(start_id,end_id+1))
 for index in range(0,len(ids),100):
  await ctx.client.delete_messages(channel,ids[index:index+100])
 await ctx.db.db.execute('INSERT INTO mirror_season_outputs(source_id,season,batch_link,start_sticker_message_id,final_post_message_id,end_sticker_message_id) VALUES(?,?,?,?,?,?) ON CONFLICT(source_id,season) DO UPDATE SET batch_link=excluded.batch_link,start_sticker_message_id=excluded.start_sticker_message_id,final_post_message_id=excluded.final_post_message_id,end_sticker_message_id=excluded.end_sticker_message_id',(row['id'],season,batch_link,final_start,post_id,final_end))
 return final_start,post_id,final_end

async def _pin_first_season(ctx,row)->None:
 first=await ctx.db.db.fetchone('SELECT start_sticker_message_id FROM mirror_season_outputs WHERE source_id=? ORDER BY season LIMIT 1',(row['id'],))
 if not first:return
 await bot_api_request(ctx.cfg.control_token,'pinChatMessage',{'chat_id':int(row['destination_chat_id']),'message_id':int(first['start_sticker_message_id']),'disable_notification':True})
 await asyncio.sleep(.5)
 ids=[]
 async for message in ctx.client.get_chat_history(int(row['destination_chat_id']),limit=6):
  if getattr(message,'service',None) or getattr(message,'pinned_message',None):ids.append(message.id)
 if ids:await ctx.client.delete_messages(int(row['destination_chat_id']),ids)

async def _publish_episode(ctx,row,season:int,episode:int,items:list[dict]):
 # Build one clean slot per quality. Reposts/alternate duplicates are reduced to
 # the largest file for that quality; ties keep the earliest source message.
 source_order=sorted(items,key=lambda item:int(item['source_message_id']))
 ranked=sorted(source_order,key=lambda item:(int(item.get('file_size') or 0),int(item['source_message_id'])))
 labels=['480p','720p','1080p','2160p']
 if len(ranked)==1:targets=['480p']
 elif len(ranked)==2:targets=['480p','720p']
 elif len(ranked)==3:targets=['480p','720p','1080p']
 else:targets=[labels[min(round(i*3/max(1,len(ranked)-1)),3)] for i in range(len(ranked))]
 for index,item in enumerate(ranked):
  if not item.get('quality'):item['quality']=targets[index]
 chosen={}
 for item in source_order:
  quality=item['quality'];old=chosen.get(quality)
  if old is None or int(item.get('file_size') or 0)>int(old.get('file_size') or 0):chosen[quality]=item
 ordered=sorted(chosen.values(),key=lambda item:(ORDER.get(item.get('quality'),99),int(item['source_message_id'])))
 await ctx.client.send_message(int(row['destination_chat_id']),f'📺 Episode {episode:02d}')
 for item in ordered:
  quality=item['quality'];caption=CAPTION.format(title=row['source_title'],season=season,quality=quality,episode=episode)
  try:await ctx.client.copy_message(int(row['destination_chat_id']),int(row['source_chat_id']),int(item['source_message_id']),caption=caption)
  except Exception as exc:
   if 'forwards_restricted' in str(exc).lower() or 'protected' in str(exc).lower():raise RuntimeError('Source channel has protected content; Telegram does not allow copying it') from exc
   raise
  await ctx.db.db.execute('INSERT OR REPLACE INTO mirror_slots(source_id,season,episode,quality,source_message_id) VALUES(?,?,?,?,?)',(row['id'],season,episode,quality,item['source_message_id']))
 for item in source_order:
  await ctx.db.db.execute('INSERT OR IGNORE INTO mirror_seen(source_id,source_message_id) VALUES(?,?)',(row['id'],item['source_message_id']))
  await ctx.db.db.execute('DELETE FROM mirror_pending WHERE source_id=? AND source_message_id=?',(row['id'],item['source_message_id']))

async def _sync_history_locked(ctx:PipelineContext,source_id:int):
 try:
  row=await ctx.db.db.fetchone('SELECT * FROM mirror_sources WHERE id=?',(source_id,))
  await add_filestore_admin(ctx,None,int(row['destination_chat_id']),ANIME_FILESTORE_BOT)
  groups=await ctx.db.db.fetchall('SELECT DISTINCT season,episode FROM mirror_pending WHERE source_id=? ORDER BY season,episode',(source_id,))
  seasons=sorted({int(group['season']) for group in groups});last_episode=0;final_sticker=None;total_episodes=len(groups)
  for season in seasons:
   start_id=await _send_season_start(ctx,row,season)
   season_groups=[group for group in groups if int(group['season'])==season]
   for group in season_groups:
    episode=int(group['episode']);items=[dict(x) for x in await ctx.db.db.fetchall('SELECT * FROM mirror_pending WHERE source_id=? AND season=? AND episode=? ORDER BY source_message_id',(source_id,season,episode))]
    await _publish_episode(ctx,row,season,episode,items);last_episode=episode
    await persist_state(ctx.db)
   end_id=await _send_season_end(ctx,row,season)
   batch_link,last_forwarded_at=await _create_season_batch(ctx,row,start_id,end_id)
   _,_,final_sticker=await _finalize_season(ctx,row,season,last_episode,start_id,end_id,batch_link,last_forwarded_at)
   await persist_state(ctx.db)
  latest=seasons[-1] if seasons else 0
  if seasons:await _pin_first_season(ctx,row)
  if seasons and not int(row['catalog_added'] or 0):
   await run_mirror_anime(ctx,row['source_title'],row['invite_link'],total_episodes)
   await ctx.db.db.execute('UPDATE mirror_sources SET catalog_added=1 WHERE id=?',(source_id,))
  await ctx.db.db.execute("UPDATE mirror_sources SET status='live',current_season=?,current_episode=?,current_end_sticker_message_id=?,current_end_text_message_id=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(latest,last_episode,final_sticker,source_id));await persist_state(ctx.db)

 except Exception as exc:
  log.exception('Historical source mirror failed');await ctx.db.db.execute("UPDATE mirror_sources SET status='failed',updated_at=CURRENT_TIMESTAMP WHERE id=?",(source_id,));await persist_state(ctx.db);await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f'❌ Mirror failed: {exc}')

async def sync_history(ctx:PipelineContext,source_id:int):
 # File-store bots support one /batch conversation at a time. Serializing
 # mirrors prevents different season endpoints from crossing each other.
 async with _HISTORY_LOCK:
  await _sync_history_locked(ctx,source_id)

def start_history(ctx,source_id):
 if not any(t.get_name()==f'mirror-history-{source_id}' for t in _TASKS):_spawn(sync_history(ctx,source_id),f'mirror-history-{source_id}')

async def restart_mirror(ctx:PipelineContext,source_id:int):
 """Clean a partial destination and rebuild it deterministically from message one."""
 try:
  row=await ctx.db.db.fetchone('SELECT * FROM mirror_sources WHERE id=?',(source_id,))
  try:await ctx.client.set_chat_title(int(row['destination_chat_id']),_channel_title(row['source_title']))
  except Exception as exc:
   if 'chat_not_modified' not in str(exc).lower():raise
  ids=[]
  async for message in ctx.client.get_chat_history(int(row['destination_chat_id'])):ids.append(message.id)
  for index in range(0,len(ids),100):
   if ids[index:index+100]:await ctx.client.delete_messages(int(row['destination_chat_id']),ids[index:index+100])
  await ctx.db.db.execute('DELETE FROM mirror_seen WHERE source_id=?',(source_id,));await ctx.db.db.execute('DELETE FROM mirror_pending WHERE source_id=?',(source_id,));await ctx.db.db.execute('DELETE FROM mirror_slots WHERE source_id=?',(source_id,));await ctx.db.db.execute('DELETE FROM mirror_season_outputs WHERE source_id=?',(source_id,))
  await _sync_profile_photo(ctx,int(row['source_chat_id']),int(row['destination_chat_id']))
  await scan_history(ctx,source_id)
  await ctx.db.db.execute("UPDATE mirror_sources SET status='syncing',current_season=0,current_episode=0,last_source_message_id=0,current_end_sticker_message_id=NULL,current_end_text_message_id=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(source_id,))
  await persist_state(ctx.db);start_history(ctx,source_id)
 except Exception as exc:
  log.exception('Source mirror restart failed');await ctx.db.db.execute("UPDATE mirror_sources SET status='failed' WHERE id=?",(source_id,));await persist_state(ctx.db);await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f'❌ Mirror restart failed: {exc}')

async def _flush_future(ctx,source_id,season,episode):
 await asyncio.sleep(300)
 row=await ctx.db.db.fetchone('SELECT * FROM mirror_sources WHERE id=?',(source_id,));items=[dict(x) for x in await ctx.db.db.fetchall('SELECT * FROM mirror_pending WHERE source_id=? AND season=? AND episode=? ORDER BY source_message_id',(source_id,season,episode))]
 if not items:return
 sticker=await ctx.db.db.fetchone('SELECT 1 FROM mirror_season_stickers WHERE source_id=? AND season=?',(source_id,season))
 if not sticker:
  await ctx.db.db.execute("UPDATE mirror_sources SET status='awaiting_stickers' WHERE id=?",(source_id,));await persist_state(ctx.db);await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f'📤 Upload the Season {season} sticker from Source Mirror panel; files are safely pending.');return
 current=int(row['current_season'] or 0);current_episode=int(row['current_episode'] or 0)
 # Never republish old-season reposts. A genuinely new episode requires a new
 # direct batch for its season, so rebuild the compact season layouts from the
 # authoritative source after the collection buffer closes.
 if season<current or (season==current and episode<=current_episode):
  for item in items:
   await ctx.db.db.execute('INSERT OR IGNORE INTO mirror_seen(source_id,source_message_id) VALUES(?,?)',(source_id,item['source_message_id']));await ctx.db.db.execute('DELETE FROM mirror_pending WHERE id=?',(item['id'],))
  await persist_state(ctx.db);return
 await restart_mirror(ctx,source_id)

async def _future_handler(ctx,client,message):
 media=_media(message)
 if not media:return
 row=await ctx.db.db.fetchone("SELECT * FROM mirror_sources WHERE source_chat_id=? AND status IN ('live','awaiting_stickers')",(message.chat.id,))
 if not row:return
 seen=await ctx.db.db.fetchone('SELECT 1 FROM mirror_seen WHERE source_id=? AND source_message_id=?',(row['id'],message.id))
 if seen:return
 caption=message.caption or '';name=_file_name(message);season,episode=detect_episode(caption)
 if episode is None:season,episode=detect_episode(name)
 quality=detect_quality(caption) or detect_quality(name);season=season or int(row['current_season'] or 1)
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
 rows=await ctx.db.db.fetchall("SELECT id,status FROM mirror_sources WHERE status IN ('restart','syncing','live','awaiting_stickers','awaiting_end_sticker','processing_existing')")
 for row in rows:
  if row['status']=='restart':_spawn(restart_mirror(ctx,int(row['id'])),f"mirror-restart-{row['id']}")
  elif row['status']=='syncing':start_history(ctx,int(row['id']))
  elif row['status']=='processing_existing':_spawn(_process_connected_destination(ctx,int(row['id'])),f"mirror-connected-{row['id']}")
  pending=await ctx.db.db.fetchall('SELECT DISTINCT season,episode FROM mirror_pending WHERE source_id=?',(row['id'],))
  if row['status']=='live':
   for item in pending:_spawn(_flush_future(ctx,int(row['id']),int(item['season']),int(item['episode'])),f"mirror-flush-{row['id']}-{item['season']}-{item['episode']}")

async def stop():
 for task in list(_TASKS):task.cancel()
 if _TASKS:await asyncio.gather(*list(_TASKS),return_exceptions=True)
 _TASKS.clear()
