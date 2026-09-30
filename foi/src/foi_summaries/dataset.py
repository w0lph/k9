"""Stage 5: assemble the dataset file, one record per FOI summary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .client import BASE
from .index import read_jsonl, write_jsonl
from .sections import parse_summary, species_flag

LICENSE = "US Government work (FDA Center for Veterinary Medicine); public domain in the United States."


def build_dataset(data_dir: Path, species: str = "dog", all_species: bool = False, include_sections: bool = True) -> dict:
    src = data_dir / ("foi_index.jsonl" if all_species else f"foi_{species.lower()}.jsonl")
    docs = read_jsonl(src)
    stats = {d["foiId"]: d for d in read_jsonl(data_dir / "text_stats.jsonl")}
    txt_dir = data_dir / "text"
    rows = []
    n_text = n_scanned = 0
    for d in docs:
        fid = d["foiId"]
        rec = {
            "foi_id": fid,
            "application_number": d.get("applicationNumber"),
            "application_type": d.get("applicationType"),
            "approval_type": d.get("approvalType"),
            "approval_type_label": d.get("approvalTypeLabel"),
            "approval_date": d.get("approvalDate"),
            "sponsor": d.get("sponsor") or d.get("sponsorName"),
            "ingredients": d.get("ingredients") or d.get("activeIngredientName"),
            "proprietary_name": d.get("proprietaryName"),
            "species": d.get("species"),
            "application_status_code": d.get("applicationStatusCode"),
            "catalogue_summary": d.get("summary"),
            "file_name": d.get("fileName"),
            "pdf_url": f"{BASE}/document/downloadFoi/{fid}",
            "retrieved_at": d.get("retrieved_at"),
        }
        st = stats.get(fid)
        tpath = txt_dir / f"{fid}.txt"
        if st and tpath.exists() and not st.get("error"):
            text = tpath.read_text(encoding="utf-8")
            n_text += 1
            rec["text"] = {"pages": st.get("pages"), "chars": st.get("chars"), "likely_scanned": st.get("likely_scanned"),
                           "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
            if st.get("likely_scanned"):
                n_scanned += 1
            parsed = parse_summary(text)
            rec["species_flag"] = species_flag(parsed.get("general_information") or {}, text)
            if not include_sections:
                parsed.pop("sections", None)
            rec["parsed"] = parsed
        else:
            rec["text"] = None
            rec["parsed"] = None
            rec["species_flag"] = "unknown"
        rows.append(rec)
    rows.sort(key=lambda r: (r["application_number"] or "", r["foi_id"]))
    out = data_dir / (f"foi_summaries_{'all' if all_species else species.lower()}.jsonl")
    write_jsonl(out, rows)
    with_sections = sum(1 for r in rows if r["parsed"] and r["parsed"]["sections_found"])
    summary = {
        "built_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "tool_version": __version__,
        "records": len(rows),
        "with_text": n_text,
        "likely_scanned": n_scanned,
        "with_template_sections": with_sections,
        "species_flag": {k: sum(1 for r in rows if r.get("species_flag") == k) for k in ("dog", "other", "unknown")},
        "distinct_applications": len({r["application_number"] for r in rows}),
        "distinct_ingredients": len({(r["ingredients"] or "").lower() for r in rows if r["ingredients"]}),
        "source": BASE,
        "license": LICENSE,
        "output": str(out),
    }
    (data_dir / "dataset_version.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
