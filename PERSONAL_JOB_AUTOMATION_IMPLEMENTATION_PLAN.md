# CareerOS personal job automation — implementation plan

Prepared: 30 October 2026, Asia/Kolkata.

Status: design only. This document does not delete or change application code, authentication, resume source, database records, or existing files.

## 1. Product decisions

CareerOS becomes a local, personal workspace for Nayan's fresher job search. The complete workflow is:

1. Register one master LaTeX resume, optionally accompanied by its PDF.
2. Confirm career facts, skills, graduation eligibility, and search preferences.
3. Periodically collect jobs from sources that provide suitable permitted, free access.
4. Remove duplicates and evaluate fresher eligibility and relevance.
5. Show jobs with requirements, evidence, gaps, freshness, and application links.
6. Select up to five important job-description skills missing from the master resume.
7. Add eligible, confirmed skills to the appropriate Skills categories in a copy of the master LaTeX source.
8. Compile and validate a real LaTeX PDF.
9. Review the changes, download the application-specific PDF/source, and apply.
10. Track applications and later use an extension to help fill supported forms.

The application opens directly without CareerOS login, registration, OTP, or password reset. Existing records remain associated with one explicitly selected local owner. Third-party account connections, including GitHub OAuth, remain separate from CareerOS login.

No paid API dependency is part of the required path. Existing model clients are reused only where the account has usable no-cost allowance. Quota exhaustion pauses work or exposes a manual path; it must never enable paid usage automatically.

## 2. Scope boundaries

### Included

- Personal use, initially on this Windows computer.
- Fresher and graduate roles; internships only when enabled in preferences.
- One active master resume revision at a time, with revision history.
- Original LaTeX as the authority for resume appearance and content.
- At most five added skill concepts per job.
- Additions within existing Skills categories only.
- Job discovery, matching, scheduled refresh, resume generation, and application tracking.
- A later browser extension for supported application forms.

### Excluded from this rebuild

- Rewriting projects, education, employment, summary, achievements, or certifications.
- Automatically changing margins, fonts, page size, section order, or document spacing.
- Creating missing qualifications or treating a JD requirement as proof of competence.
- Mandatory subscription APIs, paid scrapers, or hosted paid resume conversion.
- Guaranteed aggregation or automation support for every named job board.
- Unattended application submission, CAPTCHA solving, or storing job-board passwords.
- Public, unauthenticated internet hosting.
- Rebuilding the independent visual resume builder, ATS analyzer, skills inventory, chat, or GitHub features.

## 3. Verified starting point in this repository

| Area | Current implementation | Consequence for the plan |
| --- | --- | --- |
| Frontend | Next.js 14, React, TypeScript, Tailwind | Extend the current application |
| Backend | FastAPI, SQLAlchemy, Alembic | Add small domain modules and migrations |
| Storage | PostgreSQL; Qdrant for career retrieval | Keep PostgreSQL authoritative; vectors remain optional for this workflow |
| AI | Central LLMClient and agent model routing | Reuse rather than introduce another API client |
| Main tailor | api/tailor.py and agents/tailor_engine.py | Replace their legacy whole-resume behavior |
| Additional tailor | agents/resume_tailor_agent.py, chat intent, routes inside api/resumes.py | Retire all reachable alternate tailoring paths |
| Current scoring issue | Apply creates tailored_json but scores the original ResumeVersion | Do not carry this behavior into the replacement |
| Current scoring split | Tailor analysis uses services/ats_scorer.py; apply uses ATS v3 | No mixed scoring in the replacement |
| Existing master candidate | NAYAN_KUMAR_RESUME.tex | Offer as an import candidate, not an automatically activated master |
| Auth | AuthContext, get_current_user, cookies/tokens, several direct UserSession lookups | Removing the login page alone would leave APIs broken |
| Job matching | JobMatch table and Adzuna setting names exist | Existing fields are insufficient; no working discovery connector was found |
| PDF generation | HTML/Jinja/Playwright rendering and other legacy paths | Keep for builder; create a separate real LaTeX compiler path |

The inspected LaTeX source uses article, letter paper, 11pt, custom resume macros, and five categories: Languages, Web Development, Databases, Tools/Cloud, and AI/ML. It contains an explicit Skills section bounded by the next Projects section. It also references glyphtounicode, which the compiler environment must provide.

The source lists graduation in May 2027. This is a candidate fact, not a confirmed current preference. Search must ask for batch, student/graduate status, and earliest joining date rather than equating fresher with immediately available graduate.

Repository policy: never read, print, or edit backend/.env or .env.local. Document any required variable names and let the user configure values. Existing provider integration does not prove a credential is present or a free quota remains.

## 4. Replace the old tailoring system completely within its scope

### 4.1 Replacement contract

The new tailoring engine has one purpose: select up to five missing JD skills and patch approved additions into the master resume's Skills section. No old bullet rewrite, summary generation, broad keyword insertion, score-gain estimation, or whole-resume rewrite rule should remain active in that workflow.

