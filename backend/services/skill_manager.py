"""
services/skill_manager.py
==========================
Deterministic skill classification, capping, ranking, and evidence gating
for the resume tailoring pipeline.
"""

import re
import logging
from typing import List, Tuple, Dict, Optional

logger = logging.getLogger(__name__)

# Cap Configuration
SKILLS_HARD_CAP = 15
SKILLS_SOFT_CAP = 7
SKILLS_TOTAL_CAP = 20

# Soft skill inference patterns (regex_pattern, implied_soft_skill)
_SOFT_INFERENCE_PATTERNS = [
    (r"\b(led|leading|managed|guided|mentored|headed|directed)\b.*\b(team|group|members?|developers?|engineers?)\b", "Leadership"),
    (r"\b(owned|owner|ownership)\b", "Ownership"),
    (r"\bspearheaded\b", "Initiative"),
    (r"\bcoordinated\b.*\b(team|cross[-\s]functional|members?)\b", "Collaboration"),
    (r"\b(presented?|demo(ed|nstrated)?|pitched)\b", "Communication"),
    (r"\b(documented|wrote|authored|drafted)\b.*\b(report|doc|documentation|spec|proposal|README)\b", "Written Communication"),
    (r"\b(collaborated|partnered|worked closely|worked with)\b", "Collaboration"),
    (r"\b(solved|resolved|debugged|diagnosed|troubleshot|fixed|identified)\b.*\b(issue|bug|problem|bottleneck|error)\b", "Problem Solving"),
    (r"\b(optimized|improved|reduced|increased|enhanced)\b", "Analytical Thinking"),
    (r"\b(iterated|reworked|refactored|adapted|pivoted|updated)\b", "Adaptability"),
    (r"\b(learned|picked up|self[-\s]taught|explored)\b", "Self-Directed Learning"),
    (r"\b(delivered|shipped|deployed|launched|released)\b.*\b(on time|within|deadline|sprint|milestone)\b", "Time Management"),
    (r"\b(prioritized|managed competing|juggled)\b", "Time Management"),
    (r"\b(tested|validated|verified|ensured|reviewed)\b.*\b(accuracy|quality|correctness|consistency)\b", "Attention to Detail"),
    (r"\b(unit test|integration test|wrote tests?|testing coverage)\b", "Attention to Detail"),
    (r"\b(designed|architected|built|created|developed|implemented)\b.*\b(from scratch|novel|new|innovative|custom)\b", "Innovation"),
    (r"\b(worked with|collaborated with|communicated with)\b.*\b(stakeholder|client|product|manager|customer|user)\b", "Stakeholder Management"),
    (r"\b(gathered|elicited|collected)\b.*\b(requirement|feedback|input)\b", "Stakeholder Management"),
]

# ─── STRICT Soft Skills (authoritative behavioral-only list) ─────────────────
# Rule: ONLY genuine personality traits, behaviors, or ways of working with
# others belong here. Technical terms, domains, and acronyms are NEVER here.
#
# Categories (per user spec):
#   Communication, Teamwork, Leadership, Adaptability, Creativity,
#   Problem-solving, Time Management, Ownership, Attention to Detail,
#   Emotional traits (empathy, curiosity, growth mindset, etc.)
_STRICT_SOFT_SKILLS: set = {
    # ── Communication ────────────────────────────────────────────────────────
    "communication", "verbal communication", "written communication",
    "presentation", "public speaking", "storytelling", "active listening",
    "negotiation", "interpersonal", "interpersonal skills",
    # ── Teamwork / Collaboration ─────────────────────────────────────────────
    "teamwork", "team player", "collaboration", "cross-functional collaboration",
    "stakeholder management", "conflict resolution", "relationship building",
    # ── Leadership / Ownership ───────────────────────────────────────────────
    "leadership", "mentoring", "mentorship", "coaching", "people management",
    "initiative", "ownership", "accountability", "self-motivation",
    "decision making", "decision-making", "delegation",
    # ── Adaptability / Growth ────────────────────────────────────────────────
    "adaptability", "flexibility", "resilience", "openness to feedback",
    "learning agility", "self-directed learning", "growth mindset",
    "continuous learning", "curiosity", "enthusiasm",
    # ── Creativity / Innovation ──────────────────────────────────────────────
    "creativity", "creative thinking", "innovation", "ideation",
    "design thinking", "out-of-the-box thinking",
    # ── Problem Solving / Critical Thinking ─────────────────────────────────
    "problem solving", "problem-solving", "critical thinking",
    "analytical thinking", "root cause analysis", "debugging mindset",
    "logical reasoning",
    # ── Time Management / Organization ──────────────────────────────────────
    "time management", "prioritization", "multitasking", "organization",
    "organizational skills", "work ethic", "self-management", "self-motivated",
    "deadline management",
    # ── Attention to Detail / Accuracy ──────────────────────────────────────
    "attention to detail", "accuracy", "thoroughness", "quality focus",
    # ── Emotional / Interpersonal traits ────────────────────────────────────
    "empathy", "emotional intelligence", "patience", "cultural awareness",
    "professionalism", "integrity", "positive attitude",
}

# ─── Technical Domains (always HARD skills) ──────────────────────────────────
# Rule (strict): Any single letter, acronym, proper noun, or term naming a
# technology, language, domain, or technical field is ALWAYS a hard skill.
# These entries exist to guard single-letter / short-acronym languages and
# technical fields that might otherwise escape the HARD_SKILLS wordlist.
_TECHNICAL_DOMAINS: set = {
    # Single-letter / short programming languages
    "c", "r", "go", "rust", "v",
    # Technical acronyms / abbreviations
    "ai", "ml", "nlp", "cv", "dl", "llm", "rag",
    "dsa", "os", "vlsi", "iot", "hpc",
    "dbms", "oop", "api", "sdk", "ide",
    "tdd", "bdd", "cicd", "ci/cd",
    "sre", "swe", "qa", "ui", "ux",
    # Technical fields / domains
    "artificial intelligence", "machine learning", "natural language processing",
    "computer vision", "deep learning", "large language models",
    "cybersecurity", "information security", "infosec", "appsec",
    "networking", "network security", "network programming",
    "cloud computing", "cloud", "edge computing",
    "devops", "mlops", "devsecops", "gitops",
    "data science", "data engineering", "data analysis", "data analytics",
    "big data", "data warehousing",
    "embedded systems", "internet of things",
    "robotics", "automation", "rpa",
    "blockchain", "web3", "smart contracts",
    "quantum computing",
    "distributed systems", "parallel computing",
    "operating systems", "compiler design", "computer architecture",
    "computer graphics", "game development",
    "web development", "backend development", "frontend development",
    "full stack development", "mobile development", "android development",
    "ios development", "cross-platform development",
    # Technical methodologies (not behavioral)
    "agile", "scrum", "kanban", "waterfall", "lean",
    "microservices", "serverless", "event-driven", "soa",
    "rest", "graphql", "grpc", "websocket", "soap",
    "oop", "functional programming", "design patterns", "solid principles",
    "algorithms", "data structures", "dynamic programming",
    "graph theory", "complexity analysis",
    # Named certs / standards that are technical
    "owasp", "iso", "gdpr", "hipaa",
}

_CAPITALIZE_MAP = {
    "python": "Python", "java": "Java", "javascript": "JavaScript",
    "typescript": "TypeScript", "c++": "C++", "c#": "C#", "golang": "Go",
    "html": "HTML", "html5": "HTML5", "css": "CSS", "css3": "CSS3",
    "sql": "SQL", "nosql": "NoSQL", "graphql": "GraphQL",
    "aws": "AWS", "gcp": "GCP", "azure": "Azure",
    "cicd": "CI/CD", "ci/cd": "CI/CD",
    "api": "API", "apis": "APIs", "rest": "REST API", "rest api": "REST API",
    "grpc": "gRPC", "jwt": "JWT", "oauth": "OAuth", "oauth2": "OAuth2",
    "nlp": "NLP", "ai": "AI", "ml": "Machine Learning",
    "next.js": "Next.js", "nextjs": "Next.js",
    "react": "React", "reactjs": "React.js", "react.js": "React.js",
    "nodejs": "Node.js", "node.js": "Node.js",
    "express": "Express.js", "expressjs": "Express.js", "express.js": "Express.js",
    "mongodb": "MongoDB", "postgres": "PostgreSQL", "postgresql": "PostgreSQL",
    "redis": "Redis", "mysql": "MySQL", "sqlite": "SQLite",
    "git": "Git", "github": "GitHub", "gitlab": "GitLab",
    "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "owasp": "OWASP", "postman": "Postman",
    "scrum": "Scrum", "agile": "Agile", "kanban": "Kanban",
    "pandas": "Pandas", "numpy": "NumPy", "tensorflow": "TensorFlow",
    "pytorch": "PyTorch", "sklearn": "Scikit-learn",
    "flask": "Flask", "django": "Django", "fastapi": "FastAPI",
    "spring": "Spring Boot", "spring boot": "Spring Boot",
    "vue": "Vue.js", "angular": "Angular", "svelte": "Svelte",
    "langchain": "LangChain", "rag": "RAG", "llm": "LLM",
    "linux": "Linux", "machine learning": "Machine Learning",
    "deep learning": "Deep Learning", "natural language processing": "NLP",
    "data structures": "Data Structures", "algorithms": "Algorithms",
    "websocket": "WebSocket", "microservices": "Microservices",
    "html/css": "HTML/CSS", "git/github": "Git/GitHub",
    "dbms": "DBMS", "os": "OS", "oop": "OOP",
    "c": "C", "r": "R", "go": "Go",
}


def _canonicalize(skill: str) -> str:
    low = skill.lower().strip()
    if low in _CAPITALIZE_MAP:
        return _CAPITALIZE_MAP[low]
    words = skill.strip().split()
    return " ".join(w if w.isupper() and len(w) <= 5 else w.capitalize() for w in words)


def get_all_bullets(resume_json: dict) -> List[str]:
    """Extract all bullet strings from experience + projects."""
    bullets = []
    for item in (resume_json.get("experience") or []):
        if isinstance(item, dict):
            for b in (item.get("bullet_points") or item.get("bullets") or []):
                if b and isinstance(b, str):
                    bullets.append(b)
    for item in (resume_json.get("projects") or []):
        if isinstance(item, dict):
            for b in (item.get("bullets") or item.get("bullet_points") or []):
                if b and isinstance(b, str):
                    bullets.append(b)
    return bullets


def has_evidence(skill: str, bullets: List[str], certifications: Optional[List[str]] = None) -> bool:
    """Guardrail: True if skill appears in at least one existing bullet OR certification."""
    skill_lower = skill.lower().strip()

    # Check certifications (Fix 6)
    if certifications:
        cert_text = " ".join([c if isinstance(c, str) else str(c) for c in certifications]).lower()
        if skill_lower in cert_text or (len(skill_lower) <= 3 and re.search(rf"\b{re.escape(skill_lower)}\b", cert_text)):
            return True

    variations = {skill_lower}
    if "." in skill_lower:
        variations.add(skill_lower.split(".")[0])
    if "/" in skill_lower:
        for part in skill_lower.split("/"):
            variations.add(part.strip())
    combined_text = " ".join(bullets).lower()
    for v in variations:
        if not v:
            continue
        if len(v) <= 2:
            if re.search(rf"\b{re.escape(v)}\b", combined_text):
                return True
        else:
            if v in combined_text:
                return True
    return False


def relevance_score(skill: str, jd_text: str, bullets: List[str]) -> int:
    """Score 0-100: how relevant is this skill to this specific JD?"""
    skill_lower = skill.lower().strip()
    jd_lower = jd_text.lower()
    score = 0
    try:
        if re.sub(r"[\s./+#-]", "", skill_lower).isalnum():
            pattern = rf"\b{re.escape(skill_lower)}\b"
        else:
            pattern = re.escape(skill_lower)
        jd_matches = len(re.findall(pattern, jd_lower))
    except Exception:
        jd_matches = 1 if skill_lower in jd_lower else 0
    if jd_matches >= 1:
        score += 60
    if jd_matches >= 3:
        score += 20
    if has_evidence(skill, bullets):
        score += 20
    return score


def infer_soft_from_bullets(bullets: List[str]) -> List[Tuple[str, str]]:
    """Infer implied soft skills from bullet linguistic patterns."""
    found: Dict[str, str] = {}
    for bullet in bullets:
        for pattern, skill_name in _SOFT_INFERENCE_PATTERNS:
            if skill_name not in found:
                try:
                    if re.search(pattern, bullet, re.IGNORECASE):
                        found[skill_name] = bullet
                except Exception:
                    pass
    return list(found.items())


def _classify_skill(skill: str) -> str:
    """
    STRICT RULES (in priority order):
      1. Single letters, acronyms, or proper nouns naming a technology/
         language/field (e.g. "C", "AI", "ML", "OS", "DSA") → ALWAYS hard.
      2. Any term describing a personality trait, behavior, or way of
         working with people → ALWAYS soft.
      3. If genuinely unsure → default HARD and flag for review (misclassifying
         a technical term as soft is a worse error for resume credibility).
    """
    sl = skill.lower().strip()

    # ── Rule 1a: Technical domain / acronym guard ───────────────────────────
    # Catches: single-letter languages (C, R, Go), short acronyms (AI, ML,
    # NLP, DSA, OS, VLSI, IoT), and named technical fields. ALWAYS hard.
    if sl in _TECHNICAL_DOMAINS:
        return "hard"

    # ── Rule 1b: Master hard-skill wordlist ────────────────────────────────
    # Covers all known languages, frameworks, tools, databases, platforms,
    # protocols, and cloud services in the ATS wordlists.
    try:
        from services.ats_wordlists import HARD_SKILLS as _HS
        if sl in _HS:
            return "hard"
    except Exception:
        pass

    # ── Rule 2: Strict behavioral-only soft match (exact, no substrings) ───
    # Perfect case-insensitive match only. Substring matching is intentionally
    # disabled — "ai" is a substring of "organizational" which would cause
    # mis-classification. Only genuine personality traits / behaviors qualify.
    if sl in _STRICT_SOFT_SKILLS:
        return "soft"

    # ── Rule 3: Default → HARD (flag unknown terms for manual review) ───────
    # Misclassifying a technical term as soft damages resume credibility more
    # than the reverse. Unknown terms are conservatively treated as hard.
    logger.debug(f"[_classify_skill] Unknown term '{skill}' → defaulting to hard_skill (manual review recommended)")
    return "hard"



