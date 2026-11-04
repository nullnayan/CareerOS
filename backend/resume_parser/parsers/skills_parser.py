"""
Module 7 — Skills Parser
=========================
Phase 3 (third parser).

Extracts skills from the skills section + experience/projects sections.
Categorizes them against a built-in taxonomy.

Output:
{
  "all": ["Python", "React", "PostgreSQL", ...],
  "byCategory": {
    "programming_languages": ["Python", "JavaScript"],
    "frontend": ["React", "Vue.js"],
    "backend": ["FastAPI", "Node.js"],
    "databases": ["PostgreSQL", "MongoDB"],
    "cloud": ["AWS", "GCP"],
    "devops": ["Docker", "Kubernetes"],
    "ml_ai": ["TensorFlow", "scikit-learn"],
    "tools": ["Git", "Jira"],
    "soft_skills": ["Leadership", "Communication"],
    "other": [...]
  },
  "_confidence": "high"
}
"""

import re

# ─── Skill Taxonomy ────────────────────────────────────────────────────────────
# Lower-cased keys map to (canonical_name, category)

SKILL_TAXONOMY: dict[str, tuple[str, str]] = {
    # Programming Languages
    "python": ("Python", "programming_languages"),
    "javascript": ("JavaScript", "programming_languages"),
    "js": ("JavaScript", "programming_languages"),
    "typescript": ("TypeScript", "programming_languages"),
    "ts": ("TypeScript", "programming_languages"),
    "java": ("Java", "programming_languages"),
    "c++": ("C++", "programming_languages"),
    "c#": ("C#", "programming_languages"),
    "c": ("C", "programming_languages"),
    "go": ("Go", "programming_languages"),
    "golang": ("Go", "programming_languages"),
    "rust": ("Rust", "programming_languages"),
    "ruby": ("Ruby", "programming_languages"),
    "php": ("PHP", "programming_languages"),
    "swift": ("Swift", "programming_languages"),
    "kotlin": ("Kotlin", "programming_languages"),
    "scala": ("Scala", "programming_languages"),
    "r": ("R", "programming_languages"),
    "matlab": ("MATLAB", "programming_languages"),
    "perl": ("Perl", "programming_languages"),
    "shell": ("Shell Scripting", "programming_languages"),
    "bash": ("Bash", "programming_languages"),
    "powershell": ("PowerShell", "programming_languages"),
    "dart": ("Dart", "programming_languages"),

    # Frontend
    "react": ("React", "frontend"),
    "reactjs": ("React", "frontend"),
    "react.js": ("React", "frontend"),
    "vue": ("Vue.js", "frontend"),
    "vue.js": ("Vue.js", "frontend"),
    "vuejs": ("Vue.js", "frontend"),
    "angular": ("Angular", "frontend"),
    "angularjs": ("AngularJS", "frontend"),
    "next.js": ("Next.js", "frontend"),
    "nextjs": ("Next.js", "frontend"),
    "nuxt.js": ("Nuxt.js", "frontend"),
    "svelte": ("Svelte", "frontend"),
    "html": ("HTML", "Languages"),
    "css": ("CSS", "Languages"),
    "sass": ("SASS", "frontend"),
    "scss": ("SCSS", "frontend"),
    "tailwind": ("TailwindCSS", "frontend"),
    "tailwindcss": ("TailwindCSS", "frontend"),
    "bootstrap": ("Bootstrap", "frontend"),
    "material ui": ("Material UI", "frontend"),
    "mui": ("Material UI", "frontend"),
    "redux": ("Redux", "frontend"),
    "webpack": ("Webpack", "frontend"),
    "vite": ("Vite", "frontend"),

    # Backend
    "node.js": ("Node.js", "backend"),
    "nodejs": ("Node.js", "backend"),
    "express": ("Express.js", "backend"),
    "express.js": ("Express.js", "backend"),
    "fastapi": ("FastAPI", "backend"),
    "django": ("Django", "backend"),
    "flask": ("Flask", "backend"),
    "spring": ("Spring Boot", "backend"),
    "spring boot": ("Spring Boot", "backend"),
    "rails": ("Ruby on Rails", "Web Development"),
    "ruby on rails": ("Ruby on Rails", "Web Development"),
    "jsp": ("JSP", "Web Development"),
    "j2ee": ("J2EE", "Web Development"),
    "hibernate": ("Hibernate ORM", "Web Development"),
    "hibernate orm": ("Hibernate ORM", "Web Development"),
    "jwt": ("JWT Authentication", "Web Development"),
    "jwt authentication": ("JWT Authentication", "Web Development"),
    "graphql": ("GraphQL", "backend"),
    "rest": ("REST APIs", "backend"),
    "restful": ("REST APIs", "backend"),
    "grpc": ("gRPC", "backend"),
    "websockets": ("WebSockets", "backend"),

    # Databases
    "postgresql": ("PostgreSQL", "databases"),
    "postgres": ("PostgreSQL", "databases"),
    "mysql": ("MySQL", "databases"),
    "mongodb": ("MongoDB", "databases"),
    "sqlite": ("SQLite", "databases"),
    "redis": ("Redis", "databases"),
    "elasticsearch": ("Elasticsearch", "databases"),
    "cassandra": ("Cassandra", "databases"),
    "dynamodb": ("DynamoDB", "databases"),
    "firebase": ("Firebase", "Cloud & DevOps"),
    "sql": ("SQL", "Languages"),
    "nosql": ("NoSQL", "databases"),
    "oracle": ("Oracle DB", "databases"),
    "mssql": ("SQL Server", "databases"),
    "sql server": ("SQL Server", "databases"),
    "neo4j": ("Neo4j", "databases"),
    "supabase": ("Supabase", "databases"),

    # Cloud
    "aws": ("AWS", "cloud"),
    "amazon web services": ("AWS", "cloud"),
    "gcp": ("GCP", "cloud"),
    "google cloud": ("GCP", "cloud"),
    "azure": ("Azure", "cloud"),
    "microsoft azure": ("Azure", "cloud"),
    "heroku": ("Heroku", "cloud"),
    "vercel": ("Vercel", "cloud"),
    "netlify": ("Netlify", "cloud"),
    "cloudflare": ("Cloudflare", "cloud"),
    "digitalocean": ("DigitalOcean", "cloud"),
    "ec2": ("AWS EC2", "cloud"),
    "s3": ("AWS S3", "cloud"),
    "lambda": ("AWS Lambda", "cloud"),

    # DevOps / Infrastructure
    "docker": ("Docker", "devops"),
    "kubernetes": ("Kubernetes", "devops"),
    "k8s": ("Kubernetes", "devops"),
    "terraform": ("Terraform", "devops"),
    "ansible": ("Ansible", "devops"),
    "jenkins": ("Jenkins", "devops"),
    "github actions": ("GitHub Actions", "Cloud & DevOps"),
    "gitlab ci": ("GitLab CI", "Cloud & DevOps"),
    "ci/cd": ("CI/CD", "devops"),
    "nginx": ("Nginx", "devops"),
    "apache": ("Apache", "devops"),
    "linux": ("Linux", "Databases & Tools"),
    "ubuntu": ("Ubuntu", "Databases & Tools"),
    "unix": ("Unix", "Databases & Tools"),

    # ML / AI
    "machine learning": ("Machine Learning", "ml_ai"),
    "deep learning": ("Deep Learning", "ml_ai"),
    "tensorflow": ("TensorFlow", "ml_ai"),
    "pytorch": ("PyTorch", "ml_ai"),
    "keras": ("Keras", "ml_ai"),
    "scikit-learn": ("scikit-learn", "ml_ai"),
    "sklearn": ("scikit-learn", "ml_ai"),
    "pandas": ("Pandas", "ml_ai"),
    "numpy": ("NumPy", "ml_ai"),
    "matplotlib": ("Matplotlib", "ml_ai"),
    "seaborn": ("Seaborn", "ml_ai"),
    "nlp": ("NLP", "ml_ai"),
    "computer vision": ("Computer Vision", "Data Science & ML"),
    "opencv": ("OpenCV", "Data Science & ML"),
    "hugging face": ("Hugging Face", "ml_ai"),
    "langchain": ("LangChain", "ml_ai"),
    "llm": ("LLMs", "ml_ai"),
    "openai": ("OpenAI API", "ml_ai"),
    "data science": ("Data Science", "ml_ai"),
    "data analysis": ("Data Analysis", "ml_ai"),

    # Design & UX
    "figma": ("Figma", "Design & UX"),
    "adobe xd": ("Adobe XD", "Design & UX"),
    "photoshop": ("Photoshop", "Design & UX"),
    "illustrator": ("Illustrator", "Design & UX"),
    "adobe illustrator": ("Adobe Illustrator", "Design & UX"),
    "sketch": ("Sketch", "Design & UX"),
    "invision": ("InVision", "Design & UX"),
    "ui/ux design": ("UI/UX Design", "Design & UX"),
    "ui & ux design": ("UI & UX Design", "Design & UX"),
    "ui/ux": ("UI/UX", "Design & UX"),
    "ux/ui": ("UX/UI", "Design & UX"),
    "ux/ui design": ("UX/UI Design", "Design & UX"),
    "ui design": ("UI Design", "Design & UX"),
    "ux design": ("UX Design", "Design & UX"),
    "user interface design": ("User Interface Design", "Design & UX"),
    "user experience design": ("User Experience Design", "Design & UX"),
    "wireframing": ("Wireframing", "Design & UX"),
    "prototyping": ("Prototyping", "Design & UX"),
    "canva": ("Canva", "Design & UX"),
    "design systems": ("Design Systems", "Design & UX"),

    # Cybersecurity
    "cybersecurity": ("Cybersecurity", "Cybersecurity"),
    "network security": ("Network Security", "Cybersecurity"),
    "penetration testing": ("Penetration Testing", "Cybersecurity"),
    "ethical hacking": ("Ethical Hacking", "Cybersecurity"),
    "owasp": ("OWASP", "Cybersecurity"),
    "cryptography": ("Cryptography", "Cybersecurity"),
    "iam": ("IAM", "Cybersecurity"),
    "siem": ("SIEM", "Cybersecurity"),
    "firewall": ("Firewall", "Cybersecurity"),

    # Tools & Platforms
    "git": ("Git", "tools"),
    "github": ("GitHub", "tools"),
    "gitlab": ("GitLab", "tools"),
    "bitbucket": ("Bitbucket", "tools"),
    "jira": ("Jira", "tools"),
    "confluence": ("Confluence", "tools"),
    "slack": ("Slack", "tools"),
    "postman": ("Postman", "tools"),
    "vs code": ("VS Code", "tools"),
    "vscode": ("VS Code", "tools"),
    "intellij": ("IntelliJ IDEA", "tools"),
    "xcode": ("Xcode", "Mobile Development"),
    "jupyter": ("Jupyter", "Data Science & ML"),
    "notion": ("Notion", "tools"),
    "excel": ("Microsoft Excel", "tools"),
    "tableau": ("Tableau", "Data Science & ML"),
    "power bi": ("Power BI", "Data Science & ML"),
    "linux terminal": ("Linux Terminal", "tools"),

    # Soft Skills
    "leadership": ("Leadership", "soft_skills"),
    "communication": ("Communication", "soft_skills"),
    "teamwork": ("Teamwork", "soft_skills"),
    "problem solving": ("Problem Solving", "soft_skills"),
    "critical thinking": ("Critical Thinking", "soft_skills"),
    "time management": ("Time Management", "soft_skills"),
    "project management": ("Project Management", "soft_skills"),
    "agile": ("Agile", "soft_skills"),
    "scrum": ("Scrum", "soft_skills"),
    "kanban": ("Kanban", "soft_skills"),
    "mentoring": ("Mentoring", "soft_skills"),
    "collaboration": ("Collaboration", "soft_skills"),
    "adaptability": ("Adaptability", "soft_skills"),
    "creativity": ("Creativity", "soft_skills"),
}

# Separator patterns used in skills sections (bullets, commas, pipes, semicolons)
_SEPARATOR = re.compile(r"[,|;•\n\t]+")
_SKILL_NOISE = re.compile(r"^(skills?|technical|core|key|proficient\s+in|familiar\s+with|knowledgeable\s+in):?\s*", re.IGNORECASE)


# ─── Public entry point ────────────────────────────────────────────────────────

def parse(skills_text: str, supplemental_texts: list[str] | None = None) -> dict:
    """
    skills_text: content of the dedicated skills section
    supplemental_texts: other sections (experience, projects) to also scan for skills
    """
    combined = skills_text
    if supplemental_texts:
        combined += "\n" + "\n".join(supplemental_texts)

    # Raw skill tokens
    tokens = _tokenize(combined)

    all_skills = []
    by_category: dict[str, list[str]] = {}
    seen: set[str] = set()

    for token in tokens:
        canonical, category = _lookup(token)
        if canonical and canonical.lower() not in seen:
            all_skills.append(canonical)
            seen.add(canonical.lower())
    from services.skill_manager import consolidate_skill_categories
    by_category = consolidate_skill_categories(by_category)

    return {
        "all": all_skills,
        "byCategory": by_category,
        "_confidence": "high" if all_skills else "low"
    }


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Split skills text into candidate tokens while preserving compound phrases."""
    from services.skill_manager import protect_compound_phrases, restore_compound_phrases
    
    # Protect known compound phrases before splitting
    protected_text, placeholders = protect_compound_phrases(text)
    
    # Remove section header noise
    protected_text = _SKILL_NOISE.sub("", protected_text)
    
    # Split on separators
    parts = _SEPARATOR.split(protected_text)
    tokens = []
    for part in parts:
        part = part.strip().strip("()[]").strip()
        if 1 < len(part) <= 50:
            tokens.append(part)
            
    # Restore compound phrases
    return restore_compound_phrases(tokens, placeholders)


def _lookup(token: str) -> tuple[str | None, str]:
    """Look up a token in the taxonomy. Returns (canonical_name, category) or (None, 'other')."""
    key = token.lower().strip()

    # Direct match
    if key in SKILL_TAXONOMY:
        return SKILL_TAXONOMY[key]

    # Partial match — only for keys longer than 3 chars (prevents "js" matching "jsp")
    for skill_key, (canonical, category) in SKILL_TAXONOMY.items():
        if len(skill_key) <= 3 or len(key) <= 3:
            continue  # Short acronyms MUST be exact matches to avoid "js" in "jsp"
        if re.search(rf'\b{re.escape(skill_key)}\b', key, re.IGNORECASE):
            return canonical, category

    return None, "other"
