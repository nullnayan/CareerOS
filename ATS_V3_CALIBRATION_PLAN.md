# ATS v3 — Diagnosis, Calibration & Premium-Parity Plan

**Status:** draft v2 · **Scope:** `backend/ats/**`, `backend/ats_fixers/**`, `backend/api/ats.py`, `frontend/app/ats/page.tsx`
**Supersedes calibration sections of:** `ATS_SCORING_ENGINE_PLAN.md`

Three reported symptoms — inflated scores, JD score not rendering, no seniority selector — are all
confirmed. Investigating them surfaced a fourth problem that is more serious than any of the three:
**the scoring engine reads a different resume schema than the parser produces**, so on real user
data it scores almost nothing. Evidence below is measured, not inferred.

---

# Part 0 — Diagnosis

## 0.1 THE CRITICAL BUG — schema contract mismatch

`backend/agents/resume_parser.py:41` and `frontend/app/lib/resumeSchema.ts:57,60` establish the
production resume schema:

```
experience[*].bullet_points   experience[*].start_date   experience[*].end_date
```

`backend/ats/doc_builder.py:50,53` reads:

```python
start_date = exp_dict.get("startDate", "")     # never present
end_date   = exp_dict.get("endDate", "")       # never present
entry_bullets_str = tuple(exp_dict.get("bullets", []))   # never present
```

Same resume, two key spellings, measured through the real engine:

| | bullets seen | years exp | band | headline |
|---|---|---|---|---|
| **Production keys** (`bullet_points`, `start_date`) | **0** | **0.0** | student | **65.3** |
| Corpus keys (`bullets`, `startDate`) | 3 | 5.0 | mid | **91.3** |

The consequences cascade through everything:

1. **`doc.text.bullets` is empty for every real resume.** Only *project* bullets survive, because
   projects genuinely use the `bullets` key. So IMPACT — the heaviest dimension at 0.18–0.30 —
   plus `bullet_length` and `punctuation_consistency` all evaluate an empty or near-empty set.
2. **Experience bullet text never reaches `full_text`.** `doc_builder.py:75` appends bullet text
   inside a loop over an empty tuple. Since `checks/match.py:19` matches JD keywords against
   `doc.text.full`, **the single richest keyword source in the resume is invisible to JD matching.**
   Confirmed: `'40%' in doc.text.full` → `False`.
3. **`years_experience` is always 0.0**, so `band_from_parsed_dates` returns `student` for every
   user, `compute_years_experience` is dead weight, and the GROWTH/AUTHENTICITY date checks
   cannot function.
4. **The eval corpus uses the corpus spelling**, so `eval/corpus/data/*.json` exercises a code path
   production data never takes. Every calibration metric you have — `BASELINE_v2.md` included —
   measures a schema that does not exist in your product.

Nothing else in this plan matters until this is fixed. Calibrating a scorer that can't see bullets
is fitting a curve to noise.

**Related contract gaps in the same file:**
- `full_text` (`doc_builder.py:153-162`) omits `contact.phone`, `contact.location`,
  `project.technologies`, and education field/institution detail. Skills listed only in a project's
  tech stack are invisible to JD matching.
- `education` reads `endYear` and `gpa.raw`; verify both against the parser's actual output.
- `skills` (`:130`) assumes a list. `api/ats.py:246-261` handles skills as a **dict** of category →
  list (`technical`, `languages`, `tools`, `frameworks`). If a dict ever reaches `doc_builder`,
  it iterates the dict's *keys* and your skill names become "technical", "languages".
- `domain` is hardcoded `"software"` (`:12`) and never inferred.

## 0.2 Measured inflation

Ran the current engine over the 120-resume labelled corpus (`eval/corpus/labels.jsonl`):

| Metric | v3 today | v2 recorded (`BASELINE_v2.md`) | Target |
|---|---|---|---|
| Output range | **59.8 – 91.2** | — | 5 – 98 |
| Ground-truth range | 0 – 100 | 0 – 100 | — |
| Mean bias (pred − truth) | **+12.2** | — | ±3 |
| MAE | 22.7 | 22.2 | < 10 |
| Spearman ρ | **0.429** | 0.512 | > 0.80 |
| Distinct parseability values across 120 resumes | **{100.0}** | — | continuous |

