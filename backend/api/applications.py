"""Personal application ledger. Only explicit user edits change application status."""
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from core.workspace import get_workspace_owner
from db.session import get_db
from db.models import JobApplication, ApplicationEvent, JobPosting, LatexTailoringRun

router = APIRouter(prefix="/applications", tags=["Applications"])
Status = Literal["planned", "applied", "interview", "offer", "rejected", "withdrawn"]
STATUSES = {"planned", "applied", "interview", "offer", "rejected", "withdrawn"}


class CreateApplication(BaseModel):
    job_id: str = Field(min_length=1, max_length=36)
    tailoring_run_id: str | None = Field(default=None, max_length=36)


class UpdateApplication(BaseModel):
    status: Status | None = None
    notes: str | None = Field(default=None, max_length=10000)
    next_action_at: datetime | None = None
    applied_at: datetime | None = None
    tailoring_run_id: str | None = Field(default=None, max_length=36)
    confirmed_submitted: bool = False

    @field_validator("applied_at", "next_action_at")
    @classmethod
    def utc_dates(cls, value):
        if value and value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


def owned(db, identifier, user_id):
    row = db.query(JobApplication).filter_by(id=identifier, user_id=user_id).first()
    if not row:
        raise HTTPException(404, "Application not found.")
    return row


def validate_resume(db, identifier, job, user_id):
    if identifier is None:
        return
    run = db.query(LatexTailoringRun).filter_by(id=identifier, user_id=user_id, status="ready").first()
    if not run:
        raise HTTPException(422, "Choose a ready resume from your workspace.")
    if run.job_description != job.description:
        raise HTTPException(409, "That resume was prepared for a different job description. Prepare a matching resume first.")


def serialize(db, row, include_history=False):
    job = db.get(JobPosting, row.job_id)
    run = db.get(LatexTailoringRun, row.tailoring_run_id) if row.tailoring_run_id else None
    result = {"id": row.id, "job_id": row.job_id, "status": row.status, "notes": row.notes,
              "title": job.title, "company": job.company, "location": job.location, "apply_url": job.apply_url,
              "job_status": job.status, "applied_at": row.applied_at.isoformat() if row.applied_at else None,
              "next_action_at": row.next_action_at.isoformat() if row.next_action_at else None,
              "tailoring_run_id": row.tailoring_run_id,
              "resume_pdf_url": f"/tailor/runs/{run.id}/pdf" if run and run.status == "ready" else None,
              "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}
    if include_history:
        result["history"] = [{"id": event.id, "event_type": event.event_type, "from_status": event.from_status,
                              "to_status": event.to_status, "detail": event.detail, "created_at": event.created_at.isoformat()}
                             for event in db.query(ApplicationEvent).filter_by(application_id=row.id, user_id=row.user_id)
                             .order_by(ApplicationEvent.created_at, ApplicationEvent.id)]
    return result


@router.get("")
def list_applications(status: str = "all", q: str = "", db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    if status != "all" and status not in STATUSES:
        raise HTTPException(422, "Choose a supported application status.")
    rows = db.query(JobApplication).filter_by(user_id=owner.id).order_by(JobApplication.updated_at.desc()).all()
    counts = {value: sum(row.status == value for row in rows) for value in sorted(STATUSES)}
    items = [serialize(db, row) for row in rows if status == "all" or row.status == status]
    if q:
        items = [item for item in items if q.lower() in f"{item['title']} {item['company']} {item['location']}".lower()]
    return {"items": items, "counts": counts, "total": len(items)}


@router.post("")
def create_application(request: CreateApplication, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    job = db.query(JobPosting).filter_by(id=request.job_id, user_id=owner.id).first()
    if not job:
        raise HTTPException(404, "Job not found.")
    existing = db.query(JobApplication).filter_by(user_id=owner.id, job_id=job.id).first()
    if existing:
        return serialize(db, existing, True)
    validate_resume(db, request.tailoring_run_id, job, owner.id)
    row = JobApplication(user_id=owner.id, job_id=job.id, status="planned", notes="", tailoring_run_id=request.tailoring_run_id)
    db.add(row)
    try:
        db.flush()
        db.add(ApplicationEvent(application_id=row.id, user_id=owner.id, event_type="created", to_status="planned", detail={}))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(JobApplication).filter_by(user_id=owner.id, job_id=job.id).first()
        if not existing:
            raise
        return serialize(db, existing, True)
    return serialize(db, row, True)


@router.get("/{identifier}")
def application_detail(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    return serialize(db, owned(db, identifier, owner.id), True)


@router.patch("/{identifier}")
def update_application(identifier: str, request: UpdateApplication, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    row = owned(db, identifier, owner.id)
    fields = request.model_fields_set
    if "status" in fields and request.status is None:
        raise HTTPException(422, "Application status cannot be empty.")
    if "notes" in fields and request.notes is None:
        raise HTTPException(422, "Notes must be text.")
    if request.status == "applied" and row.status != "applied" and not request.confirmed_submitted:
        raise HTTPException(409, "Confirm that you submitted the application before marking it applied.")
    if "applied_at" in fields and request.applied_at and request.applied_at > datetime.utcnow():
        raise HTTPException(422, "Submission date cannot be in the future.")
    if "applied_at" in fields and request.applied_at and row.applied_at is None and not request.confirmed_submitted:
        raise HTTPException(409, "Confirm submission before recording a submission date.")
    if "tailoring_run_id" in fields:
        validate_resume(db, request.tailoring_run_id, db.get(JobPosting, row.job_id), owner.id)
    previous = row.status
    changes = []
    for field in ("status", "notes", "next_action_at", "applied_at", "tailoring_run_id"):
        if field in fields and getattr(row, field) != getattr(request, field):
            setattr(row, field, getattr(request, field)); changes.append(field)
    if request.status == "applied" and row.applied_at is None:
        row.applied_at = datetime.utcnow(); changes.append("applied_at")
    if changes:
        row.updated_at = datetime.utcnow()
        db.add(ApplicationEvent(application_id=row.id, user_id=owner.id,
                event_type="status_changed" if previous != row.status else "updated", from_status=previous,
                to_status=row.status, detail={"changed_fields": list(dict.fromkeys(changes)), "submission_confirmed": request.confirmed_submitted}))
        db.commit()
    return serialize(db, row, True)
