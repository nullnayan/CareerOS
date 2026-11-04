# Resume Parser — Diagnosis & Fix Plan

**Status:** draft · **Scope:** `backend/api/resumes.py`, `backend/agents/resume_parser.py`,
`backend/resume_parser/**`, `backend/services/text_extraction.py`
**Companion to:** `ATS_V3_CALIBRATION_PLAN.md` (Phase 0 of that plan depends on this one)

The ATS engine reads a schema the parser doesn't produce. Tracing why led here. The parser is
substantially better-built than the scorer — `resume_parser/` is ~1,950 lines of real modular work
with a quality scorer, coverage auditing and genuine column-aware extraction. **The problem is not
capability. It's that the pipeline emits three different schemas and throws away most of what it
computes.**

---

# Part 0 — Diagnosis

## 0.1 THE ROOT CAUSE — one function, three output schemas

`parse_resume_hybrid` (`api/resumes.py:59`) has three exit paths, and each returns a structurally
different object:

| | Path A — software OK (`:186`) | Path B — AI heal (`:163`) | Path C — vision/scanned (`:78`, `:96`) |
|---|---|---|---|
| `skills` | `{all, byCategory}` | `{all, byCategory}` | **flat `[str]`** |
| `formatting_metadata` | real, from `metadata` | **hardcoded all-`False`** | **hardcoded, `is_scanned: True`** |
| `metadata` | present | only if software ran | **absent** |
| `quality` | **dropped** | absent | absent |
| `original_section_headings` | present | from LLM | from LLM |
| `education` grade key | `cgpa_or_percentage` | `cgpa_or_percentage` | `cgpa_or_percentage` |

Every consumer downstream — `doc_builder`, `ats_fixers`, the builder UI, the tailoring engine —
has to guess which shape it got. None of them do; they each assume one. That's the whole bug class.

## 0.2 Key-name mismatches — the measured failure

`ats/doc_builder.py` reads keys that **no parser path ever emits**:

| Field | Parser emits | `doc_builder` reads | Result |
|---|---|---|---|
| Experience bullets | `bullet_points` (`resume_parser.py:41`, `resumes.py:216`) | `bullets` (`:53`) | **0 bullets, always** |
| Experience start | `start_date` (`:39`, `:214`) | `startDate` (`:50`) | **`years_experience` = 0.0, always** |
| Experience end | `end_date` (`:40`, `:215`) | `endDate` (`:51`) | is_current always True |
| Education grade | `cgpa_or_percentage` (`:50`, `:227`) | `gpa.raw` (`:116`) | GPA checks dead |
| Education date | `graduation_date` (`:49`, `:226`) | `endYear` (`:122`) | date checks dead |
| Skills | dict `{all, byCategory}` (A, B) | iterates as list (`:130`) | **skill names become `"all"`, `"byCategory"`** |

Measured end-to-end through the real engine, same resume, both spellings:

| | bullets seen | years exp | band | ATS score |
|---|---|---|---|---|
| Production keys | **0** | **0.0** | student | 65.3 |
| Corpus keys | 3 | 5.0 | mid | 91.3 |

`'40%' in doc.text.full` → **`False`**. Experience bullet text never reaches the text view the JD
keyword matcher runs against.

Note the skills row is the nastiest: it doesn't fail loudly, it silently populates the skills list
with the strings `"all"` and `"byCategory"`, which then get keyword-matched against job descriptions.

## 0.3 The fallback is all-or-nothing

`resumes.py:113-160` — `is_complete` is a single boolean. **A missing phone number discards the
entire software parse** and re-runs the whole document through the LLM (`:141`):

```python
contact = software_result.get("contact", {})
if not contact.get("phone") or not contact.get("email"):
    is_complete = False
```

What's thrown away when that fires: the categorized skills, `metadata` (page count, columns,
tables), `quality`, the coverage audit, `section_order`, and every correctly-parsed field. Replaced
by a single LLM call whose `formatting_metadata` is then hardcoded to all-`False`.

Many resumes legitimately omit a phone number. Those users get the degraded path every time, and
the ATS then scores them as having a perfect single-column layout regardless of their actual PDF.

## 0.4 Quality signals are computed, then discarded

