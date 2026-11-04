from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from core.workspace import get_workspace_owner
from db.models import User, WorkspaceSettings
from db.session import get_db

router = APIRouter(prefix="/workspace", tags=["Personal workspace"])


@router.get("/ai-routing")
def ai_routing(owner=Depends(get_workspace_owner)):
    from core.groq_keys import routing_status
    from core.agent_models import AGENT_MODELS
    from services.local_embeddings import MODEL_NAME
    return {"provider": "Groq", "groups": routing_status(),
            "models": {task: model for task, (_, model) in AGENT_MODELS.items()},
            "embeddings": {"provider": "local", "model": MODEL_NAME, "requires_key": False}}


@router.get("/owners")
def owners(db: Session = Depends(get_db)):
    if db.get(WorkspaceSettings, 1):
        return []
    return [{"id": u.id, "email": u.email} for u in db.query(User).order_by(User.created_at).all()]


class OwnerSelection(BaseModel):
    owner_id: str | None = None
    create_new: bool = False


@router.post("/owner")
def select_owner(request: OwnerSelection, db: Session = Depends(get_db)):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(30103001)"))
    if db.get(WorkspaceSettings, 1):
        raise HTTPException(409, "Workspace owner is already selected.")
    if bool(request.owner_id) == request.create_new:
        raise HTTPException(422, "Choose an existing owner or create a fresh workspace.")
    owner = User(email="personal@careeros.local") if request.create_new else db.get(User, request.owner_id)
    if not owner:
        raise HTTPException(404, "Owner not found.")
    if request.create_new:
        db.add(owner)
        db.flush()
    db.add(WorkspaceSettings(id=1, owner_id=owner.id))
    db.commit()
    return {"id": owner.id, "email": owner.email}


@router.get("")
def workspace(owner=Depends(get_workspace_owner)):
    return {"id": owner.id, "email": owner.email, "mode": "personal", "career_level": owner.career_level,
            "target_role": owner.target_role, "locale": owner.locale}


class ProfileUpdate(BaseModel):
    career_level: str | None = None
    target_role: str | None = None
    locale: str | None = None


@router.patch("/profile")
def profile(request: ProfileUpdate, db: Session = Depends(get_db), owner=Depends(get_workspace_owner)):
    if request.career_level and request.career_level not in {"student", "entry", "mid", "senior", "exec"}:
        raise HTTPException(422, "Invalid career level.")
    for key, value in request.model_dump(exclude_none=True).items():
        setattr(owner, key, value)
    db.commit()
    return {"status": "success", **request.model_dump()}
