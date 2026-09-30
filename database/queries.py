"""Queue, state, settings, and audit-log queries."""
from __future__ import annotations
import json
from typing import Any
from database.connection import Database
from utils.text_parser import normalize_title

class Queries:
 def __init__(self, db: Database): self.db=db
 async def add_movie(self,name:str,owner:int,content_type:str='movie',force_rebuild:bool=False)->int:
  q=name.strip(); kind='series' if content_type=='series' else 'movie'; qid=await self.db.execute("INSERT INTO queue(movie_name,search_query,content_type,force_rebuild,requested_by) VALUES(?,?,?,?,?)",(q,q,kind,int(force_rebuild),owner)); await self.db.execute("INSERT INTO pipeline_state(queue_id) VALUES(?)",(qid,)); return qid
 async def add_manual(self,name:str,owner:int,content_type:str,files:list[dict])->int:
  q=name.strip();kind='series' if content_type=='series' else 'movie'
  qid=await self.db.execute("INSERT INTO queue(movie_name,search_query,content_type,input_mode,status,current_stage,requested_by) VALUES(?,?,?,'manual','pending',4,?)",(q,q,kind,owner))
  payload=json.dumps(files,ensure_ascii=False)
  await self.db.execute("INSERT INTO pipeline_state(queue_id,filtered_files_json,fetched_files_json) VALUES(?,?,?)",(qid,payload,payload))
  return qid
 async def next_pending(self): return await self.db.fetchone("SELECT * FROM queue WHERE status IN ('pending','deferred') AND (next_attempt_at IS NULL OR next_attempt_at<=CURRENT_TIMESTAMP) ORDER BY COALESCE(next_attempt_at,created_at),id LIMIT 1")
 async def queue_list(self,limit:int=20): return await self.db.fetchall("SELECT * FROM queue WHERE status NOT IN ('completed','cancelled') ORDER BY created_at LIMIT ?",(limit,))
 async def set_stage(self,qid:int,stage:int,status:str): await self.db.execute("UPDATE queue SET current_stage=?,status=?,next_attempt_at=NULL,updated_at=CURRENT_TIMESTAMP,error_message=NULL WHERE id=?",(stage,status,qid))
 async def fail(self,qid:int,error:str): await self.db.execute("UPDATE queue SET status='failed',next_attempt_at=NULL,error_message=?,retry_count=retry_count+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",(error[:1000],qid))
 async def defer_floodwait(self,qid:int,seconds:int,reason:str):
  await self.db.execute("UPDATE queue SET status='deferred',next_attempt_at=datetime('now',? || ' seconds'),error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(str(max(1,int(seconds))),reason[:1000],qid))
 async def complete(self,qid:int): await self.db.execute("UPDATE queue SET status='completed',current_stage=10,updated_at=CURRENT_TIMESTAMP WHERE id=?",(qid,))
 async def retry_failed(self,qid:int):
  row=await self.db.fetchone("SELECT current_stage FROM queue WHERE id=? AND status='failed'",(qid,))
  if not row:return False
  if int(row['current_stage'] or 0)<=3:
   await self.db.execute("UPDATE pipeline_state SET source_messages_json='[]',filtered_files_json='[]',fetched_files_json='[]' WHERE queue_id=?",(qid,))
   await self.db.execute("UPDATE queue SET status='pending',current_stage=0,next_attempt_at=NULL,error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(qid,))
  else:
   await self.db.execute("UPDATE queue SET status='pending',next_attempt_at=NULL,error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(qid,))
  return True
 async def state(self,qid:int): return await self.db.fetchone("SELECT * FROM pipeline_state WHERE queue_id=?",(qid,))
 async def patch_state(self,qid:int,**values:Any):
  allowed={'source_messages_json','filtered_files_json','fetched_files_json','channel_id','invite_link','owner_promoted','forwarded_message_ids_json','batch_link','shortened_link','final_post_id','catalog_added','backup_done','backup_message_ids_json','promotion_done','promotion_link','promotion_post_id','promotion_sticker_id'}
  values={k:(json.dumps(v) if k.endswith('_json') and not isinstance(v,str) else v) for k,v in values.items() if k in allowed}
  if values:
   cols=", ".join(f"{k}=?" for k in values); await self.db.execute(f"UPDATE pipeline_state SET {cols},updated_at=CURRENT_TIMESTAMP WHERE queue_id=?",(*values.values(),qid))
 async def setting(self,key:str,default:str='')->str:
  r=await self.db.fetchone("SELECT value FROM settings WHERE key=?",(key,)); return r['value'] if r else default
 async def set_setting(self,key:str,value:str): await self.db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",(key,value))
 async def delete_setting(self,key:str): await self.db.execute("DELETE FROM settings WHERE key=?",(key,))
 async def log(self,msg:str,level:str='INFO',qid:int|None=None): await self.db.execute("INSERT INTO logs(queue_id,level,message) VALUES(?,?,?)",(qid,level,msg[:2000]))
 async def recent_logs(self,n:int=20): return await self.db.fetchall("SELECT * FROM logs ORDER BY id DESC LIMIT ?",(n,))
 async def count_today(self)->int:
  r=await self.db.fetchone("SELECT COUNT(*) n FROM created_channels WHERE date(created_at)=date('now')"); return r['n']
 async def register_channel(self,qid:int,movie:str,cid:int,invite:str,content_type:str='movie'): await self.db.execute("INSERT OR IGNORE INTO created_channels(queue_id,movie_name,content_type,channel_id,invite_link) VALUES(?,?,?,?,?)",(qid,movie,content_type,cid,invite))
 async def find_channel_by_movie(self,movie:str,content_type:str='movie'):
  wanted=normalize_title(movie)
  for row in await self.db.fetchall("SELECT * FROM created_channels WHERE content_type=? ORDER BY id DESC",(content_type,)):
   if normalize_title(row['movie_name'])==wanted:return row
  return None
 async def remove_channel(self,cid:int): await self.db.execute("DELETE FROM created_channels WHERE channel_id=?",(cid,))
 async def finalize_channel(self,cid:int,batch:str,short:str): await self.db.execute("UPDATE created_channels SET batch_link=?,shortened_link=? WHERE channel_id=?",(batch,short,cid))
 async def created_by_channel(self,cid:int): return await self.db.fetchone("SELECT * FROM created_channels WHERE channel_id=?",(cid,))
