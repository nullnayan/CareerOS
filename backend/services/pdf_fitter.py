"""
services/pdf_fitter.py
======================
V2 Resume Rendering Engine

Key improvements over V1:
  - 6 genuinely distinct template styles via _heading_css()
  - Dynamic section rendering — unknown sections (Research, Achievements, etc.) are NEVER dropped
  - Pipe-separator education format with table-based right-alignment for CGPA/dates
  - Table-based experience/project header rows (role + right-aligned dates)
  - pymupdf.Archive font embedding for real visual distinction between templates
  - section_order_override support for drag-and-drop reordering
"""

import tempfile
import pymupdf
import copy
import re
import os
import logging

from services.resume_templates import get_template
from services.template_fit import auto_order_sections, select_density_config

logger = logging.getLogger(__name__)


# ─── Known top-level keys that are NOT renderable resume sections ──────────────
_NON_SECTION_KEYS = frozenset({
    "contact", "name", "email", "phone", "location",
    "metadata", "formatting_metadata", "formatting_issues", "formatting_checks",
    "original_section_headings", "jd_skills", "skills_modified",
    "_raw_text", "_parser_version", "_raw",
    "summary", "education", "experience", "projects",
    "skills", "certifications",
    "ats_score", "score_breakdown", "match_report", "match_score",
    "suggestions", "total_potential_score", "total_potential",
    "content_flags", "recruiter_tips", "hard_skills_matched",
    "hard_skills_missing", "soft_skills_matched", "soft_skills_missing",
    "keyword_frequency", "section_checks", "job_title", "job_description",
    "id", "user_id", "created_at", "updated_at", "version", "is_tailored",
    "target_job", "score", "feedback",
})


# ─── Skill extraction ──────────────────────────────────────────────────────────

def extract_flat_skills(skills_input) -> tuple:
    """Robustly extract hard and soft skills lists from any JSON structure."""
    hard = []
    soft = []
    if not skills_input:
        return hard, soft

    if isinstance(skills_input, dict):
        for k, v in skills_input.items():
            k_low = str(k).lower()
            is_soft_key = any(ind in k_low for ind in ["soft", "interpersonal", "competenc"])
            target = soft if is_soft_key else hard

            if k == "byCategory" and isinstance(v, dict):
                for sub_cat, sub_vals in v.items():
                    sub_low = str(sub_cat).lower()
                    is_s = any(ind in sub_low for ind in ["soft", "interpersonal", "competenc"])
                    t = soft if is_s else hard
                    if isinstance(sub_vals, list):
                        t.extend([str(x).strip() for x in sub_vals if str(x).strip()])
                    elif isinstance(sub_vals, str):
                        t.extend([x.strip() for x in sub_vals.split(",") if x.strip()])
            elif k == "all" and isinstance(v, list):
                hard.extend([str(x).strip() for x in v if str(x).strip()])
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and item.strip():
                        target.append(item.strip())
                    elif isinstance(item, dict):
                        name = item.get("name") or item.get("skill") or ""
                        if name: target.append(str(name).strip())
            elif isinstance(v, str) and v.strip():
                target.extend([x.strip() for x in v.split(",") if x.strip()])
            elif isinstance(v, dict):
                for sub_v in v.values():
                    if isinstance(sub_v, list):
                        target.extend([str(x).strip() for x in sub_v if x])

        if not hard and not soft:
            def extract_strings(obj):
                if isinstance(obj, dict):
                    for val in obj.values(): extract_strings(val)
                elif isinstance(obj, list):
                    for item in obj: extract_strings(item)
                elif isinstance(obj, str) and obj.strip():
                    hard.append(obj.strip())
            extract_strings(skills_input)

    elif isinstance(skills_input, list):
        for s in skills_input:
            if isinstance(s, str):
                s_str = s.strip()
                if not s_str: continue
                if ":" in s_str and len(s_str.split(":", 1)[0]) < 30:
                    parts = s_str.split(":", 1)
                    sub_vals = [x.strip() for x in parts[1].split(",") if x.strip()]
                    if any(ind in parts[0].lower() for ind in ["soft", "interpersonal", "competenc"]):
                        soft.extend(sub_vals)
                    else:
                        hard.extend(sub_vals)
                else:
                    hard.append(s_str)
            elif isinstance(s, dict):
                name = s.get("name") or s.get("skill") or ""
                if name: hard.append(str(name).strip())

    elif isinstance(skills_input, str) and skills_input.strip():
        hard.extend([x.strip() for x in skills_input.split(",") if x.strip()])

    hard = list(dict.fromkeys([h for h in hard if h]))
    soft = list(dict.fromkeys([s for s in soft if s]))
    return hard, soft


