"""Domain service for asynchronous notification management and event dispatch."""

import math
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import database
from src.core.exceptions import NotFoundError
from src.core.pagination import PaginationMeta, PaginationParams
from src.core.tasks import TaskDispatcher
from src.domains.notifications.models import Notification


async def record_notification_background(
    user_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Execute background creation of an in-app notification record."""
    async with database.async_session_factory() as session:
        notification = Notification(
            user_id=user_id,
            event_type=event_type,
            payload=payload,
        )
        session.add(notification)
        await session.commit()


class NotificationService:
    """Manages notifications querying, read-state transitions, and asynchronous dispatch."""

    def __init__(
        self,
        session: AsyncSession,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.session = session
        self.dispatcher = dispatcher

    def dispatch_notification(
        self,
        user_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Enqueue notification creation without blocking the primary request thread."""
        if self.dispatcher is not None:
            self.dispatcher.dispatch(
                record_notification_background,
                user_id=user_id,
                event_type=event_type,
                payload=payload,
            )

    async def list_notifications(
        self,
        user_id: uuid.UUID,
        params: PaginationParams,
        is_read: bool | None = None,
    ) -> tuple[list[Notification], PaginationMeta]:
        """List notifications for the given user, optionally filtered by read status."""
        query = select(Notification).where(Notification.user_id == user_id)
        if is_read is not None:
            query = query.where(Notification.is_read == is_read)
        query = query.order_by(Notification.created_at.desc())

        count_stmt = select(func.count()).select_from(query.order_by(None).subquery())
        total_items = (await self.session.execute(count_stmt)).scalar_one_or_none() or 0
        total_pages = math.ceil(total_items / params.per_page) if total_items > 0 else 0

        paged_stmt = query.offset(params.offset).limit(params.per_page)
        items = list((await self.session.execute(paged_stmt)).scalars().all())

        meta = PaginationMeta(
            page=params.page,
            per_page=params.per_page,
            total_items=total_items,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
        )
        return items, meta

    async def mark_as_read(
        self,
        user_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> Notification:
        """Mark a notification as read, enforcing user ownership."""
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        notification = (await self.session.execute(stmt)).scalar_one_or_none()
        if not notification:
            raise NotFoundError("Notification not found.")

        notification.is_read = True
        await self.session.commit()
        await self.session.refresh(notification)
        return notification
