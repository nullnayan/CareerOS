"""
services/domain_classifier.py
==============================
Domain Classification & Anti-Fabrication Guardrail for Resume Tailoring.

Prevents domain shifting (e.g. turning a C++ compiler into a "UI component"
or a CLI tool into a "machine learning model") during resume tailoring.

Key functions:
  1. classify_text_domains(text, tech_stack) -> set of domain keys
  2. is_keyword_compatible_with_domain(keyword, project_domains) -> bool
  3. validate_bullet_domain_integrity(original_bullet, rewritten_bullet, tech_stack) -> (is_valid, reason)
"""

import re
import logging
from typing import Set, Tuple, List, Optional

logger = logging.getLogger(__name__)

# Domain definitions and their indicative signature keywords
DOMAIN_SIGNATURES = {
    "frontend_ui": {
        "name": "Frontend / UI/UX Design",
        "keywords": {
            "ui", "ux", "frontend", "front-end", "interface", "user interface",
            "css", "html", "react", "react.js", "vue", "angular", "tailwind",
            "component", "ui component", "widget", "wireframe", "wireframes",
            "prototype", "prototypes", "prototyping", "figma", "sketch", "adobe xd",
            "design system", "responsive design", "gui", "web design", "user experience",
            "user research", "mockup", "mockups"
        }
    },
    "compiler_systems": {
        "name": "Compiler / Systems Programming",
        "keywords": {
            "compiler", "mini-compiler", "lexer", "parser", "lexical", "syntax",
            "ast", "abstract syntax tree", "bytecode", "llvm", "assembly", "c++",
            "operating system", "kernel", "memory management", "xv6", "cli",
            "systems programming", "garbage collection", "interpreter", "linker"
        }
    },
    "backend_api": {
        "name": "Backend / API Engineering",
        "keywords": {
            "backend", "back-end", "api", "apis", "rest", "restful", "rest api",
            "graphql", "grpc", "endpoint", "endpoints", "microservice", "microservices",
            "server", "express", "express.js", "django", "flask", "spring", "spring boot",
            "fastapi", "node.js", "database", "sql", "postgres", "postgresql",
            "mongodb", "redis", "orm", "crud"
        }
    },
    "ai_ml": {
        "name": "AI / Machine Learning",
        "keywords": {
            "ai", "ml", "machine learning", "deep learning", "nlp", "llm", "llms",
            "rag", "tensorflow", "pytorch", "scikit-learn", "model", "models",
            "neural network", "transformer", "bert", "gpt", "training", "inference",
            "vector database", "fine-tuning", "prompt engineering"
        }
    },
    "mobile": {
        "name": "Mobile Development",
        "keywords": {
            "mobile", "ios", "android", "react native", "flutter", "swift",
            "kotlin", "apk", "app store", "play store", "mobile app"
        }
    },
    "devops_cloud": {
        "name": "DevOps / Cloud Infrastructure",
        "keywords": {
            "devops", "cloud", "aws", "gcp", "azure", "docker", "kubernetes",
            "k8s", "ci/cd", "cicd", "pipeline", "terraform", "ansible",
            "serverless", "cloud architecture", "containerization"
        }
    },
    "security": {
        "name": "Security / Cryptography",
        "keywords": {
            "security", "cybersecurity", "vulnerability", "auth", "authentication",
            "authorization", "jwt", "oauth", "encryption", "scanner", "owasp",
            "penetration testing", "firewall", "cryptography"
        }
    },
    "data_engineering": {
        "name": "Data Engineering / Analytics",
        "keywords": {
            "data engineering", "etl", "spark", "hadoop", "kafka", "data pipeline",
            "data warehouse", "snowflake", "pandas", "numpy", "data analytics"
        }
    }
}


def classify_text_domains(text: str, tech_stack: Optional[List[str]] = None) -> Set[str]:
    """
    Classifies a text string (bullet or project description) into domain categories based on signature keywords.
    """
    combined = (text or "").lower()
    if tech_stack:
        combined += " " + " ".join(str(t).lower() for t in tech_stack)

    found_domains = set()
    for domain_key, domain_info in DOMAIN_SIGNATURES.items():
        for kw in domain_info["keywords"]:
            if len(kw) <= 3:
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, combined):
                    found_domains.add(domain_key)
                    break
            else:
                if kw in combined:
                    found_domains.add(domain_key)
                    break

    return found_domains


def get_keyword_domain(keyword: str) -> Optional[str]:
    """
    Identifies if a specific keyword belongs strongly to a single domain.
    Returns domain_key if strongly domain-bound, else None (domain-neutral).
    """
    kw_lower = keyword.lower().strip()
    for domain_key, domain_info in DOMAIN_SIGNATURES.items():
        if kw_lower in domain_info["keywords"]:
            return domain_key
        # Check phrase matches
        for d_kw in domain_info["keywords"]:
            if len(d_kw) > 3 and (d_kw in kw_lower or kw_lower in d_kw):
                return domain_key
    return None


def is_keyword_compatible_with_domain(keyword: str, project_domains: Set[str]) -> bool:
    """
    Checks if a target JD keyword is compatible with the project's actual domains.
    Returns True if compatible or domain-neutral, False if domain shift.
    """
    kw_domain = get_keyword_domain(keyword)
    if not kw_domain:
        return True  # Domain neutral (e.g., "optimization", "performance", "scalability")

    # If the project has NO declared domains (generic text), allow neutral rephrasing
    if not project_domains:
        return True

    # Otherwise, the keyword's domain MUST overlap with project's actual domains
    return kw_domain in project_domains


def validate_bullet_domain_integrity(
    original_bullet: str,
    rewritten_bullet: str,
    tech_stack: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """
    Post-generation validation guardrail.

    Compares domain signatures of original vs rewritten bullet.
    If rewritten bullet introduces a strong domain keyword from a domain completely
    absent in original_bullet + tech_stack, REJECTS the rewrite.

    Returns:
        (is_valid: bool, reason: str)
    """
    orig_domains = classify_text_domains(original_bullet, tech_stack)
    rewritten_domains = classify_text_domains(rewritten_bullet)

    # Check for domain shifts: rewritten introduces a NEW domain absent in original
    new_domains = rewritten_domains - orig_domains

    if not new_domains:
        return True, "Domain integrity verified: no domain shift."

    # For each newly introduced domain, check if it introduced strong domain-specific keywords
    rewritten_lower = rewritten_bullet.lower()
    orig_lower = original_bullet.lower()

    for new_d in new_domains:
        domain_name = DOMAIN_SIGNATURES[new_d]["name"]
        domain_kws = DOMAIN_SIGNATURES[new_d]["keywords"]

        introduced_kws = []
        for kw in domain_kws:
            # Check if this keyword is in rewritten but not in original
            pattern = rf"\b{re.escape(kw)}\b" if len(kw) <= 3 else re.escape(kw)
            if re.search(pattern, rewritten_lower) and not re.search(pattern, orig_lower):
                introduced_kws.append(kw)

        if introduced_kws:
            reason = (
                f"REJECTED domain fabrication: Rewritten bullet introduced '{introduced_kws[0]}' "
                f"({domain_name}) which has zero basis in the original project "
                f"(declared domains: {list(orig_domains) or ['general']})."
            )
            logger.warning(f"[DomainValidator] {reason}")
            return False, reason

    return True, "Domain integrity verified."
