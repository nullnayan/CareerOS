"""
core/config.py — Centralised settings for CareerOS backend.

All environment variables are read exactly once here and exposed as a
typed `Settings` singleton.  Every other module should import from here
instead of calling ``os.getenv`` directly.

Usage:
    from core.config import settings
    key = settings.GROQ_API_KEY
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    JOB_DISCOVERY_ENGINE: str = os.getenv("JOB_DISCOVERY_ENGINE", "oss").strip().lower()
    JOB_LEGACY_ENABLED: bool = os.getenv("JOB_LEGACY_ENABLED", "false").lower() == "true"
    # ── Database ────────────────────────────────────────────────────────
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://careeros:careeros_dev_password@localhost:5432/careeros"
    )

    # ── Vector store ────────────────────────────────────────────────────
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")

    # Hosted AI is Groq-only; task-specific keys take priority over the fallback.
    GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
    GROQ_API_KEY_PARSING: str | None = os.getenv("GROQ_API_KEY_PARSING")
    GROQ_API_KEY_CHAT: str | None = os.getenv("GROQ_API_KEY_CHAT")
    GROQ_API_KEY_TAILORING: str | None = os.getenv("GROQ_API_KEY_TAILORING")
    GROQ_API_KEY_ATS: str | None = os.getenv("GROQ_API_KEY_ATS")
    GROQ_API_KEY_CLASSIFICATION: str | None = os.getenv("GROQ_API_KEY_CLASSIFICATION")

    # ── GitHub OAuth ─────────────────────────────────────────────────────
    GITHUB_CLIENT_ID: str = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # ── Job listings ─────────────────────────────────────────────────────
    ADZUNA_APP_ID: str | None = os.getenv("ADZUNA_APP_ID")
    ADZUNA_APP_KEY: str | None = os.getenv("ADZUNA_APP_KEY")

    # ── Security ─────────────────────────────────────────────────────────
    TOKEN_ENCRYPTION_KEY: str = os.getenv("TOKEN_ENCRYPTION_KEY", "")

    # ── Rate limiting (requests per minute per user) ──────────────────────
    RATE_LIMIT_AI_RPM: int = int(os.getenv("RATE_LIMIT_AI_RPM", "10"))
    RATE_LIMIT_UPLOAD_RPM: int = int(os.getenv("RATE_LIMIT_UPLOAD_RPM", "20"))

    def validate(self) -> list[str]:
        """Return a list of warnings for missing critical keys."""
        warnings = []
        from core.groq_keys import routing_status
        missing = [item["variable"] for item in routing_status() if not item["configured"]]
        if missing:
            warnings.append("Missing Groq task credentials: " + ", ".join(missing))
        if not self.TOKEN_ENCRYPTION_KEY or self.TOKEN_ENCRYPTION_KEY == "generate_a_real_key_before_using":
            warnings.append("TOKEN_ENCRYPTION_KEY is missing or insecure — GitHub OAuth token storage is broken.")
        return warnings


settings = Settings()
