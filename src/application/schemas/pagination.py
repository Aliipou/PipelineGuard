"""Pagination helpers for paginated list queries.

Provides a generic ``PaginatedResponse`` container and a
``PaginationParams`` value object that enforces sensible page / size
defaults and upper bounds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")

_DEFAULT_PAGE: int = 1
_DEFAULT_SIZE: int = 20
_MAX_SIZE: int = 100


@dataclass(frozen=True)
class PaginationParams:
    """Immutable pagination request parameters.

    ``page`` is 1-based.  ``size`` is clamped to [1, ``MAX_SIZE``].
    """

    page: int = _DEFAULT_PAGE
    size: int = _DEFAULT_SIZE

    def __post_init__(self) -> None:
        # frozen=True requires object.__setattr__ for validation fixups
        object.__setattr__(self, "page", max(1, self.page))
        object.__setattr__(self, "size", max(1, min(self.size, _MAX_SIZE)))

    @property
    def offset(self) -> int:
        """Zero-based offset suitable for SQL ``OFFSET`` clauses."""
        return (self.page - 1) * self.size


@dataclass
class PaginatedResponse(Generic[T]):
    """Generic wrapper returned by paginated list operations."""

    items: list[T] = field(default_factory=list)
    total: int = 0
    page: int = 1
    size: int = _DEFAULT_SIZE

    @property
    def pages(self) -> int:
        """Total number of pages (at least 1)."""
        if self.total == 0:
            return 1
        return math.ceil(self.total / self.size)

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def has_previous(self) -> bool:
        return self.page > 1
