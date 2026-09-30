# LLM and agent opportunities in canine longevity research — for an AI developer

Research date: 2026-09-28. Six parallel web-research threads (~200 searches, ~500 page fetches, plus direct API queries to PubMed, NIH RePORTER, Ensembl, ENA, HAGR). Scope: opportunities an AI developer can exploit without running a lab or holding a veterinary/biology credential. Facts below were verified on primary pages or APIs unless marked "unverified".

---

## 1. Executive summary

The field is small, data-rich, and tooling-poor. Roughly 55,000 dogs are enrolled in the Dog Aging Project (DAP), 3,000 in the Golden Retriever Lifetime Study (GRLS), 1,300 in Loyal's pivotal STAY trial, and 50,000 in Darwin's Ark, and tens of millions of dogs sit in veterinary record systems. Yet almost every step that turns those records into research is done by hand, and almost none of the machine-readable infrastructure that exists for human or mouse aging exists for dogs.

The five bottlenecks with the strongest evidence, and the most developer-shaped:

1. **Veterinary medical records are extracted manually everywhere.** DAP has 23,000+ owner-uploaded record PDFs; staff review them by hand and the extracted data is "internal use only". VetCompass finds deaths with keyword lists plus manual review. GRLS names diagnosis adjudication as its main analytic bottleneck. No open model exists that turns a vet note into a coded diagnosis or cause of death.
2. **Dogs are absent from the machine-readable aging knowledge base.** DrugAge has exactly one dog row. GenAge, Open Genes, Aging Atlas, PrimeKG, Hetionet, and LongevityBench contain no dog data. About 2,300 to 2,800 PubMed papers on canine aging have never been packaged into a corpus, knowledge graph, or tool an agent can call.
3. **Trial operations are the rate-limiter for drugs.** Three-quarters of the 72 STAY sites had never run a trial. Loyal still has two pivotal trials to run (LOY-001 and LOY-003). DAP's TRIAD is recruiting to 580 dogs. 12,000 owners applied for 1,300 STAY slots and there is no registry or matching service for canine longevity trials.
4. **Canine genomics lacks the plumbing human genomics takes for granted.** Four reference assemblies in active use with documented liftover pitfalls, no canine variant-effect predictor (the best baseline scores AUC 0.55–0.61), no APIs on OMIA, iDog, or the Dog10K database, and no clean breed-lifespan table.
5. **Owner-generated data has no open standard.** No machine-readable bundle of the validated cognitive, frailty, pain, and quality-of-life instruments exists. No open longitudinal wearable dataset for aging dogs exists, and the largest consumer wearable dataset (Whistle) vanished when the devices were bricked in August 2025.

The three opportunities to start with, in order, are an open veterinary-record extraction stack (Section 3.1), a canine aging knowledge layer exposed as agent tools (3.2), and a no-DUA developer toolkit for DAP and GRLS public artifacts (3.3). They need only public data, they address stated bottlenecks with named users, and each one earns credibility for the partner-dependent opportunities that follow.

---

## 2. How the opportunities were ranked

Each candidate was scored on five questions:

- **Is the data actually obtainable by an unaffiliated developer?** (Open licence, application-only, or effectively closed.)
- **Is there a stated bottleneck with a named user?** (Not a hypothetical.)
- **Is an LLM or agent the right tool?** (Not a job for classical ML alone, and not a job that needs a wet lab.)
- **Does it require domain science to build or validate?** (Lower is better for this brief.)
- **Is there a path to adoption or funding?**

The full access matrix is in Appendix A.

---

## 3. Ranked opportunities

### Tier 1 — build now on public data, clear users

#### 3.1 Open veterinary-record extraction stack (diagnosis, death, cause of death → codes)

**What to build.** An open-weights model plus benchmark that takes free-text veterinary notes (or an owner-uploaded record PDF) and emits structured, coded output: diagnoses and dates mapped to ICD-11 chapters, VeNom, the SNOMED CT veterinary extension (VetSCT), and OMIA/Mondo terms; death events with cause and manner (euthanasia vs unassisted); medications; and a record-quality score implementing DAP's published suitability rubric. Ship three surfaces: a Hugging Face model and eval harness, a CLI/API for cohort studies, and an owner-facing "check my vet record before I upload it" tool.

**Why it accelerates research.** Every cohort study is gated on this step and does it by hand:
- DAP: owners upload records as PDFs through REDCap; staff review manually; extraction is "Limited data extraction. Internal use only" and is not in any curated release. DAP's own suitability study measured 2.4 minutes per record for qualification and 11.5 minutes for full scoring, and its authors recommended "automated processes for the extraction of data from EMRs". A 2026 PLOS ONE study needed two veterinarians abstracting 309 records to show owners under-report dental disease (44% agreement) and dermatologic disease.
- VetCompass (20M+ animals): deaths identified by a keyword list then manual review (Teng 2022).
- GRLS: the cohort profile names "diagnosis adjudication across veterinarians of varying experience" as a bottleneck.
- SAVSNET built a death classifier and PetBERT-ICD for a 52,000-death mortality study but did not release the classifier weights or code.

