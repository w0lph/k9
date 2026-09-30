"""Source discovery and quote extraction helpers for question authors."""

from __future__ import annotations

import re
from pathlib import Path

from .common import CORPUS_DIR, DB_PATH, connect_db, load_records, norm_text, read_fulltext

STOP = {
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "with", "by", "from", "as", "at",
    "is", "are", "was", "were", "be", "been", "this", "that", "these", "those", "into", "than", "vs",
    "what", "which", "how", "many", "did", "does", "do", "according", "study", "dogs", "dog",
}


def fts_query(text: str, mode: str = "or") -> str:
    words = re.sub(r"[^\w\s-]", " ", text).replace("-", " ").split()
    terms = [t for t in words if t.lower() not in STOP and len(t) > 1]
    if not terms:  # query was all stopwords; fall back to every word
        terms = [t for t in words if len(t) > 1] or ["dog"]
    joiner = " OR " if mode == "or" else " "
    return joiner.join(f'"{t}"' for t in terms)


def search(query: str, tier: str | None = "core", limit: int = 10, fulltext_only: bool = False, db_path: Path = DB_PATH) -> list[dict]:
    conn = connect_db(db_path)
    sql = """SELECT r.key, r.year, r.title, r.pmid, r.pmcid, r.doi, r.journal, r.cited_by_count, r.has_fulltext_md, r.tiers, r.pub_types
             FROM corpus_fts f JOIN corpus_records r ON r.key = f.key WHERE corpus_fts MATCH ?"""
    params: list = [fts_query(query, "and")]
    if tier:
        sql += " AND (';' || r.tiers || ';') LIKE ?"
        params.append(f"%;{tier};%")
    if fulltext_only:
        sql += " AND r.has_fulltext_md = 1"
    sql += " ORDER BY bm25(corpus_fts, 5.0, 1.0, 2.0, 2.0) LIMIT ?"
    params.append(limit)
    rows = [dict(r) for r in conn.execute(sql, params)]
    if not rows:  # fall back to OR semantics
        params[0] = fts_query(query, "or")
        rows = [dict(r) for r in conn.execute(sql, params)]
    conn.close()
    return rows


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(norm_text(text)) if s.strip()]


def quote_candidates(key: str, phrase: str, corpus_dir: Path = CORPUS_DIR, max_hits: int = 12) -> list[tuple[str, str]]:
    """Sentences containing ``phrase`` (case-insensitive) in the record's abstract, then full text.

    Returns (location, sentence) pairs whose sentence text is guaranteed to pass the validator
    for that location.
    """
    recs = load_records(corpus_dir)
    rec = recs.get(key)
    if rec is None:
        raise KeyError(key)
    out: list[tuple[str, str]] = []
    p = phrase.lower()
    abstract = (rec.get("title") or "") + ". " + (rec.get("abstract") or "")
    for s in sentences(abstract):
        if p in s.lower():
            out.append(("abstract", s))
    body = read_fulltext(corpus_dir, rec.get("pmcid"))
    if body:
        for s in sentences(re.sub(r"^#+ .*$", "", body, flags=re.MULTILINE)):
            if p in s.lower() and len(out) < max_hits:
                out.append(("fulltext", s))
    return out[:max_hits]
