import asyncio
import os
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI

from backend.app.api.routes import router as api_router
from backend.app.api.auth import router as auth_router
from backend.app.database.session import engine
from backend.app.services.worker import worker_loop
from backend.app.services.worker import recovery_loop
from backend.app.core.lease_settings import get_lease_settings
from backend.app.services.redis_cache import close_redis, connect_redis, set_client
from backend.app.core.observability import configure_logging
from backend.app.core.request_logging import RequestLoggingMiddleware, internal_error_response
from backend.app.core.rate_limits import AuthRateLimitMiddleware, RateLimiter
from backend.app.services.browser_provider import settings as browser_settings

# 读取并校验每个进程启动的采集 Worker 数量。
def get_worker_count() -> int:
    load_dotenv()
    value = os.getenv("GEO_WORKER_COUNT", "2")

    try:
        count = int(value)
    except ValueError as error:
        raise ValueError("GEO_WORKER_COUNT 必须是正整数") from error

    if count <= 0:
        raise ValueError("GEO_WORKER_COUNT 必须大于 0")

    return count

# 读取并校验关闭服务时等待 Worker 正常结束的秒数。
def get_shutdown_timeout() -> int:
    load_dotenv()
    value = os.getenv("GEO_WORKER_SHUTDOWN_TIMEOUT", "10")

    try:
        timeout = int(value)
    except ValueError as error:
        raise ValueError(
            "GEO_WORKER_SHUTDOWN_TIMEOUT 必须是正整数"
        ) from error

    if timeout <= 0:
        raise ValueError(
            "GEO_WORKER_SHUTDOWN_TIMEOUT 必须大于 0"
        )

    return timeout

# 服务运行期间提供 HTTP 客户端和后台 Worker，退出时按顺序清理资源。
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.shutting_down = False
    app.state.rate_limiter = RateLimiter()
    worker_count = get_worker_count()
    shutdown_timeout = get_shutdown_timeout()
    get_lease_settings()
    browser_settings()
    stop_event = asyncio.Event()
    redis_client = await connect_redis()
    app.state.redis = redis_client
    set_client(redis_client)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            app.state.http_client = client

            async with asyncio.TaskGroup() as group:
                app.state.worker_stop_event = stop_event
                worker_tasks = []

                for index in range(worker_count):
                    task = group.create_task(
                        worker_loop(client, stop_event),
                        name=f"geo-worker-{index + 1}"
                    )
                    worker_tasks.append(task)

                recovery_task = group.create_task(recovery_loop(stop_event, engine), name="geo-job-recovery")

                try:
                    yield
                finally:
                    app.state.shutting_down = True
                    stop_event.set()

                    _, pending = await asyncio.wait(
                        worker_tasks + [recovery_task],
                        timeout=shutdown_timeout
                    )

                    for task in pending:
                        task.cancel()
    finally:
        set_client(None)
        await close_redis(redis_client)
        await engine.dispose()


configure_logging()
app = FastAPI(lifespan=lifespan, exception_handlers={Exception: internal_error_response})
app.add_middleware(AuthRateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
# 应用入口只挂载路由，具体 HTTP 接口定义在各自的路由模块中。
app.include_router(api_router)
app.include_router(auth_router)
