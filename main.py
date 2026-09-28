"""CineForge entry point: health server, control bot, MTProto engine, queue worker."""
from __future__ import annotations
import argparse
import asyncio
import json
import logging
import os
import signal
from pathlib import Path
from aiohttp import web
from telegram import BotCommand
from config import settings
from database.connection import Database
from database.queries import Queries
from userbot.client import build_userbot
from userbot.session_manager import generate_session
from userbot.speed_controller import SpeedController
from userbot.login_manager import LoginManager
from pipeline.context import PipelineContext
from pipeline.orchestrator import Orchestrator
from pipeline.stages.stage_5_promote import register as register_promote
from pipeline.channel_folder import ensure_created_channels_folder
from pipeline.promotion import upgrade_promotion_template
from control.bot import build_control_bot
from utils.logger import setup_logging
from utils.github_store import load_state, persist_state
log = logging.getLogger("cineforge")

async def health(request):
    app = request.app
    status = "ok" if app.get("userbot") and app.get("worker") else "setup_required" if app.get("control_bot") else "starting"
    return web.json_response({"status": status, "control_bot": app.get("control_bot", False), "userbot": app.get("userbot", False), "worker": app.get("worker", False)})

async def serve_health():
    app = web.Application()
    app.update(control_bot=False, userbot=False, worker=False)
    app.router.add_get("/", health); app.router.add_get("/health", health)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, settings.health_host, settings.port).start()
    return app, runner

class UserbotRuntime:
    """Starts the MTProto pipeline after an owner completes in-bot login."""
    def __init__(self, cfg, queries, health_app):
        self.cfg, self.db, self.health_app = cfg, queries, health_app
        self.client = None; self.worker = None; self.task = None
        self.lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return bool(self.client and self.client.is_connected and self.task and not self.task.done())

    async def start(self, session_string: str) -> None:
        async with self.lock:
            if self.running:
                return
            self.cfg.session_string = session_string
            if not self.cfg.api_id or not self.cfg.api_hash:
                raise RuntimeError("API ID and API hash are required before userbot login.")
            client = build_userbot(self.cfg)
            try:
                await client.start()
                me = await client.get_me()
                speed = SpeedController(self.db)
                context = PipelineContext(client, self.cfg, self.db, speed)
                register_promote(context)
                channel_rows=await self.db.db.fetchall("SELECT channel_id FROM created_channels WHERE channel_id IS NOT NULL ORDER BY id")
                await ensure_created_channels_folder(context,[int(row["channel_id"]) for row in channel_rows])
                worker = Orchestrator(context)
                task = asyncio.create_task(worker.run_forever(), name="pipeline-worker")
                self.client, self.worker, self.task = client, worker, task
                self.health_app["userbot"] = True; self.health_app["worker"] = True
                log.info("Userbot connected as %s", me.username or me.id)
                try: await client.send_message(self.cfg.owner_id, f"🟢 CineForge userbot online: @{me.username or me.id}")
                except Exception: log.warning("Startup notification failed", exc_info=True)
            except Exception:
                try:
                    if client.is_connected: await client.stop()
                except Exception: pass
                raise

    async def stop(self) -> None:
        async with self.lock:
            if self.worker: self.worker.stop_event.set()
            if self.task:
                try: await asyncio.wait_for(self.task, timeout=30)
                except asyncio.TimeoutError:
                    self.task.cancel(); await asyncio.gather(self.task, return_exceptions=True)
            if self.client and self.client.is_connected: await self.client.stop()
            self.client = self.worker = self.task = None
            self.health_app["userbot"] = False; self.health_app["worker"] = False

async def restore_render_state(queries: Queries) -> bool:
    """Restore private durable state. False means startup must not overwrite it."""
    try:
        state = await load_state()
        saved = state.get("settings", {})
        if not saved:
            saved = json.loads(os.getenv("CINEFORGE_SETTINGS_JSON", "{}"))
        for key, value in saved.items():
            await queries.set_setting(str(key), str(value))
        for item in state.get("channels", []):
            await queries.db.execute(
                "INSERT OR IGNORE INTO created_channels(movie_name,content_type,channel_id,invite_link,batch_link,shortened_link) VALUES(?,?,?,?,?,?)",
                (item.get("movie_name", ""), item.get("content_type", "movie"), int(item["channel_id"]), item.get("invite_link"), item.get("batch_link"), item.get("shortened_link")),
            )
        return True
    except Exception:
        log.exception("Could not restore durable CineForge state; refusing startup overwrite")
        return False

