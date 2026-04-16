#!/usr/bin/env bash
set -euo pipefail

wait_healthy() {
  local svc="$1"
  echo "  Warte auf $svc (healthy)..."
  until docker compose ps "$svc" --format json 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('Health','')=='healthy' else 1)" 2>/dev/null; do
    sleep 3
  done
  echo "  ✅ $svc healthy"
}

echo "=== PKB Startup ==="

echo "[Phase 1] Qdrant + Langfuse starten..."
docker compose up -d qdrant langfuse-web
wait_healthy qdrant
wait_healthy langfuse-web
echo "✅ Phase 1 OK"

echo "[Phase 2] Qdrant Collections anlegen..."
python3 l1-data/qdrant/setup-collections.py
echo "✅ Phase 2 OK"

echo "[Phase 3] Core Services starten..."
docker compose up -d pkb-ingestion pkb-beeai l3-dispatcher pkb-auditor
wait_healthy pkb-beeai
wait_healthy l3-dispatcher
echo "✅ Phase 3 OK"

echo "[Phase 4] Gateway starten..."
docker compose up -d pkb-gateway
wait_healthy pkb-gateway
echo "✅ Phase 4 OK"

if [[ "${1:-}" == "--full" ]]; then
  echo "[Phase 5] Optional Services starten (--full)..."
  docker compose --profile full up -d
  echo "✅ Phase 5 OK"
fi

echo ""
echo "✅ PKB Stack vollständig gestartet"
