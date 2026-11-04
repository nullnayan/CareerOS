# CareerOS — ATS Scoring Engine v3: Ground-Up Build Plan

**Audience:** an AI coding agent picking up this repo.
**Date:** 2026-08-06
**Repo root:** `careeros_scaffold/careeros`
**Reference products:** Jobscan (match rate), Resume Worded (Score My Resume: Impact / Brevity / Style), Enhancv, Teal.
**Supersedes:** the scoring behaviour of `backend/services/ats_scorer.py` (1431 lines) and `backend/ats_engine/scorer/score_engine_v2.py`.

---

## 0. How to use this document

This is **not** a patch list for the existing scorer. It is the design I would have started from, written so it can be built alongside the current engine and cut over once it beats it on a labelled corpus.

Work top to bottom. **Milestone 0 is non-negotiable** — you cannot verify any scoring change without a labelled corpus and a regression harness, and every attempt to hand-tune weights without one is how the current engine ended up with three checks silently disconnected from the score.

Every task has **files**, **what to build**, and **acceptance criteria**. Verify acceptance criteria by running the harness, not by reading the diff.

### Ground rules
1. `v3` lives in a new package `backend/ats/`. Do **not** edit `backend/services/ats_scorer.py` until Milestone 6. The two engines run side by side.
2. **No network call may influence a score.** LLMs and embeddings are allowed for JD *extraction* (cached, upstream) and for *rewrite suggestions* (post-scoring). The scoring function itself must be pure: same `ResumeDoc` + same `JobTarget` → byte-identical `ScoreReport`.
3. Every check is a pure function with no I/O. If a check needs a fact about the PDF, that fact is captured at parse time into `LayoutFacts` and passed in.
4. No check may assign its own point value. Points are derived by the scorer (§4.4). This is a structural rule, not a style preference — it is what makes the numbers honest.
5. Never read, write, or print `backend/.env`.

---

## 1. Why a rebuild rather than a repair

The check *inventory* in `ats_engine/` is good — it covers more ground than Jobscan does. The scoring layer is what fails, and it fails structurally, not incidentally:

| Defect | Root cause |
|---|---|
| `structure_completeness_val` computed, mutated 4×, never scored (`ats_scorer.py:896`) | 1431-line function; no contract forcing a check's output into the score |
| `authenticity_val` computed, rescaled, never scored (`:958`, `:1216`) | same |
| Keyword match mathematically capped at ~0.44 (`section_weighted_matcher.py:38`) | averaging per-section match *rates*, dividing by all section weights including empty ones |
| Targeted score barely moves with the JD (10% weight) | one weight vector doing two unrelated jobs |
| Same defect charged 2–3× (`:1330-1344` dampeners) | penalties applied at both component and global level, no ledger |
| `points_deducted` values are fiction | checks self-report points with no link to the actual delta |
| Same resume scores differently across runs | LLM + embeddings inside the scoring path |
| Score changes between `/analyze` and `/improve` with no edits | `full_resume_text = raw_text or " ".join(...)` — two different word sources |
| One 6-month gap caps the score at 60 (`score_engine_v2.py:60`) | binary red-flag cap instead of graded penalty |

Every one of these is a consequence of the same three missing abstractions: **a typed document model**, **a check contract**, and **a scorer that owns all arithmetic**. Adding them is the rebuild.

### What survives (do not rewrite)
- `backend/resume_parser/**` — the parser stays. v3 consumes its output.
- `backend/services/ats_wordlists.py` — 286 action verbs, 342 hard skills, buzzwords, weak phrases. Good raw material; it gets restructured in M3, not discarded.
- The *logic* inside `ats_engine/content_checks/*.py` and `formatting_checks/*.py` — ported into the new check contract in M2, mostly unchanged.
- `services/analysis_cache.py`, `services/jd_analyzer.py` — reused for cached JD extraction upstream of scoring.

### What gets deleted (M7)
`agents/ats_analyzer.py`, `agents/ats_analyzer_baseline.py` (two dead LLM scoring systems), the 6 unused exports in `score_engine_v2.py`, the `recruiter_judge` / `check_line_gaps` imports, the inline `__import__` lambda at `ats_scorer.py:1426`, and the `_build_html` page-count re-render at `:1145`.

---

## 2. Product model: three scores, not one

The single biggest design error in the current engine is that one number answers three unrelated questions. The reference products keep them apart, and so should we.

| Score | Question | Analogue | Depends on JD? |
|---|---|---|---|
| **Parseability** 0–100 | Can an ATS extract this candidate's data? | Jobscan "Searchability" | No |
| **Strength** 0–100 | Is this a good resume? | Resume Worded "Score My Resume" | No |
| **Match** 0–100 | Does this resume fit *this* job? | Jobscan "Match Rate" | Yes |
| **RoleFit** 0–100 | Does this resume fit this *kind* of job? | Jobscan "predicted skills" | No — used when no JD (§5.4) |

**Headline score** shown in the UI:

```
strength_gated = Strength × parse_gate
parse_gate     = 0.75 + 0.25 × (Parseability / 100)     # worst case ×0.75, never zero

headline = 0.45 × Match   + 0.55 × strength_gated        if JD present
headline = 0.25 × RoleFit + 0.75 × strength_gated        if no JD, target role known
headline = strength_gated                                if no JD and no target role
```

Rationale:
- `parse_gate` is **one** multiplicative factor with a stated justification (an unparseable resume is invisible regardless of quality), replacing the four ad-hoc dampeners at `ats_scorer.py:1330-1344`. It is floored at 0.75 because even a badly-formatted resume that a human opens still has its content judged.
- Match never blends into Strength. A resume can be excellent and wrong for the job; the UI must be able to say that.
- RoleFit carries less weight than Match (0.25 vs 0.45) because a role archetype is a statistical prior, not a stated requirement. It should nudge, not dominate.
- Parseability is reported but never dominates — mirrors Jobscan treating searchability as a diagnostic.

**Acceptance:** `docs/scoring-rubric.md` exists and states these formulas. The API returns all applicable scores plus `scoring_version`.

---

### 2.1 Career level is an input, not just an inference

Today nothing asks the candidate who they are, and the engine applies identical thresholds to a second-year student and a VP. A student is charged for having no formal experience section, no metrics, no leadership signal, and no professional summary — four penalties for correctly being a student.

**Before scoring, ask three questions on one screen (~10 seconds):**

