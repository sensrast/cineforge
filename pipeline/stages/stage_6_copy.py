from pyrogram.enums import ParseMode
from pipeline.context import PipelineContext
from utils.text_parser import format_template
from utils.notifications import send_channel_sticker

async def run(ctx:PipelineContext,qid:int,movie:str,channel_id:int,files:list[dict])->list[dict]:
 order={'480p':0,'720p':1,'1080p':2,'2160p':3};out=[]
 stickers={q:await ctx.db.setting(f'sticker_{q}','') for q in ('480p','720p','1080p','2160p')}
 end_sticker=await ctx.db.setting('sticker_end','')
 missing=[q for q in ('480p','720p','1080p') if not stickers[q]]
 if missing or not end_sticker:
  needed=', '.join(missing + ([] if end_sticker else ['end']))
  raise RuntimeError(f'Configure required channel stickers first: {needed}')

 for f in sorted(files,key=lambda x:(x.get('season') or 0,x.get('episode') or 0,order.get(x['quality'],99))):
  sticker_id=stickers.get(f['quality'])
  pre_sticker_message_id=None
  if sticker_id:
   pre_sticker_message_id=await send_channel_sticker(ctx.cfg.control_token,channel_id,sticker_id)
  episode_label = f"S{int(f['season'] or 1):02d}E{int(f['episode']):02d}" if f.get('episode') is not None else ''
  caption=format_template(ctx.cfg.caption,movie=movie,quality=f['quality'],owner_username=ctx.cfg.owner_username,season=str(f.get('season') or ''),episode=str(f.get('episode') or ''),episode_label=episode_label)
  if episode_label and '{episode' not in ctx.cfg.caption.lower() and episode_label not in caption:
   caption += f"\n📺 **Episode:** {episode_label}"
  copied=await ctx.speed.call(lambda f=f,c=caption:ctx.client.copy_message(channel_id,ctx.cfg.source_bot,f['source_message_id'],caption=c,parse_mode=ParseMode.MARKDOWN),qid)
  out.append({'quality':f['quality'],'season':f.get('season'),'episode':f.get('episode'),'sticker_message_id':pre_sticker_message_id,'channel_message_id':copied.id})
  await ctx.speed.delay()
 end_message_id=await send_channel_sticker(ctx.cfg.control_token,channel_id,end_sticker)
 if out:out[-1]['end_sticker_message_id']=end_message_id
 await ctx.db.patch_state(qid,forwarded_message_ids_json=out);return out
