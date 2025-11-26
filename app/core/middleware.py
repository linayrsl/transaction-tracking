import json
import time
from typing import Callable

from fastapi import Request, Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.core.logging import api_logger
from app.core.security import decode_access_token
from app.database import AsyncSessionLocal
from app.models.user import User


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

        # Get client IP (check X-Forwarded-For for proxy scenarios)
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.headers.get("X-Real-IP", "")
        if not client_ip and request.client:
            client_ip = request.client.host

        # Get user agent
        user_agent = request.headers.get("User-Agent", "Unknown")

        # Get user from request state (injected by UserInjectionMiddleware)
        user = getattr(request.state, "user", None)
        user_id = user.id if user else None

        # Call the next middleware or route handler
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            # Log the error and re-raise
            api_logger.error(
                f"{method} {path} - Status: 500 - IP: {client_ip} - "
                f"User: {user_id or 'Anonymous'} - Query: {json.dumps(query_params)} - "
                f"Error: {str(e)}"
            )
            raise

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Log the request (without sensitive body data)
        try:
            log_message = (
                f"{method} {path} - Status: {status_code} - "
                f"IP: {client_ip} - UserID: {user_id or 'Anonymous'} - "
                f"UserAgent: {user_agent} - Query: {json.dumps(query_params)} - "
                f"Duration: {duration_ms}ms"
            )
            api_logger.info(log_message)
        except Exception as e:
            # Don't let logging errors break the API
            print(f"Error logging request: {e}", flush=True)

        return response


class UserInjectionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to parse JWT token and inject User into request state.

    This middleware:
    - Extracts and validates JWT tokens from Authorization header
    - Queries the User from database using email from token
    - Stores User object in request.state.user for downstream use
    - Fails gracefully (sets user=None) for invalid tokens
    - Optimizes by skipping public paths that don't need authentication
    """

    # Paths that don't require user lookup (public endpoints)
    PUBLIC_PATHS = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/register",
        "/login",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and inject user into request state.

        Args:
            request: The incoming request
            call_next: The next middleware or route handler

        Returns:
            Response: The response from the route handler
        """
        # Initialize user as None
        request.state.user = None

        # Skip user lookup for public paths (optimization)
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Try to extract and validate JWT token
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "")

                # Decode JWT token
                payload = decode_access_token(token)
                email = payload.get("sub")

                if email:
                    # Query user from database
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(
                            select(User).where(User.email == email)
                        )
                        user = result.scalar_one_or_none()
                        if user:
                            request.state.user = user
        except Exception:
            # Token is invalid, expired, or user not found
            # Fail gracefully - request.state.user remains None
            # Route handlers will decide if authentication is required
            pass

        return await call_next(request)
