from pipeline.context import PipelineContext
from utils.text_parser import parse_results

async def run(ctx:PipelineContext,qid:int,messages:list[dict])->list[dict]:
 mandatory={'480p','720p','1080p'}
 desired=set((await ctx.db.setting('desired_qualities',ctx.cfg.qualities)).split(',')) | mandatory
 language=(await ctx.db.setting('language_filter',ctx.cfg.language_filter)).strip().lower()
 row=await ctx.db.db.fetchone('SELECT movie_name,content_type FROM queue WHERE id=?',(qid,))
 files=parse_results(messages,desired,allow_non_hindi=(language == 'any'),title_query=row['movie_name'],content_type=row['content_type'])
 if not files:raise RuntimeError(f"No exact-title {row['content_type']} files in desired qualities")
 if row['content_type']=='movie':
  available={item['quality'] for item in files};missing=mandatory-available
  if missing:await ctx.db.log('Search exhausted; continuing without unavailable qualities: '+', '.join(sorted(missing)),'WARNING',qid)
 await ctx.db.patch_state(qid,filtered_files_json=files);return files
