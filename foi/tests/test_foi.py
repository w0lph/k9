import json
from pathlib import Path

import httpx

from foi_summaries import sections
from foi_summaries.client import ADAFDAClient
from foi_summaries.dataset import build_dataset
from foi_summaries.index import _app_number, build_index, read_jsonl

SAMPLE = """FREEDOM OF INFORMATION SUMMARY
NADA 141-999
Dogalong Tablets
(dogazine hydrochloride)
Dogs. For the control of age-related slowing.

I. GENERAL INFORMATION

File Number: NADA 141-999
Sponsor: Example Animal Health, Inc.
123 Main St
Established Name: Dogazine hydrochloride
Proprietary Name: Dogalong Tablets
Dosage Form: Tablet
Route of Administration: Oral
Species/Class: Dogs
Recommended Dosage: 0.5 mg/kg (0.23 mg/lb) body weight once daily
Indications: For the control of age-related slowing in dogs.

II. EFFECTIVENESS

A. Dosage Characterization:
The terminal half-life was 12.4 hours after oral dosing. Cmax was 1.2 µg/mL.
B. Substantial Evidence:
A masked, placebo-controlled field study enrolled 240 dogs at 12 sites.

III. TARGET ANIMAL SAFETY

Dogs received 0, 1, 3 and 5 times the recommended dose of 0.5 mg/kg for 6 months. No adverse effects were observed at 1X. Vomiting occurred at 5X the recommended dose.

IV. HUMAN FOOD SAFETY

Not applicable; this product is for dogs.

VI. AGENCY CONCLUSIONS

The data submitted in support of this NADA satisfy the requirements.
"""


def test_split_sections_and_general_information():
    secs = sections.split_sections(SAMPLE)
    assert [k for k in secs if k != "preamble"] == [
        "general_information", "effectiveness", "target_animal_safety", "human_food_safety", "agency_conclusions"
    ]
    assert secs["preamble"].startswith("FREEDOM OF INFORMATION SUMMARY")
    gi = sections.parse_general_information(secs["general_information"])
    assert gi["file_number"] == "NADA 141-999"
    assert gi["sponsor"] == "Example Animal Health, Inc. 123 Main St"  # continuation folded
    assert gi["recommended_dosage"].startswith("0.5 mg/kg")
    assert gi["species_class"] == "Dogs" and gi["route_of_administration"] == "Oral"


LETTERED = """Approval Date: June 2, 1997
FREEDOM OF INFORMATION SUMMARY
I. GENERAL INFORMATION
A. File Number
NADA 006-707
B. Sponsor
Solvay Animal Health, Inc.
Mendota Heights, MN 55120
C. Proprietary Name
Sulquin 6-50 Concentrate
D. Established Name
Sodium sulfaquinoxaline liquid
G. Recommended Dosage
Chickens & turkeys-0.04% & 0.025%
I. Indication
For control of coccidiosis in chickens and turkeys. For the control of acute fowl
cholera and fowl typhoid in chickens and turkeys.
Freedom of Information Summary
NADA 006-707
Page 2 of 4
J. Effect of Supplement
DESI finalization recognizing that the product is safe and effective.
II. EFFECTIVENESS
NADA 6-707 was originally approved on February 14, 1949.
"""


def test_lettered_general_information_layout():
    secs = sections.split_sections(LETTERED)
    assert [k for k in secs if k != "preamble"] == ["general_information", "effectiveness"]
    gi = sections.parse_general_information(secs["general_information"])
    assert gi["file_number"] == "NADA 006-707"
    assert gi["sponsor"] == "Solvay Animal Health, Inc. Mendota Heights, MN 55120"
    assert gi["established_name"] == "Sodium sulfaquinoxaline liquid"
    assert gi["indication"].startswith("For control of coccidiosis") and "Page 2 of 4" not in gi["indication"]
    assert gi["effect_of_supplement"].startswith("DESI finalization")


REORDERED = """Approval Date: February 21, 1991
FREEDOM OF INFORMATION SUMMARY
GENERAL INFORMATION I.
File Number A.
NADA 042-841
Sponsor B.
Fort Dodge Laboratories
Proprietary Name C.
Amforol® Veterinary Oral Tablets
Established Name D.
kanamycin, pectin, bismuth subcarbonate
EFFECTIVENESS II.
The drug was shown effective.
"""

ARABIC = """SUPPLEMENTAL
FREEDOM OF INFORMATION SUMMARY
1.  GENERAL INFORMATION
A.  NADA Number:     048-271
B.  Sponsor:      Boehringer Ingelheim Vetmedica, Inc.
      15th & Oak
C.  Generic Name:     Dichlorvos
D.  Trade Name:     TASK® Tabs 2
2.  EFFECTIVENESS
Not applicable.
3.  TARGET ANIMAL SAFETY:
Safe at 1X.
"""


def test_reordered_and_arabic_layouts():
    secs = sections.split_sections(REORDERED)
    assert [k for k in secs if k != "preamble"] == ["general_information", "effectiveness"]
    gi = sections.parse_general_information(secs["general_information"])
    assert gi["file_number"] == "NADA 042-841" and gi["sponsor"] == "Fort Dodge Laboratories"
    assert gi["proprietary_name"].startswith("Amforol") and gi["established_name"].startswith("kanamycin")

    secs2 = sections.split_sections(ARABIC)
    assert [k for k in secs2 if k != "preamble"] == ["general_information", "effectiveness", "target_animal_safety"]
    gi2 = sections.parse_general_information(secs2["general_information"])
    assert gi2["nada_number"] == "048-271" and gi2["generic_name"] == "Dichlorvos"
    assert gi2["sponsor"] == "Boehringer Ingelheim Vetmedica, Inc. 15th & Oak" and gi2["trade_name"] == "TASK® Tabs 2"
    assert secs2["target_animal_safety"].strip() == "Safe at 1X."


