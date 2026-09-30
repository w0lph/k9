"""Pipeline steps: fetch-metadata, fetch-fulltext, convert, manifest.

Every step is idempotent: re-running merges new records, skips full texts already on
disk (unless forced), and rewrites derived files from the current state.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from . import __version__
from .config import QUERIES, DataPaths
from .europepmc import EuropePMCClient
from .jats import jats_to_markdown
from .ncbi import NCBIClient
from .records import merge, normalise, read_jsonl, write_jsonl

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------------
# Step 1: metadata
# ---------------------------------------------------------------------------------


@dataclass
class FetchStats:
    tier: str
    hit_count: int
    fetched: int
    pages: int


def _write_records(paths: DataPaths, records: dict[str, dict]) -> int:
    ordered = sorted(records.values(), key=lambda r: (r.get("year") or 0, r["key"]), reverse=True)
    return write_jsonl(paths.records, ordered)


def _run_stamp(iso: str) -> str:
    return iso.replace(":", "").replace("-", "")


def _stamp_to_iso(stamp: str) -> str:
    try:
        return datetime.strptime(stamp, "%Y%m%dT%H%M%S%z").isoformat()
    except ValueError:
        return stamp


def fetch_metadata(
    paths: DataPaths,
    tiers: list[str] | None = None,
    page_size: int = 200,
    client: EuropePMCClient | None = None,
) -> list[FetchStats]:
    """Run each tier's query; records.jsonl is rewritten after every tier and on failure,
    so an interrupted run never loses completed tiers (and raw pages are always kept)."""
    paths.ensure()
    tiers = tiers or list(QUERIES)
    own_client = client is None
    client = client or EuropePMCClient()
    retrieved_at = _now()
    run_stamp = _run_stamp(retrieved_at)

    existing = {r["key"]: r for r in read_jsonl(paths.records)}
    stats: list[FetchStats] = []
    try:
        for tier in tiers:
            query = QUERIES[tier]
            out_dir = paths.raw_search / tier / run_stamp
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "query.txt").write_text(query, encoding="utf-8")
            n = 0
            pages = 0
            hit_count = 0
            for i, page in enumerate(client.search_iter(query, page_size=page_size)):
                pages += 1
                hit_count = page.hit_count
                raw_path = out_dir / f"page_{i:04d}.json"
                raw_path.write_text(json.dumps(page.raw, ensure_ascii=False), encoding="utf-8")
                rel = str(raw_path.relative_to(paths.root)).replace("\\", "/")
                for result in page.results:
                    rec = normalise(result, tier, retrieved_at, rel)
                    key = rec["key"]
                    existing[key] = merge(existing[key], rec) if key in existing else rec
                    n += 1
                log.info("%s: page %d (%d results, %d/%d)", tier, i, len(page.results), n, hit_count)
            stats.append(FetchStats(tier=tier, hit_count=hit_count, fetched=n, pages=pages))
            _write_records(paths, existing)
    finally:
        _write_records(paths, existing)
        if own_client:
            client.close()
    return stats


def rebuild_records(paths: DataPaths) -> dict:
    """Rebuild records.jsonl purely from raw search pages on disk.

    Runs are replayed in chronological order so the newest metadata wins and every tier
    a record was ever returned for is retained. Use after an interrupted fetch, or to
    re-normalise after a change to :func:`records.normalise`.
    """
    records: dict[str, dict] = {}
    pages_read = 0
    runs: list[tuple[str, str, Path]] = []  # (stamp, tier, run_dir)
    if paths.raw_search.exists():
        for tier_dir in sorted(p for p in paths.raw_search.iterdir() if p.is_dir()):
            for run_dir in sorted(p for p in tier_dir.iterdir() if p.is_dir()):
                runs.append((run_dir.name, tier_dir.name, run_dir))
    runs.sort(key=lambda t: t[0])
    for stamp, tier, run_dir in runs:
        retrieved_at = _stamp_to_iso(stamp)
        for raw_path in sorted(run_dir.glob("page_*.json")):
            data = json.loads(raw_path.read_text(encoding="utf-8"))
            rel = str(raw_path.relative_to(paths.root)).replace("\\", "/")
            for result in data.get("resultList", {}).get("result", []) or []:
                rec = normalise(result, tier, retrieved_at, rel)
                key = rec["key"]
                records[key] = merge(records[key], rec) if key in records else rec
            pages_read += 1
    n = _write_records(paths, records)
    by_tier = {t: sum(1 for r in records.values() if t in r["tiers"]) for t in QUERIES}
    return {"runs": len(runs), "pages": pages_read, "records": n, "by_tier": by_tier}


# ---------------------------------------------------------------------------------
# Step 2: full text
# ---------------------------------------------------------------------------------


def _fulltext_candidates(records: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in records:
        pmcid = r.get("pmcid")
        if pmcid and pmcid not in seen:
            seen.add(pmcid)
            out.append(pmcid)
    return out


class ServiceDown(Exception):
    """Raised by the full-text fetch when the circuit breaker trips."""


def _record_sources(paths: DataPaths, entries: list[dict]) -> None:
    with paths.fulltext_sources.open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def read_sources(paths: DataPaths) -> dict[str, str]:
    """pmcid -> source name for every XML on disk that has a provenance entry."""
    out: dict[str, str] = {}
    if paths.fulltext_sources.exists():
        with paths.fulltext_sources.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    e = json.loads(line)
                    out[e["pmcid"]] = e["source"]
    return out


def fetch_fulltext_ncbi(
    paths: DataPaths,
    batch_size: int = 100,
    limit: int | None = None,
    client_factory=NCBIClient,
    force: bool = False,
) -> dict:
    """Fill in full text from NCBI E-utilities for PMCIDs not yet on disk (batched).

    Idempotent like the Europe PMC fetch. PMCIDs that NCBI reports as publisher-restricted are
    written to the fetch log with status 403 so later runs can skip them via the log if wanted.
    """
    paths.ensure()
    records = read_jsonl(paths.records)
    candidates = _fulltext_candidates(records)
    if limit:
        candidates = candidates[:limit]
    done = {p.stem for p in paths.fulltext_xml.glob("PMC*.xml")}
    todo = [p for p in candidates if force or p not in done]
    log.info("ncbi full text: %d candidates, %d on disk, %d to fetch", len(candidates), len(done), len(todo))
    saved = front_only = restricted = missing = errors = 0
    log_entries: list[dict] = []
    src_entries: list[dict] = []
    with client_factory() as client:
        for i in range(0, len(todo), batch_size):
            batch = todo[i: i + batch_size]
            try:
                results = list(client.fetch_articles(batch))
            except Exception as exc:  # noqa: BLE001
                log.error("ncbi batch %d failed: %s", i // batch_size, exc)
                errors += len(batch)
                for p in batch:
                    log_entries.append({"pmcid": p, "status": None, "error": str(exc), "saved": False, "source": "ncbi", "at": _now()})
                continue
            for pmcid, xml, status in results:
                entry = {"pmcid": pmcid, "source": "ncbi", "at": _now(), "ncbi_status": status}
                if xml is not None:
                    (paths.fulltext_xml / f"{pmcid}.xml").write_bytes(xml)
                    entry |= {"status": 200, "bytes": len(xml), "saved": True}
                    src_entries.append({"pmcid": pmcid, "source": "ncbi", "at": entry["at"]})
                    if status == "ok":
                        saved += 1
                    else:
                        front_only += 1
                else:
                    entry |= {"status": 403 if status == "restricted" else 404, "saved": False}
                    if status == "restricted":
                        restricted += 1
                    else:
                        missing += 1
                log_entries.append(entry)
            log.info("ncbi full text: %d/%d processed (saved %d, front-only %d, restricted %d, missing %d)",
                     min(i + batch_size, len(todo)), len(todo), saved, front_only, restricted, missing)
    with paths.fulltext_log.open("a", encoding="utf-8") as fh:
        for e in log_entries:
            fh.write(json.dumps(e) + "\n")
    _record_sources(paths, src_entries)
    return {"candidates": len(candidates), "to_fetch": len(todo), "saved_with_body": saved, "saved_front_only": front_only,
            "restricted": restricted, "missing": missing, "errors": errors,
            "remaining": len(todo) - saved - front_only - restricted - missing}


def fetch_fulltext(
    paths: DataPaths,
    force: bool = False,
    workers: int = 4,
    client_factory=EuropePMCClient,
    limit: int | None = None,
    breaker_threshold: int = 12,
) -> dict:
    """Download JATS XML for every record with a PMCID.

    Files already on disk are skipped, so the step is safe to re-run after a partial
    failure. Per-request retries should be *small* here (the CLI default is 3): a file
    that fails is simply picked up by the next run. A circuit breaker aborts the whole
    run after ``breaker_threshold`` consecutive server-side failures, which is what a
    Europe PMC full-text outage looks like (search keeps working while
    ``/fullTextXML`` returns 5xx for everything).
    """
    paths.ensure()
    records = read_jsonl(paths.records)
    candidates = _fulltext_candidates(records)
    if limit:
        candidates = candidates[:limit]

    done = {p.stem for p in paths.fulltext_xml.glob("PMC*.xml")}
    todo = [p for p in candidates if force or p not in done]
    log.info("full text: %d candidates, %d already on disk, %d to fetch", len(candidates), len(done), len(todo))

    # One client (and therefore one keep-alive connection) per worker thread.
    local = threading.local()
    clients: list[EuropePMCClient] = []
    lock = threading.Lock()
    consecutive_failures = 0
    tripped = threading.Event()

    def get_client() -> EuropePMCClient:
        c = getattr(local, "client", None)
        if c is None:
            c = client_factory()
            local.client = c
            with lock:
                clients.append(c)
        return c

    def work(pmcid: str) -> dict:
        nonlocal consecutive_failures
        if tripped.is_set():
            return {"pmcid": pmcid, "status": None, "skipped": True, "saved": False, "at": _now()}
        try:
            status, body = get_client().fulltext_xml(pmcid)
        except Exception as exc:  # noqa: BLE001 - retries exhausted or transport error
            with lock:
                consecutive_failures += 1
                if consecutive_failures >= breaker_threshold:
                    tripped.set()
            return {"pmcid": pmcid, "status": None, "error": str(exc), "saved": False, "at": _now()}
        with lock:
            consecutive_failures = 0
        entry = {"pmcid": pmcid, "status": status, "bytes": len(body), "at": _now()}
        if status == 200 and body.lstrip().startswith(b"<"):
            (paths.fulltext_xml / f"{pmcid}.xml").write_bytes(body)
            entry["saved"] = True
        else:
            entry["saved"] = False
        return entry

    results: list[dict] = []
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(work, p): p for p in todo}
            for i, fut in enumerate(as_completed(futures), 1):
                pmcid = futures[fut]
                try:
                    results.append(fut.result())
                except Exception as exc:  # noqa: BLE001 - defensive; work() catches its own
                    log.error("full text %s failed: %s", pmcid, exc)
                    results.append({"pmcid": pmcid, "status": None, "error": str(exc), "saved": False, "at": _now()})
                if i % 100 == 0 or i == len(todo):
                    log.info("full text: %d/%d done", i, len(todo))
                if tripped.is_set():
                    log.error("full text: %d consecutive failures; service looks down, aborting run", breaker_threshold)
                    ex.shutdown(wait=False, cancel_futures=True)
                    break
    finally:
        for c in clients:
            c.close()

    with paths.fulltext_log.open("a", encoding="utf-8") as fh:
        for r in results:
            if not r.get("skipped"):
                fh.write(json.dumps(r | {"source": "europepmc"}) + "\n")
    _record_sources(paths, [{"pmcid": r["pmcid"], "source": "europepmc", "at": r["at"]} for r in results if r.get("saved")])

    saved = sum(1 for r in results if r.get("saved"))
    attempted = sum(1 for r in results if not r.get("skipped"))
    return {"candidates": len(candidates), "to_fetch": len(todo), "attempted": attempted, "saved": saved,
            "not_available": sum(1 for r in results if r.get("status") == 404),
            "errors": sum(1 for r in results if r.get("error")),
            "aborted": tripped.is_set(),
            "remaining": len(todo) - saved - sum(1 for r in results if r.get("status") == 404)}


# ---------------------------------------------------------------------------------
# Step 3: convert
# ---------------------------------------------------------------------------------


SOURCE_LABELS = {"europepmc": "Europe PMC fullTextXML", "ncbi": "NCBI E-utilities efetch (db=pmc)"}


def _front_matter(rec: dict | None, pmcid: str, meta: dict, source: str | None = None) -> str:
    fm = {
        "pmcid": pmcid,
        "pmid": (rec or {}).get("pmid") or meta.get("pmid"),
        "doi": (rec or {}).get("doi") or meta.get("doi"),
        "title": (rec or {}).get("title"),
        "journal": (rec or {}).get("journal") or meta.get("journal"),
        "year": (rec or {}).get("year"),
        "license": (rec or {}).get("license") or meta.get("license"),
        "article_type": meta.get("article_type"),
        "tiers": (rec or {}).get("tiers"),
        "source": SOURCE_LABELS.get(source or "europepmc", source),
    }
    lines = ["---"]
    for k, v in fm.items():
        if v is None:
            continue
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            s = str(v).replace('"', "'")
            lines.append(f'{k}: "{s}"')
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def convert_fulltext(paths: DataPaths, force: bool = False) -> dict:
    paths.ensure()
    by_pmcid = {r["pmcid"]: r for r in read_jsonl(paths.records) if r.get("pmcid")}
    sources = read_sources(paths)
    xml_files = sorted(paths.fulltext_xml.glob("PMC*.xml"))
    converted = skipped = failed = 0
    for xf in xml_files:
        out = paths.fulltext_md / (xf.stem + ".md")
        if out.exists() and not force:
            skipped += 1
            continue
        try:
            art = jats_to_markdown(xf.read_bytes())
        except Exception as exc:  # noqa: BLE001
            log.error("convert %s failed: %s", xf.name, exc)
            failed += 1
            continue
        rec = by_pmcid.get(xf.stem)
        if art.title is None and rec:
            art.title = rec.get("title")
        out.write_text(_front_matter(rec, xf.stem, art.meta, sources.get(xf.stem)) + art.markdown(), encoding="utf-8")
        converted += 1
    return {"xml_files": len(xml_files), "converted": converted, "skipped": skipped, "failed": failed}


# ---------------------------------------------------------------------------------
# Step 4: manifest + version
# ---------------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _md_body_chars(path: Path) -> int:
    """Characters after the front matter; ~0 means abstract-only full text."""
    text = path.read_text(encoding="utf-8")
    _, _, body = text.partition("\n---\n")
    return len(body.strip())


def build_manifest(paths: DataPaths) -> dict:
    records = read_jsonl(paths.records)
    xml_on_disk = {p.stem for p in paths.fulltext_xml.glob("PMC*.xml")}
    md_chars = {p.stem: _md_body_chars(p) for p in paths.fulltext_md.glob("PMC*.md")}
    md_on_disk = set(md_chars)

    rows = []
    for r in records:
        pmcid = r.get("pmcid")
        rows.append(
            {
                "key": r["key"],
                "source": r["source"],
                "id": r["id"],
                "pmid": r.get("pmid"),
                "pmcid": pmcid,
                "doi": r.get("doi"),
                "title": r.get("title"),
                "journal": r.get("journal"),
                "year": r.get("year"),
                "first_publication_date": r.get("first_publication_date"),
                "pub_types": ";".join(r.get("pub_types") or []),
                "is_open_access": r.get("is_open_access"),
                "license": r.get("license"),
                "cited_by_count": r.get("cited_by_count"),
                "has_abstract": bool(r.get("abstract")),
                "has_fulltext_xml": bool(pmcid and pmcid in xml_on_disk),
                "has_fulltext_md": bool(pmcid and pmcid in md_on_disk),
                "fulltext_md_chars": md_chars.get(pmcid, 0) if pmcid else 0,
                "tiers": ";".join(r.get("tiers") or []),
                "in_core": "core" in (r.get("tiers") or []),
                "n_mesh": len(r.get("mesh") or []),
                "n_keywords": len(r.get("keywords") or []),
                "retrieved_at": r.get("retrieved_at"),
            }
        )
    df = pd.DataFrame(rows)
    df.to_parquet(paths.manifest_parquet, index=False)
    df.to_csv(paths.manifest_csv, index=False)

    summary = {
        "corpus_version": f"{datetime.now(UTC):%Y.%m.%d}",
        "tool_version": __version__,
        "built_at": _now(),
        "queries": QUERIES,
        "counts": {
            "records": len(df),
            "by_tier": {t: int(df["tiers"].str.contains(t).sum()) for t in QUERIES},
            "core_only": int((df["tiers"] == "core").sum()),
            "with_pmcid": int(df["pmcid"].notna().sum()),
            "open_access": int(df["is_open_access"].fillna(False).astype(bool).sum()),
            "fulltext_xml": int(df["has_fulltext_xml"].sum()),
            "fulltext_md": int(df["has_fulltext_md"].sum()),
            "fulltext_md_over_3k_chars": int((df["fulltext_md_chars"] >= 3000).sum()),
            "fulltext_md_chars_total": int(df["fulltext_md_chars"].sum()),
            "by_source": {k: int(v) for k, v in df["source"].value_counts().items()},
            "by_year": {int(k): int(v) for k, v in df["year"].dropna().astype(int).value_counts().sort_index().items()},
        },
        "records_sha256": _sha256(paths.records) if paths.records.exists() else None,
    }
    paths.version_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
