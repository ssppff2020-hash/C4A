#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llm_advisor.py — optional LLM deep-review layer (annotation only).

Design contract
---------------
The LLM is allowed to **add free-text notes** to a submission. It is *never*
allowed to change a score, a rating, or a red flag. That keeps the numbers
reproducible and auditable while still letting a model surface things a regex
cannot see (e.g. "the demo image is a mock-up, not a real run").

If ``ANTHROPIC_API_KEY`` is absent, or the ``anthropic`` package is not
installed, or the call fails, the advisor degrades silently to "no notes" and
the run continues with the deterministic rule results. This is deliberate:
a network hiccup must never break an evaluation.

The reviewer is asked for a *short, structured* JSON list, not prose, so the
output can be embedded in the Markdown report without post-processing.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Callable, List, Optional

MODEL = "claude-sonnet-5-5"
MAX_INPUT_CHARS = 24_000

SYSTEM_PROMPT = (
    "You are a C4A review assistant. You are shown the automated rule results for ONE "
    "student's C4 skill submission plus an excerpt of their documents. The rules already "
    "produced the score — you must NOT propose a different score.\n"
    "Return ONLY a JSON array (max 3 items) of objects {\"note\": \"...\", \"evidence\": \"...\"} "
    "flagging things a keyword rule cannot see: mock-ups presented as real runs, claims "
    "unsupported by files, contradictions between the skill doc and the demo, or genuine "
    "strengths the rules under-credited. Write the notes in Chinese, one sentence each. "
    "If there is nothing worth saying, return [].\n"
)


def _build_user_prompt(evidence, completeness, criteria) -> str:
    lines = [
        "作者：%s" % evidence.submission.author,
        "交付物命中：%d/5" % completeness.matched_count,
        "文件：%s" % "、".join(f.rel for f in evidence.submission.files[:20]),
        "",
        "规则评分：",
    ]
    for criterion in criteria:
        lines.append("- %s %.2f %s" % (criterion.label_cn, criterion.ratio, criterion.rating))
        for check in criterion.checks:
            lines.append("    [%s] %s — %s" % (
                {True: "pass", False: "fail", None: "n/a"}[check.ok], check.label, check.detail[:120]))
    lines.append("")
    lines.append("文档节选：")
    lines.append(evidence.authoritative_text[:MAX_INPUT_CHARS])
    return "\n".join(lines)


def make_advisor(quiet: bool = False) -> Optional[Callable]:
    """Return an advisor callable, or ``None`` when the LLM layer is unavailable."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        if not quiet:
            sys.stderr.write("NOTE: --llm 已请求但未设置 ANTHROPIC_API_KEY，退回纯规则评审。\n")
        return None
    try:
        import anthropic
    except ImportError:
        if not quiet:
            sys.stderr.write("NOTE: --llm 已请求但未安装 anthropic SDK（pip install anthropic），退回纯规则评审。\n")
        return None

    client = anthropic.Anthropic()

    def advisor(evidence, completeness, criteria) -> List[str]:
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=700,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user",
                           "content": _build_user_prompt(evidence, completeness, criteria)}],
            )
            text = "".join(block.text for block in response.content if block.type == "text")
            start, end = text.find("["), text.rfind("]")
            if start < 0 or end < 0:
                return []
            items = json.loads(text[start:end + 1])
            notes = []
            for item in items[:3]:
                if isinstance(item, dict) and item.get("note"):
                    note = item["note"]
                    if item.get("evidence"):
                        note += "（依据：%s）" % item["evidence"]
                    notes.append(note)
            return notes
        except Exception as exc:  # noqa: BLE001 - never break an evaluation
            sys.stderr.write("NOTE: LLM 复审失败（%s），仅使用规则结果。\n" % type(exc).__name__)
            return []

    return advisor
