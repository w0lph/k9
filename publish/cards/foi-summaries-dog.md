---
pretty_name: FDA CVM FOI Summaries (dog products)
language:
- en
license: other
license_name: us-government-work-public-domain
license_link: https://www.usa.gov/government-copyright
tags:
- veterinary
- dogs
- pharmacology
- pharmacokinetics
- drug-safety
- fda
- regulatory
- aging
task_categories:
- text-retrieval
- question-answering
size_categories:
- n<1K
configs:
- config_name: summaries
  data_files: foi_summaries_dog.jsonl
  default: true
- config_name: structured
  data_files: structured_dog.jsonl
- config_name: catalogue
  data_files: foi_index.jsonl
---

# FDA CVM FOI Summaries, dog products

The FDA Center for Veterinary Medicine publishes a Freedom of Information (FOI) summary for
every approved animal drug application: the effectiveness studies, target-animal safety
studies (dose multiples, durations, findings), pharmacokinetics, and the agency's
conclusions. They are US Government works but live only as PDFs behind a JavaScript
application with no bulk download. This dataset is the dog subset as machine-readable text,
parsed sections, and a typed, quote-grounded extraction. It is the only public,
regulator-reviewed source of dog pharmacokinetic and safety-margin data, which is what a
canine geroscience trial has to start from.

| Config | Rows | What |
|---|---|---|
| `summaries` | 497 | One row per FOI summary joined to a dog application: catalogue metadata, PDF link, text statistics, parsed template sections, General Information fields, candidate PK / safety sentences, dose mentions, `species_flag` |
| `structured` | 497 | Typed records extracted from each summary: indication, dose regimen, PK values, target-animal-safety design and findings, effectiveness study, adverse reactions with treated / control rates; every value carries a verbatim `quote` |
| `catalogue` | 1,726 | Every FOI summary in the FDA catalogue (all species): application number, sponsor, ingredients, approval type and date |
| `text/<foi_id>.txt` | 497 files | The extracted PDF text the quotes are checked against |

## Species

The join is by application number, and a multi-species application owns one FOI summary per
species or supplement, so a "dog application" can hold a cat, cattle, horse or deer summary.
`summaries.species_flag` (`dog` 453 / `other` 34 / `unknown` 10) and
`structured.species_class` (the species exactly as the summary states it) let you filter.
For non-dog summaries, `structured.effectiveness.n_dogs` holds that species' animal count.

## Structured extraction

| | |
|---|---|
| Records | 497 (160 ingredients): dogs only 327; dogs plus another species 133; another species 37 |
| Pharmacokinetic values | 1,026 on 191 records |
| Target-animal-safety studies | 193 records (176 with dose multiples) |
| Effectiveness studies | 414 records (290 with an animal count); generics carry the bioequivalence study or waiver statement instead |
| Adverse-reaction rows | 918 on 267 records (497 with a control-group value) |
| Validation | 4,510 quotes, 0 errors; 79 warnings for labeling-only supplements and biowaiver generics that contain no studies |

The extraction was done by model agents (Claude Fable 5.1) reading the parsed text, in 35
batches, each validated by `foi validate-structured`: every `quote` must be a verbatim
span of `text/<foi_id>.txt` (after whitespace and Unicode normalisation), and every number
in a field must appear in that field's quote. Caveats recorded per record in `notes`:
flattened PDF tables are quoted as extracted with the column order described; typos,
hyphenation breaks and private-use glyphs in the source are preserved inside quotes; counts
spelled out in words stay in the quote and the numeric field is null; literature-based
approvals carry the summary's cited figures, labelled as such.

## How it was built

```bash
cd foi && uv sync
uv run foi run            # index -> download PDFs -> extract text -> parse sections
uv run foi validate-structured data/structured_dog.jsonl
```

The section parser is template-based (Roman or Arabic numerals before or after the heading,
column-reordered layouts from pypdf) and needs no model; 480 of 497 summaries (97%) parse
into sections, the rest are 1985 to 1999 layouts. No summary in the dog subset is scanned.

## Limitations

- PDF text extraction flattens tables; the `structured` config quotes them as extracted.
- 34 summaries under dog applications are for other species and 10 could not be assigned.
- Older summaries have no General Information block; the parser then leaves those fields empty.

## Licence

FOI summaries and their text: US Government works (FDA CVM), public domain in the United
States. Parsed fields and the structured extraction: CC BY 4.0. See `LICENSE`.

## Related

- Pipeline and documentation: https://github.com/w0lph/k9/tree/main/foi
- The `dog-geroscience-mcp` server exposes this dataset as `foi_summary_search`, `foi_summary_get`, `foi_structured_search` and inside `intervention_dossier`.
