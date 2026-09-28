"""Environment and runtime configuration."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

def _int(name: str, default: int) -> int:
    try: return int(os.getenv(name, str(default)))
    except ValueError: return default

def _float(name: str, default: float) -> float:
    try: return float(os.getenv(name, str(default)))
    except ValueError: return default

@dataclass
class Config:
    api_id: int = _int("API_ID", 0)
    api_hash: str = os.getenv("API_HASH", "")
    phone: str = os.getenv("USERBOT_PHONE", "")
    session_string: str = os.getenv("USERBOT_SESSION_STRING", "")
    control_token: str = os.getenv("CONTROL_BOT_TOKEN", "")
    control_username: str = ""
    owner_id: int = _int("OWNER_USER_ID", 0)
    owner_username: str = os.getenv("OWNER_USERNAME", "").lstrip("@")
    source_bot: str = os.getenv("SOURCE_BOT_USERNAME", "MVHuntbot").lstrip("@")
    filestore_bot: str = os.getenv("FILESTORE_BOT_USERNAME", "movieinhindibot").lstrip("@")
    catalog_bot: str = os.getenv("ANIMEZONE_BOT_USERNAME", "YC_Anime_Zone_bot").lstrip("@")
    arolinks_key: str = os.getenv("AROLINKS_API_KEY", "")
    arolinks_url: str = os.getenv("AROLINKS_BASE_URL", "https://arolinks.com/api")
    tutorial_link: str = os.getenv("TUTORIAL_LINK", "")
    channel_name: str = os.getenv("CHANNEL_NAME_FORMAT", "{movie} (Hindi)")
    channel_description: str = os.getenv("CHANNEL_DESCRIPTION_TEMPLATE", "🎬 {movie}\\n\\n🔊 Audio: Hindi").replace("\\n", "\n")
    caption: str = os.getenv("CUSTOM_CAPTION_FORMAT", "🎬 **{movie}**\\n🔊 **Audio:** Hindi\\n⚡ **Quality:** {quality}").replace("\\n", "\n")
    db_path: Path = Path(os.getenv("DATABASE_PATH", "data/cineforge.db"))
    source_timeout: int = _int("SOURCE_RESPONSE_TIMEOUT", 30)
    flow_timeout: int = _int("BOT_FLOW_TIMEOUT", 60)
    max_search_pages: int = _int("MAX_SEARCH_PAGES", 32)
    language_filter: str = os.getenv("LANGUAGE_FILTER", "Hindi")
    search_strategy: str = os.getenv("SEARCH_STRATEGY", "First Matching Page")
    default_genre: str = os.getenv("DEFAULT_CATALOG_GENRE", "Action")
    catalog_language: str = os.getenv("CATALOG_LANGUAGE", "Hindi")
    owner_join_timeout: int = _int("OWNER_JOIN_TIMEOUT", 3600)
    port: int = _int("PORT", 10000)
    health_host: str = os.getenv("HEALTH_HOST", "0.0.0.0")
    limits_enabled: bool = _bool("LIMITS_ENABLED", False)
    delay_actions: float = _float("DELAY_BETWEEN_ACTIONS", 0)
    delay_movies: float = _float("DELAY_BETWEEN_MOVIES", 0)
    max_channels: int = _int("MAX_CHANNELS_PER_DAY", 0)
    qualities: str = os.getenv("DESIRED_QUALITIES", "480p,720p,1080p,2160p,4K")
    auto_catalog: bool = _bool("AUTO_CATALOG", True)

    def validate(self, require_session: bool = True) -> None:
        missing=[]
        for k,v in (("API_ID",self.api_id),("API_HASH",self.api_hash),("CONTROL_BOT_TOKEN",self.control_token),("OWNER_USER_ID",self.owner_id)):
            if not v: missing.append(k)
        if require_session and not self.session_string: missing.append("USERBOT_SESSION_STRING")
        if missing: raise RuntimeError("Missing required configuration: " + ", ".join(missing))

settings = Config()
