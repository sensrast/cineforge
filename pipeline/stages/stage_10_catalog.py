"""Catalog-bot wizard with edited-message-aware synchronization."""
from __future__ import annotations
import asyncio
import json
import re
import time
from pathlib import Path
from pipeline.context import PipelineContext
from pipeline.stages.common import click_matching
from utils.text_parser import clean_title, is_series


def _fingerprint(message) -> tuple:
    labels = []
    if message.reply_markup and getattr(message.reply_markup, "inline_keyboard", None):
        for row in message.reply_markup.inline_keyboard:
            labels.extend((button.text or "", str(button.callback_data or "")) for button in row)
    return (message.text or message.caption or "", str(message.edit_date or ""), tuple(labels))

async def _snapshot(ctx: PipelineContext) -> dict[int, tuple]:
    result = {}
    async for message in ctx.client.get_chat_history(ctx.cfg.catalog_bot, limit=20):
        if not message.outgoing:
            result[message.id] = _fingerprint(message)
    return result


def _message_has_button(message, patterns: list[str]) -> bool:
    markup = message.reply_markup
    if not markup or not getattr(markup, "inline_keyboard", None):
        return False
    for row in markup.inline_keyboard:
        for button in row:
            haystacks = (button.text or "", str(button.callback_data or ""))
            if any(re.search(pattern, value, re.I) for pattern in patterns for value in haystacks):
                return True
    return False

async def _wait_changed(ctx: PipelineContext, before: dict[int, tuple], predicate=None):
    deadline = time.monotonic() + ctx.cfg.flow_timeout
    while time.monotonic() < deadline:
        async for message in ctx.client.get_chat_history(ctx.cfg.catalog_bot, limit=20):
            if message.outgoing:
                continue
            changed = message.id not in before or before[message.id] != _fingerprint(message)
            if changed and (predicate is None or predicate(message)):
                return message
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Catalog bot did not provide the expected response in {ctx.cfg.flow_timeout}s")

async def _wait_visible_button(ctx: PipelineContext, patterns: list[str]):
    """Find a currently visible bot panel, including one edited in place."""
    deadline = time.monotonic() + ctx.cfg.flow_timeout
    while time.monotonic() < deadline:
        async for message in ctx.client.get_chat_history(ctx.cfg.catalog_bot, limit=20):
            if not message.outgoing and _message_has_button(message, patterns):
                return message
        await asyncio.sleep(0.5)
    raise RuntimeError("Catalog button not found. Expected one of: " + ", ".join(patterns))

async def _send_and_wait(ctx: PipelineContext, qid: int, text: str, predicate=None):
    before = await _snapshot(ctx)
    await ctx.speed.delay()
    await ctx.speed.call(lambda: ctx.client.send_message(ctx.cfg.catalog_bot, text), qid)
    return await _wait_changed(ctx, before, predicate)

async def _click_and_wait(ctx: PipelineContext, qid: int, message, patterns: list[str], predicate=None):
    last_error = None
    for attempt in range(3):
        before = await _snapshot(ctx)
        await ctx.speed.delay()
        if attempt:
            message = await _wait_visible_button(ctx, patterns)
        try:
            if not await click_matching(message, patterns):
                message = await _wait_visible_button(ctx, patterns)
                if not await click_matching(message, patterns):
                    raise RuntimeError("Catalog button not found. Expected one of: " + ", ".join(patterns))
            return await _wait_changed(ctx, before, predicate)
        except Exception as exc:
            last_error = exc
            text = str(exc).lower()
            if "data_invalid" not in text and "encrypted data is invalid" not in text and "timed out" not in text:
                raise
            # Callback data can be invalidated when the bot edits its keyboard
            # between retrieval and click. Refetch the latest panel and retry.
            await asyncio.sleep(0.75)
    raise RuntimeError(f"Catalog callback remained stale after retries: {last_error}")

async def run(ctx: PipelineContext, qid: int, movie: str, invite: str, source_message_id: int) -> bool:
    chat = ctx.cfg.catalog_bot

    # Do not use the first message after /admin: that can be our own outgoing
    # command. Find the actual bot panel that visibly contains Add New Title.
    await ctx.speed.call(lambda: ctx.client.send_message(chat, "/admin"), qid)
    add_patterns = [r"add.*title", r"new.*title", r"add_title", r"➕.*(?:title|anime|movie)"]
    panel = await _wait_visible_button(ctx, add_patterns)
    message = await _click_and_wait(ctx, qid, panel, add_patterns)

    message = await _send_and_wait(ctx, qid, clean_title(movie))

    # A video THUMBNAIL file_id cannot be sent as a PHOTO file_id. Upload a
    # small bundled generic catalog poster instead. This never downloads movie
    # media or its thumbnail from Telegram.
    poster = Path(__file__).resolve().parents[2] / "assets" / "catalog_poster.jpg"
    if not poster.exists():
        raise RuntimeError("Bundled catalog poster is missing")
    before = await _snapshot(ctx)
    await ctx.speed.delay()
    await ctx.speed.call(lambda: ctx.client.send_photo(chat, str(poster)), qid)
    message = await _wait_changed(ctx, before)

    if message.reply_markup and _message_has_button(message, [r"skip", r"⏩"]):
        message = await _click_and_wait(ctx, qid, message, [r"skip", r"⏩"])

    message = await _send_and_wait(ctx, qid, invite)
    state = await ctx.db.state(qid)
    filtered = json.loads(state['filtered_files_json'] or '[]') if state else []
    episode_keys = {(item.get('season'), item.get('episode')) for item in filtered if item.get('episode') is not None}
    series = is_series(movie) or bool(episode_keys)
    message = await _click_and_wait(ctx, qid, message, [r"web.*series" if series else r"movies?"])

    genre = await ctx.db.setting("default_genre", ctx.cfg.default_genre)
    genre_patterns = [re.escape(genre), r"action", r"drama", r"genre"]
    genre_panel = await _wait_visible_button(ctx, genre_patterns)
    await _click_and_wait(ctx, qid, genre_panel, genre_patterns)

    # Genre selection is multi-select. Always refetch and click Done before
    # looking for the language panel; never infer this from an intermediate
    # message returned by the genre callback.
    done_patterns = [r"(?:✅\s*)?done", r"finish(?:ed)?", r"continue"]
    done_panel = await _wait_visible_button(ctx, done_patterns)
    await _click_and_wait(ctx, qid, done_panel, done_patterns)

    language = await ctx.db.setting("catalog_language", ctx.cfg.catalog_language)
    language_patterns = [re.escape(language), r"hindi"]
    language_panel = await _wait_visible_button(ctx, language_patterns)
    message = await _click_and_wait(ctx, qid, language_panel, language_patterns)
    message = await _click_and_wait(ctx, qid, message, [r"ongoing" if series else r"completed"])

    # Anime Zone now shows a parts keyboard after status selection. CineForge
    # creates one channel/post per queue item, so select Single Part and do not
    # send the legacy numeric "0" response.
    message = await _click_and_wait(ctx, qid, message, [r"single\s*part", r"(?:^|\D)1\s*part(?:\D|$)"])
    message = await _click_and_wait(ctx, qid, message, [r"safe", r"no", r"❌"])
    await _click_and_wait(ctx, qid, message, [r"publish", r"submit"])

    await ctx.db.patch_state(qid, catalog_added=1)
    return True
