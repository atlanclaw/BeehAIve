"""Tests für pkb.wal."""
import datetime
import json
from pathlib import Path

import pytest

from pkb.wal import append_wal


def test_append_wal_creates_wal_dir_if_missing(tmp_path: Path) -> None:
    """Fehlendes wal/-Verzeichnis wird automatisch erstellt."""
    root = tmp_path / "vault"
    assert not (root / "pkb" / "90-system" / "wal").exists()

    append_wal(str(root), "boot", "First event")

    wal_dir = root / "pkb" / "90-system" / "wal"
    assert wal_dir.is_dir()
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    assert (wal_dir / f"{date_str}.jsonl").exists()


def test_append_wal_three_entries_schema(tmp_path: Path) -> None:
    """3x append → 3 Zeilen mit korrektem Schema."""
    root = tmp_path / "vault"
    append_wal(str(root), "evt1", "sum1")
    append_wal(str(root), "evt2", "sum2", ticket_id="ATL-79")
    append_wal(str(root), "evt3", "sum3", ticket_id=None, metadata={"k": 1})

    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    wal_file = root / "pkb" / "90-system" / "wal" / f"{date_str}.jsonl"
    lines = wal_file.read_text().strip().splitlines()
    assert len(lines) == 3

    entries = [json.loads(ln) for ln in lines]
    for entry in entries:
        assert set(entry.keys()) == {
            "ts",
            "event_type",
            "summary",
            "ticket_id",
            "metadata",
        }
        assert entry["ts"].endswith("Z")
        # ISO-8601 round-trip
        datetime.datetime.fromisoformat(entry["ts"].rstrip("Z"))
        assert isinstance(entry["metadata"], dict)

    assert entries[0]["event_type"] == "evt1"
    assert entries[1]["ticket_id"] == "ATL-79"
    assert entries[2]["metadata"] == {"k": 1}


def test_append_wal_daily_rotation_filename(tmp_path: Path) -> None:
    """Dateiname folgt YYYY-MM-DD.jsonl."""
    root = tmp_path / "vault"
    append_wal(str(root), "evt", "sum")
    wal_dir = root / "pkb" / "90-system" / "wal"
    files = list(wal_dir.glob("*.jsonl"))
    assert len(files) == 1
    name = files[0].name
    # YYYY-MM-DD.jsonl → 10 Zeichen Datum + ".jsonl"
    assert len(name) == len("YYYY-MM-DD.jsonl")
    datetime.datetime.strptime(name.removesuffix(".jsonl"), "%Y-%m-%d")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