# ─── Heading CSS generator ─────────────────────────────────────────────────────

def _heading_css(template: dict, s_heading: float, section_gap_pt: float) -> str:
    """
    Produces genuinely different h2 CSS per template heading_style.
    heading_style options:
      bold_underline          — bold text + thin rule below (Classic, Academic)
      accent_left_border      — bold left border bar + uppercase (Modern Tech)
      bold_plain              — bold only, no rule/border, uppercase + wide letter-spacing (Minimal)
      smallcaps_thick_border  — small-caps + thick underline (Professional)
      plain_line              — plain bold + hairline rule, no transforms (ATS Safe)
    """
    style   = template.get("heading_style", "bold_underline")
    c_head  = template["colors"]["heading"]
    case    = template.get("heading_case", "none")

    transform_css = ""
    if case == "upper":
        transform_css = "text-transform: uppercase;"
    # smallcaps is applied via font-variant, not text-transform

    base = (
        f"h2 {{ font-size: {s_heading}pt; font-weight: bold; color: {c_head}; "
        f"margin: {section_gap_pt}pt 0 2pt 0; padding-bottom: 1pt; "
        f"{transform_css} }}"
    )

    if style == "bold_underline":
        return base + f"\nh2 {{ border-bottom: 0.75pt solid {c_head}; }}"

    if style == "accent_left_border":
        return (
            f"h2 {{ font-size: {s_heading}pt; font-weight: bold; color: {c_head}; "
            f"border-left: 3pt solid {c_head}; padding-left: 6pt; "
            f"margin: {section_gap_pt}pt 0 2pt 0; "
            f"text-transform: uppercase; letter-spacing: 0.5pt; }}"
        )

    if style == "bold_plain":
        return (
            f"h2 {{ font-size: {s_heading}pt; font-weight: bold; color: {c_head}; "
            f"margin: {section_gap_pt}pt 0 2pt 0; "
            f"text-transform: uppercase; letter-spacing: 1.5pt; border: none; }}"
        )

    if style == "smallcaps_thick_border":
        return (
            f"h2 {{ font-size: {s_heading}pt; font-weight: bold; color: {c_head}; "
            f"font-variant: small-caps; letter-spacing: 0.5pt; "
            f"border-bottom: 2pt solid {c_head}; "
            f"margin: {section_gap_pt}pt 0 2pt 0; padding-bottom: 1pt; }}"
        )

    if style == "plain_line":
        return (
            f"h2 {{ font-size: {s_heading}pt; font-weight: bold; color: {c_head}; "
            f"border-bottom: 0.5pt solid #000000; "
            f"margin: {section_gap_pt}pt 0 2pt 0; padding-bottom: 1pt; }}"
        )

    return base  # fallback


def _h2(text: str, template: dict) -> str:
    """Wrap heading text in <h2>, applying case transform."""
    case = template.get("heading_case", "none")
    if case == "upper":
        text = text.upper()
    return f"<h2>{text}</h2>\n"


def _esc(s: str) -> str:
    """Minimal HTML escaping for body text."""
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _highlight_numbers(text: str) -> str:
    """Bold standalone numbers / percentages / metrics in bullet text."""
    return re.sub(r'(\b\d[\d,.]*\s*%?\+?(?:x|X|×)?\b)', r'<b>\1</b>', text)


# ─── Two-column row helper ─────────────────────────────────────────────────────

def _row_table(left: str, right: str, c_muted: str, meta_size: float) -> str:
    """
    Renders a two-column table row: left-aligned content, right-aligned metadata.
    Uses HTML <table> because CSS float:right is unreliable in pymupdf.Story.
    """
    return (
        f"<table width='100%' cellpadding='0' cellspacing='0' "
        f"style='border-collapse:collapse; margin: 0;'>"
        f"<tr>"
        f"<td style='text-align:left; vertical-align:baseline;'>{left}</td>"
        f"<td width='110' style='text-align:right; vertical-align:baseline; padding-left:24pt; "
        f"white-space:nowrap; color:{c_muted}; font-size:{meta_size}pt;'>{right}</td>"
        f"</tr></table>\n"
    )


# ─── Generic unknown section renderer ─────────────────────────────────────────

