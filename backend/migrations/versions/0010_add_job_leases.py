"""add fenced job execution leases

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


# 历史任务没有可信执行凭证，保留 NULL，不在迁移时改写运行状态。
def upgrade() -> None:
    op.add_column("jobs", sa.Column("execution_token", sa.String(32), nullable=True))
    op.add_column("jobs", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    op.add_column("jobs", sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_jobs_status_lease", "jobs", ["status", "lease_expires_at"])


# 回退需停止新 Worker；否则会丢失正在使用的执行权信息。
def downgrade() -> None:
    op.drop_index("ix_jobs_status_lease", table_name="jobs")
    for name in ("lease_expires_at", "heartbeat_at", "execution_token"):
        op.drop_column("jobs", name)
