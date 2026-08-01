#!/usr/bin/env python3
"""
Dual-client Telegram file-store bot.

- Uses a Bot API client (bot) to receive user messages and return files.
- Uses a User API client (user session) to check channel membership (force-subscribe)
  even when the bot is not admin in the force channel.

ENVIRONMENT VARIABLES (required):
- BOT_TOKEN         : token for your bot from BotFather
- USER_SESSION      : user session string exported from Pyrogram (recommended)
- API_ID            : your Telegram API_ID (int)
- API_HASH          : your Telegram API_HASH (string)
- STORAGE_CHANNEL   : the channel username or ID where files will be stored (e.g. @my_channel or -100123...)
- FORCE_CHANNEL     : (optional) channel username or ID users must join to use the bot
- DATABASE          : (optional) path to sqlite DB (default: files.db)

Security: DO NOT put BOT_TOKEN, USER_SESSION, API_ID, API_HASH or other secrets into the repository.
Store them as environment variables or CI/GitHub secrets.
"""

import os
import sqlite3
import asyncio
import logging
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Env vars
BOT_TOKEN = os.getenv("BOT_TOKEN")
USER_SESSION = os.getenv("USER_SESSION")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
STORAGE_CHANNEL = os.getenv("STORAGE_CHANNEL")
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL")
DATABASE = os.getenv("DATABASE", "files.db")

if not BOT_TOKEN:
    raise SystemExit("Set BOT_TOKEN environment variable before running.")
if not USER_SESSION or not API_ID or not API_HASH:
    raise SystemExit("Set USER_SESSION, API_ID and API_HASH environment variables before running.")
if not STORAGE_CHANNEL:
    raise SystemExit("Set STORAGE_CHANNEL environment variable before running.")

# Pyrogram clients
bot = Client("file_store_bot", bot_token=BOT_TOKEN)
user = Client("file_store_user", api_id=API_ID, api_hash=API_HASH, session_string=USER_SESSION)

# Database helpers (sqlite)
def init_db():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        chat_id TEXT,
        message_id INTEGER,
        media_type TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()


def save_file_record(owner_id, chat_id, message_id, media_type):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("INSERT INTO files(owner_id, chat_id, message_id, media_type) VALUES (?, ?, ?, ?)",
                (owner_id, str(chat_id), message_id, media_type))
    rec_id = cur.lastrowid
    conn.commit()
    conn.close()
    return rec_id


def get_file_record(rec_id):
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.execute("SELECT id, owner_id, chat_id, message_id, media_type, created_at FROM files WHERE id = ?", (rec_id,))
    row = cur.fetchone()
    conn.close()
    return row


# Membership check using user client
async def user_is_member(user_id: int) -> bool:
    """Return True if user is a member of FORCE_CHANNEL according to the user session client.
    If FORCE_CHANNEL is not set, always returns True.
    """
    if not FORCE_CHANNEL:
        return True
    try:
        m = await user.get_chat_member(FORCE_CHANNEL, user_id)
        return m.status in ("creator", "administrator", "member")
    except Exception as e:
        # For private channels or if user not found, get_chat_member can raise.
        logger.debug("user.get_chat_member error: %s", e)
        return False


# Bot command handlers
@bot.on_message(filters.command("start") & ~filters.edited)
async def start(_, message):
    text = "Hi! Send me a file and I'll store it. Use /get <id> to retrieve."
    if FORCE_CHANNEL:
        text += f"\n\nForce-sub channel: {FORCE_CHANNEL}"
    await message.reply_text(text)


@bot.on_message(filters.command("get") & ~filters.edited)
async def get_file(_, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("Usage: /get <id>")
        return
    try:
        rec_id = int(args[1])
    except ValueError:
        await message.reply_text("ID must be a number.")
        return
    rec = get_file_record(rec_id)
    if not rec:
        await message.reply_text("File not found.")
        return
    _, _, chat_id, message_id, _, _ = rec
    try:
        await bot.copy_message(chat_id=message.chat.id, from_chat_id=int(chat_id), message_id=message_id)
    except Exception as e:
        await message.reply_text("Failed to retrieve file. It might have been deleted or the bot lacks permission.")
        logger.error("copy_message error: %s", e)


@bot.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo | filters.voice))
async def store_file(_, message):
    uid = message.from_user.id
    if FORCE_CHANNEL:
        member = await user_is_member(uid)
        if not member:
            join_url = f"https://t.me/{FORCE_CHANNEL.lstrip('@')}" if str(FORCE_CHANNEL).startswith("@") else None
            text = "You must join the required channel to use this bot."
            buttons = []
            if join_url:
                buttons.append([InlineKeyboardButton("Join channel", url=join_url)])
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
            return

    try:
        # The bot still needs permission to post in STORAGE_CHANNEL for copy_message to succeed.
        copied = await bot.copy_message(chat_id=STORAGE_CHANNEL, from_chat_id=message.chat.id, message_id=message.message_id)
        rec_id = save_file_record(message.from_user.id, STORAGE_CHANNEL, copied.message_id, message.media_group_id or "single")
        await message.reply_text(f"Saved. File ID: {rec_id}\nRetrieve with /get {rec_id}")
    except Exception as e:
        await message.reply_text("Failed to store file. Make sure the bot is allowed to post in the storage channel.")
        logger.error("store_file error: %s", e)


async def main():
    init_db()
    await user.start()
    await bot.start()
    logger.info("Bot and user clients started.")
    try:
        await idle()
    finally:
        await bot.stop()
        await user.stop()


if __name__ == "__main__":
    asyncio.run(main())
