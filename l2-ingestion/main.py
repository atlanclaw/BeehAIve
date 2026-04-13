from contextlib import asynccontextmanager
from fastapi import FastAPI
from .otel_setup import setup_tracing
from .health import router as health_router
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
log = logging.getLogger("pkb.l2.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_tracing()   # L2-07: TracerProvider einmalig initialisieren
    log.info("pkb-ingestion gestartet")
    yield
    log.info("pkb-ingestion wird beendet")


app = FastAPI(title="pkb-ingestion", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)


@app.post("/ingest")
async def ingest_file(payload: dict):
    """Triggert Pipeline für eine einzelne Datei (inbox_watcher._trigger_ingest)."""
    from pathlib import Path
    from .pipeline import run_vault_scan
    path = Path(payload.get("path", ""))
    if not path.exists():
        return {"error": f"Datei nicht gefunden: {path}"}
    return run_vault_scan(vault_root=path.parent, trigger="inbox_file")
