# 根据 ORM 模型创建缺失的数据库表。

import asyncio
from backend.app.database.session import engine
from backend.app.database.models import Base

# 仅用于学习建表；已有数据库的结构升级继续使用 Alembic。
async def main():
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
