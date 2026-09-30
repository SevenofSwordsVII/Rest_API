"""Pydantic v2 schemas for work management: projects and tasks."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.core.pagination import PaginationMeta
from src.domains.work_management.models import ProjectStatus, TaskPriority, TaskStatus


class ProjectCreateRequest(BaseModel):
    """Payload for creating a new project."""

    name: str = Field(..., min_length=2, max_length=128, description="Project display name")
    description: str | None = Field(default=None, description="Detailed project description")


class ProjectUpdateRequest(BaseModel):
    """Payload for modifying an existing project."""

    name: str | None = Field(
        default=None, min_length=2, max_length=128, description="New display name"
    )
    description: str | None = Field(default=None, description="Updated description")
    status: ProjectStatus | None = Field(default=None, description="New lifecycle state")


class ProjectResponse(BaseModel):
    """Public representation of a project."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    status: ProjectStatus
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TaskCreateRequest(BaseModel):
    """Payload for creating a new task."""

    title: str = Field(..., min_length=2, max_length=255, description="Actionable task title")
    description: str | None = Field(default=None, description="Task details / criteria")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Task priority")
    assignee_id: uuid.UUID | None = Field(
        default=None, description="Assigned organization member UUID"
    )
    due_date: datetime | None = Field(default=None, description="Optional target completion date")


class TaskUpdateRequest(BaseModel):
    """Payload for updating task details, status, or assignee."""

    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None)
    status: TaskStatus | None = Field(default=None)
    priority: TaskPriority | None = Field(default=None)
    assignee_id: uuid.UUID | None = Field(default=None)
    due_date: datetime | None = Field(default=None)


class TaskResponse(BaseModel):
    """Public representation of a task."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assignee_id: uuid.UUID | None
    created_by: uuid.UUID
    due_date: datetime | None
    created_at: datetime
    updated_at: datetime


class PaginatedProjectsResponse(BaseModel):
    """Envelope for paginated project listing."""

    items: list[ProjectResponse]
    pagination: PaginationMeta


class PaginatedTasksResponse(BaseModel):
    """Envelope for paginated task listing."""

    items: list[TaskResponse]
    pagination: PaginationMeta


class CommentCreateRequest(BaseModel):
    """Payload for creating a new comment on a task."""

    content: str = Field(..., min_length=1, description="Comment text")


class CommentUpdateRequest(BaseModel):
    """Payload for modifying an existing comment."""

    content: str = Field(..., min_length=1, description="Updated comment text")


class CommentResponse(BaseModel):
    """Public representation of a comment."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    author_id: uuid.UUID
    content: str
    created_at: datetime
    updated_at: datetime


class PaginatedCommentsResponse(BaseModel):
    """Envelope for paginated comment listing."""

    items: list[CommentResponse]
    pagination: PaginationMeta
