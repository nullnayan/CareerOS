# Prompt for Antigravity — ATS analysis must work with AND without a job description

Copy everything below the line into Antigravity.

---

## Task

In this repo (`careeros`: FastAPI backend in `backend/`, Next.js frontend in `frontend/`), the ATS
scoring engine supports two modes:

- **Baseline mode** — no job description. Scores general ATS friendliness and resume strength.
- **Targeted mode** — a job description is supplied. Additionally scores resume-to-JD match.

The plumbing for both modes exists and mostly works. What is broken is the **boundary between
them**: targeted mode crashes on JDs the extractor can't read, the two modes' scores are collapsed
into one indistinguishable number, and the UI implies a JD is mandatory when it isn't.

Fix it so both modes work end to end, independently, and neither one silently stands in for the
other.

**Do not** redesign the scoring rubric, change dimension weights, add scoring dimensions, or
recalibrate score values. Do not expand `backend/ats/ontology/skills.yaml`. That work is planned
separately in `ATS_V3_CALIBRATION_PLAN.md`. This task is about correctness of the two code paths
only.

## Context you should read first

- `backend/api/ats.py` — `/ats/analyze` (saved resume) and `/ats/analyze-text` (pasted text)
- `backend/ats/api_adapter.py` — `run_v3_scoring`, `run_v3_scoring_from_json`,
  `convert_to_api_response`
- `backend/ats/scoring/scorer.py` — `score_resume`, `_run_dimension_checks`, headline formula
- `backend/ats/checks/match.py` — the four MATCH-dimension checks
- `backend/ats/jd/extract.py`, `backend/ats/jd/fallback.py` — JD extraction
- `backend/ats/scoring/rubric.py` — `MATCH_WEIGHTS`, `BAND_DIMENSION_WEIGHTS`
- `frontend/app/ats/page.tsx` — the ATS page (UI already offers both modes; do not redesign)
- `frontend/app/builder/page.tsx` — the builder's Analyze tab (also calls `/ats/analyze`)
- `frontend/app/lib/api.ts` — `analyzeATS`, `analyzeATSText`, and the `ATSResult` type

## Bugs to fix

### Bug 1 — targeted mode raises `TypeError` when the JD yields no usable keywords

This is the headline bug. It is why supplying a JD appears to break the system.

`backend/ats/scoring/scorer.py`, section 5:

```python
if jd:
    m_s, m_results = _run_dimension_checks(doc, jd, rubric, "MATCH", match_checks)
    if is_archetype:
        role_fit_score = m_s * 100.0
    else:
        match_score = m_s * 100.0
```

`_run_dimension_checks` returns `(None, [])` when no check produced a score — the early-return at
the top of the function. Weight redistribution handles that case for the base dimensions, but MATCH
is scored outside that loop and multiplies `m_s` directly.

All four checks in `backend/ats/checks/match.py` return `score=None` when the JD has no keywords:

- `KeywordMatchCheck` → `if not jd or not jd.keywords: build_result(self.id, None, ...)`
- `HardSkillsCoverageCheck` → same guard, plus `no_hard_skills_in_jd`
- `TitleMatchCheck` → `None` when `jd_title_norm == "unknown title"`
- `SeniorityFitCheck` → `None` when `seniority_not_inferable`

So a JD whose text matches nothing in the ontology, submitted through `/ats/analyze-text` (where the
title is always `"Unknown Title"` — see Bug 3), makes **every** MATCH check return `None`, and
`m_s * 100.0` raises `TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'`. The
endpoint 500s.

Required behaviour:

1. `score_resume` must never multiply a `None` dimension score. Handle `m_s is None` explicitly.
2. When MATCH has no applicable checks, `report.match` must be `None` and the response must say
   why — **not** a fabricated number, and **not** a fallback to the strength score.
3. The headline formula must handle `match_score is None` without treating it as `0`. Scoring a
   resume as if it matched 0% of a JD we could not read is a false negative, not a neutral default.
   When match is unavailable, headline should fall back to the baseline formula (`strength_gated`)
   and the response must flag that it did.
4. `mode` must still report `"targeted"` — the user supplied a JD, and the response must not claim
   otherwise.

