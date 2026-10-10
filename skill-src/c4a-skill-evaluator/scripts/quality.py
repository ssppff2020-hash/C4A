#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quality.py — Level 3 of the C4A evaluator.

Score each submission against the four C4 conditions
(可复用 / 可执行 / 可验证 / IO 明确) and derive red flags.

Why a hybrid rule engine instead of an LLM call
-----------------------------------------------
The evaluation must be **reproducible**: two TAs running it on the same folder
must get the same numbers, and a student must be able to re-run the evaluator
after a fix and see the score move for a reason. So the *scoring* is 100%
deterministic and offline. Anything genuinely semantic ("is this demo really
proof?") is left to the optional LLM advisor (``llm_advisor.py``), which only
*annotates* — it never changes the numbers. See ATTRIBUTION.md for the
rule-vs-LLM trade-off analysis.

Every check returns one of:
  ``True``  — satisfied
  ``False`` — not satisfied
  ``None``  — not applicable to this submission (excluded from the ratio)
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import textio
from collector import FileInfo, Submission
from completeness import CompletenessResult, Role

# ---------------------------------------------------------------------------
# Aggregated evidence for one submission
# ---------------------------------------------------------------------------

AUTHORITATIVE_ROLES = ("skill_doc", "teaching_doc", "executable_content")

# Fenced code blocks, language-tagged or not.
FENCE_RE = re.compile(r"```([A-Za-z0-9_+\-]*)\n(.*?)```", re.S)
FRONTMATTER_RE = re.compile(r"\A\s*---\s*\n(.*?)\n---\s*\n", re.S)
# Members harvested out of an archive are delimited by "=== path === " banners
# (see textio._read_archive), which lets us syntax-check bundled .py sources.
ARCHIVE_MEMBER_RE = re.compile(r"===[ \t]*([^\n=]*?\.py)[ \t]*===[ \t]*\n(.*?)(?=\n=== |\Z)", re.S)


@dataclass
class Evidence:
    """Everything the checks may look at, pre-computed once."""

    submission: Submission
    completeness: CompletenessResult
    role_files: Dict[str, List[FileInfo]] = field(default_factory=dict)
    role_text: Dict[str, str] = field(default_factory=dict)
    fallback_note: List[str] = field(default_factory=list)

    @property
    def files(self) -> List[FileInfo]:
        return self.submission.files

    @property
    def authoritative_text(self) -> str:
        """Text used for *negative* checks (no paths, no secrets).

        AI logs are deliberately excluded: a chat transcript legitimately
        contains absolute paths and quoted keys, and penalising the author for
        what the model printed would be a false positive.
        """
        return "\n".join(self.role_text.get(r, "") for r in AUTHORITATIVE_ROLES)

    @property
    def all_text(self) -> str:
        return "\n".join(self.role_text.values())

    @property
    def hay(self) -> str:
        """All text plus all filenames — for *positive* checks."""
        names = " ".join(f.rel for f in self.files)
        return self.all_text + "\n" + names

    @property
    def archives(self) -> List[FileInfo]:
        return [f for f in self.files if f.kind == "archive"]

    @property
    def python_files(self) -> List[FileInfo]:
        return [f for f in self.files if f.ext == ".py"]

    def code_blocks(self, language: Optional[str] = None) -> List[Tuple[str, str]]:
        out = []
        for lang, body in FENCE_RE.findall(self.all_text):
            if language is None or lang.lower() == language.lower():
                out.append((lang.lower(), body))
        return out

    def files_in(self, *role_keys: str) -> List[FileInfo]:
        out: List[FileInfo] = []
        for key in role_keys:
            out.extend(self.role_files.get(key, []))
        return out


def build_evidence(submission: Submission, completeness: CompletenessResult) -> Evidence:
    evidence = Evidence(submission=submission, completeness=completeness)
    for key, role_result in completeness.roles.items():
        evidence.role_files[key] = list(role_result.files)
        evidence.role_text[key] = "\n".join(f.text or "" for f in role_result.files)
    return evidence


# ---------------------------------------------------------------------------
# Generic check runners
# ---------------------------------------------------------------------------

def _run_regex_any(patterns: List[str], text: str) -> Tuple[bool, str]:
    for pattern in patterns:
        try:
            match = re.search(pattern, text, re.I | re.M)
        except re.error as exc:  # a bad pattern must not kill the run
            return False, "正则错误 %r: %s" % (pattern, exc)
        if match:
            snippet = text[max(0, match.start() - 20):match.end() + 20].replace("\n", " ")
            return True, "命中 /%s/ → …%s…" % (pattern, snippet.strip()[:70])
    return False, "未命中任何模式（%d 条）" % len(patterns)


def _run_regex_absent(patterns: List[str], text: str) -> Tuple[bool, str]:
    hits = []
    for pattern in patterns:
        try:
            for match in re.finditer(pattern, text, re.I | re.M):
                hits.append("%s → %s" % (pattern, match.group(0)[:40]))
        except re.error:
            continue
    if hits:
        return False, "发现 %d 处：%s" % (len(hits), "；".join(hits[:3]))
    return True, "未发现硬编码/敏感内容"


def _run_regex_all(patterns: List[str], text: str) -> Tuple[bool, str]:
    missing = [p for p in patterns if not re.search(p, text, re.I | re.M)]
    if not missing:
        return True, "全部 %d 条模式命中" % len(patterns)
    return False, "缺少：%s" % "、".join(missing[:5])


# ---------------------------------------------------------------------------
# Special detectors — the checks a regex cannot decide
# ---------------------------------------------------------------------------

def _det_runnable_artifact(ev: Evidence) -> Tuple[Optional[bool], str]:
    runnable_exts = {".skill", ".py", ".zip", ".tar.gz", ".sh", ".js", ".html"}
    artefacts = [f for f in ev.files if f.ext in runnable_exts]
    blocks = ev.code_blocks()
    if artefacts:
        return True, "可运行产物：%s" % "、".join(f.rel for f in artefacts[:4])
    if blocks:
        return True, "无可执行文件，但有 %d 段代码/Prompt 代码块" % len(blocks)
    return False, "既没有 .skill/.py 等产物，也没有代码块"


def _det_code_parses(ev: Evidence) -> Tuple[Optional[bool], str]:
    """``ast.parse`` every .py file and every ```python block."""
    checked, errors = 0, []
    for info in ev.python_files:
        if not info.text.strip():
            continue
        checked += 1
        try:
            ast.parse(info.text, filename=info.rel)
        except SyntaxError as exc:
            errors.append("%s:%s %s" % (info.rel, exc.lineno, exc.msg))
    for lang, body in ev.code_blocks():
        if lang not in ("python", "py", ""):
            continue
        if "def " not in body and "import " not in body and "=" not in body:
            continue
        checked += 1
        try:
            ast.parse(body)
        except SyntaxError as exc:
            errors.append("代码块:%s %s" % (exc.lineno, exc.msg))
    # Python shipped *inside* a .skill / .zip / .tar.gz is real code too.
    for name, body in ARCHIVE_MEMBER_RE.findall(ev.all_text):
        if not body.strip():
            continue
        checked += 1
        try:
            ast.parse(body, filename=name)
        except SyntaxError as exc:
            errors.append("%s:%s %s" % (name, exc.lineno, exc.msg))

    if checked == 0:
        return None, "没有可解析的 Python 代码（跳过）"
    if errors:
        return False, "解析 %d 段，%d 段失败：%s" % (checked, len(errors), "；".join(errors[:3]))
    return True, "%d 段 Python 代码全部通过 ast.parse" % checked


def _det_package_structure(ev: Evidence) -> Tuple[Optional[bool], str]:
    if not ev.archives:
        return None, "无 .skill/.zip 压缩包（跳过）"
    bad = []
    for info in ev.archives:
        if not info.entries:
            bad.append("%s（无法读取成员）" % info.rel)
            continue
        if not any(Path(e).name.lower() == "skill.md" for e in info.entries):
            bad.append("%s（缺少 SKILL.md）" % info.rel)
    if bad:
        return False, "；".join(bad[:3])
    return True, "%d 个压缩包结构完整（含 SKILL.md）" % len(ev.archives)


def _find_skill_md_text(ev: Evidence) -> Optional[str]:
    """Return the text of the first SKILL.md we can see (file or archive member)."""
    for info in ev.files:
        if Path(info.rel).name.lower() == "skill.md" and info.text.strip():
            return info.text
    marker = re.compile(r"===\s*[^\n]*?skill\.md\s*===\s*\n(.*?)(?=\n=== |\Z)", re.S | re.I)
    match = marker.search(ev.all_text)
    if match:
        return match.group(1)
    return None


def _det_skill_frontmatter(ev: Evidence) -> Tuple[Optional[bool], str]:
    text = _find_skill_md_text(ev)
    if text is None:
        # No SKILL.md at all: if they shipped code instead, that is fine.
        if ev.python_files or ev.code_blocks():
            return None, "未提交 SKILL.md（以脚本形式交付，跳过）"
        return False, "未找到 SKILL.md，也没有其它可执行产物"
    match = FRONTMATTER_RE.match(text)
    if not match:
        return False, "SKILL.md 缺少 YAML frontmatter"
    try:
        import yaml
        meta = yaml.safe_load(match.group(1)) or {}
    except Exception:  # noqa: BLE001
        meta = {}
    missing = [k for k in ("name", "description") if not meta.get(k)]
    if missing:
        return False, "frontmatter 缺少字段：%s" % "、".join(missing)
    return True, "frontmatter 含 name + description"


def _det_demo_evidence(ev: Evidence) -> Tuple[Optional[bool], str]:
    demo_files = ev.role_files.get("demo", [])
    if not demo_files:
        return False, "未识别到 demo 文件"
    binary = [f for f in demo_files if f.kind in ("image", "media")]
    docs = [f for f in demo_files if f.kind in ("text", "docx", "pdf", "archive", "unknown")]
    long_docs = [f for f in docs if len((f.text or "").strip()) >= 300]
    if binary and long_docs:
        return True, "既有截图/录屏（%s），又有实录文档（%s）" % (
            binary[0].rel, long_docs[0].rel)
    if binary:
        return True, "有截图/录屏：%s" % binary[0].rel
    if long_docs:
        return True, "有实录文档（%d 字）：%s" % (len(long_docs[0].text.strip()), long_docs[0].rel)
    if docs:
        return False, "demo 文件过短（< 300 字），难以证明真实运行：%s" % docs[0].rel
    return None, "demo 为二进制/无法判断"


SPECIAL_DETECTORS: Dict[str, Callable[[Evidence], Tuple[Optional[bool], str]]] = {
    "runnable_artifact": _det_runnable_artifact,
    "code_parses": _det_code_parses,
    "package_structure": _det_package_structure,
    "skill_frontmatter": _det_skill_frontmatter,
    "demo_evidence": _det_demo_evidence,
}


# ---------------------------------------------------------------------------
# Criteria + result model
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    check_id: str
    label: str
    ok: Optional[bool]
    detail: str
    suggestion: str = ""

    @property
    def icon(self) -> str:
        if self.ok is None:
            return "—"
        return "✅" if self.ok else "❌"


@dataclass
class CriterionResult:
    key: str
    label_cn: str
    label_en: str
    weight: float
    description: str
    checks: List[CheckResult] = field(default_factory=list)
    fallback_suggestion: str = ""

    @property
    def applicable(self) -> List[CheckResult]:
        return [c for c in self.checks if c.ok is not None]

    @property
    def ratio(self) -> float:
        app = self.applicable
        if not app:
            return 0.0
        return sum(1 for c in app if c.ok) / float(len(app))

    @property
    def rating(self) -> str:
        return rating_for(self.ratio)[0]

    @property
    def rating_label(self) -> str:
        return rating_for(self.ratio)[1]

    @property
    def failed(self) -> List[CheckResult]:
        return [c for c in self.applicable if not c.ok]


THRESHOLDS = {"pass": 0.70, "partial": 0.30}


def rating_for(ratio: float) -> Tuple[str, str]:
    if ratio >= THRESHOLDS["pass"]:
        return "✅", "达标"
    if ratio >= THRESHOLDS["partial"]:
        return "⚠️", "部分达标"
    return "❌", "未达标"


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(evidence: Evidence, rubric: dict) -> List[CriterionResult]:
    criteria: List[CriterionResult] = []
    fallbacks = rubric.get("criterion_fallback_suggestions", {})
    for key, spec in rubric.get("quality_criteria", {}).items():
        criterion = CriterionResult(
            key=key,
            label_cn=spec.get("label_cn", key),
            label_en=spec.get("label_en", key),
            weight=float(spec.get("weight", 0.25)),
            description=spec.get("description", ""),
            fallback_suggestion=fallbacks.get(key, ""),
        )
        for check in spec.get("checks", []):
            criterion.checks.append(_run_check(check, evidence))
        criteria.append(criterion)
    return criteria


def _run_check(check: dict, ev: Evidence) -> CheckResult:
    detector = check.get("detector", "regex")
    suggestion = check.get("suggestion", "")
    if detector == "special":
        fn = SPECIAL_DETECTORS.get(check["id"])
        if fn is None:
            ok, detail = None, "未实现的特判器：%s" % check["id"]
        else:
            ok, detail = fn(ev)
    elif detector == "regex_absent":
        ok, detail = _run_regex_absent(check.get("any", []), ev.authoritative_text)
    elif detector == "regex_all":
        ok, detail = _run_regex_all(check.get("any", []), ev.hay if check.get("scope") == "all" else ev.authoritative_text)
    else:
        scope = ev.hay if check.get("scope") == "all" else ev.authoritative_text
        ok, detail = _run_regex_any(check.get("any", []), scope)
    return CheckResult(check_id=check["id"], label=check.get("label", check["id"]),
                       ok=ok, detail=detail, suggestion=suggestion)


# ---------------------------------------------------------------------------
# Red flags (mirrors the platform rubric.json for C4A)
# ---------------------------------------------------------------------------

RED_FLAG_RULES = {
    "missing_artifacts": lambda ev: ev.completeness.matched_count < 3,
    "no_ai_log": lambda ev: not ev.completeness.roles["ai_log"].present,
    "one_shot_ai": None,  # handled specially below (needs text analysis)
}


def detect_red_flags(ev: Evidence, rubric: dict) -> List[dict]:
    flags: List[dict] = []
    specs = {f["id"]: f for f in rubric.get("red_flags", [])}

    if ev.completeness.matched_count < 3:
        flags.append(_flag(specs, "missing_artifacts",
                           "仅 %d/5 项交付物，缺少：%s" % (
                               ev.completeness.matched_count,
                               "、".join(r.label_cn for r in ev.completeness.missing_roles()))))
    ai_role = ev.completeness.roles.get("ai_log")
    if ai_role is None or not ai_role.present:
        flags.append(_flag(specs, "no_ai_log", "未提交 AI 日志"))
    else:
        log_text = "\n".join(f.text or "" for f in ai_role.files)
        iteration = re.search(
            r"迭代|第\s*[二三四五2-9]\s*轮|v[2-9]|version\s*[2-9]|再次|重跑|修正|反馈|第二轮|prompt\s*优化",
            log_text, re.I)
        if len(log_text.strip()) < 400 and not iteration:
            flags.append(_flag(specs, "one_shot_ai",
                               "AI 日志仅 %d 字且无迭代痕迹" % len(log_text.strip())))
    return flags


def _flag(specs: dict, flag_id: str, detail: str) -> dict:
    spec = specs.get(flag_id, {})
    return {
        "id": flag_id,
        "label_cn": spec.get("label_cn", flag_id),
        "dimension": spec.get("dimension", ""),
        "penalty": spec.get("penalty", 5),
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

@dataclass
class Score:
    completeness_ratio: float
    quality_ratio: float
    quality_4: float          # same thing on a 0-4 scale, per criterion
    composite: float          # 0-100
    weights: Dict[str, float]


def composite(completeness: CompletenessResult, criteria: List[CriterionResult],
              scoring: dict, weights: Optional[Dict[str, float]] = None) -> Score:
    weights = weights or {}
    total_w = 0.0
    acc = 0.0
    for criterion in criteria:
        w = float(weights.get(criterion.key, criterion.weight))
        total_w += w
        acc += w * criterion.ratio
    quality_ratio = acc / total_w if total_w else 0.0

    cfg = scoring.get("composite", {})
    cw = float(cfg.get("completeness_weight", 0.4))
    qw = float(cfg.get("quality_weight", 0.6))
    scale = float(cfg.get("scale", 100))
    blend = (cw * completeness.ratio + qw * quality_ratio) / (cw + qw)

    return Score(
        completeness_ratio=completeness.ratio,
        quality_ratio=quality_ratio,
        quality_4=quality_ratio * 4.0,
        composite=blend * scale,
        weights=weights,
    )


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

def suggestions(completeness: CompletenessResult, criteria: List[CriterionResult],
                limit: int = 6) -> List[dict]:
    """Prioritised, de-duplicated next actions for one author."""
    out: List[dict] = []

    for role in completeness.missing_roles():
        out.append({"priority": 1, "area": "交付物完整性",
                    "text": role.missing_suggestion or "补交《%s》" % role.label_cn})

    for criterion in criteria:
        for check in criterion.failed:
            if check.suggestion:
                out.append({"priority": 2 if criterion.ratio < THRESHOLDS["partial"] else 3,
                            "area": criterion.label_cn,
                            "text": "%s —— %s" % (check.label, check.suggestion)})
        if criterion.ratio < THRESHOLDS["partial"] and criterion.fallback_suggestion:
            out.append({"priority": 2, "area": criterion.label_cn,
                        "text": criterion.fallback_suggestion})

    # De-duplicate while keeping priority order stable.
    seen = set()
    deduped = []
    for item in sorted(out, key=lambda d: d["priority"]):
        if item["text"] in seen:
            continue
        seen.add(item["text"])
        deduped.append(item)
    return deduped[:limit]