def _dict_to_line(item: dict) -> str:
    """Flatten a dict item from an unknown section into a readable line."""
    parts = []
    # Prioritise common field names
    for key in ["name", "title", "role", "description", "detail", "text"]:
        val = item.get(key)
        if val and isinstance(val, str):
            parts.append(_esc(val.strip()))
    # Add remaining string values
    for k, v in item.items():
        if k in {"name", "title", "role", "description", "detail", "text"}:
            continue
        if isinstance(v, str) and v.strip():
            parts.append(_esc(v.strip()))
        elif isinstance(v, (int, float)):
            parts.append(str(v))
    return " | ".join(parts) if parts else ""


def _render_unknown_section(key: str, value, template: dict, headings: dict) -> str:
    """
    Generic renderer for any section the parser extracted that isn't one of the
    6 known types. Produces <h2> + bullet list / paragraphs.
    """
    label = headings.get(key) or key.replace("_", " ").title()
    html  = _h2(label, template)

    if isinstance(value, list) and value:
        html += "<ul class='bullet-list'>"
        for item in value:
            if isinstance(item, str) and item.strip():
                html += f"<li>{_esc(item.strip())}</li>"
            elif isinstance(item, dict):
                line = _dict_to_line(item)
                if line:
                    html += f"<li>{line}</li>"
        html += "</ul>"
    elif isinstance(value, str) and value.strip():
        html += f"<p>{_esc(value.strip())}</p>"

    return html


# ─── Main HTML builder ────────────────────────────────────────────────────────

