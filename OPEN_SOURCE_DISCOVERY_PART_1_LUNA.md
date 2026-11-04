# Part 1 — GPT-6 Luna: install and build isolated collectors

Date: 3 November 2026. Run this part first, then hand the result to GPT-6.1 Sol for Part 2. These are implementation instructions, not a completion report.

## Objective and boundary

Build the reusable open-source collection layer completely enough that Sol can integrate it without rewriting it. Do the downloads, isolated dependency installation, source wrappers, normalization, source profiles, meaningful tests and bounded technical probes. Keep the active CareerOS search path unchanged throughout Part 1.

Read `OPEN_SOURCE_DISCOVERY_IMPLEMENTATION_PLAN.md` for the complete requirements. This part implements its installation, standalone collection and verification work. Part 2 owns production routing, legacy execution guards, scheduling, database integration, frontend changes and activation. Neither part deletes the existing collectors.

## Mandatory operating rules

- Work in `C:\Users\nayan\Downloads\careeros_scaffold\careeros`. Inspect applicable repository instructions first.
- Do not start, stop or restart frontend/backend/worker/Docker. The user manages terminals.
- Keep personal discovery paused. Do not read/write the personal database, use its stored preferences for probes, import personal jobs or submit applications. Set `DATABASE_URL=sqlite://` before importing application modules for tests, and override all database dependencies with disposable storage.
- Do not modify `backend/venv`, production environment files, existing source enablement or production migrations.
- Use only the selected local open-source tools. No paid API, trial-credit dependency, RapidAPI, Apify, paid proxy, Muse or paid Crawl4AI cloud.
- Do not require an LLM for ordinary collection. Do not change resume/chat Groq routing, download a large model or install another agent framework.
- Do not change existing production routes, registry, dispatch, worker, UI or legacy collector implementations during this part. Put integrations in the new namespace below. Do not introduce network or dependency-install side effects on import.
- Use the user's existing authorization to complete routine steps. Ask only when actual missing account access or another necessary input prevents progress; continue independent work. External blocks must be recorded, not bypassed with purchased services.

## Files you own

Create or extend these paths as needed, following existing conventions:

```text
backend/jobs/oss/__init__.py
backend/jobs/oss/contracts.py
backend/jobs/oss/catalog.py
backend/jobs/oss/runtime.py
backend/jobs/oss/normalize.py
backend/jobs/oss/jobspy_adapter.py
backend/jobs/oss/ats_adapter.py
backend/jobs/oss/omkar_adapter.py
backend/jobs/oss/crawl_adapter.py
backend/jobs/oss/runners/
backend/jobs/oss/profiles/
backend/scripts/setup_oss_collectors.ps1
backend/scripts/check_oss_collectors.py
backend/scripts/probe_oss_collectors.py
backend/tests/test_oss_*.py
oss-tools/manifest.json
oss-tools/locks/
oss-tools/licenses/
OSS_SOURCE_COVERAGE.json
OSS_LUNA_HANDOFF.md
```

Keep downloaded upstream repositories, environments, browser binaries and probe artifacts in ignored runtime directories. Add narrowly scoped ignore rules if needed; do not replace any existing ignore file. If no Git repository exists, still maintain those rules and a changed-file manifest. Preserve upstream license notices. The exact directory names may follow project conventions, but document any change.

## Task 1 — baseline and reproducible setup

1. Inspect current `Listing`, `Snapshot`, `SourceError`, salary normalization and discovery tests without changing them. Record the baseline tests and commands relevant to these boundaries. Do not repeatedly run unrelated suites.
2. Inspect `backend/.source-tools-venv` first. Earlier work installed JobSpy 1.4.1 there, but verify its actual version/import status. Do not assume it is connected to CareerOS.
3. Resolve and pin tested official package versions/commits for:
   - `python-jobspy`: https://github.com/speedyapply/JobSpy
   - `ats-scrapers` with needed local-scraper extras: https://github.com/kalil0321/ats-scrapers
   - https://github.com/omkarcloud/instahyre-scraper
   - https://github.com/omkarcloud/internshala-scraper
   - https://github.com/omkarcloud/shine-scraper
   - Self-hosted `crawl4ai`: https://github.com/unclecode/crawl4ai
