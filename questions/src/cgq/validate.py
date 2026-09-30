"""Validate a question file: schema, identifiers, and verbatim grounding.

The one rule that matters: every evidence quote must appear word-for-word (after
whitespace/Unicode normalisation) in the cited record's abstract or Markdown full text.
That is what makes the set trustworthy without a domain reviewer.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .common import (
    ANSWER_TYPES,
    CATEGORIES,
    CORPUS_DIR,
    STATUSES,
    load_records,
    norm_question,
    norm_text,
    read_fulltext,
    read_jsonl,
)

ID_RE = re.compile(r"^cgq-\d{4}$")
MAX_ANSWER_WORDS = 80
MIN_QUOTE_CHARS, MAX_QUOTE_CHARS = 20, 700


@dataclass
class Report:
    n: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    by_category: Counter = field(default_factory=Counter)
    by_status: Counter = field(default_factory=Counter)
    by_difficulty: Counter = field(default_factory=Counter)
    by_location: Counter = field(default_factory=Counter)
    sources: Counter = field(default_factory=Counter)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = [
            f"questions: {self.n} | errors: {len(self.errors)} | warnings: {len(self.warnings)}",
            f"by category: {dict(sorted(self.by_category.items()))}",
            f"by status: {dict(self.by_status)} | by difficulty: {dict(sorted(self.by_difficulty.items()))}",
            f"evidence locations: {dict(self.by_location)} | distinct source records: {len(self.sources)}",
        ]
        return "\n".join(lines)


def _check_quote(rec: dict, ev: dict, corpus_dir: Path) -> str | None:
    quote = ev.get("quote") or ""
    if not (MIN_QUOTE_CHARS <= len(quote) <= MAX_QUOTE_CHARS):
        return f"quote length {len(quote)} outside {MIN_QUOTE_CHARS}-{MAX_QUOTE_CHARS}"
    nq = norm_text(quote)
    loc = ev.get("location")
    if loc == "abstract":
        hay = norm_text((rec.get("title") or "") + " " + (rec.get("abstract") or ""))
        return None if nq in hay else "quote not found verbatim in title/abstract"
    if loc == "fulltext":
        body = read_fulltext(corpus_dir, rec.get("pmcid"))
        if body is None:
            return f"no Markdown full text on disk for {rec.get('pmcid')}"
        return None if nq in norm_text(body) else "quote not found verbatim in full text"
    return f"location must be 'abstract' or 'fulltext', got {loc!r}"


def validate_rows(rows: list[dict], corpus_dir: Path = CORPUS_DIR, require_ids: bool = False) -> Report:
    recs = load_records(corpus_dir)
    rep = Report(n=len(rows))
    seen_ids: set[str] = set()
    seen_q: dict[str, int] = {}
    for i, q in enumerate(rows, 1):
        where = f"#{i}" + (f" ({q.get('id')})" if q.get("id") else "")
        err = rep.errors.append
        for key in ("question", "answer", "answer_type", "category", "evidence", "difficulty"):
            if key not in q:
                err(f"{where}: missing field {key!r}")
        if rep.errors and rep.errors[-1].startswith(where) and "missing field" in rep.errors[-1]:
            continue
        qid = q.get("id")
        if require_ids or qid:
            if not qid or not ID_RE.match(qid):
                err(f"{where}: id must match cgq-NNNN")
            elif qid in seen_ids:
                err(f"{where}: duplicate id")
            seen_ids.add(qid or "")
        question = q["question"].strip()
        if not question.endswith("?"):
            err(f"{where}: question should end with '?'")
        nk = norm_question(question)
        if nk in seen_q:
            err(f"{where}: duplicate of #{seen_q[nk]} (same question text)")
        seen_q[nk] = i
        if len(q["answer"].split()) > MAX_ANSWER_WORDS:
            err(f"{where}: answer longer than {MAX_ANSWER_WORDS} words")
        if q["answer_type"] not in ANSWER_TYPES:
            err(f"{where}: answer_type {q['answer_type']!r} not in {ANSWER_TYPES}")
        if q["category"] not in CATEGORIES:
            err(f"{where}: category {q['category']!r} not in {CATEGORIES}")
        if q["difficulty"] not in (1, 2, 3):
            err(f"{where}: difficulty must be 1, 2 or 3")
        if q.get("status", "draft") not in STATUSES:
            err(f"{where}: status {q.get('status')!r} not in {STATUSES}")
        ev_list = q.get("evidence") or []
        if not isinstance(ev_list, list) or not ev_list:
            err(f"{where}: evidence must be a non-empty list")
            continue
        for j, ev in enumerate(ev_list, 1):
            key = ev.get("key")
            rec = recs.get(key or "")
            if rec is None:
                err(f"{where} evidence {j}: unknown corpus key {key!r}")
                continue
            for fld in ("pmid", "pmcid", "doi"):
                if ev.get(fld) and rec.get(fld) and ev[fld] != rec[fld]:
                    err(f"{where} evidence {j}: {fld} {ev[fld]!r} does not match record {rec[fld]!r}")
            problem = _check_quote(rec, ev, corpus_dir)
            if problem:
                err(f"{where} evidence {j} [{key}]: {problem}")
            rep.by_location[ev.get("location")] += 1
            rep.sources[key] += 1
        rep.by_category[q["category"]] += 1
        rep.by_status[q.get("status", "draft")] += 1
        rep.by_difficulty[q["difficulty"]] += 1
        if len(q["answer"].split()) < 1:
            err(f"{where}: empty answer")
        if q["answer_type"] == "numeric" and not re.search(r"\d", q["answer"]):
            rep.warnings.append(f"{where}: numeric answer_type but no digit in answer")
    return rep


def validate_file(path: Path, corpus_dir: Path = CORPUS_DIR, require_ids: bool = False) -> Report:
    return validate_rows(read_jsonl(path), corpus_dir, require_ids)
