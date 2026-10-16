"""Telegram Bot API helpers for owner notifications and channel posts."""
from __future__ import annotations
import asyncio
from typing import Any
import aiohttp

async def bot_api_request(token: str, method: str, payload: dict[str, Any] | None = None) -> Any:
    """Call Telegram Bot API, surviving brief outbound-network interruptions."""
    if not token:
        raise RuntimeError("Control-bot token is not configured")
    endpoint = f"https://api.telegram.org/bot{token}/{method}"
    timeout = aiohttp.ClientTimeout(total=30)
    last_error = None
    for attempt in range(5):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=payload or {}) as response:
                    if response.status in {502, 503, 504} and attempt < 4:
                        await response.read()
                        await asyncio.sleep(2 ** attempt)
                        continue
                    data = await response.json(content_type=None)
                    if not response.ok or not data.get("ok"):
                        raise RuntimeError(f"Bot API {method} failed: {data.get('description', response.status)}")
                    return data.get("result")
        except aiohttp.ClientConnectorError as exc:
            # No TCP connection was established, so retrying cannot duplicate a
            # Telegram send. Render occasionally reports a sub-second
            # "Network is unreachable" even while the service itself is healthy.
            last_error = exc
            if attempt >= 4:
                break
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"Telegram Bot API temporarily unreachable after 5 attempts: {last_error}") from last_error

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

async def send_channel_sticker(token: str, channel_id: int, sticker_file_id: str) -> int:
    """Send a configured sticker to a channel and return its message ID."""
    result = await bot_api_request(token, "sendSticker", {
        "chat_id": channel_id, "sticker": sticker_file_id,
    })
    return int(result["message_id"])

def _download_keyboard(download_url: str, tutorial_url: str = "") -> dict[str, Any]:
    keyboard = [[{"text": "❐ 𝗪𝗮𝘁𝗰𝗵/𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 ❐", "url": download_url}]]
    if tutorial_url:
        keyboard.append([{"text": "❓ How to Open Link", "url": tutorial_url}])
    return {"inline_keyboard": keyboard}

async def send_download_post(
    token: str,
    channel_id: int,
    text: str,
    download_url: str,
    tutorial_url: str = "",
) -> int:
    """Send and pin a new channel post containing URL inline buttons."""
    result = await bot_api_request(token, "sendMessage", {
        "chat_id": channel_id,
        "text": text,
        "reply_markup": _download_keyboard(download_url, tutorial_url),
        "disable_web_page_preview": True,
    })
    message_id = int(result["message_id"])
    await bot_api_request(token, "pinChatMessage", {
        "chat_id": channel_id,
        "message_id": message_id,
        "disable_notification": True,
    })
    return message_id

async def edit_download_post(
    token: str,
    channel_id: int,
    message_id: int,
    text: str,
    download_url: str,
    tutorial_url: str = "",
) -> None:
    """Update an existing post in place; never create a duplicate on retry."""
    try:
        await bot_api_request(token, "editMessageText", {
            "chat_id": channel_id,
            "message_id": message_id,
            "text": text,
            "reply_markup": _download_keyboard(download_url, tutorial_url),
            "disable_web_page_preview": True,
        })
    except RuntimeError as exc:
        if "message is not modified" not in str(exc).lower():
            raise
