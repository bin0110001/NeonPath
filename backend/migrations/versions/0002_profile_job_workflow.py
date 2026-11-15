"""profile-scoped job workflow

Revision ID: 0002_profile_job_workflow
Revises: 0001_baseline
Create Date: 2026-11-14

Data impact: the previous global ``jobs.status`` held review decisions (SHORTLISTED,
REJECTED, SAVED, ARCHIVED) that belonged to nobody in particular. They are copied to
every existing profile as ``profile_jobs`` rows, existing history rows are duplicated
per profile (originals removed, since a history row must name a profile), and
``jobs.status`` is reset to READY_FOR_REVIEW for those jobs. With no profiles, such
legacy decisions and history are dropped. Downgrade cannot restore global decisions.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_profile_job_workflow"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

WORKFLOW_STATES = "('SHORTLISTED', 'REJECTED', 'SAVED', 'ARCHIVED')"


def upgrade() -> None:
    op.create_table(
        "profile_jobs",
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("profile_id", "job_id"),
    )
    op.add_column(
        "job_status_history", sa.Column("profile_id", sa.String(length=36), nullable=True)
    )
    op.execute(
        f"""
        INSERT INTO profile_jobs (profile_id, job_id, status)
        SELECT p.id, j.id, j.status FROM jobs j CROSS JOIN profiles p
        WHERE j.status IN {WORKFLOW_STATES}
        """
    )
    op.execute(
        """
        INSERT INTO job_status_history
            (id, job_id, profile_id, old_status, new_status, actor, reason, timestamp)
        SELECT gen_random_uuid()::text, h.job_id, p.id, h.old_status, h.new_status,
               h.actor, h.reason, h.timestamp
        FROM job_status_history h CROSS JOIN profiles p
        WHERE h.profile_id IS NULL
        """
    )
    op.execute("DELETE FROM job_status_history WHERE profile_id IS NULL")
    op.execute(f"UPDATE jobs SET status = 'READY_FOR_REVIEW' WHERE status IN {WORKFLOW_STATES}")
    op.alter_column("job_status_history", "profile_id", nullable=False)
    op.create_index(
        op.f("ix_job_status_history_profile_id"),
        "job_status_history",
        ["profile_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_job_status_history_profile_id", "job_status_history", "profiles", ["profile_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_job_status_history_profile_id", "job_status_history", type_="foreignkey")
    op.drop_index(op.f("ix_job_status_history_profile_id"), table_name="job_status_history")
    op.drop_column("job_status_history", "profile_id")
    op.drop_table("profile_jobs")
