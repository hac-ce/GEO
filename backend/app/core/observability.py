"""应用 JSON 日志和当前异步调用链的请求编号。"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
import json
import logging
import sys

_request_id: ContextVar[str | None] = ContextVar("geo_request_id", default=None)
logger = logging.getLogger("geo")
SAFE_FIELDS = {
    "user_id", "brand_id", "prompt_id", "job_id", "observation_id", "status",
    "method", "route", "status_code", "duration_ms", "error_type", "operation",
    "database", "redis",
}


# 只输出明确允许的结构化字段，不输出异常正文、堆栈或任意对象。
class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "event": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        data.update(getattr(record, "fields", {}))
        return json.dumps(data, ensure_ascii=False)


# 应用自己使用独立的 logger，不接管第三方库的日志格式。
def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.disabled = False


# 在日志发出时复制编号和白名单字段，避免之后格式化时丢失请求上下文。
def log_event(event: str, *, level: int = logging.INFO, **fields) -> None:
    safe = {key: value for key, value in fields.items()
            if key in SAFE_FIELDS and (value is None or type(value) in (str, int, float, bool))}
    logger.log(level, event, extra={"request_id": current_request_id(), "fields": safe})


# 读取当前请求或任务的关联编号，普通生命周期代码可能没有编号。
def current_request_id() -> str | None:
    return _request_id.get()


# 临时切换当前调用链的编号，并在异常、取消或正常返回后恢复。
@contextmanager
def request_context(request_id: str | None):
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)
