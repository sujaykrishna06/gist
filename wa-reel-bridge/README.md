# wa-reel-bridge

Watches a personal WhatsApp account for Instagram reel/post links and forwards
each one to a webhook URL as JSON. This is step 2 of the build plan — it does
**not** download or summarize anything yet, it just detects links and forwards
them so you can confirm the WhatsApp side works before wiring in Odysseus.

## Setup

```bash
npm install
cp .env.example .env
```

Edit `.env`:
- `WEBHOOK_URL` — for now, get a free throwaway URL from https://webhook.site
  and paste it in. You'll swap this for your Odysseus endpoint later.
- `ONLY_FROM_ME` — keep as `true` while testing. This means only messages
  *you* send (to yourself or any chat) will trigger it — so nobody else in a
  group chat can trigger your bot.
- `ALLOWED_CHAT_JID` — leave blank for now.

## Run

```bash
npm start
```

A QR code will print in the terminal. On your phone:
**WhatsApp > Settings > Linked Devices > Link a Device**, then scan it.

This creates a session in `auth_state/` (gitignored) so you don't have to
re-scan every time you restart the script — treat that folder like a password,
never commit or share it.

## Test it

1. Open WhatsApp on your phone, go to your own chat ("Message yourself" —
   search your own name/number, or use any private chat/group you own).
2. Share/send an Instagram reel link into that chat.
3. Watch the terminal — you should see:
   ```
   [detected] Instagram link from chat <jid>: https://www.instagram.com/reel/...
   [webhook] POST https://webhook.site/... -> 200
   ```
4. Check webhook.site in your browser — you should see the JSON payload
   land there with `link`, `chatJid`, `caption_context`, `receivedAt`.

Once you see that working end to end, note down the `chatJid` printed in the
logs — you can set `ALLOWED_CHAT_JID` to it so the bot only ever reacts to
that one chat (recommended once you move past testing).

## Notes / limitations

- This uses Baileys, an unofficial WhatsApp Web protocol library — not
  Meta's official Business API. It's the right tool for a personal, low
  volume project like this, but keep it that way: don't blast messages or
  add strangers, since aggressive automation risks the number getting
  flagged.
- Only reacts to `instagram.com/reel/`, `/reels/`, and `/p/` links. If
  Instagram's shared-link format changes, update `IG_LINK_REGEX` in
  `index.js`.
- Next step in the build plan: point `WEBHOOK_URL` at a real endpoint that
  triggers the download + summarize pipeline (yt-dlp -> whisper/vision ->
  Ollama), instead of webhook.site.


### Recommended free stack
n8n (self-hosted, free, open source) as the orchestrator/glue — it has a visual workflow builder, can trigger off incoming WhatsApp messages, shell out to yt-dlp/ffmpeg/whisper, call Ollama's API, and write to Notion/Sheets/Supabase. This fits your "AI automation" instinct well and is much easier to iterate on than raw code.
Baileys for WhatsApp connectivity (n8n can call it via webhook, or you run a small Node service alongside it).
Ollama for local LLM + vision model.
yt-dlp + ffmpeg + faster-whisper for media extraction.
Notion or Supabase for retrievable storage.
Hosted on an Oracle Cloud free-tier VM, so it's always on and reachable.

### Suggested build order
Set up the Oracle free VM (or decide to run locally first to prototype).
Get WhatsApp message-reading working in isolation (Baileys/whatsapp-web.js) — just log incoming messages to console.
Get yt-dlp downloading a reel + caption from a URL, standalone script.
Get Ollama running locally + test a vision model on a couple of extracted frames.
Wire it together in n8n: WhatsApp trigger → download → transcribe/caption/frames → LLM summarize → write to Notion.
Add comments-scraping as a "nice to have" once the core loop works.