| # | Question | Stored as | Powers |
|---|---|---|---|
| 1 | Where are you in your career? | `users.career_level` | Rubric selection (§4.3) |
| 2 | What role are you targeting? | `users.target_role` | RoleFit (§5.4), title match |
| 3 | Which region are you applying in? | `users.locale` | Locale conventions (§6) |

Asked once at first scan, persisted, editable from settings, re-prompted only when the parsed resume diverges materially from the stored answer.

**Career level options (five bands, plain-language labels):**

| Band | Label shown | Description shown |
|---|---|---|
| `student` | Student / New grad | Still studying or graduated within the last year |
| `entry` | Early career | 1–3 years of professional work |
| `mid` | Mid-level | 4–7 years, own projects end to end |
| `senior` | Senior | 8–15 years, lead others or set technical direction |
| `exec` | Leadership | 15+ years, manage teams or functions |

> **Deviation from the brief, stated deliberately.** You asked for three buckets (beginner / 2–3 years / 8–10+). I'm specifying five, because three leaves the 4–7 year range — the largest single segment of resume-tool users — with no honest home. A 5-year engineer forced to pick "intermediate (2–3 years)" gets scored against a bar that's too low; forced into "pro (8–10+)" they get scored against one they cannot meet. The three you named map to `student`/`entry`, `mid`, and `senior`/`exec`; the two extra bands cost one radio button and remove a systematic scoring error. Overrule this if the simpler UX matters more.

### Declared vs. verified — the anti-gaming rule

Self-declared level cannot be a free score. Claiming *up* is safe: a higher band raises every threshold (metric targets, leadership expectation, page budget tightens relative to content). Claiming *down* is the exploit — a 12-year veteran selecting "Student" would have tenure, progression, gap, and leadership checks marked N/A.

```python
inferred_floor  = band_from_parsed_dates(doc)     # hard evidence only: dated roles
effective_band  = max(declared_band, inferred_floor)   # claim up freely, never down
```

- If `declared < inferred_floor`: score at the floor, emit an `info` finding ("Scored as Mid-level — your resume shows 6 years of dated experience").
- If `declared ≥ inferred_floor + 2`: score at `declared` (stricter, so no exploit) and emit an `info` finding — the mismatch is itself a recruiter red flag worth surfacing: *"You selected Senior, but your resume evidences ~1 year of dated experience. Recruiters will read that same gap."*
- `inferred_floor` derives **only** from parsed date ranges, never from title keywords — titles are self-assigned and inflate freely.

**Acceptance:** a 10-year resume declaring `student` scores within 3 points of the same resume declaring `senior`. A `student` resume with no formal experience section incurs **zero** experience-section deductions. Both are corpus test cases.

---

## 3. Architecture

```
uploaded file
    │
    ├─► resume_parser/**  (existing)          ─┐
    └─► layout_probe.py   (new, at parse time) ─┤
                                                ▼
                                          ResumeDoc          ← frozen, canonical, the only input
                                                │
                          JobTarget (optional) ─┤            ← extracted once, cached, hashed
                                                ▼
                                        CheckRegistry         ← ~40 pure functions
                                                │
                                        list[CheckResult]     ← score 0..1 + Findings (no points)
                                                ▼
                                          Scorer              ← rubric + weights + penalty ledger
                                                │             ← owns ALL arithmetic
                                                ▼
                                          ScoreReport         ← 3 scores, findings w/ real points, fixes
```

### 3.1 Package layout

```
backend/ats/
  __init__.py
  models.py            # ResumeDoc, JobTarget, Finding, CheckResult, ScoreReport  (frozen dataclasses)
  doc_builder.py       # parsed JSON + LayoutFacts -> ResumeDoc   (the ONLY place text views are made)
  layout_probe.py      # pdfplumber facts captured at PARSE time, not scoring time
  profile.py           # seniority band + domain inference
  ontology/
    skills.yaml        # ~1500 canonical skills, aliases, kinds, parents
    loader.py          # SkillOntology: canonicalize(), aliases_of(), kind_of()
    titles.yaml        # job-title normalisation + seniority markers
  jd/
    extract.py         # JD text -> JobTarget  (LLM + cache + deterministic fallback)
    fallback.py        # rule-based extractor that works for NON-TECH roles
  checks/
    base.py            # Check protocol, registry, decorator
    impact.py          # metrics, action verbs, achievement framing
    brevity.py         # length, bullet length, filler, buzzwords, passive voice
    style.py           # pronouns, tense consistency, spelling, punctuation
    structure.py       # sections, contact, ordering, chronology
    formatting.py      # columns, tables, ligatures, fonts, dates, pages
    authenticity.py    # stuffing, duplicate bullets, unverifiable claims
    growth.py          # leadership / teamwork / communication / analytical
    match.py           # JD keyword + title + seniority + education match
  scoring/
    rubric.py          # per-seniority targets + weight vectors
    ledger.py          # penalty ledger (replaces red-flag cap + dampeners)
    scorer.py          # CheckResults -> ScoreReport
    version.py         # SCORING_VERSION
  api_adapter.py       # ScoreReport -> the JSON shape frontend already consumes
```

### 3.2 The document model

```python
@dataclass(frozen=True)
class Bullet:
    text: str
    section: Literal["experience", "projects", "volunteer"]
    entry_index: int
    bullet_index: int
    entry_is_current: bool          # drives verb-tense checking

@dataclass(frozen=True)
class TextViews:
    bullets: tuple[Bullet, ...]
    by_section: Mapping[str, str]   # skills/experience/projects/summary/education/certifications
    full: str                       # canonical, DERIVED FROM STRUCTURED DATA ONLY
    layout_raw: str                 # raw PDF text — permitted ONLY in formatting.py

@dataclass(frozen=True)
class LayoutFacts:
    page_count: int                 # from the UPLOADED pdf, never re-rendered
    has_columns: bool
    has_tables: bool
    is_scanned: bool
    embedded_fonts: tuple[str, ...]
    font_sizes_by_section: Mapping[str, tuple[float, ...]]
    has_images: bool
    header_footer_text: tuple[str, ...]   # text ATS commonly drops
    file_type: str

@dataclass(frozen=True)
class CandidateProfile:
    seniority: Literal["student", "entry", "mid", "senior", "exec"]
    years_experience: float
    domain: str                     # from services/domain_classifier.py
    has_formal_experience: bool

@dataclass(frozen=True)
class ResumeDoc:
    contact: Contact
    summary: str
    experience: tuple[Experience, ...]
    education: tuple[Education, ...]
    projects: tuple[Project, ...]
    skills: tuple[Skill, ...]
    certifications: tuple[Certification, ...]
    text: TextViews
    layout: LayoutFacts
    profile: CandidateProfile
```

