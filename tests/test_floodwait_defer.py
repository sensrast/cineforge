import tempfile
import unittest
from pathlib import Path
from database.connection import Database
from database.queries import Queries

class FloodWaitDeferTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'test.db')
  await self.db.connect();await self.db.init_schema(Path(__file__).parents[1]/'database/schema.sql');self.q=Queries(self.db)
 async def asyncTearDown(self):
  await self.db.close();self.tmp.cleanup()
 async def test_deferred_job_does_not_block_ready_queue(self):
  first=await self.q.add_movie('First',1);second=await self.q.add_movie('Second',1)
  await self.q.set_stage(first,4,'creating_channel');await self.q.defer_floodwait(first,3600,'cooldown')
  ready=await self.q.next_pending();self.assertEqual(ready['id'],second)
  row=await self.db.fetchone('SELECT * FROM queue WHERE id=?',(first,));self.assertEqual(row['status'],'deferred');self.assertIsNotNone(row['next_attempt_at'])
 async def test_deferred_job_returns_when_due(self):
  qid=await self.q.add_movie('Due',1);await self.q.defer_floodwait(qid,3600,'cooldown')
  await self.db.execute("UPDATE queue SET next_attempt_at=datetime('now','-1 second') WHERE id=?",(qid,))
  ready=await self.q.next_pending();self.assertEqual(ready['id'],qid)
