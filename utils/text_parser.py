"""Defensive parsers for Movie Hunt messages and generated links."""
from __future__ import annotations
import re
from typing import Any
QUALITY_RE = re.compile(r"(?i)(?<!\d)(480p|720p|1080p|2160p|4k|ds4k)(?!\w)")
SIZE_RE = re.compile(r"(?i)(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB)")
LANG_RE = re.compile(r"(?i)\b(hindi|dual[ ._-]*audio)\b|हिंदी")
BATCH_RE = re.compile(r"https?://t\.me/[A-Za-z0-9_]+\?start=[A-Za-z0-9_-]+")

def normalize_quality(q: str) -> str:
    q = q.lower()
    return {"4k": "2160p", "ds4k": "2160p"}.get(q, q)

def size_mb(text: str) -> float:
    match = SIZE_RE.search(text or "")
    if not match:
        return 0
    number = float(match.group(1))
    return number * {"KB": 1 / 1024, "MB": 1, "GB": 1024, "TB": 1048576}[match.group(2).upper()]

def _blocks(text: str) -> list[str]:
    parts = re.split(r"(?i)(?=\bName\s*:)", text)
    return [part.strip() for part in parts if part.strip()] or [text]

def parse_results(messages: list[dict[str, Any]], desired: set[str], allow_non_hindi: bool = False) -> list[dict[str, Any]]:
    """Map each filename block to its corresponding numbered Download button."""
    wanted = {normalize_quality(item.strip()) for item in desired}
    best: dict[str, dict[str, Any]] = {}
    for message in messages:
        full_text = message.get("text", "") or ""
        all_buttons = message.get("buttons", [])
        blocks = _blocks(full_text)
        # Movie Hunt commonly prints the language once for the entire result
        # page (sometimes above, between, or below Name blocks). If the page is
        # identified as Hindi/Dual Audio, apply that context to every file block.
        page_is_hindi = bool(LANG_RE.search(full_text))
        for block in blocks:
            if not allow_non_hindi and not (LANG_RE.search(block) or page_is_hindi):
                continue
            quality_match = QUALITY_RE.search(block)
            if not quality_match:
                continue
            quality = normalize_quality(quality_match.group(1))
            if quality not in wanted:
                continue
            index_match = re.search(r"(?i)(?:Click\s+)?Download\s*(\d+)", block)
            if index_match:
                index = index_match.group(1)
                candidates = [b for b in all_buttons if re.search(rf"(?i)Download\s*{re.escape(index)}(?:\D|$)", b.get("text", ""))]
            else:
                candidates = [b for b in all_buttons if re.search(r"(?i)Download\s*\d+", b.get("text", ""))]
            if not candidates:
                continue
            button = candidates[0]
            item = {
                "quality": quality,
                "source_message_id": message["id"],
                "button_text": button["text"],
                "callback_data": button.get("callback_data"),
                "size_mb": size_mb(block + " " + button["text"]),
                "source_name": re.sub(r"(?is)^.*?Name\s*:\s*", "", block).splitlines()[0].strip(),
            }
            if quality not in best or item["size_mb"] > best[quality]["size_mb"]:
                best[quality] = item
    order = {"480p": 0, "720p": 1, "1080p": 2, "2160p": 3}
    return sorted(best.values(), key=lambda item: order.get(item["quality"], 99))

def extract_batch_link(text: str) -> str | None:
    match = BATCH_RE.search(text or "")
    return match.group(0) if match else None

def clean_title(name: str) -> str:
    return re.sub(r"(?i)\s*(?:\(|-)?\s*in\s+hindi\s*\)?\s*$", "", name).strip()

def is_series(name: str) -> bool:
    return bool(re.search(r"(?i)\b(season|s\d{1,2}|episode|ep\d+)\b", name))
