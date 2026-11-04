# Master resume

Upload a `.tex` file or paste the complete LaTeX code. Add a reference resume PDF if desired, then click **Compile resume**. The reference PDF is optional and is not converted into a replacement template.

CareerOS compiles the source first. If compilation fails, the backend sends the complete source and compiler error to the configured Groq repair task, receives complete corrected LaTeX, and recompiles automatically. It makes at most two correction attempts. The old exact-fragment matching repair is no longer used in this flow. No compatibility, revision, repair, or compiler controls are needed on the page.

A successful result appears as a PDF preview with PDF and LaTeX downloads. Review it and click **Use as master** to use it for future tailoring. Original uploads remain preserved internally; compiling a new resume does not replace the active master. A failed correction never becomes a master.

## Models and compilation

Routine chat and text work use compact `openai/gpt-oss-20b`. Syntax repair and vision use `qwen/qwen3.8-27b`. Repair uses the existing tailoring credential first and the configured independent-organization backup keys on rate limits. See GROQ_MIGRATION.md.

The repair request contains the complete main source, a compiler error excerpt, and feedback from any failed correction. It returns complete source, not a list of text patches. Content checks reject changes to detected resume words, numbers, skills, and order. The candidate must pass strict compilation before a PDF is returned. Visual equivalence still needs review.

The offline image `careeros-latex:2026-10-compat` supports pdfLaTeX, XeLaTeX, and LuaLaTeX with automatic engine selection. Two bounded compiler passes run without network or shell escape in an isolated, resource-limited container. To rebuild from the backend directory:

```powershell
docker build -t careeros-latex:2026-10-compat ./compiler
```

Missing fonts, external class/style files, or unavailable dependencies cannot always be corrected from a standalone `.tex` file. The complete-project ZIP and compiler inspection APIs remain available internally, but are not shown in the simplified page. Arbitrary build scripts, BibTeX/Biber, and package downloads are not executed. Exact compatibility with every Overleaf project or TeX Live release is not guaranteed.

## Skills mapping for tailoring

Common bold-label and category-command layouts are recognized automatically. An unfamiliar template can compile and download even when automatic Skills mapping is unavailable. Automatic tailoring needs identifiable Skills category values; it only adds up to five confirmed missing skills to those values.

For custom templates, explicit comments can identify an existing value without changing layout:

```latex
\mySkillRow{Languages}{
% CAREEROS_SKILL_START: Languages
Python, Java, SQL
% CAREEROS_SKILL_END
}
```

## Verification

The latest attached resume was sent through live Groq full-source correction and the real Docker compiler: one page, no detected overflow, rendered layout reviewed. Isolated browser tests cover upload, paste, automatic repair, PDF/source downloads, explicit master activation, failed-compilation cleanup, and mobile widths. Tests do not change the personal workspace.
