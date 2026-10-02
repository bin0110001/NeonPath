"""add job status and history tracking

Revision ID: 0004_job_status_history
Revises: 0003_job_source_fix
Create Date: 2026-09-30
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_job_status_history"
down_revision = "0003_job_source_fix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add status column to jobs table
    op.add_column('jobs', sa.Column('status', sa.String(32), nullable=False, server_default='DISCOVERED'))
    
    # Create job_status_history table
    op.create_table(
        'job_status_history',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('job_id', sa.String(36), nullable=False),
        sa.Column('old_status', sa.String(32), nullable=True),
        sa.Column('new_status', sa.String(32), nullable=False),
        sa.Column('actor', sa.String(100), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_job_status_history_job_id'), 'job_status_history', ['job_id'], unique=False)
    op.create_index(op.f('ix_job_status_history_timestamp'), 'job_status_history', ['timestamp'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_job_status_history_timestamp'), table_name='job_status_history')
    op.drop_index(op.f('ix_job_status_history_job_id'), table_name='job_status_history')
    
    # Drop job_status_history table
    op.drop_table('job_status_history')
    
    # Remove status column from jobs table
    op.drop_column('jobs', 'status')