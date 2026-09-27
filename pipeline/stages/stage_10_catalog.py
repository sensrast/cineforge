from __future__ import annotations
from pipeline.context import PipelineContext
from pipeline.stages.common import latest_id,newest_after,click_matching
from utils.text_parser import clean_title,is_series
async def _response(ctx,after,predicate=None):return await newest_after(ctx.client,ctx.cfg.catalog_bot,after,ctx.cfg.flow_timeout,predicate)
async def _send(ctx,qid,text,after):
 await ctx.speed.delay();await ctx.speed.call(lambda:ctx.client.send_message(ctx.cfg.catalog_bot,text),qid);return await _response(ctx,after,lambda m:bool((m.text or m.caption) or m.reply_markup))
async def _click(ctx,qid,msg,patterns):
 before=await latest_id(ctx.client,ctx.cfg.catalog_bot);await ctx.speed.delay()
 if not await click_matching(msg,patterns):raise RuntimeError('Catalog button not found: '+patterns[0])
 return await _response(ctx,before,lambda m:bool((m.text or m.caption) or m.reply_markup))
async def run(ctx:PipelineContext,qid:int,movie:str,invite:str,source_message_id:int)->bool:
 chat=ctx.cfg.catalog_bot;before=await latest_id(ctx.client,chat)
 panel=await _send(ctx,qid,'/admin',before)
 msg=await _click(ctx,qid,panel,[r'Add New Title',r'add[_ ]?title'])
 before=await latest_id(ctx.client,chat);msg=await _send(ctx,qid,clean_title(movie),before)
 # Reuse Telegram's cached thumbnail by file_id; no movie bytes are downloaded.
 source=await ctx.client.get_messages(ctx.cfg.source_bot,source_message_id)
 thumbs=(source.video.thumbs if source.video else source.document.thumbs if source.document else None) or []
 if thumbs:
  before=await latest_id(ctx.client,chat);await ctx.speed.delay();await ctx.speed.call(lambda:ctx.client.send_photo(chat,thumbs[-1].file_id),qid);msg=await _response(ctx,before)
 elif msg.reply_markup:
  msg=await _click(ctx,qid,msg,[r'Skip',r'⏩'])
 else:raise RuntimeError('Catalog requires an image, but no reusable Telegram thumbnail exists')
 if msg.reply_markup:msg=await _click(ctx,qid,msg,[r'Skip',r'⏩'])
 before=await latest_id(ctx.client,chat);msg=await _send(ctx,qid,invite,before)
 series=is_series(movie);msg=await _click(ctx,qid,msg,[r'Web Series' if series else r'Movies'])
 msg=await _click(ctx,qid,msg,[r'Action',r'Drama',r'Genre'])
 if msg.reply_markup:msg=await _click(ctx,qid,msg,[r'Done',r'✅'])
 msg=await _click(ctx,qid,msg,[r'Hindi'])
 msg=await _click(ctx,qid,msg,[r'Ongoing' if series else r'Completed'])
 before=await latest_id(ctx.client,chat);msg=await _send(ctx,qid,'0',before)
 msg=await _click(ctx,qid,msg,[r'Safe',r'No',r'❌'])
 await _click(ctx,qid,msg,[r'Publish',r'Submit'])
 await ctx.db.patch_state(qid,catalog_added=1);return True
