"""add job core tables

Revision ID: 0002_job_core
Revises: 0001_profile_core
Create Date: 2026-09-30
"""
from alembic import op

from careerflow.infrastructure.database.models import Base

# revision identifiers, used by Alembic.
revision = "0002_job_core"
down_revision = "0001_profile_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())