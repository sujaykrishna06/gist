#!/usr/bin/env python3
"""
Gist Telegram Bot & Pipeline Orchestrator
-----------------------------------------
Listens for Instagram Reel links in Telegram messages.
Executes:
  1. extract.py (Media & frame extraction via yt-dlp + ffmpeg)
  2. understand.py (Audio transcription via faster-whisper + frame description via Ollama moondream)
  3. Direct Ollama LLM Summarization (llama3.2:3b structured JSON generation)
  4. Notion Database Logging (Notion REST API)
  5. Replies directly back in the same Telegram chat with the formatted summary
  6. Automatically cleans up temporary media files to save disk space
"""

import os
import re
import sys
import json
import logging
import asyncio
import urllib.request
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

from extract import extract_reel, cleanup_reel
from understand import process_reel_understanding
from notion_writer import post_to_notion

# Configure Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("gist-bot")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_TELEGRAM_CHAT_ID = os.environ.get("ALLOWED_TELEGRAM_CHAT_ID", "").strip()
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "llama3.2:3b")

INSTAGRAM_REEL_REGEX = re.compile(r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p)/[A-Za-z0-9_-]+")

def summarize(context: str, model_name: str = SUMMARY_MODEL) -> dict:
    prompt = f"""You are a helpful AI assistant that summarizes social media content.
Below is the extracted context from an Instagram Reel (including post caption, speech transcription, and visual frame descriptions).

Create a structured summary in JSON format with exactly the following keys:
- "title": A short, clear, catchy title for the reel (max 10 words).
- "summary": A concise, well-formatted summary of what the reel explains (2-4 bullet points or short paragraphs).
- "tags": An array of 3-5 relevant single-word topic tags (e.g. ["github", "coding", "productivity"]).

Output ONLY raw JSON matching this schema, with no markdown codeblocks or extra text.

REEL CONTEXT:
{context}
"""
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OLLAMA_API_URL, data=data, headers={"Content-Type": "application/json"})

    raw_response = ""
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            raw_response = res_json.get("response", "").strip()
    except Exception as e:
        logger.error(f"Ollama API call failed: {e}")
        return {
            "title": "Instagram Reel Summary",
            "summary": f"Extraction succeeded, but LLM summarization encountered an error: {e}",
            "tags": ["instagram", "reel"]
        }

    try:
        json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            return {
                "title": parsed.get("title", "Instagram Reel Summary"),
                "summary": parsed.get("summary", raw_response),
                "tags": parsed.get("tags", ["instagram", "reel"])
            }
    except Exception as e:
        logger.warning(f"Could not parse LLM output as JSON ({e}). Using raw response.")

    return {
        "title": "Instagram Reel Summary",
        "summary": raw_response,
        "tags": ["instagram", "reel"]
    }

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name if update.effective_user else ""
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""

    reply_text = (
        f"👋 Hi {user_name}! I am **Gist**, your automated Instagram Reel summarizer.\n\n"
        f"Send or share any Instagram Reel link here, and I will transcribe it, summarize it using local AI, "
        f"log it to your Notion database, and reply with the summary!\n\n"
        f"Your Chat ID: `{chat_id}`"
    )
    await update.message.reply_text(reply_text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = str(update.effective_chat.id)
    if ALLOWED_TELEGRAM_CHAT_ID and chat_id != ALLOWED_TELEGRAM_CHAT_ID:
        logger.warning(f"Unauthorized chat ID access attempt: {chat_id}")
        return

    text = update.message.text
    match = INSTAGRAM_REEL_REGEX.search(text)
    if not match:
        return

    reel_url = match.group(0)
    logger.info(f"Processing Reel URL: {reel_url} for chat_id: {chat_id}")

    status_msg = await update.message.reply_text("⏳ **Processing Instagram Reel...**\n`Downloading & extracting media...`", parse_mode="Markdown")

    loop = asyncio.get_running_loop()

    def process_pipeline():
        # 1. Download & Extract
        reel_dir = extract_reel(reel_url)

        # 2. Transcribe & Analyze Frames
        combined_context_path = process_reel_understanding(reel_dir)
        combined_context = combined_context_path.read_text(encoding="utf-8")

        caption_file = reel_dir / "caption.txt"
        caption_text = caption_file.read_text(encoding="utf-8") if caption_file.exists() else ""

        # 3. LLM Summarization via Ollama
        summary_dict = summarize(combined_context)

        title = summary_dict.get("title", "Instagram Reel Summary")
        summary_raw = summary_dict.get("summary", "")
        if isinstance(summary_raw, list):
            summary_text = "\n".join(f"• {item}" for item in summary_raw)
        else:
            summary_text = str(summary_raw)

        tags = summary_dict.get("tags", [])
        if not isinstance(tags, list):
            tags = [str(tags)]

        date_str = datetime.now().strftime("%Y-%m-%d")

        # 4. Notion Logging
        notion_url = post_to_notion(
            title=title,
            summary=summary_text,
            caption=caption_text,
            link=reel_url,
            date_str=date_str,
            tags=tags
        )

        # 5. Cleanup temporary files to save disk space
        cleanup_reel(reel_dir)

        return {
            "title": title,
            "summary_text": summary_text,
            "notion_url": notion_url
        }

    try:
        result = await loop.run_in_executor(None, process_pipeline)

        reply_lines = [
            f"🎬 *{result['title']}*",
            "",
            result['summary_text'],
            "",
            f"🔗 *Link*: {reel_url}"
        ]
        if result['notion_url']:
            reply_lines.append(f"📖 *Notion*: {result['notion_url']}")

        await status_msg.edit_text("\n".join(reply_lines), parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Pipeline error for {reel_url}: {e}")
        await status_msg.edit_text(f"❌ **Failed to process Reel.**\n\nError: `{e}`", parse_mode="Markdown")

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN environment variable is missing!", file=sys.stderr)
        sys.exit(1)

    logger.info("Starting Gist Telegram Bot...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    logger.info("Bot is polling for messages. Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
