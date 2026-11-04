"""Rebuild the selected workspace's local vectors; never delete legacy vectors."""
from db.session import SessionLocal
from db.models import ResumeVersion
from core.workspace import get_workspace_owner
from services.vector_store_service import embed_and_upsert_resume, ensure_collection


def main():
    ensure_collection()
    total = 0
    with SessionLocal() as db:
        owner = get_workspace_owner(db)
        resumes = db.query(ResumeVersion).filter(ResumeVersion.user_id == owner.id, ResumeVersion.raw_text.isnot(None)).all()
        for resume in resumes:
            total += embed_and_upsert_resume(owner.id, resume.id, resume.raw_text, resume.original_filename)
    print(f"Reindexed {len(resumes)} saved resumes into {total} local embedding chunks. Legacy collection preserved.")


if __name__ == "__main__":
    main()
