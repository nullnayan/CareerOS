"""
Resume Parser agent.

Job: take raw resume text (however messy) and turn it into clean,
structured JSON: skills, experience, education, projects.

This is deliberately a SMALL file that does ONE thing — see the
Architecture doc's "one agent, one job" principle. It doesn't touch the
database, doesn't handle file uploads — those are separate concerns,
handled in api/resumes.py.
"""

import json
import re
import logging
from agents.llm_client import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert resume parsing engine with zero data-loss tolerance.
You will be given the raw text of a resume, which may have messy formatting from PDF/DOCX extraction.

EXTRACT EVERY SINGLE PIECE OF INFORMATION into the EXACT JSON schema below.
Return ONLY valid JSON, nothing else — no markdown fences (```json), no explanation text, just raw JSON.

{
  "contact": {
    "name": "Full name exactly as written, or null",
    "email": "Email address or null",
    "phone": "Phone number with country code or null",
    "location": "City, State or null",
    "links": ["ARRAY of every URL/link found — include LinkedIn, GitHub, portfolio, website, LeetCode etc. e.g. ['https://linkedin.com/in/...', 'https://github.com/...']. If no URLs found, use []"]
  },
  "skills": ["FLAT array of INDIVIDUAL skill names. Do NOT include category labels like 'Languages:'. Split comma-separated lists into individual items."],
  "experience": [
    {
      "company": "Exact company/employer name",
      "title": "Exact job title",
      "start_date": "e.g. Jan 2023 or null",
      "end_date": "e.g. Dec 2024 or 'Present' if current, or null",
      "bullet_points": ["EVERY bullet point for this role verbatim. Do NOT summarize. Do NOT collapse into one string. If bullets use •, -, *, or similar, strip the marker and include the text."]
    }
  ],
  "education": [
    {
      "institution": "Exact institution name",
      "degree": "Degree/qualification type e.g. B.Tech, B.S., M.S., Ph.D., Intermediate, High School, or null — do NOT include field name here",
      "field": "Field of study or Board name e.g. Computer Science, ICSE Board, CBSE Board, or null",
      "graduation_date": "Graduation year or month+year or null",
      "cgpa_or_percentage": "Copy the CGPA, GPA, or percentage string EXACTLY as it appears — preserve the original word order, labels, colons. If 'CGPA: 7.25' return 'CGPA: 7.25'. If '8.5 CGPA' return '8.5 CGPA'. Use null only if truly absent.",
      "original_line": "The full original line verbatim (e.g. 'Intermediate / +2 (ICSE Board)') containing the degree and field, so the exact punctuation and format can be preserved."
    }
  ],
  "projects": [
    {
      "name": "Exact project name",
      "bullets": ["EVERY bullet point / description line for this project. If there is only a description paragraph, split it at sentence boundaries into separate bullets. Do NOT ever return a single string here — always return an array."],
      "technologies": ["Every technology, library, language, or tool mentioned for this project"]
    }
  ],
  "certifications": ["List EVERY certification, online course, or award. IMPORTANT: If a certification has a description on the next line (e.g. 'Learned threat detection...'), you MUST include it in the same string separated by a dash. (Example: 'Google Cybersecurity Course - Learned threat detection...'). Do NOT use bolding or markdown. Do NOT include any skills from the Skills section (e.g. 'Cybersecurity Fundamentals'). Use [] only if absolutely none exist."],
  "summary": "Professional summary or objective statement verbatim, or null if not present",
  "original_section_headings": {
    "education": "Exact heading text used for Education (e.g. 'EDUCATION', 'Education Details', or null)",
    "experience": "Exact heading text used for Experience",
    "projects": "Exact heading text used for Projects",
    "skills": "Exact heading text used for Skills",
    "certifications": "Exact heading text used for Certifications (e.g. 'Certifications & Courses')"
  }
}

CRITICAL RULES — violating any of these causes data loss and is UNACCEPTABLE:
1. contact.links MUST be an array containing ALL URLs found anywhere in the resume header or contact area.
2. education.cgpa_or_percentage MUST be extracted if ANY grade/score appears anywhere near education entries.
3. projects[*].bullets MUST be an array, never a string. Split descriptions at '. ' or bullet markers.
4. experience[*].bullet_points MUST capture EVERY bullet for each role — do not summarize or drop any.
5. certifications MUST include any course completion, certification, or award found ANYWHERE in the resume.
6. Never invent information that isn't in the text. Only extract what is actually written.
7. If the resume has no formal work experience (only projects/internships), return experience as []."""


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences that some LLMs add despite instructions."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence line
        text = re.sub(r'^```[a-zA-Z]*\n?', '', text)
        # Remove closing fence
        text = re.sub(r'\n?```\s*$', '', text)
    return text.strip()


def _normalize_contact_links(contact: dict, raw_text: str) -> dict:
    """
    Ensure contact.links is always a proper list and capture any URLs that
    the model may have placed in flat fields (contact.linkedin, contact.github, etc.)
    or that appear in the raw text but weren't extracted.
    """
    # Collect links from wherever the model may have put them
    links = list(contact.get("links") or [])
    
    # Absorb flat alias fields that some models emit
    for alias in ["linkedin", "github", "portfolio", "website", "url"]:
        val = contact.pop(alias, None)  # remove the flat field
        if val and isinstance(val, str) and val.strip() and val.lower() not in ("null", "none"):
            if val not in links:
                links.append(val.strip())
    
    # Also scan raw text for URLs not captured by the model
    url_pattern = re.compile(
        r'https?://[^\s,;\)\]>"]+|'
        r'(?:linkedin\.com|github\.com|gitlab\.com|portfolio\.)[^\s,;\)\]>"]+',
        re.IGNORECASE
    )
    for match in url_pattern.finditer(raw_text[:1000]):  # Only scan header
        url = match.group(0).strip('.,;)\'"')
        if url not in links:
            links.append(url)
    
    contact["links"] = links
    return contact


def _normalize_project_bullets(projects: list) -> list:
    """
    Ensure every project has a 'bullets' array, never a bare string 'description'.
    If description is a string, convert it to bullets by splitting on sentences.
    """
    normalized = []
    for proj in projects:
        if not isinstance(proj, dict):
            continue
        bullets = proj.get("bullets", [])
        description = proj.get("description", "")
        
        # If bullets is a string (model misbehaved), convert to list
        if isinstance(bullets, str) and bullets.strip():
            bullets = [b.strip() for b in re.split(r'[•\-\*]|(?<=\.)\s+', bullets) if b.strip() and len(b.strip()) > 5]
        
        # If bullets is empty but description has content, convert description
        if not bullets and description and isinstance(description, str):
            # Split by sentence boundaries or bullet markers
            raw_bullets = re.split(r'(?<=[.!])\s+|[•\-\*]\s*', description)
            bullets = [b.strip() for b in raw_bullets if b.strip() and len(b.strip()) > 5]
            if not bullets:
                bullets = [description.strip()]
        
        proj["bullets"] = bullets if isinstance(bullets, list) else []
        # Keep description for backwards compat but make bullets authoritative
        normalized.append(proj)
    return normalized


def _normalize_experience_bullets(experience: list) -> list:
    """Ensure every experience entry has a bullet_points array, never a bare string."""
    normalized = []
    for exp in experience:
        if not isinstance(exp, dict):
            continue
        bps = exp.get("bullet_points", [])
        description = exp.get("description", "")
        
        if isinstance(bps, str) and bps.strip():
            bps = [b.strip() for b in re.split(r'[•\-\*]|(?<=\.)\s+', bps) if b.strip() and len(b.strip()) > 5]
        
        if not bps and description and isinstance(description, str):
            raw_bps = re.split(r'(?<=[.!])\s+|[•\-\*]\s*', description)
            bps = [b.strip() for b in raw_bps if b.strip() and len(b.strip()) > 5]
            if not bps:
                bps = [description.strip()]
        
        exp["bullet_points"] = bps if isinstance(bps, list) else []
        normalized.append(exp)
    return normalized


def validate_phase1_extraction(original_text: str, extracted: dict) -> list[str]:
    warnings = []
    
    # Check bullets weren't collapsed
    for i, project in enumerate(extracted.get("projects", [])):
        bullets = project.get("bullets", [])
        if isinstance(bullets, str):
            warnings.append(f"Project {i} 'bullets' is a string, not a list — data likely lost")
        elif len(bullets) < 1:
            warnings.append(f"Project {i} '{project.get('name')}' has 0 bullets — verify against original")
    
    # Check certifications exist if original text mentions them
    cert_keywords = ["certif", "course completion", "udemy", "coursera", "edx", "nptel", "aws certified"]
    if any(kw in original_text.lower() for kw in cert_keywords) and not extracted.get("certifications"):
        warnings.append("Original mentions certifications but none were extracted")
    
    # Check CGPA/percentage exists if original mentions it
    if ("cgpa" in original_text.lower() or "gpa" in original_text.lower() or 
        re.search(r'\d+\.\d+\s*/\s*\d+|\d+%', original_text)) and not any(
        e.get("cgpa_or_percentage") for e in extracted.get("education", [])
    ):
        warnings.append("Original appears to contain CGPA/percentage but none extracted")
    
    # Check links
    link_patterns = ["linkedin", "github", "gitlab", "portfolio", "http"]
    if any(p in original_text.lower() for p in link_patterns):
        all_links = extracted.get("contact", {}).get("links", [])
        if not all_links:
            warnings.append("Original mentions profile links but none extracted into contact.links")
    
    # Check experience bullets weren't lost
    for i, exp in enumerate(extracted.get("experience", [])):
        bps = exp.get("bullet_points", [])
        if len(bps) < 1:
            warnings.append(f"Experience {i} '{exp.get('company')}' has 0 bullet points")
    
    return warnings


def parse_resume(raw_text: str) -> dict:
    """
    raw_text: plain text extracted from the uploaded resume file.
    Returns: a Python dict matching the schema above, ready to save
    directly into resume_versions.structured_json.
    """
    client = LLMClient(agent_name="resume_parser")

    response_text = client.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=raw_text,
        json_mode=True,
    )
    
    # Strip any accidental markdown fences
    response_text = _strip_json_fences(response_text)

    try:
        extracted = json.loads(response_text)
    except json.JSONDecodeError:
        # Try to find a JSON object in the response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            extracted = json.loads(json_match.group(0))
        else:
            raise ValueError(
                f"Resume Parser didn't return valid JSON. "
                f"Raw response was: {response_text[:500]}"
            )

    # ── Post-processing normalizations to recover any data the model may have misplaced ──
    
    # 1. Normalize contact section (absorb flat linkedin/github fields, extract URLs from raw text)
    if "contact" in extracted and isinstance(extracted["contact"], dict):
        extracted["contact"] = _normalize_contact_links(extracted["contact"], raw_text)
    
    # 2. Normalize project bullets (convert string descriptions to arrays)
    if "projects" in extracted and isinstance(extracted["projects"], list):
        extracted["projects"] = _normalize_project_bullets(extracted["projects"])
    
    # 3. Normalize experience bullets
    if "experience" in extracted and isinstance(extracted["experience"], list):
        extracted["experience"] = _normalize_experience_bullets(extracted["experience"])
    
    # 4. Ensure certifications is always a list
    certs = extracted.get("certifications", [])
    if isinstance(certs, str):
        extracted["certifications"] = [c.strip() for c in certs.split(",") if c.strip()]
    elif not isinstance(certs, list):
        extracted["certifications"] = []
    
    # 5. Scan raw text for certifications missed by model (bounded to last 2000 chars where certs usually appear)
    cert_scan_text = raw_text[-2000:] if len(raw_text) > 2000 else raw_text
    cert_scan_patterns = [
        r'(?:certified?|certification)\b\s+(?:in\s+)?([A-Za-z][\w ]{3,50})(?:\n|,|;|$)',
        r'([A-Za-z][\w ]{3,50})\s+(?:certificate|certification|course)\b',
    ]
    existing_cert_text = " ".join(extracted.get("certifications", [])).lower()
    for pat in cert_scan_patterns:
        for m in re.finditer(pat, cert_scan_text, re.IGNORECASE):
            cert_name = m.group(1).strip()
            if 5 < len(cert_name) < 80 and cert_name.lower() not in existing_cert_text:
                extracted["certifications"].append(cert_name)
                existing_cert_text += " " + cert_name.lower()
    
    # 6. Validate and log warnings
    warnings = validate_phase1_extraction(raw_text, extracted)
    if warnings:
        logger.warning(f"Phase 1 extraction issues: {warnings}")
    
    return extracted


