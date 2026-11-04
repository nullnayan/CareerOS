"""Personal workspace and immutable LaTeX resume revisions."""
from alembic import op
from db.models import WorkspaceSettings, LatexMaster, ConfirmedSkill, LatexTailoringRun

revision = "301030_personal_latex"
down_revision = "2a7b54366447"
branch_labels = None
depends_on = None


def upgrade():
    for table in (WorkspaceSettings, LatexMaster, ConfirmedSkill, LatexTailoringRun):
        table.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade():
    for name in ("latex_tailoring_runs", "confirmed_skills", "latex_masters", "workspace_settings"):
        op.drop_table(name)
