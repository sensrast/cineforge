"""User-friendly control-panel keyboards and setting metadata."""
from __future__ import annotations
from typing import Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

SETTING_DEFS: dict[str, dict[str, Any]] = {
    "api_id": {"title": "Telegram API ID", "category": "account", "kind": "int", "secret": False, "help": "Numeric API ID from my.telegram.org/apps."},
    "api_hash": {"title": "Telegram API Hash", "category": "account", "kind": "secret", "secret": True, "help": "API hash from my.telegram.org/apps."},
    "owner_username": {"title": "Owner Username", "category": "account", "kind": "username", "help": "Username without @, used in captions."},
    "source_bot": {"title": "Source Bot", "category": "integrations", "kind": "username", "help": "Bot searched for movie files."},
    "filestore_bot": {"title": "File-store Bot", "category": "integrations", "kind": "username", "help": "Bot used to generate batch links."},
    "catalog_bot": {"title": "Catalog Bot", "category": "integrations", "kind": "username", "help": "Bot receiving catalog submissions."},
    "arolinks_api_key": {"title": "AroLinks API Key", "category": "links", "kind": "secret", "secret": True, "help": "Leave unset to use the original batch link."},
    "arolinks_url": {"title": "AroLinks API URL", "category": "links", "kind": "url", "help": "AroLinks shortening API endpoint."},
    "tutorial_link": {"title": "Tutorial Link", "category": "links", "kind": "url_optional", "help": "Optional How to Open Link button destination."},
    "desired_qualities": {"title": "Desired Qualities", "category": "content", "kind": "qualities", "help": "Comma-separated list, such as 480p,720p,1080p,2160p."},
    "language_filter": {"title": "Source Language", "category": "content", "kind": "choice", "choices": ["Hindi", "Any"], "help": "Hindi accepts Hindi and Dual Audio. Any disables language filtering."},
    "search_strategy": {"title": "Search Strategy", "category": "content", "kind": "choice", "choices": ["First Matching Page", "All Desired Qualities", "Scan Every Page"], "help": "First Matching Page stops immediately when a page has usable files, preventing earlier buttons from disappearing."},
    "max_search_pages": {"title": "Maximum Search Pages", "category": "content", "kind": "int_positive", "help": "Maximum Movie Hunt pages to scan per title."},
    "channel_name": {"title": "Channel Name Format", "category": "channel", "kind": "template", "help": "Use {movie} where the movie name should appear."},
    "channel_description": {"title": "Channel Description", "category": "channel", "kind": "template", "help": "Supports {movie} and {owner_username}. Send multiline text normally."},
    "caption": {"title": "Clean File Caption", "category": "channel", "kind": "template", "help": "Supports {movie}, {quality}, and {owner_username}."},
    "delay_between_actions": {"title": "Action Delay", "category": "speed", "kind": "float", "suffix": " sec", "help": "Applied only when Limits is enabled."},
    "delay_between_movies": {"title": "Movie Delay", "category": "speed", "kind": "float", "suffix": " sec", "help": "Delay after each processed movie when Limits is enabled."},
    "max_channels_per_day": {"title": "Channels per Day", "category": "speed", "kind": "int", "help": "0 means unlimited. Applied only when Limits is enabled."},
    "source_timeout": {"title": "Search Timeout", "category": "speed", "kind": "int_positive", "suffix": " sec", "help": "Time to wait for Movie Hunt responses."},
    "flow_timeout": {"title": "Bot-flow Timeout", "category": "speed", "kind": "int_positive", "suffix": " sec", "help": "Time to wait at each file-store or catalog step."},
    "default_genre": {"title": "Default Catalog Genre", "category": "catalog", "kind": "text", "help": "Button text to match, for example Action or Drama."},
    "catalog_language": {"title": "Catalog Language", "category": "catalog", "kind": "text", "help": "Catalog language button text, normally Hindi."},
}

CATEGORIES = {
    "account": ("👤 Account & Login", "Telegram account credentials and session status."),
    "integrations": ("🤖 Telegram Integrations", "Bots used by each pipeline stage."),
    "content": ("🎞 Content & Filters", "Qualities, language filtering, and search depth."),
    "channel": ("📢 Channel & Captions", "Channel naming and clean post templates."),
    "links": ("🔗 Links & Monetization", "AroLinks and tutorial button settings."),
    "speed": ("⚡ Speed, Limits & Timeouts", "Runtime throttling and response timeouts."),
    "catalog": ("🗂 Catalog Defaults", "Automatic catalog submission defaults."),
}

