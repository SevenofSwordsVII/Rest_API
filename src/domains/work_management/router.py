"""FastAPI router for work management endpoints: Projects and Tasks."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.pagination import PaginationParams
from src.core.tasks import TaskDispatcher, get_task_dispatcher
from src.domains.auth.dependencies import get_current_active_user
from src.domains.auth.models import User
from src.domains.organizations.dependencies import require_org_role
from src.domains.organizations.models import Organization, OrganizationMembership, RoleEnum
from src.domains.work_management.dependencies import (
    resolve_comment_in_task,
    resolve_project_in_org,
    resolve_task_in_project,
)
from src.domains.work_management.models import (
    Comment,
    Project,
    ProjectStatus,
    Task,
    TaskPriority,
    TaskStatus,
)
from src.domains.work_management.schemas import (
    CommentCreateRequest,
    CommentResponse,
    CommentUpdateRequest,
    PaginatedCommentsResponse,
    PaginatedProjectsResponse,
    PaginatedTasksResponse,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    TaskCreateRequest,
    TaskResponse,
    TaskUpdateRequest,
)
from src.domains.work_management.service import WorkManagementService

router = APIRouter(tags=["Projects", "Tasks"])


# =========================================================================
# PROJECTS ENDPOINTS
# =========================================================================


@router.get(
    "/orgs/{org_id}/projects",
    response_model=PaginatedProjectsResponse,
    status_code=status.HTTP_200_OK,
    summary="List projects in organization",
)
async def list_projects(
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.VIEWER)),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
    params: Annotated[PaginationParams, Depends()],
    status_filter: Annotated[ProjectStatus | None, Query(alias="status")] = None,
) -> PaginatedProjectsResponse:
    """List active projects within an organization with optional status filtering."""
    org, _ = context
    service = WorkManagementService(session)
    items, meta = await service.list_projects(org.id, status_filter, params)
    return PaginatedProjectsResponse(
        items=[ProjectResponse.model_validate(p) for p in items],
        pagination=meta,
    )


@router.post(
    "/orgs/{org_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project (Member, Admin, or Owner)",
)
async def create_project(
    payload: ProjectCreateRequest,
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.MEMBER)),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectResponse:
    """Create a new project under the organization."""
    org, _ = context
    service = WorkManagementService(session)
    project = await service.create_project(org.id, current_user.id, payload)
    return ProjectResponse.model_validate(project)


@router.get(
    "/orgs/{org_id}/projects/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Get project details",
)
async def get_project(
    project: Annotated[Project, Depends(resolve_project_in_org)],
) -> ProjectResponse:
    """Get project details by ID."""
    return ProjectResponse.model_validate(project)


@router.patch(
    "/orgs/{org_id}/projects/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update project",
)
async def update_project(
    payload: ProjectUpdateRequest,
    project: Annotated[Project, Depends(resolve_project_in_org)],
    _: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.MEMBER)),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectResponse:
    """Update project name, description, or status."""
    service = WorkManagementService(session)
    updated = await service.update_project(project, payload)
    return ProjectResponse.model_validate(updated)


@router.delete(
    "/orgs/{org_id}/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete project (Admin or Owner)",
)
async def delete_project(
    project: Annotated[Project, Depends(resolve_project_in_org)],
    _: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.ADMIN)),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Soft-delete project."""
    service = WorkManagementService(session)
    await service.soft_delete_project(project, actor_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =========================================================================
# TASKS ENDPOINTS
# =========================================================================


@router.get(
    "/orgs/{org_id}/projects/{project_id}/tasks",
    response_model=PaginatedTasksResponse,
    status_code=status.HTTP_200_OK,
    summary="List tasks in project with filtering and pagination",
)
async def list_tasks(
    project: Annotated[Project, Depends(resolve_project_in_org)],
    session: Annotated[AsyncSession, Depends(get_db)],
    params: Annotated[PaginationParams, Depends()],
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority_filter: Annotated[TaskPriority | None, Query(alias="priority")] = None,
    assignee_id: Annotated[uuid.UUID | None, Query(alias="assignee_id")] = None,
) -> PaginatedTasksResponse:
    """List tasks in project with filtering."""
    service = WorkManagementService(session)
    items, meta = await service.list_tasks(
        project.id, status_filter, priority_filter, assignee_id, params
    )
    return PaginatedTasksResponse(
        items=[TaskResponse.model_validate(t) for t in items],
        pagination=meta,
    )


@router.post(
    "/orgs/{org_id}/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task in project (Member, Admin, or Owner)",
)
async def create_task(
    payload: TaskCreateRequest,
    project: Annotated[Project, Depends(resolve_project_in_org)],
    _: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.MEMBER)),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
) -> TaskResponse:
    """Create a new task within the project."""
    service = WorkManagementService(session, dispatcher=dispatcher)
    task = await service.create_task(project, current_user.id, payload)
    return TaskResponse.model_validate(task)


