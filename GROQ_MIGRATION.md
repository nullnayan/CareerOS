# Groq-only AI migration

Implemented 30 October 2026 at the user's request.

## Credential assignments

Five distinct Jarvis Groq credentials were validated and copied into CareerOS's backend environment. Jarvis was read only. Values are never included in this document, source files, the frontend, logs, or the routing-status endpoint.

| Jarvis variable | CareerOS variable | Jobs |
| --- | --- | --- |
| GROQ_API_KEY_1 | GROQ_API_KEY_PARSING | Text resume parsing, scanned resume vision, image transcription |
| GROQ_API_KEY_2 | GROQ_API_KEY_CHAT | Career chat, chat reranking, sample resume generation |
| GROQ_API_KEY_3 | GROQ_API_KEY_TAILORING | JD extraction, missing skill extraction, summary tasks |
| GROQ_API_KEY_4 | GROQ_API_KEY_ATS | Standalone ATS analysis helpers, improvements, bullet rewriting, recruiter checks |
| GROQ_API_KEY_5 | GROQ_API_KEY_CLASSIFICATION | Chat intents, skill categories, coverage auditing, job-match reasoning |

This assignment keeps a preferred key for each workload. On 31 October the user confirmed these keys belong to separate Groq organizations, so independent-quota backups are now enabled in `backend/data/groq-routing.json`. Each group uses its current primary followed by the other configured keys in a circular order. A 429 cools down that key/model pair and tries the next available key. Duplicate credentials are deduplicated. If all are limited, the earliest retry time is returned. Authentication/configuration errors are reported rather than silently hidden.

Shared-organization keys do not create extra capacity. The default for other installations remains shared-quota mode unless independent ownership is explicitly configured; `GROQ_KEYS_INDEPENDENT_ORGANIZATIONS=false` overrides the local policy. Settings shows primary variables and configured backup variables, never values. Restart existing backend/worker processes after updating routing code.

LaTeX syntax repair uses the `latex_repair` task with `GROQ_API_KEY_TAILORING` as primary and the other four configured independent organizations as backups. Repair has at most two model-output attempts, content checks, strict recompilation, a persisted diff, and manual activation of a separate compiled revision. See LATEX_COMPATIBILITY.md.

## Models and removed providers

The live Groq model list did not include the old Llama 3.1/3.3 IDs. Routine text tasks now use the compact `openai/gpt-oss-20b`: chat, parsing text resumes, building resumes, JD/ATS helpers, classifications, and coverage checks. LaTeX syntax repair and vision retain `qwen/qwen3.8-27b`. These are served by Groq, not an OpenAI API integration. No OpenAI API key is used.

The routing was simplified on 31 October after checking [Groq's current model list](https://console.groq.com/docs/models). Groq lists approximate generation speeds of 1,000 tokens/second for GPT-OSS 20B and 450 for Qwen 3.8 27B; actual end-to-end latency depends on input, output, provider load, and network conditions. Per-task output caps are explicit in `backend/core/agent_models.py`: chat 1,024; classifiers 256–512; JD/ATS 2,048–4,096; resume extraction/building and full-source LaTeX repair 8,192. GPT-OSS uses low reasoning effort; Qwen disables reasoning, matching [Groq's supported controls](https://console.groq.com/docs/reasoning). Token caps include reasoning tokens, and truncated outputs remain rejected rather than applied.

All active provider completions, including `/chat/send`, use the shared `LLMClient`; there is no separate realtime chat model override. The preferred keys and independent-organization backup policy are unchanged.

NVIDIA NIM, Gemini, Anthropic, and Zhipu credentials and runtime clients were removed from the active AI configuration. The old invalid generic Groq key was replaced with five task variables. Non-AI GitHub, Adzuna, and token-encryption settings remain intact.

The explicit request to transfer credentials authorized reading the two environment files for this migration. The transfer script reads values in memory and prints validation outcomes only; no credential was exposed in tool output. Existing environment-file restrictions continue to apply to unrelated work.

## Embeddings

Groq serves the text/vision work. Resume retrieval now embeds locally with FastEmbed and `BAAI/bge-small-en-v1.5`, producing 384-dimensional vectors without an API key. The model was downloaded and initialized locally.

A separate Qdrant collection, `career_data_bge_small_v1`, prevents mixing these vectors with old 3072-dimensional hosted embeddings. The legacy collection was preserved. The active workspace had zero saved parsed resumes to reindex at migration time. New uploads use the local model. A repeatable reindex script is provided at `backend/scripts/reindex_local_embeddings.py` for saved workspace resumes.

## LaTeX error

The user's uploaded source failed at line 188 because a nested Certifications list had no outer list item. A separate corrected revision adds that item and wraps the overflowing education row. It does not change resume claims, skills, or project bullets.

The original `Downloads/CareerOS_Master_Resume.tex` is unchanged. The corrected source is `Downloads/CareerOS_Master_Resume_fixed.tex` and is imported into CareerOS as a compiled, one-page revision without overflow. The user must review and activate it; activation was not automatic.

Compiler failures now return a short line-specific explanation. Full logs are saved in the revision's Compiler diagnostics panel rather than sent as the main error message.

## Validation

- All five credentials passed read-only model-list authentication.
- A small synthetic JSON completion succeeded through each task group.
- Synthetic resume parsing and image transcription succeeded with Groq.
- Local embeddings returned 384-dimensional unit-normalized vectors.
- 61 relevant regression tests passed, including task routing, rate-limit behavior, no secret leakage in errors, vision payloads, local embeddings, category-name escaping, actual PDF compilation, builder export, and ATS checks.
- Production frontend build passed.
- Package dependency check passed.
- Corrected resume rendered to one page and was visually inspected.

Settings now displays configured task groups without exposing secrets. Keys are loaded from the backend environment, so restart the backend after future credential changes.

Provider references: [Groq vision](https://console.groq.com/docs/vision), [Groq rate limits](https://console.groq.com/docs/rate-limits), [FastEmbed](https://github.com/qdrant/fastembed).
