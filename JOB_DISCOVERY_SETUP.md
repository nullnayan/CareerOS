**Latest operating rule and controls:** Personal discovery is paused at the user’s request while source tools are completed. Undisclosed pay is included by default; relevance and salary filters are flexible. See [TOOL_VALIDATION_STATUS.md](TOOL_VALIDATION_STATUS.md). Earlier strict-pay/60-minimum descriptions below are historical.

**Latest connection/search release (2 November):** See [SEARCH_PIPELINE_ARCHITECTURE.md](SEARCH_PIPELINE_ARCHITECTURE.md). The requested 603 listings were cleared after backup, 13 free connections are configured, and discovery is paused until Search jobs is clicked.

**2 November follow-up:** See [DISCOVERY_COMPLETION_REPORT.md](DISCOVERY_COMPLETION_REPORT.md) for review fixes, full-traversal closure, feed status checks, caching, directory verification and unresolved integrations. Earlier single-snapshot-only closure notes are superseded.

# Free local job discovery — 1 November 2026

This update supersedes the historical notes below. Read [FREE_JOB_DISCOVERY_IMPLEMENTATION_REPORT.md](FREE_JOB_DISCOVERY_IMPLEMENTATION_REPORT.md) for exact changes, setup/restart commands, validation, backups and remaining limitations.

Supported free routes: Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Remotive, public Jobicy and unauthenticated Himalayas. Add a supported company board by HTTPS URL/identifier or use the dedicated feed controls. The source register retains every named platform separately from connected sources; a checked board is not a promise of suitable jobs.

Adzuna is excluded from free scanning and cannot be newly added. Its prior enablement flag, credentials and historical listings were retained. Unsupported platforms remain unverified/permission-required or manual import. There are no paid fallbacks, trial dependencies, job-account credentials, unattended account automation or mandatory discovery AI calls.

Jobs searches retained records with SQL pagination, sorting and filters. Live Refresh is separate, bounded and resumable. Source polling/backoff and partial coverage are displayed; only complete single-board snapshots can close missing jobs. Attribution and source delays/windows apply.

Recurring automation remains disabled, matching the saved state. New adapters are available but were not automatically connected. Restart backend/worker yourself when ready using the report; no Docker restart is needed. No server was started/stopped/restarted by the agent. Validation used disposable databases and `.next-free-discovery-check`, preserving `.next`.

---

## Historical 31 October release notes

# Job discovery release

31 October 2026. Local frontend: http://127.0.0.1:3000/jobs. API: http://127.0.0.1:8010.

## Start the site

Open Docker Desktop, then run in PowerShell:

```powershell
cd C:\Users\nayan\Downloads\careeros_scaffold\careeros
docker compose up -d
cd backend
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8010 --reload
```

In a second terminal:

```powershell
cd C:\Users\nayan\Downloads\careeros_scaffold\careeros\frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
```

For production mode, stop the frontend, run `npm run build`, then `npm run start -- --hostname 127.0.0.1 --port 3000`. Do not run development and production servers on the same port. The existing compiler image is `careeros-latex:2026-10-compat`; if missing, build from the backend directory with `docker build -t careeros-latex:2026-10-compat ./compiler`.

## First search

1. Review and activate a compiled master under Master Resume.
2. Open Jobs → Preferences. Confirm roles, locations, graduation year, institution, education status, earliest joining date, experience, and optional salary. No sample profile was saved to your real workspace.
3. Open Sources. Add company boards from the directory, or enter another Greenhouse/Lever company board. Greenhouse and Lever public board requests require no API key.
4. Adzuna was optional in the historical release; it is now excluded from free discovery. Use the current public-feed controls instead.
5. Click Refresh jobs. Review eligibility reasons, uncertainties, source health, and relevance. Save or dismiss jobs and open the original application link.
6. View details → Review resume skills opens a run pinned to the job description and active master. Confirm only skills you know before generating a PDF.

## Sources and behavior

- Directory: Stripe, Canonical, Point72 (Greenhouse), ION Group (Lever). Availability and graduate batch requirements can change. The directory is not a promise of suitable openings.
- LinkedIn, Naukri, Unstop, Wellfound, and Internshala are external links only. Their listings are not automatically imported. Paste a job and its full description using Add a job description.
- Refreshes normalize listings, deduplicate canonical URLs or exact content fingerprints, preserve description revisions, and retain existing jobs on a source failure.
- Only a complete company-board snapshot can close missing listings. Search windows and incomplete responses do not close jobs.
- Eligibility checks include explicit seniority, experience, graduation batches, campus restrictions, location, remote restrictions, salary when comparable, and supplied posting dates. Unclear requirements remain reviewable; rules cannot resolve every employer wording.
- Rankings use current master content and confirmed skills. They are neither ATS scores nor interview probabilities. Unknown experience is flagged and its ranking capped.
- Adzuna and some company boards do not supply every requirement. A Greenhouse updated date is never represented as a publication date.
- No paid provider was added. Discovery uses no Groq requests. Optional AI skill extraction continues to use the existing task-specific Groq configuration.

## Storage and validation

Additive migration: `301030_job_discovery`. Source and database backups precede migration under `.implementation-backups/before-job-discovery.zip` and `.implementation-backups/before-job-discovery.sql`.

Discovery tests: `backend/tests/test_job_discovery.py`. Browser checks: `backend/scratch/verify_jobs_ui.py`, using a disposable database, mock listings, and browser-only API redirection to port 8011. Screenshots are under `scratch/jobs-ui-qa`. Public-board checks: `backend/scratch/check_job_sources.py`; these do not write workspace data.

The 78 relevant regression cases passed, with the real PDF compiler case rerun successfully after starting Docker. Production Next.js build and browser checks passed, including 390px and 700px layouts without horizontal overflow.

## Additional workflow now available

Scheduled durable discovery, background job-specific drafts, application tracking, and the paired browser extension are implemented. See AUTOMATION_SETUP.md for the separate worker terminal, schedule controls, profile setup, and extension installation. Opening an application link still does not submit it or mark it applied.
