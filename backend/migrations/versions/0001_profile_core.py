"""create profile core tables

Revision ID: 0001_profile_core
Revises:
Create Date: 2026-09-28
"""

from alembic import op

from careerflow.infrastructure.database.models import Base

revision = "0001_profile_core"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
