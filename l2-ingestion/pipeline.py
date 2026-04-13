"""
Vault-Scan-Pipeline für pkb-ingestion.
Koordiniert L2-01 → L2-02 → L2-03 → L2-04 und schreibt
ingestion_complete WAL-Event nach erfolgreichem Abschluss.

Hard Constraint:
  ingestion_complete WAL wird NUR nach vollständigem Durchlauf geschrieben.
  Pipeline ist idempotent.
"""
import logging
import os
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("pkb.l2.pipeline")
PKB_ROOT = Path(os.getenv("PKB_ROOT", "/srv/pkb"))


def run_vault_scan(
    vault_root: Optional[Path] = None,
    trigger: str = "vault_scan",
) -> dict:
    """
    Vollständiger L2-Pipeline-Durchlauf:
    L2-01 parse_vault() → L2-02 chunk_documents() →
    L2-03 embed_chunks() → L2-04 route_and_upsert()
    → ingestion_complete WAL-Event
    """
    from opentelemetry import trace
    tracer = trace.get_tracer("pkb.l2.pipeline")

    with tracer.start_as_current_span("l2.pipeline.vault_scan") as span:
        span.set_attribute("pkb.layer", "L2")
        span.set_attribute("pipeline.trigger", trigger)

        t0 = time.monotonic()
        stats = {
            "docs_parsed": 0, "chunks_created": 0,
            "embeddings_ok": 0, "embeddings_cache": 0,
            "qdrant_upserted": 0, "qdrant_stale_del": 0,
            "errors": 0, "duration_s": 0.0, "trigger": trigger,
        }

        try:
            from parser.markdown_parser import parse_vault     # L2-01
            docs = parse_vault(vault_root or PKB_ROOT)
            stats["docs_parsed"] = len(docs)

            from chunker.chunker import chunk_documents         # L2-02
            chunks = chunk_documents(docs)
            stats["chunks_created"] = len(chunks)

            from embedder.embedder import embed_chunks          # L2-03
            embedding_results = embed_chunks(chunks)
            stats["embeddings_ok"]    = sum(1 for r in embedding_results if not r.from_cache)
            stats["embeddings_cache"] = sum(1 for r in embedding_results if r.from_cache)

            from embeddings.upsert import route_and_upsert      # L2-04
            upsert_stats = route_and_upsert(vault_results=embedding_results)
            stats["qdrant_upserted"]  = upsert_stats.get("vault_upserted", 0)
            stats["qdrant_stale_del"] = upsert_stats.get("vault_stale_del", 0)
            stats["errors"]          += upsert_stats.get("errors", 0)

        except Exception as exc:
            log.error("pipeline.run_vault_scan Fehler: %s", exc)
            stats["errors"] += 1
            span.record_exception(exc)
            stats["duration_s"] = round(time.monotonic() - t0, 2)
            return stats

        stats["duration_s"] = round(time.monotonic() - t0, 2)
        for k, v in stats.items():
            span.set_attribute(f"pipeline.{k}", v)

        _write_ingestion_complete_wal(stats)
        log.info("pipeline: %s", stats)
        return stats


def _write_ingestion_complete_wal(stats: dict) -> None:
    """Schreibt ingestion_complete WAL-Eintrag. Non-blocking bei Fehler."""
    try:
        from pkb.wal import append_wal
        append_wal(
            pkb_root=str(PKB_ROOT),
            event_type="ingestion_complete",
            summary=(
                f"Vault-Scan: {stats['docs_parsed']} Dokumente, "
                f"{stats['chunks_created']} Chunks, "
                f"{stats['embeddings_ok']} Embeddings, "
                f"{stats['errors']} Fehler"
            ),
            ticket_id="BASE-L2-07",
            metadata=stats,
        )
    except Exception as exc:
        log.warning("ingestion_complete WAL-Write fehlgeschlagen (non-blocking): %s", exc)
