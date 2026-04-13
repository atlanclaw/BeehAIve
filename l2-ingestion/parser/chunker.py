"""
Chunking-Service für PKB L2 Ingestion.
Zerlegt ParsedDocument.body in DocumentChunk-Objekte.

Strategie:
  - Markdown-Dokumente: Semantisches Chunking an H2/H3-Überschriften,
    dann Sliding-Window für Abschnitte > MAX_CHUNK_SIZE
  - PDF und Klartext: Paragraph-Chunking mit Overlap
  - Minimum-Chunk-Größe: MIN_CHUNK_SIZE (50 Zeichen) — zu kleine Chunks werden
    mit dem nächsten zusammengeführt

Kein Embedding, kein Qdrant-Zugriff — nur Text-Splitting.

Pflicht-Env (alle mit Default):
  CHUNK_SIZE        (default: 512)   — Ziel-Zeichenzahl pro Chunk
  CHUNK_OVERLAP     (default: 64)    — Überlapp zwischen Chunks
  MIN_CHUNK_SIZE    (default: 50)    — Minimale Zeichenzahl, sonst Merge
"""
import hashlib
import logging
import os
import re
from datetime import datetime
from typing import Optional

from .models import ParsedDocument

logger = logging.getLogger("pkb.l2.chunker")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))
MIN_CHUNK_SIZE = int(os.getenv("MIN_CHUNK_SIZE", "50"))


# ─── Datenmodell ─────────────────────────────────────────────────────────────

from dataclasses import dataclass, field

@dataclass
class DocumentChunk:
    docid: str
    chunk_id: str
    chunk_index: int
    total_chunks: int
    text: str
    content_hash: str
    payload: dict = field(default_factory=dict)


# ─── Splitter-Funktionen ─────────────────────────────────────────────────────

_H2_H3_PATTERN = re.compile(r'^#{2,3} .+', re.MULTILINE)


def _split_by_headings(text: str) -> list[str]:
    """Teilt Markdown-Text an H2/H3-Überschriften in Sektionen."""
    positions = [m.start() for m in _H2_H3_PATTERN.finditer(text)]
    if not positions:
        return [text]
    sections = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        sections.append(text[pos:end].strip())
    # Text vor erster H2/H3 (Intro-Abschnitt)
    if positions[0] > 0:
        intro = text[:positions[0]].strip()
        if intro:
            sections.insert(0, intro)
    return [s for s in sections if s]


def _split_by_size(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Sliding-Window-Split auf Wort-Grenzen. Fallback für große Sektionen."""
    words = text.split()
    if not words:
        return []
    chunks = []
    i = 0
    # Annäherung: ~5 Zeichen/Wort
    words_per_chunk = max(1, size // 5)
    overlap_words = max(0, overlap // 5)
    while i < len(words):
        end = min(i + words_per_chunk, len(words))
        chunk = " ".join(words[i:end])
        chunks.append(chunk)
        i += words_per_chunk - overlap_words
    return chunks


def _split_paragraphs(text: str) -> list[str]:
    """Paragraph-Split (Leerzeile) für PDF/Klartext."""
    return [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]


def _merge_small_chunks(chunks: list[str], min_size: int = MIN_CHUNK_SIZE) -> list[str]:
    """Mergt Chunks unter min_size mit dem vorherigen zusammen."""
    if not chunks:
        return []
    merged = [chunks[0]]
    for chunk in chunks[1:]:
        if len(chunk) < min_size:
            merged[-1] = merged[-1] + "\n" + chunk
        else:
            merged.append(chunk)
    return merged


# ─── Payload-Builder ─────────────────────────────────────────────────────────

def _dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    """Konvertiert datetime zu ISO-8601-String für Qdrant DATETIME-Index."""
    if dt is None:
        return None
    return dt.isoformat()


def _build_payload(doc: ParsedDocument, chunk_index: int) -> dict:
    """Erstellt Qdrant-Payload für pkb_vault gemäß ATL-90 Collection-Schema.

    Alle Felder müssen exakt den Payload-Indizes aus ATL-90 entsprechen:
    docid (KEYWORD), path (KEYWORD), title (TEXT), status (KEYWORD),
    topics (KEYWORD), categories (KEYWORD), chunk_index (INTEGER),
    created_at (DATETIME), updated_at (DATETIME)
    """
    return {
        "docid":       doc.docid,
        "path":        doc.path,
        "title":       doc.title,
        "status":      doc.status or "",          # None → "" (KEYWORD-Feld darf nicht None sein)
        "topics":      doc.topics,                 # list[str], ggf. []
        "categories":  doc.categories,             # list[str], ggf. []
        "chunk_index": chunk_index,
        "created_at":  _dt_to_iso(doc.created_at), # ISO-8601 oder None
        "updated_at":  _dt_to_iso(doc.updated_at), # ISO-8601 oder None
    }


# ─── Haupt-Chunker ────────────────────────────────────────────────────────────

def chunk_document(doc: ParsedDocument) -> list[DocumentChunk]:
    """Zerlegt ein ParsedDocument in eine geordnete Liste von DocumentChunk-Objekten."""
    if not doc.body or not doc.body.strip():
        logger.warning("chunk_document: leerer body für %s — übersprungen", doc.path)
        return []

    if doc.source_type in ("markdown", "inbox_md"):
        sections = _split_by_headings(doc.body)
    elif doc.source_type == "pdf":
        sections = _split_paragraphs(doc.body)
    else:
        sections = [doc.body]

    raw_chunks: list[str] = []
    for section in sections:
        if len(section) > CHUNK_SIZE:
            raw_chunks.extend(_split_by_size(section))
        else:
            raw_chunks.append(section)

    final_texts = _merge_small_chunks(raw_chunks)
    final_texts = [t for t in final_texts if t.strip()]

    if not final_texts:
        logger.warning("chunk_document: keine Chunks für %s", doc.path)
        return []

    total = len(final_texts)
    chunks = []
    for idx, text in enumerate(final_texts):
        chunk_id = f"{doc.docid}_{idx:04d}"
        payload = _build_payload(doc, chunk_index=idx)
        chunks.append(
            DocumentChunk(
                docid=doc.docid,
                chunk_id=chunk_id,
                chunk_index=idx,
                total_chunks=total,
                text=text,
                content_hash=doc.content_hash,
                payload=payload,
            )
        )

    logger.debug("chunk_document: %s → %d Chunks (CHUNK_SIZE=%d)", doc.path, total, CHUNK_SIZE)
    return chunks


def chunk_documents(docs: list[ParsedDocument]) -> list[DocumentChunk]:
    """Chunked eine Liste von ParsedDocuments."""
    all_chunks: list[DocumentChunk] = []
    for doc in docs:
        try:
            all_chunks.extend(chunk_document(doc))
        except Exception as e:  # noqa: BLE001
            logger.error("chunk_documents: Fehler bei %s: %s", doc.path, e)
    logger.info("chunk_documents: %d Dokumente → %d Chunks gesamt", len(docs), len(all_chunks))
    return all_chunks
