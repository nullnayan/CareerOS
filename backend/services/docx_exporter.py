from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

def _add_hyperlink(paragraph, url, text):
    """Constructs a Word XML hyperlink element."""
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        part = paragraph.part
        r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("r:id"), r_id)
        new_run = OxmlElement("w:r")
        rPr = OxmlElement("w:rPr")
        c = OxmlElement("w:color")
        c.set(qn("w:val"), "0000FF")
        rPr.append(c)
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        rPr.append(u)
        new_run.append(rPr)
        new_run.text = text
        hyperlink.append(new_run)
        paragraph._p.append(hyperlink)
    except Exception:
        r = paragraph.add_run(text)
        r.underline = True

def generate_docx(resume_data: dict) -> Document:
    doc = Document()
    
    # Page setup — 0.5 inch margins (36pt)
    for section in doc.sections:
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)
        section.left_margin = Inches(0.5)
        section.right_margin = Inches(0.5)
        
    def add_section_header(title: str):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(title.upper())
        run.bold = True
        run.font.size = Pt(11)
        
    contact = resume_data.get("contact", {})
    name = contact.get("name") or "Your Name"
    
    # Header Name
    p_name = doc.add_paragraph()
    p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_name = p_name.add_run(name)
    run_name.bold = True
    run_name.font.size = Pt(20)
    p_name.paragraph_format.space_after = Pt(2)
    
    # Contact info line
    email = contact.get("email") or ""
    phone = contact.get("phone") or ""
    linkedin = contact.get("linkedin") or ""
    portfolio = contact.get("portfolio") or ""
    location = contact.get("location") or ""
    
    p_contact = doc.add_paragraph()
    p_contact.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    parts = []
    if phone: parts.append(("phone", phone, None))
    if email: parts.append(("email", email, f"mailto:{email}"))
    if location: parts.append(("location", location, None))
    if linkedin: parts.append(("linkedin", "LinkedIn Profile", linkedin if linkedin.startswith("http") else f"https://{linkedin}"))
    if portfolio: parts.append(("portfolio", "Portfolio", portfolio if portfolio.startswith("http") else f"https://{portfolio}"))
    
    for idx, (kind, label, link_url) in enumerate(parts):
        if idx > 0:
            p_contact.add_run(" | ")
        if link_url:
            _add_hyperlink(p_contact, link_url, label)
        else:
            p_contact.add_run(label)

    p_contact.paragraph_format.space_after = Pt(12)
    
    headings = resume_data.get("original_section_headings", {})
    
    # Summary
    summary = resume_data.get("summary")
    if summary:
        add_section_header(headings.get("summary", "Professional Summary"))
        p_sum = doc.add_paragraph(summary)
        p_sum.paragraph_format.space_after = Pt(6)
        
    # Experience
    experience = resume_data.get("experience", [])
    if experience:
        add_section_header(headings.get("experience", "Experience"))
        for exp in experience:
            title = exp.get("title") or exp.get("role") or ""
            company = exp.get("company") or ""
            start = exp.get("start_date") or ""
            end = exp.get("end_date") or ""
            date_str = f"{start} - {end}".strip(" - ")
            
            p_title = doc.add_paragraph()
            p_title.paragraph_format.space_before = Pt(4)
            p_title.paragraph_format.space_after = Pt(2)
            p_title.paragraph_format.keep_with_next = True
            
            run_title = p_title.add_run(f"{title} — {company}")
            run_title.bold = True
            
            p_title.add_run(f"\t{date_str}")
            
            for bullet in exp.get("bullet_points", []):
                p_bullet = doc.add_paragraph(style='List Bullet')
                p_bullet.add_run(bullet)
                p_bullet.paragraph_format.space_after = Pt(2)
                
    # Projects
    projects = resume_data.get("projects", [])
    if projects:
        add_section_header(headings.get("projects", "Projects"))
        for proj in projects:
            pname = proj.get("name") or ""
            pdesc = proj.get("description") or ""
            techs = ", ".join(proj.get("technologies", []))
            
            p_proj = doc.add_paragraph()
            p_proj.paragraph_format.space_before = Pt(4)
            p_proj.paragraph_format.space_after = Pt(2)
            p_proj.paragraph_format.keep_with_next = True
            
            run_pname = p_proj.add_run(pname)
            run_pname.bold = True
            if techs:
                p_proj.add_run(f" ({techs})")
                
            if pdesc:
                p_desc = doc.add_paragraph(pdesc)
                p_desc.paragraph_format.space_after = Pt(4)
                
    # Education
    education = resume_data.get("education", [])
    if education:
        add_section_header(headings.get("education", "Education"))
        for edu in education:
            inst = edu.get("institution") or ""
            deg = edu.get("degree") or ""
            field = edu.get("field") or ""
            grad = edu.get("graduation_date") or ""
            
            p_edu = doc.add_paragraph()
            p_edu.paragraph_format.space_before = Pt(4)
            p_edu.paragraph_format.space_after = Pt(2)
            
            degree_str = f"{deg} in {field}" if field else deg
            run_edu = p_edu.add_run(f"{inst} — {degree_str}")
            run_edu.bold = True
            p_edu.add_run(f"\t{grad}")
            
    # Skills
    skills = resume_data.get("skills", [])
    skills_modified = resume_data.get("skills_modified", True)
    jd_skills = resume_data.get("jd_skills") or []

    if skills:
        add_section_header(headings.get("skills", "Skills"))
        
        if not skills_modified:
            # FIX 3: Render untouched original skills format in DOCX
            if isinstance(skills, dict):
                cat_source = skills.get("byCategory") or {k: v for k, v in skills.items() if k != "all"}
                for cat_name, val_list in cat_source.items():
                    if isinstance(val_list, list) and val_list:
                        p_cat = doc.add_paragraph()
                        r_lbl = p_cat.add_run(f"{cat_name}: ")
                        r_lbl.bold = True
                        p_cat.add_run(", ".join([str(v) for v in val_list if v]))
                        p_cat.paragraph_format.space_after = Pt(2)
                    elif isinstance(val_list, str) and val_list.strip():
                        p_cat = doc.add_paragraph()
                        r_lbl = p_cat.add_run(f"{cat_name}: ")
                        r_lbl.bold = True
                        p_cat.add_run(val_list.strip())
                        p_cat.paragraph_format.space_after = Pt(2)
            elif isinstance(skills, list):
                p_cat = doc.add_paragraph(", ".join([str(s) for s in skills if s]))
                p_cat.paragraph_format.space_after = Pt(2)
            elif isinstance(skills, str):
                p_cat = doc.add_paragraph(skills.strip())
                p_cat.paragraph_format.space_after = Pt(2)
        else:
            # Render categorized 9-domain format with smart sparsity merging (Fixes 1 & 2)
            from services.skill_manager import group_skills_into_categories
            from services.pdf_fitter import extract_flat_skills

            hard_skills_list, soft_skills_list = extract_flat_skills(skills)
            grouped = group_skills_into_categories(hard_skills_list, jd_skills=jd_skills)
            if soft_skills_list:
                grouped["Core Concepts"] = list(dict.fromkeys(grouped.get("Core Concepts", []) + soft_skills_list))

            for cat_name, val_list in grouped.items():
                if val_list:
                    p_cat = doc.add_paragraph()
                    r_lbl = p_cat.add_run(f"{cat_name}: ")
                    r_lbl.bold = True
                    p_cat.add_run(", ".join([str(v) for v in val_list if v]))
                    p_cat.paragraph_format.space_after = Pt(2)

    # Certifications
    certs = resume_data.get("certifications", [])
    if certs:
        add_section_header(headings.get("certifications", "Certifications & Courses"))
        for cert in certs:
            p_cert = doc.add_paragraph()
            p_cert.paragraph_format.space_after = Pt(2)
            if isinstance(cert, dict):
                c_name = cert.get("name") or ""
                c_issuer = f" — {cert.get('issuer')}" if cert.get("issuer") else ""
                c_year = f" ({cert.get('year')})" if cert.get("year") else ""
                r_cname = p_cert.add_run(c_name)
                r_cname.bold = True
                if c_issuer or c_year:
                    p_cert.add_run(f"{c_issuer}{c_year}")
                c_desc = cert.get("description")
                if c_desc:
                    p_desc = doc.add_paragraph(c_desc)
                    p_desc.paragraph_format.space_after = Pt(3)
            elif cert:
                p_cert.add_run(str(cert))
    return doc
