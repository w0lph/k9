---
pretty_name: Canine Aging Corpus
language:
- en
license: other
license_name: europe-pmc-and-per-article-licences
license_link: https://europepmc.org/Copyright
tags:
- biology
- veterinary
- dogs
- aging
- longevity
- geroscience
- europe-pmc
- literature
task_categories:
- text-retrieval
size_categories:
- 1K<n<10K
configs:
- config_name: records
  data_files: records.jsonl
  default: true
- config_name: fulltext
  data_files: fulltext.parquet
- config_name: manifest
  data_files: manifest.parquet
---

# Canine Aging Corpus

A versioned, reproducible corpus of the canine aging and longevity literature, built from
the [Europe PMC](https://europepmc.org/RestfulWebService) REST API by the
[`canine-aging-corpus`](https://github.com/w0lph/k9/tree/main/corpus) pipeline. It exists so
that agents and retrieval systems can work over a fixed, citable snapshot of what has been
published about dogs as a model of aging, instead of live search results that change daily.

| | |
|---|---|
| Records | 3,565 works (`records`), of which 2,185 match the strict `core` query |
| Full text | Markdown for the open-access articles whose licence allows redistribution: CC BY or CC0 (`fulltext`, also as `fulltext/md/PMC*.md`) |
| Manifest | one row per record with identifiers, year, journal, licence, and which artefacts exist (`manifest`) |
| Snapshot | `corpus_version.json`: query definitions, counts by tier / source / year, SHA-256 of `records.jsonl`, build time (2026-09-29) |

## Query tiers

Every record carries the list of tiers it matched, so consumers can filter.

- **core**: `(dog OR dogs OR canine OR "Canis familiaris") AND (aging OR ageing OR lifespan OR longevity OR geroscience)` in title or abstract. High precision.
- **extended**: adds geriatric, senior, age-related, healthspan, frailty, senescence, cognitive dysfunction, rapamycin, life expectancy. Higher recall, more clinical noise.

## Fields (`records`)

`key` (Europe PMC `source:id`, e.g. `MED:38263575`), `source`, `id`, `pmid`, `pmcid`, `doi`,
`title`, `abstract`, `authors`, `author_string`, `journal`, `year`, `first_publication_date`,
`pub_types`, `keywords`, `mesh` (descriptor, major flag, qualifiers), `grants`,
`is_open_access`, `license`, `in_pmc`, `in_epmc`, `has_pdf`, `fulltext_urls`, `cited_by_count`,
`language`, `tiers`, `retrieved_at`, `raw_page` (which raw search page the record came from).

`fulltext` rows: `pmcid`, `pmid`, `doi`, `title`, `journal`, `year`, `license`, `source`
(which service served the JATS XML: `ncbi` or `europepmc`), `article_type`, `chars`,
`markdown` (front matter, title, abstract, body sections with heading levels, table and
figure captions; references dropped).

## How it was built

```bash
cd corpus && uv sync
uv run cac fetch-metadata --tier core && uv run cac fetch-metadata --tier extended
uv run cac fetch-fulltext --source ncbi      # batched NCBI E-utilities efetch; Europe PMC is the fallback
uv run cac convert && uv run cac manifest
```

JATS XML is converted deterministically (no model involved). Raw API pages are kept by the
pipeline for provenance and `cac rebuild-records` reconstructs `records.jsonl` from them.

## Limitations

- Full text covers 1,140 of the 1,347 records with a PMCID locally; 207 are restricted by
  their publisher from XML distribution. Only the CC BY / CC0 subset is redistributed here;
  articles under CC BY-NC variants or without a licence statement are excluded from this
  repository (`fulltext_manifest.json` has the counts) and can be fetched by the pipeline.
- Europe PMC's `license` field is only populated for part of the open-access set; records
  with an empty licence are treated as non-redistributable.
- Query-based corpora have recall limits: some classic papers that do not use the query
  vocabulary in their title or abstract are absent.

## Licence

Metadata and abstracts: retrieved from Europe PMC and redistributed under
[Europe PMC's terms](https://europepmc.org/Copyright); abstract copyright stays with the
publishers and authors. Full text: each article's own licence (CC BY or CC0), stated per
row and in each Markdown file's front matter. The compilation: CC BY 4.0. See `LICENSE`.

## Related

- [`{owner}/canine-geroscience-questions`](https://huggingface.co/datasets/{owner}/canine-geroscience-questions): a grounded question set over this corpus.
- [`{owner}/dog-geroscience-mcp-data`](https://huggingface.co/datasets/{owner}/dog-geroscience-mcp-data): the SQLite database that indexes this corpus for the `dog-geroscience-mcp` server.
- Pipeline and documentation: https://github.com/w0lph/k9/tree/main/corpus