**v3 ranks worse than the v2 engine it replaced.** This is a regression, not an offset. And the
engine cannot emit a low score — direct probes:

| Input | v3 headline |
|---|---|
| `{}` — completely empty resume | **41.0** |
| No contact, no education, no experience, one filler line | **40.7** |
| Two junk bullets, no education | **51.7** |

An empty JSON object scores 41/100. The usable band is compressed into ~60–92, which is exactly
why a resume Resume Worded rates 89 comes out at 94 here.

## 0.3 Why the scores are inflated — six structural causes

**A. Free points for absent checks.** `scoring/scorer.py:59` returns `1.0` when no check applies
to the band. With `DISABLED_CHECKS_BY_BAND` (`rubric.py:71`), students are gifted GROWTH and part
of STRUCTURE at full marks.

**B. Pass-unless-broken checks.** 11 of 14 non-JD checks initialise `score = 1.0` and only deduct
on a triggered condition. STYLE, STRUCTURE, FORMATTING, AUTHENTICITY and GROWTH — ~60% of total
weight — are near-automatic full marks. Only `quantified_bullets` and `bullet_length` are
genuinely continuous, and per §0.1 both currently see zero bullets.

**C. Layout probing is a stub, so the penalty ledger is dead code.** `layout_probe.py:12-20`
hardcodes `page_count=1`, `has_columns=False`, `is_scanned=False`; `api_adapter.py:61` calls
`probe_layout(None)`, so the PDF is never opened. Therefore:
- `parseability` is exactly `100.0` for all 120 corpus resumes → `parse_gate` (`scorer.py:134`) is
  always `1.0` and does nothing.
- Every predicate in `scoring/ledger.py:5-11` reads a hardcoded-false fact. **The entire 30-point
  penalty ledger can never fire.**
- `PageCountCheck` always sees 1 page. FORMATTING (0.14–0.18 weight) is a free dimension.

**D. Thin check coverage.** 16 checks, ~2 per dimension. Resume Worded runs ~30. Missing entirely:
spelling, grammar, weak/filler verbs, verb repetition, achievement-vs-duty phrasing, summary
quality, buzzword density, date gaps, LinkedIn/location presence, section ordering,
bullets-per-role.

**E. Naive check internals.** `checks/impact.py` `ActionVerbsCheck` counts a bullet as action-led
if its first word ends in `ed`, `ing` or `s`. "Skills", "Various", "Was", "Systems",
"Responsibilities" all pass — inflating the heaviest dimension.

**F. Rubric thresholds computed then ignored.** `get_rubric()` returns `metric_bullet_target`,
`action_verb_target`, `max_pages`, `min_words`, `max_words`, `max_bullets_per_role`,
`leadership_expectation` — **no check reads any of them.** Checks hardcode 800/200/30 words and 2
pages regardless of band. Band differentiation comes only from weights and disabled-check sets,
which is why bands barely separate.

## 0.4 Why the JD score doesn't show up — five bugs

**Bug 1 — `/ats/analyze-text` raises `NameError` on every call.** `api/ats.py:539,541`:

```python
result = run_v3_scoring(resume, jd_text)   # neither name is defined in this scope
```

The function has `structured_json` and `request.job_description`. Both branches crash → 500
unconditionally. The frontend calls this whenever text is pasted rather than a file uploaded
(`page.tsx:313`). That path has never returned a score.

**Bug 2 — the JD is silently discarded.** `ats/jd/fallback.py:27` returns `None` when fewer than 5
ontology skills appear in the JD — and `ontology/skills.yaml` contains **21 skills**. On `None`:
`score_resume` skips all MATCH checks (`scorer.py:122`); `convert_to_api_response(...,
is_targeted=bool(jd))` returns `baseline_score` instead of `match_score`; keyword lists are absent.
The frontend (`page.tsx:444`, `match_score ?? baseline_score`) renders the baseline number, so the
user sees *a* score but never a *match* score. Silent degradation, no error. Compounded by §0.1 —
even when extraction succeeds, matching runs against text missing all experience bullets.

