**Latest operating rule and controls:** Personal discovery is paused at the user’s request while source tools are completed. Undisclosed pay is included by default; relevance and salary filters are flexible. See [TOOL_VALIDATION_STATUS.md](TOOL_VALIDATION_STATUS.md). Earlier strict-pay/60-minimum descriptions below are historical.

**Latest connection/search release (2 November):** See [SEARCH_PIPELINE_ARCHITECTURE.md](SEARCH_PIPELINE_ARCHITECTURE.md). The requested 603 listings were cleared after backup, 13 free connections are configured, and discovery is paused until Search jobs is clicked.

**2 November follow-up:** See [DISCOVERY_COMPLETION_REPORT.md](DISCOVERY_COMPLETION_REPORT.md) for review fixes, full-traversal closure, feed status checks, caching, directory verification and unresolved integrations. Earlier single-snapshot-only closure notes are superseded.

# Personal job automation — implementation status

31 October 2026.

The AI stack uses five task-scoped Groq credentials plus local embeddings. See GROQ_MIGRATION.md. The uploaded resume has a separate compiled correction for baseline review. For current startup and full workflow instructions, see AUTOMATION_SETUP.md.

## First release implemented

- CareerOS password, registration, OTP, and reset endpoints are no longer mounted. Old login URLs redirect to Overview.
- A fresh local workspace was created at the user's request. The four pre-existing accounts were preserved.
- Active APIs use a stable local owner; direct login-cookie lookups were removed from parsing.
- Both old whole-resume tailoring agents were removed. Old mutation/export endpoints return a retired response. Chat directs users to the controlled tailor.
- Master source import, optional reference PDF, immutable revisions, baseline compilation/review, and explicit activation are available.
- Master input supports both `.tex` upload and pasted complete LaTeX, with optional reference PDF in either mode. Edit as new revision copies source into the editor; imports never overwrite the active master. Runaway-argument errors identify their source line.
- Tailoring selects up to five missing JD concepts, checks the full master for aliases/existing mentions, and requires explicit confirmation for additions.
- Only Skills category values can change. Protected source regions are checked, special characters are escaped, and original skills remain in order.
- Local dictionary extraction requires no API. Existing Groq extraction is optional and has no paid-provider fallback.
- Docker-based pdfLaTeX compilation runs offline with shell escape disabled, reduced privileges, resource limits, and isolated working files.
- Generated PDF validation checks page count, overflow, inserted text, and protected content. Low-priority additions are removed if needed for fit.
- Prepared source/PDF downloads and run history are available. Preview responses are inline, download links request attachments.
- Host/origin protections and single-use GitHub OAuth connection states are in place.
- Local system typography removes the prior Google Fonts build dependency.

## Resume onboarding

The original NAYAN_KUMAR_RESUME.tex was preserved. Compilation exposed a missing outer list item and an overflowing education row. A separate repair candidate fixes those two source issues and compiles to one page. It is imported and compiled in the new workspace, awaiting the user's baseline review and activation. No job-specific test skills were inserted into the real workspace.

## Verification

- 49 relevant backend tests passed, including real Docker PDF generation, fresh-owner creation, source invariants, builder export, and ATS regressions.
- Production Next.js build passed for all routes.
- Headless browser test passed import -> compile -> activate -> analyze -> confirm -> generate -> download, using a disposable database only.
- Mobile check passed without horizontal overflow.
- Generated baseline and test PDFs were rendered with Poppler and visually inspected.
- Fixed an existing ATS fallback defect exposed by the tests: a description with no recognized skills no longer receives a fabricated match score from title/seniority checks.
- Existing deprecation warnings remain; they did not fail the tests.

## Job discovery release implemented

- Editable fresher preferences, explicit confirmation before discovery, conservative eligibility checks, and explainable ranking.
- Greenhouse and Lever company-board connectors; optional Adzuna using existing credentials. No new paid provider or discovery AI calls.
- Source directory and health, deduplication, immutable JD history, safe failure preservation, manual JD import, saved/dismissed filters, and job-to-tailor handoff.
- Additive migration `301030_job_discovery` applied to the local PostgreSQL database. Existing accounts and resume data preserved.
- No synthetic jobs or eligibility preferences saved to the real workspace. Complete setup at http://127.0.0.1:3000/jobs.
- 78 relevant regression cases passed, including the real PDF case after Docker was restarted. Production build and isolated browser flow passed, including mobile/tablet overflow checks.

See JOB_DISCOVERY_SETUP.md for startup commands and source limitations.

## Automation, applications, and browser assistant implemented

- Separate durable worker with persisted schedules/tasks, leadership lock, expiring leases, deduplication, bounded retries, source Retry-After handling, and daily PDF limits in Asia/Kolkata.
- Background preparation produces immutable partial drafts using only previously confirmed skills. Other suggestions are listed for confirmation; Review skills again starts a new analysis without replacing prior artifacts.
- Automation page supports schedule settings, worker heartbeat, queue/history, Run now, retry, and queued cancellation. Pausing stops new scheduled work and cancels queued automatic tasks; running work may finish.
- Application ledger supports planned/applied/interview/offer/rejected/withdrawn, notes, follow-up dates, ready-resume pinning, and immutable activity events. Recording submission requires explicit confirmation.
- Paired Chrome/Edge Manifest V3 extension supports reviewed single-page JD import, selected basic-field autofill, and prepared PDF download. Revocable hashed credentials are bound to the paired extension ID and current workspace.
- Browser autofill profile/pairing/revocation page, Applications page, and Automation page are linked from More and Jobs.
- Migration `301031_automation` applied after backing up PostgreSQL to `.implementation-backups/before-automation.sql`.
- Final combined backend regression: 122 passed, including both real Docker PDF flows. Extension JavaScript: 4 passed. Real unpacked Chromium pairing, selected-field fill, and revocation passed; the test manifest copy grants only its local fixture to simulate the toolbar's activeTab grant. Shipped permissions remain unchanged.
- Live PostgreSQL check confirmed that a second connection cannot acquire worker leadership and can acquire it after release.
- Final production build passed for all 21 routes using a separate output directory. Actual API browser checks passed the application/profile/pairing/revocation workflow, with no JavaScript errors or horizontal overflow at 390px and 700px. Test data stayed in disposable databases.