4. Install into isolated environments. Share only compatible locked dependencies; isolate Crawl4AI and conflicting upstream requirements. Never install into the running backend environment.
5. Download/review the three OmkarCloud projects and invoke their local implementation, not their hosted API. Do not launch their demo web servers.
6. Install only necessary browser binaries. Record package versions, commit SHAs, hashes, license paths and environment interpreter paths. Produce exact locks and a repeatable setup command with Windows path handling.
7. Implement a read-only doctor that checks imports, versions, local browser readiness and optional local-model availability. It must not contact job sites, open a personal database or start services.

Done when: all usable runtimes import, setup can be reproduced from pins, and the backend environment is unchanged. If a dependency genuinely cannot install, record the exact error and keep working on other tools.

## Task 2 — one small shared contract

Freeze these concepts before writing wrappers; use dataclasses/Pydantic compatible with the existing backend. Third-party runtimes serialize plain JSON across the boundary, not pickles or imported upstream model classes.

**CollectorRequest:** `source_id`, `tool`, `connection_key`, `generation`, `query_fingerprint`, `role`, `location`, `country_code`, optional `max_age_days`, optional approved `entry_url`, `cursor`, `max_results`, `max_details`, `deadline_seconds`. Keep inputs validated and bounded. Do not pass an entire resume or database credentials.

**CollectorBatch:** `jobs`, `next_cursor`, `coverage` (`partial`, `exhausted` or `unknown`), `warnings`, `skipped`, `request_count` if observable, `elapsed_seconds`, `tool_version`. Unknown request counts stay unknown, not zero. Jobs must normalize to existing `Listing` fields plus provenance facts. Include source and original application links, salary evidence, description completeness and real source publication dates when supplied.

**CollectorFailure:** typed reason (`unsupported`, `runtime_missing`, `login_required`, `blocked`, `rate_limited`, `changed_format`, `timeout`, `transport`, `invalid_output`) with safe message, optional HTTP status and Retry-After. Do not use arbitrary exception text containing tokens in user-visible errors.

Provide a standalone entry such as `collect(request) -> CollectorBatch` for each tool. Document exact imports and example invocation. Sol will implement worker policy around this interface.

All new batches convert to non-exhaustive `Snapshot` coverage for ingestion initially. `coverage=exhausted` means this particular query/window ended; it must not authorize closing missing jobs across the company's catalogue.

## Task 3 — supervised standalone runtime

- Implement subprocess invocation with bounded JSON input/output, a hard timeout, stderr-separated diagnostics and Windows-safe argument passing. Never use `shell=True` with request content.
- Kill and clean up task-owned subprocesses/browser children on timeout/cancellation; never terminate a user-managed service. Do not present a thread timeout as cancellation of the underlying work.
- Validate cursor version and query fingerprint. Preserve exact progress where the upstream exposes it; otherwise report an unresumable limit instead of inventing a cursor.
- Validate URLs and approved source domains. Reject local/private targets in configured inputs and test the source/browser navigation boundary. Record any external-library redirect/subrequest controls that still need Sol's review.
- Runners must never write to CareerOS's database. Importing the OSS modules or running doctor must not make network requests.

## Task 4 — JobSpy wrapper

- Use the installed release's supported API. One explicit site per invocation; no implicit all-sites call.
- Cover LinkedIn, Naukri, Indeed, Glassdoor, ZipRecruiter, Bayt, BDJobs and HelloWork where supported. Record actual country and parameter limitations; do not claim India coverage from a US-only source.
- Normalize NaN/nulls, enums, dates and DataFrames to JSON. Preserve upstream errors/warnings, even for an empty DataFrame.
- Handle bounded search, actual offset semantics, repeated pages, optional detail retrieval and partial results. Do not refetch every detail unconditionally.
- Reuse existing salary logic carefully: direct advertised fields retain provenance, estimated amounts remain unverified, and description evidence must not turn into source-field evidence after reassessment.

## Task 5 — ats-scrapers wrapper and employer mappings

- Verify the local package adapter exists; a hosted dataset source or directory row alone is insufficient.
- Implement careers URL resolution, local adapter selection, bounded collection and normalization. Do not make the hosted dataset a mandatory substitute for direct collection.
- Inspect official careers URLs for Cognizant, TCS, Infosys, Wipro, Accenture and Deloitte first. Separate regional entities and graduate/experienced hiring programmes. Verify directory candidates rather than guessing tenant slugs.
- Carry forward every existing employer candidate into the coverage ledger. A verified lookup without a tested fetch remains a mapping, not a connection.
- If an upstream fetch is unbounded and has no resumable API, record its runtime limitation explicitly. Do not fake partial progress.

