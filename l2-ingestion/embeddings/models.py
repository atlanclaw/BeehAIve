# l2-ingestion/embeddings/models.py
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class MemoryChunk:
    """
    Speziell für pkb_memory — MEMORY.md Chunks.
    Unterschiedliches Payload-Schema gegenüber pkb_vault (ATL-90).
    Wird von memory_writer.py konsumiert.
    """
    docid: str               # sha256(path)[:16] — aus L2-01
    chunk_id: str            # f"{docid}_{chunk_index:04d}"
    chunk_index: int
    vector: list[float]      # len == 768
    text: str                # für Logging/Debug
    # pkb_memory spezifische Payload-Felder (ATL-90)
    source: str              # "MEMORY.md" (immer)
    dream_ts: Optional[datetime]   # Timestamp des letzten Dream-Runs
    session_count: int       # Anzahl verdichteter Sessions