Three things this buys, each of which kills a live bug:

1. **`TextViews.full` is derived from structured data only.** `layout_raw` exists but is accessible only to `checks/formatting.py`. Enforce with a lint test that greps for `layout_raw` outside that module. This kills the analyze-vs-improve score drift caused by `raw_text or " ".join(...)`.
2. **`Bullet` carries provenance.** Findings anchor to `(section, entry_index, bullet_index)`, so the UI can highlight the exact line. Currently `_get_all_text_blocks()` and the inline bullet loop at `:457-480` produce *different* bullet lists used as denominators in different checks.
3. **`LayoutFacts.page_count` comes from the uploaded PDF.** The current engine re-renders the resume through its own HTML template (`:1145`) and deducts up to 45 points based on that. Store page count on `ResumeVersion` at upload; add an Alembic migration.

### 3.3 The check contract

```python
class Check(Protocol):
    id: str                                  # "impact.quantified_bullets"
    dimension: Dimension                     # IMPACT | BREVITY | STYLE | STRUCTURE |
                                             # FORMATTING | AUTHENTICITY | GROWTH | MATCH
    requires_jd: bool
    applies_to: frozenset[Seniority]         # e.g. tenure check skips "student"

    def run(self, doc: ResumeDoc, jd: JobTarget | None, rubric: Rubric) -> CheckResult

@dataclass(frozen=True)
class CheckResult:
    check_id: str
    score: float | None                      # 0..1; None = not applicable, excluded + reweighted
    findings: tuple[Finding, ...]
    evidence: Mapping[str, Any]              # raw numbers for the debug panel

@dataclass
class Finding:
    check_id: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    title: str
    detail: str
    anchor: Anchor | None
    fix: Fix | None                          # machine-applicable where possible
    points: float = 0.0                      # ← WRITTEN BY THE SCORER, never by the check
```

Registration:

```python
@register
class QuantifiedBullets:
    id = "impact.quantified_bullets"
    dimension = Dimension.IMPACT
    requires_jd = False
    applies_to = ALL_SENIORITIES
    def run(self, doc, jd, rubric): ...
```

**The registry is the contract.** A check that is registered is scored; a check that is not registered does not exist. There is no third state in which a value is computed and quietly discarded — which is exactly what happened to `structure_completeness_val` and `authenticity_val`.

**Acceptance:** a unit test asserts that every `Dimension` has ≥1 registered check, and that every registered check id appears in the weight table. Fails the build otherwise.

---

## 4. The scorer

### 4.1 Dimensions and weights

Two weight vectors, selected by JD presence. Both sum to exactly 1.0 (assert it).

```python
# No JD — Resume Worded's Impact / Brevity / Style shape
BASELINE_WEIGHTS = {
    Dimension.IMPACT:       0.26,
    Dimension.BREVITY:      0.14,
    Dimension.STYLE:        0.10,
    Dimension.STRUCTURE:    0.14,
    Dimension.FORMATTING:   0.16,
    Dimension.AUTHENTICITY: 0.10,
    Dimension.GROWTH:       0.10,
}

# JD present — Jobscan's keyword-dominant shape, applied to the MATCH score only
MATCH_WEIGHTS = {
    "hard_skills":   0.50,   # Jobscan's documented #1 priority
    "job_title":     0.15,
    "domain_terms":  0.12,
    "seniority_fit": 0.10,
    "soft_skills":   0.07,
    "education":     0.04,
    "certifications":0.02,
}
```

Note the structural change: with a JD, keywords no longer fight the other checks for a 10% slice of one vector. They constitute an entire score, which then contributes 45% of the headline (§2). A resume matching 0% of the JD loses ~45 headline points, not 10.

### 4.2 Within-dimension weights

Each dimension has its own check-weight table in `scoring/rubric.py`, normalised over the checks that returned a non-`None` score. Example:

```python
IMPACT_CHECKS = {
    "impact.quantified_bullets":  0.40,
    "impact.action_verbs":        0.25,
    "impact.achievement_framing": 0.20,   # outcome vs. duty
    "impact.scope_signals":       0.15,   # team size, budget, user counts
}
```

If a check returns `None` (not applicable to this seniority), its weight is redistributed proportionally across the rest. This is how the student case stops being punished for a check that doesn't apply to it, instead of the current approach of multiplying the whole score by 0.75.

### 4.3 Career-level rubric

Resume Worded explicitly adapts to seniority. The current engine uses identical thresholds for a first-year student and a VP.

The rubric is selected by `effective_band` (§2.1) and controls **three** things: thresholds, which checks apply at all, and the dimension weight vector.

```python
@dataclass(frozen=True)
class Rubric:
    band: Seniority
    # thresholds
    metric_bullet_target: float     # fraction of bullets that should carry a metric
    action_verb_target: float
    max_pages: int
    min_words: int
    max_words: int
    max_bullets_per_role: int
    leadership_expectation: float   # 0..1 target for GROWTH
    # expectations — drive N/A, not deductions
    expects_summary: bool
    expects_formal_experience: bool
    expects_gpa: bool
    counts_projects_as_experience: bool
    # weights
    dimension_weights: Mapping[Dimension, float]
    disabled_checks: frozenset[str]  # return None -> weight redistributed
```

| | student | entry | mid | senior | exec |
|---|---|---|---|---|---|
| `metric_bullet_target` | 0.20 | 0.35 | 0.45 | 0.55 | 0.60 |
| `action_verb_target` | 0.75 | 0.85 | 0.90 | 0.90 | 0.90 |
| `max_pages` | 1 | 1 | 1 | 2 | 2 |
| `min_words` / `max_words` | 250 / 600 | 300 / 700 | 400 / 850 | 500 / 1100 | 550 / 1200 |
| `leadership_expectation` | 0.15 | 0.30 | 0.45 | 0.65 | 0.80 |
| `expects_summary` | ✗ | ✗ | ✓ | ✓ | ✓ |
| `expects_formal_experience` | ✗ | ✓ | ✓ | ✓ | ✓ |
| `expects_gpa` | ✓ | ✗ | ✗ | ✗ | ✗ |
| `counts_projects_as_experience` | ✓ | partial (0.7) | ✗ | ✗ | ✗ |

