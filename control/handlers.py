from __future__ import annotations
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from control.keyboards import home_keyboard, settings_keyboard, submenu_keyboard, EDITABLE_SETTINGS

CFG_ATTRS = {
    "api_id": "api_id", "api_hash": "api_hash", "owner_username": "owner_username",
    "source_bot": "source_bot", "filestore_bot": "filestore_bot", "catalog_bot": "catalog_bot",
    "arolinks_api_key": "arolinks_key", "arolinks_url": "arolinks_url",
    "tutorial_link": "tutorial_link", "channel_name": "channel_name", "channel_description": "channel_description", "caption": "caption", "desired_qualities": "qualities",
    "delay_between_actions": "delay_actions", "delay_between_movies": "delay_movies",
    "max_channels_per_day": "max_channels",
}

class ControlHandlers:
    def __init__(self, db, owner_id: int, cfg, runtime, login):
        self.db, self.owner_id, self.cfg = db, owner_id, cfg
        self.runtime, self.login = runtime, login

    def owner(self, fn):
        @wraps(fn)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.effective_user or update.effective_user.id != self.owner_id:
                if update.effective_message:
                    await update.effective_message.reply_text("🚫 Unauthorized. This bot is private.")
                return
            return await fn(update, context)
        return wrapped

    async def _values(self):
        keys = ["limits_enabled", "delay_between_actions", "delay_between_movies", "max_channels_per_day", "auto_catalog"]
        return {key: await self.db.setting(key) for key in keys}

    async def start(self, update, context):
        context.user_data.clear()
        await update.message.reply_text(
            "🎬 CineForge Admin\n\nUse Login Userbot for first-time Telegram authorization. "
            "API ID and API hash can be entered under Settings → Telegram API.",
            reply_markup=home_keyboard(self.runtime.running),
        )

    async def add(self, update, context):
        name = " ".join(context.args).strip()
        if not name:
            return await update.message.reply_text("Usage: /add <movie name>")
        qid = await self.db.add_movie(name, self.owner_id)
        await update.message.reply_text(f"✅ Queued #{qid}: {name}")

    async def batch(self, update, context):
        context.user_data["input_mode"] = "batch"
        await update.message.reply_text("Send movie titles, one per line.")

    async def text(self, update, context):
        mode = context.user_data.get("input_mode")
        text = update.message.text.strip()
        if mode == "phone":
            try:
                await self.login.send_code(self.owner_id, text)
                context.user_data["input_mode"] = "otp"
                await update.message.reply_text("📨 Telegram sent a login code. Send it here. Spaces are allowed.\n\nUse /cancel_login to abort.")
            except Exception as exc:
                await update.message.reply_text(f"❌ Could not send code: {exc}")
            return
        if mode == "otp":
            try:
                try: await update.message.delete()
                except Exception: pass
                result = await self.login.submit_code(self.owner_id, text)
                if result == "password":
                    context.user_data["input_mode"] = "password"
                    await update.effective_chat.send_message("🔑 Two-step verification is enabled. Send your password. The message will be deleted immediately.")
                else:
                    context.user_data.clear()
                    await update.effective_chat.send_message("✅ Login complete. Session saved and userbot engine started.", reply_markup=home_keyboard(True))
            except Exception as exc:
                await update.effective_chat.send_message(f"❌ Login failed: {exc}")
            return
        if mode == "password":
            try:
                try: await update.message.delete()
                except Exception: pass
                await self.login.submit_password(self.owner_id, text)
                context.user_data.clear()
                await update.effective_chat.send_message("✅ Login complete. Session saved and userbot engine started.", reply_markup=home_keyboard(True))
            except Exception as exc:
                await update.effective_chat.send_message(f"❌ Login failed: {exc}")
            return
        if mode == "setting":
            key = context.user_data.pop("setting_key")
            context.user_data.pop("input_mode", None)
            try:
                value = self._validate_setting(key, text)
                await self.db.set_setting(key, value)
                attr = CFG_ATTRS.get(key)
                if attr:
                    converted = int(value) if key in {"api_id", "max_channels_per_day"} else float(value) if key in {"delay_between_actions", "delay_between_movies"} else value
                    setattr(self.cfg, attr, converted)
                await update.message.reply_text(f"✅ {EDITABLE_SETTINGS[key]} saved.")
            except Exception as exc:
                await update.message.reply_text(f"❌ {exc}")
            return
        names = [line.strip() for line in text.splitlines() if line.strip()] if mode == "batch" else [text]
        context.user_data.clear()
        ids = [await self.db.add_movie(name, self.owner_id) for name in names]
        await update.message.reply_text(f"✅ Queued {len(ids)} title(s): " + ", ".join(map(str, ids)))

    @staticmethod
    def _validate_setting(key: str, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be empty.")
        if key in {"api_id", "max_channels_per_day"}:
            value = str(max(0, int(value)))
        elif key in {"delay_between_actions", "delay_between_movies"}:
            value = str(max(0.0, float(value)))
        elif key in {"owner_username", "source_bot", "filestore_bot", "catalog_bot"}:
            value = value.lstrip("@")
        elif key in {"arolinks_url", "tutorial_link"} and not value.startswith(("http://", "https://")):
            raise ValueError("Enter a complete http:// or https:// URL.")
        return value

    async def status_text(self) -> str:
        rows = await self.db.queue_list(); today = await self.db.count_today(); paused = await self.db.setting("pipeline_paused", "false")
        lines = [f'📊 STATUS — {"PAUSED" if paused == "true" else "RUNNING"}', f'Userbot: {"CONNECTED" if self.runtime.running else "LOGIN REQUIRED"}', f"Today: {today}", f"Queue: {len(rows)}"]
        lines += [f"#{r['id']} {r['movie_name']} — stage {r['current_stage']}/10 ({r['status']})" for r in rows[:15]]
        return "\n".join(lines)

    async def status(self, update, context): await update.message.reply_text(await self.status_text())
    async def settings(self, update, context): await update.message.reply_text("⚙️ Runtime settings", reply_markup=settings_keyboard(await self._values()))
    async def toggle_limits(self, update, context):
        old = await self.db.setting("limits_enabled", "false"); new = "false" if old == "true" else "true"
        await self.db.set_setting("limits_enabled", new); await update.message.reply_text(f"Limits: {new.upper()}")

    async def callback(self, update, context):
        query = update.callback_query; await query.answer(); data = query.data
        if data == "auth:start":
            if not await self.login.credentials_ready():
                return await query.message.reply_text("Set Telegram API ID and API hash in Settings first.")
            context.user_data["input_mode"] = "phone"
            return await query.message.reply_text("Send the Telegram account phone number with country code, for example +919876543210.")
        if data == "auth:status": return await query.message.reply_text("✅ Userbot engine is connected.")
        if data == "menu:home": return await query.edit_message_text("🎬 CineForge Admin", reply_markup=home_keyboard(self.runtime.running))
        if data == "menu:settings": return await query.edit_message_text("⚙️ Runtime settings", reply_markup=settings_keyboard(await self._values()))
        if data == "menu:status": return await query.message.reply_text(await self.status_text())
        if data.startswith("submenu:"):
            kind = data.split(":", 1)[1]
            return await query.edit_message_text(f"⚙️ {kind.title()} settings", reply_markup=submenu_keyboard(kind))
        _, action, key = data.split(":", 2)
        if action == "toggle":
            old = await self.db.setting(key, "false"); await self.db.set_setting(key, "false" if old == "true" else "true")
            await query.edit_message_reply_markup(settings_keyboard(await self._values()))
        else:
            context.user_data["input_mode"] = "setting"; context.user_data["setting_key"] = key
            secret = " (the reply is owner-only, but delete it afterward if sensitive)" if key in {"api_hash", "arolinks_api_key"} else ""
            await query.message.reply_text(f"Send the new value for {EDITABLE_SETTINGS[key]}{secret}.")

    async def cancel_login(self, update, context):
        await self.login.abort(self.owner_id); context.user_data.clear(); await update.message.reply_text("Login cancelled.")
    async def logs(self, update, context):
        try: count = min(50, max(1, int(context.args[0]))) if context.args else 20
        except ValueError: count = 20
        rows = await self.db.recent_logs(count)
        await update.message.reply_text("\n".join(f"[{r['level']}] #{r['queue_id'] or '-'} {r['message']}" for r in rows) or "No logs.")
    async def pause(self, update, context): await self.db.set_setting("pipeline_paused", "true"); await update.message.reply_text("⏸ Pipeline paused.")
    async def resume(self, update, context): await self.db.set_setting("pipeline_paused", "false"); await update.message.reply_text("▶️ Pipeline resumed.")
    async def cancel(self, update, context):
        if not context.args: return await update.message.reply_text("Usage: /cancel <queue_id>")
        await self.db.db.execute("UPDATE queue SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'", (int(context.args[0]),)); await update.message.reply_text("Cancelled if still pending.")
    async def retry(self, update, context):
        if not context.args: return await update.message.reply_text("Usage: /retry <queue_id>")
        await self.db.db.execute("UPDATE queue SET status='pending',error_message=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='failed'", (int(context.args[0]),)); await update.message.reply_text("Requeued if failed.")