**Bug 3 — half the targeted response is never produced.** `convert_to_api_response`
(`api_adapter.py:38-54`) returns only `score_breakdown`, `issues`, and one score key. `api/ats.py`
then `.get()`s `missing_keywords`, `matched_keywords`, `bullet_point_analysis`,
`premium_breakdown`, `summary` — all permanently empty. Those UI sections render blank in both
modes.

**Bug 4 — `/ats/improve/apply` 500s.** `api/ats.py:388` calls `run_ats_scorer`, never imported in
that module (it lives in `services/ats_scorer.py`). The `try` swallows the `NameError`; `:406` then
reads unbound `improved_ats` and raises uncaught.

**Bug 5 — hardcoded JD title.** `api_adapter.py:71` passes the literal `"Unknown Title"`, so
`TitleMatchCheck` can never pass even when extraction succeeds.

## 0.5 The scorer and the suggestion engine are two disconnected systems

`backend/ats_fixers/` contains 12 fixers — `grammar`, `buzzwords`, `readability`, `dates`,
`education`, `communication`, `summary`, `length_depth`, `bullet_consistency`, `quantify_impact`,
`ats_keywords`, `unnecessary_sections`. Several implement checks the scorer **does not have**
(grammar, buzzwords, readability).

But `ats_fixers/dispatcher.py:36-52` ignores the score entirely. Its own comments admit it:

```python
# ats_scorer output: contact_completeness, section_completeness, ...
# We will map based on the issues found, or we can just run the fixers if the related score is low.
# For now, let's just use a direct map or run them all if mode="auto_improve".
categories_to_run = AUTO_IMPROVE_SAFE   # i.e. all of them, always
```

Consequences, and this is the core premium-parity gap:

- **Suggestions don't correspond to the score.** The user is shown a grammar fix, but grammar isn't
  scored — fixing it moves the number by zero.
- **Score findings don't produce fixes.** A `quantified_bullets` finding has no fixer routed to it.
- **"+X points" is not computable.** Nothing links a suggestion to a score delta.
- **Duplicated logic in two places** that will drift apart (already has).

Resume Worded's actual product is not the number — it's *this loop*: every point lost maps to a
named fix, every fix maps to a point gain. You have both halves and no bridge.

## 0.6 Why there's no beginner/intermediate/pro step

`users.career_level` exists (`db/models.py:34`, migration `2a7b54366447`) and `api_adapter.py:64`
reads it — but **nothing anywhere writes it**. `grep -rn career_level` returns only the model, the
migration, and the read. So `band` falls to the hardcoded default `"entry"` (`api_adapter.py:63`)
for every user. A student is penalised for missing formal experience; a director is graded on GPA.

Secondary: `profile.py:92` takes `max(declared, inferred)` — users can claim *up* but never *down*.
A career-changer with 10 years in another field cannot be scored as entry-level, which is exactly
what they need. (Currently moot, since §0.1 forces `inferred = student` for everyone.)

## 0.7 UI defects found while tracing

- `score_breakdown` includes `version` (a string) and `match`/`role_fit` (`None` in baseline).
  `page.tsx:886` maps every entry to a `/100` `<ScoreBar>` → renders "v3.0/100" and "null/100".
- `issues` (`page.tsx:761`) and `suggestions_created` (`:951`) are rendered as two separate
  sections, but `api/ats.py` builds the second *from* the first. The user sees every finding twice.
- `ANALYZE_STEPS` (`page.tsx:283`) cycles fake progress text on a 4s timer, unrelated to actual
  backend progress.

---

# Part 1 — Fix plan

Nine phases. Phase 0 is the blocker; nothing downstream is meaningful without it.

### Phase 0 — Fix the schema contract (blocker, ~1 day)

1. **Define one canonical schema** as a Pydantic model — the single source of truth shared by
   parser, doc_builder, fixers, and frontend types. Pick `bullet_points` / `start_date` /
   `end_date` (production spelling) and migrate the corpus, not the product.
