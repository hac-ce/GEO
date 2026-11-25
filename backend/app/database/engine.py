"""创建业务数据库引擎，统一 SQLite 的连接约束。"""
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine


# 每个 SQLite 物理连接都开启外键检查，其他数据库使用自身约束机制。
def create_database_engine(url, **options):
    engine = create_async_engine(url, **options)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, connection_record):
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA foreign_keys")
                if cursor.fetchone()[0] != 1:
                    raise RuntimeError("SQLite 外键检查未能开启")
            finally:
                cursor.close()
    return engine
