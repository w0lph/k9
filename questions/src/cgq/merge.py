"""Merge draft files into one numbered set, dropping duplicates and near-duplicates."""

from __future__ import annotations

from pathlib import Path

from .common import CATEGORIES, norm_question, read_jsonl, strip_markup


def _tokens(q: str) -> set[str]:
    return {t for t in norm_question(q).split() if len(t) > 2}


def _near_dup(a: str, b: str, threshold: float = 0.8) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


def merge_files(paths: list[Path], created_by: str, created_date: str) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    dropped: list[str] = []
    for p in sorted(paths):
        for q in read_jsonl(p):
            if any(_near_dup(q["question"], r["question"]) for r in rows):
                dropped.append(f"{p.name}: near-duplicate: {q['question'][:80]}")
                continue
            q = dict(q)
            q.setdefault("created", {"by": created_by, "date": created_date})
            q.setdefault("status", "draft")
            q.setdefault("tags", [])
            # Publish clean quotes; the validator ignores markup on both sides, so they still match.
            q["evidence"] = [e | {"quote": strip_markup(e["quote"])} for e in q.get("evidence", [])]
            rows.append(q)
    order = {c: i for i, c in enumerate(CATEGORIES)}
    rows.sort(key=lambda q: (order.get(q["category"], 99), q.get("difficulty", 2), q["question"]))
    for i, q in enumerate(rows, 1):
        q["id"] = f"cgq-{i:04d}"
    # canonical key order for readability
    key_order = ["id", "category", "difficulty", "answer_type", "question", "answer", "evidence", "tags", "notes", "status", "created"]
    rows = [{k: q[k] for k in key_order if k in q} | {k: v for k, v in q.items() if k not in key_order} for q in rows]
    return rows, dropped
