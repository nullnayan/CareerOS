# CareerOS — Resume Builder: Audit + Implementation Plan

**Audience:** an AI coding agent (Gemini 3.1 Pro in Antigravity) picking up this repo.
**Date of audit:** 2026-08-06
**Repo root:** `careeros_scaffold/careeros`
**Reference product:** Reactive Resume (rxresu.me) 3-column methodology + Resume.io template gallery UX.

---

## 0. How to use this document

Work **top to bottom**. Phase 0 is non-negotiable — the app currently *destroys user data* and *cannot produce a production build*. Do not start Phase 3 (AI) before Phase 1 (data contract) lands, because the AI round-trip writes back into the same JSON shape that is currently inconsistent.

Every task below has: **files**, **what to change**, **acceptance criteria**. Verify each acceptance criterion by actually running the app, not by reading the diff.

### Ground rules for this repo
1. **Never read, write, or print the contents of `backend/.env` or `.env.local`.** If a new variable is needed, print the variable name + instructions and let the human paste the value.
2. `ResumeVersion.source` is constrained by a DB CheckConstraint to `'uploaded' | 'builder' | 'tailored' | 'ats_check' | 'tailor_input'` (`backend/db/models.py:108`). Any new source value requires an Alembic migration that rewrites the constraint.
3. Dev services bind to `127.0.0.1:8000` (FastAPI) and `127.0.0.1:3000` (Next.js) — Windows IPv6 resolution breaks `localhost` binding.
4. Schema changes go through Alembic (`backend/db/migrations/versions/`). Never hand-edit the SQLite/Postgres file.
5. Backend routers: `resumes.py` has prefix `/resumes`, `tailor.py` has `/tailor`, **`ats.py` has NO prefix** — its routes live at bare `/analyze`, `/analyze-text`, `/improve/propose`, `/improve/apply`, `/improve-bullet`. Do not "fix" this in isolation; the frontend `lib/api.ts` already depends on the bare paths.

---

## 1. What is actually built and verified working

I read the code rather than trusting the handoff notes. The following claims from the previous session **check out**:

| Claim | Status | Evidence |
|---|---|---|
| 3-column builder layout | ✅ Real | `frontend/app/builder/page.tsx` (1277 lines) — resizable `Panel`/`PanelGroup`, left data entry, centre iframe preview, right design/layout tabs |
| Playwright HTML→PDF engine | ✅ Real | `backend/services/pdf_fitter.py:814` `_render_pdf_playwright()`, called from `build_fitted_pdf()` at `:841`; `playwright 1.61.0` present in `backend/venv` |
| 6 Jinja2 templates | ✅ Real | `backend/services/templates_html/{classic,modern_tech,minimal,professional,ats_safe,academic}.html` + `base.html` |
| Template gallery with thumbnails | ✅ Real | `frontend/public/templates/*.jpg` — all 6 present |
| Design tokens as CSS variables | ⚠️ Partial | `base.html:10-17` injects 8 of 10 tokens. `background_color` and `sidebar_width` are **accepted by the UI but never used**; `page_format` is ignored (see BUG-08) |
| Base64 profile photos | ⚠️ Works, wrong architecture | `POST /resumes/upload-avatar` (`resumes.py:883`) returns a data URI that is then stored inside `structured_json` (see BUG-09) |
| Projects / Languages / Skills render | ⚠️ 5 of 6 templates | `modern_tech.html:116` breaks on Languages (see BUG-05) |
| `hidden: true` toggles sections | ⚠️ Works by accident | Filtering happens client-side in `convertToStructuredJson`; the Jinja `is_hidden` filter is dead code on lists (see BUG-06) |

**Backend AI/ATS surface already exists and is unused by the builder** — this is good news for Phase 3:
- `POST /analyze` — baseline + JD-targeted ATS scoring, persists `Suggestion` rows (`backend/api/ats.py:36`)
- `POST /improve/propose` → `POST /improve/apply` — propose-then-accept bullet rewrites (`ats.py:205`, `:300`)
- `POST /improve-bullet` — single bullet rewrite (`ats.py:495`)
- `POST /tailor/analyze` → `POST /tailor/apply` (`backend/api/tailor.py:56`, `:101`)
- Qdrant vector store initialised on startup (`backend/main.py:44`)
- Typed frontend clients for all of the above already exist in `frontend/app/lib/api.ts:215-296, 485, 633-653`

---

## 2. Bug register — what is wrong with the "completed" work

Ordered by severity. **BUG-01 through BUG-04 are Phase 0 blockers.**

---

### BUG-01 — 🔴 CRITICAL: The builder silently wipes saved resumes

**File:** `frontend/app/builder/page.tsx:410-416, 512-516`

`resumeId` is seeded from the `?id=` query param, but **there is no load-on-mount effect anywhere in the file**. Confirmed: the only three `useEffect` calls are the keyboard handler (`:467`), preview debounce (`:492`), and autosave debounce (`:512`).

Consequence chain:
1. User opens `/builder?id=<existing>`.
2. `data` is `DEFAULT_DATA` (empty).
3. The autosave effect runs **on mount** (deps `[data, templateId]` are set on first render).
4. 1500 ms later `builderSave()` fires with `resume_id: <existing>` and empty `structured_json`.
5. `builder_save` (`backend/api/resumes.py:838`) does an unconditional overwrite: `resume.structured_json = req.structured_json`.
6. **The user's resume is now blank, in the database.**

Same effect, second symptom: visiting plain `/builder` (which is what `TopBar.tsx:20` links to) creates a **new empty `ResumeVersion` row on every single page visit**, because autosave-on-mount with `resumeId === null` hits the create branch.

**Fix:**
- Add a load-on-mount effect: if `resumeIdParam` exists, `await getResume(resumeIdParam)` and hydrate `data`, `design`, `templateId`, `resumeName` from `structured_json` / `design_json` / `builder_template_id` **before** enabling autosave.
- Add a `hydratedRef` / `dirtyRef` guard so autosave is a no-op until (a) hydration finished and (b) the user has actually made an edit. Gate on a real user-edit signal from `updateData`, not on `data` identity.
- Make the create branch idempotent: hold an in-flight promise in a ref so two concurrent first-saves cannot both POST with `resume_id: null` and create duplicate rows.

