"""
Curated word lists for the deterministic ATS scoring engine.

These lists power the rule-based checks in ats_scorer.py.
No AI involved — just well-researched dictionaries.
"""

# ─── Strong Action Verbs ────────────────────────────────────────────
# Resume Worded and Harvard's resume guides recommend these.
# Each bullet point should ideally start with one of these.

STRONG_ACTION_VERBS = {
    # Leadership & Management
    "achieved", "administered", "advanced", "allocated", "appointed",
    "approved", "assigned", "attained", "authorized", "chaired",
    "championed", "consolidated", "coordinated", "cultivated", "delegated",
    "directed", "eliminated", "enforced", "established", "executed",
    "founded", "governed", "headed", "hired", "hosted", "initiated",
    "instituted", "led", "managed", "mentored", "motivated", "navigated",
    "orchestrated", "organized", "oversaw", "pioneered", "planned",
    "presided", "prioritized", "produced", "recruited", "reorganized",
    "replaced", "restored", "reviewed", "spearheaded", "steered",
    "strengthened", "supervised", "united",

    # Technical & Engineering
    "architected", "assembled", "automated", "benchmarked", "built",
    "coded", "compiled", "computed", "configured", "constructed",
    "containerized", "debugged", "deployed", "designed", "developed",
    "devised", "digitized", "engineered", "fabricated", "formulated",
    "hacked", "hardened", "implemented", "installed", "integrated",
    "iterated", "launched", "maintained", "migrated", "modeled",
    "modernized", "monitored", "operationalized", "optimized",
    "overhauled", "patched", "programmed", "prototyped", "provisioned",
    "rebuilt", "reconfigured", "redesigned", "refactored", "reengineered",
    "released", "remediated", "rendered", "replicated", "resolved",
    "restructured", "retrofitted", "scaled", "scripted", "secured",
    "shipped", "simplified", "simulated", "solved", "standardized",
    "streamlined", "stress-tested", "synthesized", "systematized",
    "tested", "troubleshot", "tuned", "unified", "upgraded", "validated",
    "verified", "virtualized",

    # Analysis & Research
    "analyzed", "appraised", "assessed", "audited", "calculated",
    "classified", "collected", "compared", "conducted", "correlated",
    "critiqued", "deciphered", "detected", "determined", "diagnosed",
    "dissected", "estimated", "evaluated", "examined", "experimented",
    "explored", "extracted", "forecasted", "identified", "inspected",
    "interpreted", "investigated", "mapped", "measured", "observed",
    "predicted", "profiled", "projected", "quantified", "researched",
    "studied", "surveyed", "tabulated", "tested", "tracked",

    # Communication & Collaboration
    "addressed", "advised", "advocated", "authored", "briefed",
    "clarified", "coached", "collaborated", "communicated", "composed",
    "consulted", "conveyed", "convinced", "corresponded", "counseled",
    "critiqued", "defined", "demonstrated", "described", "documented",
    "drafted", "edited", "educated", "elicited", "enabled", "enlisted",
    "explained", "facilitated", "guided", "illustrated", "influenced",
    "informed", "instructed", "lectured", "liaised", "mediated",
    "moderated", "negotiated", "outlined", "participated", "persuaded",
    "presented", "promoted", "proposed", "publicized", "recommended",
    "reconciled", "reported", "represented", "shaped", "solicited",
    "summarized", "taught", "trained", "translated", "wrote",

    # Creative & Design
    "conceptualized", "crafted", "created", "customized", "decorated",
    "envisioned", "fashioned", "illustrated", "imagined", "improvised",
    "innovated", "introduced", "invented", "modeled", "originated",
    "performed", "photographed", "planned", "redesigned", "revamped",
    "revitalized", "shaped", "sketched", "styled", "transformed",
    "visualized",

    # Financial & Business
    "acquired", "balanced", "boosted", "budgeted", "capitalized",
    "centralized", "conserved", "converted", "cut", "decreased",
    "delivered", "earned", "economized", "expanded", "financed",
    "generated", "grew", "improved", "increased", "leveraged",
    "marketed", "maximized", "merchandised", "minimized", "negotiated",
    "netted", "procured", "profited", "projected", "purchased",
    "realized", "recaptured", "recovered", "reduced", "saved",
    "secured", "sold", "sourced", "sustained", "tripled", "doubled",
    "yielded",
}

