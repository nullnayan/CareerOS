from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from db.session import get_db
from db.models import Suggestion
from core.workspace import get_workspace_owner as get_current_user
import logging

router = APIRouter(prefix="/suggestions", tags=["Suggestions"])
logger = logging.getLogger(__name__)


class SuggestionResponse(BaseModel):
    id: str
    type: str
    reason: str
    confidence_score: Optional[float]
    expected_impact: Optional[str]
    status: str
    payload: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class SuggestionUpdateRequest(BaseModel):
    status: str
    edited_payload: Optional[Dict[str, Any]] = None


@router.get("/", response_model=List[SuggestionResponse])
def get_suggestions(status: Optional[str] = None, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Retrieve suggestions for the current user, optionally filtered by status."""
    user_id = current_user.id
    query = db.query(Suggestion).filter(Suggestion.user_id == user_id)
    
    if status:
        query = query.filter(Suggestion.status == status)
        
    # Order by newest first
    suggestions = query.order_by(Suggestion.created_at.desc()).all()
    return suggestions


@router.patch("/{suggestion_id}", response_model=SuggestionResponse)
def update_suggestion(suggestion_id: str, request: SuggestionUpdateRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Update the status of a suggestion (accept, reject, or edit)."""
    user_id = current_user.id
    suggestion = db.query(Suggestion).filter(
        Suggestion.id == suggestion_id, 
        Suggestion.user_id == user_id
    ).first()
    
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
        
    valid_statuses = ["pending", "accepted", "rejected", "edited"]
    if request.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
        
    suggestion.status = request.status
    
    # If the status is changing from pending, set resolved_at
    if request.status != "pending" and not suggestion.resolved_at:
        suggestion.resolved_at = datetime.utcnow()
        
    if request.edited_payload:
        suggestion.payload = request.edited_payload
        
    try:
        db.commit()
        db.refresh(suggestion)
        return suggestion
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update suggestion: {e}")
        raise HTTPException(status_code=500, detail="Could not update suggestion.")
