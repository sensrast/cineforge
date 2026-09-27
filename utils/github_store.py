"""Durable small-state storage in a separate private GitHub repository."""
from __future__ import annotations
import asyncio
import base64
import json
import os
import aiohttp
_lock = asyncio.Lock()


def _config():
    return (
        os.getenv("GITHUB_STATE_TOKEN", ""),
        os.getenv("GITHUB_STATE_REPO", ""),
        os.getenv("GITHUB_STATE_PATH", "cineforge-state.json"),
    )

async def load_state() -> dict:
    token, repo, path = _config()
    if not token or not repo:
        return {}
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.get(url) as response:
            if response.status == 404:
                return {}
            response.raise_for_status(); data = await response.json()
    return json.loads(base64.b64decode(data["content"]).decode("utf-8"))

async def persist_state(db) -> bool:
    token, repo, path = _config()
    if not token or not repo:
        return False
    settings_rows = await db.db.fetchall("SELECT key,value FROM settings WHERE key != 'userbot_session_string'")
    channel_rows = await db.db.fetchall("SELECT movie_name,content_type,channel_id,invite_link,batch_link,shortened_link FROM created_channels")
    state = {
        "settings": {row["key"]: row["value"] for row in settings_rows},
        "channels": [dict(row) for row in channel_rows],
    }
    content = base64.b64encode(json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode()).decode()
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with _lock:
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as session:
            sha = None
            async with session.get(url) as response:
                if response.status == 200:
                    sha = (await response.json()).get("sha")
                elif response.status != 404:
                    response.raise_for_status()
            payload = {"message": "Update CineForge runtime state", "content": content}
            if sha: payload["sha"] = sha
            async with session.put(url, json=payload) as response:
                response.raise_for_status(); await response.read()
    return True