`resume_parser/pipeline.py:151-161` computes:

```python
output["quality"] = quality_scorer.score(output)          # completeness + quality + flags
missed_info, coverage_ratio = coverage_diff.audit_coverage(raw_text, output)
```

`quality_scorer.py` (365 lines) scores contact/experience/education/skills completeness, bullet
quality, experience depth, skill diversity and date consistency. `coverage_diff.py` (227 lines)
measures how much of the raw text made it into the structure.

**`parse_resume_hybrid` uses none of it.** Step 2 (`resumes.py:113`) reimplements a cruder audit by
hand — substring checks like `"certification" in raw_text` — and the Step 4 flat mapping
(`:186-243`) doesn't carry `quality` into the output at all.

You already have the parse-confidence signal the ATS plan says you need to build. It's computed on
every call and dropped on the floor.

## 0.5 Layout detection exists three times and reaches the scorer zero times

| Implementation | Lines | Detects | Consumed by |
|---|---|---|---|
| `resume_parser/extractor.py:_detect_layout` | ~120 | columns (x-projection), tables, scanned, pageCount | pipeline `metadata` |
| `services/text_extraction.py:check_pdf_layout` | ~70 | columns (x-projection), tables, scanned | **discarded unless scanned** |
| `ats/layout_probe.py` | 45 | **nothing — hardcoded stub** | the ATS scorer |

`extractor.py` even does column-*aware extraction* (`_extract_columnar_page`, `:119`), reading left
column top-to-bottom then right — the hard part, already solved.

Meanwhile `check_pdf_layout` is called at `resumes.py:91`, its result is checked for one boolean
(`is_scanned_pdf`), and the rest is dropped. And `ats/layout_probe.py:12-20` returns
`page_count=1, has_columns=False, is_scanned=False` — which is why ATS parseability is exactly
100.0 for all 120 corpus resumes and the 30-point penalty ledger can never fire.

**This corrects Phase 4 of the ATS plan: that work is mostly wiring, not building.**

## 0.6 Data-loss bugs

1. **Scanned PDFs lose every page after the first.** `resumes.py:94-96` renders all pages, then
   parses `images[0]` only. A two-page scanned resume silently loses half its content.
2. **Links are only scanned in the first 1,000 characters** (`resume_parser.py:115`). Resumes with
   contact details in a footer or sidebar lose their LinkedIn/GitHub.
3. **The certification regex injects junk.** `resume_parser.py:269-279` scans the last 2,000 chars
   for `([A-Za-z][\w ]{3,50})\s+(?:certificate|certification|course)\b` and appends matches with no
   validation. A bullet reading "…completed the onboarding course" becomes a certification.
4. **`_raw` is stored inside `structured_json`** (`:243`). The full resume text is duplicated into
   the JSON blob for every version — schema pollution and storage bloat.
5. **`validate_phase1_extraction` warnings go to logs only** (`:284`). The user is never told their
   resume parsed badly, and no caller can react.

## 0.7 No parser tests, no parser eval

`find backend -name "test*.py"` returns ATS tests, builder endpoint tests, and scratch files. There
is **no test for the parser** — the component every other component depends on. No fixture PDFs, no
field-level accuracy measurement, no regression gate.

This is the same failure mode as the ATS eval harness: sophisticated machinery with nothing
asserting it still works.

---

# Part 1 — Fix plan

Eight phases. Phases 0–2 unblock the ATS work and should ship together.

### Phase 0 — Freeze the contract (~1 day) — *blocks ATS Phase 0*

1. **Write `schemas/resume.py`** — one Pydantic model, the single source of truth. Canonical
   spelling (production wins): `bullet_points`, `start_date`, `end_date`, `graduation_date`,
   `cgpa_or_percentage`. Decide `skills` once — recommend `{all: [str], byCategory: {str: [str]}}`
   since two of three paths already emit it and the builder UI needs categories.
2. **Every exit path of `parse_resume_hybrid` returns that model.** Not a dict — the validated
   model. A path that can't fill a field leaves it null; it never changes shape.
3. **Generate the TypeScript types from it** so `frontend/app/lib/resumeSchema.ts` can't drift.
   `resumeSchema.ts:57,60` currently mixes `start_date` with `bullet_points` correctly but declares
   `skills: SkillItem[]`, which no path emits.
