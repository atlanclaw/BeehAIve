"""
FastAPI /health Router für pkb-ingestion.
Prüft alle L2-Subsysteme read-only.
HTTP 200 = ok oder degraded (TOON-Ausfall toleriert).
HTTP 503 = kritisch (Qdrant oder Embedder nicht erreichbar).

Subsystem-Checks:
  qdrant       — GET collections-Liste, Pflicht-Collections aus L1
  toon         — GET /health des TOON-Service (L2-05)
  embedder     — Import-Check + Singleton vorhanden (L2-03)
  model_sel    — Singleton erreichbar (L2-06)
  wal          — PKB_ROOT/wal/ Verzeichnis lesbar
"""
import logging
import os
import time
from pathlib import Path
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

log = logging.getLogger("pkb.l2.health")

PKB_ROOT     = Path(os.getenv("PKB_ROOT", "/srv/pkb"))
QDRANT_URL   = os.getenv("QDRANT_URL", "http://localhost:6333")
TOON_URL     = os.getenv("TOON_URL", "http://pkb-toon:8080")
TOON_TIMEOUT = float(os.getenv("TOON_HEALTH_TIMEOUT_S", "2.0"))

router = APIRouter()


def _check_qdrant() -> dict:
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=QDRANT_URL, timeout=3.0)
        cols = client.get_collections()
        names = [c.name for c in cols.collections]
        required = {"pkb_vault", "pkb_memory", "pkb_sessions"}
        missing = required - set(names)
        if missing:
            return {"status": "degraded", "detail": f"missing collections: {missing}"}
        return {"status": "ok", "collections": names}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _check_toon() -> dict:
    try:
        import httpx
        resp = httpx.get(f"{TOON_URL}/health", timeout=TOON_TIMEOUT)
        return {"status": "ok"} if resp.status_code == 200 else {"status": "degraded", "detail": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"status": "degraded", "detail": str(exc)}


def _check_embedder() -> dict:
    try:
        from embedder.embedder import embedder
        return {"status": "ok"} if embedder is not None else {"status": "error", "detail": "embedder singleton is None"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _check_model_selector() -> dict:
    try:
        from toon.model_selector import model_selector
        return {"status": "ok"} if model_selector is not None else {"status": "error", "detail": "model_selector singleton is None"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _check_wal() -> dict:
    wal_dir = PKB_ROOT / "wal"
    if not wal_dir.exists():
        return {"status": "degraded", "detail": f"{wal_dir} existiert nicht"}
    try:
        list(wal_dir.iterdir())
        return {"status": "ok", "path": str(wal_dir)}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@router.get("/health")
async def health_check(response: Response) -> JSONResponse:
    t0 = time.monotonic()
    checks = {
        "qdrant":         _check_qdrant(),
        "toon":           _check_toon(),
        "embedder":       _check_embedder(),
        "model_selector": _check_model_selector(),
        "wal":            _check_wal(),
    }
    critical_failed = [k for k in ("qdrant", "embedder") if checks[k]["status"] == "error"]
    overall = "error" if critical_failed else ("degraded" if any(v["status"] == "degraded" for v in checks.values()) else "ok")
    body = {"status": overall, "service": "pkb-ingestion", "layer": "L2", "checks": checks, "duration_ms": round((time.monotonic() - t0) * 1000, 1)}
    log.info("health check: %s", overall)
    return JSONResponse(content=body, status_code=503 if overall == "error" else 200)
