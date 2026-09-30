# dog-geroscience-mcp

mcp-name: io.github.w0lph/dog-geroscience-mcp

An MCP server that gives any agent (Claude, Cursor, other MCP clients) dog-specific aging
tools that do not exist anywhere else:

| Tool | Source | What it answers |
|---|---|---|
| `anage_species` | HAGR AnAge | Longevity record for the dog (or any species for comparison): max longevity, IMR, MRDT, weight, maturity. |
| `drugage_search`, `drugage_species_summary` | HAGR DrugAge | Lifespan-extension experiments by compound/species, with the NIA ITP flag; shows how thin the dog evidence is. |
| `genage_search` | HAGR GenAge | Human aging genes and model-organism longevity genes by symbol/name. |
| `dog_ortholog` | Ensembl Compara (live, cached) | Dog ortholog(s) of a human/mouse gene: id, symbol, % identity, orthology type, location. |
| `dose_translate` | FDA 2005 Km table | mg/kg conversion between species (mouse → dog = ×3/20). |
| `dap_releases`, `dap_codebook_search`, `dap_variable` | Dog Aging Project public codebooks (GitHub) | Which survey variables capture a concept; full entry for a variable; which releases contain it. |
| `nih_reporter_search` | NIH RePORTER v2 (live) | Funded projects matching a phrase, by fiscal year. |
| `corpus_search`, `corpus_record`, `corpus_info` | canine-aging-corpus (Europe PMC) | BM25 search over 3,500+ canine aging papers; abstracts for all, Markdown full text for the open-access subset. |
| `foi_summary_search`, `foi_summary_get` | foi-summaries (FDA CVM, public domain) | FOI summaries for 497 dog products: recommended dosage, indications, route, PK and safety candidate sentences, PDF link; `foi_summary_get` returns the parsed section text (e.g. the dose-multiple target-animal-safety study) by `foi_id`. |
| `foi_structured_search` | foi-summaries structured layer | Typed, quote-grounded records for all 497 summaries (1,026 PK values, 193 safety studies, 918 adverse-reaction rows): dose regimen, PK values, target-animal-safety design/findings, effectiveness study, adverse reactions with treated/control rates. |
| `intervention_dossier` | composition of the above + openFDA | One evidence package per compound: DrugAge across species with ITP and dog rows, dog-equivalent doses, corpus hits and dog trials, target ortholog, openFDA dog adverse events, FOI summaries, explicit gaps. Synonym-aware (selegiline ↔ L-deprenyl, rapamycin ↔ sirolimus). |

The server also exposes one MCP prompt, `dossier_briefing(compound, target_gene?)`, which
instructs the client model to call `intervention_dossier` and write a six-section evidence
briefing without adding anything the tools did not return. `examples/rapamycin_briefing.md`
is a worked example written from `examples/rapamycin_dossier.json`; `examples/selegiline_dossier.json`
shows the FOI and structured blocks populated for a marketed veterinary drug.

`scripts/dossier_eval.py` runs the dossier over 14 ITP-tested compounds plus two veterinary
comparators and prints a coverage table (`data/dossier_eval.json`). It measures what the
sources contain, not biological truth: for example rapamycin resolves 37 DrugAge experiments,
16 ITP rows, 152 corpus mentions and 5 candidate dog trials but no FOI summary (not a
veterinary product), while selegiline resolves 1 dog lifespan experiment, 4,117 openFDA dog
reports and 2 FOI summaries with 2 structured records, and carprofen 46,859 openFDA dog reports
plus FOI summaries and structured records up to each search's result cap (11 and 19).

Adjacent servers this one deliberately does not duplicate: `sniff-mcp` (canine genomics,
OMIA, breed allele frequencies), `mcp-veterinary-fda` (openFDA animal adverse events, Green
Book), and the `longevity-genie` servers (Open Genes, SynergyAge, gget).

## Install

