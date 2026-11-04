"""Source access inventory, separate from workspace connections and live health.

An inventory entry does not authorize crawling or claim an employer mapping.
No accounts, credentials, promotional allowances, or paid fallbacks are used.
"""
from copy import deepcopy

PROVIDERS = {
    "greenhouse": ("Greenhouse", "https://docs.greenhouse.io/job-board"),
    "lever": ("Lever", "https://github.com/lever/postings-api"),
    "ashby": ("Ashby", "https://developers.ashbyhq.com/docs/public-job-posting-api"),
    "smartrecruiters": ("SmartRecruiters", "https://developers.smartrecruiters.com/docs/endpoints"),
    "workable": ("Workable", "https://help.workable.com/hc/en-us/articles/115012771647-Using-the-Workable-API-to-create-a-careers-page"),
}
EMPLOYERS = list(dict.fromkeys("Amazon|Microsoft|Google|Adobe|Salesforce|Oracle|SAP|IBM|Zoho|Freshworks|Razorpay|PhonePe|Flipkart|Meesho|TCS|Infosys|Wipro|HCLTech|Accenture|Cognizant|Capgemini|ION Group|JPMorgan Chase|Goldman Sachs|Morgan Stanley|Canonical|Stripe|Point72|Postman|Twilio|CRED|Netflix|Atlan|Linear|Deel|NVIDIA|Mastercard|Dell|Target|Zepto|Groww|Walmart|Juspay|ServiceNow|Cisco|PayPal|Thoughtworks|HPE|Deloitte|Tekion".split("|")))

# Retain every originally named target, including unsupported routes.
PLATFORMS = "LinkedIn|Naukri.com|Unstop|Internshala|Wellfound|Indeed|Foundit|Cutshort|Instahyre|Hirist.tech|AICTE Internship Portal|National Career Service|Remotive|Jobicy|Himalayas|Glassdoor|ZipRecruiter|Bayt|BDJobs|HelloWork|FirstNaukri|Cuvette|YC Work at a Startup|HackerEarth|HackerRank|CodeChef|JobsNet|YoHire|FreshersBridge|JoinSaarthi|Preplaced|TalentBattle|PrepInsta|FreshersNow|Adzuna".split("|")
ENTERPRISE = ["Workday", "Oracle Recruiting", "Taleo", "SAP SuccessFactors", "iCIMS"]
EMPLOYERS.append("Digitals AI Inc")


