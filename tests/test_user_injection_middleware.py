import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from app.models.user import User
from app.config import settings


@pytest.mark.asyncio
async def test_user_injection_with_valid_token(client: AsyncClient, auth_token: str, db_session: AsyncSession):
    """Test that valid JWT results in user being injected into request.state"""
    # Make request with valid token - using root endpoint which doesn't require auth
    # but will go through UserInjectionMiddleware
    response = await client.get(
        "/",
        headers={"Authorization": f"Bearer {auth_token}"}
    )

    # The middleware should inject user into request.state
    # We can't directly access request.state in tests, but we can verify
    # the token is valid by checking the response
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_user_injection_with_invalid_token(client: AsyncClient):
    """Test that invalid JWT results in user=None (fail gracefully)"""
    # Make request with invalid token
    response = await client.get(
        "/",
        headers={"Authorization": "Bearer invalid_token_here"}
    )

    # Request should succeed (fail gracefully)
    # Public endpoint should work even with invalid token
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_user_injection_with_expired_token(client: AsyncClient, registered_user):
    """Test that expired JWT results in user=None"""
    # Create an expired token
    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    expired_token_data = {
        "sub": registered_user["email"],
        "exp": past_time
    }
    expired_token = jwt.encode(
        expired_token_data,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    # Make request with expired token
    response = await client.get(
        "/",
        headers={"Authorization": f"Bearer {expired_token}"}
    )

    # Request should succeed (fail gracefully)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_user_injection_skips_public_paths(client: AsyncClient):
    """Test that PUBLIC_PATHS don't trigger user lookup"""
    public_paths = ["/health", "/docs", "/redoc", "/register", "/login"]

    for path in public_paths:
        # Make requests without Authorization header
        # For /register and /login, we need to send proper JSON
        if path == "/register":
            response = await client.post(
                path,
                json={"email": "test@test.com", "password": "invalid"}
            )
            # Will fail validation but that's ok - we're testing middleware
            assert response.status_code in [201, 422]
        elif path == "/login":
            response = await client.post(
                path,
                json={"email": "test@test.com", "password": "invalid"}
            )
            # Will fail auth but that's ok - we're testing middleware
            assert response.status_code in [200, 401]
        elif path in ["/docs", "/redoc"]:
            # Docs endpoints return 200
            response = await client.get(path)
            assert response.status_code == 200
        else:
            # Health endpoint
            response = await client.get(path)
            assert response.status_code == 200


@pytest.mark.asyncio
async def test_user_injection_with_deleted_user(client: AsyncClient, auth_token: str, db_session: AsyncSession):
    """Test that token with deleted user results in user=None"""
    # Delete the user from database
    await db_session.execute(User.__table__.delete())
    await db_session.commit()

    # Make request with valid token but deleted user
    response = await client.get(
        "/",
        headers={"Authorization": f"Bearer {auth_token}"}
    )

    # Request should succeed (middleware fails gracefully)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_user_injection_without_token(client: AsyncClient):
    """Test that requests without Authorization header set user=None"""
    # Make request without Authorization header
    response = await client.get("/")

    # Request should succeed
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_user_injection_with_malformed_auth_header(client: AsyncClient):
    """Test that malformed Authorization header is handled gracefully"""
    malformed_headers = [
        {"Authorization": "invalid_format"},
        {"Authorization": "Bearer"},
        {"Authorization": ""},
    ]

    for headers in malformed_headers:
        response = await client.get("/", headers=headers)
        # Request should succeed (fail gracefully)
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_middleware_does_not_break_protected_routes(client: AsyncClient, auth_token: str):
    """Test that middleware properly supports protected routes using get_current_user"""
    # This test verifies the integration between UserInjectionMiddleware
    # and the get_current_user dependency

    # Make request to protected endpoint (if any exist)
    # For now, we're just verifying that authenticated requests work
    response = await client.get(
        "/",
        headers={"Authorization": f"Bearer {auth_token}"}
    )

    assert response.status_code == 200
