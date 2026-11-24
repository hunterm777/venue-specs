"""Fetching sources. Public pages only: no sign-in, no cookies, no API keys."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

from .diff import html_text, json_text, pdf_text, plain
from .model import Source

USER_AGENT = "venue-specs-watcher (+https://github.com/hunterm777/venue-specs)"


class FetchError(Exception):
    """A source could not be fetched."""


def _get(src: Source, timeout: float) -> bytes:
    data = src.body.encode() if src.kind == "json_post" and src.body else None
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(src.url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # https URLs from sources.yaml only
        body: bytes = resp.read()
        return body


def fetch(src: Source, timeout: float = 30.0, tries: int = 3) -> str:
    """Fetch a source and return its normalised snapshot text."""
    last: Exception | None = None
    for attempt in range(tries):
        try:
            raw = _get(src, timeout)
            break
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise FetchError(f"{src.url}: HTTP {e.code}") from e
            last = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        time.sleep(2**attempt)
    else:
        raise FetchError(f"{src.url}: {last}")
    return normalise(src, raw)


def normalise(src: Source, raw: bytes) -> str:
    """Turn fetched bytes into the snapshot text kept in watch/snapshots/."""
    if src.kind == "pdf":
        return pdf_text(raw)
    text = raw.decode("utf-8", errors="replace")
    if src.kind == "html":
        return html_text(text)
    if src.kind == "json_post":
        return json_text(text, src.keep)
    return plain(text)
