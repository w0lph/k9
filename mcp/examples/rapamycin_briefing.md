# Evidence briefing: rapamycin (sirolimus) in dogs

Written from `intervention_dossier(compound="rapamycin", target_gene="MTOR")` on 2026-09-29
(`rapamycin_dossier.json` beside this file), following the server's `dossier_briefing` prompt.
Nothing below goes beyond what the tools returned; identifiers are inline.

## 1. What is known in other species

DrugAge lists 37 lifespan experiments for rapamycin/sirolimus: 24 in mice, 8 in *C. elegans*,
5 in *Drosophila*. Sixteen mouse rows carry the NIA Interventions Testing Program flag, all in
genetically heterogeneous UM-HET3 mice:

| Regimen (diet) | Started at | Sex | Median lifespan change | Max lifespan change | PubMed |
|---|---|---|---|---|---|
| 14 ppm | 20 months | female / male | +13% / +9% (both significant) | +14% / +9% | 19587680 |
| 14 ppm | 9 months | female / male | +18% / +10% (significant) | +13% / +16% | 20974732 |
| 4.7 / 14 / 42 ppm | 9 months | female | +16% / +21% / +26% (significant) | +5% / +11% / +11% | 24341993 |
| 4.7 / 14 / 42 ppm | 9 months | male | +3% (n.s.) / +13% / +23% | +6% / +8% / +8% | 24341993 |
| 42 ppm continuous | 20 months | female / male | +4% (n.s.) / +11% | +4% / +5% | 33145977 |
| 42 ppm every other month | 20 months | female / male | +8% / +9% (significant) | +10% / +9% | 33145977 |
| 42 ppm continuous (second cohort) | 20 months | female / male | +15% / +11% (significant) | +12% / +9% | 33145977 |

The invertebrate rows are dose-response experiments in worms and flies (for example +19% to
+26% median lifespan in *C. elegans* N2 at 1 nM to 100 µM; PubMed 22560223, 23698443, 24332851,
26676933, 29874838).

## 2. What is known in dogs

The canine aging corpus holds 152 records mentioning rapamycin or sirolimus. Three are
randomized, placebo-controlled trials in companion dogs:

- **TRIAD**, the Test of Rapamycin in Aging Dogs: study design and rationale for a prospective,
  parallel-group, double-masked, randomized, placebo-controlled, multicenter trial in healthy
  middle-aged dogs from the Dog Aging Project (2025; PMID 39951177, PMC12181551).
- A masked, placebo-controlled, randomized clinical trial of low-dose rapamycin (0.025 mg/kg)
  evaluating safety and the effect on cardiac function in 17 healthy client-owned dogs (2023;
  PMID 37275618, PMC10233048).
- A randomized controlled trial of short-term (10-week), non-immunosuppressive-dose rapamycin
  in 24 middle-aged companion dogs, with clinical and haematological exams and echocardiography
  before and after (2017; PMID 28374166, PMC5411365).

Two further hits matched the trial vocabulary but are not dog trials: a canine prostate cancer
transcriptome paper that discusses mTOR inhibition (PMID 40328211) and a 1991 preclinical
immunosuppression paper (PMID 1871787).

Other relevant corpus items: a 2025 review of rapamycin as a potential longevity intervention
in companion dogs (PMC12520851, full text available), a 2018 commentary "Rapamycin: Risking
Harm for Canine Longevity" (PMID 30339072), and a 2023 case report of severe asymptomatic
hypertriglyceridaemia during long-term low-dose rapamycin (PMID 38094495, full text available).

DrugAge itself contains **no dog lifespan experiment** for rapamycin.

## 3. Dosing

No dog-equivalent dose could be computed: every DrugAge animal dose is expressed as ppm of
diet or a molar concentration, not mg/kg, so the Km conversion has nothing to translate. The
only dog mg/kg figures in the tool output are the trial doses quoted in the corpus snippets
(0.025 mg/kg in the 2023 trial). These are the trials' own regimens, not derived starting points.

## 4. Target conservation

MTOR is in GenAge (human entry 221, Entrez 2475, listed for mammal, model-organism and
cell-based evidence). Ensembl Compara resolves a one-to-one dog ortholog, ENSCAFG00845002541
(symbol MTOR) on chromosome 2 (85,480,139–85,601,386, ROS_Cfam_1.0), at 98.1% sequence
identity. The target is conserved.

## 5. Veterinary use and safety signals

openFDA holds 2 adverse-event reports in dogs for sirolimus (reactions: bloody diarrhoea 2,
vomiting 2, death 1, overdose 1). The small count is consistent with off-label use only: there
is no FDA FOI summary for any dog product containing rapamycin or sirolimus, so no regulator-
reviewed canine pharmacokinetic or dose-multiple safety study exists in the FOI dataset.

## 6. Evidence gaps

From the tool:

- DrugAge has no dog lifespan experiment for this compound.
- No mg/kg animal dose in DrugAge to translate (doses reported as ppm or % of diet).
- No FDA FOI summary for a dog product containing this ingredient.

What a canine study would need to establish first, on this evidence: a lifespan or healthspan
endpoint (the three existing dog trials measured safety, haematology and cardiac function over
weeks to months; TRIAD is the first designed around lifespan and is still in progress), a dose
rationale grounded in canine pharmacokinetics rather than mouse diet concentrations, and
prospective monitoring for the lipid signal reported in the case report.
