"""
L6 Auditor — Read-only WAL-Pruefung
Kein LLM, kein externer Netzwerkzugriff. Liest WAL + Vault, prueft Regeln.
"""
import os
import json
import logging
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)
log = logging.getLogger("pkb.l6.auditor")

WAL_DIR = Path(os.getenv("PKB_ROOT", "/srv/pkb")) / "wal"
RULES_PATH = Path(os.getenv("AUDITOR_RULES_PATH", "/app/config/auditor-rules.yaml"))


def load_rules() -> dict:
    if RULES_PATH.exists():
        with open(RULES_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def scan_wal(limit: int = 50) -> list:
    if not WAL_DIR.exists():
        return []
    files = sorted(WAL_DIR.glob("*.json"), reverse=True)[:limit]
    entries = []
    for f in files:
        try:
            entries.append(json.loads(f.read_text()))
        except Exception:
            pass
    return entries


app = FastAPI(title="pkb-auditor", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "pkb-auditor"}


@app.get("/wal")
async def get_wal(limit: int = 20):
    """Gibt die letzten WAL-Eintraege zurueck."""
    entries = scan_wal(limit=limit)
    return JSONResponse(content={"count": len(entries), "entries": entries})


@app.get("/audit")
async def run_audit():
    """Fuehrt Regelcheck gegen WAL aus."""
    rules = load_rules()
    entries = scan_wal(limit=200)
    violations = []

    max_query_len = rules.get("max_query_length", 2000)
    for e in entries:
        q = e.get("query", "")
        if len(q) > max_query_len:
            violations.append({"rule": "max_query_length", "entry": e.get("ts"), "len": len(q)})

    log.info("Audit: %d Eintraege geprueft, %d Violations", len(entries), len(violations))
    return JSONResponse(content={
        "entries_checked": len(entries),
        "violations": violations,
        "rules_applied": list(rules.keys())
    })
