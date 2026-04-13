"""
PDF Parser für PKB Inbox-Importe.
Verwendet PyMuPDF (fitz) als primären Parser, pdfminer.six als Fallback.
Output: ParsedDocument mit source_type='pdf'.
"""
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import ParsedDocument

logger = logging.getLogger("pkb.l2.parser.pdf")
PKB_ROOT = Path(os.getenv("PKB_ROOT", "/srv/pkb"))


def _extract_text_pymupdf(file_path: Path) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(file_path))
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    except ImportError:
        return ""


def _extract_text_pdfminer(file_path: Path) -> str:
    try:
        from pdfminer.high_level import extract_text
        return extract_text(str(file_path)).strip()
    except Exception as e:  # noqa: BLE001
        logger.error("pdfminer Fallback fehlgeschlagen: %s", e)
        return ""


def parse_pdf(file_path: Path) -> ParsedDocument:
    """Parst eine PDF-Datei zu ParsedDocument."""
    body = _extract_text_pymupdf(file_path)
    if not body:
        logger.warning("PyMuPDF leer — Fallback auf pdfminer: %s", file_path.name)
        body = _extract_text_pdfminer(file_path)

    rel_path = str(file_path.relative_to(PKB_ROOT))
    docid = hashlib.sha256(rel_path.encode()).hexdigest()[:16]
    content_hash = hashlib.sha256(body.encode()).hexdigest()
    title = file_path.stem.replace("-", " ").replace("_", " ").title()

    return ParsedDocument(
        docid=docid,
        path=rel_path,
        source_type="pdf",
        title=title,
        body=body,
        raw_metadata={},
        status="active",
        created_at=datetime.fromtimestamp(file_path.stat().st_ctime),
        updated_at=datetime.fromtimestamp(file_path.stat().st_mtime),
        content_hash=content_hash,
        file_mtime=file_path.stat().st_mtime,
    )