No build step: the first run downloads the prebuilt database (~90 MB) from the Hugging Face
Hub ([`w0lph/dog-geroscience-mcp-data`](https://huggingface.co/datasets/w0lph/dog-geroscience-mcp-data))
into a per-user cache directory, and every offline tool works from that single file.

```bash
uvx dog-geroscience-mcp                 # stdio server; downloads the database on first start
uvx dog-geroscience-mcp fetch-data      # or download it explicitly (prints the path)
```

Claude Desktop / Claude Code / Cursor config:

```json
{
  "mcpServers": {
    "dog-geroscience": {
      "command": "uvx",
      "args": ["dog-geroscience-mcp"]
    }
  }
}
```

Claude Desktop, one click: download `dog-geroscience-mcp-<version>.mcpb` from the
[releases page](https://github.com/w0lph/k9/releases) and open it (Settings → Extensions →
Install from file). The bundle declares the PyPI package as a `uv`-type extension, so the
desktop app installs it with its own uv; nothing else to set up. Source of the bundle:
`mcpb/` (`npx @anthropic-ai/mcpb pack mcpb dist/dog-geroscience-mcp-0.1.0.mcpb`).

Claude Code, as a plugin with a routing skill (needs `uv` on the PATH):

```text
/plugin marketplace add w0lph/k9
/plugin install dog-geroscience@k9
```

Codex CLI:

```bash
codex mcp add dog-geroscience -- uvx dog-geroscience-mcp
```

The skill alone, for any agent that reads `SKILL.md` files: copy
`plugins/dog-geroscience/skills/dog-geroscience/` into your skills directory (for Claude Code,
`~/.claude/skills/`). It routes dog-aging questions to the right tools and states how to read
their output (species labels on FOI summaries, allometric doses, verbatim quotes).

Docker (the root `Dockerfile` of the repository bakes the database into the image):

```bash
docker build -t dog-geroscience-mcp . && docker run -i --rm dog-geroscience-mcp
```

Environment: `DOG_GERO_DATA` (where the database lives; default `%LOCALAPPDATA%\dog-geroscience-mcp`
on Windows, `~/.cache/dog-geroscience-mcp` elsewhere, `<checkout>/data` in a source checkout),
`DOG_GERO_DB_URL` (alternative download URL), `DOG_GERO_AUTO_FETCH=0` (fail instead of
downloading when the database is missing).

## Build from sources

```bash
uv sync
uv run dog-geroscience-mcp build            # downloads HAGR + DAP codebooks, indexes ../corpus/data and ../foi/data
uv run dog-geroscience-mcp build --skip-download
uv run dog-geroscience-mcp build --fulltext-licences "cc by,cc0" --out dog_geroscience.sqlite   # the redistributable build
uv run dog-geroscience-mcp                  # serve from data/dog_geroscience.sqlite
uv run mcp dev src/dog_geroscience_mcp/server.py   # inspector (optional)
```

The build writes one SQLite file: plain tables + FTS5 indexes, the corpus's Markdown full
text (all of it locally; only CC BY / CC0 articles in the published file), the full FOI
records, and a `meta` table with every source URL and fetch time. `DOG_GERO_CORPUS`,
`DOG_GERO_FOI` and `DOG_GERO_FOI_STRUCTURED` point the build at the inputs.

In a source checkout, Claude Desktop can run it without PyPI:

```json
{
  "mcpServers": {
    "dog-geroscience": {
      "command": "uv",
      "args": ["--directory", "D:/OneDrive/k9/mcp", "run", "dog-geroscience-mcp"]
    }
  }
}
```

## Design

- Ground-truth tables (AnAge, DrugAge, GenAge, DAP codebooks) are served verbatim with their
  source; nothing is merged or inferred.
- Network at request time is limited to the live tools (Ensembl, RePORTER, and openFDA inside
  the dossier); Ensembl results are cached in the database. The database itself is fetched
  once, atomically, and checked for the SQLite header before use.
- Query functions in `queries.py` are pure and tested offline; `server.py` is a thin wrapper.
- Licences: code MIT; HAGR data CC BY 3.0 (commercial use permitted with attribution); DAP
  codebooks are public GitHub files; corpus content keeps each article's own licence.

## Test

```bash
uv run pytest -q
uv run ruff check src tests
```

Tests build a miniature database from fixtures and drive the server through the SDK's
in-process client; nothing touches the network.
