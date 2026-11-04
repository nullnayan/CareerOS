"""Resolve a single local owner without password/session authentication."""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from db.models import User, WorkspaceSettings
from db.session import get_db


def get_workspace_owner(db: Session = Depends(get_db)) -> User:
    workspace = db.get(WorkspaceSettings, 1)
    if not workspace and db.get_bind().dialect.name == "postgresql":
        # First-visit requests may arrive together; only one may choose/create an owner.
        db.execute(text("SELECT pg_advisory_xact_lock(30103001)"))
        db.expire_all()
        workspace = db.get(WorkspaceSettings, 1)
    if workspace:
        owner = db.get(User, workspace.owner_id)
        if owner:
            return owner
        raise HTTPException(409, "The selected workspace owner no longer exists.")
    users = db.query(User).order_by(User.created_at).limit(2).all()
    if len(users) > 1:
        raise HTTPException(409, "Multiple accounts exist. Select your personal workspace in Settings.")
    owner = users[0] if users else User(email="personal@careeros.local")
    if not users:
        db.add(owner)
        db.flush()
    db.add(WorkspaceSettings(id=1, owner_id=owner.id))
    try:
        db.commit()
    except IntegrityError:
        # SQLite/test setups have no advisory lock; concurrent first loads still
        # converge on one workspace and roll back the losing temporary owner.
        db.rollback()
        workspace = db.get(WorkspaceSettings, 1)
        if not workspace:
            raise
        owner = db.get(User, workspace.owner_id)
    return owner
