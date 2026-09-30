"""Stage 3: text. pypdf extraction with a scanned-document heuristic (no OCR here)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pypdf import PdfReader

log = logging.getLogger(__name__)

SCANNED_CHARS_PER_PAGE = 200


def extract_pdf_text(pdf_path: Path) -> tuple[str, int]:
    reader = PdfReader(str(pdf_path))
    pages = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception as exc:  # noqa: BLE001 - keep going on a bad page
            log.warning("%s: page extraction failed: %s", pdf_path.name, exc)
            pages.append("")
    return "\n\f\n".join(pages), len(pages)


def extract_all(data_dir: Path, force: bool = False) -> dict:
    pdf_dir = data_dir / "pdf"
    txt_dir = data_dir / "text"
    txt_dir.mkdir(parents=True, exist_ok=True)
    stats_path = data_dir / "text_stats.jsonl"
    existing = {}
    if stats_path.exists() and not force:
        with stats_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    d = json.loads(line)
                    existing[d["foiId"]] = d
    done = skipped = failed = 0
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        fid = int(pdf.stem)
        out = txt_dir / f"{fid}.txt"
        if out.exists() and fid in existing and not force:
            skipped += 1
            continue
        try:
            text, n_pages = extract_pdf_text(pdf)
        except Exception as exc:  # noqa: BLE001
            log.error("%s: %s", pdf.name, exc)
            existing[fid] = {"foiId": fid, "error": str(exc), "pages": 0, "chars": 0, "likely_scanned": None}
            failed += 1
            continue
        out.write_text(text, encoding="utf-8")
        cpp = len(text) / max(1, n_pages)
        existing[fid] = {"foiId": fid, "pages": n_pages, "chars": len(text), "chars_per_page": round(cpp),
                         "likely_scanned": cpp < SCANNED_CHARS_PER_PAGE}
        done += 1
    with stats_path.open("w", encoding="utf-8") as fh:
        for fid in sorted(existing):
            fh.write(json.dumps(existing[fid]) + "\n")
    scanned = sum(1 for d in existing.values() if d.get("likely_scanned"))
    return {"pdfs": len(list(pdf_dir.glob('*.pdf'))), "extracted": done, "skipped": skipped, "failed": failed,
            "likely_scanned": scanned}
