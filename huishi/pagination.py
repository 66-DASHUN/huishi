from __future__ import annotations

from dataclasses import dataclass
from math import ceil


def parse_int(value: object, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class PageQuery:
    page: int
    per_page: int

    @classmethod
    def from_values(cls, page: object, per_page: object, *, default_per_page: int = 20) -> "PageQuery":
        return cls(
            max(1, parse_int(page, 1)),
            min(100, max(10, parse_int(per_page, default_per_page))),
        )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


@dataclass(frozen=True)
class Pagination:
    page: int
    per_page: int
    total: int

    @classmethod
    def from_query(cls, query: PageQuery, total: int) -> "Pagination":
        return cls(page=query.page, per_page=query.per_page, total=max(0, int(total)))

    @property
    def pages(self) -> int:
        return max(1, ceil(self.total / self.per_page))

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages
