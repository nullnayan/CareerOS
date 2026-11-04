# CareerOS: free job discovery expansion and implementation handoff

Prepared 1 November 2026, Asia/Kolkata. This document is an implementation plan, not a claim that these integrations are already implemented.

## 1. Objective and non-negotiable constraints

Expand the existing personal CareerOS into a broad job-discovery system for Indian B.Tech CSE/AI students, particularly 2027 graduates. Retain the ability to change roles, geography and graduation year. Cover direct employers, recruiting systems, job platforms, internships and hiring challenges. Keep every source in the inventory even if integration is unavailable.

The user requires a solution with no mandatory payments and no dependence on expiring free trials or small promotional API allowances. Interpret this as **ongoing local operation without purchased scanning credits**, not infinite requests or a guarantee that third parties will stay accessible forever.

- No subscriptions, paid job-data providers, paid proxies, CAPTCHA-solving services, paid hosted scraping actors, required cloud hosting or credit-card-required trials.
- No automatic paid fallback after a free allowance is exhausted.
- Discovery, extraction and ranking must work without an LLM API. Existing Groq chat and optional tailoring features remain separate and unchanged. Rate-limited AI keys are not a foundation for unlimited discovery.
- Use existing local Python, PostgreSQL, Docker and the durable worker. Local operation still uses the user's hardware, electricity, disk and internet. It does not run while the computer is asleep or off.
- Honor source polling limits, access requirements and redistribution conditions. Technical reachability does not establish permission to bulk collect or republish content.
- Do not bypass access controls, CAPTCHAs or account restrictions, or add proxy rotation to evade blocks. A blocked source must back off and show its real status.
- No source can be promised permanently available. Unsupported sources remain visible as unsupported instead of returning fabricated success or being silently omitted.
- No claim of collecting all internet jobs, 90% market coverage, guaranteed interviews or guaranteed permanent uptime.
- Avoid a product-imposed daily job-count/paywall quota. Resource limits are explicit resumable budgets, not hidden truncation. Fair-use throttles remain necessary.

The required result is a maintainable, expandable service with honest coverage and useful eligible jobs. Completion means the agreed source implementations pass verification, not that every internet site has become accessible.

## 2. Workspace, current state and working rules

Project: `C:\Users\nayan\Downloads\careeros_scaffold\careeros`.

- Frontend: Next.js, `http://127.0.0.1:3000`.
- Backend: FastAPI, `http://127.0.0.1:8010`.
- PostgreSQL and Qdrant are provided by Docker. Docker also runs isolated LaTeX compilation.
- A separate `automation.worker` processes durable tasks. The existing desktop launcher can start it.
- The user manages their server terminals. **Do not start, stop or restart frontend, backend, worker or Docker during implementation.** Reading health is allowed. Source reload may happen under development mode; call out material effects before edits. Do not use the desktop start/stop controls to test this work.
- Do not run migrations against personal data without preparing a local backup and inspecting the additive migration. Reuse applicable project instructions and existing authorization. Do not delete/reset databases or overwrite accounts, masters or applications.
- Inspect AGENTS.md instructions and current code/docs again at implementation time. Do not assume this snapshot remains current.
- Do not read or print environment files, passwords, browser cookies or credential values merely to implement discovery. Use configured-status checks. No secret belongs in fixtures, logs, URLs shown to users or the report.
- Use the existing checkout unless project instructions require otherwise. This directory was not a Git repository when previously inspected: verify before using Git, and create scoped file backups if needed.

### Features that already work and must remain intact

- Personal workspace, without the old authentication UI.
- Master resume upload/paste, optional PDF, compilation and automatic Groq repair. Original source remains preserved; master activation is explicit.
- Skills-only job-specific tailoring with up to five confirmed missing skills and immutable output.
- Job preferences, Greenhouse/Lever connectors, optional Adzuna, manual import, source health and immutable JD history.
- Durable discovery/preparation worker, application ledger and paired browser extension.
- Browser autofill assists selected basic empty fields; final submission and file upload remain manual.

This project phase is **discovery**, not universal auto-apply, account linking or an overhaul of resume features.

### Read first

