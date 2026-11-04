# Source access register — 2 November 2026

**Latest source assessment and executable-tool status:** [SOURCE_TOOLS_IMPLEMENTATION_REPORT.md](SOURCE_TOOLS_IMPLEMENTATION_REPORT.md) contains the updated exhaustive 45-entry table and all 51 employer candidates. The table below is the earlier snapshot; its enterprise/no-adapter statements are superseded by fixture-tested Workday and explicit employer-feed profiles. No new live collectors or personal connections are claimed. The application register comes from `backend/jobs/access_review.py` and `registry.py`.

All 45 named entries are retained. This is an implementation/access inventory, not a claim that every source was newly probed or connected. Last documentation/probe dates remain visible in the app. Workspace connections and live health are separate.

| Source | Implemented route | Remaining prerequisite / limit |
| --- | --- | --- |
| [Greenhouse](https://docs.greenhouse.io/job-board) | Public JSON adapter; explicit workspace connection | Company-published board only. Public reachability does not grant bulk redistribution rights. |
| [Lever](https://github.com/lever/postings-api) | Public JSON adapter; explicit workspace connection | Company-published board only. Public reachability does not grant bulk redistribution rights. |
| [Ashby](https://developers.ashbyhq.com/docs/public-job-posting-api) | Public JSON adapter; explicit workspace connection | Company-published board only. Public reachability does not grant bulk redistribution rights. |
| [SmartRecruiters](https://developers.smartrecruiters.com/docs/endpoints) | Public JSON adapter; explicit workspace connection | Company-published board only. Public reachability does not grant bulk redistribution rights. |
| [Workable](https://help.workable.com/hc/en-us/articles/115012771647-Using-the-Workable-API-to-create-a-careers-page) | Public JSON adapter; explicit workspace connection | Company-published board only. Public reachability does not grant bulk redistribution rights. |
| LinkedIn | No collection adapter; original-site / reviewed-import route only | Automated activity restricted; community JobSpy support is not permission. No unattended account access. |
| Naukri.com | No collection adapter; original-site / reviewed-import route only | JobSpy advertises Naukri support; official permitted search/export route was not established. No package installed into the running backend and no account-based pilot. |
| [Unstop](https://unstop.com/jobs) | No collection adapter; original-site / reviewed-import route only | Public jobs route returned a cookies/JavaScript requirement during review. No supported export route or collection permission verified; manual import only. |
| [Internshala](https://internshala.com/terms) | No collection adapter; original-site / reviewed-import route only | Terms restrict data mining/extraction and copying without an applicable agreement. No automated collector enabled; use the original site or material you may import. |
| [Wellfound](https://wellfound.com/terms) | No collection adapter; original-site / reviewed-import route only | General Terms restrict harvesting/copying and disclosure of opportunities. Recruiter/Reach MCP is not a candidate job feed; no background export enabled. |
| Indeed | No collection adapter; original-site / reviewed-import route only | JobSpy support does not establish platform collection permission. No unrestricted candidate job-search API verified; manual import only. |
| Foundit | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| Cutshort | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| Instahyre | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| Hirist.tech | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| [AICTE Internship Portal](https://internship.aicte-india.org/) | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| [National Career Service](https://www.ncs.gov.in/) | No collection adapter; original-site / reviewed-import route only | Partner authorization must be established separately from jobseeker login. |
| [Remotive](https://remotive.com/remote-jobs/api) | Public JSON adapter; explicit workspace connection | 24-hour publication delay. Visible Remotive attribution and link-back required; no third-party syndication. Read-only public adapter tested; workspace connection is explicit. |
| [Jobicy](https://jobicy.com/jobs-rss-feed) | Public JSON adapter; explicit workspace connection | Public listing URLs only; seven-day rolling window, three-hour delay, cursor expires in 24 hours. Commercial direct ATS URLs excluded. Stored listings use the free batch status endpoint: explicit closed closes an occurrence; unknown stays unconfirmed. Workspace connection is explicit. |
| [Himalayas](https://himalayas.app/api) | Public JSON adapter; explicit workspace connection | Unauthenticated allowance shared; daily refresh, attribution and unchanged applicationLink required. pubDate is an UPDATE time. Expiry filtered, original applicationLink retained. Daily shared-allowance access, not unlimited. Older stored occurrences are checked in bounded batches through the single-job API; 410 confirms closure and 404 stays unknown. |
| Glassdoor | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| ZipRecruiter | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| Bayt | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| BDJobs | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| HelloWork | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| FirstNaukri | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| Cuvette | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| YC Work at a Startup | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| HackerEarth | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| HackerRank | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| CodeChef | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| JobsNet | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| YoHire | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| FreshersBridge | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| JoinSaarthi | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| Preplaced | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| TalentBattle | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| PrepInsta | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| FreshersNow | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| Adzuna | Excluded from free scanning | Excluded from free expansion. Historical records and credentials retained; existing enablement is not changed by code. |
| Workday | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| [Oracle Recruiting](https://docs.oracle.com/en/cloud/saas/human-resources/farws/api-recruiting-job-requisitions.html) | No collection adapter; original-site / reviewed-import route only | Tenant-specific HCM requisition API is not an unrestricted public catalogue. Employer external careers routes need separate verification. |
| Taleo | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| SAP SuccessFactors | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |
| [iCIMS](https://developer-community.icims.com/applications/applicant-tracking/job-portal) | No collection adapter; original-site / reviewed-import route only | Manual reviewed import only until supported, permitted free access is verified. |

## Specific outstanding work

- Supported public APIs: code and review fixes are implemented; connections are selected in Jobs → Sources. Ten company mappings are suggested, not a catalogue of every employer.
- Restricted platforms: an applicable supported export/permission route is still needed. No account passwords, cookies, CAPTCHA solvers or paid proxy services were added.
- Unverified platforms: access and schema assessment is still unfinished; absence of a verified route is not proof that integration is impossible.
- Enterprise ATS: verify each employer site and feed separately before writing/enabling that adapter. A single authenticated enterprise API does not export every tenant.
- Secondary names with uncertain domains require identification of the actual service; no guessed domains are crawled.
- Market coverage: a broader independent eligible-job benchmark is still needed. Current fixture, browser and live-board checks do not measure all internet jobs.

There is no per-user lifetime scan quota in CareerOS. Polling floors, bounded executions, response limits and provider rate limits are operational constraints and remain enforced.
