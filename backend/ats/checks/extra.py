"""
Phase 5 — remaining 4 checks:
  - SpellingCheck (pyspellchecker + 300-term tech allowlist)
  - GrammarTenseCheck (reuse detection logic from ats_fixers/grammar.py)
  - SectionOrderCheck (experience > education > skills expected order)
  - ContactInHeaderCheck (contact info should be at top, not buried)

All live in a single file: checks/extra.py
Registered via @register, dimensions assigned from plan.
"""
import re
from typing import Optional, Any

from .base import register, build_result, ALL_SENIORITIES
from ..models import ResumeDoc, CheckResult, Finding, Anchor

# ──────────────────────────────────────────────────────────────────────────────
# Tech allowlist — words pyspellchecker would flag as misspellings
# ──────────────────────────────────────────────────────────────────────────────
TECH_ALLOWLIST: frozenset[str] = frozenset({
    "python", "javascript", "typescript", "golang", "kotlin", "scala", "pytorch",
    "tensorflow", "sklearn", "numpy", "pandas", "fastapi", "nextjs", "graphql",
    "grpc", "protobuf", "kafka", "airflow", "databricks", "kubernetes", "k8s",
    "dockerfile", "redis", "mongodb", "postgresql", "mysql", "sqlite", "dynamodb",
    "elasticsearch", "opensearch", "snowflake", "bigquery", "redshift", "spark",
    "hadoop", "flink", "dbt", "mlflow", "wandb", "langchain", "openai", "llm",
    "rag", "microservices", "devops", "devsecops", "cicd", "github", "gitlab",
    "terraform", "ansible", "helm", "istio", "prometheus", "grafana", "datadog",
    "splunk", "newrelic", "sentry", "pagerduty", "jira", "figma", "mvc", "mvvm",
    "api", "apis", "rest", "restful", "oauth", "saml", "sso", "rbac", "vpc",
    "cdn", "ssl", "tls", "jwt", "websocket", "webhook", "html", "css", "sass",
    "tailwind", "webpack", "vite", "internshala", "unstop", "leetcode", "cgpa",
    "gpa", "async", "await", "backend", "frontend", "fullstack", "devops",
    "rollback", "rollout", "uptime", "downtime", "changelog", "dockerfile",
    "multicloud", "serverless", "elasticsearch", "clickhouse", "timescaledb",
    "supabase", "firebase", "vercel", "netlify", "heroku", "flyio", "railway",
    "pytest", "unittest", "mocha", "jest", "cypress", "playwright", "postman",
    "swagger", "openapi", "yaml", "toml", "makefile", "cli", "sdk", "ide",
    "vscode", "intellij", "xcode", "android", "ios", "flutter", "reactnative",
    "expo", "fastlane", "cocoapods", "gradle", "maven", "npm", "yarn", "pnpm",
    "bun", "deno", "nodejs", "expressjs", "nestjs", "django", "flask", "rails",
    "laravel", "springboot", "dotnet", "blazor", "wpf", "xamarin", "unity",
    "unreal", "threejs", "webgl", "wasm", "webassembly", "llvm", "cuda",
    "opencv", "mediapipe", "langchain", "llamaindex", "huggingface", "gpt",
    "claude", "gemini", "mistral", "ollama", "qdrant", "pinecone", "weaviate",
    "milvus", "chroma", "faiss", "ann", "rag", "lora", "qlora", "peft",
    "rdbms", "nosql", "olap", "oltp", "etl", "elt", "dag", "cron", "orm",
    "otp", "sms", "smtp", "imap", "pop3", "ldap", "rbac", "abac", "iam",
    "ec2", "s3", "rds", "ecs", "eks", "lambda", "sqs", "sns", "cloudwatch",
    "cloudfront", "route53", "gcp", "gke", "gcs", "bigquery", "pubsub",
    "azure", "aks", "cosmos", "devops", "blob", "keyvault",
    # Indian resume context
    "cgpa", "sgpa", "btech", "mtech", "bca", "mca", "bsc", "msc", "mba",
    "iit", "nit", "iiit", "bits", "vit", "srm", "manipal",
})

# Present-tense verbs that should be past-tense in finished roles
PRESENT_VERBS_CHECK: frozenset[str] = frozenset({
    "build", "develop", "design", "create", "manage", "lead", "ensure",
    "maintain", "work", "implement", "write", "run", "deploy", "test",
    "review", "handle", "support", "improve", "monitor", "analyze",
    "collaborate", "integrate", "contribute",
})

# Expected section order: experience before education before skills
EXPECTED_ORDER = ["experience", "education", "skills"]

_pyspell_available = False
try:
    from spellchecker import SpellChecker
    _pyspell_available = True
except ImportError:
    pass


@register
class SpellingCheck:
    id = "spelling"
    dimension = "STYLE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        if not _pyspell_available:
            # Skip gracefully — don't penalise for missing dependency
            return build_result(self.id, None, [], {"reason": "pyspellchecker_not_installed"})

        spell = SpellChecker()
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        findings = []
        total_words = 0
        misspelled_count = 0

        for bullet in bullets:
            words_raw = re.findall(r"[A-Za-z]+", bullet.text)
            # Filter out tech terms and short tokens
            words_to_check = [
                w for w in words_raw
                if len(w) > 3 and w.lower() not in TECH_ALLOWLIST
            ]
            total_words += len(words_to_check)

            if not words_to_check:
                continue

            misspelled = spell.unknown(words_to_check)
            # Further filter: ignore capitalised words (proper nouns / acronyms)
            misspelled = {w for w in misspelled if not w[0].isupper()}

            for word in list(misspelled)[:2]:  # cap per bullet
                misspelled_count += 1
                correction = spell.correction(word) or word
                findings.append(Finding(
                    check_id=self.id,
                    severity="medium",
                    title=f"Possible misspelling: '{word}'",
                    detail=f"Did you mean '{correction}'? Check spelling carefully.",
                    anchor=Anchor(bullet.section, bullet.entry_index, bullet.bullet_index),
                    fix=None,
                ))

        if total_words == 0:
            return build_result(self.id, None, [], {"reason": "no_checkable_words"})

        error_rate = misspelled_count / total_words
        score = max(0.0, 1.0 - error_rate * 10)  # 10% error rate → 0
        return build_result(self.id, score, findings, {
            "misspelled": misspelled_count, "total_words": total_words
        })