def _build_html(
    data: dict,
    template: dict,
    section_order: list,
    font_size_offset: float = 0.0,
    line_height_offset: float = 0.0,
    section_gap_offset: float = 0.0,
) -> tuple:
    """
    Builds the full resume HTML string and returns (html, archive).
    The archive carries embedded font buffers for pymupdf.Story.

    section_order should include both known section keys AND any custom/unknown
    section keys detected in the resume data (e.g. 'research', 'achievements').
    Any unknown keys found in data that are NOT in section_order are appended
    at the end so content is NEVER silently dropped.
    """
    # ── Compute final sizes ────────────────────────────────────────────────────
    s_name    = template["sizes"]["name"]    + font_size_offset
    s_contact = template["sizes"]["contact"] + font_size_offset
    s_heading = template["sizes"]["heading"] + font_size_offset
    s_body    = template["sizes"]["body"]    + font_size_offset
    s_meta    = template["sizes"]["meta"]    + font_size_offset

    margin_pt      = template["spacing"]["margin_pt"]
    line_height    = template["spacing"]["line_height"]    + line_height_offset
    section_gap_pt = template["spacing"]["section_gap_pt"] + section_gap_offset
    bullet_indent  = template["spacing"]["bullet_indent"]

    c_body  = template["colors"]["body"]
    c_muted = template["colors"]["muted"]
    c_head  = template["colors"]["heading"]

    name_align      = template.get("name_align", "center")
    name_letterspacing = template.get("name_letterspacing", "0pt")

    font_face_css = template.get("font_face_css", "")
    font_family   = template["font_family"]
    archive       = template.get("archive")

    # ── CSS ────────────────────────────────────────────────────────────────────
    heading_css = _heading_css(template, s_heading, section_gap_pt)

    css = f"""
{font_face_css}
@page {{ size: letter; margin: {margin_pt}pt; }}
body {{
  font-family: {font_family};
  font-size: {s_body}pt;
  line-height: {line_height};
  margin: 0; padding: 0;
  color: {c_body};
}}
h1 {{
  font-size: {s_name}pt;
  text-align: {name_align};
  margin: 0 0 1pt 0;
  font-weight: bold;
  letter-spacing: {name_letterspacing};
  color: {c_body};
}}
.contact {{
  text-align: {name_align};
  font-size: {s_contact}pt;
  color: {c_muted};
  margin-bottom: 4pt;
}}
{heading_css}
.job-title {{ font-weight: bold; color: {c_body}; font-size: {s_body}pt; }}
.job-tech  {{ font-style: italic; color: {c_muted}; font-size: {s_meta}pt; }}
.job-date  {{ color: {c_muted}; font-size: {s_meta}pt; }}
.bullet-list {{
  margin: 1pt 0 3pt 0;
  padding-left: {bullet_indent}pt;
}}
.bullet-list li {{
  margin-bottom: 1.5pt;
  font-size: {s_body}pt;
  text-align: justify;
}}
.skill-category {{ font-weight: bold; color: {c_body}; }}
.skill-values   {{ color: {c_body}; }}
p {{ margin: 0 0 2pt 0; font-size: {s_body}pt; }}
"""

    html = f"<html>\n<head>\n<style>\n{css}\n</style>\n</head>\n<body>\n"

    # ── Contact header ─────────────────────────────────────────────────────────
    contact = data.get("contact", {})
    name    = contact.get("name") or data.get("name") or "Applicant"
    html += f"<h1>{_esc(name)}</h1>\n"

    c_parts = []
    if contact.get("phone"):    c_parts.append(_esc(contact["phone"]))
    if contact.get("email"):    c_parts.append(_esc(contact["email"]))
    if contact.get("linkedin"): c_parts.append(_esc(contact["linkedin"]))
    if contact.get("github"):   c_parts.append(_esc(contact["github"]))
    if contact.get("portfolio"): c_parts.append(_esc(contact["portfolio"]))
    for lnk in (contact.get("links") or []):
        url = lnk.strip() if isinstance(lnk, str) else str(lnk.get("url", "")).strip()
        if not url:
            continue
        if "linkedin.com" in url.lower():
            label = "LinkedIn Profile"
        elif "github.com" in url.lower():
            label = "GitHub Profile"
        else:
            label = url.replace("https://", "").replace("http://", "").rstrip("/")
        if label not in c_parts:
            c_parts.append(label)
    if contact.get("location"):
        c_parts.append(_esc(contact["location"]))

    if c_parts:
        html += f"<div class='contact'>{' | '.join(c_parts)}</div>\n"

    # ── Section labels ─────────────────────────────────────────────────────────
    headings = data.get("original_section_headings", {}) or {}

    def _label(key: str, default: str) -> str:
        return headings.get(key, default)

    # ── Detect unknown sections that exist in data but not in section_order ────
    # These get appended at the end so nothing is lost.
    all_order = list(section_order)
    for key in data.keys():
        if key in _NON_SECTION_KEYS:
            continue
        if key.startswith("_"):
            continue
        if key not in all_order:
            val = data[key]
            if val and (isinstance(val, (list, str)) or isinstance(val, dict)):
                all_order.append(key)

    # ── Main section render loop ───────────────────────────────────────────────
    for sec in all_order:
        # ─ Summary ──────────────────────────────────────────────────────────
        if sec == "summary":
            summary = data.get("summary")
            if summary and isinstance(summary, str) and summary.strip():
                html += _h2(_label("summary", "Professional Summary"), template)
                html += f"<p style='text-align:justify; font-style:italic;'>{_esc(summary.strip())}</p>\n"

        # ─ Education (pipe-separator format) ────────────────────────────────
        elif sec == "education":
            education = data.get("education", [])
            if education:
                html += _h2(_label("education", "Education"), template)
                for edu in education:
                    inst  = edu.get("institution") or "Institution"
                    loc   = edu.get("location") or ""
                    grad  = edu.get("graduation_date") or ""
                    cgpa  = edu.get("cgpa_or_percentage") or ""
                    if str(cgpa).lower() in {"null", "none", ""}: cgpa = ""
                    if str(grad).lower() in {"null", "none", ""}: grad = ""

                    # Degree line — prefer structured fields over original_line
                    deg   = edu.get("degree") or ""
                    field = edu.get("field") or ""
                    if deg.lower() in {"null", ""}: deg = ""
                    if field.lower() in {"null", ""}: field = ""
                    
                    if deg or field:
                        connector = edu.get("degree_field_connector")
                        if connector is not None and field:
                            degree_str = f"{deg}{connector}{field}"
                        elif field and deg and field.lower() not in deg.lower():
                            if "board" in field.lower():
                                degree_str = f"{deg} ({field})"
                            else:
                                degree_str = f"{deg} in {field}"
                        else:
                            degree_str = deg or field
                    else:
                        orig = edu.get("original_line") or ""
                        degree_str = orig.strip() if orig and "null" not in orig.lower() else "Degree"
                        
                    if degree_str:
                        deg_lower = degree_str.lower().strip()
                        for acr, full in [
                            ("b.tech", "Bachelor of Technology"), ("btech", "Bachelor of Technology"),
                            ("b.e.", "Bachelor of Engineering"), ("b.e", "Bachelor of Engineering"), ("be", "Bachelor of Engineering"),
                            ("b.sc", "Bachelor of Science"), ("bsc", "Bachelor of Science"),
                            ("b.a.", "Bachelor of Arts"), ("b.a", "Bachelor of Arts"), ("ba", "Bachelor of Arts"),
                            ("bca", "Bachelor of Computer Applications"), ("b.c.a.", "Bachelor of Computer Applications"),
                            ("m.tech", "Master of Technology"), ("mtech", "Master of Technology"),
                            ("m.e.", "Master of Engineering"), ("m.e", "Master of Engineering"), ("me", "Master of Engineering"),
                            ("m.sc", "Master of Science"), ("msc", "Master of Science"),
                            ("m.a.", "Master of Arts"), ("m.a", "Master of Arts"), ("ma", "Master of Arts"),
                            ("mca", "Master of Computer Applications"), ("bba", "Bachelor of Business Administration"),
                            ("mba", "Master of Business Administration"),
                        ]:
                            if deg_lower == acr:
                                degree_str = full
                                break
                            elif deg_lower.startswith(acr + " ") or deg_lower.startswith(acr + ","):
                                degree_str = full + degree_str[len(acr):]
                                break

                    # CGPA formatting
                    cgpa_str = ""
                    if cgpa:
                        c_low = str(cgpa).lower()
                        if "cgpa" in c_low or "%" in c_low or "gpa" in c_low:
                            cgpa_str = str(cgpa)
                        else:
                            cgpa_str = f"CGPA: {cgpa}"

                    # Line 1: Institution | Location
                    left1 = f"<span class='job-title'>{_esc(inst)}</span>"
                    if loc:
                        left1 += f"<span style='color:{c_muted}; font-size:{s_body}pt;'> | {_esc(loc)}</span>"
                    
                    right1 = ""

                    # Line 2: Degree; CGPA | Dates
                    parts = []
                    if degree_str:
                        parts.append(_esc(degree_str))
                    if cgpa_str:
                        parts.append(_esc(cgpa_str))
                    
                    line2_str = "; ".join(parts)
                    if grad:
                        if line2_str:
                            line2_str += f" | {_esc(grad)}"
                        else:
                            line2_str = _esc(grad)
                            
                    left2  = f"<span style='font-size:{s_body}pt; font-style:italic; color:{c_body};'>{line2_str}</span>"
                    right2 = ""

                    html += _row_table(left1, right1, c_muted, s_body)
                    html += _row_table(left2, right2, c_muted, s_body)
                    html += "<p style='margin:2pt 0;'></p>\n"

        # ─ Experience ────────────────────────────────────────────────────────
        elif sec == "experience":
            experiences = data.get("experience", [])
            if experiences:
                html += _h2(_label("experience", "Experience"), template)
                for exp in experiences:
                    role    = _esc(exp.get("title") or exp.get("role") or "Role")
                    company = _esc(exp.get("company") or "Company")
                    start   = exp.get("start_date") or ""
                    end     = exp.get("end_date") or ""
                    date_str = f"{start} \u2013 {end}".strip(" \u2013 ") if (start or end) else ""
                    loc     = exp.get("location") or ""

                    left = (
                        f"<span class='job-title'>{role}</span>"
                        f"<span style='color:{c_muted};'> @ </span>"
                        f"<span class='job-tech'>{company}</span>"
                    )
                    if loc:
                        left += f"<span style='color:{c_muted}; font-size:{s_meta}pt;'> | {_esc(loc)}</span>"
                    html += _row_table(left, _esc(date_str), c_muted, s_meta)

                    bullets = exp.get("bullet_points") or exp.get("bullets") or []
                    if bullets:
                        html += "<ul class='bullet-list'>"
                        for b in bullets:
                            if isinstance(b, str) and b.strip():
                                html += f"<li>{_highlight_numbers(_esc(b.strip()))}</li>"
                        html += "</ul>\n"

        # ─ Projects ──────────────────────────────────────────────────────────
        elif sec == "projects":
            projects = data.get("projects", [])
            if projects:
                html += _h2(_label("projects", "Projects"), template)
                for proj in projects:
                    pname  = _esc(proj.get("name") or "Project")
                    techs  = ", ".join(proj.get("technologies", []) or [])
                    date_str = _esc(proj.get("date") or "")
                    link   = proj.get("link") or proj.get("url") or ""

                    tech_html = (
                        f" <span class='job-tech'>| {_esc(techs)}</span>" if techs else ""
                    )
                    left = f"<span class='job-title'>{pname}</span>{tech_html}"
                    if link:
                        left += f" <span style='color:{c_muted}; font-size:{s_meta}pt;'>({_esc(link.replace('https://','').replace('http://','').rstrip('/'))})</span>"
                    html += _row_table(left, date_str, c_muted, s_meta)

                    bullets = proj.get("bullet_points") or proj.get("bullets") or []
                    if bullets:
                        html += "<ul class='bullet-list'>"
                        for b in bullets:
                            if isinstance(b, str) and b.strip():
                                html += f"<li>{_highlight_numbers(_esc(b.strip()))}</li>"
                        html += "</ul>\n"

        # ─ Skills ────────────────────────────────────────────────────────────
        elif sec == "skills":
            skills = data.get("skills")
            if skills:
                html += _h2(_label("skills", "Skills"), template)
                hard, soft = extract_flat_skills(skills)
                jd_skills  = data.get("jd_skills") or []

                from services.skill_manager import group_skills_into_categories
                grouped = group_skills_into_categories(hard, jd_skills=jd_skills)
                if soft:
                    grouped["Core Concepts"] = list(
                        dict.fromkeys(grouped.get("Core Concepts", []) + soft)
                    )

                for cat_name, val_list in grouped.items():
                    if val_list:
                        val_str = ", ".join(str(v) for v in val_list if v)
                        html += (
                            f"<p>"
                            f"<span class='skill-category'>{_esc(cat_name)}:</span> "
                            f"<span class='skill-values'>{_esc(val_str)}</span>"
                            f"</p>\n"
                        )

        # ─ Certifications ────────────────────────────────────────────────────
        elif sec == "certifications":
            certs = data.get("certifications", [])
            if certs:
                html += _h2(_label("certifications", "Certifications"), template)
                html += "<ul class='bullet-list'>"
                for cert in certs:
                    if isinstance(cert, dict):
                        c_name = cert.get("name") or ""
                        c_desc = cert.get("description") or ""
                        cert_str = f"{c_name} \u2013 {c_desc}" if c_desc else c_name
                    else:
                        cert_str = str(cert)
                    if cert_str.strip():
                        html += f"<li>{_esc(cert_str.strip())}</li>"
                html += "</ul>\n"

        # ─ Unknown / custom section ──────────────────────────────────────────
        elif sec not in _NON_SECTION_KEYS and not sec.startswith("_"):
            val = data.get(sec)
            if val:
                html += _render_unknown_section(sec, val, template, headings)

    html += "</body>\n</html>"
    return html, archive