def _short(value: str, limit: int = 22) -> str:
    value = str(value).replace("\n", " ↵ ")
    return value if len(value) <= limit else value[: limit - 1] + "…"

def display_value(key: str, value: str) -> str:
    if not value:
        return "Not set"
    definition = SETTING_DEFS.get(key, {})
    if definition.get("secret"):
        return "••••" + value[-4:] if len(value) >= 4 else "••••"
    suffix = definition.get("suffix", "")
    return _short(value) + suffix

def home_keyboard(logged_in: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Userbot Connected" if logged_in else "🔐 Login Userbot", callback_data="auth:status" if logged_in else "auth:start")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="nav:settings"), InlineKeyboardButton("📊 Live Status", callback_data="nav:status")],
        [InlineKeyboardButton("📝 Recent Logs", callback_data="nav:logs"), InlineKeyboardButton("❓ Help", callback_data="nav:help")],
    ])

def settings_root_keyboard(values: dict[str, str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(title, callback_data=f"nav:cat:{key}")] for key, (title, _) in CATEGORIES.items()]
    limits = "ON" if values.get("limits_enabled", "false") == "true" else "OFF"
    catalog = "ON" if values.get("auto_catalog", "true") == "true" else "OFF"
    rows += [
        [InlineKeyboardButton(f"🛡 Limits: {limits}", callback_data="cfg:toggle:limits_enabled"), InlineKeyboardButton(f"🗂 Auto Catalog: {catalog}", callback_data="cfg:toggle:auto_catalog")],
        [InlineKeyboardButton("🔄 Refresh Values", callback_data="nav:settings")],
        [InlineKeyboardButton("⬅️ Back to Home", callback_data="nav:home")],
    ]
    return InlineKeyboardMarkup(rows)

def category_keyboard(category: str, values: dict[str, str], logged_in: bool) -> InlineKeyboardMarkup:
    rows = []
    if category == "account":
        rows.append([InlineKeyboardButton("✅ Session Connected" if logged_in else "🔐 Login Userbot", callback_data="auth:status" if logged_in else "auth:start")])
        if logged_in:
            rows.append([InlineKeyboardButton("🚪 Log Out Userbot", callback_data="auth:logout_ask")])
    for key, definition in SETTING_DEFS.items():
        if definition["category"] != category:
            continue
        value = display_value(key, values.get(key, ""))
        rows.append([InlineKeyboardButton(f'{definition["title"]}: {value}', callback_data=f"cfg:open:{key}")])
    rows += [
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"nav:cat:{category}")],
        [InlineKeyboardButton("⬅️ Back to Settings", callback_data="nav:settings")],
    ]
    return InlineKeyboardMarkup(rows)

def field_keyboard(key: str) -> InlineKeyboardMarkup:
    definition = SETTING_DEFS[key]
    rows = []
    if definition["kind"] == "choice":
        rows.extend([[InlineKeyboardButton(choice, callback_data=f"cfg:choose:{key}:{choice}")] for choice in definition["choices"]])
    else:
        rows.append([InlineKeyboardButton("✏️ Change Value", callback_data=f"cfg:edit:{key}")])
    if key in {"tutorial_link", "arolinks_api_key"}:
        rows.append([InlineKeyboardButton("🗑 Clear Value", callback_data=f"cfg:clear:{key}")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data=f'nav:cat:{definition["category"]}')])
    return InlineKeyboardMarkup(rows)

def input_cancel_keyboard(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Cancel and Go Back", callback_data=f'nav:cat:{SETTING_DEFS[key]["category"]}')]])

def confirmation_keyboard(confirm_callback: str, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, continue", callback_data=confirm_callback)],
        [InlineKeyboardButton("⬅️ No, go back", callback_data=back_callback)],
    ])

def status_keyboard(rows) -> InlineKeyboardMarkup:
    buttons = []
    for row in rows:
        if row['status'] == 'failed':
            buttons.append([InlineKeyboardButton(f"🔄 Retry #{row['id']} — {_short(row['movie_name'], 24)}", callback_data=f"job:retry:{row['id']}")])
    buttons += [[InlineKeyboardButton("🔄 Refresh Status", callback_data="nav:status")], [InlineKeyboardButton("⬅️ Back to Home", callback_data="nav:home")]]
    return InlineKeyboardMarkup(buttons)

def back_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Home", callback_data="nav:home")]])
