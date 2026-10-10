---
name: c4a-skill-evaluator
description: >
  Evaluate a folder of Elite20 C4 skill submissions (typically a WeChat group
  dump): identify each submission's author, check the five required deliverables,
  grade the skill against the C4 four criteria (Reusable / Executable /
  Verifiable / Clear I/O), raise the platform's red flags, rank the cohort and
  generate Markdown + CSV + Excel + HTML review reports with per-author
  improvement actions. Deterministic and offline: same folder in, same numbers out.
  Use whenever the user says "评审C4提交", "检查技能提交", "C4评审报告",
  "evaluate C4 submissions", "check C4 completeness", "review skill submissions",
  "grade these skill packages", or points at a folder of `姓名_C4_*` files and
  asks whether they are complete / how good they are / who is missing what.
  Also use when a teacher or TA wants a class-wide submission dashboard.
---

# C4A Skill Submission Evaluator

## Purpose

Given a folder that contains C4 submissions, produce the review a teaching
assistant would otherwise spend an evening writing by hand: who submitted what,
what is missing, how good it is against the four C4 conditions, and what each
student should fix next — as a reproducible report instead of a vibe.

Analogy: `wechat-doc-mapper` is the mail room (it sorts envelopes). This skill is
the grader sitting next to it — same envelope handling, plus a rubric.

## Input / Output

**Input:** one local folder path containing C4 submission files. Files should
follow the Elite20 convention `姓名拼音_C4_内容描述.扩展名`, but the skill falls
back to folder names, then file metadata, then document content when they do not.

**Output:** in `--out` (default `./output`):

| File | Contents |
|------|----------|
| `<basename>_report.md` | class overview + per-author detail + ranking + next actions |
| `<basename>_scores.csv` | one row per author, ready for a spreadsheet |
| `<basename>_scores.xlsx` | two sheets: Scores, Detail (every check) |
| `<basename>_dashboard.html` | self-contained dashboard, opens offline |
| `<basename>_scores.json` | machine-readable dump for downstream tooling |

**One-liner:** input a folder of C4 submissions, output a ranked review report in
five formats.

## Workflow

### Step 1 — Collect and group by author

```bash
python scripts/c4a_evaluator.py <FOLDER> --out ./output
```

The collector walks the folder recursively, keeps only files carrying a `C4`
token (in the name or in a parent directory), and resolves the author through a
four-step chain: filename prefix → parent folder → document metadata/content →
`Unknown` (flagged for manual review). `_v2` / `_v3` markers are detected and
reported as an iteration history.

### Step 2 — Completeness (five required deliverables)

Each file is scored against all five roles (skill doc, executable, demo,
teaching doc, AI log) using *filename pattern × extension × content signal*, then
greedily assigned to its best role so one document cannot count twice. Matches
below the confidence band are reported as ⚠️ "needs human confirmation" rather
than silently passed.

### Step 3 — Quality (the four C4 conditions)

19 checks in total, defined in `references/rubric.yaml`:

| Criterion | Checks |
|-----------|--------|
| 可复用 Reusable | install steps · no hardcoded paths · env/requirements · platform noted · no secrets |
| 可执行 Executable | runnable artefact · Python parses (`ast`) · package structure · SKILL.md frontmatter · workflow steps |
| 可验证 Verifiable | examples · expected output · reproducible commands · demo evidence · success criteria |
| IO 明确 Clear I/O | input section · output section · one-line "输入X，输出Y" · typed I/O |

A check returns pass / fail / **n/a** — n/a checks are excluded from the ratio,
so a submission is never penalised for a dimension that does not apply to it.

### Step 4 — Red flags, score and report

The three red flags from the platform rubric are applied (`missing_artifacts`,
`no_ai_log`, `one_shot_ai`). Composite score:

```
composite = 100 × (0.4 × completeness_ratio + 0.6 × quality_ratio)
```

Both weights and per-criterion weights are configurable (`--weights`,
`references/rubric.yaml`).

## Optional: LLM deep review

`--llm` adds free-text annotations from Claude for things a regex cannot judge
(mock-ups presented as real runs, claims unsupported by the files). It requires
`ANTHROPIC_API_KEY` and the `anthropic` package, and **never changes a score** —
if it is unavailable the run continues unchanged.

## Edge cases

| Situation | Handling |
|-----------|----------|
| Empty folder | Report "no C4 files found", list the scan path and the matching rule |
| Irregular file names | Fall back to folder → metadata → content; flag `Unknown` for manual review |
| Files larger than 60 MB | Recorded but not opened (name/type matching only) |
| Binary files (.png/.mp4) | Name-only matching, never parsed |
| Non-C4 files present | Excluded, listed separately in the report appendix |
| Multiple versions (_v2) | Version detected per file; iteration history shown per author |
| Chinese text in GBK/GB18030 | Encoding chain UTF-8 → GB18030 → GBK → Big5 → latin-1 |
| Corrupt archive / unreadable file | Recorded with a note, never fatal |
| A missing `openpyxl`/`pypdf` | .xlsx / PDF text is skipped with a printed note |

## Prerequisites

- Python 3.9+
- `PyYAML` (required)
- `openpyxl` (optional, for the .xlsx export), `pypdf` (optional, for PDF text),
  `anthropic` (optional, for `--llm`)
- No network access required for the default rule-based run

## Notes on honesty

The evaluator grades *whether a submission satisfies the C4 conditions*, not
whether the underlying lesson plan or code is any good. A 100/100 means "every
machine-checkable criterion is met", not "this skill is perfect". Treat the
report as a first-pass review that a human confirms — the ⚠️ ambiguous rows are
exactly where the human should look.
