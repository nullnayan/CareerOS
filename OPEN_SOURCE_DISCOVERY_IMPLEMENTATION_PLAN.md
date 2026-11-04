# CareerOS open-source job discovery implementation plan

Date: 3 November 2026. Status: implementation specification, not a claim that the integrations below are installed, connected or live-verified.

Execution is now split sequentially to control implementation cost:

- **Part 1 — GPT-6 Luna:** `OPEN_SOURCE_DISCOVERY_PART_1_LUNA.md`. Install and test isolated upstream collectors, source profiles and normalization; do not change active search routing. Deliver `OSS_LUNA_HANDOFF.md`.
- **Part 2 — GPT-6.1 Sol:** `OPEN_SOURCE_DISCOVERY_PART_2_SOL.md`. Review and repair Part 1, integrate worker/API/UI, enforce inactive legacy mode and verify rollout/rollback.

Use those ownership boundaries instead of treating the phases below as authorization for Luna to switch the production discovery engine. This master document remains the full functional specification.

## 1. Intended outcome and operating constraints

Replace the active custom job-fetching path with a coordinated combination of open-source collectors. Keep the old fetching implementations and configuration recoverable, but hide their setup controls and prevent their execution in the new mode. Do not silently fall back to old collectors.

Keep CareerOS's existing search button, preferences, background worker, database, deduplication, relevance scoring, ranking, resume preparation, application tracking and browser autofill. These are application infrastructure, not competing website scrapers. Thin integration wrappers, output normalization and source-specific navigation configuration will still be necessary.

During implementation, personal discovery remains paused. Use disposable databases and synthetic fixtures. Technical live checks must be bounded, use neutral queries and write only isolated verification artifacts. Do not run a personal job search, change the personal database, submit applications, or restart frontend/backend/worker/Docker terminals. The user manages service reloads.

No paid APIs, trial-credit dependencies, paid proxies, paid crawler cloud, RapidAPI subscriptions, Apify actors or automatic billing fallbacks. Free software does not imply unrestricted website access or guaranteed completeness. Preserve explicit failure and coverage information.

## 2. Selected tools and their responsibilities

| Component | Role | Installation source | Important boundary |
| --- | --- | --- | --- |
| JobSpy | Search supported major job boards using roles and locations | `python-jobspy`; https://github.com/speedyapply/JobSpy | Supported boards include LinkedIn, Naukri, Indeed, Glassdoor, ZipRecruiter, Bayt, BDJobs and HelloWork. Confirm the exact pinned release's supported sites and country restrictions. |
| ats-scrapers | Fetch supported company careers sites and resolve company/ATS mappings | `ats-scrapers` with the needed scraper extras; https://github.com/kalil0321/ats-scrapers | Package adapters, directory entries and hosted dataset rows are separate capabilities. Verify the installed package actually has a local scraper for each chosen source. |
| OmkarCloud Instahyre | Local Instahyre search and job details | https://github.com/omkarcloud/instahyre-scraper | Review code and pin a commit; use the local implementation rather than its hosted RapidAPI offering. |
| OmkarCloud Internshala | Local internship and fresher-job search/details | https://github.com/omkarcloud/internshala-scraper | Same local-only requirement; preserve stipend versus annual salary. |
| OmkarCloud Shine | Local Shine search/details | https://github.com/omkarcloud/shine-scraper | Same local-only requirement; validate source-provided employment and salary fields. |
| Crawl4AI | Browser collection for sites with no suitable working adapter; controlled extraction fallback | `crawl4ai`; https://github.com/unclecode/crawl4ai | Install and use the self-hosted library. Search navigation, pagination and detail-page traversal require per-site configuration. It is not an automatic connector to every job website. |

These are four tool families, with three individual OmkarCloud projects. Do not add another full job platform or orchestration framework. Do not install Browser Use or Muse for this release.

