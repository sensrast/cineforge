from telegram import InlineKeyboardButton, InlineKeyboardMarkup

EDITABLE_SETTINGS = {
    "api_id": "Telegram API ID",
    "api_hash": "Telegram API hash",
    "owner_username": "Owner username",
    "source_bot": "Source bot username",
    "filestore_bot": "File-store bot username",
    "catalog_bot": "Catalog bot username",
    "arolinks_api_key": "AroLinks API key",
    "arolinks_url": "AroLinks API URL",
    "tutorial_link": "Tutorial link",
    "channel_name": "Channel-name format",
    "channel_description": "Channel description template",
    "caption": "File caption template",
    "desired_qualities": "Desired qualities",
    "delay_between_actions": "Action delay",
    "delay_between_movies": "Movie delay",
    "max_channels_per_day": "Max channels/day",
}

def home_keyboard(logged_in: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Userbot connected" if logged_in else "🔐 Login Userbot", callback_data="auth:status" if logged_in else "auth:start")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings"), InlineKeyboardButton("📊 Status", callback_data="menu:status")],
    ])

def settings_keyboard(values: dict[str, str]) -> InlineKeyboardMarkup:
    enabled = values.get("limits_enabled", "false") == "true"
    auto = values.get("auto_catalog", "true") == "true"
    rows = [
        [InlineKeyboardButton(f'Limits: {"ON" if enabled else "OFF"}', callback_data="cfg:toggle:limits_enabled"), InlineKeyboardButton(f'Catalog: {"ON" if auto else "OFF"}', callback_data="cfg:toggle:auto_catalog")],
        [InlineKeyboardButton("Telegram API", callback_data="submenu:telegram"), InlineKeyboardButton("Integrations", callback_data="submenu:integrations")],
        [InlineKeyboardButton("Links & templates", callback_data="submenu:links"), InlineKeyboardButton("Speed & qualities", callback_data="submenu:speed")],
        [InlineKeyboardButton("⬅️ Home", callback_data="menu:home")],
    ]
    return InlineKeyboardMarkup(rows)

def submenu_keyboard(kind: str) -> InlineKeyboardMarkup:
    groups = {
        "telegram": ["api_id", "api_hash", "owner_username"],
        "integrations": ["source_bot", "filestore_bot", "catalog_bot", "arolinks_api_key", "arolinks_url"],
        "links": ["tutorial_link", "channel_name", "channel_description", "caption"],
        "speed": ["desired_qualities", "delay_between_actions", "delay_between_movies", "max_channels_per_day"],
    }
    rows = [[InlineKeyboardButton(EDITABLE_SETTINGS[key], callback_data=f"cfg:set:{key}")] for key in groups[kind]]
    rows.append([InlineKeyboardButton("⬅️ Settings", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)