## Task 6 — three OmkarCloud wrappers

- Implement bounded local search/details for Instahyre, Internshala and Shine using their pinned upstream functions.
- Keep source-native locations, skills, experience, publication/expiry and salary/stipend periods. Ignore recruiter personal details that the catalogue does not need.
- Test pagination and errors independently per project; do not assume all three use the same transport.
- Demonstrate that no collector calls its paid hosted API. Test actual output shapes rather than coding only from README samples.

## Task 7 — Crawl4AI wrapper and source profiles

- Implement a working local browser runner and profile format: approved domains, entry URL, search actions, page-ready condition, job links, next/load-more/scroll action, detail traversal, extraction and budgets.
- Prioritize Unstop and Wellfound, then uncovered company portals, Cutshort, Foundit, Cuvette and Superset. Record outcomes for other named inventory sites. Do not mark a profile implemented solely because it contains a URL.
- Prefer JobPosting/structured data or tested deterministic extraction. Support optional AI extraction of loaded content, with source evidence and validation; ordinary operation cannot depend on a hosted free LLM quota.
- Classify explicit zero matches, missing content, login, challenge/block and changed layout separately. Do not run AI extraction on an access-denied page as if it contained jobs.
- Browser fallback does not prove the whole site was searched. Test page traversal and detail descriptions. Limit any fallback attempts and report remaining coverage.

## Task 8 — tests, technical probes and coverage ledger

Run offline tests for contracts, upstream output normalization, errors, pagination, duplicates, schema changes, salary provenance, timed-out child cleanup, URL boundaries and no side effects. Add regression tests that establish behavior, not tests that merely assert function names exist.

Use bounded neutral public queries for technical probes, separate from the personal search. Save only isolated artifacts with source/tool/version, query, time, count, one redacted representative shape, description completeness and pagination observations. Include blocked/failed outcomes. Do not perform unrestricted catalogue scans. If sandbox networking fails, use the normal escalation mechanism rather than treating it as a provider failure.

Populate `OSS_SOURCE_COVERAGE.json` from the actual inventory: retain every original site and employer, and add Shine without removing an existing target. States: planned, downloaded, installed, wrapper-tested, mapped, live-verified, partial, blocked, login-required, unsupported, excluded-paid, not-a-job-catalogue. Include preferred tool, official URL, exact runtime version, country/programme scope, last technical probe and concrete outstanding input.

No request to stop and approve each phase is necessary: complete all independent Part 1 tasks. A blocked website does not block installation/testing of the others. Never label a dummy wrapper or an assignment to Crawl4AI as a successful integration.

## Required handoff to Sol

Write `OSS_LUNA_HANDOFF.md` containing:

1. Exact changed/new files, with a short purpose for each.
2. Installed versions/commits, lock/license locations, interpreter paths, setup and doctor commands, plus actual doctor output.
3. Frozen contract imports and runnable examples for each wrapper.
4. Offline test commands and actual results; relevant baseline failures identified separately.
5. Per-tool and per-priority-site live-probe results, with artifact paths and exact blockers. Separate installed, fixture-tested and live-verified.
6. Source ledger path, unresolved mappings, pagination/runtime limitations and any subprocess/network-boundary concern for review.
7. Confirmation that active search routing, production dependencies, personal data/settings, services and legacy files were not changed.
8. Remaining Part 2 work mapped to `OPEN_SOURCE_DISCOVERY_PART_2_SOL.md`.

Then stop before changing production search routing. The user will bring the handoff back to Sol. Do not claim the website has switched engines.

## Prompt to start Luna

> Work in C:\Users\nayan\Downloads\careeros_scaffold\careeros. Read OPEN_SOURCE_DISCOVERY_PART_1_LUNA.md and the referenced master plan, then implement all Part 1 tasks. Build real integrations with the selected upstream open-source tools and test them; do not stop at plans, placeholder wrappers or inventory entries. Keep the active website/search path unchanged, personal discovery paused and all user-managed services untouched. Complete independent tasks when a source is blocked and document exact blockers. Finish with OSS_LUNA_HANDOFF.md so GPT-6.1 Sol can review and integrate the work in Part 2.
