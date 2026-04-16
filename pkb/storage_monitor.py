"""
L0 Storage Monitor.

Event-getriebener Storage Monitor (inotify via watchdog).
Prüft nur bei Schreib-Events UND wenn freier Puffer < MIN_FREE_BUFFER_GB.

Vier Schwellen:
    < 80%   → OK  (nichts)
    >= 80%  → WARN_80   (silent WAL-Eintrag)
    >= 90%  → CRIT_90   (WAL + notify_fn)
    >= 95%  → STOP_95   (WAL + stop_event + notify_fn → Schreibpause)

Kein automatischer Reset — nur durch tatsächliche Speicher-Freigabe.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
from enum import Enum

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger("pkb.storage_monitor")

MIN_FREE_BUFFER_GB = 5.0   # Puffer-Gate: Prüfung nur wenn free < 5 GB
DEBOUNCE_SEC = 10.0        # max. 1 Prüfung alle 10s


class StorageLevel(Enum):
    OK = "ok"
    WARN_80 = "warn_80pct"     # silent WAL
    CRIT_90 = "crit_90pct"     # Notify
    STOP_95 = "stop_95pct"     # Schreibpause


def _use_color() -> bool:
    """ANSI-Farben nur wenn TTY und NO_COLOR nicht gesetzt."""
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


class StorageMonitor:
    """
    Event-getriebener Storage Monitor.

    Args:
        vault_root:  Pfad zum Vault (watch target).
        wal_fn:      append_wal(root, event_type, summary, ticket_id, metadata).
        notify_fn:   optionaler Callback (StorageLevel) -> None bei >= 90%.
    """

    def __init__(self, vault_root, wal_fn, notify_fn=None) -> None:
        self.vault_root = vault_root
        self.wal_fn = wal_fn
        self.notify_fn = notify_fn
        self._stop_event = threading.Event()
        self._last_check = 0.0
        self._observer = Observer()

        outer = self

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event):  # noqa: D401, ARG002
                outer._on_event()

        self._handler = _Handler()

    # ─── Observer-Lifecycle ────────────────────────────────────────────

    def start(self) -> None:
        """Observer starten und rekursiv auf vault_root hören."""
        self._observer.schedule(self._handler, str(self.vault_root), recursive=True)
        self._observer.start()
        logger.info("StorageMonitor gestartet (watch=%s)", self.vault_root)

    def stop(self) -> None:
        """Observer sauber stoppen."""
        try:
            self._observer.stop()
            self._observer.join(timeout=5)
        except Exception as exc:  # noqa: BLE001
            logger.warning("StorageMonitor stop: %s", exc)

    # ─── Block/Unblock API ─────────────────────────────────────────────

    def wait_if_blocked(self) -> None:
        """Blockiert solange _stop_event gesetzt ist. Prüft alle 30 s.

        Kein automatischer Reset — der Caller ist dafür verantwortlich,
        den Block extern zu quittieren (z. B. nach manueller Speicher-
        Freigabe durch Operator).
        """
        while self._stop_event.is_set():
            time.sleep(30)

    # ─── Event-Handling ────────────────────────────────────────────────

    def _on_event(self) -> None:
        """Wird bei JEDEM FS-Event aufgerufen. Puffer-Gate + Debounce."""
        try:
            usage = shutil.disk_usage(self.vault_root)
        except (FileNotFoundError, PermissionError) as exc:
            logger.debug("disk_usage fehlgeschlagen: %s", exc)
            return

        free_gb = usage.free / 1024 ** 3
        if free_gb >= MIN_FREE_BUFFER_GB:
            # Puffer-Gate: noch genug frei → nichts tun
            return

        now = time.monotonic()
        if now - self._last_check < DEBOUNCE_SEC:
            return
        self._last_check = now
        self._check()

    def _check(self) -> None:
        """Echte Schwellen-Prüfung. Schreibt WAL, triggert notify_fn, setzt stop_event."""
        usage = shutil.disk_usage(self.vault_root)
        pct = usage.used / usage.total * 100

        if pct >= 95:
            self.wal_fn(
                self.vault_root,
                "storage_stop_95pct",
                f"{pct:.1f}% belegt",
                None,
                {},
            )
            self._stop_event.set()
            if self.notify_fn:
                self.notify_fn(StorageLevel.STOP_95)
        elif pct >= 90:
            self.wal_fn(
                self.vault_root,
                "storage_crit_90pct",
                f"{pct:.1f}% belegt",
                None,
                {},
            )
            if self.notify_fn:
                self.notify_fn(StorageLevel.CRIT_90)
        elif pct >= 80:
            self.wal_fn(
                self.vault_root,
                "storage_warn_80pct",
                f"{pct:.1f}% belegt",
                None,
                {},
            )
        # < 80 %: kein Eintrag, kein Notify
