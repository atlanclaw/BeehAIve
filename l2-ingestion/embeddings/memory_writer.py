"""
Memory-Writer: schreibt MemoryChunk-Objekte in Qdrant pkb_memory.
Anders als vault_writer: Payload-Schema ist memory-spezifisch (ATL-90).
Kein Stale-Cleanup nötig: MEMORY.md wird vollständig neu geschrieben (dream run)
→ upsert überschreibt alle bestehenden Points mit gleicher chunk_id.
"""
import os
import logging
from typing import List
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from .models import MemoryChunk

log = logging.getLogger(__name__)
QDRANT_URL         = os.getenv("QDRANT_URL", "http://localhost:6333")
MEMORY_COLLECTION  = os.getenv("MEMORY_COLLECTION", "pkb_memory")
UPLOAD_BATCH_SIZE  = int(os.getenv("UPLOAD_BATCH_SIZE", "64"))

_client: QdrantClient | None = None

def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL)
    return _client


def _build_memory_payload(chunk: MemoryChunk) -> dict:
    return {
        "docid":         chunk.docid,
        "source":        chunk.source,
        "dream_ts":      chunk.dream_ts.isoformat() if chunk.dream_ts else None,
        "session_count": chunk.session_count,
        "chunk_index":   chunk.chunk_index,
    }


def upsert_memory(chunks: List[MemoryChunk]) -> dict:
    if not chunks:
        return {"upserted": 0, "errors": 0}

    client = _get_client()
    stats = {"upserted": 0, "errors": 0}

    points = [
        PointStruct(
            id=chunk.chunk_id,
            vector=chunk.vector,
            payload=_build_memory_payload(chunk),
        )
        for chunk in chunks
    ]

    try:
        client.upload_points(
            collection_name=MEMORY_COLLECTION,
            points=points,
            batch_size=UPLOAD_BATCH_SIZE,
            parallel=1,
            max_retries=3,
            wait=True,
        )
        stats["upserted"] = len(points)
        log.info("memory: %d points upserted → %s", len(points), MEMORY_COLLECTION)
    except Exception as exc:
        log.error("memory upsert failed: %s", exc)
        stats["errors"] += len(chunks)

    return stats
