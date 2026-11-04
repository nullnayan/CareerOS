"""Add feed and provenance lookup indexes without changing user records."""
from alembic import op

revision = "301101_discovery_indexes"
down_revision = "301031_automation"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_discovery_owner_seen", "job_postings", ["user_id", "last_seen_at", "id"]),
    ("ix_discovery_owner_rank", "job_matches", ["user_id", "match_score", "job_id"]),
    ("ix_discovery_occurrence_job", "job_source_occurrences", ["job_id"]),
    ("ix_discovery_owner_url", "job_postings", ["user_id", "apply_url"]),
    ("ix_discovery_owner_runs", "job_refresh_runs", ["user_id", "status", "started_at"]),
]


def upgrade():
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade():
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
