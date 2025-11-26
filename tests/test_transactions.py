import pytest
import httpx
import respx
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

    # Verify in database (stored as micro cents)
    result = await db_session.execute(
        select(Transaction).where(Transaction.id == data["id"])
    )
    transaction = result.scalar_one_or_none()
    assert transaction is not None
    assert transaction.amount == 123400  # Stored as micro cents


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

    # Verify stored as 999900 micro cents
    result = await db_session.execute(
        select(Transaction).where(Transaction.id == data["id"])
    )
    transaction = result.scalar_one()
    assert transaction.amount == 999900


@pytest.mark.asyncio
async def test_create_transaction_unsupported_currency(
    client: AsyncClient, auth_token: str
):
    """Test that unsupported currency code is rejected."""
    response = await client.post(
        "/transactions/",
        json={"amount": 100.00, "currency": "XYZ"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 422
    assert "Currency code not supported" in response.json()["detail"][0]["msg"]


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


# Test GET /transactions/summary/


@pytest.mark.asyncio
async def test_summary_empty(client: AsyncClient, auth_token: str):
    """Test summary returns empty array when user has no transactions."""
    response = await client.get(
        "/transactions/summary/",
        headers={"Authorization": f"Bearer {auth_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data == []


@pytest.mark.asyncio
async def test_summary_single_currency(client: AsyncClient, auth_token: str):
    """Test summary with transactions in single currency."""
    # Create 3 USD transactions
    amounts = [10.50, 25.75, 14.25]
    for amount in amounts:
        await client.post(
            "/transactions/",
            json={"amount": amount, "currency": "USD"},
            headers={"Authorization": f"Bearer {auth_token}"}
        )

    response = await client.get(
        "/transactions/summary/",
        headers={"Authorization": f"Bearer {auth_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["currency"] == "USD"
    assert data[0]["total"] == 50.50  # 10.50 + 25.75 + 14.25


@pytest.mark.asyncio
async def test_summary_multiple_currencies(client: AsyncClient, auth_token: str):
    """Test summary aggregates correctly across multiple currencies."""
    # Create transactions in different currencies
    transactions = [
        (100.00, "USD"),
        (50.50, "USD"),
        (75.25, "EUR"),
        (25.00, "EUR"),
        (200.00, "GBP"),
    ]

    for amount, currency in transactions:
        await client.post(
            "/transactions/",
            json={"amount": amount, "currency": currency},
            headers={"Authorization": f"Bearer {auth_token}"}
        )

    response = await client.get(
        "/transactions/summary/",
        headers={"Authorization": f"Bearer {auth_token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # Verify correct aggregation
    assert len(data) == 3

    # Verify alphabetical ordering (EUR, GBP, USD)
    assert data[0]["currency"] == "EUR"
    assert data[0]["total"] == 100.25  # 75.25 + 25.00

    assert data[1]["currency"] == "GBP"
    assert data[1]["total"] == 200.00

    assert data[2]["currency"] == "USD"
    assert data[2]["total"] == 150.50  # 100.00 + 50.50


@pytest.mark.asyncio
async def test_summary_requires_auth(client: AsyncClient):
    """Test that summary endpoint requires authentication."""
    response = await client.get("/transactions/summary/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_summary_data_isolation(client: AsyncClient):
    """Test that summary only includes current user's transactions."""
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

    # User1 creates USD and EUR transactions
    await client.post(
        "/transactions/",
        json={"amount": 100.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {token1}"}
    )
    await client.post(
        "/transactions/",
        json={"amount": 50.00, "currency": "EUR"},
        headers={"Authorization": f"Bearer {token1}"}
    )

    # User2 creates USD and GBP transactions
    await client.post(
        "/transactions/",
        json={"amount": 200.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {token2}"}
    )
    await client.post(
        "/transactions/",
        json={"amount": 75.00, "currency": "GBP"},
        headers={"Authorization": f"Bearer {token2}"}
    )

    # User1 should see only their summary
    response1 = await client.get(
        "/transactions/summary/",
        headers={"Authorization": f"Bearer {token1}"}
    )
    data1 = response1.json()
    assert len(data1) == 2
    assert data1[0]["currency"] == "EUR"
    assert data1[0]["total"] == 50.00
    assert data1[1]["currency"] == "USD"
    assert data1[1]["total"] == 100.00

    # User2 should see only their summary
    response2 = await client.get(
        "/transactions/summary/",
        headers={"Authorization": f"Bearer {token2}"}
    )
    data2 = response2.json()
    assert len(data2) == 2
    assert data2[0]["currency"] == "GBP"
    assert data2[0]["total"] == 75.00
    assert data2[1]["currency"] == "USD"
    assert data2[1]["total"] == 200.00


@pytest.mark.asyncio
async def test_summary_handles_decimal_precision(
    client: AsyncClient, auth_token: str
):
    """Test that summary correctly aggregates amounts with decimal precision."""
    # Create transactions with various decimal amounts
    amounts = [10.99, 20.01, 5.50, 3.50]  # Should sum to 40.00

    for amount in amounts:
        await client.post(
            "/transactions/",
            json={"amount": amount, "currency": "USD"},
            headers={"Authorization": f"Bearer {auth_token}"}
        )

    response = await client.get(
        "/transactions/summary/",
        headers={"Authorization": f"Bearer {auth_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["currency"] == "USD"
    assert data[0]["total"] == 40.00


# Test GET /convert/{transaction_id}/{target_currency}


@pytest.mark.asyncio
@respx.mock
async def test_convert_transaction_success(client: AsyncClient, auth_token: str):
    """Test successful currency conversion."""
    # Create a USD transaction
    create_response = await client.post(
        "/transactions/",
        json={"amount": 100.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    transaction_id = create_response.json()["id"]
    original_created_at = create_response.json()["created_at"]

    # Mock currency conversion API
    from app.config import settings
    respx.get(
        f"https://v6.exchangerate-api.com/v6/{settings.EXCHANGE_RATE_API_KEY}/pair/USD/EUR/100.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 0.85,
                "conversion_result": 85.0,
            },
        )
    )

    # Convert to EUR
    response = await client.get(
        f"/convert/{transaction_id}/EUR",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == transaction_id
    assert data["amount"] == 85.0
    assert data["currency"] == "EUR"
    assert data["created_at"] == original_created_at


@pytest.mark.asyncio
async def test_convert_transaction_same_currency(client: AsyncClient, auth_token: str):
    """Test that same currency returns original without API call."""
    # Create transaction
    create_response = await client.post(
        "/transactions/",
        json={"amount": 50.00, "currency": "GBP"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    transaction_id = create_response.json()["id"]

    # Convert to same currency (no mock needed - shouldn't be called)
    response = await client.get(
        f"/convert/{transaction_id}/GBP",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["amount"] == 50.00
    assert data["currency"] == "GBP"


@pytest.mark.asyncio
async def test_convert_transaction_not_found(client: AsyncClient, auth_token: str):
    """Test 404 for non-existent transaction."""
    response = await client.get(
        "/convert/99999/EUR",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Transaction not found"


@pytest.mark.asyncio
async def test_convert_transaction_wrong_user(client: AsyncClient):
    """Test that users cannot convert other users' transactions."""
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

    # User1 creates transaction
    create_response = await client.post(
        "/transactions/",
        json={"amount": 100.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {token1}"},
    )
    transaction_id = create_response.json()["id"]

    # User2 tries to convert user1's transaction
    response = await client.get(
        f"/convert/{transaction_id}/EUR",
        headers={"Authorization": f"Bearer {token2}"},
    )

    # Should get 404 (not 403) to avoid leaking transaction existence
    assert response.status_code == 404
    assert response.json()["detail"] == "Transaction not found"


@pytest.mark.asyncio
async def test_convert_transaction_invalid_currency_format(
    client: AsyncClient, auth_token: str
):
    """Test validation of target currency format."""
    # Create transaction
    create_response = await client.post(
        "/transactions/",
        json={"amount": 100.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    transaction_id = create_response.json()["id"]

    # Test invalid formats
    invalid_currencies = ["US", "USDD", "123", "us$"]

    for currency in invalid_currencies:
        response = await client.get(
            f"/convert/{transaction_id}/{currency}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
@respx.mock
async def test_convert_transaction_lowercase_currency(
    client: AsyncClient, auth_token: str
):
    """Test that lowercase currency is converted to uppercase."""
    # Create transaction
    create_response = await client.post(
        "/transactions/",
        json={"amount": 100.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    transaction_id = create_response.json()["id"]

    # Mock API (should be called with uppercase)
    from app.config import settings
    respx.get(
        f"https://v6.exchangerate-api.com/v6/{settings.EXCHANGE_RATE_API_KEY}/pair/USD/EUR/100.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 0.85,
                "conversion_result": 85.0,
            },
        )
    )

    # Call with lowercase
    response = await client.get(
        f"/convert/{transaction_id}/eur",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    assert response.json()["currency"] == "EUR"


@pytest.mark.asyncio
@respx.mock
async def test_convert_transaction_api_failure(client: AsyncClient, auth_token: str):
    """Test 503 when currency conversion API fails."""
    # Create transaction
    create_response = await client.post(
        "/transactions/",
        json={"amount": 100.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    transaction_id = create_response.json()["id"]

    # Mock API error
    from app.config import settings
    respx.get(
        f"https://v6.exchangerate-api.com/v6/{settings.EXCHANGE_RATE_API_KEY}/pair/USD/EUR/100.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "error",
                "error-type": "quota-reached",
            },
        )
    )

    # Convert should fail
    response = await client.get(
        f"/convert/{transaction_id}/EUR",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 503
    assert "Currency conversion failed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_convert_transaction_requires_auth(client: AsyncClient):
    """Test that conversion requires authentication."""
    response = await client.get("/convert/1/EUR")
    assert response.status_code == 401


@pytest.mark.asyncio
@respx.mock
async def test_convert_transaction_preserves_metadata(
    client: AsyncClient, auth_token: str
):
    """Test that conversion preserves original transaction metadata."""
    # Create transaction
    create_response = await client.post(
        "/transactions/",
        json={"amount": 100.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    original = create_response.json()

    # Mock conversion
    from app.config import settings
    respx.get(
        f"https://v6.exchangerate-api.com/v6/{settings.EXCHANGE_RATE_API_KEY}/pair/USD/EUR/100.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 0.85,
                "conversion_result": 85.0,
            },
        )
    )

    # Convert
    response = await client.get(
        f"/convert/{original['id']}/EUR",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    data = response.json()
    # Metadata should match original
    assert data["id"] == original["id"]
    assert data["created_at"] == original["created_at"]
    # Only amount and currency should change
    assert data["amount"] != original["amount"]
    assert data["currency"] != original["currency"]


@pytest.mark.asyncio
@respx.mock
async def test_convert_transaction_precision(client: AsyncClient, auth_token: str):
    """Test that conversion preserves precision correctly."""
    # Create transaction with precise amount
    create_response = await client.post(
        "/transactions/",
        json={"amount": 12.34, "currency": "USD"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    transaction_id = create_response.json()["id"]

    # Mock conversion with precise result
    from app.config import settings
    respx.get(
        f"https://v6.exchangerate-api.com/v6/{settings.EXCHANGE_RATE_API_KEY}/pair/USD/GBP/12.34"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 0.79,
                "conversion_result": 9.7486,
            },
        )
    )

    # Convert
    response = await client.get(
        f"/convert/{transaction_id}/GBP",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    # Should handle precision correctly
    assert response.json()["amount"] == 9.7486


@pytest.mark.asyncio
async def test_convert_transaction_unsupported_currency(
    client: AsyncClient, auth_token: str
):
    """Test that unsupported currency code is rejected."""
    # Create transaction
    create_response = await client.post(
        "/transactions/",
        json={"amount": 100.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    transaction_id = create_response.json()["id"]

    # Try to convert to unsupported currency (no API mock needed)
    response = await client.get(
        f"/convert/{transaction_id}/ABC",  # Invalid currency
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 422
    assert "Currency code not supported" in response.json()["detail"]


@pytest.mark.asyncio
@respx.mock
async def test_convert_transaction_large_amount(client: AsyncClient, auth_token: str):
    """Test conversion of large amounts."""
    # Create transaction with large amount
    create_response = await client.post(
        "/transactions/",
        json={"amount": 1000000.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    transaction_id = create_response.json()["id"]

    # Mock conversion
    from app.config import settings
    respx.get(
        f"https://v6.exchangerate-api.com/v6/{settings.EXCHANGE_RATE_API_KEY}/pair/USD/EUR/1000000.0"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "result": "success",
                "conversion_rate": 0.85,
                "conversion_result": 850000.0,
            },
        )
    )

    # Convert
    response = await client.get(
        f"/convert/{transaction_id}/EUR",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    assert response.json()["amount"] == 850000.0


@pytest.mark.asyncio
async def test_convert_transaction_unsupported_target_currency(
    client: AsyncClient, auth_token: str
):
    """Test that unsupported target currency is rejected."""
    # Create a valid USD transaction
    create_response = await client.post(
        "/transactions/",
        json={"amount": 100.00, "currency": "USD"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    transaction_id = create_response.json()["id"]

    # Try to convert to unsupported currency
    response = await client.get(
        f"/convert/{transaction_id}/XYZ",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 422
    assert "Currency code not supported" in response.json()["detail"]
