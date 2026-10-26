"""Initial schema for jobs, attempts, schedules, outbox, workers, and events

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-26 20:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create jobs table
    op.create_table(
        'jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('task_type', sa.String(length=128), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='QUEUED'),
        sa.Column('priority', sa.String(length=16), nullable=False, server_default='DEFAULT'),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False, server_default='300'),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.UniqueConstraint('idempotency_key', name='uq_jobs_idempotency_key'),
    )
    op.create_index('idx_jobs_task_type', 'jobs', ['task_type'])
    op.create_index('idx_jobs_status', 'jobs', ['status'])
    op.create_index('idx_jobs_priority', 'jobs', ['priority'])
    op.create_index('idx_jobs_scheduled_at', 'jobs', ['scheduled_at'])
    op.create_index('idx_jobs_status_priority_created', 'jobs', ['status', 'priority', 'created_at'])

    # 2. Create job_attempts table
    op.create_table(
        'job_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('worker_id', sa.String(length=128), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.String(length=32), nullable=False),
        sa.Column('error_type', sa.String(length=255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('traceback_text', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.UniqueConstraint('job_id', 'attempt_number', name='uq_job_attempts_job_attempt'),
    )
    op.create_index('idx_job_attempts_job_id', 'job_attempts', ['job_id'])
    op.create_index('idx_job_attempts_job_id_attempt', 'job_attempts', ['job_id', 'attempt_number'])

    # 3. Create job_schedules table
    op.create_table(
        'job_schedules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('task_type', sa.String(length=128), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('cron_expression', sa.String(length=64), nullable=False),
        sa.Column('timezone', sa.String(length=64), nullable=False, server_default='UTC'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.UniqueConstraint('name', name='uq_job_schedules_name'),
    )
    op.create_index('idx_job_schedules_task_type', 'job_schedules', ['task_type'])
    op.create_index('idx_job_schedules_next_run_at', 'job_schedules', ['next_run_at'])
    op.create_index('idx_job_schedules_next_run_enabled', 'job_schedules', ['next_run_at', 'enabled'])

    # 4. Create outbox_events table
    op.create_table(
        'outbox_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('publish_attempts', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('idx_outbox_events_job_id', 'outbox_events', ['job_id'])
    op.create_index('idx_outbox_events_created_at', 'outbox_events', ['created_at'])
    op.create_index('idx_outbox_events_unpublished', 'outbox_events', ['published_at', 'created_at'])

    # 5. Create workers table
    op.create_table(
        'workers',
        sa.Column('worker_id', sa.String(length=128), primary_key=True),
        sa.Column('hostname', sa.String(length=255), nullable=False),
        sa.Column('pid', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='ALIVE'),
        sa.Column('current_job_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('jobs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('capabilities_json', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default='{}'),
    )
    op.create_index('idx_workers_status', 'workers', ['status'])
    op.create_index('idx_workers_last_heartbeat_at', 'workers', ['last_heartbeat_at'])
    op.create_index('idx_workers_status_heartbeat', 'workers', ['status', 'last_heartbeat_at'])

    # 6. Create job_events table
    op.create_table(
        'job_events',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('details_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('actor', sa.String(length=128), nullable=False, server_default='SYSTEM'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
    )
    op.create_index('idx_job_events_job_id', 'job_events', ['job_id'])
    op.create_index('idx_job_events_event_type', 'job_events', ['event_type'])
    op.create_index('idx_job_events_job_id_created', 'job_events', ['job_id', 'created_at'])


def downgrade() -> None:
    op.drop_table('job_events')
    op.drop_table('workers')
    op.drop_table('outbox_events')
    op.drop_table('job_schedules')
    op.drop_table('job_attempts')
    op.drop_table('jobs')
