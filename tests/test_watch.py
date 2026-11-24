"""Watcher tests: parsers against real captures, the spec updater, and the M3 replays."""

from __future__ import annotations

import datetime as dt
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from watch import changelog
from watch.model import Proposal
from watch.parsers import hyperliquid, kalshi, polymarket
from watch.run import load_sources, run
from watch.specio import ROOT, load_yaml
from watch.update import Conflict, apply_all
from watch.validate import validate_all
from watch.version import crate_version, next_version

FIX = ROOT / "tests" / "fixtures" / "watch"
SOURCES = {s.id: s for s in load_sources()}


def _get(doc: dict, path: str):  # type: ignore[no-untyped-def]
    for part in path.split("."):
        doc = doc[part]
    return doc


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A scratch copy of the files the watcher writes."""
    for rel in ("specs", "history", "schema"):
        shutil.copytree(ROOT / rel, tmp_path / rel)
    for rel in (
        "VERSION",
        "crates/venue-specs/Cargo.toml",
        "crates/venue-specs-py/Cargo.toml",
        "crates/venue-specs-py/pyproject.toml",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    return tmp_path


def test_sources_cover_every_spec_citation() -> None:
    urls = {s.url for s in SOURCES.values()} | {u for s in SOURCES.values() for u in s.covers}
    cited: set[str] = set()

    def walk(n: object) -> None:
        if isinstance(n, dict):
            if isinstance(n.get("source"), str):
                cited.add(n["source"])
            for v in n.values():
                walk(v)

    for p in sorted((ROOT / "specs").glob("*/*.yaml")):
        walk(load_yaml(p))
    assert cited - urls == set()
    assert all(s.url.startswith("https://") for s in SOURCES.values())


@pytest.mark.parametrize("flatten", [False, True])
def test_hyperliquid_fee_parser_matches_spec(flatten: bool) -> None:
    text = (FIX / "hyperliquid_fees.md").read_text()
    if flatten:  # the same page with its line breaks collapsed, as a browser shows it
        text = " ".join(text.split())
    res = hyperliquid.fees(text, SOURCES["hyperliquid_fees"])
    assert res.problems == []
    assert len(res.proposals) == 7 * 3 + 3 * 2
    spec = load_yaml(ROOT / "specs/hyperliquid/perp.yaml")
    for p in res.proposals:
        assert _get(spec, p.path)["value"] == p.value, p.path


def test_hyperliquid_funding_parser_matches_spec() -> None:
    res = hyperliquid.funding((FIX / "hyperliquid_funding.md").read_text(), SOURCES["hyperliquid_funding"])
    assert res.problems == []
    spec = load_yaml(ROOT / "specs/hyperliquid/perp.yaml")
    got = {p.path: p.value for p in res.proposals}
    assert got == {
        "funding.interest_rate_8h": Decimal("0.0001"),
        "funding.premium_clamp": Decimal("0.0005"),
        "funding.cap_per_hour": Decimal("0.005"),
    }
    for path, value in got.items():
        assert _get(spec, path)["value"] == value


def test_parser_reports_a_broken_table_and_proposes_nothing_from_it() -> None:
    text = (FIX / "hyperliquid_fees.md").read_text().replace("| 3    | >100M", "| x    | >100M")
    res = hyperliquid.fees(text, SOURCES["hyperliquid_fees"])
    assert any("perps fee tier table" in p for p in res.problems)
    assert not any(p.path.startswith("fees.tiers.") for p in res.proposals)


def test_kalshi_fixed_point_parser() -> None:
    res = kalshi.fixed_point("Contracts. Minimum granularity is 0.01 contracts.", SOURCES["kalshi_fixed_point"])
    assert [(p.path, p.value) for p in res.proposals] == [("size.step", Decimal("0.01"))]
    assert kalshi.fixed_point("nothing here", SOURCES["kalshi_fixed_point"]).problems


def test_versions() -> None:
    assert next_version("2026.11.24", "2026-11-25") == "2026.11.25"
    assert next_version("2026.11.24", "2026-11-24") == "2026.11.24.1"
    assert next_version("2026.11.24.1", "2026-11-24") == "2026.11.24.2"
    assert crate_version("2026.11.24") == "2026.1124.0"
    assert crate_version("2026.01.05.3") == "2026.105.3"


def test_unchanged_sources_change_nothing(repo: Path) -> None:
    snaps, offline = repo / "snaps", repo / "offline"
    offline.mkdir()
    shutil.copy(FIX / "hyperliquid_fees.md", offline / "hyperliquid_fees.txt")
    first = run("2026-11-24", offline=offline, snapshots=snaps, root=repo, sources=list(SOURCES.values()))
    # First sight of a page records a baseline snapshot; values match the spec, so no entry.
    assert first["baseline"] == ["hyperliquid_fees"] and first["changes"] == [] and first["issues"] == []
    again = run("2026-11-25", offline=offline, snapshots=snaps, root=repo, sources=list(SOURCES.values()))
    assert again["files_changed"] is False and again["changes"] == []


def test_replay_hyperliquid_fee_change(repo: Path) -> None:
    """A real capture with tier 0 taker moved from 0.045% to 0.040%: Changed, history kept."""
    snaps, offline = repo / "snaps", repo / "offline"
    snaps.mkdir()
    offline.mkdir()
    shutil.copy(FIX / "hyperliquid_fees.md", snaps / "hyperliquid_fees.txt")
    after = (FIX / "hyperliquid_fees.md").read_text().replace("| 0.045%    | 0.015% |", "| 0.040%    | 0.015% |")
    (offline / "hyperliquid_fees.txt").write_text(after)

    out = run("2026-12-01", offline=offline, snapshots=snaps, root=repo, sources=list(SOURCES.values()))
    assert out["spec_changed"] and out["version"] == "2026.12.01" and out["issues"] == []
    assert [(c["kind"], c["summary"]) for c in out["changes"]] == [("Changed", "fees.tiers.0.taker 0.00045 -> 0.0004")]

    spec = load_yaml(repo / "specs/hyperliquid/perp.yaml")
    leaf = spec["fees"]["tiers"]["0"]["taker"]
    assert leaf["value"] == Decimal("0.0004") and leaf["effective_from"] == "2026-12-01"
    assert leaf["as_of"] == "2026-12-01" and spec["version_of_rules"] == "2026-12-01"
    hist = load_yaml(repo / "history/hyperliquid/perp.yaml")
    assert hist["entries"] == [
        {
            "path": "fees.tiers.0.taker",
            "valid_to": "2026-12-01",
            "leaf": {
                "value": Decimal("0.00045"),
                "source": "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees.md",
                "as_of": "2026-11-24",
                "note": "Base rate, before staking, referral, aligned-quote and HIP-3 adjustments.",
            },
        }
    ]
    assert leaf["note"].startswith("Base rate, before staking") and leaf["note"].endswith("first seen.")
    assert validate_all(repo) == []
    log = (repo / "CHANGELOG.md").read_text()
    assert (
        "## 2026-12-01\n\n### Hyperliquid — perp\n"
        "- Changed: fees.tiers.0.taker 0.00045 -> 0.0004 (effective 2026-12-01)"
    ) in log
    assert "  Spec: specs/hyperliquid/perp.yaml → fees" in log
    assert (repo / "VERSION").read_text().strip() == "2026.12.01"
    assert 'version = "2026.1201.0"' in (repo / "crates/venue-specs/Cargo.toml").read_text()
    # Untouched lines keep their hand-written form, comments included.
    text = (repo / "specs/hyperliquid/perp.yaml").read_text()
    assert text.startswith("# Hyperliquid perpetuals")
    assert '    "1":\n      min_14d_weighted_volume: {value: 5000000, source: "https://hyperliquid' in text
    assert text.count("\n") == (ROOT / "specs/hyperliquid/perp.yaml").read_text().count("\n")


def test_replay_kalshi_maker_fees_aug_2026(repo: Path) -> None:
    """M3 replay 1 (reconstructed feed): Kalshi's maker-fee announcement is prose, so the PRD's
    default applies: snapshot + Docs-only entry + an issue quoting the diff, specs unchanged."""
    snaps, offline = repo / "snaps", repo / "offline"
    snaps.mkdir()
    offline.mkdir()
    shutil.copy(FIX / "kalshi_changelog_before.xml", snaps / "kalshi_changelog.txt")
    shutil.copy(FIX / "kalshi_changelog_after.xml", offline / "kalshi_changelog.txt")
    before = {p: p.read_text() for p in (repo / "specs").glob("*/*.yaml")}

    out = run("2026-08-22", offline=offline, snapshots=snaps, root=repo, sources=list(SOURCES.values()))
    assert not out["spec_changed"] and out["version"] is None
    assert [(c["kind"], c["product"]) for c in out["changes"]] == [("Docs-only", "binary"), ("Docs-only", "perp")]
    assert len(out["issues"]) == 1
    issue = out["issues"][0]
    assert issue["title"] == "Docs changed: Kalshi changelog (RSS)"
    assert "+      <description>Maker fees will be enabled at 5:00 AM ET on Thursday, August 20" in issue["body"]
    assert before == {p: p.read_text() for p in (repo / "specs").glob("*/*.yaml")}
    log = (repo / "CHANGELOG.md").read_text()
    assert "### Kalshi — binary\n- Docs-only: Kalshi changelog (RSS) changed" in log
    assert (snaps / "kalshi_changelog.txt").read_text() == (FIX / "kalshi_changelog_after.xml").read_text()


PM_TICKS = {
    "ANT": "2026-11-19T11:00:00Z",
    "INTC": "2026-11-19T11:00:00Z",
    "SNDK": "2026-11-20T13:00:00Z",
}


@pytest.mark.parametrize("flatten", [False, True])
def test_polymarket_changelog_parser_matches_spec(flatten: bool) -> None:
    text = (FIX / "polymarket_perps_changelog_after.txt").read_text()
    if flatten:
        text = " ".join(text.split())
    res = polymarket.perps_changelog(text, SOURCES["polymarket_perps_changelog"])
    assert res.problems == []
    got = {(p.path, p.value, p.effective_from) for p in res.proposals}
    want = set()
    for market, starts in PM_TICKS.items():
        want |= {
            (f"price_grid.markets.{market}.tick", Decimal("0.001"), starts),
            (f"size.markets.{market}.step", Decimal("0.001"), starts),
        }
    assert got == want
    spec = load_yaml(ROOT / "specs/polymarket/perp.yaml")
    for p in res.proposals:
        leaf = _get(spec, p.path)
        assert (leaf["value"], leaf["effective_from"]) == (p.value, p.effective_from), p.path


def test_polymarket_changelog_parser_keeps_the_newest_entry_per_market() -> None:
    text = (
        "Dec 3, 2026 Later change Market Maintenance ANT tick size. During the maintenance window, the market "
        "moves to 2 quantity decimals and 2 price decimals: a 0.01 size step and a 0.01 price tick. Rollout "
        "Maintenance starts Thursday, December 3 at 6:00 AM ET (11:00 UTC). "
        + (FIX / "polymarket_perps_changelog_after.txt").read_text()
    )
    res = polymarket.perps_changelog(text, SOURCES["polymarket_perps_changelog"])
    ant = {p.path: (p.value, p.effective_from) for p in res.proposals if ".ANT." in p.path}
    assert ant == {
        "price_grid.markets.ANT.tick": (Decimal("0.01"), "2026-12-03T11:00:00Z"),
        "size.markets.ANT.step": (Decimal("0.01"), "2026-12-03T11:00:00Z"),
    }


def test_polymarket_changelog_parser_reports_a_tick_change_it_cannot_read() -> None:
    text = "Dec 3, 2026 ANT tick size changes to one tenth of a cent next week."
    res = polymarket.perps_changelog(text, SOURCES["polymarket_perps_changelog"])
    assert res.proposals == [] and res.problems and "Dec 3, 2026" in res.problems[0]
    assert polymarket.perps_changelog("no entries", SOURCES["polymarket_perps_changelog"]).problems


def test_replay_polymarket_tick_changes_nov_19(repo: Path) -> None:
    """M3 replay 2: the Perps changelog before and after its Nov 19, 2026 entry (excerpts of the
    page as pasted on 2026-11-24). ANT, INTC and SNDK gain their tick and size step; the docs give
    no earlier per-market values, so these are Added, with no history."""
    from watch.update import SpecFiles

    files = SpecFiles("polymarket", "perp", repo)
    for section in ("price_grid", "size"):
        del files.doc[section]["markets"]
    files.dirty = True
    files.save()
    snaps, offline = repo / "snaps", repo / "offline"
    snaps.mkdir()
    offline.mkdir()
    shutil.copy(FIX / "polymarket_perps_changelog_before.txt", snaps / "polymarket_perps_changelog.txt")
    shutil.copy(FIX / "polymarket_perps_changelog_after.txt", offline / "polymarket_perps_changelog.txt")
    hist_before = (repo / "history/polymarket/perp.yaml").read_text()

    out = run("2026-11-24", offline=offline, snapshots=snaps, root=repo, sources=list(SOURCES.values()))
    assert out["spec_changed"] and out["issues"] == [] and out["version"] == "2026.11.24.1"
    assert {c["kind"] for c in out["changes"]} == {"Added"} and len(out["changes"]) == 6
    assert ("price_grid.markets.SNDK.tick = 0.001", "2026-11-20T13:00:00Z") in {
        (c["summary"], c["effective_from"]) for c in out["changes"]
    }
    spec = load_yaml(repo / "specs/polymarket/perp.yaml")
    current = load_yaml(ROOT / "specs/polymarket/perp.yaml")
    for section in ("price_grid", "size"):
        assert spec[section]["markets"] == current[section]["markets"]
    assert (repo / "history/polymarket/perp.yaml").read_text() == hist_before
    assert validate_all(repo) == []
    log = (repo / "CHANGELOG.md").read_text()
    assert "### Polymarket — perp\n- Added: price_grid.markets.ANT.tick = 0.001" in log
    assert "  Spec: specs/polymarket/perp.yaml → price_grid" in log


def _pm_page(name: str, flatten: bool) -> str:
    text = (FIX / f"polymarket_perps_{name}.txt").read_text()
    return " ".join(text.split()) if flatten else text


@pytest.mark.parametrize("flatten", [False, True])
def test_polymarket_fees_parser_matches_the_rates_in_force(flatten: bool) -> None:
    """The fees page shows the rates in force until Nov 25, 2026: the spec as of Nov 24."""
    res = polymarket.perps_fees(_pm_page("fees", flatten), SOURCES["polymarket_perps_fees"])
    assert res.problems == [] and len(res.proposals) == 21
    spec = load_yaml(ROOT / "specs/polymarket/perp.yaml")
    hist = {e["path"]: e["leaf"]["value"] for e in load_yaml(ROOT / "history/polymarket/perp.yaml")["entries"]}
    for p in res.proposals:
        leaf = _get(spec, p.path)
        in_force = hist[p.path] if leaf.get("effective_from") else leaf["value"]
        assert in_force == p.value, p.path


@pytest.mark.parametrize("flatten", [False, True])
def test_polymarket_funding_parser_matches_spec(flatten: bool) -> None:
    res = polymarket.perps_funding(_pm_page("funding", flatten), SOURCES["polymarket_perps_funding"])
    assert res.problems == []
    spec = load_yaml(ROOT / "specs/polymarket/perp.yaml")
    got = {p.path: p.value for p in res.proposals}
    assert got == {
        "funding.sample_interval_seconds": Decimal(5),
        "funding.impact_notional": Decimal(1000),
        "funding.interval_hours": Decimal(1),
        "funding.cap_per_hour": Decimal("0.04"),
        "funding.interest_rate_8h": Decimal("0.0001"),
        "funding.premium_clamp": Decimal("0.0005"),
        "asset_classes.crypto.funding_scale": Decimal("1.0"),
        "asset_classes.other.funding_scale": Decimal("0.5"),
    }
    for path, value in got.items():
        assert _get(spec, path)["value"] == value, path


@pytest.mark.parametrize("flatten", [False, True])
def test_polymarket_margin_parser_matches_spec(flatten: bool) -> None:
    res = polymarket.perps_margin(_pm_page("margin", flatten), SOURCES["polymarket_perps_margin"])
    assert res.problems == []
    spec = load_yaml(ROOT / "specs/polymarket/perp.yaml")
    assert [(p.path, p.formula) for p in res.proposals] == [
        ("margin.maintenance_margin_rate", spec["margin"]["maintenance_margin_rate"]["formula"])
    ]


def test_polymarket_page_parsers_report_what_they_cannot_read() -> None:
    fees = polymarket.perps_fees(_pm_page("fees", True).replace("$1B", "1B"), SOURCES["polymarket_perps_fees"])
    assert fees.proposals == [] and fees.problems == ["perps fee tier table: expected 7 rows, found 6"]
    funding = polymarket.perps_funding("Funding is charged hourly.", SOURCES["polymarket_perps_funding"])
    assert funding.proposals == [] and len(funding.problems) == 6
    margin = polymarket.perps_margin("MMR depends on the market.", SOURCES["polymarket_perps_margin"])
    assert margin.proposals == [] and len(margin.problems) == 2


def test_reading_the_polymarket_pages_on_nov_24_changes_no_value(repo: Path) -> None:
    """Today's rates on the fees page match the history in force until Nov 25, so the upcoming
    rates on file are kept, and the funding and margin pages match the spec."""
    specs_before = (repo / "specs/polymarket/perp.yaml").read_text()
    hist_before = (repo / "history/polymarket/perp.yaml").read_text()
    props = []
    for name in ("fees", "funding", "margin"):
        props += getattr(polymarket, f"perps_{name}")(
            _pm_page(name, False), SOURCES[f"polymarket_perps_{name}"]
        ).proposals
    conflicts: list[Conflict] = []
    changes, _ = apply_all(props, "2026-11-24", repo, conflicts)
    assert changes == [] and conflicts == []
    assert (repo / "specs/polymarket/perp.yaml").read_text() == specs_before
    assert (repo / "history/polymarket/perp.yaml").read_text() == hist_before


def test_a_fee_page_that_disagrees_with_the_rate_in_force_opens_an_issue(repo: Path) -> None:
    """The page reads 0.0450% for tier 0 today, but the history says 0.0400% until Nov 25 and the
    notice says 0.0500% from then: nothing is written and an issue is opened."""
    specs_before = (repo / "specs/polymarket/perp.yaml").read_text()
    page = _pm_page("fees", False).replace("$0\t0.0400%", "$0\t0.0450%")
    assert page != _pm_page("fees", False)
    snaps, offline = repo / "snaps", repo / "offline"
    snaps.mkdir()
    offline.mkdir()
    (snaps / "polymarket_perps_fees.txt").write_text(_pm_page("fees", False))
    (offline / "polymarket_perps_fees.txt").write_text(page)
    out = run("2026-11-24", offline=offline, snapshots=snaps, root=repo, sources=[SOURCES["polymarket_perps_fees"]])
    assert not out["spec_changed"] and out["version"] is None and len(out["issues"]) == 1
    body = out["issues"][0]["body"]
    assert "fees.tiers.0.taker: the page reads 0.00045 for today" in body and "0.0005 is announced" in body
    assert (repo / "specs/polymarket/perp.yaml").read_text() == specs_before


def _pre_notice_spec(repo: Path) -> None:
    """Put the rates in force before Polymarket's Nov 2026 notice back in the spec, as it stood
    before the notice was published, and empty its history."""
    from watch.update import SpecFiles

    hist = load_yaml(repo / "history/polymarket/perp.yaml")["entries"]
    (repo / "history/polymarket/perp.yaml").unlink()
    files = SpecFiles("polymarket", "perp", repo)
    for e in hist:
        leaf = dict(e["leaf"])
        leaf["as_of"] = dt.date(2026, 11, 19)
        files._set(e["path"], __import__("watch.update", fromlist=["_flow"])._flow(leaf))
    for tier in ("0", "1", "2", "5", "6"):
        for side in ("taker", "maker"):
            node = files.doc["fees"]["tiers"][tier][side]
            if node.get("effective_from") is not None:
                node["effective_from"] = None
    files.doc["version_of_rules"] = dt.date(2026, 11, 19)
    files.save()


def test_replay_polymarket_fee_notice_nov_20(repo: Path) -> None:
    """M3 replay 3, value path only: the notice page has no parser (its layout has not been
    checked), so this applies the notice's values, as read on 2026-11-24, to the spec as it stood
    before the notice and checks the result is Upcoming entries plus the history now on file."""
    _pre_notice_spec(repo)
    url = "https://docs.polymarket.com/perps/fee-and-liquidity-reward-changes-november-2026.md"
    current = load_yaml(ROOT / "specs/polymarket/perp.yaml")
    props = []
    for tier, row in current["fees"]["tiers"].items():
        for side in ("taker", "maker"):
            leaf = row[side]
            if leaf.get("effective_from") == "2026-11-25":
                props.append(
                    Proposal(
                        "polymarket",
                        "perp",
                        f"fees.tiers.{tier}.{side}",
                        url,
                        value=leaf["value"],
                        effective_from="2026-11-25",
                    )
                )
    props.append(
        Proposal("polymarket", "perp", "fees.liquidation_fee", url, value=Decimal("0.01"), effective_from="2026-11-25")
    )
    changes, _ = apply_all(props, "2026-11-20", repo)

    assert {c.kind for c in changes} == {"Upcoming"} and len(changes) == 8
    got = load_yaml(repo / "history/polymarket/perp.yaml")["entries"]
    want = load_yaml(ROOT / "history/polymarket/perp.yaml")["entries"]
    assert sorted((e["path"], e["valid_to"], e["leaf"]["value"]) for e in got) == sorted(
        (e["path"], e["valid_to"], e["leaf"]["value"]) for e in want
    )
    spec = load_yaml(repo / "specs/polymarket/perp.yaml")
    for tier, row in current["fees"]["tiers"].items():
        for side in ("taker", "maker"):
            assert spec["fees"]["tiers"][tier][side]["value"] == row[side]["value"]
    assert spec["fees"]["liquidation_fee"]["value"] == Decimal("0.01")
    assert spec["version_of_rules"] == "2026-11-25"
    assert validate_all(repo) == []
    text = changelog.render(changes)
    assert text.startswith(
        "### Polymarket — perp\n- Upcoming: fees.liquidation_fee 0.005 -> 0.01 (takes effect 2026-11-25)"
    )


def test_added_fills_an_unverified_entry(repo: Path) -> None:
    p = Proposal("kalshi", "binary", "size.minimum_order", "https://docs.kalshi.com/x", value=Decimal("0.01"))
    changes, _ = apply_all([p], "2026-12-01", repo)
    assert [c.kind for c in changes] == ["Added"]
    assert _get(load_yaml(repo / "specs/kalshi/binary.yaml"), "size.minimum_order")["value"] == Decimal("0.01")
    assert not (repo / "history/kalshi/binary.yaml").read_text().count("minimum_order")
    assert validate_all(repo) == []


def test_revising_an_upcoming_value_keeps_no_history(repo: Path) -> None:
    url = "https://docs.polymarket.com/perps/fee-and-liquidity-reward-changes-november-2026.md"
    p = Proposal("polymarket", "perp", "fees.liquidation_fee", url, value=Decimal("0.008"), effective_from="2026-11-25")
    before = (repo / "history/polymarket/perp.yaml").read_text()
    changes, _ = apply_all([p], "2026-11-24", repo)
    assert [c.kind for c in changes] == ["Upcoming"] and "announcement revised" in changes[0].summary
    assert (repo / "history/polymarket/perp.yaml").read_text() == before


def test_changelog_merges_same_day(tmp_path: Path) -> None:
    from watch.model import Change

    log = tmp_path / "CHANGELOG.md"
    a = Change("Changed", "hyperliquid", "perp", "x 1 -> 2", "https://a", "specs/hyperliquid/perp.yaml", "fees")
    b = Change("Docs-only", "kalshi", "binary", "page changed", "https://b")
    changelog.write([a], "2026-12-01", log)
    changelog.write([b], "2026-12-01", log)
    changelog.write([a], "2026-12-02", log)
    text = log.read_text()
    assert text.count("## 2026-12-01") == 1 and text.index("## 2026-12-02") < text.index("## 2026-12-01")
    assert "### Kalshi — binary" in text
