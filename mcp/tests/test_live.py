"""Live-tool clients against a mocked HTTP transport: happy path, retry, and error reporting."""

from __future__ import annotations

import httpx

from dog_geroscience_mcp import live
from dog_geroscience_mcp.paths import ENSEMBL_REST, REPORTER_API

HOMOLOGY = {
    "data": [
        {
            "id": "ENSG00000140443",
            "homologies": [
                {
                    "type": "ortholog_one2one",
                    "taxonomy_level": "Eutheria",
                    "dn_ds": None,
                    "source": {"id": "ENSG00000140443", "perc_id": 95.1},
                    "target": {"id": "ENSCAFG00845012345", "species": "canis_lupus_familiaris", "perc_id": 96.2, "perc_pos": 97.0},
                }
            ],
        }
    ]
}
LOOKUP = {"display_name": "IGF1R", "description": "insulin like growth factor 1 receptor", "biotype": "protein_coding",
          "assembly_name": "ROS_Cfam_1.0", "seq_region_name": "3", "start": 100, "end": 200, "strand": 1}


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.invalid")


def test_dog_ortholog_happy_path_and_cache(conn, db_path):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if "/homology/symbol/homo_sapiens/IGF1R" in str(req.url):
            return httpx.Response(200, json=HOMOLOGY)
        if "/lookup/id/ENSCAFG00845012345" in str(req.url):
            return httpx.Response(200, json=LOOKUP)
        return httpx.Response(404)

    rw = httpx.Client(transport=httpx.MockTransport(handler))
    out = live.dog_ortholog("IGF1R", "human", cache_db=db_path, client=rw)
    assert out["n_orthologs"] == 1
    o = out["orthologs"][0]
    assert o["dog_symbol"] == "IGF1R" and o["type"] == "ortholog_one2one" and o["location"] == "3:100-200:1"
    assert len(calls) == 2
    again = live.dog_ortholog("igf1r", "human", cache_db=db_path, client=rw)
    assert again["cached"] is True and len(calls) == 2  # served from the built DB's cache table
    # the read-only query connection still sees the cached row
    assert conn.execute("SELECT COUNT(*) FROM ensembl_cache").fetchone()[0] == 1


def test_dog_ortholog_reports_server_errors_instead_of_raising(monkeypatch):
    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    n = {"calls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        n["calls"] += 1
        return httpx.Response(500, text="boom")

    out = live.dog_ortholog("IGF1R", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert out["error"].startswith("Ensembl REST request failed") and out["retryable"] is True
    assert n["calls"] == 3  # retried

    def bad_symbol(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="No valid lookup found for symbol NOPE")

    out2 = live.dog_ortholog("NOPE", client=httpx.Client(transport=httpx.MockTransport(bad_symbol)))
    assert out2["retryable"] is False and "NOPE" in out2["error"]


def test_reporter_search_shapes_results_and_handles_outage(monkeypatch):
    monkeypatch.setattr(live.time, "sleep", lambda s: None)
    payload = {
        "meta": {"total": 1},
        "results": [
            {
                "appl_id": 11027111, "project_num": "5R01AG090843-02", "fiscal_year": 2026,
                "project_title": "Test of Rapamycin in Aging Dogs (TRIAD)", "organization": {"org_name": "TEXAS A&M"},
                "principal_investigators": [{"full_name": "Kate Creevy"}], "agency_ic_admin": {"abbreviation": "NIA"},
                "activity_code": "R01", "award_amount": 2636580, "project_start_date": "2024-12-01", "project_end_date": "2029-11-30",
                "abstract_text": "x" * 3000,
            }
        ],
    }
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        assert str(req.url) == REPORTER_API
        seen["body"] = req.read()
        return httpx.Response(200, json=payload)

    out = live.reporter_search("Dog Aging Project", fiscal_years=[2025, 2026], limit=5, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert out["total"] == 1
    p = out["results"][0]
    assert p["principal_investigators"] == ["Kate Creevy"] and p["agency"] == "NIA"
    assert p["url"].endswith("/11027111") and len(p["abstract"]) == 1500
    assert b'"fiscal_years": [2025, 2026]' in seen["body"] or b'"fiscal_years":[2025,2026]' in seen["body"]

    down = live.reporter_search("x", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    assert "NIH RePORTER request failed" in down["error"]


def test_species_alias_resolution():
    assert live._species("Human") == "homo_sapiens" and live._species("Mouse") == "mus_musculus"
    assert live._species("Rattus norvegicus") == "rattus_norvegicus"
    assert ENSEMBL_REST.startswith("https://rest.ensembl.org")
