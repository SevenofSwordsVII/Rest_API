"""Unit tests for pagination schemas and metadata calculations."""

from src.core.pagination import PaginatedResponse, PaginationMeta


def test_pagination_meta_and_paginated_response() -> None:
    meta = PaginationMeta(
        page=1,
        page_size=10,
        total_items=25,
        total_pages=3,
        has_next=True,
        has_prev=False,
    )
    items = ["item1", "item2"]
    paginated = PaginatedResponse[str](items=items, meta=meta)

    assert paginated.items == items
    assert paginated.meta is not None
    assert paginated.meta.total_pages == 3
    assert paginated.meta.has_next is True
    assert paginated.meta.has_prev is False
