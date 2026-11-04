"""Durable automation, application history, and paired browser profiles."""
from alembic import op
from db.models import (AutomationSettings, AutomationTask, AutomationWorker, JobApplication,
                       ApplicationEvent, AutofillProfile, ExtensionPairing, ExtensionCredential)

revision = "301031_automation"
down_revision = "301030_job_discovery"
branch_labels = None
depends_on = None

MODELS = (AutomationSettings, AutomationTask, AutomationWorker, JobApplication,
          ApplicationEvent, AutofillProfile, ExtensionPairing, ExtensionCredential)


def upgrade():
    for model in MODELS:
        model.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    for model in reversed(MODELS):
        model.__table__.drop(bind=op.get_bind())
