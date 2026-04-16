#!/usr/bin/env bash
set -euo pipefail

if [ ! -S /var/run/docker.sock ]; then
  echo "FEHLER: Docker Socket nicht gefunden (/var/run/docker.sock)"
  exit 1
fi

if [ ! -f /sys/fs/cgroup/cgroup.controllers ]; then
  echo "WARNUNG: cgroup v2 nicht verfügbar, nur docker update wird genutzt"
fi

exec python3 -m uvicorn pkb.resource_manager_api:app \
  --host 127.0.0.1 --port 8090 --workers 1
