"""
Per-bullet annotation engine — provides inline feedback for every bullet.
Combines rule-based checks from ats_scorer with positive reinforcement.
"""
import re
from services.ats_wordlists import STRONG_ACTION_VERBS, WEAK_PHRASES, BUZZWORDS

def annotate_bullet(bullet: str, jd_keywords: list = None) -> dict:
    """Analyze a single bullet and return annotations."""
    annotations = []
    word_count = len(bullet.split())
    first_word = bullet.strip().split()[0].lower().rstrip(".,;:!") if bullet.strip() else ""
    
    # ── Positive signals (green) ──
    if first_word in STRONG_ACTION_VERBS:
        annotations.append({
            "type": "positive", "icon": "✅",
            "text": f"Strong action verb: '{bullet.split()[0]}'"
        })
    
    metric_pattern = re.compile(
        r'\d+\s*%|\$\s*[\d,]+|\d+x\b|\d+\s*\+|\b\d+\s*users?\b'
        r'|\b\d+\s*clients?\b|\b\d+\s*projects?\b', re.IGNORECASE
    )
    if metric_pattern.search(bullet):
        annotations.append({
            "type": "positive", "icon": "📊",
            "text": "Contains quantified metric — great!"
        })
    
    if 8 <= word_count <= 20:
        annotations.append({
            "type": "positive", "icon": "📏",
            "text": f"Good length ({word_count} words)"
        })
    
    # JD keyword matches
    if jd_keywords:
        matched = [kw for kw in jd_keywords if isinstance(kw, str) and kw.lower() in bullet.lower()]
        if matched:
            annotations.append({
                "type": "positive", "icon": "🎯",
                "text": f"Contains JD keywords: {', '.join(matched[:3])}"
            })
    
    # ── Negative signals (red/yellow) ──
    for phrase in WEAK_PHRASES:
        if phrase in bullet.lower():
            annotations.append({
                "type": "warning", "icon": "⚠️",
                "text": f"Weak phrasing: '{phrase}' — try a strong verb instead"
            })
            break
    
    if word_count > 25:
        annotations.append({
            "type": "warning", "icon": "📏",
            "text": f"Too long ({word_count} words) — aim for under 20"
        })
    elif word_count < 6:
        annotations.append({
            "type": "warning", "icon": "📏",
            "text": f"Too short ({word_count} words) — add more detail"
        })
    
    if not metric_pattern.search(bullet):
        annotations.append({
            "type": "suggestion", "icon": "💡",
            "text": "No metrics — add numbers (%, $, count) to show impact"
        })
    
    if re.search(r'\b(I|me|my|we|us|our)\b', bullet, re.IGNORECASE):
        annotations.append({
            "type": "warning", "icon": "🚫",
            "text": "Contains personal pronouns — remove for professional tone"
        })
    
    passive_starters = {"was", "were", "been", "being", "had", "have", "has"}
    if first_word in passive_starters:
        annotations.append({
            "type": "warning", "icon": "🔄",
            "text": "Starts with passive voice — lead with an action verb"
        })
    
    # ── Overall quality rating ──
    positive_count = sum(1 for a in annotations if a["type"] == "positive")
    warning_count = sum(1 for a in annotations if a["type"] == "warning")
    
    if positive_count >= 3 and warning_count == 0:
        quality = "excellent"
    elif positive_count >= 2 and warning_count <= 1:
        quality = "good"
    elif warning_count >= 2:
        quality = "needs_work"
    else:
        quality = "acceptable"
    
    return {
        "bullet": bullet,
        "quality": quality,
        "annotations": annotations,
    }


def annotate_all_bullets(resume_json: dict, jd_keywords: list = None) -> dict:
    """Annotate every bullet in experience + projects sections."""
    results = {"experience": [], "projects": []}
    
    for section in ["experience", "projects"]:
        items = resume_json.get(section, [])
        if not isinstance(items, list):
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            bullets = item.get("bullets") or item.get("bullet_points") or []
            item_annotations = []
            for j, bullet in enumerate(bullets):
                if isinstance(bullet, str) and bullet.strip():
                    item_annotations.append(annotate_bullet(bullet, jd_keywords))
            results[section].append({
                "item_index": i,
                "title": item.get("title") or item.get("name") or f"Item {i+1}",
                "company": item.get("company", ""),
                "bullet_annotations": item_annotations,
            })
    
    # Summary stats
    all_annotations = []
    for sec in ["experience", "projects"]:
        for item in results[sec]:
            all_annotations.extend(item["bullet_annotations"])
    
    results["summary_stats"] = {
        "total_bullets": len(all_annotations),
        "excellent": sum(1 for a in all_annotations if a["quality"] == "excellent"),
        "good": sum(1 for a in all_annotations if a["quality"] == "good"),
        "acceptable": sum(1 for a in all_annotations if a["quality"] == "acceptable"),
        "needs_work": sum(1 for a in all_annotations if a["quality"] == "needs_work"),
    }
    
    return results
