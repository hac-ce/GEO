"""persist the request that submitted a collection job

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


# 旧任务无法还原提交请求编号，保留 NULL，不伪造历史追踪信息。
def upgrade() -> None:
    op.add_column("jobs", sa.Column("request_id", sa.String(32), nullable=True))


# 回退只移除关联编号，保留任务和回答内容。
def downgrade() -> None:
    op.drop_column("jobs", "request_id")
