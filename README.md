# CareerOS

CareerOS is an AI-powered career workspace for discovering jobs, analyzing resume ATS compatibility, tailoring LaTeX resumes, and managing job applications.

## Features

- Job discovery with source adapters, filters, matching, and saved connections.
- Resume parsing, ATS scoring, and actionable feedback.
- A master LaTeX resume with reviewed, skills-only tailoring and PDF compilation.
- Application tracking, scheduled preparation, and a companion browser extension.
- A local personal workspace with task-specific Groq model routing.

## Local setup

Requires Python 3.11+, Node.js 18+, and Docker Desktop. Personal mode runs without login and is intended for a local computer. Keep services bound to loopback.

Start PostgreSQL and Qdrant from the repository root:

```sh
docker compose up -d
```

Set up the backend:

```sh
cd backend
python -m venv venv
# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Copy `backend/.env.example` to `backend/.env` and fill in your credentials. The example database URL uses port **5455**, matching Docker Compose. Generate your own token encryption key as explained in the example.

From `backend`, run:

```sh
python -m alembic upgrade head
docker build -t careeros-latex:2026-10-compat ./compiler
python -m uvicorn main:app --host 127.0.0.1 --port 8010
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open [CareerOS](http://127.0.0.1:3000). For scheduled preparation, start `python -m automation.worker` from `backend` in a separate terminal.

On Windows, optionally copy `scripts/CareerOS.example.toml` to `scripts/CareerOS.toml`, set your checkout path, and use the start/stop scripts. See [automation setup](AUTOMATION_SETUP.md), [personal mode](PERSONAL_MODE_SETUP.md), and [extension setup](extension/README.md) for details. Some implementation notes describe the original development computer; substitute your own paths.

## Repository layout

| Directory | Purpose |
| --- | --- |
| `backend/` | FastAPI, resume analysis, tailoring, discovery, and background workers |
| `frontend/` | Next.js and React workspace |
| `extension/` | Companion browser extension |
| `scripts/` | Windows desktop launcher |
| `oss-tools/` | Source manifests, dependency locks, and upstream license notices |

Credentials, local databases, uploads, personal PDFs, runtime environments, and backups are excluded from Git. Keep your real resume and provider keys local.
