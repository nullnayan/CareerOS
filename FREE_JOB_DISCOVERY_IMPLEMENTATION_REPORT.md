**2 November follow-up:** See [DISCOVERY_COMPLETION_REPORT.md](DISCOVERY_COMPLETION_REPORT.md) for review fixes, full-traversal closure, feed status checks, caching, directory verification and unresolved integrations. Earlier single-snapshot-only closure notes are superseded.

# Free local discovery implementation — 1 November 2026

The implemented release repairs existing ingestion, adds three company APIs and three public feeds, retains the full source inventory, and adds resumable bounded discovery and database pagination. It does **not** turn the unverified platform inventory into connected integrations. No paid provider, trial, proxy, cloud service, mandatory discovery AI, application submission, or job-account credential collection was added.

## Preservation and operational record

- No frontend, backend, worker, or Docker service was started, stopped, or restarted. Browser QA served static build artifacts through Playwright interception and used an in-process disposable API client.
- Before/after checks: **398 personal jobs**, the same active master revision, the same five source enablement flags, and unchanged automation settings: disabled, 60-minute interval, preparation enabled, five pending preparations, minimum relevance 60, five PDFs/day.
- Existing sources remain Adzuna India, Canonical, Point72, Stripe, and ION. New adapters and directory suggestions were not automatically connected to personal data.
- Adzuna's existing enabled flag was preserved. The free-only coordinator excludes it, and new Adzuna connections are rejected. Credentials and historical listings were untouched. It can still be disabled through its existing source control.
- No synthetic jobs, resumes, profile changes, applications, or skill confirmations entered the personal database.
- This checkout has no Git repository. Scoped original discovery/UI backups: `.implementation-backups/free-discovery-20261101/code-before.zip`.
- PostgreSQL backup before indexes: `.implementation-backups/free-discovery-20261101/before-indexes.sql`, 9,190,523 bytes. Its contents were not printed.
- Applied additive migration: `301101_discovery_indexes`. It adds five lookup indexes and changes no user records or uniqueness constraints. Upgrade and downgrade were exercised on disposable SQLite first.

## Exact code changes

