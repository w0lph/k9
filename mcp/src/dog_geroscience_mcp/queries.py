"""Pure query functions over the built SQLite database.

Every function takes an open ``sqlite3.Connection`` and returns JSON-serialisable data,
so they are testable without MCP and reusable from other code.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

# AnAge lists the domestic dog as Canis familiaris (common name "Domestic dog");
# DrugAge uses "Canis lupus familiaris". Aliases map either form to the AnAge name.
DOG = "Canis familiaris"

ANAGE_ALIASES: dict[str, str] = {
    "dog": DOG,
    "dogs": DOG,
    "domestic dog": DOG,
    "canis familiaris": DOG,
    "canis lupus familiaris": DOG,
    "wolf": "Canis lupus",
    "gray wolf": "Canis lupus",
    "grey wolf": "Canis lupus",
    "human": "Homo sapiens",
    "humans": "Homo sapiens",
    "mouse": "Mus musculus",
    "house mouse": "Mus musculus",
    "rat": "Rattus norvegicus",
    "norway rat": "Rattus norvegicus",
    "cat": "Felis catus",
    "domestic cat": "Felis catus",
    "naked mole rat": "Heterocephalus glaber",
    "naked mole-rat": "Heterocephalus glaber",
}


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(cur: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in ("", None)}


def _fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression (quoted terms, implicit AND)."""
    terms = [t.replace('"', "") for t in text.replace("-", " ").split()]
    return " ".join(f'"{t}"' for t in terms if t)


# -- meta -------------------------------------------------------------------------


