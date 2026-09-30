"""End-to-end: connect an in-process MCP client to the server and call tools."""

from __future__ import annotations

import contextlib
import json

from mcp import Client

from dog_geroscience_mcp.server import create_server

EXPECTED_TOOLS = {
    "corpus_info",
    "anage_species",
    "drugage_search",
    "drugage_species_summary",
    "genage_search",
    "dog_ortholog",
    "dose_translate",
    "dap_releases",
    "dap_codebook_search",
    "dap_variable",
    "nih_reporter_search",
    "corpus_search",
    "corpus_record",
    "intervention_dossier",
    "foi_summary_search",
    "foi_summary_get",
    "foi_structured_search",
}


def _data(result):
    """Unwrap a CallToolResult into plain Python (structured content preferred)."""
    sc = getattr(result, "structured_content", None)
    if sc:
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    return None


@contextlib.asynccontextmanager
async def connected(db_path, corpus_dir):
    # Entered inside the test's own task: anyio cancel scopes must not cross tasks, which
    # rules out a yielding async fixture here.
    async with Client(create_server(db_path, corpus_dir)) as c:
        yield c


async def test_lists_all_tools_with_descriptions(db_path, corpus_dir):
    async with connected(db_path, corpus_dir) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools.tools}
    assert names == EXPECTED_TOOLS
    assert all(t.description and len(t.description) > 40 for t in tools.tools)
    schema = {t.name: t.input_schema for t in tools.tools}
    assert "compound" in schema["drugage_search"]["properties"]
    assert schema["dose_translate"]["required"] == ["dose_mg_per_kg", "from_species"]


async def test_offline_tools_round_trip(db_path, corpus_dir):
    async with connected(db_path, corpus_dir) as client:
        info = _data(await client.call_tool("corpus_info", {}))
        assert info["corpus"]["records"] == 3 and info["build"]["hagr"]["anage"] == 5

        dog = _data(await client.call_tool("anage_species", {}))
        assert dog[0]["scientific_name"] == "Canis familiaris"
        assert _data(await client.call_tool("anage_species", {"species": "dog"}))[0]["common_name"] == "Domestic dog"

        rows = _data(await client.call_tool("drugage_search", {"species": "Canis"}))
        assert rows[0]["compound_name"] == "L-deprenyl"

        genes = _data(await client.call_tool("genage_search", {"query": "MTOR"}))
        assert genes["human"][0]["symbol"] == "MTOR"

        d = _data(await client.call_tool("dose_translate", {"dose_mg_per_kg": 4, "from_species": "mouse"}))
        assert d["dose_mg_per_kg_out"] == 0.6

        cb = _data(await client.call_tool("dap_codebook_search", {"query": "cause of death"}))
        assert cb["results"][0]["variable"] == "eol_cause_death"

        var = _data(await client.call_tool("dap_variable", {"variable": "dog_id"}))
        assert var["present_in_releases"] == ["2025_v1.0", "2024_v1.1"]

        hits = _data(await client.call_tool("corpus_search", {"query": "rapamycin"}))
        assert hits[0]["key"] == "MED:38263575"

        rec = _data(
            await client.call_tool("corpus_record", {"key": "PMC0000001", "include_fulltext": True, "max_chars": 60})
        )
        assert rec["fulltext"]["truncated"] is True and rec["title"].startswith("Weekly rapamycin")

        missing = _data(await client.call_tool("corpus_record", {"key": "nope"}))
        assert "error" in missing

        bad = _data(await client.call_tool("dose_translate", {"dose_mg_per_kg": 1, "from_species": "cat"}))
        assert "unknown species" in bad["error"] and "dog" in bad["known_species"]

        missing_foi = _data(await client.call_tool("foi_summary_get", {"foi_id": 1}))
        assert "FOI dataset not found" in missing_foi["error"] or "no FOI summary" in missing_foi["error"]

        prompts = await client.list_prompts()
        assert "dossier_briefing" in {p.name for p in prompts.prompts}


async def test_foi_summary_get_reads_sections(db_path, corpus_dir, tmp_path):
    foi = tmp_path / "foi_summaries_dog.jsonl"
    foi.write_text(json.dumps({
        "foi_id": 7, "application_number": "141-007", "proprietary_name": "Dogalong", "ingredients": "Dogazine",
        "parsed": {"general_information": {"recommended_dosage": "0.5 mg/kg"},
                   "sections": {"general_information": "GI text", "target_animal_safety": "Dogs received 1X, 3X and 5X." * 3}},
        "text": {"pages": 3},
    }) + "\n", encoding="utf-8")
    async with Client(create_server(db_path, corpus_dir, foi_path=foi)) as client:
        rec = _data(await client.call_tool("foi_summary_get", {"foi_id": 7, "sections": ["target_animal_safety"], "max_chars": 40}))
        assert rec["sections"] == {"target_animal_safety": ("Dogs received 1X, 3X and 5X." * 3)[:40]} and rec["truncated"] is True
        assert rec["sections_available"] == ["general_information", "target_animal_safety"]
        assert rec["general_information"]["recommended_dosage"] == "0.5 mg/kg"
        nope = _data(await client.call_tool("foi_summary_get", {"foi_id": 8}))
        assert "no FOI summary" in nope["error"]
