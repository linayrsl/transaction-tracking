"""Shared pytest fixtures for all tests."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.database import Base, get_db
from app.models.user import User
from app.models.transaction import Transaction
from app.config import settings


# ===== DATABASE CONFIGURATION =====

def get_test_database_url() -> tuple[str, str]:
    """Parse production URL and create test database URL."""
    prod_url = settings.DATABASE_URL
    # Split: postgresql+asyncpg://user:pass@localhost:5432/transaction_tracking
    # Result: postgresql+asyncpg://user:pass@localhost:5432/transaction_tracking_test

    if "//" in prod_url and "/" in prod_url.split("//")[1]:
        base_url = prod_url.rsplit("/", 1)[0]
        db_name = "transaction_tracking_test"
        test_url = f"{base_url}/{db_name}"
        return test_url, db_name
    else:
        raise ValueError(f"Cannot parse DATABASE_URL: {prod_url}")


TEST_DATABASE_URL, TEST_DB_NAME = get_test_database_url()
POSTGRES_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"


# ===== SESSION-SCOPED DATABASE SETUP =====

@pytest.fixture(scope="session")
async def setup_test_database():
    """Create test database, yield engine, then drop database."""
    # Connect to postgres database to create test DB
    admin_engine = create_async_engine(
        POSTGRES_URL,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool
    )

    async with admin_engine.begin() as conn:
        # Drop if exists (from failed previous run)
        await conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
        # Create fresh test database
        await conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))

    await admin_engine.dispose()

    # Create test engine and tables
    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    # Cleanup after all tests
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()

    # Drop test database
    admin_engine = create_async_engine(
        POSTGRES_URL,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool
    )
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"DROP DATABASE {TEST_DB_NAME}"))
    await admin_engine.dispose()


@pytest.fixture(scope="session")
def test_engine(setup_test_database):
    """Get test database engine."""
    return setup_test_database


@pytest.fixture(scope="session")
def TestSessionLocal(test_engine):
    """Create session maker for tests."""
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# ===== DEPENDENCY OVERRIDE =====

@pytest.fixture(scope="session", autouse=True)
def override_get_db(TestSessionLocal):
    """Override FastAPI's get_db dependency and middleware database session."""
    # Override FastAPI dependency
    async def _override_get_db():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    # Override middleware's AsyncSessionLocal
    from app.core import middleware
    from app import database
    original_session = database.AsyncSessionLocal
    database.AsyncSessionLocal = TestSessionLocal
    middleware.AsyncSessionLocal = TestSessionLocal

    yield

    # Restore original
    app.dependency_overrides.clear()
    database.AsyncSessionLocal = original_session
    middleware.AsyncSessionLocal = original_session


# ===== FUNCTION-SCOPED CLEANUP =====

@pytest.fixture(scope="function", autouse=True)
async def cleanup_database(TestSessionLocal):
    """Clean all tables after each test."""
    yield

    async with TestSessionLocal() as session:
        async with session.begin():
            await session.execute(Transaction.__table__.delete())
            await session.execute(User.__table__.delete())


# ===== SHARED FIXTURES =====

@pytest.fixture
async def client():
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session(TestSessionLocal):
    """Get database session."""
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture
async def registered_user(client: AsyncClient):
    """Register a user and return credentials."""
    email = "testuser@example.com"
    password = "TestPass123!"
    await client.post("/register", json={"email": email, "password": password})
    return {"email": email, "password": password}


@pytest.fixture
async def auth_token(registered_user: dict, client: AsyncClient):
    """Get JWT token for authenticated requests."""
    response = await client.post(
        "/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    return response.json()["access_token"]
