"""
Verification test for the deterministic ATS scoring engine.
Tests:
1. Determinism (10 runs produce the exact same score)
2. Sub-scores are within 0-100
3. Issues list is well-formed
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.ats_scorer import score_resume_baseline, score_resume_targeted

# A realistic resume JSON structure
SAMPLE_RESUME = {
    "contact": {
        "name": "Nayan Kumar",
        "email": "nayan@example.com",
        "phone": "+91-9876543210",
        "location": "Dehradun, India",
        "linkedin": "linkedin.com/in/nayankumar",
        "github": "github.com/nayankumar"
    },
    "summary": "Full-stack developer with experience in building modern web applications using React, Node.js, and Python. Passionate about clean code and scalable architecture.",
    "education": [
        {
            "institution": "Indian Institute of Technology",
            "degree": "Bachelor of Technology",
            "field": "Computer Science",
            "graduation_date": "May 2025"
        }
    ],
    "experience": [
        {
            "company": "Tech Startup XYZ",
            "title": "Software Engineering Intern",
            "start_date": "Jan 2024",
            "end_date": "Jun 2024",
            "bullet_points": [
                "Developed a real-time notification system using WebSockets, serving 5000+ daily active users",
                "Optimized API response time by 40% through query optimization and Redis caching",
                "Built responsive UI components using React and TypeScript, improving user engagement by 25%"
            ]
        },
        {
            "company": "Freelance",
            "title": "Web Developer",
            "start_date": "Jul 2023",
            "end_date": "Dec 2023",
            "bullet_points": [
                "Designed and deployed 3 production websites for local businesses using Next.js and Tailwind CSS",
                "Implemented SEO optimizations that increased organic traffic by 60% within 3 months"
            ]
        }
    ],
    "projects": [
        {
            "name": "CareerOS",
            "description": "AI-powered career management platform with resume parsing, ATS analysis, and job matching",
            "bullet_points": [
                "Architected a full-stack application using Next.js, FastAPI, and PostgreSQL",
                "Integrated multiple AI models (Llama 3.3, Gemini) for resume analysis and scoring",
                "Implemented a vector-based RAG system using Qdrant for intelligent career Q&A"
            ],
            "date": "2025"
        }
    ],
    "skills": [
        "Python", "JavaScript", "TypeScript", "React", "Next.js", "Node.js",
        "FastAPI", "Django", "PostgreSQL", "MongoDB", "Redis", "Docker",
        "Git", "GitHub", "Linux", "AWS", "Tailwind CSS", "HTML", "CSS"
    ]
}

SAMPLE_RAW_TEXT = """
Nayan Kumar
nayan@example.com | +91-9876543210 | Dehradun, India
LinkedIn: linkedin.com/in/nayankumar | GitHub: github.com/nayankumar

SUMMARY
Full-stack developer with experience in building modern web applications using React, Node.js, and Python.

EXPERIENCE
Software Engineering Intern | Tech Startup XYZ | Jan 2024 - Jun 2024
- Developed a real-time notification system using WebSockets, serving 5000+ daily active users
- Optimized API response time by 40% through query optimization and Redis caching
- Built responsive UI components using React and TypeScript, improving user engagement by 25%

Web Developer | Freelance | Jul 2023 - Dec 2023
- Designed and deployed 3 production websites for local businesses using Next.js and Tailwind CSS
- Implemented SEO optimizations that increased organic traffic by 60% within 3 months

PROJECTS
CareerOS | 2025
- Architected a full-stack application using Next.js, FastAPI, and PostgreSQL
- Integrated multiple AI models for resume analysis and scoring
- Implemented a vector-based RAG system using Qdrant for intelligent career Q&A

EDUCATION
Bachelor of Technology in Computer Science | Indian Institute of Technology | May 2025

SKILLS
Python, JavaScript, TypeScript, React, Next.js, Node.js, FastAPI, Django, PostgreSQL, MongoDB, Redis, Docker, Git, GitHub, Linux, AWS, Tailwind CSS, HTML, CSS
"""

SAMPLE_JD = """
Senior Full Stack Engineer

We are looking for a Senior Full Stack Engineer to join our team. You will:
- Build and maintain web applications using React, TypeScript, and Node.js
- Design and implement REST APIs and microservices using Python/FastAPI
- Work with PostgreSQL and Redis for data storage and caching
- Deploy and manage applications on AWS (EC2, S3, Lambda, ECS)
- Use Docker and Kubernetes for containerization
- Write clean, testable code with CI/CD pipelines
- Collaborate with product and design teams

