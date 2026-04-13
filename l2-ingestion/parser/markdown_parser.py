"""
Markdown Parser für PKB Vault-Notizen.
Extrahiert Frontmatter (YAML) und Body-Text.
Kein Chunking, kein Embedding — nur ParsedDocument-Output.

Pflicht-Env: PKB_ROOT (default: /srv/pkb)
"""
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from .models import ParsedDocument

logger = logging.getLogger("pkb.l2.parser.markdown")

PKB_ROOT = Path(os.getenv("PKB_ROOT", "/srv/pkb"))

_FRONTMATTER_DELIM = "---"


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Trennt YAML-Frontmatter vom Body. Gibt ({}, body) wenn kein FM."""
    lines = text.split("\n")
    if not lines[0].strip() == _FRONTMATTER_DELIM:
        return {}, text
    end = next(
        (i for i, l in enumerate(lines[1:], 1) if l.strip() == _FRONTMATTER_DELIM),
        None,
    )
    if end is None:
        return {}, text
    try:
        fm = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as e:
        logger.warning("Frontmatter-Parse-Fehler: %s", e)
        fm = {}
    body = "\n".join(lines[end + 1:]).strip()
    return fm, body


def _extract_title(fm: dict, body: str, path: Path) -> str:
    """Titel-Hierarchie: FM title > erste H1 > Dateiname."""
    if t := fm.get("title"):
        return str(t)
    for line in body.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def _norm_datetime(val) -> Optional[datetime]:
    """Konvertiert str/date/datetime Frontmatter-Wert zu datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        from datetime import date
        if isinstance(val, date):
            return datetime(val.year, val.month, val.day)
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


def parse_markdown(file_path: Path) -> ParsedDocument:
    """Parst eine einzelne Markdown-Datei zu ParsedDocument."""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    fm, body = _split_frontmatter(text)
    title = _extract_title(fm, body, file_path)
    rel_path = str(file_path.relative_to(PKB_ROOT))
    docid = hashlib.sha256(rel_path.encode()).hexdigest()[:16]
    content_hash = hashlib.sha256(body.encode()).hexdigest()

    return ParsedDocument(
        docid=docid,
        path=rel_path,
        source_type="markdown",
        title=title,
        body=body,
        raw_metadata=fm,
        status=fm.get("status"),
        topics=list(fm.get("topics") or []),
        categories=list(fm.get("categories") or []),
        created_at=_norm_datetime(fm.get("created_at") or fm.get("date")),
        updated_at=_norm_datetime(fm.get("updated_at") or fm.get("modified")),
        content_hash=content_hash,
        file_mtime=file_path.stat().st_mtime,
    )


def parse_vault(vault_root: Optional[Path] = None) -> list[ParsedDocument]:
    """Parst alle .md-Dateien unter vault_root. Default: PKB_ROOT."""
    root = vault_root or PKB_ROOT
    docs = []
    for md_file in root.rglob("*.md"):
        try:
            docs.append(parse_markdown(md_file))
        except Exception as e:  # noqa: BLE001
            logger.error("Parse-Fehler %s: %s", md_file, e)
    logger.info("parse_vault: %d Dokumente geparst", len(docs))
    return docs