`README.md`, `IMPLEMENTATION_STATUS.md`, `JOB_DISCOVERY_SETUP.md`, `AUTOMATION_SETUP.md`, `PERSONAL_MODE_SETUP.md`, `LATEX_COMPATIBILITY.md`, and this plan.

Primary implementation paths:

- `backend/jobs/connectors.py`, `schemas.py`, `service.py`, `matching.py`.
- `backend/api/jobs.py`.
- `backend/automation/service.py`, `worker.py`.
- `backend/db/models.py`, `session.py`, migrations.
- `backend/tests/test_job_discovery.py`, `test_automation.py`, `test_automation_pdf.py`, `test_autofill.py`.
- `frontend/app/jobs/page.tsx`, `frontend/app/lib/jobs.ts`, automation UI.
- Existing discovery/automation browser verifiers under `backend/scratch`.

## 3. Verified defect and current scaling limitations

### Import defect: reproduce and fix before adding sources

Public Stripe and Point72 Greenhouse feeds were successfully retrieved on 1 November 2026. Their ingestion failed when reproduced in a disposable SQLite database using `Session(..., autoflush=False)`.

Production `SessionLocal` has `autoflush=False`. Multiple source listings can resolve to the same canonical job before pending dependent objects have been flushed. Subsequent database queries do not see pending `JobDescriptionRevision` and/or `JobMatch` objects. This queues duplicate rows and produces unique-constraint failures for:

- `(job_id, content_hash)` in `job_description_revisions`.
- `(user_id, job_id)` in `job_matches`.

Fix ingestion so same-batch canonical duplicates and repeated description hashes reuse pending/persisted objects correctly. Options include a carefully placed flush and/or explicit per-batch identity maps. Preserve distinct source occurrences, original application URLs and complete descriptions. Do not weaken uniqueness constraints or discard valid duplicates before preserving provenance.

Create regression cases with **autoflush=False**, including multiple native IDs mapping to the same canonical URL and identical content. Cover repeated refreshes and cross-source duplicates too. Current tests often use default autoflush, which can hide this defect.

### Other limitations to inspect and address

- `/jobs/sources` currently caps the workspace at 12 sources. This is insufficient for a company directory.
- `SourceInput.provider` currently permits only Greenhouse, Lever and Adzuna.
- Greenhouse currently processes up to 1,500 records; Lever up to ten 100-record pages. A truncation is partial, not proof of complete coverage.
- `/jobs` currently loads and assesses every stored job before returning a capped slice. It lacks real page navigation. Adding thousands of jobs requires indexed querying and paginated UI.
- Manual import generates a new source native ID each time; dedupe behavior must remain correct.
- The worker currently treats one global refresh as one discovery task. Refresh stale-claim recovery is ten minutes and task leases are twenty minutes. Adding many sources could exceed these assumptions.
- Source failures should retain prior listings; incomplete search windows must never close unseen jobs.
- Existing Adzuna credentials returned 401. The user rejects its subscription model. Keep Adzuna excluded from the new free setup; do not delete credentials or disturb historical jobs.

## 4. Source access register

Every source must have separate **access classification**, **implementation status** and **observed health**. A community tool existing does not make it official, approved, free forever or tested.

Suggested access classifications: documented public API, documented public MCP, documented feed, authorized partner API, assessed public-page extraction, user-assisted import, unverified, unavailable, excluded-paid.

Implementation states: inventoried, researching, prototype, tested, enabled, disabled. Health: never checked, healthy, partial, rate limited, login required, permission required, blocked, changed format, unreachable.

Record documentation URL, date checked, authentication requirements, attribution conditions, cost/trial status, polling floor, pagination support, description completeness, publication-date reliability and known geography limitations.

### A. All 14 originally inventoried job platforms

