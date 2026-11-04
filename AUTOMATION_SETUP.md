# Complete local CareerOS workflow

31 October 2026. This release adds durable scheduling, background draft PDFs, an application ledger, and a paired Chrome/Edge extension to the existing fresher discovery and LaTeX tailoring workflow.

## Run in your own terminals

Open Docker Desktop. In terminal 1:

```powershell
cd C:\Users\nayan\Downloads\careeros_scaffold\careeros
docker compose up -d
cd backend
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8010 --reload
```

In terminal 2:

```powershell
cd C:\Users\nayan\Downloads\careeros_scaffold\careeros\frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
```

In terminal 3:

```powershell
cd C:\Users\nayan\Downloads\careeros_scaffold\careeros\backend
.\venv\Scripts\python.exe -m automation.worker
```

Open http://127.0.0.1:3000/jobs. Backend logs stay in terminal 1; frontend logs in terminal 2; background work logs in terminal 3. Keep Docker and the worker running for scheduled work. The machine does not run jobs while powered off or sleeping. One bounded catch-up occurs after restart; missed intervals are not all replayed.

## Complete personal setup

1. Master Resume: upload a `.tex` file or paste the complete LaTeX code, optionally add a reference PDF, and click Compile resume. The backend automatically attempts Groq correction and recompilation if needed. Review the generated PDF and click Use as master for future tailoring.
2. Jobs → Preferences: confirm your real graduation year, institution, joining date, roles, and locations. Jobs → Sources: connect company boards.
3. More → Automation: choose the interval, relevance threshold, maximum pending preparations, and daily PDF limit. Save with scheduled discovery enabled when ready. Discovery is off until you explicitly enable it.
4. More → Browser autofill: enter and save the contact/profile values you want to use. Nothing is inferred about visa status, identity, demographics, or legal declarations.

No synthetic profile, sample jobs, applications, or skill confirmations from validation are written to the personal workspace.

## Automation behavior

PostgreSQL stores schedules, tasks, leases, retries, errors, and artifact references. One worker owns a PostgreSQL leadership lock, so two worker terminals cannot both compile. Tasks recover after an expired lease; transient failures retry up to three attempts with backoff and source Retry-After delays. Invalid or stale input needs review rather than endless retries.

Pausing cancels queued automatic work and prevents future scheduled work. A running operation can finish; its PDF and history stay available. Explicit Run now and Queue resume PDF actions remain available. Queued tasks can be cancelled; failed/cancelled tasks can be retried. A changed job description or active master requires fresh preparation.

Only jobs that pass stated eligibility checks are selected automatically. Uncertain joining dates, batches, or other requirements remain in the feed for manual review. Up to the configured pending-task limit are queued. PDF tasks wait until the next Asia/Kolkata day when the daily limit is reached.

Each draft starts from the immutable active master. Only previously confirmed missing skills can be added automatically, up to five; other suggestions appear under Awaiting confirmation. All normal source/PDF invariants still apply. Open the skill review and choose Review skills again to confirm more skills in a new immutable run. Draft creation never submits an application.

## Applications

Use Track application on a job to create a planned record. More → Applications supports notes, follow-up dates, status history, and a pinned ready resume. Mark Applied only after submission; the UI requires explicit confirmation. Status changes do not interact with the employer site. Existing pinned PDFs remain attached even when a later master is activated.

## Install the browser extension

1. Open `chrome://extensions` or `edge://extensions` in your browser and enable Developer mode.
2. Choose Load unpacked and select `C:\Users\nayan\Downloads\careeros_scaffold\careeros\extension`.
3. Open CareerOS → More → Browser autofill and generate a pairing code. It expires after five minutes and can be used once.
4. Open the extension popup, paste the code, and pair. Credentials are stored as hashes in CareerOS and can be revoked from the Browser autofill page.
5. On an application page, click Preview fields. Review/select the proposed values, then click Fill. Only recognized empty basic text inputs are filled. Existing values, uploads, custom widgets, sensitive declarations, and submission remain manual.
6. Prepared PDFs can be downloaded from the extension and selected manually in the employer upload field.

The extension uses activeTab rather than access to every browsing page. It runs only after your click. Chromium grants the permission through the extension toolbar action. Generic HTML inputs and Greenhouse/Lever patterns are supported; iframe-hosted forms may need opening the actual application URL in its own tab. Unsupported widgets stay manual.

## LinkedIn, Naukri, Unstop, Wellfound, and Internshala

The automatic server-side connectors remain Greenhouse, Lever, and optional Adzuna with existing credentials. No unsupported private API or mass scraper is represented as a live integration.

For another board, open the job in your own browser, select its description text, and use the extension's job preview/import. Review title, company, location, URL, and text; confirm whether it is the full description before saving. This imports only the page content you explicitly supply. The Jobs page also supports pasted JDs. The extension does not log in, crawl search results, or submit applications for you.

## Storage, migration, and verification

Migration `301031_automation` adds the new tables without deleting existing accounts or resumes. Database backup: `.implementation-backups/before-automation.sql`.

Backend regression suites cover applications, pairing/revocation, current-owner boundaries, queue deduplication, leases, retries, pause/cancel, daily limits, and confirmed-only background preparation. `tests/test_automation_pdf.py` exercises a real Docker compile from an isolated queue to a downloadable partial draft when `CAREEROS_TEST_LATEX=1` is set. Browser verifiers in `backend/scratch` use disposable data. Extension tests and setup are under `extension`.

Validation: 122 backend cases and four extension JavaScript cases passed. The actual unpacked Chromium extension passed pairing, preview, selected-field fill, and revocation; its disposable QA manifest grants only the local fixture to simulate toolbar activeTab permission in headless mode. The shipped manifest retains activeTab and the loopback API host only. A live PostgreSQL advisory-lock check also passed.

The final production build passed all 21 routes. Actual API browser checks passed application tracking, submission confirmation, notes, follow-up dates, profile save, pairing, single-use redemption, and revocation; desktop and 390px/700px layouts were verified. The distributable extension package is `CareerOS-browser-extension.zip`; Load unpacked can use the existing `extension` directory directly.

For an isolated production build while a dev server is running:

```powershell
$env:CAREEROS_NEXT_DIST_DIR='.next-release-check'
npm run build
Remove-Item Env:CAREEROS_NEXT_DIST_DIR
```

Normal startup uses `.next`. No paid API provider was added. Discovery, ranking, worker scheduling, and extension autofill use no AI requests; optional Groq extraction remains available in Tailor.
