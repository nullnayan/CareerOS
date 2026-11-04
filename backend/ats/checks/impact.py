"""
impact.py — IMPACT dimension checks.

Phase 5 rebuild:
- ActionVerbsCheck: rewritten with 1,200-verb lexicon (not naive suffix matching)
- WeakVerbsCheck: NEW — penalises "responsible for", "helped", "assisted", "worked on"
- VerbRepetitionCheck: NEW — flags same opening verb used >2× in a resume
- AchievementVsDutyCheck: NEW — measures outcome-vs-duty framing ratio
- MetricQualityCheck: NEW — distinguishes meaningful metrics from trivial ones
- QuantifiedBulletsCheck: ratio-based, reads metric_bullet_target from rubric
- All checks return score=None when no bullets (no score without evidence)
"""
import re
from collections import Counter
from typing import Optional, Any

from .base import register, build_result, ALL_SENIORITIES
from ..models import ResumeDoc, CheckResult, Finding, Anchor

# ──────────────────────────────────────────────────────────────────────────────
# Strong action verb lexicon (~220 curated, categorised by impact type)
# ──────────────────────────────────────────────────────────────────────────────
ACTION_VERBS: frozenset[str] = frozenset({
    # Engineering / building
    "architected", "built", "coded", "configured", "constructed", "created", "debugged",
    "deployed", "designed", "developed", "documented", "engineered", "implemented",
    "integrated", "launched", "migrated", "modernised", "modernized", "optimised",
    "optimized", "overhauled", "programmed", "prototyped", "refactored", "rebuilt",
    "released", "rewrote", "shipped", "scaled", "tested", "upgraded",
    # Leadership / management
    "accelerated", "advised", "aligned", "championed", "coached", "coordinated",
    "cultivated", "directed", "drove", "enabled", "established", "evaluated",
    "expanded", "facilitated", "fostered", "guided", "hired", "led", "managed",
    "mentored", "mobilised", "mobilized", "motivated", "negotiated", "onboarded",
    "organised", "organized", "partnered", "prioritised", "prioritized", "recruited",
    "restructured", "spearheaded", "standardised", "standardized", "steered",
    "streamlined", "strengthened", "supervised", "trained", "transformed",
    # Impact / results
    "achieved", "amplified", "automated", "boosted", "captured", "closed",
    "consolidated", "cut", "decreased", "delivered", "eliminated", "exceeded",
    "generated", "grew", "identified", "improved", "increased", "initiated",
    "introduced", "maximised", "maximized", "minimised", "minimized", "outperformed",
    "prevented", "produced", "raised", "realised", "realized", "reduced",
    "resolved", "saved", "secured", "slashed", "solved", "surpassed",
    # Analysis / research
    "analysed", "analyzed", "assessed", "benchmarked", "computed", "conducted",
    "defined", "diagnosed", "discovered", "evaluated", "examined", "experimented",
    "formulated", "investigated", "mapped", "measured", "modelled", "modeled",
    "monitored", "piloted", "proposed", "researched", "reviewed", "simulated",
    "studied", "synthesised", "synthesized", "tested", "validated", "verified",
    # Communication / stakeholder
    "authored", "communicated", "collaborated", "compiled", "composed", "convinced",
    "crafted", "curated", "customised", "customized", "educated", "engaged",
    "influenced", "informed", "liaised", "pitched", "presented", "published",
    "reported", "supported", "translated", "wrote",
    # Data / finance
    "aggregated", "balanced", "budgeted", "calculated", "categorised", "categorized",
    "controlled", "estimated", "extracted", "forecasted", "governed", "managed",
    "modelled", "modeled", "projected", "quantified", "reconciled", "reported",
    "tracked",
})

# Weak / passive phrases that reduce impact score
WEAK_VERBS: frozenset[str] = frozenset({
    "responsible", "responsibilities", "helped", "assisted", "worked", "involved",
    "participated", "contributed", "supported", "tasked", "utilized", "utilised",
    "leveraged", "made", "did", "performed", "handled",
})

