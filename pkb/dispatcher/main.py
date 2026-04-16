"""
L3 Dispatcher
Nimmt Anfragen vom Gateway entgegen, leitet sie an pkb-beeai weiter.
Schreibt WAL-Eintraege fuer Auditierung.
"""
import os
import logging
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)
log = logging.getLogger("pkb.l3.dispatcher")

BEEAI_ENDPOINT = os.getenv("BEEAI_ENDPOINT", "http://pkb-beeai:4713")
WAL_DIR = Path(os.getenv("PKB_ROOT", "/srv/pkb")) / "wal"


def write_wal(event: dict):
    WAL_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    wal_file = WAL_DIR / f"dispatch_{ts}.json"
    wal_file.write_text(json.dumps(event, ensure_ascii=False, indent=2))


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("l3-dispatcher gestartet — BeeAI: %s", BEEAI_ENDPOINT)
    yield
    log.info("l3-dispatcher wird beendet")


app = FastAPI(title="l3-dispatcher", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "l3-dispatcher"}


@app.post("/dispatch")
async def dispatch(payload: dict):
    """
    Empfaengt {"query": str, "user_id": str, "chat_id": str} vom Gateway.
    Leitet an BeeAI weiter und gibt Antwort zurueck.
    """
    query = payload.get("query", "")
    user_id = payload.get("user_id", "unknown")
    chat_id = payload.get("chat_id", "unknown")

    log.info("Dispatch von user=%s: %s", user_id, query[:120])
    write_wal({"event": "dispatch", "user_id": user_id, "chat_id": chat_id,
               "query": query, "ts": datetime.now(timezone.utc).isoformat()})

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{BEEAI_ENDPOINT}/query",
                                     json={"query": query, "context": {"user_id": user_id}})
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPError as e:
        log.error("BeeAI nicht erreichbar: %s", e)
        raise HTTPException(status_code=503, detail="BeeAI-Service nicht verfuegbar")

    write_wal({"event": "response", "user_id": user_id, "answer": result.get("answer", "")[:512],
               "ts": datetime.now(timezone.utc).isoformat()})
    return JSONResponse(content=result)
