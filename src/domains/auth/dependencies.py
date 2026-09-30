"""FastAPI dependencies for extracting and verifying the authenticated user context."""

import uuid
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import UnauthorizedError
from src.core.security import decode_access_token
from src.domains.auth.models import User

# Optional bearer scheme so missing tokens raise standardized UnauthorizedError
_bearer_security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_security)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Validate JWT access token and return the corresponding database User entity."""
    if credentials is None:
        raise UnauthorizedError(message="Authentication credentials were not provided.")

    if credentials.scheme.lower() != "bearer":
        raise UnauthorizedError(message="Invalid authentication scheme; Bearer token required.")

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError(message="Token signature has expired.") from None
    except jwt.PyJWTError:
        raise UnauthorizedError(message="Could not validate credentials.") from None

    sub: str | None = payload.get("sub")
    if not sub:
        raise UnauthorizedError(message="Token payload is missing subject claim.")

    try:
        user_id = uuid.UUID(sub)
    except (ValueError, TypeError):
        raise UnauthorizedError(message="Subject claim is not a valid user identifier.") from None

    user = await session.get(User, user_id)
    if user is None:
        raise UnauthorizedError(message="User matching token credentials no longer exists.")

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Ensure the authenticated user account is active."""
    if not current_user.is_active:
        raise UnauthorizedError(message="User account is deactivated.")
    return current_user
