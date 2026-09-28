from __future__ import annotations
import json
from pipeline.context import PipelineContext

async def run(ctx:PipelineContext,qid:int,files:list[dict])->list[dict]:
 """Return files fetched while each Movie Hunt result page was active.

 Movie Hunt edits one keyboard in place, so attempting to click Stage-2 page
 metadata after pagination can select the wrong file or a vanished button.
 Stage 1 is therefore the single authoritative fetching stage.
 """
 state=await ctx.db.state(qid)
 existing=json.loads(state['fetched_files_json'] or '[]') if state else []
 if not existing:
  raise RuntimeError('No page-active prefetched files are available; refusing to click stale Movie Hunt buttons')
 return existing
