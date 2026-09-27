from __future__ import annotations
from datetime import datetime,timezone
from pipeline.context import PipelineContext
from pipeline.stages.common import latest_id,newest_after
async def run(ctx:PipelineContext,qid:int,files:list[dict])->list[dict]:
 out=[];chat=ctx.cfg.source_bot
 for f in files:
  message=await ctx.client.get_messages(chat,f['source_message_id']); before=await latest_id(ctx.client,chat)
  clicked=False
  if message.reply_markup:
   for ri,row in enumerate(message.reply_markup.inline_keyboard):
    for ci,b in enumerate(row):
     if (b.text or '')==f['button_text']:
      await ctx.speed.call(lambda m=message,r=ri,c=ci:m.click(r,c),qid);clicked=True;break
    if clicked:break
  if not clicked:raise RuntimeError(f"Download button disappeared for {f['quality']}")
  media=await newest_after(ctx.client,chat,before,max(60,ctx.cfg.flow_timeout),lambda m:bool(m.video or m.document))
  out.append({'quality':f['quality'],'source_message_id':media.id,'received_at':datetime.now(timezone.utc).isoformat()})
  await ctx.speed.delay()
 await ctx.db.patch_state(qid,fetched_files_json=out);return out
