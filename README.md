# BeehAIve 🐝

> Personal Knowledge Base — neue BASE-Architektur (LH → L0 → L1 → L2)

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)](https://docker.com)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20DB-red)](https://qdrant.tech)
[![Langfuse](https://img.shields.io/badge/Langfuse-Observability-purple)](https://langfuse.com)

## Überblick

BeehAIve ist die saubere Neuimplementierung des PKB (Personal Knowledge Base) Systems
mit einer klar geschichteten BASE-Architektur. Dieses Repo wurde aus `atlanTiKern`
(Commits ATL-73 bis ATL-100) entkoppelt und enthält ausschließlich die neue Schichtstruktur.

## Layer-Architektur

```
LH  Hardware-Layer    — Hardware-Profil, Modell-Limits, RAM-Budget
L0  Platform-Layer    — Docker Compose, Startup-Sequenz, Resource Manager
L1  Data-Layer        — Qdrant Collections, WAL, Vault-Struktur, Obsidian-Config
L2  Ingestion-Layer   — Parser-Pipeline, Chunking, Qdrant-Writer, TOON, Health-Check
```

### Services (docker-compose)

| Service | Layer | Port | Beschreibung |
|---|---|---|---|
| `qdrant` | L1 | 1081 | Vektordatenbank (Container: 1337) |
| `langfuse-web` | L4 | 1084 | Observability & Tracing (Container: 7777) |
| `pkb-resource-manager` | L0 | — | RAM/CPU-Limits via cgroup v2 |
| `pkb-ingestion` | L2 | 3692 | Ingestion-Pipeline (Parser → Chunker → Writer) |
| `pkb-beeai` | L3 | 4713 | BeeAI Agent |
| `l3-dispatcher` | L3 | 3693 | Task-Dispatcher |
| `pkb-gateway` | L6 | 7777 | Telegram-Gateway (Engels-Tor) |
| `pkb-auditor` | L6 | — | WAL-Auditor (read-only) |

## Schnellstart

```bash
# 1. Repo klonen
git clone https://github.com/atlanclaw/BeehAIve.git
cd BeehAIve

# 2. Umgebungsvariablen konfigurieren
cp .env.example .env
# → .env anpassen: Telegram-Token, Langfuse-Keys, etc.

# 3. Stack starten
docker compose up -d

# 4. Health-Check
curl http://localhost:1081/healthz    # Qdrant
curl http://localhost:3692/health     # Ingestion
```

## Verzeichnisstruktur

```
BeehAIve/
├── lh-hardware/          # LH: Hardware-Profil & Modell-Limits
│   ├── model-profiles/
│   └── health-checks/
├── l0-platform/          # L0: Docker Platform & Resource Management
├── l1-data/              # L1: Qdrant-Schema, Vault, WAL, Obsidian-Config
│   ├── qdrant/
│   ├── vault/
│   └── obsidian-config/
├── l2-ingestion/         # L2: Ingestion-Service (Python)
│   ├── main.py
│   ├── pipeline.py
│   ├── health.py
│   ├── otel_setup.py
│   └── requirements.txt
├── config/               # Shared Config-Files
├── scripts/              # Deployment & Utility Scripts
├── tests/                # Test-Suite
├── docker-compose.yml    # Haupt-Stack
├── docker-compose.gpu.yml
└── .env.example
```

## Voraussetzungen

- Docker Desktop (WSL2) oder Docker Engine
- AMD AI350 / 32 GB RAM (empfohlen, siehe `lh-hardware/model-profiles/`)
- Python 3.11+ (für lokale Entwicklung)

## Herkunft

Dieses Repo wurde aus [`atlanclaw/atlanTiKern`](https://github.com/atlanclaw/atlanTiKern)
entkoppelt. Die alte v1-Architektur (L0–L3 Monolith mit Paperclip/TOON/NemoClaw) verbleibt
im Ursprungs-Repo als Archiv.

## Lizenz

Siehe [LICENSE](LICENSE).
