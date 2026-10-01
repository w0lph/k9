# canine-trials — a registry of canine aging trials and cohorts

There is no registry for interventional studies of aging in dogs: veterinary trials are not on
ClinicalTrials.gov, company programs are known only from press releases, and the published
trials are scattered across nutrition, behaviour and veterinary journals. This package keeps
one typed record per study, with every field backed by a verbatim quote from a source held in
this repository or in the [canine-aging-corpus](../corpus/README.md), and a validator that
refuses records whose quotes cannot be found.

## Scope

Interventional studies in dogs whose stated purpose is to modify aging or an age-related
decline (lifespan, healthspan, cognition, mobility or function in senior dogs,
immunosenescence, age-related organ decline, cancer prevention in older dogs), in laboratory
colonies or client-owned dogs, of any design; plus longitudinal aging cohorts; plus company
regulatory programs for lifespan-extension drugs, flagged as company- or press-sourced.
Disease treatment trials framed around a disease rather than aging are out of scope.

## Files

| Path | What |
|---|---|
| `schema.json` | JSON Schema (2020-12) for a record |
| `data/canine_trials.jsonl` | the registry, one record per line |
| `data/canine_trials.csv` | flat export (`ct export`) |
| `data/sources/web/<slug>.txt` | text snapshots of company and press pages quoted by `web` sources (`web_index.json` has URL, date, hash) |
| `data/sources/europepmc/pmid_<pmid>.json` | abstracts of peer-reviewed sources outside the corpus |

Quotes from `pmid` sources are checked against the corpus abstract (or full text when
`quote_scope` is `fulltext`) read from the dog-geroscience-mcp database
(`../mcp/data/dog_geroscience.sqlite`, or `$DOG_GERO_DB`) or from `../corpus/data`.

## Use

```bash
uv sync --extra dev
uv run ct validate                      # schema + verbatim quotes; exit 1 on any error
uv run ct stats
uv run ct export                        # data/canine_trials.csv
uv run ct merge drafts/*.jsonl          # dedupe by id, sort by year, write data/canine_trials.jsonl
uv run pytest -q
```

## Adding a record

1. Find the source: a corpus record (PMID), or snapshot a web page into `data/sources/web/`
   and add it to `web_index.json` with the URL and retrieval date.
2. Write the record against `schema.json`. One record per study; later papers on the same
   study are additional `sources` with a `role` (design, results, follow-up, sub-analysis).
3. Every quote is a verbatim, contiguous sentence of the source. Fields the source does not
   state are `null`; `result` keeps the source's own wording, including significance.
4. `uv run ct validate` must pass.

The first release (v0, 2026-10-01) was drafted from corpus abstracts by model-assisted
extraction in three batches plus hand-written company records, then validated; no domain-expert
review yet. Entries that rest only on company announcements carry a warning in validation and
a note in the record.

## Licence

Registry text (summaries, field values) CC BY 4.0. Quotes are short excerpts used for
verification and attribution; the underlying articles keep their own licences. Company and
press snapshots are kept for verification only.
