# foi-summaries

FDA Center for Veterinary Medicine publishes a Freedom of Information (FOI) summary for every
approved animal drug application: the effectiveness studies, target-animal safety studies
(dose multiples, durations, findings), pharmacokinetics, and the agency's conclusions. They
are US Government works (public domain) but live only as PDFs behind a JavaScript app with
no bulk download. This package turns them into a dataset, dog products first.

Why it matters for canine geroscience: it is the only public, regulator-reviewed source of
dog pharmacokinetics and safety-margin data, and it is where the first lifespan-extension
drug's summary will appear when one is conditionally approved.

## Pipeline

| Stage | Command | Output |
|---|---|---|
| Index | `foi index` | `foi_index.jsonl` (every FOI summary, all species), `applications_dog.jsonl` (search results for species = Dog), `foi_dog.jsonl` (the join), `index_summary.json` |
| PDFs | `foi download [--all-species] [--limit N]` | `pdf/<foiId>.pdf` (idempotent) |
| Text | `foi text` | `text/<foiId>.txt`, `text_stats.jsonl` (pages, chars, `likely_scanned` when < 200 chars/page) |
| Dataset | `foi dataset [--no-sections]` | `foi_summaries_dog.jsonl`, `dataset_version.json` |

`foi run` does all four for the dog subset.

Each dataset record carries the catalogue metadata (application number, sponsor, ingredients,
proprietary name, approval type and date, one-line summary, PDF URL) and, where text was
extractable, a deterministic parse of the summary template:

- `sections`: text of each Roman-numeral section (General Information, Effectiveness,
  Target Animal Safety, Human Food Safety, User Safety, Agency Conclusions, ...);
- `general_information`: the `Field: value` block (established name, dosage form, route,
  species/class, recommended dosage, indications, ...);
- `pk_sentences`, `safety_sentences`, `dose_mentions`: candidate sentences and dose strings
  for a later LLM or human structuring pass.

The parser is template-based and needs no model, so every field is traceable to a span of the
source text. Scanned summaries (older applications) are flagged rather than OCR'd.

## v0 (2026-09-29)

| | |
|---|---|
| FOI summaries in the catalogue (all species) | 1,726 |
| Dog applications (search, species = Dog) | 694 |
| FOI summaries joined to dog applications | 497 (350 applications, 159 distinct ingredients) |
| Text extracted | 497 of 497; none flagged as scanned |
| Template sections parsed | 480 (97%); the 17 misses are 1985–1999 layouts |
| General Information fields | sponsor 427, dosage form 375, proprietary name 362, dosage 335, route 318, indication 279, species/class 238 |
| Candidate sentences | pharmacokinetics on 202 summaries, target-animal safety on 132 |

Three heading layouts are handled: `II. EFFECTIVENESS`, `2. EFFECTIVENESS`, and pypdf's
column-reordered `EFFECTIVENESS II.` / `File Number A.`. The `dog-geroscience-mcp` build
loads this file into a `foi_dog` table for its `foi_summary_search` and
`intervention_dossier` tools.

Each record also carries `species_flag` (`dog` 453 / `other` 34 / `unknown` 10): the join is by
application number, and a multi-species NADA owns one FOI summary per species or supplement,
so a dog application can hold a cat-indication summary. Filter on the flag.

## Structured extraction (`data/structured_dog.jsonl`)

All 497 summaries were extracted into typed records: indication, dose regimen, pharmacokinetic
values, target-animal-safety design and findings, the pivotal effectiveness study, and adverse
reactions with treated/control rates. `foi validate-structured` enforces that every value's
`quote` is a verbatim span of the summary text and that every number in a field appears in
its quote; the merged file passes with 4,510 quotes checked and 0 errors.

| | |
|---|---|
| Records | 497 (160 ingredients). Species as stated by each summary: dogs only 327; dogs plus another species 133; another species under a dog application 37 |
| Pharmacokinetic values | 1,026 on 191 records |
| Target-animal-safety studies | 193 records (176 with dose multiples) |
| Effectiveness studies | 414 records (290 with an animal count); generics carry the bioequivalence study or waiver statement instead |
| Adverse-reaction rows | 918 on 267 records (497 rows with a control-group value) |
| Validator warnings | 79, all "no PK, safety or effectiveness content": labeling-only supplements and biowaiver generics, each explained in `notes` |

Extraction was done by model subagents (Claude Fable 5.1) reading the parsed text with
`foi show` / `foi grep`: 35 drafts of up to 15 records under `data/structured/drafts/`
(batch plan in `data/structured/batches.json`; `foi structured-status` reports progress),
merged with `foi merge-structured`. Caveats, recorded per record in `notes`:

- A multi-species application can own a cat, cattle, horse, poultry, deer or other summary. The
  record keeps the summary's own `species_class`, and for those records `n_dogs` holds that
  species' animal count.
- Flattened PDF tables are quoted as extracted, with the column order described in
  `conditions` or `notes`.
- Typos, hyphenation breaks and private-use glyphs in the source text are preserved verbatim
  inside quotes; counts spelled out in words ("Forty-eight") stay in the quote and the numeric
  field is null.
- Literature-based approvals (conditional approvals, DESI-era products) carry the summary's
  cited figures, labelled as such.

Extend by adding records to a new draft file and re-running merge + validate; `foi schema`
prints the record shape.

## Source API

Read from the site's own AngularJS services (`searchResultService.js`,
`foiDrugSummariesService.js`), base `https://animaldrugsatfda.fda.gov/adafda/app/search/public`:

- `POST /advancedSearch` with a **flat** JSON body (`speciesName`, `activeIngredientName`,
  `pageSize`, `pageNumber`, ...). A nested `paging` object returns HTTP 500.
- `GET /foiDrugSummaries/foiApplicationNumbers` then
  `GET /foiDrugSummaries/foiApplicationsInfo/{start}/{end}/`.
- `GET /document/downloadFoi/{foiId}` (PDF).

The client throttles to about four requests a second and retries on 5xx.

## Develop

```bash
uv sync
uv run pytest -q
uv run ruff check src tests
```