@register
class GrammarTenseCheck:
    id = "grammar_tense"
    dimension = "STYLE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        """
        Detects present-tense verbs in completed (non-current) experience bullets.
        Reuses detection logic from ats_fixers/grammar.py without importing it
        (to avoid circular deps and LLM calls in the scoring hot path).
        """
        bullets = doc.text.bullets
        if not bullets:
            return build_result(self.id, None, [], {"reason": "no_bullets"})

        findings = []
        tense_errors = 0
        exp_bullets = [b for b in bullets if b.section == "experience" and not b.entry_is_current]

        if not exp_bullets:
            return build_result(self.id, None, [], {"reason": "no_past_experience_bullets"})

        for bullet in exp_bullets:
            words = bullet.text.strip().split()
            if not words:
                continue
            first = words[0].lower().rstrip(".,;:()")
            if first in PRESENT_VERBS_CHECK:
                tense_errors += 1
                findings.append(Finding(
                    check_id=self.id,
                    severity="low",
                    title=f"Present tense in past role: '{words[0]}'",
                    detail=f"Past roles use past tense. Change '{words[0]}' to its past form.",
                    anchor=Anchor(bullet.section, bullet.entry_index, bullet.bullet_index),
                    fix=None,
                ))

        total = len(exp_bullets)
        error_ratio = tense_errors / total
        score = max(0.0, 1.0 - error_ratio * 2)
        return build_result(self.id, score, findings, {
            "tense_errors": tense_errors, "total_past_bullets": total
        })


@register
class SectionOrderCheck:
    id = "section_order"
    dimension = "STRUCTURE"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        """
        Checks that major sections appear in the expected order:
        Experience → Education → Skills (for experienced candidates).
        Students may place Education first — that's fine.
        """
        # Build the order in which sections appear in full_text
        full = doc.text.full
        positions = {}
        for section in ["experience", "education", "skills", "projects"]:
            text = doc.text.by_section.get(section, "")
            if text:
                idx = full.find(text[:30])  # anchor by first 30 chars
                if idx >= 0:
                    positions[section] = idx

        if len(positions) < 2:
            return build_result(self.id, None, [], {"reason": "insufficient_sections_to_order"})

        findings = []

        # For experienced candidates: experience should precede education
        if rubric.expects_formal_experience:
            exp_pos = positions.get("experience", -1)
            edu_pos = positions.get("education", -1)
            if exp_pos > 0 and edu_pos > 0 and edu_pos < exp_pos:
                findings.append(Finding(
                    check_id=self.id, severity="low",
                    title="Education appears before Experience",
                    detail="For experienced candidates, place Experience before Education.",
                    anchor=None, fix=None,
                ))

        # Skills should not appear before Experience
        exp_pos = positions.get("experience", -1)
        skills_pos = positions.get("skills", -1)
        if exp_pos > 0 and skills_pos > 0 and skills_pos < exp_pos:
            findings.append(Finding(
                check_id=self.id, severity="low",
                title="Skills section appears before Experience",
                detail="Move Skills below Experience and Education for standard ATS readability.",
                anchor=None, fix=None,
            ))

        score = max(0.0, 1.0 - len(findings) * 0.3)
        return build_result(self.id, score, findings, {"order_issues": len(findings)})


@register
class ContactInHeaderCheck:
    id = "contact_in_header"
    dimension = "FORMATTING"
    requires_jd = False
    applies_to = ALL_SENIORITIES

    def run(self, doc: ResumeDoc, jd: Optional[Any], rubric: Any) -> CheckResult:
        """
        Checks that contact info is at the top (in header/footer area) rather than buried.
        Uses layout.header_footer_text if available, otherwise checks if contact text
        appears early in full_text.
        """
        contact = doc.contact
        if not contact.email:
            return build_result(self.id, None, [], {"reason": "no_contact_to_check"})

        findings = []

        # If we have layout data, check if email is in header_footer_text
        if doc.layout.page_count > 0 and doc.layout.header_footer_text:
            header_text = " ".join(doc.layout.header_footer_text).lower()
            email_in_header = contact.email.lower() in header_text if contact.email else False
            if not email_in_header:
                findings.append(Finding(
                    check_id=self.id, severity="medium",
                    title="Contact info may not be in header",
                    detail="Place your name and contact details at the very top of the document.",
                    anchor=None, fix=None,
                ))
            score = 1.0 if email_in_header else 0.5
        else:
            # No layout: check if email appears in first 15% of full_text
            full = doc.text.full
            if not full or not contact.email:
                return build_result(self.id, None, [], {"reason": "no_layout_and_no_text"})

            cutoff = max(50, len(full) // 7)
            top_section = full[:cutoff].lower()
            if contact.email.lower() in top_section:
                score = 1.0
            else:
                score = 0.6
                findings.append(Finding(
                    check_id=self.id, severity="low",
                    title="Contact info not detected at top",
                    detail="Ensure name, email, and phone are on the first few lines.",
                    anchor=None, fix=None,
                ))

        return build_result(self.id, score, findings, {})
