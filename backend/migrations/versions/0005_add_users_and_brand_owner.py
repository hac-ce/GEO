"""create users and brand ownership

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    with op.batch_alter_table("brand") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_brand_user_id_users", "users", ["user_id"], ["id"])

def downgrade() -> None:
    with op.batch_alter_table("brand") as batch_op:
        batch_op.drop_constraint("fk_brand_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")
    op.drop_table("users")
