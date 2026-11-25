"""add collection timestamps, model provenance and query indexes

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


# 旧记录的真实时间和来源未知，新增列允许为空，不使用迁移时间回填。
def upgrade() -> None:
    for name in ("created_at", "started_at", "finished_at"):
        op.add_column("jobs", sa.Column(name, sa.DateTime(), nullable=True))
    op.add_column("observations", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.add_column("observations", sa.Column("provider", sa.String(40), nullable=True))
    op.add_column("observations", sa.Column("model", sa.String(200), nullable=True))
    op.create_index("ix_brand_user_id_id", "brand", ["user_id", "id"])
    op.create_index("ix_prompts_brand_id_id", "prompts", ["brand_id", "id"])
    op.create_index("ix_observations_prompt_id_id", "observations", ["prompt_id", "id"])
    op.create_index("ix_jobs_status_id", "jobs", ["status", "id"])
    op.create_index("ix_jobs_prompt_id_id", "jobs", ["prompt_id", "id"])


# 回退会丢弃本版本新增的元数据，原有问题和回答文本保留。
def downgrade() -> None:
    for table, name in (
        ("jobs", "ix_jobs_prompt_id_id"),
        ("jobs", "ix_jobs_status_id"),
        ("observations", "ix_observations_prompt_id_id"),
        ("prompts", "ix_prompts_brand_id_id"),
        ("brand", "ix_brand_user_id_id"),
    ):
        op.drop_index(name, table_name=table)
    for name in ("model", "provider", "created_at"):
        op.drop_column("observations", name)
    for name in ("finished_at", "started_at", "created_at"):
        op.drop_column("jobs", name)