def _flatten_any_skills(skills_input) -> List[str]:
    """Extract flat strings from any skills JSON structure (dict, list, nested dicts)."""
    flat = []
    if not skills_input:
        return flat
    if isinstance(skills_input, dict):
        if "all" in skills_input and isinstance(skills_input["all"], list):
            for s in skills_input["all"]:
                if isinstance(s, str) and s.strip():
                    flat.append(s.strip())
        for k, v in skills_input.items():
            if k == "all":
                continue
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and item.strip():
                        flat.append(item.strip())
                    elif isinstance(item, dict):
                        n = item.get("name") or item.get("skill") or ""
                        if n: flat.append(str(n).strip())
            elif isinstance(v, str) and v.strip():
                flat.append(v.strip())
            elif isinstance(v, dict):
                for sub_v in v.values():
                    if isinstance(sub_v, list):
                        flat.extend([str(x).strip() for x in sub_v if x])
    elif isinstance(skills_input, list):
        for s in skills_input:
            if isinstance(s, str) and s.strip():
                flat.append(s.strip())
            elif isinstance(s, dict):
                n = s.get("name") or s.get("skill") or ""
                if n: flat.append(str(n).strip())
    elif isinstance(skills_input, str) and skills_input.strip():
        flat.extend([x.strip() for x in skills_input.split(",") if x.strip()])
    return flat


def classify_resume_skills(resume_json: dict) -> Tuple[List[str], List[str], List[Tuple[str, str]]]:
    """
    Classify existing resume skills into hard vs soft using the hard-first
    rule: any named technology/tool/domain is hard regardless of how abstract
    it sounds. Only genuine behavioral terms are classified as soft.
    """
    raw_skills = _flatten_any_skills(resume_json.get("skills", []))

    # Expand "Category: skill1, skill2" or comma-separated lists
    normalized = []
    for s in raw_skills:
        s_str = str(s).strip()
        if not s_str:
            continue
        if ":" in s_str and len(s_str.split(":", 1)[0]) < 40:
            parts = s_str.split(":", 1)
            sub_skills = [x.strip() for x in parts[1].split(",") if x.strip()]
            normalized.extend(sub_skills)
        elif "," in s_str:
            sub_skills = [x.strip() for x in s_str.split(",") if x.strip()]
            normalized.extend(sub_skills)
        else:
            normalized.append(s_str)

    existing_hard = []
    existing_soft = []
    for skill in normalized:
        if not skill:
            continue
        if _classify_skill(skill) == "soft":
            existing_soft.append(_canonicalize(skill))
        else:
            existing_hard.append(_canonicalize(skill))

    bullets = get_all_bullets(resume_json)
    inferred_soft = infer_soft_from_bullets(bullets)
    return existing_hard, existing_soft, inferred_soft