2. **`doc_builder.py`** — read the canonical keys. Add a compatibility shim that accepts both
   spellings during migration but **logs a warning** on the legacy path so drift is visible.
3. **Add a fail-loud contract assertion.** If a resume has ≥1 experience entry and
   `len(doc.text.bullets) == 0`, that is a parse failure, not a zero score. Raise or flag; never
   silently score it.
4. **Fix `full_text` composition** — include phone, location, project technologies, education
   institution/degree/field, and certification names.
5. **Migrate `eval/corpus/data/*.json`** to canonical keys and re-run the baseline. Every number in
   `BASELINE_v2.md` is currently untrustworthy.
6. **Handle dict-shaped `skills`** in `doc_builder`, matching the tolerance `api/ats.py` already has.

**Acceptance:** a real parsed resume yields `len(doc.text.bullets) == ` its true bullet count;
`years_experience` is non-zero for a dated resume; experience bullet text appears in `doc.text.full`.

### Phase 1 — Stop the bleeding (hotfix, ~half a day)

Pure bug fixes, no scoring changes, shippable independently.

1. **`api/ats.py:515-604`** — rewrite `analyze_text` to build a real resume object and pass
   `request.job_description`. Delete the undefined `resume` / `jd_text` references.
2. **`api/ats.py:296`** — import `run_ats_scorer`, or better switch `improve_apply` to
   `run_v3_scoring`. Initialise `improved_ats = {}` before the `try`.
3. **`jd/fallback.py:27`** — never return `None`. Return a `JobTarget` with whatever was found plus
   an `extraction_confidence` field.
4. **`api_adapter.py`** — add `jd_extraction_status` (`ok | low_confidence | failed`); always emit
   `match_score` when a JD was supplied. **No silent mode flips.**
5. **`api_adapter.py:38-54`** — populate `matched_keywords` / `missing_keywords` from the
   `keyword_match` check's `evidence` (already computed); populate `bullet_point_analysis` from
   bullet-anchored findings. Move `version` out of `score_breakdown` into a `meta` key.
6. **`page.tsx:886`** — filter `score_breakdown` to numeric values before rendering bars.
7. **Remove the duplicate suggestions section** (`page.tsx:951`), keeping `issues`.

### Phase 2 — Seniority capture (~1 day)

1. **API** — `PATCH /users/me/profile` accepting `career_level ∈ {student, entry, mid, senior, exec}`.
2. **Frontend** — a required step before first analysis, persisted so it's asked once, editable later:

   | UI label | Band | Definition shown to user |
   |---|---|---|
   | Student / Fresher | `student` | No full-time role yet; internships and projects |
   | Beginner (0–2 yrs) | `entry` | First job or two |
   | Intermediate (2–6 yrs) | `mid` | Owns features end to end, no reports |
   | Pro / Senior (6–12 yrs) | `senior` | Leads projects or people |
   | Leadership (12+ yrs) | `exec` | Org-level ownership |

3. **`profile.py:77-99`** — replace `max(declared, inferred)` with bounded reconciliation: allow ±1
   band freely; beyond that clamp and attach an informational finding. **Career-changers must be
   able to declare down.**
4. **`api_adapter.py:63`** — drop the `"entry"` default; infer from parsed dates when unset.
5. **Also capture target role and target industry** here. Both are needed for Phase 6 (archetype
   scoring) and are cheap to collect in the same step.

**Acceptance:** the same resume scored as `student` vs `senior` yields materially different scores
and different findings.

### Phase 3 — Make the eval harness a gate (~1 day, do this BEFORE Phase 5)

`eval/test_v3.py` scores the corpus, prints five rows, and asserts only that the list is non-empty.
It cannot fail on a calibration regression — which is why ρ fell from 0.512 to 0.429 unnoticed.

1. Rewrite to mirror `test_baseline.py`: load labels, compute Spearman + MAE overall and per band,
   write `BASELINE_v3.md`.
