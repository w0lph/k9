"""Stage 1: the index. Every FOI summary in the catalogue, joined to the dog application list."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from .client import ADAFDAClient

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def write_jsonl(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_index(data_dir: Path, client: ADAFDAClient | None = None, species: str = "Dog") -> dict:
    """Write ``foi_index.jsonl`` (all species), ``applications_<species>.jsonl`` and
    ``foi_<species>.jsonl`` (FOI documents whose application is approved for the species)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    own = client is None
    client = client or ADAFDAClient()
    retrieved_at = _now()
    try:
        foi_docs: dict[int, dict] = {}
        for doc in client.iter_foi_documents():
            fid = doc.get("foiId")
            if fid is None:
                continue
            doc = dict(doc)
            doc["retrieved_at"] = retrieved_at
            foi_docs[fid] = doc
        log.info("FOI catalogue: %d documents", len(foi_docs))

        apps: dict[str, dict] = {}
        for row in client.iter_applications(speciesName=species):
            num = row.get("applicationNumber")
            if num is None:
                continue
            row = dict(row)
            row["applicationNumber"] = _app_number(num)
            row["retrieved_at"] = retrieved_at
            apps[row["applicationNumber"]] = row
        log.info("%s applications: %d", species, len(apps))
    finally:
        if own:
            client.close()

    sp = species.lower()
    write_jsonl(data_dir / "foi_index.jsonl", sorted(foi_docs.values(), key=lambda d: (d.get("applicationNumber") or "", d["foiId"])))
    write_jsonl(data_dir / f"applications_{sp}.jsonl", sorted(apps.values(), key=lambda a: a["applicationNumber"]))

    joined = []
    for doc in foi_docs.values():
        app = apps.get(doc.get("applicationNumber") or "")
        if app is None:
            continue
        joined.append(
            doc
            | {
                "species": species,
                "applicationId": app.get("applicationId"),
                "activeIngredientName": app.get("activeIngredientName"),
                "proprietaryName": app.get("proprietaryName"),
                "sponsorName": app.get("sponsorName"),
                "applicationStatusCode": app.get("applicationStatusCode"),
                "applicationTypeCode": app.get("applicationType"),
            }
        )
    joined.sort(key=lambda d: (d.get("applicationNumber") or "", d["foiId"]))
    write_jsonl(data_dir / f"foi_{sp}.jsonl", joined)
    summary = {
        "retrieved_at": retrieved_at,
        "foi_documents_all_species": len(foi_docs),
        f"applications_{sp}": len(apps),
        f"foi_documents_{sp}": len(joined),
        f"applications_{sp}_with_foi": len({d["applicationNumber"] for d in joined}),
    }
    (data_dir / "index_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _app_number(num) -> str:
    """Normalise to the catalogue's zero-padded 'NNN-NNN' form (search rows return ints)."""
    s = str(num)
    if "-" in s:
        return s
    s = s.zfill(6)
    return f"{s[:-3]}-{s[-3:]}"
