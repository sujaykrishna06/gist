# Gist — WhatsApp → Instagram Reel Summarizer

**Gist** is a fully free, self-hosted automated pipeline that transforms Instagram Reels sent via WhatsApp into structured, AI-generated summaries. It extracts audio transcriptions, visual frame descriptions, and post captions using local open-source models, indexes them into embedded vector memory (ChromaDB), logs them to Notion, and replies directly back on WhatsApp.

---

## 🏗 Project Stack & Directory Structure

- **`wa-reel-bridge/`**: Node.js service using `@whiskeysockets/baileys` to listen for `instagram.com` reel links on WhatsApp, forward them to `http://localhost:5050/webhook`, and expose an Express `POST /reply` server on port `3000` to send WhatsApp messages back.
- **`reel-extract/`**: Python pipeline utilizing `yt-dlp` for video/caption downloads, `ffmpeg` for audio/frame extraction, `faster-whisper` for speech-to-text, and `Ollama` vision model (`moondream`) for frame descriptions.
- **`server/`**: FastAPI webhook orchestration server (`server/app.py`) listening on `http://localhost:5050`, running direct Ollama LLM summarization (`llama3.2:3b`), embedded ChromaDB indexing (`./chroma_data`), Notion database logging (`server/notion_writer.py`), and WhatsApp reply POSTing.
- **`chroma_data/`**: In-process, embedded ChromaDB directory storing vector memories in the `odysseus_memories` collection without external server dependencies.

---

## 📋 Build-Order Checklist

- [x] **Step 0: Initial Setup & Project Naming**
  - Aliased project to `gist`.
  - Reorganized `wa-reel-bridge` into its own directory.
  - Audited system dependencies (`yt-dlp`, `ffmpeg`, `ollama`, `python`).
- [x] **Step 1: Sanity-Check wa-reel-bridge**
  - Verified `npm start`, QR code authentication, and WhatsApp link detection.
  - Configured payload forwarding to `http://localhost:5050/webhook`.
- [x] **Step 2: Standalone Download/Extraction Script (`reel-extract/`)**
  - Built `reel-extract/extract.py` with `yt-dlp` (v2026.08.19) and `ffmpeg`.
  - Downloads `video.mp4`, 16kHz mono `audio.wav`, 5 keyframes (`frames/frame_01.jpg`..`frame_05.jpg`), `caption.txt`, and `meta.json`.
- [x] **Step 3: Transcription + Vision Description (`reel-extract/understand.py`)**
  - Speech-to-text via `faster-whisper` -> `transcript.txt`.
  - Frame visual analysis via Ollama `moondream` -> `frames_description.txt`.
  - Bundled context into `combined_context.txt`.
- [x] **Step 4: Direct Ollama & Embedded ChromaDB Setup**
  - Fully removed Odysseus containers.
  - Direct HTTP LLM summarization via Ollama (`llama3.2:3b`) returning structured JSON (`title`, `summary`, `tags`).
  - Embedded ChromaDB storage via `chromadb.PersistentClient(path="./chroma_data")` storing vectors & metadata.
- [x] **Step 5: Notion Integration & WhatsApp Reply Loop**
  - Built `server/notion_writer.py` posting to Notion REST API (`Title`, `Summary`, `Caption`, `Link`, `Date`, `Tags`) with graceful fallback if unconfigured.
  - Added Express `POST /reply` endpoint to `wa-reel-bridge/index.js` using `sock.sendMessage(chatJid, { text })`.
  - Added automated WhatsApp reply POST in `server/app.py`.

---

## 🔑 Config & Environment Variables

- `wa-reel-bridge/.env`:
  - `WEBHOOK_URL=http://localhost:5050/webhook`
  - `PORT=3000`
  - `ONLY_FROM_ME=true`
  - `ALLOWED_CHAT_JID=148399793934420@lid`
- `server/.env`:
  - `NOTION_TOKEN` (Notion internal integration token)
  - `NOTION_DATABASE_ID` (Notion database ID)
  - `WA_BRIDGE_REPLY_URL=http://localhost:3000/reply`
  - `SUMMARY_MODEL=llama3.2:3b`
  - `OLLAMA_API_URL=http://localhost:11434/api/generate`

---

## 🚀 How to Run the Complete System

1. **Start Gist Webhook Server**:
   ```powershell
   python server/app.py
   ```
2. **Start WhatsApp Bridge**:
   ```powershell
   cd wa-reel-bridge
   npm start
   ```
3. Send any Instagram Reel link to yourself on WhatsApp! Gist automatically downloads, transcribes, describes, summarizes, stores in embedded ChromaDB, logs to Notion, and replies to your WhatsApp chat with the summary!