The new engine does not call an old tailor internally as a fallback.

### 4.2 Inventory and removal sequence

1. Capture the current call graph: frontend /tailor, typed API clients, /tailor/analyze, /tailor/apply, /tailor/versions, /resumes/tailor, phase8 exports, and chat-triggered tailoring.
2. Record old request/response contracts and keep representative examples for migration tests.
3. Implement the new contract behind a clearly separate internal module.
4. Switch the tailor UI, job preparation worker, and chat action to the same new service.
5. Remove legacy tailor prompts, rule tables, scoring estimates, full-resume mutation functions, and imports once no active callers remain.
6. Remove obsolete tailor endpoints or return an explicit retired-endpoint response; do not silently run old behavior.
7. Remove unreferenced agent model entries only after checking all callers.
8. Rewrite TAILORING_ENGINE_PLAN.md to point at this plan as the active direction. Label incompatible historical plans as historical.

This is a scoped deletion of obsolete tailoring behavior. Do not delete services/ats_scorer.py, ats_fixers, PDF helpers, schemas, or model clients merely because tailoring imports them today; other product surfaces use them. The independent ATS improvement tool may keep its own behavior but must never be invoked implicitly by new tailoring.

Keep historical tailored resumes and their files. Label old versions as legacy and do not use them as the new master or as truthful profile evidence by default.

### 4.3 Completion evidence

- All tailoring entry points resolve to one new service.
- No active tailor import references either legacy whole-resume agent.
- Chat cannot bypass the new patch restrictions.
- Existing builder, standalone ATS, chat retrieval, and GitHub operations continue to work.

## 5. Remove CareerOS login and retain a stable local identity

### 5.1 Owner selection and existing data

- Back up database records and local resume artifacts before migrations.
- On first migration, inspect account counts without exposing credentials.
- If there is exactly one existing owner, propose that owner for the personal workspace.
- If there are multiple owners, require selecting which one is Nayan's workspace; never combine or expose all accounts automatically.
- If there are no accounts, create one local owner record.
- Save the selected owner in a singleton workspace configuration. Do not regenerate its ID at every startup.
- Preserve user_id relationships and existing data filters.

### 5.2 Backend changes

- Introduce a workspace-owner dependency that resolves the configured local owner without login.
- Replace current-user dependencies throughout resume, ATS, skills, suggestions, chat, tailor, and GitHub routes.
- Replace direct cookie/UserSession lookups inside parse and legacy resume routes; route all active operations through the same owner resolver.
- Move profile editing out of /auth into a workspace-profile API.
- Remove registration, login, logout, OTP, password-reset routes and SMTP startup requirements from the active app.
- Remove imports of the auth router and authentication dependency once all callers migrate.
- Leave old auth tables and password hashes untouched during the first migration; dropping them is unnecessary for removing login.
- Keep GitHub credentials encrypted and continue to validate its OAuth state with a short-lived, single-use local connection transaction.

### 5.3 Frontend changes

- Replace AuthProvider with a workspace/profile provider.
- Remove redirect-to-login logic and authentication-only loading screens.
- Remove login/register/forgot-password pages and account/logout menu actions; old URLs can redirect to Overview.
- Remove session_token localStorage reads/writes and obsolete authentication headers from API helpers.
- Keep chat session IDs: a chat conversation ID is unrelated to a login session.
- Display Personal workspace and Settings in the menu.
- Keep TaskProvider mounted at a stable application level; durable jobs must not depend on page-local state.

### 5.4 Local access model

Serve frontend and backend on loopback. Publish PostgreSQL and Qdrant ports on loopback as well. No public deployment is included in the no-login design. Validate browser request origins and hosts, use a local workspace request token for mutations, and pair the future extension separately. These are local request protections, not a restored login screen.

Acceptance: a fresh browser opens Overview, all active APIs resolve the same owner, old data stays accessible to its selected owner, and no browser token or SMTP setup is required for normal use.

## 6. Master LaTeX resume management

### 6.1 Inputs

Supported first release: one UTF-8 .tex file, optionally one reference PDF. If a source requires assets or custom style files, support a reviewed project bundle later; do not pretend arbitrary LaTeX projects are already supported.

- LaTeX only: compile a baseline PDF and ask the user to approve it.
- LaTeX plus PDF: compile the source and show both outputs for comparison.
- PDF only: preserve for reference and request source; do not reconstruct the resume into a new layout automatically.

The uploaded PDF is a visual reference, not the source of truth. Differences between supplied PDF and compiled source must be surfaced before activation. Do not infer that the existing .tex file matches the separately mentioned Desktop PDF; that comparison has not been performed.

### 6.2 Immutable revisions

For every master revision store source bytes, source hash, filename, imported timestamp, compiler version/image, baseline PDF, page count, extracted text, category map, patch-region description, and validation outcome.

