"""Conservative fresher eligibility and explainable, deterministic relevance."""
from datetime import date, datetime
import re
from tailoring.selection import TERMS, canonical, contains
from jobs.schemas import SearchPreferences

INDIAN_CITIES = {"bengaluru", "bangalore", "hyderabad", "delhi", "ncr", "noida", "gurugram", "gurgaon", "pune", "mumbai", "chennai", "kolkata", "dehradun", "ahmedabad"}
EXPLICIT_FOREIGN = r"\b(united states|united kingdom|us|uk|usa|u\.s\.|london|new york|san francisco|canada|germany|australia|singapore|ireland|poland|berlin|toronto|emea|europe|americas|latin america|china|japan)\b"


def experience_required(text: str) -> float | None:
    values = []
    section = ""
    for line in text.splitlines():
        if re.fullmatch(r"\s*(preferred qualifications|preferred skills|nice.to.have)\s*:?\s*", line, re.I): section = "preferred"
        if re.fullmatch(r"\s*(minimum qualifications|requirements|required skills)\s*:?\s*", line, re.I): section = "required"
        if section == "preferred" or re.search(r"preferred|nice.to.have|bonus", line, re.I): continue
        qualifier = r"\s*['’]?\s+(?:of\s+)?(?:(?:professional|relevant|work|industry|commercial|software|engineering|development|programming|hands.on|full.time)\s+){0,4}experience"
        patterns = [r"\b(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*\d+(?:\.\d+)?\s*(?:years?|yrs?)" + qualifier,
                    r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)" + qualifier,
                    r"experience\s*(?:of|:|at least)?\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
                    r"experience\s*:\s*(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*\d+(?:\.\d+)?\s*(?:years?|yrs?)"]
        for index, pattern in enumerate(patterns):
            for match in re.finditer(pattern, line, re.I):
                if index and re.search(r"(?:\d\s*[-–]|\d+\s+to)\s*$", line[:match.start()]): continue
                values.append(float(match[1]))
    return max(values) if values else None


def graduation_batches(text: str) -> list[int]:
    years = set()
    for sentence in re.split(r"[\n.!?]", text):
        if not re.search(r"graduat|batch|class of|passing.out|freshers?", sentence, re.I): continue
        for match in re.finditer(r"\b(20[2-4]\d)\s*/\s*(\d{2})\b", sentence):
            # Common fresher notation: 2026/27 means the two named batches.
            other = int(match[1][:2] + match[2])
            if 0 <= other - int(match[1]) <= 4: years.update([int(match[1]), other])
        for match in re.finditer(r"\b(20[2-4]\d)\b", sentence):
            # Do not interpret experience dates, company founding dates, or a
            # joining/start date in the same sentence as graduation eligibility.
            before = sentence[max(0, match.start() - 30):match.start()].lower()
            if re.search(r"(?:join|start|founded|established)\w*\s+(?:in\s+)?$", before): continue
            years.add(int(match[1]))
        for match in re.finditer(r"\b(20[2-4]\d)\s*(?:-|–|to)\s*(20[2-4]\d)\b", sentence):
            if 0 < int(match[2]) - int(match[1]) <= 4:
                years.update(range(int(match[1]), int(match[2]) + 1))
    return sorted(years)


def source_experience(facts: dict) -> float | None:
    """Read explicit source experience ranges without treating unknown as zero."""
    values = []
    for key in ("experience_range", "experience"):
        raw = facts.get(key)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool) and 0 <= raw <= 50:
            values.append(float(raw))
        elif isinstance(raw, str):
            value = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:\+|(?:-|–|to)\s*\d+(?:\.\d+)?)?\s*(?:years?|yrs?)?\s*", raw, re.I)
            if value: values.append(float(value[1]))
            elif re.fullmatch(r"\s*(?:freshers?|no experience(?: required)?)\s*", raw, re.I): values.append(0.0)
    return max(values) if values else None


def role_alignment(title: str, roles: list[str]) -> float:
    title = re.sub(r"[^a-z0-9]+", " ", title.lower())
    best = 0.0
    for role in roles:
        tokens = re.findall(r"[a-z0-9]+", role.lower())
        if not tokens: continue
        if " ".join(tokens) in title: return 1.0
        best = max(best, sum(token in title.split() for token in tokens) / len(tokens))
        if "backend" in tokens and re.search(r"back.end", title): best = max(best, .8)
    return best