Crawl4AI is included in the installed stack, but it should not repeat every successful HTTP/API collection. Prefer structured extraction without an LLM. Optional AI extraction may use a verified local Ollama model. Existing Groq can be explicitly optional, with its rate limits visible; it must not become a required dependency for discovering jobs. Do not introduce Gemini as a mandatory free-tier dependency or change existing resume/chat model routing.

## 3. Existing code to preserve and integration points

Read and trace these areas before editing:

- `backend/jobs/adapters.py`, `connectors.py`, `company_connectors.py`, `public_feeds.py`, `enterprise.py`, `structured_feeds.py`: current fetching implementations and dispatch.
- `backend/jobs/registry.py`, `access_review.py`, `directory.py`, `connections.py`, `scheduling.py`: capabilities, source identity, configuration and cooldowns.
- `backend/jobs/search_control.py`, `search_sessions.py` if present, and discovery handling in `backend/automation/`: pause, session generation, leadership, cancellation and continuation.
- `backend/api/jobs.py`, `backend/jobs/schemas.py`, `backend/core/config.py`: routes, validation and settings.
- `backend/jobs/service.py`, `matching.py`, `salary.py`: existing normalized ingestion, matching and salary provenance.
- `frontend/app/jobs/page.tsx`, `connections-panel.tsx`, and `frontend/app/lib/jobs.ts`: search lifecycle and source-management UI.
- Existing backend discovery tests and `backend/scratch/verify_free_discovery_ui.py`: regression and isolated browser checks.

Retain legacy source rows, IDs, mappings, disabled states, checkpoints and existing postings. Do not rewrite all legacy rows into new providers. Use separate new connections or explicitly versioned configuration so new cursors cannot be mistaken for legacy cursors.

## 4. Target architecture

```text
CareerOS: Search jobs
       |
Existing search-session / background-worker infrastructure
       |
Open-source discovery coordinator
  - immutable search brief and source plan
  - one preferred tool per logical source
  - concurrency, per-domain cooldown and checkpoints
       |
  +---- JobSpy isolated runner
  +---- ats-scrapers isolated runner
  +---- selected OmkarCloud isolated runners
  +---- Crawl4AI isolated browser runner
       |
Validated batch of source observations + coverage metadata
       |
Existing CareerOS ingestion and deduplication
       |
Existing relevance, salary rules, WFH priority and sorting
       |
Progressive results and per-source status
```

No third-party collector gets direct database credentials. Runners receive only a minimal search request and return bounded structured output. The existing application worker remains the database writer. No website credentials or entire resume are needed for ordinary public searches.

Suggested new package: `backend/jobs/oss/`, containing `contracts.py`, `catalog.py`, `coordinator.py`, `runtime.py`, `normalize.py`, tool wrappers and a `runners/` directory. Keep upstream downloads under a separate ignored runtime/vendor directory, with their own license notices and lock manifest. Do not copy upstream code into existing collector modules without attribution.

## 5. Phase A — baseline, downloads and isolated installation

1. Record current regression results and exact files/settings involved in source execution. Do not dump secrets or personal records into the report.
2. Inspect `backend/.source-tools-venv` before creating or replacing it. Earlier work installed JobSpy 1.4.1 there; that installation alone does not establish a CareerOS integration. Confirm its actual package metadata and import health.
3. Resolve package versions and repository commits from official PyPI/GitHub sources. Download each selected upstream project and inspect its license, dependencies, startup behavior and network calls. Do not assume a GitHub README proves the scraper works.
4. Use isolated runtime environments rather than installing into `backend/venv`. Try a single locked environment for compatible JobSpy and ats-scrapers dependencies. Use separate environments when versions conflict; keep Crawl4AI/browser dependencies isolated from the web backend and separate OmkarCloud dependencies when necessary.
5. Pin exact versions, git SHAs, source URLs and hashes in a runtime manifest. Keep upstream license/NOTICE requirements. Capture a dependency lock after successful installation. Never run unbounded package upgrades during application startup.
6. Install required browser binaries into the scraper runtime. Do not open browser windows or create additional web-server terminals during setup. Use per-task child processes or a local runner pool, not each project's demo HTTP server.
7. Provide one reproducible setup command and a read-only doctor command. Doctor reports runtime presence, pinned version, browser availability and optional local-model status without contacting job websites or starting services.

