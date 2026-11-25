"""数据库统一保存不带时区的 UTC 时间，接口显式输出 UTC。"""
from datetime import UTC, datetime


# 每次调用都取当前时间，交给 ORM 作为插入默认值或状态变化时间。
def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# 旧数据没有时间时返回 None；Z 表示 UTC，避免浏览器误当成本地时间。
def timestamp_to_string(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
