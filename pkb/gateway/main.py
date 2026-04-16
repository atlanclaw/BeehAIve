"""
L6 Gateway — Telegram-Tor
Empfaengt Telegram-Updates, validiert Absender, leitet an Dispatcher weiter.
"""
import os
import logging
import asyncio

import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)
log = logging.getLogger("pkb.l6.gateway")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_IDS = set(
    int(i.strip()) for i in os.getenv("TELEGRAM_ALLOWED_IDS", "").split(",") if i.strip()
)
DISPATCHER_ENDPOINT = os.getenv("DISPATCHER_ENDPOINT", "http://l3-dispatcher:3693")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    if TELEGRAM_ALLOWED_IDS and user.id not in TELEGRAM_ALLOWED_IDS:
        log.warning("Unerlaubter Zugriff von user_id=%s", user.id)
        await update.message.reply_text("\u26d4 Zugriff verweigert.")
        return

    query = update.message.text or ""
    log.info("Nachricht von user=%s: %s", user.id, query[:120])

    await update.message.reply_text("\U0001f41d Verarbeite...")

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{DISPATCHER_ENDPOINT}/dispatch",
                json={"query": query, "user_id": str(user.id), "chat_id": str(chat_id)}
            )
            resp.raise_for_status()
            answer = resp.json().get("answer", "(keine Antwort)")
    except Exception as e:
        log.error("Dispatcher-Fehler: %s", e)
        answer = "\u274c Fehler beim Verarbeiten der Anfrage."

    await update.message.reply_text(answer)


# FastAPI health endpoint parallel zum Telegram-Bot
from fastapi import FastAPI
import uvicorn
import threading

health_app = FastAPI(title="pkb-gateway-health")

@health_app.get("/health")
async def health():
    return {"status": "ok", "service": "pkb-gateway"}


def run_health_server():
    uvicorn.run(health_app, host="0.0.0.0", port=7777, log_level="warning")


async def main():
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN nicht gesetzt — Gateway kann nicht starten")
        return

    # Health-Server in separatem Thread
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("pkb-gateway gestartet — erlaubte IDs: %s", TELEGRAM_ALLOWED_IDS or "alle")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    asyncio.run(main())
