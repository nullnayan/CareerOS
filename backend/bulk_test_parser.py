"""
Phase 7 — Bulk Testing & Verification
=====================================
Scans the `test_resumes/` directory for .pdf, .docx, and .txt files.
If directory doesn't exist or is empty, programmatically generates:
  - a mock DOCX resume (using python-docx)
  - a mock PDF resume (by duplicating the real one or creating a basic document)
  - a mock TXT resume

Parses all files, measures speed/completeness/quality, and reports summary stats.
Saves detailed log to `validation_report.json` without crashing on any single failure.
"""

import os
import sys
import time
import json
import traceback

sys.path.insert(0, ".")

from resume_parser.pipeline import parse_resume

TEST_DIR = "test_resumes"

def create_mock_resumes():
    """Programmatically generate a set of mock resumes for testing if none exist."""
    if not os.path.exists(TEST_DIR):
        os.makedirs(TEST_DIR)
        print(f"Created directory: {TEST_DIR}")
        
    # Copy the real PDF resume from parent if available
    parent_pdf = "../john_doe_resume.pdf"
    if os.path.exists(parent_pdf):
        import shutil
        shutil.copy(parent_pdf, os.path.join(TEST_DIR, "john_doe_resume.pdf"))
        print("Coopied john_doe_resume.pdf to test directory.")

    # 1. Create a mock DOCX resume
    docx_path = os.path.join(TEST_DIR, "jane_smith_resume.docx")
    if not os.path.exists(docx_path):
        try:
            from docx import Document
            doc = Document()
            doc.add_heading("Jane Smith", 0)
            doc.add_paragraph("jane.smith@example.com | 1-800-555-0199 | github.com/janesmith")
            
            doc.add_heading("Summary", level=1)
            doc.add_paragraph("Results-driven Product Manager with 5 years of experience leading cross-functional teams.")
            
            doc.add_heading("Experience", level=1)
            doc.add_paragraph("Product Manager at TechCorp")
            doc.add_paragraph("Feb 2021 - Present")
            doc.add_paragraph("- Led launch of 3 new SaaS features, increasing user engagement by 25%")
            doc.add_paragraph("- Managed product roadmap and coordinated with team of 12 developers")
            
            doc.add_paragraph("Associate PM at StartupInc")
            doc.add_paragraph("Jun 2019 - Jan 2021")
            doc.add_paragraph("- Wrote specifications and user stories, reducing dev cycle time by 15%")
            
            doc.add_heading("Education", level=1)
            doc.add_paragraph("Bachelor of Arts in Economics")
            doc.add_paragraph("Stanford University")
            doc.add_paragraph("2015 - 2019")
            doc.add_paragraph("GPA: 3.8/4.0")
            
            doc.add_heading("Skills", level=1)
            doc.add_paragraph("Product Strategy, Roadmap Development, Agile/Scrum, JIRA, SQL, Tableau, Figma")
            
            doc.add_heading("Certifications", level=1)
            doc.add_paragraph("Certified Scrum Product Owner (CSPO) - 2020")
            
            doc.add_heading("Languages", level=1)
            doc.add_paragraph("English (Native), Spanish (Conversational)")
            
            doc.save(docx_path)
            print(f"Generated mock DOCX: {docx_path}")
        except Exception as e:
            print(f"Failed to generate mock DOCX: {e}")

    # 2. Create a mock TXT resume
    txt_path = os.path.join(TEST_DIR, "bob_jones_resume.txt")
    if not os.path.exists(txt_path):
        content = """
Bob Jones
bob.jones@example.com | (555) 444-3322
Dallas, TX

Summary
Systems Administrator with expertise in Linux and AWS.

Work Experience
Senior SysAdmin | Dallas Solutions
Mar 2018 - Present
- Maintained 99.99% uptime for 200+ production servers
- Automated backups using bash scripting, saving 5 hours of manual work weekly
- Migrated legacy servers to AWS EC2 and S3

Education
Associate of Science in Network Administration
Dallas Community College
2014 - 2016

Skills
Linux, Bash, AWS, Docker, Git, Terraform, Network Security
"""
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(content.strip())
        print(f"Generated mock TXT: {txt_path}")

def run_bulk_test():
    create_mock_resumes()
    
    files = [f for f in os.listdir(TEST_DIR) if f.lower().endswith((".pdf", ".docx", ".txt"))]
    if not files:
        print("No test files found.")
        return
        
    print("\n" + "=" * 70)
    print(f"BULK TESTING PARSER ON {len(files)} RESUMES")
    print("=" * 70)
    
    results = []
    total_time = 0.0
    successful_parses = 0
    
    for filename in files:
        filepath = os.path.join(TEST_DIR, filename)
        print(f"Processing: {filename}...", end="", flush=True)
        
        start_time = time.time()
        try:
            with open(filepath, "rb") as f:
                file_bytes = f.read()
            
            parsed = parse_resume(file_bytes, filename, include_raw=False)
            elapsed = time.time() - start_time
            total_time += elapsed
            successful_parses += 1
            
            quality = parsed.get("quality", {})
            completeness = quality.get("completeness", {})
            overall_q = quality.get("quality", {}).get("overall", 0.0)
            overall_c = completeness.get("overall", 0.0)
            
            results.append({
                "filename": filename,
                "status": "success",
                "elapsed_seconds": round(elapsed, 3),
                "completeness_score": overall_c,
                "quality_score": overall_q,
                "word_count": parsed["metadata"].get("wordCount", 0),
                "skills_count": len(parsed["skills"].get("all", [])),
                "experience_entries": len(parsed["experience"].get("entries", []))
            })
            print(f" OK ({elapsed:.2f}s) | Comp: {overall_c:.2f} | Qual: {overall_q:.2f}")
            
        except Exception as e:
            elapsed = time.time() - start_time
            results.append({
                "filename": filename,
                "status": "error",
                "elapsed_seconds": round(elapsed, 3),
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            print(f" FAILED ({elapsed:.2f}s) | Error: {e}")
            
    # Compute aggregates
    success_rate = (successful_parses / len(files)) * 100
    avg_time = (total_time / successful_parses) if successful_parses > 0 else 0.0
    
    comp_scores = [r["completeness_score"] for r in results if r["status"] == "success"]
    qual_scores = [r["quality_score"] for r in results if r["status"] == "success"]
    
    avg_comp = sum(comp_scores) / len(comp_scores) if comp_scores else 0.0
    avg_qual = sum(qual_scores) / len(qual_scores) if qual_scores else 0.0
    
    # Save validation report
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_files": len(files),
            "successful_parses": successful_parses,
            "success_rate_pct": round(success_rate, 2),
            "average_parse_time_seconds": round(avg_time, 3),
            "average_completeness": round(avg_comp, 3),
            "average_quality": round(avg_qual, 3),
        },
        "results": results
    }
    
    report_path = "validation_report.json"
    with open(report_path, "w", encoding="utf-8") as rf:
        json.dump(report, rf, indent=2)
        
    print("\n" + "=" * 70)
    print("BULK TEST SUMMARY")
    print("=" * 70)
    print(f"Total Resumes Tested:   {len(files)}")
    print(f"Success Rate:           {success_rate:.1f}%")
    print(f"Avg Parse Time:         {avg_time:.3f}s")
    print(f"Avg Completeness:       {avg_comp:.2f}")
    print(f"Avg Quality Score:      {avg_qual:.2f}")
    print(f"Detailed Report Saved: {report_path}")
    print("=" * 70)

if __name__ == "__main__":
    run_bulk_test()
