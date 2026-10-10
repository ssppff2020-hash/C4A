#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""c4a_evaluator.py — command-line entry point for the C4A skill evaluator.

    python scripts/c4a_evaluator.py <FOLDER> [options]

Pipeline:  scan  ->  group by author  ->  completeness  ->  quality  ->  report

Everything is deterministic and offline. Run it twice on the same folder and
you get byte-identical numbers.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Make the sibling modules importable no matter where the script is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import collector  # noqa: E402
import completeness as completeness_mod  # noqa: E402
import quality as quality_mod  # noqa: E402
import report as report_mod  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover - pyyaml is a declared prerequisite
    sys.stderr.write("ERROR: PyYAML is required. Install with: pip install pyyaml\n")
    raise SystemExit(2)

DEFAULT_RUBRIC = Path(__file__).resolve().parent.parent / "references" / "rubric.yaml"


def load_rubric(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def parse_weights(raw: str) -> dict:
    """``--weights reusable=0.4,executable=0.3`` -> ``{"reusable": 0.4, ...}``"""
    weights = {}
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise argparse.ArgumentTypeError("weights must look like key=value, got %r" % chunk)
        key, value = chunk.split("=", 1)
        weights[key.strip()] = float(value)
    return weights


def parse_tags(raw: list) -> dict:
    tags = {}
    for chunk in raw or []:
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            tags[key.strip()] = value.strip()
    return tags


def build_report(folder: Path, rubric: dict, weights: dict, tags: dict,
                 llm=None) -> report_mod.ClassReport:
    roles = completeness_mod.load_roles(rubric)

    c4_files, other_files = collector.scan(folder)
    submissions = collector.group_by_author(c4_files)

    authors = []
    for name, submission in submissions.items():
        comp = completeness_mod.check(submission, roles)
        evidence = quality_mod.build_evidence(submission, comp)
        criteria = quality_mod.evaluate(evidence, rubric)
        flags = quality_mod.detect_red_flags(evidence, rubric)
        actions = quality_mod.suggestions(comp, criteria)
        score = quality_mod.composite(comp, criteria, rubric.get("scoring", {}), weights)

        notes = []
        if llm is not None:
            notes = llm(evidence, comp, criteria)

        authors.append(report_mod.AuthorReport(
            submission=submission, completeness=comp, criteria=criteria, score=score,
            flags=flags, actions=actions,
            unmatched=completeness_mod.unmatched_files(submission, comp),
            llm_notes=notes, tag=tags.get(name, tags.get("__all__", "")),
        ))

    weights_note = ""
    if weights:
        weights_note = "自定义：" + "、".join("%s=%.2f" % (k, v) for k, v in weights.items())

    return report_mod.ClassReport(
        folder=str(folder),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        rubric_version="v%s" % rubric.get("version", "?"),
        authors=authors,
        non_c4_files=other_files,
        weights_note=weights_note,
        llm_enabled=llm is not None,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="c4a_evaluator",
        description="C4A — C4 skill-submission auto evaluator (scan / completeness / quality / report)")
    parser.add_argument("folder", help="folder containing C4 submissions (e.g. a WeChat group dump)")
    parser.add_argument("--out", default="output", help="output directory (default: ./output)")
    parser.add_argument("--formats", default="md,csv,xlsx,html,json",
                        help="comma list of md,csv,xlsx,html,json (default: all)")
    parser.add_argument("--config", default=str(DEFAULT_RUBRIC), help="path to rubric.yaml")
    parser.add_argument("--weights", default="",
                        help="override criterion weights, e.g. reusable=0.4,verifiable=0.3")
    parser.add_argument("--tag", action="append", default=[],
                        help="label an author in the report, e.g. --tag Liyang=SYNTHETIC")
    parser.add_argument("--basename", default="c4a", help="output file stem (default: c4a)")
    parser.add_argument("--llm", action="store_true",
                        help="enable the optional LLM deep-review annotation (needs ANTHROPIC_API_KEY)")
    parser.add_argument("--quiet", action="store_true", help="only print the summary table")
    args = parser.parse_args(argv)

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        sys.stderr.write("ERROR: '%s' is not a directory.\n" % folder)
        return 2

    rubric_path = Path(args.config)
    if not rubric_path.is_file():
        sys.stderr.write("ERROR: rubric not found: %s\n" % rubric_path)
        return 2
    rubric = load_rubric(rubric_path)
    weights = parse_weights(args.weights)
    tags = parse_tags(args.tag)

    llm = None
    if args.llm:
        import llm_advisor
        llm = llm_advisor.make_advisor(quiet=args.quiet)

    report = build_report(folder, rubric, weights, tags, llm)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    formats = {f.strip().lower() for f in args.formats.split(",") if f.strip()}
    written = []

    if "md" in formats:
        path = out_dir / ("%s_report.md" % args.basename)
        path.write_text(report_mod.render_markdown(report), encoding="utf-8")
        written.append(path)
    if "csv" in formats:
        path = out_dir / ("%s_scores.csv" % args.basename)
        report_mod.write_csv(report, path)
        written.append(path)
    if "json" in formats:
        path = out_dir / ("%s_scores.json" % args.basename)
        report_mod.write_json(report, path)
        written.append(path)
    if "html" in formats:
        path = out_dir / ("%s_dashboard.html" % args.basename)
        report_mod.write_html(report, path)
        written.append(path)
    if "xlsx" in formats:
        path = out_dir / ("%s_scores.xlsx" % args.basename)
        note = report_mod.write_xlsx(report, path)
        if note:
            sys.stderr.write("NOTE: %s\n" % note)
        else:
            written.append(path)

    _print_summary(report, written)
    return 0


def _print_summary(report: report_mod.ClassReport, written) -> None:
    stats = report.stats()
    line = "-" * 78
    print(line)
    print("C4A 自动评审 · %s" % report.folder)
    print("提交 %d 人 ｜ 完整 %d ｜ 部分 %d ｜ 严重缺失 %d ｜ 平均综合分 %.1f" % (
        stats["n"], stats["complete"], stats["partial"], stats["insufficient"],
        stats["avg_composite"]))
    print(line)
    print("%-18s %-8s %-7s %-6s %s" % ("作者", "完整性", "四条件", "综合分", "红牌"))
    for author in report.ranked:
        print("%-18s %-8s %-7.2f %-6.1f %s" % (
            author.author[:18],
            "%d/5 %s" % (author.completeness.matched_count, author.completeness.icon),
            author.score.quality_4, author.score.composite,
            "、".join(f["label_cn"] for f in author.flags) or "—"))
    print(line)
    if written:
        print("已生成：")
        for path in written:
            print("  %s" % path)


if __name__ == "__main__":
    raise SystemExit(main())