# ─── Page stats ───────────────────────────────────────────────────────────────

def _get_page_stats(html_content: str, archive=None) -> tuple:
    """Returns (page_count, fill_ratio_on_first_page)."""
    try:
        story = pymupdf.Story(html=html_content, archive=archive)
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tf.close()
        writer = pymupdf.DocumentWriter(tf.name)
        mediabox = pymupdf.paper_rect("letter")
        rect = pymupdf.Rect(36, 36, mediabox.width - 36, mediabox.height - 36)
        page_count = 0
        last_fill = 0.0
        more = True
        while more:
            device = writer.begin_page(mediabox)
            more, filled_rect = story.place(rect)
            if page_count == 0:
                filled_height = filled_rect.height if hasattr(filled_rect, 'height') else (filled_rect[3] - filled_rect[1])
                last_fill = filled_height / rect.height if rect.height > 0 else 0.0
            story.draw(device)
            writer.end_page()
            page_count += 1
        writer.close()
        try:
            os.unlink(tf.name)
        except Exception:
            pass
        return page_count, last_fill
    except Exception as e:
        logger.warning(f"_get_page_stats error: {e}")
        return 1, 0.8


# ─── PDF writer ───────────────────────────────────────────────────────────────

def _write_pdf(html: str, archive=None) -> str:
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp_path = temp_file.name
    temp_file.close()

    story  = pymupdf.Story(html=html, archive=archive)
    writer = pymupdf.DocumentWriter(temp_path)
    more   = True
    while more:
        mediabox = pymupdf.paper_rect("letter")
        rect     = pymupdf.Rect(36, 36, mediabox.width - 36, mediabox.height - 36)
        device   = writer.begin_page(mediabox)
        more, _  = story.place(rect)
        story.draw(device)
        writer.end_page()
    writer.close()
    return temp_path


