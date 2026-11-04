# Historical: Tailoring Engine v2 audit

Superseded on 30 October 2026 by `PERSONAL_JOB_AUTOMATION_IMPLEMENTATION_PLAN.md` and the skills-only LaTeX implementation documented in `PERSONAL_MODE_SETUP.md`. The whole-resume agents described below were retired. Do not implement these historical rules in the new tailor.

**Audience:** an AI coding agent picking up this repo.
**Date:** 2026-08-06
**Repo root:** `careeros_scaffold/careeros`
**Reference products:** Jobscan (Match Report + Power Edit), Resume Worded (Targeted Resume), Rezi (real-time content analysis + keyword targeting), Teal (per-application versions + gap tracking), Enhancv.
**Companion doc:** `ATS_SCORING_ENGINE_PLAN.md` — the scorer rebuild. These two systems share the `JobTarget` model, the skill ontology, and the career-level rubric. Read §5 of that plan before starting M2 here.

---

## 0. How to use this document

Work top to bottom. **Milestone 0 is non-negotiable** — this system's failure mode is putting false claims on a user's resume, and you cannot verify that you've stopped doing it without a test suite that tries to make it happen.

Every task has **files**, **what to build**, **acceptance criteria**. Verify acceptance by running the suite, not by reading the diff.

### Ground rules
1. v2 lives in a new package `backend/tailor/`. Do not edit `agents/tailor_engine.py` or `agents/resume_tailor_agent.py` until M6.
2. **The truthfulness invariant is the product.** Formally: for every tailored resume `T` derived from original `O`, `claims(T) ⊆ claims(O)`, where a claim is a skill, number, employer, title, date, technology, or scope assertion. Everything else in this document exists to enforce that line. A tailoring tool that inflates a match rate by inventing skills is worse than no tool — it gets the user caught in an interview.
3. Every mutation flows through one `Change` object, one guard pipeline, and one applier. No path may write to `structured_json` directly.
4. Never read, write, or print `backend/.env`.
5. `ResumeVersion.source` is DB-constrained to `'uploaded' | 'builder' | 'tailored' | 'ats_check' | 'tailor_input'` (`db/models.py:108`). A new value needs an Alembic migration rewriting the constraint.

---

## 1. Current state

Three paths exist. All three are reachable. Two of them do the same job.

| | **A** `tailor_engine.py` (951) | **B** `ats_fixers/` (15 files, 1581) | **C** `resume_tailor_agent.py` (401) |
|---|---|---|---|
| Purpose | Tailor to JD | Improve resume generally | Tailor to JD |
| Routes | `/tailor/analyze`, `/tailor/apply` | `/improve/propose`, `/improve/apply` | `resumes.py:785`, `chat.py:294` |
| Model | Suggest → accept → apply | Propose → accept → apply | Auto-rewrite whole JSON |
| Score uses the JD | **✗** key mismatch | **✗** imports baseline scorer | n/a |
| User approval | ✓ | ✓ | **✗** |
| Facts locked | **✗** | ✓ `locked_registry` | ✓ phase 3 |
| Asks user for metrics | ✗ | **✓** `quantify_impact` | ✗ |
| Skill injection guarded | **✗** | partial | **✗** |
| Summary validated | ✗ | ✗ (Rule 5 is a comment) | n/a |

**A and C are redundant.** C has the better guards, A has the better interaction model, neither has both.
**B is complementary** — "make my resume better" is a different product surface from "target this job" and should stay separate. But it needs the same safety kernel.

### The three shapes of the same idea
Each path invented its own change format:

```python
# A
{id, type, section, item_index, bullet_index, original, alternatives[],
 keywords_added, estimated_score_gain, priority, reason}
# B
{section, item_index, bullet_index, field, original, proposed, reason, type, category}
# C
(none — returns a whole rewritten resume JSON)
```

Three formats mean three appliers, three validators, and three places for a bug to hide. Unifying them is the single highest-leverage change in this plan.

---

## 2. Verified bugs

Ranked by damage. Every one confirmed by reading the code, not inferred.

### Critical — wrong numbers shown to users

