"""
Phase Gate Test — Validates Phases 1-3 of the resume parser.
Run from the backend directory:
    .\\venv\\Scripts\\python.exe test_parser_phase1_3.py
"""

import sys
import json
import os

sys.path.insert(0, ".")

from resume_parser.pipeline import parse_resume

# ─── Test 1: Plain text resume (simplest case) ────────────────────────────────

SAMPLE_RESUME_TXT = """
John Doe
john.doe@example.com | (555) 123-4567 | linkedin.com/in/johndoe | github.com/johndoe
San Francisco, CA

Summary
Experienced software engineer with 6+ years building scalable backend systems.

Experience

Software Engineer at Google
Jan 2020 - Present
• Built distributed services handling 1M+ daily requests using Python and Kubernetes
• Reduced API latency by 40% through query optimization and caching with Redis
• Led migration from monolith to microservices architecture

Junior Developer at StartupXYZ
Jun 2017 - Dec 2019
• Developed React frontend for e-commerce platform serving 50K users
• Implemented REST APIs using Node.js and Express.js
• Worked with PostgreSQL and MongoDB databases

Education

Bachelor of Science in Computer Science
Massachusetts Institute of Technology
2013 - 2017
GPA: 3.9/4.0
Cum Laude

Skills
Python, JavaScript, TypeScript, React, FastAPI, Node.js, PostgreSQL, MongoDB,
Docker, Kubernetes, AWS, Git, Linux, Machine Learning, TensorFlow, Redis

Certifications
AWS Certified Solutions Architect - Professional (2022)
Google Cloud Professional Data Engineer (2021)

Languages
English (Native)
Hindi (Fluent)

Achievements
• Winner of Google Hackathon 2021 — built AI-powered accessibility tool
• Dean's List — 4 consecutive semesters at MIT
""".strip()


def run_tests():
    print("=" * 60)
    print("RESUME PARSER — PHASE 1-3 TEST GATE")
    print("=" * 60)

    # ── Test 1: TXT file ──────────────────────────────────────────────────────
    print("\n[TEST 1] Parsing plain-text resume...")
    result = parse_resume(SAMPLE_RESUME_TXT.encode("utf-8"), "resume.txt", include_raw=False)

    # Check metadata
    assert result["metadata"]["fileType"] == "txt", "fileType should be 'txt'"
    assert result["metadata"]["parserVersion"] == "1.0.0", "parserVersion missing"
    assert result["metadata"]["wordCount"] > 50, "wordCount too low"
    print("  ✓ metadata OK")

    # Check contact
    c = result["contact"]
    assert c["email"] == "john.doe@example.com", f"email wrong: {c['email']}"
    assert c["phone"] is not None, "phone missing"
    assert "linkedin.com" in (c["linkedin"] or ""), f"linkedin wrong: {c['linkedin']}"
    assert "github.com" in (c["github"] or ""), f"github wrong: {c['github']}"
    assert c["name"] is not None, "name not extracted"
    print(f"  ✓ contact OK — name={c['name']}, email={c['email']}, phone={c['phone']}")

    # Check experience
    exp = result["experience"]["entries"]
    assert len(exp) >= 2, f"Expected >=2 experience entries, got {len(exp)}"
    assert any("Google" in (e.get("company") or "") or "Google" in (e.get("title") or "") for e in exp), "Google not found in experience"
    assert result["experience"]["_derived"]["totalYearsExperience"] is not None, "totalYearsExperience missing"
    print(f"  ✓ experience OK — {len(exp)} entries, {result['experience']['_derived']['totalYearsExperience']} years")

    # Check education
    edu = result["education"]
    assert len(edu) >= 1, f"Expected >=1 education entry, got {len(edu)}"
    assert any("Bachelor" in (e.get("degree") or "") for e in edu), "Bachelor degree not found"
    print(f"  ✓ education OK — {len(edu)} entries")

    # Check skills
    skills = result["skills"]
    assert len(skills["all"]) >= 5, f"Expected >=5 skills, got {len(skills['all'])}"
    assert "programming_languages" in skills["byCategory"], "no programming_languages category"
    print(f"  ✓ skills OK — {len(skills['all'])} skills across {len(skills['byCategory'])} categories")

    # Check certifications
    certs = result["certifications"]
    assert len(certs) >= 1, f"Expected >=1 certification, got {len(certs)}"
    print(f"  ✓ certifications OK — {len(certs)} found")

    # Check languages
    langs = result["languages"]
    assert len(langs) >= 1, f"Expected >=1 language, got {len(langs)}"
    assert any(l["language"] == "English" for l in langs), "English not found"
    print(f"  ✓ languages OK — {len(langs)} found")

    # Check achievements
    achs = result["achievements"]
    assert len(achs) >= 1, f"Expected >=1 achievement, got {len(achs)}"
    print(f"  ✓ achievements OK — {len(achs)} found")

    # Check section_order is populated
    assert len(result["section_order"]) >= 3, "section_order too short"
    print(f"  ✓ section_order OK — {result['section_order']}")

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED — Phases 1-3 verified")
    print("=" * 60)

    # Print compact summary
    print("\n📄 PARSED OUTPUT PREVIEW:")
    preview = {
        "contact": {k: v for k, v in result["contact"].items() if not k.startswith("_")},
        "experience_count": len(result["experience"]["entries"]),
        "total_years": result["experience"]["_derived"]["totalYearsExperience"],
        "education_count": len(result["education"]),
        "skills_count": len(result["skills"]["all"]),
        "skill_categories": list(result["skills"]["byCategory"].keys()),
        "certs_count": len(result["certifications"]),
        "languages": [l["language"] for l in result["languages"]],
        "achievements_count": len(result["achievements"]),
    }
    print(json.dumps(preview, indent=2))


if __name__ == "__main__":
    try:
        run_tests()
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\n💥 UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