| Source | Current assessment | Required next action |
| --- | --- | --- |
| LinkedIn | Community JobSpy/MCP implementations exist; no official unrestricted job-search API established for our use. Platform restricts automated activity. | Assess permitted access; do not assume a scraper is approved or enable unattended account automation. Retain external/manual route. |
| Naukri.com | JobSpy and community Naukri MCP implementations exist; open official search API not verified. | Evaluate isolated read-only search where permitted; separate candidate account actions from discovery. |
| Unstop | Internal JSON search route was proposed in the pasted chat but was not successfully verified in this audit. | Validate actual route, permission, response schema, pagination, batch dates and descriptions; otherwise mark unverified. |
| Internshala | Public listings exist; external job-search API/MCP not verified. | Assess integration permission and allowed collection; retain reviewed import. |
| Wellfound | Official Wellfound/Reach MCP documentation concerns recruiter applications/candidate sourcing. | Do not use recruiter MCP as a job-seeker feed. Assess candidate/public listings separately. |
| Indeed | JobSpy advertises support. Official partner APIs do not establish an unrestricted public search feed. | Evaluate permitted community access or approved integration; no paid subscription dependency. |
| Foundit | Open job-search API/MCP not verified. | Assess partner/public-page options individually. |
| Cutshort | Public listings exist; supported external search API not verified. | Inspect supported access before implementation; do not label private requests a public API. |
| Instahyre | Employer ATS integrations documented, not proof of catalogue export access. | Assess job-seeker access separately. |
| Hirist.tech | Public listings readable; open supported search API not verified. | Assess structured page extraction/access conditions. |
| AICTE Internship Portal | Public listings exist; self-service external API not verified. | Assess official feed/permission and permitted public-page extraction. |
| National Career Service | Partner integration is documented; self-service credentials not verified. | Investigate partner route; no assumption that a jobseeker login authorizes API export. |
| Remotive | Documented public API/RSS. Public jobs delayed by 24 hours; attribution/link-back and reuse conditions apply. | Implement only if current conditions fit personal CareerOS use. Label delay. |
| Jobicy | Documented REST API, RSS and read-only MCP. Public data has window/delay limits; some enhanced/direct-link access may be commercial. | Use only genuinely public ongoing access, attribution and source links. Reject commercial features. Verify current windows/limits. |

### B. All nine originally inventoried recruiting-system groups

| Source family | Approach |
| --- | --- |
| Greenhouse | Existing documented public Job Board GET connector. Repair imports and verify all-page handling. |
| Lever | Existing documented postings connector. Verify pagination and region handling. |
| Ashby | Add documented public job-postings API; board name per employer. |
| SmartRecruiters | Add documented company Posting API; verify external posting access separately from authenticated/internal operations. |
| Workable | Add documented public published-job endpoints; do not require employer-admin API tokens for public boards. |
| Workday | Discover tenant/host/career-site identifiers per employer. Official integrations require appropriate tenant authorization; assess external careers access separately. |
| Oracle Recruiting / Taleo | Treat as two adapter families with employer-specific sites. Investigate supported feeds or authorized APIs; assess public careers extraction separately. |
| SAP SuccessFactors | Official recruiting/OData access requires appropriate permissions. Assess each employer's external careers pages independently. |
| iCIMS | Documented Job Portal API shows authentication. Use authorized access or separately assess employer public careers pages. |

### C. Additional named sources: retain all in inventory

- **Himalayas:** documented official remote-job MCP with unauthenticated public search and OAuth for personal features. Check ongoing access conditions and any API/feed alternative for background synchronization.
- **Glassdoor, ZipRecruiter, Bayt, BDJobs, HelloWork:** advertised JobSpy sources. Evaluate separately. Their geography coverage differs; do not represent Bangladesh/France/US-only results as India opportunities.
- **FirstNaukri, Cuvette, YC Work at a Startup:** separate discovery targets; open supported export API not verified.
- **HackerEarth, HackerRank, CodeChef:** hiring challenge/event discovery. Assessment APIs are not necessarily job-search APIs. Inspect actual live opportunities and do not imply contests guarantee interviews.
- **JobsNet, YoHire, FreshersBridge, JoinSaarthi, Preplaced, TalentBattle, PrepInsta, FreshersNow:** secondary links/drive discovery. Confirm each domain, feed, attribution and extraction conditions. Link announcements to original employer listings and dates. Do not assume hourly accuracy.
- **Adzuna:** excluded from free-only expansion. Keep history and configured secrets intact. Disable its connected source only through the existing source setting, and report the change.

