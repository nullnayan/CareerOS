def get_flags(resume_json: dict) -> list:
    """
    Flag outdated/irrelevant sections for user removal. No AI used.
    """
    changes = []
    
    # Heuristic list of usually unnecessary sections
    unnecessary_keys = ["hobbies", "interests", "references"]
    
    for key in unnecessary_keys:
        if key in resume_json and resume_json[key]:
            # If it's a list and it's empty, ignore. Same for string/dict.
            val = resume_json[key]
            if isinstance(val, (list, dict, str)) and not val:
                continue
                
            changes.append({
                "section": key,
                "item_index": 0,
                "field": key,
                "original": f"[{key.title()} section present]",
                "proposed": f"Do you want to remove the '{key.title()}' section? It is rarely needed on modern ATS resumes.",
                "reason": f"{key.title()} section is generally unnecessary and takes up valuable space.",
                "type": "question"  # Handled as a deletion confirmation by frontend
            })
            
    # Check for duplicate summary/objective
    has_summary = bool(resume_json.get("summary"))
    has_objective = bool(resume_json.get("objective"))
    
    if has_summary and has_objective:
        changes.append({
            "section": "objective",
            "item_index": 0,
            "field": "objective",
            "original": resume_json["objective"],
            "proposed": "You have both a Summary and an Objective. Do you want to remove the Objective? Summaries are preferred.",
            "reason": "Duplicate introductory sections.",
            "type": "question"
        })
        
    return changes