2. **Assert thresholds** — fail the build if ρ < 0.80, MAE > 10, or the empty-resume probe > 10.
3. **Golden-file tests** — fixed resumes with locked expected scores, so any scoring change forces
   an explicit reviewed diff.
4. **Contract test** — the Phase 0 assertion, run over every corpus file.
5. **Per-check contribution report** — which checks actually move the score, which are inert.

### Phase 4 — Make layout real (~1–2 days)

Until this lands, ~30% of the rubric is unfalsifiable.

1. **`layout_probe.py`** — implement with `pdfplumber`: real page count; column detection via
   x-coordinate clustering of word boxes; `find_tables()`; scanned detection via empty text layer;
   embedded fonts; header/footer text by position band; image presence.
2. **Thread the PDF through** — `run_v3_scoring` must accept a path or bytes. Persist layout facts
   on `ResumeVersion` at upload so re-scoring doesn't need the original file.
3. **Handle the no-PDF case honestly.** Builder-generated and pasted-text resumes have no PDF. Set
   `layout_facts_available=False`, skip FORMATTING, and **redistribute its weight** across other
   dimensions — do not award it free. Surface "formatting not evaluated" in the UI.
4. Make `parseability` continuous rather than the current 3-value ladder (`scorer.py:111-116`):
   factor in tables, contact-in-header, non-embedded fonts, image-only sections.

### Phase 5 — Rebuild the check suite (~4–6 days, the bulk)

Target ~32 checks. Two non-negotiable rules:

- **No check may return 1.0 by default.** Score must be earned from evidence — a ratio or count
  against a band threshold — never awarded for absence of a defect.
- **Every check reads thresholds from `rubric`.** Wire up the seven values `get_rubric()` already
  computes and nothing consumes.

| Dimension | Add (existing in parens) |
|---|---|
| IMPACT | `weak_verbs`, `verb_repetition`, `achievement_vs_duty`, `metric_quality` (distinguish "50,000 users" from "3 meetings"), `scope_signals` — *(quantified_bullets, action_verbs)* |
| BREVITY | `bullets_per_role`, `word_count_vs_band`, `summary_length` — *(resume_length, bullet_length)* |
| STYLE | `spelling`, `grammar`, `filler_words`, `buzzword_density`, `passive_voice` — *(personal_pronouns, punctuation_consistency)* |
| STRUCTURE | `linkedin_present`, `location_present`, `section_order`, `summary_specificity`, `education_completeness`, `skills_organisation` — *(contact_completeness, section_presence)* |
| FORMATTING | `column_layout`, `tables_used`, `contact_in_header_footer`, `font_embedding`, `special_characters`, `bullet_glyph_consistency` — *(page_count, date_format_consistency)* |
| AUTHENTICITY | `date_gaps`, `date_overlaps`, `title_inflation`, `unverifiable_superlatives` — *(duplicate_bullets, keyword_stuffing)* |
| GROWTH | `title_trajectory`, `tenure_pattern`, `increasing_scope` — *(leadership, career_progression)* |

Also: rewrite `ActionVerbsCheck` against a real ~1,200-verb lexicon; **delete the free-points rule**
at `scorer.py:58-59` and renormalise remaining dimension weights to sum to 1.0 instead.

**Reuse, don't rewrite:** `ats_fixers/grammar.py`, `buzzwords.py`, `readability.py`, `dates.py` and
`education.py` already contain detection logic for several of these. Extract the detection half
into checks; keep the rewrite half in the fixers (see Phase 7).

### Phase 6 — Rebuild targeted/JD mode (~3 days)

1. **Expand the ontology from 21 to 1,500+ skills.** Highest-leverage single change for match
   quality. Seed from **ESCO** or **O\*NET** (both free, both cover non-tech roles), plus a curated
   tech layer. Each entry needs aliases and a `kind` (`hard | soft | tool | certification | domain`).
2. **Implement the LLM extraction path** that `jd/extract.py:17` marks TODO — title, normalised
   title, required vs. preferred skills, min years, degree, seniority. Replace the in-process
   `_MOCK_CACHE` dict (unbounded, dies on restart) with a real keyed cache.