| # | Bug | Location |
|---|---|---|
| 1 | **Path A's match score never reads the JD.** `parse_jd` returns `hard_skills` / `soft_skills`; `_run_ats_scorer_orchestrator` reads `required_hard_skills` / `required_soft_skills` / `jd_keywords` / `raw_jd_text`. Zero key overlap → `jd_keywords = []` → `is_targeted = False` → silently runs `BASELINE_WEIGHTS`. Affects `/tailor/analyze` **and** `/tailor/apply`. | `tailor_engine.py:110`, `ats_scorer.py:499` |
| 2 | **Path B's score never reads the JD either.** Both endpoints `from services.ats_scorer import score_resume_baseline`. But `dispatch(jd=...)` *does* pass the JD to `ats_keywords`. JD-aware UI over a baseline number. | `api/ats.py:208`, `:302` |
| 3 | **Score gains are inflated.** `max(1, round(share * delta))` — 20 suggestions against a true delta of 6 advertise 20 points. If delta ≤ 0 it falls back to `TYPE_WEIGHTS` and still advertises gains, including when applying everything *lowers* the score. | `tailor_engine.py:775-783` |
| 4 | **`total_potential_score` counts no-op suggestions.** Location suggestions carry `alternatives: [""]`; `_apply_single_suggestion` resolves `custom_text` to `""` and the `if custom_text:` guard skips. Never applies, always counted. | `tailor_engine.py:624`, `:739-747` |

### Critical — false claims on the resume

| # | Bug | Location |
|---|---|---|
| 5 | **`generate_skill_suggestions` is a fabrication feature.** Input is `hard_skills_missing` — skills confirmed *absent*. Each becomes "add to your Skills section" with a score gain. No LLM, no gate; deliberate by construction. | `tailor_engine.py:513` |
| 6 | **`build_capped_skills_section` does not gate hard skills.** Soft skills call `has_evidence()`. The JD hard-skill loop adds unconditionally with `reason: "Required by JD"`. The docstring claims "an evidence guardrail (no fabricated hard skills)". | `skill_manager.py:~752` |
| 7 | **Fabricated skills evict real ones.** `SKILLS_HARD_CAP = 15`; overflow pruned by `relevance_score` = 60 for appearing in the JD, 20 for having evidence. An injected skill scores 60–80; a real, evidenced skill the JD doesn't name scores 20. The tailored resume can drop Python to keep Kubernetes. | `skill_manager.py:216`, `:~770` |
| 8 | **Path A has no fabrication guard on bullet rewrites.** Validation is: non-empty, not identical, `len > 10`. | `tailor_engine.py:462-471` |
| 9 | **Generated summaries bypass every validator.** `validate_change` Rule 5 is a comment reading *"For now, we just log it"* — and it doesn't log. `validate_rewrite` only fires when `fld in ("bullets","bullet_points")`, so summaries skip it too. | `validation.py:~100`, `api/ats.py:~330` |

### High — silent data corruption

| # | Bug | Location |
|---|---|---|
| 10 | **Phase 3's number guard reverts the whole rewrite.** Diffs `\b\d+\b` across the entire JSON dump; any new token reverts **all** bullets in experience *and* projects. "10K" → "10,000" tokenizes as `10` + `000`; `000` is new → full revert. Tailoring frequently no-ops and reports success. | `resume_tailor_agent.py:267-285` |
| 11 | **Index-paired repair attaches bullets to the wrong job.** Rules 3, 4, 8 pair `orig[i]` with `tailored[i]`. Nothing forbids the LLM reordering or dropping a role, so Company A's name and dates land on Company B's bullets. | `resume_tailor_agent.py:225-261`, `:292-317` |
| 12 | **`extract_numbers` word-boundary bug, implemented twice identically.** `\b\d+(?:\.\d+)?%?\b` splits "10K" into `10`, and "10,000" into `10` + `000`. Legitimate rewrites rejected. | `locked_registry.py:29`, `validation.py:6` |
| 13 | **Locked-registry matching is raw substring.** `token in original and token not in rewritten` — a title of "Engineer" locks that substring anywhere; a one-character corruption of a company name passes if the substring survives elsewhere. | `locked_registry.py:41` |
| 14 | **`skills_modified` is written into `structured_json`.** A UI flag now lives in the resume and flows into exports, PDF rendering, and scoring text. | `tailor_engine.py:948` |
| 15 | **Score drift across propose/apply.** `improve_propose` scores with `raw_text=resume.raw_text`; `improve_apply` scores with `raw_text=None`. Different text source → the before/after numbers aren't comparable. | `api/ats.py:219`, `:~380` |

