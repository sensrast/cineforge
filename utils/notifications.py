"""Telegram Bot API helpers for owner notifications and channel posts."""
from __future__ import annotations
from typing import Any
import aiohttp

async def bot_api_request(token: str, method: str, payload: dict[str, Any] | None = None) -> Any:
    """Call a Telegram Bot API method and return its result."""
    if not token:
        raise RuntimeError("Control-bot token is not configured")
    endpoint = f"https://api.telegram.org/bot{token}/{method}"
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(endpoint, json=payload or {}) as response:
            data = await response.json(content_type=None)
            if not response.ok or not data.get("ok"):
                raise RuntimeError(f"Bot API {method} failed: {data.get('description', response.status)}")
            return data.get("result")

async def notify_control_bot(token: str, owner_id: int, text: str) -> None:
    """Send a private message to the configured owner via the control bot."""
    if not owner_id:
        raise RuntimeError("Owner ID is not configured")
    await bot_api_request(token, "sendMessage", {
        "chat_id": owner_id,
        "text": text,
        "disable_web_page_preview": True,
    })

async def get_control_bot_identity(token: str) -> dict[str, Any]:
    """Return the control bot's Bot API identity."""
    return await bot_api_request(token, "getMe")

async def send_download_post(
    token: str,
    channel_id: int,
    text: str,
    download_url: str,
    tutorial_url: str = "",
) -> int:
    """Send and pin a channel post containing URL inline buttons."""
    keyboard = [[{"text": "🚀 Download Movie", "url": download_url}]]
    if tutorial_url:
        keyboard.append([{"text": "❓ How to Open Link", "url": tutorial_url}])
    result = await bot_api_request(token, "sendMessage", {
        "chat_id": channel_id,
        "text": text,
        "reply_markup": {"inline_keyboard": keyboard},
        "disable_web_page_preview": True,
    })
    message_id = int(result["message_id"])
    await bot_api_request(token, "pinChatMessage", {
        "chat_id": channel_id,
        "message_id": message_id,
        "disable_notification": True,
    })
    return message_id
