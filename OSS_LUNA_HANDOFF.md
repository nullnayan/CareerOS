# OSS Luna handoff — Part 1 complete

Date: 3 November 2026  
Workspace: `C:\Users\nayan\Downloads\careeros_scaffold\careeros`

## Scope and status

Part 1 is implemented: upstream repositories were pinned and downloaded, dependencies were installed into isolated runtimes, local wrappers and source profiles were built, normalized output and pagination are covered by tests, and bounded technical probes were recorded. **This work is not connected to the active search route.** The legacy collectors and their configuration remain in place. Personal discovery is still paused.

The repository has no `.git` directory at either the project root or its parent. The root `.gitignore` and `backend/.gitignore` contain narrow runtime ignore rules. [OSS_LUNA_CHANGED_FILES.json](OSS_LUNA_CHANGED_FILES.json) is the file-by-file inventory, including a short purpose for every new or modified file. Downloaded checkouts, environments, browser binaries, and probe JSON are under the ignored `oss-tools/runtime/` directory.

## Installed tools and provenance

| Tool | Version / pinned commit | Isolated interpreter | Lock and license |
| --- | --- | --- | --- |
| JobSpy | `python-jobspy 1.4.1`; `a606f9cf077c34f6ce6cbfcc76238f57b3c20671` | `C:\Users\nayan\Downloads\careeros_scaffold\careeros\backend\.source-tools-venv\Scripts\python.exe` | `oss-tools/locks/jobspy-py311.lock.txt`; `oss-tools/licenses/JobSpy-LICENSE.txt` |
| ats-scrapers | `0.3.0`; `6b44a1badc9bfbf5cf176f75265cc5729e520e99` | `C:\Users\nayan\Downloads\careeros_scaffold\careeros\oss-tools\runtime\environments\ats\Scripts\python.exe` | `oss-tools/locks/ats-py311.lock.txt`; `oss-tools/licenses/ats-scrapers-LICENSE.txt` |
| OmkarCloud Instahyre scraper | Source pinned; no package version metadata; `16a64f440e39a1545ea1322e21c6d8ef654a3358` | `C:\Users\nayan\Downloads\careeros_scaffold\careeros\oss-tools\runtime\environments\instahyre\Scripts\python.exe` | `oss-tools/locks/instahyre-py311.lock.txt`; `oss-tools/licenses/instahyre-scraper-LICENSE.txt` |
| OmkarCloud Internshala scraper | Source pinned; no package version metadata; `4755e7c83ec565e456384dffede100e9dfdc6a3d` | `C:\Users\nayan\Downloads\careeros_scaffold\careeros\oss-tools\runtime\environments\internshala\Scripts\python.exe` | `oss-tools/locks/internshala-py311.lock.txt`; `oss-tools/licenses/internshala-scraper-LICENSE.txt` |
| OmkarCloud Shine scraper | Source pinned; no package version metadata; `ec9c0978b71ff502bf17e6b34fd0a64d150e410c` | `C:\Users\nayan\Downloads\careeros_scaffold\careeros\oss-tools\runtime\environments\shine\Scripts\python.exe` | `oss-tools/locks/shine-py311.lock.txt`; `oss-tools/licenses/shine-scraper-LICENSE.txt` |
| Crawl4AI | `0.9.5`; `838869bdda93f25e6d50b3f50ae9577d9b19a586`; Playwright `1.64.1`, Chromium revision `1248` | `C:\Users\nayan\Downloads\careeros_scaffold\careeros\oss-tools\runtime\environments\crawl4ai\Scripts\python.exe` | `oss-tools/locks/crawl4ai-py311.lock.txt`; `oss-tools/licenses/crawl4ai-LICENSE.txt` |

Exact source revisions, interpreter paths, requirement counts, license/lock SHA-256 values, Chromium executable hashes, and binary sizes are in [oss-tools/manifest.json](oss-tools/manifest.json). The editable local JobSpy install remains in the pre-existing `.source-tools-venv`; `backend/venv` was not installed into or modified.

### Setup and doctor

From the project root, rerun setup with:

```powershell
.\backend\scripts\setup_oss_collectors.ps1
```

The setup script checks out the fixed commits when absent, installs the committed locks, installs only the local editable packages that provide package metadata, and installs Chromium. It does not start services or contact job websites. I verified the repeat install using `-SkipSourceDownload -SkipBrowser` after the local checkouts and browser were present; it completed successfully.

