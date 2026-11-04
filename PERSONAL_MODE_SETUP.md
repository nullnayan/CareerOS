# CareerOS personal mode — first implementation

The personal workflow includes the no-login local workspace, master LaTeX revisions, skills-only tailoring, isolated PDF compilation, fresher discovery, durable scheduled preparation, applications, and a paired browser extension. See AUTOMATION_SETUP.md for complete startup commands and setup, including the separate worker terminal.

## Start the app

1. Start Docker Desktop and the project's PostgreSQL/Qdrant services.
2. From `backend`, activate `venv` and run `python -m alembic upgrade head`.
3. Build the compiler once: `docker build -t careeros-latex:2026-10-compat ./compiler`.
4. From `backend`, run `b.bat`. The new default API port is **8010**, because another application already occupies 8000 on this computer.
5. From `frontend`, run `f.bat`. Open `http://127.0.0.1:3000`.

The backend may also be started with `python -m uvicorn main:app --host 127.0.0.1 --port 8010`. The frontend supports `NEXT_PUBLIC_CAREEROS_API_BASE` for an alternate local API. This is a build-time public URL setting, not a secret. No environment files were read or edited directly during implementation.

Bind services to loopback. This personal mode is not a public hosting configuration.

## First use

- A fresh local workspace was created at your request. Four older accounts and their data were preserved. On another installation, Settings can select an existing owner or create a fresh workspace.
- Open Master Resume and upload a UTF-8 `.tex` file, optionally with the corresponding PDF.
- Compile the baseline, review it, check the review box, and activate it.
- Open Tailor, paste a full JD, and optionally label the company/role.
- The local dictionary works without API calls. The optional AI checkbox uses the existing Groq route; it does not switch to paid providers.
- Review up to five JD skills absent from the whole master resume. Confirm only skills you know and choose their categories.
- Generate the PDF. Download the PDF and `.tex` and inspect the category-level changes.

Selecting a skill confirms it for future tailoring. A prepared run is immutable; start a new analysis to make a different selection. Existing resume versions remain stored. Legacy whole-resume tailoring and its chat behavior have been retired.

## Existing LaTeX source needs two onboarding repairs

The original `NAYAN_KUMAR_RESUME.tex` is unchanged. Actual compilation found:

1. A missing outer list item in Certifications, causing a fatal compilation error.
2. A long education row that overflows its alignment.

A separate proposed source is saved at `scratch/NAYAN_KUMAR_RESUME_compile_candidate.tex`. It adds the required outer list item and wraps the education description within its column. It compiles to one page without overflow in the new compiler. A compiled draft was placed in your fresh workspace for review. This candidate has **not** been made your active master. Review it against your intended PDF before using it.

The skill patcher never repairs these regions during tailoring. Onboarding repairs and later skill additions are separate operations.

## Data and backups

- The additive migration is `301030_personal_latex`.
- New tables: workspace settings, master revisions, explicit skill confirmations, and tailoring runs.
- Original source is retained in PostgreSQL and on disk. PDF artifacts live under `backend/data/latex`.
- Backups made before migration: `.implementation-backups/before-personal-mode.zip`, `.implementation-backups/careeros.db`, and `.implementation-backups/careeros-postgres.sql`.
- Account and old session tables are retained for recovery; password/OTP routes are no longer mounted.
- GitHub connection states are now validated, expire after ten minutes, and can be consumed only once.

## Validation

The new tests cover source preservation, aliases, duplicate prevention, five-skill limits, owner selection, retired routes, host/origin guards, and real PDF generation. Existing builder and ATS tests were updated to use isolated data and the actual bare ATS endpoint paths.

Run from `backend`:

`python -m pytest tests/test_personal_tailoring.py tests/test_builder_endpoints.py tests/test_ats_dual_mode.py ats/eval/test_v3.py -q`

For Docker compilation coverage, set `CAREEROS_TEST_LATEX=1` in the command's environment. Browser verification is available in `backend/scratch/verify_personal_ui.py`; it redirects only its own browser to a disposable database on port 8011. It does not choose an owner or add skills in the real workspace.

The frontend builds without Google Fonts access, using local system typography. No provider credentials, paid API requests, or external application submissions were needed for validation.
