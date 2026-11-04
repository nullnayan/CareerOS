
from sqlalchemy.orm import Session
from db.session import SessionLocal
from db.models import ResumeVersion
from services.ats_scorer import score_resume_baseline
import json

db = SessionLocal()
resume = db.query(ResumeVersion).order_by(ResumeVersion.created_at.desc()).first()

result = score_resume_baseline(resume.structured_json, raw_text=resume.raw_text)
print('Score:', result['baseline_score'])
print('Issues:')
for issue in result['issues']:
    print('- ' + issue['issue'] + ' (' + str(issue.get('points_deducted', 0)) + ' pts)')