**Dimension weights per band** (each row sums to 1.0 — assert it):

| Dimension | student | entry | mid | senior | exec |
|---|---|---|---|---|---|
| IMPACT | 0.18 | 0.24 | 0.28 | 0.30 | 0.30 |
| BREVITY | 0.12 | 0.13 | 0.14 | 0.15 | 0.15 |
| STYLE | 0.10 | 0.10 | 0.10 | 0.09 | 0.08 |
| STRUCTURE | 0.22 | 0.18 | 0.14 | 0.12 | 0.11 |
| FORMATTING | 0.18 | 0.17 | 0.16 | 0.15 | 0.14 |
| AUTHENTICITY | 0.10 | 0.10 | 0.10 | 0.09 | 0.08 |
| GROWTH | 0.10 | 0.08 | 0.08 | 0.10 | 0.14 |

The shape encodes the real difference: a student is graded mostly on *having a well-built, parseable, complete document*, an executive mostly on *demonstrated impact and leadership*.

**Checks disabled per band** (return `None`, weight redistributed — never a deduction):

```python
DISABLED = {
  "student": {"structure.formal_experience_section", "impact.scope_signals",
              "growth.people_management", "structure.career_progression",
              "authenticity.employment_gaps", "brevity.summary_required"},
  "entry":   {"growth.people_management", "structure.career_progression"},
  "mid":     set(),
  "senior":  {"structure.gpa_present"},
  "exec":    {"structure.gpa_present", "impact.individual_contributor_depth"},
}
```

This is the mechanism your brief asks for. A student with no experience section does not lose points for it — the check reports `None`, and `STRUCTURE`'s remaining checks are renormalised to absorb the weight. Compare the current engine, which charges the student at `ats_scorer.py:874-881` (25 pts), `:1228-1230` (`experience_quality = 0.0`, 10% of the score), and again via the `×0.90` dampener at `:1344`.

Band-specific substitutions rather than absences:

| Band | Instead of… | Score… |
|---|---|---|
| student | work experience | projects, coursework, internships, GPA, campus leadership |
| student | professional summary | objective **or** nothing — neither is penalised |
| entry | deep tenure | internship-to-full-time conversion, promotion within 3 years |
| senior/exec | task-level bullets | scope: team size, budget, org influence, cross-functional reach |

**Acceptance:** the same student resume scores ≥ 15 points higher under `student` than under `mid`. `sum(dimension_weights) == 1.0` for all five bands. Every id in `DISABLED` exists in the registry (typo guard — a misspelled id would silently disable nothing).

### 4.4 Honest points — the core rule

Checks never assign points. The scorer derives them, and they sum exactly to the deduction:

```python
def assign_points(dim: Dimension, result: CheckResult,
                  dim_weight: float, check_weight: float,
                  score_basis: float) -> None:
    lost = score_basis * dim_weight * check_weight * (1.0 - result.score)
    if not result.findings:
        return
    sev_mass = {"critical": 5, "high": 3, "medium": 2, "low": 1, "info": 0}
    total = sum(sev_mass[f.severity] for f in result.findings) or 1
    for f in result.findings:
        f.points = round(lost * sev_mass[f.severity] / total, 1)
```

**Invariant test (must be in CI):**
```
sum(f.points for f in report.findings) + sum(report.ledger.applied)
    == round(score_basis - report.strength, 1)   ± 0.5
```

This makes "you lost 6.2 points here" a derived fact. Today those numbers (`points_deducted: 25`, `: 20`, `: 15`) are hand-typed constants with no relationship to the score, and a user who adds them up will catch it.

### 4.5 The penalty ledger

Delete `REDFLAG_SCORE_CAP` and all four multiplicative dampeners. One explicit, additive, capped stage:

```python
LEDGER = [
  # (predicate,                        points, reason,                      charged_elsewhere?)
  (lambda d,j: d.layout.is_scanned,        18, "Scanned/image PDF",                False),
  (lambda d,j: d.layout.page_count >= 3,   12, "Three or more pages",              False),
  (lambda d,j: over_page_budget(d),         6, "Exceeds page budget for seniority",False),
  (lambda d,j: d.layout.has_columns,        8, "Multi-column layout",              False),
  (lambda d,j: seniority_mismatch(d),       8, "Senior title vs. tenure",          False),
  (lambda d,j: gap_months(d) > 18,          5, "Extended unexplained gap",         False),
]
LEDGER_CAP = 30
```

Three rules, all enforced by tests:
1. **A defect charged in the ledger must not also lower a component score.** A `charged_elsewhere` audit test walks every ledger entry and asserts no registered check covers the same predicate. This is what the current `metric_pct == 0 → ×0.75` violates — metrics are already 60% of a 30%-weight component.
2. **Gaps are graded, not binary,** and never charged for `student`. A student with two summer internships nine months apart currently gets capped at 60 regardless of resume quality.
3. **Total ledger is capped at 30**, so no single flag can zero a strong resume.

Every ledger entry emits a `Finding` whose `points` is the value actually charged.

---

## 5. The JD / match engine

### 5.1 Skill ontology — build this asset first

`ATS_scorer.py:22` defines an `ACRONYM_MAP` that is **never used**, so "AWS" in the JD versus "Amazon Web Services" in the resume scores as a miss. That is a headline Jobscan feature sitting dead in the file. The fix is not to wire up a 30-entry dict; it is to build the ontology the whole engine needs.

`backend/ats/ontology/skills.yaml`, ~1500 entries:

```yaml
- id: aws
  canonical: Amazon Web Services
  kind: cloud_platform          # hard_skill | tool | cloud_platform | language |
                                # framework | database | methodology | soft_skill | certification
  aliases: [aws, amazon web services, amazon aws, aws cloud]
  parents: [cloud_computing]
- id: react
  canonical: React
  kind: framework
  aliases: [react, react.js, reactjs, react js]
  parents: [javascript, frontend]
```

Seed from ESCO + O*NET + Stack Overflow tags + the existing 342-entry `HARD_SKILLS`. `SkillOntology.canonicalize(term) -> SkillId | None` is then the single normalisation point for resume skills, JD skills, and match reporting. This one asset fixes acronyms, aliases, categorisation, and the non-tech coverage gap simultaneously.

