"""Pydantic v2 schemas for the Notifications domain."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.core.pagination import PaginationMeta


class NotificationResponse(BaseModel):
    """Public representation of an in-app notification."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    is_read: bool
    payload: dict[str, Any]
    created_at: datetime


class PaginatedNotificationsResponse(BaseModel):
    """Paginated envelope for notification records."""

    items: list[NotificationResponse]
    pagination: PaginationMeta
