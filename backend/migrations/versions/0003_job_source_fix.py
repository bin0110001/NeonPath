"""fix job source record last_seen_at default

Revision ID: 0003_job_source_fix
Revises: 0002_job_core
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_job_source_fix"
down_revision = "0002_job_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add server default to last_seen_at column
    op.alter_column('job_source_records', 'last_seen_at',
                    server_default=sa.text('CURRENT_TIMESTAMP'))


def downgrade() -> None:
    # Remove server default from last_seen_at column
    op.alter_column('job_source_records', 'last_seen_at',
                    server_default=None)