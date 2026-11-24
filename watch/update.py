"""Apply parsed values to the spec and history files.

A value equal to the one on file changes nothing. A value for an unverified or missing entry is
Added. A different value replaces the one on file, which moves to history/ with its validity
ending when the new value starts: Upcoming when that is after today, Changed otherwise. When the
source states no start date, the new value starts on the day it was first seen.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from .model import Change, Proposal
from .specio import ROOT, load_yaml

UNDATED = "Start date not stated by the source; effective_from is the day the change was first seen."
LEAF_KEYS = ("value", "formula", "source", "as_of", "effective_from", "unit", "note")


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    y.representer.add_representer(
        Decimal,
        lambda r, d: r.represent_scalar("tag:yaml.org,2002:" + ("float" if "." in _num(d) else "int"), _num(d)),
    )
    return y


def _num(d: Decimal) -> str:
    """Exact decimal text; whole numbers are written as integers (read back exactly either way)."""
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _start(effective: str | None) -> str:
    return (effective or "")[:10]


def _date(text: str) -> Any:
    """Plain YYYY-MM-DD is written unquoted, like the hand-written files; instants stay strings."""
    if len(text) == 10:
        return dt.date.fromisoformat(text)
    return text


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, (Decimal, int)) and isinstance(b, (Decimal, int)) and not isinstance(a, bool):
        return Decimal(a) == Decimal(b)
    return bool(a == b)


def _get(doc: Any, path: str) -> Any:
    node = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _is_leaf(node: Any) -> bool:
    return isinstance(node, dict) and "source" in node


def _flow(m: dict[str, Any]) -> CommentedMap:
    out = CommentedMap()
    for k in LEAF_KEYS:
        if k in m:
            v = m[k]
            out[k] = DoubleQuotedScalarString(v) if isinstance(v, str) else v
    out.fa.set_flow_style()
    return out


class SpecFiles:
    """Round-trip editor for one venue x product spec and its history file."""

    def __init__(self, venue: str, product: str, root: Path = ROOT) -> None:
        self.venue, self.product = venue, product
        self.spec_path = root / "specs" / venue / f"{product}.yaml"
        self.history_path = root / "history" / venue / f"{product}.yaml"
        self.rel = f"specs/{venue}/{product}.yaml"
        self._y = _yaml()
        self.exact = load_yaml(self.spec_path)  # Decimal view, for comparisons
        self.doc = self._y.load(self.spec_path.read_text(encoding="utf-8"))
        self.history: Any = None
        self.dirty = False

    def _history(self) -> Any:
        if self.history is None:
            if self.history_path.exists():
                self.history = self._y.load(self.history_path.read_text(encoding="utf-8"))
            else:
                header = [("schema_version", 1), ("venue", self.venue), ("product", self.product)]
                self.history = CommentedMap([*header, ("entries", CommentedSeq())])
        return self.history

    def _set(self, path: str, leaf: CommentedMap) -> None:
        parts = path.split(".")
        node = self.doc
        exact = self.exact
        for p in parts[:-1]:
            child = node.get(p)
            if not isinstance(child, dict) or "source" in child or "unverified" in child:
                child = CommentedMap()
                node[p] = child
                exact[p] = {}
            node = child
            exact = exact[p]
        node[parts[-1]] = leaf
        exact[parts[-1]] = {k: v for k, v in leaf.items()}
        self.dirty = True

    def apply(self, prop: Proposal, today: str) -> Change | None:
        """Apply one proposal; return the changelog line, or None when nothing changed."""
        cur = _get(self.exact, prop.path)
        new: dict[str, Any] = {}
        if prop.formula is not None:
            new["formula"] = prop.formula
        else:
            new["value"] = prop.value
        new["source"] = prop.source
        new["as_of"] = _date(today)
        section = prop.path.split(".")[0]

        def change(kind: str, summary: str, effective: str | None) -> Change:
            return Change(kind, self.venue, self.product, summary, prop.source, self.rel, section, effective)

        shown = prop.formula if prop.formula is not None else prop.value
        if not _is_leaf(cur):
            new["effective_from"] = _date(prop.effective_from) if prop.effective_from else None
            if prop.note:
                new["note"] = prop.note
            self._set(prop.path, _flow(new))
            self._bump(prop.effective_from or today)
            return change("Added", f"{prop.path} = {shown}", prop.effective_from)

        old_val = cur.get("formula") if prop.formula is not None else cur.get("value")
        if _same(old_val, shown) and ("formula" in cur) == (prop.formula is not None):
            return None

        starts = prop.effective_from or today
        for k in ("unit", "note"):
            if k in cur:
                new[k] = cur[k]
        if prop.note:
            new["note"] = prop.note
        if prop.effective_from is None:
            new["note"] = (str(new.get("note", "")).replace(UNDATED, "").strip() + " " + UNDATED).strip()
        new["effective_from"] = _date(starts)
        cur_start = str(cur.get("effective_from") or "")
        if cur_start and _start(cur_start) > today:
            # The value on file was announced but never took effect; replace it, no history.
            self._set(prop.path, _flow(new))
            self._bump(starts)
            kind = "Upcoming" if _start(starts) > today else "Changed"
            return change(kind, f"{prop.path} {old_val} -> {shown} (announcement revised)", starts)

        hist_leaf = {k: cur[k] for k in LEAF_KEYS if k in cur}
        hist_leaf["as_of"] = _date(str(hist_leaf["as_of"]))
        if hist_leaf.get("effective_from"):
            hist_leaf["effective_from"] = _date(str(hist_leaf["effective_from"]))
        entry = CommentedMap([("path", prop.path), ("valid_to", _date(starts)), ("leaf", _flow(hist_leaf))])
        entry.fa.set_flow_style()
        self._history()["entries"].append(entry)
        self._set(prop.path, _flow(new))
        self._bump(starts)
        kind = "Upcoming" if _start(starts) > today else "Changed"
        return change(kind, f"{prop.path} {old_val} -> {shown}", starts)

    def _bump(self, starts: str) -> None:
        day = _start(starts)
        if day > str(self.doc.get("version_of_rules")):
            self.doc["version_of_rules"] = _date(day)
            self.exact["version_of_rules"] = day

    def save(self) -> list[Path]:
        if not self.dirty:
            return []
        with self.spec_path.open("w", encoding="utf-8") as fh:
            self._y.dump(self.doc, fh)
        written = [self.spec_path]
        if self.history is not None:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with self.history_path.open("w", encoding="utf-8") as fh:
                self._y.dump(self.history, fh)
            written.append(self.history_path)
        return written


def normalise(root: Path = ROOT) -> list[Path]:
    """Rewrite every spec and history file in the form the watcher writes, so its edits
    show up as one-line diffs."""
    y = _yaml()
    out = []
    for path in sorted((root / "specs").glob("*/*.yaml")) + sorted((root / "history").glob("*/*.yaml")):
        doc = y.load(path.read_text(encoding="utf-8"))
        with path.open("w", encoding="utf-8") as fh:
            y.dump(doc, fh)
        out.append(path)
    return out


def apply_all(proposals: list[Proposal], today: str, root: Path = ROOT) -> tuple[list[Change], list[Path]]:
    """Apply proposals grouped by spec file; return changelog lines and files written."""
    files: dict[tuple[str, str], SpecFiles] = {}
    changes: list[Change] = []
    for p in proposals:
        key = (p.venue, p.product)
        if key not in files:
            files[key] = SpecFiles(p.venue, p.product, root)
        c = files[key].apply(p, today)
        if c:
            changes.append(c)
    written = [path for f in files.values() for path in f.save()]
    return changes, written