def evaluate(job, preferences: SearchPreferences, resume_text: str, confirmed_skills: list[str], today: date | None = None) -> dict:
    today = today or date.today()
    text = job.title + "\n" + job.description
    facts = job.facts or {}
    blocked, unknown, reasons = [], [], []
    if facts.get("source_expiry_at", "9999") <= datetime.utcnow().isoformat():
        blocked.append("Source listing has expired.")
    zones = facts.get("timezone_restrictions")
    if zones and preferences.country_code == "in" and not any(str(zone) in {"5.5", "+5.5", "UTC+05:30", "+05:30"} for zone in zones):
        blocked.append("Remote timezone restrictions exclude India's standard offset.")
    if preferences.max_required_experience <= 2 and re.search(r"\b(senior|sr\.?|principal|staff|lead|manager|director|head|vp)\b", job.title, re.I):
        blocked.append("Title requires a senior or leadership role.")
    years = experience_required(text)
    structured_years = source_experience(facts)
    if structured_years is not None: years = max(years, structured_years) if years is not None else structured_years
    if years is not None:
        if years > preferences.max_required_experience: blocked.append(f"Requires at least {years:g} years of experience.")
        else: reasons.append(f"Experience requirement fits your limit ({years:g} years minimum).")
    elif re.search(r"\b(fresher|graduate|new.grad|entry.level|trainee|intern(?:ship)?)\b", job.title, re.I):
        reasons.append("The title explicitly targets graduates or entry-level candidates.")
    else:
        unknown.append("Minimum experience is not clearly stated.")
    batches = graduation_batches(text)
    if batches:
        if preferences.graduation_year is None: unknown.append("Confirm your graduation year to check batch eligibility.")
        elif preferences.graduation_year not in batches: blocked.append("Listed graduation batches: " + ", ".join(map(str, batches)) + ".")
        else: reasons.append(f"Your {preferences.graduation_year} graduation batch is listed.")
    campus = re.search(r"\b(IIT\s+[A-Za-z]+|NIT\s+[A-Za-z]+)\b", job.title, re.I)
    if campus:
        if not preferences.institution: unknown.append(f"Campus-specific opening: {campus[0]}. Confirm your institution.")
        elif campus[0].lower() not in preferences.institution.lower(): blocked.append(f"Campus-specific opening for {campus[0]}.")
    if preferences.education_status == "student" and re.search(r"(?:must\s+(?:have\s+)?(?:already\s+)?(?:graduated|completed)|degree must be completed)", text, re.I):
        blocked.append("The employer explicitly requires a completed degree.")
    joining = re.search(r"(?:join|start|available)\w*\s+(?:by|on|from)\s+(20\d\d-\d\d-\d\d)", text, re.I)
    if joining:
        try:
            required_date = date.fromisoformat(joining[1])
            if not preferences.earliest_joining_date: unknown.append("Confirm your earliest joining date.")
            elif preferences.earliest_joining_date > required_date: blocked.append(f"Employer needs availability by {required_date.isoformat()}.")
        except ValueError: unknown.append("Joining date needs manual review.")
    elif preferences.education_status == "student" and "intern" not in job.title.lower():
        unknown.append("Confirm that the full-time joining date fits your studies.")
    employment = str(facts.get("employment_type", "")).lower().replace("-", "_").replace(" ", "_")
    if "intern" in job.title.lower() or "intern" in employment: employment = "internship"
    elif "part" in employment: employment = "part_time"
    elif "contract" in employment or "contractor" in job.title.lower(): employment = "contract"
    elif "full" in employment: employment = "full_time"
    else: employment = "unknown"
    if employment != "unknown" and employment not in preferences.employment_types: blocked.append("Employment type is outside your preferences.")
    locations = [job.location]
    for secondary in facts.get("secondary_locations") or []:
        value = secondary.get("location", "") if isinstance(secondary, dict) else secondary
        if isinstance(value, str) and value.strip(): locations.append(value)
    location = "\n".join(locations).lower()
    mode = str(facts.get("work_mode", "unknown")).lower().replace("_", "")
    if mode in {"onsite", "on-site"}: mode = "onsite"
    elif mode not in {"remote", "hybrid"}:
        mode = "hybrid" if "hybrid" in location else "remote" if re.search(r"remote|home.based|work.from.home|\bwfh\b", location) else "unknown"
    if mode != "unknown" and mode not in preferences.work_modes: blocked.append("Work arrangement is outside your preferences.")
    indian = "india" in location or any(city in location for city in INDIAN_CITIES)
    worldwide = bool(re.search(r"worldwide|anywhere|global", location))
    location_match = not preferences.locations or any(place.lower() in location for place in preferences.locations)
    if any(place.lower() == "india" for place in preferences.locations) and indian: location_match = True
    if not location_match:
        if mode == "remote" and worldwide: reasons.append("Worldwide remote location fits your remote preference.")
        elif not location or (mode == "remote" and not re.search(EXPLICIT_FOREIGN, location)):
            unknown.append("Location or remote-country eligibility is not explicit.")
        else: blocked.append("Location is outside your preferences.")
    elif preferences.locations: reasons.append("Location matches your preferences.")
    restriction = job.location + "\n" + "\n".join(line for line in job.description.splitlines() if re.search(r"applicants|candidates|position|role|remote work", line, re.I))
    if mode == "remote" and re.search(r"(?:US|U\.S\.|United States|UK|United Kingdom)\s+only", restriction, re.I) and preferences.country_code == "in":
        blocked.append("Remote work is explicitly restricted to another country.")
    permitted = facts.get("applicant_location_requirements")
    if permitted and preferences.country_code == "in" and not any(str(place).lower().strip() in {"india", "in", "worldwide", "anywhere", "global"} for place in permitted):
        blocked.append("Employer's applicant-country restriction does not include India.")
    if any(company.lower() in job.company.lower() for company in preferences.excluded_companies): blocked.append("Company is excluded in your preferences.")
    academic_text = " ".join([resume_text, preferences.degree, preferences.course]).lower()
    degree_evidence = bool(re.search(r"b\s*\.?\s*tech|bachelor|b\s*\.?\s*e\b|computer science|information technology", academic_text))
    academic_match = degree_evidence and bool(re.search(r"engineering|computer science|bachelor|b\.?\s*tech|related (?:field|discipline)", text, re.I))
    if academic_match: reasons.insert(0, "Degree/course requirements align with your supplied education evidence.")
    if re.search(r"(?:must have|requires?|mandatory)\s+(?:an?\s+)?ph\.?d|ph\.?d\s+(?:is\s+)?required", text, re.I) and not re.search(r"ph\.?d|doctor of", academic_text):
        blocked.append("Employer explicitly requires a PhD; it is not present in your education evidence.")
    salary_max = facts.get("salary_max")
    if preferences.minimum_salary_annual_inr:
        if facts.get("salary_currency") == "INR" and facts.get("salary_period") == "annual" and salary_max:
            if salary_max < preferences.minimum_salary_annual_inr: reasons.append("Advertised pay is below your saved salary preference; adjust the salary filter if needed.")
        else: unknown.append("Comparable annual INR salary is not supplied.")
    if job.published_at and preferences.max_posting_age_days and (today - job.published_at.date()).days > preferences.max_posting_age_days:
        blocked.append("Publication date is outside your freshness window.")
    if job.status != "open": blocked.append("Opening is no longer listed by its sources.")
    align = role_alignment(job.title, preferences.target_roles)
    if align < .35: blocked.append("Role title does not match your target roles.")
    else: reasons.append("Title aligns with your target roles.")
    terms = list(dict.fromkeys(term for values in TERMS.values() for term in values))
    terms += [term for term in confirmed_skills if term not in terms]
    required = [term for term in terms if contains(job.description, term)]
    matched = [term for term in required if contains(resume_text, term) or any(canonical(term) == canonical(known) for known in confirmed_skills)]
    missing = [term for term in required if term not in matched]
    if matched: reasons.append("Relevant skills: " + ", ".join(matched[:5]) + ".")
    coverage = len(matched) / len(required) if required else 0
    freshness = 5 if job.published_at and (today - job.published_at.date()).days <= 14 else 0
    score = round(min(100, 40 * align + 40 * coverage + (10 if not blocked else 0) + (5 if academic_match else 0) + freshness))
    if "Minimum experience is not clearly stated." in unknown:
        score = min(score, 60)
    return {"eligibility": "ineligible" if blocked else "review" if unknown else "eligible",
            "relevance_score": score, "reasons": reasons[:5], "blocked_reasons": list(dict.fromkeys(blocked)),
            "unknowns": list(dict.fromkeys(unknown)), "matched_skills": matched, "missing_skills": missing[:8],
            "minimum_experience": years, "graduation_batches": batches, "work_mode": mode,
            "employment_type": employment, "resume_evidence_available": bool(resume_text.strip()),
            "note": "Rule-based relevance, not an interview probability or ATS score."}
