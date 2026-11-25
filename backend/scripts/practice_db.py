# 练习新增和查询品牌；每次运行都会插入一条 apple。

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database.session import engine
from backend.app.database.models import Brand

# 练习使用异步 Session 新增品牌并读取结果。
async def main():
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            brand = Brand(name="apple", aliases=[], domain="apple.com")
            db.add(brand)
            await db.commit()
            statement = select(Brand)
            result = await db.scalars(statement)
            rows = result.all()
            for row in rows:
                print(row.id, row.name, row.aliases, row.domain)
            print(brand.id)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
