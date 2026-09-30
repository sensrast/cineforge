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
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with _lock:
        # Read the database only after acquiring the process lock. Every saved
        # setting is durable, including API credentials, phone, and session.
        settings_rows = await db.db.fetchall("SELECT key,value FROM settings")
        channel_rows = await db.db.fetchall("SELECT movie_name,content_type,channel_id,invite_link,batch_link,shortened_link,owner_admin_confirmed FROM created_channels")
        local_settings = {row["key"]: row["value"] for row in settings_rows}
        local_channels = [dict(row) for row in channel_rows]
        queue_rows=await db.db.fetchall("SELECT * FROM queue WHERE status NOT IN ('completed','cancelled') ORDER BY id")
        active_queue=[dict(row) for row in queue_rows]
        pipeline=[]
        for row in queue_rows:
            state_row=await db.db.fetchone("SELECT * FROM pipeline_state WHERE queue_id=?",(row["id"],))
            if state_row:pipeline.append(dict(state_row))
        manual_sessions=[dict(row) for row in await db.db.fetchall("SELECT * FROM manual_upload_sessions")]
        manual_files=[dict(row) for row in await db.db.fetchall("SELECT * FROM manual_upload_files ORDER BY id")]
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as session:
            for attempt in range(3):
                sha = None; remote_settings = {}
                async with session.get(url) as response:
                    if response.status == 200:
                        current=await response.json();sha=current.get("sha")
                        try:
                            remote=json.loads(base64.b64decode(current["content"]).decode("utf-8"))
                            remote_settings=remote.get("settings",{})
                        except Exception:
                            remote_settings={}
                    elif response.status != 404:
                        response.raise_for_status()
                # Never erase a durable setting merely because a fresh local
                # SQLite database did not contain that key. Local values win.
                merged_settings=dict(remote_settings);merged_settings.update(local_settings)
                state={"version":4,"settings":merged_settings,"channels":local_channels,"queue":active_queue,"pipeline":pipeline,"manual_sessions":manual_sessions,"manual_files":manual_files}
                content=base64.b64encode(json.dumps(state,ensure_ascii=False,separators=(",", ":")).encode()).decode()
                payload={"message":"Update CineForge runtime state","content":content}
                if sha:payload["sha"]=sha
                async with session.put(url,json=payload) as response:
                    if response.status in {409,422} and attempt<2:
                        await response.read();await asyncio.sleep(.5*(attempt+1));continue
                    response.raise_for_status();await response.read();return True
    return False
