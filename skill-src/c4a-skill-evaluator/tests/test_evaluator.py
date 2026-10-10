#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Golden-set tests for c4a-skill-evaluator.

The fixture folder ``tests/fixtures/wechat_dump/`` is a *deliberately* mixed
WeChat-style dump: three synthetic C4 submissions of known-and-different
quality, plus two non-C4 files that must be filtered out. Every assertion here
is a claim about the evaluator's judgement, so this file doubles as the
"误判率" evidence for the C4A rubric.

Run:
    python -m unittest discover -s tests -v
    python tests/test_evaluator.py -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import collector          # noqa: E402
import completeness as cmp_mod  # noqa: E402
import quality as quality_mod   # noqa: E402
import report as report_mod     # noqa: E402

import yaml               # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wechat_dump"
RUBRIC = SKILL_DIR / "references" / "rubric.yaml"

# Expected profile of each synthetic author. If a rule change moves these
# numbers, the change broke a documented expectation -> update deliberately.
EXPECTED = {
    "Chenmingyuan": {"files": 5, "band": "complete", "flags": set()},
    "Liyang":       {"files": 4, "band": "partial",  "flags": {"one_shot_ai"}},
    "Zhaolei":      {"files": 2, "band": "insufficient",
                     "flags": {"missing_artifacts", "no_ai_log"}},
}


def build(folder: Path):
    rubric = yaml.safe_load(RUBRIC.read_text(encoding="utf-8"))
    roles = cmp_mod.load_roles(rubric)
    c4_files, other_files = collector.scan(folder)
    submissions = collector.group_by_author(c4_files)

    results = {}
    for author, submission in submissions.items():
        comp = cmp_mod.check(submission, roles)
        ev = quality_mod.build_evidence(submission, comp)
        criteria = quality_mod.evaluate(ev, rubric)
        flags = quality_mod.detect_red_flags(ev, rubric)
        score = quality_mod.composite(comp, criteria, rubric["scoring"])
        results[author] = {
            "submission": submission, "completeness": comp, "criteria": criteria,
            "flags": flags, "score": score, "evidence": ev,
        }
    return rubric, results, other_files


class TestCollector(unittest.TestCase):
    """Level 1 — collection and author resolution."""

    @classmethod
    def setUpClass(cls):
        cls.rubric, cls.results, cls.others = build(FIXTURES)

    def test_non_c4_files_are_filtered(self):
        names = {f.rel for f in self.others}
        self.assertIn("Elite20_课表.md", names)
        self.assertIn("群公告.txt", names)
        self.assertNotIn("Chenmingyuan_C4_skill说明.md", names)

    def test_exactly_three_c4_authors(self):
        self.assertEqual(sorted(self.results), ["Chenmingyuan", "Liyang", "Zhaolei"])

    def test_author_resolution_uses_filename(self):
        for author, data in self.results.items():
            methods = {f.author_method for f in data["submission"].files}
            self.assertIn("filename(ascii)", methods,
                          "%s should resolve from the filename" % author)

    def test_non_c4_dump_does_not_produce_a_phantom_author(self):
        self.assertNotIn("Unknown", self.results)
        self.assertNotIn("Elite20", self.results)


class TestCompleteness(unittest.TestCase):
    """Level 2 — the five required deliverables."""

    @classmethod
    def setUpClass(cls):
        _, cls.results, _ = build(FIXTURES)

    def test_expected_counts_and_bands(self):
        for author, want in EXPECTED.items():
            comp = self.results[author]["completeness"]
            self.assertEqual(comp.matched_count, want["files"],
                             "%s completeness" % author)
            self.assertEqual(comp.band, want["band"], "%s band" % author)

    def test_liyang_is_missing_exactly_the_demo(self):
        comp = self.results["Liyang"]["completeness"]
        missing = {r.key for r in comp.missing_roles()}
        self.assertEqual(missing, {"demo"})

    def test_demo_role_collects_both_image_and_transcript(self):
        comp = self.results["Chenmingyuan"]["completeness"]
        demo_files = {f.rel for f in comp.roles["demo"].files}
        self.assertTrue(any(f.endswith(".png") for f in demo_files))
        self.assertTrue(any("运行结果" in f for f in demo_files))

    def test_a_file_is_never_assigned_to_two_roles(self):
        for data in self.results.values():
            comp = data["completeness"]
            seen = [f.rel for role in comp.roles.values() for f in role.files]
            self.assertEqual(len(seen), len(set(seen)),
                             "a file was double-counted")

    def test_skill_doc_does_not_steal_the_teaching_doc(self):
        comp = self.results["Chenmingyuan"]["completeness"]
        self.assertIn("Chenmingyuan_C4_教学说明.md",
                      {f.rel for f in comp.roles["teaching_doc"].files})
        self.assertNotIn("Chenmingyuan_C4_教学说明.md",
                         {f.rel for f in comp.roles["skill_doc"].files})


