"""Load and dump spec YAML exactly: numbers as Decimal, dates as strings."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
HISTORY = ROOT / "history"
SCHEMA = ROOT / "schema" / "spec.schema.json"


class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps decimals exact and leaves dates as text."""


def _decimal(loader: yaml.SafeLoader, node: yaml.Node) -> Decimal:
    return Decimal(loader.construct_scalar(node).replace("_", ""))  # type: ignore[arg-type]


_Loader.add_constructor("tag:yaml.org,2002:float", _decimal)
_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:timestamp"]
    for k, v in _Loader.yaml_implicit_resolvers.items()
}


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_Loader)


def spec_files() -> list[Path]:
    return sorted(SPECS.glob("*/*.yaml"))


def history_path(venue: str, product: str) -> Path:
    return HISTORY / venue / f"{product}.yaml"


def to_json(obj: Any) -> Any:
    """Convert loaded YAML to JSON-safe data, keeping decimals as Decimal."""
    if isinstance(obj, dict):
        return {str(k): to_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json(v) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, (str, Decimal)):
        return obj
    if isinstance(obj, int):
        return obj
    raise TypeError(f"unsupported value {obj!r}")


def dumps(obj: Any, indent: int | None = None, _level: int = 0) -> str:
    """JSON encoder that writes Decimal as an exact JSON number."""
    pad = "" if indent is None else "\n" + " " * (indent * (_level + 1))
    end = "" if indent is None else "\n" + " " * (indent * _level)
    sep = ","
    colon = ":" if indent is None else ": "
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        items = [f"{pad}{json.dumps(k)}{colon}{dumps(v, indent, _level + 1)}" for k, v in obj.items()]
        return "{" + sep.join(items) + end + "}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        items = [f"{pad}{dumps(v, indent, _level + 1)}" for v in obj]
        return "[" + sep.join(items) + end + "]"
    if isinstance(obj, bool) or obj is None:
        return json.dumps(obj)
    if isinstance(obj, Decimal):
        text = format(obj, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".") or "0"
        return text if text != "-0" else "0"
    if isinstance(obj, (int, str)):
        return json.dumps(obj)
    raise TypeError(f"unsupported value {obj!r}")


def json_safe(obj: Any) -> Any:
    """Decimal -> float-free JSON types for jsonschema (numbers as Decimal stay numbers)."""
    return to_json(obj)
