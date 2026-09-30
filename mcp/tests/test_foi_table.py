import json

from dog_geroscience_mcp import dossier, queries
from dog_geroscience_mcp.build import build_db

FOI_ROW = {
    "foi_id": 555, "application_number": "141-999", "approval_type": "Original approval", "approval_date": "January 01, 2020",
    "sponsor": "Example Animal Health", "ingredients": "Dogazine hydrochloride", "proprietary_name": "Dogalong",
    "catalogue_summary": "Original approval for age-related slowing in dogs.", "pdf_url": "https://example/foi/555",
    "species_flag": "dog",
    "text": {"pages": 12, "chars": 30000, "likely_scanned": False},
    "parsed": {
        "sections_found": ["general_information", "effectiveness", "target_animal_safety"],
        "general_information": {"established_name": "Dogazine hydrochloride", "recommended_dosage": "0.5 mg/kg once daily",
                                "indications": "For the control of age-related slowing in dogs.", "route_of_administration": "Oral",
                                "dosage_form": "Tablet", "species_class": "Dogs"},
        "pk_sentences": ["The terminal half-life was 12.4 hours."],
        "safety_sentences": ["No adverse effects were observed at 1X."],
        "dose_mentions": ["0.5 mg/kg once daily"],
    },
}


def test_foi_table_and_search(raw_dir, corpus_dir, tmp_path):
    foi = tmp_path / "foi_summaries_dog.jsonl"
    cat_row = FOI_ROW | {"foi_id": 556, "species_flag": "other", "proprietary_name": "Catalong",
                         "parsed": FOI_ROW["parsed"] | {"general_information": {"species_class": "Cats"}}}
    foi.write_text(json.dumps(FOI_ROW) + "\n" + json.dumps(cat_row) + "\n", encoding="utf-8")
    db = tmp_path / "db.sqlite"
    summary = build_db(raw_dir, corpus_dir, db, foi_path=foi)
    assert summary["foi"]["records"] == 2
    conn = queries.connect(db)
    assert queries.has_table(conn, "foi_dog")
    hits = queries.foi_search(conn, "dogazine")
    assert [h["species_flag"] for h in hits] == ["dog", "other"]  # dog summaries rank first
    assert hits[0]["application_number"] == "141-999" and hits[0]["recommended_dosage"] == "0.5 mg/kg once daily"
    assert hits[0]["pk_sentences"] == ["The terminal half-life was 12.4 hours."] and hits[0]["likely_scanned"] is False
    assert queries.foi_search(conn, "age-related slowing")[0]["foi_id"] == 555  # indication substring
    assert queries.foi_search(conn, "nothing") == []
    # the dossier picks the table up and stops listing the FOI gap
    d = dossier.build_dossier(conn, "Dogazine", include_openfda=False)
    assert [f["proprietary_name"] for f in d["foi_summaries_dog"]] == ["Dogalong"]  # cat summary excluded
    assert not any("FOI summary" in g for g in d["gaps"])
    conn.close()


STRUCTURED_ROW = {
    "foi_id": 555, "application_number": "141-999", "product_name": "Dogalong", "ingredient": "Dogazine hydrochloride",
    "species_class": "Dogs", "extracted_by": "test",
    "indication": {"text": "control of age-related slowing", "quote": "For the control of age-related slowing in dogs."},
    "dose_regimen": {"dose": "0.5 mg/kg", "route": "oral", "frequency": "once daily", "duration_or_conditions": None, "quote": "0.5 mg/kg once daily"},
    "pharmacokinetics": [{"parameter": "half-life", "value": "12.4 hours", "conditions": "oral", "quote": "The terminal half-life was 12.4 hours."}],
    "target_animal_safety": {"dose_multiples": ["1X", "3X", "5X"], "duration": "6 months", "n_animals": "32",
                             "findings": [{"finding": "vomiting at 5X", "quote": "Vomiting occurred at 5X."}], "design_quote": "32 dogs received 1X, 3X and 5X for 6 months."},
    "effectiveness": {"design": "masked RCT", "n_dogs": "240", "primary_endpoint": "owner score", "result": "improved", "quote": "240 dogs"},
    "adverse_reactions": [{"term": "Vomiting", "treated": "12.3%", "control": "4.1%", "quote": "12.3% vs 4.1%"}],
    "notes": None,
}


def test_foi_structured_table_search_and_dossier(raw_dir, corpus_dir, tmp_path):
    foi = tmp_path / "foi_summaries_dog.jsonl"
    foi.write_text(json.dumps(FOI_ROW) + "\n", encoding="utf-8")
    fs = tmp_path / "structured_dog.jsonl"
    cat_structured = STRUCTURED_ROW | {"foi_id": 556, "species_class": "Cats (feline supplement)", "product_name": "Catalong"}
    fs.write_text(json.dumps(STRUCTURED_ROW) + "\n" + json.dumps(cat_structured) + "\n", encoding="utf-8")
    db = tmp_path / "db3.sqlite"
    summary = build_db(raw_dir, corpus_dir, db, foi_path=foi, foi_structured_path=fs)
    assert summary["foi_structured"]["records"] == 2
    conn = queries.connect(db)
    hits = queries.foi_structured_search(conn, "dogazine")
    assert hits[0]["dose_regimen"] == {"dose": "0.5 mg/kg", "route": "oral", "frequency": "once daily", "duration_or_conditions": None, "quote": "0.5 mg/kg once daily"}
    assert hits[0]["pharmacokinetics"][0]["value"] == "12.4 hours"
    assert hits[0]["target_animal_safety"]["dose_multiples"] == ["1X", "3X", "5X"]
    assert hits[0]["adverse_reactions"][0]["treated"] == "12.3%"
    assert "dose" not in hits[0]  # flattened columns folded back into dose_regimen
    d = dossier.build_dossier(conn, "Dogazine", include_openfda=False)
    assert [f["foi_id"] for f in d["foi_structured"]] == [555]  # the feline record is excluded
    assert d["foi_summaries_dog"][0]["foi_id"] == 555
    assert dossier._non_dog("Cats (feline) for this supplement; product also labeled for dogs") is False
    assert dossier._non_dog("Cats") is True and dossier._non_dog(None) is False
    conn.close()


def test_build_without_foi_dataset_is_fine(raw_dir, corpus_dir, tmp_path):
    db = tmp_path / "db2.sqlite"
    summary = build_db(raw_dir, corpus_dir, db, foi_path=tmp_path / "missing.jsonl")
    assert summary["foi"] == {}
    conn = queries.connect(db)
    assert not queries.has_table(conn, "foi_dog") and queries.foi_search(conn, "x") == []
    conn.close()
