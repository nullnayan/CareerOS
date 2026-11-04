**Latest connection/search release (2 November):** See [SEARCH_PIPELINE_ARCHITECTURE.md](SEARCH_PIPELINE_ARCHITECTURE.md). The requested 603 listings were cleared after backup, 13 free connections are configured, and discovery is paused until Search jobs is clicked.

# Discovery follow-up — 2 November 2026

The three review defects are fixed. Additional free-discovery work adds conditional HTTP caching, stored-feed status checks, four employer directory mappings, status uncertainty in the UI, and another experience-wording regression. This is not completion of every website integration in the original plan.

## Implemented and verified

- Company scans now carry a durable traversal start and validity state. The final successful page reconciles missing occurrences across all batches. Failed requests retain the checkpoint. Malformed pages, repeated jobs/cursors, rolling feeds and changed full-board membership suppress closure. A listing remains open while another active source occurrence exists.
- Re-enabling a source preserves Retry-After and normal polling deadlines. Explicit re-enable resets a permission/login stop without discarding its existing deadline. Regression cases cover both HTTP 429 and successful polling.
- Matching considers Ashby secondary locations and still enforces explicit remote-country restrictions. Assessment-cache versioning rechecks existing records on the next feed read.
- Experience-before-range wording, found on a live Graviton listing, now parses correctly instead of remaining unknown. Preferred experience remains optional.
- A bounded process-local cache sends ETag/Last-Modified validators. HTTP 304 reuses the validated response. Failures never serve stale data; private/no-store/varying responses and Adzuna credentials are not cached. The cache is optional and clears on process restart; durable scan progress remains in the database.
- Jobicy checks up to 100 older stored occurrences with its free batch status endpoint. Himalayas checks up to five older occurrences per execution. Queues rotate by occurrence timestamp. Explicit closure deactivates only that source occurrence; unknown/404 remains unconfirmed. All status changes commit atomically with ingestion/checkpoint advancement, and errors enter source backoff.
- Sources and job details expose availability-check uncertainty. Date rendering accepts timezone offsets. Production/browser checks include both behaviors.
- The company directory now has ten board mappings. Added Razorpay Software Private Limited, Meesho, Graviton Research Capital LLP and AiStudio. A directory mapping is separate from a workspace connection and live health.

No dependency installation, paid provider, purchased quota, proxy, new API key or discovery AI call was introduced. No migration is required. Personal jobs, resumes, profile, source enablement and automation settings were not written during this follow-up. No frontend/backend/worker/Docker service was started, stopped or restarted. Live provider results were ingested only into disposable in-memory SQLite.

## Live directory observations

| Board | Observation on 2 November | Result |
| --- | --- | --- |
| Razorpay / Greenhouse | 27 records, all full descriptions | Repeated isolated ingestion passed |
| Graviton / Greenhouse | 21 records, all full descriptions | Repeated isolated ingestion passed |
| AiStudio / Ashby | 3 records, all full descriptions | Repeated isolated ingestion passed |
| Meesho / Lever | Current public board found; API exceeded the 20-second response budget | Mapping retained; successful ingestion not claimed |
| Postman / old Greenhouse identifier | HTTP 404 | Excluded from connected-board suggestions; remains employer candidate |
| PhonePe / old Greenhouse identifier | HTTP 404 | Excluded from connected-board suggestions; remains employer candidate |

Live status-endpoint checks: Himalayas returned a correctly handled 404/unknown result for the documented example path. Jobicy exceeded the response budget; live compatibility for that endpoint was not confirmed today. Both adapters have isolated documented-response regression tests. Results: `backend/scratch/status_endpoint_probe_results.json`.

Machine-readable directory observations: `backend/scratch/discovery_completion_probes.json`. API counts are point-in-time observations, not suitable-job counts, market recall, permission to redistribute, or uptime guarantees. The probe script now uses the accepted directory; the recorded JSON also preserves the two rejected attempts.

