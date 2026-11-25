"""使用原生 ASGI 中间件串联请求编号和访问日志。"""
import asyncio
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.responses import JSONResponse
from starlette.routing import NoMatchFound
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.app.core.observability import log_event, request_context


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    # 每次 HTTP 请求生成服务端编号，不采信客户端传入的关联编号。
    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = perf_counter()
        status_code = None
        error_type = None

        # 在响应开始时添加编号；不读取请求体、查询参数或响应正文。
        async def send_with_id(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = [(key, value) for key, value in message.get("headers", [])
                           if key.lower() != b"x-request-id"]
                message = {**message, "headers": headers + [(b"x-request-id", request_id.encode("ascii"))]}
            await send(message)

        with request_context(request_id):
            try:
                await self.app(scope, receive, send_with_id)
            except asyncio.CancelledError:
                status_code = status_code or 499
                error_type = "CancelledError"
                raise
            except Exception as error:
                status_code = status_code or 500
                error_type = type(error).__name__
                raise
            finally:
                matched = scope.get("route")
                route = getattr(matched, "path", "<unmatched>")
                name = getattr(matched, "name", None)
                # 新版 FastAPI 的嵌套路由保留原始局部路径；静态地址可按路由名解析完整前缀。
                if name and not scope.get("path_params"):
                    try:
                        route = str(scope["app"].url_path_for(name))
                    except NoMatchFound:
                        pass
                log_event("http.request", level=logging.ERROR if error_type or (status_code or 0) >= 500 else logging.INFO,
                          method=scope.get("method"), route=route, status_code=status_code,
                          duration_ms=round((perf_counter() - started) * 1000, 2), error_type=error_type)
                if name == "auth:database.login" and status_code == 400:
                    log_event("auth.login_rejected", status_code=400)
                if name == "auth:database.logout" and status_code == 204:
                    log_event("auth.logged_out", status_code=204)


# 未处理异常由框架的最外层错误处理器生成 500，也带上已经生成的编号。
async def internal_error_response(request: Request, error: Exception):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        {"detail": "服务器内部错误", "request_id": request_id}, status_code=500,
        headers={"X-Request-ID": request_id} if request_id else {},
    )