# ─── Link injector ────────────────────────────────────────────────────────────

def _inject_links_to_pdf(pdf_path: str, data: dict):
    contact = data.get("contact", {})
    email   = contact.get("email")
    links   = contact.get("links", [])
    if not email and not links:
        return

    try:
        doc  = pymupdf.open(pdf_path)
        if not doc or len(doc) == 0:
            return
        page = doc[0]

        if email:
            for r in page.search_for(email):
                page.insert_link({"kind": pymupdf.LINK_URI, "from": r, "uri": f"mailto:{email}"})

        for link in links:
            raw_url = link if isinstance(link, str) else link.get("url", "")
            if not raw_url:
                continue
            uri = raw_url if raw_url.startswith(("http://", "https://")) else f"https://{raw_url}"

            if "linkedin" in raw_url.lower():
                labels = ["LinkedIn Profile", "LinkedIn", "linkedin"]
            elif "github" in raw_url.lower():
                labels = ["GitHub Profile", "GitHub", "github"]
            else:
                domain = raw_url.split("//")[-1].split("/")[0]
                labels = [domain, raw_url.replace("https://", "").replace("http://", "")]

            for lbl in labels:
                rects = page.search_for(lbl)
                if rects:
                    for r in rects:
                        page.insert_link({"kind": pymupdf.LINK_URI, "from": r, "uri": uri})
                    break

        temp_dir  = os.path.dirname(pdf_path)
        saved     = os.path.join(temp_dir, f"saved_{os.path.basename(pdf_path)}")
        doc.save(saved)
        doc.close()
        try:
            os.remove(pdf_path)
        except Exception:
            pass
        os.replace(saved, pdf_path)
    except Exception as e:
        logger.warning(f"_inject_links_to_pdf failed: {e}")


