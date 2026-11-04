import os
from jinja2 import Environment, FileSystemLoader
from services.resume_migrations import upgrade_to_v1

# Set up Jinja2 environment pointing to the templates_html directory
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates_html")
env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)

# ─── Custom Jinja filters ──────────────────────────────────────────────────────

def is_hidden(item) -> bool:
    """
    Returns True if a SINGLE item is explicitly marked hidden.
    Only works on dicts — calling it on a list always returns False
    (use section_visible() for section-level gating instead).
    """
    if isinstance(item, dict):
        return item.get("hidden") is True
    return False

def section_visible(section_visibility: dict, key: str) -> bool:
    """Returns True if the section is NOT hidden (default visible)."""
    return section_visibility.get(key, True)

env.filters["is_hidden"] = is_hidden


def build_html(data: dict, template_id: str, section_order: list, design: dict) -> str:
    """
    Renders the modern HTML template using Jinja2 and full modern CSS.
    Upgrades legacy data to v1 schema before rendering.
    """
    import copy

    # Upgrade legacy rows to v1 canonical shape on every render
    data = upgrade_to_v1(copy.deepcopy(data) if isinstance(data, dict) else {})
    design = copy.deepcopy(design) if isinstance(design, dict) else {}

    # Ensure template_id maps to a valid jinja file
    valid_templates = {
        "classic": "classic.html",
        "modern_tech": "modern_tech.html",
        "minimal": "minimal.html",
        "professional": "professional.html",
        "ats_safe": "ats_safe.html",
        "academic": "academic.html",
    }

    file_name = valid_templates.get(template_id, "classic.html")
    template = env.get_template(file_name)

    # Build flat skill lists for templates that still use hard_skills/soft_skills
    from services.pdf_fitter import extract_flat_skills
    skills_raw = data.get("skills", [])
    # v1 skills are objects — extract names first
    skill_names = [s["name"] for s in skills_raw if isinstance(s, dict) and not s.get("hidden") and s.get("name")]
    hard_skills = skill_names
    soft_skills: list[str] = []

    # Section order: prefer data-embedded order, fall back to arg, then default
    effective_section_order = (
        data.get("section_order")
        or section_order
        or ["summary", "experience", "education", "projects",
            "skills", "languages", "certifications", "awards",
            "publications", "volunteer", "interests", "references", "custom_sections"]
    )
    section_visibility: dict = data.get("section_visibility") or {}

    html = template.render(
        data=data,
        section_order=effective_section_order,
        section_visibility=section_visibility,
        section_visible=lambda key: section_visibility.get(key, True),
        design=design,
        hard_skills=hard_skills,
        soft_skills=soft_skills,
    )

    return html