Avoid treating alternate spellings as new sources: LinkedIn/linkdin; Naukri/Naukri.com; Unstop/Instop/Unshop. Ask only if an actually different URL is supplied. Edureka is not Adzuna and is not a required job source.

### D. Direct-employer directory targets

Retain these previously named employers as directory candidates, not promises of current jobs or verified ATS mappings:

Amazon, Microsoft, Google, Adobe, Salesforce, Oracle, SAP, IBM, Zoho, Freshworks, Razorpay, PhonePe, Flipkart, Meesho, TCS, Infosys, Wipro, HCLTech, Accenture, Cognizant, Capgemini, ION Group, JPMorgan Chase, Goldman Sachs, Morgan Stanley, Canonical, Stripe, Point72, Postman, Twilio, CRED, Netflix, Atlan, Linear, Deel, NVIDIA, Mastercard, Dell, Target.

Also retain employers named as examples in the pasted chat: Zepto, Groww, Walmart, Juspay, ServiceNow, Cisco, PayPal, Thoughtworks, HPE, Wipro, Cognizant, Deloitte, Tekion, and relevant additional startups found during directory discovery. Deduplicate employer aliases. Never copy an assumed company-to-ATS mapping from the chat without checking its current official careers link.

Start with employers offering India/remote internships and 2027 graduate opportunities. Expand the directory in batches; an arbitrary list size is not a coverage guarantee.

## 5. Architecture and contracts

Use the existing backend and durable worker; no new cloud service or separate MCP server per site is required.

### Discovery connectors

Group code by provider, with one registry dispatching to adapters. Separate provider code from persistence and eligibility assessment. An adapter accepts source configuration, broad queries, cursors and a bounded execution budget. It returns normalized listings plus explicit scan metadata.

Extend rather than discard the existing Listing/Snapshot contracts. Required scan metadata includes:

- Exact scan scope: full company board versus filtered/time-window search.
- Completion status, cursor/checkpoint, pages and record counts.
- Truncation reason, skipped/malformed records, warnings and retry time.
- Whether missing records can be considered closed. Default false for search windows, aggregators and incomplete scans.

A budget controls resource use **per execution**, not a lifetime job allowance. Resume unfinished work with persisted checkpoints. Detect repeated pages/cursors, avoid infinite pagination, and declare partial coverage rather than silently slicing records.

### Normalized records and provenance

Preserve native source ID, provider/source instance, requisition ID when known, title, company, location(s), remote restrictions, employment type, source URL, original apply URL, full description or explicit excerpt status, parsed facts and provenance.

Keep publication time, source update time, first-seen time and last-verified time distinct. Unknown publication times stay unknown. Never map updated_at or search-engine crawl time to a fabricated posting date.

Use source/native ID for source identity, canonical application URLs for strong cross-source matches and exact fingerprints as a secondary signal. Do not merge different jobs just because employer, title and location match. Preserve all source occurrences. Do not strip query parameters needed to identify the vacancy. A short excerpt cannot overwrite a full employer JD.

### Source directory

Store provider, employer, verified careers URL, board/tenant/site identifiers, access classification, enabled state, last verification and applicable conditions. Registry entries must not claim a website has been tested when it has only been researched.

Provide safe URL/provider detection for known public board hosts. Arbitrary URL extraction needs SSRF protection: validate destinations and redirects, block local/private/link-local addresses, restrict schemes/ports, bound response size and time, and never fetch browser-provided credentials.

### JobSpy evaluation

JobSpy is an optional community library; MCP is not required. Use a pinned version after review. Evaluate it in a separate local virtual environment or bounded subprocess so it does not upgrade the running backend's dependencies or hang the worker.

Do not install an arbitrary latest MCP package with broad account permissions. Review dependencies, licenses and read/write capabilities. Keep login, messaging, profile editing and application submission disabled/out of scope. Do not copy cookies from the user's main browser profile.

Record actual failures, supported/ignored filters and incomplete results. No proxies, paid hosting or automatic account-based retries. A tool advertising a platform does not satisfy acceptance criteria without a working permitted read-only test.

## 6. Matching, query planning and freshness

