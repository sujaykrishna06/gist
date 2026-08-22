# Gist — Instagram Reel Summarizer (Telegram Bot)

**Gist** is a fully free, self-hosted automated pipeline that transforms Instagram Reels sent via Telegram into structured, AI-generated summaries. It extracts audio transcriptions, visual frame descriptions, and post captions using local open-source models, logs them to Notion, and replies directly back in Telegram.

---

## 🏗 Simplified Python Architecture

- **`bot.py`**: Single Python Telegram Bot & Pipeline Orchestrator using `python-telegram-bot`. Listens for `instagram.com/reel/` links, triggers extraction & comprehension, sends summaries back to Telegram, and logs to Notion.
- **`extract.py`**: Media & frame downloader using `yt-dlp` and `ffmpeg`. Automatically cleans up temp video/audio/frame files post-summarization.
- **`understand.py`**: Speech-to-text via `faster-whisper` and frame visual analysis via Ollama vision model (`moondream`).
- **`notion_writer.py`**: Notion REST API integration for logging Reel title, summary, caption, link, date, and tags to your Notion database.

---

## 🔑 Environment Variables (`.env`)

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ALLOWED_TELEGRAM_CHAT_ID=your_telegram_chat_id

# Notion Integration
NOTION_TOKEN=your_notion_token
NOTION_DATABASE_ID=your_notion_database_id

# Local Ollama
SUMMARY_MODEL=llama3.2:3b
OLLAMA_API_URL=http://localhost:11434/api/generate
```

---

## 🚀 How to Run 24/7 on Ubuntu Server

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start Telegram Bot with PM2**:
   ```bash
   pm2 start "venv/bin/python bot.py" --name "gist-bot"
   pm2 save
   ```

3. Share any Instagram Reel link directly to your bot on Telegram!