Run the read-only doctor from the project root with:

```powershell
$env:DATABASE_URL = 'sqlite://'
& '.\backend\venv\Scripts\python.exe' '.\backend\scripts\check_oss_collectors.py' --json
```

Actual final doctor output:

```json
{
  "browser": {
    "chromium": "C:\\Users\\nayan\\Downloads\\careeros_scaffold\\careeros\\oss-tools\\runtime\\browsers\\chromium-1248\\chrome-win64\\chrome.exe",
    "headless_shell": "C:\\Users\\nayan\\Downloads\\careeros_scaffold\\careeros\\oss-tools\\runtime\\browsers\\chromium_headless_shell-1248\\chrome-headless-shell-win64\\chrome-headless-shell.exe",
    "ok": true
  },
  "local_model": {"available": false, "configured": false, "model": null},
  "runtimes": {
    "ats_scrapers": {"interpreter": "C:\\Users\\nayan\\Downloads\\careeros_scaffold\\careeros\\oss-tools\\runtime\\environments\\ats\\Scripts\\python.exe", "ok": true, "package": "ats-scrapers", "version": "0.3.0"},
    "crawl4ai": {"interpreter": "C:\\Users\\nayan\\Downloads\\careeros_scaffold\\careeros\\oss-tools\\runtime\\environments\\crawl4ai\\Scripts\\python.exe", "ok": true, "package": "Crawl4AI", "playwright": "1.64.1", "version": "0.9.5"},
    "instahyre": {"import": "ok", "interpreter": "C:\\Users\\nayan\\Downloads\\careeros_scaffold\\careeros\\oss-tools\\runtime\\environments\\instahyre\\Scripts\\python.exe", "ok": true, "package": "instahyre-scraper"},
    "internshala": {"import": "ok", "interpreter": "C:\\Users\\nayan\\Downloads\\careeros_scaffold\\careeros\\oss-tools\\runtime\\environments\\internshala\\Scripts\\python.exe", "ok": true, "package": "internshala-scraper"},
    "jobspy": {"interpreter": "C:\\Users\\nayan\\Downloads\\careeros_scaffold\\careeros\\backend\\.source-tools-venv\\Scripts\\python.exe", "ok": true, "package": "python-jobspy", "version": "1.4.1"},
    "shine": {"import": "ok", "interpreter": "C:\\Users\\nayan\\Downloads\\careeros_scaffold\\careeros\\oss-tools\\runtime\\environments\\shine\\Scripts\\python.exe", "ok": true, "package": "shine-scraper"}
  },
  "side_effects": "No job sites, database, or CareerOS services were contacted or started.",
  "source_commits": {
    "JobSpy": "a606f9cf077c34f6ce6cbfcc76238f57b3c20671",
    "ats-scrapers": "6b44a1badc9bfbf5cf176f75265cc5729e520e99",
    "crawl4ai": "838869bdda93f25e6d50b3f50ae9577d9b19a586",
    "instahyre-scraper": "16a64f440e39a1545ea1322e21c6d8ef654a3358",
    "internshala-scraper": "4755e7c83ec565e456384dffede100e9dfdc6a3d",
    "shine-scraper": "ec9c0978b71ff502bf17e6b34fd0a64d150e410c"
  },
  "status": "ok"
}
```

`pip check` also reported `No broken requirements found.` in each of the six isolated runtimes. The only nonlocal network traffic in Part 1 was the separately recorded bounded public-source probes below.

## Frozen contract and wrapper examples

The frozen interface is `CollectorRequest` → `CollectorBatch` / typed `CollectorFailure` from `jobs.oss.contracts`. Requests contain bounded search terms, source/tool IDs, a query fingerprint, limits, and an optional approved URL. No resume, database credentials, or personal search data cross the process boundary. `CollectorBatch.to_snapshot()` always maps to non-exhaustive catalogue coverage.

Each example is executable from the `backend` directory with `DATABASE_URL=sqlite://`. The `collect` call makes bounded requests to the named public source. A code example does not grant that source permission; keep JobSpy and unverified portals behind the access review until their missing prerequisite is satisfied.

**JobSpy** (`backend/jobs/oss/jobspy_adapter.py`):

