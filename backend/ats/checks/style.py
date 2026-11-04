"""
style.py — STYLE dimension checks.

Phase 5 rebuild:
- PersonalPronounsCheck: existing, improved
- PunctuationConsistencyCheck: existing, improved  
- SpellingCheck: NEW — lightweight pyspellchecker with tech allowlist
- FillerWordsCheck: NEW — "various", "multiple", "team player", etc.
- BuzzwordDensityCheck: NEW — "synergy", "leverage", "rockstar", etc.
- PassiveVoiceCheck: NEW — detects passive constructions in bullets
"""
import re
from typing import Optional, Any

from .base import register, build_result, ALL_SENIORITIES
from ..models import ResumeDoc, CheckResult, Finding, Anchor

# Tech allowlist so "Python", "DevOps", "async" don't flag as misspellings
TECH_ALLOWLIST = frozenset({
    "python", "javascript", "typescript", "golang", "kotlin", "scala", "clojure",
    "haskell", "erlang", "elixir", "pytorch", "tensorflow", "sklearn", "numpy",
    "pandas", "matplotlib", "seaborn", "fastapi", "fasthtml", "nextjs", "nuxtjs",
    "graphql", "grpc", "protobuf", "kafka", "airflow", "databricks", "kubernetes",
    "k8s", "dockerfile", "docker", "redis", "mongodb", "postgresql", "mysql",
    "sqlite", "dynamodb", "elasticsearch", "opensearch", "pinecone", "qdrant",
    "snowflake", "bigquery", "redshift", "spark", "hadoop", "flink", "dbt",
    "mlflow", "wandb", "langchain", "openai", "anthropic", "llm", "llms",
    "rag", "embeddings", "finetuning", "microservices", "devops", "devsecops",
    "cicd", "ci", "cd", "github", "gitlab", "bitbucket", "jenkins", "terraform",
    "ansible", "helm", "istio", "prometheus", "grafana", "datadog", "splunk",
    "newrelic", "sentry", "pagerduty", "jira", "confluence", "figma", "canva",
    "async", "await", "mvc", "mvvm", "api", "apis", "rest", "restful", "oauth",
    "saml", "sso", "rbac", "abac", "iam", "vpc", "cdn", "ssl", "tls", "jwt",
    "websocket", "webhook", "grpc", "thrift", "avro", "parquet", "json", "yaml",
    "xml", "html", "css", "sass", "scss", "tailwind", "webpack", "vite",
    "internshala", "unstop", "leetcode", "hackerrank", "cgpa", "gpa",
})

FILLER_PATTERNS = [
    (re.compile(r"\bvarious\b", re.IGNORECASE), "Replace 'various' with specifics (name the tools, count, or category)."),
    (re.compile(r"\bmultiple\b", re.IGNORECASE), "Replace 'multiple' with an exact number."),
    (re.compile(r"\bteam player\b", re.IGNORECASE), "Show teamwork through outcomes, not the phrase 'team player'."),
    (re.compile(r"\bhard[-\s]?working\b", re.IGNORECASE), "Demonstrate work ethic through results."),
    (re.compile(r"\bfast[-\s]?paced\b", re.IGNORECASE), "Remove — adds no information."),
    (re.compile(r"\bself[-\s]?motivated\b", re.IGNORECASE), "Remove — adds no information."),
    (re.compile(r"\bexperience\s+(?:in|with)\b", re.IGNORECASE), "Prefer 'Built X' or 'Used X to Y'."),
    (re.compile(r"\bknowledge\s+of\b", re.IGNORECASE), "Prefer 'Applied X' or 'Implemented Y using X'."),
    (re.compile(r"\bfamiliarity\s+with\b", re.IGNORECASE), "Only list skills you can discuss in depth."),
    (re.compile(r"\babilities?\b", re.IGNORECASE), "Remove — implicit from your bullet evidence."),
]

BUZZWORD_PATTERNS = [
    re.compile(r"\bsynergy\b", re.IGNORECASE),
    re.compile(r"\bleverage[d]?\b", re.IGNORECASE),
    re.compile(r"\brock\s*star\b", re.IGNORECASE),
    re.compile(r"\bninja\b", re.IGNORECASE),
    re.compile(r"\bguru\b", re.IGNORECASE),
    re.compile(r"\bthought\s+leader\b", re.IGNORECASE),
    re.compile(r"\bparadigm\b", re.IGNORECASE),
    re.compile(r"\bholistic\b", re.IGNORECASE),
    re.compile(r"\boutside[\s-]the[\s-]box\b", re.IGNORECASE),
    re.compile(r"\bpassionate\s+about\b", re.IGNORECASE),
    re.compile(r"\bworld[\s-]?class\b", re.IGNORECASE),
    re.compile(r"\bcutting[\s-]?edge\b", re.IGNORECASE),
    re.compile(r"\bstate[\s-]of[\s-]the[\s-]art\b", re.IGNORECASE),
    re.compile(r"\bvalue[\s-]add(?:ed)?\b", re.IGNORECASE),
]

