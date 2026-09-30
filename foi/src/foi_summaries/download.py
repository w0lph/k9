"""Stage 2: PDFs. Idempotent; a file on disk is never re-fetched unless forced."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from .client import ADAFDAClient
from .index import read_jsonl

log = logging.getLogger(__name__)


def download_pdfs(data_dir: Path, species: str = "dog", all_species: bool = False, limit: int | None = None,
                  workers: int = 3, force: bool = False, client_factory=ADAFDAClient) -> dict:
    src = data_dir / ("foi_index.jsonl" if all_species else f"foi_{species.lower()}.jsonl")
    docs = read_jsonl(src)
    ids = sorted({d["foiId"] for d in docs if d.get("foiId") is not None})
    if limit:
        ids = ids[:limit]
    pdf_dir = data_dir / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    todo = [i for i in ids if force or not (pdf_dir / f"{i}.pdf").exists()]
    log.info("pdf: %d ids, %d on disk, %d to fetch", len(ids), len(ids) - len(todo), len(todo))

    def work(fid: int) -> dict:
        with client_factory() as c:
            status, body, ctype = c.download_foi(fid)
        entry = {"foiId": fid, "status": status, "bytes": len(body), "content_type": ctype,
                 "at": datetime.now(UTC).replace(microsecond=0).isoformat()}
        if status == 200 and body[:5] == b"%PDF-":
            (pdf_dir / f"{fid}.pdf").write_bytes(body)
            entry["saved"] = True
        else:
            entry["saved"] = False
        return entry

    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(work, i): i for i in todo}
        for n, fut in enumerate(as_completed(futs), 1):
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                results.append({"foiId": futs[fut], "status": None, "error": str(exc), "saved": False})
            if n % 50 == 0 or n == len(todo):
                log.info("pdf: %d/%d", n, len(todo))
    with (data_dir / "download_log.jsonl").open("a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")
    return {"ids": len(ids), "attempted": len(todo), "saved": sum(1 for r in results if r.get("saved")),
            "failed": sum(1 for r in results if not r.get("saved"))}