| File | Result |
| --- | --- |
| `backend/jobs/service.py` | Flush dependent revisions, occurrences and matches after each ingested listing. Preserve canonical provenance and full JDs against excerpts. Cache rule-based assessments with preference/resume/confirmed-skill/day versions. Preserve original feed application links in output. |
| `backend/jobs/connectors.py` | Expanded scan metadata; resumable ingestion budgets; Lever pagination offsets/repeated-ID checks; conservative publication dates; fixed documented API hosts, HTTPS validation, response size/time limits and restricted redirects; safe provider detection. Retain identifying query parameters such as `ref`. |
| `backend/jobs/company_connectors.py` | New Ashby, SmartRecruiters and Workable adapters. SmartRecruiters fetches full sections with bounded detail requests and offset continuation. Workable collects description, requirements and benefits. |
| `backend/jobs/public_feeds.py` | New Remotive, public Jobicy, and unauthenticated Himalayas adapters. Preserve attribution, source links, delay/window information, full/excerpt status and cursors. Himalayas retains update/expiry/timezone facts and its unchanged application link. |
| `backend/jobs/registry.py` | 45 provider/platform entries plus 51 employer candidates, retaining every source/employer named in the plan, with Oracle Recruiting and Taleo separate. Access classification, implementation, observed probe and workspace health are separate. |
| `backend/jobs/scheduling.py` | Durable source state/checkpoints stored as `source_state` control rows in existing refresh metadata. Poll floors, paced continuation pages, permission stops, and durable Retry-After/backoff. Control rows are excluded from refresh history. |
| `backend/jobs/schemas.py` | Supported company APIs, public feeds and known-host automatic detection accepted by source setup. |
| `backend/jobs/matching.py` | Preserve India timezone restrictions, reject expired listings, and recognize fresher batch notation such as `2026/27`. Discovery remains deterministic and local. |
| `backend/api/jobs.py` | Remove twelve-source cap. Publish complete inventory and capability/status metadata. Coordinate bounded batches, persist progress/heartbeats, atomically advance checkpoints with ingestion, and preserve prior jobs on failure. SQL-backed page/filter/sort queries with stale-assessment invalidation. Hide expired feed content and reject expired tailoring handoffs. |
| `backend/automation/service.py` | Pass automatic/manual context, renew a discovery task lease before preparation work, queue paced automatic continuations only while automation is enabled, retain PDF limits, and reject queued jobs that expire before preparation. |
| `backend/db/migrations/versions/301101_discovery_indexes.py` | Index owner/date, owner/rank, job occurrence lookup, owner/application URL, and owner/refresh status/date. |
| `frontend/app/jobs/page.tsx` | Provider detection/company setup, three free-feed controls, full access register, separate candidate directory, source health/scope/next-check visibility, progress polling, pagination, sort, and accurate published/first-seen/verified/source-update labels. Existing details, Save/Dismiss, Tailor, PDF queue and application tracking remain. |
| `frontend/app/lib/jobs.ts` | Types for pagination, register and source scan metadata. |
| `backend/tests/test_job_discovery.py` | Production-like `autoflush=False` fixture, same-batch canonical duplicate regression, conservative Lever date regression. |
| `backend/tests/test_free_discovery.py` | Provider/empty/malformed/partial pagination fixtures, duplicate provenance, preserved full descriptions, URL/redirect/size boundaries, feed expiry/timezone/attribution, cached SQL pagination/invalidation, persistent cooldown/permission stops, checkpoint expiry/reset and 2027 batch cases. |
| `backend/tests/test_automation.py` | Automatic-context mock update, paced continuation/lease preservation and expired queued-job cases. |
| `backend/scratch/probe_free_discovery.py` | Repeatable read-only probes and twice-repeated in-memory SQLite ingestion; `--only` permits a single provider check. |
| `backend/scratch/verify_free_discovery_ui.py` | Server-free static-artifact browser QA, intercepting every API request into disposable SQLite. |

Next.js added the isolated output directory to `tsconfig.json` during validation; that generated include was removed afterward. Normal `.next` output was not rebuilt.

## Validation

**Final focused backend run: 138 passed, 3 skipped.** Skips are the three opt-in real Docker compiler cases. Compiler behavior was not changed. Existing Pydantic/FastAPI/SWIG deprecation warnings remain.

```powershell
cd C:\Users\nayan\Downloads\careeros_scaffold\careeros\backend
$env:DATABASE_URL='sqlite://'
.\venv\Scripts\python.exe -m pytest tests/test_free_discovery.py tests/test_job_discovery.py tests/test_automation.py tests/test_automation_pdf.py tests/test_applications.py tests/test_autofill.py tests/test_personal_tailoring.py tests/test_master_compatibility.py -q
Remove-Item Env:DATABASE_URL
```

Frontend production build passed for all 21 routes with `CAREEROS_NEXT_DIST_DIR=.next-free-discovery-check`. Browser QA passed 55-job pagination, sorting, stored search, details, save, provider setup, register, partial health, and 390px/700px layouts, with no browser errors or horizontal overflow. Screenshots: `scratch/free-discovery-ui/`.

All source probes were read-only. Returned data was ingested twice only into in-memory SQLite with `autoflush=False`. Observations, UTC timestamps and durations are recorded in `backend/scratch/free_discovery_probe_results.json`; successful probes are not uptime guarantees.

