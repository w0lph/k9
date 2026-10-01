import json

from dog_geroscience_mcp import queries
from dog_geroscience_mcp.build import build_db

RECORD = {
    "id": "demo-rapamycin-rct", "name": "Demo rapamycin trial", "acronym": "DEMO", "kind": "randomized_controlled_trial",
    "status": "completed", "setting": "client_owned", "intervention": "rapamycin", "intervention_class": "drug",
    "comparator": "placebo", "dose_regimen": None, "duration": "10 weeks",
    "population": {"n": 24, "n_note": None, "breed": None, "age": "middle-aged", "other": None},
    "primary_outcome": "echocardiographic measures", "result": "no clinical side effects", "lead_organization": None,
    "sponsor_or_funder": None, "registration": [], "start_year": 2017, "end_year": 2017,
    "sources": [{"type": "pmid", "pmid": "28374166", "slug": None, "doi": None, "title": "t", "year": 2017, "role": "results",
                 "quotes": ["Our results showed no clinical side effects"], "quote_scope": "abstract"}],
    "summary": "A demo record.", "notes": None, "parent_id": None, "tags": ["rapamycin", "cardiac"], "extracted_by": "test",
}


def test_trials_table_and_search(raw_dir, corpus_dir, tmp_path):
    trials = tmp_path / "canine_trials.jsonl"
    trials.write_text(json.dumps(RECORD) + "\n", encoding="utf-8")
    db = tmp_path / "db.sqlite"
    summary = build_db(raw_dir, corpus_dir, db, trials_path=trials)
    assert summary["trials"]["records"] == 1
    conn = queries.connect(db)
    hits = queries.trial_search(conn, "rapamycin")
    assert [h["id"] for h in hits] == ["demo-rapamycin-rct"]
    assert hits[0]["sources"][0]["quotes"][0].startswith("Our results")
    assert queries.trial_search(conn, "28374166")[0]["acronym"] == "DEMO"
    assert queries.trial_search(conn, "rapamycin", status="ongoing") == []
    assert queries.trial_search(conn, trial_id="demo-rapamycin-rct")[0]["population"]["n"] == 24
    assert queries.trial_stats(conn)["kind"] == {"randomized_controlled_trial": 1}


def test_no_trials_file_is_fine(raw_dir, corpus_dir, tmp_path):
    db = tmp_path / "db.sqlite"
    summary = build_db(raw_dir, corpus_dir, db, trials_path=tmp_path / "missing.jsonl")
    assert summary["trials"] == {}
    assert queries.trial_search(queries.connect(db), "anything") == []
