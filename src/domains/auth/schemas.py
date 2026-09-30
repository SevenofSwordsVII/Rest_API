"""Pydantic v2 schemas for authentication requests, responses, and token envelopes."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_REGEX = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

EmailType = Annotated[
    str,
    Field(
        pattern=EMAIL_REGEX,
        max_length=255,
        json_schema_extra={"format": "email"},
    ),
]


class UserRegisterRequest(BaseModel):
    """Payload for registering a new user account."""

    email: EmailType = Field(..., description="Unique email address for the account")
    password: str = Field(..., min_length=8, max_length=128, description="Minimum 8 characters")
    full_name: str | None = Field(default=None, max_length=128, description="Optional full name")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class LoginRequest(BaseModel):
    """Payload for authenticating with email and password."""

    email: EmailType = Field(..., description="User email address")
    password: str = Field(..., description="User password")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class RefreshTokenRequest(BaseModel):
    """Payload for rotating refresh token or revoking active session."""

    refresh_token: str = Field(..., min_length=1, description="Raw plaintext refresh token")


class PasswordChangeRequest(BaseModel):
    """Payload for authenticated password change."""

    current_password: str = Field(..., description="Existing plaintext password")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password (minimum 8 characters)",
    )


class TokenPairResponse(BaseModel):
    """OAuth 2.0 bearer token pair response."""

    access_token: str = Field(..., description="Signed JWT access token")
    refresh_token: str = Field(..., description="Rotating refresh token for renewing session")
    token_type: str = Field(default="Bearer", description="OAuth2 token type")
    expires_in: int = Field(..., description="Access token expiration window in seconds")


class UserResponse(BaseModel):
    """Public user identity representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique user UUID")
    email: EmailType = Field(..., description="Registered email address")
    full_name: str | None = Field(default=None, description="User full name")
    is_active: bool = Field(..., description="Whether user account is active")
    created_at: datetime = Field(..., description="Account creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Account last update timestamp (UTC)")
