"""``ct`` command line: validate, merge drafts, stats, export."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from .validate import DATA, SourceTexts, read_jsonl, validate_records

REGISTRY = DATA / "canine_trials.jsonl"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _sort_key(r: dict):
    return (r.get("start_year") or r.get("end_year") or max((s.get("year") or 0) for s in r.get("sources") or [{}]) or 0, r.get("name", ""))


def cmd_validate(args) -> int:
    records = read_jsonl(args.path)
    rep = validate_records(records, texts=SourceTexts(db_path=args.db) if args.db else None)
    for w in rep.warnings:
        print("WARNING", w)
    for e in rep.errors:
        print("ERROR", e)
    print(f"records: {rep.records} | quotes checked: {rep.quotes} | errors: {len(rep.errors)} | warnings: {len(rep.warnings)}")
    return 0 if rep.ok else 1


def cmd_merge(args) -> int:
    merged: dict[str, dict] = {}
    for p in args.paths:
        for r in read_jsonl(p):
            if r["id"] in merged:
                print(f"duplicate id {r['id']} in {p}; keeping the first", file=sys.stderr)
                continue
            merged[r["id"]] = r
    records = sorted(merged.values(), key=_sort_key)
    _write_jsonl(args.out, records)
    print(f"wrote {len(records)} records to {args.out}")
    return 0


def cmd_stats(args) -> int:
    records = read_jsonl(args.path)
    kinds = Counter(r.get("kind") for r in records)
    status = Counter(r.get("status") for r in records)
    classes = Counter(r.get("intervention_class") for r in records)
    n_sources = sum(len(r.get("sources") or []) for r in records)
    n_quotes = sum(len(s.get("quotes") or []) for r in records for s in r.get("sources") or [])
    pmids = {s.get("pmid") for r in records for s in r.get("sources") or [] if s.get("type") in ("pmid", "europepmc")}
    print(json.dumps({"records": len(records), "kinds": dict(kinds), "status": dict(status), "intervention_class": dict(classes),
                      "sources": n_sources, "distinct_pmids": len(pmids - {None}), "quotes": n_quotes}, indent=2))
    return 0


def cmd_export(args) -> int:
    records = read_jsonl(args.path)
    cols = ["id", "name", "acronym", "kind", "status", "setting", "intervention", "intervention_class", "comparator", "dose_regimen",
            "duration", "n", "breed", "age", "primary_outcome", "result", "lead_organization", "sponsor_or_funder", "start_year", "end_year", "pmids", "summary"]
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in records:
            pop = r.get("population") or {}
            w.writerow({**{c: r.get(c) for c in cols if c not in ("n", "breed", "age", "pmids")},
                        "n": pop.get("n"), "breed": pop.get("breed"), "age": pop.get("age"),
                        "pmids": ";".join(str(s.get("pmid")) for s in r.get("sources") or [] if s.get("pmid"))})
    print(f"wrote {len(records)} rows to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ct", description="Canine aging trial registry tools.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate", help="Schema + verbatim-quote validation of a registry JSONL.")
    p.add_argument("path", type=Path, nargs="?", default=REGISTRY)
    p.add_argument("--db", type=Path, help="dog-geroscience-mcp SQLite with corpus abstracts (default: ../mcp/data/dog_geroscience.sqlite or $DOG_GERO_DB).")
    p = sub.add_parser("merge", help="Merge draft JSONL files into the registry (dedupe by id, sort by year).")
    p.add_argument("paths", type=Path, nargs="+")
    p.add_argument("-o", "--out", type=Path, default=REGISTRY)
    p = sub.add_parser("stats", help="Counts by kind, status and class.")
    p.add_argument("path", type=Path, nargs="?", default=REGISTRY)
    p = sub.add_parser("export", help="Flat CSV of the registry.")
    p.add_argument("path", type=Path, nargs="?", default=REGISTRY)
    p.add_argument("-o", "--out", type=Path, default=DATA / "canine_trials.csv")
    args = ap.parse_args(argv)
    return {"validate": cmd_validate, "merge": cmd_merge, "stats": cmd_stats, "export": cmd_export}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
