from __future__ import annotations
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from control.keyboards import settings_keyboard
class ControlHandlers:
 def __init__(self,db,owner_id:int):self.db,self.owner_id=db,owner_id
 def owner(self,fn):
  @wraps(fn)
  async def wrapped(update:Update,context:ContextTypes.DEFAULT_TYPE):
   if not update.effective_user or update.effective_user.id!=self.owner_id:
    if update.effective_message:await update.effective_message.reply_text('🚫 Unauthorized. This bot is private.')
    return
   return await fn(update,context)
  return wrapped
 async def _values(self):
  keys=['limits_enabled','delay_between_actions','delay_between_movies','max_channels_per_day','auto_catalog']
  return {k:await self.db.setting(k) for k in keys}
 async def start(self,u,c):await u.message.reply_text('🎬 CineForge\n\n/add <title> — queue a title\n/batch — queue multiple lines\n/status — pipeline status\n/settings — runtime settings\n/logs [count] — audit log\n/pause /resume — worker control')
 async def add(self,u,c):
  name=' '.join(c.args).strip()
  if not name:return await u.message.reply_text('Usage: /add <movie name>')
  qid=await self.db.add_movie(name,self.owner_id);await u.message.reply_text(f'✅ Queued #{qid}: {name}')
 async def batch(self,u,c):c.user_data['batch_mode']=True;await u.message.reply_text('Send movie titles, one per line.')
 async def text(self,u,c):
  text=u.message.text.strip()
  if key:=c.user_data.pop('setting_key',None):
   try:
    if key in {'delay_between_actions','delay_between_movies'}:value=str(max(0,float(text)))
    else:value=str(max(0,int(text)))
   except ValueError:return await u.message.reply_text('Enter a non-negative number.')
   await self.db.set_setting(key,value);return await u.message.reply_text(f'✅ {key} = {value}')
  names=[x.strip() for x in text.splitlines() if x.strip()] if c.user_data.pop('batch_mode',False) else [text]
  ids=[await self.db.add_movie(n,self.owner_id) for n in names];await u.message.reply_text(f'✅ Queued {len(ids)} title(s): '+', '.join(map(str,ids)))
 async def status(self,u,c):
  rows=await self.db.queue_list();today=await self.db.count_today();paused=await self.db.setting('pipeline_paused','false')
  lines=[f'📊 STATUS — {"PAUSED" if paused=="true" else "RUNNING"}',f'Today: {today}',f'Queue: {len(rows)}']
  lines += [f"#{r['id']} {r['movie_name']} — stage {r['current_stage']}/10 ({r['status']})" for r in rows[:15]]
  await u.message.reply_text('\n'.join(lines))
 async def settings(self,u,c):await u.message.reply_text('Runtime settings\n0 means unlimited.',reply_markup=settings_keyboard(await self._values()))
 async def toggle_limits(self,u,c):
  old=await self.db.setting('limits_enabled','false');new='false' if old=='true' else 'true';await self.db.set_setting('limits_enabled',new);await u.message.reply_text(f'Limits: {new.upper()}')
 async def callback(self,u,c):
  await u.callback_query.answer();_,action,key=u.callback_query.data.split(':',2)
  if action=='toggle':
   old=await self.db.setting(key,'false');await self.db.set_setting(key,'false' if old=='true' else 'true')
   await u.callback_query.edit_message_reply_markup(settings_keyboard(await self._values()))
  else:c.user_data['setting_key']=key;await u.callback_query.message.reply_text(f'Send the new numeric value for {key}.')
 async def logs(self,u,c):
  try:n=min(50,max(1,int(c.args[0]))) if c.args else 20
  except ValueError:n=20
  rows=await self.db.recent_logs(n);await u.message.reply_text('\n'.join(f"[{r['level']}] #{r['queue_id'] or '-'} {r['message']}" for r in rows) or 'No logs.')
 async def pause(self,u,c):await self.db.set_setting('pipeline_paused','true');await u.message.reply_text('⏸ Pipeline paused.')
 async def resume(self,u,c):await self.db.set_setting('pipeline_paused','false');await u.message.reply_text('▶️ Pipeline resumed.')
 async def cancel(self,u,c):
  if not c.args:return await u.message.reply_text('Usage: /cancel <queue_id>')
  await self.db.db.execute("UPDATE queue SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",(int(c.args[0]),));await u.message.reply_text('Cancelled if still pending.')
 async def retry(self,u,c):
  if not c.args:return await u.message.reply_text('Usage: /retry <queue_id>')
  await self.db.db.execute("UPDATE queue SET status='pending',error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='failed'",(int(c.args[0]),));await u.message.reply_text('Requeued if failed.')
