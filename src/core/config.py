"""Global configuration and environment validation using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings validated against environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Project & Work Management API"
    ENVIRONMENT: Literal["local", "test", "staging", "production"] = "local"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Security & Tokens
    SECRET_KEY: str = Field(
        default="change_me_to_a_secure_random_string_32_chars_min",
        min_length=32,
        description="Cryptographic secret key for signing tokens",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=1)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1)

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/rest_db",
        description="Async PostgreSQL connection URL",
    )
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1)
    DATABASE_MAX_OVERFLOW: int = Field(default=20, ge=0)
    DATABASE_POOL_TIMEOUT: int = Field(default=30, ge=1)
    DATABASE_ECHO: bool = False

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = Field(default=60, ge=1)
    AUTH_RATE_LIMIT_PER_MINUTE: int = Field(default=10, ge=1)

    # Admin Panel
    ADMIN_USERNAME: str = Field(default="admin", description="SQLAdmin username")
    ADMIN_PASSWORD: str = Field(
        default="admin_change_me_in_production",
        description="SQLAdmin password",
    )

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT == "test"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()


# Singleton instance for quick access
settings = get_settings()
