from db.session import SessionLocal
from db.models import ResumeVersion
from services.ats_scorer import score_resume_baseline

db = SessionLocal()
# Get the tailored resume version
r = db.query(ResumeVersion).filter(ResumeVersion.id == 'bd2ce8e5-68ed-408b-8df3-55c943e78dfb').first()
if not r:
    print("Resume not found!")
else:
    print("Scoring:", r.original_filename)
    res = score_resume_baseline(r.structured_json, r.raw_text)
    print("Baseline Score:", res.get("baseline_score"))
    print("\nIssues:")
    for issue in res.get("issues", []):
        print(f"- {issue['issue']} ({issue['points_deducted']} pts) - Category: {issue['category']}")
