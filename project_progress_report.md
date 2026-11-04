# Project Progress Report & AI Handoff Document

This document summarizes the current status of the CareerOS development, detail of what is completed, and instructions for any other AI agent to resume this task without losing context.

---

## 1. Overall Status
* **Milestones 1–4 Completed**: Parsing, hybrid vector search (Qdrant), RAG chat system, multimodal attachments (images & zips), secure GitHub OAuth and folder commits, and LLM-powered resume tailoring with direct PDF downloads are **100% complete and verified**.
* **Next Major Goals**:
  1. **Job Match Agent**: Integration with the Adzuna API to query, score, and rank jobs against the user's PostgreSQL skill inventory.
  2. **Resume Builder**: A Next.js wizard interface to compile experiences, education, and projects into the structured JSON schema.

---

## 2. Completed Milestones & Files Map

### ✅ Milestone 1: Vector Store & Embeddings Pipeline
* **Functionality**: Automatically extracts text from uploaded resumes, chunks it, and creates vector embeddings using Gemini's `text-embedding-004` to upsert into a local Qdrant collection.
* **Key Files**:
  * [vector_store_service.py](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/backend/services/vector_store_service.py) — Handles document chunking, calling Gemini embeddings, and Qdrant Upserts.
  * [resumes.py](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/backend/api/resumes.py) — API endpoints for uploading and fetching resumes.

### ✅ Milestone 2: RAG Chat System & Multimodal Input
* **Functionality**: Hybrid retrieval (Postgres structured lookup + Qdrant semantic vector search) for grounded, accurate context. Supports dragging/dropping and uploading `.pdf`, `.docx`, `.txt`, `.zip` folders, and images (transcribed via Gemini 1.5 Flash).
* **Key Files**:
  * [chat_agent.py](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/backend/agents/chat_agent.py) — Core RAG logic.
  * [chat.py](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/backend/api/chat.py) — API endpoints for sending chat messages and processing intents.
  * [chat/page.tsx](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/frontend/app/chat/page.tsx) — Chat workspace UI with drag-and-drop overlay and interactive cards.

### ✅ Milestone 3: GitHub Connect & Folder Push
* **Functionality**: Authenticates users to GitHub via secure Fernet token encryption at rest. Enables conversational commands (like *"push this project to github"*) to scan attached folders (zipped), strip out binaries/node_modules, and push directly using the Git Data API.
* **Key Files**:
  * [encryption.py](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/backend/core/encryption.py) — Key encryption.
  * [github_service.py](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/backend/services/github_service.py) — low-level Git Data API operations.
  * [github.py](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/backend/api/github.py) — OAuth and push router.

### ✅ Milestone 4: Resume Tailoring & ATS Optimization
* **Functionality**: Rewrite resumes to match specific job descriptions using NVIDIA NIM. Creates a clean, ATS-optimized print layout (using Georgia typography) and compiles a physical PDF using PyMuPDF Stories for direct download.
* **Key Models Routing** ([agent_models.py](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/backend/core/agent_models.py)):
  * Chat: `meta/llama-3.1-8b-instruct` (Fast/warm)
  * Tailoring: `meta/llama-3.1-8b-instruct` (Fast/warm)
* **Key Files**:
  * [resume_tailor_agent.py](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/backend/agents/resume_tailor_agent.py) — Rewrite logic.
  * [resume/preview/[id]/page.tsx](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/frontend/app/resume/preview/%5Bid%5D/page.tsx) — Print preview page.
  * `GET /resumes/{resume_id}/pdf` endpoint in [resumes.py](file:///C:/Users/nayan/Downloads/careeros_scaffold/careeros/backend/api/resumes.py) — Compiles and serves PDF.

---

## 3. Left / Outstanding Tasks (Handoff Guide for Next AI)

### 📋 Task 1: Job Match Agent
1. **Adzuna API Integration**:
   * Set up connection details inside `.env` (communicate values to user).
   * Create service to query Adzuna jobs matching skills stored in PostgreSQL.
2. **Matching & Scoring**:
   * Use an LLM agent to compare job responsibilities with user's Postgres skills inventory.
   * Score match from 0-100% and generate reasoning bullet points.

### 📋 Task 2: Resume Builder Wizard
1. **Wizard Form UI**:
   * Create a step-by-step Next.js form/wizard for inputting Contact, Experience, Education, Skills, and Projects.
2. **JSON Sync & Save**:
   * Compile input into the standardized JSON schema and save as a new `ResumeVersion` (with `source="builder"`).

---

## 4. Crucial Guidelines & Environment Facts
> [!IMPORTANT]
> **Rule on Env Files**: NEVER access or edit `.env` or `.env.local` directly. Print configuration instructions/variables to the user so they can paste them themselves.
> **Database Constraints**: `ResumeVersion` source must only be `'uploaded'` or `'builder'`. 
> **Port bindings**: Dev services are bound to `127.0.0.1:8000` (FastAPI) and `127.0.0.1:3000` (Next.js) to avoid Windows IPv6 resolution issues.
