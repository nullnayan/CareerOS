import sys
from fastapi.testclient import TestClient
from main import app
from db.session import SessionLocal
from db.models import User, ResumeVersion
from api.auth import get_current_user
import traceback

def test():
    try:
        db = SessionLocal()
        # Find any user with a resume
        resume = db.query(ResumeVersion).first()
        if not resume:
            print("No resume found in db to test with")
            return
            
        user = db.query(User).filter(User.id == resume.user_id).first()
        
        # Override dependency
        app.dependency_overrides[get_current_user] = lambda: user
        
        client = TestClient(app)
        print(f"Testing improve_propose with resume_id: {resume.id}")
        response = client.post("/improve/propose", json={"resume_id": str(resume.id), "mode": "auto_improve"})
        
        print("Status Code:", response.status_code)
        if response.status_code != 200:
            print(response.json())
    except Exception as e:
        traceback.print_exc()

test()
