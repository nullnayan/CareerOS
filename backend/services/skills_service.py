from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from db.models import Skill
import logging

logger = logging.getLogger(__name__)

def extract_and_upsert_skills(db: Session, user_id: int, resume_id: int, parsed_data: dict):
    """
    Extracts skills from the parsed resume JSON and upserts them into the skills table.
    """
    raw_skills = parsed_data.get("skills", [])
    
    if not raw_skills:
        logger.info(f"No skills found in resume {resume_id} for user {user_id}")
        return

    skill_records = []
    for skill in raw_skills:
        # Handle cases where the AI returns a list of strings vs a list of dictionaries
        skill_name = skill if isinstance(skill, str) else skill.get("name", "")
        if not skill_name:
            continue
            
        skill_records.append({
            "user_id": user_id,
            "name": skill_name.strip(),
            "source_resume_id": resume_id,
            "confidence": 0.8  # Default confidence
        })

    if not skill_records:
        return

    # PostgreSQL specific bulk upsert
    stmt = insert(Skill).values(skill_records)

    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=['user_id', 'name'], 
        set_={
            'source_resume_id': stmt.excluded.source_resume_id,
            'confidence': stmt.excluded.confidence
        }
    )

    try:
        db.execute(upsert_stmt)
        db.commit()
        logger.info(f"Successfully upserted {len(skill_records)} skills for user {user_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to upsert skills: {str(e)}")
        raise e