Public board evidence: [Razorpay](https://job-boards.greenhouse.io/razorpaysoftwareprivatelimited), [Graviton](https://job-boards.greenhouse.io/gravitonresearchcapital), [Meesho](https://jobs.lever.co/meesho), [AiStudio](https://jobs.ashbyhq.com/aistudio). The last board requires JavaScript for its page; its public API returned three records.

## Validation

- Final full focused backend suite: **161 passed, 3 skipped**. Skips are opt-in real Docker compiler cases. Existing deprecation warnings remain.
- Frontend TypeScript check passed.
- Production build passed for all 21 routes, using `.next-discovery-completion-check`. The running `.next` output was not rebuilt, and Next.js's generated tsconfig include was restored afterward.
- Headless browser QA passed against static build artifacts and an intercepted disposable API: 55-job pagination, search/sort, details/save, company setup, source register, partial status, unknown availability, timezone-offset dates, and 390/700px layouts. Zero browser errors; zero servers started.
- Screenshots: `scratch/discovery-completion-ui/`. Desktop feed screenshot inspected visually.

## Remaining integration boundary

Working adapter families remain Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Remotive, Jobicy and Himalayas. They use ongoing public access rather than a trial quota. External throttling/availability still applies.

- LinkedIn's [published restrictions](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibited-software-and-extensions) do not establish an unattended collection route for CareerOS.
- [Wellfound General Terms](https://wellfound.com/terms) and [Internshala terms](https://internshala.com/terms) restrict the proposed collection/reuse. Their candidate accounts are not connected to a background export adapter.
- Naukri's official terms URL was blocked to the research browser by robots.txt; no conclusion that its terms were successfully reviewed is claimed. No supported free export route was established. JobSpy remains uninstalled and is not represented as an official or reliable integration.
- Unstop's jobs/terms routes returned a cookies/JavaScript requirement in the research browser. No supported export route or successful collector was verified. This does not prove that no integration is possible.
- Workday, Oracle Recruiting, Taleo, SuccessFactors and iCIMS still need employer-specific external routes or authorized feeds. Internal employer APIs are not universal public catalogues. [SAP's documentation](https://learning.sap.com/courses/sap-successfactors-recruiting-candidate-experience/describing-the-new-features-and-enhancements-in-the-2h-2023-release_f278480f-f3fe-4bf0-9c57-ad63fdda3f5b) describes employer-configured XML/RSS feeds; CareerOS does not possess those feeds for every employer.
- The other inventoried platforms and remaining employer candidates still need individual route/access/schema assessment. No successful pilot or finished adapter is claimed for them. Every named platform stays in the source register; unverified entries are not active connections.
- The existing one-posting fresher reference check plus these live board checks do not constitute an independently curated market-coverage benchmark. A broad eligible-job recall benchmark remains unfinished.

See `SOURCE_ACCESS_REVIEW_2026-11-02.md` for all 45 entries. Several requirements remain unresolved, so this report deliberately does not label the whole original plan complete. Universal, unlimited, permanently free internet-wide scanning cannot be promised by a connector implementation.

## Use the changes

1. When ready, reload/restart the backend and worker yourself in your existing terminals. No database migration or Docker restart is needed. A development frontend can hot reload; a production frontend needs your normal build/start workflow.
2. Open Jobs → Sources. Add whichever company boards and free feeds you want. Nothing was automatically connected to your workspace.
3. Save/review Preferences, then Refresh. Manual refresh remains bounded; subsequent runs resume checkpoints when due. Completed multi-batch boards can now close removed jobs safely.
4. Enable recurring automation only when you want it. The existing local worker and computer must be running. Discovery/preparation does not submit applications or link job-board accounts.

Public status endpoint references: [Jobicy batch status](https://jobicy.com/jobs-rss-feed), [Himalayas single-job status](https://himalayas.app/api). Confirmed closed, unknown and network failure are handled separately. Budgeted checks can take multiple runs to cover a large retained catalogue; this is not instantaneous verification of every stored job.