### Medium — logic that doesn't do what it says

| # | Bug | Location |
|---|---|---|
| 16 | `has_no_jd_kw` is always `True` (missing keywords are by definition absent), so `_is_weak_bullet` collapses to `weak_verb or no_metric`, and bullet `priority` is always `"medium"`. | `tailor_engine.py:388-393`, `:484` |
| 17 | **The rewriter is forbidden from using good verbs.** `used_verbs` collects openers from the existing resume; the prompt says `NEVER use these`. A resume already using Built/Designed/Led pushes the model to weaker synonyms. | `tailor_engine.py:428` |
| 18 | `spearheaded` is in `CLICHE_PHRASES` and in the scorer's `STRONG_ACTION_VERBS`. Flagged and rewarded simultaneously. | `tailor_engine.py:58`, `ats_wordlists.py` |
| 19 | Weak-verb detection uses `f" {wv} "`, so "Built a system that **supported** 10K users" is flagged as weak. | `tailor_engine.py:331` |
| 20 | `_count_in_text` has no word boundaries. "R" counts every letter R; "Go" matches "going". These counts are shown as *"appears N times in the JD."* | `tailor_engine.py:173` |
| 21 | `_find_sections` and `ats_keywords._get_resume_text` search `json.dumps(...)` / `str(resume_json)` — matching against JSON **keys** and URL fragments, not content. | `tailor_engine.py:195`, `ats_keywords.py:56` |
| 22 | `while len(valid) < 3: valid.append(valid[0])` — the UI shows three alternatives, two identical. | `tailor_engine.py:475` |
| 23 | **`AUTO_IMPROVE_SAFE` lists all 12 fixers.** The `mode` parameter distinguishes nothing; the "safe subset" concept is dead. | `dispatcher.py:26` |
| 24 | `summary.fix` does `skills[0]` — raises `KeyError: 0` on dict-shaped skills (new schema), swallowed by the dispatcher's broad `except`. New-schema resumes silently never get summary fixes. | `summary.py:11` |
| 25 | `readability` requires strictly shorter output while `validate_rewrite`'s `min_len` rejects aggressive compression. The two validators pull opposite directions on the same text. | `validation.py:~85`, `locked_registry.py:~78` |
| 26 | `add_skill` validation is `bool(proposed.strip())`. Safe in baseline mode, unsafe in JD mode where `in_resume` tests against a dict repr. | `validation.py:~30` |
| 27 | `improve_apply` saves with `source="builder"` — improved resumes are indistinguishable from builder-created ones. | `api/ats.py:~395` |
| 28 | `version_number` from `COUNT(*)` — races, and wrong after deletes. | `api/tailor.py:~140` |
| 29 | `ThreadPoolExecutor(max_workers=len(categories_to_run))` — 12 threads making LLM calls per request, unbounded. | `dispatcher.py:~76` |
| 30 | Path A makes up to **11 sequential LLM calls** per analyze (1 JD + 8 bullets + summary + tips). No concurrency, no cache. | `tailor_engine.py:833` |
| 31 | `tailor_resume` logs `jd_analysis.get('resume_missing_skills')` — key doesn't exist (`resume_missing_hard_skills`). Always logs 0. | `resume_tailor_agent.py:344` |
| 32 | Opt-in soft skills are computed and discarded — `build_capped_skills_section` returns them third; the caller destructures into `_`. | `resume_tailor_agent.py:378` |

### Duplication
4 JD extractors (`parse_jd`, `phase1_jd_analysis_and_gaps`, `analyze_jd`, `extract_jd_skills_deterministic`) · 3 change formats · 2 identical `extract_numbers` · 3 section-presence checkers (`ats_scorer`, `tailor_engine.check_sections`, `score_engine_v2.check_missing_info`) · 2 skill-classification stacks.

---

## 3. What premium tools do that this doesn't