HARD_SKILL_CATEGORY_MAP = [
    # 1. Languages
    ("Languages", {
        "python", "java", "javascript", "typescript", "c++", "c#", "c", "go", "golang", "rust",
        "kotlin", "swift", "php", "ruby", "html", "css", "sql", "r", "bash", "shell", "v", "assembly", "dart", "scala", "perl", "matlab"
    }),
    # 2. Web Development
    ("Web Development", {
        "react", "react.js", "reactjs", "next.js", "nextjs", "nuxt.js", "vue", "vue.js", "vuejs", "angular", "angularjs", "svelte", "sveltekit",
        "tailwind", "tailwind css", "bootstrap", "html5", "css3", "sass", "scss", "redux", "mui", "material ui", "webpack", "vite",
        "node.js", "nodejs", "express", "express.js", "fastapi", "flask", "django", "spring", "spring boot", "spring mvc",
        "graphql", "rest", "rest api", "rest apis", "microservices", "grpc", "jwt", "hibernate", "hibernate orm", "j2ee", "jsp",
        "rails", "ruby on rails", "laravel", "oauth", "jwt authentication", "websockets"
    }),
    # 3. Mobile Development
    ("Mobile Development", {
        "android", "ios", "react native", "flutter", "xcode", "android studio", "swiftui", "jetpack compose", "mobile app development", "app store", "google play"
    }),
    # 4. Databases & Tools
    ("Databases & Tools", {
        "postgresql", "postgres", "mysql", "mongodb", "redis", "sqlite", "oracle", "elasticsearch", "dynamodb", "cassandra", "dbms",
        "nosql", "sql server", "mssql", "neo4j", "supabase", "git", "github", "gitlab", "bitbucket", "postman", "jira", "confluence",
        "vs code", "vscode", "intellij", "intellij idea", "notion", "excel", "microsoft excel", "slack", "linux", "ubuntu", "unix", "npm", "yarn", "pnpm"
    }),
    # 5. Cloud & DevOps
    ("Cloud & DevOps", {
        "aws", "gcp", "azure", "docker", "kubernetes", "k8s", "jenkins", "ci/cd", "cicd", "terraform", "ansible",
        "github actions", "gitlab ci", "nginx", "apache", "firebase", "cloudflare", "digitalocean", "heroku", "vercel", "netlify", "docker-compose",
        "ec2", "aws ec2", "s3", "aws s3", "lambda", "aws lambda"
    }),
    # 6. Data Science & ML
    ("Data Science & ML", {
        "pandas", "numpy", "tensorflow", "pytorch", "scikit-learn", "sklearn", "keras", "matplotlib", "seaborn",
        "data science", "data analysis", "machine learning", "deep learning", "nlp", "power bi", "tableau", "jupyter", "rag", "llm", "llms", "openai",
        "hugging face", "langchain", "ai", "opencv", "computer vision"
    }),
    # 7. Design & UX
    ("Design & UX", {
        "figma", "adobe xd", "photoshop", "illustrator", "adobe illustrator", "sketch", "invision",
        "ui/ux design", "ui & ux design", "ui/ux", "ux/ui", "ux/ui design", "ui design", "ux design",
        "user interface design", "user experience design", "wireframing", "prototyping", "canva", "design systems"
    }),
    # 8. Cybersecurity
    ("Cybersecurity", {
        "cybersecurity", "network security", "penetration testing", "ethical hacking", "owasp", "cryptography", "iam", "siem", "firewall", "vulnerability assessment"
    }),
    # 9. Core Concepts
    ("Core Concepts", {
        "data structures", "data structures & algorithms", "algorithms", "oop", "system design", "operating systems", "os", "networking",
        "agile", "scrum"
    })
]

CANONICAL_CATEGORY_MAP = {
    'languages': 'Languages',
    'programming_languages': 'Languages',
    'programming languages': 'Languages',
    'coding': 'Languages',
    'web development': 'Web Development',
    'web_development': 'Web Development',
    'web': 'Web Development',
    'frontend': 'Web Development',
    'backend': 'Web Development',
    'frameworks': 'Web Development',
    'libraries': 'Web Development',
    'mobile': 'Mobile Development',
    'mobile development': 'Mobile Development',
    'mobile_development': 'Mobile Development',
    'databases & tools': 'Databases & Tools',
    'databases and tools': 'Databases & Tools',
    'databases': 'Databases & Tools',
    'tools': 'Databases & Tools',
    'cloud & devops': 'Cloud & DevOps',
    'cloud and devops': 'Cloud & DevOps',
    'cloud': 'Cloud & DevOps',
    'devops': 'Cloud & DevOps',
    'data science & ml': 'Data Science & ML',
    'data science and ml': 'Data Science & ML',
    'data science': 'Data Science & ML',
    'ml_ai': 'Data Science & ML',
    'ai/ml': 'Data Science & ML',
    'design & ux': 'Design & UX',
    'design and ux': 'Design & UX',
    'design': 'Design & UX',
    'ui/ux': 'Design & UX',
    'cybersecurity': 'Cybersecurity',
    'security': 'Cybersecurity',
    'core concepts': 'Core Concepts',
    'core_concepts': 'Core Concepts',
    'cs fundamentals': 'Core Concepts',
}

VALID_CATEGORIES = {
    "Languages", "Web Development", "Mobile Development", "Databases & Tools",
    "Cloud & DevOps", "Data Science & ML", "Design & UX", "Cybersecurity", "Core Concepts"
}

