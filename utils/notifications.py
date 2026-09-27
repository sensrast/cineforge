"""Reliable owner notifications through the private control bot."""
from __future__ import annotations
import aiohttp

async def notify_control_bot(token: str, owner_id: int, text: str) -> None:
    """Send a private message to the configured owner via Telegram Bot API."""
    if not token or not owner_id:
        raise RuntimeError("Control-bot token or owner ID is not configured")
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(endpoint, json={
            "chat_id": owner_id,
            "text": text,
            "disable_web_page_preview": True,
        }) as response:
            data = await response.json(content_type=None)
            if not response.ok or not data.get("ok"):
                raise RuntimeError(f"Control bot notification failed: {data.get('description', response.status)}")
