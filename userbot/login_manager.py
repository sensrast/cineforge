"""Owner-only, control-bot-driven MTProto authentication flow."""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from typing import Awaitable, Callable
import aiohttp
from pyrogram import Client
from pyrogram.errors import (
    BadRequest, PhoneCodeExpired, PhoneCodeInvalid, PhoneNumberInvalid,
    SessionPasswordNeeded, PasswordHashInvalid,
)
from database.queries import Queries
from config import Config
log = logging.getLogger(__name__)

@dataclass
class PendingLogin:
    client: Client
    phone: str
    phone_code_hash: str

class LoginManager:
    """Creates a string session without writing a Pyrogram session file."""
    def __init__(self, db: Queries, cfg: Config, start_engine: Callable[[str], Awaitable[None]]):
        self.db = db
        self.cfg = cfg
        self.start_engine = start_engine
        self.pending: dict[int, PendingLogin] = {}

    async def credentials_ready(self) -> bool:
        api_id = await self.db.setting("api_id", str(self.cfg.api_id or ""))
        api_hash = await self.db.setting("api_hash", self.cfg.api_hash)
        return bool(api_id and api_hash)

    async def send_code(self, owner_id: int, phone: str) -> None:
        """Connect and ask Telegram to send a login code to the account."""
        await self.abort(owner_id)
        api_id = int(await self.db.setting("api_id", str(self.cfg.api_id or 0)))
        api_hash = await self.db.setting("api_hash", self.cfg.api_hash)
        if not api_id or not api_hash:
            raise RuntimeError("Set API_ID and API_HASH in Settings before login.")
        client = Client(
            f"cineforge_login_{owner_id}", api_id=api_id, api_hash=api_hash,
            in_memory=True, no_updates=True,
        )
        await client.connect()
        try:
            sent = await client.send_code(phone)
        except Exception:
            await client.disconnect()
            raise
        self.pending[owner_id] = PendingLogin(client, phone, sent.phone_code_hash)

    async def submit_code(self, owner_id: int, code: str) -> str:
        """Submit OTP; return 'password' when Telegram requires 2FA."""
        pending = self.pending.get(owner_id)
        if not pending:
            raise RuntimeError("Login expired. Press Login Userbot again.")
        code = "".join(ch for ch in code if ch.isdigit())
        try:
            await pending.client.sign_in(pending.phone, pending.phone_code_hash, code)
        except SessionPasswordNeeded:
            return "password"
        except (PhoneCodeInvalid, PhoneCodeExpired) as exc:
            raise RuntimeError(str(exc)) from exc
        await self._finish(owner_id)
        return "complete"

    async def submit_password(self, owner_id: int, password: str) -> None:
        pending = self.pending.get(owner_id)
        if not pending:
            raise RuntimeError("Login expired. Press Login Userbot again.")
        try:
            await pending.client.check_password(password)
        except PasswordHashInvalid as exc:
            raise RuntimeError("Incorrect two-step verification password.") from exc
        await self._finish(owner_id)

    async def _finish(self, owner_id: int) -> None:
        pending = self.pending.pop(owner_id)
        try:
            session = await pending.client.export_session_string()
            await self.db.set_setting("userbot_session_string", session)
            await self.db.set_setting("userbot_phone", pending.phone)
            self.cfg.session_string = session
            await self._persist_render_session(session)
        finally:
            await pending.client.disconnect()
        await self.start_engine(session)

    async def _persist_render_session(self, session: str) -> None:
        """Optionally persist the session as a Render environment secret.

        This prevents loss on Render's ephemeral filesystem. The feature is
        enabled only when RENDER_API_KEY and RENDER_SERVICE_ID are configured.
        """
        api_key = os.getenv("RENDER_API_KEY", "")
        service_id = os.getenv("RENDER_SERVICE_ID", "")
        if not api_key or not service_id:
            return
        endpoint = f"https://api.render.com/v1/services/{service_id}/env-vars"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        timeout = aiohttp.ClientTimeout(total=30)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as http:
                async with http.get(endpoint) as response:
                    response.raise_for_status()
                    records = await response.json()
                values = {item.get("envVar", item)["key"]: item.get("envVar", item).get("value", "") for item in records}
                values["USERBOT_SESSION_STRING"] = session
                payload = [{"key": key, "value": value} for key, value in values.items()]
                async with http.put(endpoint, json=payload) as response:
                    response.raise_for_status()
                    await response.read()
            log.info("Userbot session persisted to Render environment")
        except Exception:
            # Local database persistence still succeeds; do not invalidate a
            # successful Telegram login because the optional backup failed.
            log.exception("Could not persist userbot session to Render environment")

    async def abort(self, owner_id: int) -> None:
        pending = self.pending.pop(owner_id, None)
        if pending:
            try:
                await pending.client.disconnect()
            except Exception:
                log.debug("Pending login disconnect failed", exc_info=True)
