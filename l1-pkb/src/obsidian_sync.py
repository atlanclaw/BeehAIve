"""Bidirectional sync bridge between Qdrant and an Obsidian vault directory."""

import argparse
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from .config import config

logger = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _log_to_backlog(
    action: str,
    doc_id: str | None = None,
    title: str | None = None,
    content_hash_before: str | None = None,
    content_hash_after: str | None = None,
) -> None:
    """Write a JSON entry to backlog/tickets/ for Paperclip tracking."""
    backlog_dir = Path(config.BACKLOG_PATH) / "tickets"
    backlog_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    entry = {
        "action": action,
        "doc_id": doc_id,
        "title": title,
        "content_hash_before": content_hash_before,
        "content_hash_after": content_hash_after,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    filename = f"obsidian-sync-{ts}-{action}.json"
    filepath = backlog_dir / filename
    filepath.write_text(json.dumps(entry, indent=2) + "\n")
    logger.info("Backlog entry: %s → %s", action, filepath.name)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _build_frontmatter(doc: dict, synced_at: str, content_hash: str) -> str:
    fm = {
        "doc_id": doc["doc_id"],
        "title": doc.get("metadata", {}).get("title", doc["doc_id"]),
        "source": "pkb-api",
        "tags": doc.get("metadata", {}).get("tags", []),
        "synced_at": synced_at,
        "content_hash": content_hash,
        "qdrant_chunks": doc.get("chunks", 0),
    }
    return "---\n" + yaml.dump(fm, default_flow_style=False, allow_unicode=True) + "---\n"


def _parse_vault_file(filepath: Path) -> tuple[dict | None, str]:
    raw = filepath.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(raw)
    if not match:
        return None, raw
    fm_text = match.group(1)
    body = raw[match.end():]
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None, raw
    return fm, body


def _safe_filename(title: str, doc_id: str) -> str:
    name = title if title and title != "Unknown" else doc_id
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name.strip()


def export_vault(vault_path: str | None = None) -> dict:
    """Export all documents from Qdrant into the Obsidian vault as Markdown files."""
    vault = Path(vault_path or config.OBSIDIAN_VAULT_PATH)
    pkb_dir = vault / "pkb"
    pkb_dir.mkdir(parents=True, exist_ok=True)

    api_url = config.PKB_API_URL.rstrip("/")
    synced_at = datetime.now(timezone.utc).isoformat()

    response = httpx.get(f"{api_url}/export/vault", timeout=120.0)
    response.raise_for_status()
    documents = response.json().get("documents", [])

    written = 0
    skipped = 0

    for doc in documents:
        doc_id = doc["doc_id"]
        content = doc.get("content", "")
        ch = _content_hash(content)
        title = doc.get("metadata", {}).get("title", doc_id)

        filename = _safe_filename(title, doc_id) + ".md"
        filepath = pkb_dir / filename

        if filepath.exists():
            existing_fm, _ = _parse_vault_file(filepath)
            if existing_fm and existing_fm.get("content_hash") == ch:
                skipped += 1
                continue

        frontmatter = _build_frontmatter(doc, synced_at, ch)
        filepath.write_text(frontmatter + "\n" + content, encoding="utf-8")
        written += 1

        _log_to_backlog(action="obsidian_export", doc_id=doc_id, title=title, content_hash_after=ch)

    logger.info("Export complete: %d written, %d skipped", written, skipped)
    return {"written": written, "skipped": skipped, "total": len(documents)}


def sync_vault_changes(vault_path: str | None = None) -> dict:
    """Scan all .md files in the vault and sync changes back to Qdrant."""
    vault = Path(vault_path or config.OBSIDIAN_VAULT_PATH)
    api_url = config.PKB_API_URL.rstrip("/")

    updated = 0
    created = 0
    unchanged = 0

    md_files = [
        f for f in vault.rglob("*.md")
        if ".obsidian" not in f.parts and f.name != "README.md"
    ]

    for filepath in md_files:
        fm, body = _parse_vault_file(filepath)
        body_stripped = body.strip()
        if not body_stripped:
            continue

        current_hash = _content_hash(body_stripped)

        if fm and fm.get("doc_id"):
            stored_hash = fm.get("content_hash", "")
            if current_hash == stored_hash:
                unchanged += 1
                continue

            doc_id = fm["doc_id"]
            metadata = {
                "title": fm.get("title", filepath.stem),
                "source": "obsidian",
                "tags": fm.get("tags", []),
            }
            response = httpx.put(
                f"{api_url}/documents/{doc_id}",
                json={"content": body_stripped, "metadata": metadata},
                timeout=120.0,
            )
            response.raise_for_status()

            fm["content_hash"] = current_hash
            fm["synced_at"] = datetime.now(timezone.utc).isoformat()
            fm["source"] = "obsidian"
            new_frontmatter = "---\n" + yaml.dump(fm, default_flow_style=False, allow_unicode=True) + "---\n"
            filepath.write_text(new_frontmatter + "\n" + body_stripped, encoding="utf-8")

            _log_to_backlog(
                action="obsidian_update", doc_id=doc_id, title=fm.get("title"),
                content_hash_before=stored_hash, content_hash_after=current_hash,
            )
            updated += 1

        else:
            title = filepath.stem
            metadata = {"title": title, "source": "obsidian", "tags": []}
            response = httpx.post(
                f"{api_url}/ingest",
                json={"content": body_stripped, "metadata": metadata},
                timeout=120.0,
            )
            response.raise_for_status()
            result = response.json()

            new_fm = {
                "doc_id": result["doc_id"],
                "title": title,
                "source": "obsidian",
                "tags": [],
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": current_hash,
                "qdrant_chunks": result.get("chunks", 0),
            }
            new_frontmatter = "---\n" + yaml.dump(new_fm, default_flow_style=False, allow_unicode=True) + "---\n"
            filepath.write_text(new_frontmatter + "\n" + body_stripped, encoding="utf-8")

            _log_to_backlog(action="obsidian_create", doc_id=result["doc_id"], title=title, content_hash_after=current_hash)
            created += 1

    logger.info("Sync complete: %d updated, %d created, %d unchanged", updated, created, unchanged)
    return {"updated": updated, "created": created, "unchanged": unchanged}


def _start_watcher(vault_path: str | None = None) -> None:
    """Watch the vault directory for changes using watchdog with debounced sync."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        logger.error("watchdog not installed. Run: pip install watchdog")
        return

    vault = Path(vault_path or config.OBSIDIAN_VAULT_PATH)
    vault.mkdir(parents=True, exist_ok=True)

    class _DebouncedHandler(FileSystemEventHandler):
        def __init__(self):
            self._last_event = 0.0
            self._debounce_seconds = 2.0

        def _should_process(self, event) -> bool:
            if event.is_directory:
                return False
            if not event.src_path.endswith(".md"):
                return False
            if ".obsidian" in event.src_path:
                return False
            now = time.time()
            if now - self._last_event < self._debounce_seconds:
                return False
            self._last_event = now
            return True

        def on_modified(self, event):
            if self._should_process(event):
                logger.info("Vault change detected: %s", event.src_path)
                try:
                    sync_vault_changes(str(vault))
                except Exception as e:
                    logger.error("Sync failed after vault change: %s", e)

        def on_created(self, event):
            if self._should_process(event):
                logger.info("New vault file: %s", event.src_path)
                try:
                    sync_vault_changes(str(vault))
                except Exception as e:
                    logger.error("Sync failed after vault change: %s", e)

    observer = Observer()
    observer.schedule(_DebouncedHandler(), str(vault), recursive=True)
    observer.start()
    logger.info("Watching vault at %s for changes...", vault)

    try:
        while True:
            time.sleep(config.OBSIDIAN_SYNC_INTERVAL)
            logger.debug("Periodic sync tick")
            try:
                sync_vault_changes(str(vault))
            except Exception as e:
                logger.error("Periodic sync failed: %s", e)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def main() -> None:
    """CLI entrypoint for obsidian_sync module."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Obsidian ↔ Qdrant sync bridge")
    parser.add_argument("--watch", action="store_true", help="Watch vault for changes (continuous mode)")
    parser.add_argument("--export", action="store_true", help="One-time export from Qdrant to vault")
    parser.add_argument("--sync", action="store_true", help="One-time sync from vault to Qdrant")
    parser.add_argument("--vault-path", type=str, default=None, help="Override vault path")
    args = parser.parse_args()

    vault = args.vault_path or config.OBSIDIAN_VAULT_PATH

    if args.export:
        result = export_vault(vault)
        print(f"Export: {result}")
    elif args.sync:
        result = sync_vault_changes(vault)
        print(f"Sync: {result}")
    elif args.watch:
        logger.info("Initial export before starting watcher...")
        try:
            export_vault(vault)
        except Exception as e:
            logger.warning("Initial export failed (API may not be ready): %s", e)
        _start_watcher(vault)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
