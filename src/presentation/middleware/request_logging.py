"""
Structured JSON request logging middleware.

Every request/response cycle is logged as a single structured JSON event
containing method, path, status code, duration, tenant context, user id,
and a unique request id for distributed tracing.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger: structlog.stdlib.BoundLogger = structlog.get_logger("eu_platform.request")


def configure_structlog() -> None:
    """Configure *structlog* for JSON output with standard processors.

    Call once at application startup (from ``create_app``).
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every HTTP request/response with structured JSON fields.

    Captured fields:
        - ``request_id``  -- unique UUID for the request
        - ``method``      -- HTTP method
        - ``path``        -- request path
        - ``status_code`` -- response status
        - ``duration_ms`` -- wall-clock duration in milliseconds
        - ``tenant_id``   -- resolved tenant (if available)
        - ``user_id``     -- authenticated user (if available)
        - ``client_ip``   -- client IP address
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(uuid.uuid4())

        # Attach request_id so downstream handlers can reference it
        request.state.request_id = request_id

        start = time.perf_counter()

        try:
            response: Response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self._log_request(
                request=request,
                request_id=request_id,
                status_code=500,
                duration_ms=duration_ms,
                level="error",
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Inject request-id into the response for client-side correlation
        response.headers["X-Request-ID"] = request_id

        level = "info" if response.status_code < 400 else "warning"
        if response.status_code >= 500:
            level = "error"

        self._log_request(
            request=request,
            request_id=request_id,
            status_code=response.status_code,
            duration_ms=duration_ms,
            level=level,
        )

        return response

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _log_request(
        *,
        request: Request,
        request_id: str,
        status_code: int,
        duration_ms: float,
        level: str = "info",
    ) -> None:
        tenant_id: str | None = None
        tenant_ctx = getattr(request.state, "tenant_context", None)
        if tenant_ctx is not None:
            tenant_id = str(tenant_ctx.tenant_id)

        user_id: str | None = None
        jwt_claims: dict[str, Any] | None = getattr(
            request.state, "jwt_claims", None
        )
        if jwt_claims:
            user_id = jwt_claims.get("sub")

        event_data: dict[str, Any] = {
            "request_id": request_id,
            "method": request.method,
            "path": str(request.url.path),
            "query": str(request.url.query) if request.url.query else None,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "client_ip": request.client.host if request.client else None,
        }

        log_method = getattr(logger, level, logger.info)
        log_method("http_request", **event_data)
