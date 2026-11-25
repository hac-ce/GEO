"""persist user-scoped idempotent job submissions

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


# 新表与 Job 在同一数据库中，唯一约束负责并发竞争时只保留一个任务。
def upgrade() -> None:
    op.create_table(
        "job_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "key_hash", name="uq_job_submissions_user_key"),
    )


# 回退会丢失重复提交保护记录，不能在仍有重试请求时随意执行。
def downgrade() -> None:
    op.drop_table("job_submissions")
