"""PKB FastAPI Application - L1 REST API."""

import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import config
from .document_processor import (
    delete_document,
    export_all_documents,
    ingest_document,
    list_documents,
    query_documents,
    reassemble_document,
    update_document,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PKB API",
    description="Personal Knowledge Base - Document Ingestion & RAG Query API",
    version="1.0.0",
)


class IngestRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Document content to ingest")
    metadata: dict | None = Field(default=None, description="Optional metadata (title, source, tags)")


class IngestResponse(BaseModel):
    doc_id: str
    chunks: int
    status: str


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Query to search the PKB")
    top_k: int | None = Field(default=None, ge=1, le=20, description="Number of results")


class QueryResponse(BaseModel):
    query: str
    answer: str
    sources: list[dict]


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    services: dict


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check health of the PKB API and its dependencies."""
    import httpx

    services = {}

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"http://{config.QDRANT_HOST}:{config.QDRANT_PORT}/healthz",
                timeout=5.0,
            )
            services["qdrant"] = "healthy" if r.status_code == 200 else "unhealthy"
    except Exception:
        services["qdrant"] = "unreachable"

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"http://{config.OLLAMA_HOST}:{config.OLLAMA_PORT}/api/tags",
                timeout=5.0,
            )
            services["ollama"] = "healthy" if r.status_code == 200 else "unhealthy"
    except Exception:
        services["ollama"] = "unreachable"

    overall = "healthy" if all(v == "healthy" for v in services.values()) else "degraded"

    return HealthResponse(
        status=overall,
        timestamp=datetime.now(timezone.utc).isoformat(),
        services=services,
    )


@app.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest):
    """Ingest a document into the PKB."""
    try:
        result = ingest_document(request.content, request.metadata)
        return IngestResponse(**result)
    except Exception as e:
        logger.error("Ingestion failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """Query the PKB using RAG."""
    try:
        result = query_documents(request.query, request.top_k)
        return QueryResponse(**result)
    except Exception as e:
        logger.error("Query failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
async def get_documents():
    """List all documents in the PKB."""
    try:
        docs = list_documents()
        return {"documents": docs, "count": len(docs)}
    except Exception as e:
        logger.error("List documents failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/documents/{doc_id}")
async def remove_document(doc_id: str):
    """Delete a document from the PKB."""
    try:
        result = delete_document(doc_id)
        return result
    except Exception as e:
        logger.error("Delete failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents/{doc_id}/content")
async def get_document_content(doc_id: str):
    """Get the full reassembled content of a document."""
    try:
        result = reassemble_document(doc_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get document content failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/documents/{doc_id}")
async def update_doc(doc_id: str, request: IngestRequest):
    """Update an existing document (re-chunk, re-embed, re-store)."""
    try:
        result = update_document(doc_id, request.content, request.metadata)
        return result
    except Exception as e:
        logger.error("Update document failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/export/vault")
async def export_vault():
    """Export all documents for Obsidian vault initialization."""
    try:
        documents = export_all_documents()
        return {"documents": documents, "count": len(documents)}
    except Exception as e:
        logger.error("Export vault failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/obsidian")
async def trigger_obsidian_sync():
    """Manually trigger a vault→Qdrant sync."""
    from .obsidian_sync import sync_vault_changes
    try:
        result = sync_vault_changes()
        return {"status": "completed", **result}
    except Exception as e:
        logger.error("Obsidian sync failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
