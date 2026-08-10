#!/usr/bin/env python3
"""Walk git history from the first commit and derive x.y.z.

Rules (x is fixed at 0):
  * y, z start at 0
  * a commit whose subject starts with "feat"  -> y += 1, z = 0
  * any other commit                          -> z += 1
  * log one line every time y or z changes:
        <commit-date>  <sha8>  <subject-first-50-chars>  <x>.<y>.<z>
  * after the table, write the final version into project ``pyproject.toml``

Run from any directory inside the target git repository:

    python scripts/version-calc.py
"""

from __future__ import annotations

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


def update_pyproject_version(version: str) -> Path:
    """Set ``[project].version`` in the repo-root pyproject.toml."""
    path = repo_root() / "pyproject.toml"
    if not path.is_file():
        raise FileNotFoundError(f"pyproject.toml not found at {path}")

    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(?m)^version\s*=\s*"[^"]*"',
        f'version = "{version}"',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(
            f'expected exactly one top-level version = "..." in {path}, found {count}'
        )
    if updated == text:
        return path
    path.write_text(updated, encoding="utf-8")
    return path


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

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
        LOGGER.warning("no commits; keeping version %s", version)

    path = update_pyproject_version(version)
    try:
        display_path = path.relative_to(repo_root()).as_posix()
    except ValueError:
        display_path = path.name
    # Match history row layout: <date>  <sha8>  <subject-50>  <version>
    LOGGER.info(
        "%s  %s  %s  %s",
        "-------------------------",
        "--------",
        f"set {display_path}"[:50],
        version,
    )
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
