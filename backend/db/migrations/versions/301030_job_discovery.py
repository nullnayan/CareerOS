"""Job preferences, source health, canonical listings, and JD history."""
from alembic import op
import sqlalchemy as sa
from db.models import JobSearchPreferences, JobSource, JobPosting, JobSourceOccurrence, JobDescriptionRevision, JobRefreshRun

revision = "301030_job_discovery"
down_revision = "301030_personal_latex"
branch_labels = None
depends_on = None


def upgrade():
    for model in (JobSearchPreferences, JobSource, JobPosting, JobSourceOccurrence, JobDescriptionRevision, JobRefreshRun):
        model.__table__.create(bind=op.get_bind(), checkfirst=True)
    op.add_column("job_matches", sa.Column("job_id", sa.String(36), sa.ForeignKey("job_postings.id"), nullable=True))
    op.add_column("job_matches", sa.Column("assessment", sa.JSON(), nullable=True))
    op.add_column("job_matches", sa.Column("state", sa.String(20), nullable=True, server_default="new"))
    op.add_column("job_matches", sa.Column("tailoring_run_id", sa.String(36), sa.ForeignKey("latex_tailoring_runs.id"), nullable=True))
    op.create_index("uq_user_job_match", "job_matches", ["user_id", "job_id"], unique=True)
    op.create_index("uq_job_refresh_running", "job_refresh_runs", ["user_id"], unique=True,
                    postgresql_where=sa.text("status = 'running'"), sqlite_where=sa.text("status = 'running'"))


def downgrade():
    op.drop_index("uq_job_refresh_running", table_name="job_refresh_runs")
    op.drop_index("uq_user_job_match", table_name="job_matches")
    for name in ("tailoring_run_id", "state", "assessment", "job_id"):
        op.drop_column("job_matches", name)
    for table in ("job_refresh_runs", "job_description_revisions", "job_source_occurrences", "job_postings", "job_sources", "job_search_preferences"):
        op.drop_table(table)
