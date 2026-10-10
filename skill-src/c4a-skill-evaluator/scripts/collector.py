#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collector.py — Level 1 of the C4A evaluator.

Scan a folder that looks like a WeChat group dump, decide which files are C4
submissions, work out *who* submitted each one, group by author and detect
``_v2`` / ``_v3`` iterations.

Inherited from ``wechat_doc_mapper.py``:
  * ``inventory_folder``'s recursive walk + compound-extension handling +
    "an unreadable file is skipped, not fatal" behaviour (see ATTRIBUTION).
New in C4A:
  * the C4 relevance filter,
  * the four-step author-resolution chain (filename -> folder -> content -> ?),
  * version detection and history,
  * a memoised text-extraction pass shared with the completeness/quality stages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import textio

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# "C4" as its own token: _C4_, -C4-, "C4 ", "(C4)" ... but not "C4A" or "C40".
C4_TOKEN_RE = re.compile(r"(?:^|[^A-Za-z0-9])c4(?!a)(?:[^A-Za-z0-9]|$)", re.I)

# Step 1 of the author chain: "<Name>_C4_..." / "<Name> C4 ..."
AUTHOR_ASCII_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9]{1,29})\s*[_\-\s]+c4(?:[_\-\s]|$)", re.I)
AUTHOR_CJK_RE = re.compile(r"^\s*([一-鿿]{2,4})\s*[_\-\s]+c4(?:[_\-\s]|$)", re.I)

# Step 3 of the author chain: "作者：张三" / "Author: Li Ming"
AUTHOR_IN_TEXT_RE = re.compile(
    r"(?:作者|提交人|姓名|author|by)\s*[:：]\s*([A-Za-z][A-Za-z0-9_\-]{1,29}|[一-鿿]{2,4})",
    re.I)

# Version markers: _v2 / (v2) / 版本：v3 / "版本：2"
VERSION_RE = re.compile(r"(?:^|[_\-\s(（])v(?:er|ersion)?\.?\s*(\d{1,2})(?=[)\s_\-（]|$)", re.I)
VERSION_CN_RE = re.compile(r"(?:版本|version)\s*[:：]\s*v?(\d{1,2})", re.I)

# Folder names that must never be mistaken for an author.
GENERIC_DIRS = {
    "c4", "c4a", "materials", "samples", "sample", "cohort", "submissions",
    "submission", "wechat", "files", "docs", "documents", "output", "outputs",
    "downloads", "download", "desktop", "temp", "tmp", "src", "data", "群文件",
    "挑战", "资料", "未分类", "新文件夹", "归档", "backup",
}

# Non-C4 leftovers we explicitly report rather than silently drop.
IGNORE_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}


@dataclass
class FileInfo:
    """One file on disk, with everything downstream stages need."""

    path: Path
    rel: str
    stem: str
    ext: str
    size: int
    modified: str
    is_c4: bool = False
    author: str = "Unknown"
    author_method: str = ""
    version: int = 1
    version_sources: List[str] = field(default_factory=list)
    text: str = ""
    kind: str = "unknown"
    note: str = ""
    entries: List[str] = field(default_factory=list)

    @property
    def hay(self) -> str:
        """Lower-cased haystack used by the name-based detectors."""
        return (self.rel + " " + self.stem).lower()

    @property
    def is_archive(self) -> bool:
        return self.kind == "archive"

    def to_dict(self) -> dict:
        return {
            "path": self.rel, "ext": self.ext, "size_kb": round(self.size / 1024, 1),
            "modified": self.modified, "author": self.author,
            "author_method": self.author_method, "version": self.version,
            "kind": self.kind, "note": self.note,
        }


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def _title_case(name: str) -> str:
    """``songpengfei`` -> ``Songpengfei`` (leave already-cased names alone)."""
    if name.islower() or name.isupper():
        return name.capitalize()
    return name


def resolve_author_from_name(stem: str) -> Tuple[Optional[str], str]:
    """Chain step 1+2: pull the author out of the filename."""
    for pattern, tag in ((AUTHOR_ASCII_RE, "filename(ascii)"), (AUTHOR_CJK_RE, "filename(cjk)")):
        match = pattern.match(stem)
        if match:
            return _title_case(match.group(1)), tag
    return None, ""


def resolve_author_from_folder(path: Path, root: Path) -> Tuple[Optional[str], str]:
    """Chain step 3: fall back to the nearest meaningful parent directory."""
    try:
        parents = list(path.relative_to(root).parents)[:-1]  # drop "." itself
    except ValueError:
        parents = []
    for parent in parents:
        name = parent.name.strip()
        if not name or name.lower() in GENERIC_DIRS or len(name) > 30:
            continue
        if AUTHOR_ASCII_RE.match(name + "_C4_x"):
            return _title_case(name), "folder"
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]{1,29}", name):
            return _title_case(name), "folder"
        if re.fullmatch(r"[一-鿿]{2,4}", name):
            return name, "folder(cjk)"
    return None, ""