Acceptance: imports and fixture extraction work in the isolated runtimes; the backend's installed dependencies and user-managed services are unchanged.

## 6. Phase B — preserve but disable the legacy collectors

Introduce an application setting such as `JOB_DISCOVERY_ENGINE=oss`, plus an explicit administrative legacy execution guard defaulting to false. Invalid configuration must fail clearly, not silently select a legacy implementation.

- Keep all legacy modules and tests. Do not delete or heavily refactor them merely to hide them.
- Enforce the selected engine at the shared execution boundary used by direct refresh, Search jobs, scheduled discovery, queued continuations, status verifiers and worker retries. Inventory every caller of the old fetch functions.
- In OSS mode, old source rows cannot schedule or execute network collection, even if their historical `enabled` field is true. Do not mutate those fields just to implement the mode switch.
- Remove legacy sources from the active search denominator so searches do not wait forever for intentionally disabled collectors.
- Hide legacy add-source, default-connection, feed and enterprise-collector setup controls from normal navigation. Backend mutations for those collector routes must reject use in OSS mode; hiding a button alone is insufficient.
- Existing legacy source health/history may remain read-only under an archived details view, clearly labelled inactive. Historical data and application references remain readable.
- Version new discovery tasks with the selected engine and generation. Cancel or ignore mismatched old tasks safely; never reinterpret an old cursor for an OSS runner. Before committing each result, recheck pause, task cancellation and generation.
- Switching modes requires an explicit administrative action. An OSS failure never enables legacy mode automatically.

Acceptance: mock legacy network calls to raise assertions, exercise all discovery entry points, and show that none can invoke them in OSS mode. Old data and configuration stay recoverable.

## 7. Phase C — common request, batch contract and runtime control

Define typed contracts independent of a particular library:

- Request: engine/version, source and connection IDs, session generation, approved source URL, role, location/country, requested age, page/detail budgets and opaque cursor.
- Job observation: native ID, title, employer, original source URL, application URL, raw location, work arrangement, employment type, description, completeness, publication/expiry if actually supplied, compensation amounts/currency/period, compensation evidence and collection timestamp.
- Batch: jobs, opaque next cursor, exhausted/partial/unknown state, skipped count, warnings, request counts, elapsed time and tool/version.
- Failure: unsupported source, runtime unavailable, login required, blocked, rate limited, changed format, timeout, transport failure or extraction-validation failure. Empty results are a separate outcome, not a generic failure.

Translate valid observations into the existing `Listing`/`Snapshot` and `SourceError` contracts. Start new collectors with non-exhaustive coverage and no authority to close missing jobs. Keep duplicate occurrences from different sources while merging appropriate canonical postings.

Wrap each runner in a killable subprocess or supervised worker process with a deadline and bounded input/output. A timed-out Python thread is not a cancelled scraper. Terminate only task-owned processes and their browsers; clean them up on cancellation. Do not stop user-managed processes.

Normalize DataFrame nulls/NaN, enums and dates before JSON serialization. Limit body sizes, record counts and recursive data. Preserve library errors/warnings even when the library returns an empty DataFrame. Never classify a blocked response as a successful zero-job search.

## 8. Phase D — JobSpy integration

