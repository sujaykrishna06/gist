// wa-reel-bridge
//
// Connects to a personal WhatsApp account (via QR code, same as WhatsApp Web),
// watches for incoming messages that contain an Instagram reel/post link, and
// forwards each link to a webhook URL (Gist backend server).
// Also exposes an Express POST /reply endpoint to send WhatsApp messages back.

require("dotenv").config();
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");
const qrcode = require("qrcode-terminal");
const pino = require("pino");
const fs = require("fs");
const path = require("path");
const express = require("express");

const WEBHOOK_URL = process.env.WEBHOOK_URL;
const ONLY_FROM_ME = (process.env.ONLY_FROM_ME || "true").toLowerCase() === "true";
const ALLOWED_CHAT_JID = process.env.ALLOWED_CHAT_JID || "";
const PORT = process.env.PORT || 3000;

// Matches instagram.com/reel/..., /reels/..., or /p/... links (with or without www, query strings, etc.)
const IG_LINK_REGEX = /https?:\/\/(www\.)?instagram\.com\/(reel|reels|p)\/[A-Za-z0-9_-]+\/?\S*/gi;

// Very small in-memory dedupe so the same link forwarded twice in a row doesn't fire the webhook twice.
const recentlySeen = new Map();
const DEDUPE_WINDOW_MS = 60_000;

let sock = null;

function isDuplicate(link) {
  const now = Date.now();
  for (const [seenLink, ts] of recentlySeen) {
    if (now - ts > DEDUPE_WINDOW_MS) recentlySeen.delete(seenLink);
  }
  if (recentlySeen.has(link)) return true;
  recentlySeen.set(link, now);
  return false;
}

function extractText(msg) {
  const m = msg.message;
  if (!m) return "";
  return (
    m.conversation ||
    m.extendedTextMessage?.text ||
    m.imageMessage?.caption ||
    m.videoMessage?.caption ||
    ""
  );
}

async function forwardToWebhook(payload) {
  if (!WEBHOOK_URL || WEBHOOK_URL.includes("replace-me")) {
    console.log("[warn] WEBHOOK_URL not configured — link detected but not forwarded:");
    console.log(payload);
    return;
  }
  try {
    const res = await fetch(WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    console.log(`[webhook] POST ${WEBHOOK_URL} -> ${res.status}`);
  } catch (err) {
    console.error("[webhook] failed to forward:", err.message);
  }
}

// Set up Express HTTP server for /reply calls from backend server
const app = express();
app.use(express.json());

app.post("/reply", async (req, res) => {
  const { chatJid, text } = req.body;
  if (!chatJid || !text) {
    return res.status(400).json({ error: "Missing chatJid or text in request body" });
  }
  if (!sock) {
    return res.status(503).json({ error: "WhatsApp socket not connected yet" });
  }
  try {
    await sock.sendMessage(chatJid, { text });
    console.log(`[reply] Sent WhatsApp reply to ${chatJid}`);
    return res.json({ status: "sent", chatJid });
  } catch (err) {
    console.error(`[reply] Failed to send message to ${chatJid}:`, err.message);
    return res.status(500).json({ error: err.message });
  }
});

app.get("/health", (req, res) => {
  res.json({ status: "ok", connected: !!sock });
});

app.listen(PORT, () => {
  console.log(`[bridge-server] Listening for reply POSTs on port ${PORT}`);
});

async function start() {
  const authDir = path.join(__dirname, "auth_state");
  if (!fs.existsSync(authDir)) fs.mkdirSync(authDir);

  const { state, saveCreds } = await useMultiFileAuthState(authDir);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: "silent" }),
    printQRInTerminal: false,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("\nScan this QR code with WhatsApp (Linked Devices > Link a Device):\n");
      qrcode.generate(qr, { small: true });
    }

    if (connection === "close") {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const loggedOut = statusCode === DisconnectReason.loggedOut;
      console.log(`[connection] closed (loggedOut=${loggedOut}). Reconnecting: ${!loggedOut}`);
      if (!loggedOut) start();
    } else if (connection === "open") {
      console.log("[connection] WhatsApp connected.");
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;

    for (const msg of messages) {
      if (!msg.message) continue;

      const chatJid = msg.key.remoteJid;
      const fromMe = !!msg.key.fromMe;

      if (ONLY_FROM_ME && !fromMe) continue;
      if (ALLOWED_CHAT_JID && chatJid !== ALLOWED_CHAT_JID) continue;

      const text = extractText(msg);
      if (!text) continue;

      const links = text.match(IG_LINK_REGEX);
      if (!links || links.length === 0) continue;

      for (const rawLink of links) {
        const link = rawLink.replace(/[)\].,]+$/, ""); // trim trailing punctuation
        if (isDuplicate(link)) {
          console.log(`[skip] duplicate within dedupe window: ${link}`);
          continue;
        }

        console.log(`[detected] Instagram link from chat ${chatJid}: ${link}`);

        await forwardToWebhook({
          source: "whatsapp",
          chatJid,
          link,
          caption_context: text,
          receivedAt: new Date().toISOString(),
        });
      }
    }
  });
}

start().catch((err) => {
  console.error("Fatal error starting bridge:", err);
  process.exit(1);
});