**Evidence that LLMs work here.** VetLLM (PSB 2024) showed a 7B model fine-tuned on 200 notes beat supervised models trained on 100,000. UC Davis (2025) got 96.9% sensitivity from GPT-4o extracting clinical signs from feline records, with repeat-run agreement higher than between two humans. The Feb 2026 PLOS Digital Health benchmark (13 open models, 246,473 visits, 7,739 SNOMED codes) got weighted F1 76.9 with GatorTron, but generalisation outside Colorado State was untested. A July 2026 Veterinary Pathology scoping review concludes veterinary work is still supervised-heavy while human medicine has moved to prompt-based LLMs.

**Data you can actually get.**
- PetEVAL (Hugging Face, gated by contact form, Apache 2.0): 17,600 real UK first-opinion notes with ICD-11 chapter labels, disease NER, and de-identification NER. The only real, labelled, open corpus.
- SAVSNET free sample: 4,415 de-identified consults (xlsx).
- Encoders with open weights: PetBERT (SAVSNET, OpenRAIL), VetBERT (Melbourne, OpenRAIL), GatorTron-vet (PhysioNet, credentialed).
- Vocabularies: VeNom (free with registration, no modification), VetSCT (needs free UMLS licence; REST API with key), OMIA and Vertebrate Breed Ontology (CC BY 4.0).
- DAP's published suitability rubric (Praczko 2022) and the EOLS instrument for cause-of-death categories.

**Who uses it and how to reach them.**
- DAP: does not accept open-ended collaboration requests but does accept ancillary-study abstracts (ancillarystudies@dogagingproject.org). The pitch is concrete: run the validated extractor over 23,000+ VEMRs and benchmark against the 309-dog manual abstraction already published.
- Darwin's Ark (50,000 dogs, access "managed by request"), GRLS Data Commons (rolling RFP), Loyal (STAY endpoints depend on clinic records at 72 sites), FDA (already funding companion-animal AI/EHR dashboards at Cornell and Minnesota at $200k/yr).

**Constraints.** Big EHR corpora (Banfield/Mars, VCA, CSU) are closed; SAVSNET currently accepts only funded applicants; VetCompass requires a Board application. Build and publish on PetEVAL first, then bring the benchmark to data holders. Note that DAP's DUA forbids redistributing "derived variables or novel methodology" built on DUA data, so keep model development on public corpora.

#### 3.2 Canine geroscience agent toolkit: corpus, cross-species translation tools, and knowledge graph

*(Sharpened after a second pass on 2026-09-28; see Section 7 for the deep-dive and MVP plan.)*

**What to build.** (a) A complete, versioned corpus of the canine aging literature (2,185 Europe PMC records; 643 with open-access full text, abstracts for the rest) with a PaperQA2 index and a gold-standard question set; (b) an MCP server of dog-specific *aging* tools that do not exist anywhere: AnAge/DrugAge dog rows, GenAge and Open Genes aging genes mapped to their dog orthologs with conservation, ITP mouse results joined to dog evidence, FDA Km dose translation (dog Km = 20; HED = dog dose ÷ 1.8), DAP and GRLS codebook search, NIH RePORTER canine geroscience grants; (c) a structured, public-domain dataset extracted from FDA Freedom of Information summaries for dog drugs (pharmacokinetics, target-animal safety findings, doses), which today exist only as PDFs; (d) an "intervention translator" agent workflow that composes all of the above to answer "what do we know about intervention X in dogs, and what would a dog study look like?"; (e) a canine-aging knowledge graph built last, from the outputs of (a)–(d).

**Prior art to build on, not duplicate.** Three open MCP servers already cover adjacent ground: sniff-mcp (canine genomics: 9.67M variants across 188 breeds on CanFam4, OMIA disease layer, ESM2/phyloP pathogenicity, breed life expectancy from McMillan 2024; hosted free API, MIT code, CC BY data), mcp-veterinary-fda (Green Book, openFDA animal adverse events, FOI summary index; MIT, TypeScript), and the longevity-genie servers (Open Genes, SynergyAge, gget, BioThings; MIT, Python/FastMCP, SQLite pulled from Hugging Face). VetClaw provides 51 markdown reasoning skills for veterinary agents but nothing on aging. None of these cover aging biology in dogs, cross-species intervention translation, the literature corpus, or the DAP/GRLS codebooks.

**Why it accelerates research.** Every agentic-science platform is human-centric: FutureHouse/Edison's Robin and Kosmos, Google's AI co-scientist (used by Calico for aging hypotheses in 2026), and Insilico's September 2026 Longevity-LLMs and Longevity Claw agent have no dog data. HAGR's DrugAge has one dog row (L-deprenyl in beagles). Open Genes, Aging Atlas, HALD, PrimeKG, Hetionet, and SPOKE have no Canis nodes. The corpus is small enough to curate completely, and nobody has done it.