- Run one explicitly selected site per task, not JobSpy's implicit all-site default.
- Map CareerOS roles, locations and age preferences to the pinned release's supported arguments. Rotate role/location combinations through checkpoints instead of multiplying all combinations into one burst.
- Start with up to 20 observations per batch. Fetch detailed descriptions through the library in bounded stages; listings without full descriptions stay excerpts.
- Preserve the exporter/library's original salary source. Estimated pay stays unverified, including when repeated normalization examines description text. No currency conversion assumptions or invented salary floors.
- Validate returned source/application URLs and maintain source identity. If the library provides a direct employer URL, preserve both links.
- Check offset semantics separately for each supported board. Detect repeated pages. Stop at the provider's real limit and report partial coverage rather than claiming all results were retrieved.
- Keep country limitations visible: a US/Canada or France source must not be presented as verified India coverage. Do not silently reinterpret an India search as a US search.
- Handle temporary blocks with cooldown and visible status; no proxy purchase or repeated anti-block attempts.

Acceptance: source-specific fixtures for all configured JobSpy boards, timeout and failure propagation, resumable pagination, salary provenance and idempotent end-to-end ingestion.

## 9. Phase E — ats-scrapers and company mapping

Use local adapters as the preferred route. The hosted directory may help discover candidate mappings, but verify each mapping against the company's official careers site. Its existence is not proof that the local package supports collection or that all regional/fresher hiring is covered.

First verify Cognizant, TCS, Infosys, Wipro, Accenture and Deloitte, followed by every employer already in CareerOS's candidate inventory. Record official careers URL, actual recruiting system, regional scope, chosen tool, package adapter availability, probe outcome and remaining limitation.

The earlier research found directory candidates for Accenture/Workday and Wipro/Deloitte India/SuccessFactors. Treat these as candidates only. Verify Cognizant, TCS and Infosys independently; do not guess ATS slugs. Keep TCS graduate hiring/NextStep separate from experienced hiring, and Deloitte India separate from other entities.

If an employer has no working local adapter, assign a Crawl4AI source profile and test it. Do not revive the old Workday or enterprise collectors as a silent fallback. If hosted dataset search is offered later, mark its snapshot time and coverage; it is not equivalent to a fresh direct scrape and must not become an unacknowledged external service dependency.

If a library's API only exposes an unbounded full-board fetch, assess memory/runtime before enabling large employers. Prefer its supported pagination/streaming; otherwise isolate and cap the task, expose the limitation and avoid pretending it has resumable partial progress.

Acceptance: exact company connection plus successful bounded fetch, usable descriptions and original application links in isolated storage. Include unresolved regional/programme coverage in the report.

## 10. Phase F — OmkarCloud local integration

Review and download the three projects individually. Pin tested commits. Import or invoke their local collection functions through wrappers; do not depend on their RapidAPI accounts, hosted domains or promotional free-call allowances. Do not launch their demonstration servers on CareerOS's ports.

For each project, implement search, pagination, detail retrieval, salary/stipend normalization, employer identity, expiration handling and typed failure mapping. Conserve source-native experience and skills fields. Do not collect recruiter personal information merely because the upstream tool returns it; the job catalogue does not require it.

Check repository behavior rather than assuming all three use the same browser or JSON transport. Compare local JSON output with a live public source page before promoting the connection to verified.

Acceptance: a successful local public search/detail probe for each site, fixture regressions, no call to its paid hosted API, and persistence through CareerOS ingestion.

## 11. Phase G — Crawl4AI source profiles and recovery

Create explicit profiles for Unstop, Wellfound, Cutshort, Foundit, Cuvette, Superset, Instahyre/Internshala fallback if appropriate, and unsupported named company portals. Retain all other original inventory entries as evaluated targets. New browser profiles require working navigation and an actual probe before becoming enabled connections.

Each profile declares approved domains, entry URL, search interaction, country/role handling, page-ready conditions, job-link identification, pagination/scroll strategy, detail extraction, output schema and execution budget. Use the open-source browser/crawler for retrieval; wrappers are integration code, not a second custom HTTP scraper engine.

Extraction order: source JobPosting structured data, tested deterministic extraction, then optional LLM extraction of already loaded content. Do not invoke all extraction methods for every successful page. Runtime/session reuse must remain bounded and isolated per site/account.

