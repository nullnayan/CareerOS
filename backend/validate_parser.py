"""Phase 4 + 5 validation: normalization and quality scoring."""
import sys, json
sys.path.insert(0, ".")

from resume_parser.pipeline import parse_resume

SAMPLE = b"""John Doe
john.doe@example.com | (555) 123-4567 | linkedin.com/in/johndoe | github.com/johndoe
San Francisco, CA

Summary
Experienced software engineer with 6+ years building scalable backend systems.

Experience

Software Engineer at Google
Jan 2020 - Present
- Led team of 5 engineers delivering distributed services handling 1M+ daily requests using Python and Kubernetes
- Reduced API latency by 40% through query optimization and Redis caching
- Drove migration from monolith to microservices, improving deployment frequency by 3x

Junior Developer at StartupXYZ
Jun 2017 - Dec 2019
- Developed React frontend for e-commerce platform serving 50K+ users
- Implemented REST APIs using Node.js and PostgreSQL, handling 10K requests/day
- Reduced bug backlog by 60% through systematic code review process

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
AWS Certified Solutions Architect (2022)
Google Cloud Professional (2021)

Languages
English (Native), Hindi (Fluent)

Achievements
Winner of Google Hackathon 2021
"""

result = parse_resume(SAMPLE, "resume.txt")

print("=== CONTACT (normalized) ===")
c = result["contact"]
print("  name:", c.get("name"))
print("  email:", c.get("email"))
print("  phone:", c.get("phone"))
print("  linkedin:", c.get("linkedin"))
print("  location:", c.get("location"))
print("  _confidence present:", "_confidence" in c)

print()
print("=== EDUCATION (normalized) ===")
for e in result["education"]:
    print("  degree:", e.get("degree"))
    print("  institution:", e.get("institution"))
    print("  gpa:", e.get("gpa"))
    print("  honors:", e.get("honors"))
    print("  _confidence present:", "_confidence" in e)

print()
print("=== EXPERIENCE (normalized) ===")
exp = result["experience"]
print("  entries:", len(exp["entries"]))
for e in exp["entries"]:
    print(f"  [{e.get('title')} @ {e.get('company')}]")
    print(f"    {e.get('startDate')} -> {e.get('endDate')} (isCurrent={e.get('isCurrent')})")
    print(f"    bullets: {len(e.get('bullets', []))}")
    print(f"    _confidence present:", "_confidence" in e)
    print(f"    _raw present:", "_raw" in e)

print()
print("=== SKILLS (normalized) ===")
s = result["skills"]
print("  totalCount:", s.get("totalCount"))
print("  categories:", list(s.get("byCategory", {}).keys()))

print()
print("=== QUALITY REPORT ===")
q = result["quality"]
print("  completeness:", q["completeness"])
print("  quality:", q["quality"])
print("  flags:")
for f in q["flags"]:
    print(f"    [{f['type'].upper()}] {f['field']}: {f['message']}")

print()
print("=== ASSERTIONS ===")

# Phase 4 assertions
assert "_confidence" not in result["contact"], "_confidence should be removed from contact"
assert isinstance(result["contact"].get("location"), dict), "location should be a dict"
assert result["contact"]["location"]["city"] == "San Francisco", f"city wrong: {result['contact']['location']}"
assert result["education"][0]["gpa"]["score"] == 3.9, f"GPA score wrong: {result['education'][0]['gpa']}"
assert result["education"][0]["gpa"]["scale"] == 4.0, f"GPA scale wrong"
assert "_confidence" not in result["education"][0], "education _confidence should be removed"
assert "_raw" not in result["experience"]["entries"][0], "experience _raw should be removed"
assert result["skills"]["totalCount"] >= 5, "skills totalCount missing"

# Phase 5 assertions
assert "quality" in result, "quality block missing"
assert "completeness" in result["quality"], "completeness missing"
assert result["quality"]["completeness"]["overall"] > 0.3, "completeness too low"
assert result["quality"]["quality"]["overall"] >= 0.0, "quality score invalid"
assert isinstance(result["quality"]["flags"], list), "flags should be a list"
assert result["quality"]["quality"]["totalYearsExperience"] is not None, "totalYears missing"

print("ALL ASSERTIONS PASSED - Phases 4 and 5 OK")
print()
print("Completeness overall:", result["quality"]["completeness"]["overall"])
print("Quality overall:     ", result["quality"]["quality"]["overall"])
print("Has quantified impact:", result["quality"]["quality"]["hasQuantifiedImpact"])
print("Bullet strength:     ", result["quality"]["quality"]["bulletStrength"])
print("Flag count:          ", len(result["quality"]["flags"]))