def classify_skill_with_ai(skill_name: str) -> Optional[str]:
    """
    AI Fallback classifier: calls llama-3.1-8b-instant to classify an unknown skill.
    Validates response strictly against canonical categories and caches result dynamically.
    Guaranteed not to block or crash on error/timeout — returns None cleanly.
    """
    logger.info(f"AI Fallback triggered for unknown skill: '{skill_name}'")
    try:
        from agents.llm_client import LLMClient
        client = LLMClient("skill_classifier")
        system_prompt = (
            "You are a tech skill classification engine. Classify the given technical skill "
            "into EXACTLY one of these categories: Languages, Web Development, Mobile Development, "
            "Databases & Tools, Cloud & DevOps, Data Science & ML, Design & UX, Cybersecurity, Core Concepts. "
            "Respond ONLY with the exact category name, with no punctuation or extra text."
        )
        user_prompt = f"Skill: {skill_name}"
        res = client.generate(system_prompt, user_prompt).strip()
        
        # Clean trailing punctuation
        res_clean = re.sub(r'[^a-zA-Z\s&]', '', res).strip()
        
        for cat in VALID_CATEGORIES:
            if res_clean.lower() == cat.lower():
                # Cache dynamically in memory for instant future lookups
                for cat_name, cat_set in HARD_SKILL_CATEGORY_MAP:
                    if cat_name == cat:
                        cat_set.add(skill_name.lower().strip())
                        break
                logger.info(f"AI classified '{skill_name}' -> '{cat}' (cached into HARD_SKILL_CATEGORY_MAP)")
                return cat
                
        logger.warning(f"AI returned invalid category '{res}' for skill '{skill_name}'. Falling back to 'Other'.")
        return None
    except Exception as e:
        logger.error(f"AI skill classification failed for '{skill_name}': {e}. Falling through to 'Other'.")
        return None


def consolidate_skill_categories(by_category_dict: dict) -> dict:
    """
    Consolidates any multi-category dictionary into the 4 canonical categories:
    Languages, Web Development, Databases & Tools, Core Concepts, plus Other.
    Re-classifies each individual skill so that skills listed under ambiguous
    headings (like 'Tools & Libraries') get assigned to their true canonical category.
    """
    if not isinstance(by_category_dict, dict):
        return {}

    all_individual_skills = []
    for orig_cat, skills in by_category_dict.items():
        if orig_cat == "all":
            continue
        if isinstance(skills, str):
            skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        elif isinstance(skills, list):
            skill_list = [str(s).strip() for s in skills if s]
        else:
            continue
        for s in skill_list:
            if s and s not in all_individual_skills:
                all_individual_skills.append(s)

    if not all_individual_skills:
        return {}

    return group_skills_into_categories(all_individual_skills)


COMPOUND_SKILL_PHRASES = [
    "data structures and algorithms", "data structures & algorithms",
    "ui & ux design", "ui/ux design", "ux/ui design", "user interface design", "user experience design",
    "machine learning & ai", "machine learning and ai",
    "html5 & css3", "ci/cd", "ci / cd"
]

def protect_compound_phrases(text: str) -> Tuple[str, Dict[str, str]]:
    """Replaces known compound skill phrases with temporary placeholders before splitting."""
    placeholders = {}
    protected_text = text
    for idx, phrase in enumerate(COMPOUND_SKILL_PHRASES):
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        match = pattern.search(protected_text)
        if match:
            exact_original_match = match.group(0)
            key = f"__COMPOUND_SKILL_{idx}__"
            placeholders[key] = exact_original_match
            protected_text = pattern.sub(key, protected_text)
    return protected_text, placeholders

def restore_compound_phrases(skills_list: List[str], placeholders: Dict[str, str]) -> List[str]:
    """Restores compound skill placeholders back to their original compound phrase."""
    restored = []
    for item in skills_list:
        clean_item = item
        for key, orig_phrase in placeholders.items():
            if key.lower() in clean_item.lower():
                clean_item = clean_item.replace(key, orig_phrase)
        restored.append(clean_item)
    return restored


