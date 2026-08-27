#!/usr/bin/env python3
"""Derive the project version from Git history and refresh the uv lockfile.

Rules (major is fixed at 0):

* a commit whose subject starts with ``feat`` increments minor and resets patch;
* every other commit increments patch.

Without ``--apply`` the script only prints the calculated version. With
``--apply`` it updates ``[project].version`` in ``pyproject.toml`` and runs
``uv lock`` so the project package entry in ``uv.lock`` stays in sync.

Run from any directory:

    python scripts/version-calc.py
    python scripts/version-calc.py --apply
    python scripts/version-calc.py --quiet --apply
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_FILE = REPO_ROOT / "pyproject.toml"
UV_LOCK_FILE = REPO_ROOT / "uv.lock"

PROJECT_SECTION_RE = re.compile(rb"(?ms)^\[project\][ \t]*\r?\n(?P<body>.*?)(?=^\[|\Z)")
PROJECT_VERSION_RE = re.compile(
    rb"(?m)^version[ \t]*=[ \t]*(?P<quote>[\"'])(?P<version>[^\"']*)(?P=quote)"
)


def run_git(*args: str) -> str:
    """Run Git at the repository root and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def is_feature(subject: str) -> bool:
    """Return whether a commit subject starts a feature release increment."""
    return subject.lstrip().lower().startswith("feat")


def calculate_version_from_subjects(subjects: Iterable[str]) -> str:
    """Return the release version derived from commit subjects in order."""
    minor = 0
    patch = 0
    saw_commit = False

    for subject in subjects:
        saw_commit = True
        if is_feature(subject):
            minor += 1
            patch = 0
        else:
            patch += 1

    if not saw_commit:
        raise RuntimeError("no commits found; cannot derive version")

    return f"0.{minor}.{patch}"


def iter_commits() -> Iterator[tuple[str, str, str]]:
    """Yield full hash, ISO date, and subject from oldest to newest."""
    output = run_git("log", "--reverse", "--pretty=format:%H%x1f%aI%x1f%s")
    for line in output.splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) == 3:
            yield parts[0], parts[1], parts[2]


def calculate_version(*, print_history: bool = True) -> str:
    """Walk Git history and return the project version."""
    commits = tuple(iter_commits())
    version = calculate_version_from_subjects(subject for _, _, subject in commits)

    if print_history:
        minor = 0
        patch = 0
        for full_hash, date, subject in commits:
            if is_feature(subject):
                minor += 1
                patch = 0
            else:
                patch += 1
            headline = subject.split("\n", 1)[0][:50]
            print(f"{date}  {full_hash[:8]}  {headline}  0.{minor}.{patch}")

    return version


def prepare_pyproject_replacement(path: Path, version: str) -> tuple[str, bytes]:
    """Prepare an exact replacement for ``[project].version``."""
    raw = path.read_bytes()
    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"could not read project metadata from {path}") from exc

    project = document.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("version"), str):
        raise RuntimeError(f"could not read project version from {path}")

    section = PROJECT_SECTION_RE.search(raw)
    if section is None:
        raise RuntimeError(f"could not find [project] in {path}")

    body = section.group("body")
    matches = tuple(PROJECT_VERSION_RE.finditer(body))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one [project].version in {path}")

    match = matches[0]
    previous = match.group("version").decode("utf-8")
    if project["version"] != previous:
        raise RuntimeError(f"project version in {path} is ambiguous")

    version_bytes = version.encode("utf-8")
    start = section.start("body") + match.start("version")
    end = section.start("body") + match.end("version")
    updated = raw[:start] + version_bytes + raw[end:]
    return previous, updated


def run_uv_lock() -> None:
    """Refresh or create the project's uv lockfile."""
    subprocess.run(["uv", "lock"], cwd=REPO_ROOT, check=True)
    if not UV_LOCK_FILE.is_file():
        raise RuntimeError(f"uv lock did not create {UV_LOCK_FILE}")


def apply_version(version: str) -> None:
    """Update pyproject.toml and refresh uv.lock as one operation."""
    previous_pyproject = PYPROJECT_FILE.read_bytes()
    previous_lock = UV_LOCK_FILE.read_bytes() if UV_LOCK_FILE.exists() else None
    previous, updated = prepare_pyproject_replacement(PYPROJECT_FILE, version)

    try:
        if updated == previous_pyproject:
            print(f"unchanged pyproject.toml: project version = {version}")
        else:
            PYPROJECT_FILE.write_bytes(updated)
            print(f"updated pyproject.toml: project version {previous} -> {version}")
        run_uv_lock()
    except Exception:
        # Keep metadata consistent if uv cannot resolve the updated project.
        PYPROJECT_FILE.write_bytes(previous_pyproject)
        if previous_lock is None:
            if UV_LOCK_FILE.exists():
                UV_LOCK_FILE.unlink()
        else:
            UV_LOCK_FILE.write_bytes(previous_lock)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Derive the project version from Git history")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="update pyproject.toml and refresh uv.lock",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="do not print per-commit history",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    version = calculate_version(print_history=not args.quiet)
    if not args.quiet:
        print()
    print(f"version: {version}")

    if args.apply:
        apply_version(version)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"command failed: {exc.stderr.strip() if exc.stderr else exc}\n")
        sys.exit(1)
    except (OSError, RuntimeError, ValueError, re.error, tomllib.TOMLDecodeError) as exc:
        sys.stderr.write(f"{exc}\n")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
