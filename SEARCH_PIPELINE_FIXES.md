# Search results and filters — 3 November 2026

This update supersedes earlier report statements about the eight-result JobSpy window, 15-minute search cutoff, overlap stopping, relevance controls, Instahyre proxy requirement, and lack of cross-process cancellation.

## Search behavior

- Jobs no longer display a relevance number, expose a relevance filter, or sort/filter by the historical score. Automated resume preparation no longer uses that score or its old threshold; it considers eligible jobs by publication/first-seen date. Existing stored score fields remain for database compatibility.
- The experience selector supports 0 through 10 years. It includes jobs whose stated minimum experience fits the selection. Unknown experience is explicitly labeled and has its own inclusion checkbox; it is never converted to zero.
- Naukri's `experience_range` and source job-level evidence survive normalization. Eligibility considers the source range alongside description requirements. The cache version changes so previously stored source evidence is reassessed. Old postings whose discarded evidence is absent need recollection.
- Posting-age choices include last 1 day and last 3 days. Changing a dropdown filters stored jobs; clicking Search jobs saves the chosen age and experience before starting collection. JobSpy receives the selected age in hours. Source-local limitations remain visible; no claim that every collector implements a date search remotely.
- JobSpy retrieves up to 20 jobs with bounded inline descriptions per call instead of eight. Other tools keep their separate existing batch sizes. HTTP deadlines/request ceilings still prevent hanging processes, and real source blocks/rate limits remain respected.
- A partly overlapping page is deduplicated and continues while new results are found. Fully repeated pages stop with a warning. The offset advances over the raw returned page, not just the surviving normalized rows.
- OSS continuations are paced at 10 seconds instead of 60. The arbitrary 15-minute chain cutoff is removed. Individual operations remain bounded; chains stop on exhaustion, no progress, source failure/access restrictions, or user pause/cancel.
- Finished sources are marked for their search generation so a long chain does not start scanning them again after a normal polling interval. A deliberate new search starts fresh checkpoints and clears successful-search polling delays while preserving real error/rate-limit cooldowns.

## Verification

- Final related backend suite: **307 passed, 3 skipped**. The two assertions that depended on relevance were updated to check salary/date ordering and absence of a score gate. New regressions cover Naukri ranges, unknown experience, 1/3-day filters, 0–10 years, new-search checkpoints, continuation after 15 minutes, and no refetch of finished sources.
- Frontend production build passed, using `.next-search-filters-final` separately from the running server's `.next`. TypeScript configuration was restored byte-for-byte.
- Isolated browser verification passed: no search on load, no relevance score/control, experience values 0/3/10 and unknown inclusion, 1/3-day filters, selected age saved before search, editable salary controls/unknown salary, sorting, pagination, details/save, source setup, and mobile/tablet overflow. No servers were started.
- A neutral seven-day India software-engineer probe collected **39 distinct Naukri jobs** and **40 distinct LinkedIn jobs** over two batches each, from many companies. Naukri returned stated experience ranges including 0–1 years and experienced roles. These counts describe unfiltered retrieval samples, not the number suitable for the user's profile or total source coverage.
- Live evidence is in ignored runtime artifacts `oss-tools/runtime/probes/pagination-naukri.json` and `pagination-linkedin.json`; test/build/browser logs are under `scratch/search-filters-*`.

## Loading the change

No user-managed service was started, stopped or restarted. Backend and worker processes must load the updated code before live searches use it. Refresh the frontend after its code is loaded, select experience/date controls, and click Search jobs. No personal database, profile or settings were read or modified by implementation/testing; neutral probe jobs were not ingested.

This fixes the integration's result restrictions; it does not resolve unrelated source access gates or promise every job on every website.
