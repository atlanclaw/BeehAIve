"""
MEMORY.md — verdichtete Wissensdatei (Hard Constraint: max. 200 Zeilen).

Nur ``autoDream`` via :func:`dream_lock` darf ``MEMORY.md`` schreiben.
"""
import datetime
import fcntl
import json
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def dream_lock(root: str):
    """Exklusiver Lock für MEMORY.md — nur autoDream darf schreiben."""
    lock_path = Path(root) / "pkb" / "90-system" / ".dream.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("dream_lock: MEMORY.md ist bereits gesperrt")
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def update_dream_state(root: str, line_count: int) -> None:
    """Aktualisiert ``90-system/.dream_state.json`` mit Timestamp + Zeilenzahl."""
    state_path = Path(root) / "pkb" / "90-system" / ".dream_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "line_count": line_count,
    }
    state_path.write_text(json.dumps(state, indent=2))
