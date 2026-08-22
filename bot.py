import os
import re
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import urllib.request
import urllib.parse

from extract import extract_reel, cleanup_reel
from understand import process_reel_understanding
from notion_writer import post_to_notion

# Configure Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("gist-bot")

# Load Environment Variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_TELEGRAM_CHAT_ID = os.environ.get("ALLOWED_TELEGRAM_CHAT_ID")
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "llama3.2:3b")

INSTAGRAM_REEL_REGEX = re.compile(
    r"https?://(?:www\.)?instagram\.com/reel/([A-Za-z0-9_-]+)",
    re.IGNORECASE
)

SYSTEM_PROMPT = """You are a video understanding & summarizing assistant.
Analyze the provided context (Instagram caption, speech-to-text transcript, and visual keyframe descriptions).
Produce a concise, structured JSON summary with the following key structure:
{
  "title": "<Catchy 4-8 word title summarizing the reel>",
  "summary": "<2-4 bullet points or concise paragraphs explaining key takeaways, actionable advice, or main ideas>",
  "tags": ["<tag1>", "<tag2>", "<tag3>"]
}
Output ONLY valid JSON. Do not include markdown code block backticks."""

def summarize(context_text: str) -> dict:
    prompt_payload = {
        "model": SUMMARY_MODEL,
        "prompt": f"{SYSTEM_PROMPT}\n\nREEL CONTEXT:\n{context_text}",
        "stream": False,
        "format": "json"
    }
    
    data = json.dumps(prompt_payload).encode("utf-8")
    req = urllib.request.Request(OLLAMA_API_URL, data=data, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            raw_response = res_json.get("response", "").strip()
    except Exception as e:
        logger.error(f"Error calling Ollama API ({SUMMARY_MODEL}): {e}")
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
        f"👋 Hi {user_name}! I am Gist, your automated Instagram Reel summarizer.\n\n"
        f"Send or share any Instagram Reel link here, and I will transcribe it, summarize it using local AI, "
        f"log it to your Notion database, and reply with the summary!\n\n"
        f"Your Chat ID: {chat_id}"
    )
    await update.message.reply_text(reply_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not (update.message.text or update.message.caption):
        return

    chat_id = str(update.effective_chat.id)
    if ALLOWED_TELEGRAM_CHAT_ID and chat_id != ALLOWED_TELEGRAM_CHAT_ID:
        logger.warning(f"Unauthorized chat ID access attempt: {chat_id}")
        return

    text = update.message.text or update.message.caption or ""
    match = INSTAGRAM_REEL_REGEX.search(text)
    if not match:
        return

    reel_url = match.group(0)
    logger.info(f"Processing Reel URL: {reel_url} for chat_id: {chat_id}")

    # Immediately respond with status message so user gets feedback right away
    status_msg = await update.message.reply_text("⏳ Received Reel link!\n[1/4] Downloading media & audio...")

    loop = asyncio.get_running_loop()

    def update_status_sync(msg_text: str):
        try:
            asyncio.run_coroutine_threadsafe(status_msg.edit_text(msg_text), loop)
        except Exception as err:
            logger.warning(f"Failed to update progress status: {err}")

    def process_pipeline():
        # 1. Download & Extract
        reel_dir = extract_reel(reel_url)

        # Update status
        update_status_sync("⏳ Processing Reel...\n[2/4] Transcribing audio & analyzing keyframe...")

        # 2. Transcribe & Analyze Frames
        combined_context_path = process_reel_understanding(reel_dir)
        combined_context = combined_context_path.read_text(encoding="utf-8")

        caption_file = reel_dir / "caption.txt"
        caption_text = caption_file.read_text(encoding="utf-8") if caption_file.exists() else ""

        # Update status
        update_status_sync("⏳ Processing Reel...\n[3/4] Generating AI summary...")

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

        # Update status
        update_status_sync("⏳ Processing Reel...\n[4/4] Logging entry to Notion database...")

        # 4. Notion Logging
        notion_url = post_to_notion(
            title=title,
            summary=summary_text,
            caption=caption_text,
            link=reel_url,
            date_str=date_str,
            tags=tags
        )

        # 5. Cleanup temporary files
        cleanup_reel(reel_dir)

        return {
            "title": title,
            "summary_text": summary_text,
            "notion_url": notion_url
        }

    try:
        result = await loop.run_in_executor(None, process_pipeline)

        reply_lines = [
            f"🎬 {result['title']}",
            "",
            result['summary_text'],
            "",
            f"🔗 Link: {reel_url}"
        ]
        if result['notion_url']:
            reply_lines.append(f"📖 Notion: {result['notion_url']}")

        full_reply = "\n".join(reply_lines)

        try:
            await status_msg.edit_text(full_reply)
        except Exception as edit_err:
            logger.warning(f"Message edit failed ({edit_err}), sending new message fallback...")
            await update.message.reply_text(full_reply)

    except Exception as e:
        logger.error(f"Pipeline error for {reel_url}: {e}")
        try:
            await status_msg.edit_text(f"❌ Failed to process Reel.\n\nError: {e}")
        except Exception:
            await update.message.reply_text(f"❌ Failed to process Reel.\n\nError: {e}")

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not configured in .env!")
        return

    logger.info("Starting Gist Telegram Bot...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    logger.info("Bot is polling for messages. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