- Keep the raw uploaded source immutable.
- Create a versioned working template with explicit editable category-value boundaries, established once during onboarding.
- Prefer external byte-offset spans plus a source hash for the current single-file template; optional comment markers require a separately approved template revision.
- Validate that exactly one Skills section is selected.
- Refuse ambiguous category boundaries rather than applying a broad regex replacement.
- Changing the active master creates a new revision and affects future outputs only.

Every tailored artifact is derived from the selected master revision, never from another tailored artifact. Jobs pin the master revision they used.

### 6.3 Profile extraction

Extract skill terms and career facts for searching, but do not regenerate the .tex from parsed JSON. Parse errors must not alter the master source. Profile corrections and source changes are separate actions.

Acceptance: activate the intended source, preview its baseline, find all five current categories, retain the original bytes, and reproduce the same visible baseline after an application restart.

## 7. New skill selection policy

### 7.1 What counts as missing

The requested rule is skills present in the JD and absent from the resume. Compare normalized concepts against the entire master resume, including Skills, projects, coursework, and other sections.

- A concept already mentioned anywhere is not a missing skill.
- Equivalent names such as JS/JavaScript or K8s/Kubernetes do not consume additional slots.
- Related technologies are not automatically equivalent: Java is not JavaScript, Docker is not Kubernetes, and generic cloud coursework does not establish AWS proficiency.
- A skill known to the user but absent from the master can be added if it has been explicitly confirmed in the personal skill registry.
- A new JD-only skill requires confirmation. It must not become a profile fact merely because the model selected it.

If later desired, a separate user-controlled action can promote existing project skills into Skills. That is outside this first missing-skills policy.

### 7.2 Extract requirements once per JD revision

Produce structured terms with canonical name, original wording, required/preferred status, supporting JD excerpt, proposed category, and extraction confidence.

Ignore company boilerplate, benefits, equal-opportunity text, application instructions, and unsupported model inventions. Treat job text as data: instructions embedded in listings must never control the AI or trigger application actions.

Use the existing LLM client for bounded extraction and categorization. Deterministic validation must confirm that every selected term is grounded in the JD. If model access is unavailable, use the local skill dictionary and editable manual candidates, with reduced-coverage labeling.

### 7.3 Choose up to five

1. Remove concepts already present in the master.
2. Remove duplicates, aliases, generic personality phrases, and non-skill requirements such as years of experience.
3. Prioritize explicitly required skills over preferred ones.
4. Prioritize skills central to the role over incidental mentions.
5. Use repetition only as supporting evidence; boilerplate frequency must not dominate.
6. Order ties deterministically by first relevant JD occurrence, then canonical term.
7. Select the top five remaining concepts, or fewer if fewer are valid.

Show these candidates even if some require confirmation. Auto-add only the confirmed subset. Do not silently replace an unconfirmed top-five candidate with a sixth term; let the user dismiss and recalculate explicitly if desired.

Missing keywords are requirements to consider, not proof of ability. If a user says a selected skill is unfamiliar, record it as a gap and exclude it from the resume.

### 7.4 Confirmation and categories

Each candidate displays the JD excerpt, reason for priority, current evidence/confirmation status, category, and proposed text. The user can confirm, reject, or change category. A confirmation is reusable for future jobs but does not change the immutable master source.

Use the existing Languages, Web Development, Databases, Tools/Cloud, and AI/ML categories. If a term does not fit, ask for category selection; do not create a new heading automatically.

The same skill cannot appear in multiple categories. Existing skills are never deleted or reordered. Added terms go at the end of the chosen category in selection order.

### 7.5 Example behavior

If a JD names seven missing concepts, five are selected. If three of those five are confirmed, add three and show two awaiting confirmation. If no missing, confirmed concepts remain, generate an unchanged copy or show Already covered. Never force five additions.

## 8. Deterministic LaTeX patching

The model returns skill concepts and categories, not replacement LaTeX and not a rewritten document.

The patcher:

1. Loads the pinned master bytes and verifies the hash.
2. Resolves the exact value spans of the affected Skills categories.
3. Checks selected concepts against the JD, registry, duplicate rules, and five-skill cap.
4. Escapes literal text for LaTeX, including &, %, $, #, _, braces, backslash, tilde, and caret where needed.
5. Inserts only the text of approved terms and necessary separators.
6. Reconstructs the document while preserving encoding, line endings, and every byte outside allowed category spans.
7. Produces an audit diff and a new source hash.
8. Rejects changes to headings, macros, project text, personal details, preamble, geometry, or arbitrary commands.

Append-only verification checks existing category content and order as well as protected regions. A model-generated string containing commands must be treated as literal text or rejected.

Acceptance: a fixture with additions in two categories changes only those values; applying the same operation twice cannot duplicate terms; malformed or ambiguous input causes no partial write.

## 9. Compile the resume into a PDF

### 9.1 Compiler choice

