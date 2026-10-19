"""SQLAdmin integration: authentication backend, model view registrations, and admin factory."""

import secrets
import uuid
from typing import Any

from fastapi import FastAPI
from sqladmin import Admin, BaseView, ModelView, action, expose
from sqladmin.authentication import AuthenticationBackend
from sqladmin.filters import (
    AllUniqueStringValuesFilter,
    BooleanFilter,
)
from sqlalchemy import Boolean
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from src.core.config import settings
from src.core.database import async_session_factory
from src.domains.audit.models import AuditLogEntry
from src.domains.auth.models import RefreshToken, User
from src.domains.organizations.models import Organization, OrganizationMembership
from src.domains.work_management.models import Project, Task


class AdminAuth(AuthenticationBackend):
    """Session-based authentication backend protecting the /admin dashboard."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        if not username or not password:
            return False

        # ponytail: env-credential check caps at single admin; upgrade to DB lookup on User.is_superuser + argon2 verify for multi-admin RBAC
        valid_user = secrets.compare_digest(str(username), settings.ADMIN_USERNAME)
        valid_pass = secrets.compare_digest(str(password), settings.ADMIN_PASSWORD)

        if not (valid_user and valid_pass):
            return False

        request.session.update({"admin_token": secrets.token_hex(32)})
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("admin_token")
        return bool(token)


# -------------------------------------------------------------------------
# Base Model View with Resilient Filtering
# -------------------------------------------------------------------------


class BaseAdminModelView(ModelView):
    """Base ModelView ensuring robust async session handling and filter normalization."""

    def get_filters(self) -> list[Any]:
        """Normalize column_filters so both Filter instances and bare SQLA columns work safely."""
        filters = getattr(self, "column_filters", None)
        if not filters:
            return []

        normalized = []
        for f in filters:
            if hasattr(f, "parameter_name") and hasattr(f, "template"):
                normalized.append(f)
            else:
                col_name = f if isinstance(f, str) else getattr(f, "key", str(f))
                col = getattr(self.model, col_name, None)
                if col is not None and hasattr(col, "type") and isinstance(col.type, Boolean):
                    normalized.append(BooleanFilter(f))
                else:
                    normalized.append(AllUniqueStringValuesFilter(f))
        return normalized


# -------------------------------------------------------------------------
# Model Views
# -------------------------------------------------------------------------


class UserAdmin(BaseAdminModelView, model=User):
    """Admin interface for User account lifecycle management."""

    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"

    column_list = [
        User.id,
        User.email,
        User.full_name,
        User.is_active,
        User.is_superuser,
        User.created_at,
    ]
    column_searchable_list = [User.email, User.full_name]
    column_sortable_list = [User.email, User.created_at, User.is_active]
    column_filters = [
        BooleanFilter(User.is_active),
        BooleanFilter(User.is_superuser),
    ]

    # Exclude sensitive secrets and relations from forms and details
    column_details_exclude_list = [User.hashed_password]
    form_excluded_columns = [
        User.hashed_password,
        User.refresh_tokens,
        User.created_at,
        User.updated_at,
    ]

    can_create = False  # Creation via API registration handles proper password hashing
    can_delete = True
    can_edit = True

    @action(
        name="toggle_active",
        label="Toggle Active Status",
        confirmation_message="Toggle active flag on selected users?",
    )
    async def toggle_active(self, request: Request) -> Response:
        pks = request.query_params.get("pks", "").split(",")
        if pks and pks[0]:
            async with self.session_maker() as session:
                for pk in pks:
                    try:
                        pk_val: Any = uuid.UUID(pk) if isinstance(pk, str) else pk
                    except (ValueError, TypeError):
                        pk_val = pk
                    user = await session.get(User, pk_val)
                    if user:
                        user.is_active = not user.is_active
                await session.commit()
        return RedirectResponse(request.url_for("admin:list", identity=self.identity), status_code=303)


class RefreshTokenAdmin(BaseAdminModelView, model=RefreshToken):
    """Admin interface for monitoring active session tokens."""

    name = "Session Token"
    name_plural = "Session Tokens"
    icon = "fa-solid fa-key"

    column_list = [
        RefreshToken.id,
        RefreshToken.user_id,
        RefreshToken.family_id,
        RefreshToken.is_revoked,
        RefreshToken.expires_at,
    ]
    column_searchable_list = [RefreshToken.token_hash]
    column_filters = [
        BooleanFilter(RefreshToken.is_revoked),
    ]
    can_create = False
    can_edit = False
    can_delete = True


class OrganizationAdmin(BaseAdminModelView, model=Organization):
    """Admin interface for managing tenant organizations."""

    name = "Organization"
    name_plural = "Organizations"
    icon = "fa-solid fa-building"

    column_list = [
        Organization.id,
        Organization.name,
        Organization.slug,
        Organization.deleted_at,
        Organization.created_at,
    ]
    column_searchable_list = [Organization.name, Organization.slug]
    column_sortable_list = [Organization.name, Organization.created_at]
    form_excluded_columns = [
        Organization.memberships,
        Organization.created_at,
        Organization.updated_at,
    ]


class OrganizationMembershipAdmin(BaseAdminModelView, model=OrganizationMembership):
    """Admin interface for inspecting tenant-user memberships and RBAC roles."""

    name = "Membership"
    name_plural = "Memberships"
    icon = "fa-solid fa-users-gear"

    column_list = [
        OrganizationMembership.id,
        OrganizationMembership.organization_id,
        OrganizationMembership.user_id,
        OrganizationMembership.role,
        OrganizationMembership.created_at,
    ]
    column_filters = [
        AllUniqueStringValuesFilter(OrganizationMembership.role),
    ]
    form_excluded_columns = [OrganizationMembership.created_at, OrganizationMembership.updated_at]


class ProjectAdmin(BaseAdminModelView, model=Project):
    """Admin interface for workspace projects."""

    name = "Project"
    name_plural = "Projects"
    icon = "fa-solid fa-folder-kanban"

    column_list = [
        Project.id,
        Project.name,
        Project.status,
        Project.organization_id,
        Project.created_at,
    ]
    column_searchable_list = [Project.name]
    column_sortable_list = [Project.name, Project.status, Project.created_at]
    column_filters = [
        AllUniqueStringValuesFilter(Project.status),
    ]
    form_excluded_columns = [
        Project.tasks,
        Project.created_at,
        Project.updated_at,
    ]


class TaskAdmin(BaseAdminModelView, model=Task):
    """Admin interface for work tasks."""

    name = "Task"
    name_plural = "Tasks"
    icon = "fa-solid fa-list-check"

    column_list = [
        Task.id,
        Task.title,
        Task.status,
        Task.priority,
        Task.project_id,
        Task.due_date,
    ]
    column_searchable_list = [Task.title]
    column_sortable_list = [Task.status, Task.priority, Task.due_date]
    column_filters = [
        AllUniqueStringValuesFilter(Task.status),
        AllUniqueStringValuesFilter(Task.priority),
    ]
    form_excluded_columns = [
        Task.comments,
        Task.created_at,
        Task.updated_at,
    ]


class AuditLogAdmin(BaseAdminModelView, model=AuditLogEntry):
    """Append-only audit trail: view and search only, no modifications allowed."""

    name = "Audit Log"
    name_plural = "Audit Logs"
    icon = "fa-solid fa-shield-halved"

    column_list = [
        AuditLogEntry.id,
        AuditLogEntry.action,
        AuditLogEntry.target_resource,
        AuditLogEntry.actor_id,
        AuditLogEntry.organization_id,
        AuditLogEntry.created_at,
    ]
    column_searchable_list = [AuditLogEntry.action, AuditLogEntry.target_resource]
    column_sortable_list = [AuditLogEntry.created_at, AuditLogEntry.action]

    can_create = False
    can_edit = False
    can_delete = False


# -------------------------------------------------------------------------
# Custom View
# -------------------------------------------------------------------------


class SystemInfoView(BaseView):
    """Custom dashboard page displaying operational application metadata."""

    name = "System Info"
    icon = "fa-solid fa-server"

    @expose("/system", methods=["GET"])
    async def system_page(self, request: Request) -> Response:
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>System Info</title></head>
        <body style="font-family: sans-serif; padding: 2rem;">
            <h2>{settings.APP_NAME} - Operational Info</h2>
            <ul>
                <li><strong>Environment:</strong> {settings.ENVIRONMENT}</li>
                <li><strong>Debug:</strong> {settings.DEBUG}</li>
                <li><strong>API Prefix:</strong> {settings.API_V1_PREFIX}</li>
            </ul>
            <p><a href="/admin">&larr; Back to Admin Dashboard</a></p>
        </body>
        </html>
        """
        return Response(content=html, media_type="text/html")


# -------------------------------------------------------------------------
# Admin Factory
# -------------------------------------------------------------------------


def setup_admin(
    app: FastAPI,
    engine: AsyncEngine,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> Admin:
    """Instantiate and configure SQLAdmin dashboard attached to FastAPI."""
    authentication_backend = AdminAuth(secret_key=settings.SECRET_KEY)

    admin = Admin(
        app=app,
        engine=engine,
        session_maker=session_maker or async_session_factory,
        authentication_backend=authentication_backend,
        title=f"{settings.APP_NAME} Admin",
        base_url="/admin",
    )

    # Register Model Views
    admin.add_view(UserAdmin)
    admin.add_view(RefreshTokenAdmin)
    admin.add_view(OrganizationAdmin)
    admin.add_view(OrganizationMembershipAdmin)
    admin.add_view(ProjectAdmin)
    admin.add_view(TaskAdmin)
    admin.add_view(AuditLogAdmin)

    # Register Custom Views
    admin.add_view(SystemInfoView)

    return admin
