"""Unified response models and pagination."""

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard success response envelope."""
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None


class PaginatedData(BaseModel, Generic[T]):
    """Paginated data wrapper."""
    items: List[T]
    page: int
    size: int
    total: int
    total_pages: int


class APIErrorResponse(BaseModel):
    """Standard error response envelope."""
    code: int
    message: str
    detail: Any = None


def paginated_response(
    items: List[Any],
    page: int,
    size: int,
    total: int,
) -> dict:
    """Build a paginated API response as a plain dict.

    Returns a dict so FastAPI's jsonable_encoder can handle ORM objects
    inside the items list through response_model serialization.
    """
    total_pages = (total + size - 1) // size if size > 0 else 0
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "items": items,
            "page": page,
            "size": size,
            "total": total,
            "total_pages": total_pages,
        },
    }
