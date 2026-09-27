"""Queue, state, settings, and audit-log queries."""
from __future__ import annotations
import json
from typing import Any
from database.connection import Database

class Queries:
 def __init__(self, db: Database): self.db=db
 async def add_movie(self,name:str,owner:int)->int:
  q=name.strip(); qid=await self.db.execute("INSERT INTO queue(movie_name,search_query,requested_by) VALUES(?,?,?)",(q,q,owner)); await self.db.execute("INSERT INTO pipeline_state(queue_id) VALUES(?)",(qid,)); return qid
 async def next_pending(self): return await self.db.fetchone("SELECT * FROM queue WHERE status='pending' ORDER BY created_at,id LIMIT 1")
 async def queue_list(self,limit:int=20): return await self.db.fetchall("SELECT * FROM queue WHERE status NOT IN ('completed','cancelled') ORDER BY created_at LIMIT ?",(limit,))
 async def set_stage(self,qid:int,stage:int,status:str): await self.db.execute("UPDATE queue SET current_stage=?,status=?,updated_at=CURRENT_TIMESTAMP,error_message=NULL WHERE id=?",(stage,status,qid))
 async def fail(self,qid:int,error:str): await self.db.execute("UPDATE queue SET status='failed',error_message=?,retry_count=retry_count+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",(error[:1000],qid))
 async def complete(self,qid:int): await self.db.execute("UPDATE queue SET status='completed',current_stage=10,updated_at=CURRENT_TIMESTAMP WHERE id=?",(qid,))
 async def state(self,qid:int): return await self.db.fetchone("SELECT * FROM pipeline_state WHERE queue_id=?",(qid,))
 async def patch_state(self,qid:int,**values:Any):
  allowed={'source_messages_json','filtered_files_json','fetched_files_json','channel_id','invite_link','owner_promoted','forwarded_message_ids_json','batch_link','shortened_link','final_post_id','catalog_added'}
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
 async def register_channel(self,qid:int,movie:str,cid:int,invite:str): await self.db.execute("INSERT OR IGNORE INTO created_channels(queue_id,movie_name,channel_id,invite_link) VALUES(?,?,?,?)",(qid,movie,cid,invite))
 async def created_by_channel(self,cid:int): return await self.db.fetchone("SELECT * FROM created_channels WHERE channel_id=?",(cid,))
