import asyncio
from pipeline.context import PipelineContext
from pipeline.stages.common import latest_id,wait_for_batch_link

async def run(ctx:PipelineContext,qid:int,channel_id:int,forwarded:list[dict])->str:
 if not forwarded:raise RuntimeError('No channel files available for batch')
 chat=ctx.cfg.filestore_bot;before=await latest_id(ctx.client,chat)
 await ctx.speed.call(lambda:ctx.client.send_message(chat,'/batch'),qid)
 # The file-store bot needs a fixed settling window between this three-step
 # conversation. This protocol timing remains active even in unlimited mode.
 await asyncio.sleep(2)
 first=forwarded[0].get('sticker_message_id') or forwarded[0]['channel_message_id']
 last=forwarded[-1].get('end_sticker_message_id') or forwarded[-1]['channel_message_id']
 await ctx.speed.call(lambda:ctx.client.forward_messages(chat,channel_id,first),qid)
 await asyncio.sleep(2)
 await ctx.speed.call(lambda:ctx.client.forward_messages(chat,channel_id,last),qid)
 # Newer file-store bots first send/edit a Processing message. Treat that as
 # an acknowledgement and keep watching the same message (including buttons)
 # for up to 20 minutes instead of failing at the normal 60-second flow limit.
 link=await wait_for_batch_link(ctx.client,chat,before,ctx.cfg.flow_timeout,1200)
 await ctx.db.patch_state(qid,batch_link=link);return link
