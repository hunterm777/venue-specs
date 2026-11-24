"""Open the watcher's issues with the GitHub CLI, or comment on an open one with the same title."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main(argv: list[str]) -> int:
    summary = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    extra = json.loads(Path(argv[1]).read_text(encoding="utf-8")) if len(argv) > 1 else []
    open_issues = json.loads(_gh("issue", "list", "--state", "open", "--limit", "200", "--json", "number,title"))
    by_title = {i["title"]: i["number"] for i in open_issues}
    for issue in [*summary.get("issues", []), *extra]:
        if issue["title"] in by_title:
            _gh("issue", "comment", str(by_title[issue["title"]]), "--body", issue["body"])
        else:
            _gh("issue", "create", "--title", issue["title"], "--body", issue["body"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
