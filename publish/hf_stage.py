"""Assemble the Hugging Face dataset repositories under publish/stage/ from the local data.

Run from the repository root inside the mcp environment (it has pandas, pyarrow and the
server's build function):

    uv run --directory mcp python ../publish/hf_stage.py --owner <hf-username> [--only corpus,questions,foi,mcp-data]

Nothing here talks to the Hub; publish/hf_upload.ps1 does the uploads. Four repositories:

    canine-aging-corpus         records + manifest + redistributable full text (CC BY / CC0 only)
    canine-geroscience-questions the reviewed question set (v0.1) and v0
    foi-summaries-dog           FOI summaries, structured records, extracted text, catalogue
    dog-geroscience-mcp-data    the prebuilt SQLite database the MCP server downloads on first run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "publish" / "stage"
CARDS = ROOT / "publish" / "cards"

# Record licences (as Europe PMC reports them) whose Markdown full text is redistributed.
REDISTRIBUTABLE = {"cc by", "cc0"}

LICENSE_TEXTS = {
    "canine-aging-corpus": """Mixed licences; see README.md.

- records.jsonl and manifest.parquet: bibliographic metadata and abstracts retrieved from the
  Europe PMC REST API (https://europepmc.org/RestfulWebService), redistributed under Europe
  PMC's terms (https://europepmc.org/Copyright). Abstract copyright remains with the
  respective publishers and authors.
- fulltext.parquet and fulltext/md/: article full text, only for articles whose Europe PMC
  licence field is CC BY (any version) or CC0. Each row/file carries the article's licence
  and identifiers; attribute the original authors and journal.
- The compilation itself (selection, conversion, manifest): CC BY 4.0.
""",
    "foi-summaries-dog": """The FOI summaries (text/, foi_summaries_dog.jsonl, foi_index.jsonl) are works of the
United States Government (FDA Center for Veterinary Medicine) and are in the public domain
in the United States (17 U.S.C. 105). Source: https://animaldrugsatfda.fda.gov.

structured_dog.jsonl (the typed, quote-grounded extraction) and the parsed fields are
released under CC BY 4.0.
""",
    "dog-geroscience-mcp-data": """dog_geroscience.sqlite bundles several sources; each table keeps its own terms:

- anage, drugage, genage_*: Human Ageing Genomic Resources (https://genomics.senescence.info),
  CC BY 3.0.
- dap_codebook*: Dog Aging Project public codebooks as published at
  https://github.com/dogagingproject/dataRelease.
- corpus_records, corpus_fts: Europe PMC metadata and abstracts (https://europepmc.org/Copyright).
- corpus_fulltext: article full text only where the licence is CC BY or CC0; each row
  carries its licence.
- foi_dog, foi_records: FDA CVM FOI summaries, US Government works (public domain).
- foi_structured: CC BY 4.0.
""",
}


def fresh(d: Path) -> Path:
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    return d


def card(name: str, dest: Path, owner: str) -> None:
    text = (CARDS / f"{name}.md").read_text(encoding="utf-8").replace("{owner}", owner)
    (dest / "README.md").write_text(text, encoding="utf-8", newline="\n")
    if name in LICENSE_TEXTS:
        (dest / "LICENSE").write_text(LICENSE_TEXTS[name], encoding="utf-8", newline="\n")


def _front(text: str, key: str) -> str | None:
    if not text.startswith("---"):
        return None
    for line in text.split("\n", 60)[1:]:
        if line.strip() == "---":
            break
        if line.startswith(key + ":"):
            return line.split(":", 1)[1].strip().strip('"')
    return None


def stage_corpus(owner: str) -> Path:
    import pandas as pd

    src = ROOT / "corpus" / "data"
    dest = fresh(STAGE / "canine-aging-corpus")
    for f in ("records.jsonl", "manifest.parquet", "corpus_version.json"):
        shutil.copy2(src / f, dest / f)

    recs: dict[str, dict] = {}
    with (src / "records.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                if r.get("pmcid"):
                    recs[r["pmcid"]] = r
    sources: dict[str, str] = {}
    sp = src / "fulltext" / "sources.jsonl"
    if sp.exists():
        with sp.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    s = json.loads(line)
                    sources[s["pmcid"]] = s.get("source")

    md_dir = src / "fulltext" / "md"
    out_md = dest / "fulltext" / "md"
    out_md.mkdir(parents=True)
    rows: list[dict] = []
    excluded: Counter[str] = Counter()
    for p in sorted(md_dir.glob("PMC*.md")):
        r = recs.get(p.stem, {})
        lic = (r.get("license") or "").strip().lower()
        if lic not in REDISTRIBUTABLE:
            excluded[lic or "(none)"] += 1
            continue
        text = p.read_text(encoding="utf-8")
        shutil.copy2(p, out_md / p.name)
        rows.append({
            "pmcid": p.stem, "pmid": r.get("pmid"), "doi": r.get("doi"), "title": r.get("title"),
            "journal": r.get("journal"), "year": r.get("year"), "license": lic, "source": sources.get(p.stem),
            "article_type": _front(text, "article_type"), "chars": len(text), "markdown": text,
        })
    pd.DataFrame(rows).to_parquet(dest / "fulltext.parquet", index=False)
    (dest / "fulltext_manifest.json").write_text(json.dumps({
        "included": len(rows), "licences_included": sorted(REDISTRIBUTABLE),
        "excluded_by_licence": dict(excluded.most_common()),
        "note": "Full text is redistributed only for CC BY / CC0 articles; the pipeline (corpus/) fetches the rest.",
    }, indent=2), encoding="utf-8", newline="\n")
    card("canine-aging-corpus", dest, owner)
    print(f"corpus: {len(recs)} PMC records, full text kept {len(rows)}, excluded {dict(excluded)}")
    return dest


def stage_questions(owner: str) -> Path:
    src = ROOT / "questions"
    dest = fresh(STAGE / "canine-geroscience-questions")
    for f in ("data/canine_geroscience_v0_1.jsonl", "data/canine_geroscience_v0.jsonl", "schema.json"):
        shutil.copy2(src / f, dest / Path(f).name)
    card("canine-geroscience-questions", dest, owner)
    return dest


def stage_foi(owner: str) -> Path:
    src = ROOT / "foi" / "data"
    dest = fresh(STAGE / "foi-summaries-dog")
    for f in ("foi_summaries_dog.jsonl", "structured_dog.jsonl", "dataset_version.json", "foi_index.jsonl"):
        shutil.copy2(src / f, dest / f)
    shutil.copytree(src / "text", dest / "text")
    card("foi-summaries-dog", dest, owner)
    print(f"foi: {sum(1 for _ in (dest / 'text').iterdir())} text files")
    return dest


def stage_mcp_data(owner: str) -> Path:
    from dog_geroscience_mcp.build import build_db

    dest = fresh(STAGE / "dog-geroscience-mcp-data")
    summary = build_db(
        ROOT / "mcp" / "data" / "raw", ROOT / "corpus" / "data", dest / "dog_geroscience.sqlite",
        foi_path=ROOT / "foi" / "data" / "foi_summaries_dog.jsonl",
        foi_structured_path=ROOT / "foi" / "data" / "structured_dog.jsonl",
        fulltext_licences=REDISTRIBUTABLE,
    )
    (dest / "build_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8", newline="\n")
    card("dog-geroscience-mcp-data", dest, owner)
    print(f"mcp-data: corpus full text stored {summary['corpus']['with_fulltext_md']} of {summary['corpus']['fulltext_on_disk']}; "
          f"foi {summary['foi'].get('records')}; structured {summary['foi_structured'].get('records')}")
    return dest


STAGES = {"corpus": stage_corpus, "questions": stage_questions, "foi": stage_foi, "mcp-data": stage_mcp_data}


def size_mb(d: Path) -> float:
    return sum(p.stat().st_size for p in d.rglob("*") if p.is_file()) / 1e6


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--owner", required=True, help="Hugging Face user or org that will own the repositories.")
    ap.add_argument("--only", help="Comma-separated subset of: " + ",".join(STAGES))
    args = ap.parse_args(argv)
    wanted = [s.strip() for s in args.only.split(",")] if args.only else list(STAGES)
    unknown = [w for w in wanted if w not in STAGES]
    if unknown:
        print(f"unknown stage(s): {unknown}", file=sys.stderr)
        return 2
    for w in wanted:
        d = STAGES[w](args.owner)
        print(f"  -> {d} ({size_mb(d):.1f} MB)")
    print("\nNext: .\\publish\\hf_upload.ps1 -Owner", args.owner)
    return 0


if __name__ == "__main__":
    sys.exit(main())
