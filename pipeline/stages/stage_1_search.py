from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from pipeline.context import PipelineContext
from pipeline.stages.common import latest_id, buttons, newest_after
from utils.text_parser import parse_results, normalize_quality

log = logging.getLogger(__name__)

async def _fetch_series_page(ctx: PipelineContext, qid: int, current, items: list[dict], fetched: list[dict], seen: set[tuple]) -> None:
    """Fetch episode qualities while their edited-page buttons still exist."""
    chat = ctx.cfg.source_bot
    for item in items:
        key = (item.get("season"), item.get("episode"), item["quality"])
        if key in seen:
            continue
        current = await ctx.client.get_messages(chat, current.id)
        position = None
        if current.reply_markup:
            for row_index, row in enumerate(current.reply_markup.inline_keyboard):
                for column_index, button in enumerate(row):
                    if (button.text or "") == item["button_text"]:
                        position = (column_index, row_index); break
                if position: break
        if not position:
            await ctx.db.log(f"Series button unavailable for S{item.get('season')}E{item.get('episode')} {item['quality']}", "WARNING", qid)
            continue
        before = await latest_id(ctx.client, chat)
        await ctx.speed.call(lambda m=current, p=position: m.click(*p), qid)
        media = await newest_after(ctx.client, chat, before, max(60, ctx.cfg.flow_timeout), lambda m: bool(m.video or m.document))
        fetched.append({
            "quality": item["quality"], "season": item.get("season"), "episode": item.get("episode"),
            "source_message_id": media.id, "received_at": datetime.now(timezone.utc).isoformat(),
        })
        seen.add(key)
        await ctx.speed.delay()

async def run(ctx: PipelineContext, qid: int, movie: str) -> list[dict]:
    """Search Movie Hunt and walk edited-message pagination defensively."""
    chat = ctx.cfg.source_bot
    before = await latest_id(ctx.client, chat)
    await ctx.speed.call(lambda: ctx.client.send_message(chat, movie), qid)
    current = await newest_after(
        ctx.client, chat, before, ctx.cfg.source_timeout,
        lambda m: bool((m.text or m.caption) and m.reply_markup),
    )
    pages: list[dict] = []
    seen_text: set[str] = set()
    max_pages = max(1, min(100, int(await ctx.db.setting("max_search_pages", str(ctx.cfg.max_search_pages)))))
    desired_raw = [item.strip() for item in (await ctx.db.setting("desired_qualities", ctx.cfg.qualities)).split(",") if item.strip()]
    desired = {normalize_quality(item) for item in desired_raw}
    language = (await ctx.db.setting("language_filter", ctx.cfg.language_filter)).strip().lower()
    strategy = (await ctx.db.setting("search_strategy", ctx.cfg.search_strategy)).strip().lower()
    series_fetched: list[dict] = []
    series_seen: set[tuple] = set()
    series_mode = False
    for _ in range(max_pages):
        text = current.text or current.caption or ""
        if text in seen_text:
            break
        seen_text.add(text)
        page_data = {"id": current.id, "text": text, "buttons": buttons(current)}
        pages.append(page_data)
        page_matches = parse_results([page_data], desired, allow_non_hindi=(language == "any"), title_query=movie)
        if any(item.get("is_series") for item in page_matches):
            series_mode = True
            await _fetch_series_page(ctx, qid, current, [item for item in page_matches if item.get("is_series")], series_fetched, series_seen)
        matches = parse_results(pages, desired, allow_non_hindi=(language == "any"), title_query=movie)
        found = {item["quality"] for item in matches}
        progress = (
            f"Movie Hunt page {len(pages)}: found {', '.join(sorted(found)) or 'no desired qualities'} "
            f"({len(found)}/{len(desired)}), strategy={strategy}"
        )
        log.info(progress)
        await ctx.db.log(progress, "INFO", qid)
        # Movie Hunt usually edits one result message in-place. Therefore,
        # First Matching Page is the safe default: once usable files exist,
        # preserve that keyboard and proceed directly to file fetching.
        if found and strategy == "first matching page" and not series_mode:
            await ctx.db.log("Usable files found; preserving this page and stopping pagination", "INFO", qid)
            break
        if desired and desired.issubset(found) and strategy != "scan every page" and not series_mode:
            await ctx.db.log("All desired qualities found; stopping pagination", "INFO", qid)
            break
        next_pos = None
        if current.reply_markup:
            for row_index, row in enumerate(current.reply_markup.inline_keyboard):
                for column_index, button in enumerate(row):
                    label = button.text or ""
                    if "NEXT" in label.upper() or "⏩" in label:
                        # Message.click uses x=column, y=row.
                        next_pos = (column_index, row_index)
                        break
                if next_pos:
                    break
        if not next_pos:
            break
        old_text = text
        await ctx.speed.delay()
        await ctx.speed.call(lambda m=current, p=next_pos: m.click(*p), qid)
        changed = None
        for _poll in range(ctx.cfg.source_timeout * 2):
            # Movie Hunt normally edits the same result message, but some
            # versions send a new result message instead.
            candidate = await ctx.client.get_messages(chat, current.id)
            candidate_text = candidate.text or candidate.caption or ""
            if candidate_text and candidate_text != old_text:
                changed = candidate
                break
            async for newer in ctx.client.get_chat_history(chat, limit=5):
                newer_text = newer.text or newer.caption or ""
                if newer.id > current.id and newer_text and newer_text != old_text and newer.reply_markup:
                    changed = newer
                    break
            if changed:
                break
            await asyncio.sleep(0.5)
        if changed is None:
            break
        current = changed
    updates = {"source_messages_json": pages}
    if series_fetched:
        updates["fetched_files_json"] = sorted(series_fetched, key=lambda item: (
            item.get("season") or 0, item.get("episode") or 0,
            {"480p": 0, "720p": 1, "1080p": 2, "2160p": 3}.get(item["quality"], 99),
        ))
        await ctx.db.log(f"Prefetched {len(series_fetched)} episodic files across result pages", "INFO", qid)
    await ctx.db.patch_state(qid, **updates)
    return pages
