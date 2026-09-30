"""FastAPI router for authentication and identity endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.rate_limit import auth_endpoint_limiter, rate_limit
from src.domains.auth.dependencies import get_current_active_user
from src.domains.auth.models import User
from src.domains.auth.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserRegisterRequest,
    UserResponse,
)
from src.domains.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    dependencies=[Depends(rate_limit(limiter=auth_endpoint_limiter))],
)
async def register(
    payload: UserRegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Create a new local user account with credentials."""
    service = AuthService(session)
    user = await service.register(payload)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenPairResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate with credentials and receive token pair",
    dependencies=[Depends(rate_limit(limiter=auth_endpoint_limiter))],
)
async def login(
    payload: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPairResponse:
    """Validate credentials and issue an initial rotating access/refresh token pair."""
    service = AuthService(session)
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return await service.login(payload, user_agent=user_agent, ip_address=ip_address)


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and obtain new access token",
    dependencies=[Depends(rate_limit(limiter=auth_endpoint_limiter))],
)
async def refresh_token(
    payload: RefreshTokenRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPairResponse:
    """Rotate an unexpired refresh token, enforcing single-use and reuse detection."""
    service = AuthService(session)
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return await service.rotate_refresh_token(payload, user_agent=user_agent, ip_address=ip_address)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Invalidate current refresh token session",
)
async def logout(
    payload: RefreshTokenRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Invalidate the session family associated with the specified refresh token."""
    service = AuthService(session)
    await service.logout(payload, current_user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Change user password and globally revoke all active refresh token sessions",
    dependencies=[Depends(rate_limit(limiter=auth_endpoint_limiter))],
)
async def change_password(
    payload: PasswordChangeRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Update password and revoke all active sessions for the user across all devices."""
    service = AuthService(session)
    await service.change_password(current_user, payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authenticated user profile",
    tags=["Users"],
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserResponse:
    """Return the profile information for the authenticated user."""
    return UserResponse.model_validate(current_user)