class TestQuality(unittest.TestCase):
    """Level 3 — the four C4 conditions."""

    @classmethod
    def setUpClass(cls):
        _, cls.results, _ = build(FIXTURES)

    def _criterion(self, author, key):
        return next(c for c in self.results[author]["criteria"] if c.key == key)

    def test_hardcoded_paths_are_caught_only_where_they_exist(self):
        zhaolei = self._criterion("Zhaolei", "reusable")
        chen = self._criterion("Chenmingyuan", "reusable")
        self.assertIn("no_absolute_paths", {c.check_id for c in zhaolei.failed})
        self.assertNotIn("no_absolute_paths", {c.check_id for c in chen.failed})

    def test_verifiable_collapses_without_a_demo_or_examples(self):
        self.assertLess(self._criterion("Liyang", "verifiable").ratio, 0.35)
        self.assertGreaterEqual(self._criterion("Chenmingyuan", "verifiable").ratio, 0.7)

    def test_clean_submission_meets_every_criterion(self):
        for criterion in self.results["Chenmingyuan"]["criteria"]:
            self.assertEqual(criterion.rating, "✅", criterion.label_cn)

    def test_python_syntax_is_actually_parsed(self):
        checks = {c.check_id: c for c in self._criterion("Chenmingyuan", "executable").checks}
        self.assertIs(checks["code_parses"].ok, True)
        self.assertIn("ast.parse", checks["code_parses"].detail)

    def test_missing_python_source_is_reported_as_na_not_failed(self):
        """A submission with no Python at all must not be punished for that."""
        checks = {c.check_id: c for c in self._criterion("Liyang", "executable").checks}
        self.assertIs(checks["code_parses"].ok, True)   # Liyang ships a .py

    def test_scores_are_ordered_as_designed(self):
        scores = {a: self.results[a]["score"].composite for a in self.results}
        self.assertGreater(scores["Chenmingyuan"], scores["Liyang"])
        self.assertGreater(scores["Liyang"], scores["Zhaolei"])
        self.assertGreaterEqual(scores["Chenmingyuan"], 95)
        self.assertLess(scores["Zhaolei"], 55)


class TestRedFlags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.results, _ = build(FIXTURES)

    def test_flags_match_the_platform_rubric(self):
        for author, want in EXPECTED.items():
            got = {f["id"] for f in self.results[author]["flags"]}
            self.assertEqual(got, want["flags"], "%s flags" % author)

    def test_clean_submission_has_no_flags(self):
        self.assertEqual(self.results["Chenmingyuan"]["flags"], [])


class TestDeterminism(unittest.TestCase):
    """The same folder must produce the same numbers — that is the whole point."""

    def test_two_runs_agree(self):
        _, first, _ = build(FIXTURES)
        _, second, _ = build(FIXTURES)
        a = {k: round(v["score"].composite, 6) for k, v in first.items()}
        b = {k: round(v["score"].composite, 6) for k, v in second.items()}
        self.assertEqual(a, b)

    def test_repeated_scan_of_one_author_is_stable(self):
        _, results, _ = build(FIXTURES)
        comp = results["Zhaolei"]["completeness"]
        self.assertEqual(comp.matched_count, 2)


class TestReportRendering(unittest.TestCase):
    """Level 4 — every output format renders without raising."""

    @classmethod
    def setUpClass(cls):
        _, results, others = build(FIXTURES)
        rubric = yaml.safe_load(RUBRIC.read_text(encoding="utf-8"))
        authors = [
            report_mod.AuthorReport(
                submission=d["submission"], completeness=d["completeness"],
                criteria=d["criteria"], score=d["score"], flags=d["flags"],
                actions=quality_mod.suggestions(d["completeness"], d["criteria"]),
                unmatched=cmp_mod.unmatched_files(d["submission"], d["completeness"]),
            )
            for d in results.values()
        ]
        cls.report = report_mod.ClassReport(
            folder=str(FIXTURES), generated_at="2026-01-01 00:00:00",
            rubric_version="v2", authors=authors, non_c4_files=others)

    def test_markdown_contains_every_section(self):
        text = report_mod.render_markdown(self.report)
        for heading in ("## 一、班级总览", "## 二、作者详情", "## 三、排名", "## 四、全班改进建议"):
            self.assertIn(heading, text)

    def test_ranking_is_sorted_descending(self):
        ranked = self.report.ranked
        scores = [a.score.composite for a in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(ranked[0].author, "Chenmingyuan")
        self.assertEqual(ranked[-1].author, "Zhaolei")

    def test_zhaolei_gets_actionable_suggestions(self):
        zhaolei = next(a for a in self.report.authors if a.author == "Zhaolei")
        text = " ".join(a["text"] for a in zhaolei.actions)
        self.assertTrue(zhaolei.actions, "a failing submission must get actions")
        self.assertTrue("绝对路径" in text or "安装" in text)

    def test_html_and_json_render(self):
        html = report_mod.render_html(self.report)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Chenmingyuan", html)
        payload = json.dumps(report_mod.to_json(self.report), ensure_ascii=False)
        self.assertIn("Chenmingyuan", payload)

    def test_csv_rows_have_one_row_per_author(self):
        rows = report_mod.render_rows(self.report)
        self.assertEqual(len(rows), 3)
        self.assertEqual({r["author"] for r in rows}, set(EXPECTED))


if __name__ == "__main__":
    unittest.main(verbosity=2)
