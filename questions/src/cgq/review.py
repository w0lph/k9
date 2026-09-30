"""Apply reviewer verdicts (pass / fix / drop) to a question set and write the next version."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .common import read_jsonl, write_jsonl

FIXABLE = ("question", "answer", "answer_type", "difficulty")


def apply_reviews(questions_path: Path, review_paths: list[Path], out_path: Path, min_confidence: str = "low") -> dict:
    rank = {"low": 0, "medium": 1, "high": 2}
    verdicts: dict[str, dict] = {}
    for p in sorted(review_paths):
        for v in read_jsonl(p):
            verdicts[v["id"]] = v
    rows = read_jsonl(questions_path)
    kept, dropped, fixed, unreviewed = [], [], [], 0
    for q in rows:
        v = verdicts.get(q["id"])
        if v is None:
            unreviewed += 1
            kept.append(q)
            continue
        conf_ok = rank.get(v.get("confidence", "low"), 0) >= rank[min_confidence]
        verdict = v.get("verdict")
        if verdict == "drop" and conf_ok:
            dropped.append({"id": q["id"], "issue": v.get("issue")})
            continue
        if verdict == "fix" and conf_ok and isinstance(v.get("fix"), dict):
            changes = {k: val for k, val in v["fix"].items() if k in FIXABLE and val not in (None, "")}
            if changes:
                q = q | changes
                q["review"] = {"issue": v.get("issue"), "changed": sorted(changes)}
                fixed.append({"id": q["id"], "changed": sorted(changes)})
        q["status"] = "reviewed" if verdict in ("pass", "fix") else q.get("status", "validated")
        kept.append(q)
    write_jsonl(out_path, kept)
    return {
        "input": len(rows),
        "reviewed": len(rows) - unreviewed,
        "unreviewed": unreviewed,
        "verdicts": dict(Counter(v.get("verdict") for v in verdicts.values())),
        "fixed": fixed,
        "dropped": dropped,
        "output": str(out_path),
        "output_count": len(kept),
    }