Requirements:
- 3+ years of experience in full-stack development
- Proficiency in React, TypeScript, Python, and Node.js
- Experience with AWS cloud services
- Strong understanding of REST APIs and microservices
- Experience with Docker and Kubernetes
- Familiarity with PostgreSQL and Redis
- Experience with CI/CD tools (GitHub Actions, Jenkins)
- Strong problem-solving and communication skills
"""


def test_baseline():
    print("=" * 60)
    print("TEST 1: BASELINE SCORING")
    print("=" * 60)

    result = score_resume_baseline(SAMPLE_RESUME, SAMPLE_RAW_TEXT)

    print(f"\n  Baseline Score: {result['baseline_score']}")
    print(f"\n  Score Breakdown:")
    for key, val in result['score_breakdown'].items():
        bar = '#' * (val // 5) + '-' * (20 - val // 5)
        print(f"    {key:30s} {bar} {val}/100")

    print(f"\n  Summary: {result['summary']}")
    print(f"\n  Issues ({len(result['issues'])} found):")
    for i, issue in enumerate(result['issues'][:5], 1):
        print(f"    {i}. [{issue['severity'].upper():6s}] {issue['issue']}")
        print(f"       -> {issue['suggestion']}")

    # Verify sub-scores are 0-100
    for key, val in result['score_breakdown'].items():
        assert 0 <= val <= 100, f"Sub-score {key} = {val} is out of range!"
    print("\n  [OK] All sub-scores are within 0-100")

    # Verify determinism
    scores = []
    for _ in range(10):
        r = score_resume_baseline(SAMPLE_RESUME, SAMPLE_RAW_TEXT)
        scores.append(r['baseline_score'])
    assert len(set(scores)) == 1, f"Non-deterministic scores: {scores}"
    print(f"  ✓ 10 runs all produced the same score: {scores[0]}")

    return result['baseline_score']


def test_targeted():
    print("\n" + "=" * 60)
    print("TEST 2: TARGETED SCORING (vs Job Description)")
    print("=" * 60)

    result = score_resume_targeted(SAMPLE_RESUME, SAMPLE_JD, SAMPLE_RAW_TEXT)

    print(f"\n  Match Score: {result['match_score']}")
    print(f"\n  Score Breakdown:")
    for key, val in result['score_breakdown'].items():
        bar = '#' * (val // 5) + '-' * (20 - val // 5)
        print(f"    {key:30s} {bar} {val}/100")

    print(f"\n  Matched Keywords ({len(result['matched_keywords'])}):")
    print(f"    {', '.join(result['matched_keywords'][:15])}")
    print(f"\n  Missing Keywords ({len(result['missing_keywords'])}):")
    print(f"    {', '.join(result['missing_keywords'][:15])}")

    print(f"\n  Issues ({len(result['issues'])} found):")
    for i, issue in enumerate(result['issues'][:5], 1):
        print(f"    {i}. [{issue['severity'].upper():6s}] {issue['issue']}")

    # Verify sub-scores
    for key, val in result['score_breakdown'].items():
        assert 0 <= val <= 100, f"Sub-score {key} = {val} is out of range!"
    print("\n  ✓ All sub-scores are within 0-100")

    # Verify determinism
    scores = []
    for _ in range(10):
        r = score_resume_targeted(SAMPLE_RESUME, SAMPLE_JD, SAMPLE_RAW_TEXT)
        scores.append(r['match_score'])
    assert len(set(scores)) == 1, f"Non-deterministic scores: {scores}"
    print(f"  ✓ 10 runs all produced the same score: {scores[0]}")

    return result['match_score']


def test_layout_checks():
    print("\n" + "=" * 60)
    print("TEST 3: FORMATTING LAYOUT CHECKS")
    print("=" * 60)

    layout_resume = SAMPLE_RESUME.copy()
    layout_resume["formatting_metadata"] = {
        "has_columns": True,
        "has_tables": True,
        "is_scanned_pdf": False
    }

    result = score_resume_baseline(layout_resume, SAMPLE_RAW_TEXT)
    print(f"  Formatting Score with Columns + Tables: {result['score_breakdown']['formatting_compatibility']}/100")
    
    assert result['score_breakdown']['formatting_compatibility'] == 57, f"Expected formatting score 57, got {result['score_breakdown']['formatting_compatibility']}"
    
    issues_found = [i["issue"] for i in result["issues"]]
    assert "Multi-column layout detected" in issues_found
    assert "Tables detected in resume layout" in issues_found
    print("  ✓ Formatting layout penalties and issues verified successfully!")


if __name__ == "__main__":
    baseline = test_baseline()
    targeted = test_targeted()
    test_layout_checks()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print(f"  Baseline Score: {baseline}")
    print(f"  Targeted Score: {targeted}")
    print("=" * 60)