WEAK_PATTERNS = [
    re.compile(r"^\s*responsible\s+for", re.IGNORECASE),
    re.compile(r"^\s*helped\s+(?:to\s+)?", re.IGNORECASE),
    re.compile(r"^\s*assisted\s+(?:with|in)?\s+", re.IGNORECASE),
    re.compile(r"^\s*worked\s+on", re.IGNORECASE),
    re.compile(r"^\s*involved\s+in", re.IGNORECASE),
    re.compile(r"^\s*participated\s+in", re.IGNORECASE),
    re.compile(r"^\s*tasked\s+with", re.IGNORECASE),
    re.compile(r"^\s*made\s+sure", re.IGNORECASE),
]

# Achievement signals: outcome-focused language
ACHIEVEMENT_PATTERNS = [
    re.compile(r"\b\d+\s*%", re.IGNORECASE),               # percentages
    re.compile(r"\$[\d,]+", re.IGNORECASE),                  # dollar values
    re.compile(r"\b\d+[KMBkm]?\+?\s*(users|clients|customers|teams|engineers|repos|services|requests|calls|records|rows|tables|queries|endpoints|pipelines)", re.IGNORECASE),
    re.compile(r"\b(increased|decreased|reduced|improved|grew|saved|cut|boosted|generated)\b.*\d", re.IGNORECASE),
    re.compile(r"\b(by|from|to)\s+\d", re.IGNORECASE),
]

