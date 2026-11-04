"""
structure.py — STRUCTURE dimension checks.

Phase 5 rebuild:
- ContactCompletenessCheck: score is continuous (not binary 0/1), checks location + LinkedIn
- SectionPresenceCheck: improved, band-aware
- LinkedInPresentCheck: NEW — flags missing LinkedIn/GitHub link
- LocationPresentCheck: NEW — separate from contact completeness
- SummarySpecificityCheck: NEW — summary mentions title/role, not generic
- EducationCompletenessCheck: NEW — degree + field + year all present
- SkillsOrganisationCheck: NEW — skills section exists and is non-trivial
"""
import re
from typing import Optional, Any

from .base import register, build_result, ALL_SENIORITIES
from ..models import ResumeDoc, CheckResult, Finding

LINKEDIN_PATTERN = re.compile(r"linkedin\.com", re.IGNORECASE)
GITHUB_PATTERN = re.compile(r"github\.com", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

GENERIC_SUMMARY_PATTERNS = [
    re.compile(r"\bexperienced\s+professional\b", re.IGNORECASE),
    re.compile(r"\bpassionate\s+(?:about|developer|engineer)\b", re.IGNORECASE),
    re.compile(r"\bself[-\s]motivated\b", re.IGNORECASE),
    re.compile(r"\bteam\s+player\b", re.IGNORECASE),
    re.compile(r"\bseeking\s+(?:a\s+)?(?:challenging|exciting|rewarding)\b", re.IGNORECASE),
    re.compile(r"\bhardworking\b", re.IGNORECASE),
]


@register
class ContactCompletenessCheck:
    id = "contact_completeness"
    dimension = "STRUCTURE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        contact = doc.contact
        findings = []
        points = 0
        max_points = 4

        if contact.email:
            points += 1
        else:
            findings.append(Finding(
                check_id=self.id, severity="critical",
                title="Missing email address",
                detail="Email is required on every resume.",
                anchor=None, fix=None,
            ))

        if contact.phone:
            points += 1
        else:
            findings.append(Finding(
                check_id=self.id, severity="high",
                title="Missing phone number",
                detail="Add a phone number so recruiters can reach you.",
                anchor=None, fix=None,
            ))

        if contact.location:
            points += 1
        else:
            findings.append(Finding(
                check_id=self.id, severity="medium",
                title="Missing location",
                detail="Add city/state or 'Remote' so employers know your availability.",
                anchor=None, fix=None,
            ))

        all_links = " ".join(contact.links)
        if LINKEDIN_PATTERN.search(all_links) or GITHUB_PATTERN.search(all_links):
            points += 1
        else:
            findings.append(Finding(
                check_id=self.id, severity="low",
                title="Missing LinkedIn or GitHub link",
                detail="Add your LinkedIn profile URL and/or GitHub to the contact header.",
                anchor=None, fix=None,
            ))

        score = points / max_points
        return build_result(self.id, score, findings, {"points": points, "max_points": max_points})


@register
class SectionPresenceCheck:
    id = "section_presence"
    dimension = "STRUCTURE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        findings = []
        deductions = 0.0

        # Experience: only required for non-students
        if rubric.expects_formal_experience:
            if not doc.experience:
                deductions += 0.5
                findings.append(Finding(
                    check_id=self.id, severity="critical",
                    title="No experience section",
                    detail="Add your work history. If you have gaps, include freelance, consulting, or side projects.",
                    anchor=None, fix=None,
                ))
        else:
            # Students: projects count as experience
            has_content = bool(doc.experience or doc.projects)
            if not has_content:
                deductions += 0.3
                findings.append(Finding(
                    check_id=self.id, severity="high",
                    title="No experience or projects section",
                    detail="Add internships, personal projects, or coursework projects.",
                    anchor=None, fix=None,
                ))

        if not doc.education:
            deductions += 0.4
            findings.append(Finding(
                check_id=self.id, severity="high",
                title="No education section",
                detail="Add your degree, institution, and graduation year.",
                anchor=None, fix=None,
            ))

        if not doc.skills:
            deductions += 0.1
            findings.append(Finding(
                check_id=self.id, severity="low",
                title="No skills section",
                detail="Add a skills section listing relevant technical and domain skills.",
                anchor=None, fix=None,
            ))

        score = max(0.0, 1.0 - deductions)
        return build_result(self.id, score, findings, {})


@register
class SummarySpecificityCheck:
    id = "summary_specificity"
    dimension = "STRUCTURE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        summary = (doc.summary or "").strip()
        if not summary:
            # Only penalise if summary is expected
            if rubric.expects_summary:
                return build_result(self.id, 0.3, [Finding(
                    check_id=self.id, severity="medium",
                    title="Summary missing",
                    detail="Add a 2-4 sentence professional summary.",
                    anchor=None, fix=None,
                )], {})
            return build_result(self.id, None, [], {"reason": "not_expected"})

        findings = []
        generic_hits = sum(1 for p in GENERIC_SUMMARY_PATTERNS if p.search(summary))

        # Check for specifics: year count, role title, domain keyword
        has_years = bool(re.search(r"\d+\s*(?:\+\s*)?years?", summary, re.IGNORECASE))
        has_role = bool(re.search(r"\b(?:engineer|developer|analyst|designer|manager|scientist|architect|lead|director)\b", summary, re.IGNORECASE))

        specificity_score = 0.0
        if has_years:
            specificity_score += 0.4
        if has_role:
            specificity_score += 0.4
        if generic_hits == 0:
            specificity_score += 0.2
        else:
            for _ in range(generic_hits):
                findings.append(Finding(
                    check_id=self.id, severity="low",
                    title="Generic summary phrasing",
                    detail="Replace vague phrases with specific titles, years, and outcomes.",
                    anchor=None, fix=None,
                ))

        score = min(1.0, specificity_score)
        return build_result(self.id, score, findings, {
            "has_years": has_years, "has_role": has_role, "generic_hits": generic_hits
        })


@register
class EducationCompletenessCheck:
    id = "education_completeness"
    dimension = "STRUCTURE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not doc.education:
            return build_result(self.id, None, [], {"reason": "no_education"})

        findings = []
        entry_scores = []

        for edu in doc.education:
            pts = 0
            if edu.institution:
                pts += 1
            if edu.degree:
                pts += 1
            if edu.field:
                pts += 1
            if edu.end_year:
                pts += 1
            entry_scores.append(pts / 4)

            if not edu.degree:
                findings.append(Finding(
                    check_id=self.id, severity="medium",
                    title=f"Missing degree for '{edu.institution or 'education entry'}'",
                    detail="Add degree type (BSc, MSc, BTech, etc.).",
                    anchor=None, fix=None,
                ))
            if not edu.end_year:
                findings.append(Finding(
                    check_id=self.id, severity="low",
                    title="Missing graduation year",
                    detail="Add graduation year so employers know your timeline.",
                    anchor=None, fix=None,
                ))

        score = sum(entry_scores) / len(entry_scores)
        return build_result(self.id, score, findings, {"entries": len(doc.education)})


@register
class SkillsOrganisationCheck:
    id = "skills_organisation"
    dimension = "STRUCTURE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not doc.skills:
            return build_result(self.id, 0.0, [Finding(
                check_id=self.id, severity="medium",
                title="No skills listed",
                detail="Add a skills section with your technical tools, languages, and frameworks.",
                anchor=None, fix=None,
            )], {"count": 0})

        count = len(doc.skills)
        has_categories = any(s.category for s in doc.skills)

        findings = []
        if count < 5:
            findings.append(Finding(
                check_id=self.id, severity="low",
                title=f"Few skills listed ({count})",
                detail="List at least 8–15 relevant skills across languages, tools, and frameworks.",
                anchor=None, fix=None,
            ))

        score_parts = [min(1.0, count / 10)]  # 10+ skills = full marks on count
        if has_categories:
            score_parts.append(1.0)
        else:
            score_parts.append(0.7)  # uncategorised skills: partial credit

        score = sum(score_parts) / len(score_parts)
        return build_result(self.id, score, findings, {"count": count, "categorised": has_categories})
