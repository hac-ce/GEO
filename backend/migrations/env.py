from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from backend.app.database.models import Base

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# 将 ORM 模型定义的表结构交给 Alembic。
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # 在任何结构变更前发现旧孤儿记录；不自动删除或重新分配业务数据。
        if connection.dialect.name == "sqlite":
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                raise RuntimeError("数据库存在外键不一致记录，请先检查并修复后再迁移")
            connection.rollback()
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()
        if connection.dialect.name == "sqlite":
            if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
                raise RuntimeError("迁移后外键检查失败，请停止启动并检查数据库")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
