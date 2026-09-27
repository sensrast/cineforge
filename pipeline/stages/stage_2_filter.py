from pipeline.context import PipelineContext
from utils.text_parser import parse_results
async def run(ctx:PipelineContext,qid:int,messages:list[dict])->list[dict]:
 desired=set((await ctx.db.setting('desired_qualities',ctx.cfg.qualities)).split(','))
 files=parse_results(messages,desired)
 if not files:raise RuntimeError('No matching Hindi/Dual Audio files in desired qualities')
 await ctx.db.patch_state(qid,filtered_files_json=files);return files
