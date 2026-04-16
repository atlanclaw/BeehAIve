"""
Write-Ahead-Log (WAL) — append-only JSONL pro Tag.

Jeder Systemvorgang schreibt einen Eintrag nach
    <root>/pkb/90-system/wal/YYYY-MM-DD.jsonl
"""
import datetime
import json
from pathlib import Path


def append_wal(
    root: str,
    event_type: str,
    summary: str,
    ticket_id: str = None,
    metadata: dict = None,
) -> None:
    """Append a WAL entry as a single JSONL line.

    Args:
        root:       Vault-Root (enthält ``pkb/90-system/wal/``).
        event_type: Kategorie-Slug des Events (z. B. ``storage_warn_80pct``).
        summary:    Kurzbeschreibung.
        ticket_id:  Optionale Linear-Issue-Referenz.
        metadata:   Zusätzliche Daten (dict).
    """
    wal_dir = Path(root) / "pkb" / "90-system" / "wal"
    wal_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "event_type": event_type,
        "summary": summary,
        "ticket_id": ticket_id,
        "metadata": metadata or {},
    }
    with open(wal_dir / f"{date_str}.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
