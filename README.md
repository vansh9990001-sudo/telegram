# Telegram FileStore Bot (Pyrogram + MongoDB)

This repository contains a Telegram bot built with Pyrogram and Motor (async MongoDB driver). The bot saves incoming media file_ids to MongoDB, supports searching saved items, and generates shareable deep links that deliver stored files to users.

Contents
- bot.py — main bot, integrated with config/database modules
- config.py — environment configuration loader + validation
- database.py — Motor client, collection references, index setup
- requirements.txt — Python dependencies
- Dockerfile — image build (already present or add if needed)
- render.yaml — Render background-worker configuration
- .env.example — environment variable example (see README instructions)

Quick start (local)
1. Copy .env.example to .env and fill values:
   - API_ID, API_HASH, BOT_TOKEN
   - MONGO_URI (e.g., MongoDB Atlas connection string)
   - DB_NAME
   - Optional: BOT_USERNAME, SHARE_TOKEN_TTL_DAYS

2. Create a virtualenv and install dependencies:
   ```
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Run the bot:
   ```
   python bot.py
   ```

4. Testing:
   - Send a file to the bot in a private chat. The bot replies with the DB id.
   - Use `/share` (reply to the file or with the DB id) to generate a deep link:
     `https://t.me/<bot_username>?start=share_<token>`
   - Clicking the link opens the bot and sends the file to the clicker.

Deploy to Render
1. Push the repo to GitHub.
2. Create a new Render service:
   - Type: Background Worker
   - Connect the repo
   - Use Docker (Dockerfile present)
   - Add environment variables from `.env`
   - Deploy

Notes & suggestions
- Share links are public: anyone with the token can get the file. If you need restricted sharing, add authentication or link protection.
- If you set SHARE_TOKEN_TTL_DAYS > 0, shares will be created with an `expires_at` and a TTL index will be created (database.ensure_indexes).
- For production, consider logging, rate limiting, and monitoring.

If you want, I can:
- Open a PR on your repo with these files committed to branch `feature/add-filestore-bot`.
- Add a small health ping or metrics endpoint (requires a web service).
- Add automated token cleanup job or analytics for downloads.
