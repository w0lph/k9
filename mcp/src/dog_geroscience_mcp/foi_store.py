"""Lazy access to full FOI summary records (section text, General Information fields).

Records come from the foi-summaries dataset file when it is present (a source checkout
next to ``../foi``), otherwise from the ``foi_records`` table that ``build`` copies into the
SQLite database, so an installed server needs nothing but the database.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path


class FoiStore:
    def __init__(self, path: Path, db_path: Path | None = None):
        self.path = path
        self.db_path = db_path
        self._by_id: dict[int, dict] | None = None
        self._lock = threading.Lock()

    def _load_file(self) -> dict[int, dict]:
        out: dict[int, dict] = {}
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    out[int(r["foi_id"])] = r
        return out

    def _load_db(self) -> dict[int, dict]:
        out: dict[int, dict] = {}
        if not self.db_path or not self.db_path.exists():
            return out
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            has = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='foi_records'"
            ).fetchone()
            if has:
                for foi_id, rec in conn.execute("SELECT foi_id, record FROM foi_records"):
                    out[int(foi_id)] = json.loads(rec)
        finally:
            conn.close()
        return out

    def _load(self) -> dict[int, dict]:
        with self._lock:
            if self._by_id is None:
                self._by_id = self._load_file() if self.path.exists() else self._load_db()
        return self._by_id

    @property
    def available(self) -> bool:
        return bool(self._load())

    def get(self, foi_id: int, sections: list[str] | None = None, max_chars: int = 30000) -> dict | None:
        rec = self._load().get(int(foi_id))
        if rec is None:
            return None
        parsed = rec.get("parsed") or {}
        all_sections = parsed.get("sections") or {}
        if sections:
            wanted = {s.strip().lower().replace(" ", "_") for s in sections}
            chosen = {k: v for k, v in all_sections.items() if k in wanted}
        else:
            chosen = dict(all_sections)
        # trim to budget, longest sections first
        budget = max_chars
        out_sections: dict[str, str] = {}
        for k, v in chosen.items():
            if budget <= 0:
                out_sections[k] = ""
                continue
            out_sections[k] = v[:budget]
            budget -= len(out_sections[k])
        return {
            "foi_id": rec["foi_id"],
            "application_number": rec.get("application_number"),
            "proprietary_name": rec.get("proprietary_name"),
            "ingredients": rec.get("ingredients"),
            "sponsor": rec.get("sponsor"),
            "approval_type": rec.get("approval_type"),
            "approval_date": rec.get("approval_date"),
            "pdf_url": rec.get("pdf_url"),
            "general_information": parsed.get("general_information"),
            "sections_available": list(all_sections),
            "sections": out_sections,
            "truncated": any(len(all_sections.get(k, "")) > len(v) for k, v in out_sections.items()),
            "text": rec.get("text"),
            "license": "US Government work (FDA CVM); public domain",
        }
