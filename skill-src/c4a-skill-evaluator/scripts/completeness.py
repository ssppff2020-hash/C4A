#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""completeness.py — Level 2 of the C4A evaluator.

Decide, for each author, whether the five C4 deliverables (C4 §四) are present.

The interesting engineering problem here is **false positives**. A naive
"does any .md mention 输入?" rule matches half the folder. So instead of a
boolean per role we compute a *score* for every (file, role) pair:

    filename pattern hit   : 3 * len(longest matching pattern)   (capped at 12)
    preferred extension    : +3
    content signal present : +2 per signal                      (capped at 6)

and then run a **greedy assignment**: every file lands in the role where it
scores highest, provided it clears ``MATCH_WEAK``. That mirrors how a human TA
reads a submission — "this file is clearly the teaching doc, so it is not also
the skill doc".

Scores in ``[MATCH_WEAK, MATCH_STRONG)`` count as present but are flagged
``ambiguous`` so the report can say "we think this is your demo, please confirm".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import textio
from collector import FileInfo, Submission

MATCH_WEAK = 7     # below this -> not a match
MATCH_STRONG = 12  # at or above this -> confident match


# ---------------------------------------------------------------------------
# Rubric model
# ---------------------------------------------------------------------------

@dataclass
class Role:
    key: str
    label_cn: str
    label_en: str
    required: bool
    filename_patterns: List[str]
    content_signals: List[str]
    preferred_extensions: List[str]
    missing_suggestion: str = ""
    order: int = 0


@dataclass
class RoleHit:
    role: Role
    score: int
    reason: str
    name_hits: List[str] = field(default_factory=list)
    content_hits: List[str] = field(default_factory=list)


@dataclass
class RoleResult:
    role: Role
    files: List[FileInfo] = field(default_factory=list)
    ambiguous: bool = False

    @property
    def present(self) -> bool:
        return bool(self.files)

    @property
    def status(self) -> str:
        if not self.files:
            return "missing"
        return "ambiguous" if self.ambiguous else "ok"


@dataclass
class CompletenessResult:
    roles: Dict[str, RoleResult]
    matched_count: int
    total_count: int

    @property
    def band(self) -> str:
        if self.matched_count >= 5:
            return "complete"
        if self.matched_count >= 3:
            return "partial"
        return "insufficient"

    @property
    def icon(self) -> str:
        return {"complete": "✅", "partial": "⚠️", "insufficient": "❌"}[self.band]

    @property
    def label(self) -> str:
        return {"complete": "齐全", "partial": "部分缺失", "insufficient": "严重缺失"}[self.band]

    @property
    def ratio(self) -> float:
        return self.matched_count / float(self.total_count or 1)

    def missing_roles(self) -> List[Role]:
        return [r.role for r in self.roles.values() if not r.present]


def load_roles(rubric: dict) -> List[Role]:
    roles: List[Role] = []
    for order, (key, spec) in enumerate(rubric.get("required_deliverables", {}).items()):
        roles.append(Role(
            key=key,
            label_cn=spec.get("label_cn", key),
            label_en=spec.get("label_en", key),
            required=bool(spec.get("required", True)),
            filename_patterns=[p.lower() for p in spec.get("filename_patterns", [])],
            content_signals=[s.lower() for s in spec.get("content_signals", [])],
            preferred_extensions=[e.lower() for e in spec.get("preferred_extensions", [])],
            missing_suggestion=spec.get("missing_suggestion", ""),
            order=order,
        ))
    return roles


# ---------------------------------------------------------------------------
# Scoring one (file, role) pair
# ---------------------------------------------------------------------------

def score_file_for_role(info: FileInfo, role: Role) -> RoleHit:
    """Score how well ``info`` fills ``role``."""
    name_hits = [p for p in role.filename_patterns if p and p in info.hay]
    longest = max((len(p) for p in name_hits), default=0)
    name_score = min(12, 3 * longest)

    ext_score = 3 if info.ext in role.preferred_extensions else 0

    hay = (info.text or "")[:MAX_SCAN].lower()
    content_hits = [s for s in role.content_signals if s and s in hay]
    # Content signals are also looked for in the filename, because a file named
    # "demo_运行结果.md" carries signal in its own name.
    for signal in role.content_signals:
        if signal and signal in info.hay and signal not in content_hits:
            content_hits.append(signal)
    content_score = min(6, 2 * len(content_hits))

    score = name_score + ext_score + content_score
    reasons = []
    if name_hits:
        reasons.append("文件名命中: %s" % "、".join(name_hits[:3]))
    if ext_score:
        reasons.append("扩展名匹配: %s" % info.ext)
    if content_hits:
        reasons.append("内容信号: %s" % "、".join(content_hits[:4]))
    return RoleHit(role=role, score=score, reason="；".join(reasons) or "无命中",
                   name_hits=name_hits, content_hits=content_hits)


MAX_SCAN = 60_000  # only the head of a file is scanned for signals


def assign(submission: Submission, roles: List[Role]) -> CompletenessResult:
    """Greedy (file -> best role) assignment for one author."""
    pairs: List[Tuple[int, int, FileInfo, RoleHit]] = []
    for info in submission.files:
        for role in roles:
            hit = score_file_for_role(info, role)
            if hit.score >= MATCH_WEAK:
                # tie-break: higher score, then rubric order, then path
                pairs.append((-hit.score, role.order, info, hit))

    pairs.sort(key=lambda t: (t[0], t[1], t[2].rel))

    assigned: Dict[str, List[FileInfo]] = {role.key: [] for role in roles}
    confident: Dict[str, bool] = {role.key: False for role in roles}
    taken: set = set()
    for _, _, info, hit in pairs:
        if id(info) in taken:
            continue
        assigned[hit.role.key].append(info)
        taken.add(id(info))
        if hit.score >= MATCH_STRONG:
            confident[hit.role.key] = True

    results: Dict[str, RoleResult] = {}
    for role in roles:
        files = assigned[role.key]
        # A role is only "ambiguous" when *nothing* matched it confidently;
        # one weak supporting file alongside a strong one is normal.
        results[role.key] = RoleResult(role=role, files=files,
                                       ambiguous=bool(files) and not confident[role.key])

    matched = sum(1 for r in results.values() if r.present)
    return CompletenessResult(roles=results, matched_count=matched, total_count=len(roles))


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def check(submission: Submission, roles: List[Role]) -> CompletenessResult:
    return assign(submission, roles)


def render_matrix(result: CompletenessResult) -> List[Tuple[str, str, str, str]]:
    """Rows for the report table: (deliverable, icon, matched file, note)."""
    rows = []
    for role_result in result.roles.values():
        if not role_result.files:
            rows.append((role_result.role.label_cn, "❌", "—",
                         role_result.role.missing_suggestion or "缺失"))
            continue
        icon = "⚠️" if role_result.ambiguous else "✅"
        names = "、".join(f.rel for f in role_result.files[:3])
        if len(role_result.files) > 3:
            names += " 等 %d 个" % len(role_result.files)
        note = "需人工确认" if role_result.ambiguous else "命中"
        rows.append((role_result.role.label_cn, icon, names, note))
    return rows


def unmatched_files(submission: Submission, result: CompletenessResult) -> List[FileInfo]:
    used = {id(f) for rr in result.roles.values() for f in rr.files}
    return [f for f in submission.files if id(f) not in used]
