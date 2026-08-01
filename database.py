"""
MongoDB helper for FileStore Bot using motor.

Exposes:
 - client, db
 - files_collection, shares_collection
 - ensure_indexes() to create expected indexes (text index, unique token, optional TTL).
"""
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from datetime import datetime, timedelta

from config import MONGO_URI, DB_NAME, SHARE_TOKEN_TTL_DAYS

log = logging.getLogger(__name__)

client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
files_collection = db.get_collection("files")
shares_collection = db.get_collection("shares")

async def ensure_indexes() -> None:
    """
    Create indexes:
     - Text index on file_name & caption for search
     - Unique index on shares.token
     - Index on shares.created_at
     - Optional TTL index on shares.expires_at when SHARE_TOKEN_TTL_DAYS > 0
    """
    try:
        # Text index for search
        await files_collection.create_index(
            [("file_name", "text"), ("caption", "text")],
            name="file_text_idx",
            default_language="english",
        )
        log.info("Ensured text index on files (file_name, caption).")

        # Unique token for shares
        await shares_collection.create_index("token", unique=True, name="share_token_unique")
        await shares_collection.create_index("created_at", name="share_created_idx")
        log.info("Ensured indexes on shares collection.")

        # TTL index: Mongo uses the field value as expiry moment when expireAfterSeconds=0
        if SHARE_TOKEN_TTL_DAYS and SHARE_TOKEN_TTL_DAYS > 0:
            await shares_collection.create_index("expires_at", expireAfterSeconds=0, name="share_expires_ttl")
            log.info("Ensured TTL index on shares.expires_at")
    except Exception:
        log.exception("Failed to ensure indexes.")
        raise
