"""Build the SQLite data layer from upstream sources.

Two stages so tests can run offline:

* :func:`download_sources` fetches HAGR zips and Dog Aging Project codebooks into ``raw/``.
* :func:`build_db` reads ``raw/`` plus the canine-aging-corpus directory and writes one
  SQLite file with plain tables, an FTS5 index over the corpus, and a ``meta`` table
  recording every source, URL, and timestamp.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .paths import (
    DAP_CODEBOOK_API,
    DAP_CODEBOOK_RAW,
    HAGR_SOURCES,
    USER_AGENT,
)

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip()).strip("_").lower()
    return s or "col"


# ---------------------------------------------------------------------------------
# Stage 1: download
# ---------------------------------------------------------------------------------


def download_sources(raw_dir: Path, client: httpx.Client | None = None) -> dict:
    raw_dir.mkdir(parents=True, exist_ok=True)
    own = client is None
    client = client or httpx.Client(timeout=120, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    manifest: dict[str, dict] = {}
    try:
        for name, (url, member) in HAGR_SOURCES.items():
            resp = client.get(url)
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                data = zf.read(member)
            out = raw_dir / member
            out.write_bytes(data)
            manifest[name] = {"url": url, "file": member, "bytes": len(data), "fetched_at": _now()}
            log.info("downloaded %s (%d bytes)", member, len(data))

        listing = client.get(DAP_CODEBOOK_API)
        listing.raise_for_status()
        dap_dir = raw_dir / "dap_codebooks"
        dap_dir.mkdir(exist_ok=True)
        for entry in listing.json():
            fname = entry.get("name", "")
            if not fname.endswith(".csv"):
                continue
            resp = client.get(DAP_CODEBOOK_RAW + fname)
            resp.raise_for_status()
            (dap_dir / fname).write_bytes(resp.content)
            manifest[f"dap:{fname}"] = {"url": DAP_CODEBOOK_RAW + fname, "file": f"dap_codebooks/{fname}",
                                        "bytes": len(resp.content), "fetched_at": _now()}
            log.info("downloaded %s (%d bytes)", fname, len(resp.content))
    finally:
        if own:
            client.close()
    (raw_dir / "download_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


# ---------------------------------------------------------------------------------
# Stage 2: build
# ---------------------------------------------------------------------------------


def _read_delimited(path: Path, delimiter: str) -> tuple[list[str], list[list[str]]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    header = [_snake(h) for h in rows[0]]
    return header, [r for r in rows[1:] if any(c.strip() for c in r)]


def _create_table(conn: sqlite3.Connection, table: str, columns: list[str], extra: list[str] | None = None) -> None:
    cols = ", ".join(f'"{c}" TEXT' for c in columns + (extra or []))
    conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    conn.execute(f'CREATE TABLE "{table}" ({cols})')


def _insert_rows(conn: sqlite3.Connection, table: str, columns: list[str], rows, extra_values: list | None = None) -> int:
    ncol = len(columns) + len(extra_values or [])
    placeholders = ", ".join("?" for _ in range(ncol))
    n = 0
    for r in rows:
        r = list(r)[: len(columns)] + [""] * max(0, len(columns) - len(r))
        conn.execute(f'INSERT INTO "{table}" VALUES ({placeholders})', r + (extra_values or []))
        n += 1
    return n


def _load_hagr(conn: sqlite3.Connection, raw_dir: Path) -> dict:
    counts = {}
    spec = {
        "anage": ("anage_data.txt", "\t"),
        "drugage": ("drugage.csv", ","),
        "genage_human": ("genage_human.csv", ","),
        "genage_models": ("genage_models.csv", ","),
    }
    for table, (fname, delim) in spec.items():
        path = raw_dir / fname
        if not path.exists():
            log.warning("missing %s; skipping %s", fname, table)
            continue
        header, rows = _read_delimited(path, delim)
        _create_table(conn, table, header)
        counts[table] = _insert_rows(conn, table, header, rows)
    # AnAge: convenient scientific-name column.
    if "anage" in counts:
        conn.execute("ALTER TABLE anage ADD COLUMN scientific_name TEXT")
        conn.execute("UPDATE anage SET scientific_name = genus || ' ' || species")
        conn.execute("CREATE INDEX IF NOT EXISTS anage_sci ON anage(scientific_name)")
    if "drugage" in counts:
        conn.execute("CREATE INDEX IF NOT EXISTS drugage_species ON drugage(species)")
        conn.execute("CREATE INDEX IF NOT EXISTS drugage_compound ON drugage(compound_name)")
    return counts


_RELEASE_RE = re.compile(r"DAP_(\d{4})_CODEBOOK_v([\d.]+)\.csv")


def _load_dap(conn: sqlite3.Connection, raw_dir: Path) -> dict:
    dap_dir = raw_dir / "dap_codebooks"
    files = sorted(dap_dir.glob("DAP_*_CODEBOOK_*.csv")) if dap_dir.exists() else []
    if not files:
        log.warning("no DAP codebooks found under %s", dap_dir)
        return {}
    conn.execute("DROP TABLE IF EXISTS dap_codebook")
    conn.execute(
        """CREATE TABLE dap_codebook (
            release TEXT, release_year INTEGER, release_version TEXT,
            data_file TEXT, variable TEXT, survey_text TEXT, "values" TEXT, value_labels TEXT)"""
    )
    counts = {}
    for f in files:
        m = _RELEASE_RE.match(f.name)
        if not m:
            continue
        year, version = int(m.group(1)), m.group(2)
        release = f"{year}_v{version}"
        header, rows = _read_delimited(f, ",")
        n = 0
        for r in rows:
            vals = {h: (r[i] if i < len(r) else "") for i, h in enumerate(header)}
            conn.execute(
                "INSERT INTO dap_codebook VALUES (?,?,?,?,?,?,?,?)",
                (
                    release, year, version,
                    vals.get("datafile", ""), vals.get("variable", ""), vals.get("surveytext", ""),
                    vals.get("values", ""), vals.get("valuelabels", ""),
                ),
            )
            n += 1
        counts[release] = n
    conn.execute("CREATE INDEX IF NOT EXISTS dap_var ON dap_codebook(release, variable)")
    conn.execute("DROP TABLE IF EXISTS dap_codebook_fts")
    conn.execute(
        "CREATE VIRTUAL TABLE dap_codebook_fts USING fts5(release UNINDEXED, data_file, variable, survey_text, value_labels)"
    )
    conn.execute(
        "INSERT INTO dap_codebook_fts SELECT release, data_file, variable, survey_text, value_labels FROM dap_codebook"
    )
    return counts


def _load_corpus(conn: sqlite3.Connection, corpus_dir: Path, fulltext_licences: set[str] | None = None) -> dict:
    """Corpus records plus an FTS index, and the Markdown full text of every record whose
    licence is in ``fulltext_licences`` (``None`` = every file on disk). The published
    database is built with ``{"cc by", "cc0"}`` so it only redistributes what may be."""
    records_path = corpus_dir / "records.jsonl"
    if not records_path.exists():
        log.warning("no corpus records at %s", records_path)
        return {}
    md_dir = corpus_dir / "fulltext" / "md"
    md_on_disk = {p.stem for p in md_dir.glob("PMC*.md")} if md_dir.exists() else set()
    allowed = None if fulltext_licences is None else {s.strip().lower() for s in fulltext_licences}
    stored: set[str] = set()

    conn.execute("DROP TABLE IF EXISTS corpus_fulltext")
    conn.execute("CREATE TABLE corpus_fulltext (pmcid TEXT PRIMARY KEY, license TEXT, chars INTEGER, markdown TEXT)")
    conn.execute("DROP TABLE IF EXISTS corpus_records")
    conn.execute(
        """CREATE TABLE corpus_records (
            key TEXT PRIMARY KEY, source TEXT, id TEXT, pmid TEXT, pmcid TEXT, doi TEXT,
            title TEXT, abstract TEXT, journal TEXT, year INTEGER, first_publication_date TEXT,
            pub_types TEXT, is_open_access INTEGER, license TEXT, cited_by_count INTEGER,
            tiers TEXT, keywords TEXT, mesh TEXT, mesh_major TEXT, has_fulltext_md INTEGER, retrieved_at TEXT)"""
    )
    conn.execute("DROP TABLE IF EXISTS corpus_fts")
    conn.execute(
        "CREATE VIRTUAL TABLE corpus_fts USING fts5(key UNINDEXED, title, abstract, keywords, mesh, tokenize='porter unicode61')"
    )
    n = 0
    with records_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            mesh_list = [m for m in (r.get("mesh") or []) if isinstance(m, dict) and m.get("descriptor")]
            mesh_all = "; ".join(m["descriptor"] for m in mesh_list)
            mesh_major = "; ".join(m["descriptor"] for m in mesh_list if m.get("major"))
            # Europe PMC occasionally emits null entries inside keyword/pub-type lists.
            keywords = "; ".join(str(k) for k in (r.get("keywords") or []) if k)
            pub_types = ";".join(str(p) for p in (r.get("pub_types") or []) if p)
            tiers = ";".join(r.get("tiers") or [])
            pmcid = r.get("pmcid")
            licence = (r.get("license") or "").strip().lower()
            if pmcid and pmcid in md_on_disk and pmcid not in stored and (allowed is None or licence in allowed):
                text = (md_dir / f"{pmcid}.md").read_text(encoding="utf-8")
                conn.execute("INSERT INTO corpus_fulltext VALUES (?,?,?,?)", (pmcid, licence or None, len(text), text))
                stored.add(pmcid)
            conn.execute(
                "INSERT INTO corpus_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    r["key"], r.get("source"), r.get("id"), r.get("pmid"), pmcid, r.get("doi"),
                    r.get("title"), r.get("abstract"), r.get("journal"), r.get("year"),
                    r.get("first_publication_date"), pub_types,
                    1 if r.get("is_open_access") else 0, r.get("license"), r.get("cited_by_count"),
                    tiers, keywords, mesh_all, mesh_major, 1 if pmcid in stored else 0,
                    r.get("retrieved_at"),
                ),
            )
            conn.execute(
                "INSERT INTO corpus_fts VALUES (?,?,?,?,?)",
                (r["key"], r.get("title") or "", r.get("abstract") or "", keywords, mesh_all),
            )
            n += 1
    conn.execute("CREATE INDEX IF NOT EXISTS corpus_year ON corpus_records(year)")
    conn.execute("CREATE INDEX IF NOT EXISTS corpus_pmcid ON corpus_records(pmcid)")
    version = {}
    vf = corpus_dir / "corpus_version.json"
    if vf.exists():
        version = json.loads(vf.read_text(encoding="utf-8"))
    return {"records": n, "with_fulltext_md": len(stored), "fulltext_on_disk": len(md_on_disk),
            "fulltext_licences": "all" if allowed is None else sorted(allowed),
            "corpus_version": version.get("corpus_version"), "records_sha256": version.get("records_sha256")}


def _load_foi(conn: sqlite3.Connection, foi_path: Path | None) -> dict:
    """FDA FOI summaries for dog products (from the foi-summaries dataset): ``foi_dog`` holds
    the fields an agent searches on; ``foi_records`` keeps each full record (section text,
    General Information) verbatim so the built database is self-contained."""
    if not foi_path or not foi_path.exists():
        log.info("no FOI dataset at %s; skipping", foi_path)
        return {}
    conn.execute("DROP TABLE IF EXISTS foi_records")
    conn.execute("CREATE TABLE foi_records (foi_id INTEGER PRIMARY KEY, record TEXT)")
    conn.execute("DROP TABLE IF EXISTS foi_dog")
    conn.execute(
        """CREATE TABLE foi_dog (
            foi_id INTEGER PRIMARY KEY, application_number TEXT, proprietary_name TEXT, ingredients TEXT,
            sponsor TEXT, approval_type TEXT, approval_date TEXT, catalogue_summary TEXT,
            established_name TEXT, recommended_dosage TEXT, indications TEXT, route TEXT, dosage_form TEXT,
            species_class TEXT, pk_sentences TEXT, safety_sentences TEXT, dose_mentions TEXT,
            sections_found TEXT, likely_scanned INTEGER, pdf_url TEXT, species_flag TEXT)"""
    )
    n = 0
    with foi_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            p = r.get("parsed") or {}
            gi = p.get("general_information") or {}
            conn.execute(
                "INSERT OR REPLACE INTO foi_dog VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    r["foi_id"], r.get("application_number"),
                    r.get("proprietary_name") or gi.get("proprietary_name") or gi.get("trade_name"),
                    r.get("ingredients"), r.get("sponsor"), r.get("approval_type"), r.get("approval_date"),
                    r.get("catalogue_summary"), gi.get("established_name") or gi.get("generic_name"),
                    gi.get("recommended_dosage") or gi.get("recommended_dose") or gi.get("dosage"),
                    gi.get("indications") or gi.get("indications_for_use") or gi.get("indication"),
                    gi.get("route_of_administration"), gi.get("dosage_form"), gi.get("species_class") or gi.get("species"),
                    json.dumps(p.get("pk_sentences") or []), json.dumps(p.get("safety_sentences") or []),
                    json.dumps(p.get("dose_mentions") or []), ";".join(p.get("sections_found") or []),
                    1 if (r.get("text") or {}).get("likely_scanned") else 0, r.get("pdf_url"),
                    r.get("species_flag") or "unknown",
                ),
            )
            conn.execute("INSERT OR REPLACE INTO foi_records VALUES (?, ?)", (r["foi_id"], line.strip()))
            n += 1
    conn.execute("CREATE INDEX IF NOT EXISTS foi_ing ON foi_dog(ingredients)")
    return {"records": n, "path": str(foi_path)}


def _load_foi_structured(conn: sqlite3.Connection, path: Path | None) -> dict:
    """Typed, quote-grounded extraction records (foi-summaries ``structured_dog.jsonl``)."""
    if not path or not path.exists():
        log.info("no structured FOI file at %s; skipping", path)
        return {}
    conn.execute("DROP TABLE IF EXISTS foi_structured")
    conn.execute(
        """CREATE TABLE foi_structured (
            foi_id INTEGER PRIMARY KEY, application_number TEXT, product_name TEXT, ingredient TEXT,
            species_class TEXT, indication TEXT, dose TEXT, route TEXT, frequency TEXT, duration_or_conditions TEXT,
            dose_quote TEXT, pharmacokinetics TEXT, target_animal_safety TEXT, effectiveness TEXT,
            adverse_reactions TEXT, notes TEXT, extracted_by TEXT)"""
    )
    n = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            dr = r.get("dose_regimen") or {}
            conn.execute(
                "INSERT OR REPLACE INTO foi_structured VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    int(r["foi_id"]), r.get("application_number"), r.get("product_name"), r.get("ingredient"),
                    r.get("species_class"), (r.get("indication") or {}).get("text"), dr.get("dose"), dr.get("route"),
                    dr.get("frequency"), dr.get("duration_or_conditions"), dr.get("quote"),
                    json.dumps(r.get("pharmacokinetics") or []), json.dumps(r.get("target_animal_safety")),
                    json.dumps(r.get("effectiveness")), json.dumps(r.get("adverse_reactions") or []),
                    r.get("notes"), r.get("extracted_by"),
                ),
            )
            n += 1
    conn.execute("CREATE INDEX IF NOT EXISTS foi_structured_ing ON foi_structured(ingredient)")
    return {"records": n, "path": str(path)}


def _load_trials(conn: sqlite3.Connection, path: Path | None) -> dict:
    """Canine aging trial registry (canine-trials ``canine_trials.jsonl``): one row per study with
    the searchable fields flattened and the full record kept as JSON."""
    if not path or not path.exists():
        log.info("no trial registry at %s; skipping", path)
        return {}
    conn.execute("DROP TABLE IF EXISTS trials")
    conn.execute(
        """CREATE TABLE trials (
            id TEXT PRIMARY KEY, name TEXT, acronym TEXT, kind TEXT, status TEXT, setting TEXT,
            intervention TEXT, intervention_class TEXT, comparator TEXT, start_year INTEGER, end_year INTEGER,
            n INTEGER, breed TEXT, age TEXT, primary_outcome TEXT, result TEXT, lead_organization TEXT,
            tags TEXT, pmids TEXT, summary TEXT, record TEXT)"""
    )
    n = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            pop = r.get("population") or {}
            pmids = ";".join(str(s.get("pmid")) for s in r.get("sources") or [] if s.get("pmid"))
            conn.execute(
                "INSERT OR REPLACE INTO trials VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    r["id"], r.get("name"), r.get("acronym"), r.get("kind"), r.get("status"), r.get("setting"),
                    r.get("intervention"), r.get("intervention_class"), r.get("comparator"), r.get("start_year"), r.get("end_year"),
                    pop.get("n"), pop.get("breed"), pop.get("age"), r.get("primary_outcome"), r.get("result"),
                    r.get("lead_organization"), ";".join(r.get("tags") or []), pmids, r.get("summary"), json.dumps(r, ensure_ascii=False),
                ),
            )
            n += 1
    return {"records": n, "path": str(path)}


def build_db(raw_dir: Path, corpus_dir: Path, db_path: Path, foi_path: Path | None = None,
             foi_structured_path: Path | None = None, fulltext_licences: set[str] | None = None,
             trials_path: Path | None = None) -> dict:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".building.sqlite")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    try:
        summary = {
            "built_at": _now(),
            "hagr": _load_hagr(conn, raw_dir),
            "dap_codebooks": _load_dap(conn, raw_dir),
            "corpus": _load_corpus(conn, corpus_dir, fulltext_licences),
            "foi": _load_foi(conn, foi_path),
            "foi_structured": _load_foi_structured(conn, foi_structured_path),
            "trials": _load_trials(conn, trials_path),
        }
        dl = raw_dir / "download_manifest.json"
        summary["downloads"] = json.loads(dl.read_text(encoding="utf-8")) if dl.exists() else {}
        conn.execute("DROP TABLE IF EXISTS meta")
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO meta VALUES ('build', ?)", (json.dumps(summary),))
        conn.execute("DROP TABLE IF EXISTS ensembl_cache")
        conn.execute("CREATE TABLE ensembl_cache (key TEXT PRIMARY KEY, value TEXT, fetched_at TEXT)")
        conn.commit()
    finally:
        conn.close()
    if db_path.exists():
        db_path.unlink()
    tmp.rename(db_path)
    return summary
