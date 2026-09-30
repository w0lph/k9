import json

import pytest

from cgq import merge, validate
from cgq.common import norm_text, strip_markup

REC = {
    "key": "MED:1", "id": "1", "source": "MED", "pmid": "1", "pmcid": "PMC1", "doi": "10.1/x",
    "title": "Weekly rapamycin in companion dogs",
    "abstract": "We enrolled 580 dogs. Median lifespan was 12.5 years — in “large” dogs.",
    "year": 2026, "tiers": ["core"],
}


@pytest.fixture()
def corpus(tmp_path, monkeypatch):
    (tmp_path / "records.jsonl").write_text(json.dumps(REC) + "\n", encoding="utf-8")
    md = tmp_path / "fulltext" / "md"
    md.mkdir(parents=True)
    (md / "PMC1.md").write_text("---\npmcid: \"PMC1\"\n---\n\n## Methods\n\nDogs received 0.15 mg/kg once weekly.\n", encoding="utf-8")
    validate.load_records.cache_clear()
    return tmp_path


def _q(**over):
    base = {
        "question": "How many dogs were enrolled?",
        "answer": "580",
        "answer_type": "numeric",
        "category": "interventions",
        "difficulty": 1,
        "evidence": [{"key": "MED:1", "location": "abstract", "quote": "We enrolled 580 dogs."}],
    }
    return base | over


def test_norm_text_folds_typography():
    assert norm_text("12.5 years — in “large”  dogs") == '12.5 years - in "large" dogs'


def test_norm_text_ignores_inline_markup_both_ways():
    src = "LE<sub>birth</sub> was 12.69 years in <i>Canis familiaris</i> (R^2^ ~ATAC~ = 26%)."
    clean = "LEbirth was 12.69 years in Canis familiaris (R2 ATAC = 26%)."
    assert norm_text(src) == norm_text(clean)
    assert strip_markup(src) == clean


def test_merge_publishes_clean_quotes_that_still_validate(tmp_path, corpus):
    q = _q(evidence=[{"key": "MED:1", "location": "abstract", "quote": "Median lifespan was <i>12.5</i> years"}])
    assert validate.validate_rows([q], corpus).ok
    p = tmp_path / "d.jsonl"
    p.write_text(json.dumps(q) + "\n", encoding="utf-8")
    rows, _ = merge.merge_files([p], "t", "2026-09-28")
    assert rows[0]["evidence"][0]["quote"] == "Median lifespan was 12.5 years"
    assert validate.validate_rows(rows, corpus, require_ids=True).ok


def test_valid_question_passes(corpus):
    rep = validate.validate_rows([_q()], corpus)
    assert rep.ok and rep.n == 1 and rep.by_location["abstract"] == 1


def test_quote_must_be_verbatim(corpus):
    bad = _q(evidence=[{"key": "MED:1", "location": "abstract", "quote": "We enrolled 581 dogs today."}])
    rep = validate.validate_rows([bad], corpus)
    assert any("not found verbatim" in e for e in rep.errors)


def test_typographic_quote_variants_still_match(corpus):
    q = _q(evidence=[{"key": "MED:1", "location": "abstract", "quote": 'Median lifespan was 12.5 years - in "large" dogs.'}])
    assert validate.validate_rows([q], corpus).ok


def test_fulltext_location_and_missing_file(corpus):
    ok = _q(evidence=[{"key": "MED:1", "location": "fulltext", "quote": "Dogs received 0.15 mg/kg once weekly."}])
    assert validate.validate_rows([ok], corpus).ok
    (corpus / "fulltext" / "md" / "PMC1.md").unlink()
    rep = validate.validate_rows([ok], corpus)
    assert any("no Markdown full text" in e for e in rep.errors)


def test_schema_and_duplicate_checks(corpus):
    rows = [
        _q(),
        _q(question="How many dogs were enrolled?"),  # exact duplicate
        _q(answer_type="prose"),
        _q(category="nope"),
        _q(difficulty=5),
        _q(question="Missing question mark"),
        _q(evidence=[{"key": "MED:999", "location": "abstract", "quote": "We enrolled 580 dogs."}]),
        _q(evidence=[{"key": "MED:1", "pmid": "2", "location": "abstract", "quote": "We enrolled 580 dogs."}]),
    ]
    rep = validate.validate_rows(rows, corpus)
    msgs = "\n".join(rep.errors)
    for needle in ("duplicate of #1", "answer_type 'prose'", "category 'nope'", "difficulty must be", "end with '?'", "unknown corpus key", "pmid '2' does not match"):
        assert needle in msgs, needle


def test_merge_numbers_sorts_and_drops_near_duplicates(tmp_path, corpus):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    a.write_text(json.dumps(_q(category="cognition")) + "\n" + json.dumps(_q(question="What was the median lifespan?", answer="12.5 years", category="lifespan_epidemiology")) + "\n", encoding="utf-8")
    b.write_text(json.dumps(_q(question="How many dogs were enrolled in total?")) + "\n", encoding="utf-8")
    rows, dropped = merge.merge_files([a, b], "tester", "2026-09-28")
    assert [r["id"] for r in rows] == ["cgq-0001", "cgq-0002"]
    assert [r["category"] for r in rows] == ["lifespan_epidemiology", "cognition"]  # CATEGORIES order
    assert len(dropped) == 1 and "near-duplicate" in dropped[0]
    assert rows[0]["created"] == {"by": "tester", "date": "2026-09-28"} and rows[0]["status"] == "draft"
    assert list(rows[0])[:4] == ["id", "category", "difficulty", "answer_type"]
    rep = validate.validate_rows(rows, corpus, require_ids=True)
    assert rep.ok
