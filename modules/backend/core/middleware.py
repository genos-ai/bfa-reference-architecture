"""
Request Context Middleware.

Middleware for request tracking, timing, source identification, and context propagation.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from modules.backend.core.logging import VALID_SOURCES, bind_context, clear_context, get_logger
from modules.backend.core.utils import utc_now

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds request context to every request.

    Features:
    - Generates or propagates request ID (X-Request-ID header)
    - Extracts source identifier (X-Frontend-ID header)
    - Records request timing (X-Response-Time header)
    - Binds request context to structlog for automatic inclusion in logs
    - Stores context in request.state for access by handlers

    Headers:
    - X-Request-ID: Unique request identifier (generated if not provided)
    - X-Frontend-ID: Source identifier (web, cli, mobile, api, internal, etc.)
    - X-Response-Time: Response duration in milliseconds

    Usage:
        All logs within a request will automatically include:
        - request_id: Unique identifier for the request
        - source: Origin that sent the request
        - method: HTTP method
        - path: Request path

        Access in endpoints:
            request.state.request_id
            request.state.source
            request.state.start_time
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request with context tracking."""
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        raw_source = request.headers.get("X-Frontend-ID", "").lower().strip() or None

        if raw_source is not None and raw_source not in VALID_SOURCES:
            logger.warning(
                "Invalid X-Frontend-ID header, ignoring",
                extra={"raw_source": raw_source, "valid_sources": sorted(VALID_SOURCES)},
            )
            raw_source = None

        start_time = utc_now()

        request.state.request_id = request_id
        request.state.source = raw_source
        request.state.start_time = start_time

        clear_context()
        context: dict = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        }
        if raw_source is not None:
            context["source"] = raw_source
        bind_context(**context)

        logger.debug(
            "Request started",
            extra={
                "client_host": request.client.host if request.client else None,
                "user_agent": request.headers.get("User-Agent"),
            },
        )

        try:
            response = await call_next(request)

            duration_ms = int((utc_now() - start_time).total_seconds() * 1000)

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms}ms"

            logger.debug(
                "Request completed",
                extra={
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

            return response

        except Exception as exc:
            duration_ms = int((utc_now() - start_time).total_seconds() * 1000)

            logger.error(
                "Request failed with exception",
                extra={
                    "duration_ms": duration_ms,
                    "error_type": type(exc).__name__,
                },
            )

            raise

        finally:
            clear_context()
