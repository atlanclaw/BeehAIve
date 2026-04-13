"""
Vault-Writer: schreibt EmbeddingResult-Objekte aus L2-03
idempotent in Qdrant pkb_vault.
Implementiert Stale-Chunk-Cleanup wenn Chunk-Anzahl sinkt.
"""
import os
import logging
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
from embedder.models import EmbeddingResult  # L2-03

log = logging.getLogger(__name__)
QDRANT_URL        = os.getenv("QDRANT_URL", "http://localhost:6333")
VAULT_COLLECTION  = os.getenv("QDRANT_COLLECTION", "pkb_vault")
UPLOAD_BATCH_SIZE = int(os.getenv("UPLOAD_BATCH_SIZE", "64"))

_client: QdrantClient | None = None

def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL)
    return _client


def upsert_vault(results: List[EmbeddingResult]) -> dict:
    """
    Schreibt EmbeddingResults in pkb_vault.
    1. upload_points() — idempotenter Upsert via chunk_id als Point-ID
    2. Stale-Chunk-Cleanup — löscht alte chunk_ids für betroffene docids
    Gibt Stats zurück: {upserted, stale_deleted, errors}
    """
    if not results:
        return {"upserted": 0, "stale_deleted": 0, "errors": 0}

    client = _get_client()
    stats = {"upserted": 0, "stale_deleted": 0, "errors": 0}

    points = [
        PointStruct(id=r.chunk_id, vector=r.vector, payload=r.payload)
        for r in results
    ]
    try:
        client.upload_points(
            collection_name=VAULT_COLLECTION,
            points=points,
            batch_size=UPLOAD_BATCH_SIZE,
            parallel=1,
            max_retries=3,
            wait=True,
        )
        stats["upserted"] = len(points)
        log.info("vault: %d points upserted → %s", len(points), VAULT_COLLECTION)
    except Exception as exc:
        log.error("vault upsert failed: %s", exc)
        stats["errors"] += len(points)
        return stats

    new_ids_by_docid: dict[str, set[str]] = {}
    for r in results:
        docid = r.payload.get("docid", "")
        new_ids_by_docid.setdefault(docid, set()).add(r.chunk_id)

    for docid, new_ids in new_ids_by_docid.items():
        try:
            stale = _find_stale_ids(client, VAULT_COLLECTION, docid, new_ids)
            if stale:
                client.delete(
                    collection_name=VAULT_COLLECTION,
                    points_selector=stale,
                    wait=True,
                )
                stats["stale_deleted"] += len(stale)
                log.info("vault: %d stale chunks deleted for docid=%s", len(stale), docid)
        except Exception as exc:
            log.warning("stale cleanup failed for docid=%s: %s", docid, exc)

    return stats


def _find_stale_ids(
    client: QdrantClient,
    collection: str,
    docid: str,
    current_ids: set[str],
) -> list[str]:
    scroll_filter = Filter(
        must=[
            FieldCondition(key="docid", match=MatchValue(value=docid))
        ]
    )
    result, _ = client.scroll(
        collection_name=collection,
        scroll_filter=scroll_filter,
        limit=1000,
        with_payload=False,
        with_vectors=False,
    )
    existing_ids = {str(point.id) for point in result}
    return list(existing_ids - current_ids)
