"""Shared paths, corpus access, and text normalisation."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = Path(os.environ.get("CGQ_CORPUS", PROJECT_ROOT.parent / "corpus" / "data"))
DB_PATH = Path(os.environ.get("CGQ_DB", PROJECT_ROOT.parent / "mcp" / "data" / "dog_geroscience.sqlite"))
DATA_DIR = PROJECT_ROOT / "data"

CATEGORIES = [
    "lifespan_epidemiology",   # life tables, life expectancy, breed/size mortality patterns
    "body_size_genetics",      # size–lifespan trade-off, IGF1, breed genetics of longevity
    "interventions",           # rapamycin, diet restriction, drugs, supplements, trials
    "biomarkers_clocks",       # epigenetic clocks, blood/metabolomic biomarkers of age
    "cognition",               # canine cognitive dysfunction, cognitive testing
    "frailty_hrql",            # frailty instruments, healthspan, quality of life
    "dap_methods",             # Dog Aging Project design, cohorts, instruments, data quality
    "translational_model",     # dogs as a model of human aging; comparative arguments
    "immunity_microbiome",     # immunosenescence, inflammaging, microbiome, metabolome
    "disease_mortality",       # causes of death, multimorbidity, sex/neuter effects
]

ANSWER_TYPES = ["numeric", "categorical", "short_text", "list", "boolean"]
STATUSES = ["draft", "validated", "reviewed"]

_WS = re.compile(r"\s+")
_TAG = re.compile(r"</?[A-Za-z][^<>]{0,40}>")  # inline HTML that Europe PMC leaves in abstracts
_MARK = re.compile(r"[\^~*]")  # Markdown emphasis/super/subscript markers from the JATS converter


def strip_markup(s: str) -> str:
    """Remove inline HTML tags and Markdown markers; keeps the readable text."""
    return _WS.sub(" ", _MARK.sub("", _TAG.sub("", s))).strip()


def norm_text(s: str) -> str:
    """Whitespace-collapsed, NFKC-normalised, typographic quotes/dashes folded, markup dropped.

    Used on both the quote and the source text, so a quote copied with or without the
    source's ``<i>``/``<sub>`` tags or ``*``/``^``/``~`` markers still matches.
    """
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace(" ", " ")
    s = _MARK.sub("", _TAG.sub("", s))
    return _WS.sub(" ", s).strip()


def norm_question(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", norm_text(s).lower())


@lru_cache(maxsize=1)
def load_records(corpus_dir: Path = CORPUS_DIR) -> dict[str, dict]:
    path = corpus_dir / "records.jsonl"
    recs: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                recs[r["key"]] = r
    return recs


def fulltext_path(corpus_dir: Path, pmcid: str | None) -> Path | None:
    if not pmcid:
        return None
    p = corpus_dir / "fulltext" / "md" / f"{pmcid}.md"
    return p if p.exists() else None


def read_fulltext(corpus_dir: Path, pmcid: str | None) -> str | None:
    p = fulltext_path(corpus_dir, pmcid)
    if p is None:
        return None
    text = p.read_text(encoding="utf-8")
    _, _, body = text.partition("\n---\n")
    return body


def connect_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def read_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{i}: invalid JSON: {exc}") from exc
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
