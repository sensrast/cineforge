from pipeline.context import PipelineContext
from pipeline.stages.common import latest_id,newest_after
from utils.text_parser import extract_batch_link
async def run(ctx:PipelineContext,qid:int,channel_id:int,forwarded:list[dict])->str:
 if not forwarded:raise RuntimeError('No channel files available for batch')
 chat=ctx.cfg.filestore_bot;before=await latest_id(ctx.client,chat)
 await ctx.speed.call(lambda:ctx.client.send_message(chat,'/batch'),qid)
 prompt=await newest_after(ctx.client,chat,before,ctx.cfg.flow_timeout,lambda m:bool(m.text or m.caption))
 first=forwarded[0].get('sticker_message_id') or forwarded[0]['channel_message_id']
 last=forwarded[-1].get('end_sticker_message_id') or forwarded[-1]['channel_message_id']
 before=prompt.id;await ctx.speed.call(lambda:ctx.client.forward_messages(chat,channel_id,first),qid)
 second=await newest_after(ctx.client,chat,before,ctx.cfg.flow_timeout,lambda m:bool(m.text or m.caption))
 direct=extract_batch_link(second.text or second.caption or '')
 if direct:link=direct
 else:
  before=second.id;await ctx.speed.call(lambda:ctx.client.forward_messages(chat,channel_id,last),qid)
  result=await newest_after(ctx.client,chat,before,ctx.cfg.flow_timeout,lambda m:bool(extract_batch_link(m.text or m.caption or '')))
  link=extract_batch_link(result.text or result.caption or '')
 if not link:raise RuntimeError('File-store bot did not return a batch link')
 await ctx.db.patch_state(qid,batch_link=link);return link