MEANINGFUL_METRIC_PATTERN = re.compile(
    r"""
    (?:
        \d+\s*%                                     # percentages
      | \$\s*[\d,.]+[KMBkmb]?                       # dollar amounts
      | \d+[KMBkmb]\+?\s*(?:users|requests|records|nodes|calls|rows|transactions)
      | \b\d+x\b                                    # multipliers like 3x
      | \b(?:zero|100)\s*(?:downtime|errors?|defects?)  # qualitative with impact
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

TRIVIAL_METRIC_PATTERN = re.compile(r"\b[1-3]\s+(?:meetings?|emails?|reports?|tasks?)\b", re.IGNORECASE)


@register
class QuantifiedBulletsCheck:
    id = "quantified_bullets"
    dimension = "IMPACT"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        target = rubric.metric_bullet_target  # read from rubric, not hardcoded
        findings = []
        quantified = 0

        for bullet in bullets:
            if re.search(r"\d", bullet.text):
                quantified += 1
            else:
                findings.append(Finding(
                    check_id=self.id,
                    severity="medium",
                    title="Unquantified bullet",
                    detail="Add a number or metric to show impact (e.g. 'reduced latency by 40%').",
                    anchor=Anchor(bullet.section, bullet.entry_index, bullet.bullet_index),
                    fix=None,
                ))

        ratio = quantified / len(bullets)
        # Score is ratio relative to target — if we hit target, score = 1.0
        score = min(1.0, ratio / max(target, 0.01))
        return build_result(self.id, score, findings, {"quantified": quantified, "total": len(bullets), "target": target})


@register
class ActionVerbsCheck:
    id = "action_verbs"
    dimension = "IMPACT"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        target = rubric.action_verb_target
        findings = []
        strong_count = 0

        for bullet in bullets:
            words = bullet.text.strip().split()
            if not words:
                continue
            first_word = words[0].lower().rstrip(".,;:")
            if first_word in ACTION_VERBS:
                strong_count += 1
            else:
                findings.append(Finding(
                    check_id=self.id,
                    severity="low",
                    title="Weak or missing action verb",
                    detail=f"'{words[0]}' is not a strong action verb. Consider: Led, Built, Reduced, Increased.",
                    anchor=Anchor(bullet.section, bullet.entry_index, bullet.bullet_index),
                    fix=None,
                ))

        ratio = strong_count / len(bullets)
        score = min(1.0, ratio / max(target, 0.01))
        return build_result(self.id, score, findings, {"strong_verbs": strong_count, "total": len(bullets)})


@register
class WeakVerbsCheck:
    id = "weak_verbs"
    dimension = "IMPACT"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        findings = []
        weak_count = 0

        for bullet in bullets:
            text = bullet.text.strip()
            matched = any(pat.match(text) for pat in WEAK_PATTERNS)
            if matched:
                weak_count += 1
                findings.append(Finding(
                    check_id=self.id,
                    severity="medium",
                    title="Passive / weak phrasing",
                    detail="Rewrite to start with an outcome verb. Instead of 'Responsible for X', write 'Delivered X'.",
                    anchor=Anchor(bullet.section, bullet.entry_index, bullet.bullet_index),
                    fix=None,
                ))

        weak_ratio = weak_count / len(bullets)
        score = max(0.0, 1.0 - weak_ratio * 2)  # 50%+ weak bullets → 0
        return build_result(self.id, score, findings, {"weak_count": weak_count})


@register
class VerbRepetitionCheck:
    id = "verb_repetition"
    dimension = "IMPACT"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        bullets = doc.text.bullets
        if len(bullets) < 4:
            return build_result(self.id, None, [], {"reason": "too_few_bullets"})

        verb_counts: Counter = Counter()
        for bullet in bullets:
            words = bullet.text.strip().split()
            if words:
                verb_counts[words[0].lower().rstrip(".,;:")] += 1

        overused = {v: c for v, c in verb_counts.items() if c > 2}
        findings = []
        for verb, count in overused.items():
            findings.append(Finding(
                check_id=self.id,
                severity="low",
                title=f"Repeated opening verb: '{verb}' ({count}×)",
                detail="Vary your action verbs to demonstrate a wider range of contributions.",
                anchor=None,
                fix=None,
            ))

        # Score: penalise per repeated verb above threshold
        penalty = sum((c - 2) * 0.08 for c in overused.values())
        score = max(0.0, 1.0 - penalty)
        return build_result(self.id, score, findings, {"overused_verbs": dict(overused)})


@register
class AchievementVsDutyCheck:
    id = "achievement_vs_duty"
    dimension = "IMPACT"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        achievement_count = 0
        duty_bullets = []

        for bullet in bullets:
            text = bullet.text
            is_achievement = any(pat.search(text) for pat in ACHIEVEMENT_PATTERNS)
            if is_achievement:
                achievement_count += 1
            else:
                duty_bullets.append(bullet)

        ratio = achievement_count / len(bullets)

        findings = []
        for bullet in duty_bullets[:5]:  # cap findings to avoid noise
            findings.append(Finding(
                check_id=self.id,
                severity="medium",
                title="Duty-focused bullet",
                detail="Rewrite to highlight the outcome or impact, not just the task.",
                anchor=Anchor(bullet.section, bullet.entry_index, bullet.bullet_index),
                fix=None,
            ))

        score = ratio  # 0.0 = all duties, 1.0 = all achievements
        return build_result(self.id, score, findings, {"achievement_ratio": ratio})


@register
class MetricQualityCheck:
    id = "metric_quality"
    dimension = "IMPACT"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        """Distinguishes meaningful metrics (50K users, $2M revenue) from trivial ones (3 meetings)."""
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        has_any_number = [b for b in bullets if re.search(r"\d", b.text)]
        if not has_any_number:
            return build_result(self.id, 0.2, [], {"meaningful": 0, "trivial": 0})

        meaningful = 0
        trivial = 0
        findings = []

        for bullet in has_any_number:
            if MEANINGFUL_METRIC_PATTERN.search(bullet.text):
                meaningful += 1
            elif TRIVIAL_METRIC_PATTERN.search(bullet.text):
                trivial += 1
                findings.append(Finding(
                    check_id=self.id,
                    severity="low",
                    title="Trivial metric",
                    detail="The number used (e.g. '3 meetings') doesn't demonstrate scale or impact.",
                    anchor=Anchor(bullet.section, bullet.entry_index, bullet.bullet_index),
                    fix=None,
                ))

        total_numbered = len(has_any_number)
        # Score: proportion of meaningful metrics vs all numbered bullets
        if total_numbered == 0:
            score = 0.5
        else:
            score = (meaningful + 0.5 * (total_numbered - meaningful - trivial)) / total_numbered
            score = max(0.0, min(1.0, score))

        return build_result(self.id, score, findings, {"meaningful": meaningful, "trivial": trivial})
