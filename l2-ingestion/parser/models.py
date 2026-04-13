from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class ParsedDocument:
    """Normiertes Dokument-Objekt — Output jedes Parsers."""
    # Identifikation
    docid: str                  # sha256 des path (stabil, kein Content-Hash hier)
    path: str                   # relativer Pfad ab PKB_ROOT, z.B. '10-projects/foo.md'
    source_type: str            # 'markdown' | 'pdf' | 'inbox_md'

    # Inhalt
    title: str                  # Frontmatter 'title' oder erste H1-Überschrift
    body: str                   # Volltext (ohne Frontmatter)
    raw_metadata: dict          # alle Frontmatter-Keys as-is

    # Standardisierte Metadaten (aus Frontmatter normiert)
    status: Optional[str] = None        # 'draft' | 'active' | 'archived'
    topics: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Provenienz
    content_hash: str = ""      # sha256(body) — für Embedding-Cache in L2-03
    file_mtime: float = 0.0     # os.path.getmtime — für Change-Detection
