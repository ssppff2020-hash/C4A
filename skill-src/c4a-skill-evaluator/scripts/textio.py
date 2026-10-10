#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""textio.py — format-aware text extraction for C4A submission files.

Design goals
------------
* **Zero hard dependencies.** PDF / DOCX / archive support degrades gracefully:
  if ``pypdf`` is missing we still return the filename, we just cannot quote
  the file's contents.
* **Never raise on a single bad file.** Every extractor returns an
  :class:`Extraction` carrying a human-readable ``note``; the caller records
  that note as evidence instead of crashing the whole run.
* **Bounded work.** Each file contributes at most ``MAX_CHARS`` characters so a
  multi-megabyte log cannot blow up runtime or memory.

Inherited from wechat-doc-mapper: the compound-extension handling
(``.tar.gz``) and the "large file -> name only" shortcut.
"""

from __future__ import annotations

import re
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

MAX_CHARS = 200_000        # per-file text cap
MAX_READ_BYTES = 4 << 20   # never read more than 4 MiB off disk
MAX_ARCHIVE_ENTRIES = 500  # archive member listing cap
MAX_ARCHIVE_TEXT = 120_000 # total text harvested from one archive

# Encoding chain: UTF-8 first (the platform standard), then the GB-family used
# by Chinese Windows tooling, then a never-fails last resort.
ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "latin-1")

TEXT_EXTS = {
    ".md", ".markdown", ".txt", ".py", ".json", ".yaml", ".yml", ".csv",
    ".tsv", ".log", ".html", ".css", ".js", ".ts", ".sh", ".bat", ".ps1",
    ".tex", ".rst", ".toml", ".ini", ".cfg", ".xml",
}
ARCHIVE_EXTS = {".skill", ".zip"}
TAR_EXTS = {".tar", ".gz", ".tgz", ".tar.gz", ".tar.bz2", ".tar.xz"}
OOXML_EXTS = {".docx", ".pptx", ".xlsx"}
LEGACY_OFFICE_EXTS = {".doc", ".ppt", ".xls"}
PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"}
MEDIA_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".mp3", ".wav", ".m4a"}


def split_compound_ext(name: str) -> str:
    """Return the effective extension, treating ``.tar.gz`` as one unit."""
    low = name.lower()
    for compound in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if low.endswith(compound):
            return compound
    return Path(low).suffix


@dataclass
class Extraction:
    """Result of trying to read one file."""

    text: str = ""
    kind: str = "unknown"   # text|docx|pdf|archive|image|media|legacy|binary|missing
    note: str = ""
    entries: List[str] = field(default_factory=list)
    syntax_error: str = ""  # populated only by the .py syntax probe

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------

def decode_bytes(data: bytes, limit: int = MAX_CHARS) -> "tuple[str, str]":
    """Decode ``data`` trying the encoding chain. Returns ``(text, note)``."""
    for enc in ENCODINGS:
        try:
            return data.decode(enc)[:limit], "decoded as %s" % enc
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")[:limit], "decoded with U+FFFD replacement"


def read_text_file(path: Path) -> Extraction:
    """Read a plain-text-ish file with bounded size and encoding fallback."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(MAX_READ_BYTES)
    except OSError as exc:
        return Extraction(kind="missing", note="unreadable: %s" % exc)
    text, note = decode_bytes(data)
    return Extraction(text=text, kind="text", note=note)


# ---------------------------------------------------------------------------
# OOXML (.docx / .pptx / .xlsx) — pure stdlib via zipfile + tag stripping
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")


