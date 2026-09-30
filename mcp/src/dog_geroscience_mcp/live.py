"""Live lookups: Ensembl orthologs (cached in SQLite) and NIH RePORTER grants."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .paths import ENSEMBL_REST, REPORTER_API, USER_AGENT


def _get_with_retry(client: httpx.Client, url: str, params: dict | None = None, attempts: int = 3) -> httpx.Response:
    """GET with a short retry on 429/5xx/transport errors (public APIs flap)."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            r = client.get(url, params=params)
        except httpx.TransportError as exc:
            last = exc
        else:
            if r.status_code == 429 or r.status_code >= 500:
                last = httpx.HTTPStatusError(f"HTTP {r.status_code} from {url}", request=r.request, response=r)
            else:
                return r
        if i < attempts - 1:
            time.sleep(1.5 * (i + 1))
    assert last is not None
    raise last


def _error(source: str, exc: Exception, **extra) -> dict:
    return {"error": f"{source} request failed: {exc}", "retryable": True, "source": source, **extra}

SPECIES_ALIASES = {
    "human": "homo_sapiens",
    "homo sapiens": "homo_sapiens",
    "mouse": "mus_musculus",
    "mus musculus": "mus_musculus",
    "rat": "rattus_norvegicus",
    "dog": "canis_lupus_familiaris",
    "canis lupus familiaris": "canis_lupus_familiaris",
}
DOG = "canis_lupus_familiaris"


def _species(name: str) -> str:
    return SPECIES_ALIASES.get(name.strip().lower(), name.strip().lower().replace(" ", "_"))


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})


# -- Ensembl ----------------------------------------------------------------------


def _cache_get(cache_db: Path | None, key: str) -> dict | None:
    """Best-effort read from the ``ensembl_cache`` table of the built database."""
    if cache_db is None or not cache_db.exists():
        return None
    try:
        with sqlite3.connect(cache_db, timeout=5) as conn:
            row = conn.execute("SELECT value FROM ensembl_cache WHERE key = ?", (key,)).fetchone()
    except sqlite3.Error:
        return None
    return json.loads(row[0]) if row else None


def _cache_put(cache_db: Path | None, key: str, value: dict) -> None:
    """Best-effort write with a short-lived read-write connection (safe from any thread)."""
    if cache_db is None or not cache_db.exists():
        return
    try:
        with sqlite3.connect(cache_db, timeout=5) as conn:
            conn.execute("INSERT OR REPLACE INTO ensembl_cache VALUES (?,?,?)", (key, json.dumps(value), _now()))
    except sqlite3.Error:
        pass


