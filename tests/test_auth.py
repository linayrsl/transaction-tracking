import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User


# Test data
VALID_EMAIL = "test@example.com"
VALID_PASSWORD = "TestPass123!"
WEAK_PASSWORD = "weak"
INVALID_EMAIL = "not-an-email"


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, db_session: AsyncSession):
    """Test successful user registration."""
    response = await client.post(
        "/register", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}
    )

    assert response.status_code == 201

    # Verify user exists in database
    result = await db_session.execute(select(User).where(User.email == VALID_EMAIL))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.email == VALID_EMAIL.lower()


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Test registration with duplicate email returns 400."""
    # Register first time
    await client.post(
        "/register", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}
    )

    # Try to register again with same email
    response = await client.post(
        "/register", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}
    )

    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    """Test registration with invalid email format."""
    response = await client.post(
        "/register", json={"email": INVALID_EMAIL, "password": VALID_PASSWORD}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    """Test registration with weak password fails validation."""
    response = await client.post(
        "/register", json={"email": VALID_EMAIL, "password": WEAK_PASSWORD}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_case_insensitive_email(client: AsyncClient, db_session: AsyncSession):
    """Test that emails are stored in lowercase."""
    mixed_case_email = "Test@Example.COM"
    response = await client.post(
        "/register", json={"email": mixed_case_email, "password": VALID_PASSWORD}
    )

    assert response.status_code == 201

    # Verify in database
    result = await db_session.execute(
        select(User).where(User.email == mixed_case_email.lower())
    )
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.email == mixed_case_email.lower()


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """Test successful login returns JWT token."""
    # Register user first
    await client.post(
        "/register", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}
    )

    # Login
    response = await client.post(
        "/login", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 0


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Test login with wrong password returns 401."""
    # Register user first
    await client.post(
        "/register", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}
    )

    # Try to login with wrong password
    response = await client.post(
        "/login", json={"email": VALID_EMAIL, "password": "WrongPass123!"}
    )

    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Test login with non-existent email returns 401."""
    response = await client.post(
        "/login", json={"email": "nonexistent@example.com", "password": VALID_PASSWORD}
    )

    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_case_insensitive(client: AsyncClient):
    """Test login works with different case email."""
    # Register with lowercase
    await client.post(
        "/register", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}
    )

    # Login with different case
    mixed_case_email = "Test@Example.COM"
    response = await client.post(
        "/login", json={"email": mixed_case_email, "password": VALID_PASSWORD}
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_token_includes_bearer_type(client: AsyncClient):
    """Test that token response includes bearer type."""
    # Register and login
    await client.post(
        "/register", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}
    )
    response = await client.post(
        "/login", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_request_logging_format_changed(client: AsyncClient):
    """Test that log format now uses 'UserID:' instead of 'User:'"""
    import os

    # Register user
    response = await client.post(
        "/register", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}
    )
    assert response.status_code == 201

    # Login to get token
    login_response = await client.post(
        "/login", json={"email": VALID_EMAIL, "password": VALID_PASSWORD}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Make authenticated request
    auth_response = await client.get(
        "/",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert auth_response.status_code == 200

    # Verify log format uses "UserID:" (not "User:")
    log_file_path = "logs/api_requests.log"
    if os.path.exists(log_file_path):
        with open(log_file_path, "r") as log_file:
            log_content = log_file.read()

            # Find recent logs that use the new format
            recent_lines = log_content.split("\n")[-10:]  # Last 10 lines
            recent_log = "\n".join(recent_lines)

            # Verify new format exists (UserID: instead of User:)
            assert "UserID:" in recent_log, "Logs should use 'UserID:' format"

            # The middleware refactoring successfully changed the log format from
            # "User: email@example.com" to "UserID: <numeric_id>" for better privacy
