"""Standardized pagination schemas and SQLAlchemy 2.0 query pagination helpers."""

import math
from typing import Annotated, Any, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class PaginationParams:
    """FastAPI dependency parsing and validating standard pagination query parameters."""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1, description="Page number starting at 1")] = 1,
        per_page: Annotated[
            int | None, Query(ge=1, le=100, description="Items per page (max 100)")
        ] = None,
        page_size: Annotated[
            int | None, Query(ge=1, le=100, description="Items per page (max 100)")
        ] = None,
    ) -> None:
        self.page = page
        effective_limit = per_page if per_page is not None else page_size
        self.per_page = effective_limit if effective_limit is not None else 20

    @property
    def page_size(self) -> int:
        return self.per_page

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


class PaginationMeta(BaseModel):
    """Metadata describing the pagination state."""

    page: int = Field(..., ge=1, description="Current page number")
    per_page: int = Field(default=20, ge=1, description="Number of items per page")
    total_items: int = Field(..., ge=0, description="Total count of matching items")
    total_pages: int = Field(..., ge=0, description="Total calculated pages")
    has_next: bool = Field(default=False, description="Whether a subsequent page exists")
    has_prev: bool = Field(default=False, description="Whether a preceding page exists")
    page_size: int | None = Field(default=None, description="Legacy alias for per_page")

    def model_post_init(self, __context: Any) -> None:
        if self.page_size is not None and "per_page" not in self.model_fields_set:
            self.per_page = self.page_size
        if self.page_size is None:
            self.page_size = self.per_page


class PaginatedResponse[T](BaseModel):
    """Generic wrapper envelope for paginated collections."""

    items: list[T]
    pagination: PaginationMeta | None = None
    meta: PaginationMeta | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.pagination is None and self.meta is not None:
            self.pagination = self.meta
        elif self.meta is None and self.pagination is not None:
            self.meta = self.pagination


async def paginate(
    session: AsyncSession,
    query: Select[Any],
    params: PaginationParams,
) -> tuple[list[T], PaginationMeta]:
    """Execute count and windowed fetch queries asynchronously."""
    # Count total items efficiently using subquery
    count_subquery = query.order_by(None).subquery()
    count_stmt = select(func.count()).select_from(count_subquery)
    total_items = (await session.execute(count_stmt)).scalar_one_or_none() or 0

    total_pages = math.ceil(total_items / params.per_page) if total_items > 0 else 0

    # Fetch items for requested page
    window_stmt = query.offset(params.offset).limit(params.per_page)
    items: list[T] = list((await session.execute(window_stmt)).scalars().all())

    meta = PaginationMeta(
        page=params.page,
        per_page=params.per_page,
        total_items=total_items,
        total_pages=total_pages,
        has_next=params.page < total_pages,
        has_prev=params.page > 1,
    )

    return items, meta
