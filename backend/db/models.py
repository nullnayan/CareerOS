"""
Database models for CareerOS.

Each class here is a Python description of one database table. SQLAlchemy
turns these into real SQL tables when we run a migration (next file).

Why classes instead of raw SQL: we get autocomplete, type-checking, and can
build queries as normal Python instead of writing SQL strings everywhere —
safer (less risk of SQL injection bugs) and easier to change later.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean, ForeignKey, DateTime, JSON, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def new_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    clerk_user_id = Column(Text, unique=True, nullable=True)
    email = Column(Text, nullable=False)
    hashed_password = Column(Text, nullable=True)
    career_level = Column(Text, nullable=True)
    target_role = Column(Text, nullable=True)
    locale = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    resume_versions = relationship("ResumeVersion", back_populates="user", cascade="all, delete-orphan")
    skills = relationship("Skill", back_populates="user", cascade="all, delete-orphan")
    suggestions = relationship("Suggestion", back_populates="user", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")
    github_connection = relationship("GitHubConnection", back_populates="user", uselist=False, cascade="all, delete-orphan")
    push_events = relationship("PushEvent", back_populates="user", cascade="all, delete-orphan")
    job_matches = relationship("JobMatch", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    """Stores local session tokens for cookie-based authentication."""
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="sessions")


class PendingRegistration(Base):
    """Stores temporary credentials and OTPs before registration completion."""
    __tablename__ = "pending_registrations"

    email = Column(Text, primary_key=True)
    hashed_password = Column(Text, nullable=False)
    otp_code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PasswordResetOtp(Base):
    """Stores OTP codes requested for resetting user passwords."""
    __tablename__ = "password_reset_otps"

    email = Column(Text, primary_key=True)
    otp_code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)





class ResumeVersion(Base):
    """Every resume, whether uploaded by the user or built from scratch,
    lives here. This is the 'one data model, two input paths' table."""
    __tablename__ = "resume_versions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"))
    source = Column(Text, nullable=False)  # 'uploaded', 'builder', or 'tailored'
    raw_text = Column(Text, nullable=True)
    structured_json = Column(JSON, nullable=False)
    layout_facts = Column(JSON, nullable=True)
    original_filename = Column(Text, nullable=True)
    version_number = Column(Integer, default=1, nullable=True)
    ats_score = Column(Float, nullable=True)
    issues_json = Column(JSON, nullable=True)
    diff_json = Column(JSON, nullable=True)
    design_json = Column(JSON, nullable=True)          # Builder design settings (colors, fonts, spacing, photo)
    builder_template_id = Column(Text, nullable=True)  # Selected template ID from the builder
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="resume_versions")
    clarifications = relationship("ResumeClarification", back_populates="resume_version", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("source IN ('uploaded', 'builder', 'tailored', 'ats_check', 'tailor_input')", name="check_resume_source"),
    )


class ResumeClarification(Base):
    """Stores the clarification questions and user answers for a resume version."""
    __tablename__ = "resume_clarifications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    resume_version_id = Column(UUID(as_uuid=False), ForeignKey("resume_versions.id", ondelete="CASCADE"))
    bullet_id = Column(Text, nullable=False)
    question = Column(Text, nullable=False)
    user_answer = Column(Text, nullable=True)
    answered_at = Column(DateTime, nullable=True)

    resume_version = relationship("ResumeVersion", back_populates="clarifications")



class Skill(Base):
    """Deduplicated skill inventory, one row per unique skill per user."""
    __tablename__ = "skills"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(Text, nullable=False)
    source_resume_id = Column(UUID(as_uuid=False), ForeignKey("resume_versions.id", ondelete="SET NULL"), nullable=True)
    confidence = Column(Float, nullable=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="skills")

    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_user_skill'),
    )


class Suggestion(Base):
    """Every AI suggestion, from any agent. Nothing changes the user's data
    until they explicitly accept one of these."""
    __tablename__ = "suggestions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"))
    type = Column(Text, nullable=False)  # e.g. 'ats_gap', 'skill_detected', 'bullet_rewrite'
    reason = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=True)
    expected_impact = Column(Text, nullable=True)
    status = Column(Text, default="pending")  # pending | accepted | rejected | edited
    target_entity_type = Column(Text, nullable=True)
    target_entity_id = Column(UUID(as_uuid=False), nullable=True)
    payload = Column(JSON, nullable=True)  # the actual proposed change
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="suggestions")

    __table_args__ = (
        CheckConstraint("status IN ('pending','accepted','rejected','edited')", name="check_suggestion_status"),
    )


class ChatMessage(Base):
    """Chat history, persisted per user across sessions."""
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"))
    session_id = Column(UUID(as_uuid=False), nullable=False)
    role = Column(Text, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    cited_resume_version_id = Column(UUID(as_uuid=False), ForeignKey("resume_versions.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="chat_messages")

    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="check_message_role"),
    )


class GitHubConnection(Base):
    """One GitHub OAuth connection per user. Token is encrypted before
    being stored — see core/security.py (built in a later step)."""
    __tablename__ = "github_connections"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    encrypted_access_token = Column(Text, nullable=False)
    github_username = Column(Text, nullable=True)
    scope = Column(Text, nullable=True)
    connected_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="github_connection")


class PushEvent(Base):
    """Audit log AND state machine for the chat-triggered GitHub push flow.
    A row is created the moment the user's chat message is classified as a
    push intent — status moves from pending_confirmation to confirmed to
    succeeded/failed."""
    __tablename__ = "push_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"))
    repo_name = Column(Text, nullable=False)
    files = Column(JSON, nullable=True)
    status = Column(Text, nullable=False)  # pending_confirmation | confirmed | succeeded | failed
    triggered_by_message_id = Column(UUID(as_uuid=False), ForeignKey("chat_messages.id"), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="push_events")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_confirmation','confirmed','succeeded','failed')",
            name="check_push_status"
        ),
    )


class JobMatch(Base):
    """Cached job/internship matches from Adzuna, refreshed periodically
    (not re-queried on every dashboard view)."""
    __tablename__ = "job_matches"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(Text, nullable=False)
    company = Column(Text, nullable=True)
    location = Column(Text, nullable=True)
    source_url = Column(Text, nullable=False)
    match_score = Column(Float, nullable=True)
    matched_skills = Column(JSON, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    job_id = Column(String(36), ForeignKey("job_postings.id"), nullable=True)
    assessment = Column(JSON, nullable=True)
    state = Column(String(20), default="new", nullable=True)
    tailoring_run_id = Column(String(36), ForeignKey("latex_tailoring_runs.id"), nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_user_job_match"),)

    user = relationship("User", back_populates="job_matches")


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"
    id = Column(Integer, primary_key=True, default=1)
    owner_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)


class LatexMaster(Base):
    __tablename__ = "latex_masters"
    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    filename = Column(Text, nullable=False)
    source = Column(Text, nullable=False)
    source_hash = Column(String(64), nullable=False)
    categories = Column(JSON, nullable=False)
    status = Column(String(32), nullable=False, default="draft")
    baseline_pages = Column(Integer, nullable=True)
    diagnostics = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ConfirmedSkill(Base):
    __tablename__ = "confirmed_skills"
    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    canonical = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    category = Column(Text, nullable=False)
    confirmed_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "canonical", name="uq_confirmed_skill"),)


class LatexTailoringRun(Base):
    __tablename__ = "latex_tailoring_runs"
    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    master_id = Column(String(36), ForeignKey("latex_masters.id"), nullable=False)
    job_description = Column(Text, nullable=False)
    label = Column(Text, nullable=False)
    candidates = Column(JSON, nullable=False)
    source = Column(Text, nullable=True)
    changes = Column(JSON, nullable=True)
    status = Column(String(32), nullable=False, default="analyzed")
    diagnostics = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class JobSearchPreferences(Base):
    __tablename__ = "job_search_preferences"
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), primary_key=True)
    data = Column(JSON, nullable=False)
    confirmed_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class JobSource(Base):
    __tablename__ = "job_sources"
    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    provider = Column(String(20), nullable=False)
    board = Column(String(100), nullable=False)
    company = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    last_checked_at = Column(DateTime)
    last_success_at = Column(DateTime)
    last_error = Column(Text)
    last_count = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint("user_id", "provider", "board", name="uq_job_source"),)


class JobPosting(Base):
    __tablename__ = "job_postings"
    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    identity_key = Column(String(64), nullable=False)
    title = Column(Text, nullable=False)
    company = Column(Text, nullable=False)
    location = Column(Text, nullable=False)
    apply_url = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    description_hash = Column(String(64), nullable=False)
    description_complete = Column(Boolean, default=False, nullable=False)
    facts = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="open")
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    published_at = Column(DateTime)
    __table_args__ = (UniqueConstraint("user_id", "identity_key", name="uq_job_identity"),)


class JobSourceOccurrence(Base):
    __tablename__ = "job_source_occurrences"
    id = Column(String(36), primary_key=True, default=new_uuid)
    source_id = Column(String(36), ForeignKey("job_sources.id"), nullable=False)
    job_id = Column(String(36), ForeignKey("job_postings.id"), nullable=False)
    native_id = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("source_id", "native_id", name="uq_source_native_job"),)


class JobDescriptionRevision(Base):
    __tablename__ = "job_description_revisions"
    id = Column(String(36), primary_key=True, default=new_uuid)
    job_id = Column(String(36), ForeignKey("job_postings.id"), nullable=False)
    content_hash = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    complete = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("job_id", "content_hash", name="uq_job_description_revision"),)


class JobRefreshRun(Base):
    __tablename__ = "job_refresh_runs"
    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    status = Column(String(20), nullable=False, default="running")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime)
    summary = Column(JSON, nullable=False, default=dict)


class AutomationSettings(Base):
    __tablename__ = "automation_settings"
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), primary_key=True)
    data = Column(JSON, nullable=False, default=dict)
    next_run_at = Column(DateTime)
    last_run_at = Column(DateTime)


class AutomationTask(Base):
    __tablename__ = "automation_tasks"
    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    kind = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="queued", index=True)
    dedupe_key = Column(String(64), nullable=False, unique=True)
    payload = Column(JSON, nullable=False, default=dict)
    result = Column(JSON, nullable=False, default=dict)
    attempts = Column(Integer, nullable=False, default=0)
    error = Column(Text)
    available_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    lease_until = Column(DateTime)
    lease_owner = Column(String(36))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime)


class AutomationWorker(Base):
    __tablename__ = "automation_workers"
    id = Column(String(36), primary_key=True)
    heartbeat_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class JobApplication(Base):
    __tablename__ = "job_applications"
    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    job_id = Column(String(36), ForeignKey("job_postings.id"), nullable=False)
    status = Column(String(20), nullable=False, default="planned")
    notes = Column(Text, nullable=False, default="")
    applied_at = Column(DateTime)
    next_action_at = Column(DateTime)
    tailoring_run_id = Column(String(36), ForeignKey("latex_tailoring_runs.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_application_job"),)


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id = Column(String(36), primary_key=True, default=new_uuid)
    application_id = Column(String(36), ForeignKey("job_applications.id"), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    event_type = Column(String(32), nullable=False)
    from_status = Column(String(20))
    to_status = Column(String(20))
    detail = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AutofillProfile(Base):
    __tablename__ = "autofill_profiles"
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), primary_key=True)
    data = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ExtensionPairing(Base):
    __tablename__ = "extension_pairings"
    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    code_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime)


class ExtensionCredential(Base):
    __tablename__ = "extension_credentials"
    id = Column(String(36), primary_key=True, default=new_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    label = Column(Text, nullable=False, default="Browser extension")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    revoked_at = Column(DateTime)
