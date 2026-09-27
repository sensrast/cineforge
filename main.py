"""CineForge entry point: health server, MTProto userbot, control bot, queue worker."""
from __future__ import annotations
import argparse,asyncio,json,logging,signal
from pathlib import Path
from aiohttp import web
from config import settings
from database.connection import Database
from database.queries import Queries
from userbot.client import build_userbot
from userbot.session_manager import generate_session
from userbot.speed_controller import SpeedController
from pipeline.context import PipelineContext
from pipeline.orchestrator import Orchestrator
from pipeline.stages.stage_5_promote import register as register_promote
from control.bot import build_control_bot
from utils.logger import setup_logging
log=logging.getLogger('cineforge')
async def health(request):
 app=request.app
 payload={'status':'ok' if app.get('ready') and app.get('userbot') else 'degraded' if app.get('error') else 'starting','userbot':app.get('userbot',False),'worker':app.get('worker',False)}
 if app.get('error'):payload['error']=app['error']
 return web.json_response(payload)
async def serve_health():
 app=web.Application();app['ready']=False;app['userbot']=False;app['worker']=False;app.router.add_get('/',health);app.router.add_get('/health',health)
 runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,settings.health_host,settings.port);await site.start();return app,runner
async def run():
 setup_logging();health_app,runner=await serve_health()
 db=Database(settings.db_path);await db.connect();await db.init_schema(Path(__file__).parent/'database/schema.sql');queries=Queries(db)
 # Interrupted work resumes from its recorded stage after a restart.
 await db.execute("UPDATE queue SET status='pending' WHERE status NOT IN ('pending','completed','failed','cancelled')")
 try:
  settings.validate(require_session=True)
 except RuntimeError as exc:
  # Keep the web service alive so secrets can be configured in Render after
  # the first deployment. /health reports degraded until the next restart.
  health_app['ready']=True;health_app['error']=str(exc);log.error('%s',exc)
  await asyncio.Event().wait();return
 userbot=build_userbot(settings);await userbot.start();health_app['userbot']=True
 me=await userbot.get_me();log.info('Userbot connected as %s',me.username or me.id)
 speed=SpeedController(queries);ctx=PipelineContext(userbot,settings,queries,speed);register_promote(ctx)
 control=build_control_bot(settings.control_token,queries,settings.owner_id);await control.initialize();await control.start();await control.updater.start_polling(drop_pending_updates=False)
 worker=Orchestrator(ctx);task=asyncio.create_task(worker.run_forever(),name='pipeline-worker');health_app['worker']=True;health_app['ready']=True
 try:
  await userbot.send_message(settings.owner_id,f'🟢 CineForge online\nUserbot: @{me.username or me.id}')
 except Exception:log.warning('Could not send startup notification',exc_info=True)
 stop=asyncio.Event();loop=asyncio.get_running_loop()
 for sig in (signal.SIGINT,signal.SIGTERM):
  try:loop.add_signal_handler(sig,stop.set)
  except NotImplementedError:pass
 await stop.wait();worker.stop_event.set()
 try: await asyncio.wait_for(task, timeout=120)
 except asyncio.TimeoutError: task.cancel(); await asyncio.gather(task, return_exceptions=True)
 await control.updater.stop();await control.stop();await control.shutdown();await userbot.stop();await db.close();await runner.cleanup()
async def cli():
 parser=argparse.ArgumentParser();parser.add_argument('--generate-session',action='store_true');args=parser.parse_args()
 if args.generate_session:
  print('\nUSERBOT_SESSION_STRING='+await generate_session(settings));return
 await run()
if __name__=='__main__':asyncio.run(cli())
