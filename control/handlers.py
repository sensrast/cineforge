from __future__ import annotations
from functools import wraps
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from utils.github_store import persist_state
from control.keyboards import (
    SETTING_DEFS, CATEGORIES, display_value, home_keyboard, settings_root_keyboard,
    category_keyboard, field_keyboard, input_cancel_keyboard, confirmation_keyboard,
    back_home_keyboard, status_keyboard, content_type_keyboard,manual_upload_keyboard,
    mirror_panel_keyboard,mirror_confirm_keyboard,
)
from pipeline.source_mirror import create_source,save_season_sticker,missing_seasons
from control.manual_upload import detect_quality,detect_episode,assign_qualities,summary

CFG_ATTRS = {
    "api_id": "api_id", "api_hash": "api_hash", "owner_username": "owner_username",
    "source_bot": "source_bot", "filestore_bot": "filestore_bot", "catalog_bot": "catalog_bot",
    "arolinks_api_key": "arolinks_key", "arolinks_url": "arolinks_url",
    "tutorial_link": "tutorial_link", "channel_name": "channel_name",
    "channel_description": "channel_description", "caption": "caption",
    "desired_qualities": "qualities", "language_filter": "language_filter", "search_strategy": "search_strategy", "source_timeout": "source_timeout",
    "flow_timeout": "flow_timeout", "max_search_pages": "max_search_pages",
    "default_genre": "default_genre", "catalog_language": "catalog_language",
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

    async def _value(self, key: str) -> str:
        defaults = {
            "api_id": str(self.cfg.api_id or ""), "api_hash": self.cfg.api_hash,
            "owner_username": self.cfg.owner_username, "source_bot": self.cfg.source_bot,
            "filestore_bot": self.cfg.filestore_bot, "catalog_bot": self.cfg.catalog_bot,
            "arolinks_api_key": self.cfg.arolinks_key, "arolinks_url": self.cfg.arolinks_url,
            "tutorial_link": self.cfg.tutorial_link, "channel_name": self.cfg.channel_name,
            "channel_description": self.cfg.channel_description, "caption": self.cfg.caption,
            "desired_qualities": self.cfg.qualities, "language_filter": getattr(self.cfg, "language_filter", "Hindi"),
            "search_strategy": getattr(self.cfg, "search_strategy", "First Matching Page"),
            "max_search_pages": str(getattr(self.cfg, "max_search_pages", 32)),
            "source_timeout": str(self.cfg.source_timeout), "flow_timeout": str(self.cfg.flow_timeout),
            "default_genre": getattr(self.cfg, "default_genre", "Action"),
            "catalog_language": getattr(self.cfg, "catalog_language", "Hindi"),
            "delay_between_actions": str(self.cfg.delay_actions), "delay_between_movies": str(self.cfg.delay_movies),
            "max_channels_per_day": str(self.cfg.max_channels),
            "limits_enabled": str(self.cfg.limits_enabled).lower(), "auto_catalog": str(self.cfg.auto_catalog).lower(),
        }
        return await self.db.setting(key, defaults.get(key, ""))

    async def _values(self) -> dict[str, str]:
        keys = list(SETTING_DEFS) + ["limits_enabled", "auto_catalog", "userbot_phone"]
        return {key: await self._value(key) for key in keys}

    async def _edit(self, query, text: str, reply_markup) -> None:
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
        except BadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise

    def _clear_input(self, context) -> None:
        for key in ("input_mode", "setting_key"):
            context.user_data.pop(key, None)

    async def _home(self, query) -> None:
        await self._edit(query, "🎬 CineForge Admin Panel\n\nChoose an option below. All controls are restricted to the configured owner account.", home_keyboard(self.runtime.running))

    async def _settings_root(self, query=None, message=None) -> None:
        values = await self._values()
        summary = (
            "⚙️ Settings Overview\n\n"
            f"👤 API credentials: {'Configured' if values['api_id'] and values['api_hash'] else 'Incomplete'}\n"
            f"🔐 Userbot session: {'Connected' if self.runtime.running else 'Login required'}\n"
            f"🤖 Bots: @{values['source_bot']} → @{values['filestore_bot']} → @{values['catalog_bot']}\n"
            f"🎞 Qualities: {values['desired_qualities']}\n"
            f"🌐 Source language: {values['language_filter']}\n"
            f"🛡 Limits: {values['limits_enabled'].upper()} | Daily max: {values['max_channels_per_day']}\n"
            f"🗂 Auto catalog: {values['auto_catalog'].upper()}\n\n"
            "Select a category to view every current value and its explanation."
        )
        markup = settings_root_keyboard(values)
        if query: await self._edit(query, summary, markup)
        else: await message.reply_text(summary, reply_markup=markup, disable_web_page_preview=True)

    async def _category(self, query, category: str) -> None:
        values = await self._values(); title, description = CATEGORIES[category]
        lines = [f"{title}", description, ""]
        if category == "account":
            phone = values.get("userbot_phone", "")
            masked = ("••••" + phone[-4:]) if phone else "Not saved"
            lines += [f"Session: {'Connected' if self.runtime.running else 'Not connected'}", f"Phone: {masked}", ""]
        for key, definition in SETTING_DEFS.items():
            if definition["category"] == category:
                lines.append(f"• {definition['title']}: {display_value(key, values.get(key, ''))}")
        await self._edit(query, "\n".join(lines), category_keyboard(category, values, self.runtime.running))

    async def _field(self, query, key: str) -> None:
        definition = SETTING_DEFS[key]; value = await self._value(key)
        text = (
            f"⚙️ {definition['title']}\n\n"
            f"Current value: {display_value(key, value)}\n\n"
            f"ℹ️ {definition['help']}"
        )
        await self._edit(query, text, field_keyboard(key))

    async def start(self, update, context):
        context.user_data.clear()
        await update.message.reply_text(
            "🎬 CineForge Admin Panel\n\nUse the buttons below to log in, configure the complete pipeline, and monitor jobs.",
            reply_markup=home_keyboard(self.runtime.running),
        )

    async def add(self, update, context):
        name = " ".join(context.args).strip()
        if not name: return await update.message.reply_text("Usage: /add <title>")
        context.user_data["pending_title"] = name
        await update.message.reply_text(f"Choose content type for: {name}", reply_markup=content_type_keyboard("type"))

    async def movie(self, update, context):
        name=" ".join(context.args).strip()
        if not name:return await update.message.reply_text("Usage: /movie <title>")
        qid=await self.db.add_movie(name,self.owner_id,"movie");await persist_state(self.db);await update.message.reply_text(f"✅ Movie queued #{qid}: {name}")

    async def series(self, update, context):
        name=" ".join(context.args).strip()
        if not name:return await update.message.reply_text("Usage: /series <title>")
        qid=await self.db.add_movie(name,self.owner_id,"series");await persist_state(self.db);await update.message.reply_text(f"✅ Series queued #{qid}: {name}")

    async def rebuild(self, update, context):
        name=" ".join(context.args).strip()
        if not name:return await update.message.reply_text("Usage: /rebuild <movie title>")
        qid=await self.db.add_movie(name,self.owner_id,"movie",force_rebuild=True);await persist_state(self.db)
        await update.message.reply_text(f"🔄 Forced clean movie rebuild queued #{qid}: {name}")

    async def batch(self, update, context):
        await update.message.reply_text("Choose the content type for this batch.", reply_markup=content_type_keyboard("batchtype"))

    async def manual(self, update, context):
        await update.message.reply_text("📤 Manual Upload\n\nChoose whether these files are for a movie or series. No genre will be requested.",reply_markup=content_type_keyboard("manualtype"))

    async def _manual_session(self):
        return await self.db.db.fetchone("SELECT * FROM manual_upload_sessions WHERE owner_id=?",(self.owner_id,))

    async def _manual_files(self):
        return [dict(row) for row in await self.db.db.fetchall("SELECT * FROM manual_upload_files WHERE owner_id=? ORDER BY id",(self.owner_id,))]

    async def _manual_review_text(self) -> str:
        session=await self._manual_session();files=await self._manual_files()
        if not session:return "No manual-upload session is active."
        heading=f"📤 Manual Upload — {session['title'] or 'waiting for title'}\nType: {session['content_type'].title()}\nFiles: {len(files)}"
        if not files:return heading+"\n\nSend video or document files, then press Done."
        try:return heading+"\n\n"+summary(files,session['content_type'])
        except ValueError as exc:return heading+f"\n\n⚠️ {exc}"

    async def media(self,update,context):
        session=await self._manual_session()
        if not session or session['status']!='collecting':
            return await update.message.reply_text("Press Manual Upload first, choose Movie or Series, and send the title before uploading files.",reply_markup=home_keyboard(self.runtime.running))
        media=update.message.document or update.message.video
        if not media:return
        name=getattr(media,'file_name',None) or ''
        caption=update.message.caption or ''
        quality=detect_quality(name+' '+caption)
        season,episode=detect_episode(name+' '+caption)
        existing=await self.db.db.fetchone("SELECT id FROM manual_upload_files WHERE owner_id=? AND file_unique_id=?",(self.owner_id,media.file_unique_id))
        if existing:return await update.message.reply_text("↩️ That Telegram file is already in this upload session.",reply_markup=manual_upload_keyboard())
        await self.db.db.execute("INSERT INTO manual_upload_files(owner_id,message_id,file_unique_id,file_size,file_name,caption,explicit_quality,season,episode) VALUES(?,?,?,?,?,?,?,?,?)",(
            self.owner_id,update.message.message_id,media.file_unique_id,int(getattr(media,'file_size',0) or 0),name,caption,quality,season,episode))
        await persist_state(self.db)
        files=await self._manual_files()
        detected=f"detected as {quality}" if quality else "quality will be inferred by size"
        episode_text=f", S{int(season or 1):02d}E{int(episode):02d}" if episode is not None else ''
        await update.message.reply_text(f"✅ File {len(files)} received — {detected}{episode_text}.",reply_markup=manual_upload_keyboard())

    async def _mirror_panel(self,query=None,message=None):
        rows=await self.db.db.fetchall('SELECT * FROM mirror_sources ORDER BY id DESC')
        text='🔄 Source Mirror\n\nConnect a channel where the userbot account is already a subscriber. Historical video/document files will be imported, then future files will sync after a 5-minute quality buffer.'
        if query:await self._edit(query,text,mirror_panel_keyboard(rows))
        else:await message.reply_text(text,reply_markup=mirror_panel_keyboard(rows))

    async def _resolve_mirror_source(self,ref):
        if not self.runtime.running:raise RuntimeError('Userbot must be connected first.')
        chat=await self.runtime.client.get_chat(ref)
        if 'channel' not in str(chat.type).lower():raise RuntimeError('Selected chat is not a channel.')
        return {'chat_id':chat.id,'title':chat.title or str(chat.id),'ref':str(ref)}

    async def source_forward(self,update,context):
        if context.user_data.get('input_mode')!='mirror_source':
            if update.message.document or update.message.video:return await self.media(update,context)
            return
        origin=getattr(update.message,'forward_origin',None);chat=getattr(origin,'chat',None)
        if not chat:return await update.message.reply_text('Forward a channel post (with forward tag), or send @username / t.me link / numeric channel ID.')
        try:candidate=await self._resolve_mirror_source(chat.id)
        except Exception as exc:return await update.message.reply_text(f'❌ Could not resolve source: {exc}')
        context.user_data['mirror_candidate']=candidate;context.user_data.pop('input_mode',None)
        await update.message.reply_text(f"Confirm source channel:\n\n{candidate['title']}\nID: {candidate['chat_id']}\n\nA same-name destination channel will be created.",reply_markup=mirror_confirm_keyboard())

    async def text(self, update, context):
        mode = context.user_data.get("input_mode"); text = update.message.text.strip()
        if mode=='mirror_source':
            ref=text
            if 't.me/' in ref:ref='@'+ref.rstrip('/').rsplit('/',1)[-1]
            elif ref.lstrip('-').isdigit():ref=int(ref)
            try:candidate=await self._resolve_mirror_source(ref)
            except Exception as exc:return await update.message.reply_text(f'❌ Could not resolve source: {exc}\nSend another source or cancel.')
            context.user_data['mirror_candidate']=candidate;context.user_data.pop('input_mode',None)
            return await update.message.reply_text(f"Confirm source channel:\n\n{candidate['title']}\nID: {candidate['chat_id']}\n\nA same-name destination channel will be created.",reply_markup=mirror_confirm_keyboard())
        if mode == "phone":
            try:
                await self.login.send_code(self.owner_id, text); context.user_data["input_mode"] = "otp"
                await update.message.reply_text("📨 Telegram sent a login code. Send it here; spaces are allowed.\n\nThe OTP message will be deleted immediately.", reply_markup=back_home_keyboard())
            except Exception as exc: await update.message.reply_text(f"❌ Could not send code: {exc}", reply_markup=back_home_keyboard())
            return
        if mode == "otp":
            try:
                try: await update.message.delete()
                except Exception: pass
                result = await self.login.submit_code(self.owner_id, text)
                if result == "password":
                    context.user_data["input_mode"] = "password"
                    await update.effective_chat.send_message("🔑 Send your two-step-verification password. It will be deleted immediately.", reply_markup=back_home_keyboard())
                else:
                    context.user_data.clear(); await update.effective_chat.send_message("✅ Login complete. Session saved and engine started.", reply_markup=home_keyboard(True))
            except Exception as exc: await update.effective_chat.send_message(f"❌ Login failed: {exc}", reply_markup=back_home_keyboard())
            return
        if mode == "password":
            try:
                try: await update.message.delete()
                except Exception: pass
                await self.login.submit_password(self.owner_id, text); context.user_data.clear()
                await update.effective_chat.send_message("✅ Login complete. Session saved and engine started.", reply_markup=home_keyboard(True))
            except Exception as exc: await update.effective_chat.send_message(f"❌ Login failed: {exc}", reply_markup=back_home_keyboard())
            return
        if mode == "setting":
            key = context.user_data.get("setting_key")
            try:
                value = self._validate_setting(key, text)
                if SETTING_DEFS[key].get("secret"):
                    try: await update.message.delete()
                    except Exception: pass
                await self._save_setting(key, value)
                self._clear_input(context)
                await update.effective_chat.send_message(f"✅ {SETTING_DEFS[key]['title']} saved.\nNew value: {display_value(key, value)}", reply_markup=field_keyboard(key))
            except Exception as exc:
                await update.effective_chat.send_message(f"❌ {exc}\n\nPlease try again or press Cancel.", reply_markup=input_cancel_keyboard(key))
            return
        session=await self._manual_session()
        if mode=="manual_title" or (session and session['status']=='awaiting_title'):
            if not text:return await update.message.reply_text("Title cannot be empty.")
            await self.db.db.execute("UPDATE manual_upload_sessions SET title=?,status='collecting',updated_at=CURRENT_TIMESTAMP WHERE owner_id=?",(text,self.owner_id))
            context.user_data.clear();await persist_state(self.db)
            return await update.message.reply_text(
                f"📤 {session['content_type'].title() if session else 'Manual'}: {text}\n\nSend or forward every video/document file now. Explicit 480p/720p/1080p/2160p text is respected; missing qualities are inferred by file size. Press Done after the last file.",
                reply_markup=manual_upload_keyboard())
        if mode in {"batch", "single_typed"}:
            kind=context.user_data.get("content_type","movie")
            names=[line.strip() for line in text.splitlines() if line.strip()] if mode=="batch" else [text]
            context.user_data.clear();ids=[await self.db.add_movie(name,self.owner_id,kind) for name in names];await persist_state(self.db)
            return await update.message.reply_text(f"✅ Queued {len(ids)} {kind} title(s): "+", ".join(map(str,ids)),reply_markup=home_keyboard(self.runtime.running))
        context.user_data["pending_title"]=text
        await update.message.reply_text(f"Is this a movie or series?\n\n{text}",reply_markup=content_type_keyboard("type"))

    def _validate_setting(self, key: str, value: str) -> str:
        definition = SETTING_DEFS[key]; kind = definition["kind"]; value = value.strip()
        if not value: raise ValueError("Value cannot be empty.")
        if kind in {"int", "int_positive"}:
            number = int(value)
            if kind == "int_positive" and number < 1: raise ValueError("Enter a whole number greater than zero.")
            if kind == "int" and number < 0: raise ValueError("Enter zero or a positive whole number.")
            if key == "api_id" and number <= 0: raise ValueError("API ID must be greater than zero.")
            if key == "max_search_pages" and number > 100: raise ValueError("Maximum search pages cannot exceed 100.")
            if key in {"source_timeout", "flow_timeout"} and not 5 <= number <= 600: raise ValueError("Timeout must be between 5 and 600 seconds.")
            value = str(number)
        elif kind == "float":
            number = float(value)
            if not 0 <= number <= 86400: raise ValueError("Delay must be between 0 and 86400 seconds.")
            value = str(number)
        elif kind == "username": value = value.lstrip("@")
        elif kind in {"url", "url_optional"} and not value.startswith(("http://", "https://")): raise ValueError("Enter a complete http:// or https:// URL.")
        elif kind == "qualities":
            allowed = {"480p", "720p", "1080p", "2160p", "4k"}
            parts = [part.strip().lower() for part in value.split(",") if part.strip()]
            if not parts or any(part not in allowed for part in parts): raise ValueError("Use comma-separated values from 480p, 720p, 1080p, 2160p, 4K.")
            value = ",".join("4K" if part == "4k" else part for part in parts)
        elif kind == "template":
            lowered = value.lower()
            if key == "channel_name" and "{movie}" not in lowered: raise ValueError("Channel-name format must include {movie} (any letter case is accepted).")
            if key == "caption" and ("{movie}" not in lowered or "{quality}" not in lowered): raise ValueError("Caption must include {movie} and {quality} (any letter case is accepted).")
            if key == "promotion_caption" and "{movie}" not in lowered: raise ValueError("Promotion caption must include {movie}.")
        return value

    async def _save_setting(self, key: str, value: str) -> None:
        await self.db.set_setting(key, value)
        attr = CFG_ATTRS.get(key)
        if attr:
            converter = int if key in {"api_id", "max_channels_per_day", "source_timeout", "flow_timeout", "max_search_pages"} else float if key in {"delay_between_actions", "delay_between_movies"} else str
            setattr(self.cfg, attr, converter(value))
        await persist_state(self.db)

    async def status_text(self) -> str:
        rows = await self.db.queue_list(); today = await self.db.count_today(); paused = await self.db.setting("pipeline_paused", "false")
        lines = [f'📊 Live Status', f'Pipeline: {"PAUSED" if paused == "true" else "RUNNING"}', f'Userbot: {"CONNECTED" if self.runtime.running else "LOGIN REQUIRED"}', f"Channels today: {today}", f"Active queue: {len(rows)}", ""]
        for row in rows[:15]:
            line = f"• #{row['id']} [{row['content_type'].upper()}] {row['movie_name']} — stage {row['current_stage']}/10 ({row['status']})"
            if row['status']=='deferred' and row['next_attempt_at']:
                line+=f"\n  Automatic retry: {row['next_attempt_at']} UTC"
            if row['status'] in {'failed','deferred'} and row['error_message']:
                line += f"\n  Info: {row['error_message'][:180]}"
            lines.append(line)
        return "\n".join(lines)

    async def status(self, update, context):
        rows = await self.db.queue_list()
        await update.message.reply_text(await self.status_text(), reply_markup=status_keyboard(rows))
    async def settings(self, update, context): await self._settings_root(message=update.message)
    async def toggle_limits(self, update, context):
        old = await self.db.setting("limits_enabled", "false"); new = "false" if old == "true" else "true"
        await self.db.set_setting("limits_enabled", new); self.cfg.limits_enabled = new == "true"
        await persist_state(self.db)
        await update.message.reply_text(f"Limits: {new.upper()}", reply_markup=back_home_keyboard())

    async def callback(self, update, context):
        query = update.callback_query; await query.answer(); data = query.data
        if data.startswith('mirror:'):
            parts=data.split(':');action=parts[1]
            if action=='panel':return await self._mirror_panel(query=query)
            if action=='add':
                context.user_data.clear();context.user_data['input_mode']='mirror_source'
                return await self._edit(query,'Send @username, t.me link, numeric channel ID, or forward any post from the source channel.\n\nThe userbot account must already be subscribed.',back_home_keyboard())
            if action=='cancel':context.user_data.clear();return await self._mirror_panel(query=query)
            if action=='confirm':
                candidate=context.user_data.get('mirror_candidate')
                if not candidate:return await self._edit(query,'Source confirmation expired. Select it again.',mirror_panel_keyboard())
                if not self.runtime.running:return await self._edit(query,'Userbot is not connected.',back_home_keyboard())
                try:
                    source_id,seasons,invite=await create_source(self.runtime.worker.ctx,candidate['chat_id'],candidate['ref'],candidate['title'])
                except Exception as exc:return await self._edit(query,f'❌ Could not create mirror: {exc}',back_home_keyboard())
                context.user_data.clear()
                if seasons:
                    context.user_data.update(input_mode='mirror_sticker',mirror_source_id=source_id,mirror_seasons=seasons)
                    return await self._edit(query,f"✅ Destination created:\n{invite}\n\nNow send the custom sticker for Season {seasons[0]}. The existing End sticker will be used at season boundaries.",back_home_keyboard())
                return await self._edit(query,f'✅ Mirror connected and historical sync started.\n{invite}',home_keyboard(self.runtime.running))
            if action=='view':
                source_id=int(parts[2]);row=await self.db.db.fetchone('SELECT * FROM mirror_sources WHERE id=?',(source_id,));missing=await missing_seasons(self.runtime.worker.ctx,source_id) if row and self.runtime.running else []
                if missing:context.user_data.update(input_mode='mirror_sticker',mirror_source_id=source_id,mirror_seasons=missing)
                return await self._edit(query,(f"🔄 {row['source_title']}\nStatus: {row['status']}\nDestination: {row['invite_link']}"+(f"\n\nSend Season {missing[0]} sticker now." if missing else '')) if row else 'Mirror not found.',mirror_panel_keyboard())
        if data.startswith("addmode:"):
            kind=data.split(":",1)[1];context.user_data.clear();context.user_data.update(input_mode="single_typed",content_type=kind)
            return await self._edit(query,f"Send the {kind} title.",back_home_keyboard())
        if data.startswith("batchtype:"):
            kind=data.split(":",1)[1];context.user_data.clear();context.user_data.update(input_mode="batch",content_type=kind)
            return await self._edit(query,f"Send {kind} titles, one per line.",back_home_keyboard())
        if data.startswith("manualtype:"):
            kind=data.split(":",1)[1];context.user_data.clear();context.user_data['input_mode']='manual_title'
            await self.db.db.execute("DELETE FROM manual_upload_files WHERE owner_id=?",(self.owner_id,))
            await self.db.db.execute("INSERT INTO manual_upload_sessions(owner_id,content_type,title,status) VALUES(?,?,NULL,'awaiting_title') ON CONFLICT(owner_id) DO UPDATE SET content_type=excluded.content_type,title=NULL,status='awaiting_title',updated_at=CURRENT_TIMESTAMP",(self.owner_id,kind))
            await persist_state(self.db)
            return await self._edit(query,f"📤 Manual {kind.title()} Upload\n\nSend the title now. No genre will be requested.",back_home_keyboard())
        if data.startswith("manual:"):
            action=data.split(":",1)[1]
            if action=='start':
                return await self._edit(query,"📤 Manual Upload\n\nChoose Movie or Series. No genre will be requested.",content_type_keyboard('manualtype'))
            session=await self._manual_session()
            if action=='cancel':
                await self.db.db.execute("DELETE FROM manual_upload_files WHERE owner_id=?",(self.owner_id,));await self.db.db.execute("DELETE FROM manual_upload_sessions WHERE owner_id=?",(self.owner_id,));context.user_data.clear();await persist_state(self.db)
                return await self._edit(query,"🗑 Manual upload cancelled. No job was created.",home_keyboard(self.runtime.running))
            if not session:return await self._edit(query,"This manual-upload session expired. Start a new one.",home_keyboard(self.runtime.running))
            if action=='review':return await self._edit(query,await self._manual_review_text(),manual_upload_keyboard())
            if action=='remove':
                last=await self.db.db.fetchone("SELECT id FROM manual_upload_files WHERE owner_id=? ORDER BY id DESC LIMIT 1",(self.owner_id,))
                if last:await self.db.db.execute("DELETE FROM manual_upload_files WHERE id=?",(last['id'],));await persist_state(self.db)
                return await self._edit(query,await self._manual_review_text(),manual_upload_keyboard())
            if action=='done':
                files=await self._manual_files()
                if not files:return await self._edit(query,"Send at least one video/document before pressing Done.",manual_upload_keyboard())
                try:assigned=assign_qualities(files,session['content_type'])
                except ValueError as exc:return await self._edit(query,f"⚠️ Cannot finish yet:\n\n{exc}",manual_upload_keyboard())
                payload=[{
                    'quality':item['quality'],'season':item.get('season'),'episode':item.get('episode'),
                    'source_message_id':item['message_id'],'source_chat_id':self.owner_id,'manual_bot_api':True,
                    'source_name':item.get('file_name') or item.get('caption') or f"Manual file {index}",
                    'file_unique_id':item['file_unique_id'],'file_size':item.get('file_size',0),
                } for index,item in enumerate(assigned,1)]
                qid=await self.db.add_manual(session['title'],self.owner_id,session['content_type'],payload)
                await self.db.db.execute("DELETE FROM manual_upload_files WHERE owner_id=?",(self.owner_id,));await self.db.db.execute("DELETE FROM manual_upload_sessions WHERE owner_id=?",(self.owner_id,));context.user_data.clear();await persist_state(self.db)
                return await self._edit(query,f"✅ Manual {session['content_type']} queued as job #{qid}.\n\n{summary(files,session['content_type'])}\n\nMovie Hunt was skipped. The normal channel, batch-link, backup, catalog, folder, and promotion stages will continue automatically.",home_keyboard(self.runtime.running))
        if data.startswith("type:"):
            kind=data.split(":",1)[1];title=context.user_data.pop("pending_title","")
            if not title:return await self._edit(query,"The pending title expired. Send it again.",home_keyboard(self.runtime.running))
            qid=await self.db.add_movie(title,self.owner_id,kind);await persist_state(self.db);context.user_data.clear()
            return await self._edit(query,f"✅ {kind.title()} queued #{qid}: {title}",home_keyboard(self.runtime.running))
        if data.startswith("nav:"):
            self._clear_input(context)
            if data == "nav:home":
                await self.login.abort(self.owner_id); return await self._home(query)
            if data == "nav:settings": return await self._settings_root(query=query)
            if data.startswith("nav:cat:"): return await self._category(query, data.split(":", 2)[2])
            if data == "nav:status":
                rows = await self.db.queue_list()
                return await self._edit(query, await self.status_text(), status_keyboard(rows))
            if data == "nav:logs":
                rows = await self.db.recent_logs(15); text = "📝 Recent Logs\n\n" + ("\n".join(f"[{r['level']}] #{r['queue_id'] or '-'} {r['message']}" for r in rows) or "No logs yet.")
                return await self._edit(query, text[:3900], back_home_keyboard())
            if data == "nav:help":
                return await self._edit(query, "❓ Help\n\n1. Configure Telegram API credentials.\n2. Press Login Userbot and complete OTP/2FA.\n3. Review integration usernames and links.\n4. Add titles with /add or plain text.\n5. Monitor progress from Live Status.\n\nEvery submenu shows its current saved values.", back_home_keyboard())
        if data == "auth:start":
            if not await self.login.credentials_ready():
                return await self._edit(query, "⚠️ Telegram API ID and API Hash are required first.", back_home_keyboard())
            context.user_data["input_mode"] = "phone"
            return await self._edit(query, "🔐 Userbot Login\n\nSend the Telegram phone number with country code, for example +919876543210.", back_home_keyboard())
        if data == "auth:status": return await self._edit(query, "✅ Userbot Connected\n\nThe MTProto engine and queue worker are running.", back_home_keyboard())
        if data == "auth:logout_ask": return await self._edit(query, "⚠️ Log out userbot?\n\nThis stops the pipeline and removes the saved local session. Pending queue records are preserved.", confirmation_keyboard("auth:logout_do", "nav:cat:account"))
        if data == "auth:logout_do":
            await self.runtime.stop(); await self.db.delete_setting("userbot_session_string"); self.cfg.session_string = ""
            return await self._edit(query, "✅ Userbot logged out and the saved session was removed.", back_home_keyboard())
        if data.startswith("job:retry:"):
            queue_id = int(data.rsplit(":", 1)[1])
            await self.db.retry_failed(queue_id);await persist_state(self.db)
            rows = await self.db.queue_list()
            return await self._edit(query, "✅ Job requeued.\n\n" + await self.status_text(), status_keyboard(rows))
        if data.startswith("job:cancel:"):
            queue_id=int(data.rsplit(":",1)[1])
            changed=await self.db.db.execute("UPDATE queue SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status NOT IN ('completed','cancelled')",(queue_id,));await persist_state(self.db)
            rows=await self.db.queue_list()
            return await self._edit(query,f"🛑 Cancellation requested for job #{queue_id}. The active operation will stop at its next checkpoint.\n\n"+await self.status_text(),status_keyboard(rows))
        if data.startswith("cfg:"):
            parts = data.split(":"); action = parts[1]; key = parts[2]
            if action == "toggle":
                old = await self._value(key); new = "false" if old == "true" else "true"; await self.db.set_setting(key, new)
                if key == "limits_enabled": self.cfg.limits_enabled = new == "true"
                if key == "auto_catalog": self.cfg.auto_catalog = new == "true"
                await persist_state(self.db)
                return await self._settings_root(query=query)
            if action == "open": return await self._field(query, key)
            if action == "edit":
                context.user_data["input_mode"] = "setting"; context.user_data["setting_key"] = key
                definition = SETTING_DEFS[key]
                return await self._edit(query, f"✏️ Change {definition['title']}\n\n{definition['help']}\n\nSend the new value now.", input_cancel_keyboard(key))
            if action == "clear":
                await self.db.set_setting(key, ""); attr = CFG_ATTRS.get(key)
                if attr: setattr(self.cfg, attr, "")
                await persist_state(self.db)
                return await self._field(query, key)
            if action == "choose":
                value = ":".join(parts[3:]); await self._save_setting(key, value); return await self._field(query, key)

    async def photo(self,update,context):
        key=context.user_data.get("setting_key")
        if context.user_data.get("input_mode")!="setting" or not key or SETTING_DEFS.get(key,{}).get("kind")!="photo":
            return await update.message.reply_text("Open Settings → Catalog Defaults → Promotion Image first.",reply_markup=back_home_keyboard())
        value=update.message.photo[-1].file_id
        await self._save_setting(key,value);self._clear_input(context)
        await update.message.reply_text(f"✅ {SETTING_DEFS[key]['title']} saved.",reply_markup=field_keyboard(key))

    async def sticker(self, update, context):
        if context.user_data.get('input_mode')=='mirror_sticker':
            source_id=int(context.user_data['mirror_source_id']);seasons=list(context.user_data.get('mirror_seasons') or [])
            if not seasons:return await update.message.reply_text('No season sticker is pending.',reply_markup=home_keyboard(self.runtime.running))
            season=int(seasons[0]);missing=await save_season_sticker(self.runtime.worker.ctx,source_id,season,update.message.sticker.file_id)
            if missing:
                context.user_data['mirror_seasons']=missing
                return await update.message.reply_text(f'✅ Season {season} sticker saved. Now send the sticker for Season {missing[0]}.',reply_markup=back_home_keyboard())
            context.user_data.clear();return await update.message.reply_text(f'✅ Season {season} sticker saved. Historical sync started.',reply_markup=home_keyboard(self.runtime.running))
        key = context.user_data.get("setting_key")
        if context.user_data.get("input_mode") != "setting" or not key or SETTING_DEFS.get(key, {}).get("kind") != "sticker":
            return await update.message.reply_text("Open Settings → Channel & Captions and choose a sticker slot first.", reply_markup=back_home_keyboard())
        value = update.message.sticker.file_id
        await self._save_setting(key, value)
        self._clear_input(context)
        await update.message.reply_text(f"✅ {SETTING_DEFS[key]['title']} saved.", reply_markup=field_keyboard(key))

    async def cancel_login(self, update, context):
        await self.login.abort(self.owner_id); context.user_data.clear(); await update.message.reply_text("Login cancelled.", reply_markup=home_keyboard(self.runtime.running))
    async def logs(self, update, context):
        try: count = min(50, max(1, int(context.args[0]))) if context.args else 20
        except ValueError: count = 20
        rows = await self.db.recent_logs(count); await update.message.reply_text(("\n".join(f"[{r['level']}] #{r['queue_id'] or '-'} {r['message']}" for r in rows) or "No logs.")[:3900], reply_markup=back_home_keyboard())
    async def pause(self, update, context):
        await self.db.set_setting("pipeline_paused","true");await persist_state(self.db)
        await update.message.reply_text("⏸ Pipeline paused.",reply_markup=back_home_keyboard())
    async def resume(self, update, context):
        await self.db.set_setting("pipeline_paused","false");await persist_state(self.db)
        await update.message.reply_text("▶️ Pipeline resumed.",reply_markup=back_home_keyboard())
    async def cancel(self, update, context):
        if not context.args: return await update.message.reply_text("Usage: /cancel <queue_id>", reply_markup=back_home_keyboard())
        qid=int(context.args[0]);await self.db.db.execute("UPDATE queue SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status NOT IN ('completed','cancelled')",(qid,));await persist_state(self.db);await update.message.reply_text(f"🛑 Cancellation requested for job #{qid}. Active work will stop at its next checkpoint.",reply_markup=back_home_keyboard())
    async def retry(self, update, context):
        if not context.args: return await update.message.reply_text("Usage: /retry <queue_id>", reply_markup=back_home_keyboard())
        await self.db.retry_failed(int(context.args[0]));await persist_state(self.db);await update.message.reply_text("Requeued if failed. Search/fetch failures restart cleanly from page 1.",reply_markup=back_home_keyboard())
