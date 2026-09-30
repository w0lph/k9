"""Stage 4: deterministic structure from the FOI summary template.

CVM FOI summaries follow a stable outline (Roman-numeral sections) and a "General
Information" block of ``Field: value`` lines. Parsing those needs no model and gives
reliable, quotable structure. Free-text findings (PK values, safety conclusions, adverse
event tables) are surfaced as *candidate sentences* for a later LLM or human pass.
"""

from __future__ import annotations

import re

# A section heading is a line whose uppercase title contains a known section name and that
# carries a Roman or Arabic numeral either before it ("II. EFFECTIVENESS", "2. EFFECTIVENESS")
# or, in pypdf's column-reordered output, after it ("GENERAL INFORMATION I.").
_TITLE_WORDS = (
    r"GENERAL INFORMATION|EFFECTIVENESS|TARGET ANIMAL SAFETY|HUMAN FOOD SAFETY|USER SAFETY|"
    r"AGENCY CONCLUSIONS|ENVIRONMENTAL (?:IMPACT|ASSESSMENT)|LABELING|ATTACHMENTS?"
)
SECTION_RE = re.compile(
    rf"^[ \t]*(?:(?:[IVX]{{1,4}}|\d{{1,2}})[.)][ \t]+)?(?P<title>(?:{_TITLE_WORDS})(?:[ \t]+[A-Z/&,()'\-]+){{0,4}})"
    rf"(?:[ \t]+(?:[IVX]{{1,4}}|\d{{1,2}})\.)?[ \t]*:?[ \t]*$",
    re.MULTILINE,
)
_NUMBERED_RE = re.compile(r"^[ \t]*(?:[IVX]{1,4}|\d{1,2})[.)][ \t]+|[ \t]+(?:[IVX]{1,4}|\d{1,2})\.[ \t]*:?[ \t]*$", re.MULTILINE)

# Canonical names for the section titles seen across three decades of summaries.
CANON = [
    ("general information", "general_information"),
    ("effectiveness", "effectiveness"),
    ("target animal safety", "target_animal_safety"),
    ("human food safety", "human_food_safety"),
    ("user safety", "user_safety"),
    ("agency conclusions", "agency_conclusions"),
    ("environmental", "environmental"),
    ("labeling", "labeling"),
    ("attachments", "attachments"),
]

GI_FIELDS = [
    "File Number", "NADA Number", "ANADA Number", "Application Number", "Sponsor", "Established Name",
    "Generic Name", "Proprietary Name", "Trade Name", "Dosage Form", "How Supplied", "How Dispensed",
    "Dispensing Status", "Amount of Active Ingredient", "Route of Administration", "Route(s) of Administration",
    "Species/Class(es)", "Species/Class", "Species(es)", "Species",
    "Recommended Dosage", "Recommended Dose", "Dosage", "Pharmacological Category", "Indications for Use",
    "Indications", "Indication", "Effect of Supplement", "Marketing Status", "Withdrawal Period",
    "Patent Information", "Exclusivity",
]
# Layouts seen: ``Field: value``; lettered ``A. Field`` with the value on the next line(s);
# and pypdf's reordered ``Field A.`` (letter after the name). A trailing colon is optional.
_GI_RE = re.compile(
    r"^[ \t]*(?:[A-Z]\.[ \t]+)?(?P<field>"
    + "|".join(re.escape(f) for f in sorted(GI_FIELDS, key=len, reverse=True))
    + r")(?:[ \t]+[A-Z]\.)?[ \t]*:?[ \t]*(?P<value>.*)$",
    re.MULTILINE,
)
_PAGE_FOOTER_RE = re.compile(r"^\s*(?:Freedom of Information Summary|N?ANADA \d{3}-\d{3}|Page \d+ of \d+)\s*$", re.MULTILINE | re.IGNORECASE)

PK_TERMS = ("half-life", "half life", "t1/2", "cmax", "tmax", "bioavailab", "auc", "clearance", "volume of distribution",
            "plasma concentration", "steady state", "steady-state", "protein binding")
SAFETY_TERMS = ("no adverse", "adverse reaction", "adverse event", "well tolerated", "clinically significant",
                "margin of safety", "times the", "x the recommended", "toxic", "mortality", "death")
# tail runs to the end of the sentence, but a period inside a decimal (0.23) does not end it
DOSE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|µg|ug|g|IU|mL)\s*/\s*(?:kg|lb)\b(?:[^.\n]|\.(?=\d)){0,80}", re.IGNORECASE
)


def _canon(title: str) -> str:
    t = title.lower()
    for needle, name in CANON:
        if needle in t:
            return name
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def split_sections(text: str) -> dict[str, str]:
    """Return {canonical_section_name: text}. Text before the first heading is ``preamble``."""
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return {"preamble": text}
    out: dict[str, str] = {}
    pre = text[: matches[0].start()].strip()
    if pre:
        out["preamble"] = pre
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        name = _canon(m.group("title"))
        body = text[m.end(): end].strip()
        if name == "general_information" and "general_information" not in out and i == 0 and not body:
            continue  # a table-of-contents entry; the real section follows
        if name in out:  # repeated heading (e.g. two effectiveness sections): append
            out[name] = out[name] + "\n\n" + body
        else:
            out[name] = body
    return out


def parse_general_information(text: str) -> dict[str, str]:
    """Field/value pairs in either layout, continuation lines folded until the next field.

    A value stops at a blank line (paragraph break) or at the next field heading; page
    footers that pypdf interleaves are dropped.
    """
    text = _PAGE_FOOTER_RE.sub("", text)
    fields: dict[str, str] = {}
    matches = list(_GI_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # text[m.end():end] starts with the newline that ended the heading line
        chunk = (m.group("value") + text[m.end(): end]).strip()
        chunk = chunk.split("\n\n", 1)[0]
        value = re.sub(r"\s+", " ", chunk).strip()
        key = re.sub(r"[^a-z0-9]+", "_", _CANON_FIELD.get(m.group("field"), m.group("field")).lower()).strip("_")
        if value and key not in fields:
            fields[key] = value[:600]
    return fields


_CANON_FIELD = {
    "Species(es)": "Species",
    "Species/Class(es)": "Species/Class",
    "Route(s) of Administration": "Route of Administration",
}

_DOG_RE = re.compile(r"\b(dogs?|canines?|canis)\b", re.IGNORECASE)
_OTHER_RE = re.compile(r"\b(cats?|feline|horses?|equine|cattle|bovine|swine|pigs?|porcine|sheep|ovine|goats?|caprine|"
                       r"chickens?|turkeys?|poultry|fish|salmon|trout|bees|ferrets?|rabbits?)\b", re.IGNORECASE)


def species_flag(gi: dict, text_head: str = "") -> str:
    """'dog' if the summary's species field (or its first lines) names dogs, 'other' if it
    names only another species, 'unknown' otherwise. Applications approved for several species
    carry one FOI summary per species/supplement, so a dog application can own a cat summary."""
    field = gi.get("species_class") or gi.get("species") or ""
    src = field if field.strip(" .") else text_head[:1500]
    if _DOG_RE.search(src):
        return "dog"
    if _OTHER_RE.search(src):
        return "other"
    return "unknown"


_SENT_SPLIT = re.compile(r"(?<=[.;])\s+(?=[A-Z(])")


def sentences_with(text: str, terms: tuple[str, ...], max_n: int = 25) -> list[str]:
    out = []
    for s in _SENT_SPLIT.split(re.sub(r"\s+", " ", text)):
        low = s.lower()
        if any(t in low for t in terms) and 12 <= len(s) <= 500:
            out.append(s.strip())
            if len(out) >= max_n:
                break
    return out


def dose_mentions(text: str, max_n: int = 30) -> list[str]:
    seen, out = set(), []
    for m in DOSE_RE.finditer(text):
        s = re.sub(r"\s+", " ", m.group(0)).strip()
        if s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
        if len(out) >= max_n:
            break
    return out


def parse_summary(text: str) -> dict:
    sections = split_sections(text)
    gi = parse_general_information(sections.get("general_information") or sections.get("preamble") or text[:6000])
    eff = sections.get("effectiveness", "")
    tas = sections.get("target_animal_safety", "")
    return {
        "sections_found": [k for k in sections if k != "preamble"],
        "general_information": gi,
        "pk_sentences": sentences_with(eff + "\n" + sections.get("general_information", ""), PK_TERMS),
        "safety_sentences": sentences_with(tas, SAFETY_TERMS),
        "dose_mentions": dose_mentions(text),
        "section_chars": {k: len(v) for k, v in sections.items()},
        "sections": sections,
    }
