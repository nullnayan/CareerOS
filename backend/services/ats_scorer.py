import re
from services.text_extraction import _normalize_ligatures
from typing import Optional, Dict, List
from services.ats_wordlists import (
    STRONG_ACTION_VERBS, WEAK_PHRASES, BUZZWORDS,
    HARD_SKILLS, STOPWORDS,
)

# ─── Soft skills list (interpersonal / non-technical) ────────────────────────
SOFT_SKILLS = {
    "communication", "teamwork", "team player", "collaboration", "leadership",
    "problem solving", "problem-solving", "critical thinking", "time management",
    "adaptability", "creativity", "initiative", "multitasking", "work ethic",
    "attention to detail", "interpersonal", "presentation", "negotiation",
    "conflict resolution", "decision making", "decision-making", "empathy",
    "flexibility", "organization", "organizational", "self-motivated",
    "project management", "stakeholder management", "analytical", "innovative",
}

# ─── Acronym synonym expansion ──────────────────────────────────────────────
# Maps short form ↔ long form so keyword matching finds both
ACRONYM_MAP = {
    "aws": "amazon web services",
    "amazon web services": "aws",
    "gcp": "google cloud platform",
    "google cloud platform": "gcp",
    "ci/cd": "continuous integration continuous deployment",
    "nlp": "natural language processing",
    "natural language processing": "nlp",
    "ml": "machine learning",
    "machine learning": "ml",
    "ai": "artificial intelligence",
    "artificial intelligence": "ai",
    "ui": "user interface",
    "ux": "user experience",
    "api": "application programming interface",
    "sdk": "software development kit",
    "oop": "object oriented programming",
    "k8s": "kubernetes",
    "kubernetes": "k8s",
    "js": "javascript",
    "javascript": "js",
    "ts": "typescript",
    "typescript": "ts",
    "db": "database",
    "sql": "structured query language",
    "nosql": "no sql",
    "devops": "development operations",
    "sre": "site reliability engineering",
    "tdd": "test driven development",
    "bdd": "behavior driven development",
    "rest": "representational state transfer",
    "vm": "virtual machine",
    "os": "operating system",
}

# ─── Unprofessional email patterns ──────────────────────────────────────────
UNPROFESSIONAL_EMAIL_PATTERNS = re.compile(
    r'(?:hotboy|hottie|sexy|cool|ninja|rockstar|wizard|beast|legend|'
    r'killer|badboy|badgirl|lol|omg|wtf|yolo|swag|420|69|xXx|'
    r'gaming|gamer|hacker|h4x0r)',
    re.IGNORECASE
)

# ─── Known certification keywords ────────────────────────────────────────────
CERTIFICATION_KEYWORDS = {
    "aws certified", "google cloud certified", "azure certified",
    "pmp", "prince2", "scrum master", "csm", "psm",
    "certified kubernetes", "ckad", "cka",
    "comptia", "security+", "network+", "a+",
    "cisco", "ccna", "ccnp", "ccie",
    "tensorflow developer", "google professional",
    "databricks", "snowflake certified",
    "salesforce", "oracle certified",
    "certified data scientist", "certified data analyst",
    "itil", "six sigma", "lean", "togaf",
}

# ─── Section order scoring ───────────────────────────────────────────────────
# Premium ATS check: sections should appear in this order
EXPECTED_SECTION_ORDER = ["contact", "summary", "experience", "education", "skills", "projects", "certifications"]


# Import the new ats_engine components
from ats_engine.keyword_engine.section_weighted_matcher import section_weighted_score
from ats_engine.content_checks.stuffing_checker import combined_stuffing_score
from ats_engine.content_checks.leadership_style_checker import check_leadership_signals, check_style
from ats_engine.content_checks.redflag_checker import check_seniority_mismatch, check_date_gaps
from ats_engine.formatting_checks.whitespace_checker import check_line_gaps
from ats_engine.formatting_checks.consistency_checker import combined_consistency_score
from ats_engine.content_checks.readability_checker import check_readability
from ats_engine.content_checks.repetition_checker import combined_repetition_score
from ats_engine.content_checks.unnecessary_sections_checker import check_unnecessary_sections
from ats_engine.scorer.score_engine_v2 import (
    calculate_ats_score, categorize_skills,
    analyze_all_bullets, build_jd_match_report, check_missing_info,
    build_best_practices_checklist, check_parsing_confidence
)
from agents.recruiter_judge import score_recruiter_readiness, score_trajectory_alignment

# ─── Helpers ────────────────────────────────────────────────────────

def _get_all_text_blocks(resume: dict) -> list[str]:
    """Collect every descriptive text block from experience + projects."""
    blocks = []
    experience_list = resume.get("experience", [])
    if isinstance(experience_list, list):
        for exp in experience_list:
            if not isinstance(exp, dict):
                continue
            raw_bullets = exp.get("bullets", exp.get("bullet_points", []))
            for bp in raw_bullets:
                blocks.append(bp)
            if exp.get("description"):
                blocks.append(exp["description"])
    projects_list = resume.get("projects", [])
    if isinstance(projects_list, list):
        for proj in projects_list:
            if not isinstance(proj, dict):
                continue
            if proj.get("description"):
                blocks.append(proj["description"])
            raw_bullets = proj.get("bullets", proj.get("bullet_points", []))
            for bp in raw_bullets:
                blocks.append(bp)
    return blocks


def _get_skills_list(resume: dict) -> list[str]:
    """Normalize skills into a flat list of lowercase strings."""
    skills = []
    for s in resume.get("skills", []):
        if isinstance(s, str):
            skills.append(s.strip().lower())
        elif isinstance(s, dict):
            name = s.get("name", "").strip().lower()
            if name:
                skills.append(name)
    return skills


def _get_sections_text(resume: dict) -> dict[str, str]:
    """Helper to extract text from each section of the structured JSON."""
    sections = {}
    
    # 1. Skills
    skills = _get_skills_list(resume)
    sections["skills"] = ", ".join(skills)
    
    # 2. Experience
    exp_texts = []
    experience_list = resume.get("experience", [])
    if isinstance(experience_list, list):
        for exp in experience_list:
            if not isinstance(exp, dict):
                continue
            company = exp.get("company", "") or ""
            title = exp.get("title", "") or ""
            desc = exp.get("description", "") or ""
            raw_bullets = exp.get("bullets", exp.get("bullet_points", []))
            bullets = " ".join([b for b in raw_bullets if isinstance(b, str)]) if isinstance(raw_bullets, list) else ""
            exp_texts.append(f"{title} at {company}. {desc} {bullets}")
    sections["experience"] = " ".join(exp_texts)
    
    # 3. Projects
    proj_texts = []
    projects_list = resume.get("projects", [])
    if isinstance(projects_list, list):
        for proj in projects_list:
            if not isinstance(proj, dict):
                continue
            name = proj.get("name", "") or ""
            desc = proj.get("description", "") or ""
            raw_bullets = proj.get("bullets", proj.get("bullet_points", []))
            bullets = " ".join([b for b in raw_bullets if isinstance(b, str)]) if isinstance(raw_bullets, list) else ""
            proj_texts.append(f"{name}. {desc} {bullets}")
    sections["projects"] = " ".join(proj_texts)
    
    # 4. Summary
    sections["summary"] = resume.get("summary") or ""
    
    # 5. Education
    edu_texts = []
    education_list = resume.get("education", [])
    if isinstance(education_list, list):
        for edu in education_list:
            if not isinstance(edu, dict):
                continue
            inst = edu.get("institution", "") or ""
            deg = edu.get("degree", "") or ""
            field = edu.get("field", "") or ""
            edu_texts.append(f"{deg} in {field} from {inst}")
    sections["education"] = " ".join(edu_texts)
    
    # 6. Certifications
    certs = resume.get("certifications", [])
    if isinstance(certs, list):
        cert_names = [c if isinstance(c, str) else c.get("name", str(c)) for c in certs if isinstance(c, (str, dict))]
        sections["certifications"] = ", ".join(cert_names)
    else:
        sections["certifications"] = str(certs)
    
    return sections