def parse_resume_vision(image_bytes: bytes, mime_type: str) -> dict:
    """
    image_bytes: raw bytes of the resume image (PNG, JPG, or PDF page converted to PNG).
    mime_type: e.g. "image/png" or "image/jpeg".
    Returns: a Python dict matching the strict JSON schema.
    """
    client = LLMClient(agent_name="resume_vision_parser")

    user_prompt = "Here is an image of the resume. Please parse and extract all details according to the schema instructions."

    response_text = client.generate_vision(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        image_bytes=image_bytes,
        mime_type=mime_type,
        json_mode=True,
    )

    response_text = _strip_json_fences(response_text)

    try:
        extracted = json.loads(response_text)
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            extracted = json.loads(json_match.group(0))
        else:
            raise ValueError(
                f"Resume Vision Parser didn't return valid JSON. "
                f"Raw response was: {response_text[:500]}"
            )

    # Apply standard normalizations
    if "contact" in extracted and isinstance(extracted["contact"], dict):
        extracted["contact"] = _normalize_contact_links(extracted["contact"], "")

    if "projects" in extracted and isinstance(extracted["projects"], list):
        extracted["projects"] = _normalize_project_bullets(extracted["projects"])

    if "experience" in extracted and isinstance(extracted["experience"], list):
        extracted["experience"] = _normalize_experience_bullets(extracted["experience"])

    certs = extracted.get("certifications", [])
    if isinstance(certs, str):
        extracted["certifications"] = [c.strip() for c in certs.split(",") if c.strip()]
    elif not isinstance(certs, list):
        extracted["certifications"] = []

    return extracted

