"""HTTP middleware for correlation ID tracking, request timing, and access logging."""

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.core.logging import correlation_id_ctx

logger = logging.getLogger("api.access")

CORRELATION_ID_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request has a correlation ID, bound to context and response headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        corr_id = request.headers.get(CORRELATION_ID_HEADER)
        if not corr_id:
            corr_id = str(uuid.uuid4())

        token = correlation_id_ctx.set(corr_id)
        try:
            response = await call_next(request)
            response.headers[CORRELATION_ID_HEADER] = corr_id
            return response
        finally:
            correlation_id_ctx.reset(token)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware recording latency and HTTP access logs with correlation ID."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        response: Response | None = None
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            client_host = request.client.host if request.client else "unknown"

            # Avoid logging excessive noise for pure health checks in production
            if request.url.path not in ("/health",):
                logger.info(
                    f"{request.method} {request.url.path} -> {status_code} in {duration_ms:.2f}ms",
                    extra={
                        "http_method": request.method,
                        "http_path": request.url.path,
                        "http_status": status_code,
                        "duration_ms": round(duration_ms, 2),
                        "client_ip": client_host,
                    },
                )
