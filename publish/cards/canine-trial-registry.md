---
license: cc-by-4.0
language:
  - en
pretty_name: Canine aging trial registry
tags:
  - dogs
  - aging
  - geroscience
  - clinical-trials
  - veterinary
  - registry
size_categories:
  - n<1K
configs:
  - config_name: default
    data_files: canine_trials.jsonl
---

# Canine aging trial registry

A registry of interventional studies and longitudinal cohorts on aging in dogs: lifespan and
healthspan trials (rapamycin, diet restriction, L-deprenyl, the Dog Aging Project's TRIAD),
cognitive-aging and mobility trials in senior dogs, immunosenescence and organ-decline
interventions, cancer-prevention trials in older dogs, lifetime cohorts (Dog Aging Project,
Golden Retriever Lifetime Study), and company regulatory programs for lifespan-extension drugs
(Loyal's STAY study of LOY-002, LOY-001, LOY-003).

Veterinary trials are not registered on ClinicalTrials.gov and company programs are known
only from announcements, so no such registry existed. Each record is typed (design, status,
setting, intervention and class, comparator, dose regimen, duration, population, primary
outcome, result as the source states it, organisation, registration ids, sources) and every
field is backed by a verbatim quote from the cited source; a validator refuses records whose
quotes cannot be found in the cited abstract, full text or page snapshot.

## Files

| File | Contents |
|---|---|
| `canine_trials.jsonl` | one record per study (schema in `schema.json`) |
| `canine_trials.csv` | flat export of the main fields |
| `schema.json` | JSON Schema 2020-12 |
| `sources/web/*.txt`, `sources/web_index.json` | text snapshots of company and press pages quoted by `web` sources, with URL, date and hash |
| `sources/europepmc/*.json` | abstracts of peer-reviewed sources outside the canine-aging-corpus |

Quotes from `pmid` sources are checked against the
[canine-aging-corpus](https://huggingface.co/datasets/{owner}/canine-aging-corpus) abstracts
and full texts.

## Provenance and caveats

v0 (2026-10-01): candidates were screened from the corpus (trial-tagged records and
trial-vocabulary searches) and drafted by model-assisted extraction in batches, plus
hand-written company records; all quotes validated; no domain-expert review yet. Records of
kind `regulatory_program` rest on company and press sources only and say so in `notes`.
Disease-treatment trials framed around a disease rather than aging are out of scope.

Source code, validator and contribution guide: https://github.com/w0lph/k9/tree/main/trials.
The registry is served as `canine_trial_search` by the
[dog-geroscience-mcp](https://huggingface.co/datasets/{owner}/dog-geroscience-mcp-data) server
and as pages at https://w0lph.github.io/k9/trials/.

## Licence

Registry text CC BY 4.0. Quotes are short excerpts used for verification and attribution;
the cited articles keep their own licences. Snapshots of company and press pages are kept
for verification only.
