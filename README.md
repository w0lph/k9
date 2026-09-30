# k9 — AI tooling for canine longevity research

Research brief: [canine-longevity-ai-opportunities.md](canine-longevity-ai-opportunities.md)
(landscape, ranked opportunities, and the Phase 1 plan in Section 7).

Phase 1 components:

| Directory | What | Status |
|---|---|---|
| [corpus/](corpus/README.md) | `canine-aging-corpus`: reproducible Europe PMC corpus of the canine aging literature (records, JATS→Markdown full text from Europe PMC or NCBI, manifest, version file). | Complete: 3,565 records (2,185 core); full text for 1,140 of 1,347 PMCIDs (the other 207 are publisher-restricted from XML distribution). |
| [mcp/](mcp/README.md) | `dog-geroscience-mcp`: MCP server with 17 dog-specific aging tools (AnAge/DrugAge/GenAge dog rows, dog orthologs via Ensembl with caching, FDA Km dose translation, Dog Aging Project codebooks across 9 releases, NIH RePORTER, BM25 corpus search with full-text retrieval, FOI summaries and structured records, intervention dossier). | Complete: 23 offline tests, smoke-tested against live Ensembl/RePORTER and over stdio; DB built from the finished corpus and FOI layers. |
| [questions/](questions/README.md) | `canine-geroscience-questions`: 133 questions across 10 categories, each with a gold answer and a verbatim quote from a corpus record, enforced by a validator; plus a BM25 retrieval baseline. | v0.1: drafted, validator-clean, then reviewed item-by-item by an independent LLM pass (9 fixes, 1 drop); recall@5 = 0.985. No domain-expert review yet. |

Phase 2 components:

| Directory | What | Status |
|---|---|---|
| [foi/](foi/README.md) | `foi-summaries`: FDA CVM Freedom of Information summaries as a public-domain dataset (index of 1,726 summaries, 497 dog-product PDFs, text, parsed sections and General Information fields, species flags) plus a typed, quote-validated extraction of all 497 summaries (1,026 PK values, 193 safety studies, 414 effectiveness studies, 918 adverse-reaction rows). | Complete: 497 records, 97% with parsed sections; structured layer covers all 497 (4,510 quotes, 0 errors, 79 explained warnings). |
| `mcp/` (extended) | `intervention_dossier` (synonym-aware, species-filtered), `foi_summary_search`, `foi_summary_get`, `foi_structured_search`, the `dossier_briefing` prompt; `scripts/dossier_eval.py` coverage table over ITP compounds. | Complete; 23 tests. |

`.\rebuild.ps1` regenerates everything in dependency order (`-Fresh` re-fetches sources).
[PUBLISHING.md](PUBLISHING.md) is the step-by-step for the Hugging Face Hub (dataset cards and
staging script in `publish/`), PyPI and the MCP registry (`mcp/server.json`), and Glama
(`glama.json`, root `Dockerfile`). The server installs with
`uvx dog-geroscience-mcp` (PyPI), as a Claude Desktop extension (`.mcpb` on the releases page),
or as a Claude Code plugin with a routing skill (`/plugin marketplace add w0lph/k9`, then
`/plugin install dog-geroscience@k9`; sources in `plugins/`), and downloads its database on
first run. Each directory is its own
`uv` project:

```bash
cd corpus && uv sync --extra dev && uv run pytest -q
cd mcp && uv sync && uv run dog-geroscience-mcp build && uv run pytest -q
cd questions && uv sync && uv run pytest -q && uv run cgq validate data/canine_geroscience_v0.jsonl --require-ids
cd foi && uv sync && uv run foi run && uv run pytest -q
cd mcp && uv run dog-geroscience-mcp build --skip-download   # picks up ../foi/data/foi_summaries_dog.jsonl
```

Large derived data (`corpus/data`, `mcp/data`, FOI PDFs and text) is git-ignored; it is
rebuilt by the pipelines and published as Hugging Face datasets (`publish/`).
