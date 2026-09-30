"""``foi`` command line: index -> download -> text -> dataset (or ``run`` for all)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="foi", description="FDA CVM FOI summaries as a dataset.")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("index", help="Fetch the FOI catalogue and the dog application list; join them.")
    p = sub.add_parser("download", help="Download FOI PDFs (dog subset by default).")
    p.add_argument("--all-species", action="store_true")
    p.add_argument("--limit", type=int)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("text", help="Extract text from downloaded PDFs.")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("dataset", help="Parse sections/fields and write the dataset JSONL.")
    p.add_argument("--all-species", action="store_true")
    p.add_argument("--no-sections", action="store_true", help="Omit full section text (smaller file).")
    p = sub.add_parser("run", help="index + download + text + dataset for the dog subset.")
    p.add_argument("--limit", type=int)
    p.add_argument("--workers", type=int, default=3)
    sub.add_parser("stats", help="Print index and dataset summaries.")
    p = sub.add_parser("show", help="Print a summary's metadata, General Information and section sizes; --text prints the text.")
    p.add_argument("foi_id", type=int)
    p.add_argument("--text", action="store_true")
    p.add_argument("--section", help="Print only this parsed section (e.g. target_animal_safety).")
    p.add_argument("--max-chars", type=int, default=40000)
    p = sub.add_parser("grep", help="Print sentences of a summary containing a phrase (safe to quote verbatim).")
    p.add_argument("foi_id", type=int)
    p.add_argument("phrase")
    p = sub.add_parser("validate-structured", help="Validate a structured-extraction JSONL against the summary texts.")
    p.add_argument("path", type=Path)
    p = sub.add_parser("merge-structured", help="Merge structured drafts into data/structured_dog.jsonl.")
    p.add_argument("paths", type=Path, nargs="+")
    p.add_argument("-o", "--out", type=Path)
    sub.add_parser("schema", help="Print the structured-record schema.")
    sub.add_parser("structured-status", help="Progress of the batch extraction against data/structured/batches.json.")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    dd: Path = args.data_dir

    if args.cmd == "index":
        from .index import build_index

        print(json.dumps(build_index(dd), indent=2))
    elif args.cmd == "download":
        from .download import download_pdfs

        print(json.dumps(download_pdfs(dd, all_species=args.all_species, limit=args.limit, workers=args.workers, force=args.force), indent=2))
    elif args.cmd == "text":
        from .text import extract_all

        print(json.dumps(extract_all(dd, force=args.force), indent=2))
    elif args.cmd == "dataset":
        from .dataset import build_dataset

        print(json.dumps(build_dataset(dd, all_species=args.all_species, include_sections=not args.no_sections), indent=2))
    elif args.cmd == "run":
        from .dataset import build_dataset
        from .download import download_pdfs
        from .index import build_index
        from .text import extract_all

        print(json.dumps(build_index(dd)))
        print(json.dumps(download_pdfs(dd, limit=args.limit, workers=args.workers)))
        print(json.dumps(extract_all(dd)))
        print(json.dumps(build_dataset(dd), indent=2))
    elif args.cmd == "stats":
        for name in ("index_summary.json", "dataset_version.json"):
            p = dd / name
            print(f"== {name} ==")
            print(p.read_text(encoding="utf-8") if p.exists() else "(missing)")
    elif args.cmd in ("show", "grep"):
        from .sections import sentences_with
        from .structured import norm, read_jsonl

        rec = next((r for r in read_jsonl(dd / "foi_summaries_dog.jsonl") if r["foi_id"] == args.foi_id), None)
        if rec is None:
            print(f"no record with foi_id {args.foi_id}", file=sys.stderr)
            return 1
        text = (dd / "text" / f"{args.foi_id}.txt").read_text(encoding="utf-8")
        if args.cmd == "grep":
            hits = sentences_with(norm(text), (args.phrase.lower(),), max_n=40)
            for s in hits:
                print("-", s)
            return 0
        meta = {k: rec.get(k) for k in ("foi_id", "application_number", "proprietary_name", "ingredients", "sponsor", "approval_type", "approval_date", "catalogue_summary")}
        print(json.dumps(meta, indent=2, ensure_ascii=False))
        parsed = rec.get("parsed") or {}
        print("general_information:", json.dumps(parsed.get("general_information"), indent=2, ensure_ascii=False))
        print("section_chars:", parsed.get("section_chars"))
        if args.section:
            print(f"--- {args.section} ---")
            print((parsed.get("sections") or {}).get(args.section, "(no such section)")[: args.max_chars])
        elif args.text:
            print("--- text ---")
            print(text[: args.max_chars])
    elif args.cmd == "validate-structured":
        from .structured import read_jsonl, validate_structured

        rep = validate_structured(read_jsonl(args.path), dd)
        print(rep.summary())
        for w in rep.warnings:
            print("WARN ", w)
        for e in rep.errors:
            print("ERROR", e)
        return 0 if rep.ok else 1
    elif args.cmd == "merge-structured":
        from .structured import merge_structured

        n, dropped = merge_structured(args.paths, args.out or dd / "structured_dog.jsonl")
        print(f"wrote {n} records; dropped {len(dropped)}")
        for d in dropped:
            print("  ", d)
    elif args.cmd == "schema":
        from .structured import SCHEMA_DOC

        print(json.dumps(SCHEMA_DOC, indent=2))
    elif args.cmd == "structured-status":
        from .structured import read_jsonl, validate_structured

        plan = json.loads((dd / "structured" / "batches.json").read_text(encoding="utf-8"))
        done_total = 0
        for b in plan:
            path = dd / "structured" / "drafts" / f"batch_{b['batch']}.jsonl"
            planned = {r["foi_id"] for r in b["records"]}
            if not path.exists():
                print(f"batch {b['batch']}: pending ({len(planned)} planned)")
                continue
            rows = read_jsonl(path)
            got = {r.get("foi_id") for r in rows}
            rep = validate_structured(rows, dd)
            missing = sorted(planned - got)
            extra = sorted(got - planned)
            state = "ok" if rep.ok and not missing and not extra else "ISSUES"
            done_total += len(got & planned)
            print(f"batch {b['batch']}: {state} records {len(rows)}/{len(planned)} errors {len(rep.errors)} warnings {len(rep.warnings)}"
                  + (f" missing {missing}" if missing else "") + (f" extra {extra}" if extra else ""))
        print(f"done {done_total} of {sum(len(b['records']) for b in plan)} planned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
