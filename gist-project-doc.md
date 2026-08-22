# Gist — WhatsApp → Instagram Reel Summarizer

**Gist** is a fully free, self-hosted pipeline that turns Instagram Reels sent via WhatsApp into structured AI-generated summaries. It extracts audio transcriptions, visual frame descriptions, and post captions using local open-source models, then indexes summaries in a local vector memory (ChromaDB) and mirrors them into Notion for easy browsing.

Project path: `c:\Users\SUJAY\Documents\projects\gist` (junctioned as `go-on`).

---

## Architecture

- **`wa-reel-bridge/`** — Node.js, `@whiskeysockets/baileys`. Listens on WhatsApp for `instagram.com` reel links and POSTs a payload to `http://localhost:5050/webhook`.
  - Payload fields: `source`, `chatJid`, `link`, `caption_context`, `receivedAt`.
  - Config (`wa-reel-bridge/.env`): `WEBHOOK_URL`, `ONLY_FROM_ME=true`, `ALLOWED_CHAT_JID`.
  - Auth session keys stored in `auth_state/` (gitignored).
- **`reel-extract/`** — Python.
  - `extract.py`: uses `yt-dlp` (v2026.08.19) + `ffmpeg` to produce `video.mp4`, `audio.wav` (16kHz mono PCM), `frames/frame_01.jpg`..`frame_05.jpg`, `caption.txt`, `meta.json`.
  - `understand.py`: `faster-whisper` for `transcript.txt`; Ollama vision model `moondream` (1.7GB) for `frames_description.txt`; bundles everything into `combined_context.txt`.
- **`server/app.py`** — FastAPI webhook orchestration server on port `5050`. Runs the full pipeline: receive payload → extract → understand → summarize → store → reply.

### Removed from the architecture

Odysseus (a Docker Compose agent platform that previously wrapped Ollama + ChromaDB at `127.0.0.1:7000` / `127.0.0.1:8100`) has been **shut down** (`docker compose down`) and is no longer part of the stack. Its two jobs are now done directly:

- **Summarization**: `server/app.py` calls the local Ollama API directly (`http://localhost:11434`, model `llama3.2:3b`) instead of routing through Odysseus.
- **Vector memory**: ChromaDB is used embedded/in-process via `chromadb.PersistentClient(path="./chroma_data")` — no separate container or server needed. Collection name: `odysseus_memories` (kept for continuity), MiniLM embeddings.

### Added to the architecture

- **Notion**: a free Notion internal integration writes each summary as a page into a Notion database, used purely as a human-readable, browsable, mobile-friendly log. Database properties: `Title`, `Summary`, `Caption`, `Link`, `Date`, `Tags`. Notion is *not* used for semantic search — ChromaDB still handles "find reels about X" queries.
- **WhatsApp reply loop**: previously, nothing sent a message back to WhatsApp after processing (this was the main bug). Fix: `wa-reel-bridge` exposes `POST /reply` (`{ chatJid, text }`) which calls `sock.sendMessage(chatJid, { text })` on the existing Baileys socket. `server/app.py` calls this endpoint after Chroma + Notion writes complete, sending back the summary text.

---

## Env vars

**`wa-reel-bridge/.env`**
- `WEBHOOK_URL` → `http://localhost:5050/webhook`
- `ONLY_FROM_ME` → `true`
- `ALLOWED_CHAT_JID`

**`server/.env`** (or equivalent config)
- `NOTION_TOKEN`
- `NOTION_DATABASE_ID`
- `WA_BRIDGE_REPLY_URL` → e.g. `http://localhost:3000/reply` (whatever port `wa-reel-bridge` runs its Express server on)

No Odysseus-related env vars (Chroma host/port at `127.0.0.1:8100`, Odysseus URL) should remain.

---

## Build-order checklist

- [x] Step 0: Initial setup, project naming, dependency audit (`yt-dlp`, `ffmpeg`, `ollama`, `docker`, `python`).
- [x] Step 1: `wa-reel-bridge` sanity check — QR auth, link detection verified.
- [x] Step 2: Standalone `reel-extract/extract.py` — download + extraction verified on a sample reel.
- [x] Step 3: `reel-extract/understand.py` — transcription + vision description + context bundling verified.
- [x] Step 4 (original): Odysseus orchestration + vector memory — **since replaced**, see "Removed from the architecture" above.
- [x] Step 5: End-to-end webhook integration (`server/app.py` on port 5050) — payload receipt through to memory indexing verified.
- [ ] Step 6: Direct Ollama summarization call in `server/app.py` (replacing Odysseus routing).
- [ ] Step 7: Bare/embedded ChromaDB client (replacing Odysseus's Chroma instance).
- [ ] Step 8: Notion integration + writer function.
- [ ] Step 9: WhatsApp reply endpoint in `wa-reel-bridge` + call from `server/app.py`.
- [ ] Step 10: End-to-end test of the rebuilt pipeline.

---

## Key decisions & gotchas

- **Project alias**: linked via Windows directory junction so all paths use the project name **gist**.
- **Local infra confirmed working**: Python 3.14, Docker 29.5, Ollama, `yt-dlp`, `ffmpeg`.
- **yt-dlp**: kept upgraded to `2026.08.19` to handle Instagram webpage/DASH stream changes.
- **Vision model**: `moondream` chosen for fast, lightweight per-frame descriptions.
- **Everything must stay free and self-hosted** — no paid APIs except Notion's free tier.
- **Notion failures should not break the pipeline** — if the Notion write fails, log a warning and continue; Chroma indexing and the WhatsApp reply should still succeed independently.
- **WhatsApp reply POST should not block/crash the webhook** if `wa-reel-bridge` is briefly unreachable — log and continue.

---

## How to run

1. Start the Gist server:
   ```powershell
   python server/app.py
   ```
2. Start the WhatsApp bridge:
   ```powershell
   cd wa-reel-bridge
   npm start
   ```
3. Send an Instagram Reel link to yourself on WhatsApp. Gist downloads, transcribes, describes, summarizes, indexes into ChromaDB, logs to Notion, and replies in the same WhatsApp chat with the summary.
