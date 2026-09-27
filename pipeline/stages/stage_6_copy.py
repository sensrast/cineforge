from pyrogram.enums import ParseMode
from pipeline.context import PipelineContext
async def run(ctx:PipelineContext,qid:int,movie:str,channel_id:int,files:list[dict])->list[dict]:
 order={'480p':0,'720p':1,'1080p':2,'2160p':3};out=[]
 for f in sorted(files,key=lambda x:order.get(x['quality'],99)):
  caption=ctx.cfg.caption.format(movie=movie,quality=f['quality'],owner_username=ctx.cfg.owner_username)
  copied=await ctx.speed.call(lambda f=f,c=caption:ctx.client.copy_message(channel_id,ctx.cfg.source_bot,f['source_message_id'],caption=c,parse_mode=ParseMode.MARKDOWN),qid)
  out.append({'quality':f['quality'],'channel_message_id':copied.id});await ctx.speed.delay()
 await ctx.db.patch_state(qid,forwarded_message_ids_json=out);return out
