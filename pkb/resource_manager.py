"""
L0 Resource Manager.
Stellt apply_idle_all() und apply_burst() bereit.
Die Stage-Gate-Logik (wann welche Stage aktiv ist) liegt in L3.
"""
import logging
import os
import subprocess
from pathlib import Path

import yaml

logger = logging.getLogger("pkb.resource_manager")

BUDGETS_CONFIG = os.getenv(
    "RESOURCE_BUDGETS_CONFIG", "/app/config/resource-budgets.yaml"
)
CGROUP_BASE = Path("/sys/fs/cgroup")


def _load_config() -> dict:
    with open(BUDGETS_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_memory(value: str) -> int:
    """Konvertiert '16000m' / '16g' → Bytes."""
    v = value.strip().lower()
    if v.endswith("m"):
        return int(v[:-1]) * 1024 * 1024
    if v.endswith("g"):
        return int(v[:-1]) * 1024 * 1024 * 1024
    return int(v)


def _get_container_id(name: str) -> str | None:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.Id}}", name],
        capture_output=True, text=True, timeout=5
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _update_container_resources(
    container_name: str,
    memory_bytes: int,
    cpu_cores: float,
) -> bool:
    cpu_period = 100_000
    cpu_quota = int(cpu_cores * cpu_period)

    result = subprocess.run(
        [
            "docker", "update",
            f"--memory={memory_bytes}",
            f"--memory-swap={memory_bytes}",
            f"--cpu-period={cpu_period}",
            f"--cpu-quota={cpu_quota}",
            container_name,
        ],
        capture_output=True, text=True, timeout=10
    )

    if result.returncode == 0:
        logger.debug(
            "docker update OK: %s → %dMB, %.1f cores",
            container_name, memory_bytes // (1024 ** 2), cpu_cores
        )
        return True

    # Fallback: cgroup v2
    logger.warning(
        "docker update fehlgeschlagen für %s, versuche cgroup-Fallback: %s",
        container_name, result.stderr.strip()
    )
    container_id = _get_container_id(container_name)
    if not container_id:
        return False

    scope = CGROUP_BASE / "system.slice" / f"docker-{container_id}.scope"
    if not scope.exists():
        return False

    try:
        (scope / "memory.max").write_text(str(memory_bytes))
        (scope / "memory.swap.max").write_text("0")
        (scope / "cpu.max").write_text(f"{cpu_quota} {cpu_period}")
        logger.debug("cgroup v2 Fallback OK: %s", container_name)
        return True
    except PermissionError:
        logger.error(
            "cgroup v2 Fallback: keine Berechtigung für %s "
            "(Resource Manager braucht privileged oder CAP_SYS_ADMIN)",
            container_name
        )
        return False


class ResourceManager:
    """
    L0 Resource Manager — stellt Idle + Burst Primitives bereit.
    Stage-Gate Context-Manager (stage()) wird in L3/BeeAI implementiert.
    """

    def __init__(self) -> None:
        self._config = _load_config()
        self._idle = self._config["idle_limits"]

    def apply_idle_all(self) -> None:
        """Setzt alle Dienste auf Idle-Budget. Wird von L3 vor jeder Stage aufgerufen."""
        for container, budgets in self._idle.items():
            ram_val = next(
                (v for k, v in budgets.items() if k.startswith("idle_ram_")),
                "256m"
            )
            cpu_val = next(
                (v for k, v in budgets.items() if k.startswith("idle_cpu_")),
                "0.1"
            )
            _update_container_resources(
                container,
                _parse_memory(ram_val),
                float(cpu_val),
            )

    def apply_burst(self, container_name: str, ram: str, cpu: float) -> bool:
        """Setzt einen Dienst auf Burst-Budget. Wird von L3 Stage-Gate aufgerufen."""
        logger.info("BURST: %s → RAM=%s CPU=%.1f", container_name, ram, cpu)
        return _update_container_resources(
            container_name,
            _parse_memory(ram),
            cpu,
        )


# Singleton — wird von L3 importiert
# Lazy: nur instanziieren wenn BUDGETS_CONFIG existiert (sonst ImportError in CI/Tests).
try:
    resource_manager = ResourceManager()
except FileNotFoundError:  # pragma: no cover
    logger.warning(
        "resource-budgets.yaml nicht gefunden (%s) — Singleton nicht initialisiert",
        BUDGETS_CONFIG,
    )
    resource_manager = None  # type: ignore[assignment]