- Reuse existing rule-based matching; do not introduce mandatory LLM scoring.
- Search several broad role families, then inspect complete descriptions locally for skill aliases, seniority, experience, graduation batch, institution and location restrictions.
- Include software engineer/developer, backend, full stack, frontend, intern, graduate and trainee families. Do not simply AND every skill in the resume.
- Avoid relying solely on portal experience tags, but preserve hard eligibility requirements extracted from the JD. Unknown is not eligible by default.
- Partition searches by supported role/location/time windows when needed; deduplicate overlap and track which partitions were actually scanned.
- Resume from a prior successful watermark with overlap to cover delayed indexing and clock differences. Do not filter only the last hour after downtime.
- Label reposts/updates when identifiable. An old vacancy first seen today is not necessarily newly published.
- A provider's explicit publication delay must appear in its status; no promise of immediate discovery from a delayed feed.
- Add configurable relevance/newest sort and database-backed pagination. Users must be able to browse all retained results without a hidden 100/300-result UI ceiling.
- Keep relevance distinct from ATS score or interview probability.

## 7. Scheduling, failure isolation and scale

Extend the existing worker to support per-source/checkpoint work or bounded discovery batches. Preserve leader locking, deduplication, task recovery, pause/cancel behavior and maximum preparation queues.

- Apply per-provider concurrency and minimum polling intervals. Retry-After takes precedence.
- Back off 429/temporary failures; stop repeated unauthorized/login/CAPTCHA attempts and show action required.
- Separate a global discovery coordinator from source execution so one slow board cannot hold the entire refresh indefinitely.
- Reconcile ten-minute refresh claims and twenty-minute worker leases with the new task design. Renew leases or bound tasks; do not queue overlapping scans after an arbitrary stale timeout.
- Use idempotent ingestion and cursor commits. Do not hold database transactions open across slow network requests.
- Expose cancellation checkpoints and preserve prior successful data on failure.
- A zero-result response is not automatically a ban. Check schema/login/redirect signals and compare with previous health. Label suspicious results as needing review, without inventing a cause.
- Enable cache/conditional requests when supported. Avoid re-fetching every unchanged full JD.
- Keep scanning limits separate from the existing daily PDF-preparation limit; do not remove the PDF limit as a side effect of this work.
- Preserve the user's paused/enabled schedule state. Do not enable recurring work merely to test it.

## 8. UI requirements

Extend Jobs/Sources instead of creating a disconnected admin product.

- A source directory showing access method, connection/setup state, free/trial/paid classification, last check, last success, record counts, errors, scope and limits.
- Add a supported employer board by URL/identifier. Detect provider where reliable, explain required identifiers otherwise.
- Replace the twelve-source ceiling with a scalable directory and operational budgets. Do not promise an infinite number of simultaneous requests.
- Explicit enabled/disabled controls; remove Adzuna from suggested free sources and label historical Adzuna access clearly.
- Show sources awaiting permission or implementation without pretending they work.
- Distinguish search of stored CareerOS jobs from live discovery. Show live refresh progress/partial failures.
- Pagination, sorting, eligible/review filters, source filters, saved/dismissed filters and source attribution.
- Display published versus first-seen dates accurately, full-JD versus excerpt status, stale verification and closure status.
- Links to reviewed manual/browser import remain available. Importing one permitted JD does not turn a platform into a crawler.
- Preserve mobile layouts and existing Tailor/Track application actions.

## 9. Implementation stages and gates

### Stage 0: baseline and backups

Reinspect instructions, source files and migrations. Record current source count, enablement, schedule state and job counts through existing interfaces without exposing credentials. Prepare scoped code/config backups if Git is unavailable. Back up the database before any additive migration. Do not modify profile, resume or applications to create test cases.

### Stage 1: existing ingestion correctness

Implement the autoflush regression fix, idempotent import cases, source failure preservation and accurate partial-scan metadata. Confirm Stripe/Point72 with small read-only live probes plus disposable ingestion, not just mocked JSON. Do not bulk-import to the real workspace as a test.

Gate: tests pass under production-like autoflush behavior and repeated refreshes do not duplicate revisions, matches or jobs.

