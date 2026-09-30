import json

from foi_summaries.structured import merge_structured, validate_structured

TEXT = """I. GENERAL INFORMATION
Recommended Dosage: 0.5 mg/kg (0.23 mg/lb) body weight once daily.
II. EFFECTIVENESS
The terminal half-life was 12.4 hours after oral dosing. A masked, placebo-controlled field study enrolled 240 dogs at 12 sites.
III. TARGET ANIMAL SAFETY
Thirty-two dogs (n = 32) received 0, 1, 3 and 5 times the recommended dose for 6 months. Vomiting occurred at 5X the recommended dose.
Vomiting was reported in 12.3% of treated dogs and 4.1% of control dogs.
"""


def _setup(tmp_path):
    (tmp_path / "text").mkdir()
    (tmp_path / "text" / "9.txt").write_text(TEXT, encoding="utf-8")
    (tmp_path / "foi_summaries_dog.jsonl").write_text(json.dumps({"foi_id": 9}) + "\n", encoding="utf-8")


def _rec(**over):
    base = {
        "foi_id": 9, "application_number": "141-009", "product_name": "Dogalong", "ingredient": "Dogazine",
        "species_class": "Dogs", "extracted_by": "test",
        "dose_regimen": {"dose": "0.5 mg/kg", "route": "oral", "frequency": "once daily", "duration_or_conditions": None,
                         "quote": "Recommended Dosage: 0.5 mg/kg (0.23 mg/lb) body weight once daily."},
        "pharmacokinetics": [{"parameter": "half-life", "value": "12.4 hours", "conditions": "oral", "quote": "The terminal half-life was 12.4 hours after oral dosing."}],
        "target_animal_safety": {"dose_multiples": ["1X", "3X", "5X"], "duration": "6 months", "n_animals": "32",
                                 "findings": [{"finding": "Vomiting at 5X", "quote": "Vomiting occurred at 5X the recommended dose."}],
                                 "design_quote": "Thirty-two dogs (n = 32) received 0, 1, 3 and 5 times the recommended dose for 6 months."},
        "effectiveness": {"design": "masked placebo-controlled field study", "n_dogs": "240", "primary_endpoint": None, "result": "n/a",
                          "quote": "A masked, placebo-controlled field study enrolled 240 dogs at 12 sites."},
        "adverse_reactions": [{"term": "Vomiting", "treated": "12.3%", "control": "4.1%",
                               "quote": "Vomiting was reported in 12.3% of treated dogs and 4.1% of control dogs."}],
    }
    return base | over


def test_valid_record_passes(tmp_path):
    _setup(tmp_path)
    rep = validate_structured([_rec()], tmp_path)
    assert rep.ok, rep.errors
    assert rep.quotes_checked == 6


def test_numbers_must_come_from_quote_and_quote_must_be_verbatim(tmp_path):
    _setup(tmp_path)
    bad_num = _rec(pharmacokinetics=[{"parameter": "half-life", "value": "14.4 hours", "conditions": None, "quote": "The terminal half-life was 12.4 hours after oral dosing."}])
    bad_quote = _rec(effectiveness={"design": "x", "n_dogs": "240", "result": "y", "quote": "A masked study enrolled 240 dogs."})
    unknown = _rec(foi_id=10)
    rep = validate_structured([bad_num, bad_quote, unknown], tmp_path)
    msgs = "\n".join(rep.errors)
    assert "number 14.4 not in quote" in msgs and "quote not found verbatim" in msgs and "foi_id unknown" in msgs
    # a count that is not in the design quote is flagged
    words = _rec()
    words["target_animal_safety"]["n_animals"] = "31"
    rep2 = validate_structured([words], tmp_path)
    assert any("design.n_animals: number 31" in e for e in rep2.errors)


def test_merge_dedups_and_sorts(tmp_path):
    _setup(tmp_path)
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    a.write_text(json.dumps(_rec()) + "\n", encoding="utf-8")
    b.write_text(json.dumps(_rec()) + "\n" + json.dumps(_rec(foi_id=9, ingredient="Aaa")) + "\n", encoding="utf-8")
    n, dropped = merge_structured([b, a], tmp_path / "out.jsonl")
    assert n == 1 and len(dropped) == 2
