# Scoring guide — how a C4 submission becomes a number

This document explains exactly how the evaluator turns a folder of files into
the scores in the report, so that a teacher can defend (or override) any number
it produces. Every threshold named here lives in `rubric.yaml` — nothing is
hard-coded in the scripts except the four *special detectors*.

---

## 1. Completeness — five deliverables

Each file is scored against each of the five roles:

```
score(file, role) = min(12, 3 × longest matching filename pattern)
                  + (3 if file extension is in the role's preferred list)
                  + min(6, 2 × number of content signals found)
```

Content signals are looked for in the file body **and** in the filename, so
`demo_运行结果.md` earns credit for the word "demo" even before it is opened.

Then a **greedy assignment** runs: all `(file, role)` pairs with `score ≥ 7`
are sorted by score descending; each file is given to its highest-scoring role
and removed from the pool. Consequences:

* A file can never be counted for two deliverables. (This is the bug that made
  the first prototype report `6/5` files for one student.)
* `skill说明.md` lands in *skill doc* even though "skill" also appears in the
  *executable content* pattern list, because its skill-doc score is higher.

| score | meaning |
|-------|---------|
| ≥ 12 | confident match ✅ |
| 7–11 | weak match ⚠️ — counted, but the report says "needs human confirmation" |
| < 7 | not a match |

A role is flagged ⚠️ only when **no** file in it matched confidently. One weak
supporting file next to a strong one is normal and does not raise the flag.

Band: 5/5 = 齐全 ✅ · 3–4/5 = 部分缺失 ⚠️ · <3/5 = 严重缺失 ❌.

## 2. Quality — four criteria, 19 checks

Every check returns **pass**, **fail**, or **n/a**. `n/a` is excluded from the
denominator, so a submission is never punished for a dimension that does not
apply to it (e.g. no Python file at all → `code_parses` is n/a, not fail).

```
criterion_ratio = passed / (passed + failed)
```

| ratio | rating |
|-------|--------|
| ≥ 0.70 | ✅ 达标 |
| 0.30 – 0.69 | ⚠️ 部分达标 |
| < 0.30 | ❌ 未达标 |

### What each check actually looks at

Negative checks (`no_absolute_paths`, `no_hardcoded_secrets`) scan only the
**authoritative** text: skill doc + teaching doc + executable. The AI log is
deliberately excluded, because a chat transcript legitimately contains absolute
paths and quoted keys, and penalising the author for what the model printed
would be a false positive.

`code_parses` runs `ast.parse` over three sources of Python: standalone `.py`
files, ```` ```python ```` fences, and `.py` members harvested out of
`.skill` / `.zip` / `.tar.gz` archives.

## 3. Red flags

Mirrored from the platform's `rubric.json` for C4A:

| flag | rule |
|------|------|
| `missing_artifacts` | fewer than 3 of the 5 deliverables present |
| `no_ai_log` | the AI-log deliverable is missing |
| `one_shot_ai` | AI log present but < 400 characters **and** no iteration marker (第N轮 / 迭代 / v2 / prompt 优化 / 修正 …) |

`one_shot_ai` is a heuristic, and it is the flag most likely to be argued with.
It is deliberately conservative (it needs *both* a short log and no iteration
vocabulary), and the report shows the log length it measured so the student can
see exactly why it fired.

## 4. Composite score

```
completeness_ratio = matched_deliverables / 5
quality_ratio      = Σ(weight_i × criterion_ratio_i) / Σ(weight_i)     # default weight 0.25 each
composite          = 100 × (0.4 × completeness_ratio + 0.6 × quality_ratio)
```

Both layers are configurable:

```bash
# emphasise the four conditions over deliverable count
python scripts/c4a_evaluator.py <FOLDER> --weights reusable=0.4,executable=0.3,verifiable=0.2,clear_io=0.1
```

Editing `scoring.composite` in `rubric.yaml` changes the 0.4 / 0.6 blend.

## 5. How to change the rules

* **Add a keyword** → edit the relevant `any:` list in `rubric.yaml`.
* **Add a whole check** → add an entry with `detector: regex` and a
  `suggestion`; it is picked up automatically and appears in every report.
* **Add a check a regex cannot express** → write a function in
  `scripts/quality.py`, register it in `SPECIAL_DETECTORS`, and reference it
  with `detector: special`.

After any rule change, run the golden set:

```bash
python -m unittest discover -s tests -v
```

The fixtures encode the expected verdicts for three submissions of known
quality; a rule change that moves them is a change to the evaluator's
judgement and must be made on purpose.

## 6. Known limitations

1. **It grades conformance, not quality.** A well-formed but pedagogically weak
   lesson plan can score 100. The rubric asks "does this meet the four C4
   conditions", not "is this good work".
2. **Binary artefacts are name-only.** A `.png` proves a screenshot exists, not
   that it shows a real run — that judgement is what `--llm` adds.
3. **Keyword matching is language-bound.** The rubric ships with Chinese and
   English signals; a submission written in another language will under-score
   until signals are added.
4. **Version tracking is per file.** A file with no `_v2` marker and no version
   sentence is assumed to be v1, so a fully-updated submission with no markers
   reports as uniformly v1 (which is correct but uninformative).