## LaTeX compatibility update

- Upload/paste plus full-project ZIP, compiler selection/auto detection, local assets, unvalidated recovery preview, reviewed repair proposals, reference comparison, and complete project downloads are implemented.
- Unfamiliar templates can import and compile before Skills mapping is configured. Common category commands are detected; explicit markers support custom heading/layout commands while preserving all protected source and PDF content.
- Compatibility compiler image built successfully with real pdfLaTeX, XeLaTeX, and LuaLaTeX checks. Relevant backend coverage now totals 176 passing cases, with one platform-permission skip. Production build and browser checks passed.
- The uploaded failing master still needs its two proposed source repairs; the exact proposal was compiled successfully without accepting it or changing the stored source.

See LATEX_COMPATIBILITY.md for usage, supported inputs, and remaining project limits.

## Groq syntax repair and independent-organization backups

- Added Repair with Groq AI: strict initial compilation, at most two model-output attempts, small exact edit validation, protected resume text/number/order checks, strict recompilation, and immutable compiled output with a persisted diff. Activation stays manual.
- `latex_repair` uses the tailoring primary. Every AI task has up to four backups from the other configured groups because the user confirmed independent organizations. Key/model cooldowns, deduplication, earliest-reset reporting, and an explicit shared-quota override are implemented. Settings exposes backup variable names without values.
- Live Groq repaired the uploaded failing master in one repair attempt and compiled it to one page. The original revision and active master were preserved; `master-ai-repaired.tex` is ready for review.
- AI-repair API/browser checks passed, including persisted diffs, source preservation, responsive layout, and explicit activation. Synthetic failover tests cover every task, shared-quota protection, cooldown skipping, and exhausted/duplicate credentials.
- Final focused routing/repair regression: 59 passed. Compatibility/tailoring regression with real compilers: 96 passed and one platform-specific symlink check skipped. The final frontend production build passed for all 21 routes.
- Fixed the normal Master Resume path: Compile baseline now automatically tries Groq after failure (remembered browser opt-out available), switches to the compiled repaired revision, and clears stale errors on revision changes. Repeated repairs for an original reuse the verified result. Source selection is disabled while operations are running to avoid cross-revision errors.

## Operational limits and setup

The worker must be running alongside Docker and the app. Scheduled discovery remains disabled until you save your real preferences, connect sources, and enable it. The extension requires manual Load unpacked and pairing in your browser. No test jobs, profile values, application states, or confirmations were saved to your workspace.

LinkedIn, Naukri, Unstop, Wellfound, and Internshala do not have automatic server-side connectors in this release. Their JDs can be imported through an explicit browser selection/review or pasted on Jobs. The extension fills recognized empty HTML inputs; unfamiliar widgets, cross-origin frames, file uploads, and final submission remain manual. This is a local personal deployment, not a cloud always-on service.

## Review

Frontend: http://127.0.0.1:3000/master

Backend: http://127.0.0.1:8010

See PERSONAL_MODE_SETUP.md for restart commands and backup locations. Another service occupies port 8000 and was left untouched.

## Simplified master resume and compact models

- Master Resume now shows only LaTeX upload/paste, optional reference PDF, Compile resume, and the resulting PDF/downloads. Use as master follows PDF review. Previous technical controls are no longer exposed.
- A single backend request imports and compiles; failures send complete source and compiler errors to Groq, receive full corrected LaTeX, and automatically recompile with at most two correction attempts. Exact-fragment patch matching is removed from this flow.
- The latest attached source passed a live Groq plus Docker correction/compile test and produced a one-page PDF without detected overflow; rendered layout reviewed. Original and active masters were not changed by validation.
- Routine chat/text tasks use compact GPT-OSS 20B; syntax repair and vision retain Qwen 27B. Task output limits reduce unnecessary generation. Existing independent-organization backup keys remain enabled.
- Current usage instructions in LATEX_COMPATIBILITY.md supersede the older compatibility UI descriptions above.


## Free discovery expansion — 1 November 2026

- Fixed canonical duplicate ingestion under production `autoflush=False`, preserving immutable revisions, matches and occurrences. Actual Stripe/Point72 data passed repeated disposable ingestion.
- Added documented Ashby, SmartRecruiters and Workable company adapters; public Remotive, Jobicy and Himalayas feeds; known-host board detection; bounded requests/pages/details; checkpoints; durable throttling/backoff; permission stops; progress heartbeats; paced automatic continuation and lease renewal.
- Retained 45 source entries and 51 employer candidates. Unsupported sources stay disconnected. JobSpy was reviewed without installation or account/proxy use. Adzuna is excluded from scans while historical records and settings remain intact.
- Added SQL pagination/filter/sort with rule-based assessment caching and invalidation. Source access, implementation, dated probe evidence, workspace health, scope and next checks are visible. Publication, first-seen, source update and verification dates remain distinct.
- Applied additive migration `301101_discovery_indexes` after a PostgreSQL backup. Personal jobs remain 398; active master, source enablement and automation settings are unchanged. Automation remains disabled.
- Read FREE_JOB_DISCOVERY_IMPLEMENTATION_REPORT.md for exact validation, remaining limitations and user-run restart commands. No server was started/stopped/restarted during implementation.
