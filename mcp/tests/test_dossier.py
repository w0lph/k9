import httpx

from dog_geroscience_mcp import dossier, live


def test_parse_dose_and_species():
    assert dossier.parse_mg_per_kg("2 mg/kg") == 2.0
    assert dossier.parse_mg_per_kg("500 mcg/kg daily") == 0.5
    assert dossier.parse_mg_per_kg("1 g/kg") == 1000.0
    assert dossier.parse_mg_per_kg("14 ppm") is None and dossier.parse_mg_per_kg(None) is None
    assert dossier.km_species("Mus musculus") == "mouse" and dossier.km_species("Canis lupus familiaris") == "dog"
    assert dossier.km_species("Drosophila melanogaster") is None


def _openfda(total: int):
    def handler(req: httpx.Request) -> httpx.Response:
        if total == 0:
            return httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})
        if "count" in req.url.params:
            return httpx.Response(200, json={"results": [{"term": "Vomiting", "count": 3}, {"term": "Lethargy", "count": 2}]})
        return httpx.Response(200, json={"meta": {"results": {"total": total}}, "results": [{}]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openfda_dog_events_shapes_and_404(monkeypatch):
    out = live.openfda_dog_events("selegiline", client=_openfda(5))
    assert out["total"] == 5 and out["top_reactions"][0] == {"term": "Vomiting", "count": 3}
    none = live.openfda_dog_events("nothing", client=_openfda(0))
    assert none["total"] == 0 and none["top_reactions"] == [] and "error" not in none


def test_dossier_rapamycin_fixture(conn, db_path, monkeypatch):
    monkeypatch.setattr(live, "dog_ortholog", lambda gene, sp="human", cache_db=None, client=None: {"orthologs": [{"dog_symbol": gene.upper()}], "n_orthologs": 1})
    d = dossier.build_dossier(conn, "rapamycin", target_gene="MTOR", cache_db=db_path, openfda_client=_openfda(0))
    assert d["drugage"]["n_experiments"] == 3 and d["drugage"]["by_species"] == {"Mus musculus": 2, "Rattus norvegicus": 1}
    assert len(d["drugage"]["itp_rows"]) == 2 and d["drugage"]["dog_rows"] == []
    tr = d["dog_equivalent_doses"]["rows"]
    assert len(tr) == 1 and tr[0]["species"] == "Rattus norvegicus" and tr[0]["dog_equivalent_mg_per_kg"] == 0.6  # 2 × 6/20
    assert d["corpus"]["records_mentioning_compound"] == 1
    assert d["corpus"]["top_core_hits"][0]["key"] == "MED:38263575"
    assert d["corpus"]["dog_trials"] and d["corpus"]["dog_trials"][0]["key"] == "MED:38263575"
    assert d["target"]["genage"]["human"][0]["symbol"] == "MTOR" and d["target"]["dog_ortholog"]["n_orthologs"] == 1
    assert d["openfda_dog_adverse_events"]["total"] == 0
    assert d["foi_summaries_dog"] is None  # fixture DB has no FOI table
    gaps = " ".join(d["gaps"])
    assert "no dog lifespan experiment" in gaps and "not a marketed veterinary product" in gaps
    assert "No NIA" not in gaps  # ITP rows exist


def test_aliases_and_synonym_lookup(conn):
    names = [n.lower() for n in dossier.aliases_for("Selegiline")]
    assert "l-deprenyl" in names and "anipryl" in names
    assert "17-α-estradiol" in dossier.aliases_for("17-alpha-estradiol")
    d = dossier.build_dossier(conn, "selegiline", include_openfda=False)
    assert d["drugage"]["n_experiments"] == 1 and d["drugage"]["dog_rows"][0]["compound_name"] == "L-deprenyl"
    assert "L-deprenyl" in d["names_searched"]
    d2 = dossier.build_dossier(conn, "sirolimus", include_openfda=False)  # -> rapamycin rows
    assert d2["drugage"]["n_experiments"] == 3 and d2["corpus"]["records_mentioning_compound"] == 1


def test_dossier_unknown_compound_lists_all_gaps(conn):
    d = dossier.build_dossier(conn, "unobtainium", include_openfda=False)
    assert d["drugage"]["n_experiments"] == 0 and d["corpus"]["records_mentioning_compound"] == 0
    assert any("any species" in g for g in d["gaps"]) and any("No record in the canine aging corpus" in g for g in d["gaps"])
    assert d["openfda_dog_adverse_events"] is None
