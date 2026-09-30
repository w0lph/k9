import json
from pathlib import Path

from canine_aging_corpus.records import merge, normalise, read_jsonl, write_jsonl

FIX = Path(__file__).parent / "fixtures" / "search_page.json"


def _results():
    return json.loads(FIX.read_text(encoding="utf-8"))["resultList"]["result"]


def test_normalise_journal_article():
    rec = normalise(_results()[0], "core", "2026-09-28T00:00:00+00:00", "raw/p.json")
    assert rec["key"] == "MED:38263575"
    assert rec["pmcid"] == "PMC0000001"
    assert rec["journal"] == "GeroScience"
    assert rec["year"] == 2026
    assert rec["authors"] == ["Doe J", "Roe R"]
    assert rec["is_open_access"] is True
    assert rec["mesh"][1] == {"descriptor": "Dogs", "major": True, "qualifiers": ["physiology"]}
    assert rec["keywords"] == ["Aging", "Rapamycin"]
    assert rec["grants"][0]["grant_id"] == "R01AG090843"
    assert rec["fulltext_urls"][0]["availability"] == "OA"
    assert rec["tiers"] == ["core"]


def test_normalise_preprint_without_journal():
    rec = normalise(_results()[1], "extended", "t", "p")
    assert rec["key"] == "PPR:PPR900001"
    assert rec["pmid"] is None and rec["pmcid"] is None
    assert rec["journal"] is None
    assert rec["is_open_access"] is False
    assert rec["mesh"] == [] and rec["grants"] == []


def test_merge_unions_tiers_and_keeps_newest():
    a = normalise(_results()[0], "core", "t1", "p1")
    b = normalise(_results()[0], "extended", "t2", "p2")
    b["cited_by_count"] = 5
    m = merge(a, b)
    assert m["tiers"] == ["core", "extended"]
    assert m["cited_by_count"] == 5
    assert m["retrieved_at"] == "t2"


def test_jsonl_roundtrip(tmp_path):
    p = tmp_path / "r.jsonl"
    recs = [normalise(r, "core", "t", "p") for r in _results()]
    assert write_jsonl(p, recs) == 2
    assert read_jsonl(p) == recs
    assert read_jsonl(tmp_path / "missing.jsonl") == []
