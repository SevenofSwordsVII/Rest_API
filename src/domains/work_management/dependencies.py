"""FastAPI dependencies for resolving project and task contexts within tenant boundaries."""

import uuid
from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.domains.organizations.dependencies import require_org_role
from src.domains.organizations.models import Organization, OrganizationMembership, RoleEnum
from src.domains.work_management.models import Comment, Project, Task
from src.domains.work_management.service import WorkManagementService


async def resolve_project_in_org(
    project_id: Annotated[uuid.UUID, Path(..., description="Project UUID identifier")],
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.VIEWER)),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Project:
    """Resolve project verifying it belongs to the authenticated tenant organization."""
    org, _ = context
    service = WorkManagementService(session)
    return await service.get_project(org.id, project_id)


async def resolve_task_in_project(
    task_id: Annotated[uuid.UUID, Path(..., description="Task UUID identifier")],
    project: Annotated[Project, Depends(resolve_project_in_org)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Task:
    """Resolve task verifying it belongs to the resolved project."""
    service = WorkManagementService(session)
    return await service.get_task(project.id, task_id)


async def resolve_comment_in_task(
    comment_id: Annotated[uuid.UUID, Path(..., description="Comment UUID identifier")],
    task: Annotated[Task, Depends(resolve_task_in_project)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Comment:
    """Resolve comment verifying it belongs to the resolved task."""
    service = WorkManagementService(session)
    return await service.get_comment(task.id, comment_id)
