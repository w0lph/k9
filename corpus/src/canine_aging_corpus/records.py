"""Normalise Europe PMC ``core`` results into flat corpus records.

A record is keyed by ``(source, id)`` — Europe PMC's own identity — so a preprint (PPR)
and its later journal version (MED) are kept as separate works. Downstream code can join
them on DOI where Europe PMC provides the link.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _get(d: dict, *path: str, default: Any = None) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _yn(value: Any) -> bool | None:
    if value in ("Y", "y", True):
        return True
    if value in ("N", "n", False):
        return False
    return None


def record_key(rec: dict) -> str:
    return f"{rec['source']}:{rec['id']}"


def normalise(result: dict, tier: str, retrieved_at: str, raw_page: str) -> dict:
    """Flatten one Europe PMC core result."""
    journal = _get(result, "journalInfo", "journal", "title") or result.get("journalTitle")
    authors = [
        a.get("fullName") or " ".join(filter(None, [a.get("firstName"), a.get("lastName")]))
        for a in _get(result, "authorList", "author", default=[]) or []
    ]
    mesh = [
        {
            "descriptor": m.get("descriptorName"),
            "major": _yn(m.get("majorTopic_YN")),
            "qualifiers": [
                q.get("qualifierName")
                for q in _get(m, "meshQualifierList", "meshQualifier", default=[]) or []
            ],
        }
        for m in _get(result, "meshHeadingList", "meshHeading", default=[]) or []
    ]
    grants = [
        {"grant_id": g.get("grantId"), "agency": g.get("agency"), "acronym": g.get("acronym")}
        for g in _get(result, "grantsList", "grant", default=[]) or []
    ]
    fulltext_urls = [
        {
            "site": u.get("site"),
            "availability": u.get("availabilityCode"),
            "style": u.get("documentStyle"),
            "url": u.get("url"),
        }
        for u in _get(result, "fullTextUrlList", "fullTextUrl", default=[]) or []
    ]
    year = result.get("pubYear") or _get(result, "journalInfo", "yearOfPublication")
    return {
        "key": f"{result.get('source')}:{result.get('id')}",
        "id": result.get("id"),
        "source": result.get("source"),
        "pmid": result.get("pmid"),
        "pmcid": result.get("pmcid"),
        "doi": result.get("doi"),
        "title": result.get("title"),
        "abstract": result.get("abstractText"),
        "authors": authors,
        "author_string": result.get("authorString"),
        "journal": journal,
        "year": int(year) if year and str(year).isdigit() else None,
        "first_publication_date": result.get("firstPublicationDate"),
        "pub_types": _get(result, "pubTypeList", "pubType", default=[]) or [],
        "language": result.get("language"),
        "mesh": mesh,
        "keywords": _get(result, "keywordList", "keyword", default=[]) or [],
        "grants": grants,
        "is_open_access": _yn(result.get("isOpenAccess")),
        "in_epmc": _yn(result.get("inEPMC")),
        "in_pmc": _yn(result.get("inPMC")),
        "has_pdf": _yn(result.get("hasPDF")),
        "license": result.get("license"),
        "cited_by_count": result.get("citedByCount"),
        "fulltext_urls": fulltext_urls,
        "tiers": [tier],
        "retrieved_at": retrieved_at,
        "raw_page": raw_page,
    }


def merge(existing: dict, incoming: dict) -> dict:
    """Merge a re-fetched record: union tiers, keep the newest metadata."""
    tiers = sorted(set(existing.get("tiers", [])) | set(incoming.get("tiers", [])))
    merged = {**existing, **incoming}
    merged["tiers"] = tiers
    return merged


def write_jsonl(path: Path, records: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
