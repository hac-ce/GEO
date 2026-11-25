"""记录任务提交时选择的采集方式；历史任务仍使用API。"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("collection_method", sa.String(24), nullable=False, server_default="api"))


def downgrade():
    op.drop_column("jobs", "collection_method")
