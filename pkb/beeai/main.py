"""
L3 BeeAI Agent Service
Empfaengt Tasks vom Dispatcher, fuehrt BeeAI-Agent aus, antwortet mit Ergebnis.
OTEL-Tracing via Langfuse OTLP.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from opentelemetry import trace

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)
log = logging.getLogger("pkb.l3.beeai")

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:1337")
BEE_LLM = os.getenv("BEE_LLM", "qwen2.5:3b")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://langfuse-web:7777")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("pkb-beeai gestartet — LLM: %s | Qdrant: %s", BEE_LLM, QDRANT_URL)
    yield
    log.info("pkb-beeai wird beendet")


app = FastAPI(title="pkb-beeai", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "pkb-beeai", "llm": BEE_LLM}


@app.post("/query")
async def query(payload: dict):
    """
    Empfaengt {"query": str, "context": dict} vom Dispatcher.
    TODO: BeeAI-Agent-Integration hier implementieren.
    """
    tracer = trace.get_tracer("pkb.beeai")
    with tracer.start_as_current_span("beeai.query") as span:
        user_query = payload.get("query", "")
        span.set_attribute("query.text", user_query[:256])
        log.info("Query empfangen: %s", user_query[:120])
        # STUB — hier BeeAI-Agent-Call einbauen
        return JSONResponse(content={
            "answer": f"[STUB] Query erhalten: {user_query}",
            "source": "pkb-beeai",
            "llm": BEE_LLM
        })
