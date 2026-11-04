def get_flags(resume_json: dict) -> list:
    """
    Flag missing education fields. No AI used.
    Returns clarifying questions for the frontend to ask the user.
    """
    changes = []
    
    edu_list = resume_json.get("education", [])
    
    for i, edu in enumerate(edu_list):
        institution = edu.get("institution", "").strip()
        degree = edu.get("degree", "").strip()
        
        display_name = institution if institution else (degree if degree else f"Education Entry #{i+1}")
        
        # Check institution
        if not institution:
            changes.append({
                "section": "education",
                "item_index": i,
                "field": "institution",
                "original": "",
                "proposed": "What is the name of the institution for this degree?",
                "reason": "Missing institution name",
                "type": "question"
            })
            
        # Check degree
        if not degree:
            changes.append({
                "section": "education",
                "item_index": i,
                "field": "degree",
                "original": "",
                "proposed": f"What degree did you earn at {display_name}?",
                "reason": "Missing degree name",
                "type": "question"
            })
            
        # Check dates — support both snake_case and camelCase field names
        start = (
            edu.get("start_date") or edu.get("startDate") or ""
        ).strip()
        end = (
            edu.get("end_date") or edu.get("endDate") or ""
        ).strip()
        if not start and not end:
            changes.append({
                "section": "education",
                "item_index": i,
                "field": "dates",
                "original": "",
                "proposed": f"When did you attend {display_name}? (e.g. 2018 - 2022)",
                "reason": "Missing dates",
                "type": "question"
            })
            
        # Check GPA (optional, but good to prompt if recent grad - let's keep it simple for now)
        # Assuming missing fields are questions
        
    return changes