Use local TeX Live with pdfLaTeX, initially through a pinned Docker compiler environment because Docker is already part of the development setup. The current source appears suited to pdfLaTeX, but successful baseline compilation is the acceptance gate. No compiler installation or package availability has been verified yet.

Install the required classes, packages, fonts, and glyphtounicode in the compiler image during setup. Compilation itself should run offline. Retain the image version with artifacts. Do not introduce an Overleaf dependency or a paid PDF API.

### 9.2 Isolation and execution

- Each compilation gets a unique temporary working directory.
- Mount only the selected input files and output directory, never the project secrets or full home directory.
- Run without network, with non-root privileges, a read-only base filesystem, and CPU/memory/process/time limits.
- Explicitly disable shell escape and prevent arbitrary host file access. Shell-escape disabling alone is not complete isolation.
- Use an argument-array subprocess invocation; do not interpolate uploaded filenames into a shell command.
- Make errors noninteractive and terminate on fatal compilation failures.
- Restrict inputs to approved project paths and reviewed support files; reject traversal, symlinks, and unexpected executable content.
- Cap compilation passes and capture bounded diagnostic logs.

pdfTeX documents a no-shell-escape option; use it in addition to container isolation. [pdfTeX manual](https://tug.ctan.org/systems/doc/pdftex/manual/pdftex-a.pdf)

### 9.3 PDF validation and layout policy

- Require a readable, nonempty PDF.
- Compare page count with the approved baseline; if baseline is one page, a two-page result is a failed automatic fit.
- Inspect compilation warnings and text bounding boxes for overflow or clipping.
- Extract text and verify added terms, allowing normal ligature/whitespace differences.
- Compare protected-section text against the compiled baseline with appropriate normalization.
- Render pages for visual review; protect headings, spacing, readability, links, and glyphs.
- Save build diagnostics and validation results with the artifact.

Adding text can move later content even when source outside Skills is unchanged. The requirement guarantees unchanged source content and styling, not identical pixel coordinates after insertion.

If additions create overflow, try again from the original master with the lowest-priority added skill removed, down to zero. Do not shrink fonts, change spacing, or delete existing material. Show which additions could not fit. If the master itself fails, stop and request correction rather than substituting an HTML rendering.

### 9.4 Deliverables

Expose the tailored PDF, tailored .tex file, before/after skill diff, job association, and validation status. Use a readable company-role filename plus an internal unique identifier. DOCX is outside the first LaTeX workflow because it cannot guarantee this template's appearance.

## 10. Personal profile and search preferences

Create a settings page with editable, confirmed fields:

- Target job titles and accepted alternatives.
- Locations, remote/hybrid/onsite preferences, relocation willingness.
- Employment type and whether to include internships.
- Graduation year, student/graduate status, degree, and batch eligibility.
- Earliest full-time joining date and internship availability.
- Maximum required experience, with uncertain requirements held for review.
- Salary preference, while keeping missing salary distinct from an unsuitable salary.
- Work authorization and relevant geographic restrictions, explicitly entered.
- Excluded companies, roles, locations, and previously rejected openings.
- Search frequency, result caps, and automatic PDF generation cap.

Start with preferences pending confirmation rather than infer them from unrelated chats. For example, do not hide a role with missing batch information or assume immediate availability from the fresher label.

The skill registry stores canonical term, aliases, category, source, confirmation state, and confirmation timestamp. Automatically generated tailored resumes must not feed new unconfirmed facts back into that registry or RAG context.

## 11. Job-source strategy

### 11.1 Source choices

| Source | Initial treatment | Release gate |
| --- | --- | --- |
| Greenhouse company boards | Candidate first connector; documented public GET interface | Known company board tokens, permitted usage, attribution/retention review |
| Lever company boards | Candidate first connector; documented postings interface | Known company site names, permitted usage and request limits |
| Adzuna | Optional connector; setting names already exist in config.py | User obtains eligible no-cost credentials; verify India coverage, allowed display, quotas, and JD completeness |
| LinkedIn | External search/navigation and authorized integration research | Do not promise backend scraping or browser automation |
| Naukri | External source option and partner-access research | A permitted free retrieval/display route must be established |
| Unstop | External source option and partner-access research | A permitted free retrieval/display route must be established |
| Wellfound | External source option and authorized-access research | Content reuse/collection rights must be established |
| Internshala | External source option and authorized-access research | Permission must cover the intended collection and AI use |
| User-provided job | Job URL plus explicitly supplied JD | Source recorded; do not automatically crawl restricted destinations |

No source badge should imply a live integration when the connector is disabled. External search links let the user browse that source; they do not import its results into CareerOS. User-provided content is not a substitute for checking applicable content-use restrictions.

Greenhouse and Lever are per-company interfaces, not universal job-search engines. Maintain a small, editable directory of relevant companies, board identifiers, and successful refresh timestamps. Public accessibility alone is not a blanket redistribution license; check intended use and provider conditions.

Documentation: [Greenhouse Job Board API](https://docs.greenhouse.io/job-board), [Lever Postings API](https://github.com/lever/postings-api), [Adzuna API overview](https://developer.adzuna.com/overview).

Source constraints: [LinkedIn automation policy](https://www.linkedin.com/help/recruiter/answer/a1340567), [Wellfound terms](https://wellfound.com/terms), [Internshala terms](https://internshala.com/terms/). No general public retrieval API was verified for Naukri or Unstop during this planning work. Avoid categorical claims that none exists.

### 11.2 Connector contract

Each connector reports source identity, capabilities, availability, fetch timestamp, native job ID, canonical URL, application URL, title, company, location, employment type, description, description completeness, salary with currency/period if supplied, published/deadline dates if supplied, and raw-source fingerprint.

Capabilities explicitly distinguish search, full-description retrieval, expiry checks, and application assistance. Store applicable attribution and retention constraints. Keep API credentials server-side.

### 11.3 Normalize and deduplicate

- Upsert by source and native ID.
- Prefer stable employer/requisition identifiers for cross-source merging.
- Normalize company, role, location, and canonical URLs.
- Use description similarity only as supporting evidence; do not merge distinct locations or requisitions solely by title.
- Preserve every source occurrence while grouping equivalent openings under one canonical job.
- Track first seen, last seen, last successful verification, and closed/expired/unknown status separately.
- A connector outage must not mark all its jobs closed.
- Do not label collection time as publication time.

## 12. Fresher eligibility and relevance

Run inexpensive structured filtering before model calls.

1. Identify explicit experience requirements and senior titles; reject clearly incompatible openings.
2. Check batch, graduation, joining date, employment type, and location restrictions.
3. Keep missing requirements as unknown, with a Needs eligibility review label.
4. Rank suitable roles using target title alignment, confirmed skill overlap, project relevance, location preferences, and freshness.
5. Explain the top reasons and missing must-have requirements.

Maintain distinct outputs: eligibility status, relevance score, skill coverage, and source confidence. These are not probabilities of interview or employment.

Job suitability must be evaluated from the confirmed profile before resume keyword additions. Adding a keyword cannot change factual experience, joining availability, or batch eligibility. Never reward the engine for inserting unconfirmed skills.

The existing ATS analyzer remains optional. If used, score extracted content from the actual compiled tailored artifact using one version of ATS v3. Reuse valid layout facts from that PDF; do not borrow original layout facts blindly. Do not show invented score-gain points or force score improvements as the success criterion.

## 13. Job feed and resume preparation UI

### 13.1 Navigation

Primary destinations: Overview, Jobs, Master Resume, Tailor, Applications. Keep existing ATS, Builder, Skills, Chat, and GitHub accessible through secondary navigation. Use the current paper/ink design system for new pages.

### 13.2 Jobs page

Filters: target role, location, employment type, source, freshness, eligibility, saved state, and resume status. Each card shows title/company, location, source, posted date when known, last checked, eligibility, relevance reasons, key requirements, and gaps.

Actions: View details, Save, Dismiss, Review tailored resume, Open application, Mark applied. Jobs without a full JD display Needs full description and cannot produce a supposedly complete tailoring result.

### 13.3 Job details and tailor workspace

Show the JD, original link, eligibility reasoning, top-five missing candidates, category placement, confirmation controls, source diff, baseline PDF, generated PDF, build status, and downloads.

The interface must clearly distinguish Suggested, Awaiting confirmation, Added, Omitted for fit, Already covered, and Rejected. A pending or failed artifact must not display a working-download badge.

### 13.4 Automatic preparation

For the top few eligible jobs, automatically analyze requirements and prepare a draft using confirmed skills. Starting default: up to five new successful PDF preparations per day, configurable later. Additional job analyses can be queued separately within quotas.

If a candidate needs confirmation, show that state without blocking unrelated jobs. A partial draft may include only the eligible subset, with the omitted terms clearly listed. A draft is available for review, never an implicit submission authorization.

## 14. Background automation

### 14.1 Minimal architecture

Use the existing PostgreSQL database for durable tasks, schedules, leases, and run history. Add a separate Python worker process using the existing database stack. A Redis/Celery dependency is unnecessary for the first personal release.

Persist schedules and have the worker check due work. A configurable starting schedule is 09:00 and 18:00 Asia/Kolkata. These are proposed product defaults, not automations created by this document.

The computer, database, and worker must be running. If the machine sleeps, perform one bounded catch-up when it resumes; do not promise always-on execution or replay every missed interval.

### 14.2 Pipeline

Collect -> normalize -> deduplicate -> assess eligibility -> rank -> extract JD skills -> select candidates -> patch eligible skills -> compile -> validate -> publish draft.

Separate collection, analysis, and compilation tasks so one slow source or failed document does not block the whole run. Use conservative provider-specific concurrency; start with one compiler job at a time.

### 14.3 Reliability

- Persist status, attempts, next retry time, lease expiry, progress, error category, and output references.
- Claim tasks atomically; reclaim abandoned tasks after lease expiry.
- Use unique idempotency keys to prevent duplicate artifacts and repeated source fetches.
- Retry transient timeouts/429/5xx with bounded backoff and applicable Retry-After handling.
- Do not retry invalid LaTeX, unknown source mappings, or malformed input indefinitely.
- Pause on quota exhaustion and expose when work can resume.
- Stop and cancel controls prevent new work; already completed files remain available.
- Show last successful run, new suitable jobs, drafts created, failed tasks, and next run.

Cache JD extraction by source-content hash, extractor version, and model. Cache tailoring by master revision, JD revision, confirmation-profile version, selected concepts, patcher version, compiler image, and policy version. A changed master invalidates future reuse but does not overwrite old application artifacts.

## 15. Data model and storage

Use Alembic migrations. Preserve existing records and constraints. Prefer additive tables to overloading structured_json with raw source and opaque binary artifacts.

| Proposed entity | Purpose |
| --- | --- |
| WorkspaceSettings | Selected owner, timezone, local-mode settings |
| CareerProfile / profile revision | Confirmed eligibility and search facts |
| ConfirmedSkill | Canonical skills, category, aliases, confirmation provenance |
| ResumeMaster | Logical master and active revision pointer |
| ResumeMasterRevision | Immutable .tex/source hash, category mapping, baseline artifact, compiler settings |
| JobSearchPreferences | Search filters, caps, frequencies, exclusions |
| JobSource / CompanyBoard | Capabilities, allowed access settings, board directory, refresh health |
| JobPosting | Canonical opening, stable identity, normalized facts |
| JobSourceOccurrence | Source IDs, URLs, attribution, seen/verified state |
| JobDescriptionRevision | Description snapshot, completeness, hash, extracted requirements |
| JobMatch | Per-owner eligibility, relevance, explanation, dismissal/saved state |
| TailoringRun | Pinned inputs, top-five candidates, decisions, patches, state, diagnostics |
| ResumeArtifact | Original/tailored source and PDF paths, hashes, validation, page count |
| Application | Job, exact submitted artifact, status, dates, notes, evidence |
| AutomationSchedule / Task / Run | Durable execution and activity history |
| ExtensionPairing | Revocable local connection for supported form assistance |

Evolve the existing JobMatch table where compatible; avoid two competing authoritative match tables. If linking new LaTeX artifacts into ResumeVersion, preserve its existing source constraint or add an explicit migration before introducing any new source value.

Store files under a configured application data directory, with generated internal IDs rather than user-controlled path names. Keep metadata and hashes in PostgreSQL. Back up database and artifacts together and provide export of the master and application history. Never place API keys in logs, documents, source bundles, or the browser.

## 16. Proposed backend boundaries and APIs

These are design names, not implemented endpoints. Resolve final path conflicts against existing routes during implementation.

| Area | Proposed operations |
| --- | --- |
| Workspace | Read personal workspace; edit profile/preferences; select owner during migration |
| Master resume | Import .tex and optional PDF; inspect baseline; confirm regions; activate revision; download source |
| Jobs | List/filter; detail; import supplied JD; refresh; save/dismiss; verify status |
| Tailoring | Analyze job against master; confirm candidate skills; prepare; read progress; download artifacts |
| Applications | Create/update application; pin submitted resume; record status and notes |
| Automation | Read/edit schedule and caps; run now; pause/resume; cancel task; inspect history |
| Extension | Pair/revoke; read minimal application context; propose answers; report confirmed submission |

Proposed internal modules:

- core/workspace.py for local-owner resolution.
- api/workspace.py, api/jobs.py, api/automation.py, api/applications.py, and a rewritten api/tailor.py.
- tailoring/requirements.py, selection.py, policy.py, latex_regions.py, patcher.py, and orchestrator.py.
- services/latex_compiler.py, resume_artifacts.py, and pdf_validation.py.
- jobs/connectors/, normalization.py, deduplication.py, eligibility.py, and ranking.py.
- automation/worker.py, scheduling.py, tasks.py, and quotas.py.

Keep API routes thin. The worker, chat, and UI call the same services. Do not let an API-supplied arbitrary filesystem path select a master or output file.

## 17. Free-service and request budget policy

Use the current LLMClient and routing registry. Add narrow roles for JD skill extraction and category classification if required. Do not inherit old multi-phase resume rewrite agents or assume the comments about model availability are current.

- Groq is a candidate default when the user's existing account has available free limits.
- NIM or Gemini may be optional only when the account's current no-cost allowance and intended use permit it.
- The existing local-model route may serve as an optional fallback if already installed and suitable; do not assume hardware or model availability.
- Required path works with manual term review when AI is unavailable.
- Job collection initially uses documented company boards; Adzuna remains optional until credentials, quota, and terms are checked.
- Compilation, ranking rules, storage, and scheduling run locally.
- No automatic switch to Anthropic, paid Groq tiers, paid aggregators, or other billable fallbacks.
- Display request estimates, observed throttling, paused tasks, and cache hits; do not advertise unlimited free access.

Groq documents multiple request/token limits, so rate handling must account for more than requests per minute. NVIDIA describes API-catalog use for prototyping; it does not justify a promise of perpetual unlimited hosted inference. [Groq rate limits](https://console.groq.com/docs/rate-limits), [NVIDIA NIM FAQ](https://docs.api.nvidia.com/nim/docs/product).

Existing Adzuna variable names establish integration readiness only. Adzuna's overview requires app_id and app_key; no usable credentials, account allowance, or complete-JD entitlement were verified. [Adzuna overview](https://developer.adzuna.com/overview).

## 18. Application tracking

Statuses: Saved, Preparing, Ready, Applied, Assessment, Interview, Offer, Rejected, Withdrawn, and Closed. Keep saved-job state separate from actual application submission.

- Opening an application URL never marks Applied.
- Pin the exact resume artifact used, not merely the current master ID.
- Record company, job URL, requisition when known, application date, notes, follow-up date, and confirmation reference if available.
- Warn if an equivalent opening already has an application record.
- Permit manual status changes and preserve history.
- Store the full permitted JD snapshot or source/hash metadata according to retention rights, rather than only a short snippet.

Follow-ups remain in-app unless the user explicitly requests another notification channel. No automated recruiter messages or emails are included.

## 19. Autofill extension — later phase

### 19.1 First supported scope

Build a Chrome/Edge extension for a small, explicitly supported set of employer forms where assistance is permitted. Start with stable employer application forms after reviewing their actual structure and terms. Greenhouse/Lever listing APIs do not themselves authorize all third-party form automation.

Chrome content scripts provide the technical mechanism for interacting with pages with appropriate permissions. [Chrome documentation](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts)

### 19.2 Workflow

1. Pair the extension with the local CareerOS workspace using a short-lived code and revocable credential.
2. User opens the original application page and explicitly invokes assistance.
3. Identify the job and choose the intended ready resume artifact.
4. Read supported field labels/types and map to profile facts or previously approved answers.
5. Show a preview of proposed values and highlight unknowns.
6. Fill supported fields and verify the resulting values persisted through page validation.
7. Attach the generated PDF only where the browser/form adapter supports this; otherwise provide download and manual upload.
8. User reviews and submits.
9. Mark Applied only after reliable confirmation or explicit user action.

Use a generic semantic mapper plus tested site adapters. Do not send full pages, cookies, passwords, or unrelated form content to AI services. Share only the necessary context with the extension.

### 19.3 Fields and limits

- Basic facts: name, contact details, links, education, and explicit availability.
- Employer questions: draft answers grounded in the confirmed profile, for review.
- Work authorization, compensation, declarations, and demographic questions: use explicit stored choices or ask.
- CAPTCHAs, sign-in, unsupported widgets, and ambiguous questions remain manual.
- Keep a visible list of filled and unanswered fields.
- Scope extension permissions to supported sites or user-invoked active tabs; never request unrelated browser history.
- Enforce a strict, validated protocol between the extension and local backend; arbitrary web pages cannot invoke pairing or retrieve private artifacts.

Direct application APIs require employer/partner access where applicable. Greenhouse and Lever document credentials for application submission. Public GET endpoints do not provide those credentials. [Greenhouse](https://docs.greenhouse.io/job-board), [Lever](https://github.com/lever/postings-api).

## 20. Failure behavior

| Failure | Required behavior |
| --- | --- |
| Compiler/package unavailable | Show setup diagnostics; keep source; no fake PDF |
| Master fails baseline compilation | Cannot activate it for automatic tailoring |
| PDF and .tex disagree | Show comparison; require choosing the intended source revision |
| Skills region ambiguous | Require mapping; no whole-file rewrite |
| JD is truncated | Mark incomplete; request full description |
| Fewer than five missing skills | Return fewer; never fill slots artificially |
| Unconfirmed skill | Await confirmation; no automatic insertion |
| Five additions overflow | Remove lowest-priority additions and rebuild from master; report omissions |
| Model emits invalid terms | Reject output; bounded retry or manual review |
| Provider quota exhausted | Pause; preserve progress; no billable fallback |
| Connector blocked or unavailable | Show source health; no bypass or false empty-success state |
| Listing disappears | Mark closed only with suitable evidence; preserve application history |
| Worker crashes | Reclaim expired lease; idempotent retry |
| Master/preferences change mid-run | Complete against pinned revision or explicitly supersede task |
| Unsupported form | Download/copy assistance; manual completion |
| Computer offline | Show last refresh and resume bounded work when available |

## 21. Tests and acceptance gates

These changes affect generated career documents, identity resolution, durable automation, and external form interactions. Meaningful regression tests are required.

### Core tailoring

- Whole-resume concept matching catches aliases and project mentions.
- Required-vs-preferred ranking produces stable top-five candidates.
- No more than five concepts are inserted, and unconfirmed terms are excluded.
- Existing skills are not deleted or reordered.
- Source outside editable category values is byte-identical to the master.
- LaTeX special characters remain literal and compile correctly.
- Re-running a job does not duplicate skills or overwrite the master.
- Chat and worker use the same restrictions as the UI.

### Compilation and artifacts

- Actual imported master compiles in a clean pinned environment.
- Normal, long, zero-addition, Unicode, and special-character cases are covered.
- Timeout, invalid source, missing package, and inaccessible path tests fail cleanly.
- Page-count/overflow fallback produces a validated artifact or an explicit failure.
- Generated PDF includes inserted terms and preserves protected-section text.
- Visual comparison covers the master and representative dense skill additions.
- No returned artifact belongs to a different master/JD revision.

### Local workspace and migration

- Existing selected owner's records remain intact.
- Multiple owners cannot be silently merged.
- No active feature redirects to login or requires session_token.
- Parse, upload, exports, ATS, skills, suggestions, chat, and GitHub resolve the same owner.
- Browser origin/host checks and extension pairing protect local mutation routes.

### Discovery and worker

- Connector fixtures cover missing fields, expired jobs, pagination, and quotas.
- Distinct requisitions are not merged just because titles match.
- Source outages do not close the entire feed.
- Student batch/joining eligibility and unknown values are handled explicitly.
- Retry, lease recovery, cancellation, quota pause, and cache invalidation work.
- Repeated refreshes do not create duplicate jobs, applications, or PDFs.

### End-to-end release demonstration

Open CareerOS without login -> activate approved master -> set fresher preferences -> retrieve or import a complete JD -> inspect five or fewer missing skills -> confirm applicable terms -> build PDF -> verify only Skills source changed -> download -> open application -> manually mark Applied with exact artifact -> restart app and confirm history persists.

Extension acceptance is a later demonstration on real supported forms with user review and explicit submission confirmation.

## 22. Implementation phases and release order

| Phase | Work | Gate before moving on |
| --- | --- | --- |
| 0. Baseline | Back up data, inventory legacy callers, record current UI/API behavior | Recoverable data and agreed replacement boundaries |
| 1. Personal mode | Stable local owner, migrate active APIs, remove login UI/routes | No-login end-to-end access to existing records |
| 2. Master and compiler | Import/revisions, Skills mapping, compiler image, baseline preview | Actual master compiles and is explicitly activated |
| 3. New tailor | JD extraction, top-five policy, confirmations, deterministic patching, PDF validation | Only permitted Skills edits; truthful candidates; valid exports |
| 4. Legacy removal | Switch chat/UI/jobs contract; delete unreferenced tailor rules/endpoints/prompts | No alternate whole-resume tailoring path remains |
| 5. Preferences and jobs | Confirm profile, company directory, first connector, normalized feed, eligibility ranking | Useful deduplicated fresher jobs with full descriptions where needed |
| 6. Durable automation | Schedules, queue, quotas, retries, bounded automatic preparation | Refresh/preparation survives restarts without duplicate work |
| 7. Applications | Job-specific resume pinning, states, notes, submission evidence | Accurate persistent application history |
| 8. Autofill | Extension pairing, supported adapters, field preview and verification | Reliable assisted forms with user submission |

Release A is phases 0-4: personal no-login CareerOS with a reliable LaTeX skills-only tailor for pasted job descriptions.

Release B is phases 5-7: job discovery and automatic draft preparation attached to an application tracker.

Release C is phase 8: supported form assistance. Additional sources are introduced independently when their free-access and permission gates pass.

Avoid committing to calendar dates before the baseline compiler and source-access gates are exercised. These are the largest external uncertainties.

## 23. First concrete implementation milestone

The first complete slice should use Nayan's approved LaTeX source and one supplied JD. It must open without CareerOS login, show up to five genuinely missing JD skills, accept confirmations, edit only category values, compile a valid PDF locally, show the exact changes, and preserve both original and generated source.

Do not begin multi-source collection or extension work until this slice passes. It establishes the document behavior on which every later automation depends.

## 24. Decisions intentionally left configurable

- Which supplied LaTeX revision is the approved master.
- Whether the optional PDF matches that revision.
- Actual target titles, locations, batch eligibility, and joining date.
- Which owner to select if multiple existing accounts exist.
- Which model/provider has current no-cost allowance on the user's accounts.
- Which sources provide suitable permitted free access at implementation time.
- Whether automatic preparation starts enabled and its daily cap.
- Whether to include internships alongside fresher jobs.

None of these requires abandoning the plan. Implement the settings and onboarding surfaces, use conservative disabled/pending defaults for unconfirmed values, and resolve each before dependent work runs.