3. **Use the extracted title** instead of `"Unknown Title"` (`api_adapter.py:71`).
4. **Implement `MATCH_WEIGHTS`.** `rubric.py:37-45` defines seven weighted components and the table
   is imported but never used — `_run_dimension_checks` averages MATCH checks equally. Build one
   check per component and weight properly.
5. **Semantic matching, not substring.** `checks/match.py:22` uses `kw.lower() in text_lower`, so
   "React" matches inside "Reactive" and "Go" inside "Django". Match canonicalised ontology IDs with
   word-boundary regex, then embedding similarity for out-of-ontology terms.
6. **Weight by requirement.** `JDKeyword.required` exists but is hardcoded `False`
   (`fallback.py:23`). A missing must-have should cost far more than a missing nice-to-have.

### Phase 7 — Bridge the scorer and the fixers (~3 days) — *the premium-parity phase*

This is what turns a score into a product.

1. **One finding taxonomy.** Every check emits a `finding_code`. Every fixer declares which codes it
   can repair. `dispatcher.py` routes by code instead of running all twelve blindly.
2. **Score-delta simulation.** For each proposed fix: apply to a copy of the resume JSON, re-score,
   report the true delta. Show "+3.2 points" per suggestion — computed, never guessed.
3. **Rank suggestions by delta ÷ effort**, not by severity. Highest-leverage fix first is the entire
   UX of a premium tool.
4. **Close the loop.** After applying, re-score and show before → after with the delta attributed
   per change.
5. **Coverage assertion in CI**: every finding code a check can emit must have at least one fixer,
   or an explicit `no_auto_fix` declaration. No orphan findings.

### Phase 8 — Recalibrate (~2 days, last)

1. **Re-label the corpus.** Current labels have a mean of exactly 60.0 in four of five bands —
   almost certainly generated, not judged. You cannot calibrate to a degenerate target. Re-label by
   hand or regenerate with real spread, and add ~40 deliberately bad resumes (scanned, three-column,
   no metrics, typo-ridden) to anchor the low end.
2. **Set anchors.** Empty resume < 10 (from 41 today). Strong metric-dense resume ≥ 90.
3. **Fit a monotonic calibration curve** so the prediction distribution matches labels. Monotonic
   preserves ranking and guarantees improvements always raise the score.
4. **Cross-check against Resume Worded** on 15–20 real resumes across the range. Target ±5 points,
   and — more important — identical ordering.

**Acceptance:** MAE < 10, ρ > 0.80, range spans 5–95, empty resume < 10.

## Sequencing

```
Phase 0 (schema)  ──►  Phase 1 (hotfix)  ──►  Phase 3 (eval gate)  ──►  Phase 4 (layout)
                                    │                                        │
                       Phase 2 (band UI)                          Phase 5 (checks)
                                                                             │
                       Phase 6 (JD/ontology) ──────────────────────►  Phase 7 (bridge)
                                                                             │
                                                                    Phase 8 (calibrate)
```

Phase 0 blocks everything. Phase 3 must precede Phase 5 so the rebuild is guarded. Phase 8 is last
because calibration is meaningless until the checks are honest. Phases 2 and 6 can run in parallel.

---

# Part 2 — Frontend rebuild (`app/ats/page.tsx`)

The current page is a 1,381-line component that renders findings twice, shows fake progress, and
presents the score as a verdict rather than a starting point. What follows is a redesign of how
results and suggestions surface. No implementation here.

## 2.1 Structural changes first

- **Split the component.** 1,381 lines in one file with ~20 `useState` hooks. Extract:
  `ScoreHeader`, `BreakdownPanel`, `FindingsList`, `FindingCard`, `KeywordPanel`,
  `ImproveDrawer`, `DiffViewer`. Move analysis state into a reducer.
- **Delete the duplicate list.** `issues` and `suggestions_created` are the same data
  (`api/ats.py` builds one from the other). Keep one.
- **Replace fake progress** (`ANALYZE_STEPS`, 4s timer) with real backend stages streamed over SSE,
  or a single honest indeterminate spinner. Fake steps that don't match reality read as broken when
  analysis is fast, and as frozen when it's slow.
