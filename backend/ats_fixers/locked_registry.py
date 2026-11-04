import re

def build_locked_registry(parsed_resume: dict) -> set:
    """Extracts all structurally important data that the LLM is never allowed to modify."""
    locked = set()
    
    # 1. Contact info
    contact = parsed_resume.get("contact", {})
    if contact.get("name"): locked.add(contact["name"])
    if contact.get("phone"): locked.add(contact["phone"])
    if contact.get("email"): locked.add(contact["email"])
    
    for link in contact.get("links", []):
        url = link if isinstance(link, str) else link.get("url")
        if url: locked.add(url)

    # 2. Section metadata (dates, orgs, titles)
    for section_name in ["experience", "projects", "education"]:
        for entry in parsed_resume.get(section_name, []):
            if entry.get("title"): locked.add(entry["title"])
            if entry.get("role"): locked.add(entry["role"])
            if entry.get("org"): locked.add(entry["org"])
            if entry.get("company"): locked.add(entry["company"])
            if entry.get("institution"): locked.add(entry["institution"])
            if entry.get("degree"): locked.add(entry["degree"])
            if entry.get("start_date"): locked.add(entry["start_date"])
            if entry.get("end_date"): locked.add(entry["end_date"])
            
    return {str(item) for item in locked if item}


def extract_numbers(text: str) -> set:
    """Finds all numbers/percentages in a string to lock them."""
    if not text:
        return set()
    # Matches integers, decimals, and numbers with %
    matches = re.findall(r'\b\d+(?:\.\d+)?%?\b', text)
    return set(matches)


def validate_rewrite(original: str, rewritten: str, locked_registry: set, user_provided_data: str = None) -> bool:
    """
    Returns True if the rewritten bullet is valid and hasn't corrupted data.
    """
    if not original or not rewritten:
        return False

    # 1. Check if any locked tokens present in the original were dropped
    for token in locked_registry:
        if token in original and token not in rewritten:
            return False
            
    # 2. Check if any existing numbers were modified or dropped
    original_numbers = extract_numbers(original)
    rewritten_numbers = extract_numbers(rewritten)
    
    user_numbers = set()
    if user_provided_data:
        user_numbers = extract_numbers(user_provided_data)
        
    # The rewritten bullet should contain all original numbers
    for num in original_numbers:
        if num not in rewritten_numbers:
            return False
            
    # The rewritten bullet shouldn't introduce NEW numbers unless the user provided them
    for num in rewritten_numbers:
        if num not in original_numbers and num not in user_numbers:
            return False
            
    # 3. Check length tolerance
    # The prompt might add clarification context so allow a little more leniency if user provided data
    tolerance = 0.25 if user_provided_data else 0.15
    base_len = len(original)
    
    # If the user provided a 30 character metric, the new bullet could naturally be longer
    if user_provided_data:
        base_len += len(user_provided_data)
        
    max_len = max(base_len * (1 + tolerance), base_len + 30)
    min_len = min(len(original) * (1 - tolerance), len(original) - 30)

    if len(rewritten) > max_len or len(rewritten) < min_len:
        return False
        
    return True
