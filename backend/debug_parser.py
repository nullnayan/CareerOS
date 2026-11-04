"""Debug the experience section segmentation."""
import sys
sys.path.insert(0, ".")
from resume_parser import extractor, segmenter
from resume_parser.parsers import experience_parser

SAMPLE = b"""John Doe
john.doe@example.com | (555) 123-4567 | linkedin.com/in/johndoe | github.com/johndoe
San Francisco, CA

Summary
Experienced software engineer with 6+ years building scalable backend systems.

Experience

Software Engineer at Google
Jan 2020 - Present
- Built distributed services using Python and Kubernetes
- Reduced API latency by 40% through caching with Redis

Junior Developer at StartupXYZ
Jun 2017 - Dec 2019
- Developed React frontend for e-commerce platform
- Implemented REST APIs using Node.js and PostgreSQL

Education

Bachelor of Science in Computer Science
Massachusetts Institute of Technology
2013 - 2017
GPA: 3.9/4.0

Skills
Python, JavaScript, React, FastAPI, Node.js, PostgreSQL, Docker, Kubernetes, AWS, Git
"""

extraction = extractor.extract(SAMPLE, "resume.txt")
sections = segmenter.segment(extraction["rawText"])

print("=== EXPERIENCE SECTION TEXT ===")
print(repr(sections.get("experience", "MISSING")))
print()
print("=== UNKNOWN SECTIONS ===")
for k, v in sections.get("unknown_sections", {}).items():
    print(f"  [{k}]: {repr(v[:80])}")
print()
print("=== SECTION ORDER ===")
print(sections.get("section_order", []))

# Now parse the experience
exp_text = sections.get("experience", "")
print()
print("=== EXPERIENCE PARSE RESULT ===")
result = experience_parser.parse(exp_text)
print("entries:", len(result["entries"]))
for e in result["entries"]:
    print(" -", e.get("title"), "|", e.get("company"), "|", e.get("startDate"), "-", e.get("endDate"))
