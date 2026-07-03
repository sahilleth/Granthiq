"""
Pagination schemas and utilities for cursor-based pagination.
"""

import base64
import json
from typing import Generic, TypeVar, List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime


T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    """
    Cursor-based pagination response.

    Use this for paginated endpoints where clients pass a cursor
    to fetch the next page of results.
    """

    items: List[T] = Field(default_factory=list, description="Items in current page")
    next_cursor: Optional[str] = Field(default=None, description="Cursor for next page")
    previous_cursor: Optional[str] = Field(
        default=None, description="Cursor for previous page"
    )
    total_count: int = Field(default=0, description="Total number of items")
    has_more: bool = Field(default=False, description="Whether there are more items")

    class Config:
        from_attributes = True


class PaginationParams(BaseModel):
    """
    Cursor-based pagination parameters.

    Clients should pass:
    - limit: Number of items per page (1-100)
    - cursor: Base64-encoded cursor for the next page
    """

    limit: int = Field(default=20, ge=1, le=100, description="Number of items per page")
    cursor: Optional[str] = Field(default=None, description="Cursor for pagination")


def encode_cursor(data: Dict[str, Any]) -> str:
    """
    Encode pagination cursor from a dictionary.

    The dictionary typically contains:
    - offset: The offset for the next query
    - timestamp: Optional timestamp for stable cursors

    Args:
        data: Dictionary containing pagination data

    Returns:
        Base64-encoded cursor string
    """
    json_str = json.dumps(data, default=str)
    return base64.b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> Dict[str, Any]:
    """
    Decode pagination cursor to a dictionary.

    Args:
        cursor: Base64-encoded cursor string

    Returns:
        Dictionary with pagination data

    Raises:
        ValueError: If cursor is invalid or cannot be decoded
    """
    try:
        json_str = base64.b64decode(cursor.encode()).decode()
        return json.loads(json_str)
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"Invalid cursor: {e}")


def create_cursor_params(
    limit: int, cursor: Optional[str] = None, default_offset: int = 0
) -> Dict[str, Any]:
    """
    Create pagination parameters from cursor or return defaults.

    Args:
        limit: Number of items per page
        cursor: Optional cursor string
        default_offset: Default offset if no cursor provided

    Returns:
        Dictionary with 'offset' and 'limit' keys
    """
    if cursor:
        try:
            data = decode_cursor(cursor)
            return {
                "offset": data.get("offset", default_offset),
                "limit": min(limit, data.get("limit", 20)),
            }
        except ValueError:
            return {"offset": default_offset, "limit": limit}

    return {"offset": default_offset, "limit": limit}


def build_pagination_response(
    items: List[T],
    total_count: int,
    limit: int,
    offset: int,
    cursor_data: Optional[Dict[str, Any]] = None,
) -> CursorPage[T]:
    """
    Build a cursor-based pagination response.

    Args:
        items: List of items for current page
        total_count: Total number of items
        limit: Number of items per page
        offset: Current offset
        cursor_data: Optional data to encode in next cursor

    Returns:
        CursorPage with cursors and metadata
    """
    has_more = (offset + limit) < total_count

    # Create next cursor
    next_cursor = None
    if has_more and items:
        next_cursor_data = {"offset": offset + len(items), "limit": limit}
        if cursor_data:
            next_cursor_data.update(cursor_data)
        next_cursor = encode_cursor(next_cursor_data)

    # Create previous cursor
    previous_cursor = None
    if offset > 0:
        prev_offset = max(0, offset - limit)
        previous_cursor = encode_cursor({"offset": prev_offset, "limit": limit})

    return CursorPage(
        items=items,
        next_cursor=next_cursor,
        previous_cursor=previous_cursor,
        total_count=total_count,
        has_more=has_more,
    )


class OffsetPaginationParams(BaseModel):
    """
    Alternative: Offset-based pagination parameters.

    Use this when cursor-based pagination is not feasible.
    """

    limit: int = Field(default=20, ge=1, le=100, description="Number of items per page")
    offset: int = Field(default=0, ge=0, description="Number of items to skip")


class OffsetPage(BaseModel, Generic[T]):
    """
    Offset-based pagination response.

    Alternative to cursor-based pagination.
    """

    items: List[T] = Field(default_factory=list)
    total_count: int = Field(default=0)
    limit: int = Field(default=20)
    offset: int = Field(default=0)
    has_more: bool = Field(default=False)

    @classmethod
    def create(
        cls, items: List[T], total_count: int, limit: int, offset: int
    ) -> "OffsetPage[T]":
        """Create offset pagination response."""
        return cls(
            items=items,
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total_count,
        )
