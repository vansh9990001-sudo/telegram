"""
Configuration loader for Telegram FileStore Bot.

Loads configuration from environment variables and .env when present.
"""
from dotenv import load_dotenv
import os
from typing import Optional

load_dotenv()

def _int_env(name: str, default: int = 0) -> int:
    val = os.getenv(name)
    try:
        return int(val) if val is not None and val != "" else default
    except ValueError:
        return default

API_ID: int = _int_env("API_ID", 0)
API_HASH: str = os.getenv("API_HASH", "")
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME: str = os.getenv("DB_NAME", "telegram_filestore")
BOT_USERNAME: Optional[str] = os.getenv("BOT_USERNAME")  # optional: set to avoid an extra API call
SHARE_TOKEN_TTL_DAYS: int = _int_env("SHARE_TOKEN_TTL_DAYS", 0)  # 0 = never expire

def validate_config() -> None:
    missing = []
    if not API_ID:
        missing.append("API_ID")
    if not API_HASH:
        missing.append("API_HASH")
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
