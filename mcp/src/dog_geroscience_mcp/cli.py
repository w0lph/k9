"""``dog-geroscience-mcp`` command line: ``serve`` (default), ``fetch-data`` or ``build``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .paths import CORPUS_DIR, DATA_DIR, DB_FILENAME, DB_PATH, DB_URL, FOI_PATH, FOI_STRUCTURED_PATH, TRIALS_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dog-geroscience-mcp", description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_serve = sub.add_parser("serve", help="Run the MCP server over stdio (default). Downloads the database on first run.")
    p_serve.add_argument("--db", type=Path, default=DB_PATH)
    p_serve.add_argument("--corpus-dir", type=Path, default=CORPUS_DIR)

    p_fetch = sub.add_parser("fetch-data", help="Download the prebuilt database (Hugging Face Hub by default).")
    p_fetch.add_argument("--data-dir", type=Path, default=DATA_DIR)
    p_fetch.add_argument("--url", default=DB_URL)
    p_fetch.add_argument("--force", action="store_true", help="Re-download even if the file exists.")

    p_build = sub.add_parser("build", help="Download sources and build the SQLite database from the corpus and FOI datasets.")
    p_build.add_argument("--data-dir", type=Path, default=DATA_DIR)
    p_build.add_argument("--corpus-dir", type=Path, default=CORPUS_DIR)
    p_build.add_argument("--foi", type=Path, default=FOI_PATH, help="foi-summaries dog dataset JSONL (optional).")
    p_build.add_argument("--foi-structured", type=Path, default=FOI_STRUCTURED_PATH, help="structured extraction JSONL (optional).")
    p_build.add_argument("--trials", type=Path, default=TRIALS_PATH, help="canine-trials registry JSONL (optional).")
    p_build.add_argument("--out", type=Path, help=f"Write the database here instead of <data-dir>/{DB_FILENAME}.")
    p_build.add_argument(
        "--fulltext-licences",
        help='Comma-separated record licences whose Markdown full text is stored in the database, e.g. "cc by,cc0" '
             "for a redistributable build. Default: every full text on disk.",
    )
    p_build.add_argument("--skip-download", action="store_true", help="Reuse files already in data/raw.")
    p_build.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)
    cmd = args.cmd or "serve"

    if cmd == "build":
        logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
        logging.getLogger("httpx").setLevel(logging.WARNING)
        from .build import build_db, download_sources

        raw = args.data_dir / "raw"
        if not args.skip_download:
            download_sources(raw)
        licences = None
        if args.fulltext_licences:
            licences = {s.strip().lower() for s in args.fulltext_licences.split(",") if s.strip()}
        out = args.out or args.data_dir / DB_FILENAME
        summary = build_db(raw, args.corpus_dir, out, foi_path=args.foi, foi_structured_path=args.foi_structured,
                           fulltext_licences=licences, trials_path=args.trials)
        print(json.dumps({k: v for k, v in summary.items() if k != "downloads"}, indent=2))
        return 0

    if cmd == "fetch-data":
        logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")
        from .data_fetch import ensure_db

        path = ensure_db(args.data_dir / DB_FILENAME, args.url, force=args.force)
        print(json.dumps({"db": str(path), "bytes": path.stat().st_size, "url": args.url}, indent=2))
        return 0

    # serve: keep stdout clean for the protocol; log to stderr, and keep httpx quiet.
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    from .server import run_stdio

    # `serve` may be implicit (no subcommand), in which case its options are absent.
    run_stdio(getattr(args, "db", DB_PATH), getattr(args, "corpus_dir", CORPUS_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
