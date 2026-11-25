"""认证配置：用户模型、数据库依赖及可撤销的数据库令牌策略。"""
from fastapi import Depends
from fastapi_users import (
    BaseUserManager,
    IntegerIDMixin,
    FastAPIUsers,
    schemas,
)
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
)
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_db
from backend.app.database.models import AccessToken, User
from backend.app.core.observability import log_event


# 注册成功时返回的用户信息，不包含密码和密码哈希。
class UserRead(schemas.BaseUser[int]):
    pass


# 校验注册时提交的邮箱和密码。
class UserCreate(schemas.BaseUserCreate):
    pass

# 为 FastAPI Users 提供操作用户表的数据库适配器。
async def get_user_db(db: AsyncSession = Depends(get_db)):
    yield SQLAlchemyUserDatabase(db, User)

# 使用框架提供的用户管理逻辑，用户编号采用整数。
class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    # 框架确认用户已保存后调用，不记录注册邮箱、密码或哈希。
    async def on_after_register(self, user, request=None):
        log_event("auth.registered", user_id=user.id)

    # 框架验证密码并签发登录响应后调用，不记录令牌。
    async def on_after_login(self, user, request=None, response=None):
        log_event("auth.logged_in", user_id=user.id)

# 为后续认证流程提供用户管理器。
async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)

# 使用 Authorization: Bearer 请求头传递登录令牌。
bearer_transport = BearerTransport(
    tokenUrl="/api/auth/session/login",
)

# 将同一请求的 Session 交给令牌表适配器，不另建数据库连接。
async def get_access_token_db(db: AsyncSession = Depends(get_db)):
    yield SQLAlchemyAccessTokenDatabase(db, AccessToken)


# 框架生成随机令牌并落库；每次读取检查创建时间，登录一小时后过期。
def get_database_strategy(access_token_db=Depends(get_access_token_db)):
    return DatabaseStrategy(access_token_db, lifetime_seconds=3600)

# Bearer 只决定令牌如何传递；数据库策略决定如何签发、验证和撤销。
auth_backend = AuthenticationBackend(
    name="database",
    transport=bearer_transport,
    get_strategy=get_database_strategy,
)

fastapi_users = FastAPIUsers[User, int](
    get_user_manager,
    [auth_backend],
)

# 生成认证依赖；只有接口使用 Depends 时才会执行当前用户检查。
current_active_user = fastapi_users.current_user(active=True)
