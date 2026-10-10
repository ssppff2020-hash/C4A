#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""note-organizer — C4 test fixture (synthetic, by Liyang).

把一堆 .txt 课堂笔记按课程归类，生成 index.md 目录。
用法: python note-organizer.py <笔记文件夹>
"""

import sys
from pathlib import Path

COURSES = ["数据结构", "操作系统", "计算机网络", "数据库"]


def classify(text):
    """Return the first course name mentioned in the note."""
    for course in COURSES:
        if course in text:
            return course
    return "未分类"


def organize(folder):
    folder = Path(folder)
    buckets = {}
    for note in sorted(folder.glob("*.txt")):
        try:
            text = note.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        buckets.setdefault(classify(text), []).append(note.name)
    return buckets


def main():
    if len(sys.argv) < 2:
        print("用法: python note-organizer.py <笔记文件夹>")
        return 2
    buckets = organize(sys.argv[1])
    lines = ["# 课堂笔记目录", ""]
    for course, names in sorted(buckets.items()):
        lines.append("## %s" % course)
        lines.extend("- %s" % name for name in names)
        lines.append("")
    output = "\n".join(lines)
    Path("index.md").write_text(output, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