async def seed_bootstrap_settings(queries: Queries) -> None:
    """Make effective environment/bootstrap values durable without replacing saved values."""
    values={
        "api_id":str(settings.api_id or ""),"api_hash":settings.api_hash,
        "owner_username":settings.owner_username,"source_bot":settings.source_bot,
        "filestore_bot":settings.filestore_bot,"catalog_bot":settings.catalog_bot,
        "arolinks_api_key":settings.arolinks_key,"arolinks_url":settings.arolinks_url,
        "tutorial_link":settings.tutorial_link,"channel_name":settings.channel_name,
        "channel_description":settings.channel_description,"caption":settings.caption,
        "desired_qualities":settings.qualities,"language_filter":settings.language_filter,
        "search_strategy":settings.search_strategy,"max_search_pages":str(settings.max_search_pages),
        "source_timeout":str(settings.source_timeout),"flow_timeout":str(settings.flow_timeout),
        "default_genre":settings.default_genre,"catalog_language":settings.catalog_language,
        "delay_between_actions":str(settings.delay_actions),"delay_between_movies":str(settings.delay_movies),
        "max_channels_per_day":str(settings.max_channels),"limits_enabled":str(settings.limits_enabled).lower(),
        "auto_catalog":str(settings.auto_catalog).lower(),"userbot_phone":settings.phone,
        "userbot_session_string":settings.session_string,
    }
    for key,value in values.items():
        if value and not await queries.db.fetchone("SELECT 1 FROM settings WHERE key=?",(key,)):
            await queries.set_setting(key,value)

async def apply_saved_settings(queries: Queries) -> None:
    mapping = {
        "api_id": ("api_id", int), "api_hash": ("api_hash", str), "owner_username": ("owner_username", str),
        "source_bot": ("source_bot", str), "filestore_bot": ("filestore_bot", str), "catalog_bot": ("catalog_bot", str),
        "arolinks_api_key": ("arolinks_key", str), "arolinks_url": ("arolinks_url", str),
        "tutorial_link": ("tutorial_link", str), "channel_name": ("channel_name", str),
        "channel_description": ("channel_description", str), "caption": ("caption", str), "desired_qualities": ("qualities", str),
        "language_filter": ("language_filter", str), "search_strategy": ("search_strategy", str), "max_search_pages": ("max_search_pages", int),
        "source_timeout": ("source_timeout", int), "flow_timeout": ("flow_timeout", int),
        "default_genre": ("default_genre", str), "catalog_language": ("catalog_language", str),
        "delay_between_actions": ("delay_actions", float), "delay_between_movies": ("delay_movies", float),
        "max_channels_per_day": ("max_channels", int),
    }
    for key, (attribute, converter) in mapping.items():
        value = await queries.setting(key, "")
        if value:
            try: setattr(settings, attribute, converter(value))
            except (TypeError, ValueError): log.warning("Ignoring invalid saved setting %s", key)

async def run():
    setup_logging(); health_app, runner = await serve_health()
    db = Database(settings.db_path); await db.connect(); await db.init_schema(Path(__file__).parent / "database/schema.sql")
    queries = Queries(db)
    durable_loaded=await restore_render_state(queries)
    await db.execute("UPDATE queue SET status='pending' WHERE status NOT IN ('pending','completed','failed','cancelled')")
    await apply_saved_settings(queries)
    if durable_loaded:
        await seed_bootstrap_settings(queries)
        promo_caption=await queries.setting("promotion_caption","")
        if promo_caption:
            await queries.set_setting("promotion_caption",upgrade_promotion_template(promo_caption))
        try: await persist_state(queries)
        except Exception: log.exception("Could not persist complete startup state")
    else:
        raise RuntimeError("Durable state could not be loaded; refusing to start with reset defaults")
    if not settings.control_token or not settings.owner_id:
        raise RuntimeError("CONTROL_BOT_TOKEN and OWNER_USER_ID are required bootstrap settings.")

    runtime = UserbotRuntime(settings, queries, health_app)
    login = LoginManager(queries, settings, runtime.start)
    control = build_control_bot(settings.control_token, queries, settings.owner_id, settings, runtime, login)
    while True:
        try:
            await control.initialize(); await control.start(); await control.updater.start_polling(drop_pending_updates=False)
            await control.bot.set_my_commands([
                BotCommand("start", "Open the admin panel"), BotCommand("add", "Choose type for one title"),
                BotCommand("movie", "Queue a movie directly"), BotCommand("series", "Queue a series directly"),
                BotCommand("rebuild", "Force a clean movie rebuild"),
                BotCommand("batch", "Choose type and queue multiple titles"), BotCommand("status", "Show live pipeline status"),
                BotCommand("settings", "Open detailed settings"), BotCommand("logs", "Show recent activity"),
                BotCommand("pause", "Pause the queue worker"), BotCommand("resume", "Resume the queue worker"),
                BotCommand("cancel", "Cancel a pending queue item"), BotCommand("retry", "Retry a failed item"),
            ])
            health_app["control_bot"] = True
            break
        except Exception:
            log.exception("Control bot connection failed; retrying in 10 seconds")
            try: await control.shutdown()
            except Exception: pass
            await asyncio.sleep(10)

    session = await queries.setting("userbot_session_string", settings.session_string)
    if session:
        try: await runtime.start(session)
        except Exception: log.exception("Saved userbot session could not be started; use the Login button again")
    else:
        log.warning("No userbot session. Open the control bot and press Login Userbot.")

    stop = asyncio.Event(); loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(sig, stop.set)
        except NotImplementedError: pass
    await stop.wait()
    await runtime.stop(); await control.updater.stop(); await control.stop(); await control.shutdown(); await db.close(); await runner.cleanup()

async def cli():
    parser = argparse.ArgumentParser(); parser.add_argument("--generate-session", action="store_true"); args = parser.parse_args()
    if args.generate_session:
        print("\nUSERBOT_SESSION_STRING=" + await generate_session(settings)); return
    await run()

if __name__ == "__main__": asyncio.run(cli())