def source_register():
    entries = []
    for key, (name, docs) in PROVIDERS.items():
        entries.append(dict(id=key, name=name, access="documented_public_api", implementation="tested",
            health="never_checked", documentation_url=docs, checked_at="2026-11-01", authentication="none",
            cost="ongoing_public_access", polling_floor_seconds=3600,
            conditions="Company-published board only. Public reachability does not grant bulk redistribution rights.",
            scope="company_board", pagination="bounded; closure only after a valid complete board traversal",
            description="full when supplied; missing/truncated descriptions stay excerpts",
            publication_dates="provider-specific; update/create dates are not publication dates", geography="employer-dependent"))
    for name in PLATFORMS + ENTERPRISE:
        entries.append(dict(id=name.lower().replace(" ", "_"), name=name, access="unverified",
            implementation="inventoried", health="never_checked", documentation_url=None, checked_at=None,
            authentication="not established; no job-account credentials collected", cost="unverified",
            polling_floor_seconds=None, scope="not_connected", pagination="unverified", description="unverified",
            publication_dates="unverified", geography="not established; no India coverage claim",
            conditions="Manual reviewed import only until supported, permitted free access is verified."))
    overrides = {
        "LinkedIn": dict(access="user_assisted_import", health="permission_required", conditions="Automated activity restricted; community JobSpy support is not permission. No unattended account access."),
        "Wellfound": dict(access="user_assisted_import", health="permission_required", documentation_url="https://wellfound.com/terms", checked_at="2026-11-02", conditions="General Terms restrict harvesting/copying and disclosure of opportunities. Recruiter/Reach MCP is not a candidate job feed; no background export enabled."),
        "Internshala": dict(access="user_assisted_import", health="permission_required", documentation_url="https://internshala.com/terms", checked_at="2026-11-02", conditions="Terms restrict data mining/extraction and copying without an applicable agreement. No automated collector enabled; use the original site or material you may import."),
        "Unstop": dict(documentation_url="https://unstop.com/jobs", checked_at="2026-11-01", implementation="researching", conditions="Public jobs route returned a cookies/JavaScript requirement during review. No supported export route or collection permission verified; manual import only."),
        "Naukri.com": dict(implementation="researching", conditions="JobSpy advertises Naukri support; official permitted search/export route was not established. No package installed into the running backend and no account-based pilot."),
        "Indeed": dict(implementation="researching", conditions="JobSpy support does not establish platform collection permission. No unrestricted candidate job-search API verified; manual import only."),
        "Oracle Recruiting": dict(access="authorized_partner_api", documentation_url="https://docs.oracle.com/en/cloud/saas/human-resources/farws/api-recruiting-job-requisitions.html", checked_at="2026-11-01", conditions="Tenant-specific HCM requisition API is not an unrestricted public catalogue. Employer external careers routes need separate verification."),
        "National Career Service": dict(access="authorized_partner_api", health="permission_required", documentation_url="https://www.ncs.gov.in/", conditions="Partner authorization must be established separately from jobseeker login."),
        "AICTE Internship Portal": dict(documentation_url="https://internship.aicte-india.org/"),
        "iCIMS": dict(access="authorized_partner_api", health="permission_required", documentation_url="https://developer-community.icims.com/applications/applicant-tracking/job-portal"),
        "Remotive": dict(implementation="tested", access="documented_public_api", cost="ongoing_public_access", documentation_url="https://remotive.com/remote-jobs/api", checked_at="2026-11-01", polling_floor_seconds=21600, conditions="24-hour publication delay. Visible Remotive attribution and link-back required; no third-party syndication. Read-only public adapter tested; workspace connection is explicit."),
        "Jobicy": dict(implementation="tested", access="documented_public_api", cost="ongoing_public_access", documentation_url="https://jobicy.com/jobs-rss-feed", checked_at="2026-11-01", polling_floor_seconds=3600, conditions="Public listing URLs only; seven-day rolling window, three-hour delay, cursor expires in 24 hours. Commercial direct ATS URLs excluded. Stored listings use the free batch status endpoint: explicit closed closes an occurrence; unknown stays unconfirmed. Workspace connection is explicit."),
        "Himalayas": dict(implementation="tested", access="documented_public_api", cost="ongoing_public_access", documentation_url="https://himalayas.app/api", checked_at="2026-11-01", polling_floor_seconds=86400, conditions="Unauthenticated allowance shared; daily refresh, attribution and unchanged applicationLink required. pubDate is an UPDATE time. Expiry filtered, original applicationLink retained. Daily shared-allowance access, not unlimited. Older stored occurrences are checked in bounded batches through the single-job API; 410 confirms closure and 404 stays unknown."),
        "Adzuna": dict(access="excluded_paid", cost="excluded_paid", implementation="disabled", conditions="Excluded from free expansion. Historical records and credentials retained; existing enablement is not changed by code."),
    }
    probes = {"Greenhouse": "Stripe: 745 occurrences/744 jobs; Point72: 206/205; repeated disposable ingestion passed",
        "Lever": "ION: 84 listings", "Ashby": "Ashby: 74 full descriptions", "SmartRecruiters": "1 full description; bounded partial scan",
        "Workable": "Digitals: 12 full descriptions; documented endpoint redirects to fixed official widget endpoint",
        "Remotive": "12 full descriptions", "Jobicy": "100 full descriptions; continuation available", "Himalayas": "20 full descriptions; continuation available"}
    for entry in entries:
        entry.update(overrides.get(entry["name"], {}))
        from jobs.access_review import assessment
        entry.update(assessment(entry["name"]))
        if entry["id"] in {"remotive", "jobicy", "himalayas"}:
            entry.update(authentication="none", scope="rolling_feed", description="full when supplied; excerpts labelled",
                         pagination="single bounded page per execution with persisted cursor when supplied",
                         publication_dates="original publication for Remotive/Jobicy; unknown for Himalayas (update time retained)",
                         geography="remote with source country/timezone restrictions; worldwide is not assumed")
        entry["observed_probe"] = probes.get(entry["name"])
        entry["probe_date"] = "2026-11-01" if entry["observed_probe"] else None
    return deepcopy(entries)


def capability(provider):
    return next((entry for entry in source_register() if entry["id"] == provider), None)