4. **Add a contract test** asserting all three paths produce the same key set on the same fixture.
5. **Write a migration** for existing `structured_json` rows, and strip `_raw` into its own column.

**Acceptance:** all three paths validate against one model; `doc_builder` reads canonical keys and
sees the true bullet count.

### Phase 1 — One normalization boundary (~1 day)

Normalization currently happens in three places: `agents/resume_parser.py` (`_normalize_*`),
`resume_parser/normalizer.py`, and inline inside `parse_resume_hybrid`'s Step 4 mapping.

1. **Collapse into one `normalize_to_canonical(raw_parse, source)` function** that every path calls
   last. Delete the inline mapping at `resumes.py:186-243`.
2. Move the string-to-array bullet recovery, contact-link absorption and cert list coercion into it.
3. **Keep normalization pure and testable** — dict in, model out, no I/O.

### Phase 2 — Field-level healing instead of all-or-nothing (~2 days)

Replace the binary `is_complete` with per-field confidence.

1. **Use `quality_scorer`'s output** as the audit rather than the hand-rolled substring checks.
   Per-section completeness scores already exist (`_score_contact_completeness`,
   `_score_experience_completeness`, …).
2. **Heal only what's weak.** If contact is incomplete but experience parsed well, send *only the
   contact block's* source text to the LLM. Keep everything else from the software parse.
3. **Merge, don't replace** — preserve `metadata`, `quality`, `section_order` and coverage from the
   software run regardless of which fields were healed.
4. **Never hardcode `formatting_metadata`.** If the software parse didn't run, call
   `check_pdf_layout` directly rather than asserting all-`False`.

**Acceptance:** a resume missing only a phone number retains its real layout metadata and
categorized skills.

### Phase 3 — Surface parse confidence (~1 day)

1. **Include `quality` and `coverage_ratio` in the parser's return** and persist them on
   `ResumeVersion`.
2. **Return them from the API** so the ATS layer and the UI can both react.
3. **Define a low-confidence threshold** below which the ATS refuses to present an authoritative
   score — showing "we may have misread your resume, please review" plus the parsed structure for
   correction. This is the honest counterpart to the ATS plan's "no silent degradation" rule.
4. **Promote `validate_phase1_extraction` warnings** from log lines to structured fields on the
   response.

### Phase 4 — Unify layout detection (~1 day) — *replaces most of ATS Phase 4*

1. **Delete two of the three implementations.** Keep `extractor._detect_layout` (the most complete —
   it has pageCount and feeds column-aware extraction). Make `check_pdf_layout` a thin wrapper or
   remove it.
2. **Rewrite `ats/layout_probe.py` to read persisted layout facts** rather than re-probing. The
   parser already opened the PDF; the scorer shouldn't open it again.
3. **Persist `LayoutFacts` on `ResumeVersion` at upload** so re-scoring needs no file access.
4. **Extend the fact set** with what the ATS ledger wants and the extractor doesn't yet produce:
   embedded fonts, header/footer text by position, image presence.

**Acceptance:** ATS `parseability` shows a real distribution; the penalty ledger fires on a genuine
three-page two-column PDF.

### Phase 5 — Fix the data-loss bugs (~1 day)

1. **Vision path: parse every page**, then merge. `resumes.py:94` currently drops page 2+.
2. **Scan the whole document for links**, not `raw_text[:1000]`.
3. **Gate the certification regex** on section context — only apply within a certifications section,
   or drop the regex entirely and rely on the LLM, which the prompt already instructs thoroughly.
4. **Move `_raw` out of `structured_json`** into its own column.
5. **Handle multi-page non-scanned PDFs explicitly** — confirm `_extract_from_pdf` concatenates
   pages in reading order for columnar layouts across page boundaries.

### Phase 6 — Parser eval harness (~3 days) — *the ceiling item*

This is the single highest-value item in either plan. Everything downstream inherits parse errors,
and §0.2 shows how invisibly they fail.