# ─── Bullet pruner ────────────────────────────────────────────────────────────

def _score_bullet(bullet: str) -> int:
    score = len(bullet)
    if re.search(r'\d', bullet):
        score += 50
    strong_verbs = ["led", "developed", "architected", "managed", "increased",
                    "decreased", "improved", "built", "launched", "delivered"]
    if any(v in bullet.lower() for v in strong_verbs):
        score += 20
    return score


def _prune_weakest_bullet(data: dict) -> dict:
    weakest_score = float("inf")
    weakest_loc   = None
    for sec in ["experience", "projects"]:
        for i, item in enumerate(data.get(sec, [])):
            key     = "bullet_points" if sec == "experience" else "bullets"
            bullets = item.get(key) or item.get("bullet_points") or item.get("bullets") or []
            if len(bullets) <= 1:
                continue
            for j, bullet in enumerate(bullets):
                score = _score_bullet(str(bullet))
                if score < weakest_score:
                    weakest_score = score
                    weakest_loc   = (sec, i, key)
    if weakest_loc:
        sec, i, key = weakest_loc
        bullets = data[sec][i].get(key) or []
        if len(bullets) > 1:
            # Remove the weakest-scoring bullet
            scored = [(j, _score_bullet(str(b))) for j, b in enumerate(bullets)]
            scored.sort(key=lambda x: x[1])
            del bullets[scored[0][0]]
    return data


# ─── Expansion fitter ─────────────────────────────────────────────────────────

def _expand_to_fill_page(
    data: dict,
    template: dict,
    section_order: list,
    font_size_offset: float,
    line_height_offset: float,
) -> tuple:
    """
    Bidirectional Fitter — Expansion Phase:
    Gradually increases section gap to fill the page to ~95%.
    """
    best_gap_offset = 0.0
    target_fill     = 0.95
    gap_ceiling     = template.get("fit_overrides", {}).get("gap_ceiling", 16.0)

    while best_gap_offset < gap_ceiling:
        test_gap             = best_gap_offset + 0.5
        test_html, archive   = _build_html(data, template, section_order, font_size_offset, line_height_offset, section_gap_offset=test_gap)
        pages, fill          = _get_page_stats(test_html, archive=archive)
        if pages <= 1 and fill <= target_fill:
            best_gap_offset = test_gap
        else:
            break

    return _build_html(data, template, section_order, font_size_offset, line_height_offset, section_gap_offset=best_gap_offset)


def build_preview_html(
    data: dict,
    template_id: str = None,
    section_order: list = None,
    font_id: str = None,
    design: dict = None,
) -> str:
    """
    Public function that returns the rendered HTML string for live preview.
    Uses the new modern Jinja templates.
    """
    if not template_id:
        template_id = "classic"
    if not section_order:
        from services.template_fit import auto_order_sections
        section_order = auto_order_sections(data, template_id=template_id)
        
    from services.html_templates import build_html
    return build_html(data, template_id, section_order, design or {})


