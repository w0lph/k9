---
pretty_name: dog-geroscience-mcp database
language:
- en
license: other
license_name: mixed-see-card
license_link: https://github.com/w0lph/k9/blob/main/mcp/README.md
tags:
- mcp
- model-context-protocol
- dogs
- aging
- geroscience
- sqlite
viewer: false
---

# dog-geroscience-mcp database

`dog_geroscience.sqlite` is the prebuilt database that the
[`dog-geroscience-mcp`](https://pypi.org/project/dog-geroscience-mcp/) server downloads on
first run (`uvx dog-geroscience-mcp`, or `dog-geroscience-mcp fetch-data`). It is not meant to
be browsed here; it exists so that installing the server needs no build step.

| Table | Source | Terms |
|---|---|---|
| `anage`, `drugage`, `genage_human`, `genage_models` | [HAGR](https://genomics.senescence.info) | CC BY 3.0 |
| `dap_codebook`, `dap_codebook_fts` | [Dog Aging Project codebooks](https://github.com/dogagingproject/dataRelease) | as published on GitHub |
| `corpus_records`, `corpus_fts` | [Canine Aging Corpus](https://huggingface.co/datasets/{owner}/canine-aging-corpus) (Europe PMC) | Europe PMC terms |
| `corpus_fulltext` | the corpus's CC BY / CC0 full text only | per-article licence in each row |
| `foi_dog`, `foi_records`, `foi_structured` | [FOI summaries, dog products](https://huggingface.co/datasets/{owner}/foi-summaries-dog) | public domain; extraction CC BY 4.0 |
| `meta` | build summary: every source URL, fetch time, counts | |
| `ensembl_cache` | empty; filled at run time by the `dog_ortholog` tool | |

`build_summary.json` is the same build record as `meta.build`.

## Rebuilding it

```bash
cd mcp && uv sync
uv run dog-geroscience-mcp build --fulltext-licences "cc by,cc0" --out dog_geroscience.sqlite
```

`build` downloads the HAGR files and the DAP codebooks, indexes `../corpus/data` and
`../foi/data`, and writes a single file. Without `--fulltext-licences` it stores every full
text on disk (for local use); the published file stores only the redistributable subset.

## Licence

Mixed, per table, as listed above and in `LICENSE`. The server code is MIT.
