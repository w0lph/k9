from dog_geroscience_mcp import dose, queries


def test_build_summary_and_meta(conn, db_path):
    info = queries.build_info(conn)
    assert info["hagr"] == {"anage": 5, "drugage": 5, "genage_human": 3, "genage_models": 2}
    assert info["dap_codebooks"] == {"2025_v1.0": 4, "2024_v1.1": 1}
    assert info["corpus"]["records"] == 3 and info["corpus"]["with_fulltext_md"] == 1
    assert info["corpus"]["corpus_version"] == "2026.09.28"
    assert info["downloads"]["anage"]["url"] == "fixture"
    assert not db_path.with_suffix(".building.sqlite").exists()


def test_anage_dog_default_aliases_and_ranking(conn):
    dog = queries.anage_species(conn)
    assert dog[0]["scientific_name"] == "Canis familiaris"
    assert dog[0]["maximum_longevity_yrs"] == "27" and dog[0]["imr_per_yr"] == "0.02"
    assert "female_maturity_days" not in dog[0]  # empty cells dropped
    # DrugAge-style name and plain "dog" resolve to the same single AnAge row.
    for alias in ("Canis lupus familiaris", "dog", "Domestic Dog"):
        rows = queries.anage_species(conn, alias)
        assert rows[0]["scientific_name"] == "Canis familiaris", alias
    assert len(queries.anage_species(conn, "dog")) == 1  # alias, not a '%dog%' scan (Bush dog excluded)
    assert queries.anage_species(conn, "wolf")[0]["common_name"] == "Gray wolf"
    # Genus scan still works and ranks the exact match first.
    canis = queries.anage_species(conn, "Canis")
    assert {r["scientific_name"] for r in canis} == {"Canis familiaris", "Canis lupus"}
    human = queries.anage_species(conn, "Homo sapiens")
    assert human[0]["common_name"] == "Human"
    assert queries.anage_species(conn, "mouse")[0]["genus"] == "Mus"


def test_drugage_filters(conn):
    rapa = queries.drugage_search(conn, compound="rapa")
    assert len(rapa) == 3 and {r["species"] for r in rapa} == {"Mus musculus", "Rattus norvegicus"}
    dog = queries.drugage_search(conn, species="Canis")
    assert len(dog) == 1 and dog[0]["compound_name"] == "L-deprenyl"
    itp = queries.drugage_search(conn, itp_only=True)
    assert {r["compound_name"] for r in itp} == {"Rapamycin", "Acarbose"}
    summary = queries.drugage_species_summary(conn)
    assert summary[0]["species"] == "Mus musculus" and summary[0]["compounds"] == 2


def test_genage_search_orders_exact_symbol_first(conn):
    res = queries.genage_search(conn, "igf1r")
    assert res["human"][0]["symbol"] == "IGF1R" and res["human"][0]["why"] == "mammal"
    assert res["model_organisms"][0]["symbol"] == "Igf1r"
    assert res["model_organisms"][0]["longevity_influence"] == "Anti-Longevity"
    assert queries.genage_search(conn, "rapamycin")["human"][0]["symbol"] == "MTOR"


def test_dap_codebook_search_and_variable(conn):
    rels = queries.dap_releases(conn)
    assert [r["release"] for r in rels] == ["2025_v1.0", "2024_v1.1"]
    hit = queries.dap_codebook_search(conn, "rapamycin")
    assert hit["release"] == "2025_v1.0"
    assert hit["results"][0]["variable"] == "mp_rapamycin"
    dental = queries.dap_codebook_search(conn, "dental", data_file="HLES_health")
    assert dental["results"][0]["variable"] == "hs_condition_type"
    assert queries.dap_codebook_search(conn, "rapamycin", release="2024")["results"] == []
    var = queries.dap_variable(conn, "DOG_ID")
    assert var["variable"]["data_file"] == "Dog_Overview"
    assert var["present_in_releases"] == ["2025_v1.0", "2024_v1.1"]
    assert queries.dap_variable(conn, "nope")["variable"] is None


def test_corpus_search_tiers_years_and_snippets(conn):
    core = queries.corpus_search(conn, "rapamycin")
    assert [r["key"] for r in core] == ["MED:38263575"]
    assert core[0]["has_fulltext_md"] is True and core[0]["is_open_access"] is True
    assert "[Rapamycin]" in core[0]["snippet"] or "[rapamycin]" in core[0]["snippet"].lower()
    # "dental" only matches an extended-tier record
    assert queries.corpus_search(conn, "dental") == []
    ext = queries.corpus_search(conn, "dental", tier="extended")
    assert ext[0]["key"] == "MED:1"
    assert queries.corpus_search(conn, "dogs", tier=None, year_from=2020) and all(
        r["year"] >= 2020 for r in queries.corpus_search(conn, "dogs", tier=None, year_from=2020)
    )
    # porter stemming: "aging" matches "age"
    assert queries.corpus_search(conn, "aging", tier=None)
    assert queries.corpus_search(conn, "lifespan", tier="core")[0]["key"] == "PPR:PPR900001"


def test_corpus_record_lookup_by_any_identifier(conn, corpus_dir):
    for ident in ("MED:38263575", "38263575", "PMC0000001", "10.1000/x"):
        rec = queries.corpus_record(conn, ident)
        assert rec and rec["key"] == "MED:38263575"
    assert queries.corpus_record(conn, "nope") is None
    ft = queries.corpus_fulltext(conn, corpus_dir, "PMC0000001", max_chars=40)
    assert ft["truncated"] is True and ft["markdown"].startswith("---")
    assert queries.corpus_fulltext(conn, corpus_dir, "PMC9") is None
    stats = queries.corpus_stats(conn)
    assert stats == {"records": 3, "core": 2, "open_access": 1, "with_fulltext_md": 1, "by_year": {"2019": 1, "2026": 2}}


def test_dose_translation_matches_fda_table():
    r = dose.translate(4.0, "mouse", "dog")
    assert r["dose_mg_per_kg_out"] == 0.6 and r["km_from"] == 3 and r["km_to"] == 20
    r2 = dose.translate(10.0, "dog", "human")
    assert abs(r2["dose_mg_per_kg_out"] - 5.4054) < 1e-3  # 10 × 20/37
    assert dose.translate(1.0, "Canis lupus familiaris", "humans")["from_species"] == "dog"
    try:
        dose.translate(1.0, "cat")
    except ValueError as exc:
        assert "unknown species" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown species")
