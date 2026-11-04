"""
GitHub API endpoints.

/github/connect    — redirects user to GitHub OAuth consent screen
/github/callback   — handles OAuth code exchange, encrypts & stores token
/github/status     — checks if user has a connected GitHub account
/github/disconnect — removes the stored connection
/github/push       — creates repo + pushes files (called after chat confirmation)
"""

import os
import uuid
import logging
import secrets
import time
from threading import Lock
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from dotenv import load_dotenv

from db.session import get_db
from db.models import GitHubConnection, PushEvent
from core.workspace import get_workspace_owner as get_current_user
from core.encryption import encrypt_token, decrypt_token
from services.github_service import (
    exchange_code_for_token,
    get_user_profile,
    create_repository,
    push_files_to_repo,
)

load_dotenv()

router = APIRouter(prefix="/github", tags=["GitHub"])
_oauth_states = {}
_oauth_lock = Lock()
logger = logging.getLogger(__name__)

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


# ─── Request / Response models ──────────────────────────────────────

class PushRequest(BaseModel):
    repo_name: str
    description: str = ""
    private: bool = False
    files: List[dict]  # [{"path": "file.py", "content": "..."}]
    push_event_id: Optional[str] = None


class GitHubStatusResponse(BaseModel):
    connected: bool
    github_username: Optional[str] = None
    scope: Optional[str] = None
    connected_at: Optional[datetime] = None


class PushResponse(BaseModel):
    status: str
    repo_url: Optional[str] = None
    commit_sha: Optional[str] = None
    files_pushed: int = 0
    error: Optional[str] = None


# ─── Endpoints ──────────────────────────────────────────────────────

@router.get("/connect")
def connect_github(current_user=Depends(get_current_user)):
    """
    Step 1 of OAuth: redirect the user to GitHub's authorization page.
    After they approve, GitHub redirects them to /github/callback.
    """
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="GITHUB_CLIENT_ID is not configured in .env"
        )

    # Generate a random state for CSRF protection
    state = secrets.token_urlsafe(32)
    with _oauth_lock:
        now = time.monotonic()
        for key in list(_oauth_states):
            if _oauth_states[key][1] <= now:
                del _oauth_states[key]
        if len(_oauth_states) >= 32:
            raise HTTPException(429, "Too many pending GitHub connections. Try again later.")
        _oauth_states[state] = (current_user.id, now + 600)

    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={FRONTEND_URL}/github/callback"
        f"&scope=repo"
        f"&state={state}"
    )

    return {"auth_url": github_auth_url, "state": state}


@router.get("/callback")
def github_callback(
    code: str = Query(...),
    state: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Step 2 of OAuth: GitHub redirects here with a temporary code.
    We exchange it for an access token, encrypt it, and store it.
    """
    with _oauth_lock:
        pending = _oauth_states.pop(state, None) if state else None
    if not pending or pending[0] != current_user.id or pending[1] <= time.monotonic():
        raise HTTPException(400, "GitHub connection expired or state is invalid. Start Connect again.")
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="GitHub OAuth credentials not configured in .env"
        )

    user_id = current_user.id

    try:
        # Exchange code for token
        token_data = exchange_code_for_token(
            code=code,
            client_id=GITHUB_CLIENT_ID,
            client_secret=GITHUB_CLIENT_SECRET,
        )
        access_token = token_data["access_token"]
        scope = token_data.get("scope", "")

        # Fetch GitHub profile
        profile = get_user_profile(access_token)
        github_username = profile.get("login", "")

        # Encrypt and store
        encrypted = encrypt_token(access_token)

        # Upsert — update if exists, create if not
        existing = (
            db.query(GitHubConnection)
            .filter(GitHubConnection.user_id == user_id)
            .first()
        )

        if existing:
            existing.encrypted_access_token = encrypted
            existing.github_username = github_username
            existing.scope = scope
            existing.connected_at = datetime.utcnow()
        else:
            conn = GitHubConnection(
                user_id=user_id,
                encrypted_access_token=encrypted,
                github_username=github_username,
                scope=scope,
            )
            db.add(conn)

        db.commit()
        logger.info(f"GitHub connected for user {user_id} as @{github_username}")

        return {
            "status": "connected",
            "github_username": github_username,
        }

    except Exception as e:
        logger.error(f"GitHub OAuth callback failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=GitHubStatusResponse)
def github_status(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Check if the current user has a connected GitHub account."""
    user_id = current_user.id

    conn = (
        db.query(GitHubConnection)
        .filter(GitHubConnection.user_id == user_id)
        .first()
    )

    if not conn:
        return GitHubStatusResponse(connected=False)

    return GitHubStatusResponse(
        connected=True,
        github_username=conn.github_username,
        scope=conn.scope,
        connected_at=conn.connected_at,
    )


@router.delete("/disconnect")
def disconnect_github(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Remove the GitHub connection for the current user."""
    user_id = current_user.id

    conn = (
        db.query(GitHubConnection)
        .filter(GitHubConnection.user_id == user_id)
        .first()
    )

    if not conn:
        raise HTTPException(status_code=404, detail="No GitHub connection found.")

    db.delete(conn)
    db.commit()
    return {"status": "disconnected"}


@router.post("/push", response_model=PushResponse)
def push_to_github(request: PushRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """
    Execute the GitHub push: create repo (if needed) + push files.
    Called after the user confirms in the chat UI.
    """
    user_id = current_user.id

    # 1. Get the user's GitHub connection
    conn = (
        db.query(GitHubConnection)
        .filter(GitHubConnection.user_id == user_id)
        .first()
    )
    if not conn:
        raise HTTPException(
            status_code=400,
            detail="GitHub not connected. Please connect your GitHub account first."
        )

    access_token = decrypt_token(conn.encrypted_access_token)
    owner = conn.github_username

    # 2. Update push event status if provided
    push_event = None
    if request.push_event_id:
        push_event = db.get(PushEvent, request.push_event_id)
        if push_event:
            push_event.status = "confirmed"
            db.commit()

    try:
        # 3. Create the repository
        try:
            create_repository(
                access_token=access_token,
                repo_name=request.repo_name,
                description=request.description,
                private=request.private,
            )
        except ValueError:
            # Repo already exists — that's fine, we'll push to it
            logger.info(f"Repo {request.repo_name} already exists, pushing to it")

        # 4. Push files
        if not request.files:
            raise ValueError("No files to push")

        result = push_files_to_repo(
            access_token=access_token,
            owner=owner,
            repo_name=request.repo_name,
            files=request.files,
            commit_message=f"Add files via CareerOS: {request.description or request.repo_name}",
        )

        # 5. Update push event
        if push_event:
            push_event.status = "succeeded"
            push_event.repo_name = request.repo_name
            push_event.files = [f["path"] for f in request.files]
            db.commit()

        return PushResponse(
            status="success",
            repo_url=result["repo_url"],
            commit_sha=result["commit_sha"],
            files_pushed=result["files_pushed"],
        )

    except Exception as e:
        logger.error(f"GitHub push failed: {e}")

        if push_event:
            push_event.status = "failed"
            push_event.error_message = str(e)
            db.commit()

        return PushResponse(
            status="failed",
            error=str(e),
        )
