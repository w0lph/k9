"""Validate registry records: schema, identifiers, and verbatim quotes against the cited source texts.

Source texts come from three places:
- ``pmid`` sources: the canine-aging-corpus abstract (and full text when ``quote_scope`` is
  ``fulltext``) read from the dog-geroscience-mcp database (``corpus_records`` and
  ``corpus_fulltext`` tables) or, failing that, from ``corpus/data``;
- ``web`` sources: ``trials/data/sources/web/<slug>.txt`` snapshots;
- ``europepmc`` sources: ``trials/data/sources/europepmc/pmid_<pmid>.json``.

Quotes are compared after collapsing whitespace and stripping HTML tags, so line wrapping and
``<h4>`` section markers in abstracts do not matter, but every character of the quote itself must
appear in order in the source.
"""

from __future__ import annotations

import html
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve()
PROJECT = HERE.parents[2]                      # trials/
ROOT = PROJECT.parent                          # repository root
SCHEMA_PATH = PROJECT / "schema.json"
DATA = PROJECT / "data"
SOURCES = DATA / "sources"
DEFAULT_DB = Path(os.environ.get("DOG_GERO_DB", ROOT / "mcp" / "data" / "dog_geroscience.sqlite"))
CORPUS_DIR = Path(os.environ.get("DOG_GERO_CORPUS", ROOT / "corpus" / "data"))

_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>")  # real tags only; "P<.05" is not a tag
_WS = re.compile(r"\s+")


def norm(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(_TAG.sub(" ", text))
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("‐", "-").replace("‑", "-").replace("‒", "-").replace("–", "-").replace("—", "-").replace(" ", " ")
    return _WS.sub(" ", text).strip()


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open("r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: invalid JSON: {e}") from e
    return out


class SourceTexts:
    """Lazy access to the texts quotes are checked against."""

    def __init__(self, db_path: Path = DEFAULT_DB, corpus_dir: Path = CORPUS_DIR, sources_dir: Path = SOURCES):
        self.db_path, self.corpus_dir, self.sources_dir = db_path, corpus_dir, sources_dir
        self._conn: sqlite3.Connection | None = None
        self._records: dict[str, dict] | None = None
        self._cache: dict[tuple, str | None] = {}

    def _db(self) -> sqlite3.Connection | None:
        if self._conn is None and self.db_path.exists():
            self._conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _jsonl_records(self) -> dict[str, dict]:
        if self._records is None:
            self._records = {}
            p = self.corpus_dir / "records.jsonl"
            if p.exists():
                for r in read_jsonl(p):
                    if r.get("pmid"):
                        self._records[str(r["pmid"])] = r
        return self._records

    def corpus_record(self, pmid: str) -> dict | None:
        conn = self._db()
        if conn is not None:
            row = conn.execute("SELECT pmid, pmcid, doi, title, year, abstract FROM corpus_records WHERE pmid = ?", (pmid,)).fetchone()
            if row:
                return dict(row)
        return self._jsonl_records().get(pmid)

    def abstract(self, pmid: str) -> str | None:
        r = self.corpus_record(pmid)
        return r.get("abstract") if r else None

    def fulltext(self, pmid: str) -> str | None:
        r = self.corpus_record(pmid)
        if not r or not r.get("pmcid"):
            return None
        conn = self._db()
        if conn is not None:
            row = conn.execute("SELECT markdown FROM corpus_fulltext WHERE pmcid = ?", (r["pmcid"],)).fetchone()
            if row and row[0]:
                return row[0]
        p = self.corpus_dir / "fulltext" / "md" / f"{r['pmcid']}.md"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def web(self, slug: str) -> str | None:
        p = self.sources_dir / "web" / f"{slug}.txt"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def europepmc(self, pmid: str) -> str | None:
        p = self.sources_dir / "europepmc" / f"pmid_{pmid}.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        return " ".join(x for x in (d.get("title"), d.get("abstract")) if x)

    def text_for(self, src: dict) -> tuple[str | None, str]:
        """Return (text, description) for a source entry, or (None, why)."""
        t = src.get("type")
        if t == "pmid":
            pmid = str(src.get("pmid") or "")
            if src.get("quote_scope") == "fulltext":
                ft = self.fulltext(pmid)
                return (ft, f"full text of PMID {pmid}") if ft else (None, f"no full text on disk for PMID {pmid}")
            ab = self.abstract(pmid)
            if ab is None:
                return None, f"PMID {pmid} not in the corpus (or no database/records.jsonl found)"
            title = (self.corpus_record(pmid) or {}).get("title") or ""
            return f"{title} {ab}", f"abstract of PMID {pmid}"
        if t == "web":
            w = self.web(str(src.get("slug") or ""))
            return (w, f"web snapshot {src.get('slug')}") if w else (None, f"no web snapshot {src.get('slug')}")
        if t == "europepmc":
            e = self.europepmc(str(src.get("pmid") or ""))
            return (e, f"Europe PMC abstract {src.get('pmid')}") if e else (None, f"no Europe PMC file for PMID {src.get('pmid')}")
        return None, f"unknown source type {t!r}"


@dataclass
class Report:
    records: int = 0
    quotes: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_records(records: list[dict], texts: SourceTexts | None = None, schema: dict | None = None) -> Report:
    schema = schema or load_schema()
    texts = texts or SourceTexts()
    validator = jsonschema.Draft202012Validator(schema)
    rep = Report(records=len(records))
    ids: dict[str, int] = {}
    for i, rec in enumerate(records, 1):
        rid = rec.get("id", f"<record {i}>")
        for err in sorted(validator.iter_errors(rec), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "<root>"
            rep.errors.append(f"{rid}: schema: {loc}: {err.message}")
        if rid in ids:
            rep.errors.append(f"{rid}: duplicate id (also record {ids[rid]})")
        ids[rid] = i
    for rec in records:
        rid = rec.get("id")
        if rec.get("parent_id") and rec["parent_id"] not in ids:
            rep.errors.append(f"{rid}: parent_id {rec['parent_id']!r} is not a record id")
        for s_i, src in enumerate(rec.get("sources") or []):
            text, desc = texts.text_for(src)
            if text is None:
                rep.errors.append(f"{rid}: source {s_i}: {desc}")
                continue
            ntext = norm(text)
            for q in src.get("quotes") or []:
                rep.quotes += 1
                if norm(q) not in ntext:
                    rep.errors.append(f"{rid}: source {s_i}: quote not found verbatim in {desc}: {q[:90]!r}")
        if rec.get("kind") == "regulatory_program" and not any(s.get("type") == "pmid" for s in rec.get("sources") or []):
            rep.warnings.append(f"{rid}: company/press-sourced only (no peer-reviewed source)")
        if rec.get("status") == "completed" and not rec.get("result"):
            rep.warnings.append(f"{rid}: completed but no result recorded")
    return rep


def validate_file(path: Path, texts: SourceTexts | None = None) -> Report:
    return validate_records(read_jsonl(path), texts=texts)
