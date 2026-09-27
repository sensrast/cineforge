from __future__ import annotations
import asyncio
from pipeline.context import PipelineContext
from pipeline.stages.common import latest_id, buttons, newest_after

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
    for _ in range(max_pages):
        text = current.text or current.caption or ""
        if text in seen_text:
            break
        seen_text.add(text)
        pages.append({"id": current.id, "text": text, "buttons": buttons(current)})
        await ctx.db.log(f"Movie Hunt search page {len(pages)} collected", "INFO", qid)
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
    await ctx.db.patch_state(qid, source_messages_json=pages)
    return pages