### Stage 2: source register, scalable data access and company APIs

Add the source capability registry and additive metadata only where needed. Implement Ashby, SmartRecruiters and Workable. Extend safe board URL validation and source input options. Add database-backed job pagination and necessary indexes; remove repeated whole-database reassessment from normal feed reads where practical, with proper invalidation on changed preferences/master/JD.

Gate: provider fixtures, page/empty/partial/error tests, integration tests and small live probes pass. Directory claims reflect actual verification.

### Stage 3: ongoing public feeds and MCP-backed job sources

Implement public ongoing-access portions of Jobicy, Himalayas and Remotive only after checking current conditions. Prefer direct APIs for the worker where supported; use an MCP client only where it adds capability. Record windows, delays and attribution. No commercial API upgrade.

Gate: no card, trial countdown or purchased quota is needed for enabled access. Missing items from rolling feeds do not close saved jobs.

### Stage 4: community/platform pilots

Evaluate JobSpy for Naukri, LinkedIn, Indeed and other listed supported portals, individually and subject to permitted access. Validate Unstop independently rather than trusting the pasted endpoint. Research all remaining listed platforms. Ship only working, acceptable, cost-free connectors. Leave remaining entries in honest permission-required/unverified states.

Gate: a source must return real useful data in a permitted read-only test, report access failures, maintain full-JD status and demonstrate sustainable polling. Unsupported filters cannot silently count as applied filters.

### Stage 5: enterprise career sites and secondary discovery

Assess Workday, Oracle Recruiting, Taleo, SuccessFactors and iCIMS employer sites individually. Reuse adapter families where verified. Investigate government partner feeds and permitted challenge/aggregator extraction. Never request employer-only credentials from a normal student account or fabricate access.

Gate: each added route has a documented access decision and verified mappings. Time-limited/paid-only routes stay excluded from active free discovery.

### Stage 6: automation, UI and end-to-end validation

Complete per-source scheduling/checkpoints, health UI, provenance, dedupe and cancellation. Add eligible batches of verified company connections through the normal application interface after backups, without changing recurring automation state. Do not subscribe, connect personal job accounts or auto-apply.

Final handoff must distinguish implemented/tested, experimentally evaluated, not integrated, and externally unavailable sources. There is no requirement to pretend that an inaccessible website has been solved.

## 10. Verification requirements

Use isolated databases for automated tests. No synthetic jobs, confirmations, applications or profile changes in the user's workspace.

Meaningful backend cases:

- Same-batch duplicate native/canonical identities with autoflush=False; revision/match uniqueness and provenance retained.
- Existing full descriptions preserved against aggregator excerpts.
- Full pagination, repeated cursor detection, resumable truncation, schema errors and valid empty results.
- Source/network/auth/rate-limit failures with existing listings preserved and Retry-After honored.
- No closure from partial pages, rolling windows, blocked requests or query-specific scans.
- Correct time semantics, missing dates, aliases, foreign-remote restrictions, 2027 eligibility and unknown joining dates.
- Pause/cancel, lease recovery, non-overlapping source tasks, bounded subprocess timeouts and clean task completion.
- SSRF/redirect and response-size boundaries for any new generic URL path; secret-free failure messages.
- Owner isolation, job-feed pagination, sorting and invalidation after preference/master changes.

Run existing relevant discovery, automation, application, autofill and tailoring regressions. No need to rebuild unrelated features. Run meaningful compiler coverage only if related changes justify it and Docker is already available.

Frontend: typecheck/build using a separate output directory (`CAREEROS_NEXT_DIST_DIR=.next-release-check`), never overwrite a running dev server's `.next`. Use disposable/mocked browser flows for source setup, status, partial refresh, pagination, details, Tailor handoff and responsive layout. Do not launch real background searches merely by opening a QA page.

Live source probes: small, read-only, bounded and attributable. Record date, version, endpoint family, scope, returned count, description completeness, duration and failure class. A successful probe is not an uptime guarantee. Do not probe paid endpoints or consume promotional trials.

## 11. Measuring success

