"""短时间请求限额：Redis 原子计数，可选的单进程内存回退。"""
import asyncio
from hashlib import sha256
from math import ceil
import os
from time import monotonic

from fastapi import HTTPException, Request
from redis.exceptions import RedisError
from starlette.responses import JSONResponse

from backend.app.core.observability import log_event

# Adapted from fastapi-limiter v0.1.6, Copyright 2020 long2ice, Apache-2.0.
# Changes: EVAL, explicit TTL repair, app-scoped limits and bounded local fallback.
# License: licenses/fastapi-limiter-Apache-2.0.txt
# 一次 Lua 执行完成检查与计数，避免分步调用造成并发竞态。
RATE_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local current = tonumber(redis.call('GET', key) or '0')
if current >= limit then
    local ttl = redis.call('PTTL', key)
    if ttl < 1 then
        redis.call('PEXPIRE', key, window)
        ttl = window
    end
    return ttl
end
if current > 0 then
    redis.call('INCR', key)
else
    redis.call('SET', key, 1, 'PX', window)
end
return 0
"""


# 配置错误在创建限流器时直接报错，不能悄悄关闭限流。
def positive_setting(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} 必须是正整数")
    return value


class RateLimiter:
    def __init__(self, *, limits=None, window_seconds=None, max_entries=4096, clock=monotonic):
        self.limits = limits if limits is not None else {
            "login": positive_setting("GEO_LOGIN_RATE_LIMIT", 10),
            "register": positive_setting("GEO_REGISTER_RATE_LIMIT", 5),
            "collection": positive_setting("GEO_COLLECTION_RATE_LIMIT", 10),
        }
        self.window = window_seconds if window_seconds is not None else positive_setting("GEO_RATE_WINDOW_SECONDS", 60)
        if self.window <= 0 or max_entries <= 0 or any(value <= 0 for value in self.limits.values()):
            raise ValueError("限流配置必须为正数")
        self.max_entries = max_entries
        self.clock = clock
        self.entries = {}
        self.lock = asyncio.Lock()

    # 本地计数也要原子处理，且不能通过不断创建新地址挤掉尚未到期的限额。
    async def local_retry_after(self, key, limit):
        async with self.lock:
            now = self.clock()
            deadline, count = self.entries.get(key, (now + self.window, 0))
            if deadline <= now:
                deadline, count = now + self.window, 0
            if key not in self.entries and len(self.entries) >= self.max_entries:
                self.entries = {k: v for k, v in self.entries.items() if v[0] > now}
                if len(self.entries) >= self.max_entries:
                    return max(1, ceil(min(value[0] for value in self.entries.values()) - now))
            if count >= limit:
                return max(1, ceil(deadline - now))
            self.entries[key] = (deadline, count + 1)
            return 0

    # Redis 失败时使用有界内存回退；不把服务地址或主体原文写入日志。
    async def enforce(self, policy: str, subject: str, redis_client=None):
        digest = sha256(subject.encode("utf-8")).hexdigest()
        key = f"geo:rate:{policy}:{digest}"
        limit = self.limits[policy]
        retry_after = None
        if redis_client is not None:
            try:
                async with asyncio.timeout(0.3):
                    milliseconds = await redis_client.eval(RATE_SCRIPT, 1, key, limit, self.window * 1000)
                if type(milliseconds) is not int or milliseconds < 0:
                    raise RedisError("invalid limiter response")
                retry_after = ceil(milliseconds / 1000)
            except (RedisError, TimeoutError):
                log_event("rate_limit.degraded", operation=policy)
        if retry_after is None:
            retry_after = await self.local_retry_after(key, limit)
        if retry_after:
            log_event("rate_limit.blocked", operation=policy, status_code=429)
            raise HTTPException(429, "请求过于频繁，请稍后重试", headers={"Retry-After": str(retry_after)})


# 每个应用实例拥有自己的回退计数器；正常 lifespan 启动时会主动创建。
def get_rate_limiter(request: Request) -> RateLimiter:
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        limiter = request.app.state.rate_limiter = RateLimiter()
    return limiter


# 两种采集入口共用用户限额，不能换问题或换入口绕过。
async def limit_collection(request: Request, user_id: int):
    await get_rate_limiter(request).enforce(
        "collection", f"user:{user_id}", getattr(request.app.state, "redis", None),
    )


class AuthRateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    # 认证前按连接来源限额；不读取密码，也不信任任意客户端的转发头。
    async def __call__(self, scope, receive, send):
        policies = {"/api/auth/session/login": "login", "/api/auth/jwt/login": "login",
                    "/api/auth/register": "register"}
        policy = policies.get(scope.get("path")) if scope["type"] == "http" and scope.get("method") == "POST" else None
        if policy:
            request = Request(scope)
            subject = "ip:" + (request.client.host if request.client else "unknown")
            try:
                await get_rate_limiter(request).enforce(policy, subject, getattr(request.app.state, "redis", None))
            except HTTPException as error:
                await JSONResponse({"detail": error.detail}, status_code=error.status_code,
                                   headers=error.headers)(scope, receive, send)
                return
        await self.app(scope, receive, send)
