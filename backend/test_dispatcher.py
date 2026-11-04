import os
import sys
import json
from sqlalchemy.orm import Session
from db.session import SessionLocal
from db.models import ResumeVersion
from services.ats_scorer import score_resume_baseline
from ats_fixers.dispatcher import dispatch

def test_dispatcher(resume_id: str):
    db = SessionLocal()
    try:
        resume = db.get(ResumeVersion, resume_id)
        if not resume:
            print(f"Resume {resume_id} not found.")
            return

        print(f"Testing dispatcher on Resume {resume_id}...")
        
        # 1. Run ATS Scorer
        ats_result = score_resume_baseline(resume.structured_json, raw_text=resume.raw_text)
        print(f"Current ATS Score: {ats_result.get('baseline_score')}/100")
        
        # 2. Run Dispatcher in auto_improve mode
        print("\n--- AUTO IMPROVE MODE ---")
        changes_auto = dispatch(ats_result, resume.structured_json, mode="auto_improve")
        
        for category, changes in changes_auto.items():
            print(f"\nCategory: {category}")
            for c in changes:
                print(f"  [{c['type'].upper()}] {c['field']}")
                print(f"  Orig: {c['original']}")
                print(f"  Prop: {c['proposed']}")
                print(f"  Rsn : {c['reason']}")

        # 3. Run Dispatcher in custom mode (run everything)
        print("\n--- RUN ALL FIXERS MODE ---")
        changes_all = dispatch(ats_result, resume.structured_json, mode="all")
        
        for category, changes in changes_all.items():
            if category in changes_auto:
                continue # skip printing again
            print(f"\nCategory: {category}")
            for c in changes:
                print(f"  [{c['type'].upper()}] {c['field']}")
                print(f"  Orig: {c['original']}")
                print(f"  Prop: {c['proposed']}")
                print(f"  Rsn : {c['reason']}")
                
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_dispatcher.py <resume_id>")
    else:
        test_dispatcher(sys.argv[1])
