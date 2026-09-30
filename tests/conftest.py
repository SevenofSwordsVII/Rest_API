"""Global Pytest fixtures for unit, integration, and contract tests."""

import os
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import src.domains.audit.models  # noqa: F401
import src.domains.auth.models  # noqa: F401
import src.domains.notifications.models  # noqa: F401
import src.domains.organizations.models  # noqa: F401
import src.domains.work_management.models  # noqa: F401
from src.core.database import Base, get_db
from src.main import create_app

# Use in-memory SQLite for fast isolated tests if not explicitly pointing to PostgreSQL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///:memory:",
)


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create test database engine."""
    engine_kwargs: dict[str, object] = {"future": True}
    if "sqlite" in TEST_DATABASE_URL:
        engine_kwargs.update(
            {
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            }
        )

    engine = create_async_engine(TEST_DATABASE_URL, **engine_kwargs)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    import src.core.database

    original_factory = src.core.database.async_session_factory
    src.core.database.async_session_factory = session_maker

    yield engine

    src.core.database.async_session_factory = original_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def cleanup_database(test_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Ensure database tables are cleaned up after each test."""
    yield
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated database session for direct test assertions."""
    session_maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_maker() as session:
        yield session


@pytest.fixture
def app(test_engine: AsyncEngine) -> FastAPI:
    """FastAPI test application with overridden database dependency."""
    application = create_app()

    session_maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    application.dependency_overrides[get_db] = _override_get_db
    return application


@pytest_asyncio.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Asynchronous HTTP test client using ASGITransport."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
