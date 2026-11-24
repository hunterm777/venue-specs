"""Validate every spec and history file against schema/spec.schema.json."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import ValidationError

from watch.specio import ROOT, SCHEMA, load_yaml, spec_files


def _validator(ref: str | None = None) -> Any:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    if ref:
        schema = {**schema, "$ref": ref}
        for key in ("required", "properties", "additionalProperties", "allOf", "type", "title", "description"):
            schema.pop(key, None)
    checker = Draft202012Validator.TYPE_CHECKER.redefine(
        "number", lambda _c, v: isinstance(v, (int, Decimal)) and not isinstance(v, bool)
    )
    cls = validators.extend(Draft202012Validator, type_checker=checker)  # type: ignore[no-untyped-call]
    return cls(schema)


def validate_all(root: Path = ROOT) -> list[str]:
    spec_v = _validator()
    hist_v = _validator("#/$defs/history_file")
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted((root / "specs").glob("*/*.yaml")):
        doc = load_yaml(path)
        errors += [f"{path.name}: {_fmt(e)}" for e in spec_v.iter_errors(doc)]
        venue, product = path.parent.name, path.stem
        if (doc.get("venue"), doc.get("product")) != (venue, product):
            errors.append(f"{path}: venue/product must match its path {venue}/{product}")
        seen.add((venue, product))
    for path in sorted((root / "history").glob("*/*.yaml")):
        doc = load_yaml(path)
        errors += [f"history/{path.parent.name}/{path.name}: {_fmt(e)}" for e in hist_v.iter_errors(doc)]
        if (path.parent.name, path.stem) not in seen:
            errors.append(f"{path}: no matching spec file")
    return errors


def _fmt(err: ValidationError) -> str:
    loc = ".".join(str(p) for p in err.absolute_path) or "<root>"
    return f"{loc}: {err.message}"


def main() -> int:
    errors = validate_all()
    for e in errors:
        print(e, file=sys.stderr)
    print(f"{len(spec_files())} spec files, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