**Acceptance:** Open a saved builder resume, wait 5 s, refresh — data intact. Visit `/builder` fresh 3 times without typing → `GET /resumes/` row count unchanged.

---

### BUG-02 — 🔴 CRITICAL: There is no way to reopen a saved resume

**Files:** `frontend/app/components/TopBar.tsx:20`, `frontend/app/resume/page.tsx`, `frontend/app/tailor/page.tsx:435`

Nothing in the app navigates to `/builder?id=…`. The nav link is a bare `/builder`. `resume/page.tsx` lists resumes but offers no "Edit in builder" action. So "cloud saves" are **write-only**: data goes in and can never be loaded back through the UI.

**Fix:** Add an "Open in Builder" action to each `source === 'builder'` row (and ideally `'uploaded'` too, so a parsed resume can be edited) in `frontend/app/resume/page.tsx`, routing to `/builder?id=<id>`. Add a "My Resumes" dropdown to the builder header.

**Acceptance:** Create a resume in the builder → navigate away → reopen from the resume list → all fields, design and template restored.

---

### BUG-03 — 🔴 CRITICAL: `npm run build` fails (TypeScript error)

**File:** `frontend/app/builder/page.tsx:642`

```
error TS2322: Property 'autoSaveId' does not exist on type ... Did you mean 'autoSave'?
```

`react-resizable-panels@^4.12.2` renamed the prop. Next.js typechecks during `next build`, so **the app cannot be built for production at all right now**. Only `next dev` works.

**Fix:** `<PanelGroup autoSave="builder-panels" orientation="horizontal">`.

**Acceptance:** `cd frontend && npx tsc --noEmit` exits clean; `npm run build` succeeds.

---

### BUG-04 — 🔴 CRITICAL: `pip install -r requirements.txt` is broken, and Playwright is not declared

**File:** `backend/requirements.txt`

The last line is corrupted — UTF-16LE bytes were appended to a UTF-8 file. Hexdump of the tail:
```
6a00 6900 6e00 6a00 6100 3200 3d00 3d00 3300 2e00 3100 2e00 3600 0d00 0a00
 j    i    n    j    a    2    =    =    3    .    1    .    6   \r   \n
```
`pip` sees `j\x00i\x00n\x00j\x00a\x002\x00...` and fails or installs garbage. A clean-machine setup is impossible.

Separately, **`playwright` is not in `requirements.txt` at all** — it only exists in the pre-existing `backend/venv`. There is also no documented `playwright install chromium` step, which is a *separate* ~150 MB browser download that pip does not perform.

**Fix:**
1. Rewrite `requirements.txt` as clean UTF-8 (no BOM, LF endings) with `jinja2==3.1.6` as a normal line.
2. Add `playwright==1.61.0`.
3. Add to `README.md` after the pip step:
   ```bash
   python -m playwright install chromium
   ```
4. Verify with `pip install -r requirements.txt --dry-run` in a scratch venv.

**Acceptance:** Fresh venv, `pip install -r requirements.txt && python -m playwright install chromium` → `uvicorn main:app` starts and `GET /resumes/<id>/pdf` returns a Chromium-rendered PDF.

---

### BUG-05 — 🟠 HIGH: Data contract mismatch — Languages render blank in Modern Tech

**Files:** `frontend/app/builder/page.tsx:524-551`, `backend/services/templates_html/modern_tech.html:113-127`

`convertToStructuredJson` flattens languages to **strings**:
```ts
languages: d.languages.filter(...).map(l => l.fluency ? `${l.language} (${l.fluency})` : l.language)
```
Four templates consume that correctly with `{{ data.languages | join(' • ') }}`. But `modern_tech.html:116-124` iterates and does `{{ lang.language }}` / `{{ lang.fluency }}` — attribute access on a `str` yields Jinja `Undefined`, which renders as empty string. Result: **Modern Tech shows a "Languages" heading followed by blank rows.** `academic.html` doesn't render languages at all.

This is a symptom, not the disease. The disease is that **no canonical resume JSON schema is written down anywhere**, so the frontend serialiser and six templates drifted independently.

**Fix (structural — do this via Phase 1, not as a local patch):**
1. Make `languages` a list of objects in the canonical schema: `{id, language, fluency, level, hidden}` (Task 1.1). Stop flattening to strings in the frontend (Task 1.2).
2. Update the four `join`-based templates (`classic.html:163`, `minimal.html:161`, `professional.html:148`, `ats_safe.html:143`) to iterate objects instead:
   `{% for lang in data.languages %}{% if not lang.hidden %}{{ lang.language }}{% if lang.fluency %} ({{ lang.fluency }}){% endif %}{% endif %}{% endfor %}`
3. `modern_tech.html:116-124` then works unchanged — it already expects objects.
4. Add a Languages block to `academic.html`, which renders none today.
5. Extract this into `templates_html/partials/languages.html` and `{% include %}` it in all six, so the shape is defined once (Task 1.4).

**Quick-patch alternative if you must fix it before Phase 1:** change `modern_tech.html:116-124` to `{{ data.languages | join('  •  ') }}` to match the other five. This makes the bug disappear but leaves the underlying contract broken — only do it if Phase 1 is more than a few days out.

**Acceptance:** Add 3 languages, cycle through all 6 templates — each shows all 3 with fluency.

---

### BUG-06 — 🟠 HIGH: 7 left-panel sections collect data that can never appear on the resume

**File:** `frontend/app/builder/page.tsx:524-551`

`LEFT_SECTIONS` (`:154`) exposes 16 sections. `convertToStructuredJson` emits only 10 keys. Fields silently dropped on their way to the renderer:

| Dropped | Detail |
|---|---|
| `publications` | entire section — typed (`PubItem`), UI'd, never serialised |
| `volunteer` | entire section |
| `interests` | entire section |
| `references` | entire section |
| `custom_sections` | entire section |
| `profiles` | only `url` survives; `network` + `username` discarded → templates can't label a link "GitHub" |
| `contact.headline` | dropped — no template renders a professional headline |
| `contact.website` | dropped |
| `contact.custom_fields` | dropped |
| `education.description` | dropped |
| `skills.level`, `skills.keywords` | dropped (skills flattened to bare names) |
| `awards.date`, `awards.description` | dropped |
| `certifications.issuer/date/url` | dropped (flattened to title only) |

A user can spend twenty minutes filling in Publications and Volunteer work and see **nothing** in the preview or the PDF. This is the single largest gap between what the builder appears to do and what it does.

Related: because `convertToStructuredJson` already applies `.filter(e => !e.hidden)`, the Jinja `is_hidden` filter (`backend/services/html_templates.py:11`) never sees a hidden item. Worse, expressions like `{% if data.experience and not data.experience | is_hidden %}` call `is_hidden` on a **list**, which returns `False` unconditionally — dead code that reads as if section-level hiding works. There is no section-level hide at all.

**Fix (this is the main body of Phase 1 — Tasks 1.2, 1.3, 1.4):**
1. **Delete `convertToStructuredJson` entirely** (`builder/page.tsx:524-551`). Once builder state *is* the canonical schema (Task 1.1), serialisation is `JSON.stringify(data)` and nothing can be dropped in transit. This one deletion fixes every row in the table above.
2. Keep the renames the templates already depend on by choosing them *in the schema itself* rather than in a translation layer — pick one name per field (`position` **or** `title`, `grade` **or** `cgpa_or_percentage`) and use it in the TS types, the Pydantic model, and all six templates. Whichever you pick, `resume_migrations.py` (Task 1.5) maps the legacy name on read.
3. **Send hidden items to the server** and filter in Jinja instead (Task 1.3). Rewrite the `is_hidden` filter to be item-level only, add a `section_visible(key)` helper backed by `section_visibility`, and delete every meaningless `data.<list> | is_hidden` check from the six templates.
4. **Build the 6 missing section partials** — `publications`, `volunteer`, `interests`, `references`, `custom_sections`, plus a `profiles` partial that uses `network`/`username` to label links. Put them in `templates_html/partials/` and include them from the `section_order` loop (Task 2.1), so adding a section is one new file rather than six template edits.
5. **Surface the newly-available fields:** `contact.headline` under the name in the header, `contact.website` + `custom_fields` in the contact line, `education.description`, `awards.date`/`description`, `certifications.issuer`/`date`/`url`. Decide explicitly whether `skills.level` renders as dots/bars per template — ATS Safe should ignore it.
6. **Delete any section you decide not to render** from `LEFT_SECTIONS` (`:154`). A form that collects data which never appears is worse than no form.

**Acceptance:** Every section in `LEFT_SECTIONS` round-trips to at least one template. Per-section hide toggle works (a hidden section keeps its data but disappears from the render).

---

### BUG-07 — 🟠 HIGH: The "Layout / Section Order" panel is non-functional decoration

**Files:** `frontend/app/builder/page.tsx:1078-1097`, `backend/services/html_templates.py:59`, all 6 templates

