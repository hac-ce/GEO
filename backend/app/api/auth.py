"""认证接口：注册、登录、退出和查询当前用户。"""

from fastapi import APIRouter, Depends

from backend.app.core.auth import (
    UserCreate,
    UserRead,
    auth_backend,
    current_active_user,
    fastapi_users,
)
from backend.app.database.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 复用框架的注册接口，请求使用 JSON，响应不包含密码或密码哈希。
router.include_router(fastapi_users.get_register_router(UserRead, UserCreate))

# 复用框架的登录和退出接口；登录使用 username/password 表单。
router.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/session")
# 兼容旧客户端的地址；调用同一数据库策略，不接受或签发旧 JWT。
router.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/jwt", include_in_schema=False)


# 认证通过后返回当前用户，响应字段由 UserRead 限定。
@router.get("/me", response_model=UserRead)
async def get_me(user: User = Depends(current_active_user)):
    return user
