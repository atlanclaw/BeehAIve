# BASE-L0-00 — L0 Architektur-Anker

> **Dieses Dokument ist read-only Referenz.** Es dient als Anker und Abgrenzungsdefinition für alle BASE-L0-xx Issues.

## Was ist L0?

L0 ist die **lokale Container- und Runtime-Plattform**. Sie entkoppelt die physische Hardware (LH) von den fachlichen Schichten L1–L6. L0 setzt technisch durch, was LH advisory definiert.

```
LH  →  definiert physische Maximalwerte (advisory)
L0  →  setzt Container-Policies durch (enforcement)
L1+ →  fachliche Schichten, nutzen L0 als Plattform
```

## Schichten-Abgrenzung

| Was | Schicht | Beispiel |
| --- | --- | --- |
| Physische RAM-/CPU-/SSD-Grenzen | **LH** | `hardware-profile.yaml` |
| Advisory Burst/Idle-Maxima | **LH** | `runtime_budget_advisory` |
| Docker Engine, Compose, Netzwerke | **L0** | `docker-compose.yml` |
| cgroup v2, Container-RAM-Limits | **L0** | `resource_manager.py` |
| Stage-Budget-Policies | **L0** | `pipeline-stages.yaml` |
| Startup-Reihenfolge, Health-Waits | **L0** | `start.sh` |
| Storage Monitor (inotify) | **L0** | `storage_monitor.py` |
| Qdrant als Datendienst | **L1** | ab hier fachlich |

## Hard Constraints

```
✅  L0 enthält KEINE Business-Logik — nur Runtime-Control
✅  Resource Manager ist privilegierter Sidecar — kein Teil von L3
✅  L3 Dispatcher triggert Stage-Wechsel — L0 setzt sie durch
✅  L6 triggert nur Requests — kein direkter Stage-Control durch L6
✅  Alle Container-Limits lesen advisory Werte aus LH hardware-profile.yaml
✅  Resource Manager läuft nur auf pkb-core Netzwerk — kein externer Port
```

## Verzeichnis-Scope L0

```
BeehAIve/
├── docker-compose.yml              # L0: Netzwerke, Volumes, Services
├── config/
│   └── pipeline-stages.yaml         # L0: Burst/Idle-Budgets pro Stage
├── l0-platform/
│   ├── resource_manager.py          # L0: cgroup/docker update Sidecar
│   └── storage_monitor.py           # L0: inotify Storage Monitor
├── scripts/
│   ├── start.sh                     # L0: Pflicht-Startreihenfolge
│   └── first-run-check.py           # L0: Mindest-Speicher-Prüfung
```
