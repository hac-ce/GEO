"""公开的存活与就绪检查，不返回数据库路径、凭据或原始异常。"""
import asyncio

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from backend.app.database.session import get_db
from backend.app.database.models import AccessToken, Job, JobSubmission
from backend.app.core.observability import log_event
from backend.app.services.redis_cache import cache_enabled
from backend.app.services.browser_provider import settings as browser_settings

router = APIRouter(prefix="/health", tags=["health"])


# 存活检查不访问外部依赖；保留原入口供前端识别运行模式。
@router.get("")
@router.get("/live")
def liveness(request: Request):
    return {
        "status": "ok", "project": "GEO-learning",
        "mode": getattr(request.app.state, "runtime_mode", "live"),
        "redis": "configured" if getattr(request.app.state, "redis", None) else "disabled",
        "browser_enabled": browser_settings().enabled and getattr(request.app.state, "runtime_mode", "live") != "demo",
    }


# 真实执行一次业务表查询；缓存是可选依赖，失败只降级，不使服务未就绪。
@router.get("/ready")
async def readiness(request: Request, db: AsyncSession = Depends(get_db)):
    database = "unavailable"
    try:
        async with asyncio.timeout(1):
            await db.execute(select(Job.id, Job.request_id, Job.lease_expires_at, Job.collection_method).limit(1))
            await db.execute(select(JobSubmission.id).limit(1))
            await db.execute(select(AccessToken.created_at).limit(1))
        database = "ok"
    except Exception as error:
        log_event("health.database_failed", error_type=type(error).__name__)
    finally:
        try:
            await db.rollback()
        except Exception as error:
            database = "unavailable"
            log_event("health.database_failed", error_type=type(error).__name__)

    redis = "disabled"
    if cache_enabled():
        redis = "unavailable"
        client = getattr(request.app.state, "redis", None)
        if client is not None:
            try:
                async with asyncio.timeout(0.5):
                    if await client.ping():
                        redis = "ok"
            except Exception as error:
                log_event("health.redis_failed", error_type=type(error).__name__)
    ready = database == "ok" and not getattr(request.app.state, "shutting_down", False)
    return JSONResponse({
        "status": "ready" if ready else "not_ready",
        "database": database, "redis": redis,
        "degraded": redis == "unavailable",
    }, status_code=200 if ready else 503)
