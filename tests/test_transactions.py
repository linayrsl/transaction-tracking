import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core import middleware as middleware_module
from app.database import get_db
from app.main import app
from app.models.transaction import Transaction
from app.models.user import User

# Test database setup (same pattern as test_auth.py)
TEST_DATABASE_URL = settings.DATABASE_URL
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


# Override get_db dependency and middleware's AsyncSessionLocal
app.dependency_overrides[get_db] = override_get_db
middleware_module.AsyncSessionLocal = TestSessionLocal


@pytest.fixture(scope="function", autouse=True)
async def cleanup_database():
    """Clean tables after each test."""
    yield
    async with TestSessionLocal() as session:
        async with session.begin():
            await session.execute(Transaction.__table__.delete())
            await session.execute(User.__table__.delete())


@pytest.fixture
async def client():
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session():
    """Get database session for direct DB access."""
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture
async def registered_user(client: AsyncClient):
    """Register a user and return credentials."""
    email = "test@example.com"
    password = "TestPass123!"
    await client.post("/register", json={"email": email, "password": password})
    return {"email": email, "password": password}


@pytest.fixture
async def auth_token(client: AsyncClient, registered_user):
    """Get auth token for registered user."""
    response = await client.post(
        "/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    return response.json()["access_token"]


# Test POST /transactions
@pytest.mark.asyncio
async def test_create_transaction_success(
    client: AsyncClient, auth_token: str, db_session: AsyncSession
):
    """Test successful transaction creation."""
    response = await client.post(
        "/transactions/",
        json={"amount": 12.34, "currency": "USD"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["amount"] == 12.34
    assert data["currency"] == "USD"
    assert "id" in data
    assert "created_at" in data

    # Verify in database (stored as cents)
    result = await db_session.execute(
        select(Transaction).where(Transaction.id == data["id"])
    )
    transaction = result.scalar_one_or_none()
    assert transaction is not None
    assert transaction.amount == 1234  # Stored as cents


@pytest.mark.asyncio
async def test_create_transaction_requires_auth(client: AsyncClient):
    """Test that creating transaction requires authentication."""
    response = await client.post(
        "/transactions/", json={"amount": 10.00, "currency": "USD"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_transaction_validates_amount(
    client: AsyncClient, auth_token: str
):
    """Test amount validation (must be positive)."""
    response = await client.post(
        "/transactions/",
        json={"amount": -10.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_transaction_validates_currency(
    client: AsyncClient, auth_token: str
):
    """Test currency validation (3-letter uppercase)."""
    # Test invalid formats (note: lowercase is valid and gets converted to uppercase)
    invalid_currencies = ["US", "USDD", "123", "us$"]

    for currency in invalid_currencies:
        response = await client.post(
            "/transactions/",
            json={"amount": 10.00, "currency": currency},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_transaction_converts_currency_to_uppercase(
    client: AsyncClient, auth_token: str
):
    """Test that lowercase currency is converted to uppercase."""
    response = await client.post(
        "/transactions/",
        json={"amount": 10.00, "currency": "eur"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["currency"] == "EUR"


@pytest.mark.asyncio
async def test_create_transaction_handles_decimal_precision(
    client: AsyncClient, auth_token: str, db_session: AsyncSession
):
    """Test that amounts with 2 decimal places are handled correctly."""
    response = await client.post(
        "/transactions/",
        json={"amount": 99.99, "currency": "GBP"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["amount"] == 99.99

    # Verify stored as 9999 cents
    result = await db_session.execute(
        select(Transaction).where(Transaction.id == data["id"])
    )
    transaction = result.scalar_one()
    assert transaction.amount == 9999


# Test GET /transactions
@pytest.mark.asyncio
async def test_list_transactions_empty(client: AsyncClient, auth_token: str):
    """Test listing transactions when user has none."""
    response = await client.get(
        "/transactions/", headers={"Authorization": f"Bearer {auth_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["per_page"] == 10


@pytest.mark.asyncio
async def test_list_transactions_with_data(client: AsyncClient, auth_token: str):
    """Test listing transactions returns user's transactions."""
    # Create 3 transactions
    for i in range(3):
        await client.post(
            "/transactions/",
            json={"amount": float(i + 1) * 10, "currency": "USD"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    response = await client.get(
        "/transactions/", headers={"Authorization": f"Bearer {auth_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 3
    assert data["total"] == 3
    # Verify ordered by created_at desc (newest first)
    assert data["items"][0]["amount"] == 30.0  # Last created
    assert data["items"][2]["amount"] == 10.0  # First created


@pytest.mark.asyncio
async def test_list_transactions_pagination(client: AsyncClient, auth_token: str):
    """Test pagination works correctly."""
    # Create 15 transactions
    for i in range(15):
        await client.post(
            "/transactions/",
            json={"amount": float(i + 1), "currency": "USD"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    # Test first page (default 10 items)
    response = await client.get(
        "/transactions/?page=1&per_page=10",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] == 15
    assert data["page"] == 1
    assert data["per_page"] == 10
    assert data["total_pages"] == 2

    # Test second page
    response = await client.get(
        "/transactions/?page=2&per_page=10",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    data = response.json()
    assert len(data["items"]) == 5
    assert data["page"] == 2


@pytest.mark.asyncio
async def test_list_transactions_respects_max_per_page(
    client: AsyncClient, auth_token: str
):
    """Test that per_page cannot exceed 50."""
    response = await client.get(
        "/transactions/?per_page=100",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_list_transactions_requires_auth(client: AsyncClient):
    """Test that listing transactions requires authentication."""
    response = await client.get("/transactions/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_transactions_data_isolation(client: AsyncClient):
    """Test that users only see their own transactions."""
    # Register two users
    await client.post(
        "/register", json={"email": "user1@example.com", "password": "Pass123!"}
    )
    await client.post(
        "/register", json={"email": "user2@example.com", "password": "Pass123!"}
    )

    # Get tokens
    token1 = (
        await client.post(
            "/login", json={"email": "user1@example.com", "password": "Pass123!"}
        )
    ).json()["access_token"]

    token2 = (
        await client.post(
            "/login", json={"email": "user2@example.com", "password": "Pass123!"}
        )
    ).json()["access_token"]

    # User1 creates 2 transactions
    await client.post(
        "/transactions/",
        json={"amount": 10.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    await client.post(
        "/transactions/",
        json={"amount": 20.00, "currency": "EUR"},
        headers={"Authorization": f"Bearer {token1}"},
    )

    # User2 creates 1 transaction
    await client.post(
        "/transactions/",
        json={"amount": 30.00, "currency": "GBP"},
        headers={"Authorization": f"Bearer {token2}"},
    )

    # User1 should see only their 2 transactions
    response1 = await client.get(
        "/transactions/", headers={"Authorization": f"Bearer {token1}"}
    )
    data1 = response1.json()
    assert data1["total"] == 2
    assert all(item["currency"] in ["USD", "EUR"] for item in data1["items"])

    # User2 should see only their 1 transaction
    response2 = await client.get(
        "/transactions/", headers={"Authorization": f"Bearer {token2}"}
    )
    data2 = response2.json()
    assert data2["total"] == 1
    assert data2["items"][0]["currency"] == "GBP"
