from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import time
from collections import defaultdict
from dotenv import load_dotenv

# Load env variables on startup
load_dotenv()

# Import your routers
from api import resumes, ats, skills, suggestions, chat, github, workspace, tailor, jobs, automation, applications, autofill
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from urllib.parse import urlsplit

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CareerOS API",
    description="AI-powered career operating system — backend service",
    version="0.1.0"
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])


@app.middleware("http")
async def local_request_guard(request: Request, call_next):
    origin = request.headers.get("origin")
    import re
    extension_origin = bool(origin and re.fullmatch(r"chrome-extension://[a-p]{32}", origin))
    extension_route = request.url.path == "/autofill/pair" or request.url.path.startswith("/autofill/extension/")
    extension_id = request.headers.get("x-careeros-extension", "")
    extension_bearer_route = request.url.path.startswith("/autofill/extension/")
    paired_get = not origin and extension_bearer_route and re.fullmatch(r"[a-p]{32}", extension_id)
    if (extension_origin and extension_route) or paired_get:
        # These endpoints enforce a single-use pairing code or a scoped bearer.
        # No other personal workspace route accepts extension origins.
        return await call_next(request)
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1"}:
            return JSONResponse(status_code=403, content={"detail": "Only the local CareerOS workspace may access this API."})
    if request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse(status_code=403, content={"detail": "Cross-site requests are disabled in personal mode."})
    return await call_next(request)

# Configure CORS so your Next.js frontend can talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|chrome-extension://[a-p]{32}",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-memory rate limiter (Task 4.6) ─────────────────────────────────────
# Sliding-window per-user rate limiter stored in memory.
# For production use Redis + slowapi; this covers the dev case cleanly.

_AI_ROUTES = {
    "/resumes/builder-download-pdf",
    "/analyze",
    "/improve/propose",
    "/improve/apply",
    "/improve-bullet",
    "/tailor",
    "/tailor/phase8/pdf",
    "/tailor/phase8/docx",
}
_UPLOAD_ROUTES = {"/resumes/upload", "/resumes/parse"}

# {user_key: [timestamp, ...]}
_rate_store: dict[str, list[float]] = defaultdict(list)


def _sliding_window_check(key: str, limit: int, window_s: int = 60) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = time.time()
    bucket = _rate_store[key]
    # Drop timestamps outside the window
    _rate_store[key] = [t for t in bucket if now - t < window_s]
    if len(_rate_store[key]) >= limit:
        return False
    _rate_store[key].append(now)
    return True


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    from core.config import settings

    path = request.url.path
    limit = None
    if path in _AI_ROUTES or (path.startswith("/tailor/masters/") and path.endswith("/ai-repair")):
        limit = settings.RATE_LIMIT_AI_RPM
    elif path in _UPLOAD_ROUTES:
        limit = settings.RATE_LIMIT_UPLOAD_RPM

    if limit is not None:
        # Use session token or IP as the user key
        token = request.headers.get("authorization", request.client.host if request.client else "anon")
        key = f"{path}:{token}"
        if not _sliding_window_check(key, limit):
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded — max {limit} requests/minute for this endpoint."},
                headers={"Retry-After": "60"},
            )

    return await call_next(request)


# Health check endpoint
@app.get("/health", tags=["default"])
def health_check():
    return {"status": "ok", "service": "careeros-backend"}


# Initialize Qdrant collection on startup (idempotent — safe to call repeatedly)
@app.on_event("startup")
def startup_init_vector_store():
    try:
        from services.vector_store_service import ensure_collection
        ensure_collection()
    except Exception as e:
        # Non-fatal: Qdrant might not be running yet during development.
        logger.warning(f"Could not initialize Qdrant on startup (non-fatal): {e}")


@app.on_event("startup")
def startup_validate_config():
    """Warn loudly at startup if any critical environment variables are missing."""
    from core.config import settings
    warnings = settings.validate()
    for w in warnings:
        logger.warning(f"[CONFIG] ⚠  {w}")
    if not warnings:
        logger.info("[CONFIG] ✓  All critical settings are present.")


# Include routers - NO prefixes or tags here, because they are already in the router files!
app.include_router(workspace.router)
app.include_router(resumes.router)
app.include_router(ats.router)
app.include_router(skills.router)
app.include_router(suggestions.router)
app.include_router(chat.router)
app.include_router(github.router)
app.include_router(tailor.router)
app.include_router(jobs.router)
app.include_router(automation.router)
app.include_router(applications.router)
app.include_router(autofill.router)
