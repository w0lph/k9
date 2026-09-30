---
pretty_name: Canine Geroscience Questions
language:
- en
license: cc-by-4.0
tags:
- biology
- veterinary
- dogs
- aging
- longevity
- geroscience
- evaluation
- grounded-qa
task_categories:
- question-answering
size_categories:
- n<1K
configs:
- config_name: v0_1
  data_files: canine_geroscience_v0_1.jsonl
  default: true
- config_name: v0
  data_files: canine_geroscience_v0.jsonl
---

# Canine Geroscience Questions

A question set for evaluating LLMs and agents on canine aging research. Every question has a
concise gold answer and at least one piece of evidence: a record key in the
[Canine Aging Corpus](https://huggingface.co/datasets/{owner}/canine-aging-corpus) plus a
**verbatim quote** that a validator checks against that record's abstract or full text.
No quote, no question.

| | |
|---|---|
| Questions (v0.1, `status: reviewed`) | 133 across 10 categories, 12 to 15 per category |
| Categories | lifespan_epidemiology, body_size_genetics, interventions, biomarkers_clocks, cognition, frailty_hrql, dap_methods, translational_model, immunity_microbiome, disease_mortality |
| Difficulty | 1 = stated in an abstract; 2 = needs a results section or two facts; 3 = synthesis or a non-obvious detail |
| Answer types | numeric, short_text, list, categorical, boolean |
| Evidence | 97 distinct corpus records; at most three questions per record |
| Retrieval baseline | BM25 over the corpus: recall@1 = 0.918, recall@5 = 0.985 |

## Record shape

```json
{"id": "cgq-0001", "category": "lifespan_epidemiology", "difficulty": 1, "answer_type": "numeric",
 "question": "In the 2015 life table constructed from 299,555 dogs insured in Japan ..., what was the overall life expectancy of dogs?",
 "answer": "13.7 years.",
 "evidence": [{"key": "MED:25896026", "pmid": "25896026", "doi": "...", "title": "...", "year": 2015,
               "location": "abstract", "quote": "... The overall life expectancy of dogs was 13.7 years."}],
 "tags": ["life_table", "life_expectancy", "insurance", "Japan"], "status": "reviewed",
 "created": {"by": "claude-fable-5-1", "date": "2026-09-29"}}
```

`schema.json` is the JSON Schema. Items changed by the review carry a `review` field with the
issue and the keys that changed; items whose source has an internal inconsistency say so in
`notes`.

## How it was made

One drafting model agent per category worked from the corpus with the `cgq` helpers
(BM25 `find`, `show`, `quote`) under fixed authoring rules (facts a careful reader could
verify; answers must follow from the quotes; questions stand alone; cover many sources).
Every draft had to pass `cgq validate`, which normalises whitespace, Unicode and inline
markup and then requires each quote to be a contiguous span of the record's text.

A second, independent model pass reviewed every v0 question against its quotes with a
pass / fix / drop rubric: 124 pass, 9 fix, 1 drop (a near-duplicate), giving v0.1.
**No domain expert has reviewed the set**; `reviewed` means machine-verified grounding
plus one independent model review.

## Known limitations

- Most questions are grounded at abstract level because only the open-access subset of the
  corpus has full text; some primary papers (the 2017 and 2023 rapamycin trials, the TRIAD
  design paper) are abstract-only.
- Two same-paper pairs leak each other's answer if shown together (cgq-0038 and cgq-0031;
  cgq-0131 and cgq-0121).
- Answers that mix a number with a category are labelled `numeric` where `short_text` would
  also fit.

## Using it

Score exact or normalised match on `answer` for numeric and categorical items, and use the
quotes as the rubric for free-text grading. `cgq evaluate` in the
[repository](https://github.com/w0lph/k9/tree/main/questions) reports retrieval recall@k for
any index over the corpus.

## Licence

Questions and answers: CC BY 4.0. Quotes remain under the licence of their source article
and are limited to short spans for evaluation purposes.
