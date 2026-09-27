"""Defensive parsers for Movie Hunt messages and generated links."""
from __future__ import annotations
import re
from typing import Any
# Telegram filenames often concatenate tags (for example 480pHEVC), so a
# trailing word boundary would incorrectly miss the quality.
QUALITY_RE = re.compile(r"(?i)(480\s*p|720\s*p|1080\s*p|2160\s*p|ds4k|4k)")
SIZE_RE = re.compile(r"(?i)(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB)")
LANG_RE = re.compile(r"(?i)\b(hindi|dual[ ._-]*audio)\b|हिंदी")
BATCH_RE = re.compile(r"https?://t\.me/[A-Za-z0-9_]+\?start=[A-Za-z0-9_-]+")

def normalize_quality(q: str) -> str:
    q = re.sub(r"\s+", "", q.lower())
    return {"4k": "2160p", "ds4k": "2160p"}.get(q, q)

def normalize_title(text: str) -> str:
    """Normalize a requested or source title for exact-title comparisons."""
    text = re.sub(r"(?i)\b(19|20)\d{2}\b", " ", text)
    text = re.sub(r"(?i)\b(?:hindi|dual\s*audio|webrip|web-dl|bluray|hevc|x26[45]|10bit|480p|720p|1080p|2160p|4k)\b", " ", text)
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

def title_matches(query: str, candidate: str) -> bool:
    """Reject sequel collisions such as Pushpa -> Pushpa 2."""
    wanted = normalize_title(query).split()
    actual = normalize_title(candidate).split()
    if not wanted or not actual:
        return False
    # Requested tokens must appear contiguously in the source filename.
    positions = [i for i in range(len(actual) - len(wanted) + 1) if actual[i:i + len(wanted)] == wanted]
    if not positions:
        return False
    start = positions[0]; remainder = actual[start + len(wanted):]
    wanted_numbers = {token for token in wanted if token.isdigit() and 1 <= int(token) <= 20}
    # A small number immediately following the matched title is normally a
    # sequel/part marker. Do not let a base-title request select that sequel.
    if not wanted_numbers and remainder:
        first = remainder[0]
        if (first.isdigit() and 1 <= int(first) <= 20) or first in {"ii", "iii", "iv"}:
            return False
        if first in {"part", "chapter", "season"} and len(remainder) > 1 and remainder[1].isdigit():
            return False
    return True

def size_mb(text: str) -> float:
    match = SIZE_RE.search(text or "")
    if not match:
        return 0
    number = float(match.group(1))
    return number * {"KB": 1 / 1024, "MB": 1, "GB": 1024, "TB": 1048576}[match.group(2).upper()]

def _blocks(text: str) -> list[str]:
    parts = re.split(r"(?i)(?=\bName\s*:)", text)
    return [part.strip() for part in parts if part.strip()] or [text]

def parse_results(messages: list[dict[str, Any]], desired: set[str], allow_non_hindi: bool = False, title_query: str = "") -> list[dict[str, Any]]:
    """Map each matching title block to its numbered Download button."""
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
            source_name = re.sub(r"(?is)^.*?Name\s*:\s*", "", block).splitlines()[0].strip()
            if title_query and not title_matches(title_query, source_name):
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
                "source_name": source_name,
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