### Bug 2 — the two modes' scores are collapsed into one number

`backend/ats/api_adapter.py`, end of `convert_to_api_response`:

```python
if is_targeted:
    response["match_score"] = report.headline
    # Keep baseline_score also available so older frontend code doesn't break
    response["baseline_score"] = report.headline
else:
    response["baseline_score"] = report.headline
```

Two problems:

- `report.headline` is **not** a match score. Per `scorer.py`, in targeted mode it is
  `0.45 * match + 0.55 * strength_gated` — a blend. The frontend labels it "Job match score"
  (`frontend/app/ats/page.tsx` ~line 691). That label is false.
- In targeted mode `baseline_score` and `match_score` are set to the identical value, so the
  frontend's `match_score ?? baseline_score` fallback is a no-op and the genuine resume-strength
  number (`report.strength`) never reaches the client except buried in `score_breakdown`.

Required behaviour — report three distinct, honestly-named numbers in **both** modes where they
exist:

| field | meaning | baseline mode | targeted mode |
|---|---|---|---|
| `baseline_score` | resume strength, JD-independent | number | number (same basis) |
| `match_score` | resume-to-JD match only | absent | number, or `null` per Bug 1 |
| `overall_score` | the blended headline | number (== baseline) | number |

Delete the "older frontend code doesn't break" duplication. Update the callers instead.

### Bug 3 — `/ats/analyze-text` never supplies a JD title, silently losing 15% of the match score

`run_v3_scoring` calls `_infer_jd_title(resume)` (target_role → first experience title). The pasted
-text variant does not:

```python
def run_v3_scoring_from_json(structured_json, job_description=None, band="entry", jd_title=""):
    ...
    jd = extract_job_target(job_description, jd_title or "Unknown Title", band)
```

`backend/api/ats.py` (~line 546) calls it without `jd_title`, so the title is always
`"Unknown Title"`. `TitleMatchCheck` then returns `None` for every pasted-text request, and
`job_title` carries `0.15` in `MATCH_WEIGHTS` — so the paste-text path systematically scores
differently from the upload path on the same resume and JD. It is also one of the four `None`s that
trigger the Bug 1 crash.

Fix: extract the title-inference logic from `_infer_jd_title` into a function that takes the
structured dict (not the ORM object), and call it from both entry points. `run_v3_scoring` can pass
`resume.user.target_role` in as an override.

### Bug 4 — extraction confidence is unusable by the client

`backend/ats/jd/fallback.py` emits `extraction_confidence` as `"ok" | "low"` based on a
5-keyword threshold. `convert_to_api_response` buries it at `meta.jd_extraction_status`, with the
literal `"n/a"` in baseline mode. Three gaps:

1. There is no `"failed"` state. A JD yielding **zero** keywords reports `"low"` — the same value as
   a JD yielding four. Zero keywords is a different event: it means we could not read the JD at all,
   and per Bug 1 it must produce `match_score: null`.
2. `backend/ats/jd/extract.py` (the LLM path) must apply the same contract and vocabulary. Check it
   and align it.
3. The frontend never reads `meta` at all, so a low-confidence extraction is indistinguishable from
   a good one.

Settle on `"ok" | "low_confidence" | "failed"`, set `"failed"` at zero usable keywords, and surface
the value at the **top level** of the response as `jd_extraction_status` (omit the key entirely in
baseline mode rather than emitting `"n/a"`).

### Bug 5 — the frontend reads response fields the API has never returned

`frontend/app/ats/page.tsx` reads:

- `result.premium_breakdown` (~line 672)
- `result.resume_vs_jd_match_pct` (~line 1064)
- `result.jd_matching` (~line 1070)

`convert_to_api_response` returns none of these. The corresponding UI is permanently dead in both
modes. Either populate each from real data or delete the field and the UI that consumes it. Do not
leave dead keys or empty-state defaults that read as "we checked and found nothing".

### Bug 6 — the frontend collapses the two scores

`frontend/app/ats/page.tsx` ~line 444:

```ts
const score = result?.match_score ?? result?.baseline_score ?? null;
```

