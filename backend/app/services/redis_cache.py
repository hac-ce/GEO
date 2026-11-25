"""Redis 缓存的连接、读写和失效处理。"""

import json
import os
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from backend.app.core.observability import log_event

_client: Redis | None = None


def cache_enabled() -> bool:
    return os.getenv("GEO_REDIS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


async def connect_redis() -> Redis | None:
    """连接 Redis；未启用或连接失败时返回 None，业务仍可使用数据库。"""
    if not cache_enabled():
        return None
    url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    client = Redis.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
    try:
        await client.ping()
    except RedisError:
        await client.aclose()
        log_event("cache.unavailable", operation="connect")
        return None
    return client


def set_client(client: Redis | None) -> None:
    global _client
    _client = client


async def close_redis(client: Redis | None) -> None:
    if client is not None:
        await client.aclose()


async def get_json(key: str) -> Any | None:
    if _client is None:
        return None
    try:
        value = await _client.get(key)
        return None if value is None else json.loads(value)
    except (RedisError, json.JSONDecodeError):
        log_event("cache.unavailable", operation="read")
        return None


async def set_json(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    if _client is None:
        return
    ttl = ttl_seconds or int(os.getenv("GEO_REDIS_TTL", "60"))
    try:
        await _client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except RedisError:
        log_event("cache.unavailable", operation="write")


async def delete_key(key: str) -> None:
    if _client is None:
        return
    try:
        await _client.delete(key)
    except RedisError:
        log_event("cache.unavailable", operation="delete")


def summary_key(brand_id: int) -> str:
    return f"geo:brand-summary:{brand_id}"
