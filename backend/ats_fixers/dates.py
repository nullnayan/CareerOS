from dateutil import parser
import re
import logging

logger = logging.getLogger(__name__)

# The resume schema uses snake_case. Check both camelCase and snake_case for safety.
START_FIELDS = ["start_date", "startDate"]
END_FIELDS = ["end_date", "endDate"]


def _standardize_date(date_str: str) -> str:
    """Attempt to standardize a date string to 'Mon YYYY' format."""
    if not date_str:
        return ""

    date_str_clean = date_str.strip().lower()
    if date_str_clean in ["present", "current", "now"]:
        return "Present"

    date_str_clean = re.sub(r'[^\w\s\-,]', '', date_str)

    try:
        parsed = parser.parse(date_str_clean, default=parser.parse("2000-01-01"))
        return parsed.strftime("%b %Y")
    except Exception:
        return date_str


def fix(resume_json: dict) -> list:
    """
    Standardize dates in experience, education, and projects.
    Returns a list of proposed changes.
    """
    changes = []

    sections_to_check = ["experience", "education", "projects"]

    for section in sections_to_check:
        items = resume_json.get(section) or []
        for i, item in enumerate(items):
            # Check start date — try snake_case first, then camelCase
            for start_key in START_FIELDS:
                if start_key in item and item[start_key]:
                    orig = item[start_key]
                    std = _standardize_date(orig)
                    if std and std != orig and orig.strip().lower() not in ["present", "current", "now"]:
                        changes.append({
                            "section": section,
                            "item_index": i,
                            "field": start_key,
                            "original": orig,
                            "proposed": std,
                            "reason": f"Standardized date format from '{orig}' to '{std}'",
                            "type": "rewrite"
                        })
                    break  # only use the first matching key

            # Check end date
            for end_key in END_FIELDS:
                if end_key in item and item[end_key]:
                    orig = item[end_key]
                    std = _standardize_date(orig)
                    if std and std != orig:
                        changes.append({
                            "section": section,
                            "item_index": i,
                            "field": end_key,
                            "original": orig,
                            "proposed": std,
                            "reason": f"Standardized date format from '{orig}' to '{std}'",
                            "type": "rewrite"
                        })
                    break

    return changes
