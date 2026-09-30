"""Retrieval baseline: can BM25 over the corpus find each question's evidence record?

This is the cheapest, LLM-free signal that the question set and the corpus index are
useful together. recall@k = fraction of questions whose *any* evidence key appears in the
top-k BM25 hits for the question text (OR semantics over content words, all tiers).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .common import DB_PATH, connect_db, read_jsonl
from .find import fts_query

KS = (1, 5, 10, 20)


def retrieval_recall(rows: list[dict], db_path: Path = DB_PATH, max_k: int = 20) -> dict:
    conn = connect_db(db_path)
    hits_at = {k: 0 for k in KS}
    per_cat: dict[str, dict[int, int]] = defaultdict(lambda: {k: 0 for k in KS})
    cat_n: dict[str, int] = defaultdict(int)
    misses = []
    for q in rows:
        gold = {e["key"] for e in q.get("evidence", [])}
        match = fts_query(q["question"], "or")
        got = [
            r[0]
            for r in conn.execute(
                "SELECT key FROM corpus_fts WHERE corpus_fts MATCH ? ORDER BY bm25(corpus_fts, 5.0, 1.0, 2.0, 2.0) LIMIT ?",
                (match, max_k),
            )
        ]
        rank = next((i + 1 for i, k in enumerate(got) if k in gold), None)
        cat = q.get("category", "?")
        cat_n[cat] += 1
        for k in KS:
            if rank is not None and rank <= k:
                hits_at[k] += 1
                per_cat[cat][k] += 1
        if rank is None:
            misses.append({"id": q.get("id"), "question": q["question"], "gold": sorted(gold)})
    conn.close()
    n = max(1, len(rows))
    return {
        "n": len(rows),
        "recall_at": {k: round(hits_at[k] / n, 3) for k in KS},
        "per_category": {c: {k: round(v[k] / cat_n[c], 2) for k in KS} for c, v in sorted(per_cat.items())},
        "misses": misses,
    }


def evaluate_file(path: Path, db_path: Path = DB_PATH) -> dict:
    return retrieval_recall(read_jsonl(path), db_path)
