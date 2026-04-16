"""
L0 Resource Manager
Privilegierter Sidecar: überwacht cgroup v2 Budgets und exponiert /health.
Kommuniziert nur über pkb-internal Network.
"""
import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)
log = logging.getLogger("pkb.l0.resource_manager")

CONFIG_PATH = Path(os.getenv("RESOURCE_BUDGETS_CONFIG", "/app/config/resource-budgets.yaml"))
CGROUP_ROOT = Path("/sys/fs/cgroup")


def load_budgets() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    log.warning("resource-budgets.yaml nicht gefunden: %s", CONFIG_PATH)
    return {}


def read_cgroup_stat(service: str) -> dict:
    """Liest memory.current aus cgroup v2 für einen Service (best-effort)."""
    cgroup_path = CGROUP_ROOT / "system.slice" / f"{service}.service" / "memory.current"
    try:
        val = int(cgroup_path.read_text().strip())
        return {"memory_bytes": val}
    except Exception:
        return {"memory_bytes": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("pkb-resource-manager gestartet — config: %s", CONFIG_PATH)
    app.state.budgets = load_budgets()
    yield
    log.info("pkb-resource-manager wird beendet")


app = FastAPI(title="pkb-resource-manager", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "pkb-resource-manager"}


@app.get("/budgets")
async def get_budgets():
    """Gibt die konfigurierten Resource-Budgets zurück."""
    return JSONResponse(content=app.state.budgets)


@app.get("/cgroup/{service}")
async def get_cgroup(service: str):
    """Liest aktuellen cgroup v2 Memory-Verbrauch eines Services."""
    stat = read_cgroup_stat(service)
    budgets = app.state.budgets.get("services", {}).get(service, {})
    return {"service": service, "current": stat, "budget": budgets}


@app.post("/reload")
async def reload_config():
    """Hot-Reload der resource-budgets.yaml."""
    app.state.budgets = load_budgets()
    log.info("Budgets neu geladen")
    return {"status": "reloaded", "services": list(app.state.budgets.get("services", {}).keys())}
