"""Authentication and token lifecycle domain service."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import utc_now
from src.core.exceptions import ConflictError, UnauthorizedError
from src.core.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)
from src.domains.audit.service import AuditService
from src.domains.auth.models import RefreshToken, User
from src.domains.auth.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserRegisterRequest,
)


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime instance is offset-aware UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


class AuthService:
    """Encapsulates account registration, credential verification, and token rotation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit_service = AuditService(session)

    async def register(self, payload: UserRegisterRequest) -> User:
        """Register a new user account with uniquely verified email."""
        stmt = select(User).where(User.email == payload.email)
        existing_user = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing_user is not None:
            raise ConflictError(message="A user with this email address already exists.")

        user = User(
            email=payload.email,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            is_active=True,
            is_superuser=False,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def login(
        self,
        payload: LoginRequest,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenPairResponse:
        """Authenticate user credentials and issue an initial rotating token pair."""
        stmt = select(User).where(User.email == payload.email)
        user = (await self.session.execute(stmt)).scalar_one_or_none()

        if user is None or not verify_password(payload.password, user.hashed_password):
            await self.audit_service.record_audit(
                action="auth.login_failed",
                target_resource=f"user:email={payload.email}",
                actor_id=user.id if user else None,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"reason": "invalid_credentials"},
            )
            raise UnauthorizedError(message="Invalid email or password.")

        if not user.is_active:
            await self.audit_service.record_audit(
                action="auth.login_failed",
                target_resource=f"user:{user.id}",
                actor_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"reason": "account_inactive"},
            )
            raise UnauthorizedError(message="User account is inactive.")

        raw_refresh_token = generate_secure_token(32)
        token_hash = hash_token(raw_refresh_token)
        family_id = uuid.uuid4()
        expires_at = utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        refresh_record = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            family_id=family_id,
            is_consumed=False,
            is_revoked=False,
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=expires_at,
        )
        self.session.add(refresh_record)
        await self.session.commit()

        access_token = create_access_token(subject=str(user.id))
        return TokenPairResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def rotate_refresh_token(
        self,
        payload: RefreshTokenRequest,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenPairResponse:
        """Atomically rotate refresh token, enforcing reuse detection and family revocation."""
        token_hash = hash_token(payload.refresh_token)

        # Atomically consume the token to prevent race conditions on concurrent requests
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_consumed.is_(False),
                RefreshToken.is_revoked.is_(False),
            )
            .values(is_consumed=True)
        )
        result = await self.session.execute(stmt)
        cursor_result = cast(CursorResult[Any], result)

        if cursor_result.rowcount == 0:
            # Token was already consumed, revoked, or non-existent; inspect record
            token_record = (
                await self.session.execute(
                    select(RefreshToken).where(RefreshToken.token_hash == token_hash)
                )
            ).scalar_one_or_none()

            if token_record is None:
                raise UnauthorizedError(message="Invalid refresh token.")

            if token_record.is_revoked:
                raise UnauthorizedError(message="Refresh token has been revoked.")

            if token_record.is_consumed:
                revoke_stmt = (
                    update(RefreshToken)
                    .where(RefreshToken.family_id == token_record.family_id)
                    .values(is_revoked=True)
                )
                await self.session.execute(revoke_stmt)
                await self.session.commit()
                await self.audit_service.record_audit(
                    action="auth.token_revoked",
                    target_resource=f"user:{token_record.user_id}",
                    actor_id=token_record.user_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    metadata={"family_id": str(token_record.family_id), "reason": "token_reuse"},
                )
                raise UnauthorizedError(
                    message="Refresh token reuse detected; session has been revoked."
                )

        token_record = (
            await self.session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == token_hash)
            )
        ).scalar_one()

        if ensure_utc(token_record.expires_at) <= utc_now():
            raise UnauthorizedError(message="Refresh token has expired.")

        user = await self.session.get(User, token_record.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError(message="User account is inactive or not found.")

        # Issue next rotating refresh token within the same session family
        new_raw_token = generate_secure_token(32)
        new_token_hash = hash_token(new_raw_token)
        expires_at = utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        new_record = RefreshToken(
            user_id=user.id,
            token_hash=new_token_hash,
            family_id=token_record.family_id,
            is_consumed=False,
            is_revoked=False,
            user_agent=user_agent or token_record.user_agent,
            ip_address=ip_address or token_record.ip_address,
            expires_at=expires_at,
        )
        self.session.add(new_record)
        await self.session.commit()

        access_token = create_access_token(subject=str(user.id))
        return TokenPairResponse(
            access_token=access_token,
            refresh_token=new_raw_token,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def logout(self, payload: RefreshTokenRequest, current_user_id: uuid.UUID) -> None:
        """Invalidate the session family associated with the given refresh token."""
        token_hash = hash_token(payload.refresh_token)
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == current_user_id,
        )
        token_record = (await self.session.execute(stmt)).scalar_one_or_none()

        if token_record is not None:
            revoke_stmt = (
                update(RefreshToken)
                .where(RefreshToken.family_id == token_record.family_id)
                .values(is_revoked=True)
            )
            await self.session.execute(revoke_stmt)
            await self.session.commit()
            await self.audit_service.record_audit(
                action="auth.logout",
                target_resource=f"user:{current_user_id}",
                actor_id=current_user_id,
                metadata={"family_id": str(token_record.family_id)},
            )

    async def change_password(self, user: User, payload: PasswordChangeRequest) -> None:
        """Update password and globally revoke all active refresh token sessions."""
        if not verify_password(payload.current_password, user.hashed_password):
            raise UnauthorizedError(message="Current password is incorrect.")

        user.hashed_password = hash_password(payload.new_password)

        # Globally revoke all sessions for this user
        revoke_all_stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )
        await self.session.execute(revoke_all_stmt)
        await self.session.commit()
        await self.audit_service.record_audit(
            action="auth.password_changed",
            target_resource=f"user:{user.id}",
            actor_id=user.id,
        )