1. **Build a fixture set of 50+ real resume PDFs** spanning: single/multi-column, 1/2/3 pages,
   scanned, DOCX, Indian formats (CGPA, 10th/12th boards, photo, DOB), non-tech roles, career
   changers, and deliberately broken files.
2. **Hand-label ground truth per file** — every field, every bullet.
3. **Measure field-level accuracy**: precision/recall per field, bullet-count recall (did we lose
   bullets?), date-parse accuracy, coverage ratio. Report per file type.
4. **Gate CI on it.** Fail the build on regression, exactly as `ATS_V3_CALIBRATION_PLAN.md` Phase 3
   does for scoring.
5. **Track software-path vs AI-path accuracy separately** so you know whether the LLM fallback is
   actually helping or just costing money.

**Do not skip the labelling.** Without ground truth this is unmeasurable, and unmeasured parsing is
why the schema mismatch survived this long.

### Phase 7 — Cost, latency, determinism (~2 days)

1. **Measure the software-path hit rate.** If the phone-number rule (§0.3) is forcing most resumes
   to the LLM, Phase 2 alone is a large cost saving.
2. **Cache by file hash** — the same upload should never be parsed twice.
3. **Pin a `parser_version`** on every stored parse, alongside the ATS `scoring_version`. Reparsing
   under a new version must be explicit, never silent.
4. **Set a latency budget** and measure the vision path separately — it's the slowest and now, per
   Phase 5, multi-page.

---

# Part 2 — How this changes the ATS plan

| `ATS_V3_CALIBRATION_PLAN.md` | Revision |
|---|---|
| **Phase 0** (schema contract) | Becomes a *consumer* of this plan's Phase 0. Fix the contract at the source, not in `doc_builder`. The compatibility shim is still worth having as a tripwire. |
| **Phase 4** (make layout real) | Mostly redundant — the detection exists in `extractor.py`. Reduces from 1–2 days of building to ~1 day of wiring (this plan's Phase 4). |
| **Part 3, item 1** (parser eval) | Promoted from "future consideration" to this plan's Phase 6, and it should be scheduled before ATS Phase 8 calibration. There is no point fitting a curve to scores derived from unmeasured parses. |
| **Part 3, item 3** (determinism) | Extends to `parser_version`, not just `scoring_version`. |
| **Part 3, item 6** (India-specific) | The parser prompt already handles ICSE/CBSE boards, "Intermediate / +2", and CGPA-vs-percentage (`resume_parser.py:47-51`). That's further along than the ATS side. The gap is that `doc_builder` reads `gpa.raw` and drops all of it. |

**Revised order across both plans:**

```
PARSER P0 (contract) ──► PARSER P1 (normalize) ──► ATS P0/P1 (consume + hotfix)
        │                                                      │
        └──► PARSER P2 (healing) ──► PARSER P3 (confidence) ───┤
                                                               │
PARSER P4 (layout wiring) ──────────────────────────────────► ATS P3 (eval gate) ──► ATS P5 (checks)
                                                               │
PARSER P6 (parser eval) ─────────────────────────────────────► ATS P8 (calibrate)
```

Parser Phases 0–1 are the critical path for everything. Parser Phase 6 gates ATS Phase 8.

---

# Part 3 — Open questions

1. **Which `skills` shape wins?** `{all, byCategory}` serves the builder UI and two of three paths
   already emit it, but the LLM prompt (`resume_parser.py:34`) explicitly asks for a flat array and
   `resumeSchema.ts:194` declares `SkillItem[]`. Three answers in one codebase — pick one before
   Phase 0.
2. **Is the software pipeline good enough to be primary?** It's 1,950 lines with real quality
   scoring. Phase 6's eval will answer whether the LLM fallback earns its cost, but the answer
   changes the architecture: if the software path is strong, the LLM becomes a targeted healer
   (Phase 2); if it's weak, consider LLM-first with the software parse as validation.
3. **Should the user be able to correct a bad parse?** Currently there's no path from "we misread
   your resume" to a fix. A confirm-and-edit step after upload would both improve data quality and
   generate labelled training data for Phase 6 — the fixtures build themselves.
4. **Vision path for multi-page: merge or per-page-then-stitch?** Per-page parsing risks splitting a
   role across a page boundary into two entries. Worth deciding with a fixture.
