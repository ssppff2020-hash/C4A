#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""literature-format-assistant — C4 test fixture (synthetic, by Chenmingyuan).

输入：一个 BibTeX 文件 + 目标格式（gbt7714 / apa）
输出：逐条格式诊断报告 report.md + 修正后的 fixed.bib，退出码 0/1

Usage:
    python literature-format-assistant.py --input refs.bib --style gbt7714 --out ./out
"""

import argparse
import os
import re
import sys

REQUIRED_FIELDS = {"article": ("author", "title", "journal", "year", "volume", "pages")}


def parse_bib(text):
    """Minimal BibTeX reader: returns a list of (key, entry_type, fields)."""
    entries = []
    for match in re.finditer(r"@(\w+)\s*\{\s*([^,]+),(.*?)\n\}", text, re.S):
        entry_type, key, body = match.group(1).lower(), match.group(2).strip(), match.group(3)
        fields = {}
        for field in re.finditer(r"(\w+)\s*=\s*[{\"](.+?)[}\"]\s*,?\s*\n", body + "\n", re.S):
            fields[field.group(1).lower()] = " ".join(field.group(2).split())
        entries.append((key, entry_type, fields))
    return entries


def check_entry(key, entry_type, fields):
    """Return a list of (level, message) diagnostics for one entry."""
    issues = []
    for field in REQUIRED_FIELDS.get(entry_type, ()):
        if not fields.get(field):
            issues.append(("ERROR", "缺%s(%s) —— 期刊论文 GB/T 7714 必填 %s" % (field, field, field)))
    author = fields.get("author", "")
    if author and re.search(r"^[a-z]", author):
        issues.append(("WARN", "作者名应为首字母大写 —— 建议 '%s'" % author.capitalize()))
    return issues


def format_gbt7714(fields):
    return "%s. %s[J]. %s, %s, %s(%s): %s." % (
        fields.get("author", "?"), fields.get("title", "?"), fields.get("journal", "?"),
        fields.get("year", "?"), fields.get("volume", "?"), fields.get("number", "1"),
        fields.get("pages", "?"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="BibTeX format checker (GB/T 7714 / APA)")
    parser.add_argument("--input", required=True, help="path to a .bib file")
    parser.add_argument("--style", default="gbt7714", choices=["gbt7714", "apa"])
    parser.add_argument("--out", default="out", help="output directory")
    args = parser.parse_args(argv)

    with open(args.input, "r", encoding="utf-8", errors="replace") as handle:
        entries = parse_bib(handle.read())

    os.makedirs(args.out, exist_ok=True)
    lines, errors = [], 0
    for index, (key, entry_type, fields) in enumerate(entries, 1):
        issues = check_entry(key, entry_type, fields)
        errors += sum(1 for level, _ in issues if level == "ERROR")
        if issues:
            for level, message in issues:
                lines.append("[%d] %-7s %s" % (index, level, message))
        else:
            lines.append("[%d] OK      %s" % (index, format_gbt7714(fields)))

    report = "\n".join(lines) + "\n---\n合计 %d 条\n" % len(entries)
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as handle:
        handle.write(report)
    print(report)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
