"""FastAPI router for Audit Logging endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.pagination import PaginationParams
from src.domains.audit.schemas import (
    AuditLogResponse,
    PaginatedAuditLogsResponse,
)
from src.domains.audit.service import AuditService
from src.domains.organizations.dependencies import require_org_role
from src.domains.organizations.models import Organization, OrganizationMembership, RoleEnum

router = APIRouter(tags=["Audit"])


@router.get(
    "/orgs/{org_id}/audit-logs",
    response_model=PaginatedAuditLogsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve organization audit log (Admin or Owner only)",
)
async def list_audit_logs(
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.ADMIN)),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
    params: Annotated[PaginationParams, Depends()],
    action: Annotated[str | None, Query(description="Filter by audit action code")] = None,
) -> PaginatedAuditLogsResponse:
    """Retrieve chronological audit records for an organization (Admin or Owner only)."""
    org, _ = context
    service = AuditService(session)
    items, meta = await service.list_audit_logs(org.id, params, action=action)
    return PaginatedAuditLogsResponse(
        items=[AuditLogResponse.model_validate(entry) for entry in items],
        pagination=meta,
    )
