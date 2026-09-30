"""``cgq`` command line."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from .common import CORPUS_DIR, DB_PATH, load_records, read_fulltext, write_jsonl
from .evaluate import evaluate_file
from .find import quote_candidates, search
from .merge import merge_files
from .validate import validate_file


def _print_record(rec: dict, abstract: bool) -> None:
    ft = "ft" if rec.get("has_fulltext_md") else "--"
    print(f"{rec['key']:<16} {rec.get('year')} cit={rec.get('cited_by_count') or 0:<4} {ft} {rec.get('title')}")
    ids = " ".join(f"{k}={rec[k]}" for k in ("pmid", "pmcid", "doi") if rec.get(k))
    print(f"    {ids} | {rec.get('journal')} | tiers={rec.get('tiers')}")
    if abstract and rec.get("abstract"):
        print("    " + rec["abstract"].replace("\n", " "))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cgq", description="Canine geroscience question-set tooling.")
    ap.add_argument("--corpus-dir", type=Path, default=CORPUS_DIR)
    ap.add_argument("--db", type=Path, default=DB_PATH)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("find", help="BM25 search of the corpus (AND of content words, OR fallback).")
    p.add_argument("query")
    p.add_argument("--tier", default="core", help="core | extended | all")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--abstract", action="store_true", help="Print abstracts.")
    p.add_argument("--fulltext-only", action="store_true")

    p = sub.add_parser("show", help="Print one record (abstract) and optionally its full text.")
    p.add_argument("key")
    p.add_argument("--fulltext", action="store_true")
    p.add_argument("--max-chars", type=int, default=20000)

    p = sub.add_parser("quote", help="Sentences in a record containing a phrase (safe to cite verbatim).")
    p.add_argument("key")
    p.add_argument("phrase")

    p = sub.add_parser("validate", help="Validate a JSONL question file.")
    p.add_argument("path", type=Path)
    p.add_argument("--require-ids", action="store_true")

    p = sub.add_parser("merge", help="Merge draft files into a numbered set.")
    p.add_argument("paths", type=Path, nargs="+")
    p.add_argument("-o", "--out", type=Path, required=True)
    p.add_argument("--by", default="claude-fable-5-1")

    p = sub.add_parser("evaluate", help="Retrieval recall@k of evidence records for each question.")
    p.add_argument("path", type=Path)
    p.add_argument("--show-misses", action="store_true")

    p = sub.add_parser("review-apply", help="Apply reviewer verdict files (pass/fix/drop) and write the next version.")
    p.add_argument("questions", type=Path)
    p.add_argument("reviews", type=Path, nargs="+")
    p.add_argument("-o", "--out", type=Path, required=True)
    p.add_argument("--min-confidence", default="low", choices=["low", "medium", "high"])

    args = ap.parse_args(argv)

    if args.cmd == "find":
        tier = None if args.tier == "all" else args.tier
        for rec in search(args.query, tier, args.limit, args.fulltext_only, args.db):
            recs = load_records(args.corpus_dir)
            _print_record(recs[rec["key"]] | {"has_fulltext_md": rec["has_fulltext_md"], "cited_by_count": rec["cited_by_count"]}, args.abstract)
        return 0

    if args.cmd == "show":
        rec = load_records(args.corpus_dir).get(args.key)
        if rec is None:
            print(f"unknown key {args.key}", file=sys.stderr)
            return 1
        body = read_fulltext(args.corpus_dir, rec.get("pmcid"))
        _print_record(rec | {"has_fulltext_md": body is not None}, abstract=True)
        if args.fulltext:
            print("\n--- full text ---" if body else "\n(no full text on disk)")
            if body:
                print(body[: args.max_chars])
        return 0

    if args.cmd == "quote":
        for loc, s in quote_candidates(args.key, args.phrase, args.corpus_dir):
            print(f"[{loc}] {s}")
        return 0

    if args.cmd == "validate":
        rep = validate_file(args.path, args.corpus_dir, args.require_ids)
        print(rep.summary())
        for w in rep.warnings:
            print("WARN ", w)
        for e in rep.errors:
            print("ERROR", e)
        return 0 if rep.ok else 1

    if args.cmd == "merge":
        rows, dropped = merge_files(args.paths, args.by, datetime.now(UTC).strftime("%Y-%m-%d"))
        write_jsonl(args.out, rows)
        print(f"wrote {len(rows)} questions to {args.out}; dropped {len(dropped)} near-duplicates")
        for d in dropped:
            print("  ", d)
        return 0

    if args.cmd == "evaluate":
        res = evaluate_file(args.path, args.db)
        print(json.dumps({k: v for k, v in res.items() if k != "misses"}, indent=2))
        if args.show_misses:
            for m in res["misses"]:
                print("MISS", m["id"], m["gold"], m["question"][:90])
        return 0

    if args.cmd == "review-apply":
        from .review import apply_reviews

        print(json.dumps(apply_reviews(args.questions, args.reviews, args.out, args.min_confidence), indent=2))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
