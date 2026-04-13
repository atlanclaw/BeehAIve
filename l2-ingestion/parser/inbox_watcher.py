"""
Inbox-Watcher für l1-data/vault/pkb/50-inbox/.
Verwendet inotify (inotify_simple) um neue Dateien zu erkennen.
Triggert Parser und ruft den /ingest Callback auf.

Pflicht-Env:
  PKB_ROOT         (default: /srv/pkb)
  INGEST_ENDPOINT  (default: http://localhost:8001/ingest)
"""
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger("pkb.l2.inbox_watcher")

PKB_ROOT = Path(os.getenv("PKB_ROOT", "/srv/pkb"))
INBOX_PATH = PKB_ROOT / "50-inbox"
INGEST_ENDPOINT = os.getenv("INGEST_ENDPOINT", "http://localhost:8001/ingest")

SUPPORTED_SUFFIXES = {".md", ".pdf", ".txt"}


def watch_inbox() -> None:
    """Blockierender Watch-Loop. Triggert Ingestion bei neuen Dateien."""
    try:
        import inotify_simple
    except ImportError:
        logger.warning("inotify_simple nicht verfügbar — Polling-Fallback aktiv (5s)")
        _poll_fallback()
        return

    inotify = inotify_simple.INotify()
    inotify.add_watch(
        str(INBOX_PATH),
        inotify_simple.flags.CLOSE_WRITE | inotify_simple.flags.MOVED_TO,
    )
    logger.info("Inbox-Watcher aktiv: %s", INBOX_PATH)

    while True:
        for event in inotify.read(timeout=1000):
            fname = event.name
            if not fname:
                continue
            fpath = INBOX_PATH / fname
            if fpath.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            logger.info("Neue Datei erkannt: %s", fpath.name)
            _trigger_ingest(fpath)


def _trigger_ingest(file_path: Path) -> None:
    """POST an /ingest Endpoint mit Dateipfad."""
    import httpx
    try:
        resp = httpx.post(
            INGEST_ENDPOINT,
            json={"path": str(file_path)},
            timeout=30.0,
        )
        resp.raise_for_status()
        logger.info("Ingest getriggert: %s — Status %d", file_path.name, resp.status_code)
    except Exception as e:  # noqa: BLE001
        logger.error("Ingest-Trigger fehlgeschlagen für %s: %s", file_path.name, e)


def _poll_fallback(interval: int = 5) -> None:
    """Polling-Fallback wenn inotify_simple nicht verfügbar."""
    seen: set[str] = set()
    while True:
        try:
            current = {
                f.name for f in INBOX_PATH.iterdir()
                if f.suffix.lower() in SUPPORTED_SUFFIXES
            }
            for new_file in current - seen:
                _trigger_ingest(INBOX_PATH / new_file)
            seen = current
        except Exception as e:  # noqa: BLE001
            logger.error("Poll-Fehler: %s", e)
        time.sleep(interval)
