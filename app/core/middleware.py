import json
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.logging import api_logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all API requests with details including path, parameters,
    timestamp, status code, and response time.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and log details.

        Args:
            request: The incoming request
            call_next: The next middleware or route handler

        Returns:
            Response: The response from the route handler
        """
        # Check if path should be excluded from logging
        if request.url.path in settings.LOG_EXCLUDED_PATHS:
            return await call_next(request)

        # Start timing
        start_time = time.time()

        # Capture request details
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params) if request.query_params else {}

        # Capture request body (with size limit to avoid memory issues)
        body = None
        try:
            if request.method in ["POST", "PUT", "PATCH"]:
                # Read body and restore it for the actual handler
                body_bytes = await request.body()
                if body_bytes:
                    # Limit body size to 10KB for logging
                    if len(body_bytes) <= 10240:
                        try:
                            body = json.loads(body_bytes)
                        except json.JSONDecodeError:
                            body = body_bytes.decode("utf-8", errors="ignore")[:500]
                    else:
                        body = f"<body too large: {len(body_bytes)} bytes>"
        except Exception as e:
            body = f"<error reading body: {str(e)}>"

        # Call the next middleware or route handler
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            # Log the error and re-raise
            api_logger.error(
                f"{method} {path} - Status: 500 - Query: {json.dumps(query_params)} - "
                f"Body: {json.dumps(body) if body else 'None'} - Error: {str(e)}"
            )
            raise

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Log the request
        try:
            log_message = (
                f"{method} {path} - Status: {status_code} - "
                f"Query: {json.dumps(query_params)} - "
                f"Body: {json.dumps(body) if body else 'None'} - "
                f"Duration: {duration_ms}ms"
            )
            api_logger.info(log_message)
        except Exception as e:
            # Don't let logging errors break the API
            print(f"Error logging request: {e}", flush=True)

        return response