def resolve_author_from_text(text: str) -> Tuple[Optional[str], str]:
    """Chain step 4: last resort — look for an explicit author line."""
    if not text:
        return None, ""
    for match in AUTHOR_IN_TEXT_RE.finditer(text[:4000]):
        candidate = match.group(1).strip()
        if candidate.lower() in {"ai", "claude", "作者"} or len(candidate) < 2:
            continue
        return _title_case(candidate), "content"
    return None, ""


def detect_version(stem: str, text: str) -> Tuple[int, List[str]]:
    """Detect an iteration marker; returns ``(version, sources)``."""
    sources: List[str] = []
    version = 1
    match = VERSION_RE.search(stem)
    if match:
        version = max(version, int(match.group(1)))
        sources.append("filename:v%s" % match.group(1))
    else:
        match = VERSION_CN_RE.search(stem)
        if match:
            version = max(version, int(match.group(1)))
            sources.append("filename:版本%s" % match.group(1))
    if text:
        head = text[:1500]
        for match in VERSION_CN_RE.finditer(head):
            value = int(match.group(1))
            if version < value <= 20:
                version = value
                sources.append("content:版本%s" % value)
    return version, sources


def scan(folder: Path, read_content: bool = True, max_mb: float = 60.0) -> Tuple[List[FileInfo], List[FileInfo]]:
    """Walk ``folder`` and return ``(c4_files, non_c4_files)``.

    ``max_mb`` guards against pathological files: anything larger is recorded
    but never opened (name-only matching), mirroring wechat-doc-mapper's
    "[Large file]" shortcut.
    """
    c4_files: List[FileInfo] = []
    other_files: List[FileInfo] = []

    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.name.startswith(".") or path.name.lower() in IGNORE_NAMES:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue

        rel = path.relative_to(folder)
        ext = textio.split_compound_ext(path.name)
        is_c4 = bool(C4_TOKEN_RE.search(path.name)) or bool(C4_TOKEN_RE.search(str(rel.parent)))

        info = FileInfo(
            path=path, rel=str(rel).replace("\\", "/"), stem=path.stem, ext=ext,
            size=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
            is_c4=is_c4,
        )

        if is_c4 and read_content and stat.st_size <= max_mb * 1024 * 1024:
            extraction = textio.extract(path)
            info.text = extraction.text
            info.kind = extraction.kind
            info.note = extraction.note
            info.entries = extraction.entries
        elif stat.st_size > max_mb * 1024 * 1024:
            info.kind = "large"
            info.note = "skipped content analysis: %.0f MB > %.0f MB cap" % (
                stat.st_size / 1024 / 1024, max_mb)

        (c4_files if is_c4 else other_files).append(info)

    _resolve_authors(folder, c4_files)
    return c4_files, other_files


def _resolve_authors(folder: Path, files: Iterable[FileInfo]) -> None:
    """Run the four-step author chain in place."""
    unresolved: List[FileInfo] = []
    for info in files:
        author, method = resolve_author_from_name(info.stem)
        if not author:
            author, method = resolve_author_from_folder(info.path, folder)
        if author:
            info.author = author
            info.author_method = method
        else:
            unresolved.append(info)

    # Content fallback needs extracted text, so it runs as a second pass and
    # only for the files that the cheap steps could not resolve.
    for info in unresolved:
        if not info.text and info.path.stat().st_size <= 60 * 1024 * 1024:
            extraction = textio.extract(info.path)
            info.text = info.text or extraction.text
            info.kind = info.kind if info.kind != "unknown" else extraction.kind
            info.note = info.note or extraction.note
            info.entries = info.entries or extraction.entries
        author, method = resolve_author_from_text(info.text)
        info.author = author or "Unknown"
        info.author_method = method or "unresolved"

    for info in files:
        version, sources = detect_version(info.stem, info.text)
        info.version = version
        info.version_sources = sources


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

@dataclass
class Submission:
    """All C4 files attributed to one author."""

    author: str
    files: List[FileInfo] = field(default_factory=list)

    @property
    def version(self) -> int:
        return max((f.version for f in self.files), default=1)

    @property
    def version_history(self) -> Dict[int, List[str]]:
        history: Dict[int, List[str]] = {}
        for info in self.files:
            history.setdefault(info.version, []).append(info.rel)
        return dict(sorted(history.items()))

    @property
    def needs_manual_review(self) -> bool:
        return self.author == "Unknown" or any(
            f.author_method == "content" for f in self.files)


def group_by_author(files: Iterable[FileInfo]) -> Dict[str, Submission]:
    """Group C4 files by resolved author, preserving a stable order."""
    groups: Dict[str, Submission] = {}
    for info in files:
        groups.setdefault(info.author, Submission(author=info.author)).files.append(info)
    for submission in groups.values():
        submission.files.sort(key=lambda f: f.rel)
    return dict(sorted(groups.items(), key=lambda kv: kv[0].lower()))
