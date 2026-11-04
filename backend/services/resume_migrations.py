"""
backend/services/resume_migrations.py
======================================
Upgrade legacy structured_json rows to the canonical v1 schema.

Called on READ for any row that lacks schema_version, so old parsed
('uploaded') resumes continue to load correctly without a destructive
one-shot data migration.

Never mutates the database — returns a plain dict ready to feed into
Jinja templates or the PDF engine.
"""

import re
import uuid


def _make_id() -> str:
    return uuid.uuid4().hex[:8]


def upgrade_to_v1(raw: dict) -> dict:
    """
    Promote a legacy structured_json dict to schema_version=1 shape.
    Returns a new dict; does NOT modify the input.
    """
    if not raw or not isinstance(raw, dict):
        raw = {}

    # Already v1 — pass through
    if raw.get("schema_version") == 1:
        return raw

    out: dict = {"schema_version": 1}

    # ── Contact ─────────────────────────────────────────────────────────
    raw_contact = raw.get("contact") or {}
    if isinstance(raw_contact, str):
        raw_contact = {}

    # Legacy parsers sometimes put links as a plain list of URL strings
    raw_links = raw_contact.get("links") or []
    profiles = []
    for lnk in raw_links:
        if isinstance(lnk, str):
            profiles.append({"id": _make_id(), "network": "", "username": "", "url": lnk, "hidden": False})
        elif isinstance(lnk, dict):
            profiles.append({
                "id": lnk.get("id") or _make_id(),
                "network": lnk.get("network") or lnk.get("name") or "",
                "username": lnk.get("username") or "",
                "url": lnk.get("url") or "",
                "hidden": lnk.get("hidden", False),
            })

    out["contact"] = {
        "name": raw_contact.get("name") or raw.get("name") or "",
        "headline": raw_contact.get("headline") or "",
        "email": raw_contact.get("email") or raw.get("email") or "",
        "phone": raw_contact.get("phone") or raw.get("phone") or "",
        "location": raw_contact.get("location") or raw.get("location") or "",
        "website": raw_contact.get("website") or "",
        "custom_fields": raw_contact.get("custom_fields") or [],
    }

    # ── Photo ────────────────────────────────────────────────────────────
    raw_photo = raw.get("photo") or {}
    if not isinstance(raw_photo, dict):
        raw_photo = {}
    out["photo"] = {
        "url": raw_photo.get("url") or "",
        "hidden": raw_photo.get("hidden", False),
        "size": raw_photo.get("size", 80),
        "border_radius": raw_photo.get("border_radius", 50),
        "border_color": raw_photo.get("border_color", "#e5e7eb"),
        "border_width": raw_photo.get("border_width", 0),
        "shadow_width": raw_photo.get("shadow_width", 0),
        "aspect_ratio": raw_photo.get("aspect_ratio", 1.0),
        "rotation": raw_photo.get("rotation", 0.0),
    }

    # ── Profiles (already reconstructed above from contact.links) ────────
    # If the doc already has a top-level profiles list (from builder saves), prefer it
    if raw.get("profiles") and isinstance(raw["profiles"], list):
        profiles = raw["profiles"]
    out["profiles"] = profiles

    # ── Summary ──────────────────────────────────────────────────────────
    out["summary"] = raw.get("summary") or ""

    # ── Experience ───────────────────────────────────────────────────────
    raw_exp = raw.get("experience") or []
    experience = []
    for e in raw_exp:
        if not isinstance(e, dict):
            continue
        experience.append({
            "id": e.get("id") or _make_id(),
            "hidden": e.get("hidden", False),
            "company": e.get("company") or "",
            # canonical: position — accept legacy alias 'title'
            "position": e.get("position") or e.get("title") or e.get("role") or "",
            "location": e.get("location") or "",
            "start_date": e.get("start_date") or e.get("startDate") or "",
            "end_date": e.get("end_date") or e.get("endDate") or "",
            "url": e.get("url") or "",
            "bullet_points": e.get("bullet_points") or e.get("bullets") or [],
        })
    out["experience"] = experience

    # ── Education ────────────────────────────────────────────────────────
    raw_edu = raw.get("education") or []
    education = []
    for e in raw_edu:
        if not isinstance(e, dict):
            continue
        education.append({
            "id": e.get("id") or _make_id(),
            "hidden": e.get("hidden", False),
            "institution": e.get("institution") or "",
            "degree": e.get("degree") or "",
            "field": e.get("field") or "",
            # canonical: grade — accept legacy alias 'cgpa_or_percentage'
            "grade": e.get("grade") or e.get("cgpa_or_percentage") or "",
            "location": e.get("location") or "",
            "graduation_date": e.get("graduation_date") or e.get("graduationDate") or "",
            "description": e.get("description") or "",
        })
    out["education"] = education

    # ── Projects ─────────────────────────────────────────────────────────
    raw_proj = raw.get("projects") or []
    projects = []
    for p in raw_proj:
        if not isinstance(p, dict):
            continue
        projects.append({
            "id": p.get("id") or _make_id(),
            "hidden": p.get("hidden", False),
            "name": p.get("name") or "",
            # canonical: period — accept legacy alias 'date'
            "period": p.get("period") or p.get("date") or "",
            # canonical: url — accept legacy alias 'link'
            "url": p.get("url") or p.get("link") or "",
            "technologies": p.get("technologies") or [],
            "bullets": p.get("bullets") or p.get("bullet_points") or [],
        })
    out["projects"] = projects

    # ── Skills ───────────────────────────────────────────────────────────
    raw_skills = raw.get("skills") or []
    skills = []
    if isinstance(raw_skills, list):
        for s in raw_skills:
            if isinstance(s, str) and s.strip():
                # Flat string → object
                skills.append({"id": _make_id(), "hidden": False, "name": s.strip(), "level": 0, "keywords": []})
            elif isinstance(s, dict):
                skills.append({
                    "id": s.get("id") or _make_id(),
                    "hidden": s.get("hidden", False),
                    "name": s.get("name") or "",
                    "level": s.get("level") or 0,
                    "keywords": s.get("keywords") or [],
                })
    elif isinstance(raw_skills, dict):
        # byCategory dict or similar
        for cat_name, items in raw_skills.items():
            if cat_name in ("byCategory", "all"):
                continue
            if isinstance(items, list):
                for item in items:
                    name = item if isinstance(item, str) else (item.get("name") or "")
                    if name:
                        skills.append({"id": _make_id(), "hidden": False, "name": name, "level": 0, "keywords": []})
    out["skills"] = skills

    # ── Languages ────────────────────────────────────────────────────────
    raw_langs = raw.get("languages") or []
    languages = []
    for l in raw_langs:
        if isinstance(l, str) and l.strip():
            # Parse legacy "English (Native)" string format
            m = re.match(r"^(.+?)\s*\((.+)\)$", l.strip())
            if m:
                languages.append({"id": _make_id(), "hidden": False, "language": m.group(1).strip(), "fluency": m.group(2).strip(), "level": 0})
            else:
                languages.append({"id": _make_id(), "hidden": False, "language": l.strip(), "fluency": "", "level": 0})
        elif isinstance(l, dict):
            languages.append({
                "id": l.get("id") or _make_id(),
                "hidden": l.get("hidden", False),
                "language": l.get("language") or "",
                "fluency": l.get("fluency") or "",
                "level": l.get("level") or 0,
            })
    out["languages"] = languages

    # ── Awards ───────────────────────────────────────────────────────────
    raw_awards = raw.get("awards") or []
    awards = []
    for a in raw_awards:
        if isinstance(a, str) and a.strip():
            # Legacy "Title — Awarder" string
            parts = a.split("—", 1)
            awards.append({
                "id": _make_id(), "hidden": False,
                "title": parts[0].strip(),
                "awarder": parts[1].strip() if len(parts) > 1 else "",
                "date": "", "description": "",
            })
        elif isinstance(a, dict):
            awards.append({
                "id": a.get("id") or _make_id(),
                "hidden": a.get("hidden", False),
                "title": a.get("title") or "",
                "awarder": a.get("awarder") or "",
                "date": a.get("date") or "",
                "description": a.get("description") or "",
            })
    out["awards"] = awards

    # ── Certifications ────────────────────────────────────────────────────
    raw_certs = raw.get("certifications") or []
    certifications = []
    for c in raw_certs:
        if isinstance(c, str) and c.strip():
            certifications.append({"id": _make_id(), "hidden": False, "title": c.strip(), "issuer": "", "date": "", "url": "", "description": ""})
        elif isinstance(c, dict):
            certifications.append({
                "id": c.get("id") or _make_id(),
                "hidden": c.get("hidden", False),
                "title": c.get("title") or "",
                "issuer": c.get("issuer") or "",
                "date": c.get("date") or "",
                "url": c.get("url") or "",
                "description": c.get("description") or "",
            })
    out["certifications"] = certifications

    # ── Publications ──────────────────────────────────────────────────────
    raw_pubs = raw.get("publications") or []
    publications = []
    for p in raw_pubs:
        if isinstance(p, dict):
            publications.append({
                "id": p.get("id") or _make_id(),
                "hidden": p.get("hidden", False),
                "title": p.get("title") or "",
                "publisher": p.get("publisher") or "",
                "date": p.get("date") or "",
                "url": p.get("url") or "",
                "summary": p.get("summary") or "",
            })
    out["publications"] = publications

    # ── Volunteer ─────────────────────────────────────────────────────────
    raw_vol = raw.get("volunteer") or []
    volunteer = []
    for v in raw_vol:
        if isinstance(v, dict):
            volunteer.append({
                "id": v.get("id") or _make_id(),
                "hidden": v.get("hidden", False),
                "organization": v.get("organization") or "",
                "position": v.get("position") or "",
                "location": v.get("location") or "",
                "period": v.get("period") or "",
                "description": v.get("description") or "",
            })
    out["volunteer"] = volunteer

    # ── Interests ─────────────────────────────────────────────────────────
    raw_interests = raw.get("interests") or []
    interests = []
    for i in raw_interests:
        if isinstance(i, str):
            interests.append({"id": _make_id(), "hidden": False, "name": i.strip(), "keywords": []})
        elif isinstance(i, dict):
            interests.append({
                "id": i.get("id") or _make_id(),
                "hidden": i.get("hidden", False),
                "name": i.get("name") or "",
                "keywords": i.get("keywords") or [],
            })
    out["interests"] = interests

    # ── References ────────────────────────────────────────────────────────
    raw_refs = raw.get("references") or []
    references = []
    for r in raw_refs:
        if isinstance(r, dict):
            references.append({
                "id": r.get("id") or _make_id(),
                "hidden": r.get("hidden", False),
                "name": r.get("name") or "",
                "position": r.get("position") or "",
                "phone": r.get("phone") or "",
                "url": r.get("url") or "",
                "description": r.get("description") or "",
            })
    out["references"] = references

    # ── Custom Sections ────────────────────────────────────────────────────
    raw_custom = raw.get("custom_sections") or []
    custom_sections = []
    for cs in raw_custom:
        if isinstance(cs, dict):
            custom_sections.append({
                "id": cs.get("id") or _make_id(),
                "hidden": cs.get("hidden", False),
                "name": cs.get("name") or "",
                "items": cs.get("items") or [],
            })
    out["custom_sections"] = custom_sections

    # ── Section order & visibility ─────────────────────────────────────────
    from schemas.resume import DEFAULT_SECTION_ORDER
    out["section_order"] = raw.get("section_order") or list(DEFAULT_SECTION_ORDER)
    out["section_visibility"] = raw.get("section_visibility") or {}

    return out
