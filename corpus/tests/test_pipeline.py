"""End-to-end test with a mocked Europe PMC (httpx.MockTransport)."""

import json
from pathlib import Path

import httpx
import pytest

from canine_aging_corpus.config import QUERIES, DataPaths
from canine_aging_corpus.europepmc import EuropePMCClient, TransientHTTPError
from canine_aging_corpus.pipeline import (
    build_manifest,
    convert_fulltext,
    fetch_fulltext,
    fetch_metadata,
    rebuild_records,
)
from canine_aging_corpus.records import read_jsonl

FIX = Path(__file__).parent / "fixtures"


class FakeEuropePMC:
    """Two-page search for every query; one PMCID has full text; counts 503s served."""

    def __init__(self, flaky: int = 0):
        self.flaky = flaky
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.flaky > 0:
            self.flaky -= 1
            return httpx.Response(503, text="<html>503</html>")
        if request.url.path.endswith("/search"):
            cursor = request.url.params.get("cursorMark")
            page = json.loads((FIX / "search_page.json").read_text(encoding="utf-8"))
            if cursor == "*":
                page["nextCursorMark"] = "CURSOR2"
            else:
                page["resultList"]["result"] = [page["resultList"]["result"][0] | {"id": "38263576", "pmid": "38263576", "pmcid": "PMC0000002", "citedByCount": 1}]
                page["nextCursorMark"] = "CURSOR2"  # same cursor => stop
            return httpx.Response(200, json=page)
        if request.url.path.endswith("/PMC0000001/fullTextXML"):
            return httpx.Response(200, content=(FIX / "sample_jats.xml").read_bytes())
        if request.url.path.endswith("/fullTextXML"):
            return httpx.Response(404, text="not found")
        return httpx.Response(400, text="unexpected")


def _client_factory(fake: FakeEuropePMC):
    def make(**kw):
        return EuropePMCClient(transport=httpx.MockTransport(fake.handler), min_interval=0, max_attempts=4, **kw)
    return make


def test_pagination_dedup_tiers_and_retry(tmp_path):
    fake = FakeEuropePMC(flaky=2)  # first two calls 503 -> retried
    paths = DataPaths(root=tmp_path)
    with _client_factory(fake)() as client:
        stats = fetch_metadata(paths, page_size=2, client=client)
    assert [s.tier for s in stats] == list(QUERIES)
    assert all(s.pages == 2 for s in stats)
    recs = read_jsonl(paths.records)
    keys = sorted(r["key"] for r in recs)
    assert keys == ["MED:38263575", "MED:38263576", "PPR:PPR900001"]
    by_key = {r["key"]: r for r in recs}
    assert by_key["MED:38263575"]["tiers"] == ["core", "extended"]
    raw_pages = list(paths.raw_search.rglob("page_*.json"))
    assert len(raw_pages) == 4  # 2 tiers x 2 pages
    assert all((p.parent / "query.txt").exists() for p in raw_pages)


def test_fulltext_convert_manifest(tmp_path):
    fake = FakeEuropePMC()
    paths = DataPaths(root=tmp_path)
    with _client_factory(fake)() as client:
        fetch_metadata(paths, page_size=2, client=client)

    ft = fetch_fulltext(paths, workers=2, client_factory=_client_factory(fake))
    assert ft["candidates"] == 2 and ft["saved"] == 1 and ft["not_available"] == 1
    assert ft["aborted"] is False and ft["remaining"] == 0
    assert (paths.fulltext_xml / "PMC0000001.xml").exists()
    # idempotent: second run attempts nothing
    ft2 = fetch_fulltext(paths, workers=2, client_factory=_client_factory(fake))
    assert ft2["attempted"] == 1 and ft2["saved"] == 0  # only the 404 one is retried

    cv = convert_fulltext(paths)
    assert cv == {"xml_files": 1, "converted": 1, "skipped": 0, "failed": 0}
    md = (paths.fulltext_md / "PMC0000001.md").read_text(encoding="utf-8")
    assert md.startswith("---\npmcid: \"PMC0000001\"")
    assert "tiers: [core, extended]" in md
    assert "## Introduction" in md

    summary = build_manifest(paths)
    c = summary["counts"]
    assert c["records"] == 3
    assert c["by_tier"] == {"core": 3, "extended": 3}
    assert c["with_pmcid"] == 2
    assert c["fulltext_xml"] == 1 and c["fulltext_md"] == 1
    assert c["fulltext_md_chars_total"] > 500 and c["fulltext_md_over_3k_chars"] == 0
    import pandas as pd

    mdf = pd.read_parquet(paths.manifest_parquet).set_index("key")
    assert mdf.loc["MED:38263575", "fulltext_md_chars"] > 500
    assert mdf.loc["PPR:PPR900001", "fulltext_md_chars"] == 0
    assert c["by_source"] == {"MED": 2, "PPR": 1}
    assert paths.manifest_parquet.exists() and paths.manifest_csv.exists()
    assert summary["records_sha256"]


