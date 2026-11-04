"""Pinned collector capabilities and conservative source boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = REPO_ROOT / "oss-tools" / "runtime"
TOOL_VERSIONS = {
    "jobspy": "python-jobspy 1.4.1 / JobSpy a606f9cf077c34f6ce6cbfcc76238f57b3c20671",
    "ats_scrapers": "ats-scrapers 0.3.0 / 6b44a1badc9bfbf5cf176f75265cc5729e520e99",
    "instahyre": "OmkarCloud instahyre-scraper / 16a64f440e39a1545ea1322e21c6d8ef654a3358",
    "internshala": "OmkarCloud internshala-scraper / 4755e7c83ec565e456384dffede100e9dfdc6a3d",
    "shine": "OmkarCloud shine-scraper / ec9c0978b71ff502bf17e6b34fd0a64d150e410c",
    "crawl4ai": "crawl4ai 0.9.5 / 838869bdda93f25e6d50b3f50ae9577d9b19a586",
}


@dataclass(frozen=True)
class SourceCapability:
    source_id: str
    tool: str
    official_url: str
    country_scope: str
    allowed_domains: tuple[str, ...]
    limitation: str = ""


JOBSPY_SITES = {
    "linkedin": SourceCapability("linkedin", "jobspy", "https://www.linkedin.com/jobs/", "country stated by request; no account session", ("linkedin.com",), "No credentials, cookies, or proxies; access controls remain authoritative."),
    "naukri": SourceCapability("naukri", "jobspy", "https://www.naukri.com/", "India only", ("naukri.com",), "Country is fixed to India by upstream implementation."),
    "indeed": SourceCapability("indeed", "jobspy", "https://www.indeed.com/", "Upstream country enum; exact ISO mapping required", ("indeed.com",), "Country maps through country_indeed; no US fallback for India."),
    "glassdoor": SourceCapability("glassdoor", "jobspy", "https://www.glassdoor.com/Job/", "Upstream country enum; exact ISO mapping required", ("glassdoor.com",), "Country maps through country_indeed; access may require login."),
    "zip_recruiter": SourceCapability("zip_recruiter", "jobspy", "https://www.ziprecruiter.com/", "United States and Canada", ("ziprecruiter.com",), "No India coverage claim."),
    "bayt": SourceCapability("bayt", "jobspy", "https://www.bayt.com/", "Supported Bayt markets; location must be explicit", ("bayt.com",), "Uses source-native location; market list is not equivalent to worldwide coverage."),
    "bdjobs": SourceCapability("bdjobs", "jobspy", "https://bdjobs.com/", "Bangladesh only", ("bdjobs.com",), "Country is fixed to Bangladesh by upstream implementation."),
    "hellowork": SourceCapability("hellowork", "jobspy", "https://www.hellowork.com/", "France only", ("hellowork.com",), "Country is fixed to France by upstream implementation."),
}

OMKAR_SITES = {
    "instahyre": SourceCapability("instahyre", "instahyre", "https://www.instahyre.com/", "India; source-native regions can include outside-India", ("instahyre.com",), "One result page is fixed at 35 cards; no paid host or proxy."),
    "internshala_jobs": SourceCapability("internshala_jobs", "internshala", "https://internshala.com/jobs/", "India; fresher/jobs board", ("internshala.com",), "Terms review restricts automated extraction; do not live-collect without an applicable agreement."),
    "internshala_internships": SourceCapability("internshala_internships", "internshala", "https://internshala.com/internships/", "India; internship board", ("internshala.com",), "Terms review restricts automated extraction; do not live-collect without an applicable agreement."),
    "shine": SourceCapability("shine", "shine", "https://www.shine.com/job-search/", "India; source-native locations", ("shine.com",), "Local API is source-owned and may change; no hosted API or paid service."),
}

ATS_API_DOMAINS = {
    "greenhouse": ("greenhouse.io",),
    "lever": ("lever.co",),
    "ashby": ("ashbyhq.com",),
    "workable": ("workable.com",),
    "smartrecruiters": ("smartrecruiters.com",),
    "workday": ("myworkdayjobs.com",),
    "successfactors": ("successfactors.eu", "successfactors.com"),
    "oracle": ("oraclecloud.com", "oracle.com"),
    "icims": ("icims.com",),
    "taleo": ("taleo.net",),
    "adp": ("adp.com",),
    "jobvite": ("jobvite.com",),
}

PLATFORM_URLS = {
    "LinkedIn": "https://www.linkedin.com/jobs/", "Naukri.com": "https://www.naukri.com/",
    "Unstop": "https://unstop.com/jobs", "Internshala": "https://internshala.com/",
    "Wellfound": "https://wellfound.com/jobs", "Indeed": "https://in.indeed.com/",
    "Foundit": "https://www.foundit.in/", "Cutshort": "https://cutshort.io/jobs",
    "Instahyre": "https://www.instahyre.com/", "Hirist.tech": "https://www.hirist.tech/",
    "AICTE Internship Portal": "https://internship.aicte-india.org/", "National Career Service": "https://www.ncs.gov.in/",
    "Remotive": "https://remotive.com/remote-jobs", "Jobicy": "https://jobicy.com/jobs-rss-feed",
    "Himalayas": "https://himalayas.app/jobs", "Glassdoor": "https://www.glassdoor.co.in/Job/",
    "ZipRecruiter": "https://www.ziprecruiter.com/", "Bayt": "https://www.bayt.com/",
    "BDJobs": "https://bdjobs.com/", "HelloWork": "https://www.hellowork.com/",
    "FirstNaukri": "https://www.firstnaukri.com/", "Cuvette": "https://cuvette.tech/",
    "YC Work at a Startup": "https://www.workatastartup.com/", "HackerEarth": "https://www.hackerearth.com/challenges/",
    "HackerRank": "https://www.hackerrank.com/", "CodeChef": "https://www.codechef.com/",
    "JobsNet": "https://jobsnet.in/", "YoHire": "https://yohire.in/",
    "FreshersBridge": "https://www.freshersbridge.in/", "JoinSaarthi": "https://joinsaarthi.com/",
    "Preplaced": "https://www.preplaced.in/", "TalentBattle": "https://talentbattle.in/",
    "PrepInsta": "https://prepinsta.com/", "FreshersNow": "https://www.freshersnow.com/",
    "Adzuna": "https://www.adzuna.com/", "Shine": "https://www.shine.com/job-search/",
}

