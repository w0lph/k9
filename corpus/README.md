# canine-aging-corpus

Versioned, reproducible corpus of the canine aging / longevity literature, built from
[Europe PMC](https://europepmc.org/RestfulWebService).

## What it produces

All outputs live under `data/` (git-ignored; published separately).

| Path | Contents |
|---|---|
| `data/raw/europepmc/search/<tier>/<run>/page_*.json` | Raw search pages exactly as returned, plus `query.txt`. Provenance; never modified. |
| `data/records.jsonl` | One normalised record per Europe PMC work (`source:id`), with abstract, MeSH, keywords, grants, OA flags, and the list of query **tiers** it matched. |
| `data/fulltext/xml/PMC*.xml` | JATS full text where Europe PMC serves it (open-access subset plus some author manuscripts). |
| `data/fulltext/md/PMC*.md` | Markdown conversion (front matter + title, abstract, body sections, table/figure captions; references dropped). |
| `data/manifest.parquet`, `data/manifest.csv` | One row per record: identifiers, year, journal, OA/licence, which artefacts exist, tiers. |
| `data/corpus_version.json` | Query definitions, counts by tier/source/year, SHA-256 of `records.jsonl`, build timestamp. |

## Query tiers

Defined in `src/canine_aging_corpus/config.py`.

- **core** — `(dog OR dogs OR canine OR "Canis familiaris") AND (aging OR ageing OR lifespan OR longevity OR geroscience)` in title/abstract. High precision; this is the set used in the opportunity analysis.
- **extended** — adds geriatric, senior, age-related, healthspan, frailty, senescence, cognitive dysfunction, rapamycin, life expectancy. Higher recall, more clinical noise. Every record carries all tiers it matched, so consumers can filter.

## Usage

```bash
uv sync --extra dev
uv run cac run                      # fetch-metadata -> fetch-fulltext -> convert -> manifest
uv run cac stats                    # counts from corpus_version.json
```

Individual steps:

```bash
uv run cac fetch-metadata --tier core --page-size 500 --max-attempts 12
uv run cac rebuild-records          # rebuild records.jsonl from raw pages, no network
uv run cac fetch-fulltext --workers 4 --limit 20
uv run cac convert
uv run cac manifest
```

## Full-text sources

Two services serve PMC JATS XML and the pipeline can use either:

- **Europe PMC** `/{PMCID}/fullTextXML` (default `--source europepmc`): one request per file; covers
  the open-access subset and some author manuscripts.
- **NCBI E-utilities** `efetch.fcgi?db=pmc` (`--source ncbi`): batched, 100 PMCIDs per request,
  3 requests/second (10 with `NCBI_API_KEY`). Articles whose publisher does not allow XML
  distribution come back as front matter with a notice; the pipeline records those as
  status 403 and saves nothing.

`fulltext/sources.jsonl` records which service each XML came from, and the Markdown front
matter's `source` field carries it through. On 2026-09-28 Europe PMC's endpoint returned
HTTP 500 for hours; NCBI filled the 951-file backlog in 44 seconds (722 with bodies, 22
front-only, 207 publisher-restricted).

## Robustness

Europe PMC has been observed returning 503 for the whole API for tens of minutes at a
time. The pipeline is built for that:

- Every request retries on 429/5xx/transport errors with exponential backoff (`--max-attempts`).
- `records.jsonl` is rewritten after every completed tier and again on failure, so an
  interrupted run never loses finished tiers.
- Raw pages are always written as they arrive; `cac rebuild-records` reconstructs
  `records.jsonl` from them without touching the network (runs replayed in
  chronological order; tiers are unioned, newest metadata wins).
- Full-text and conversion steps are idempotent and skip files already on disk unless `--force`.
- The full-text step fails fast (`--max-attempts 3` by default) and has a circuit breaker:
  after `--breaker` consecutive failures it aborts with exit code 3 and reports
  `remaining`. Europe PMC's search endpoint has stayed up while `/fullTextXML` returned
  500 for everything, so the right response is to re-run the step later, not to wait
  inside it. `data/ft_loop.sh` is a simple "re-run every 10 minutes until remaining=0" loop.

## Identity and provenance

- Records are keyed by Europe PMC `source:id` (e.g. `MED:38263575`, `PPR:PPR900001`), so a
  preprint and its journal version are separate works, joinable on DOI.
- Each record stores `retrieved_at` and the relative path of the raw page it came from.
- The pipeline sends a generic `User-Agent`; set `CAC_CONTACT` to add a `From:` header if
  you want Europe PMC to be able to reach you.

## Development

```bash
uv run pytest -q
uv run ruff check src tests
```

Tests use fixtures plus `httpx.MockTransport`; nothing in the suite touches the network.

## Licence

Code: MIT. Corpus contents retain their original licences; Europe PMC open-access full
text carries the licence stated in each article's front matter, and abstracts/metadata are
redistributed under Europe PMC's terms.