# ─── Weak / Filler Phrases ──────────────────────────────────────────
# These phrases signal passive, vague writing. Deduct points if found.

WEAK_PHRASES = [
    "responsible for",
    "helped with",
    "helped in",
    "assisted in",
    "assisted with",
    "worked on",
    "worked with",
    "was involved in",
    "involved in",
    "participated in",
    "tasked with",
    "played a role",
    "was part of",
    "contributed to",
    "in charge of",
    "duties included",
    "duties include",
    "job duties",
    "day-to-day",
    "handled various",
    "various tasks",
    "etc.",
    "and so on",
    "among other things",
    "as needed",
    "on a daily basis",
    "utilized",  # Overly formal; use "used"
    "leveraged",  # Often misused as filler
]

# ─── Buzzwords / Clichés ────────────────────────────────────────────
# Generic soft-skill claims with no evidence. Flag these.

BUZZWORDS = [
    "detail-oriented",
    "detail oriented",
    "hard worker",
    "hard-working",
    "hardworking",
    "team player",
    "go-getter",
    "self-starter",
    "self starter",
    "results-driven",
    "results driven",
    "dynamic",
    "synergy",
    "think outside the box",
    "outside the box",
    "passionate",
    "motivated individual",
    "highly motivated",
    "excellent communication skills",
    "strong communication",
    "proven track record",
    "fast learner",
    "quick learner",
    "people person",
    "proactive",
    "strategic thinker",
    "innovative thinker",
    "best of breed",
    "guru",
    "ninja",
    "rockstar",
    "wizard",
]

# ─── Hard Skills Dictionary ─────────────────────────────────────────
# Known technical skills. Used to distinguish hard vs soft skills
# and to validate that the resume contains concrete, indexable terms.

