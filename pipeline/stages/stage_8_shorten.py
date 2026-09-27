from pipeline.context import PipelineContext
from utils.arolinks import AroLinks
async def run(ctx:PipelineContext,qid:int,batch_link:str)->str:
 key = await ctx.db.setting('arolinks_api_key', ctx.cfg.arolinks_key)
 try:link=await AroLinks(ctx.cfg.arolinks_url,key).shorten(batch_link)
 except Exception as e:
  await ctx.db.log(f'AroLinks fallback: {e}','WARNING',qid);link=batch_link
 await ctx.db.patch_state(qid,shortened_link=link);return link