Match score and resume-strength score answer different questions. With Bug 2 fixed these are
genuinely different numbers, so:

1. In targeted mode, show both, labelled distinctly. Never let one silently stand in for the other.
2. Fix the ~line 691 label so the headline number is described as what it actually is.
3. When `match_score` is `null` (Bug 1), show the baseline result plus a visible note that the job
   description could not be read — not a zero, and not a silently baseline-looking result.
4. Surface `jd_extraction_status`: on `low_confidence` or `failed`, show a visible caveat.
5. `score_breakdown` is rendered as `/100` progress bars — filter to numeric values before
   rendering `<ScoreBar>`, since `match` and `role_fit` are `null` in baseline mode.
6. Update the `ATSResult` type in `frontend/app/lib/api.ts` to match the new response shape.

### Bug 7 — the builder's Analyze tab implies a JD is required

`frontend/app/builder/page.tsx` ~line 1282: the JD textarea is headed "Job Description" with
placeholder "Paste job description here for ATS matching..." and a single "Analyze" button. The call
at ~line 707 already passes `jobDescription || undefined`, so baseline mode works — but nothing tells
the user that, and the analyze tab reads as JD-gated.

Match what the ATS page already does correctly: label the field optional, and switch the button text
between "Analyze against job description" and "Run baseline analysis" based on whether the textarea
has content. Do not redesign the tab beyond this.

Leave `frontend/app/tailor/page.tsx` alone — tailoring genuinely requires a JD, and its 50-character
minimum (~line 637) is correct.

## Cross-cutting rule

**No silent degradation anywhere.** Every bug above is an instance of the same fault: a failure
became a different, plausible-looking result instead of a reported problem. Any path that cannot
produce what was asked for must say so in the response payload. No `except: pass`, no returning
`None` to mean "fall back to something else", no mode or score basis changing without a flag in the
response. While you are in these files, if you find another instance of this pattern, report it even
if you do not fix it.

## Acceptance criteria

`backend/tests/` currently holds only `test_builder_endpoints.py`. Add ATS dual-mode tests covering:

1. `POST /ats/analyze-text` with resume text and **no** JD → 200, `mode == "baseline"`, numeric
   `baseline_score`, no `match_score` key, no `jd_extraction_status` key.
2. `POST /ats/analyze-text` with resume text **and** a keyword-rich JD → 200, `mode == "targeted"`,
   numeric `match_score`, numeric `baseline_score`, `match_score != baseline_score`,
   `jd_extraction_status == "ok"`.
3. `POST /ats/analyze` (saved resume) in both modes → same expectations.
4. **The Bug 1 regression test:** a JD containing zero recognised skills and no inferable title →
   200 (not 500), `mode == "targeted"`, `jd_extraction_status == "failed"`, `match_score is None`,
   and a numeric `baseline_score`. Must not return a match number, must not report
   `mode == "baseline"`.
5. A JD with 1–4 recognised skills → `jd_extraction_status == "low_confidence"`, numeric
   `match_score`.
6. The same resume + JD through `/ats/analyze` and `/ats/analyze-text` produce the same
   `score_breakdown` keys and a `match_score` within a small tolerance — proving Bug 3's title
   asymmetry is gone.
7. `score_breakdown` contains `match` only in targeted mode, and every value in it is numeric.

Also confirm manually, all four combinations: upload a PDF and run baseline; same resume with a JD;
then both again via the paste-text tab. Each must return a score and a correctly labelled mode.

## Constraints

- Python backend, TypeScript/Next.js frontend. Match existing code style in each.
- Do not change dimension weights, thresholds, or check logic in `backend/ats/checks/` beyond what
  Bug 1 requires (returning `None` correctly is already right — the fix belongs in the scorer).
- Do not expand `backend/ats/ontology/skills.yaml`.
- Do not change `backend/ats/scoring/calibration.py` anchors.
- Keep `backend/services/ats_scorer.py` (the older v2 scorer) and
  `backend/agents/ats_analyzer*.py` in place; do not delete them.
- Run the existing test suite and report anything you break.

## When you're done

Report: which files changed, what each acceptance test asserts and its result, and any further
silent-degradation pattern you found but did not fix.
