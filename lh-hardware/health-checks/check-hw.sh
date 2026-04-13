#!/usr/bin/env bash
set -euo pipefail
PASS=0; FAIL=0

check() {
  local label="$1"; shift
  if "$@" &>/dev/null; then
    echo "  ✅ $label"
    ((PASS++))
  else
    echo "  ❌ $label"
    ((FAIL++))
  fi
}

echo "=== LH Hardware Health Check ==="
echo "--- GPU ---"
lspci | grep -i vga || echo "  ⚠️  kein VGA-Gerät gefunden"
echo "--- RAM ---"
free -h
echo "--- Disk ---"
df -h .
echo "--- Ollama Modelle ---"
check "Ollama erreichbar" ollama list
echo "--- Docker ---"
check "Docker läuft" docker info
check "Compose Plugin" docker compose version
echo ""
[ $FAIL -eq 0 ] && echo "✅ Hardware-Check PASSED ($PASS checks)" \
                 || echo "❌ Hardware-Check FAILED ($FAIL/$((FAIL+PASS)) checks)"
exit $FAIL