def group_skills_into_categories(
    hard_skills: List[str],
    jd_skills: Optional[List[str]] = None,
    sparsity_threshold: int = 3
) -> Dict[str, List[str]]:
    """
    Groups hard skills into 9 canonical domains with JD-aware sparsity merging.
    - If a resume category has < 3 skills, it merges into 'Core Concepts' UNLESS the JD
      emphasizes that category (jd_skills has >= 3 skills in that category).
    - If no JD context is provided, it uses the flat sparsity threshold (< 3 -> merge).
    """
    groups: Dict[str, List[str]] = {cat: [] for cat, _ in HARD_SKILL_CATEGORY_MAP}
    uncategorized = []

    # Step 1: Classify candidate's resume skills
    for skill in hard_skills:
        sl = skill.lower().strip()
        placed = False
        
        # Exact match
        for cat_name, cat_set in HARD_SKILL_CATEGORY_MAP:
            if sl in cat_set:
                if skill not in groups[cat_name]:
                    groups[cat_name].append(skill)
                placed = True
                break

        # Pattern match
        if not placed:
            for cat_name, cat_set in HARD_SKILL_CATEGORY_MAP:
                if any(kw in sl for kw in cat_set if len(kw) > 3):
                    if skill not in groups[cat_name]:
                        groups[cat_name].append(skill)
                    placed = True
                    break

        # AI Fallback Layer
        if not placed:
            ai_cat = classify_skill_with_ai(skill)
            if ai_cat and ai_cat in groups:
                if skill not in groups[ai_cat]:
                    groups[ai_cat].append(skill)
                placed = True

        # Fallthrough to uncategorized
        if not placed:
            if skill not in uncategorized:
                uncategorized.append(skill)

    # Step 2: Classify JD skills (Full 3-step pipeline: exact -> pattern -> AI fallback)
    jd_counts: Dict[str, int] = {cat: 0 for cat, _ in HARD_SKILL_CATEGORY_MAP}
    if jd_skills:
        for jd_s in jd_skills:
            sl_jd = jd_s.lower().strip()
            placed_jd = False
            for cat_name, cat_set in HARD_SKILL_CATEGORY_MAP:
                if sl_jd in cat_set:
                    jd_counts[cat_name] += 1
                    placed_jd = True
                    break
            if not placed_jd:
                for cat_name, cat_set in HARD_SKILL_CATEGORY_MAP:
                    if any(kw in sl_jd for kw in cat_set if len(kw) > 3):
                        jd_counts[cat_name] += 1
                        placed_jd = True
                        break
            if not placed_jd:
                ai_cat = classify_skill_with_ai(jd_s)
                if ai_cat and ai_cat in jd_counts:
                    jd_counts[ai_cat] += 1

    # Step 3: Apply Smart Sparsity Merging (JD-Aware)
    result: Dict[str, List[str]] = {}
    sparse_merged_to_core: List[str] = []

    for cat_name, _ in HARD_SKILL_CATEGORY_MAP:
        resume_count = len(groups[cat_name])
        jd_count = jd_counts.get(cat_name, 0)
        
        if resume_count > 0:
            # Sparsity condition: resume has < 3 skills AND JD has < 3 skills
            # (If JD count >= 3, override and KEEP as its own category heading!)
            if resume_count < sparsity_threshold and jd_count < sparsity_threshold and cat_name != "Core Concepts":
                logger.info(
                    f"Sparse category '{cat_name}' (resume={resume_count}, JD={jd_count}) -> merged into Core Concepts"
                )
                sparse_merged_to_core.extend(groups[cat_name])
            else:
                result[cat_name] = groups[cat_name]

    if uncategorized:
        sparse_merged_to_core.extend(uncategorized)

    if sparse_merged_to_core:
        if "Core Concepts" not in result:
            result["Core Concepts"] = []
        for s in sparse_merged_to_core:
            if s not in result["Core Concepts"]:
                result["Core Concepts"].append(s)

    return result


def preserve_original_skill_structure(original_skills: dict, hard_list: List[str], existing_soft: List[str]) -> Dict[str, List[str]]:
    """
    Consolidates skills into canonical categories (Languages, Web Development, Databases & Tools, Core Concepts)
    and places new skills into their appropriate category.
    """
    import copy
    
    categories = {}
    if isinstance(original_skills, dict):
        if "byCategory" in original_skills and isinstance(original_skills["byCategory"], dict):
            categories = copy.deepcopy(original_skills["byCategory"])
        else:
            categories = copy.deepcopy({k: v for k, v in original_skills.items() if k != "all"})
            
    if not categories:
        return group_skills_into_categories(hard_list)
        
    consolidated = consolidate_skill_categories(categories)
    
    # Add any missing hard skills into consolidated categories
    for skill in hard_list:
        placed = False
        skill_lower = skill.lower().strip()
        for cat_name, cat_skills in consolidated.items():
            if any(skill_lower == str(s).lower().strip() for s in cat_skills):
                placed = True
                break
        if not placed:
            temp_grouped = group_skills_into_categories([skill])
            for target_cat, target_skills in temp_grouped.items():
                if target_cat not in consolidated:
                    consolidated[target_cat] = []
                for s in target_skills:
                    if s not in consolidated[target_cat]:
                        consolidated[target_cat].append(s)

    return consolidate_skill_categories(consolidated)


def sort_hard_skills_by_category(hard_skills: List[str]) -> List[str]:
    """
    Sort hard skills according to fixed category order:
    Languages -> Frontend -> Backend -> Databases -> Tools/Cloud -> Core Concepts
    """
    groups = group_skills_into_categories(hard_skills)
    ordered = []
    for cat_list in groups.values():
        for s in cat_list:
            if s not in ordered:
                ordered.append(s)
    return ordered


