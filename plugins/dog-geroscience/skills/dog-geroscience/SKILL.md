---
name: dog-geroscience
description: Aging research in companion dogs. Use when a question involves dogs as a model of aging, canine lifespan or longevity interventions (rapamycin, metformin, selegiline, diet restriction), translating a mouse or human intervention to dogs, dog orthologs of aging genes, Dog Aging Project survey variables, FDA veterinary drug summaries (dose, pharmacokinetics, target-animal safety), or the canine aging literature. Routes to the dog-geroscience MCP tools and says how to read their output.
---

# Dog geroscience

The `dog-geroscience` MCP server holds the aging data that exists only for dogs. Use its tools
instead of general knowledge whenever the question is about dogs and aging; cite identifiers
(PMID, PMCID, foi_id, application number, Ensembl id) from the tool output.

## Routing

| Question | Tool |
|---|---|
| "What do we know about compound X in dogs?" | `intervention_dossier(compound=X, target_gene=...)` first; it composes the tools below and lists explicit evidence gaps. Then drill down. |
| Lifespan-extension experiments for a compound, any species, ITP results | `drugage_search(compound=..., species=...)`; `drugage_species_summary()` shows how thin the dog evidence is |
| Dog longevity record, comparison species | `anage_species(species=...)` |
| Is an aging gene conserved in the dog? | `genage_search(query=...)` for the human/model-organism entry, then `dog_ortholog(gene_symbol=..., from_species="human"|"mouse")` |
| Starting dose for dogs from a mouse or human mg/kg dose | `dose_translate(dose_mg_per_kg=..., from_species=..., to_species="dog")` |
| Which Dog Aging Project survey variables measure a concept; how a variable is coded | `dap_codebook_search(query=...)`, then `dap_variable(variable=..., release=...)`; `dap_releases()` lists releases |
| Who is funded to study this | `nih_reporter_search(query=..., fiscal_years=...)` |
| Dog papers on a topic; a specific paper's abstract or full text | `corpus_search(query=..., tier="core"|"extended", year_from=..., open_access_only=...)`, then `corpus_record(key=..., include_fulltext=true)` |
| FDA-approved dog products containing an ingredient; recommended dose, indication | `foi_summary_search(query=...)` |
| Pivotal study, target-animal-safety (dose multiples), PK values, adverse reactions for a product | `foi_structured_search(query=...)` for typed values with quotes; `foi_summary_get(foi_id=..., sections=["target_animal_safety"])` for the section text |
| What data the server holds and how fresh it is | `corpus_info()` |

For a written evidence briefing, use the server's `dossier_briefing` prompt (six sections:
other species, dogs, dosing, target conservation, veterinary use and safety, gaps).

## How to read the output

- **Species labels matter.** A dog application can own a cat, cattle or horse FOI summary.
  `foi_summary_search` results carry `species_flag` (`dog`, `other`, `unknown`) and structured
  records carry `species_class` as the summary states it; do not present a non-dog study as
  dog evidence. For non-dog summaries, `n_dogs` holds that species' animal count.
- **Quotes are verbatim.** Every structured FOI value has a `quote` copied from the FDA text,
  typos and flattened tables included; quote it as evidence rather than paraphrasing numbers.
- **Doses from `dose_translate` are allometric starting points**, not recommendations; say so.
  DrugAge doses given as ppm of diet cannot be translated, and the tool says when that happens.
- **DrugAge has almost no dog rows** (one lifespan experiment, L-deprenyl). Absence of a dog
  row is a gap to report, not evidence of no effect.
- **Corpus hits are BM25 over abstracts**; a "dog trial" flag is vocabulary-based. Confirm the
  design from the abstract before calling something a randomized trial.
- **Live tools can fail** (`dog_ortholog`, `nih_reporter_search`, openFDA inside the dossier).
  They return an `error` block with `retryable`; report the source as unavailable instead of
  guessing.
- **First run downloads the database** (about 90 MB from the Hugging Face Hub); a slow first
  call is normal.

## Answer shape

State the finding, then the identifier, then the caveat. Example: "Selegiline is approved for
dogs (Anipryl, NADA 141-080; foi_id 2554 original approval, 614 supplement). The FOI
target-animal-safety study dosed 0.5X, 1X, 1.5X and 3X (1 to 6 mg/kg/day) for 183 days in 40
dogs; at 6 mg/kg the incidence of stereotypic weaving behaviour was statistically significant
[quote from the record]. DrugAge lists one dog lifespan experiment for L-deprenyl
(PMID 9307048, an elderly-subset survival benefit that a 2025 reanalysis found not significant
after adjusting for age at enrolment, PMID 40816452)." If a tool returned nothing, say which
tool and what was searched.