- **Persist results.** Currently analysis lives in `TaskContext` and dies on refresh. Store scored
  runs so users can revisit and compare.

## 2.2 Score presentation — three fixes

1. **Show the band, not just the number.** "72 — Good" alone invites the "why not 85?" question.
   Show the distance to the next band and what closes it: *"72 · Good — 6 points from Excellent,
   mostly from unquantified bullets."*
2. **Never show a bare number for a degraded run.** If §0.1's contract assertion fires, or layout
   facts are unavailable, or JD extraction was low-confidence, the score must be visibly caveated —
   *"Formatting not evaluated (pasted text)"* — not silently rendered as if complete.
3. **Add percentile context** once you have corpus volume: *"Top 30% of Entry-level Software
   resumes."* A raw number has no meaning; a rank does. This is table stakes for premium tools.

## 2.3 The findings list — the main redesign

Today findings are a flat severity-sorted list with no path to action. Replace with:

**Sort by score impact, not severity.** With Phase 7's delta simulation, each card leads with a
computed `+3.2` chip. Users fix top-down and watch the number climb. This single change is most of
the perceived quality difference between a free and a premium tool.

**Group by dimension, collapsed by default**, with per-dimension earned/available points. Users
should see "Impact 12/26" and expand only that.

**Each finding card shows:**
- the point delta, computed by simulation
- the offending text, inline, with the exact span highlighted — not a description of it
- the proposed rewrite alongside, as a diff
- **Accept · Edit · Skip** on the card itself
- a one-line *why* ("Recruiters scan for outcomes; this bullet states a duty")
- an anchor link that scrolls the resume preview to the exact line

`Finding.anchor` (section, entry_index, bullet_index) already exists and is populated — nothing
currently uses it. Wire it to a side-by-side resume preview with the finding highlighted in place.
Line-level anchoring is the feature users actually pay for.

**Three states per finding, not two.** Currently accept-or-reject. Add **"Answer to fix"** for
findings that need user input — `quantify_impact` and `ats_keywords` already return questions
(`dispatcher.py`), and the UI has nowhere good to put them. Inline question → answer → generated
rewrite, on the card.

## 2.4 The improve drawer

- **Preview the score before committing.** Show projected score as changes are toggled, live.
- **Batch by category** with select-all-in-category, rather than one flat accept-all.
- **Show what was rejected and why** — `locked_registry.validate_rewrite` (`api/ats.py:327`)
  silently `continue`s on validation failure. The user's accepted change vanishes with no
  explanation. Surface it: *"Skipped — the rewrite changed a company name."*
- **Undo.** `improve_apply` creates a new `ResumeVersion`; expose version history and let users
  revert.

## 2.5 JD / targeted mode

- **Two-column keyword view**: matched (with where each was found) vs. missing (with which section
  should carry it), ordered by JD importance once `required` is populated in Phase 6.
- **Show the extraction confidence.** If the JD parsed poorly, say so — don't render an
  authoritative match percentage over a bad extraction.
- **Separate the two numbers.** Match score and resume-strength score answer different questions and
  should never be collapsed into one figure via `match_score ?? baseline_score` (`page.tsx:444`).

## 2.6 Empty, error and loading states

Every failure currently becomes `alert()` or a red string. Specify per case: parse failure ("we
couldn't read this PDF — it may be scanned"), contract-assertion failure, JD extraction failure,
LLM timeout, rate limit. Each needs a distinct message and a recovery action.

---

# Part 3 — Will this be as good as a premium site?

Honest answer: **Phases 0–8 close the gap on scoring accuracy and get you to rough parity on the
core loop. They do not get you to premium parity overall.** Nine things remain, roughly in order of
how much they matter.

**1. Parse quality is the real ceiling.** Everything downstream inherits parser errors, and §0.1
shows how invisibly that fails. Premium tools invest more in extraction than in scoring. You need a
parser eval set — 50+ real PDFs with hand-labelled ground truth — measuring field-level extraction
accuracy, tracked as its own metric. This is arguably a tenth phase and I'd rank it above Phase 8.

**2. Real ATS emulation.** Jobscan's moat is simulating how *specific* systems (Workday, Taleo,
iCIMS, Greenhouse) actually parse a document — each has different failure modes with tables,
headers and date formats. Generic "ATS-friendliness" is a weaker claim. Research what each vendor's
parser breaks on and encode it per-target.