Create a reproducible reference set from permitted manual searches and official employer listings for a fixed set of roles, locations and times. Record known eligible listings, fetched listings, duplicates, stale jobs, missing fields, missed reference listings and failures.

Report recall against this **explicit reference set**, not the entire internet. Also report source coverage, successful versus partial scans, successful refresh age and operating requirements. Show incremental unique eligible jobs per source to determine useful priorities. Do not add overlapping source percentages together.

## 12. Current documentation pointers (reverify before enabling)

- Greenhouse: https://docs.greenhouse.io/job-board
- Lever: https://github.com/lever/postings-api
- Ashby: https://developers.ashbyhq.com/docs/public-job-posting-api
- SmartRecruiters: https://developers.smartrecruiters.com/docs/endpoints
- Workable public endpoints: https://help.workable.com/hc/en-us/articles/115012771647-Using-the-Workable-API-to-create-a-careers-page
- JobSpy: https://github.com/speedyapply/JobSpy
- MCP wrapper: https://pypi.org/project/mcp-jobspy/
- LinkedIn automation guidance: https://www.linkedin.com/help/recruiter/answer/a1340567
- Wellfound recruiter MCP: https://help.wellfound.com/article/1219-connect-wellfound-to-your-ai-assistant
- Wellfound Reach MCP: https://help.wellfound.com/article/1221-connect-wellfound-reach-to-your-ai-assistant
- Instahyre employer integration: https://help.instahyre.com/en/article/get-started-with-ats-integration-14s0ijg/
- Remotive: https://remotive.com/remote-jobs/api
- Jobicy: https://jobicy.com/jobs-rss-feed
- Himalayas: https://himalayas.app/docs/remote-jobs-mcp
- iCIMS: https://developer-community.icims.com/applications/applicant-tracking/job-portal
- Oracle Recruiting: https://docs.oracle.com/en/cloud/saas/human-resources/farws/api-recruiting-job-requisitions.html
- Taleo integration: https://docs.oracle.com/en/cloud/saas/talent-acquisition/17.6/tsscg/taleo-configuration.html
- AICTE portal: https://internship.aicte-india.org/
- NCS portal: https://www.ncs.gov.in/

## 13. Prompt to start implementation in a new chat

> Continue CareerOS at C:\Users\nayan\Downloads\careeros_scaffold\careeros. Read FREE_JOB_DISCOVERY_IMPLEMENTATION_PLAN.md and the existing project instructions/docs first, then implement the plan in stages. The requirement is ongoing free local job discovery: no paid APIs, expiring trials, subscriptions, paid proxies, required cloud services or mandatory AI usage for discovery. Keep all listed sources in the register; verify access rather than promising all internet jobs or unlimited third-party requests. Begin with the verified autoflush=False ingestion bug and existing-source regression tests, then add the source registry and documented company-board connectors. Preserve the working master resume, skills-only tailoring, user data and current automation enablement. I manage server terminals: do not start, stop or restart frontend, backend, worker or Docker. Test with isolated databases and a separate frontend build directory. Proceed autonomously with routine authorized implementation; report any source that requires external permission or payment instead of substituting a paid service or claiming it is connected. No auto-apply or job-account credential collection in this phase. Finish with exact changes, validation results, remaining source limitations and any restart instructions for me to execute.


## Execution follow-up — 2 November 2026

See [DISCOVERY_COMPLETION_REPORT.md](DISCOVERY_COMPLETION_REPORT.md) and [all 45 source entries](SOURCE_ACCESS_REVIEW_2026-11-02.md).

- Review defects: fixed, with regression tests.
- Conditional HTTP caching: implemented with bounded process-local validators.
- Full traversal closure reconciliation: implemented with durable checkpoints and conservative invalidation.
- Stored Jobicy/Himalayas status synchronization: implemented with bounded rotating work; live Himalayas response verified, live Jobicy probe timed out.
- Employer directory expansion: four mappings added; unsuccessful old Postman/PhonePe identifiers excluded.
- Broader platform/enterprise adapters, remaining employer mappings and an independent market-coverage benchmark: still unfinished. Do not present the entire original plan as complete.
- Personal records/source connections and recurring-automation settings were preserved. No servers restarted.
