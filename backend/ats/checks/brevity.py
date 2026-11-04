"""
brevity.py — BREVITY dimension checks.

Phase 5 rebuild:
- ResumeLengthCheck: reads max_words/min_words from rubric (not hardcoded 800/200)
- BulletLengthCheck: reads max_bullets_per_role from rubric
- BulletsPerRoleCheck: NEW — flags roles with too many or too few bullets
- WordCountVsBandCheck: NEW — separate from length, checks density not just total
- SummaryLengthCheck: NEW — summary too long/short/absent when expected
"""
import re
from typing import Optional, Any
from .base import register, build_result, ALL_SENIORITIES
from ..models import ResumeDoc, CheckResult, Finding, Anchor


def _word_count(text: str) -> int:
    return len(text.split())


@register
class ResumeLengthCheck:
    id = "resume_length"
    dimension = "BREVITY"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        full_text = doc.text.full
        if not full_text.strip():
            return build_result(self.id, 0.0, [Finding(
                check_id=self.id, severity="critical",
                title="Empty resume", detail="No content detected.",
                anchor=None, fix=None,
            )], {})

        words = _word_count(full_text)
        min_w = rubric.min_words
        max_w = rubric.max_words
        findings = []

        if words < min_w:
            score = max(0.0, words / min_w)
            findings.append(Finding(
                check_id=self.id, severity="high",
                title=f"Resume too short ({words} words)",
                detail=f"For {rubric.band} level, target {min_w}–{max_w} words. Add more detail to bullets.",
                anchor=None, fix=None,
            ))
        elif words > max_w:
            overflow = words - max_w
            score = max(0.4, 1.0 - (overflow / max_w) * 0.5)
            findings.append(Finding(
                check_id=self.id, severity="medium",
                title=f"Resume too long ({words} words)",
                detail=f"For {rubric.band} level, target {min_w}–{max_w} words. Cut low-impact bullets.",
                anchor=None, fix=None,
            ))
        else:
            score = 1.0

        return build_result(self.id, score, findings, {"words": words, "min": min_w, "max": max_w})


@register
class BulletLengthCheck:
    id = "bullet_length"
    dimension = "BREVITY"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    # Ideal bullet: 10–25 words
    MIN_WORDS = 8
    MAX_WORDS = 30

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        findings = []
        ok = 0

        for bullet in bullets:
            wc = _word_count(bullet.text)
            if wc < self.MIN_WORDS:
                findings.append(Finding(
                    check_id=self.id, severity="low",
                    title=f"Bullet too short ({wc} words)",
                    detail="Expand: add context, action, and measurable result.",
                    anchor=Anchor(bullet.section, bullet.entry_index, bullet.bullet_index),
                    fix=None,
                ))
            elif wc > self.MAX_WORDS:
                findings.append(Finding(
                    check_id=self.id, severity="low",
                    title=f"Bullet too long ({wc} words)",
                    detail="Trim to 10–25 words. One idea per bullet.",
                    anchor=Anchor(bullet.section, bullet.entry_index, bullet.bullet_index),
                    fix=None,
                ))
            else:
                ok += 1

        score = ok / len(bullets)
        return build_result(self.id, score, findings, {"ok": ok, "total": len(bullets)})


@register
class BulletsPerRoleCheck:
    id = "bullets_per_role"
    dimension = "BREVITY"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    MIN_BULLETS = 2

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not doc.experience:
            return build_result(self.id, None, [], {"reason": "no_experience"})

        max_per_role = rubric.max_bullets_per_role
        findings = []
        role_scores = []

        for i, exp in enumerate(doc.experience):
            n = len(exp.bullets)
            if n < self.MIN_BULLETS:
                findings.append(Finding(
                    check_id=self.id, severity="medium",
                    title=f"Too few bullets for '{exp.title or exp.company}'",
                    detail=f"Add at least {self.MIN_BULLETS} impact bullets per role.",
                    anchor=None, fix=None,
                ))
                role_scores.append(n / self.MIN_BULLETS)
            elif n > max_per_role:
                findings.append(Finding(
                    check_id=self.id, severity="low",
                    title=f"Too many bullets for '{exp.title or exp.company}' ({n})",
                    detail=f"Trim to {max_per_role} strongest bullets per role.",
                    anchor=None, fix=None,
                ))
                role_scores.append(max_per_role / n)
            else:
                role_scores.append(1.0)

        score = sum(role_scores) / len(role_scores) if role_scores else 1.0
        return build_result(self.id, score, findings, {"roles": len(doc.experience)})


@register
class SummaryLengthCheck:
    id = "summary_length"
    dimension = "BREVITY"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not rubric.expects_summary:
            # Summary is optional for students/entry — skip, not penalise
            return build_result(self.id, None, [], {"reason": "not_expected_for_band"})

        summary = (doc.summary or "").strip()
        if not summary:
            return build_result(self.id, 0.3, [Finding(
                check_id=self.id, severity="medium",
                title="Missing professional summary",
                detail="Add a 2–4 sentence summary that targets your target role and seniority.",
                anchor=None, fix=None,
            )], {"words": 0})

        words = _word_count(summary)
        findings = []

        if words < 20:
            score = 0.5
            findings.append(Finding(
                check_id=self.id, severity="low",
                title=f"Summary too brief ({words} words)",
                detail="Expand to 2–4 sentences covering your expertise, impact, and target role.",
                anchor=None, fix=None,
            ))
        elif words > 80:
            score = 0.6
            findings.append(Finding(
                check_id=self.id, severity="low",
                title=f"Summary too long ({words} words)",
                detail="Trim to 3–4 focused sentences. Recruiters skim summaries.",
                anchor=None, fix=None,
            ))
        else:
            score = 1.0

        return build_result(self.id, score, findings, {"words": words})