LLM output must include source evidence and pass field validation. Missing salary, batch, experience or remote status remains unknown. A syntactically valid Pydantic object does not prove the fields are true. Preserve links in extracted content; stripping HTML must not lose the application destination.

Recovery rules:

- Distinguish explicit zero matches from absent expected content, a challenge page, login and selector/schema errors.
- Allow a bounded extraction fallback when content loaded but parsing failed. Do not use LLM extraction to fabricate results from an access-denied page.
- Treat 401/403/challenges as source access states. Ask for user action only if a tested integration genuinely needs it; do not ask for every website account in advance.
- A proposed extraction repair is fixture-tested and versioned before replacing a known profile. Do not let an agent execute arbitrary generated Python against the production worker or database.
- Respect approved public-host boundaries and block private/local targets, including redirects, browser subrequests and any discovered application links that would be fetched. Credentials stay out of logs and model prompts.

Acceptance: tests for HTML changes, load-more, multiple pages, detail traversal, empty results, blocked/login pages, malformed AI JSON, invented links, slow browsing, cancellation and private-network targets.

## 12. Phase H — performance and search lifecycle

Initial configurable budgets, to tune after measurements:

- At most three collector tasks concurrently across the machine, one active browser collector initially, one active task per source domain.
- Approximately 20 search observations or up to 8 details per batch. Workload-dependent deadlines around 60–90 seconds for HTTP tools and 120 seconds for browser batches, enforced through runner supervision.
- Durable cursors for genuine supported continuations, including role/location position, library version and query fingerprint. Commit partial progress only where the cursor precisely represents what was processed.
- Retry with source-aware backoff and Retry-After. Keep long cooldowns outside worker slots. Never sleep a process while holding a database session just to wait for a provider.
- Apply fair scheduling across tools and sources; fast boards must not starve browser sources or vice versa.
- Stream committed batches through the existing search-status polling mechanism. The user can view early results while slow sources continue.
- Cache immutable or recent source observations with visible freshness. Avoid a new browser or full-company catalogue fetch when cached data is sufficient; expose whether Search jobs used recent data or fetched fresh data.
- Same-query requests reuse/coalesce a running session. Changed preferences create a new query generation. Stop, pause and cancellation prevent later stale writes.
- After a bounded search window, show completed, partial, deferred, blocked and failed sources. Report queued continuations honestly; never keep a spinner running indefinitely.

These are execution budgets, not a lifetime quota on jobs. Larger searches continue across batches when the source and its access limits allow it. Measure time to first results, total elapsed time, jobs per source, requests, browser memory and fallback frequency. Do not promise a fixed search time across all external sites.

## 13. Phase I — website integration and existing user rules

The Sources tab should expose the open-source stack only, with per-tool installation health and per-site observed health. A read-only archived legacy view can be available separately. Setup/connect operations save configuration without searching. GET requests and opening Jobs must not launch collectors.

Offer individual source selection, a preview of the source plan, and a connection action for verified configurations. Distinguish installed tool, implemented wrapper, configured source and live-verified source. Do not count an inventory row as a working connection. Show exactly which sources are included in the next search.

Keep existing user rules:

- Default 60 relevance, with an editable 0–100 control; use degree/course and confirmed skills.
- Default minimum annual INR salary of 5.5 LPA, fully editable/removable.
- Unknown or estimated salary is included by default; the salary floor does not reject those jobs.
- Best sorting prioritizes WFH, then verified annual INR salary and relevance, with explicit stable handling of unknown pay. Non-INR amounts cannot be compared as INR without a separately approved conversion feature.
- Preserve filters and sorting for work arrangement, salary, relevance, age, source and job type.
- Reuse existing deduplication and provenance; do not merge different requisitions just because title/company match.
- No application submissions or resume changes happen during discovery. Skills-only tailoring and up to five confirmed missing skills remain unchanged.

