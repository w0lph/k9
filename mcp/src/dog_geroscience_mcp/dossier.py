"""Intervention dossier: everything this server can say about a compound, for dogs.

Deterministic composition of the other tools, so an agent (or a human) gets one structured
evidence package instead of running six lookups by hand:

* DrugAge lifespan experiments across species, with the NIA ITP flag and dog rows separated;
* allometric dog-equivalent doses for every mg/kg animal dose in those rows;
* canine aging corpus hits (and how many mention the compound at all);
* optional target gene: GenAge entries and the dog ortholog (Ensembl, cached);
* openFDA adverse-event reports in dogs (a proxy for "is this a marketed veterinary drug");
* FDA FOI summaries for dog products containing the ingredient (when the FOI table is built);
* an explicit list of evidence gaps.

Nothing here is inferred by a model; every block carries its source.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import dose, live, queries

_DOSE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|µg|ug|g)\s*/\s*kg", re.IGNORECASE)
_TO_MG = {"mg": 1.0, "mcg": 0.001, "µg": 0.001, "ug": 0.001, "g": 1000.0}

# Names differ across sources (DrugAge, corpus, openFDA). Lookups try every alias.
SYNONYMS: dict[str, list[str]] = {
    "selegiline": ["L-deprenyl", "deprenyl", "Anipryl"],
    "l-deprenyl": ["selegiline", "deprenyl", "Anipryl"],
    "rapamycin": ["sirolimus"],
    "sirolimus": ["rapamycin"],
    "17-alpha-estradiol": ["17-α-estradiol", "17α-estradiol", "17alpha-estradiol", "alpha-estradiol"],
    "nordihydroguaiaretic acid": ["NDGA", "masoprocol"],
    "ndga": ["nordihydroguaiaretic acid", "masoprocol"],
    "green tea": ["green tea extract", "epigallocatechin gallate", "EGCG"],
    "aspirin": ["acetylsalicylic acid"],
    "metformin": ["metformin hydrochloride"],
    "acarbose": [],
    "canagliflozin": [],
    "vitamin e": ["alpha-tocopherol", "tocopherol"],
    "nad": ["nicotinamide riboside", "nicotinamide mononucleotide", "NMN", "NR"],
    "carprofen": ["Rimadyl"],
}


def aliases_for(compound: str) -> list[str]:
    """The compound plus known alternative names (deduplicated, order preserved)."""
    key = compound.strip().lower()
    out = [compound.strip()]
    for alt in SYNONYMS.get(key, []):
        if alt.lower() not in {o.lower() for o in out}:
            out.append(alt)
    # generic spelling variants: alpha/α, hyphen/space, and the Unicode hyphen (U+2010) DrugAge uses
    for base in list(out):
        for v in (
            base.replace("alpha", "α"), base.replace("α", "alpha"), base.replace("-", " "), base.replace(" ", "-"),
            base.replace("-", "‐"), base.replace("‐", "-"),
        ):
            if v.lower() not in {o.lower() for o in out}:
                out.append(v)
    return out


_KM_SPECIES = {
    "mus musculus": "mouse",
    "rattus norvegicus": "rat",
    "canis lupus familiaris": "dog",
    "homo sapiens": "human",
    "oryctolagus cuniculus": "rabbit",
    "mesocricetus auratus": "hamster",
    "cavia porcellus": "guinea pig",
    "macaca mulatta": "monkey",
    "macaca fascicularis": "monkey",
}


_OTHER_SPECIES_RE = re.compile(r"\b(cats?|feline|horses?|equine|cattle|bovine|swine|pigs?|sheep|goats?|poultry)\b", re.IGNORECASE)
_DOG_WORD_RE = re.compile(r"\b(dogs?|canine)\b", re.IGNORECASE)


def _non_dog(species_class: str | None) -> bool:
    """True when a species field names another species and never mentions dogs."""
    s = species_class or ""
    return bool(_OTHER_SPECIES_RE.search(s)) and not _DOG_WORD_RE.search(s)


def parse_mg_per_kg(dosage: str | None) -> float | None:
    if not dosage:
        return None
    m = _DOSE_RE.search(dosage)
    if not m:
        return None
    return round(float(m.group(1)) * _TO_MG[m.group(2).lower()], 4)


def km_species(species: str | None) -> str | None:
    return _KM_SPECIES.get((species or "").strip().lower())


def build_dossier(
    conn: sqlite3.Connection,
    compound: str,
    target_gene: str | None = None,
    corpus_limit: int = 10,
    cache_db: Path | None = None,
    include_openfda: bool = True,
    openfda_client=None,
) -> dict:
    compound = compound.strip()
    names = aliases_for(compound)
    rows: list[dict] = []
    seen_rows: set[tuple] = set()
    for name in names:
        for r in queries.drugage_search(conn, compound=name, limit=1000):
            sig = tuple(r.get(k) for k in ("compound_name", "species", "strain", "dosage", "age_at_initiation",
                                             "treatment_duration", "gender", "avg_lifespan_change_percent",
                                             "max_lifespan_change_percent", "pubmed_id"))
            if sig not in seen_rows:
                seen_rows.add(sig)
                rows.append(r)
    by_species: dict[str, int] = {}
    for r in rows:
        by_species[r.get("species", "?")] = by_species.get(r.get("species", "?"), 0) + 1
    itp_rows = [r for r in rows if (r.get("itp") or "").lower() == "yes"]
    dog_rows = [r for r in rows if "canis" in (r.get("species") or "").lower()]

    translations = []
    seen = set()
    for r in rows:
        mgkg = parse_mg_per_kg(r.get("dosage"))
        sp = km_species(r.get("species"))
        if mgkg is None or sp is None or sp == "dog":
            continue
        key = (sp, mgkg)
        if key in seen:
            continue
        seen.add(key)
        t = dose.translate(mgkg, sp, "dog")
        translations.append(
            {
                "species": r.get("species"),
                "dosage_as_reported": r.get("dosage"),
                "mg_per_kg": mgkg,
                "dog_equivalent_mg_per_kg": t["dose_mg_per_kg_out"],
                "factor": t["factor"],
                "itp": r.get("itp"),
                "pubmed_id": r.get("pubmed_id"),
            }
        )

    name_expr = " OR ".join(f'"{n.replace(chr(34), "")}"' for n in names)
    corpus_total = len(queries.corpus_match(conn, f"({name_expr})", tier=None, limit=100000))
    corpus_hits = [h for h in queries.corpus_match(conn, f"({name_expr})", tier="core", limit=corpus_limit) if "error" not in h]
    trial_expr = f'({name_expr}) AND ("trial" OR "randomized" OR "randomised" OR "placebo" OR "masked" OR "blinded")'
    trial_hits = [h for h in queries.corpus_match(conn, trial_expr, tier=None, limit=10) if "error" not in h][:5]

    target = None
    if target_gene:
        target = {
            "gene": target_gene,
            "genage": queries.genage_search(conn, target_gene, limit=5),
            "dog_ortholog": live.dog_ortholog(target_gene, "human", cache_db=cache_db),
        }

    openfda = None
    if include_openfda:
        for name in names[:4]:  # first alias with reports wins
            openfda = live.openfda_dog_events(name, client=openfda_client)
            if openfda.get("total", 0) > 0 or openfda.get("error"):
                break
    foi = None
    if queries.has_table(conn, "foi_dog"):
        foi, seen_foi = [], set()
        for name in names:
            for f in queries.foi_search(conn, name, limit=10):
                # a dog application can own a cat-indication summary; skip those
                if f["foi_id"] not in seen_foi and f.get("species_flag") != "other":
                    seen_foi.add(f["foi_id"])
                    foi.append(f)
    foi_structured = None
    if queries.has_table(conn, "foi_structured"):
        foi_structured, seen_fs = [], set()
        for name in names:
            for f in queries.foi_structured_search(conn, name, limit=10):
                if f["foi_id"] not in seen_fs and not _non_dog(f.get("species_class")):
                    seen_fs.add(f["foi_id"])
                    foi_structured.append(f)

    gaps: list[str] = []
    if not rows:
        gaps.append("DrugAge has no lifespan experiment for this compound in any species.")
    elif not dog_rows:
        gaps.append("DrugAge has no dog lifespan experiment for this compound.")
    if not itp_rows:
        gaps.append("No NIA Interventions Testing Program result flagged in DrugAge.")
    if corpus_total == 0:
        gaps.append("No record in the canine aging corpus mentions this compound.")
    elif not trial_hits:
        gaps.append("Corpus mentions exist but no randomized/placebo-controlled dog trial surfaced for it.")
    if not translations and rows:
        gaps.append("No mg/kg animal dose in DrugAge to translate (doses reported as ppm or % of diet).")
    if openfda is not None and openfda.get("total", 0) == 0 and not openfda.get("error"):
        gaps.append("No openFDA adverse-event reports in dogs: likely not a marketed veterinary product.")
    if foi is not None and not foi:
        gaps.append("No FDA FOI summary for a dog product containing this ingredient.")
    if target and not target["dog_ortholog"].get("orthologs"):
        gaps.append(f"No dog ortholog resolved for {target_gene} (Ensembl).")

    return {
        "compound": compound,
        "names_searched": names,
        "drugage": {
            "n_experiments": len(rows),
            "by_species": by_species,
            "itp_rows": itp_rows,
            "dog_rows": dog_rows,
            "other_rows_sample": [r for r in rows if r not in dog_rows][:20],
            "source": "DrugAge (HAGR), CC BY 3.0",
        },
        "dog_equivalent_doses": {
            "rows": translations,
            "method": "FDA 2005 Km body-surface-area conversion; starting-point heuristic only",
        },
        "corpus": {
            "records_mentioning_compound": corpus_total,
            "top_core_hits": corpus_hits,
            "dog_trials": trial_hits,
            "source": "canine-aging-corpus (Europe PMC)",
        },
        "target": target,
        "openfda_dog_adverse_events": openfda,
        "foi_summaries_dog": foi,
        "foi_structured": foi_structured,
        "gaps": gaps,
    }
