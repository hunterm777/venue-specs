"""Normalising fetched sources and diffing them against stored snapshots."""

from __future__ import annotations

import difflib
import hashlib
import html
import json
import re
from typing import Any

_SCRIPT = re.compile(r"<(script|style|noscript)\b.*?</\1\s*>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|li|tr|h[1-6]|br|section|article|table|ul|ol)\b[^>]*>", re.I)


def html_text(raw: str) -> str:
    """Visible text of an HTML page, one block per line, so diffs show words, not markup."""
    text = _SCRIPT.sub("", raw)
    text = _BLOCK.sub("\n", text)
    text = html.unescape(_TAG.sub("", text))
    lines = (re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line) + "\n"


def json_text(raw: str, keep: tuple[str, ...] = ()) -> str:
    """Canonical JSON, keeping only `keep` keys when given (drops fast-moving fields)."""
    data: Any = json.loads(raw)
    if keep and isinstance(data, dict):
        data = {k: data[k] for k in keep if k in data}
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def pdf_text(raw: bytes) -> str:
    """A PDF is tracked by hash: any byte change counts as a change to review."""
    return f"sha256 {hashlib.sha256(raw).hexdigest()}\nbytes {len(raw)}\n"


def plain(raw: str) -> str:
    """Markdown or RSS: trim trailing space and settle line endings."""
    lines = [line.rstrip() for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def unified(old: str, new: str, name: str) -> str:
    """Unified diff of two snapshots."""
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True), f"{name} (before)", f"{name} (after)", n=2
        )
    )


def excerpt(diff: str, max_lines: int = 120) -> str:
    """The first lines of a diff, for an issue body."""
    lines = diff.splitlines()
    if len(lines) <= max_lines:
        return diff
    return "\n".join(lines[:max_lines]) + f"\n... {len(lines) - max_lines} more diff lines\n"


def added_lines(diff: str) -> list[str]:
    """Lines the new snapshot adds."""
    return [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
