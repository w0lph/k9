# canine-geroscience-questions

A question set for evaluating LLMs and agents on canine aging research. Every question has
a concise gold answer and at least one piece of evidence: a corpus record key plus a
**verbatim quote** that the validator checks against that record's abstract or full text.
No quote, no question.

Why this shape: there is no domain reviewer on this project. Verbatim grounding against a
fixed, versioned corpus (`../corpus`) is the quality gate that makes the set trustworthy,
and it makes each question machine-checkable if the corpus is rebuilt.

## Layout

| Path | Contents |
|---|---|
| `schema.json` | JSON Schema for a question. |
| `data/drafts/<category>.jsonl` | Per-category drafts (validated before merge). |
| `data/canine_geroscience_v0.jsonl` | The merged, numbered set. |
| `src/cgq/` | Tooling: `find`, `show`, `quote`, `validate`, `merge`, `evaluate`. |

Categories: lifespan_epidemiology, body_size_genetics, interventions, biomarkers_clocks,
cognition, frailty_hrql, dap_methods, translational_model, immunity_microbiome,
disease_mortality.

## Authoring workflow

```bash
uv sync
uv run cgq find "rapamycin dogs trial" --abstract          # discover sources (BM25 over the corpus)
uv run cgq show MED:28374166 --fulltext                    # read a record (Markdown full text if open access)
uv run cgq quote MED:28374166 "echocardiographic"          # sentences safe to cite verbatim
uv run cgq validate data/drafts/interventions.jsonl        # must be clean before merge
uv run cgq merge data/drafts/*.jsonl -o data/canine_geroscience_v0.jsonl
uv run cgq evaluate data/canine_geroscience_v0.jsonl       # BM25 recall@k of the evidence record
```

Authoring rules:

- Ask about facts a careful reader could verify: numbers, definitions, findings, designs,
  named instruments. Not author names, journal names, or dates of publication.
- The answer must follow from the quote(s). Prefer one quote per evidence item; use two
  evidence items when a fact spans two papers (e.g. a claim and its replication).
- Mix difficulty: 1 = stated in an abstract; 2 = needs a results section or two facts;
  3 = synthesis or a non-obvious detail.
- Cover many sources; at most three questions per source record.
- Write questions that stand alone (name the study or population when it matters:
  "In the 2017 randomized trial of short-term rapamycin in middle-aged dogs, ...").

## v0 (2026-09-28)

`data/canine_geroscience_v0.jsonl`: 134 questions, all validator-clean.

| | |
|---|---|
| Categories | 10, with 12–15 questions each |
| Difficulty | 43 easy / 60 medium / 31 hard |
| Answer types | numeric 58, short_text 34, list 30, categorical 10, boolean 2 |
| Evidence | 161 quotes from 97 distinct corpus records; 121 abstract-level, 40 full-text |
| Retrieval baseline | BM25 recall@1 = 0.918, recall@5 = 0.985 |

How it was made: one drafting agent per category worked from the corpus with the `cgq` helpers
under the rules above, and had to pass `cgq validate` before handing back. The merge step
strips inline markup from quotes (the validator ignores markup on both sides, so they still
match). No domain expert has reviewed the set; every item is `status: validated`, meaning
machine-verified grounding, not expert review.

Known limitations of v0:

- Only the open-access subset has full text, so most questions are grounded at abstract
  level; several important primary papers (the 2017 and 2023 rapamycin trials, the TRIAD
  design paper, the 2022 dog/human methylation clocks) are abstract-only in this corpus
  build. Two TRIAD dosing questions are therefore grounded in a 2025 review's full text
  rather than the design paper, which is why BM25 misses them (it ranks the design paper first).
- Some classic sources are absent from the corpus altogether (e.g. the 2007 IGF1 small-size
  allele paper, the original CCDR development paper), so they cannot be asked about.
- A few sources are used by more than one category (up to 7 evidence items from one Dog
  Aging Project metabolomics paper).
- Where a source contains an internal inconsistency (e.g. the Portugal life-expectancy paper's
  abstract vs table, a systematic review whose study counts do not sum), the gold answer follows
  the abstract and the `notes` field flags it.

## v0.1 (2026-09-29): reviewed

`data/canine_geroscience_v0_1.jsonl`: 133 questions, `status: reviewed`.

A second, independent LLM pass reviewed every v0 question against its quote(s) with a
pass / fix / drop rubric (`data/review/batch_0*.jsonl`, applied with `cgq review-apply
--min-confidence medium`). Result: 124 pass, 9 fix, 1 drop.

- Dropped: cgq-0016 (near-duplicate of cgq-0008 from the same paper).
- Fixed: four question stems that asserted a detail the paper does not state or that was
  ambiguous (cgq-0012 abstract-vs-table discrepancy, cgq-0038 authors' conclusion vs a
  results line, cgq-0079 "which two variables" when the abstract names three, cgq-0081
  "teaching hospital", cgq-0134 "Kennel Club registered"); two answers trimmed to what the
  quote supports (cgq-0054, cgq-0075); two answer_type labels (cgq-0056, cgq-0088).
- Fixed items carry a `review` field with the issue and the changed keys.

Reviewer observations kept for users of the set: two same-paper pairs leak each other's
answer if shown together (cgq-0038 → cgq-0031; cgq-0131 → cgq-0121); several answers that mix
a number with a category are labelled `numeric` where `short_text` would also fit. This is
still not a domain-expert review.

## Retrieval baseline

`cgq evaluate` reports recall@{1,5,10,20}: whether BM25 over the corpus (question text,
OR of content words) ranks any of the question's evidence records in the top k. This is a
sanity check on both the questions and the index, and a floor for any retrieval-augmented
agent to beat.

## Licence

Questions and answers: CC BY 4.0. Quotes remain under the licence of their source article
and are limited to short spans for evaluation purposes.
