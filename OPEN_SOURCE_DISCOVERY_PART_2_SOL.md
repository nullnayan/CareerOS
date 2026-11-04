# Part 2 — GPT-6.1 Sol: review, integrate and roll out

Date: 3 November 2026. Start after Luna completes Part 1. Do not repeat its finished installation and wrapper work without evidence that repair is needed.

## Objective

Review Luna's concrete implementation, repair material issues, and make the open-source collector stack the only active job-fetching engine. Preserve all old collectors and their configuration for explicit rollback, while hiding their controls and enforcing their inactive state on the backend and worker. Reuse CareerOS's result-processing infrastructure.

Read `OSS_LUNA_HANDOFF.md`, `OSS_SOURCE_COVERAGE.json`, `OPEN_SOURCE_DISCOVERY_PART_1_LUNA.md` and `OPEN_SOURCE_DISCOVERY_IMPLEMENTATION_PLAN.md`. The master plan remains the detailed functional specification; this file defines the integration ownership and order.

## Constraints

- Do not restart frontend/backend/worker/Docker. User manages reloads.
- Personal discovery remains paused. Use disposable SQLite, mocked providers and separate build artifacts for validation. No personal database changes, personal searches or application submissions.
- Do not install into the running backend environment or alter resume/chat Groq routing.
- No paid services, trial-credit dependencies or silent legacy fallback.
- Preserve all master-resume originals, tailoring behavior, application history, paired extension and existing preferences.

## Task 1 — targeted review and repairs

1. Run doctor and the Part 1 tests. Inspect the diff/file manifest, contracts, runner supervision and representative real upstream invocation paths.
2. Check that wrappers invoke upstream implementations, not dummy results, hosted paid endpoints or unfinished TODOs. Compare the stated coverage with artifacts.
3. Review query/cursor semantics, salary provenance, unsafe URLs/redirects/browser requests, output limits, subprocess/browser cleanup and upstream failure propagation.
4. Confirm source profiles implement navigation and detail traversal, not only extraction from a fixture.
5. Fix material defects with regression tests. Keep Luna's useful architecture and pins unless a concrete problem justifies replacing them. Re-probe only sources affected by a change or insufficient evidence; do not repeat every successful live request.
6. Identify actual external prerequisites early and ask only for inputs needed by tested connections. Continue unrelated integration while awaiting answers. Never count a blocked source as completed.

## Task 2 — shared dispatch and source policy

Build the coordinator under `backend/jobs/oss/` around Luna's contract. Select one preferred tool per logical source, with an explicit Crawl4AI fallback where usable. Never run every collector against the same source by default.

Add typed central configuration for `JOB_DISCOVERY_ENGINE=oss` and an explicit administrative legacy execution permission defaulting to false. Reject invalid modes. Preserve old modules, source rows, enablement and checkpoints without destructive migration.

Trace and guard every entry point: Search jobs, direct refresh, automation scheduling, continuation, retry, status verifiers and direct legacy fetch entry points reachable through application routes. Guard setup mutations as well as execution. Remove inactive legacy sources from the current session's expected-source denominator. OSS failure must not route to legacy.

Version tasks/configurations/cursors by engine and query generation. Ignore/cancel mismatched old tasks safely. Recheck pause, generation and cancellation before every ingestion commit. Preserve the worker's existing leadership and serialization protections.

Use distinct OSS connection identity without breaking old occurrence/application references. Doctor and missing-runtime errors must fail clearly rather than enabling the old engine.

## Task 3 — source setup and truthful coverage

- Wire idempotent OSS connection setup into the API. Setup saves configuration; it does not search, unpause discovery or turn on recurring automation.
- Show the actual installed tool, selected adapter, configured source and observed health as separate concepts.
- Keep all original inventory targets and add Shine. Use Luna's actual findings, not the assumption that a crawler covers every website.
- Verify the priority job boards and Cognizant/TCS/Infosys/Wipro/Accenture/Deloitte mappings, including regional and graduate-programme scope. Repair missing mappings where independently possible.
- Keep login-required, blocked, unsupported and non-job portals visible with exact next actions.
- Do not silently substitute manual export for automatic fetching and then describe the source as connected.

## Task 4 — worker scheduling and performance

Integrate the new coordinator with the existing background worker and search-status lifecycle; do not put browser work in HTTP request handlers.

