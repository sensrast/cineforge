from __future__ import annotations
import json
from datetime import datetime,timezone
from pipeline.context import PipelineContext
from pipeline.stages.common import latest_id,newest_after
from utils.text_parser import explicit_non_hindi,media_label
async def run(ctx:PipelineContext,qid:int,files:list[dict])->list[dict]:
 state=await ctx.db.state(qid)
 existing=json.loads(state['fetched_files_json'] or '[]') if state else []
 if existing:return existing
 out=[];chat=ctx.cfg.source_bot
 strict_hindi=(await ctx.db.setting('language_filter',ctx.cfg.language_filter)).strip().lower()!='any'
 for f in files:
  message=await ctx.client.get_messages(chat,f['source_message_id']); before=await latest_id(ctx.client,chat)
  clicked=False
  if message.reply_markup:
   for ri,row in enumerate(message.reply_markup.inline_keyboard):
    for ci,b in enumerate(row):
     if (b.text or '')==f['button_text']:
      # Pyrogram coordinates are x=column, y=row.
      await ctx.speed.call(lambda m=message,r=ri,c=ci:m.click(c,r),qid);clicked=True;break
    if clicked:break
  if not clicked:raise RuntimeError(f"Download button disappeared for {f['quality']}")
  media=await newest_after(ctx.client,chat,before,max(60,ctx.cfg.flow_timeout),lambda m:bool(m.video or m.document))
  delivered_label=media_label(media)
  if strict_hindi and explicit_non_hindi(delivered_label):
   await ctx.db.log(f"Rejected delivered non-Hindi file for {f['quality']}: {delivered_label[:180]}",'WARNING',qid)
   continue
  out.append({'quality':f['quality'],'source_message_id':media.id,'received_at':datetime.now(timezone.utc).isoformat(),'source_name':delivered_label or f.get('source_name','')})
  await ctx.speed.delay()
 if not out:raise RuntimeError('No valid Hindi files could be fetched')
 missing={'480p','720p','1080p'}-{item['quality'] for item in out}
 if missing:await ctx.db.log('Continuing without unavailable qualities: '+', '.join(sorted(missing)),'WARNING',qid)
 await ctx.db.patch_state(qid,fetched_files_json=out);return out