# ─── Playwright PDF renderer ──────────────────────────────────────────────────

def _render_pdf_playwright(html: str, page_format: str = "Letter") -> str:
    """
    Render HTML to a PDF using Playwright headless Chromium.
    Returns the absolute path to the generated temp PDF file.
    """
    from playwright.sync_api import sync_playwright

    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tf.close()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.pdf(
            path=tf.name,
            format=page_format,
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()

    return tf.name


# ─── Main public entry point ──────────────────────────────────────────────────

def build_fitted_pdf(
    data: dict,
    template_id: str = None,
    section_order_override: list = None,
    font_id: str = None,
    design: dict = None,
) -> str:
    """
    Builds a one-page ATS-friendly PDF using the chosen template and font.
    Tries Playwright (headless Chromium) first for full CSS support;
    falls back to PyMuPDF if Playwright is unavailable.

    Args:
        data:                  Parsed resume JSON.
        template_id:           One of: classic, modern_tech, minimal, professional, ats_safe, academic.
        section_order_override: Optional user-specified section order from drag-and-drop UI.
        font_id:               Optional font override from font_registry (e.g. 'calibri', 'georgia').
        design:                The design tokens (colors, fonts, etc.).

    Returns:
        Absolute path to the generated PDF temp file.
    """
    if not template_id:
        template_id = "classic"

    template       = get_template(template_id, font_id=font_id)
    
    if not section_order_override:
        section_order_override = auto_order_sections(data, template_id=template_id)
    section_order = section_order_override
    
    density_config = select_density_config(data)

    font_size_offset   = density_config["font_size_offset"]
    line_height_offset = density_config["line_height_offset"]
    section_gap_offset = 0.0

    current_data = copy.deepcopy(data)

    # ── Try Playwright (full CSS support) ──────────────────────────────────────
    try:
        from services.html_templates import build_html
        # Playwright takes the new modern Jinja templates which handle design seamlessly!
        html = build_html(current_data, template_id, section_order, design or {})
        pdf_path = _render_pdf_playwright(html)
        _inject_links_to_pdf(pdf_path, current_data)
        return pdf_path
    except Exception as pw_err:
        logger.warning(f"Playwright PDF render failed, falling back to PyMuPDF: {pw_err}")

    # ── Fallback: PyMuPDF (original pipeline with fitting) ────────────────────
    html, archive = _build_html(current_data, template, section_order, font_size_offset, line_height_offset, section_gap_offset)
    pages, fill   = _get_page_stats(html, archive=archive)

    # Phase 1 — fits natively: expand to fill page
    if pages <= 1:
        fitted_html, archive = _expand_to_fill_page(current_data, template, section_order, font_size_offset, line_height_offset)
        pdf_path = _write_pdf(fitted_html, archive=archive)
        _inject_links_to_pdf(pdf_path, current_data)
        return pdf_path

    # Phase 2 — doesn't fit: scale down gently
    lh_ceiling   = template.get("fit_overrides", {}).get("lh_ceiling", 1.35)
    font_ceiling  = template.get("fit_overrides", {}).get("font_ceiling", 10.8)
    min_font_offset = -1.5
    while font_size_offset > min_font_offset:
        font_size_offset   -= 0.1
        line_height_offset -= 0.02
        html, archive = _build_html(current_data, template, section_order, font_size_offset, line_height_offset, section_gap_offset)
        pages, fill   = _get_page_stats(html, archive=archive)
        if pages <= 1:
            pdf_path = _write_pdf(html, archive=archive)
            _inject_links_to_pdf(pdf_path, current_data)
            return pdf_path

    # Phase 3 — still doesn't fit: prune weak bullets
    for _ in range(20):
        current_data  = _prune_weakest_bullet(current_data)
        html, archive = _build_html(current_data, template, section_order, font_size_offset, line_height_offset, section_gap_offset)
        pages, fill   = _get_page_stats(html, archive=archive)
        if pages <= 1:
            pdf_path = _write_pdf(html, archive=archive)
            _inject_links_to_pdf(pdf_path, current_data)
            return pdf_path

    # Fallback — write whatever we have
    pdf_path = _write_pdf(html, archive=archive)
    _inject_links_to_pdf(pdf_path, current_data)
    return pdf_path
