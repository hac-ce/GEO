"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-15 21:15:31.837061

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# 当前版本及其前一个版本；None 表示这是起点。
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """从空库创建品牌、问题和回答三张表。"""
    op.create_table('brand',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('aliases', sa.JSON(), nullable=False),
    sa.Column('domain', sa.String(length=253), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('prompts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('brand_id', sa.Integer(), nullable=False),
    sa.Column('question', sa.String(length=500), nullable=False),
    sa.ForeignKeyConstraint(['brand_id'], ['brand.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('observations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('prompt_id', sa.Integer(), nullable=False),
    sa.Column('question', sa.String(length=500), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['prompt_id'], ['prompts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """按依赖的相反顺序删除三张表，执行会删除表内数据。"""
    op.drop_table('observations')
    op.drop_table('prompts')
    op.drop_table('brand')
