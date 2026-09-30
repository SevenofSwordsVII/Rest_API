"""Domain service implementing Project and Task lifecycle, filtering, and invariant checks."""

import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import utc_now
from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from src.core.pagination import PaginationMeta, PaginationParams
from src.core.tasks import TaskDispatcher
from src.domains.audit.service import AuditService
from src.domains.notifications.service import NotificationService
from src.domains.organizations.models import OrganizationMembership, RoleEnum
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
    CommentUpdateRequest,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
)


class WorkManagementService:
    """Manages project and task domain operations with strict tenant isolation."""

    def __init__(
        self,
        session: AsyncSession,
        dispatcher: TaskDispatcher | None = None,
    ) -> None:
        self.session = session
        self.dispatcher = dispatcher
        self.notification_service = NotificationService(session, dispatcher=dispatcher)
        self.audit_service = AuditService(session)

    async def validate_assignee_in_org(
        self, organization_id: uuid.UUID, assignee_id: uuid.UUID
    ) -> None:
        """Enforce invariant: assignee must be an active member of the project's organization."""
        stmt = select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == assignee_id,
        )
        membership = (await self.session.execute(stmt)).scalar_one_or_none()
        if not membership:
            raise ValidationError(
                "Assignee must be an active member of the project's organization."
            )

    async def create_project(
        self, organization_id: uuid.UUID, creator_id: uuid.UUID, payload: ProjectCreateRequest
    ) -> Project:
        """Create a new project under the specified organization."""
        project = Project(
            organization_id=organization_id,
            created_by=creator_id,
            name=payload.name,
            description=payload.description,
            status=ProjectStatus.ACTIVE,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def get_project(self, organization_id: uuid.UUID, project_id: uuid.UUID) -> Project:
        """Retrieve active project by ID within organization."""
        stmt = select(Project).where(
            Project.id == project_id,
            Project.organization_id == organization_id,
            Project.deleted_at.is_(None),
        )
        project = (await self.session.execute(stmt)).scalar_one_or_none()
        if not project:
            raise NotFoundError("Project not found.")
        return project

    async def list_projects(
        self,
        organization_id: uuid.UUID,
        status_filter: ProjectStatus | None,
        params: PaginationParams,
    ) -> tuple[list[Project], PaginationMeta]:
        """List active projects in organization with optional status filtering."""
        query = select(Project).where(
            Project.organization_id == organization_id,
            Project.deleted_at.is_(None),
        )
        if status_filter is not None:
            query = query.where(Project.status == status_filter)
        query = query.order_by(Project.created_at.desc())

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

    async def update_project(self, project: Project, payload: ProjectUpdateRequest) -> Project:
        """Update project metadata or lifecycle state."""
        if payload.name is not None:
            project.name = payload.name
        if payload.description is not None:
            project.description = payload.description
        if payload.status is not None:
            project.status = payload.status
        project.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def soft_delete_project(
        self, project: Project, actor_id: uuid.UUID | None = None
    ) -> None:
        """Soft-delete a project by setting deleted_at."""
        project.deleted_at = utc_now()
        project.updated_at = utc_now()
        await self.session.commit()
        await self.audit_service.record_audit(
            action="project.deleted",
            target_resource=f"project:{project.id}",
            organization_id=project.organization_id,
            actor_id=actor_id,
        )

    async def create_task(
        self, project: Project, creator_id: uuid.UUID, payload: TaskCreateRequest
    ) -> Task:
        """Create a task in project, checking archive freeze and assignee membership."""
        if project.status == ProjectStatus.ARCHIVED or project.deleted_at is not None:
            raise ConflictError("Cannot create tasks in an archived or deleted project.")

        if payload.assignee_id is not None:
            await self.validate_assignee_in_org(project.organization_id, payload.assignee_id)

        task = Task(
            project_id=project.id,
            created_by=creator_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            assignee_id=payload.assignee_id,
            due_date=payload.due_date,
            status=TaskStatus.TODO,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)

        if task.assignee_id is not None:
            self.notification_service.dispatch_notification(
                user_id=task.assignee_id,
                event_type="task.assigned",
                payload={
                    "task_id": str(task.id),
                    "title": task.title,
                    "project_id": str(task.project_id),
                    "actor_id": str(creator_id),
                },
            )

        return task

    async def get_task(self, project_id: uuid.UUID, task_id: uuid.UUID) -> Task:
        """Retrieve task by ID within project context."""
        stmt = select(Task).where(
            Task.id == task_id,
            Task.project_id == project_id,
            Task.deleted_at.is_(None),
        )
        task = (await self.session.execute(stmt)).scalar_one_or_none()
        if not task:
            raise NotFoundError("Task not found.")
        return task

    async def list_tasks(
        self,
        project_id: uuid.UUID,
        status_filter: TaskStatus | None,
        priority_filter: TaskPriority | None,
        assignee_filter: uuid.UUID | None,
        params: PaginationParams,
    ) -> tuple[list[Task], PaginationMeta]:
        """List tasks for a project with optional filters."""
        query = select(Task).where(
            Task.project_id == project_id,
            Task.deleted_at.is_(None),
        )
        if status_filter is not None:
            query = query.where(Task.status == status_filter)
        if priority_filter is not None:
            query = query.where(Task.priority == priority_filter)
        if assignee_filter is not None:
            query = query.where(Task.assignee_id == assignee_filter)
        query = query.order_by(Task.created_at.desc())

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

    async def update_task(
        self,
        project: Project,
        task: Task,
        payload: TaskUpdateRequest,
        actor_id: uuid.UUID | None = None,
    ) -> Task:
        """Update task details, enforcing archived project freeze and assignee membership."""
        if project.status == ProjectStatus.ARCHIVED or project.deleted_at is not None:
            raise ConflictError("Cannot modify tasks in an archived or deleted project.")

        old_status = task.status
        old_assignee_id = task.assignee_id

        if payload.assignee_id is not None:
            await self.validate_assignee_in_org(project.organization_id, payload.assignee_id)
            task.assignee_id = payload.assignee_id

        if payload.title is not None:
            task.title = payload.title
        if payload.description is not None:
            task.description = payload.description
        if payload.status is not None:
            task.status = payload.status
        if payload.priority is not None:
            task.priority = payload.priority
        if payload.due_date is not None:
            task.due_date = payload.due_date

        task.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(task)

        if payload.assignee_id is not None and payload.assignee_id != old_assignee_id:
            self.notification_service.dispatch_notification(
                user_id=payload.assignee_id,
                event_type="task.assigned",
                payload={
                    "task_id": str(task.id),
                    "title": task.title,
                    "project_id": str(task.project_id),
                    "actor_id": str(actor_id) if actor_id else None,
                },
            )

        if payload.status is not None and payload.status != old_status:
            recipient_id = task.assignee_id if task.assignee_id else task.created_by
            if recipient_id:
                self.notification_service.dispatch_notification(
                    user_id=recipient_id,
                    event_type="task.status_changed",
                    payload={
                        "task_id": str(task.id),
                        "old_status": str(old_status),
                        "new_status": str(payload.status),
                        "actor_id": str(actor_id) if actor_id else None,
                    },
                )

        return task

    async def soft_delete_task(
        self,
        task: Task,
        organization_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """Soft-delete task by setting deleted_at."""
        task.deleted_at = utc_now()
        task.updated_at = utc_now()
        await self.session.commit()
        await self.audit_service.record_audit(
            action="task.deleted",
            target_resource=f"task:{task.id}",
            organization_id=organization_id,
            actor_id=actor_id,
        )

    async def create_comment(
        self, task: Task, author_id: uuid.UUID, payload: CommentCreateRequest
    ) -> Comment:
        """Create a comment on a task."""
        if task.deleted_at is not None:
            raise ConflictError("Cannot comment on a deleted task.")

        comment = Comment(
            task_id=task.id,
            author_id=author_id,
            content=payload.content,
        )
        self.session.add(comment)
        await self.session.commit()
        await self.session.refresh(comment)

        recipients = set()
        if task.assignee_id and task.assignee_id != author_id:
            recipients.add(task.assignee_id)
        if task.created_by and task.created_by != author_id:
            recipients.add(task.created_by)

        for recipient_id in recipients:
            self.notification_service.dispatch_notification(
                user_id=recipient_id,
                event_type="comment.created",
                payload={
                    "task_id": str(task.id),
                    "comment_id": str(comment.id),
                    "actor_id": str(author_id),
                },
            )

        return comment

    async def get_comment(self, task_id: uuid.UUID, comment_id: uuid.UUID) -> Comment:
        """Fetch a specific comment on a task."""
        stmt = select(Comment).where(
            Comment.id == comment_id,
            Comment.task_id == task_id,
        )
        comment = (await self.session.execute(stmt)).scalar_one_or_none()
        if not comment:
            raise NotFoundError("Comment not found.")
        return comment

    async def list_comments(
        self, task_id: uuid.UUID, params: PaginationParams
    ) -> tuple[list[Comment], PaginationMeta]:
        """List comments for a task ordered chronologically."""
        query = select(Comment).where(Comment.task_id == task_id).order_by(Comment.created_at.asc())

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

    async def update_comment(
        self, comment: Comment, author_id: uuid.UUID, payload: CommentUpdateRequest
    ) -> Comment:
        """Update comment content enforcing author-only edit check."""
        if comment.author_id != author_id:
            raise ForbiddenError("Only the author may edit this comment.")

        comment.content = payload.content
        comment.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(comment)
        return comment

    async def delete_comment(
        self, comment: Comment, actor_id: uuid.UUID, actor_role: RoleEnum
    ) -> None:
        """Delete comment enforcing author or admin/owner permission check."""
        if comment.author_id != actor_id and actor_role not in (RoleEnum.ADMIN, RoleEnum.OWNER):
            raise ForbiddenError(
                "Only the author or organization administrators may delete this comment."
            )

        await self.session.delete(comment)
        await self.session.commit()
