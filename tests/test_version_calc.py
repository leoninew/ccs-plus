"""Tests for the standalone version calculation script."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "version-calc.py"
SPEC = importlib.util.spec_from_file_location("version_calc", SCRIPT_PATH)
assert SPEC and SPEC.loader
version_calc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(version_calc)


def write_pyproject(path: Path, version: str) -> None:
    path.write_text(f'[project]\nname = "ccs-plus"\nversion = "{version}"\n', encoding="utf-8")


def test_main_reports_version_without_changing_project_files(monkeypatch, tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    write_pyproject(pyproject, "0.1.0")
    monkeypatch.setattr(version_calc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        version_calc,
        "iter_commits",
        lambda: iter([("a" * 40, "2026-08-27T00:00:00+00:00", "feat: add launcher")]),
    )

    assert version_calc.main([]) == 0
    assert 'version = "0.1.0"' in pyproject.read_text(encoding="utf-8")


def test_apply_updates_project_version_and_lockfile(monkeypatch, tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_bytes(b'[project]\r\nname = "ccs-plus"\r\nversion = "0.0.0"\r\n')
    monkeypatch.setattr(version_calc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        version_calc,
        "iter_commits",
        lambda: iter([("a" * 40, "2026-08-27T00:00:00+00:00", "feat: add launcher")]),
    )
    calls: list[tuple[list[str], Path, bool]] = []

    def fake_run(command: list[str], *, cwd: Path, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append((command, cwd, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(version_calc.subprocess, "run", fake_run)

    assert version_calc.main(["--apply"]) == 0
    assert 'version = "0.1.0"' in pyproject.read_text(encoding="utf-8")
    assert b'version = "0.1.0"\n' in pyproject.read_bytes()
    assert calls == [(["uv", "lock"], tmp_path, True)]


def test_apply_refreshes_lockfile_when_version_is_current(monkeypatch, tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    write_pyproject(pyproject, "0.1.0")
    monkeypatch.setattr(version_calc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        version_calc,
        "iter_commits",
        lambda: iter([("a" * 40, "2026-08-27T00:00:00+00:00", "feat: add launcher")]),
    )
    calls: list[tuple[list[str], Path, bool]] = []

    def fake_run(command: list[str], *, cwd: Path, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append((command, cwd, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(version_calc.subprocess, "run", fake_run)

    assert version_calc.main(["--apply"]) == 0
    assert calls == [(["uv", "lock"], tmp_path, True)]