**3. Determinism and score stability.** Same resume must yield the same score forever, and any
recalibration will move every existing user's number. You need: a pinned `SCORING_VERSION` on every
stored result (the field exists, use it), scores never silently recomputed under a user, and an
explicit migration message when the version bumps. A score that drifts destroys trust faster than a
score that's slightly wrong.

**4. Latency budget.** Premium tools return in under 5 seconds. Your Phase 5 check suite plus Phase
6 LLM extraction will not, unaddressed. Needs a budget per phase, parallel check execution
(`dispatcher.py` already uses a thread pool — the scorer doesn't), and caching keyed on
`(resume_hash, jd_hash, scoring_version)`.

**5. Benchmarking corpus.** Percentiles, "top 30% for this role", industry comparisons — all
require real resume volume with outcome data. Start collecting anonymised scored resumes now, with
consent, because this asset takes months to accumulate and cannot be bought.

**6. India-specific rules — your actual differentiator.** You're targeting Internshala and Unstop.
Indian resume conventions diverge sharply from US tools' assumptions: photos and DOB are common
(and should be flagged for international applications but not domestic), percentage/CGPA instead of
GPA, 10th/12th board marks as expected sections, "Fresher" as a legitimate positioning, notice
period, expected CTC. Resume Worded scores all of this wrong. A locale-aware rubric
(`ontology/locales.yaml` exists but is unused) is a genuine advantage no US incumbent will build.

**7. Outcome feedback.** The strongest scorers learn from which resumes actually got interviews.
Once the automation system from our earlier conversation is applying to jobs, you have that
telemetry natively — and it's the one thing Resume Worded structurally cannot get. Design the
schema for it now even if you don't use it for a year.

**8. Observability.** Bugs 1–5 and §0.1 all share one cause: **silent fallbacks**. `except:
pass`, `.get(x, default)`, returning `None` on failure. A rule worth adopting globally — degraded
results must be labelled degraded, at every layer. Plus structured logging on score distribution,
alerting when the mean shifts, and per-check firing rates so an inert check is visible.

**9. Cost and abuse controls.** Phase 6 puts an LLM on the JD path. Needs per-user rate limits, cost
tracking per analysis, and a cheap deterministic path for repeat scoring.

**Where you'd land:** Phases 0–8 plus items 1, 3 and 4 gets you a defensible product roughly at
parity on core scoring. Items 6 and 7 are where you'd exceed the incumbents for your market — and
both are things they can't easily copy. I'd sequence 1, 3, 4 into the main plan and treat 6 as a
fast-follow, because the Indian-market rubric is worth more to you than closing the last few points
of correlation with a US tool that scores your users wrong anyway.

---

# Part 4 — Open questions

1. **Match Resume Worded's numbers, or its ranking?** Matching numbers means copying their
   harshness curve — a product decision. Recommendation: match ranking tightly, sit 3–5 points
   above them absolute. Rigour without despair, especially for the student segment.
2. **Spelling/grammar dependency.** `language-tool-python` is accurate but needs a Java runtime;
   `pyspellchecker` plus a curated tech allowlist is lighter. Decide before Phase 5. Note
   `ats_fixers/grammar.py` already exists — check what it uses.
3. **Is the corpus trustworthy?** Four of five bands with a ground-truth mean of exactly 60.0
   suggests generated labels. Phase 8 depends on the answer, and Phase 0 requires migrating the
   corpus anyway — do both in one pass.
4. **Keep two systems or merge?** `services/ats_scorer.py` (v2) is still live and referenced from
   `api/ats.py:388`. Decide whether it's deleted at Phase 1 or kept as a fallback, and if kept,
   what routes to it.