def test_species_flag_and_heading_variants():
    assert sections.species_flag({"species_class": "Dogs"}) == "dog"
    assert sections.species_flag({"species": "(es): Cats"}) == "other"
    assert sections.species_flag({}, "FREEDOM OF INFORMATION SUMMARY\nfor use in dogs") == "dog"
    assert sections.species_flag({}, "no species here") == "unknown"
    gi = sections.parse_general_information("A. Species(es): Cats\nB. Route(s) of Administration: Oral\n")
    assert gi == {"species": "Cats", "route_of_administration": "Oral"}


def test_parse_summary_candidates():
    p = sections.parse_summary(SAMPLE)
    assert p["sections_found"][0] == "general_information"
    assert any("half-life" in s for s in p["pk_sentences"]) and any("Cmax" in s for s in p["pk_sentences"])
    assert any("No adverse effects" in s for s in p["safety_sentences"])
    assert "0.5 mg/kg (0.23 mg/lb) body weight once daily" in p["dose_mentions"]
    assert p["section_chars"]["target_animal_safety"] > 50


def test_app_number_normalisation():
    assert _app_number(4536) == "004-536" and _app_number("141-999") == "141-999" and _app_number(141999) == "141-999"


class FakeADAFDA:
    def __init__(self):
        self.calls = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append((req.method, req.url.path))
        path = req.url.path
        if path.endswith("/foiDrugSummaries/foiApplicationNumbers"):
            return httpx.Response(200, json=[{"foiApplicationNumStart": "000-000", "foiApplicationNumEnd": "141-999"}])
        if "/foiDrugSummaries/foiApplicationsInfo/" in path:
            return httpx.Response(200, json=[
                {"applicationNumber": "141-999", "foiId": 1, "sponsor": "Example", "applicationType": "N", "approvalType": "Original approval",
                 "approvalDate": "January 01, 2020", "summary": "s", "fileName": "a.pdf", "ingredients": "Dogazine"},
                {"applicationNumber": "200-001", "foiId": 2, "sponsor": "Cattle Co", "applicationType": "A", "approvalType": "Original approval",
                 "approvalDate": "x", "summary": "s", "fileName": "b.pdf", "ingredients": "Bovine thing"},
            ])
        if path.endswith("/advancedSearch"):
            body = json.loads(req.content)
            assert body["speciesName"] == "Dog" and "paging" not in body  # flat body, as the app sends
            if body["pageNumber"] == 1:
                return httpx.Response(200, json={"content": [{"applicationId": 9, "applicationNumber": 141999, "activeIngredientName": "Dogazine",
                                                              "proprietaryName": "Dogalong", "applicationStatusCode": "A", "applicationType": "N", "sponsorName": "Example"}],
                                                 "last": False})
            return httpx.Response(200, json={"content": [], "last": True})
        if path.endswith("/document/downloadFoi/1"):
            return httpx.Response(200, content=b"%PDF-1.4 fake", headers={"content-type": "application/pdf"})
        return httpx.Response(404)


def test_index_joins_dog_applications(tmp_path):
    fake = FakeADAFDA()
    client = ADAFDAClient(transport=httpx.MockTransport(fake.handler), min_interval=0)
    summary = build_index(tmp_path, client=client)
    assert summary["foi_documents_all_species"] == 2 and summary["applications_dog"] == 1
    assert summary["foi_documents_dog"] == 1
    dog = read_jsonl(tmp_path / "foi_dog.jsonl")
    assert dog[0]["foiId"] == 1 and dog[0]["species"] == "Dog" and dog[0]["proprietaryName"] == "Dogalong"
    assert dog[0]["applicationNumber"] == "141-999"


def test_dataset_assembly_with_text(tmp_path):
    fake = FakeADAFDA()
    client = ADAFDAClient(transport=httpx.MockTransport(fake.handler), min_interval=0)
    build_index(tmp_path, client=client)
    (tmp_path / "text").mkdir()
    (tmp_path / "text" / "1.txt").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "text_stats.jsonl").write_text(json.dumps({"foiId": 1, "pages": 3, "chars": len(SAMPLE), "chars_per_page": 400, "likely_scanned": False}) + "\n", encoding="utf-8")
    s = build_dataset(tmp_path)
    assert s["records"] == 1 and s["with_text"] == 1 and s["with_template_sections"] == 1
    assert s["species_flag"] == {"dog": 1, "other": 0, "unknown": 0}
    rec = read_jsonl(Path(s["output"]))[0]
    assert rec["foi_id"] == 1 and rec["pdf_url"].endswith("/document/downloadFoi/1")
    assert rec["species_flag"] == "dog"
    assert rec["parsed"]["general_information"]["established_name"] == "Dogazine hydrochloride"
    assert rec["text"]["sha256"]
    s2 = build_dataset(tmp_path, include_sections=False)
    assert "sections" not in read_jsonl(Path(s2["output"]))[0]["parsed"]