```python
from jobs.oss.contracts import CollectorRequest, query_fingerprint
from jobs.oss.jobspy_adapter import collect

source_id, tool, role, location, country = "naukri", "jobspy", "software engineer", "Bengaluru", "IN"
request = CollectorRequest(
    source_id=source_id, tool=tool, connection_key=source_id, generation=1,
    query_fingerprint=query_fingerprint(source_id, tool, role, location, country),
    role=role, location=location, country_code=country, max_results=5,
    max_details=0, deadline_seconds=30,
)
batch = collect(request)
```

JobSpy is configured one explicit site per call. The country gates cover India-only Naukri, Bangladesh-only BDJobs, France-only HelloWork, supported Indeed/Glassdoor country enums, US/Canada ZipRecruiter, and documented Bayt market limits. **Part 1 did not live-probe these sites** because the access review has not established the required permitted exports/contracts. The adapter has no session cookies, proxy, or fallback.

**Local ATS adapter** (`backend/jobs/oss/ats_adapter.py`):

```python
from jobs.oss.contracts import CollectorRequest, query_fingerprint
from jobs.oss.ats_adapter import collect

source_id, tool, role, location, country = "stripe", "ats_scrapers", "software engineer", "remote", "US"
request = CollectorRequest(
    source_id=source_id, tool=tool, connection_key=source_id, generation=1,
    query_fingerprint=query_fingerprint(source_id, tool, role, location, country),
    role=role, location=location, country_code=country,
    entry_url="https://job-boards.greenhouse.io/stripe", max_results=1,
    max_details=1, deadline_seconds=50,
)
batch = collect(request)
```

Supply the employer's exact official board URL. A directory match alone is not a tested fetch. `ats-scrapers.fetch()` has no portable continuation cursor; the runner caps outbound calls at 24 and reports unknown/partial coverage instead of inventing progress.

**OmkarCloud wrappers** (`backend/jobs/oss/omkar_adapter.py`):

```python
from jobs.oss.contracts import CollectorRequest, query_fingerprint
from jobs.oss.omkar_adapter import collect

source_id, tool, role, location, country = "shine", "shine", "software engineer", "Bengaluru", "IN"
request = CollectorRequest(
    source_id=source_id, tool=tool, connection_key=source_id, generation=1,
    query_fingerprint=query_fingerprint(source_id, tool, role, location, country),
    role=role, location=location, country_code=country, max_results=1,
    max_details=1, deadline_seconds=30,
)
batch = collect(request)
```

The same adapter calls the pinned local projects by source ID. Instahyre returns a typed `blocked` result before network because the upstream project requires a proxy; Internshala returns `blocked` before network because its reviewed terms restrict automated extraction absent an applicable agreement. No demo server, paid API, proxy, or RapidAPI path is used.

**Crawl4AI profile adapter** (`backend/jobs/oss/crawl_adapter.py`):

```python
from jobs.oss.contracts import CollectorRequest, query_fingerprint
from jobs.oss.crawl_adapter import collect

source_id, tool, role, location, country = "cutshort", "crawl4ai", "software engineer", "Bengaluru", "IN"
request = CollectorRequest(
    source_id=source_id, tool=tool, connection_key=source_id, generation=1,
    query_fingerprint=query_fingerprint(source_id, tool, role, location, country),
    role=role, location=location, country_code=country,
    entry_url="https://cutshort.io/jobs", max_results=1,
    max_details=1, deadline_seconds=35,
)
batch = collect(request)
```

The runner checks HTTPS/domain/DNS boundaries, robots policy, access markers, page/detail budgets, and only extracts structured or profile-evidenced records. AI extraction is optional local-only and disabled unless explicitly configured; no hosted LLM is needed. Profiles for unverified query routes remain marked unverified.

## Tests and setup verification

Final Part 1 suite, run from `backend` with disposable SQLite and the bounded offline fixtures:

```powershell
$env:DATABASE_URL = 'sqlite://'
$ossTests = Get-ChildItem 'tests/test_oss_*.py' | ForEach-Object { $_.FullName }
& 'venv/Scripts/python.exe' -m pytest $ossTests -q
```

Result: **36 passed in 7.60s**. This includes request/batch contracts, salary evidence, dates/URLs, cursors, source error shapes, all three Omkar paginators and detail paths, safe access gates, isolated upstream serialization, Crawl4AI page/cursor/detail traversal, no-network imports, and hard subprocess-tree cleanup on timeout.