### 5.2 JobTarget

```python
@dataclass(frozen=True)
class JDKeyword:
    term: str
    skill_id: str | None
    kind: str
    jd_frequency: int
    required: bool           # required vs. preferred — RW weighs these differently

@dataclass(frozen=True)
class JobTarget:
    title: str
    title_normalized: str
    seniority: str
    keywords: tuple[JDKeyword, ...]
    min_years: float | None
    required_degree: str | None
    source_hash: str         # sha256(jd_text) — the cache key AND the determinism guarantee
```

Extraction runs **once**, upstream, in `api/ats.py`, cached by `source_hash`. `JobTarget` is data by the time it reaches the scorer. The rule from §0 holds: the score is a pure function of `(ResumeDoc, JobTarget)`.

**Deterministic fallback (`jd/fallback.py`)** must work when the LLM fails *and* for non-tech roles. The current fallback (`ats_scorer.py:289-294`) keeps only words already present in `HARD_SKILLS`, so a nursing or accounting JD yields zero keywords, `is_targeted` flips to `False`, and the user receives a **baseline score labelled as a targeted one, with no warning**. Replace with: noun-phrase chunking → ontology lookup → TF-IDF against a background JD corpus for unmatched terms. If extraction still yields <5 keywords, return `Match = None` and say so in the response. Never silently downgrade.

### 5.3 Match scoring

Per-keyword, not per-section. The current `section_weighted_score` averages section match *rates* and divides by the sum of all section weights (4.55) including sections a keyword could never appear in — capping keyword match at roughly 0.44 for a flawless resume.

```python
def score_match(doc: ResumeDoc, jd: JobTarget, onto: SkillOntology) -> MatchResult:
    SECTION_W = {"skills": 1.0, "experience": 1.0, "projects": 0.85,
                 "summary": 0.7, "certifications": 0.6, "education": 0.4}
    total_w = earned_w = 0.0
    for kw in jd.keywords:
        w = (MATCH_WEIGHTS_BY_KIND[kw.kind]
             * (1.0 if kw.required else 0.5)
             * min(1.0 + 0.15 * (kw.jd_frequency - 1), 1.6))   # Jobscan: frequency matters
        total_w += w
        best = max((SECTION_W[s] for s, text in doc.text.by_section.items()
                    if found(kw, text, onto)), default=0.0)
        earned_w += w * best
    return earned_w / total_w if total_w else 0.0
```

`found()` is deterministic, in order: normalise → word-boundary exact → ontology alias → parent-skill partial credit (0.6) → stem. **No embeddings.** The current semantic path uses a 0.5 cosine threshold — nearly any two English tech phrases clear that — and compares each keyword against a whole 500-word section blob, because `section_chunks` splits on `\n` while section text is joined with spaces.

Canonicalise JD keywords through the ontology *before* scoring, so "React" / "React.js" / "ReactJS" collapse to one keyword rather than three independent gaps.

Report `matched` / `missing` from **one** computation. Today `keyword_details` (lowercased) and `missing_keywords` (case-sensitive `in`) disagree inside the same response — "Python" can appear in both lists.

### 5.4 Scoring without a JD — role archetypes

Your brief requires a flagship score **with or without** a job description. Today the no-JD path counts how many of 342 hard skills appear anywhere in the text and divides by 20 (`ats_scorer.py:581-598`). Twenty buzzwords scores full marks; a nurse or an accountant scores zero. It rewards exactly the stuffing that `authenticity` is supposed to catch.

The fix is to score against the **statistical profile of the target role** — Jobscan's "predicted skills" concept, generalised.

`backend/ats/ontology/archetypes/` — one YAML per normalised role, ~120 roles covering the top job families:

```yaml
id: data_analyst
titles: [data analyst, business analyst, analytics analyst, reporting analyst]
family: data
core_skills:                 # p(skill appears | role), from a JD corpus
  sql: 0.91
  excel: 0.78
  python: 0.64
  tableau: 0.55
  statistics: 0.41
expected_sections: [experience, education, skills, projects]
typical_evidence:            # what strong resumes in this role quantify
  - dashboards delivered
  - reports automated
  - data volume processed
  - stakeholders served
title_progression: [junior data analyst, data analyst, senior data analyst, analytics lead]
```

**Construction:** cluster a corpus of public job descriptions by normalised title, compute per-skill frequency, keep skills with `p ≥ 0.15`. Bootstrap with 200 hand-collected JDs for each of the top 20 roles; expand from live JDs users paste in (they already flow through `jd/extract.py` — persist them, anonymised, as a corpus that compounds over time). **This is a durable moat: every JD a user pastes makes the JD-less score better for the next user.**

**RoleFit** reuses the entire match pipeline. Synthesise a `JobTarget` from the archetype:

```python
def archetype_to_target(arch: Archetype, band: Seniority) -> JobTarget:
    return JobTarget(
        title=arch.titles[0],
        title_normalized=arch.id,
        seniority=band,
        keywords=tuple(
            JDKeyword(term=s, skill_id=s, kind=onto.kind_of(s),
                      jd_frequency=max(1, round(p * 10)),   # frequency ∝ prevalence
                      required=(p >= 0.60))                  # common enough to be expected
            for s, p in arch.core_skills.items()
        ),
        min_years=None, required_degree=None,   # an archetype states no hard requirement
        source_hash=f"archetype:{arch.id}:{band}",           # deterministic, cacheable
    )
```

One code path scores both cases; only the `JobTarget` source differs. Findings phrase themselves differently — *"SQL appears in 91% of Data Analyst postings and is missing from your resume"* rather than *"missing keyword"* — which reads as insight rather than nagging, and is the single most premium-feeling output in the report.

If the user gave no target role, infer a candidate archetype from their titles and skills and **ask them to confirm** rather than guessing silently. If confidence is low, omit RoleFit and score Strength alone (§2 formula, third case).

**Acceptance:** a strong Data Analyst resume scores `RoleFit ≥ 0.75` with no JD supplied. A strong Registered Nurse resume also scores `RoleFit ≥ 0.75` — the current engine gives it ~0.0. Swapping the target role to an unrelated one drops RoleFit by ≥ 30 points.

---

## 6. Check inventory

Port from `ats_engine/` unless marked **NEW**. Logic mostly survives; the wrapper and the honesty rules are what change.

