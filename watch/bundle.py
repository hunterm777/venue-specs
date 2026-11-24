"""Build venue-specs.json from the YAML specs and history.

The Rust crate embeds this file, the Python package wraps the crate, and the release
attaches it as an asset, so all three carry the same data and version.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from watch.specio import HISTORY, ROOT, dumps, load_yaml, spec_files, to_json

BUNDLE = ROOT / "crates" / "venue-specs" / "data" / "venue-specs.json"


def version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def build() -> dict[str, Any]:
    specs = [to_json(load_yaml(p)) for p in spec_files()]
    history = [to_json(load_yaml(p)) for p in sorted(HISTORY.glob("*/*.yaml"))]
    return {"schema_version": 1, "version": version(), "specs": specs, "history": history}


def render() -> str:
    return dumps(build(), indent=1) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        current = BUNDLE.read_text(encoding="utf-8") if BUNDLE.exists() else ""
        if current != text:
            print(f"{BUNDLE.relative_to(ROOT)} is out of date; run python -m watch.bundle", file=sys.stderr)
            return 1
        print("bundle up to date")
        return 0
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else BUNDLE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