Relevant pre-existing baseline, also run from `backend` with `DATABASE_URL=sqlite://`:

```powershell
& 'venv/Scripts/python.exe' -m pytest tests/test_source_tools.py tests/test_search_architecture.py -q
```

Result: **75 passed, 12 pre-existing deprecation warnings in 10.18s**. No baseline failure was observed.

The Windows sandbox blocks loopback sockets used by Python 3.11 asyncio's event-loop startup. The Crawl4AI offline fixture initially hung inside `socket.socketpair`; rerunning that fixture and the final suite through the approved outside-sandbox execution path passed. This was an execution-environment restriction, not a provider result. No CareerOS service was launched.

## Bounded technical probes and exact blockers

Artifacts are redacted and ignored under `oss-tools/runtime/probes/`. They contain synthetic software-engineer queries, field-presence shapes, counts, versions, times, pagination observations, and safe failure messages—not job text, applications, accounts, or personal preferences.

| Target | Latest result | Evidence and exact limit |
| --- | --- | --- |
| Shine | `partial`; 1 job, 1 complete description, 2 guarded requests; continuation observed | Final artifact: `oss-tools/runtime/probes/part1-shine-guard-followup.json`. The upstream exposed another page; only page 1 and one bounded detail were fetched. |
| Greenhouse / Stripe | `partial`; 1 job, 1 complete description, 1 reported fetch; no continuation | `part1-greenhouse-stripe-followup.json`. The pinned local `fetch()` is not resumable; it caps a full-board request at 24 outbound calls and output at `max_results`. The first run used the wrong internal interpreter directory and returned `runtime_missing`; the environment map was fixed, regression-tested, and this latest retry supersedes that failure. |
| Unstop | `timeout`; 0 records; request count unknown | The hard browser request ceiling was reached before a page could be evaluated. The earlier review also saw cookie/JavaScript gating. No challenge bypass was attempted. |
| Cutshort | `timeout`; 0 records; request count unknown | The hard browser request ceiling was reached before a page could be evaluated. No pagination result was established. |
| Foundit | `blocked`; 0 records; request count unknown; HTTP 200 | The loaded page matched login/access-challenge indicators. No challenge bypass was attempted. |
| Cuvette | `blocked`; 0 records; request count unknown | The `robots.txt` host did not resolve to an approved public address. |
| Cognizant | `unknown` coverage; 1 record, 1 complete description, 49 browser requests; no next page | A single official-page probe returned a record, but did not establish a public search route, ATS mapping, or exhaustive results. Out-of-domain/non-public subrequests were blocked. |
| TCS | `blocked`; 0 records; request count unknown; HTTP 200 | The page matched login/access-challenge indicators. Graduate and experienced routes remain separate unresolved scopes. |
| Infosys | `unknown` coverage; 1 record, 0 complete descriptions, 60 browser requests | The hard browser ceiling was reached during detail traversal; out-of-domain/non-public requests were blocked. No next page was verified. |
| Wipro | `unknown` coverage; 1 record, 0 complete descriptions, 60 browser requests | The hard browser ceiling was reached during detail traversal; out-of-domain/non-public requests were blocked. No next page was verified. |
| Accenture | `timeout`; 0 records; request count unknown | The hard browser request ceiling was reached before a page could be evaluated. The India entry is not an ATS or graduate/experienced mapping. |
| Deloitte | `unknown` coverage; 1 record, 0 complete descriptions, 60 browser requests | The hard browser ceiling was reached during detail traversal; out-of-domain/non-public requests were blocked. The global page did not verify Deloitte India entity/programme scope. |
| Wellfound | `blocked` before network; 0 requests | Existing access review requires a permitted export/agreement because terms restrict harvesting/copying. No traffic was sent. |
| Superset | `login_required` before network; 0 requests | No public job-search route was established. No candidate session was used. |
| Instahyre | `blocked` before network; 0 requests | The pinned local project requires a proxy; none is configured or permitted. No proxy was added. |
| Internshala | `blocked` before network; 0 requests | Reviewed terms restrict data mining/extraction/copying absent an applicable agreement. No traffic was sent. |

