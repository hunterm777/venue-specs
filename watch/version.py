"""Calendar versions: YYYY.MM.DD, then YYYY.MM.DD.N for a second release the same day.

The crate cannot use four-part versions, so Cargo.toml carries YYYY.(MM*100+DD).N, where N is 0
for the first release of the day.
"""

from __future__ import annotations

import re
from pathlib import Path

from .specio import ROOT


def next_version(current: str, day: str) -> str:
    """The data version for a release on `day` (YYYY-MM-DD)."""
    base = day.replace("-", ".")
    if current == base:
        return f"{base}.1"
    if current.startswith(base + "."):
        return f"{base}.{int(current.rsplit('.', 1)[1]) + 1}"
    return base


def crate_version(version: str) -> str:
    """2026.11.24 -> 2026.1124.0; 2026.11.24.2 -> 2026.1124.2."""
    parts = version.split(".")
    y, m, d = (int(p) for p in parts[:3])
    n = int(parts[3]) if len(parts) > 3 else 0
    return f"{y}.{m * 100 + d}.{n}"


def python_version(version: str) -> str:
    """PEP 440 normalises 2026.11.24 to itself and 2026.11.24.1 likewise."""
    return ".".join(str(int(p)) for p in version.split("."))


_PKG_VERSION = re.compile(r'(?m)^version = "[^"]*"$')


def bump(day: str, root: Path = ROOT) -> str:
    """Write the next version to VERSION, both Cargo.toml files and pyproject.toml."""
    current = (root / "VERSION").read_text(encoding="utf-8").strip()
    new = next_version(current, day)
    (root / "VERSION").write_text(new + "\n", encoding="utf-8")
    for rel, value in (
        ("crates/venue-specs/Cargo.toml", crate_version(new)),
        ("crates/venue-specs-py/Cargo.toml", crate_version(new)),
        ("crates/venue-specs-py/pyproject.toml", python_version(new)),
    ):
        path = root / rel
        text = path.read_text(encoding="utf-8")
        path.write_text(_PKG_VERSION.sub(f'version = "{value}"', text, count=1), encoding="utf-8")
    return new