HARD_SKILLS = {
    # Programming Languages
    "python", "java", "javascript", "typescript", "c", "c++", "c#",
    "go", "golang", "rust", "ruby", "php", "swift", "kotlin", "scala",
    "r", "matlab", "perl", "lua", "dart", "elixir", "haskell",
    "objective-c", "assembly", "fortran", "cobol", "vba", "bash",
    "shell", "powershell", "sql", "plsql", "t-sql", "graphql",

    # Web Frontend
    "html", "html5", "css", "css3", "sass", "scss", "less",
    "tailwindcss", "tailwind", "bootstrap", "material ui", "mui",
    "react", "reactjs", "react.js", "react native", "next.js", "nextjs",
    "vue", "vuejs", "vue.js", "nuxt", "nuxtjs", "angular", "angularjs",
    "svelte", "sveltekit", "gatsby", "remix", "astro",
    "jquery", "redux", "zustand", "mobx", "webpack", "vite", "parcel",
    "rollup", "babel", "eslint", "prettier",

    # Web Backend
    "node.js", "nodejs", "express", "express.js", "expressjs",
    "fastapi", "flask", "django", "spring", "spring boot", "springboot",
    "rails", "ruby on rails", "laravel", "asp.net", ".net", "dotnet",
    "gin", "fiber", "actix", "rocket", "phoenix", "nestjs", "nest.js",
    "graphql", "rest", "rest api", "rest apis", "grpc", "soap",
    "websocket", "websockets", "microservices",

    # Databases
    "mysql", "postgresql", "postgres", "sqlite", "mariadb", "oracle",
    "sql server", "mssql", "mongodb", "mongoose", "redis", "memcached",
    "cassandra", "dynamodb", "couchdb", "neo4j", "elasticsearch",
    "opensearch", "influxdb", "timescaledb", "supabase", "firebase",
    "firestore", "cockroachdb", "planetscale", "neon",

    # Cloud & DevOps
    "aws", "amazon web services", "ec2", "s3", "lambda", "ecs", "eks",
    "fargate", "cloudformation", "cdk", "sagemaker", "bedrock",
    "azure", "microsoft azure", "gcp", "google cloud", "google cloud platform",
    "heroku", "vercel", "netlify", "digitalocean", "linode",
    "docker", "kubernetes", "k8s", "helm", "terraform", "ansible",
    "puppet", "chef", "vagrant", "packer",
    "ci/cd", "cicd", "jenkins", "github actions", "gitlab ci",
    "circleci", "travis ci", "argo cd", "argocd",
    "nginx", "apache", "caddy", "traefik", "haproxy",
    "linux", "ubuntu", "centos", "debian", "rhel",

    # Data Science & ML
    "machine learning", "deep learning", "neural networks",
    "natural language processing", "nlp", "computer vision", "cv",
    "tensorflow", "pytorch", "keras", "scikit-learn", "sklearn",
    "pandas", "numpy", "scipy", "matplotlib", "seaborn", "plotly",
    "jupyter", "jupyter notebook", "colab",
    "opencv", "yolo", "transformers", "hugging face", "huggingface",
    "bert", "gpt", "llm", "large language model", "rag",
    "langchain", "llamaindex", "vector database", "pinecone", "qdrant",
    "weaviate", "chroma", "faiss", "embeddings",
    "data analysis", "data analytics", "data engineering",
    "data pipeline", "etl", "airflow", "spark", "pyspark",
    "hadoop", "hive", "kafka", "flink", "dbt",
    "tableau", "power bi", "looker", "metabase", "superset",

    # Mobile
    "android", "ios", "flutter", "react native", "xamarin",
    "swiftui", "uikit", "jetpack compose", "kotlin multiplatform",

    # Testing
    "jest", "mocha", "chai", "pytest", "unittest", "junit",
    "selenium", "cypress", "playwright", "puppeteer",
    "postman", "insomnia", "swagger", "openapi",
    "tdd", "bdd", "unit testing", "integration testing",
    "e2e testing", "load testing", "stress testing",

    # Security
    "cybersecurity", "penetration testing", "pen testing",
    "owasp", "encryption", "ssl", "tls", "https",
    "oauth", "oauth2", "jwt", "jwt authentication",
    "saml", "sso", "single sign-on", "rbac",
    "firewalls", "ids", "ips", "siem", "soar",
    "vulnerability assessment", "malware analysis",

    # Version Control & Collaboration
    "git", "github", "gitlab", "bitbucket", "svn",
    "jira", "confluence", "trello", "asana", "notion",
    "slack", "teams", "figma", "sketch", "adobe xd",
    "agile", "scrum", "kanban", "waterfall", "sprint",

    # Other
    "api", "apis", "sdk", "cli", "orm",
    "data structures", "algorithms", "data structures & algorithms",
    "operating systems", "os", "compiler design",
    "system design", "distributed systems", "concurrency",
    "blockchain", "web3", "solidity", "ethereum",
    "iot", "internet of things", "embedded systems",
    "robotics", "ros", "arduino", "raspberry pi",
}

# ─── Stopwords for Keyword Extraction ────────────────────────────────
# Used when extracting keywords from job descriptions

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "as", "is", "was", "are",
    "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "will", "would", "shall", "should", "may", "might", "must",
    "can", "could", "about", "above", "after", "again", "against",
    "all", "am", "any", "aren't", "because", "before", "below",
    "between", "both", "couldn't", "didn't", "doesn't", "doing",
    "don't", "down", "during", "each", "few", "further", "hadn't",
    "hasn't", "haven't", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "into", "isn't",
    "it", "its", "itself", "let's", "me", "more", "most", "mustn't",
    "my", "myself", "no", "nor", "not", "off", "once", "only",
    "other", "our", "ours", "ourselves", "out", "over", "own",
    "same", "shan't", "she", "so", "some", "such", "than", "that",
    "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "too", "under", "until", "up",
    "very", "we", "what", "when", "where", "which", "while", "who",
    "whom", "why", "won't", "wouldn't", "you", "your", "yours",
    "yourself", "yourselves",
    # Additional common resume filler words
    "able", "also", "well", "work", "working", "using", "used",
    "need", "needed", "including", "include", "includes", "like",
    "looking", "look", "join", "role", "position", "candidate",
    "ideal", "required", "requirements", "experience", "year", "years",
    "strong", "excellent", "good", "great", "best", "new", "us",
    "company", "team", "opportunity", "etc", "within", "across",
}