def _calculate_years_experience(resume: dict) -> float:
    from ats_engine.content_checks.redflag_checker import DATE_RANGE_PATTERN, _parse_month_year
    total_months = 0.0
    experience_list = resume.get("experience", [])
    if not isinstance(experience_list, list):
        return 0.0
    for exp in experience_list:
        if not isinstance(exp, dict):
            continue
        start_str = exp.get("start_date") or exp.get("startDate") or ""
        end_str = exp.get("end_date") or exp.get("endDate") or "Present"
        if not start_str:
            continue
        range_str = f"{start_str} - {end_str}"
        m = DATE_RANGE_PATTERN.search(range_str)
        if m:
            start = _parse_month_year(m.group(1))
            end = _parse_month_year(m.group(2))
            if start and end:
                months = (end.year - start.year) * 12 + (end.month - start.month)
                total_months += max(0, months)
    return total_months / 12.0


def _match_fn(text: str, keywords: list) -> float:
    """Combines exact matching and local semantic embeddings."""
    text_lower = text.lower()
    if not text_lower.strip() or not keywords:
        return 0.0
        
    matched = 0
    missing_kws = []
    for kw in keywords:
        if kw.lower().strip() in text_lower:
            matched += 1
        else:
            missing_kws.append(kw)
            
    if not missing_kws:
        return 1.0

    try:
        from agents.llm_client import get_embeddings_batch
        import numpy as np
        
        chunks = [c.strip() for c in text.split('\n') if len(c.strip()) > 10]
        if not chunks:
            chunks = [text]
            
        chunk_vecs = np.array(get_embeddings_batch(chunks))
        kw_vecs = np.array(get_embeddings_batch(missing_kws))
        
        if len(chunk_vecs) > 0 and len(kw_vecs) > 0:
            chunk_norms = np.linalg.norm(chunk_vecs, axis=1)
            for kw_vec in kw_vecs:
                kw_norm = np.linalg.norm(kw_vec)
                dots = np.dot(chunk_vecs, kw_vec)
                sims = dots / (chunk_norms * kw_norm + 1e-9)
                if np.max(sims) > 0.5:
                    matched += 1
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Semantic match failed: {e}")
        
    return matched / len(keywords)


def _extract_jd_keywords(job_description: str) -> List[str]:
    """Helper to extract unique keywords from Job Description using centralized JDAnalyzer."""
    if not job_description or not job_description.strip():
        return []
    try:
        from services.jd_analyzer import analyze_jd
        analysis = analyze_jd(job_description)
        kws = (analysis.get("required_hard_skills", []) +
               analysis.get("required_soft_skills", []) +
               analysis.get("jd_keywords", []))
        result = list({k.strip() for k in kws if k and isinstance(k, str)})
        if result:
            return result
    except Exception:
        pass

    # Regex fallback
    jd_lower = job_description.lower()
    jd_words = re.findall(r'[a-z][a-z\.\+\#\-/]+', jd_lower)
    jd_words = [w for w in jd_words if w not in STOPWORDS and len(w) > 2]
    jd_keywords = set(w for w in jd_words if w in HARD_SKILLS)
    return list(jd_keywords)


def score_resume_baseline(resume_json: dict, raw_text: str = None) -> dict:
    """Exposes baseline scoring, wrapping around new ats_engine logic."""
    if raw_text:
        raw_text = _normalize_ligatures(raw_text)
    return _run_ats_scorer_orchestrator(resume_json, job_description="", raw_text=raw_text)


def score_resume_targeted(resume_json: dict, job_description, raw_text: str = None) -> dict:
    """
    Exposes targeted scoring using canonical JD analysis object (dict) or raw text string.
    Single-source-of-truth: If job_description is a string, converts it to canonical
    jd_analysis dict via Phase 1 to guarantee consistent keyword extraction.
    """
    if raw_text:
        raw_text = _normalize_ligatures(raw_text)
    return _run_ats_scorer_orchestrator(resume_json, job_description=job_description, raw_text=raw_text)


def _adapt_resume_to_legacy_schema(resume: dict) -> dict:
    """
    Adapts the new resume pipeline schema to the legacy schema format
    expected by the ATS Scorer and ats_engine.
    """
    if not isinstance(resume, dict):
        return {}

    # If it is already legacy, return it as-is
    is_new_schema = (
        isinstance(resume.get("experience"), dict) or 
        isinstance(resume.get("skills"), dict) or
        isinstance(resume.get("contact", {}).get("location"), dict)
    )
    if not is_new_schema:
        return resume

    adapted = {}

    # 1. Contact Info
    contact = resume.get("contact") or {}
    links = list(contact.get("links") or [])
    for field in ["linkedin", "github", "portfolio"]:
        val = contact.get(field)
        if val and val not in links:
            links.append(val)
            
    loc_val = contact.get("location")
    if isinstance(loc_val, dict):
        loc_str = loc_val.get("raw") or ""
    else:
        loc_str = str(loc_val or "")

    adapted["contact"] = {
        "name": contact.get("name"),
        "email": contact.get("email"),
        "phone": contact.get("phone"),
        "location": loc_str if loc_str else None,
        "links": links
    }

    # 2. Summary
    adapted["summary"] = resume.get("summary")

    # 3. Skills
    skills = resume.get("skills") or {}
    if isinstance(skills, dict):
        adapted["skills"] = skills.get("all") or []
    else:
        adapted["skills"] = list(skills)

    # 4. Experience
    exp = resume.get("experience") or {}
    entries = []
    if isinstance(exp, dict):
        entries = exp.get("entries") or []
    else:
        entries = list(exp)
        
    adapted_exp = []
    for e in entries:
        if isinstance(e, dict):
            adapted_exp.append({
                "company": e.get("company"),
                "title": e.get("title"),
                "start_date": e.get("startDate"),
                "end_date": "Present" if e.get("isCurrent") else e.get("endDate"),
                "bullet_points": e.get("bullets") or []
            })
    adapted["experience"] = adapted_exp

    # 5. Education
    edu = resume.get("education") or []
    adapted_edu = []
    if isinstance(edu, list):
        for e in edu:
            if isinstance(e, dict):
                gpa_val = e.get("gpa")
                if isinstance(gpa_val, dict):
                    gpa_str = gpa_val.get("raw") or ""
                else:
                    gpa_str = str(gpa_val or "")
                
                adapted_edu.append({
                    "institution": e.get("institution"),
                    "degree": e.get("degree"),
                    "field": e.get("field"),
                    "graduation_date": str(e.get("endYear")) if e.get("endYear") else None,
                    "cgpa_or_percentage": gpa_str if gpa_str else None
                })
    adapted["education"] = adapted_edu

    # 6. Projects
    proj = resume.get("projects")
    adapted_proj = []
    if isinstance(proj, str) and proj.strip():
        adapted_proj.append({
            "name": "Personal Projects",
            "bullets": [p.strip() for p in proj.split("\n") if p.strip()],
            "technologies": []
        })
    elif isinstance(proj, list):
        for p in proj:
            if isinstance(p, dict):
                adapted_proj.append({
                    "name": p.get("name"),
                    "bullets": p.get("bullets") or p.get("bullet_points") or [],
                    "technologies": p.get("technologies") or []
                })
    adapted["projects"] = adapted_proj

    # 7. Certifications
    certs = resume.get("certifications") or []
    adapted_certs = []
    if isinstance(certs, list):
        for c in certs:
            if isinstance(c, str):
                adapted_certs.append(c)
            elif isinstance(c, dict):
                name = c.get("name")
                if name:
                    adapted_certs.append(name)
    adapted["certifications"] = adapted_certs

    # 8. Extra metadata
    adapted["formatting_metadata"] = {
        "has_columns": resume.get("metadata", {}).get("hasColumns", False),
        "has_tables": resume.get("metadata", {}).get("hasTables", False),
        "is_scanned_pdf": resume.get("metadata", {}).get("isScannedPdf", False),
    }

    return adapted