| Provider / board | Observed records | Full descriptions | Disposable result |
| --- | ---: | ---: | --- |
| Greenhouse / Stripe | 745 | 745 | 744 canonical jobs, 744 revisions/matches, 745 occurrences; repeat passed |
| Greenhouse / Point72 | 206 | 197 | 205 canonical jobs/matches, 206 revisions/occurrences; repeat passed |
| Lever / ION | 84 | 83 | 84 jobs/revisions/matches/occurrences; repeat passed |
| Ashby / Ashby | 74 | 74 | Repeat passed |
| SmartRecruiters / own company | 1 | 1 | Deliberately partial one-detail probe; offset returned; repeat passed |
| Workable / Digitals AI Inc | 12 raw | 12 | 11 distinct native identities, 10 canonical jobs/revisions/matches; repeat passed |
| Remotive public | 12 | 12 | Window scan; no closure; repeat passed |
| Jobicy public | 100 | 100 | One page, continuation present; no closure; repeat passed |
| Himalayas public | 20 | 20 | One page, continuation present; no closure; repeat passed |

The Workable example identifier `workable` returned an official redirect and then 404. The adapter was verified against the actual `digitals` employer board. Only the exact redirect from the documented Workable account endpoint to its official widget endpoint is permitted; arbitrary redirects are rejected. See [Workable's documented public endpoint](https://help.workable.com/hc/en-us/articles/115012771647-Using-the-Workable-API-to-create-a-careers-page).

A deliberately tiny reference check used [one manually located 2026/27 fresher posting](https://apply.workable.com/digitals/j/F81B5F03A4): 1 expected, 1 retrieved from its board. This verifies that particular listing, not market recall, broad student eligibility, or comprehensive India coverage. A larger independently curated eligible-listing benchmark remains future work.

## Execution budgets and access conditions

- One refresh selects at most three distinct providers and one source per provider, oldest checked first. Deferred sources remain in the directory. Enabled recurring automation can enqueue a paced follow-up; manual refresh never enables a schedule.
- Company polling floor: one hour. Remotive: six hours; Jobicy: one hour; Himalayas: one day. Continuation pages are paced at least one minute apart. These are execution/polling budgets, not lifetime record quotas.
- Single-response boards ingest at most 1,500 normalized records per execution and resume by offset. Lever walks at most ten 100-record pages per execution. SmartRecruiters fetches at most eight full details per normal source execution. Public cursor feeds fetch one page per execution.
- Requests accept at most 8 MB, have a 20-second connection/read timeout plus elapsed-time checks between chunks, and use fixed API hosts. A slow current socket read can take until its timeout. There is no generic URL crawler, and application URLs are never fetched by the company connectors.
- Checkpoints commit with successful ingestion. Repeated IDs/cursors and cursor cycles stop unsafe pagination. Expired Jobicy traversals restart with a new traversal timestamp.
- Network failures back off exponentially; Retry-After takes precedence. Unauthorized, permission-required and unapproved-redirect states stop automatic source attempts until explicit source re-enable. Re-enable does not establish third-party permission.
- Only a complete single-board snapshot can close missing jobs. Partial, continued, malformed and rolling-feed scans retain them. Multi-execution board traversals currently do not reconcile missing-job closure across pages.
- Run progress heartbeats advance at source completion boundaries. Existing ten-minute stale-claim recovery and twenty-minute worker leases remain; bounded source work avoids a company directory becoming one unlimited refresh, and the worker renews its lease after discovery before preparing drafts.
- A paused schedule does not spawn automatic continuations/preparations; already-started network requests may finish. Cancellation remains the existing queued-task control; this release does not forcibly terminate an individual HTTP request.
- [Remotive](https://remotive.com/remote-jobs/api): public results delayed 24 hours; visible source/link-back required; no syndication to other job boards. No private paid API is used.
- [Jobicy](https://jobicy.com/jobs-rss-feed): public seven-day window, three-hour delay, source listing links and cursor expiry. Commercial direct-ATS link access is excluded. Explicit batch status synchronization for retained jobs outside the window is not implemented; they can remain stale/unknown and are not falsely closed.
- [Himalayas](https://himalayas.app/api): no key required, shared unauthenticated allowance, daily data refresh and attribution requirements. `pubDate` is update time, not original publication. Expired content is hidden and application links remain unchanged. Early closure before supplied expiry can remain unknown; per-listing live status synchronization is not implemented.
- Greenhouse updated times and Workable/Lever created times are not presented as publication dates. Lever's previously inferred publication date is cleared when that listing is next refreshed, while the source creation value remains in facts.

## Sources that remain unavailable or unintegrated

All 45 inventory entries remain visible even when disconnected. All originally named employers remain candidates; no guessed enterprise ATS mappings were added.

- **LinkedIn:** manual route only. [Its current guidance restricts third-party scraping/automation](https://www.linkedin.com/help/recruiter/answer/a1340567). Community support is not collection permission.
- **Naukri, Indeed, Glassdoor, ZipRecruiter, Bayt, BDJobs, HelloWork:** [JobSpy advertises these platforms](https://github.com/speedyapply/JobSpy), but sustainable permitted access was not established individually. The library was not installed, no proxy/cookies/login were used, and no platform pilot is claimed successful.
- **Unstop:** [the jobs page](https://unstop.com/jobs) returned a cookies/JavaScript requirement during review. No supported public export endpoint was verified. No private endpoint from the pasted proposal was assumed to work.
- **Internshala, Foundit, Cutshort, Instahyre, Hirist, FirstNaukri, Cuvette, YC Work at a Startup:** no verified permitted export adapter in this release. Wellfound's recruiter MCP is not used as a candidate feed.
- **Workday, Oracle Recruiting, Taleo, SuccessFactors, iCIMS:** employer/tenant mappings and permitted external routes still need individual assessment. The [Oracle requisitions API](https://docs.oracle.com/en/cloud/saas/human-resources/farws/api-recruiting-job-requisitions.html) is not proof of an unrestricted catalogue; [iCIMS Job Portal API examples require authentication](https://developer-community.icims.com/applications/applicant-tracking/job-portal). No employer-only credentials were requested.
- **AICTE and NCS:** supported public export/partner permission is not established for this workspace. A student login is not treated as API export authorization.
- **HackerEarth, HackerRank, CodeChef:** challenge/assessment APIs are not represented as hiring-opportunity feeds. No contest-to-interview promise is made.
- **JobsNet, YoHire, FreshersBridge, JoinSaarthi, Preplaced, TalentBattle, PrepInsta, FreshersNow:** retained, unverified secondary targets. Domains, collection terms and original-employer provenance need individual verification before connectors can be enabled.
- **Adzuna:** excluded from all new free discovery. Its historical data and configured secrets remain intact.

Conditional HTTP caching, bulk per-listing closure revalidation, full traversal closure reconciliation, a larger reference benchmark, and verified mappings for the remaining employer directory are not implemented. These are explicit remaining engineering tasks, not reasons to substitute paid services.

## Commands for the user

No restart was performed by the agent. The index migration is already applied. When ready, restart the backend and worker in your existing terminals so both processes use the new code. Backend development reload may already have picked up changes; the worker does not automatically reload.

Backend command, after stopping your existing backend process yourself:

```powershell
cd C:\Users\nayan\Downloads\careeros_scaffold\careeros\backend
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8010 --reload
```

Worker command, after stopping your existing worker yourself:

```powershell
cd C:\Users\nayan\Downloads\careeros_scaffold\careeros\backend
.\venv\Scripts\python.exe -m automation.worker
```

Your frontend development process can hot reload. If using production mode, stop it yourself before building its normal output and starting it again:

```powershell
cd C:\Users\nayan\Downloads\careeros_scaffold\careeros\frontend
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

No Docker restart is needed. Open Jobs → Sources to explicitly add company boards or public feeds. Refresh respects cooldowns and may report deferred/partial work. Automation is still disabled; enable it yourself only when you want recurring operation. The machine and existing local worker must remain awake/running for ongoing discovery.
