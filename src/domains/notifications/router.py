"""FastAPI router for Notification endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.pagination import PaginationParams
from src.domains.auth.dependencies import get_current_active_user
from src.domains.auth.models import User
from src.domains.notifications.schemas import (
    NotificationResponse,
    PaginatedNotificationsResponse,
)
from src.domains.notifications.service import NotificationService

router = APIRouter(tags=["Notifications"])


@router.get(
    "/notifications",
    response_model=PaginatedNotificationsResponse,
    status_code=status.HTTP_200_OK,
    summary="List notifications for current user",
)
async def list_notifications(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    params: Annotated[PaginationParams, Depends()],
    is_read: Annotated[bool | None, Query(description="Filter by read status")] = None,
) -> PaginatedNotificationsResponse:
    """Retrieve chronological notifications for the authenticated user."""
    service = NotificationService(session)
    items, meta = await service.list_notifications(current_user.id, params, is_read=is_read)
    return PaginatedNotificationsResponse(
        items=[NotificationResponse.model_validate(n) for n in items],
        pagination=meta,
    )


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark notification as read",
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationResponse:
    """Transition an unread notification to read status."""
    service = NotificationService(session)
    notification = await service.mark_as_read(current_user.id, notification_id)
    return NotificationResponse.model_validate(notification)
