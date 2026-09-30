"""Structured extraction layer over FOI summaries, with verbatim-grounding validation.

A structured record turns the parsed summary into typed fields (dose regimen, PK values,
target-animal-safety design and findings, effectiveness design, adverse reactions). Every
field that carries a number or a claim must also carry a ``quote`` that appears word-for-word
in the summary's extracted text, and the numbers in the field must appear in that quote. The
extraction can be done by a model or a person; the validator is what makes it trustworthy.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

_WS = re.compile(r"\s+")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")

SCHEMA_DOC = {
    "foi_id": "int — must exist in foi_summaries_dog.jsonl",
    "application_number": "str",
    "product_name": "str",
    "ingredient": "str",
    "species_class": "str (e.g. 'Dogs')",
    "indication": {"text": "str", "quote": "verbatim"},
    "dose_regimen": {"dose": "str incl. unit (e.g. '0.5 mg/kg')", "route": "str", "frequency": "str",
                     "duration_or_conditions": "str | null", "quote": "verbatim"},
    "pharmacokinetics": [{"parameter": "half-life | tmax | cmax | auc | bioavailability | clearance | protein binding | other",
                          "value": "str incl. unit", "conditions": "str | null (dose, route, fed/fasted, n)", "quote": "verbatim"}],
    "target_animal_safety": {"dose_multiples": ["list of str, e.g. '1X','3X','5X'"], "duration": "str | null",
                             "n_animals": "str | null", "findings": [{"finding": "str", "quote": "verbatim"}],
                             "design_quote": "verbatim sentence describing the study design"},
    "effectiveness": {"design": "str", "n_dogs": "str | null", "primary_endpoint": "str | null", "result": "str", "quote": "verbatim"},
    "adverse_reactions": [{"term": "str", "treated": "str | null (e.g. '12.3%' or '5/120')", "control": "str | null", "quote": "verbatim"}],
    "notes": "str | null — extractor caveats (e.g. table lost in PDF text)",
    "extracted_by": "str",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace(" ", " ")
    s = s.replace("–", "-").replace("—", "-").replace("\f", " ")
    return _WS.sub(" ", s).strip()


@dataclass
class Report:
    n: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    quotes_checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return f"records: {self.n} | quotes checked: {self.quotes_checked} | errors: {len(self.errors)} | warnings: {len(self.warnings)}"


def _numbers(s: str | None) -> set[str]:
    return {m.group(0).replace(",", ".") for m in _NUM.finditer(s or "")}


class _Checker:
    def __init__(self, text: str, where: str, rep: Report):
        self.text = norm(text)
        self.where = where
        self.rep = rep

    def quote(self, obj: dict, path: str, *value_keys: str, required: bool = True) -> None:
        q = obj.get("quote")
        if not q:
            if required:
                self.rep.errors.append(f"{self.where} {path}: missing quote")
            return
        if not (12 <= len(q) <= 1200):
            self.rep.errors.append(f"{self.where} {path}: quote length {len(q)} outside 12-1200")
            return
        self.rep.quotes_checked += 1
        if norm(q) not in self.text:
            self.rep.errors.append(f"{self.where} {path}: quote not found verbatim in summary text: {q[:80]!r}")
            return
        qn = _numbers(q)
        for k in value_keys:
            for num in _numbers(str(obj.get(k) or "")):
                if num not in qn:
                    self.rep.errors.append(f"{self.where} {path}.{k}: number {num} not in quote")


def validate_structured(rows: list[dict], data_dir: Path) -> Report:
    rep = Report(n=len(rows))
    known = _known_ids(data_dir)
    seen: set[int] = set()
    for i, r in enumerate(rows, 1):
        fid = r.get("foi_id")
        where = f"#{i} (foi {fid})"
        if not isinstance(fid, int) or fid not in known:
            rep.errors.append(f"{where}: foi_id unknown or not an int")
            continue
        if fid in seen:
            rep.errors.append(f"{where}: duplicate foi_id")
        seen.add(fid)
        for key in ("product_name", "ingredient", "species_class", "extracted_by"):
            if not r.get(key):
                rep.errors.append(f"{where}: missing {key}")
        tpath = data_dir / "text" / f"{fid}.txt"
        if not tpath.exists():
            rep.errors.append(f"{where}: no text file")
            continue
        c = _Checker(tpath.read_text(encoding="utf-8"), where, rep)
        if r.get("indication"):
            c.quote(r["indication"], "indication")
        dr = r.get("dose_regimen")
        if dr:
            c.quote(dr, "dose_regimen", "dose")
        else:
            rep.warnings.append(f"{where}: no dose_regimen")
        for j, pk in enumerate(r.get("pharmacokinetics") or [], 1):
            c.quote(pk, f"pharmacokinetics[{j}]", "value")
        tas = r.get("target_animal_safety")
        if tas:
            if tas.get("design_quote"):
                c.quote({"quote": tas["design_quote"], "n_animals": tas.get("n_animals")}, "target_animal_safety.design", "n_animals")
            for j, f in enumerate(tas.get("findings") or [], 1):
                c.quote(f, f"target_animal_safety.findings[{j}]")
        eff = r.get("effectiveness")
        if eff:
            c.quote(eff, "effectiveness", "n_dogs")
        for j, ar in enumerate(r.get("adverse_reactions") or [], 1):
            c.quote(ar, f"adverse_reactions[{j}]", "treated", "control")
        if not (r.get("pharmacokinetics") or tas or eff):
            rep.warnings.append(f"{where}: no PK, safety or effectiveness content")
    return rep


def _known_ids(data_dir: Path) -> set[int]:
    p = data_dir / "foi_summaries_dog.jsonl"
    ids: set[int] = set()
    if p.exists():
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    ids.add(int(json.loads(line)["foi_id"]))
    return ids


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def merge_structured(paths: list[Path], out: Path) -> tuple[int, list[str]]:
    rows: dict[int, dict] = {}
    dropped: list[str] = []
    for p in sorted(paths):
        for r in read_jsonl(p):
            fid = r.get("foi_id")
            if fid in rows:
                dropped.append(f"{p.name}: duplicate foi_id {fid}")
                continue
            rows[fid] = r
    ordered = [rows[k] for k in sorted(rows, key=lambda k: (rows[k].get("ingredient") or "", k))]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in ordered:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(ordered), dropped