@router.get(
    "/orgs/{org_id}/projects/{project_id}/tasks/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Get task details",
)
async def get_task(
    task: Annotated[Task, Depends(resolve_task_in_project)],
) -> TaskResponse:
    """Get task details by ID."""
    return TaskResponse.model_validate(task)


@router.patch(
    "/orgs/{org_id}/projects/{project_id}/tasks/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Update task details, status, or assignee",
)
async def update_task(
    payload: TaskUpdateRequest,
    project: Annotated[Project, Depends(resolve_project_in_org)],
    task: Annotated[Task, Depends(resolve_task_in_project)],
    _: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.MEMBER)),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
) -> TaskResponse:
    """Update task details, status, or assignee."""
    service = WorkManagementService(session, dispatcher=dispatcher)
    updated = await service.update_task(project, task, payload, actor_id=current_user.id)
    return TaskResponse.model_validate(updated)


@router.delete(
    "/orgs/{org_id}/projects/{project_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete task",
)
async def delete_task(
    project: Annotated[Project, Depends(resolve_project_in_org)],
    task: Annotated[Task, Depends(resolve_task_in_project)],
    _: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.MEMBER)),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Soft-delete task."""
    service = WorkManagementService(session)
    await service.soft_delete_task(
        task,
        organization_id=project.organization_id,
        actor_id=current_user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =========================================================================
# COMMENTS ENDPOINTS
# =========================================================================


@router.get(
    "/orgs/{org_id}/projects/{project_id}/tasks/{task_id}/comments",
    response_model=PaginatedCommentsResponse,
    status_code=status.HTTP_200_OK,
    tags=["Comments"],
    summary="List comments for a task",
)
async def list_comments(
    task: Annotated[Task, Depends(resolve_task_in_project)],
    _: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.VIEWER)),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
    params: Annotated[PaginationParams, Depends()],
) -> PaginatedCommentsResponse:
    """List comments for a task chronologically."""
    service = WorkManagementService(session)
    items, meta = await service.list_comments(task.id, params)
    return PaginatedCommentsResponse(
        items=[CommentResponse.model_validate(c) for c in items],
        pagination=meta,
    )


@router.post(
    "/orgs/{org_id}/projects/{project_id}/tasks/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Comments"],
    summary="Add comment to task",
)
async def create_comment(
    payload: CommentCreateRequest,
    task: Annotated[Task, Depends(resolve_task_in_project)],
    _: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.MEMBER)),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
) -> CommentResponse:
    """Add a new comment to a task."""
    service = WorkManagementService(session, dispatcher=dispatcher)
    comment = await service.create_comment(task, current_user.id, payload)
    return CommentResponse.model_validate(comment)


@router.patch(
    "/orgs/{org_id}/projects/{project_id}/tasks/{task_id}/comments/{comment_id}",
    response_model=CommentResponse,
    status_code=status.HTTP_200_OK,
    tags=["Comments"],
    summary="Update comment (Author only)",
)
async def update_comment(
    payload: CommentUpdateRequest,
    comment: Annotated[Comment, Depends(resolve_comment_in_task)],
    _: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.MEMBER)),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CommentResponse:
    """Update comment content (author only)."""
    service = WorkManagementService(session)
    updated = await service.update_comment(comment, current_user.id, payload)
    return CommentResponse.model_validate(updated)


@router.delete(
    "/orgs/{org_id}/projects/{project_id}/tasks/{task_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Comments"],
    summary="Delete comment (Author or Admin/Owner)",
)
async def delete_comment(
    comment: Annotated[Comment, Depends(resolve_comment_in_task)],
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.MEMBER)),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete comment (author or admin/owner)."""
    _, membership = context
    service = WorkManagementService(session)
    await service.delete_comment(comment, current_user.id, membership.role)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
