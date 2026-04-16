#!/usr/bin/env bash
set -euo pipefail
BASE="l1-data/vault/pkb"
mkdir -p \
  "$BASE/00-admin/templates" \
  "$BASE/10-projects" \
  "$BASE/20-areas" \
  "$BASE/30-references" \
  "$BASE/40-archive" \
  "$BASE/50-inbox/web-captures" \
  "$BASE/50-inbox/email-imports" \
  "$BASE/50-inbox/telegram-inbox" \
  "$BASE/50-inbox/pdf-queue" \
  "$BASE/90-system/ingestion-logs" \
  "$BASE/90-system/qdrant-backups" \
  "$BASE/90-system/embedding-cache" \
  "$BASE/90-system/wal" \
  "l1-data/obsidian-config/.obsidian" \
  "l1-data/qdrant"
echo "✅ Verzeichnisse angelegt"