| Capability | Reference | Status |
|---|---|---|
| Skills reordered by JD relevance | Jobscan, Rezi | **missing** — `sort_hard_skills_by_category` sorts by category, not relevance |
| Terminology normalisation (`Postgres`→`PostgreSQL` when the JD says so) | Jobscan | **missing** |
| Acronym expansion both directions | Jobscan | **missing** (`ACRONYM_MAP` exists in `ats_scorer.py:22`, unused) |
| Promote a skill buried in a bullet into the Skills section | Jobscan, Teal | partial — B does it, A doesn't |
| Bullet / project / experience reordering | Teal, Enhancv | **missing** |
| Subsetting: hide irrelevant skills, projects, old roles | Teal | **missing** |
| Section reordering (skills above experience for technical JDs) | Enhancv | **missing** |
| Side-by-side editor with live re-score per change | **Jobscan Power Edit** | **missing** |
| Required vs. preferred requirement weighting | Resume Worded | **missing** |
| Gap report — what tailoring *cannot* fix | Teal | **missing** |
| Ask the user for a metric instead of inventing one | — | **have**, in B only (`quantify_impact`) |
| Per-application version tied to company + role | Teal | partial — label is `"Tailored v3"` |
| Cover letter from the same JD analysis | all of them | **missing** |
| Aggressiveness setting | Rezi | **missing** |
| Keyword placement guidance (*where* to add it) | Rezi | partial — a static string |

---

## 4. Target architecture

```
ResumeDoc (from ATS_SCORING_ENGINE_PLAN §3.2)
JobTarget (from ATS_SCORING_ENGINE_PLAN §5.2)  ─── one extractor, cached, deterministic
        │
        ▼
   TailorPlanner  ──► ChangeSet  (list[Change], each with tier, evidence, rationale)
        │                 │
        │                 ▼
        │            GuardPipeline   ── every Change passes or is rejected with a reason
        │                 │
        │                 ▼
        │            user approves (per change, or per tier)
        │                 ▼
        │             Applier  ── the ONLY code that mutates a resume
        │                 ▼
        │            Diff + re-score
        ▼
     GapReport   ── requirements no edit can satisfy
```

### 4.1 Package layout

```
backend/tailor/
  models.py            Change, ChangeSet, Tier, Evidence, GapReport, TailorPlan
  planner.py           (ResumeDoc, JobTarget, Rubric) -> ChangeSet
  apply.py             the single applier
  diff.py              human-readable change list + before/after
  gaps.py              unfixable-requirement detection
  ops/
    reorder.py         skills / bullets / projects / sections
    terminology.py     JD vocabulary + acronym expansion  (uses ats/ontology)
    promote.py         surface skills buried in bullets
    subset.py          hide or compress irrelevant content
    rewrite.py         LLM bullet + summary rewrites
    ask.py             question-type changes  (port from ats_fixers/quantify_impact.py)
  guards/
    pipeline.py        run all guards, return Verdict(ok, reason, guard_id)
    facts.py           locked registry            (port + fix locked_registry.py)
    numbers.py         ONE number extractor       (fix \b bug, delete both copies)
    evidence.py        has_evidence — applied to hard skills too
    domain.py          wraps services/domain_classifier.py
    budget.py          page/length budget
    claims.py          the truthfulness invariant checker
  eval/
    corpus/            (resume, JD) pairs
    test_truthfulness.py
    test_no_loss.py
    test_ops.py
```

### 4.2 The Change model — one shape for all three paths

```python
class Tier(IntEnum):
    LOSSLESS   = 0   # reorder, rename, promote. Reversible, no content invented, no LLM.
    LOSSY      = 1   # subset/hide/compress. Reversible, nothing invented, no LLM.
    GENERATIVE = 2   # LLM rewrites existing content.
    ELICIT     = 3   # requires user input; never auto-applied.

@dataclass(frozen=True)
class Anchor:
    section: str            # summary | skills | experience | projects | education | certifications | _document
    item_index: int | None
    bullet_index: int | None
    field: str | None

@dataclass(frozen=True)
class Evidence:
    kind: Literal["bullet", "certification", "skill_list", "project_tech", "jd", "user_input"]
    quote: str              # the exact text that justifies this change
    anchor: Anchor | None

@dataclass
class Change:
    id: str
    op: str                 # "reorder.skills", "terminology.normalize", "rewrite.bullet", ...
    tier: Tier
    anchor: Anchor
    before: Any
    after: Any
    alternatives: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()      # REQUIRED for tier >= 1. Empty = auto-reject.
    rationale: str = ""
    keywords_addressed: tuple[str, ...] = ()
    score_delta: float | None = None          # measured, never guessed (§4.5)
    guard_verdicts: tuple[Verdict, ...] = ()
    requires_input: bool = False
```

Two rules that kill whole bug classes by construction:

- **`evidence` is mandatory for tier ≥ 1.** `generate_skill_suggestions` cannot be expressed in this model — there is no evidence to attach to a skill the candidate doesn't have. Bug #5 becomes unrepresentable.
- **`score_delta` is measured, never assigned.** No `estimated_score_gain: 2` constants. Bug #3 becomes unrepresentable.

### 4.3 The operation catalogue

This is the product surface. Currently only tier 2 exists.

**Tier 0 — Lossless. No LLM. Safe to auto-apply.**

| Op | What it does | Evidence |
|---|---|---|
| `reorder.skills` | JD-relevant skills first, within existing categories | JD keyword rank |
| `reorder.bullets` | Most JD-relevant bullet first within each role | keyword overlap |
| `reorder.projects` | Most relevant project first | keyword overlap |
| `reorder.sections` | Skills above experience for technical JDs; projects above experience for `student` band | rubric + JD |
| `terminology.normalize` | `Postgres` → `PostgreSQL` when the JD uses the long form | ontology alias + JD term |
| `terminology.acronym` | First use becomes `Amazon Web Services (AWS)`, later uses stay `AWS` | ontology |
| `promote.skill` | A skill in a bullet but absent from Skills gets listed | the bullet, quoted |

`promote.skill` is the honest replacement for bug #5: it produces most of the same keyword lift, and the candidate already owns every skill it surfaces.

**Tier 1 — Lossy but reversible. No LLM.**

| Op | What it does |
|---|---|
| `subset.skills` | Hide skills irrelevant to this JD (never delete from the master resume) |
| `subset.projects` | Show the top N by relevance |
| `subset.bullets` | Trim low-relevance bullets from older roles |
| `subset.experience` | Collapse roles older than ~12 years to a single line |

Every tier-1 change is a *view* over the master resume. The master is never mutated — `ResumeVersion` stores the ChangeSet, and the tailored document is a projection. This makes "revert to original" free.

**Tier 2 — Generative. Guarded.**

`rewrite.bullet` · `rewrite.summary` · `rewrite.project_description`

**Tier 3 — Elicit. Never auto-applied.**

| Op | Prompt to the user |
|---|---|
| `ask.metric` | "How many users / what % improvement?" → port `quantify_impact.get_flags_and_questions` |
| `ask.skill_experience` | "The JD wants Kubernetes. Have you used it? Describe how." → port `ats_keywords` question path |
| `ask.gap` | "This role asks for 5 years; your resume shows 2. Want to address this in the cover letter?" |

Tier 3 is the correct answer to a missing skill. The user supplies the truth or the gap stands.

**Aggressiveness setting** maps directly onto tiers: `Light` = 0 · `Balanced` = 0+1 · `Full` = 0+1+2. Tier 3 is always offered, never auto-applied.

### 4.4 The guard pipeline

Every `Change` passes every guard before reaching the user. A rejection carries a reason and is logged, not silently dropped.

```python
GUARDS = [
    ClaimsGuard(),      # after ⊆ claims(before ∪ evidence)   ← the invariant
    FactsGuard(),       # locked registry: names, employers, titles, dates, URLs
    NumbersGuard(),     # no new numeric claim without user_input evidence
    DomainGuard(),      # a compiler project must not become a UI project
    EvidenceGuard(),    # tier >= 1 requires non-empty evidence
    LengthGuard(),      # per-op bounds; no global contradiction (bug #25)
    BudgetGuard(),      # ChangeSet must not exceed RUBRICS[band].max_pages
]
```

Fixes required while porting:

- **`guards/numbers.py`** — one implementation. Tokenise `10K`, `10,000`, `2.5x`, `$1.2M`, `40%` as single units. Delete `locked_registry.extract_numbers` and `validation.extract_numbers`. (bug #12)
- **`guards/facts.py`** — match on normalised whole tokens, not raw substrings. (bug #13)
- **`guards/budget.py`** — new. Tailoring lengthens content; the scorer deducts up to 25 points for spilling to page 2. Today the two systems fight. The planner must treat the page budget as a constraint, so adding a keyword forces a compensating `subset` op. (bug #40)
- **`ClaimsGuard`** — new, and the one that matters. Extract the claim set from `before` and `evidence`, extract it from `after`, assert containment. This is what would have caught bugs #5, #6, #8, and #9 as a class.

### 4.5 Honest score deltas

Delete `estimate_score_gains` entirely. Replace with measurement:

```python
def measure(doc, jd, changeset) -> None:
    base = score(doc, jd).headline
    for ch in changeset:                       # tier 0/1 are pure functions — cheap
        ch.score_delta = round(score(apply_one(doc, ch), jd).headline - base, 1)
    changeset.combined_delta = round(
        score(apply_all(doc, changeset), jd).headline - base, 1)
```

Report **both** the per-change delta and the combined delta, and state plainly that they don't sum — overlapping changes don't stack. Jobscan Power Edit shows exactly this: your match rate moving in real time as you accept edits. It is the most persuasive thing the product can do, and it requires no estimation heuristic once scoring is deterministic (`ATS_SCORING_ENGINE_PLAN` §0 rule 2).

### 4.6 The gap report

Not every requirement is fixable by editing. Split them:

```python
@dataclass
class Gap:
    requirement: str
    kind: Literal["skill", "years", "degree", "certification", "domain"]
    severity: Literal["blocker", "major", "minor"]
    honest_options: list[str]   # "take the AWS CCP cert", "address it in the cover letter"
```

A tool that returns 95% by inventing skills is worse than one that returns 68% and says *"they want Kubernetes; you've never used it — here's what you can honestly do."* This is the feature that distinguishes a tailoring product from a keyword stuffer, and it costs one extra pass over the unmatched `JobTarget` keywords.

---

## 5. Milestones

### M0 — Adversarial test harness *(blocks everything)*
- `tailor/eval/corpus/` — **40 (resume, JD) pairs**, deliberately hostile: JDs demanding skills the resume lacks; JDs in a different domain entirely; resumes with numbers in every awkward format (`10K`, `10,000`, `$1.2M`, `2.5x`, `40%`); resumes with duplicate company names; resumes with roles out of chronological order; student resumes with no experience section; non-tech resumes.
- `test_truthfulness.py` — run every path over every pair, extract the claim set from the output, assert `claims(T) ⊆ claims(O)`. **Run it against the current code first and record the failure count** — that number is the headline justification for this work.
- `test_no_loss.py` — assert no skill present in `O` and relevant to the JD is absent from `T` (catches bug #7).
- **Acceptance:** `pytest backend/tailor/eval` produces a per-path violation table for the current code. Committed to `eval/BASELINE_v1.md`.

### M1 — Kernel
- `models.py`, `apply.py`, `diff.py`, `guards/*`.
- Port and fix: `locked_registry.py` → `guards/facts.py`, both `extract_numbers` → `guards/numbers.py`, `validation.py` → `guards/pipeline.py`.
- **Acceptance:** `apply.py` is the only module in `backend/tailor/` that mutates a resume dict — enforce with a lint test. `NumbersGuard` correctly tokenises all formats in the M0 corpus. `ClaimsGuard` rejects a hand-written `Change` that adds an unowned skill. Every guard rejection carries a `reason`.

### M2 — JD contract + fix the score
- Adopt `JobTarget` from `ATS_SCORING_ENGINE_PLAN` §5.2 as the only JD representation. Delete `parse_jd` and `phase1_jd_analysis_and_gaps`; route everything through the cached extractor.
- Fix bugs #1 and #2: one call site, correct keys, targeted scoring in both `/tailor/*` and `/improve/*`.
- **Acceptance:** a resume matching 0% of a JD and one matching 90% produce *different* scores through both `/tailor/analyze` and `/improve/propose` — today they don't. `grep -c "def parse_jd\|phase1_jd_analysis"` returns 0. Same JD text twice → one LLM call.

### M3 — Tier 0 ops
- `ops/reorder.py`, `ops/terminology.py`, `ops/promote.py`. All pure functions, no LLM.
- Requires the skill ontology from `ATS_SCORING_ENGINE_PLAN` §5.1 for aliases and acronyms.
- **Acceptance:** every tier-0 change is byte-reversible. Match score rises measurably on the M0 corpus with **zero** `ClaimsGuard` violations and zero LLM calls. `Postgres`→`PostgreSQL` and `AWS`↔`Amazon Web Services` both fire.

### M4 — Tier 1 + Tier 2 ops
- `ops/subset.py` as a projection over the master (never a delete). `ops/rewrite.py` for bullets and summary, behind the full guard pipeline.
- Fix while porting: bugs #17 (stop banning the resume's own strong verbs), #18 (remove `spearheaded` from the cliché list), #19 (anchor weak-verb detection to bullet start), #22 (never pad duplicate alternatives — return however many are genuinely distinct).
- Concurrency: rewrites run in a bounded pool (bugs #29, #30).
- **Acceptance:** `/tailor/analyze` p95 under 15s. Rewrite prompts never receive a verb ban list. `ClaimsGuard` violations remain zero on the corpus. Reverting a tier-1 change restores the original byte-for-byte.

### M5 — Tier 3 + gap report
- `ops/ask.py` — port `quantify_impact.get_flags_and_questions` and `ats_keywords`'s question path onto the `Change` model. `gaps.py`.
- **Acceptance:** for a JD demanding an unowned skill, the system produces an `ask.skill_experience` change **and** a `Gap` entry — never an `add_skill`. Answering the question routes the user's text through `NumbersGuard` before it lands.

### M6 — Consolidation
- Refactor Path A onto the kernel. **Retire Path C** — port its Rules 3/4/8 concepts (fact locking, domain integrity) into guards, then delete `resume_tailor_agent.py` and repoint `api/resumes.py:785` and `api/chat.py:294` at the kernel with `Tier.GENERATIVE` and auto-approve, so even the "automatic" path gets a diff.
- Refactor Path B's 12 fixers to emit `Change` objects. **Keep B as a separate product surface** — it answers a different question. Fix bug #23 by making `AUTO_IMPROVE_SAFE` mean tier ≤ 1.
- Fix the leftovers: #14 (`skills_modified` out of `structured_json`), #15 (one text source), #24 (dict-shaped skills), #27 (`source="tailored"`), #28 (version number from a sequence), #31, #32 (restore opt-in soft skills).
- **Acceptance:** `agents/resume_tailor_agent.py` and `agents/tailor_engine.py` are deleted. `grep -r "structured_json\[" backend/` shows writes only from `tailor/apply.py`. All three routes return the same `Change` shape. Truthfulness violations: **0**.

### M7 — Premium UX
- **Live re-score editor** (Jobscan Power Edit): side-by-side original/tailored, per-change accept/reject, match rate updating on each toggle. The killer feature, and M4 + §4.5 make it nearly free.
- Per-application versions labelled from the JD's company and title, not `"Tailored v3"`.
- Aggressiveness selector wired to tiers.
- Cover letter generated from the same `JobTarget` + `GapReport`.
- **Acceptance:** toggling a change updates the displayed match rate within 300ms. Version list shows company and role. Reverting all changes yields the original resume byte-for-byte.

---

## 6. Non-functional

| Requirement | Target |
|---|---|
| Tier 0/1 op latency | < 50 ms, no I/O — they're pure functions |
| `/tailor/analyze` p95 | < 15 s (currently ~11 sequential LLM calls) |
| JD extraction | once per JD hash, cached, shared with the scorer |
| Re-score on change toggle | < 300 ms — requires the deterministic scorer |
| Truthfulness violations | **0**, enforced in CI |
| Every rejected change | logged with guard id + reason, surfaced in a debug panel |

---

## 7. Open decisions

1. **Master-plus-ChangeSet vs. materialised copies.** §4.3 proposes storing tailored resumes as a ChangeSet over the master, which makes revert free and per-application versions cheap. It's a schema change (`ResumeVersion.change_set JSON`) and a bigger migration. The alternative — keep materialising full copies — is simpler but loses free revert and makes "what did I change for this application" a diff computation. Recommend the ChangeSet; confirm before M1.
2. **Retiring Path C.** M6 deletes it. If `api/chat.py`'s conversational tailoring depends on getting a complete resume back in one shot, the kernel needs a synchronous auto-approve wrapper. Confirm the chat flow's expectations first.
3. **Terminology normalisation aggressiveness.** Rewriting the candidate's `Postgres` to the JD's `PostgreSQL` is safe. Rewriting their job title to the JD's title is not. The line is drawn at §4.3 tier 0, but confirm you agree that titles are never touched — some competitors do allow a parenthetical equivalent (`Member of Technical Staff II (Software Engineer)`), which is defensible and could be a tier-1 op.
4. **Cover letter scope.** M7 lists it because every reference product has one and the `JobTarget` + `GapReport` inputs already exist. It is genuinely a separate feature; cut it if M7 gets long.