def test_fulltext_circuit_breaker_aborts_when_service_is_down(tmp_path):
    """Search works, /fullTextXML 500s for everything: abort early, keep nothing on disk."""
    fake = FakeEuropePMC()
    paths = DataPaths(root=tmp_path)
    with _client_factory(fake)() as client:
        fetch_metadata(paths, page_size=2, client=client)
    # Inflate the candidate list so the breaker has room to trip.
    recs = read_jsonl(paths.records)
    extra = [recs[0] | {"key": f"MED:x{i}", "id": f"x{i}", "pmcid": f"PMC9{i:06d}"} for i in range(40)]
    from canine_aging_corpus.records import write_jsonl

    write_jsonl(paths.records, recs + extra)

    def down_handler(request: httpx.Request) -> httpx.Response:
        fake.calls += 1
        return httpx.Response(500, text="boom")

    def factory():
        return EuropePMCClient(transport=httpx.MockTransport(down_handler), min_interval=0, max_attempts=2)

    ft = fetch_fulltext(paths, workers=3, client_factory=factory, breaker_threshold=6)
    assert ft["aborted"] is True
    assert ft["saved"] == 0
    assert 6 <= ft["errors"] < ft["to_fetch"]  # stopped well before trying all 42
    assert ft["remaining"] == ft["to_fetch"]
    assert not list(paths.fulltext_xml.glob("*.xml"))


def test_transient_error_gives_up_after_max_attempts(tmp_path):
    fake = FakeEuropePMC(flaky=100)
    client = EuropePMCClient(transport=httpx.MockTransport(fake.handler), min_interval=0, max_attempts=3)
    with pytest.raises(Exception) as ei:
        client.search_page(QUERIES["core"])
    assert "503" in str(ei.value)
    assert fake.calls == 3


def test_interrupted_run_keeps_completed_tier_and_rebuild_matches(tmp_path):
    """Outage after the core tier: core records must be on disk; rebuild reproduces them."""
    fake = FakeEuropePMC()
    paths = DataPaths(root=tmp_path)
    calls_before_outage = 2  # the two core pages succeed, then everything 503s

    real_handler = fake.handler

    def handler(request: httpx.Request) -> httpx.Response:
        if fake.calls >= calls_before_outage:
            fake.calls += 1
            return httpx.Response(503, text="down")
        return real_handler(request)

    client = EuropePMCClient(transport=httpx.MockTransport(handler), min_interval=0, max_attempts=2)
    with pytest.raises(TransientHTTPError):
        fetch_metadata(paths, page_size=2, client=client)

    recs = read_jsonl(paths.records)
    assert sorted(r["key"] for r in recs) == ["MED:38263575", "MED:38263576", "PPR:PPR900001"]
    assert all(r["tiers"] == ["core"] for r in recs)
    assert (paths.raw_search / "extended").exists()  # run dir + query.txt written, no pages
    assert not list((paths.raw_search / "extended").rglob("page_*.json"))

    # Rebuild from raw pages gives the same records (modulo retrieval timestamp source).
    paths.records.unlink()
    info = rebuild_records(paths)
    assert info["pages"] == 2 and info["records"] == 3
    assert info["by_tier"] == {"core": 3, "extended": 0}
    rebuilt = {r["key"]: r for r in read_jsonl(paths.records)}
    for r in recs:
        assert rebuilt[r["key"]]["title"] == r["title"]
        assert rebuilt[r["key"]]["tiers"] == ["core"]
        assert rebuilt[r["key"]]["raw_page"] == r["raw_page"]

    # A later successful run of the extended tier merges in and unions tiers.
    fake2 = FakeEuropePMC()
    with _client_factory(fake2)() as client2:
        stats = fetch_metadata(paths, tiers=["extended"], page_size=2, client=client2)
    assert [s.tier for s in stats] == ["extended"]
    merged = {r["key"]: r for r in read_jsonl(paths.records)}
    assert merged["MED:38263575"]["tiers"] == ["core", "extended"]
    assert rebuild_records(paths)["by_tier"] == {"core": 3, "extended": 3}
