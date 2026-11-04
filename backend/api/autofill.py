"""Explicit browser pairing and a narrow, revocable application-profile bridge."""
from datetime import datetime, timedelta
import hashlib
import re
import secrets
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import update
from sqlalchemy.orm import Session
from db.models import (AutofillProfile, ExtensionPairing, ExtensionCredential,
                       WorkspaceSettings, User, LatexTailoringRun)
from db.session import get_db
from core.workspace import get_workspace_owner
from jobs.connectors import public_url
from jobs.schemas import ManualJob

router = APIRouter(prefix="/autofill", tags=["Browser autofill"])
EXTENSION_ORIGIN = re.compile(r"^chrome-extension://[a-p]{32}$")


def hashed(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(default="", max_length=150)
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    location: str = Field(default="", max_length=200)
    linkedin: str = Field(default="", max_length=500)
    github: str = Field(default="", max_length=500)
    portfolio: str = Field(default="", max_length=500)

    @field_validator("full_name", "first_name", "last_name", "email", "phone", "location", "linkedin", "github", "portfolio")
    @classmethod
    def trim(cls, value):
        return value.strip()

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("linkedin", "github", "portfolio")
    @classmethod
    def web_url(cls, value):
        return public_url(value) if value else ""


def profile_data(db, user_id):
    row = db.get(AutofillProfile, user_id)
    return ProfileInput(**(row.data if row else {})).model_dump()


@router.get("/profile")
def profile(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    return profile_data(db, owner.id)


@router.put("/profile")
def save_profile(request: ProfileInput, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    row = db.get(AutofillProfile, owner.id)
    if not row:
        row = AutofillProfile(user_id=owner.id, data={}); db.add(row)
    row.data, row.updated_at = request.model_dump(), datetime.utcnow()
    db.commit()
    return row.data


@router.post("/pairings")
def create_pairing(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    # Replace outstanding invitations; only hashes are persisted.
    now = datetime.utcnow()
    db.query(ExtensionPairing).filter_by(user_id=owner.id, consumed_at=None).update({"consumed_at": now})
    code = secrets.token_urlsafe(24)
    expires = now + timedelta(minutes=5)
    db.add(ExtensionPairing(user_id=owner.id, code_hash=hashed(code), expires_at=expires))
    db.commit()
    return {"code": code, "expires_at": expires.isoformat()}


class PairInput(BaseModel):
    code: str = Field(min_length=20, max_length=128)
    label: str = Field(default="Browser extension", min_length=1, max_length=100)


def extension_origin(origin: str | None = Header(default=None)):
    if not origin or not EXTENSION_ORIGIN.fullmatch(origin):
        raise HTTPException(403, "This endpoint is only available to a paired Chromium extension.")
    return origin


@router.post("/pair")
def pair(request: PairInput, db: Session = Depends(get_db), origin=Depends(extension_origin)):
    now = datetime.utcnow()
    invitation = db.query(ExtensionPairing).filter_by(code_hash=hashed(request.code)).first()
    workspace = db.get(WorkspaceSettings, 1)
    if not invitation or invitation.consumed_at or invitation.expires_at <= now or not workspace or invitation.user_id != workspace.owner_id:
        raise HTTPException(401, "Pairing code is invalid, expired, or already used.")
    # Atomic consume prevents two concurrent pairings from reusing one invitation.
    consumed = db.execute(update(ExtensionPairing).where(ExtensionPairing.id == invitation.id,
        ExtensionPairing.consumed_at.is_(None), ExtensionPairing.expires_at > now).values(consumed_at=now))
    if consumed.rowcount != 1:
        db.rollback(); raise HTTPException(401, "Pairing code was already used.")
    token = secrets.token_urlsafe(40)
    credential = ExtensionCredential(user_id=invitation.user_id, token_hash=hashed(origin + "|" + token), label=request.label.strip() or "Browser extension")
    db.add(credential); db.commit()
    return {"token": token, "credential_id": credential.id}


def extension_owner(authorization: str | None = Header(default=None), x_careeros_extension: str | None = Header(default=None), origin: str | None = Header(default=None), db: Session = Depends(get_db)):
    # Chromium may omit Origin on privileged extension GET requests. Require an
    # explicit extension id and bind the bearer hash to the origin that paired.
    # A supplied Origin must also agree; a website origin can never use this bridge.
    extension = "chrome-extension://" + (x_careeros_extension or "")
    if not EXTENSION_ORIGIN.fullmatch(extension) or (origin is not None and origin != extension):
        raise HTTPException(403, "This endpoint is only available to a paired Chromium extension.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Pair the extension with CareerOS first.")
    token = authorization[7:]
    credential = db.query(ExtensionCredential).filter_by(token_hash=hashed(extension + "|" + token), revoked_at=None).first()
    workspace = db.get(WorkspaceSettings, 1)
    if not credential or not workspace or credential.user_id != workspace.owner_id:
        raise HTTPException(401, "Extension access was revoked or the personal workspace changed. Pair again.")
    owner = db.get(User, credential.user_id)
    if not owner: raise HTTPException(401, "Workspace owner no longer exists.")
    return owner


@router.get("/credentials")
def credentials(db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    return [{"id": row.id, "label": row.label, "created_at": row.created_at.isoformat(),
             "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None}
            for row in db.query(ExtensionCredential).filter_by(user_id=owner.id).order_by(ExtensionCredential.created_at.desc())]


@router.delete("/credentials/{identifier}")
def revoke(identifier: str, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    row = db.query(ExtensionCredential).filter_by(id=identifier, user_id=owner.id).first()
    if not row: raise HTTPException(404, "Extension not found.")
    row.revoked_at = datetime.utcnow(); db.commit()
    return {"revoked": True}


@router.get("/extension/profile")
def extension_profile(db: Session = Depends(get_db), owner=Depends(extension_owner)):
    return profile_data(db, owner.id)


@router.post("/extension/import")
def extension_import(request: ManualJob, db: Session = Depends(get_db), owner=Depends(extension_owner)):
    from api.jobs import import_job
    return import_job(request, db, owner)


@router.get("/extension/resumes")
def resumes(db: Session = Depends(get_db), owner=Depends(extension_owner)):
    return [{"id": run.id, "label": run.label, "created_at": run.created_at.isoformat()}
            for run in db.query(LatexTailoringRun).filter_by(user_id=owner.id, status="ready").order_by(LatexTailoringRun.created_at.desc()).limit(30)]


@router.get("/extension/resumes/{identifier}")
def resume_download(identifier: str, db: Session = Depends(get_db), owner=Depends(extension_owner)):
    from api.tailor import run_file
    return run_file(identifier, "pdf", True, db, owner)
