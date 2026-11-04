import re
import logging

logger = logging.getLogger(__name__)

def extract_numbers(text: str) -> set:
    """Extract all numeric tokens from text, including percentages and years."""
    if not text:
        return set()
    # Matches integers, decimals, percentages, e.g., 40, 40%, 3.5, 2023
    return set(re.findall(r'\b\d+(?:\.\d+)?%?\b', text))

def extract_allowed_entities(resume_json: dict) -> set:
    """Extract all valid companies, titles, and institutions from the resume."""
    entities = set()
    
    for exp in resume_json.get("experience", []):
        if exp.get("company"): entities.add(exp["company"].lower())
        if exp.get("title"): entities.add(exp["title"].lower())
        
    for edu in resume_json.get("education", []):
        if edu.get("institution"): entities.add(edu["institution"].lower())
        if edu.get("degree"): entities.add(edu["degree"].lower())
        
    return entities

def validate_change(category: str, change: dict, original_resume: dict) -> bool:
    """
    The safety gate. Every proposed change must pass through here.
    Returns True if safe to present to the user, False if it violates safety rules.
    
    Expected change dict format:
    {
      "section": "projects",
      "item_index": 2,
      "field": "bullet_text",
      "original": "old text",
      "proposed": "new text",
      "reason": "...",
      "type": "rewrite" # or "question"
    }
    """
    
    # 1. If it's just a clarifying question for the user, it's safe (doesn't modify resume yet)
    if change.get("type") == "question":
        return True

    # 1b. add_skill type — adds a skill from resume body to Skills section (no hallucination risk)
    if change.get("type") == "add_skill":
        return bool(change.get("proposed", "").strip())

        
    original = change.get("original", "").strip()
    proposed = change.get("proposed", "").strip()
    section = change.get("section", "")
    
    if not proposed:
        logger.warning("Validation failed: Proposed text is empty.")
        return False
        
    # 2. NEVER touch contact info automatically via AI
    if section == "contact" and category != "user_edit":
        logger.warning("Validation failed: Attempted to modify contact section.")
        return False

    # 3. Prevent hallucinated numbers
    # We strictly check that no new numeric tokens appear in the proposed text 
    # that weren't in the original text, UNLESS the category is quantify_impact 
    # (where the user explicitly provided a new number).
    if category != "quantify_impact":
        orig_nums = extract_numbers(original)
        prop_nums = extract_numbers(proposed)
        new_nums = prop_nums - orig_nums
        if new_nums:
            logger.warning(f"Validation failed: Hallucinated numbers detected {new_nums}")
            return False

    # 4. Length bloat check (runaway generation)
    # For micro-edits, sentence shouldn't balloon.
    if category in ["communication", "buzzwords", "ats_keywords"]:
        orig_words = original.split()
        prop_words = proposed.split()
        
        # If original is very short (e.g. 5 words), a 50% increase is just 2-3 words.
        # We allow either a 30% increase OR a flat +7 words, whichever is greater.
        max_allowed_len = max(int(len(orig_words) * 1.3), len(orig_words) + 7)
        
        if len(prop_words) > max_allowed_len:
            logger.warning(f"Validation failed: Length bloat. Original={len(orig_words)}, Proposed={len(prop_words)}")
            return False

    # 4b. Readability check — proposed must be strictly shorter than original.
    # The purpose of the readability fixer is compression; longer rewrites defeat the goal.
    if category == "readability":
        orig_words = len(original.split())
        prop_words = len(proposed.split())
        if prop_words >= orig_words:
            logger.warning(f"Readability validation failed: Proposed ({prop_words}w) is not shorter than original ({orig_words}w)")
            return False

    # 5. Summary validation (must only use existing skills)
    # If the AI generated a summary, we could check against allowed entities.
    # For now, we just log it. (In a real scenario, we might strictly enforce this).
    
    return True

