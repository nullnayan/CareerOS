"""Connection lifecycle and required next actions for the entire inventory."""
from sqlalchemy import text
from db.models import JobSource
from jobs.adapters import ADAPTERS
from jobs.directory import company_directory
from jobs.registry import source_register

PLATFORM_URLS = {
    "LinkedIn": "https://www.linkedin.com/jobs/", "Naukri.com": "https://www.naukri.com/",
    "Unstop": "https://unstop.com/jobs", "Internshala": "https://internshala.com/", "Wellfound": "https://wellfound.com/jobs",
    "Indeed": "https://in.indeed.com/", "Foundit": "https://www.foundit.in/", "Cutshort": "https://cutshort.io/jobs",
    "Instahyre": "https://www.instahyre.com/", "Hirist.tech": "https://www.hirist.tech/",
    "FirstNaukri": "https://www.firstnaukri.com/", "Cuvette": "https://cuvette.tech/",
    "YC Work at a Startup": "https://www.workatastartup.com/", "AICTE Internship Portal": "https://internship.aicte-india.org/",
    "National Career Service": "https://www.ncs.gov.in/", "Glassdoor": "https://www.glassdoor.co.in/Job/",
    "ZipRecruiter": "https://www.ziprecruiter.com/", "Bayt": "https://www.bayt.com/", "BDJobs": "https://bdjobs.com/",
    "HelloWork": "https://www.hellowork.com/", "HackerEarth": "https://www.hackerearth.com/challenges/",
    "HackerRank": "https://www.hackerrank.com/", "CodeChef": "https://www.codechef.com/",
    "JobsNet": "https://jobsnet.in/", "YoHire": "https://yohire.in/", "FreshersBridge": "https://www.freshersbridge.in/",
    "JoinSaarthi": "https://joinsaarthi.com/", "Preplaced": "https://www.preplaced.in/",
    "TalentBattle": "https://talentbattle.in/", "PrepInsta": "https://prepinsta.com/", "FreshersNow": "https://www.freshersnow.com/",
}
ENTERPRISE_NAMES = {"Workday", "Oracle Recruiting", "Taleo", "SAP SuccessFactors", "iCIMS"}


def requirements(db, owner):
    sources = db.query(JobSource).filter_by(user_id=owner.id).all()
    result = []
    for entry in source_register():
        provider = entry["id"]
        connected = [s for s in sources if s.provider == provider]
        if provider in ADAPTERS:
            state = "connected" if connected else "available"
            action = "Review source health; refresh when due." if connected else "Connect a company board." if ADAPTERS[provider].kind == "company_api" else "Connect this free public feed."
            needed = []
            if ADAPTERS[provider].kind == "employer_configured":
                state = "connected" if connected else "feed_required"
                action = "Review this employer connection's observed health." if connected else "Use employer connection setup below; no employer is connected automatically."
                needed = [entry["required_prerequisite"]]
        elif entry["access"] == "excluded_paid":
            state, action, needed = "excluded", "Excluded from free discovery; historical records retained.", []
        elif entry["name"] in ENTERPRISE_NAMES:
            state, action, needed = "feed_required", "Add a verified employer public feed, or import a reviewed job from its careers page.", ["Employer career-site or public job-feed URL"]
        else:
            state, action = "external_import", "Open the original site. Import a reviewed job using the paired extension or supplied description."
            needed = ["Supported public export/feed or partner access for unattended collection"]
        if entry.get("required_prerequisite") and provider not in ADAPTERS:
            needed = [entry["required_prerequisite"]]
        reviewed = [s for s in sources if s.provider == "manual" and s.board == "reviewed:" + entry.get("community_site", "")]
        result.append({**entry, "connection_state": state, "source_ids": [s.id for s in connected],
            "enabled_connections": sum(s.enabled for s in connected), "next_action": action,
            "required_input": needed, "website_url": PLATFORM_URLS.get(entry["name"]),
            "reviewed_imports": [s.id for s in reviewed],
            "collects_automatically": provider in ADAPTERS and any(s.enabled for s in connected)})
    return result


def connect_free_defaults(db, owner):
    # This changes only source connections, never preferences or automation.
    if db.get_bind().dialect.name == "postgresql": db.execute(text("SELECT pg_advisory_xact_lock(30103003)"))
    defaults = [row for row in company_directory() if row.get("verified_for_setup")]
    defaults += [{"provider": name, "board": "public", "company": name.title()} for name in ("remotive", "jobicy", "himalayas")]
    added, retained = [], []
    for row in defaults:
        source = db.query(JobSource).filter_by(user_id=owner.id, provider=row["provider"], board=row["board"]).first()
        if source:
            retained.append({"id": source.id, "provider": source.provider, "board": source.board, "enabled": source.enabled})
            continue
        source = JobSource(user_id=owner.id, provider=row["provider"], board=row["board"], company=row["company"], enabled=True)
        db.add(source); db.flush()
        added.append({"id": source.id, "provider": source.provider, "board": source.board, "company": source.company})
    db.commit()
    return {"added": added, "retained": retained, "note": "Connections saved. Existing disabled sources and automation settings were preserved. Refresh starts discovery when you choose."}