def _run_ats_scorer_orchestrator(resume_json: dict, job_description: str = "", raw_text: str = None) -> dict:
    """Orchestrates all new ats_engine components and maps them back for API compatibility."""
    resume_json = _adapt_resume_to_legacy_schema(resume_json)
    issues = []
    
    # Pre-extract texts & bullets
    sections = _get_sections_text(resume_json)
    bullets = []
    experience_list = resume_json.get("experience", [])
    if isinstance(experience_list, list):
        for exp in experience_list:
            if isinstance(exp, dict):
                # Robust extraction: if bullet_points is empty but description has text, parse it
                bps = exp.get("bullets", exp.get("bullet_points", []))
                if not bps or not isinstance(bps, list):
                    desc = exp.get("description", "") or ""
                    # Split by bullet points or newlines
                    parsed_bullets = [line.strip().lstrip("•-*• ") for line in re.split(r'\n|•|\*|-', desc) if len(line.strip()) > 5]
                    bullets.extend(parsed_bullets)
                else:
                    bullets.extend([b for b in bps if isinstance(b, str)])
    projects_list = resume_json.get("projects", [])
    if isinstance(projects_list, list):
        for proj in projects_list:
            if isinstance(proj, dict):
                bps = proj.get("bullets", proj.get("bullet_points", []))
                if not bps or not isinstance(bps, list):
                    desc = proj.get("description", "") or ""
                    parsed_bullets = [line.strip().lstrip("•-*• ") for line in re.split(r'\n|•|\*|-', desc) if len(line.strip()) > 5]
                    bullets.extend(parsed_bullets)
                else:
                    bullets.extend([b for b in bps if isinstance(b, str)])
        
    full_resume_text = raw_text or " ".join(sections.values())
    
    # --- 1. Keyword match (Canonical Single Source of Truth — Fix 1) ---
    jd_analysis = None
    jd_text = ""
    if isinstance(job_description, dict):
        jd_analysis = job_description
        jd_text = job_description.get("raw_jd_text", "")
    elif isinstance(job_description, str) and job_description.strip():
        jd_text = job_description
    if jd_analysis and isinstance(jd_analysis, dict):
        hard_kws = jd_analysis.get("required_hard_skills", []) or jd_analysis.get("jd_required_skills", [])
        soft_kws = jd_analysis.get("required_soft_skills", []) or jd_analysis.get("soft_skills_missing", [])
        extra_kws = jd_analysis.get("jd_keywords", [])
        jd_keywords = list({k.strip(): k for k in (hard_kws + soft_kws + extra_kws) if k and isinstance(k, str)}.values())
    elif jd_text:
        jd_keywords = _extract_jd_keywords(jd_text)
    else:
        jd_keywords = []

    is_targeted = bool(jd_keywords)
    
    if is_targeted:
        # Pre-compute batch embeddings for all keywords and resume section chunks to avoid 429 Rate Limits
        from agents.llm_client import get_embeddings_batch
        import numpy as np
        
        # Gather all chunks from all sections
        all_chunks = set()
        section_chunks = {}
        for sec_name, text in sections.items():
            chunks = [c.strip() for c in text.split('\n') if len(c.strip()) > 10]
            if not chunks and text.strip():
                chunks = [text.strip()]
            section_chunks[sec_name] = chunks
            for c in chunks:
                all_chunks.add(c)
                
        all_chunks_list = list(all_chunks)
        
        # Batch embed all chunks and keywords together
        to_embed = all_chunks_list + jd_keywords
        try:
            embeddings = get_embeddings_batch(to_embed)
            chunk_embeds = {text: emb for text, emb in zip(all_chunks_list, embeddings[:len(all_chunks_list)])}
            kw_embeds = {text: emb for text, emb in zip(jd_keywords, embeddings[len(all_chunks_list):])}
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to batch embed: {e}")
            chunk_embeds = {}
            kw_embeds = {}
            
        def _batched_match_fn(text: str, keywords: list) -> float:
            text_lower = text.lower()
            if not text_lower.strip() or not keywords:
                return 0.0
                
            matched = 0
            missing_kws = []
            for kw in keywords:
                if kw.lower().strip() in text_lower:
                    matched += 1
                else:
                    missing_kws.append(kw)
                    
            if not missing_kws:
                return 1.0
                
            # Use precomputed embeddings for semantic similarity of missing keywords
            chunks = section_chunks.get(text, [c.strip() for c in text.split('\n') if len(c.strip()) > 10])
            if not chunks and text.strip():
                chunks = [text.strip()]
                
            chunk_vec_list = [chunk_embeds[c] for c in chunks if c in chunk_embeds]
            kw_vec_list = [kw_embeds[kw] for kw in missing_kws if kw in kw_embeds]
            
            if chunk_vec_list and kw_vec_list:
                chunk_vecs = np.array(chunk_vec_list)
                chunk_norms = np.linalg.norm(chunk_vecs, axis=1)
                
                for kw_vec in kw_vec_list:
                    kw_vec = np.array(kw_vec)
                    kw_norm = np.linalg.norm(kw_vec)
                    dots = np.dot(chunk_vecs, kw_vec)
                    sims = dots / (chunk_norms * kw_norm + 1e-9)
                    if np.max(sims) > 0.5:
                        matched += 1
            return matched / len(keywords)

        keyword_match_res = section_weighted_score(sections, jd_keywords, _batched_match_fn)
        keyword_match_val = keyword_match_res["keyword_match_score"]
    else:
        # Check HARD_SKILLS found using strict word boundaries to avoid false positives (e.g. matching 'c' or 'go' inside other words)
        skills_list_lower = set(s.lower() for s in _get_skills_list(resume_json))
        resume_text_lower = full_resume_text.lower()
        
        hard_skills_found = 0
        for hs in HARD_SKILLS:
            escaped_hs = re.escape(hs)
            if hs.isalnum():
                pattern = re.compile(rf'\b{escaped_hs}\b')
            else:
                pattern = re.compile(rf'{escaped_hs}')
                
            if pattern.search(resume_text_lower) or hs in skills_list_lower:
                hard_skills_found += 1
                
        # Normalize: 20+ hard skills = 1.0 score; 0 = 0.0.
        hard_skill_density = min(hard_skills_found / 20.0, 1.0)
        keyword_match_val = hard_skill_density

    # --- 2. Quantified impact ---
    action_verb_hits = sum(1 for b in bullets if b.strip() and b.strip().split()[0].lower().rstrip(".,;:!") in STRONG_ACTION_VERBS)
    
    # Check metrics
    metric_pattern = re.compile(
        r'\d+\s*%'           # 30%
        r'|\$\s*[\d,]+'      # $50,000
        r'|\d+x\b'           # 3x
        r'|\d+\s*\+'         # 100+
        r'|\b\d+\s*users?\b' # 500 users
        r'|\b\d+\s*clients?\b'
        r'|\b\d+\s*projects?\b'
        r'|\b\d+\s*(?:ms|seconds?|minutes?|hours?)\b'
        r'|\b\d+\s*(?:GB|MB|TB|KB)\b'
        r'|\b(?:reduced|increased|improved|boosted|cut|grew|saved)\b.*\b\d+',
        re.IGNORECASE
    )
    metric_hits = sum(1 for b in bullets if metric_pattern.search(b))
    
    n_bullets = max(len(bullets), 1)
    action_verb_pct = action_verb_hits / n_bullets
    metric_pct = metric_hits / n_bullets
    
    # Industry standard: 70%+ action verbs and 40%+ metrics is considered perfect (100% score).
    # Anything below that scales down linearly.
    impact_verb_score = min(action_verb_pct / 0.70, 1.0)
    impact_metric_score = min(metric_pct / 0.40, 1.0)
    quantified_impact_val = float(impact_verb_score * 0.4 + impact_metric_score * 0.6)
    
    if action_verb_pct < 0.70:
        issues.append({
            "category": "content",
            "severity": "medium",
            "issue": f"Only {action_verb_hits}/{n_bullets} bullet points start with a strong action verb",
            "suggestion": "Start each bullet point with a powerful verb (Engineered, Designed, Optimized, Built, etc.).",
            "points_deducted": int((1 - impact_verb_score) * 10),
        })
    if metric_pct < 0.40:
        issues.append({
            "category": "content",
            "severity": "medium",
            "issue": f"Only {metric_hits}/{n_bullets} bullet points contain quantifiable metrics",
            "suggestion": "Add numbers, percentages, or measurable outcomes (e.g. 'Reduced load time by 40%', 'Processed 10K+ records').",
            "points_deducted": int((1 - impact_metric_score) * 20),
        })

    # --- 3. Formatting Parsability ---
    formatting_parsability_val = 1.0
    metadata = resume_json.get("formatting_metadata") or {}
    
    if metadata.get("is_scanned_pdf"):
        penalty = 0.30
        formatting_parsability_val -= penalty
        issues.append({
            "category": "formatting",
            "severity": "high",
            "issue": "Scanned or image-based PDF detected",
            "suggestion": "Recruiters and ATS parsers cannot read scanned resumes. Re-export your resume as a text-based PDF.",
            "points_deducted": int(penalty * 100),
        })
    if metadata.get("has_columns"):
        penalty = 0.15
        formatting_parsability_val -= penalty
        issues.append({
            "category": "formatting",
            "severity": "high",
            "issue": "Multi-column layout detected",
            "suggestion": "Multi-column layouts confuse standard ATS parsers because they read left-to-right across the page. Use a single-column layout.",
            "points_deducted": int(penalty * 100),
        })
    if metadata.get("has_tables"):
        penalty = 0.10
        formatting_parsability_val -= penalty
        issues.append({
            "category": "formatting",
            "severity": "medium",
            "issue": "Tables detected in resume layout",
            "suggestion": "ATS systems read left-to-right, jumbling table cell content together. Avoid tables entirely and list details sequentially.",
            "points_deducted": int(penalty * 100),
        })
        
    if full_resume_text:
        ligatures = {'\ufb00': 'ff', '\ufb01': 'fi', '\ufb02': 'fl', '\ufb03': 'ffi', '\ufb04': 'ffl'}
        found_ligatures = [r for l, r in ligatures.items() if l in full_resume_text]
        if found_ligatures:
            penalty = min(len(found_ligatures) * 0.08, 0.20)
            formatting_parsability_val -= penalty
            issues.append({
                "category": "formatting",
                "severity": "high",
                "issue": f"PDF contains ligature characters: {', '.join(found_ligatures)}",
                "suggestion": "These special characters break many ATS parsers. Re-export your PDF from a word processor with ligatures disabled.",
                "points_deducted": int(penalty * 100),
            })
            
        word_count = len(full_resume_text.split())
        if word_count < 150:
            penalty = 0.15
            formatting_parsability_val -= penalty
            issues.append({
                "category": "formatting",
                "severity": "high",
                "issue": f"Resume is very short ({word_count} words)",
                "suggestion": "A competitive resume should have 300-700 words. Add more detail to your experience and projects.",
                "points_deducted": int(penalty * 100),
            })
        elif word_count < 300:
            penalty = 0.08
            formatting_parsability_val -= penalty
            issues.append({
                "category": "formatting",
                "severity": "medium",
                "issue": f"Resume is somewhat short ({word_count} words)",
                "suggestion": "Consider adding more descriptive bullet points. Aim for 400-700 words.",
                "points_deducted": int(penalty * 100),
            })
        elif word_count > 1000:
            penalty = 0.10
            formatting_parsability_val -= penalty
            issues.append({
                "category": "formatting",
                "severity": "medium",
                "issue": f"Resume is very long ({word_count} words)",
                "suggestion": "Keep your resume concise. Aim for a single page (400-600 words) for entry-level roles.",
                "points_deducted": int(penalty * 100),
            })
            

    formatting_parsability_val = max(0.0, formatting_parsability_val)

    consistency_res = combined_consistency_score(bullets, full_resume_text, None)
    if consistency_res["score"] < 1.0:
        formatting_parsability_val -= (1.0 - consistency_res["score"])
        if consistency_res["date_format_check"]["penalty"] > 0:
            issues.append({
                "category": "formatting",
                "severity": "medium",
                "issue": "Mixed date formats detected",
                "suggestion": "Use a consistent date format (e.g. 'Jan 2023 - Present' or '01/2023 - Present') throughout.",
                "points_deducted": int(consistency_res["date_format_check"]["penalty"] * 100),
            })
        if consistency_res["bullet_check"]["penalty"] > 0:
            issues.append({
                "category": "formatting",
                "severity": "low",
                "issue": "Mixed bullet styles detected",
                "suggestion": "Use a single, standard bullet character (like '•' or '-') for all lists.",
                "points_deducted": int(consistency_res["bullet_check"]["penalty"] * 100),
            })


    # --- 4. Structure completeness ---
    contact = resume_json.get("contact", {})
    contact_score = 0.0
    if contact.get("name") and len(contact["name"].strip()) >= 2:
        contact_score += 0.25
    else:
        issues.append({
            "category": "contact",
            "severity": "high",
            "issue": "Missing or incomplete name in contact section",
            "suggestion": "Add your full professional name at the top of your resume.",
            "points_deducted": 20,
        })
        
    email = contact.get("email", "")
    if email and "@" in email and "." in email:
        contact_score += 0.25
    else:
        issues.append({
            "category": "contact",
            "severity": "high",
            "issue": "Missing or invalid email address",
            "suggestion": "Include a professional email address (e.g. yourname@gmail.com).",
            "points_deducted": 20,
        })
        
    phone = contact.get("phone", "")
    if phone and re.search(r'\d{7,}', re.sub(r'[\s\-\(\)\+]', '', phone)):
        contact_score += 0.25
    else:
        issues.append({
            "category": "contact",
            "severity": "medium",
            "issue": "Missing or invalid phone number",
            "suggestion": "Add a phone number with country code (e.g. +91-XXXXXXXXXX).",
            "points_deducted": 20,
        })
        
    # Check contact links — primary location is now contact.links array
    links_list = contact.get("links", [])
    has_url = bool(links_list and isinstance(links_list, list) and any(l for l in links_list if isinstance(l, str) and l.strip()))
    if not has_url:
        # Legacy flat field fallback (older parsed resumes)
        has_url = any(contact.get(k) for k in ["linkedin", "github", "portfolio", "website", "url"])
    if not has_url:
        has_url = any(isinstance(val, str) and ("linkedin.com" in val or "github.com" in val or "http" in val) for val in contact.values())
    if not has_url:
        # Fallback: scan contact values and top 400 characters of resume text for "linkedin" or "github" keywords
        contact_vals_lower = " ".join(str(val).lower() for val in contact.values())
        resume_header_lower = full_resume_text[:400].lower()
        if "linkedin" in contact_vals_lower or "github" in contact_vals_lower or "linkedin" in resume_header_lower or "github" in resume_header_lower:
            has_url = True
    if has_url:
        contact_score += 0.25
    else:
        issues.append({
            "category": "contact",
            "severity": "low",
            "issue": "No LinkedIn, GitHub, or portfolio link found",
            "suggestion": "Add a LinkedIn profile or GitHub URL to showcase your work.",
            "points_deducted": 20,
        })
        
    sections_present_score = 0.0
    summary = resume_json.get("summary", "")
    if summary:
        word_count = len(summary.split())
        if 15 <= word_count <= 80:
            sections_present_score += 0.25
        else:
            sections_present_score += 0.15
            issues.append({
                "category": "completeness",
                "severity": "low",
                "issue": f"Professional summary length ({word_count} words) is sub-optimal",
                "suggestion": "Aim for a concise 20-50 words summary of your experience and core skills.",
                "points_deducted": 10,
            })
    else:
        issues.append({
            "category": "completeness",
            "severity": "high",
            "issue": "Missing professional summary / objective section",
            "suggestion": "Add a 2-3 sentence summary highlighting your core skills, experience level, and career focus.",
            "points_deducted": 25,
        })
        
    education = resume_json.get("education", [])
    if education and len(education) >= 1:
        if any(e.get("institution") and (e.get("degree") or e.get("field")) for e in education):
            sections_present_score += 0.25
        else:
            sections_present_score += 0.10
            issues.append({
                "category": "completeness",
                "severity": "medium",
                "issue": "Education section is incomplete — missing institution or degree",
                "suggestion": "Include institution name, degree type, and graduation date.",
                "points_deducted": 15,
            })
    else:
        issues.append({
            "category": "completeness",
            "severity": "high",
            "issue": "Missing education section",
            "suggestion": "Add your education with institution, degree, field of study, and graduation date.",
            "points_deducted": 25,
        })
        
    experience = resume_json.get("experience", [])
    projects = resume_json.get("projects", [])
    if len(experience) >= 2:
        sections_present_score += 0.25
    elif len(experience) >= 1 or len(projects) >= 2:
        sections_present_score += 0.20
        if not experience:
            issues.append({
                "category": "completeness",
                "severity": "low",
                "issue": "No formal work experience section — using projects as experience",
                "suggestion": "If you have internships or freelance work, list them under 'Experience' to strengthen ATS parsing.",
                "points_deducted": 5,
            })
    else:
        issues.append({
            "category": "completeness",
            "severity": "high",
            "issue": "No experience or projects section found",
            "suggestion": "Add work experience, internships, or academic projects.",
            "points_deducted": 25,
        })
        
    skills = _get_skills_list(resume_json)
    if len(skills) >= 8:
        sections_present_score += 0.25
    else:
        issues.append({
            "category": "completeness",
            "severity": "high",
            "issue": "No skills section found or has very few skills",
            "suggestion": "Add a skills section with your technical competencies.",
            "points_deducted": 25,
        })
        

    structure_completeness_val = float(contact_score * 0.4 + sections_present_score * 0.6)

    unnecessary_res = check_unnecessary_sections(full_resume_text, list(sections.keys()))
    if unnecessary_res["penalty"] > 0:
        structure_completeness_val -= unnecessary_res["penalty"]
        issues.append({
            "category": "completeness",
            "severity": "medium",
            "issue": f"Unnecessary sections detected: {', '.join(unnecessary_res['flagged_sections'])}",
            "suggestion": "Remove outdated or low-value sections like 'Objective', 'References', or 'Hobbies'.",
            "points_deducted": int(unnecessary_res["penalty"] * 100),
        })


    # --- 5. Content Quality ---
    content_quality_val = 1.0
    weak_phrase_count = 0
    buzzword_count = 0
    length_issues = 0
    
    for block in _get_all_text_blocks(resume_json):
        # Weak phrases
        for phrase in WEAK_PHRASES:
            if phrase in block.lower():
                weak_phrase_count += 1
                if weak_phrase_count <= 2:
                    issues.append({
                        "category": "content",
                        "severity": "medium",
                        "issue": f"Weak phrasing detected: '{phrase}' in '{block[:60]}...'",
                        "suggestion": f"Replace '{phrase}' with a strong action verb like 'Developed', 'Engineered', or 'Optimized'.",
                        "points_deducted": 5,
                    })
                break
                
        # Buzzwords
        for buzz in BUZZWORDS:
            if buzz in block.lower():
                buzzword_count += 1
                if buzzword_count <= 2:
                    issues.append({
                        "category": "content",
                        "severity": "low",
                        "issue": f"Cliche/buzzword detected: '{buzz}'",
                        "suggestion": f"Remove '{buzz}' and replace with a specific, evidence-backed achievement.",
                        "points_deducted": 3,
                    })
                break
                
        word_count = len(block.split())
        if word_count < 8 or word_count > 40:
            length_issues += 1
            
    content_quality_val -= min(weak_phrase_count * 0.05, 0.20)
    content_quality_val -= min(buzzword_count * 0.03, 0.10)
    
    n_blocks = max(len(_get_all_text_blocks(resume_json)), 1)
    content_quality_val -= min((length_issues / n_blocks) * 0.10, 0.20)
    content_quality_val = max(0.0, content_quality_val)

    # --- 6. Authenticity (Stuffing checker) ---
    authenticity_res = combined_stuffing_score(bullets, full_resume_text, jd_keywords)
    authenticity_val = authenticity_res["score"]
    
    stuffed_kws = authenticity_res["density_check"]["stuffed_keywords"]
    if stuffed_kws:
        issues.append({
            "category": "content",
            "severity": "high",
            "issue": f"Keyword stuffing detected: {', '.join(stuffed_kws.keys())}",
            "suggestion": "Avoid repeating keywords excessively. Let them flow naturally in descriptions.",
            "points_deducted": int(authenticity_res["density_check"]["density_penalty"] * 100),
        })
    flagged_bullets = authenticity_res["bullet_check"]["flagged_bullets"]
    if flagged_bullets:
        issues.append({
            "category": "content",
            "severity": "high",
            "issue": f"Detected {len(flagged_bullets)} low-substance comma list bullets",
            "suggestion": "Rewrite lists of tools/skills into action-oriented accomplishment sentences.",
            "points_deducted": int(authenticity_res["bullet_check"]["stuffing_penalty"] * 100),
        })

    # --- 7. Growth signals ---
    growth_signals_res = check_leadership_signals(full_resume_text)
    growth_signals_val = growth_signals_res["score"]
    
    if growth_signals_val < 0.4:
        issues.append({
            "category": "content",
            "severity": "low",
            "issue": "Few leadership or teamwork signal words found",
            "suggestion": "Incorporate active collaboration and initiative verbs (e.g. led, spearheaded, collaborated, presented).",
            "points_deducted": 5,
        })

    # --- 8. Style ---
    style_res = check_style(full_resume_text, bullets)
    style_val = style_res["score"]
    
    if style_res["filler_word_hits"] > 3:
        issues.append({
            "category": "content",
            "severity": "low",
            "issue": f"Filler words detected ({style_res['filler_word_hits']} instances)",
            "suggestion": "Remove weak fillers like 'very', 'just', 'actually', or 'in order to' for conciseness.",
            "points_deducted": 5,
        })
    if style_res["personal_pronoun_hits"] > 0:
        issues.append({
            "category": "content",
            "severity": "medium",
            "issue": f"First-person pronouns detected ({style_res['personal_pronoun_hits']} instances)",
            "suggestion": "Resume bullets should start with action verbs. Avoid using 'I', 'me', 'my', or 'myself'.",
            "points_deducted": 10,
        })
    # --- 9. Readability ---
    readability_res = check_readability(full_resume_text)
    readability_val = readability_res["score"]
    
    # Floor: resume with actual content should never score 0%
    if full_resume_text.strip() and len(full_resume_text.split()) > 20:
        readability_val = max(0.3, readability_val)

    if readability_val < 0.7 and readability_res["details"].get("flesch_reading_ease", 50) < 40:
        issues.append({
            "category": "content",
            "severity": "medium",
            "issue": "Text readability is very low (dense/jargon-heavy)",
            "suggestion": "Break up dense paragraphs and simplify complex jargon. Target a 'Standard' reading ease.",
            "points_deducted": int((1.0 - readability_val) * 15),
        })
        
    # --- 10. Repetition ---
    repetition_res = combined_repetition_score(bullets)
    repetition_val = repetition_res["score"]
    if repetition_res["duplicate_check"]["penalty"] > 0:
        issues.append({
            "category": "content",
            "severity": "high",
            "issue": "Duplicate or near-identical bullet points found",
            "suggestion": "Tailor each bullet point to its specific role/project. Avoid copy-pasting.",
            "points_deducted": int(repetition_res["duplicate_check"]["penalty"] * 100),
        })
    if repetition_res["opener_check"]["penalty"] > 0:
        issues.append({
            "category": "content",
            "severity": "medium",
            "issue": f"Repetitive bullet opener: '{repetition_res['opener_check']['dominant_opener']}'",
            "suggestion": "Vary your action verbs. Avoid starting multiple bullets with the same phrase.",
            "points_deducted": int(repetition_res["opener_check"]["penalty"] * 100),
        })

    # ── Phase 2: Additional premium checks ──────────────────────────────────────

    # A. Email professionalism check
    contact_email = (resume_json.get("contact") or {}).get("email", "") or ""
    if contact_email and UNPROFESSIONAL_EMAIL_PATTERNS.search(contact_email.split("@")[0]):
        issues.append({
            "category": "contact",
            "severity": "medium",
            "issue": f"Unprofessional email address detected: '{contact_email}'",
            "suggestion": "Use a professional email like firstname.lastname@gmail.com",
            "points_deducted": 10,
        })
        contact_score = max(0.0, contact_score - 0.10)

    # B. Certifications section bonus
    # B. Hybrid AI & Text Certifications detection (check anywhere in structured details)
    certs_list = resume_json.get("certifications", [])
    cert_texts_combined = ""
    if isinstance(certs_list, list) and certs_list:
        cert_texts_combined = " ".join(
            (c if isinstance(c, str) else c.get("name", "")) for c in certs_list
        ).lower()
    elif isinstance(certs_list, str):
        cert_texts_combined = certs_list.lower()
        
    # Hybrid AI fallback: scan education, summary, and skills list for certification keywords
    skills_text = " ".join(_get_skills_list(resume_json))
    edu_text = " ".join(
        ((e.get("degree") or "") + " " + (e.get("field") or ""))
        for e in resume_json.get("education", []) if isinstance(e, dict)
    )
    all_possible_cert_sources = (cert_texts_combined + " " + skills_text + " " + edu_text + " " + full_resume_text).lower()
    
    # Check if we have extracted certifications in JSON, OR if any keyword matches
    has_certifications = False
    found_certs = []
    if isinstance(certs_list, list) and len(certs_list) > 0:
        has_certifications = True
        found_certs = [c if isinstance(c, str) else c.get("name", str(c)) for c in certs_list]
    elif isinstance(certs_list, str) and len(certs_list.strip()) > 5:
        has_certifications = True
        found_certs = [certs_list.strip()]
        
    if not has_certifications:
        found_certs = [ck for ck in CERTIFICATION_KEYWORDS if ck in all_possible_cert_sources]
        has_certifications = len(found_certs) > 0

    cert_bonus = 0.0
    if has_certifications:
        cert_bonus = 0.08
        issues.insert(0, {
            "category": "completeness",
            "severity": "low",
            "issue": f"✅ Recognized certification detected: {', '.join(found_certs[:3])}",
            "suggestion": "Great job listing certifications; they significantly boost technical recruiter visibility.",
            "points_deducted": -8,
        })
    
    # C. Hard skills vs. soft skills breakdown
    all_resume_skills = set(s.lower() for s in _get_skills_list(resume_json))
    hard_skills_in_resume = all_resume_skills & {hs.lower() for hs in HARD_SKILLS}
    soft_skills_in_resume = all_resume_skills & SOFT_SKILLS
    
    hard_skill_count = len(hard_skills_in_resume)
    soft_skill_count = len(soft_skills_in_resume)
    
    if hard_skill_count == 0 and len(all_resume_skills) > 0:
        issues.append({
            "category": "completeness",
            "severity": "high",
            "issue": "No recognizable hard/technical skills found in skills section",
            "suggestion": "List concrete technical tools (e.g. Python, React, SQL, Docker) rather than only soft skills.",
            "points_deducted": 15,
        })
        structure_completeness_val = max(0.0, structure_completeness_val - 0.15)

    # D. Keyword in-context scoring bonus
    exp_text_lower = sections.get("experience", "").lower()
    skills_used_in_context = sum(1 for s in hard_skills_in_resume if s in exp_text_lower)
    context_bonus = 0.0
    if hard_skill_count > 0:
        context_ratio = skills_used_in_context / max(hard_skill_count, 1)
        context_bonus = context_ratio * 0.05  # Up to 5% bonus

    # E. Volunteer/Awards section bonus
    volunteer_keywords = ["volunteer", "volunteering", "award", "awards", "honor", "honours",
                          "recognition", "achievement", "scholarship", "fellowship"]
    has_volunteer_awards = any(kw in full_resume_text.lower() for kw in volunteer_keywords)
    volunteer_bonus = 0.03 if has_volunteer_awards else 0.0

    # F. Strict 1-Page and Word Count Density / Empty Space Checks
    word_count_total = len(full_resume_text.split()) if full_resume_text else 0
    years_exp = _calculate_years_experience(resume_json)
    
    # 1. Physical Page Count check (using exact PDF layout measurements)
    try:
        from services.pdf_fitter import _build_html, _get_page_count
        html_layout = _build_html(resume_json, font_size_pt=10.0, line_height=1.2)
        actual_pages = _get_page_count(html_layout)
        
        # If it spills over, check if a tight layout (9.5pt, 1.05 line height) fits on fewer pages
        if actual_pages > 1:
            html_layout_tight = _build_html(resume_json, font_size_pt=9.5, line_height=1.05)
            tight_pages = _get_page_count(html_layout_tight)
            if tight_pages < actual_pages:
                actual_pages = tight_pages
    except Exception as e:
        actual_pages = 1  # Fallback if PDF engine fails during ATS scoring
        
    if actual_pages == 2:
        issues.append({
            "category": "formatting",
            "severity": "high",
            "issue": f"Resume spills onto a second page",
            "suggestion": "Keep your resume strictly to 1 page unless you have 10+ years of experience. Trim redundant bullets.",
            "points_deducted": 25,
        })
        formatting_parsability_val = max(0.0, formatting_parsability_val - 0.25)
    elif actual_pages >= 3:
        issues.append({
            "category": "formatting",
            "severity": "high",
            "issue": f"Resume is excessively long ({actual_pages} pages)",
            "suggestion": "No resume should exceed 2 pages. Condense your descriptions and focus on recent achievements.",
            "points_deducted": 45,
        })
        formatting_parsability_val = max(0.0, formatting_parsability_val - 0.45)
        
    # 2. Empty Space Check (Too sparse = negative layout rating)
    # If the candidate has few words (< 200 words) but listed multiple sections, it indicates a very sparse page layout.
    if word_count_total < 220:
        issues.append({
            "category": "formatting",
            "severity": "high",
            "issue": "Excessive empty/blank space detected on resume",
            "suggestion": "Your resume is too thin. Fill the white space by detailing project technologies and adding professional summary bullets.",
            "points_deducted": 12,
        })
        formatting_parsability_val = max(0.0, formatting_parsability_val - 0.12)

    # G. Section ordering check
    raw_lower = full_resume_text.lower()
    section_positions = {}
    for sec in EXPECTED_SECTION_ORDER:
        # Find approximate position of section heading
        pattern = re.compile(rf'\b{re.escape(sec)}\b', re.IGNORECASE)
        m = pattern.search(raw_lower)
        if m:
            section_positions[sec] = m.start()
    
    ordered_sections = sorted(section_positions.items(), key=lambda x: x[1])
    actual_order = [s for s, _ in ordered_sections]
    
    # Check if experience comes before education (most important ordering rule)
    if "experience" in actual_order and "education" in actual_order:
        if actual_order.index("education") < actual_order.index("experience"):
            issues.append({
                "category": "formatting",
                "severity": "low",
                "issue": "Education section appears before Work Experience",
                "suggestion": "For candidates with work experience, list Work Experience before Education. This prioritizes your professional background.",
                "points_deducted": 5,
            })
            formatting_parsability_val = max(0.0, formatting_parsability_val - 0.05)

    # H. De-default authenticity and repetition (start neutral, reward good writing)
    # Instead of starting at 1.0 (free points), start at 0.5 and reward cleanliness
    authenticity_val = 0.5 + (authenticity_val * 0.5)   # 0.5 baseline, max 1.0
    repetition_val = 0.5 + (repetition_val * 0.5)       # 0.5 baseline, max 1.0

    # Apply bonuses to structure completeness
    structure_completeness_val = min(1.0, structure_completeness_val + cert_bonus + volunteer_bonus)

    # Apply context bonus to keyword match
    if is_targeted:
        keyword_match_val = min(1.0, keyword_match_val + context_bonus)

    # Calculate separate components for the user's weights sheet
    experience_quality_val = 1.0
    if not experience:
        experience_quality_val = 0.0
    
    # Calculate education completeness
    education_completeness_val = 1.0
    if not education:
        education_completeness_val = 0.0
    elif not any(e.get("institution") for e in education if isinstance(e, dict)):
        education_completeness_val = 0.5

    # Contact completeness score (normalize contact_score)
    contact_completeness_val = contact_score

    # Assemble content quality from checks (blend of quality + readability + repetition)
    content_quality_val = (content_quality_val * 0.4) + (readability_val * 0.3) + (repetition_val * 0.3)

    # ─────────────────────────────────────────────────────────────────────────
    # Assemble all check values matching WEIGHTS / BASELINE_WEIGHTS exactly
    is_baseline = not is_targeted
    
    if is_baseline:
        hard_skill_density_val = keyword_match_val
        checks = {
            "quantified_impact": quantified_impact_val,
            "content_quality": content_quality_val,
            "formatting_parsability": formatting_parsability_val,
            "experience_quality": experience_quality_val,
            "hard_skill_density": hard_skill_density_val,
            "section_completeness": sections_present_score,
            "growth_signals": growth_signals_val,
            "education_completeness": education_completeness_val,
            "contact_completeness": contact_completeness_val,
            "style": style_val,
        }
    else:
        checks = {
            "quantified_impact": quantified_impact_val,
            "content_quality": content_quality_val,
            "formatting_parsability": formatting_parsability_val,
            "experience_quality": experience_quality_val,
            "keyword_match": keyword_match_val,
            "section_completeness": sections_present_score,
            "growth_signals": growth_signals_val,
            "education_completeness": education_completeness_val,
            "contact_completeness": contact_completeness_val,
            "style": style_val,
        }


    # --- Red flag checks ---
    experience_list = resume_json.get("experience", [])
    experience_list = experience_list if isinstance(experience_list, list) else []
    
    titles = [exp.get("title", "") for exp in experience_list if isinstance(exp, dict)]
    total_years = _calculate_years_experience(resume_json)
    seniority_res = check_seniority_mismatch(titles, total_years)
    
    date_ranges = []
    for exp in experience_list:
        if isinstance(exp, dict):
            start = exp.get("start_date") or exp.get("startDate") or ""
            end = exp.get("end_date") or exp.get("endDate") or "Present"
            if start:
                date_ranges.append(f"{start} - {end}")
            
    gaps_res = check_date_gaps(date_ranges)
    
    redflags = {
        "seniority": seniority_res,
        "gaps": gaps_res,
    }
    
    if seniority_res["seniority_mismatch"]:
        issues.append({
            "category": "redflag",
            "severity": "high",
            "issue": "Senior title mismatch against experience",
            "suggestion": "You have listed a Lead/Senior title but have less than 2 years of work experience.",
            "points_deducted": 30,
        })
    if gaps_res["gaps_found"] > 0:
        issues.append({
            "category": "redflag",
            "severity": "medium",
            "issue": f"Found {gaps_res['gaps_found']} employment gap(s) over 6 months",
            "suggestion": "Be prepared to explain gaps in dates during interviews, or fill them with freelance/education details.",
            "points_deducted": int(gaps_res["penalty"] * 100),
        })

    # Run the new scorer engine (with correct weights for baseline vs targeted)
    if is_baseline:
        from ats_engine.scorer.score_engine_v2 import BASELINE_WEIGHTS
        score_res = calculate_ats_score(checks, redflags, debug=True, weights_override=BASELINE_WEIGHTS)
    else:
        score_res = calculate_ats_score(checks, redflags, debug=True)
    overall_score = score_res["overall_score"]
    
    # ─── Resume Worded Calibrated Dampeners ─────────────────────────
    # If a resume fails critical quality standards, apply multipliers to prevent
    # high formatting/template scores from inflating a low-content document.
    
    # 1. Metric-less penalty (no metrics is a severe human reviewer red flag)
    if metric_pct == 0.0:
        overall_score = overall_score * 0.75  # 25% reduction
        
    # 2. Bloated or very thin resume check
    if word_count_total < 300:
        overall_score = overall_score * 0.85  # 15% reduction
        
    # 3. Missing critical sections (Education only — Summary already penalized via issues list -25pts)
    missing_critical = 0
    if not education:
        missing_critical += 1
    if missing_critical >= 2:
        overall_score = overall_score * 0.80
    elif missing_critical >= 1:
        overall_score = overall_score * 0.90
        
    overall_score = max(0.0, min(100.0, overall_score))
    overall_score = round(overall_score, 1)
    
    # Sort issues by severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda x: severity_order.get(x["severity"], 3))
    
    # Generate summary
    high_count = sum(1 for i in issues if i["severity"] == "high")
    if overall_score >= 85:
        summary = "Excellent ATS compatibility. Your resume is well-structured and ready for most applicant tracking systems."
    elif overall_score >= 70:
        summary = f"Good ATS compatibility with {high_count} high-priority issues to address."
    elif overall_score >= 50:
        summary = f"Moderate ATS compatibility. Found {high_count} critical issues that are likely reducing your visibility to recruiters."
    else:
        summary = f"Low ATS compatibility. {high_count} critical issues need immediate attention before submitting to job applications."
        
    return {
        "baseline_score": int(overall_score),
        "match_score": int(overall_score),
        "score_breakdown": {
            "contact_completeness": int(contact_score * 100),
            "section_completeness": int(sections_present_score * 100),
            "quantified_impact": int(quantified_impact_val * 100),
            "growth_signals": int(growth_signals_val * 100),
            "content_quality": int(content_quality_val * 100),
            "formatting_compatibility": int(formatting_parsability_val * 100),
            "keyword_match": int(keyword_match_val * 100),
            "readability": int(readability_val * 100),
            "style": int(style_val * 100),
        },
        "premium_breakdown": {
            "hard_skills_found": hard_skill_count,
            "soft_skills_found": soft_skill_count,
            "skills_used_in_context": skills_used_in_context,
            "has_certifications": has_certifications,
            "cert_bonus_pts": int(cert_bonus * 100),
            "has_volunteer_or_awards": has_volunteer_awards,
            "estimated_word_count": word_count_total,
            "years_experience": round(years_exp, 1),
            "section_order": actual_order,
        },
        "formatting_health": {
            "single_column": not metadata.get("has_columns", False),
            "no_tables": not metadata.get("has_tables", False),
            "text_based_pdf": not metadata.get("is_scanned_pdf", False),
            "no_ligatures": not any(l in (full_resume_text or "") for l in ['\ufb00', '\ufb01', '\ufb02', '\ufb03', '\ufb04']),
            "standard_length": 300 <= word_count_total <= 800,
            "single_page": actual_pages == 1,
            "consistent_dates": consistency_res["date_format_check"]["penalty"] == 0 if consistency_res else True,
            "consistent_bullets": consistency_res["bullet_check"]["penalty"] == 0 if consistency_res else True,
            "no_excessive_whitespace": word_count_total >= 220,
            "experience_before_education": not (
                "experience" in actual_order and "education" in actual_order
                and actual_order.index("education") < actual_order.index("experience")
            ),
        },
        "keyword_details": [
            {
                "keyword": kw,
                "status": "matched" if (
                    kw.lower() in sections.get("skills", "").lower()
                    or kw.lower() in sections.get("experience", "").lower()
                    or kw.lower() in sections.get("projects", "").lower()
                ) else "missing",
                "found_in_sections": [
                    sec for sec in ["skills", "experience", "projects", "summary", "education"]
                    if kw.lower() in sections.get(sec, "").lower()
                ],
                "frequency": sum(
                    sections.get(sec, "").lower().count(kw.lower())
                    for sec in sections
                ),
            }
            for kw in jd_keywords
        ],
        "missing_keywords": [k for k in jd_keywords if k not in sections["skills"] and k not in sections["experience"] and k not in sections["projects"]],
        "matched_keywords": [k for k in jd_keywords if k in sections["skills"] or k in sections["experience"] or k in sections["projects"]],
        "bullet_rewrites": [],
        "bullet_annotations": (lambda: __import__('services.bullet_annotator', fromlist=['annotate_all_bullets']).annotate_all_bullets(resume_json, jd_keywords))(),
        "issues": [i for i in issues if i.get("points_deducted", 0) > 0],  # filter out bonus markers
        "issues_with_bonuses": issues,
        "summary": summary,
        "debug_breakdown": score_res["breakdown"],
    }
