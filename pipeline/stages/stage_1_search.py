from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from pipeline.context import PipelineContext
from pipeline.stages.common import latest_id, buttons, newest_after
from pipeline.cancellation import checkpoint
from utils.text_parser import parse_results, normalize_quality, explicit_non_hindi, media_label, title_matches, QUALITY_RE

log = logging.getLogger(__name__)

async def _fetch_page_items(ctx: PipelineContext, qid: int, current, items: list[dict], fetched: list[dict], seen: set[tuple], attempted: set[tuple], strict_hindi: bool, movie: str) -> None:
    """Fetch matching qualities while their edited-page buttons still exist."""
    chat = ctx.cfg.source_bot
    for item in items:
        await checkpoint(ctx,qid)
        key = (item.get("season"), item.get("episode"), item["quality"])
        candidate_key=(item["quality"],item.get("source_name",""),round(float(item.get("size_mb") or 0),1),str(item.get("callback_data") or ""))
        if key in seen or candidate_key in attempted:
            continue
        attempted.add(candidate_key)
        current = await ctx.client.get_messages(chat, current.id)
        position = None
        if current.reply_markup:
            # Callback data identifies the intended file more reliably than
            # duplicated button labels such as "Download 1".
            callback=str(item.get("callback_data") or "")
            if callback:
                for row_index,row in enumerate(current.reply_markup.inline_keyboard):
                    for column_index,button in enumerate(row):
                        raw=button.callback_data
                        live_callback=raw.decode(errors="ignore") if isinstance(raw,bytes) else str(raw or "")
                        if live_callback==callback:
                            position=(column_index,row_index);break
                    if position:break
            if not position:
                for row_index, row in enumerate(current.reply_markup.inline_keyboard):
                    for column_index, button in enumerate(row):
                        if (button.text or "") == item["button_text"]:
                            position = (column_index, row_index); break
                    if position: break
        if not position:
            label = f"S{item.get('season')}E{item.get('episode')} " if item.get('episode') is not None else ""
            await ctx.db.log(f"Download button unavailable for {label}{item['quality']}", "WARNING", qid)
            continue
        before = await latest_id(ctx.client, chat)
        await ctx.speed.call(lambda m=current, p=position: m.click(*p), qid)
        media = await newest_after(ctx.client, chat, before, max(60, ctx.cfg.flow_timeout), lambda m: bool(m.video or m.document))
        delivered_label=media_label(media)
        if strict_hindi and explicit_non_hindi(delivered_label):
            await ctx.db.log(f"Rejected delivered non-Hindi file for {item['quality']}: {delivered_label[:180]}","WARNING",qid)
            continue
        if delivered_label and not title_matches(movie, delivered_label):
            await ctx.db.log(f"Rejected delivered wrong-title/sequel file for {movie}: {delivered_label[:180]}","WARNING",qid)
            continue
        actual_quality=QUALITY_RE.search(delivered_label)
        if actual_quality and normalize_quality(actual_quality.group(1))!=item["quality"]:
            await ctx.db.log(f"Rejected quality mismatch: selected {item['quality']} but delivered {normalize_quality(actual_quality.group(1))}: {delivered_label[:150]}","WARNING",qid)
            continue
        fetched.append({
            "quality": item["quality"], "season": item.get("season"), "episode": item.get("episode"),
            "source_message_id": media.id, "received_at": datetime.now(timezone.utc).isoformat(),
            "source_name": delivered_label or item.get("source_name", ""),
        })
        seen.add(key)
        await ctx.speed.delay()

async def run(ctx: PipelineContext, qid: int, movie: str, content_type: str = "movie") -> list[dict]:
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
    mandatory = {"480p", "720p", "1080p"}
    desired = {normalize_quality(item) for item in desired_raw} | mandatory
    language = (await ctx.db.setting("language_filter", ctx.cfg.language_filter)).strip().lower()
    strategy = (await ctx.db.setting("search_strategy", ctx.cfg.search_strategy)).strip().lower()
    prefetched: list[dict] = []
    fetched_keys: set[tuple] = set()
    attempted_candidates: set[tuple] = set()
    series_mode = False
    for _ in range(max_pages):
        await checkpoint(ctx,qid)
        text = current.text or current.caption or ""
        if text in seen_text:
            break
        seen_text.add(text)
        page_data = {"id": current.id, "text": text, "buttons": buttons(current)}
        pages.append(page_data)
        page_matches = parse_results([page_data], desired, allow_non_hindi=(language == "any"), title_query=movie, content_type=content_type)
        if any(item.get("is_series") for item in page_matches):
            series_mode = True
        if page_matches:
            await _fetch_page_items(ctx, qid, current, page_matches, prefetched, fetched_keys, attempted_candidates, strict_hindi=(language != "any"), movie=movie)
        matches = parse_results(pages, desired, allow_non_hindi=(language == "any"), title_query=movie, content_type=content_type)
        found = {item["quality"] for item in prefetched}
        offered={item["quality"] for item in matches}
        progress = (
            f"Movie Hunt page {len(pages)}: fetched {', '.join(sorted(found)) or 'none'}; "
            f"offered {', '.join(sorted(offered)) or 'none'} ({len(found)}/{len(desired)}), strategy={strategy}"
        )
        log.info(progress)
        await ctx.db.log(progress, "INFO", qid)
        # Movie Hunt usually edits one result message in-place. Therefore,
        # First Matching Page is the safe default: once usable files exist,
        # preserve that keyboard and proceed directly to file fetching.
        fetched_qualities = {item["quality"] for item in prefetched if item.get("episode") is None}
        if mandatory.issubset(fetched_qualities) and not series_mode:
            await ctx.db.log("Mandatory 480p, 720p and 1080p files fetched; stopping pagination", "INFO", qid)
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
        pagination_clicked=False
        for attempt in range(3):
            try:
                current=await ctx.client.get_messages(chat,current.id)
                await ctx.speed.call(lambda m=current, p=next_pos: m.click(*p), qid)
                pagination_clicked=True
                break
            except Exception as exc:
                if "timed out" not in str(exc).lower() and "timeout" not in exc.__class__.__name__.lower():
                    raise
                await ctx.db.log(f"Movie Hunt Next timed out; retry {attempt+1}/3","WARNING",qid)
                await asyncio.sleep(1+attempt)
        if not pagination_clicked:
            await ctx.db.log("Movie Hunt pagination remained unavailable; continuing with valid qualities already fetched","WARNING",qid)
            break
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
    if not prefetched:
        await ctx.db.patch_state(qid,**updates)
        raise RuntimeError("Movie Hunt pages were exhausted without a valid delivered file; stale result buttons will not be retried")
    if content_type == "movie" and prefetched:
        missing=mandatory-{item["quality"] for item in prefetched if item.get("episode") is None}
        if missing:
            await ctx.db.log("All listed pages checked; continuing without unavailable Hindi qualities: "+", ".join(sorted(missing)),"WARNING",qid)
    if prefetched:
        updates["fetched_files_json"] = sorted(prefetched, key=lambda item: (
            item.get("season") or 0, item.get("episode") or 0,
            {"480p": 0, "720p": 1, "1080p": 2, "2160p": 3}.get(item["quality"], 99),
        ))
        await ctx.db.log(f"Prefetched {len(prefetched)} matching files while result buttons were active", "INFO", qid)
    await ctx.db.patch_state(qid, **updates)
    return pages
