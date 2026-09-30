"""FastAPI application factory, lifespan management, middleware, and operational health checks."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.core.config import settings
from src.core.database import engine
from src.core.exceptions import register_exception_handlers
from src.core.logging import setup_logging
from src.core.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware
from src.domains.audit.router import router as audit_router
from src.domains.auth.router import router as auth_router
from src.domains.notifications.router import router as notifications_router
from src.domains.organizations.router import router as orgs_router
from src.domains.work_management.router import router as work_router

logger = logging.getLogger("api.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context managing startup and graceful shutdown."""
    setup_logging(debug=settings.DEBUG)
    logger.info("Initializing %s in [%s] mode", settings.APP_NAME, settings.ENVIRONMENT)

    yield

    logger.info("Shutting down %s, closing database connection pools", settings.APP_NAME)
    await engine.dispose()


def create_app() -> FastAPI:
    """Build, configure, and return the FastAPI application instance."""
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description=(
            "Production-grade, modular monolith REST API boilerplate "
            "with FastAPI, SQLAlchemy 2.0 Async, and PostgreSQL"
        ),
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    # 1. Custom Exception Handlers (OpenAPI contract-compliant)
    register_exception_handlers(app)

    # 2. Middleware Stack (Executed in reverse order of addition)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    # 3. Operational Endpoints
    @app.get("/health", tags=["Operational"], summary="Liveness probe")
    async def health_check() -> dict[str, str]:
        """Verify the service process is alive."""
        return {"status": "ok"}

    @app.get("/ready", tags=["Operational"], summary="Readiness probe")
    async def readiness_check() -> JSONResponse:
        """Verify the service and its underlying database are ready to serve traffic."""
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "ready", "database": "connected"},
            )
        except Exception as exc:
            logger.error("Readiness check failed: %s", exc)
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "unhealthy", "database": "disconnected"},
            )

    # 4. Domain Routers
    app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
    app.include_router(orgs_router, prefix=settings.API_V1_PREFIX)
    app.include_router(work_router, prefix=settings.API_V1_PREFIX)
    app.include_router(notifications_router, prefix=settings.API_V1_PREFIX)
    app.include_router(audit_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