| Dimension | Check | Source |
|---|---|---|
| IMPACT | quantified_bullets | port; widen metric regex — `10K+`, `1M`, `2.5x`, `three-fold`, `from 5s to 200ms`, bare counts all currently miss |
| | action_verbs | port; match on lemma not `split()[0]`, so `Co-led` / `Re-architected` count |
| | achievement_framing | **NEW** — outcome-vs-duty classifier (rule-based: result clause present?) |
| | scope_signals | **NEW** — team size, budget, user/request volume |
| BREVITY | resume_length | port, seniority-aware via rubric |
| | bullet_length | port |
| | filler_words | port + **fix**: `text.count("just")` matches "adjusted", `"very"` matches "every" — use `\b` |
| | buzzwords | port |
| | passive_voice | **NEW** — spaCy dep-parse, or `\b(was|were|been|being)\s+\w+ed\b` |
| STYLE | personal_pronouns | port + **fix**: `\bi\b` on lowercased text matches the "i" in "i.e." |
| | verb_tense_consistency | **NEW** — past for ended roles, present for `entry_is_current` |
| | spelling | **NEW** — `pyspellchecker` + allowlist built from the ontology |
| | punctuation_consistency | **NEW** — trailing periods uniform across bullets |
| STRUCTURE | contact_completeness | port |
| | section_presence | port |
| | section_order | **rewrite** — use headings from `resume_parser/segmenter.py`. Current version regex-searches the word anywhere, so "5 years of experience" in the summary sets the experience position to char 50 |
| | reverse_chronological | **NEW** — sort check on parsed `startDate` |
| | unnecessary_sections | port + **fix** — the `section_headers` argument is currently `sections.keys()`, a hardcoded 6-item list, so that branch never fires |
| FORMATTING | layout_parsability | port (columns/tables/scanned) — now from `LayoutFacts` |
| | page_count | **rewrite** — uploaded PDF, not re-rendered HTML |
| | ligatures | port |
| | date_format_consistency | port |
| | font_consistency | port — `LayoutFacts.font_sizes_by_section` finally supplies the argument that is currently always `None` |
| | header_footer_content | **NEW** — contact info in a PDF header is dropped by many parsers |
| AUTHENTICITY | keyword_stuffing | port — **and actually score it** |
| | duplicate_bullets | port |
| | repeated_openers | port |
| | comma_dump_bullets | port |
| GROWTH | leadership / teamwork / communication / analytical | port, thresholds from rubric |
| MATCH | hard_skills / job_title / seniority_fit / education / certifications / domain_terms | §5.3 |

### Additional checks the current system has no equivalent for

| Dimension | Check | Why premium tools have it |
|---|---|---|
| STRUCTURE | `heading_standardness` | ATS parsers key on canonical headings. "What I've Done" / "My Journey" silently drop a whole section. Map against a synonym table; warn, don't fail — a reviewer found Resume Worded *too* rigid here, so accept "Work History", "Professional Experience", "Employment". |
| STRUCTURE | `top_third_density` | Recruiter 6-second scan. Score what is extractable from the first third of page 1: name, title, top skills, most recent role. |
| STRUCTURE | `career_progression` | Title advancement over time. N/A for student/entry. Senior resumes that show flat titles for 10 years read poorly. |
| STRUCTURE | `gpa_relevance` | GPA is a *positive* for `student`, neutral for `entry`, and a mild negative for `senior`/`exec`. Same field, opposite sign by band — impossible in the current engine. |
| FORMATTING | `filename` | `resume_final_v3(2).pdf` vs `Firstname_Lastname_Resume.pdf`. Trivial to check, universally flagged by premium tools, and a genuine recruiter irritant. Requires threading the original filename onto `ResumeVersion`. |
| FORMATTING | `link_integrity` | LinkedIn/GitHub present as *text* but not a live hyperlink; default LinkedIn slugs (`/in/john-smith-8a3b91024`); dead URLs. Async HEAD check at **upload** time, cached onto `LayoutFacts` — never inside the scorer (§0 rule 2). |
| FORMATTING | `locale_conventions` | See below. |
| AUTHENTICITY | `unverifiable_superlatives` | "world-class", "best-in-class", "guru", "10x engineer" — distinct from buzzwords; these are unfalsifiable self-assessment. |
| IMPACT | `metric_plausibility` | Flag implausible claims ("increased revenue by 40,000%"). Protects the candidate from an interview ambush. |

### Locale conventions — `ontology/locales.yaml`

The current `UNNECESSARY_SECTIONS` regex (`unnecessary_sections_checker.py:12-20`) hardcodes `marital status`, `father's name`, `religion`, `nationality`, and `declaration` as universal penalties. Those are India-market résumé conventions. Penalising them is **correct** when targeting US/UK roles and **wrong** when applying domestically in markets where they remain conventional — and given this product's likely user base, that misfire will hit a large share of scans.

```yaml
US:      {photo: forbidden, dob: forbidden, personal_details: forbidden, declaration: forbidden, max_pages: 1, address: city_state_only}
UK:      {photo: forbidden, dob: forbidden, personal_details: forbidden, declaration: forbidden, max_pages: 2}
IN:      {photo: discouraged, dob: discouraged, personal_details: discouraged, declaration: discouraged, max_pages: 2}
DE:      {photo: conventional, dob: conventional, personal_details: allowed, declaration: forbidden, max_pages: 2}
```

Severity scales with the locale value: `forbidden` → high, `discouraged` → low + explanatory copy ("common in India, but drop it for US or remote-US roles"), `conventional` → no finding. Locale comes from question 3 in §2.1.

**Acceptance:** an Indian resume with a photo and DOB scores `high` severity under `locale=US` and `low` under `locale=IN`, with different copy. A German resume with a photo produces no finding under `locale=DE`.

### Checks to delete outright
- `volunteer_bonus` (`:1134-1137`) — fires on the word "achievement" appearing anywhere; near-universally true.
- `CERTIFICATION_KEYWORDS` whole-resume sweep (`:1080-1094`) — listing "Salesforce" or "Lean" as a *skill* is counted as holding a certification. Replace with the parsed `certifications` array plus a heading-anchored scan.
- `context_bonus` (`:1125-1131`) — undocumented free 5%.

---

## 7. Calibration — the part that makes it flagship

Everything above is engineering. This is the differentiator, and it is why Milestone 0 comes first.