Use progressive feedback such as "4 of 10 sources checked; 2 deferred; 1 login required" rather than "all internet jobs searched."

## 14. Exhaustive coverage ledger

Carry forward all 45 existing register entries and 51 employer candidates. Add Shine as a new inventory item rather than replacing an existing target, updating count-sensitive tests deliberately. Do not label every platform a source of actual vacancies: contest, mentoring and training portals require separate evidence of job listings.

For each existing site/employer plus Shine, record:

`name | official URL | preferred tool | pinned version/commit | local adapter/profile | configuration | country/programme scope | live probe date | observed result | pagination/detail coverage | access requirement | next action`

Possible states: planned, downloaded, installed, wrapper-tested, configured, live-verified, partial, blocked, login-required, unsupported, excluded-paid or not-a-job-catalogue. A Crawl4AI assignment alone does not qualify as implemented. Preserve all unresolved targets in the final report with concrete reasons.

## 15. Phase J — regression, rollout and rollback

1. Run the existing relevant backend suite as a baseline; the previous review-fix run recorded 236 passed and 3 skipped. Re-establish the actual current baseline rather than assuming that count is immutable.
2. Add meaningful tests for mode isolation, disabled legacy routes, queued legacy tasks, all runner contracts, pagination, partial timeouts, errors, salary provenance, duplicates, cancellation and query generations.
3. Test each external adapter using recorded/synthetic fixtures. Separate opt-in live probes from offline CI. Store tool/version and a bounded redacted probe artifact.
4. Verify each named priority site's search plus at least one detail page in an isolated database. Never use personal profile searches as a smoke test.
5. Build the frontend using a separate Next.js output directory; restore any generated tsconfig changes. Run browser verification with disposable API/database and assert no search on page load, no legacy controls, responsive filters, progressive statuses and truthful coverage.
6. Check that resume compilation/repair, master sources, existing applications, automation controls and extension pairing/autofill are preserved. Avoid duplicate worker/service startup.
7. Publish a coverage and validation report identifying working sources and exact remaining blockers. Do not describe downloaded code or passing mock tests as a completed live integration.
8. Activate OSS as the configured fetching mode only with the runtime ready. Preserve the personal paused state. Record which user-managed services need code reload, but do not restart them.
9. Rollback: an explicit administrative engine switch restores the retained legacy dispatch and UI. Keep new OSS rows/checkpoints separate, cancel mode-mismatched pending tasks, and retain imported results and application references. Do not use destructive database restoration for routine rollback.

## 16. Deliverables and completion criteria

- Reproducible isolated setup, pinned dependencies/commits, license notices and doctor command.
- Open-source coordinator and tested wrappers for JobSpy, ats-scrapers, the three selected OmkarCloud projects and Crawl4AI.
- Backend-enforced inactive legacy fetching plus hidden legacy setup UI, with tested explicit rollback.
- Working source configuration, task scheduling, bounded pagination, timeouts, cancellation, failure reporting and progressive results.
- Accurate source/employer coverage ledger, including unresolved connections.
- Offline tests, opted-in isolated live probes, production build and browser verification results.
- A short operating guide explaining source setup, runtime checks, Search jobs, source failures, dependency upgrades and user-managed reloads.

The target is broad free discovery through upstream tools. Completion of the software stack must be reported separately from completion of every requested website connection. If a named site cannot be collected, document and surface that blocker; do not silently substitute a manual import, hide the site, or claim universal coverage.

## 17. Handoff instruction for implementation

Implement this plan in the existing CareerOS checkout. Inspect current code and applicable instructions first. Work through installation, mode isolation, integration, source verification and UI wiring; do not stop after creating inventory entries or wrappers. Keep personal discovery paused and use disposable data for validation. Do not restart services. Prefer the selected upstream tools for actual retrieval; preserve existing collectors inactive for rollback and retain CareerOS's result-processing infrastructure. Keep unresolved sources visible with exact blockers and report only verification actually performed.