Full records and query timestamps are in `part1-probes-2026-11-03.json`; targeted retries are in the two follow-up files listed above. Probe-driver corrections only changed ignored artifact metadata for unobservable failure counts to `null` and replaced the initial Stripe result with a later successful bounded run in the ledger. JobSpy websites were not live-probed because the access review did not establish permitted direct collection. These outcomes do not mean a whole site or catalogue was searched.

## Coverage, mappings, and limitations

[OSS_SOURCE_COVERAGE.json](OSS_SOURCE_COVERAGE.json) retains the original **45** register sources, adds **Shine**, and separately records the Part 1 **Superset** target (47 source entries total). It also retains all **51** employer candidates. Current source state counts are: 17 blocked, 1 excluded-paid, 5 installed, 8 previously live-verified existing APIs/feeds, 1 login-required, 3 not-a-job-catalogue, 1 partial, and 11 planned. Employer counts are 2 blocked, 11 mapped, 5 partial, 33 planned.

Specific limitations for Sol to keep visible:

- No source assignment is an active connection. The first-six company pages now have explicit profiles, but the generic query parameters are unverified and none of their ATS tenant URLs were guessed. The Stripe Greenhouse fetch is an employer-board test, not a mapping for other employers.
- The source ledger carries all employer URLs and directory matches. A `mapped` employer remains mapping-only until that exact board is fetched. Microsoft is specifically Microsoft AI, not the whole Microsoft catalogue; Meesho remains excluded from default setup.
- JobSpy is offline-tested only. Platform support does not establish access permission; the access prerequisites for LinkedIn, Naukri, Indeed, Glassdoor, ZipRecruiter, Bayt, BDJobs, and HelloWork remain in the ledger. There is no account, cookie, proxy, or all-sites mode.
- `ats-scrapers` can resolve known board hosts such as Stripe Greenhouse; it could not resolve TCS from the official careers URL. Its full-board fetch is bounded but non-resumable, so capped results remain partial/unknown.
- Crawl4AI treats cross-domain and non-public browser requests as blocked, limits pages/details/requests, checks robots, and stops on access challenges. Those limits caused several recorded timeouts or incomplete details; Part 2 may tune budgets only with new evidence while preserving the allowlist and stop rules.
- The Shine wrapper now keeps both search and details under the same no-proxy HTTPS host/redirect/request guard. Instahyre and Internshala are intentionally blocked before any site traffic under the current review.
- Normalized salary records retain direct-field versus description evidence and estimates remain unverified. Raw source dates are retained only where supplied. Description completeness is explicit; one-page retrieval is not treated as exhausted catalogue coverage.

## Exact Part 2 ownership for Sol

Follow [OPEN_SOURCE_DISCOVERY_PART_2_SOL.md](OPEN_SOURCE_DISCOVERY_PART_2_SOL.md). Part 1 deliberately stopped before any of these changes:

1. Add `JOB_DISCOVERY_ENGINE=oss` and a default-off administrative legacy execution permission; trace and guard search, refresh, automation, continuation, retry, status, and direct legacy entry points. Do not silently fall back to legacy collectors.
2. Build the shared coordinator and explicit source/tool policy around the frozen contract; version tasks/cursors by engine and query generation, and preserve pause/cancel/worker leadership checks before ingestion commits.
3. Add idempotent OSS source setup/status while keeping setup from searching, unpausing discovery, or enabling automation. Keep source access blockers and unmapped employers visible.
4. Integrate bounded worker scheduling, cooldowns, progress/status, and truthful partial/blocked outcomes. Do not infer job closure from these collectors.
5. Reuse existing ingestion, deduplication, application references, salary provenance, relevance and result ranking. Keep resume/chat Groq routing unchanged.
6. Update Jobs/Sources for OSS status and hide legacy controls in OSS mode while preserving read-only history and explicit administrative rollback.
7. Add mode/entry-point integration tests; run disposable end-to-end ingestion/ranking and rollback validation; build frontend into a separate output directory and verify the UI without restarting user-managed services.
8. Produce Sol's implementation report and operating guide with actual active code paths and the blockers in this ledger.

## Part 1 boundary confirmation

The active website/search routing, production dependency environment, registry/source enablement, production migrations, legacy collector implementations, personal database/settings, resume/chat routing, and user-managed frontend/backend/worker/Docker services were not changed. No personal search, application submission, user account, cookie, paid service, or hosted LLM was used. No job site is claimed as active in CareerOS.
