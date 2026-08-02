#!/usr/bin/env python3
"""
Telegram File Store Bot (Pyrogram) integrated with config.py and database.py.

Features:
 - Save incoming media file_ids + metadata to MongoDB
 - /search <query> to find files by filename or caption
 - /share (reply or DB id) to create a short public share link:
     https://t.me/<BOT_USERNAME>?start=share_<token>
 - /start share_<token> deep link handling to deliver the file to the clicker
"""
import os
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from bson.objectid import ObjectId
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

import config
from database import files_collection, shares_collection, ensure_indexes

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

config.validate_config()

API_ID = config.API_ID
API_HASH = config.API_HASH
BOT_TOKEN = config.BOT_TOKEN
BOT_USERNAME = config.BOT_USERNAME
SHARE_TOKEN_TTL_DAYS = config.SHARE_TOKEN_TTL_DAYS

# Pyrogram client (session name stored in working dir)
app = Client("file_store_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def make_token() -> str:
    return uuid.uuid4().hex[:12]

async def get_bot_username():
    global BOT_USERNAME
    if BOT_USERNAME:
        return BOT_USERNAME
    me = await app.get_me()
    BOT_USERNAME = me.username or me.first_name
    return BOT_USERNAME

def extract_media_info(msg: Message):
    if msg.document:
        return msg.document.file_id, getattr(msg.document, "file_name", None), "document", getattr(msg.document, "file_size", None)
    if msg.photo:
        p = msg.photo[-1]
        return p.file_id, None, "photo", getattr(p, "file_size", None)
    if msg.video:
        return msg.video.file_id, getattr(msg.video, "file_name", None), "video", getattr(msg.video, "file_size", None)
    if msg.audio:
        return msg.audio.file_id, getattr(msg.audio, "file_name", None), "audio", getattr(msg.audio, "file_size", None)
    if msg.voice:
        return msg.voice.file_id, None, "voice", getattr(msg.voice, "file_size", None)
    if msg.sticker:
        return msg.sticker.file_id, None, "sticker", None
    if msg.animation:
        return msg.animation.file_id, None, "animation", getattr(msg.animation, "file_size", None)
    if msg.video_note:
        return msg.video_note.file_id, None, "video_note", getattr(msg.video_note, "file_size", None)
    return None, None, None, None

async def send_saved_file(chat_id: int, file_doc: dict):
    ftype = file_doc.get("file_type")
    fid = file_doc.get("file_id")
    caption = file_doc.get("caption")
    kwargs = {"caption": caption} if caption else {}
    try:
        if ftype == "document":
            await app.send_document(chat_id, fid, **kwargs)
        elif ftype == "photo":
            await app.send_photo(chat_id, fid, **kwargs)
        elif ftype == "video":
            await app.send_video(chat_id, fid, **kwargs)
        elif ftype == "audio":
            await app.send_audio(chat_id, fid, **kwargs)
        elif ftype == "voice":
            await app.send_voice(chat_id, fid, **kwargs)
        elif ftype == "sticker":
            await app.send_sticker(chat_id, fid)
        elif ftype == "animation":
            await app.send_animation(chat_id, fid, **kwargs)
        elif ftype == "video_note":
            await app.send_video_note(chat_id, fid)
        else:
            await app.send_document(chat_id, fid, **kwargs)
    except Exception:
        log.exception("Failed to send saved file.")

@app.on_message(filters.private & filters.media)
async def media_handler(client: Client, message: Message):
    file_id, file_name, file_type, file_size = extract_media_info(message)
    if not file_id:
        return
    doc = {
        "file_id": file_id,
        "file_type": file_type,
        "file_name": file_name,
        "caption": message.caption,
        "size": file_size,
        "uploader_id": message.from_user.id if message.from_user else None,
        "uploader_username": getattr(message.from_user, "username", None) if message.from_user else None,
        "created_at": datetime.utcnow(),
        "original_chat_id": message.chat.id,
        "original_message_id": message.message_id,
    }
    res = await files_collection.insert_one(doc)
    db_id = str(res.inserted_id)
    await message.reply_text(
        f"Saved file as id: {db_id}\nUse /share (reply to this message) to create a public share link, or /share {db_id}"
    )

@app.on_message(filters.command("share") & filters.private)
async def share_handler(client: Client, message: Message):
    target_doc = None

    if message.reply_to_message:
        file_id, _, _, _ = extract_media_info(message.reply_to_message)
        if file_id:
            target_doc = await files_collection.find_one({"file_id": file_id})
        else:
            text = message.reply_to_message.text or ""
            if "Saved file as id:" in text:
                try:
                    _id = text.split("Saved file as id:")[1].strip().split()[0]
                    target_doc = await files_collection.find_one({"_id": ObjectId(_id)})
                except Exception:
                    target_doc = None

    if not target_doc and len(message.command) >= 2:
        arg = message.command[1].strip()
        try:
            target_doc = await files_collection.find_one({"_id": ObjectId(arg)})
        except Exception:
            target_doc = await files_collection.find_one({"file_id": arg})

    if not target_doc:
        await message.reply_text("Could not find the file. Reply to the original media or provide the DB id.")
        return

    token = make_token()
    share_doc = {
        "token": token,
        "file_id": target_doc["_id"],
        "created_by": message.from_user.id if message.from_user else None,
        "created_at": datetime.utcnow(),
        "expires_at": None
    }
    if SHARE_TOKEN_TTL_DAYS and SHARE_TOKEN_TTL_DAYS > 0:
        share_doc["expires_at"] = datetime.utcnow() + timedelta(days=SHARE_TOKEN_TTL_DAYS)
    try:
        await shares_collection.insert_one(share_doc)
    except Exception:
        token = make_token()
        share_doc["token"] = token
        await shares_collection.insert_one(share_doc)

    bot_username = await get_bot_username()
    link = f"https://t.me/{bot_username}?start=share_{token}"
    await message.reply_text(f"Share link (anyone can open it):\n{link}")

@app.on_message(filters.command("search") & filters.private)
async def search_handler(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /search <query>")
        return
    query = " ".join(message.command[1:]).strip()
    cursor = files_collection.find({"$text": {"$search": query}}, {"score": {"$meta": "textScore"}}).sort([("score", {"$meta": "textScore"})]).limit(10)
    results = await cursor.to_list(length=10)
    if not results:
        regex = {"$or": [{"file_name": {"$regex": query, "$options": "i"}}, {"caption": {"$regex": query, "$options": "i"}}]}
        results = await files_collection.find(regex).limit(10).to_list(length=10)

    if not results:
        await message.reply_text("No results found.")
        return

    lines = []
    buttons = []
    for r in results:
        rid = str(r["_id"])
        name = r.get("file_name") or r.get("caption") or r.get("file_type") or "unknown"
        uploader = r.get("uploader_username") or r.get("uploader_id") or "unknown"
        lines.append(f"• {name} — ({r.get('file_type')}) — id: {rid} — uploader: {uploader}")
        buttons.append([InlineKeyboardButton("Get link", callback_data=f"getlink:{rid}")])

    text = "Search results:\n\n" + "\n".join(lines)
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"^getlink:(.+)"))
async def callback_getlink(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    data = callback_query.data or ""
    _, rid = data.split(":", 1)
    try:
        file_doc = await files_collection.find_one({"_id": ObjectId(rid)})
    except Exception:
        file_doc = None
    if not file_doc:
        await callback_query.message.reply_text("File not found.")
        return
    token = make_token()
    share_doc = {
        "token": token,
        "file_id": file_doc["_id"],
        "created_by": callback_query.from_user.id if callback_query.from_user else None,
        "created_at": datetime.utcnow(),
        "expires_at": None
    }
    if SHARE_TOKEN_TTL_DAYS and SHARE_TOKEN_TTL_DAYS > 0:
        share_doc["expires_at"] = datetime.utcnow() + timedelta(days=SHARE_TOKEN_TTL_DAYS)
    try:
        await shares_collection.insert_one(share_doc)
    except Exception:
        token = make_token()
        share_doc["token"] = token
        await shares_collection.insert_one(share_doc)

    bot_username = await get_bot_username()
    link = f"https://t.me/{bot_username}?start=share_{token}"
    await callback_query.message.reply_text(f"Share link:\n{link}")

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    args = message.command[1:] if len(message.command) > 1 else []
    if not args:
        await message.reply_text("Welcome to FileStore Bot. Send me files to save them. Use /search <query>.")
        return
    arg = args[0]
    if arg.startswith("share_"):
        token = arg.split("share_", 1)[1]
        share = await shares_collection.find_one({"token": token})
        if not share:
            await message.reply_text("Share link invalid or expired.")
            return
        file_doc = await files_collection.find_one({"_id": share["file_id"]})
        if not file_doc:
            await message.reply_text("File not found.")
            return
        await message.reply_text("Sending shared file...")
        await send_saved_file(message.chat.id, file_doc)
        # record delivery
        try:
            await shares_collection.update_one({"_id": share["_id"]}, {"$push": {"delivered_to": {"user_id": message.from_user.id if message.from_user else None, "at": datetime.utcnow()}}})
        except Exception:
            log.exception("Failed to update share delivery info.")
    else:
        await message.reply_text("Welcome. Use /help to learn more.")

@app.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    text = (
        "FileStore Bot commands:\n"
        "• Send any file to save it. You'll get a DB id.\n"
        "• /share (reply to your media) — generate a public share link.\n"
        "• /share <db_id> — generate a share link for a known id.\n"
        "• /search <query> — search saved files by name or caption.\n"
        "Clicking a share link opens this bot and sends the file to the clicker."
    )
    await message.reply_text(text)

async def main():
    # Ensure DB indexes and start bot
    await ensure_indexes()
    await app.start()
    bot_username = await get_bot_username()
    log.info(f"Bot @{bot_username} started.")
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down.")
