#!/usr/bin/env python3
"""
Gist Orchestration Server & Webhook Receiver
--------------------------------------------
Listens for WhatsApp Reel payloads forwarded by wa-reel-bridge.
Automatically executes:
  1. reel-extract/extract.py   (Media & frame extraction)
  2. reel-extract/understand.py (Speech-to-text & vision frame description)
  3. Direct Ollama Summarization (llama3.2:3b structured JSON generation)
  4. Embedded ChromaDB Indexing (PersistentClient at ./chroma_data)
  5. Notion Database Logging   (Notion API v1 integration)
  6. WhatsApp Reply Loop        (POSTs summary back to wa-reel-bridge)
"""

import sys
import os
import re
import json
import urllib.request
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / "server" / ".env")
load_dotenv(dotenv_path=BASE_DIR / "wa-reel-bridge" / ".env")

sys.path.append(str(BASE_DIR / "reel-extract"))
from extract import extract_reel
from understand import process_reel_understanding
from notion_writer import post_to_notion

import chromadb

app = FastAPI(title="Gist Webhook Server")

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "llama3.2:3b")
WA_BRIDGE_REPLY_URL = os.environ.get("WA_BRIDGE_REPLY_URL", "http://localhost:3000/reply")
CHROMA_DATA_PATH = str(BASE_DIR / "chroma_data")

class WebhookPayload(BaseModel):
    source: str = "whatsapp"
    chatJid: str = ""
    link: str
    caption_context: str = ""
    receivedAt: str = ""

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
        print(f"[error] Ollama summarization API call failed: {e}", flush=True)
        return {
            "title": "Instagram Reel Summary",
            "summary": f"Extraction succeeded, but LLM summarization encountered an error: {e}",
            "tags": ["instagram", "reel"]
        }

    # Clean JSON output from LLM
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
        print(f"[warn] Could not parse LLM output as JSON ({e}). Falling back to raw response.", flush=True)

    return {
        "title": "Instagram Reel Summary",
        "summary": raw_response,
        "tags": ["instagram", "reel"]
    }

def store_in_embedded_chroma(
    reel_id: str,
    title: str,
    summary_text: str,
    caption_text: str,
    url: str,
    date_str: str,
    tags: list,
    chat_jid: str
) -> bool:
    try:
        client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)
        collection = client.get_or_create_collection("odysseus_memories")

        doc_text = f"Title: {title}\n\nSummary:\n{summary_text}\n\nCaption:\n{caption_text}"
        tag_str = ",".join(tags) if isinstance(tags, list) else str(tags)

        collection.upsert(
            ids=[f"reel_{reel_id}"],
            documents=[doc_text],
            metadatas=[{
                "link": url,
                "date": date_str,
                "tags": tag_str,
                "caption": caption_text[:500],
                "title": title[:200],
                "chat_jid": chat_jid,
                "source": "whatsapp_reel"
            }]
        )
        print(f"[chroma] Successfully indexed reel {reel_id} in embedded ChromaDB ({CHROMA_DATA_PATH})!", flush=True)
        return True
    except Exception as e:
        print(f"[error] Embedded ChromaDB indexing failed: {e}", flush=True)
        return False

def send_whatsapp_reply(chat_jid: str, reply_text: str):
    if not chat_jid:
        print("[warn] No chatJid provided in payload. Skipping WhatsApp reply.", flush=True)
        return

    payload = {
        "chatJid": chat_jid,
        "text": reply_text
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(WA_BRIDGE_REPLY_URL, data=data, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[server] Sent WhatsApp reply via bridge: HTTP {resp.status}", flush=True)
    except Exception as e:
        print(f"[warn] Failed to send WhatsApp reply to {WA_BRIDGE_REPLY_URL}: {e}", flush=True)

def process_reel_pipeline(payload: WebhookPayload):
    print(f"\n==================================================", flush=True)
    print(f"[server] STARTING GIST PIPELINE for URL: {payload.link}", flush=True)
    print(f"==================================================", flush=True)

    try:
        # 1. Download & Extract Media
        reel_dir = extract_reel(payload.link)
        reel_id = reel_dir.name

        # 2. Transcribe & Analyze Frames
        combined_context_path = process_reel_understanding(reel_dir)
        combined_context = combined_context_path.read_text(encoding="utf-8")

        # Load caption text if available
        caption_file = reel_dir / "caption.txt"
        caption_text = caption_file.read_text(encoding="utf-8") if caption_file.exists() else ""

        # 3. Direct Ollama Summarization
        print(f"[server] Summarizing content via Ollama ({SUMMARY_MODEL})...", flush=True)
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

        # Save summary locally
        summary_file = reel_dir / "summary.json"
        summary_file.write_text(json.dumps(summary_dict, indent=2), encoding="utf-8")

        date_str = datetime.now().strftime("%Y-%m-%d")

        # 4. Embedded ChromaDB Indexing
        store_in_embedded_chroma(
            reel_id=reel_id,
            title=title,
            summary_text=summary_text,
            caption_text=caption_text,
            url=payload.link,
            date_str=date_str,
            tags=tags,
            chat_jid=payload.chatJid
        )

        # 5. Notion Integration (Graceful warning if credentials missing)
        notion_url = post_to_notion(
            title=title,
            summary=summary_text,
            caption=caption_text,
            link=payload.link,
            date_str=date_str,
            tags=tags
        )

        # 6. WhatsApp Reply Loop
        reply_lines = [
            f"🎬 *{title}*",
            "",
            summary_text,
            "",
            f"🔗 *Link*: {payload.link}"
        ]
        if notion_url:
            reply_lines.append(f"📖 *Notion*: {notion_url}")

        reply_message = "\n".join(reply_lines)
        send_whatsapp_reply(payload.chatJid, reply_message)

        print(f"==================================================", flush=True)
        print(f"[server] GIST PIPELINE COMPLETE FOR {reel_id}", flush=True)
        print(f"==================================================\n", flush=True)

    except Exception as e:
        print(f"[error] Pipeline execution failed for {payload.link}: {e}", flush=True)

@app.post("/webhook")
async def handle_webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
    print(f"[webhook] Received payload for link: {payload.link}", flush=True)
    background_tasks.add_task(process_reel_pipeline, payload)
    return {
        "status": "accepted",
        "message": "Gist pipeline triggered in background",
        "link": payload.link
    }

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "gist-server"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5050, reload=False)
