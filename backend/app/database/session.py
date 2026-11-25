# 数据库连接与 Session 管理。

from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database.engine import create_database_engine
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DATABASE = Path(__file__).resolve().parents[3] / "data" / "db" / "geo_learning.db"
if not os.getenv("GEO_DATABASE_URL"):
    DEFAULT_DATABASE.parent.mkdir(parents=True, exist_ok=True)

engine = create_database_engine(
    os.getenv(
        "GEO_DATABASE_URL",
        "sqlite+aiosqlite:///" + DEFAULT_DATABASE.as_posix(),
    ),
    echo=False
)

# 为请求提供 Session，并在依赖退出时关闭；提交由接口负责。
async def get_db():
    async with AsyncSession(engine, expire_on_commit=False) as db:
        yield db