def build_capped_skills_section(
    resume_json: dict,
    jd_required_hard: List[str],
    jd_required_soft: List[str],
    jd_text: str,
    hard_cap: int = SKILLS_HARD_CAP,
    soft_cap: int = SKILLS_SOFT_CAP,
    total_cap: int = SKILLS_TOTAL_CAP,
    original_skills: Optional[dict] = None,
) -> Tuple[Dict[str, List[str]], List[dict], List[str]]:
    """
    Build the final capped, evidence-gated, ranked skills section dict.
    Hard skills are mandatory and ordered by fixed category.
    Soft skills are OPTIONAL and suggested as opt-in choices only if supported by bullet evidence.
    
    Returns: (skills_dict, audit_log, suggested_opt_in_soft_skills)
    """
    audit_log = []
    bullets = get_all_bullets(resume_json)
    certifications = resume_json.get("certifications", []) or []
    existing_hard, existing_soft, inferred_soft = classify_resume_skills(resume_json)
    logger.info(f"[SkillManager] Existing hard={len(existing_hard)}, soft={len(existing_soft)}, inferred soft={len(inferred_soft)}")

    hard_set = {s.lower(): s for s in existing_hard}

    # Add JD hard skills
    for jd_hard_raw in jd_required_hard:
        canonical = _canonicalize(jd_hard_raw)
        sl = canonical.lower()
        if sl not in hard_set:
            hard_set[sl] = canonical
            audit_log.append({
                "action": "ADD", "type": "hard", "skill": canonical,
                "reason": "Required by JD"
            })

    hard_list = list(hard_set.values())

    # Safety Fallback: If hard_list is empty, recover all non-soft skills from original resume JSON
    if not hard_list:
        fallback_skills = _flatten_any_skills(resume_json.get("skills", []))
        soft_lower_set = {x.lower() for x in existing_soft}
        hard_list = [_canonicalize(s) for s in fallback_skills if s and s.lower() not in soft_lower_set]

    # Prune hard skills if exceeding cap
    if len(hard_list) > hard_cap:
        scored = sorted([(s, relevance_score(s, jd_text, bullets)) for s in hard_list], key=lambda x: x[1], reverse=True)
        hard_list = [s for s, _ in scored[:hard_cap]]

    # Sort hard skills according to FIXED category order
    hard_list = sort_hard_skills_by_category(hard_list)

    # ── Soft Skills (Opt-in only, evidence gated) ──
    suggested_soft_set = {}

    # Check evidence for inferred soft skills
    for skill_name, evidence_bullet in inferred_soft:
        sl = skill_name.lower()
        if sl not in suggested_soft_set:
            suggested_soft_set[sl] = skill_name
            audit_log.append({
                "action": "SUGGEST_OPT_IN", "type": "soft", "skill": skill_name,
                "reason": "Supported by bullet evidence (opt-in choice)",
                "evidence": evidence_bullet[:100]
            })

    # Check evidence for JD soft skills
    for jd_soft_raw in jd_required_soft:
        canonical = _canonicalize(jd_soft_raw)
        sl = canonical.lower()
        if sl not in suggested_soft_set and has_evidence(canonical, bullets, certifications):
            suggested_soft_set[sl] = canonical
            audit_log.append({
                "action": "SUGGEST_OPT_IN", "type": "soft", "skill": canonical,
                "reason": "Required by JD & supported by evidence (opt-in choice)"
            })

    suggested_soft_list = list(suggested_soft_set.values())[:soft_cap]

    orig_is_categorized = False
    if original_skills:
        orig_is_categorized = (
            isinstance(original_skills, dict) and 
            ("byCategory" in original_skills or any(isinstance(v, list) for k,v in original_skills.items() if k != "all"))
        )

    if orig_is_categorized:
        result_dict = preserve_original_skill_structure(original_skills, hard_list, existing_soft)
    else:
        result_dict = group_skills_into_categories(hard_list)
        if existing_soft:
            if isinstance(result_dict, dict):
                result_dict["Soft Skills"] = list(dict.fromkeys(existing_soft))
            elif isinstance(result_dict, list):
                result_dict.extend([s for s in existing_soft if s not in result_dict])

    logger.info(f"[SkillManager] Final: hard={len(hard_list)}, suggested soft={len(suggested_soft_list)}")
    return result_dict, audit_log, suggested_soft_list


def extract_jd_skills_deterministic(jd_text: str) -> Tuple[List[str], List[str]]:
    """Scan JD text for all known hard and soft skills using wordlists."""
    try:
        from services.ats_wordlists import HARD_SKILLS as _HARD_SKILLS_SET
        from services.ats_scorer import SOFT_SKILLS as _SOFT_SKILLS_SET
    except Exception:
        return [], []

    jd_lower = jd_text.lower()

    def _is_present(skill: str) -> bool:
        sl = skill.lower().strip()
        try:
            if re.sub(r"[\s./+#-]", "", sl).isalnum():
                pattern = rf"\b{re.escape(sl)}\b"
            else:
                pattern = re.escape(sl)
            return bool(re.search(pattern, jd_lower))
        except Exception:
            return sl in jd_lower

    hard = [_canonicalize(hs) for hs in _HARD_SKILLS_SET if _is_present(hs)]
    soft = [_canonicalize(ss) for ss in _SOFT_SKILLS_SET if _is_present(ss)]
    return hard, soft
