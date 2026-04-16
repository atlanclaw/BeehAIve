"""Tests für pkb.resource_manager."""
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Konfig-Datei aus dem Repo für Import bereitstellen
REPO_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault(
    "RESOURCE_BUDGETS_CONFIG",
    str(REPO_ROOT / "config" / "resource-budgets.yaml"),
)

# Import erst NACH ENV-Setup
sys.path.insert(0, str(REPO_ROOT))
from pkb import resource_manager as rm  # noqa: E402


# ─── _parse_memory ──────────────────────────────────────────────────

def test_parse_memory_megabytes() -> None:
    assert rm._parse_memory("16000m") == 16000 * 1024 * 1024


def test_parse_memory_gigabytes() -> None:
    assert rm._parse_memory("16g") == 16 * 1024 * 1024 * 1024


def test_parse_memory_raw_bytes() -> None:
    assert rm._parse_memory("1048576") == 1048576


def test_parse_memory_whitespace_and_case() -> None:
    assert rm._parse_memory(" 512M ") == 512 * 1024 * 1024
    assert rm._parse_memory("2G") == 2 * 1024 * 1024 * 1024


# ─── docker update → cgroup v2 Fallback ─────────────────────────────

def _fake_completed(returncode: int, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout="cid123\n", stderr=stderr
    )


def test_docker_update_fails_triggers_cgroup_fallback(tmp_path: Path) -> None:
    """docker update schlägt fehl → cgroup v2 Dateien werden beschrieben."""
    # Fake cgroup-Scope anlegen
    scope = tmp_path / "system.slice" / "docker-cid123.scope"
    scope.mkdir(parents=True)
    (scope / "memory.max").write_text("max")
    (scope / "memory.swap.max").write_text("max")
    (scope / "cpu.max").write_text("max 100000")

    # subprocess.run: erster Call = docker update (fail), zweiter = docker inspect (OK)
    calls = {"n": 0}

    def fake_run(cmd, *args, **kwargs):
        calls["n"] += 1
        if cmd[0] == "docker" and cmd[1] == "update":
            return _fake_completed(1, stderr="oci runtime error")
        if cmd[0] == "docker" and cmd[1] == "inspect":
            return _fake_completed(0)
        raise AssertionError(f"unerwarteter Call: {cmd}")

    with mock.patch.object(rm, "CGROUP_BASE", tmp_path), \
         mock.patch.object(rm.subprocess, "run", side_effect=fake_run):
        ok = rm._update_container_resources("pkb-beeai", 512 * 1024 * 1024, 0.5)

    assert ok is True, "Fallback muss erfolgreich melden"
    # cgroup-Dateien tragen neue Werte
    assert (scope / "memory.max").read_text() == str(512 * 1024 * 1024)
    assert (scope / "memory.swap.max").read_text() == "0"
    assert (scope / "cpu.max").read_text() == f"{int(0.5 * 100_000)} 100000"
    # docker update + docker inspect = 2 Calls
    assert calls["n"] == 2


def test_docker_update_success_no_fallback() -> None:
    """docker update OK → kein cgroup-Fallback nötig."""
    def fake_run(cmd, *args, **kwargs):
        assert cmd[:2] == ["docker", "update"]
        return _fake_completed(0)

    with mock.patch.object(rm.subprocess, "run", side_effect=fake_run):
        ok = rm._update_container_resources("pkb-qdrant", 256 * 1024 * 1024, 0.1)

    assert ok is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
