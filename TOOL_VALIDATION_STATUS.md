# Tool validation and flexible search controls — 2 November 2026

## Latest source-tools release — 2 November 2026

See [SOURCE_TOOLS_IMPLEMENTATION_REPORT.md](SOURCE_TOOLS_IMPLEMENTATION_REPORT.md) for the exhaustive 45-source / 51-employer checklist and exact external prerequisites. This section supersedes older implementation counts below.

- Added a fixture-tested Workday external career-site adapter, explicit employer-feed profiles for Taleo/SAP/Oracle/iCIMS, persistent employer setup, conditional public-feed caching, and an offline JobSpy-compatible preview/selected-import workflow for eight boards. JobSpy is **not installed or executed**. These are not newly verified live collectors; no new personal connection was enabled.
- Added four opt-in primary board-page mappings (Twilio, CRED, ServiceNow, Microsoft AI), giving 15 directory boards. Default setup still selects the prior ten company boards plus three public feeds; Microsoft AI is only that division. No old PhonePe/Postman slug reused.
- Ingestion now bulk-loads identities/revisions/matches and reconciles closures in bounded queries, with parent-before-dependent flushes under enforced foreign keys. Repeated 1,200-record synthetic ingestion stays within 30 SELECTs per execution; paused catalogue requests skip reassessment.
- Final focused backend suite: **227 passed, 3 skipped**. Skips remain opt-in real compiler cases. Production frontend build passed for all 21 routes in `.next-source-tools-check`; normal `.next` was not built, and tsconfig was restored byte-for-byte.
- Extended isolated browser checks passed explicit search, relevance 40/50, editable salary/unknown-pay controls, sorting/pagination/details/save, employer setup without discovery, export preview/selection/confirmation/import, preserved disabled scheduling, and 390/700px layouts. Zero browser errors or horizontal overflow; screenshots under `scratch/source-tools-ui/`.
- Personal discovery remains paused. No personal DB reads/writes, record deletion, migrations, dependency installation or service restarts were performed. Reload backend/worker code yourself when ready. Opening Jobs still shows no cards and makes no discovery request; Source setup does not resume searches.
- Full unattended integration of every named platform remains unresolved pending provider-specific export/permission/tenant prerequisites. Oracle/iCIMS feed support is not their authenticated API. Workday is an undocumented external-site transport tested with fixtures; no live employer collector verification is claimed.

## Current operating rule

The user requested that searches wait until the tools are ready. The current personal search was paused, its queued/running discovery task was cancelled, and recurring automation remains disabled. Existing listing data was retained. Further verification in this change used synthetic SQLite fixtures and static browser artifacts, not personal job searches. Backend, frontend and worker services were not stopped/restarted by the agent; the user restarted their own stale worker.

## Completed changes

- Jobs without a verified comparable annual INR minimum are included by default. They are labelled salary not disclosed / salary not verified, and the LPA filter does not exclude them.
- An optional checkbox can require verified comparable pay instead. For comparable pay, the chosen LPA filter still applies to the advertised minimum. No salary estimates or exchange rates were invented.
- Relevance and salary controls accept editable values down to zero; clearing a field removes that filter. Relevance 40 and 50 are supported. Saved salary preferences no longer silently lock a different per-search salary threshold.
- Salary is treated as a result filter rather than a qualification blocker. Other eligibility restrictions remain available, with All eligibility and Outside preferences views restored.
- Reset filters restores defaults of relevance 60, salary 5.5 LPA, unverified salaries included, and best/WFH-first sorting. Sorting controls remain independent.
- Search status reports checked/enabled source counts and remaining sources. A finished task with due sources/pages left behind is marked incomplete rather than completed. Explicitly paused searches report paused.
- Result diagnostics distinguish eligibility, relevance and salary exclusions. Empty results no longer imply that no source returned jobs.
- Paused result requests skip catalogue reassessment entirely. Stale assessments preload posting/match pairs in one query instead of looking up each match individually, and reuse one evidence-version calculation per batch. This removes a per-job query pattern found during diagnosis; no live performance guarantee is claimed.

## Diagnosis that led to the changes

The earlier search had run one batch: 44 records from three connections, with ten other connections deferred. Its worker process still held older code in memory, so manual continuations were not scheduled. The user stopped that specific worker process and relaunched it. The already requested search was resumed once before the later instruction to pause all searching.

At the initial diagnostic snapshot, one eligible 60+ result lacked a verified salary minimum, explaining the strict view's zero results. After worker recovery, all 13 connections were observed checked, with further feed pages pending. The user then requested a pause. Those observations are historical diagnosis, not a reason to keep running searches.

## Validation

- Full focused backend suite: **192 passed, 3 skipped**. The skips remain opt-in real Docker compiler cases.
- Production frontend build passed in `.next-search-flexibility-check`; normal `.next` output was left untouched and tsconfig was restored.
- Isolated browser QA passed actual requests at relevance 40 and 50 and salary 2 LPA, reset behavior, inclusion/exclusion of an undisclosed-pay fixture, independent WFH/salary sorting, pagination, details/save, source setup, and mobile/tablet layouts. No browser errors or horizontal overflow.
- Regression tests cover unknown pay included at a selected salary threshold, strict opt-out, adjustable thresholds despite saved defaults, incomplete scans, paused-feed short-circuiting and bulk match loading.
- Screenshots: `scratch/search-flexibility-ui/`.

## Source tools still outside the completed native set

The executable native set remains five company API adapters, three public-feed adapters and the structured-feed framework. The 13 configured connections do not represent unrestricted catalogues from 13 large job websites. The paired extension supplies a separate reviewed-import/autofill route.

LinkedIn, Naukri, Unstop, Wellfound, Internshala and other inventoried targets are not declared working automatic collectors. Their source-specific implementation/access assessment remains unfinished. Generic public feed support does not establish a feed for every enterprise ATS tenant. Community JobSpy was researched, but was not installed, enabled or exercised against user jobs in this change.

Future work should target source adapters and access contracts, using documented schemas, fixtures and bounded tests. Do not resume the personal search or claim that every internet job source is connected. See `SOURCE_ACCESS_REVIEW_2026-11-02.md` for the full inventory and `SEARCH_PIPELINE_ARCHITECTURE.md` for the current architecture.
