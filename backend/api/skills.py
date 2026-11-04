from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from db.session import get_db
from db.models import Skill
from core.workspace import get_workspace_owner as get_current_user
import logging

router = APIRouter(prefix="/skills", tags=["Skills"])
logger = logging.getLogger(__name__)


class SkillResponse(BaseModel):
    id: str
    name: str
    source_resume_id: Optional[str]
    confidence: Optional[float]
    first_seen_at: datetime

    class Config:
        from_attributes = True


class SkillCreateRequest(BaseModel):
    name: str


class SkillBatchCreateRequest(BaseModel):
    skills: List[str]
    source_resume_id: Optional[str] = None


@router.get("/", response_model=List[SkillResponse])
def get_skills(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Retrieve all deduplicated skills for the current user."""
    user_id = current_user.id
    skills = db.query(Skill).filter(Skill.user_id == user_id).all()
    return skills


@router.post("/", response_model=SkillResponse)
def add_skill(request: SkillCreateRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Manually add a skill to the inventory."""
    user_id = current_user.id
    
    # Check if skill already exists for this user (case-insensitive)
    existing_skill = db.query(Skill).filter(
        Skill.user_id == user_id,
        Skill.name.ilike(request.name.strip())
    ).first()

    if existing_skill:
        raise HTTPException(status_code=400, detail="Skill already exists in your inventory.")

    new_skill = Skill(
        user_id=user_id,
        name=request.name.strip(),
        confidence=1.0  # Manually added, so confidence is 100%
    )
    
    db.add(new_skill)
    try:
        db.commit()
        db.refresh(new_skill)
        return new_skill
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to add skill: {e}")
        raise HTTPException(status_code=500, detail="Could not add skill.")


@router.post("/batch", response_model=List[SkillResponse])
def add_skills_batch(request: SkillBatchCreateRequest, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Manually add multiple skills to the inventory at once."""
    user_id = current_user.id
    
    # Get existing skills for user (case-insensitive check handled below)
    existing_skills = db.query(Skill).filter(Skill.user_id == user_id).all()
    existing_skill_names = {s.name.lower() for s in existing_skills}
    
    new_skills = []
    for skill_name in request.skills:
        clean_name = skill_name.strip()
        if not clean_name or clean_name.lower() in existing_skill_names:
            continue
            
        new_skill = Skill(
            user_id=user_id,
            name=clean_name,
            source_resume_id=request.source_resume_id,
            confidence=1.0
        )
        db.add(new_skill)
        new_skills.append(new_skill)
        existing_skill_names.add(clean_name.lower())
        
    try:
        db.commit()
        for skill in new_skills:
            db.refresh(skill)
        return new_skills
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to add batch skills: {e}")
        raise HTTPException(status_code=500, detail="Could not add skills in batch.")


@router.delete("/{skill_id}")
def delete_skill(skill_id: str, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Remove a skill from the inventory."""
    user_id = current_user.id
    skill = db.query(Skill).filter(Skill.id == skill_id, Skill.user_id == user_id).first()
    
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
        
    db.delete(skill)
    db.commit()
    return {"status": "success", "message": f"Skill '{skill.name}' removed."}
