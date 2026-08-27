#!/usr/bin/env python3
"""Walk git history from the first commit and derive x.y.z.

Rules (x is fixed at 0):
  * y, z start at 0
  * a commit whose subject starts with "feat"  -> y += 1, z = 0
  * any other commit                          -> z += 1
  * log one line every time y or z changes:
        <commit-date>  <sha8>  <subject-first-50-chars>  <x>.<y>.<z>
  * ``--apply`` writes the final version into ``pyproject.toml`` and refreshes
    ``uv.lock``

Run from any directory inside the target git repository:

    python scripts/version-calc.py
    python scripts/version-calc.py --apply
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

LOGGER = logging.getLogger("version-calc")


def run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        capture_output=True,
        check=True,
        text=True,
    )
    return proc.stdout


def is_feature(subject: str) -> bool:
    return subject.lstrip().lower().startswith("feat")


def iter_commits() -> Iterator[tuple[str, str, str]]:
    """Yield (full_hash, iso_date, subject) from oldest to newest."""
    log = run_git(
        "log",
        "--reverse",
        "--pretty=format:%H%x1f%aI%x1f%s",
    )
    for line in log.splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) != 3:
            continue
        full_hash, date, subject = parts
        yield full_hash, date, subject


def repo_root() -> Path:
    return Path(run_git("rev-parse", "--show-toplevel").strip())


def update_pyproject_version(version: str) -> tuple[Path, bool]:
    """Set ``[project].version`` and return its path and whether it changed."""
    path = repo_root() / "pyproject.toml"
    if not path.is_file():
        raise FileNotFoundError(f"pyproject.toml not found at {path}")

    text = path.read_bytes().decode("utf-8")
    updated, count = re.subn(
        r'(?m)^version\s*=\s*"[^"]*"\r?$',
        f'version = "{version}"',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(
            f'expected exactly one top-level version = "..." in {path}, found {count}'
        )
    if updated == text and "\r\n" not in text:
        return path, False
    path.write_text(updated, encoding="utf-8", newline="\n")
    return path, True


def refresh_uv_lockfile(root: Path) -> None:
    """Update the lockfile after project metadata changes."""
    subprocess.run(["uv", "lock"], cwd=root, check=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate the project version from Git history.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the calculated version and refresh uv.lock",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)

    x = 0
    y = 0
    z = 0
    saw_commit = False

    for full_hash, date, subject in iter_commits():
        saw_commit = True
        short = full_hash[:8]
        if is_feature(subject):
            y += 1
            z = 0
        else:
            z += 1
        headline = subject.split("\n", 1)[0][:50]
        LOGGER.info("%s  %s  %s  %s.%s.%s", date, short, headline, x, y, z)

    version = f"{x}.{y}.{z}"
    if not saw_commit:
        LOGGER.warning("no commits; calculated version %s", version)

    if not args.apply:
        LOGGER.info("calculated version %s; rerun with --apply to update project files", version)
        return 0

    root = repo_root()
    path, changed = update_pyproject_version(version)
    display_path = path.relative_to(root).as_posix()
    if changed:
        LOGGER.info("set %s to %s", display_path, version)
    else:
        LOGGER.info("%s already matches %s", display_path, version)
    refresh_uv_lockfile(root)
    LOGGER.info("refreshed uv.lock")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        LOGGER.error("git failed: %s", (exc.stderr or "").strip() or exc)
        sys.exit(1)
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        LOGGER.error("%s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