Three independent failures stacked:
1. **Frontend:** the panel renders static `<div>`s with a `GripVertical` icon. No drag handlers, no `Reorder` usage (framer-motion's `Reorder` *is* imported at `:6` but unused here), no state.
2. **Transport:** `fetchPreview` (`:485`) and `autoSave` (`:503`) both pass `undefined` for `sectionOrder`.
3. **Renderer:** `build_html` accepts `section_order` and passes it into the Jinja context (`html_templates.py:59`), but **grep confirms not one of the 6 templates references `section_order`.** Every template hardcodes its section sequence.

So even a correct drag-and-drop implementation would change nothing. Also note there is **no DB column for section order** — `ResumeVersion` has `design_json` and `builder_template_id` but nothing for ordering, and `builder_save` ignores the `section_order` field it accepts in its request model.

**Fix — all four layers must change together; fixing any one alone yields no visible behaviour change.** Full detail in Phase 2, Task 2.1. In summary:
1. **Schema:** add `section_order: list[str]` and `section_visibility: dict[str, bool]` to the canonical JSON (Task 1.1) — they ride inside `structured_json`, so no migration.
2. **Frontend:** replace the static `<div>`s at `builder/page.tsx:1078-1097` with real drag-and-drop using `@dnd-kit/sortable` (already a dependency) or framer-motion's `Reorder` (already imported at `:6`), writing to `data.section_order`.
3. **Transport:** pass `section_order` in `fetchPreview` (`:485`) and `autoSave` (`:503`) — both currently hand `undefined` to functions that already accept the argument.
4. **Templates:** replace each template's hardcoded section sequence with a driven loop over `section_order`, including per-section partials. Two-column templates keep two lists (`sidebar_order`, `main_order`).

**Acceptance:** Drag Education above Experience → preview reorders within ~1 s → reload the page → order persists. Works in all 6 templates.

---

### BUG-08 — 🟠 HIGH: Export ignores page format, and silently falls back to a different-looking engine

**File:** `backend/services/pdf_fitter.py:814-838, 884-890`; `backend/services/templates_html/base.html:26-49`

Three distinct problems in the render path:

**(a) A4 is impossible.** The right panel offers `Letter | A4` (`builder/page.tsx:1058`), but:
- `base.html:27` hardcodes `@page { size: letter; }`
- `base.html:46-48` hardcodes `width: 816px; height: 1056px` (US Letter at 96 dpi)
- `_render_pdf_playwright(html, page_format="Letter")` is called with **no argument** at `:885`, so the default always wins

Selecting A4 changes nothing. On an A4 print it produces a mis-scaled page.

**(b) Overflow is silently truncated.** `base.html:49` sets `overflow: hidden` on a fixed-height body. Content past one page is **cut off with no warning** — the Playwright path performs none of the shrink-to-fit logic the PyMuPDF path has. A 2-page CV loses page 2 invisibly.

**(c) A rendering failure silently swaps engines.** `build_fitted_pdf` wraps the whole Playwright path in `try/except` and on *any* exception (`:888`) falls through to the legacy PyMuPDF pipeline, which uses the **old non-Jinja templates**. The user gets a PDF that looks nothing like the preview they were just looking at, with only a `logger.warning` to show for it. Most likely trigger in practice: Chromium not installed (BUG-04).

**Fix:**
- Thread `design.page_format` → `_render_pdf_playwright(html, page_format=...)`, and make `@page size` / body dimensions template variables (`--page-w/--page-h`, A4 = 794×1123 px @96dpi).
- Decide multi-page policy explicitly. Recommendation: allow real page breaks (drop `overflow: hidden`, add `page-break-inside: avoid` on `.entry`) and surface a page count in the UI, rather than silently truncating.
- Either delete the PyMuPDF fallback or return HTTP 503 with a clear "PDF engine unavailable" message. A silent engine swap is worse than an error.

**Acceptance:** A4 export measures 210×297 mm. A 3-page-worth resume exports 3 pages with no mid-entry splits. Killing Chromium produces a visible error, not a different-looking document.

---

### BUG-09 — 🟠 HIGH: Base64 photos bloat every request and the database

**Files:** `backend/api/resumes.py:883-903`, `frontend/app/builder/page.tsx:478-490`

`upload-avatar` accepts up to 3 MB and returns a base64 data URI — which is ~4 MB of text after encoding, and is **not stored server-side**. The frontend parks it in `data.photo.url`, i.e. inside `structured_json`. Therefore:
- Every preview refresh (400 ms debounce, fires on **every keystroke**) POSTs ~4 MB of base64 to `/resumes/preview-html`.
- Every autosave (1500 ms debounce) POSTs the same ~4 MB and writes it into the `structured_json` JSON column.
- Typing a summary paragraph can push tens of MB over the wire and rewrite the row dozens of times.

**Fix:** Persist the upload to `backend/uploads/avatars/<user_id>/<uuid>.<ext>` and return a URL path. Store the *path* in `structured_json`. For the PDF path, inline it to base64 **only at render time inside `build_html`** (Chromium needs local access; a `file://` URL or a data URI generated server-side both work). Reduce the size cap to 1 MB and re-encode to a max 512×512 JPEG/WebP on upload.

**Acceptance:** With a photo set, the `/resumes/preview-html` request body is < 100 KB. Photo appears in preview and PDF.

---

### BUG-10 — 🟠 HIGH: IDOR — any user can download any user's resume

**Files:** `backend/api/resumes.py:557, 580, 609, 779`

```python
@router.get("/{resume_id}/pdf")
def get_resume_pdf(resume_id: str, template_id=None, font_id=None, db=Depends(get_db)):
```
**No `current_user` dependency, and no ownership check.** Same for `/{resume_id}/docx` (`:580`), `/{resume_id}/original` (`:609`) and `POST /{resume_id}/annotate` (`:779`). Anyone who can guess or obtain a resume UUID can fetch another user's full resume PDF. Compare `builder_save` (`:838`) and `/analyze` (`ats.py:37`), which *do* filter on `current_user.id` — so this is an oversight, not a design decision.

Related dead code: `getResumePdfUrl` (`lib/api.ts:725-732`) appends `?token=<session_token>` to the URL, but `get_current_user` (`backend/api/auth.py:106-113`) only reads the `session_id` **cookie** or an `Authorization: Bearer` **header** — never a query param. So once auth is added, `window.open(url)` will 401 unless either the cookie rides along on the top-level navigation or query-param auth is explicitly supported.

**Fix:** Add `current_user=Depends(get_current_user)` plus `ResumeVersion.user_id == current_user.id` to all four endpoints. Then make download work: either (a) teach `get_current_user` to accept a short-lived `?token=`, or (b) preferred — `fetch()` the PDF with credentials, `URL.createObjectURL(blob)`, open that. (b) avoids putting session tokens in browser history and server logs.

**Acceptance:** Requesting another user's resume ID returns 404. Download button still works.

---

### BUG-11 — 🟡 MEDIUM: Design changes never autosave → downloaded PDF ≠ preview

**File:** `frontend/app/builder/page.tsx:512-516`

```ts
useEffect(() => {
  saveDebounceRef.current = setTimeout(() => autoSave(data, templateId, resumeId), 1500);
  return () => clearTimeout(saveDebounceRef.current);
}, [data, templateId]);          // ← design and resumeId missing
```

`autoSave` closes over `design` and `resumeName`, and is recreated when they change (`:510`), but the effect **doesn't list them as deps**, so it never re-fires. Changing only a colour, font or margin is not persisted until some unrelated `data` edit happens to flush it.

Now combine with `handleDownload` (`:555-559`): it opens `GET /resumes/{id}/pdf`, and that endpoint reads `resume.design_json` **from the database** (`resumes.py:567`). So the download reflects the last-persisted design, not what's on screen. **User picks a colour, hits Download, gets the old colour.**

Also at `:555`: if `resumeId` is null, `handleDownload` saves and `return`s — the download never happens and the user gets no feedback. And `getResumePdfUrl(resumeId, templateId)` never passes design, so even a correct DB state depends on the save having landed first.

**Fix:** Add `design`, `resumeName`, `resumeId` to the effect deps. Change download to `POST` the live `{structured_json, design, template_id, section_order, page_format}` and stream the PDF back — the export must not depend on save timing. Await the save then continue when `resumeId` is null.

**Acceptance:** Change primary colour → immediately Download → PDF uses the new colour. Status chip shows "Saved" after a colour-only change.

---

### BUG-12 — 🟡 MEDIUM: `builder_save` nulls out design and drops section order / font

**File:** `backend/api/resumes.py:838-880`

The update branch:
```python
resume.structured_json = req.structured_json
resume.design_json     = req.design_json      # ← None wipes stored design
resume.builder_template_id = req.template_id
```
- `design_json` is unconditionally assigned, so any caller omitting it **erases** the saved design.
- `original_filename` is accepted in the request model but never applied on update → **renaming a resume in the header does nothing.**
- `section_order` and `font_id` are accepted and then silently discarded — there are no columns for them.

**Fix** — replace the update branch with partial-update semantics, so an omitted field means "leave unchanged" rather than "set to null":

```python
if req.structured_json is not None:
    resume.structured_json = req.structured_json
if req.design_json is not None:
    resume.design_json = req.design_json
if req.template_id is not None:
    resume.builder_template_id = req.template_id
if req.original_filename:
    resume.original_filename = req.original_filename
db.commit()
```

For `section_order` and `font_id`, pick one of:
- **(a) Preferred, no migration:** carry both *inside* `structured_json` (`section_order`) and `design_json` (`font_id`) per the Task 1.1 schema. Then the two lines above already persist them, and you can drop the unused top-level fields from `BuilderSaveRequest`.
- **(b) Explicit columns:** add an Alembic revision (`backend/db/migrations/versions/`) adding `section_order_json JSON NULL` and `font_id TEXT NULL` to `resume_versions`, then assign them in the same guarded style. Only do this if you want to query/index by them.

Do **not** leave fields in the request model that the handler ignores — that is what produced this bug.

**Acceptance:** Rename a resume, refresh, name persists. Saving without a design payload doesn't clear the design. Section order and font survive a reload.

---

### BUG-13 — 🟡 MEDIUM: Temp PDF/DOCX files are never deleted

**Files:** `backend/api/resumes.py:557-578, 580-607, 745-777`; `backend/services/pdf_fitter.py:820-822`

Every export creates a `NamedTemporaryFile(delete=False)` and hands the path to `FileResponse`. Nothing ever unlinks it. With autosave-driven preview traffic this grows without bound in the system temp dir. (`backend/` already shows the pattern's residue: `dummy.pdf`, `test_font.pdf`, `tailored_resume.pdf`, `test_sans.pdf`, `test_serif.pdf` committed at the repo root.)

**Fix:** `FileResponse(path, background=BackgroundTask(os.unlink, path))`.

---

### BUG-14 — 🟡 MEDIUM: One Chromium process launched per PDF, and a sync-API deadlock risk

**File:** `backend/services/pdf_fitter.py:819-836`

`_render_pdf_playwright` calls `sync_playwright()` → `p.chromium.launch()` → `browser.close()` on every single request. That's roughly 0.5–1.5 s of pure browser startup per export.

The latent bug: `sync_playwright()` raises `Error: It looks like you are using Playwright Sync API inside the asyncio loop` if it runs on a thread with a live event loop. Today's callers (`get_resume_pdf`, `run_phase8_pdf`) are `def`, so FastAPI runs them in a worker thread and it happens to work. **The moment someone marks an export endpoint `async def`** — and note `preview-html` at `:806` is already `async def` — this breaks. It will then be swallowed by the `except` at `:888` and silently degrade to the PyMuPDF renderer (BUG-08c), making it a confusing bug to trace.

**Fix:** Switch to `playwright.async_api` with a module-level browser singleton launched in a FastAPI lifespan handler, reusing one browser across requests and creating a fresh `page` (or `new_context()`) per render. Add a lock or a small page pool.

**Acceptance:** Second and subsequent PDF exports complete in < 400 ms. Works from both `def` and `async def` endpoints.

---

### BUG-15 — 🟡 MEDIUM: PyMuPDF link injection corrupts Chromium output

**File:** `backend/services/pdf_fitter.py:673-721`, called at `:886`

`_inject_links_to_pdf` was written for the PyMuPDF pipeline, which produces no real hyperlinks — it text-searches the PDF for the email and for labels like `"GitHub"` and staples URI link rects over the hits. But **Chromium already emits proper `<a href>` hyperlinks**, so on the Playwright path this re-opens the freshly written PDF and overlays *duplicate, coordinate-guessed* link rectangles on top of correct ones. It also text-searches for bare domains, so a domain mentioned in a bullet becomes an unintended link.

**Fix:** Skip `_inject_links_to_pdf` entirely when the Playwright path succeeds. Ensure the templates wrap contact details in real `<a>` tags (`mailto:`, `tel:`, profile URLs) so Chromium generates them natively.

---

### BUG-16 — 🟢 LOW: Undo/redo is unreliable

**File:** `frontend/app/builder/page.tsx:433-464`

`updateData` calls `setUndoStack` and `setRedoStack` **from inside the `setData` updater function**. React updaters must be pure; under StrictMode (and under concurrent re-renders) they are invoked more than once, pushing duplicate history entries. The 500 ms `lastUndoTimeRef` coalescing window partially masks it. `undo`/`redo` also read `data` from a closure while mutating stacks in a callback, so rapid Ctrl+Z can drop or duplicate a step.

**Fix:** Move history into a `useReducer` where every action produces `{present, past, future}` atomically, or push to the stack from the event handler *before* calling `setData`.

---

### BUG-17 — 🟢 LOW: Config and hygiene inconsistencies

| Issue | Location | Detail |
|---|---|---|
| Postgres port mismatch | `docker-compose.yml:11` vs `backend/.env.example:4` | Compose publishes `5455:5432`; `.env.example` says `…@localhost:5432/careeros`. A fresh clone following the README cannot connect. Fix `.env.example` to `5455`. |
| SQLite/Postgres ambiguity | `backend/careeros.db` exists | A SQLite file is committed while `db/session.py` defaults to Postgres. Decide one for dev, document it, and gitignore the other. Note SQLite silently accepts things Postgres will reject. |
| Duplicate tailor routes | `resumes.py:689` `POST /resumes/tailor` vs `tailor.py:56` `POST /tailor/analyze` | Two overlapping tailoring surfaces. Pick one for the builder's Analyze button and mark the other deprecated. |
| Dead `token` query param | `lib/api.ts:729-731` | See BUG-10. |
| Debug artefacts committed | `backend/` root | `dummy.pdf`, `test_*.pdf`, `temp_resume.json`, `latest_resume_json*.txt`, `sample_resume.txt`, `validation_report.json`, `b.bat`, `debug_parser.py`, plus 12 files in `backend/uploads/`. Add to `.gitignore` and remove from the working tree. |
| `preview-html` blocks the loop | `resumes.py:806` | `async def` doing synchronous Jinja rendering. Either make it `def` (threadpool) or `await run_in_threadpool(...)`. |

**Fix:** each row's fix is inline above; execute them together as Phase 4, Task 4.3. The `.env.example` port and the SQLite/Postgres decision are worth pulling forward into Phase 0 if anyone else needs to run this repo from a clean clone.

---

## 3. Root cause: there is no canonical resume schema

Nine of the seventeen bugs above (05, 06, 07, 09, 12, and the Languages/skills/photo mismatches) trace to one absence: **the resume JSON shape is defined implicitly, in three places that disagree.**

1. `ResumeData` TS interfaces — `builder/page.tsx:27-68` (rich, 16 sections)
2. `convertToStructuredJson` — `builder/page.tsx:524-551` (lossy, 10 keys, renames `position`→`title`, `grade`→`cgpa_or_percentage`, flattens objects to strings)
3. Six Jinja templates, each assuming a slightly different shape (`join`-able strings vs. dicts with attributes)

Plus a fourth consumer: the resume *parser* (`backend/resume_parser/`) writes into the same `structured_json` column for `source='uploaded'` rows, with its own conventions.

**Fix this first (Phase 1) or every later phase will re-introduce the same class of bug.** The AI tailoring work in Phase 3 reads and writes this exact JSON — building it on an undefined contract guarantees rework.

---

## 4. Implementation plan

### 4.0 Bug → task traceability

Every bug in section 2 is assigned to a task below. Use this table as the checklist — a phase is not done until each of its bugs passes its own acceptance criterion. Nothing in section 2 is left unassigned.

| Bug | Severity | Fixed by | Phase |
|---|---|---|---|
| BUG-01 wipes saved resumes | 🔴 | Task 0.3 | 0 |
| BUG-02 can't reopen a save | 🔴 | Task 0.4 | 0 |
| BUG-03 build fails | 🔴 | Task 0.1 | 0 |
| BUG-04 pip install fails | 🔴 | Task 0.2 | 0 |
| BUG-05 languages blank | 🟠 | Tasks 1.1, 1.4 | 1 |
| BUG-06 7 dead sections | 🟠 | Tasks 1.2, 1.3, 1.4 | 1 |
| BUG-07 fake section order | 🟠 | Task 2.1 | 2 |
| BUG-08 A4 / truncation / silent fallback | 🟠 | Task 2.2 | 2 |
| BUG-09 base64 photo bloat | 🟠 | Task 2.4 | 2 |
| BUG-10 IDOR | 🟠 | Task 0.5 | 0 |
| BUG-11 design not autosaved, PDF ≠ preview | 🟡 | Tasks 0.3 (effect deps), 2.3 (export path) | 0 + 2 |
| BUG-12 save nulls design / drops fields | 🟡 | Task 0.6 | 0 |
| BUG-13 temp files leak | 🟡 | Task 0.6 | 0 |
| BUG-14 Chromium per request | 🟡 | Task 2.5 | 2 |
| BUG-15 link injection corrupts PDF | 🟡 | Task 2.5 | 2 |
| BUG-16 undo/redo unreliable | 🟢 | Task 2.8 | 2 |
| BUG-17 config + hygiene | 🟢 | Task 4.3 | 4 |

Phase 0 clears all four 🔴 blockers plus BUG-10, BUG-12, BUG-13 and the autosave half of BUG-11 — 8 of 17 in roughly half a day.

---

### Phase 0 — Unblock (do first, ~half a day)

| # | Task | Files | Acceptance |
|---|---|---|---|
| 0.1 | Fix BUG-03 `autoSaveId` → `autoSave` | `builder/page.tsx:642` | `npx tsc --noEmit` clean; `npm run build` succeeds |
| 0.2 | Fix BUG-04 requirements encoding + add `playwright==1.61.0` + document `playwright install chromium` | `backend/requirements.txt`, `README.md` | Fresh venv installs and renders a PDF |
| 0.3 | Fix BUG-01 load-on-mount + autosave guard + create-once idempotency | `builder/page.tsx` | Reopening a resume preserves data; 3 fresh `/builder` visits create 0 rows |
| 0.4 | Fix BUG-02 "Open in Builder" entry points | `resume/page.tsx`, builder header | Round-trip edit works end to end |
| 0.5 | Fix BUG-10 ownership checks on the 4 unprotected endpoints | `resumes.py:557,580,609,779` | Cross-user fetch → 404; download still works |
| 0.6 | Fix BUG-12 + BUG-13 (save semantics, temp cleanup) | `resumes.py:838`, all `FileResponse` sites | Rename persists; temp dir stays flat |

**Do not proceed until 0.1–0.6 all pass.** Write a short manual smoke checklist and run it.

---

### Phase 1 — Canonical schema (highest leverage, ~1–2 days)

**Task 1.1 — Define the contract as executable code, not prose.**

Create `backend/schemas/resume.py` with Pydantic v2 models (`pydantic==2.9.2` is already a dependency) covering all 16 sections. Every section item carries `id: str` and `hidden: bool = False`. Nested objects stay nested — **no flattening to strings.** Include a `schema_version: int` field.

Mirror it in `frontend/app/lib/resumeSchema.ts` as the single source of TS types, and delete the local `ResumeData` interfaces from `builder/page.tsx` in favour of imports.

Suggested canonical shape (adjust to fit the parser's existing output where reasonable — do not gratuitously break `source='uploaded'` rows):

```python
class ResumeJSON(BaseModel):
    schema_version: int = 1
    contact:  Contact          # name, headline, email, phone, location, website, custom_fields[]
    photo:    Photo            # url(path, not base64), size, border_radius, border_width, border_color, hidden
    summary:  str = ""
    profiles: list[Profile]    # network, username, url, hidden      ← keeps network label
    experience: list[Experience]     # company, position, location, start_date, end_date, url, bullet_points[], hidden
    education:  list[Education]      # institution, degree, field, grade, location, graduation_date, description, hidden
    projects:   list[Project]        # name, period, url, technologies[], bullets[], hidden
    skills:     list[Skill]          # name, level, keywords[], hidden   ← objects, not strings
    languages:  list[Language]       # language, fluency, level, hidden  ← objects, not strings
    awards:     list[Award]
    certifications: list[Certification]
    publications:   list[Publication]
    volunteer:      list[Volunteer]
    interests:      list[Interest]
    references:     list[Reference]
    custom_sections: list[CustomSection]
    section_order:  list[str]        # canonical section keys, user-ordered
    section_visibility: dict[str, bool]   # section-level hide
```

**Task 1.2 — Delete `convertToStructuredJson`.**
The builder's in-memory state becomes the canonical shape, so serialisation is `JSON.stringify(data)`. Validate server-side with the Pydantic model in `preview-html`, `builder-save`, and every export endpoint. Return 422 with field paths on mismatch.

**Task 1.3 — Move `hidden` filtering server-side.**
Send *everything*, including hidden items, and let Jinja skip them. Rewrite the `is_hidden` filter to be item-level only, add a separate `section_visible(key)` helper for section-level hiding, and delete the meaningless `data.experience | is_hidden` list checks from all 6 templates.

**Task 1.4 — Migrate the 6 templates to the canonical shape.**
Fixes BUG-05 and BUG-06 together. Each template must render, or explicitly and deliberately omit, all 16 sections. Extract shared section partials into `templates_html/partials/` and `{% include %}` them so a schema change is a one-file edit, not six.

**Task 1.5 — Backward compatibility.**
Existing rows have no `schema_version`. Add `backend/services/resume_migrations.py` with `upgrade_to_v1(raw: dict) -> ResumeJSON` that promotes legacy shapes (string skills → `{name}`, `"English (Native)"` → `{language, fluency}`, `title`↔`position`, `cgpa_or_percentage`→`grade`) and run it on read for any row lacking a version. Do **not** write a destructive one-shot data migration — parsed resumes also live in this column.

**Acceptance for Phase 1:** A fixture resume populating all 16 sections renders every section in all 6 templates. An old pre-schema row still loads and renders. Round-trip `save → load → save` is byte-stable.

---

### Phase 2 — Builder feature completion (~2–3 days)

**Task 2.1 — Real section reordering (BUG-07). All four layers:**
1. **Schema/DB:** `section_order` and `section_visibility` live inside `structured_json` per Task 1.1 — **no migration needed.** (If you'd rather have them as columns, write an Alembic revision adding `section_order_json` and `font_id` to `resume_versions` and update `builder_save` to persist them.)
2. **Frontend:** implement drag-and-drop with the already-installed `@dnd-kit/*` (or framer-motion `Reorder`, already imported at `:6`) in the Layout tab, writing to `data.section_order`.
3. **Transport:** pass `section_order` through `previewResumeHtml` and `builderSave` — both already accept the argument and are being handed `undefined` today.
4. **Templates:** replace hardcoded section sequences with a driven loop:
   ```jinja
   {% for key in section_order %}
     {% if section_visible(key) %}{% include "partials/" ~ key ~ ".html" %}{% endif %}
   {% endfor %}
   ```
   For two-column templates (`modern_tech`), maintain two ordered lists — `sidebar_order` and `main_order`.

**Task 2.2 — Export correctness (BUG-08).**
Thread `page_format` end to end; parameterise page dimensions in `base.html`; decide and implement the multi-page policy; remove or hard-fail the silent PyMuPDF fallback.

**Task 2.3 — Export path rework (BUG-11).**
New `POST /resumes/export/pdf` taking the **live** payload `{structured_json, design, template_id, section_order, page_format}` and streaming the PDF. Frontend fetches with credentials → blob → download. Same for DOCX. The DB is no longer in the export path, so preview and download cannot diverge.

**Task 2.4 — Photo storage (BUG-09).**
Server-side file storage, resize/re-encode on upload, path in JSON, base64 inlined only at render time.

**Task 2.5 — Playwright browser pool (BUG-14) + drop link injection on the Chromium path (BUG-15).**

**Task 2.6 — Remaining design tokens.**
Wire `background_color` (currently hardcoded `#ffffff` at `base.html:44`) and `sidebar_width` (`modern_tech` only). Remove any token from the UI you don't intend to implement — a control that does nothing is worse than an absent one.

**Task 2.7 — Preview polish.**
Debounced skeleton/spinner (state exists at `:420`, barely surfaced), page-count indicator, zoom-to-fit default, and a visible red error state when `preview-html` 500s — right now `fetchPreview` only `console.error`s (`:487`) and the user stares at a stale preview.

**Task 2.8 — Undo/redo via reducer (BUG-16).**

---

### Phase 3 — AI tailoring in the builder (~2–3 days)

The backend already works and is exercised by `/ats` and `/tailor` pages. This phase is mostly builder-side integration. **Do not start before Phase 1 lands** — these endpoints read and write `structured_json`.

**Task 3.1 — Analyze panel.** Add a fourth right-panel tab (`design | layout | ai`) with a JD textarea. On submit: ensure saved (`resumeId` exists), then `POST /analyze` with `{resume_id, job_description}` (`lib/api.ts:215`). Render score, keyword coverage, and the returned `Suggestion` rows.

**Task 3.2 — Suggestion review UI.** Honour the project's core rule — *AI never mutates user data directly.* Every suggestion gets Accept / Reject / Edit. Accept applies the patch to builder state locally (preview updates instantly), then persists via autosave. Wire `POST /improve/propose` → `POST /improve/apply` (`ats.py:205`, `:300`).

**Task 3.3 — Per-bullet rewrite.** Inline ✨ button on each experience/project bullet → `POST /improve-bullet` (`ats.py:495`) → show original vs. rewritten diff → accept or discard.

**Task 3.4 — Keyword gap highlighting.** Use `services/jd_analyzer.py` + `ats_engine/keyword_engine/section_weighted_matcher.py` output to highlight missing JD keywords in the left panel where they'd naturally belong.

**Task 3.5 — Score history.** Persist ATS score per save (`ResumeVersion.ats_score` already exists) and sparkline it so the user sees improvement over time.

**Task 3.6 — Loading/error states.** LLM calls take seconds and can fail. Every AI action needs a spinner, a timeout, a retry, and a readable error. Never leave a button spinning forever.

---

### Phase 4 — Polish and hardening (~1–2 days)

- **4.1 DOCX export from the builder.** `services/docx_exporter.py` exists (234 lines) but predates the canonical schema and the design tokens — audit it against Phase 1 and wire the button.
- **4.2 Resume management.** Duplicate, rename, delete, and version list. `version_number` already exists on the model and is unused by the builder.
- **4.3 Config hygiene (BUG-17).** Fix the `.env.example` port, settle SQLite vs Postgres, resolve the duplicate tailor routes, gitignore the debug artefacts.
- **4.4 Tests.** At minimum: a golden-render test per template against an all-sections fixture (assert every section's heading appears), a schema round-trip test, a legacy-row upgrade test, and an auth test asserting cross-user 404 on all export endpoints.
- **4.5 Accessibility + mobile.** The 3-column layout has no responsive story below ~1024 px. Decide: tabbed mobile view, or an explicit "desktop only" gate.
- **4.6 Rate limiting** on `preview-html` and the AI endpoints.

---

## 5. Recommended execution order for the agent

```
Phase 0  ──►  Phase 1  ──►  Phase 2  ──►  Phase 3  ──►  Phase 4
(blockers)    (schema)      (features)    (AI)          (polish)
```

Phase 0 tasks are independent — parallelise freely.
Phase 1 is strictly sequential: 1.1 → 1.2 → 1.3 → 1.4 → 1.5.
Phase 2 tasks are independent of each other once Phase 1 is done.
Phase 3 requires Phase 1. Phase 4 requires Phase 2 and 3.

**After every phase:** run `npx tsc --noEmit`, start both servers, and walk the smoke checklist. Do not batch phases before verifying — several of these bugs (BUG-01, BUG-08c, BUG-14) fail *silently*, so a passing build proves very little here.

---

## 6. Smoke checklist (run after every phase)

1. `cd frontend && npx tsc --noEmit` → clean
2. Backend boots; `GET /health` → `{"status":"ok"}`
3. Fresh `/builder` visit, no typing, wait 5 s → **no new resume row** created
4. Fill all 16 sections → every one appears in the preview
5. Cycle all 6 templates → no blank sections, no Jinja errors in the backend log
6. Change primary colour / font / margins → preview updates within ~1 s
7. Upload a photo → appears in preview; `preview-html` request body < 100 KB
8. Save → navigate away → reopen from resume list → **everything restored**
9. Reorder sections → preview order changes → persists across reload
10. Download PDF → matches the preview exactly, including the most recent unsaved design tweak
11. Export A4 → measures 210×297 mm
12. Request another user's resume PDF by ID → 404
13. Paste a JD → Analyze → score + suggestions; accept one → preview updates
14. Check the system temp dir → no accumulating `.pdf` files

---

## 7. Quick reference — file map

**Backend**
| Path | Role |
|---|---|
| `main.py` | App, CORS, router registration, Qdrant startup |
| `api/resumes.py` | Builder endpoints: `preview-html:806`, `builder-save:838`, `upload-avatar:883`, `{id}/pdf:557`, `{id}/docx:580` |
| `api/ats.py` | `analyze:36`, `improve/propose:205`, `improve/apply:300`, `improve-bullet:495` (**no router prefix**) |
| `api/tailor.py` | `tailor/analyze:56`, `tailor/apply:101`, `tailor/versions:207` |
| `api/auth.py` | `get_current_user:106` (session cookie or Bearer), register/login/OTP |
| `services/html_templates.py` | Jinja env + `build_html():17` |
| `services/pdf_fitter.py` | `build_preview_html():791`, `_render_pdf_playwright():814`, `build_fitted_pdf():841`, `_inject_links_to_pdf():673`, `extract_flat_skills():48` |
| `services/templates_html/` | `base.html` + 6 templates |
| `db/models.py` | `ResumeVersion:87` — `design_json`, `builder_template_id`, source CheckConstraint at `:108` |

**Frontend**
| Path | Role |
|---|---|
| `app/builder/page.tsx` | The whole builder, 1277 lines — **split this up during Phase 1** |
| `app/lib/api.ts` | Typed client; builder fns at `:666-732` |
| `app/context/AuthContext.tsx` | Session state |
| `public/templates/*.jpg` | Gallery thumbnails |

**A note on `builder/page.tsx`:** at 1277 lines it holds all 16 section editors, all the dialogs, the design panel, and the state machine in one file. Several bugs here (01, 11, 16) are the direct result of that size — the missing effect dep and the missing load effect are easy to overlook in a file this long. Split it as part of Phase 1: `builder/components/sections/*.tsx`, `builder/components/DesignPanel.tsx`, `builder/components/LayoutPanel.tsx`, `builder/hooks/useResumeState.ts`, `builder/hooks/useAutosave.ts`.

---

## 8. Honest summary

The previous session's report is **accurate about what was built** — the 3-column shell, the Playwright engine, 6 templates, design tokens, photos, and the preview are all genuinely there, and the architecture is the right one.

It is **too optimistic about the state of that work**. Verified by reading the code:

- The production build **does not compile** (BUG-03).
- `pip install -r requirements.txt` **fails on a clean machine** (BUG-04).
- "Cloud saves" are **write-only and actively destructive** — opening a saved resume blanks it (BUG-01, BUG-02). This is the most urgent item in the document.
- The Layout / Section Order panel is **non-functional at all four layers** (BUG-07).
- **7 of the 16 left-panel sections** feed data that no template can render (BUG-06).
- Any authenticated-or-not caller can **download any user's resume** (BUG-10).
- The A4 option, the `background_color` control, and the `sidebar_width` control **do nothing** (BUG-08a, 2.6).

Rough remaining effort: **6–10 focused days**. Phase 0 alone is roughly half a day and converts the project from "loses data" to "safe to demo" — do it before anything else, including before showing this to anyone.
