import json
from pathlib import Path

from canine_trials.validate import SourceTexts, norm, validate_records


def _texts(tmp_path: Path) -> SourceTexts:
    web = tmp_path / "sources" / "web"
    web.mkdir(parents=True)
    (web / "press.txt").write_text("Loyal announced today that the trial\nenrolled 1,300 dogs at 70 clinics.\n", encoding="utf-8")
    return SourceTexts(db_path=tmp_path / "missing.sqlite", corpus_dir=tmp_path / "nocorpus", sources_dir=tmp_path / "sources")


def _record(**over) -> dict:
    rec = {
        "id": "demo-trial", "name": "Demo trial", "kind": "regulatory_program", "status": "ongoing",
        "population": {"n": 1300}, "summary": "A demo record.",
        "sources": [{"type": "web", "slug": "press", "quotes": ["the trial enrolled 1,300 dogs at 70 clinics."]}],
    }
    rec.update(over)
    return rec


def test_norm_collapses_whitespace_and_tags():
    assert norm("<h4>Results</h4>Median  life\nspan") == "Results Median life span"


def test_valid_record_passes(tmp_path):
    rep = validate_records([_record()], texts=_texts(tmp_path))
    assert rep.ok, rep.errors
    assert rep.quotes == 1
    assert any("company/press-sourced" in w for w in rep.warnings)


def test_quote_must_be_verbatim(tmp_path):
    rec = _record(sources=[{"type": "web", "slug": "press", "quotes": ["the trial enrolled 1300 dogs at 70 clinics."]}])
    rep = validate_records([rec], texts=_texts(tmp_path))
    assert not rep.ok and "not found verbatim" in rep.errors[0]


def test_schema_rejects_unknown_fields_and_duplicate_ids(tmp_path):
    rep = validate_records([_record(), _record(extra="x")], texts=_texts(tmp_path))
    assert any("duplicate id" in e for e in rep.errors)
    assert any("schema" in e and "extra" in e for e in rep.errors)


def test_missing_source_is_an_error(tmp_path):
    rec = _record(sources=[{"type": "pmid", "pmid": "1", "quotes": ["twenty characters at least here"]}])
    rep = validate_records([rec], texts=_texts(tmp_path))
    assert not rep.ok and "not in the corpus" in rep.errors[0]


def test_jsonl_roundtrip(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
    from canine_trials.validate import read_jsonl
    assert read_jsonl(p)[0]["id"] == "demo-trial"


def test_norm_keeps_comparison_operators():
    assert norm("greater for CF dogs (P<.05). <i>p</i> < .0001 <h4>Results</h4>") == "greater for CF dogs (P<.05). p < .0001 Results"
