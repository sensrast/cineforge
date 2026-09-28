"""User-friendly control-panel keyboards and setting metadata."""
from __future__ import annotations
from typing import Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

SETTING_DEFS: dict[str, dict[str, Any]] = {
    "api_id": {"title": "Telegram API ID", "category": "account", "kind": "int", "secret": False, "help": "Numeric API ID from my.telegram.org/apps."},
    "api_hash": {"title": "Telegram API Hash", "category": "account", "kind": "secret", "secret": True, "help": "API hash from my.telegram.org/apps."},
    "owner_username": {"title": "Branding Username / Channel", "category": "account", "kind": "username", "help": "Owner-provided username or channel username used only for branding in captions and descriptions. It is not used to identify the admin account."},
    "source_bot": {"title": "Source Bot", "category": "integrations", "kind": "username", "help": "Bot searched for movie files."},
    "filestore_bot": {"title": "File-store Bot", "category": "integrations", "kind": "username", "help": "Bot used to generate batch links."},
    "catalog_bot": {"title": "Catalog Bot", "category": "integrations", "kind": "username", "help": "Bot receiving catalog submissions."},
    "arolinks_api_key": {"title": "AroLinks API Key", "category": "links", "kind": "secret", "secret": True, "help": "Leave unset to use the original batch link."},
    "arolinks_url": {"title": "AroLinks API URL", "category": "links", "kind": "url", "help": "AroLinks shortening API endpoint."},
    "tutorial_link": {"title": "Tutorial Link", "category": "links", "kind": "url_optional", "help": "Optional How to Open Link button destination."},
    "backup_enabled": {"title": "Backup Storage", "category": "links", "kind": "bool", "help": "Copy media server-side to a private backup channel before deleting temporary channel files."},
    "backup_channel": {"title": "Backup Channel", "category": "links", "kind": "text", "help": "Enter a numeric channel ID such as -100123... or a public @username. The userbot must be a member/admin."},
    "desired_qualities": {"title": "Desired Qualities", "category": "content", "kind": "qualities", "help": "Comma-separated list, such as 480p,720p,1080p,2160p."},
    "language_filter": {"title": "Source Language", "category": "content", "kind": "choice", "choices": ["Hindi", "Any"], "help": "Hindi accepts Hindi and Dual Audio. Any disables language filtering."},
    "search_strategy": {"title": "Search Strategy", "category": "content", "kind": "choice", "choices": ["First Matching Page", "All Desired Qualities", "Scan Every Page"], "help": "First Matching Page stops immediately when a page has usable files, preventing earlier buttons from disappearing."},
    "max_search_pages": {"title": "Maximum Search Pages", "category": "content", "kind": "int_positive", "help": "Maximum Movie Hunt pages to scan per title."},
    "channel_name": {"title": "Channel Name Format", "category": "channel", "kind": "template", "help": "Use {movie} where the movie name should appear."},
    "channel_description": {"title": "Channel Description", "category": "channel", "kind": "template", "help": "Supports {movie} and {owner_username}. Send multiline text normally."},
    "caption": {"title": "Clean File Caption", "category": "channel", "kind": "template", "help": "Supports {movie}, {quality}, {owner_username}, {season}, {episode}, and {episode_label}."},
    "sticker_480p": {"title": "480p Sticker", "category": "channel", "kind": "sticker", "help": "Press Change Value, then send or forward the sticker to this bot."},
    "sticker_720p": {"title": "720p Sticker", "category": "channel", "kind": "sticker", "help": "Press Change Value, then send or forward the sticker to this bot."},
    "sticker_1080p": {"title": "1080p Sticker", "category": "channel", "kind": "sticker", "help": "Press Change Value, then send or forward the sticker to this bot."},
    "sticker_2160p": {"title": "2160p / 4K Sticker", "category": "channel", "kind": "sticker", "help": "Optional sticker for 2160p or 4K files."},
    "sticker_start": {"title": "Final Starting Sticker", "category": "channel", "kind": "sticker", "help": "Sent before the final download post."},
    "sticker_end": {"title": "End Sticker", "category": "channel", "kind": "sticker", "help": "Used as the batch-ending sticker and sent after the final post."},
    "delay_between_actions": {"title": "Action Delay", "category": "speed", "kind": "float", "suffix": " sec", "help": "Applied only when Limits is enabled."},
    "delay_between_movies": {"title": "Movie Delay", "category": "speed", "kind": "float", "suffix": " sec", "help": "Delay after each processed movie when Limits is enabled."},
    "max_channels_per_day": {"title": "Channels per Day", "category": "speed", "kind": "int", "help": "0 means unlimited. Applied only when Limits is enabled."},
    "source_timeout": {"title": "Search Timeout", "category": "speed", "kind": "int_positive", "suffix": " sec", "help": "Time to wait for Movie Hunt responses."},
    "flow_timeout": {"title": "Bot-flow Timeout", "category": "speed", "kind": "int_positive", "suffix": " sec", "help": "Time to wait at each file-store or catalog step."},
    "floodwait_defer_threshold": {"title": "FloodWait Defer Threshold", "category": "speed", "kind": "int_positive", "suffix": " sec", "help": "FloodWaits at or above this duration defer only the affected movie so the rest of a batch can continue. Telegram's exact retry time is always respected."},
    "owner_admin_reconcile_interval": {"title": "Owner Admin Check Interval", "category": "speed", "kind": "int_positive", "suffix": " sec", "help": "Permanent interval for checking every created channel and granting the owner full administrator rights after joining. This never expires."},
    "default_genre": {"title": "Default Catalog Genre", "category": "catalog", "kind": "text", "help": "Button text to match, for example Action or Drama."},
    "catalog_language": {"title": "Catalog Language", "category": "catalog", "kind": "text", "help": "Catalog language button text, normally Hindi."},
    "promotion_enabled": {"title": "Updates Promotion", "category": "catalog", "kind": "bool", "help": "After channel completion, generate a provider link and publish the promotional image."},
    "promotion_image": {"title": "Promotion Image", "category": "catalog", "kind": "photo", "help": "Press Change Value, then send the reusable promotional image to this control bot."},
    "promotion_updates_channel": {"title": "Updates Channel", "category": "catalog", "kind": "text", "help": "Channel ID or @username where the final promotional image is posted. The control bot must be an administrator."},
    "promotion_link_provider": {"title": "Link Provider Bot", "category": "catalog", "kind": "username", "help": "The userbot sends /genlink and then forwards the temporary image post here."},
    "promotion_caption": {"title": "Promotion Caption", "category": "catalog", "kind": "template", "help": "Final updates-channel text. Supports {movie} and Telegram HTML such as <b>bold</b> and <blockquote>quote</blockquote>."},
    "promotion_button_text": {"title": "Promotion Button Text", "category": "catalog", "kind": "text", "help": "Text used for both generated-link inline buttons."},
    "promotion_updates_sticker": {"title": "Updates Post Sticker", "category": "catalog", "kind": "sticker", "help": "Sticker sent immediately after every promotional post in the updates channel."},
    "created_channels_folder_enabled": {"title": "Created Channels Folder", "category": "channel", "kind": "bool", "help": "Keep channels created by CineForge inside a dedicated Telegram folder on the userbot account."},
    "created_channels_folder_name": {"title": "Folder Name", "category": "channel", "kind": "text", "help": "Telegram folder name used for channels created by CineForge."},
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
    if definition.get("kind") in {"sticker","photo"}:
        return "Configured ✅"
    if definition.get("kind") == "bool":
        return "ON ✅" if str(value).lower() == "true" else "OFF"
    suffix = definition.get("suffix", "")
    return _short(value) + suffix

def home_keyboard(logged_in: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Userbot Connected" if logged_in else "🔐 Login Userbot", callback_data="auth:status" if logged_in else "auth:start")],
        [InlineKeyboardButton("🎬 Add Movie", callback_data="addmode:movie"), InlineKeyboardButton("📺 Add Series", callback_data="addmode:series")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="nav:settings"), InlineKeyboardButton("📊 Live Status", callback_data="nav:status")],
        [InlineKeyboardButton("📝 Recent Logs", callback_data="nav:logs"), InlineKeyboardButton("❓ Help", callback_data="nav:help")],
    ])

def content_type_keyboard(prefix: str = "type") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Movie", callback_data=f"{prefix}:movie"), InlineKeyboardButton("📺 Series", callback_data=f"{prefix}:series")],
        [InlineKeyboardButton("⬅️ Back to Home", callback_data="nav:home")],
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
    elif definition["kind"] == "bool":
        rows.extend([[InlineKeyboardButton("✅ Enable", callback_data=f"cfg:choose:{key}:true")], [InlineKeyboardButton("❌ Disable", callback_data=f"cfg:choose:{key}:false")]])
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
        elif row['status'] not in {'completed','cancelled'}:
            buttons.append([InlineKeyboardButton(f"🛑 Cancel #{row['id']} — {_short(row['movie_name'], 24)}",callback_data=f"job:cancel:{row['id']}")])
    buttons += [[InlineKeyboardButton("🔄 Refresh Status", callback_data="nav:status")], [InlineKeyboardButton("⬅️ Back to Home", callback_data="nav:home")]]
    return InlineKeyboardMarkup(buttons)

def back_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Home", callback_data="nav:home")]])
