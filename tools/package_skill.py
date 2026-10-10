#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""package_skill.py — pack a skill directory into a ``.skill`` archive.

A ``.skill`` file is a plain ZIP whose top level is the skill directory
(cf. C4 CHALLENGE.md §七). This script exists because Git Bash on Windows
ships without the ``zip`` binary, and because packaging should be one
reproducible command rather than a hand-typed zip invocation.

Usage:
    python tools/package_skill.py <SKILL_DIR> [--out FILE.skill]

Example:
    python tools/package_skill.py skill-src/c4a-skill-evaluator \
        --out Songpengfei_C4A_skill-evaluator.skill
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

EXCLUDE_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".DS_Store"}


def should_skip(path: Path) -> bool:
    if any(part in EXCLUDE_DIRS for part in path.parts):
        return True
    return path.name in EXCLUDE_SUFFIXES or path.suffix in EXCLUDE_SUFFIXES


def build(skill_dir: Path, out_file: Path) -> int:
    if not (skill_dir / "SKILL.md").is_file():
        sys.stderr.write("ERROR: %s has no SKILL.md — not a valid skill directory.\n" % skill_dir)
        return 2

    out_file.parent.mkdir(parents=True, exist_ok=True)
    members = []
    with zipfile.ZipFile(out_file, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_dir() or should_skip(path.relative_to(skill_dir)):
                continue
            arcname = (Path(skill_dir.name) / path.relative_to(skill_dir)).as_posix()
            zf.write(path, arcname)
            members.append(arcname)

    print("packed %d files -> %s (%.1f KB)" % (
        len(members), out_file, out_file.stat().st_size / 1024))
    for name in members:
        print("   %s" % name)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Pack a skill directory into a .skill archive")
    parser.add_argument("skill_dir", help="directory containing SKILL.md")
    parser.add_argument("--out", default=None, help="output .skill path")
    args = parser.parse_args(argv)

    skill_dir = Path(args.skill_dir).expanduser().resolve()
    if not skill_dir.is_dir():
        sys.stderr.write("ERROR: %s is not a directory.\n" % skill_dir)
        return 2
    out_file = Path(args.out) if args.out else skill_dir.with_suffix(".skill")
    return build(skill_dir, out_file)


if __name__ == "__main__":
    raise SystemExit(main())
