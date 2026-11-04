"""Conservative annual INR salary normalization; never invent undisclosed pay."""
import math
import re


def number(value):
    try:
        value = float(str(value).replace(",", ""))
        return value if math.isfinite(value) and 0 < value <= 1_000_000_000 else None
    except (TypeError, ValueError): return None


def salary_facts(description, facts):
    facts = dict(facts or {})
    if facts.get("original_salary_source") in {"estimated", "estimate"}:
        for key in ("salary_min", "salary_max", "annual_salary_min_inr", "annual_salary_max_inr", "salary_evidence"):
            facts.pop(key, None)
        return facts
    lower, upper = number(facts.get("salary_min")), number(facts.get("salary_max"))
    currency = str(facts.get("salary_currency") or "").upper()
    period = str(facts.get("salary_period") or "").lower()
    multiplier = {"annual": 1, "annually": 1, "year": 1, "yearly": 1, "month": 12, "monthly": 12}.get(period)
    if currency == "INR" and multiplier and lower and (upper is None or upper >= lower):
        facts.update(annual_salary_min_inr=round(lower * multiplier),
                     annual_salary_max_inr=round((upper or lower) * multiplier),
                     salary_evidence="description" if facts.get("salary_evidence") == "description" else "source_fields")
        return facts
    # A description must explicitly label compensation or include an annual
    # salary unit. An unrelated budget/fee is not a salary estimate.
    for line in description.splitlines():
        if re.search(r"\bestimat(?:e|ed|es|ion)\b", line, re.I): continue
        if not re.search(r"salary|compensation|ctc|package|stipend|\blpa\b", line, re.I): continue
        match = re.search(r"(?:₹|INR|Rs\.?\s*)?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:-|–|to)\s*(?:₹|INR|Rs\.?\s*)?\s*(\d[\d,]*(?:\.\d+)?)\s*(LPA|lakhs?\s*(?:per\s*annum|annually|a\s*year)|per\s*annum|per\s*year|annually|per\s*month|monthly)", line, re.I)
        if not match:
            match = re.search(r"(?:₹|INR|Rs\.?\s*)?\s*(\d[\d,]*(?:\.\d+)?)\s*(LPA|lakhs?\s*(?:per\s*annum|annually|a\s*year)|per\s*annum|per\s*year|annually|per\s*month|monthly)", line, re.I)
            if not match or re.search(r"up\s*to|upto|maximum", line[:match.start()], re.I): continue
            low, high, unit = number(match[1]), number(match[1]), match[2]
        else: low, high, unit = number(match[1]), number(match[2]), match[3]
        if not low or not high or low > high: continue
        is_lakh = bool(re.search(r"lpa|lakh", unit, re.I))
        # Plain numbers in a foreign-currency line must not be relabelled INR.
        if re.search(r"USD|EUR|GBP|\$|€|£", line, re.I): continue
        if not is_lakh and not re.search(r"₹|\bINR\b|\bRs\.?", line, re.I): continue
        factor = 100000 if is_lakh else 12 if "month" in unit.lower() else 1
        facts.update(salary_min=low * factor, salary_max=high * factor, salary_currency="INR", salary_period="annual",
                     annual_salary_min_inr=round(low * factor), annual_salary_max_inr=round(high * factor), salary_evidence="description")
        return facts
    # Do not retain previously derived values after a source changes its pay.
    facts.pop("annual_salary_min_inr", None); facts.pop("annual_salary_max_inr", None)
    return facts