### 7.1 Corpus
`backend/ats/eval/corpus/` — **120 resumes**, stratified 5 seniority bands × 4 domains (software, data, non-tech professional, trades/healthcare) × 6 quality levels. Sources: synthetic generation from templates, public samples, consented user uploads (anonymised). Include ~15 adversarial cases:
- keyword-stuffed twin of an honest resume
- 3-page junior resume
- scanned PDF
- two-column designer resume
- non-English-native phrasing
- career-changer with a legitimate 2-year gap
- non-tech resume with zero recognisable hard skills

### 7.2 Labels
Three independent 0–100 ratings per resume; median is ground truth. Use recruiters where possible; otherwise one human plus two LLM judges running *different* rubrics (never the same prompt twice — correlated errors are worse than noise). Store as `corpus/labels.jsonl` with rater id and rubric version.

### 7.3 Metrics (CI gates)
| Metric | Gate |
|---|---|
| Spearman ρ vs. human rank | ≥ 0.80 |
| MAE | ≤ 8 points |
| Monotonicity | Improving a resume must never lower the score — 40 paired before/after cases, 100% pass |
| Adversarial separation | Stuffed twin scores ≥ 10 points below its honest counterpart, 100% pass |
| Determinism | Same input × 10 runs → identical bytes |
| Points invariant | §4.4 holds for all 120 |
| Band sanity | Non-tech resumes are not systematically ≥ 8 points below equivalent-quality tech resumes |

### 7.4 Weight fitting
Do **not** hand-tune. Set plausible bounds per dimension (e.g. IMPACT ∈ [0.18, 0.32]), then fit via constrained least squares against the labelled corpus, subject to `sum == 1.0`. Refit whenever the corpus grows by 20%. Hand-tuning is how `quantified_impact` ended up at 0.30 while `style` sits at 0.02 — a legitimately useful check with negligible influence.

### 7.5 Score distribution
Target median ≈ 62, p90 ≈ 85, p99 ≈ 94. Apply a monotone calibration curve as the final step if the raw distribution is compressed. Publish bands in the UI (90+ exceptional / 80–89 strong / 65–79 solid / 50–64 needs work / <50 significant issues), matching how Resume Worded frames 85+ as the target.

### 7.6 Golden files
Every corpus resume has its full `ScoreReport` JSON checked into `eval/golden/`. Any diff fails CI and must be explicitly re-blessed with a note. **This is the mechanism that would have caught `structure_completeness_val` going dark**, and it is worth more than any single test.

---

## 8. The report layer — what makes a score feel premium

A correct number is table stakes. What users actually pay for at Jobscan and Resume Worded is the *report around* the number. None of the following exists in the current system, and most of it falls out of the §4.4 honest-points model for almost no extra work.

### 8.1 Score bands
Calibrated in §7.5, with copy attached. `90+` exceptional / `80–89` strong / `65–79` solid, needs work / `50–64` significant gaps / `<50` not ready to send. Resume Worded frames 85+ as the target; match that expectation so a user moving between tools isn't whiplashed.

### 8.2 Dimension dashboard
Seven bars (Impact, Brevity, Style, Structure, Formatting, Authenticity, Growth), each 0–100 with its own band, plus **"24 of 31 checks passed"**. Checks marked N/A for the user's band are shown greyed with "not applicable at your career level" — this is how the student *sees* that they weren't penalised, which matters as much as not being penalised.

### 8.3 Fix simulation — "+X points"
The highest-perceived-value feature in this document, and nearly free given §4.4:

```python
def simulate_fixes(doc, jd, report, top_n=5) -> list[tuple[Finding, float]]:
    base = report.headline
    out = []
    for f in report.findings:
        if f.fix and f.fix.kind == "transform":        # machine-applicable doc edit
            out.append((f, round(score(f.fix.apply(doc), jd).headline - base, 1)))
        else:                                          # can't auto-write a metric
            out.append((f, estimate_delta(report, f)))  # set that check to 1.0, redo the
                                                        # scorer arithmetic only — cheap
    return sorted(out, key=lambda t: -t[1])[:top_n]
```

Two tiers, labelled honestly in the UI: `simulated` (exact — we applied the change and rescored) and `estimated` (arithmetic projection). Surface as *"Fix these 3 things → 62 → 78."* This turns a static grade into a workflow, which is the entire Jobscan product loop.

Requires `Fix` to be a structured object, not prose:
```python
@dataclass(frozen=True)
class Fix:
    kind: Literal["transform", "guidance"]
    description: str
    apply: Callable[[ResumeDoc], ResumeDoc] | None
    target: Anchor | None
```

### 8.4 Peer percentile
"Top 18% of Mid-level Software Engineers." New table `score_distributions(band, domain, has_jd, histogram, n, updated_at)`, refreshed nightly from anonymised scores. Suppress the claim until `n ≥ 200` in that cell and fall back to the §7 corpus distribution. This is the single strongest trust signal premium tools deploy, and it costs one nightly job.

### 8.5 Re-scan diff
Persist every `ScoreReport`. On re-scan show per-dimension deltas and which findings resolved, appeared, or persisted: *"Impact 54 → 71. Resolved 4 issues. 1 new issue."* Jobscan's whole retention model is scan → fix → rescan; without the diff, users can't feel progress.

### 8.6 Recruiter view
Render the top third of page 1 and list exactly what a recruiter extracts in six seconds. Pairs with `structure.top_third_density`.

### 8.7 Transparency panel
"Why this score" — dimension weights used, band applied, checks skipped and why, ledger entries charged. Ship it. Every competitor is opaque here, and given §4.4 makes the arithmetic exact, transparency is a differentiator rather than a liability.

**Acceptance:** simulated deltas reconcile — applying the top 3 simulated fixes and rescoring lands within ±2 points of the predicted total. N/A checks are visibly marked, not hidden.

---

## 9. Milestones

Each milestone is independently shippable and leaves the current engine serving traffic.

### M0 — Harness and corpus *(no scoring changes; blocks everything)*
- `backend/ats/eval/` — corpus loader, label store, metric runner, golden-file differ.
- 120 labelled resumes, **stratified across all five career bands** (§2.1) — at minimum 20 `student` and 20 `senior`/`exec`, since band-specific behaviour is the thing most likely to regress unnoticed.
- Run the **current** engine against the corpus and record its baseline metrics. Expect ρ ≈ 0.4–0.6, and expect student resumes to be systematically under-scored — quantify that gap now so M4 can prove it closed.
- **Acceptance:** `pytest backend/ats/eval -m corpus` prints a metrics table for v2, broken out per band. Baseline committed to `eval/BASELINE_v2.md`.

