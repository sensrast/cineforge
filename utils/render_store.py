"""Persist small runtime state in Render environment variables."""
from __future__ import annotations
import asyncio
import json
import os
import aiohttp
_lock = asyncio.Lock()

async def set_render_env(key: str, value: str) -> bool:
    api_key = os.getenv("RENDER_API_KEY", "")
    service_id = os.getenv("RENDER_SERVICE_ID", "")
    if not api_key or not service_id:
        return False
    endpoint = f"https://api.render.com/v1/services/{service_id}/env-vars"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=30)
    async with _lock:
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(endpoint) as response:
                response.raise_for_status(); records = await response.json()
            values = {item.get("envVar", item)["key"]: item.get("envVar", item).get("value", "") for item in records}
            if values.get(key) == value:
                return True
            values[key] = value
            payload = [{"key": name, "value": stored} for name, stored in values.items()]
            async with session.put(endpoint, json=payload) as response:
                response.raise_for_status(); await response.read()
    return True

async def persist_settings(db) -> bool:
    rows = await db.db.fetchall("SELECT key,value FROM settings WHERE key != 'userbot_session_string'")
    payload = {row["key"]: row["value"] for row in rows}
    return await set_render_env("CINEFORGE_SETTINGS_JSON", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

async def persist_channels(db) -> bool:
    rows = await db.db.fetchall("SELECT movie_name,channel_id,invite_link,batch_link,shortened_link FROM created_channels")
    payload = [dict(row) for row in rows]
    return await set_render_env("CINEFORGE_CHANNELS_JSON", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
