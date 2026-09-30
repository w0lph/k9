"""Coverage evaluation of intervention_dossier over ITP-tested compounds.

Not a truth test: it measures what the dossier *finds* for compounds where we know evidence
exists somewhere (mouse ITP results, dog trials, marketed veterinary products), so gaps in
the sources (not the tool) are visible. Run:

    uv run python scripts/dossier_eval.py [--no-openfda]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dog_geroscience_mcp import queries
from dog_geroscience_mcp.dossier import build_dossier
from dog_geroscience_mcp.paths import DB_PATH

# Agents tested by the NIA Interventions Testing Program (mice) plus two dog comparators.
COMPOUNDS = [
    ("rapamycin", "MTOR"),
    ("acarbose", None),
    ("17-alpha-estradiol", None),
    ("metformin", None),
    ("resveratrol", "SIRT1"),
    ("aspirin", None),
    ("nordihydroguaiaretic acid", None),
    ("canagliflozin", None),
    ("glycine", None),
    ("methylene blue", None),
    ("curcumin", None),
    ("green tea", None),
    ("simvastatin", None),
    ("captopril", None),
    ("selegiline", None),  # = L-deprenyl; the one DrugAge dog experiment; marketed as Anipryl
    ("carprofen", None),   # marketed canine NSAID; no lifespan data expected
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-openfda", action="store_true")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "dossier_eval.json")
    args = ap.parse_args()

    conn = queries.connect(args.db)
    rows = []
    print("| compound | DrugAge exp | species | ITP rows | dog rows | dog-eq doses | corpus mentions | dog trials | openFDA dog reports | FOI hits | FOI structured | gaps |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for compound, gene in COMPOUNDS:
        t = time.time()
        d = build_dossier(conn, compound, target_gene=gene, cache_db=args.db, include_openfda=not args.no_openfda)
        da = d["drugage"]
        ofda = d["openfda_dog_adverse_events"] or {}
        foi = d["foi_summaries_dog"]
        row = {
            "compound": compound,
            "drugage_experiments": da["n_experiments"],
            "species": len(da["by_species"]),
            "itp_rows": len(da["itp_rows"]),
            "dog_rows": len(da["dog_rows"]),
            "dog_equivalent_doses": len(d["dog_equivalent_doses"]["rows"]),
            "corpus_mentions": d["corpus"]["records_mentioning_compound"],
            "dog_trials": len(d["corpus"]["dog_trials"]),
            "openfda_dog_reports": ofda.get("total") if ofda else None,
            "foi_hits": None if foi is None else len(foi),
            "foi_structured": None if d.get("foi_structured") is None else len(d["foi_structured"]),
            "gaps": d["gaps"],
            "target_ortholog": (d["target"] or {}).get("dog_ortholog", {}).get("n_orthologs") if d["target"] else None,
            "seconds": round(time.time() - t, 1),
        }
        rows.append(row)
        print(f"| {compound} | {row['drugage_experiments']} | {row['species']} | {row['itp_rows']} | {row['dog_rows']} | "
              f"{row['dog_equivalent_doses']} | {row['corpus_mentions']} | {row['dog_trials']} | "
              f"{row['openfda_dog_reports'] if row['openfda_dog_reports'] is not None else '-'} | "
              f"{row['foi_hits'] if row['foi_hits'] is not None else 'n/a'} | "
              f"{row['foi_structured'] if row['foi_structured'] is not None else 'n/a'} | {len(row['gaps'])} |")
    conn.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