def build_info(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT value FROM meta WHERE key='build'").fetchone()
    return json.loads(row[0]) if row else {}


def has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?", (name,)).fetchone() is not None


# -- FDA FOI summaries (dog products) ------------------------------------------------


def foi_search(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[dict]:
    """FOI summaries for dog products whose ingredient, proprietary name or General
    Information block matches the query (substring on ingredient/name, FTS on the parsed
    fields). Returns catalogue metadata plus recommended dosage / indication / PK candidates."""
    if not has_table(conn, "foi_dog"):
        return []
    q = f"%{query.strip()}%"
    rows = _rows(
        conn.execute(
            """SELECT foi_id, application_number, proprietary_name, ingredients, sponsor, approval_type,
                      approval_date, catalogue_summary, recommended_dosage, indications, route,
                      dosage_form, pk_sentences, safety_sentences, pdf_url, likely_scanned, species_flag
               FROM foi_dog WHERE ingredients LIKE ? OR proprietary_name LIKE ? OR indications LIKE ?
               ORDER BY CASE species_flag WHEN 'dog' THEN 0 WHEN 'unknown' THEN 1 ELSE 2 END, approval_date DESC LIMIT ?""",
            (q, q, q, limit),
        )
    )
    for r in rows:
        for k in ("pk_sentences", "safety_sentences"):
            try:
                r[k] = json.loads(r[k]) if r.get(k) else []
            except (TypeError, json.JSONDecodeError):
                r[k] = []
        r["likely_scanned"] = bool(r.get("likely_scanned"))
    return [_clean(r) for r in rows]


# -- AnAge ------------------------------------------------------------------------


def anage_species(conn: sqlite3.Connection, query: str = DOG, limit: int = 5) -> list[dict]:
    query = ANAGE_ALIASES.get(query.strip().lower(), query.strip())
    q = f"%{query}%"
    cur = conn.execute(
        """SELECT * FROM anage
           WHERE scientific_name LIKE ? OR common_name LIKE ? OR genus LIKE ?
           ORDER BY CASE WHEN scientific_name = ? COLLATE NOCASE THEN 0
                         WHEN common_name = ? COLLATE NOCASE THEN 1 ELSE 2 END,
                    scientific_name LIMIT ?""",
        (q, q, q, query, query, limit),
    )
    return [_clean(r) for r in _rows(cur)]


# -- DrugAge ----------------------------------------------------------------------


def drugage_search(
    conn: sqlite3.Connection,
    compound: str | None = None,
    species: str | None = None,
    itp_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    where, params = [], []
    if compound:
        where.append("compound_name LIKE ?")
        params.append(f"%{compound.strip()}%")
    if species:
        where.append("species LIKE ?")
        params.append(f"%{species.strip()}%")
    if itp_only:
        where.append("itp = 'Yes'")
    sql = "SELECT * FROM drugage"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY compound_name, species LIMIT ?"
    params.append(limit)
    return [_clean(r) for r in _rows(conn.execute(sql, params))]


def drugage_species_summary(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute(
        "SELECT species, COUNT(*) AS experiments, COUNT(DISTINCT compound_name) AS compounds FROM drugage GROUP BY species ORDER BY experiments DESC"
    )
    return _rows(cur)


# -- GenAge -----------------------------------------------------------------------


def genage_search(conn: sqlite3.Connection, query: str, limit: int = 25) -> dict:
    q = f"%{query.strip()}%"
    exact = query.strip().upper()
    human = _rows(
        conn.execute(
            """SELECT * FROM genage_human WHERE symbol LIKE ? OR name LIKE ? OR entrez_gene_id = ?
               ORDER BY CASE WHEN UPPER(symbol) = ? THEN 0 ELSE 1 END, symbol LIMIT ?""",
            (q, q, query.strip(), exact, limit),
        )
    )
    models = _rows(
        conn.execute(
            """SELECT * FROM genage_models WHERE symbol LIKE ? OR name LIKE ?
               ORDER BY CASE WHEN UPPER(symbol) = ? THEN 0 ELSE 1 END, symbol LIMIT ?""",
            (q, q, exact, limit),
        )
    )
    return {"human": [_clean(r) for r in human], "model_organisms": [_clean(r) for r in models]}


# -- DAP codebooks ----------------------------------------------------------------


def dap_releases(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn.execute(
            "SELECT release, release_year, release_version, COUNT(*) AS variables, COUNT(DISTINCT data_file) AS data_files FROM dap_codebook GROUP BY release ORDER BY release_year DESC, release_version DESC"
        )
    )


def _resolve_release(conn: sqlite3.Connection, release: str | None) -> str | None:
    rels = dap_releases(conn)
    if not rels:
        return None
    if not release or release == "latest":
        return rels[0]["release"]
    for r in rels:
        if r["release"] == release or str(r["release_year"]) == release:
            return r["release"]
    return rels[0]["release"]


def dap_codebook_search(
    conn: sqlite3.Connection,
    query: str,
    release: str | None = "latest",
    data_file: str | None = None,
    limit: int = 25,
) -> dict:
    rel = _resolve_release(conn, release)
    if rel is None:
        return {"release": None, "results": []}
    match = _fts_query(query)
    sql = """SELECT c.release, c.data_file, c.variable, c.survey_text, c."values", c.value_labels,
                    bm25(dap_codebook_fts) AS rank
             FROM dap_codebook_fts f JOIN dap_codebook c
               ON c.release = f.release AND c.variable = f.variable AND c.data_file = f.data_file
             WHERE dap_codebook_fts MATCH ? AND f.release = ?"""
    params: list = [match, rel]
    if data_file:
        sql += " AND c.data_file LIKE ?"
        params.append(f"%{data_file}%")
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    try:
        rows = _rows(conn.execute(sql, params))
    except sqlite3.OperationalError:
        rows = []
    for r in rows:
        r.pop("rank", None)
    return {"release": rel, "query": query, "results": [_clean(r) for r in rows]}


def dap_variable(conn: sqlite3.Connection, variable: str, release: str | None = "latest") -> dict:
    rel = _resolve_release(conn, release)
    row = conn.execute(
        'SELECT release, data_file, variable, survey_text, "values", value_labels FROM dap_codebook WHERE release = ? AND variable = ? COLLATE NOCASE',
        (rel, variable),
    ).fetchone()
    present_in = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT release FROM dap_codebook WHERE variable = ? COLLATE NOCASE ORDER BY release_year DESC",
            (variable,),
        ).fetchall()
    ]
    return {"release": rel, "variable": _clean(dict(row)) if row else None, "present_in_releases": present_in}


def foi_structured_search(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[dict]:
    """Typed FOI extraction records (dose regimen, PK values, target-animal-safety design and
    findings, effectiveness, adverse reactions), each value carrying its verbatim quote.
    Matches ingredient, product name or indication (substring)."""
    if not has_table(conn, "foi_structured"):
        return []
    q = f"%{query.strip()}%"
    rows = _rows(
        conn.execute(
            """SELECT * FROM foi_structured WHERE ingredient LIKE ? OR product_name LIKE ? OR indication LIKE ?
               ORDER BY foi_id DESC LIMIT ?""",
            (q, q, q, limit),
        )
    )
    out = []
    for r in rows:
        for k in ("pharmacokinetics", "target_animal_safety", "effectiveness", "adverse_reactions"):
            try:
                r[k] = json.loads(r[k]) if r.get(k) else None
            except (TypeError, json.JSONDecodeError):
                r[k] = None
        r["dose_regimen"] = {k: r.pop(k, None) for k in ("dose", "route", "frequency", "duration_or_conditions")} | {"quote": r.pop("dose_quote", None)}
        out.append(_clean(r))
    return out


# -- Trial registry ---------------------------------------------------------------


def trial_search(conn: sqlite3.Connection, query: str = "", limit: int = 10, trial_id: str | None = None,
                 status: str | None = None) -> list[dict]:
    """Canine aging trial registry records. ``query`` matches name, acronym, intervention,
    summary, tags or cited PMIDs (substring, case-insensitive); ``trial_id`` fetches one record;
    ``status`` filters (completed, ongoing, planned, unknown). Returns the full typed records
    with their verbatim source quotes."""
    if not has_table(conn, "trials"):
        return []
    if trial_id:
        rows = conn.execute("SELECT record FROM trials WHERE id = ?", (trial_id,)).fetchall()
    else:
        q = f"%{(query or '').strip()}%"
        sql = ("SELECT record FROM trials WHERE (name LIKE ? OR acronym LIKE ? OR intervention LIKE ? OR summary LIKE ? "
               "OR tags LIKE ? OR pmids LIKE ? OR kind LIKE ?)")
        params: list = [q, q, q, q, q, q, q]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY COALESCE(start_year, end_year, 0) DESC, name LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
    return [json.loads(r[0]) for r in rows]


def trial_stats(conn: sqlite3.Connection) -> dict:
    if not has_table(conn, "trials"):
        return {"records": 0}
    out = {"records": conn.execute("SELECT COUNT(*) FROM trials").fetchone()[0]}
    for col in ("kind", "status", "intervention_class"):
        out[col] = {k or "null": v for k, v in conn.execute(f"SELECT {col}, COUNT(*) FROM trials GROUP BY {col}")}
    return out


# -- Corpus -----------------------------------------------------------------------


def corpus_search(
    conn: sqlite3.Connection,
    query: str,
    tier: str | None = "core",
    year_from: int | None = None,
    year_to: int | None = None,
    open_access_only: bool = False,
    limit: int = 20,
) -> list[dict]:
    match = _fts_query(query)
    sql = """SELECT r.key, r.title, r.year, r.journal, r.pmid, r.pmcid, r.doi, r.is_open_access,
                    r.has_fulltext_md, r.tiers, r.cited_by_count, r.pub_types,
                    snippet(corpus_fts, 2, '[', ']', '…', 24) AS snippet,
                    bm25(corpus_fts, 5.0, 1.0, 2.0, 2.0) AS rank
             FROM corpus_fts f JOIN corpus_records r ON r.key = f.key
             WHERE corpus_fts MATCH ?"""
    params: list = [match]
    if tier:
        sql += " AND (';' || r.tiers || ';') LIKE ?"
        params.append(f"%;{tier};%")
    if year_from:
        sql += " AND r.year >= ?"
        params.append(year_from)
    if year_to:
        sql += " AND r.year <= ?"
        params.append(year_to)
    if open_access_only:
        sql += " AND r.is_open_access = 1"
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    try:
        rows = _rows(conn.execute(sql, params))
    except sqlite3.OperationalError as exc:
        return [{"error": f"bad query: {exc}"}]
    out = []
    for r in rows:
        r.pop("rank", None)
        r["is_open_access"] = bool(r["is_open_access"])
        r["has_fulltext_md"] = bool(r["has_fulltext_md"])
        out.append(_clean(r))
    return out


def corpus_match(conn: sqlite3.Connection, match_expr: str, tier: str | None = None, limit: int = 20) -> list[dict]:
    """corpus_search with a raw FTS5 MATCH expression (caller quotes terms), e.g.
    ``'"rapamycin" AND ("trial" OR "randomized" OR "placebo")'``."""
    sql = """SELECT r.key, r.title, r.year, r.journal, r.pmid, r.pmcid, r.doi, r.is_open_access,
                    r.has_fulltext_md, r.tiers, r.cited_by_count, r.pub_types,
                    snippet(corpus_fts, 2, '[', ']', '…', 24) AS snippet
             FROM corpus_fts f JOIN corpus_records r ON r.key = f.key
             WHERE corpus_fts MATCH ?"""
    params: list = [match_expr]
    if tier:
        sql += " AND (';' || r.tiers || ';') LIKE ?"
        params.append(f"%;{tier};%")
    sql += " ORDER BY bm25(corpus_fts, 5.0, 1.0, 2.0, 2.0) LIMIT ?"
    params.append(limit)
    try:
        rows = _rows(conn.execute(sql, params))
    except sqlite3.OperationalError as exc:
        return [{"error": f"bad match expression: {exc}"}]
    for r in rows:
        r["is_open_access"] = bool(r["is_open_access"])
        r["has_fulltext_md"] = bool(r["has_fulltext_md"])
    return [_clean(r) for r in rows]


def corpus_count(conn: sqlite3.Connection, query: str, tier: str | None = None) -> int:
    """Number of corpus records whose title/abstract/keywords/MeSH match the query."""
    match = _fts_query(query)
    sql = "SELECT COUNT(*) FROM corpus_fts f JOIN corpus_records r ON r.key = f.key WHERE corpus_fts MATCH ?"
    params: list = [match]
    if tier:
        sql += " AND (';' || r.tiers || ';') LIKE ?"
        params.append(f"%;{tier};%")
    try:
        return int(conn.execute(sql, params).fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def corpus_record(conn: sqlite3.Connection, key: str) -> dict | None:
    row = conn.execute("SELECT * FROM corpus_records WHERE key = ? OR pmid = ? OR pmcid = ? OR doi = ?", (key, key, key, key)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["is_open_access"] = bool(d["is_open_access"])
    d["has_fulltext_md"] = bool(d["has_fulltext_md"])
    return _clean(d)


def corpus_fulltext(conn: sqlite3.Connection, corpus_dir: Path | None, pmcid: str, max_chars: int = 20000) -> dict | None:
    """Markdown full text: from the ``corpus_fulltext`` table when the build stored it,
    otherwise from the corpus directory on disk (source checkouts)."""
    text: str | None = None
    if has_table(conn, "corpus_fulltext"):
        row = conn.execute("SELECT markdown FROM corpus_fulltext WHERE pmcid = ?", (pmcid,)).fetchone()
        if row is not None:
            text = row["markdown"]
    if text is None and corpus_dir is not None:
        path = corpus_dir / "fulltext" / "md" / f"{pmcid}.md"
        if path.exists():
            text = path.read_text(encoding="utf-8")
    if text is None:
        return None
    truncated = len(text) > max_chars
    return {"pmcid": pmcid, "chars": len(text), "truncated": truncated, "markdown": text[:max_chars]}


def corpus_stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM corpus_records").fetchone()[0]
    core = conn.execute("SELECT COUNT(*) FROM corpus_records WHERE (';'||tiers||';') LIKE '%;core;%'").fetchone()[0]
    oa = conn.execute("SELECT COUNT(*) FROM corpus_records WHERE is_open_access = 1").fetchone()[0]
    ft = conn.execute("SELECT COUNT(*) FROM corpus_records WHERE has_fulltext_md = 1").fetchone()[0]
    years = _rows(conn.execute("SELECT year, COUNT(*) AS n FROM corpus_records WHERE year IS NOT NULL GROUP BY year ORDER BY year"))
    return {"records": total, "core": core, "open_access": oa, "with_fulltext_md": ft,
            "by_year": {str(y["year"]): y["n"] for y in years}}
