"""The weekly watcher: fetch every source, diff against snapshots, parse, update specs, log.

    python -m watch.run                    # fetch live, update the repo in place
    python -m watch.run --offline DIR      # read fetched copies from DIR/<id>.txt instead
    python -m watch.run --date 2026-11-24  # the detection date to log (default: today, UTC)

It writes the updated specs, history, snapshots and CHANGELOG.md, and a summary for the
workflow in --out (default watch-out/): summary.json with what changed and the issues to open.
It never commits, tags or opens issues itself; .github/workflows/watch.yml does that after the
specs validate and the tests pass.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from . import changelog
from .diff import excerpt, unified
from .fetch import FetchError, fetch
from .model import Change, Issue, ParseResult, Proposal, Source
from .specio import ROOT
from .update import apply_all
from .version import bump

SOURCES = ROOT / "watch" / "sources.yaml"
SNAPSHOTS = ROOT / "watch" / "snapshots"


def load_sources(path: Path = SOURCES) -> list[Source]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    out = []
    for s in data["sources"]:
        out.append(
            Source(
                id=s["id"],
                venue=s["venue"],
                products=tuple(s["products"]),
                url=s["url"],
                kind=s["kind"],
                parser=s.get("parser"),
                body=s.get("body"),
                keep=tuple(s.get("keep", ())),
                title=s.get("title", s["id"]),
                covers=tuple(s.get("covers", ())),
            )
        )
    ids = [s.id for s in out]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate source ids in sources.yaml")
    return out


def parse(src: Source, text: str) -> ParseResult:
    if not src.parser:
        return ParseResult()
    module, func = src.parser.rsplit(".", 1)
    fn = getattr(importlib.import_module(f"watch.parsers.{module}"), func)
    try:
        result: ParseResult = fn(text, src)
    except (ValueError, ArithmeticError) as e:  # a malformed cell: read nothing from this page
        return ParseResult(problems=[f"{src.parser} failed: {e}"])
    return result


def _issue_docs_only(src: Source, diff: str, problems: list[str]) -> Issue:
    why = "This page has no parser, so" if not src.parser else "The parser found no spec value that changed, so"
    lines = [
        f"The watcher saw a change to **{src.title}** ({src.url}).",
        "",
        f"{why} nothing in the specs was updated. The snapshot and a Docs-only changelog entry were committed.",
        "Read the change below and update the spec by hand if a rule changed.",
    ]
    if problems:
        lines += ["", "Parser problems:", *[f"- {p}" for p in problems]]
    lines += ["", "```diff", excerpt(diff).rstrip("\n"), "```"]
    return Issue(f"Docs changed: {src.title}", "\n".join(lines))


def run(
    today: str,
    offline: Path | None = None,
    snapshots: Path = SNAPSHOTS,
    root: Path = ROOT,
    sources: list[Source] | None = None,
    only: set[str] | None = None,
) -> dict[str, Any]:
    sources = sources if sources is not None else load_sources()
    snapshots.mkdir(parents=True, exist_ok=True)
    proposals: list[Proposal] = []
    by_source: dict[str, list[Proposal]] = {}
    docs: list[tuple[Source, str, list[str]]] = []  # changed sources, their diff, parser problems
    baseline: list[str] = []
    fetch_errors: list[dict[str, str]] = []
    new_snapshots: dict[str, str] = {}

    for src in sources:
        if only and src.id not in only:
            continue
        try:
            if offline is not None:
                f = offline / f"{src.id}.txt"
                if not f.exists():
                    continue
                text = f.read_text(encoding="utf-8")
            else:
                text = fetch(src)
        except FetchError as e:
            fetch_errors.append({"id": src.id, "url": src.url, "error": str(e)})
            continue
        snap = snapshots / f"{src.id}.txt"
        old = snap.read_text(encoding="utf-8") if snap.exists() else None
        if old == text:
            continue
        new_snapshots[src.id] = text
        result = parse(src, text)
        by_source[src.id] = result.proposals
        proposals.extend(result.proposals)
        if old is None:
            baseline.append(src.id)
            if result.problems:
                docs.append((src, "", result.problems))
        else:
            docs.append((src, unified(old, text, src.id), result.problems))

    changes, written = apply_all(proposals, today, root)
    touched = {(c.venue, c.product, c.source) for c in changes}

    issues: list[Issue] = []
    for src, diff, problems in docs:
        moved = any((p.venue, p.product, p.source) in touched for p in by_source.get(src.id, []))
        if moved and not problems:
            continue
        if diff:
            if not moved:
                for product in src.products:
                    changes.append(
                        Change(
                            "Docs-only",
                            src.venue,
                            product,
                            f"{src.title} changed; no spec value parsed (see the issue opened today)",
                            src.url,
                        )
                    )
            issues.append(_issue_docs_only(src, diff, problems))
        else:
            issues.append(
                Issue(
                    f"Parser problem: {src.title}",
                    f"The parser for {src.url} could not read everything it expects:\n\n"
                    + "\n".join(f"- {p}" for p in problems),
                )
            )
    for err in fetch_errors:
        issues.append(
            Issue(f"Fetch failed: {err['id']}", f"The watcher could not fetch {err['url']}:\n\n    {err['error']}")
        )

    for sid, text in new_snapshots.items():
        (snapshots / f"{sid}.txt").write_text(text, encoding="utf-8")
    changelog.write(changes, today, root / "CHANGELOG.md")
    spec_changed = any(c.kind != "Docs-only" for c in changes)
    version = bump(today, root) if spec_changed else None
    return {
        "date": today,
        "spec_changed": spec_changed,
        "files_changed": bool(new_snapshots or changes),
        "version": version,
        "changes": [asdict(c) for c in changes],
        "issues": [asdict(i) for i in issues],
        "baseline": baseline,
        "fetch_errors": fetch_errors,
        "written": [str(p.relative_to(root)) for p in written],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    ap.add_argument("--offline", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "watch-out")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args(argv)
    summary = run(args.date, offline=args.offline, only=set(args.only) if args.only else None)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        f"{len(summary['changes'])} changelog entries, {len(summary['issues'])} issues, "
        f"{len(summary['baseline'])} new snapshots, {len(summary['fetch_errors'])} fetch errors; "
        f"spec changed: {summary['spec_changed']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