### M1 — Document model + career level plumbing
- `models.py`, `doc_builder.py`, `layout_probe.py`, `profile.py`.
- Alembic migration: `resume_versions.layout_facts JSON`, `resume_versions.original_filename`, `users.career_level`, `users.target_role`, `users.locale`.
- `profile.py` implements `band_from_parsed_dates()` and the `max(declared, inferred_floor)` rule (§2.1).
- Frontend: the three-question screen, shown once, editable in settings.
- API: `career_level`, `target_role`, `locale` accepted on `/analyze` and `/analyze-text`, defaulting to the stored user values.
- **Acceptance:** every corpus resume builds a `ResumeDoc`. Lint test proves `layout_raw` is referenced only in `checks/formatting.py`. Construction deterministic across 10 runs. A resume declaring `student` with 10 years of dated experience resolves to `effective_band == "senior"`.

### M2 — Check framework + port
- `checks/base.py` registry; port every existing check; wire the two orphans (`authenticity`, `structure`).
- Implement `applies_to` / `disabled_checks` and `None`-score weight redistribution.
- **Acceptance:** registry-completeness test passes. Every dimension has ≥1 check. Every id in `DISABLED` exists in the registry. No check returns a hardcoded point value — assert `Finding.points == 0.0` on every check's direct output.

### M3 — Ontology, JD engine, role archetypes
- `skills.yaml` (~1500), `titles.yaml`, `locales.yaml`, loader, `jd/extract.py`, `jd/fallback.py`, `checks/match.py`.
- `ontology/archetypes/` — 20 hand-built roles minimum, plus the JD-harvesting job that grows the corpus from user-pasted JDs (§5.4).
- **Acceptance:** perfect-match synthetic resume scores `Match ≥ 0.95` (proves the 0.44 ceiling is gone). "AWS" ↔ "Amazon Web Services" matches. A nursing JD yields ≥ 10 keywords. A strong nurse resume scores `RoleFit ≥ 0.75` with no JD. `matched ∪ missing` is exactly the keyword set, disjointly.

### M4 — Scorer + rubrics
- `rubric.py` (five bands, full applicability matrix), `ledger.py`, `scorer.py`, `version.py`, score assembly.
- **Acceptance:** every band's weights sum to 1.0. Points invariant holds on all 120. Ledger audit passes (no double-charging). Identical input → identical bytes. **The same student resume scores ≥ 15 points higher under `student` than `mid`, and incurs zero experience-section deductions.** The v2 student under-scoring gap measured in M0 is closed.

### M5 — Calibration
- Fit weights **per band** (five vectors), tune the distribution, bless golden files.
- **Acceptance:** all §7.3 gates pass, evaluated per band as well as overall — a good overall ρ that hides a broken `student` band is a failure. v3 beats the v2 baseline on ρ by ≥ 0.15.

### M6 — Report layer
- Dimension dashboard, band copy, N/A display, fix simulation (§8.3), re-scan diff, transparency panel.
- `score_distributions` table + nightly aggregation job for percentile (§8.4).
- **Acceptance:** applying the top 3 simulated fixes and rescoring lands within ±2 points of the prediction. N/A checks visibly marked. Percentile suppressed below `n = 200`.

### M7 — Remaining checks, API, cutover
- Spelling, passive voice, tense, chronology, header/footer, filename, link integrity, locale conventions, top-third density.
- `api_adapter.py` maps `ScoreReport` onto the shape the frontend already consumes; add `scoring_version` and the sub-scores.
- **Shadow mode:** run v2 and v3 on every real request for two weeks, log both, serve v2. Compare distributions **per band**. Then flip a feature flag.
- Delete the dead code listed in §1.
- **Acceptance:** shadow divergence report reviewed. Frontend renders all sub-scores. `ats_scorer.py`, both `ats_analyzer*.py` agents, and the unused `score_engine_v2` exports are gone.

---

## 10. Non-functional requirements

| Requirement | Target | Why |
|---|---|---|
| Scoring latency (no JD) | < 150 ms p95 | Pure functions, no I/O. Current engine does an LLM call, an embedding batch, and a full PDF re-render. |
| Scoring latency (with JD, cached) | < 250 ms p95 | JD extraction is upstream and cached by `source_hash`. |
| Determinism | byte-identical | CI gate. |
| `scoring_version` | in every response | Stored on the analysis row, so a score that changes after a deploy is explainable. |
| Debug payload | full `CheckResult` list behind an internal flag | Never shipped to end users. |
| Observability | log dimension sub-scores + ledger entries per request | Drift detection. |

---

## 11. Open decisions for the human

1. **Corpus labelling budget.** 120 resumes × 3 raters is the single largest cost in this plan and the single biggest determinant of quality. If recruiter time is unavailable, the LLM-judge fallback in §7.2 is acceptable but should be disclosed in `eval/BASELINE_v2.md`.
2. **Three career bands or five.** §2.1 argues for five and explains why; you asked for three. My recommendation is five, but it's your product — if you take three, merge `entry`→`student` and `senior`→`exec` rather than dropping `mid`, and accept that 4–7 year candidates will be scored against a bar tuned for 2–3.
3. **Ontology sourcing.** ESCO is CC-BY and safe. Confirm licensing before importing any commercial skills taxonomy.
4. **Archetype corpus.** 20 hand-built roles is enough to ship; 120 needs a JD corpus. Decide whether to buy a JD dataset or grow it from user-pasted JDs (§5.4) — the latter is free and compounding but slow to start, so the first 6 months of RoleFit will cover only the top 20 roles.
5. **Percentile privacy.** §8.4 aggregates user scores. Confirm this is covered by the privacy policy, and enforce the `n ≥ 200` suppression floor so no cell can identify an individual.
6. **Free vs. paid split.** Score + band + issue count free; itemised findings, fix simulation, and percentile gated is the industry-standard line. A business decision, but the architecture should not assume everything is free.
7. **spaCy dependency.** Passive voice and tense checking are far more accurate with a dep-parse (`en_core_web_sm`, ~13 MB). Regex fallbacks exist but will misfire on ~15% of bullets. Decide before M7.
8. **Shadow-mode duration.** Two weeks assumes reasonable traffic. Adjust to whatever yields ≥ 500 paired scores, with ≥ 50 per career band.
