"""
Haupt-Router für L2-04 Qdrant-Writes.
Entscheidet anhand source_type ob pkb_vault oder pkb_memory.
"""
import logging
from typing import List, Union
from embedder.models import EmbeddingResult   # L2-03
from .models import MemoryChunk
from . import vault_writer, memory_writer

log = logging.getLogger(__name__)

MEMORY_SOURCE_MARKER = "MEMORY.md"


def route_and_upsert(
    vault_results: List[EmbeddingResult],
    memory_chunks: List[MemoryChunk] | None = None,
) -> dict:
    stats = {
        "vault_upserted":  0,
        "vault_stale_del": 0,
        "memory_upserted": 0,
        "errors":          0,
    }

    if vault_results:
        v = vault_writer.upsert_vault(vault_results)
        stats["vault_upserted"]  = v.get("upserted", 0)
        stats["vault_stale_del"] = v.get("stale_deleted", 0)
        stats["errors"]         += v.get("errors", 0)

    if memory_chunks:
        m = memory_writer.upsert_memory(memory_chunks)
        stats["memory_upserted"] = m.get("upserted", 0)
        stats["errors"]         += m.get("errors", 0)

    log.info("upsert route: %s", stats)
    return stats
