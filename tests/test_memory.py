"""Tests für pkb.memory."""
import json
from pathlib import Path

import pytest

from pkb.memory import dream_lock, update_dream_state


def test_dream_lock_parallel_raises(tmp_path: Path) -> None:
    """Paralleler dream_lock schlägt fehl → RuntimeError."""
    root = tmp_path / "vault"
    with dream_lock(str(root)):
        with pytest.raises(RuntimeError, match="bereits gesperrt"):
            with dream_lock(str(root)):
                pass


def test_dream_lock_sequential_ok(tmp_path: Path) -> None:
    """Sequentielle Locks funktionieren ohne Fehler."""
    root = tmp_path / "vault"
    with dream_lock(str(root)):
        pass
    # Nach Freigabe wieder lockbar
    with dream_lock(str(root)):
        pass


def test_update_dream_state_writes_valid_json(tmp_path: Path) -> None:
    """update_dream_state schreibt valides JSON mit updated_at + line_count."""
    root = tmp_path / "vault"
    update_dream_state(str(root), line_count=42)

    state_path = root / "pkb" / "90-system" / ".dream_state.json"
    assert state_path.exists()
    data = json.loads(state_path.read_text())
    assert data["line_count"] == 42
    assert "updated_at" in data
    assert data["updated_at"].endswith("Z")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
