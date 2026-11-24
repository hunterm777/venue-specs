"""Writing our dated CHANGELOG.md, newest first, in the PRD's format."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .model import Change
from .specio import ROOT

VENUE_NAMES = {"kalshi": "Kalshi", "polymarket": "Polymarket", "hyperliquid": "Hyperliquid"}
ORDER = {"Changed": 0, "Added": 1, "Removed": 2, "Upcoming": 3, "Docs-only": 4}
INTRO = (
    "# Changelog\n\n"
    "Written by the weekly watcher (`watch/run.py`). Entries are dated by the day a change was detected\n"
    "and say when it takes effect at the venue. Entry types: Changed, Added, Removed, Upcoming\n"
    "(announced, not yet in force) and Docs-only (a watched page changed, no spec value affected).\n"
)


def _line(c: Change) -> str:
    when = ""
    if c.effective_from:
        when = f" (effective {c.effective_from})" if c.kind != "Upcoming" else f" (takes effect {c.effective_from})"
    out = f"- {c.kind}: {c.summary}{when}\n  Source: {c.source}\n"
    if c.spec_file and c.section:
        out += f"  Spec: {c.spec_file} → {c.section}\n"
    return out


def render(changes: list[Change]) -> str:
    """Venue sections for one day's changes, without the date heading."""
    groups: dict[tuple[str, str], list[Change]] = defaultdict(list)
    for c in changes:
        groups[(c.venue, c.product)].append(c)
    parts = []
    for (venue, product), items in sorted(groups.items()):
        items.sort(key=lambda c: (ORDER.get(c.kind, 9), c.summary))
        body = "".join(_line(c) for c in items)
        parts.append(f"### {VENUE_NAMES.get(venue, venue)} — {product}\n{body}")
    return "\n".join(parts)


def write(changes: list[Change], day: str, path: Path | None = None) -> bool:
    """Add one day's entries at the top (merging with an entry already written that day)."""
    if not changes:
        return False
    path = path or ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8") if path.exists() else INTRO
    head, sep, rest = text.partition("\n## ")
    block = render(changes)
    if sep and rest.startswith(day + "\n"):
        first, sep2, older = rest.partition("\n## ")
        merged = first.rstrip("\n") + "\n\n" + block
        text = head + "\n## " + merged + ("\n\n## " + older if sep2 else "\n")
    else:
        text = head.rstrip("\n") + f"\n\n## {day}\n\n{block}" + ("\n## " + rest if sep else "")
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    return True