def _strip_xml(xml: str) -> str:
    """Turn OOXML runs into plain text, keeping paragraph boundaries."""
    xml = re.sub(r"</w:p>|</a:p>|</w:tr>|</a:tr>", "\n", xml)
    xml = re.sub(r"<w:tab[^>]*/>|<a:tab[^>]*/>", "\t", xml)
    xml = _TAG_RE.sub("", xml)
    xml = (xml.replace("&amp;", "&").replace("&lt;", "<")
              .replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'"))
    return _WS_RE.sub(" ", xml)


def _read_ooxml(path: Path) -> Extraction:
    members: List[str] = []
    chunks: List[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                members.append(info.filename)
            wanted = []
            suffix = path.suffix.lower()
            if suffix == ".docx":
                wanted = ["word/document.xml"] + [
                    m for m in members if re.match(r"word/(header|footer)\d*\.xml$", m)]
            elif suffix == ".pptx":
                wanted = sorted(m for m in members if re.match(r"ppt/slides/slide\d+\.xml$", m))
            elif suffix == ".xlsx":
                wanted = ["xl/sharedStrings.xml"]
            for name in wanted[:80]:
                try:
                    raw = zf.read(name)
                except (KeyError, RuntimeError):
                    continue
                text, _ = decode_bytes(raw, limit=40_000)
                chunks.append(_strip_xml(text))
    except (zipfile.BadZipFile, OSError) as exc:
        return Extraction(kind="binary", note="OOXML unreadable: %s" % exc)

    merged = "\n".join(chunks)[:MAX_CHARS]
    return Extraction(text=merged, kind="docx", note="OOXML text via stdlib zipfile",
                      entries=members[:MAX_ARCHIVE_ENTRIES])


# ---------------------------------------------------------------------------
# PDF — optional, via pypdf
# ---------------------------------------------------------------------------

def _read_pdf(path: Path) -> Extraction:
    try:
        from pypdf import PdfReader  # noqa: WPS433 (optional dependency)
    except ImportError:
        return Extraction(kind="pdf", note="pypdf not installed - filename-only match")
    try:
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages[:40]:
            pages.append(page.extract_text() or "")
        meta = reader.metadata
        head = ""
        if meta is not None:
            for attr in ("author", "/Author", "title", "/Title"):
                value = getattr(meta, attr, None) if not attr.startswith("/") else None
                if value:
                    head += "%s: %s\n" % (attr, value)
        text = (head + "\n".join(pages))[:MAX_CHARS]
        return Extraction(text=text, kind="pdf", note="pypdf text extraction")
    except Exception as exc:  # noqa: BLE001 - third-party parsers throw anything
        return Extraction(kind="pdf", note="pypdf failed: %s" % type(exc).__name__)


# ---------------------------------------------------------------------------
# Archives (.skill / .zip / .tar.gz) — listing is always available,
# text harvest is best-effort and bounded.
# ---------------------------------------------------------------------------

def _archive_members(path: Path) -> "tuple[List[str], str]":
    """Return ``(member_names, note)`` for a zip or tar archive."""
    name = path.name.lower()
    try:
        if name.endswith((".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tar.xz")):
            with tarfile.open(str(path), "r:*") as tf:
                return [m.name for m in tf.getmembers() if m.isfile()], "tar archive"
        with zipfile.ZipFile(path) as zf:
            return [i.filename for i in zf.infolist() if not i.is_dir()], "zip archive"
    except (tarfile.TarError, zipfile.BadZipFile, OSError) as exc:
        return [], "archive unreadable: %s" % exc


def _read_archive(path: Path) -> Extraction:
    members, note = _archive_members(path)
    chunks: List[str] = []
    budget = MAX_ARCHIVE_TEXT
    name = path.name.lower()
    try:
        if name.endswith((".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tar.xz")):
            with tarfile.open(str(path), "r:*") as tf:
                for member in tf.getmembers():
                    if budget <= 0 or not member.isfile():
                        continue
                    if split_compound_ext(member.name) not in TEXT_EXTS and \
                            Path(member.name).name.lower() != "skill.md":
                        continue
                    handle = tf.extractfile(member)
                    if handle is None:
                        continue
                    text, _ = decode_bytes(handle.read(min(budget, MAX_READ_BYTES)))
                    chunks.append("\n=== %s ===\n%s" % (member.name, text))
                    budget -= len(text)
        else:
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    if budget <= 0 or info.is_dir():
                        continue
                    if split_compound_ext(info.filename) not in TEXT_EXTS and \
                            Path(info.filename).name.lower() != "skill.md":
                        continue
                    text, _ = decode_bytes(zf.read(info.filename)[:MAX_READ_BYTES])
                    chunks.append("\n=== %s ===\n%s" % (info.filename, text))
                    budget -= len(text)
    except (tarfile.TarError, zipfile.BadZipFile, OSError, KeyError, RuntimeError) as exc:
        note = "%s (harvest stopped: %s)" % (note, type(exc).__name__)

    return Extraction(text="\n".join(chunks)[:MAX_CHARS], kind="archive", note=note,
                      entries=members[:MAX_ARCHIVE_ENTRIES])


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def extract(path: Path) -> Extraction:
    """Extract whatever can be extracted from ``path``, never raising."""
    ext = split_compound_ext(path.name)
    try:
        size = path.stat().st_size
    except OSError:
        return Extraction(kind="missing", note="stat failed")

    if ext in ARCHIVE_EXTS or ext in TAR_EXTS:
        return _read_archive(path)
    if ext in OOXML_EXTS:
        return _read_ooxml(path)
    if ext in PDF_EXTS:
        return _read_pdf(path)
    if ext in TEXT_EXTS:
        return read_text_file(path)
    if ext in IMAGE_EXTS:
        return Extraction(kind="image", note="binary image - filename-only match (%d B)" % size)
    if ext in MEDIA_EXTS:
        return Extraction(kind="media", note="binary media - filename-only match (%d B)" % size)
    if ext in LEGACY_OFFICE_EXTS:
        return Extraction(kind="legacy", note="legacy Office format - filename-only match")
    return Extraction(kind="binary", note="unrecognised extension - filename-only match")


def looks_like_python(text: str) -> bool:
    return bool(re.search(r"^\s*(def |class |import |from \w+ import )", text, re.M))