- Begin with three concurrent collectors overall, one active browser and one active task per domain; make these measured, configurable budgets.
- Keep per-tool page/detail limits and hard deadlines. Do not infer that timing out a thread stops upstream requests.
- Queue cooldowns outside occupied worker slots. Honor Retry-After and maintain fair progress across sources and role/location queries.
- Persist genuine supported continuation state. No invented progress for unbounded upstream fetches.
- Coalesce duplicate searches, invalidate stale generations and preserve pause/cancel behavior.
- Deliver progressive batches and truthful completed/partial/deferred/blocked outcomes; avoid an indefinite spinner.
- Cache with visible freshness. Record elapsed time, fallback frequency, requests where measurable and browser memory; tune only when evidence justifies it.

## Task 5 — ingestion and existing result rules

Convert normalized batches through existing `ingest()`; third-party processes receive no database credentials. Reuse deduplication, occurrences, description revisions, assessments and provenance. New collectors initially have no absence-based job-closing authority.

Keep estimated/unknown salaries included by default and exempt from the LPA floor. Preserve description versus advertised-field evidence after reassessment. Retain editable relevance 0–100, default 60; editable/removable default INR 5.5 LPA minimum; WFH-first best sorting followed by verified INR pay and relevance, with deterministic unknown-pay handling. Non-INR pay must not become INR by assumption.

Preserve source-specific job identities and separate similar requisitions. Search does not prepare/submit applications or alter resume skills. Existing skills-only tailoring remains limited to up to five confirmed missing skills.

## Task 6 — frontend and legacy hiding

Update Jobs/Sources to use OSS connection setup and source status. Hide old collector add-source/default/feed/enterprise controls in OSS mode. Hide active legacy configuration in normal workflows; preserve read-only archived history and an administrative rollback route.

Show installation health, active sources in the search plan, source-level counts, last check, blocked/login states, cooldown and cached-versus-fresh results. Opening the page or a GET request must not launch discovery. Keep all sorting/filter controls flexible.

No ordinary frontend action can re-enable legacy fetching. Server guards remain authoritative even if someone calls the previous endpoints directly.

## Task 7 — verification and handoff

1. Add integration tests that assert legacy network functions are never invoked from every discovery entry point in OSS mode, including old queued tasks and status checks. Test rejection of legacy setup mutations.
2. Verify source setup idempotency, engine/query/cursor isolation, generation checks, partial progress, source failures, duplicate merging, salaries, cancellation and no personal writes.
3. Exercise OSS end-to-end ingestion and ranking with disposable data. Run the related backend regression suite and resolve new failures; historical reported counts are not a substitute for running the current suite.
4. Complete bounded technical probes only where coverage evidence is missing. Verify actual search and detail retrieval. Record runtime version, source scope, time and result; preserve blockers.
5. Run frontend TypeScript/build in a separate Next.js output directory and restore generated config changes. Run isolated browser verification for no automatic search, hidden legacy setup, progressive results, source status, filters and responsive layout.
6. Validate rollback in disposable configuration: explicit legacy restoration works, new queued tasks cannot cross modes, and records/application references remain intact.
7. Create `OSS_DISCOVERY_IMPLEMENTATION_REPORT.md` with changed files, active code paths, setup/doctor commands, runtime pins, actual test/probe evidence, complete source ledger and exact unresolved prerequisites. Separate platform implementation from website coverage.
8. Create a short operating guide. State which user-managed services need a reload. Do not restart them or start personal searching.

## Final acceptance

The new code routes job fetching exclusively through the selected upstream tools in OSS mode, with no silent calls to retained legacy collectors. The website provides a working setup/search/status flow, existing result and application features remain intact, and tests prove the boundaries. No claims of universal coverage: enumerate any site that still cannot be fetched and its specific blocker.

## Prompt to resume Sol

> Luna has completed Part 1 in C:\Users\nayan\Downloads\careeros_scaffold\careeros. Read OSS_LUNA_HANDOFF.md and OPEN_SOURCE_DISCOVERY_PART_2_SOL.md, inspect the actual work, fix material defects, then implement Part 2 through website integration and validation. Preserve but disable/hide legacy collectors; use only the selected OSS tools for active fetching. Reuse completed Part 1 work instead of rebuilding it. Keep personal discovery paused, use disposable data and do not restart services. Finish with a truthful implementation/coverage report and exact remaining blockers.