def dog_ortholog(
    gene_symbol: str,
    from_species: str = "human",
    cache_db: Path | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """Ensembl Compara orthologues of ``gene_symbol`` (in ``from_species``) in the dog.

    Returns the dog gene id(s), percent identity/positivity, orthology type (one2one etc.),
    and, when available, the dog gene's symbol, description and location.
    """
    src = _species(from_species)
    key = f"ortholog:{src}:{gene_symbol.upper()}:{DOG}"
    cached = _cache_get(cache_db, key)
    if cached:
        return {**cached, "cached": True}

    own = client is None
    client = client or _client()
    try:
        try:
            r = _get_with_retry(
                client,
                f"{ENSEMBL_REST}/homology/symbol/{src}/{gene_symbol}",
                params={"target_species": DOG, "type": "orthologues", "sequence": "none", "content-type": "application/json"},
            )
        except httpx.HTTPError as exc:
            return _error("Ensembl REST", exc, gene_symbol=gene_symbol, from_species=src)
        if r.status_code == 400:
            return {"gene_symbol": gene_symbol, "from_species": src, "error": f"Ensembl: {r.text[:200]}", "retryable": False}
        if r.status_code != 200:
            return _error("Ensembl REST", Exception(f"HTTP {r.status_code}"), gene_symbol=gene_symbol, from_species=src)
        data = r.json().get("data") or []
        homologies = data[0].get("homologies", []) if data else []
        source_id = data[0].get("id") if data else None
        out_h = []
        for h in homologies:
            t = h.get("target", {})
            s = h.get("source", {})
            entry = {
                "dog_gene_id": t.get("id"),
                "type": h.get("type"),
                "taxonomy_level": h.get("taxonomy_level"),
                "perc_id_target": t.get("perc_id"),
                "perc_pos_target": t.get("perc_pos"),
                "perc_id_source": s.get("perc_id"),
                "dn_ds": h.get("dn_ds"),
            }
            try:
                look = _get_with_retry(client, f"{ENSEMBL_REST}/lookup/id/{t.get('id')}", params={"content-type": "application/json"}, attempts=2)
            except httpx.HTTPError:
                look = None
            if look is not None and look.status_code == 200:
                lk = look.json()
                entry.update(
                    {
                        "dog_symbol": lk.get("display_name"),
                        "description": lk.get("description"),
                        "biotype": lk.get("biotype"),
                        "assembly": lk.get("assembly_name"),
                        "location": f"{lk.get('seq_region_name')}:{lk.get('start')}-{lk.get('end')}:{lk.get('strand')}",
                    }
                )
            out_h.append(entry)
        result = {
            "gene_symbol": gene_symbol,
            "from_species": src,
            "source_gene_id": source_id,
            "target_species": DOG,
            "orthologs": out_h,
            "n_orthologs": len(out_h),
            "source": "Ensembl Compara REST (homology/symbol, lookup/id)",
            "fetched_at": _now(),
        }
        if out_h and all(h.get("dog_symbol") for h in out_h):
            _cache_put(cache_db, key, result)  # only cache complete answers
        return result
    finally:
        if own:
            client.close()


# -- openFDA animal & veterinary adverse events ------------------------------------

OPENFDA_EVENTS = "https://api.fda.gov/animalandveterinary/event.json"


def openfda_dog_events(ingredient: str, top: int = 10, client: httpx.Client | None = None) -> dict:
    """Adverse-event reports in dogs whose active ingredient matches ``ingredient``.

    Two calls: one for the total, one for the top VeDDRA reaction terms. openFDA answers
    404 when nothing matches, which is reported as total 0, not an error. Public domain data;
    no API key needed at low volume.
    """
    own = client is None
    client = client or _client()
    q = f'animal.species:Dog AND drug.active_ingredients.name:"{ingredient}"'
    out: dict = {"ingredient": ingredient, "total": 0, "top_reactions": [], "source": "openFDA animal & veterinary event API"}
    try:
        r = client.get(OPENFDA_EVENTS, params={"search": q, "limit": 1})
        if r.status_code == 404:
            return out
        if r.status_code != 200:
            return out | _error("openFDA", Exception(f"HTTP {r.status_code}"))
        out["total"] = int((r.json().get("meta") or {}).get("results", {}).get("total", 0))
        r2 = client.get(OPENFDA_EVENTS, params={"search": q, "count": "reaction.veddra_term_name.exact", "limit": top})
        if r2.status_code == 200:
            out["top_reactions"] = [{"term": x.get("term"), "count": x.get("count")} for x in r2.json().get("results", [])]
        return out
    except httpx.HTTPError as exc:
        return out | _error("openFDA", exc)
    finally:
        if own:
            client.close()


# -- NIH RePORTER -----------------------------------------------------------------


def reporter_search(
    query: str = "companion dog aging",
    fiscal_years: list[int] | None = None,
    limit: int = 25,
    offset: int = 0,
    client: httpx.Client | None = None,
) -> dict:
    """Full-text search of NIH RePORTER projects (title, terms, abstract)."""
    payload: dict = {
        "criteria": {
            "advanced_text_search": {
                "operator": "and",
                "search_field": "projecttitle,terms,abstracttext",
                "search_text": query,
            }
        },
        "limit": max(1, min(limit, 100)),
        "offset": offset,
        "sort_field": "fiscal_year",
        "sort_order": "desc",
    }
    if fiscal_years:
        payload["criteria"]["fiscal_years"] = fiscal_years
    own = client is None
    client = client or _client(timeout=60.0)
    try:
        last: Exception | None = None
        data = None
        for i in range(3):
            try:
                r = client.post(REPORTER_API, json=payload, headers={"Content-Type": "application/json"})
                if r.status_code == 429 or r.status_code >= 500:
                    last = Exception(f"HTTP {r.status_code}")
                else:
                    r.raise_for_status()
                    data = r.json()
                    break
            except httpx.HTTPError as exc:
                last = exc
            if i < 2:
                time.sleep(1.5 * (i + 1))
        if data is None:
            return _error("NIH RePORTER", last or Exception("no response"), query=query)
    finally:
        if own:
            client.close()
    results = []
    for p in data.get("results", []):
        pis = [pi.get("full_name") for pi in p.get("principal_investigators") or [] if pi.get("full_name")]
        results.append(
            {
                "project_num": p.get("project_num"),
                "fiscal_year": p.get("fiscal_year"),
                "title": p.get("project_title"),
                "organization": (p.get("organization") or {}).get("org_name"),
                "principal_investigators": pis,
                "agency": (p.get("agency_ic_admin") or {}).get("abbreviation"),
                "activity_code": p.get("activity_code"),
                "award_amount": p.get("award_amount"),
                "project_start": p.get("project_start_date"),
                "project_end": p.get("project_end_date"),
                "abstract": (p.get("abstract_text") or "")[:1500],
                "url": f"https://reporter.nih.gov/project-details/{p.get('appl_id')}" if p.get("appl_id") else None,
            }
        )
    return {"query": query, "fiscal_years": fiscal_years, "total": (data.get("meta") or {}).get("total"),
            "offset": offset, "results": results, "source": "NIH RePORTER API v2"}