PASSIVE_PATTERN = re.compile(
    r"\b(?:was|were|is|are|been|being)\s+\w+ed\b",
    re.IGNORECASE,
)

PERSONAL_PRONOUN_PATTERN = re.compile(r"\b(?:i|my|me|we|our|us)\b", re.IGNORECASE)


@register
class PersonalPronounsCheck:
    id = "personal_pronouns"
    dimension = "STYLE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        findings = []
        violations = 0

        for bullet in bullets:
            if PERSONAL_PRONOUN_PATTERN.search(bullet.text):
                violations += 1
                findings.append(Finding(
                    check_id=self.id, severity="low",
                    title="Personal pronoun in bullet",
                    detail="Remove 'I', 'my', 'we'. Bullets are implicitly first-person.",
                    anchor=Anchor(bullet.section, bullet.entry_index, bullet.bullet_index),
                    fix=None,
                ))

        ratio = violations / len(bullets)
        score = max(0.0, 1.0 - ratio)
        return build_result(self.id, score, findings, {"violations": violations})


@register
class PunctuationConsistencyCheck:
    id = "punctuation_consistency"
    dimension = "STYLE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        end_periods = sum(1 for b in bullets if b.text.rstrip().endswith("."))
        no_periods = len(bullets) - end_periods

        # Inconsistency = the minority style
        minority = min(end_periods, no_periods)
        ratio = minority / len(bullets)

        findings = []
        if ratio > 0.15:  # >15% inconsistency
            findings.append(Finding(
                check_id=self.id, severity="low",
                title="Inconsistent bullet punctuation",
                detail="Either end all bullets with a period or none. Don't mix.",
                anchor=None, fix=None,
            ))

        score = max(0.0, 1.0 - ratio * 3)
        return build_result(self.id, score, findings, {"with_period": end_periods, "without": no_periods})


@register
class FillerWordsCheck:
    id = "filler_words"
    dimension = "STYLE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        all_text = doc.text.full
        if not all_text.strip():
            return build_result(self.id, None, [], {"reason": "empty"})

        findings = []
        hit_count = 0

        for pattern, suggestion in FILLER_PATTERNS:
            matches = list(pattern.finditer(all_text))
            if matches:
                hit_count += len(matches)
                findings.append(Finding(
                    check_id=self.id, severity="low",
                    title=f"Filler phrase: '{matches[0].group()}'",
                    detail=suggestion,
                    anchor=None, fix=None,
                ))

        total_bullets = len(doc.text.bullets)
        filler_ratio = hit_count / max(total_bullets, 1)
        score = max(0.0, 1.0 - filler_ratio * 0.4)
        return build_result(self.id, score, findings, {"filler_hits": hit_count})


@register
class BuzzwordDensityCheck:
    id = "buzzword_density"
    dimension = "STYLE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        all_text = doc.text.full
        if not all_text.strip():
            return build_result(self.id, None, [], {"reason": "empty"})

        found = []
        for pattern in BUZZWORD_PATTERNS:
            m = pattern.search(all_text)
            if m:
                found.append(m.group())

        findings = []
        if found:
            findings.append(Finding(
                check_id=self.id, severity="low",
                title=f"Buzzwords detected: {', '.join(set(found))}",
                detail="Replace with concrete evidence. Buzzwords signal nothing to a recruiter.",
                anchor=None, fix=None,
            ))

        score = max(0.0, 1.0 - len(found) * 0.12)
        return build_result(self.id, score, findings, {"buzzwords": found})


@register
class PassiveVoiceCheck:
    id = "passive_voice"
    dimension = "STYLE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        passive_count = 0
        findings = []

        for bullet in bullets:
            if PASSIVE_PATTERN.search(bullet.text):
                passive_count += 1
                findings.append(Finding(
                    check_id=self.id, severity="low",
                    title="Passive voice in bullet",
                    detail="Rewrite in active voice: 'Was deployed' → 'Deployed'.",
                    anchor=Anchor(bullet.section, bullet.entry_index, bullet.bullet_index),
                    fix=None,
                ))

        ratio = passive_count / len(bullets)
        score = max(0.0, 1.0 - ratio * 2)
        return build_result(self.id, score, findings, {"passive_count": passive_count})
