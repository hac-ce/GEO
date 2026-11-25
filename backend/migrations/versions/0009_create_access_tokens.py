"""create revocable database login tokens

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa
from fastapi_users_db_sqlalchemy.generics import TIMESTAMPAware

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


# 表结构与 FastAPI Users 适配器一致，不改现有用户、密码或业务数据。
def upgrade() -> None:
    op.create_table(
        "auth_access_tokens",
        sa.Column("token", sa.String(43), primary_key=True),
        sa.Column("created_at", TIMESTAMPAware(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_auth_access_tokens_created_at", "auth_access_tokens", ["created_at"])
    op.create_index("ix_auth_access_tokens_user_id", "auth_access_tokens", ["user_id"])


# 回退会清空当前所有登录令牌，但不删除用户和业务记录。
def downgrade() -> None:
    op.drop_table("auth_access_tokens")