**Data and terms.** All open: Europe PMC (abstracts for all records, full-text XML for the OA subset); HAGR (CC BY 3.0, commercial use allowed); Open Genes (CC BY, REST API); OMIA (CC BY 4.0 dumps; co-authorship discussion requested for publications relying on the MySQL dump, avoidable by depending on sniff-mcp); Ensembl REST (verified for dog: MTOR and IGF1 one-to-one orthologs); Mouse Phenome Database (ITP data, REST API); openFDA animal adverse events (JSON API, verified live: 985,705 dog reports); FDA FOI summaries (public domain, PDFs); RePORTER v2 API; Loyal's beagle multi-omic atlas (open access); DAP's 80+ publications and public codebooks. Publisher-restricted full text is the only licensing constraint (about 71% of the corpus is abstract-only).

**Who uses it.** DAP, Loyal, and academic geroscience labs planning canine studies; the Dog Aging Institute; anyone running Claude, Cursor, or another MCP client on a canine question (Edison's platform documents no extensibility, so it is not a target); and Insilico's LongevityBench leaderboard, which has no dog subset and could adopt the question set.

#### 3.3 No-DUA developer toolkit for DAP and GRLS public artifacts

**What to build.**
- A codebook and instrument knowledge layer: parse DAP's 2020–2025 codebook CSVs and annotated survey PDFs into a schema (variable → question text → gating logic → value labels → release-to-release diffs) and expose it as an MCP tool so agents write correct analysis code against Terra files. Do the same for GRLS's 11 data domains.
- A "known issues" cleaning library encoding every documented DAP data problem (diagnosis years outside 1980–2025 or before birth, blank condition details, CSLB logical inconsistencies, AFUS NA/FALSE errors, string truncation in RData/SPSS exports) as reproducible checks. DAP explicitly leaves these fixes to users.
- Replication agents over the public Publication-Resources repo, which already contains DUA-free copies of the 2024 Dog Overview, HLES dog/owner tables, survival CSVs, and 14 R scripts for the 2026 longevity-factors paper, plus microbiome taxonomy/KEGG tables and metabolomics code.
- A low-pass sequencing QC/imputation service over DAP's 8,228 public raw-read runs (SRA PRJNA800779) using the Dog10K phased panel (CC BY 4.0).
- A monitoring agent over RePORTER, Europe PMC, DAP's blog JSON, and GitHub commits for release timing, TRIAD milestones, and new codebooks.

**Why it accelerates research.** DAP has fulfilled 300+ data-access requests and 200+ researchers use the data, but there is no client library, the Broad ingest pipeline has been dormant since September 2022, and DAP warns users to match codebook version to release. DAP's IT capacity is one data scientist and one software engineer at about 25% time on the biospecimen workflow. GRLS's Data Commons has 51M data points and no API.

**Constraints.** Anything built on DUA-gated curated data cannot be redistributed (the DUA covers "derived variables or indices or novel methodology"). Everything above uses only public artifacts, so it can be open source. Commercial use of DAP data needs a separately negotiated track.

### Tier 2 — strong, but needs a partner or field operations

#### 3.4 Trial-operations agents for trial-naive clinics, owners, and sponsors

**What to build.**
- "Coordinator in a box" for general-practice clinics: protocol → per-visit checklists, source-document capture from the practice system, deviation logging, VICH-GCP training, monitor-ready audit trails.
- Owner retention and patient-reported-outcome engine: adherence nudges, survey delivery and QC, plain-language consent generation aligned to FDA's 2023 draft consent guidance (an audit found trial materials exceed 6th-grade reading level).
- Eligibility pre-screening on free-text records (IDEXX BioAnalytics already scans practice systems for sponsors) and a canine longevity trial registry with matching. The AVMA registry has 500+ listings and no API; 28% of vets never learn about trials.
- Regulatory dossier support for the FDA CVM conditional-approval lifecycle: the LOY-001 efficacy section alone was 2,300+ pages; conditional approval requires annual "active progress" renewal reports for up to four years and adverse-event reporting for the CA1 label.

**Why.** Loyal: 72 STAY sites, about three-quarters trial-naive; LOY-002 awaiting only the manufacturing section (anticipated 2027); LOY-001 pivotal (~1,000 large dogs) and LOY-003 pivotal still to run; $100M Series C in Feb 2026. DAP TRIAD: $7M NIA grant, expanding from ~170 to 580 dogs across 20+ sites, still recruiting as of 2026. Rejuvenate Bio (Merck Animal Health partner), Genflow, Epiterna, and Odacova are behind them. Leap Years lost 19–26% of dogs in six months.

**Who pays.** Loyal is the obvious partner (vets@loyal.com; a continuing-education program "reaching thousands"). Others: IDEXX BioAnalytics Veterinary Clinical Trials, Ethos Discovery, veterinary CROs, university clinical-trial offices, and Petfolk/Modern Animal/Thrive clinic groups.

**Constraint.** This is B2B software with a sales cycle; nothing here can be validated without a sponsor.

#### 3.5 Canine genomics harmonisation and annotation services

**What to build.**
- A coordinate harmonisation agent/API that lifts any dog variant between CanFam3.1, canFam4 (UU_Cfam_GSD_1.0), canFam6 (Dog10K Boxer Tasha), and ROS_Cfam_1.0, applies the documented chr27/chr32 orientation fix, validates against CanineHD/Axiom manifests, and re-annotates against Ensembl 116 and the Dog10K GTF.
- A canine variant-effect benchmark and model: OMIA's 594 dog causal variants as positives, Dog10K allele frequencies and Zoonomia phyloP constraint as features, versus the only baseline (running human tools via a "mock human variant" trick: AUC 0.55–0.61).
- Dog-native gene sets and pathways (Ensembl orthology + DoGA promoter atlas + Hoeppner's improved annotation, which found ~3,000 human protein-coding loci expressed in dog but missing from Ensembl).
- A methylation harmoniser and open clock benchmark with breed-phylogeny correction (Armero 2024 showed clocks confounded by population stratification). Public inputs: GEO GSE223748 (742 arrays, 93 breeds), GSE146920, SRP065666.
- A unified variant atlas API re-implementing CanVAS (15,451 dogs imputed to 9.7M variants; no public endpoint) from Dog10K, Darwin's Ark Dryad deposits, GRLS Axiom genotypes, NHGRI's 722-canid VCF, and Mars/Broad CC0 genomes.

**Why.** DAP just produced "the first GWAS catalog in dogs" (7,627 dogs), Darwin's Ark released 3,277 imputed genomes, and every group works on a different assembly with no shared tooling. OMIA ships CanFam3.1-only coordinates. OMIA, iDog, and the Dog10K database have no APIs.

**Caveat.** More classical bioinformatics than LLM work, though agents wrapping these services are natural. Validation needs a genomics collaborator.

#### 3.6 Owner-side instruments, wearables, and the first open aging wearable dataset

**What to build.**
- An open, machine-readable library of validated owner instruments (CCDR/CSLB 13 items, CADES, CCAS, HHHHHMM, the Canine Brief Pain Inventory — free with citation and unchanged wording — and the AKC CHF's 2026 cognitive-dysfunction guidelines) with scoring code, a FHIR-style schema, and export in DAP codebook format so records can be donated.
- An LLM-guided survey and record companion that reduces known owner misreporting (dental 44% agreement, dermatologic under-reporting) by prompting owners against their uploaded records.
- A wearable-agnostic ingestion SDK ("Open mHealth for dogs"): FitBark is the only official API (with a research program: devices under $70, CSV export); PetPace offers a research API; Tractive and Fi have only reverse-engineered clients; Whistle's data disappeared with the devices.
- The first open longitudinal wearable dataset for senior dogs, labelled with the instruments above. The only open dog wearable dataset today is 45 dogs across 7 behaviours.

**Why.** DAP fields a 200+ question baseline survey and annual follow-ups from 30,000+ dogs; Darwin's Ark deploys new surveys on request; TRIAD and Leap Years already use activity collars as endpoints. Frailty and quality of life are primary or secondary endpoints in STAY and TRIAD, and no digital endpoint has been validated against them.

**Caveat.** The dataset piece needs owner recruitment, consent, and device logistics. Impetus Grants' "AI-Enabling Datasets" round (up to $500k, three-week decisions) is the fit if framed for human relevance; AKC CHF's new Aging program and Morris's pilot mechanism are the canine-specific fits.

### Tier 3 — smaller, fast, useful

#### 3.7 Open breed lifespan and body-size table
No clean machine-readable table exists. Assemble from Teng 2022 (18 breeds, CC BY, R code on GitHub), McMillan 2024 Supplementary Table S3 (155 breeds; the supplement is open though raw records are not), AnAge, the AKC scrape, Agria and Nationwide breed pages, and cross-walk to the Vertebrate Breed Ontology. A weekend project that every longevity model would use as a baseline.

#### 3.8 Evaluation harness for veterinary and consumer pet-health AI
Consumer chatbots score 19–38% on primary diagnosis; a March 2026 audit of 71 commercial vet-AI products found 6.4% mean transparency and 63% disclosing no validity metrics. The RCVS 23-principle framework (June 2026) and ACVIM 12-item checklist (Jan 2026) now define what to disclose. LongevityBench (Cell, Sep 2026) has no dog subset. Build a canine geroscience benchmark (owner-phrased cases → triage and differentials; aging-specific reasoning with DAP/TRIAD/Loyal ground truth) and a model-card generator. Buyers: Digitail, Lupa, Vetster, AskVet, and the AVMA/ACVIM bodies.

#### 3.9 Grant, trial, and literature monitoring feed
RePORTER API, Europe PMC, Morris and AKC CHF grant directories, the AVMA registry, and DAP's blog. Low effort, high community value, and a natural on-ramp to the people in 3.1–3.4.

#### 3.10 Scribe-to-registry layer
AI scribes (ScribbleVet at UC Davis and Florida, CoVet, Talkatoo, Digitail, PetDesk) now produce uncoded SOAP text in thousands of clinics, and none feed research. A post-scribe coding and consent layer emitting VeNom/ICD-11 records to a registry does not exist. Requires vendor partnership; sequence after 3.1.

---

## 4. What is not a good opportunity for an AI developer

- **Hypothesis-generation agents (Kosmos-style) for canine aging.** Every validated result from these platforms required a wet lab. Without one, the output is unfalsifiable.
- **Products built on DAP curated data.** The DUA is non-commercial, forbids redistribution of derived variables and methods, and requires a separate negotiated track for commercial use.
- **Waiting for big EHR data.** Banfield/Mars, VCA, Colorado State, and the pet insurers (Trupanion, Nationwide, Fetch) are effectively closed to outsiders. SAVSNET currently accepts only funded applicants. Plan around PetEVAL, DAP, GRLS, and Darwin's Ark.
- **Another consumer pet chatbot.** Crowded (AskVet, Petriage, Digitail, Vetster, Pluto Pets), poorly validated, and none contribute data to research.
- **Commercial epigenetic clocks.** Embark's Dog Age Test reports calendar age, not biological age; no vendor releases raw methylation data; and clocks are confounded by breed phylogeny.

---

## 5. Where to plug in

**Events (imminent).**
- Animal Longevity Summit (ALOS), Toronto, 1–2 Oct 2026: tracks on data/monitoring, biomarkers and clocks, founders and capital; DAP, Dog Aging Institute, and Ontario Veterinary College are scientific partners.
- ARDD 2026 Pet and Animal Longevity Forum, 3 Oct 2026 (Purina, Promislow, AniVC).
- Cornell Animal Health Hackathon, Feb 2027 (sponsors: Purina, Zoetis, IDEXX, Boehringer Ingelheim).

**Funders with a plausible fit.**
- Impetus Grants (Norn Group): up to $500k, three-week decisions, current "AI-Enabling Datasets" round.
- AKC Canine Health Foundation Aging program (launched Apr 2026; small grants).
- Morris Animal Foundation pilot mechanism (canine pre-proposals due 1 Apr annually) and GRLS Data Commons RFP.
- FDA CVM U01 precedent for companion-animal AI/EHR tooling ($200k/yr at Cornell and Minnesota).
- Dog Aging Institute (501(c)(3); Kaeberlein, Creevy, Promislow as officers) and the 2022 tech-philanthropist group (Armstrong, Attia, Ferriss, McCaleb, Rose) who pledged $2.5M to DAP.

**Partners.**
- DAP via a specific ancillary-study abstract; Darwin's Ark via darwinsark.org/collaborate (they will deploy new surveys on request); GRLS via datacommons@morrisanimalfoundation.org; Loyal via vets@loyal.com; SAVSNET via its data-access portal once you have funding.

**Governance to design for.** The RCVS Veterinary AI Transparency Alliance principles (June 2026), the ACVIM validation checklist (Jan 2026), FDA's draft client-consent guidance (Sep 2023), and DAP's DUA.

---

## 6. Suggested sequencing

1. **Weeks 1–4:** Ship 3.7 (breed table) and 3.9 (monitoring feed). Register for PetEVAL, VeNom, UMLS/VetSCT. Start the corpus curation for 3.2.
2. **Months 1–3:** Build and publish the extraction benchmark and first model (3.1) on PetEVAL and the SAVSNET sample. Publish the DAP codebook MCP and known-issues library (3.3).
3. **Months 3–6:** Release the canine-aging MCP servers and PaperQA2 index (3.2). Submit an ancillary-study abstract to DAP proposing extraction over the VEMR archive, benchmarked against the 309-dog manual abstraction. Approach Loyal and IDEXX BioAnalytics with the eligibility-screening and site-tooling concept (3.4).
4. **Months 6–12:** Depending on partner response, either the trial-ops product (3.4) or the genomics services (3.5); apply to Impetus for the wearable dataset (3.6).

---

## 7. Deep-dive on 3.2: the canine geroscience agent toolkit

### 7.1 Why this one fits an AI developer

- **It is retrieval, extraction, tool-serving, and evaluation work.** The only biology-adjacent step is calling Ensembl for orthologs, which is a REST call.
- **No gatekeeper.** Every input is public infrastructure with stable licences (Europe PMC, HAGR, Open Genes, OMIA, Ensembl, openFDA, RePORTER, MPD). No data-use agreement, no partner, no approval.
- **The corpus is finite.** 2,185 records is small enough to process every paper, which is not true for human aging. "Complete coverage" is a real differentiator.
- **It composes with what exists.** Three MCP servers already cover canine genomics, FDA drug data, and human aging genes. The aging-specific dog layer is the missing piece, and it makes those servers more useful rather than competing with them.
- **Cheap.** Embedding 2,185 abstracts and 643 full texts and running LLM extraction over the OA subset costs tens of dollars, not thousands.

### 7.2 The honest risks

- **Demand risk is the flip side of independence.** Not targeting a third party means no guaranteed user. The canine geroscience community is a few hundred people. Mitigation: design around one concrete, measurable workflow (the intervention translator) rather than a generic knowledge graph, and publish a benchmark that others can adopt.
- **A dog-paper RAG alone is not a moat.** Edison's Literature agent indexes 175M papers, including every dog paper; a general LLM can already answer easy questions. The value is in the structured, dog-specific tools and the cross-species joins, not in retrieval over papers. Build the tools first and the RAG second.
- **Extraction quality without a domain reviewer.** LLM-extracted relations will contain errors. Mitigation: a two-tier design. Tier 1 is curated ground truth (OMIA, HAGR, Open Genes, DAP codebooks, FOI summaries) served verbatim. Tier 2 is literature-derived claims, always carried with citation, quote span, and confidence, never merged into Tier 1.
- **Only 29% of the corpus has open full text.** Abstract-only records still support search and citation, but extraction of methods, doses, and outcomes is limited to the OA subset. Unpaywall may lift this a little.

### 7.3 Components, ranked by value per unit of effort

| # | Component | Effort | Novelty | Notes |
|---|---|---|---|---|
| 1 | `canine-aging-corpus`: versioned dataset on Hugging Face (Europe PMC metadata + OA full-text XML), refresh script, PaperQA2 index | Low | Medium | Seed the question set from the 346 reviews. |
| 2 | `dog-geroscience-mcp`: FastMCP server, SQLite pulled from HF Hub (the opengenes-mcp pattern). Tools: `anage_dog`, `drugage_dog`, `aging_gene_dog_ortholog` (GenAge/Open Genes → Ensembl dog ortholog, % identity), `itp_results` (MPD), `dose_translate` (FDA Km), `dap_codebook_search`, `dap_variable`, `grls_domains`, `reporter_canine_aging_grants`, `corpus_search` | Low–Medium | High | Nothing like it exists. Each tool is a day or two. |
| 3 | Structured FOI summaries for dog drugs: scrape Animal Drugs @ FDA FOI PDFs, LLM-extract indication, dose, PK parameters, target-animal-safety findings, adverse-event tables → JSON | Medium | High | A new public-domain dataset; mcp-veterinary-fda gives the index, the extraction is the work. |
| 4 | Intervention translator agent + eval set: input a compound or target; output a dog evidence dossier (target conservation, dog studies from the corpus, dog PK/safety from FOI and openFDA, translated dose, gaps) | Medium | High | Evaluate on ITP positives and negatives (rapamycin, acarbose, 17α-estradiol, canagliflozin, metformin, resveratrol). |
| 5 | Canine geroscience question set (50–100 questions with gold citations) | Low | High | Offer to LongevityBench as a dog subset. |
| 6 | Knowledge graph and browsable site | High | Medium | Build from 1–4; do not start here. |

### 7.4 MVP in three phases

**Phase 1 (2–4 weeks).** Components 1, 2, and 5. Publish on GitHub and PyPI, register in the MCP registry, and post a short write-up showing five real questions answered with citations versus a baseline LLM.

**Phase 2 (1–2 months).** Components 3 and 4. The FOI dataset is the most reusable artifact; the translator is the demo that a scientist planning a dog study would actually run.

**Phase 3 (after usage signal).** Component 6, and submit the question set to longevitybenchmarks.org. Present at ARDD's Pet and Animal Longevity Forum or ALOS in 2027.

### 7.5 Design decisions to make early

- Assembly: standardise on CanFam4 (UU_Cfam_GSD_1.0) to match sniff-mcp, Dog10K, and DAP; note Ensembl's default is ROS_Cfam_1.0 and map at the gene level, not the coordinate level, to avoid liftover.
- Identifiers: Ensembl gene IDs for dog, NCBI Gene for human (matches Open Genes), OMIA IDs for phenes, Mondo for diseases, VBO for breeds, PMCID/PMID for evidence.
- Provenance on every row: source, version, retrieval date, and for LLM-extracted claims the quote span and model.
- Licence: MIT code; CC BY 4.0 for derived data, with HAGR's CC BY 3.0 and OMIA's citation request honoured in a NOTICE file.

---

## 8. Build status (2026-09-29)

What exists in this folder now, against the plan in Section 7:

| Component | Status |
|---|---|
| 7.3 #1 corpus (`corpus/`) | Done. 3,565 Europe PMC records; full text for 1,140 of 1,347 PMCIDs (207 are publisher-restricted from XML). Europe PMC's full-text endpoint failed for hours on 28 Sep; NCBI E-utilities added as a batched second source and now preferred. |
| 7.3 #2 MCP server (`mcp/`) | Done. 17 tools + 1 prompt: HAGR (AnAge/DrugAge/GenAge), Ensembl dog orthologs (cached), FDA Km dose translation, DAP codebooks (9 releases), NIH RePORTER, corpus search/records, FOI summary search/get, FOI structured search, and the deterministic `intervention_dossier`. 23 offline tests; smoke-tested live and over stdio. |
| 7.3 #3 FOI summaries dataset (`foi/`) | Done for dogs: 1,726 summaries indexed, 497 dog-product PDFs parsed (97% with template sections, species-flagged). Structured, quote-validated extraction of all 497 summaries by 35 model subagents (1,026 PK values, 193 target-animal-safety studies, 414 effectiveness studies, 918 adverse-reaction rows; 4,510 quotes, 0 errors; 79 warnings for no-study generics and supplements). |
| 7.3 #4 intervention translator | Done as `intervention_dossier` + `dossier_briefing` (synonym-aware; feline summaries under dog applications filtered out); `scripts/dossier_eval.py` reports coverage over 14 ITP compounds and two veterinary comparators. |
| 7.3 #5 question set (`questions/`) | Done: v0.1 = 133 questions, 10 categories, 97 sources, every quote validator-checked, each item then reviewed by an independent LLM pass (124 pass, 9 fix, 1 drop); BM25 recall@5 = 0.985. No domain-expert review yet. |
| 7.3 #6 knowledge graph | Not started, by design (build after usage signal). |

Lessons that changed the plan: Europe PMC is not a reliable sole source (use NCBI efetch, batched); DrugAge's compound spellings need a synonym layer before any cross-source join works; the FOI corpus is text-extractable (no scanned PDFs among dog products), so a template parser gets most of the value before any model is involved.

---

## Appendix A — Data access matrix (as of 2026-09-28)

| Resource | What | Access | Licence / terms |
|---|---|---|---|
| PetEVAL | 17,600 real UK vet notes, ICD-11 + NER labels | Hugging Face, gated form | Apache 2.0 |
| SAVSNET sample | 4,415 de-identified consults | Free download | Learning use |
| PetBERT / VetBERT | Vet-note encoders | Hugging Face | OpenRAIL |
| GatorTron-vet | Fine-tuned SNOMED coder weights | PhysioNet, credentialed | DUA |
| DAP codebooks, instruments, known issues | 2020–2025 releases | GitHub (dogagingproject/dataRelease) | No licence file |
| DAP Publication-Resources | Replication data incl. 2024 Dog Overview, HLES, survival CSVs | GitHub, "anyone can fork" | No licence file |
| DAP curated data | 50,188 dogs (2024 release); 2025 release listed | Terra after REDCap application + DUA | Non-commercial; no redistribution of derived variables/methods |
| DAP raw low-pass reads | 8,228 runs | SRA PRJNA800779 | Public |
| DAP precision microbiome | 922 dogs shotgun metagenomics | SRA PRJNA1377461 | Public |
| GRLS genotypes | 3,224 dogs, 1.1M Axiom markers | AWS Open Data s3://mafgrlsgenome | CC-BY-SA |
| GRLS phenotypes | 51M data points, 11 domains | Data Commons application (~2 days for academics; industry by application) | Terms on application |
| Darwin's Ark | 2,155 + 3,277 genotyped dogs; surveys | Dryad (open); full cohort by request | CC0 (Dryad) |
| Dog10K | 1,987 genomes, 52.9M variants, phased panel | Open HTTP + Zenodo | CC BY 4.0 |
| NHGRI dog genome releases | 722-canid VCF, Parker SNPs | Open | Unstated |
| Mars/Broad biobank genomes | 2,860 runs ~30x | SRA PRJNA1022042 | CC0 |
| GEO methylation | GSE223748 (742 arrays), GSE146920 | GEO | Public |
| OMIA | 1,019 dog traits, 594 causal variants | SQL/XML dumps, no API | CC BY 4.0 (citation/co-authorship requested for dumps) |
| HAGR (AnAge/DrugAge/GenAge) | 1 dog DrugAge row; AnAge species entry | CSV | CC BY 3.0, commercial OK |
| Open Genes | 2,402 genes (no dog) | REST API | CC BY / MPL-2.0 |
| Ensembl, UCSC, EVA, ENA/NCBI | Dog assemblies, orthologs, chains, variants | REST APIs | Open |
| VeNom | Vet diagnosis vocabulary | Registration, FTP | Free; no modification; attribution |
| VetSCT | 30k+ vet SNOMED concepts | UMLS licence; REST API with key | SNOMED derivative |
| openFDA animal & veterinary | Adverse events 1987– | JSON API + bulk | Public domain |
| FDA FOI summaries / Green Book | Approved animal drug summaries | PDFs in JS app, no API | Public domain |
| NIH RePORTER v2 | Grants | API | Open |
| VetCompass | 20M+ animals | Board application; open study extracts for learning only | Restricted |
| SAVSNET full | 9.2M consults | Portal, fee, funded applicants only | Restricted |
| Banfield / VCA / CSU notes / insurers | Largest EHR and claims corpora | Effectively closed | Closed |
| Embark / Wisdom Panel | 3M+ / 4.5M+ genotyped dogs | Partnership only | Closed |
| FitBark | Wearable API + research program | Register at fitbark.com/dev | API terms Sep 2025 |
| PetPace | Research API | Contact | Unpublished pricing |

## Appendix B — Key sources

Dog Aging Project: dogagingproject.org/data-access; data.dogagingproject.org; github.com/dogagingproject/dataRelease; github.com/dogagingproject/Dog-Aging-Project-Publication-Resources; github.com/DataBiosphere/dog-aging-ingest; Praczko et al. 2022 Front Vet Sci (PMC9389294); Schmid et al. 2026 PLOS ONE 10.1371/journal.pone.0342427; Prescott et al. 2025 GeroScience (PMC12397037); NIH RePORTER R01AG090843.

Vet NLP: PetEVAL (huggingface.co/datasets/SAVSNET/PetEVAL; ACL BioNLP 2025); PetBERT (Sci Rep 2023); VetBERT (huggingface.co/havocy28/VetBERT); VetLLM (PSB 2024); Boguslav/Kiehl 2026 PLOS Digital Health 10.1371/journal.pdig.0001147; Wulcan 2025 (github.com/ucdavis/llm_vet_records); Farrell 2024 Sci Rep 10.1038/s41598-024-77385-8; Teng 2022 Sci Rep 10.1038/s41598-022-10341-6; Chang & Chu 2026 Vet Pathol 10.1177/03009858261461761.

Industry/trials: loyal.com/posts/stay-finishes-enrollment; loyal.com/posts/loy-002-tas; loyal.com/posts/loy-003-rxe; labkey.com/loyal-for-dogs-reaches-fda-milestone; GRLS cohort profile (PMC9182714); Frontiers Vet Sci 2024 trial-recruitment audit 10.3389/fvets.2024.1418747; fda.gov conditional-approval explainer; veterinaryclinicaltrials.org; animallongevitysummit.com; agingpharma.org.

Knowledge/agents: genomics.senescence.info (DrugAge dataset.zip); open-genes.com; github.com/Future-House/paper-qa; github.com/longevity-genie/holy-bio-mcp and github.com/longevity-genie/opengenes-mcp; github.com/Insilico-org/longeclaw; Insilico Longevity-LLMs release 2026-09-17; rest.ensembl.org; api.fda.gov/animalandveterinary/event.json (verified live 2026-09-28); Europe PMC REST counts (2,185 total; 643 OPEN_ACCESS:y) on 2026-09-28; docs.edisonscientific.com.

Prior-art MCP servers (checked 2026-09-28): github.com/Sniffscore/sniff-mcp and glama.ai/mcp/connectors/world.sniff/sniff-mcp (canine genomics, OMIA, breed frequencies, CanVAS-derived, hosted at api.sniff.world); github.com/pipeworx-io/mcp-veterinary-fda (Green Book, openFDA animal events, FOI summary index); github.com/OpenVet-Projects/VetClaw (51 markdown veterinary skills, no aging content); omia.org/download (SQL/XML dumps, citation and co-authorship request).

Genomics: kiddlabshare.med.umich.edu/dog10K; zenodo.org/record/8084059; registry.opendata.aws/maf-genome; datadryad.org 10.5061/dryad.83bk3jb4r; omia.org; Horvath 2022 PNAS 10.1073/pnas.2120887119; Armero 2024 Aging (PMC11272130); Hu & Xie 2025 Open Vet J 10.5455/ovj.2025.v15.i10.35; Kidd 2025 Mamm Genome 10.1007/s00335-025-10178-0.

Owner data/funding: fitbark.com/research; petpace.com/researchers; eurekalert.org/news-releases/1135096 (Darwin's Ark); norn.group/impetus-grants; akcchf.org Aging program press release 2026-04-21; morrisanimalfoundation.org/data-commons-faqs; Frontiers Vet Sci 2026 vet-AI transparency audit 10.3389/fvets.2026.1761038.
