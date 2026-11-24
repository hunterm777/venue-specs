"""Plain data passed between the watcher's steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Source:
    """One page or endpoint in sources.yaml."""

    id: str
    venue: str
    products: tuple[str, ...]
    url: str
    kind: str  # markdown | html | rss | json_post | pdf
    parser: str | None = None  # "<venue module>.<function>", or None for prose-only pages
    body: str | None = None  # request body for json_post
    keep: tuple[str, ...] = ()  # json_post: top-level keys kept in the snapshot
    title: str = ""
    covers: tuple[str, ...] = ()  # other URLs whose changes this source carries (spec citations)


@dataclass(frozen=True)
class Proposal:
    """A spec value a parser read from a source."""

    venue: str
    product: str
    path: str
    source: str
    value: Any = None
    formula: str | None = None
    effective_from: str | None = None  # None when the source does not say
    note: str | None = None


@dataclass
class Change:
    """One line of our changelog."""

    kind: str  # Changed | Added | Removed | Upcoming | Docs-only
    venue: str
    product: str
    summary: str
    source: str
    spec_file: str | None = None
    section: str | None = None
    effective_from: str | None = None


@dataclass
class Issue:
    """An issue the workflow opens, or comments on when one with the same title is open."""

    title: str
    body: str


@dataclass
class ParseResult:
    """What a parser got from one source: values, and anything it expected but could not read."""

    proposals: list[Proposal] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
