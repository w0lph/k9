"""Build the static evidence site (docs/) from the dog-geroscience database.

Deterministic and model-free: every page is templated from database rows, every figure sits
next to its verbatim quote and source identifier, and no live service is called. Run from the
mcp project:

    uv run python scripts/build_site.py [--db data/dog_geroscience.sqlite] [--out ../docs]

Pages:
    index.html                     what the site is, counts, sources, licences
    interventions/index.html       every NIA ITP compound plus veterinary comparators
    interventions/<slug>.html      the intervention dossier (DrugAge, dog-equivalent doses,
                                   canine literature, FDA FOI summaries, gaps)
    fda-foi/index.html             every ingredient with an FDA CVM FOI summary for a dog product
    fda-foi/<slug>.html            products, dose regimen, PK values, target-animal safety,
                                   effectiveness, adverse reactions, each with its quote
    trials/index.html              the canine aging trial registry (trials/data/canine_trials.jsonl)
    trials/<id>.html               one typed record per study with its verbatim source quotes
    llms.txt, sitemap.xml, robots.txt

Files in scripts/site_static/ (search-engine verification files such as google<token>.html or
BingSiteAuth.xml) are copied verbatim into the site root on every build, and
scripts/site_static/verification.json ({"google-site-verification": "<token>", ...}) becomes
<meta> tags on the home page, so verification survives a rebuild.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import io
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

from dog_geroscience_mcp import dossier, queries

import og_images  # noqa: E402  (same directory)
import why_dogs  # noqa: E402  (same directory)

BASE_URL = "https://w0lph.github.io/k9"
STATIC_DIR = Path(__file__).resolve().parent / "site_static"
TRIALS_PATH = Path(__file__).resolve().parents[2] / "trials" / "data" / "canine_trials.jsonl"
KIND_LABEL = {"randomized_controlled_trial": "randomized controlled trial", "controlled_trial": "controlled trial",
              "single_arm_trial": "single-arm trial", "crossover_trial": "crossover trial", "pilot_study": "pilot study",
              "longitudinal_cohort": "longitudinal cohort", "regulatory_program": "company regulatory program"}
REPO = "https://github.com/w0lph/k9"
HF = "https://huggingface.co/datasets/w0lph"
VET_COMPARATORS = ["Selegiline", "Carprofen"]


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKC", name).lower().replace("‐", "-")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "x"


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def pubmed(pmid, doi=None) -> str:
    if pmid:
        return f'<a href="https://pubmed.ncbi.nlm.nih.gov/{esc(pmid)}/">PMID {esc(pmid)}</a>'
    if doi:
        return f'<a href="https://doi.org/{esc(doi)}">doi:{esc(doi)}</a>'
    return ""


def plain_snippet(text) -> str:
    """corpus_search marks matched terms with [brackets]; the static page shows the plain text."""
    return re.sub(r"\[([^\]]+)\]", r"\1", text or "")


def table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    """columns: list of (key, header). Missing keys render empty."""
    if not rows:
        return "<p class=\"none\">None recorded.</p>"
    head = "".join(f"<th>{esc(h)}</th>" for _, h in columns)
    body = []
    for r in rows:
        cells = []
        for k, _ in columns:
            v = r.get(k)
            if k == "pubmed_id":
                cells.append(f"<td>{pubmed(v)}</td>")
            elif k == "quote":
                cells.append(f"<td><q>{esc(v)}</q></td>")
            else:
                cells.append(f"<td>{esc(v)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def quote_block(text) -> str:
    return f'<blockquote><q>{esc(text)}</q></blockquote>' if text else ""


BUILD_DATE = dt.date.today().isoformat()  # replaced by the database build date in build()


def page(title: str, description: str, body: str, path: str, jsonld: dict | None = None, depth: int = 1,
         head_extra: str = "", image: str = "og-default.png") -> str:
    root = "../" * depth if depth else "./"
    canonical = f"{BASE_URL}/{path}"
    og = (f'<meta property="og:type" content="article">\n<meta property="og:title" content="{esc(title)}">\n'
          f'<meta property="og:description" content="{esc(description)}">\n<meta property="og:url" content="{esc(canonical)}">\n'
          f'<meta property="og:image" content="{BASE_URL}/{esc(image)}">\n<meta property="og:image:width" content="1200">\n'
          f'<meta property="og:image:height" content="630">\n<meta property="og:site_name" content="Canine geroscience evidence">\n'
          f'<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:title" content="{esc(title)}">\n'
          f'<meta name="twitter:description" content="{esc(description)}">\n<meta name="twitter:image" content="{BASE_URL}/{esc(image)}">')
    ld = ""
    if jsonld:
        ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
{og}
<link rel="stylesheet" href="{root}style.css">
{head_extra}{ld}
</head>
<body>
<header><nav>
<a href="{root}index.html">Canine geroscience evidence</a> ·
<a href="{root}why-dogs.html">Why dogs</a> ·
<a href="{root}interventions/index.html">Interventions</a> ·
<a href="{root}fda-foi/index.html">FDA FOI summaries</a> ·
<a href="{root}trials/index.html">Trial registry</a> ·
<a href="{REPO}">Source</a>
</nav></header>
<main>
{body}
</main>
<footer>
<p>Generated from the <a href="{REPO}/tree/main/mcp">dog-geroscience-mcp</a> database (built {BUILD_DATE}) with no model-written text: every value is templated from a database row and shown with its verbatim quote and identifier. Data: HAGR AnAge/DrugAge/GenAge (CC BY 3.0); Europe PMC metadata and abstracts (Europe PMC terms); FDA Center for Veterinary Medicine FOI summaries (US Government works, public domain); structured extractions and page text CC BY 4.0. Datasets: <a href="{HF}/canine-aging-corpus">corpus</a>, <a href="{HF}/foi-summaries-dog">FOI summaries</a>, <a href="{HF}/dog-geroscience-mcp-data">database</a>. Install the tools: <code>uvx dog-geroscience-mcp</code>.</p>
</footer>
</body>
</html>
"""


def write(out: Path, rel: str, content: str) -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline="\n").write(content)


# ------------------------------------------------------------------ interventions

DRUGAGE_COLS = [
    ("species", "Species"), ("strain", "Strain"), ("dosage", "Dose"), ("age_at_initiation", "Age at start"),
    ("treatment_duration", "Duration"), ("gender", "Sex"), ("avg_lifespan_change_percent", "Mean lifespan Δ%"),
    ("avg_lifespan_significance", "Mean sig."), ("max_lifespan_change_percent", "Max lifespan Δ%"),
    ("max_lifespan_significance", "Max sig."), ("pubmed_id", "Source"),
]
DOSE_COLS = [
    ("species", "Species"), ("dosage_as_reported", "Reported dose"), ("mg_per_kg", "mg/kg"),
    ("factor", "Km factor"), ("dog_equivalent_mg_per_kg", "Dog-equivalent mg/kg"), ("itp", "ITP"), ("pubmed_id", "Source"),
]


def render_intervention(conn: sqlite3.Connection, compound: str, ingredient_slugs: dict[str, str],
                        trial_records: list[dict] | None = None) -> tuple[str, str, dict]:
    d = dossier.build_dossier(conn, compound, include_openfda=False, corpus_limit=15)
    da, corp = d["drugage"], d["corpus"]
    by_species = ", ".join(f"{esc(k)} {v}" for k, v in sorted(da["by_species"].items(), key=lambda kv: -kv[1])) or "none"
    itp_rows, dog_rows = da["itp_rows"], da["dog_rows"]
    other = [r for r in da["other_rows_sample"] if r not in itp_rows]
    hits = corp["top_core_hits"]
    trials = corp["dog_trials"]
    foi = d["foi_summaries_dog"] or []
    struct = d.get("foi_structured") or []

    parts = [f"<h1>{esc(compound)} in dogs: the evidence</h1>",
             f"<p class=\"lede\">What the aging-research databases and the canine literature hold for {esc(compound)} "
             f"(names searched: {esc(', '.join(d['names_searched']))}). Compiled from DrugAge, the canine aging corpus and "
             f"FDA CVM FOI summaries; nothing here is inferred.</p>"]

    parts.append("<h2>Lifespan experiments in other species (DrugAge)</h2>")
    parts.append(f"<p>{da['n_experiments']} experiments recorded, by species: {by_species}.</p>")
    if itp_rows:
        parts.append("<h3>NIA Interventions Testing Program rows</h3>" + table(itp_rows, DRUGAGE_COLS))
    if other:
        parts.append("<h3>Other DrugAge rows (sample)</h3>" + table(other, DRUGAGE_COLS))

    parts.append("<h2>Lifespan experiments in dogs (DrugAge)</h2>")
    parts.append(table(dog_rows, DRUGAGE_COLS) if dog_rows else "<p class=\"none\">DrugAge records no dog lifespan experiment for this compound.</p>")

    parts.append("<h2>Dog-equivalent doses (allometric starting points, not recommendations)</h2>")
    dose_rows = d["dog_equivalent_doses"]["rows"]
    parts.append(f"<p>Method: {esc(d['dog_equivalent_doses']['method'])}.</p>")
    parts.append(table(dose_rows, DOSE_COLS) if dose_rows else "<p class=\"none\">No mg/kg dose in DrugAge to translate (doses reported as ppm of diet or a concentration).</p>")

    parts.append("<h2>Canine aging literature (Europe PMC corpus)</h2>")
    parts.append(f"<p>{corp['records_mentioning_compound']} corpus records mention this compound.</p>")
    if trials:
        parts.append("<h3>Records matching randomized or placebo-controlled trial vocabulary</h3><ul>")
        for t in trials:
            parts.append(f"<li>{esc(t.get('title'))} ({esc(t.get('journal'))}, {esc(t.get('year'))}). {pubmed(t.get('pmid'), t.get('doi'))}"
                         + (f"<br><small>{esc(plain_snippet(t.get('snippet')))}</small>" if t.get("snippet") else "") + "</li>")
        parts.append("</ul>")
    if hits:
        parts.append("<h3>Top hits in the core tier</h3><ul>")
        for h in hits:
            parts.append(f"<li>{esc(h.get('title'))} ({esc(h.get('journal'))}, {esc(h.get('year'))}). {pubmed(h.get('pmid'), h.get('doi'))}</li>")
        parts.append("</ul>")

    matched = trials_for_compound(trial_records or [], d["names_searched"])
    parts.append("<h2>Trials and cohorts in the canine aging trial registry</h2>")
    if matched:
        parts.append("<ul>" + "".join(f'<li><a href="../trials/{esc(t["id"])}.html">{esc(t["name"])}</a> ({esc(t.get("status"))})'
                                      + (f": {esc(t['result'])}" if t.get("result") else "") + "</li>" for t in matched) + "</ul>")
    else:
        parts.append("<p class=\"none\">No registered study of this compound in dogs.</p>")

    parts.append("<h2>FDA CVM FOI summaries for dog products</h2>")
    if foi:
        parts.append("<ul>")
        for f in foi:
            slug = ingredient_slugs.get((f.get("ingredients") or "").strip().lower())
            link = f' · <a href="../fda-foi/{slug}.html">structured record</a>' if slug else ""
            parts.append(f"<li>{esc(f.get('proprietary_name'))} (NADA {esc(f.get('application_number'))}, {esc(f.get('approval_type'))}, "
                         f"{esc(f.get('approval_date'))}; species flag {esc(f.get('species_flag'))}; foi_id {esc(f.get('foi_id'))}) "
                         f'· <a href="{esc(f.get("pdf_url"))}">FDA PDF</a>{link}</li>')
        parts.append("</ul>")
    else:
        parts.append("<p class=\"none\">No FDA FOI summary for a dog product contains this ingredient (it is not a marketed veterinary product).</p>")

    parts.append("<h2>Evidence gaps reported by the dossier tool</h2><ul>" + "".join(f"<li>{esc(g)}</li>" for g in d["gaps"]) + "</ul>")
    parts.append(f"<p class=\"repro\">Reproduce: <code>intervention_dossier(compound=\"{esc(compound)}\")</code> in dog-geroscience-mcp.</p>")

    title = f"{compound} in dogs: lifespan evidence, dose translation, FDA summaries"
    desc = (f"Evidence on {compound} for canine aging research: {da['n_experiments']} DrugAge lifespan experiments "
            f"({len(itp_rows)} ITP rows, {len(dog_rows)} in dogs), {corp['records_mentioning_compound']} canine aging papers, "
            f"{len(foi)} FDA FOI summaries.")
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc,
          "about": {"@type": "Drug", "name": compound}, "license": "https://creativecommons.org/licenses/by/4.0/",
          "isBasedOn": [f"{HF}/canine-aging-corpus", f"{HF}/foi-summaries-dog", "https://genomics.senescence.info/drugs/"]}
    return title, desc, {"html": "\n".join(parts), "jsonld": ld, "n_itp": len(itp_rows), "n_dog": len(dog_rows),
                         "n_corpus": corp["records_mentioning_compound"], "n_foi": len(foi)}


# ------------------------------------------------------------------ FDA FOI ingredient pages

def load_json(v):
    if v in (None, ""):
        return None
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return v


def render_ingredient(name: str, records: list[dict]) -> tuple[str, str, str, dict]:
    products = sorted({(r.get("proprietary_name") or r.get("product_name") or "", r.get("application_number") or "") for r in records})
    species = sorted({(r.get("species_class") or "").strip() for r in records if r.get("species_class")})
    parts = [f"<h1>{esc(name)}: what the FDA reviewed for dog products</h1>",
             f"<p class=\"lede\">{len(records)} Freedom of Information summar{'y' if len(records) == 1 else 'ies'} from the FDA Center for "
             f"Veterinary Medicine for products containing {esc(name)}, as typed records: every value below is followed by the "
             f"verbatim passage it was taken from. Species as stated by each summary: {esc('; '.join(species) or 'not stated')}.</p>"]
    parts.append("<h2>Products</h2><ul>" + "".join(
        f"<li>{esc(p)} (NADA/ANADA {esc(a)})</li>" for p, a in products) + "</ul>")
    n_pk = n_ar = 0
    for r in sorted(records, key=lambda x: (str(x.get("approval_date") or ""), int(x["foi_id"]))):
        pk = load_json(r.get("pharmacokinetics")) or []
        tas = load_json(r.get("target_animal_safety")) or {}
        eff = load_json(r.get("effectiveness")) or {}
        ars = load_json(r.get("adverse_reactions")) or []
        n_pk += len(pk); n_ar += len(ars)
        parts.append(f"<section class=\"record\"><h2>{esc(r.get('proprietary_name') or r.get('product_name'))} "
                     f"<small>NADA {esc(r.get('application_number'))}, {esc(r.get('approval_type'))}, {esc(r.get('approval_date'))}; "
                     f"sponsor {esc(r.get('sponsor'))}; species: {esc(r.get('species_class'))}; foi_id {esc(r.get('foi_id'))}; "
                     f'<a href="{esc(r.get("pdf_url"))}">FDA PDF</a></small></h2>')
        if r.get("indication"):
            parts.append(f"<h3>Indication</h3><p>{esc(r['indication'])}</p>")
        if r.get("dose") or r.get("dose_quote"):
            regimen = ", ".join(esc(x) for x in (r.get("dose"), r.get("route"), r.get("frequency"), r.get("duration_or_conditions")) if x)
            parts.append(f"<h3>Dose regimen</h3><p>{regimen}</p>" + quote_block(r.get("dose_quote")))
        if pk:
            parts.append("<h3>Pharmacokinetics</h3>" + table(pk, [("parameter", "Parameter"), ("value", "Value"), ("conditions", "Conditions"), ("quote", "Quote")]))
        if tas and (tas.get("findings") or tas.get("dose_multiples") or tas.get("design_quote")):
            parts.append("<h3>Target-animal safety</h3>")
            meta = []
            if tas.get("dose_multiples"):
                meta.append("dose multiples " + esc(", ".join(map(str, tas["dose_multiples"]))))
            if tas.get("duration"):
                meta.append("duration " + esc(tas["duration"]))
            if tas.get("n_animals"):
                meta.append("animals " + esc(tas["n_animals"]))
            if meta:
                parts.append("<p>" + "; ".join(meta) + ".</p>")
            parts.append(quote_block(tas.get("design_quote")))
            if tas.get("findings"):
                parts.append(table(tas["findings"], [("finding", "Finding"), ("quote", "Quote")]))
        if eff and (eff.get("quote") or eff.get("result")):
            parts.append("<h3>Effectiveness</h3>")
            meta = [esc(x) for x in (eff.get("design"), f"n = {eff['n_dogs']}" if eff.get("n_dogs") else None,
                                     f"primary endpoint: {eff['primary_endpoint']}" if eff.get("primary_endpoint") else None,
                                     f"result: {eff['result']}" if eff.get("result") else None) if x]
            parts.append("<p>" + "; ".join(meta) + "</p>" + quote_block(eff.get("quote")))
        if ars:
            parts.append("<h3>Adverse reactions</h3>" + table(ars, [("term", "Term"), ("treated", "Treated"), ("control", "Control"), ("quote", "Quote")]))
        if r.get("notes"):
            parts.append(f"<p class=\"notes\">Extraction notes: {esc(r['notes'])}</p>")
        parts.append("</section>")
    parts.append(f"<p class=\"repro\">Reproduce: <code>foi_structured_search(query=\"{esc(name)}\")</code> and "
                 f"<code>foi_summary_get(foi_id=...)</code> in dog-geroscience-mcp; dataset <a href=\"{HF}/foi-summaries-dog\">foi-summaries-dog</a> (config <code>structured</code>).</p>")
    title = f"{name}: FDA FOI summaries for dog products (dose, PK, safety, effectiveness)"
    desc = (f"{len(records)} FDA CVM FOI summaries for products containing {name}: dose regimen, {n_pk} pharmacokinetic values, "
            f"target-animal-safety findings, effectiveness studies and {n_ar} adverse-reaction rows, each with its verbatim quote.")
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc,
          "about": {"@type": "Drug", "name": name, "activeIngredient": name},
          "license": "https://creativecommons.org/licenses/by/4.0/", "isBasedOn": f"{HF}/foi-summaries-dog"}
    return title, desc, "\n".join(parts), {"jsonld": ld, "n_records": len(records), "n_pk": n_pk, "n_ar": n_ar, "species": species}


# ------------------------------------------------------------------ trial registry

def source_link(src: dict) -> str:
    if src.get("type") in ("pmid", "europepmc") and src.get("pmid"):
        label = esc(src.get("title") or f"PMID {src['pmid']}")
        return f'{label} ({esc(src.get("year"))}) {pubmed(src["pmid"], src.get("doi"))}'
    if src.get("type") == "web":
        return f'{esc(src.get("title") or src.get("slug"))} ({esc(src.get("year"))}), snapshot <code>{esc(src.get("slug"))}</code>'
    return esc(src.get("title") or "")


def render_trial(r: dict, all_ids: set[str]) -> tuple[str, str, str, dict]:
    pop = r.get("population") or {}
    kind = KIND_LABEL.get(r.get("kind"), r.get("kind"))
    parts = [f"<h1>{esc(r['name'])}</h1>",
             f"<p class=\"lede\">{esc(r.get('summary'))}</p>"]
    facts = [("Design", kind), ("Status", r.get("status")), ("Setting", (r.get("setting") or "").replace("_", " ") or None),
             ("Intervention", r.get("intervention")), ("Intervention class", (r.get("intervention_class") or "").replace("_", " ") or None),
             ("Comparator", r.get("comparator")), ("Dose regimen", r.get("dose_regimen")), ("Duration", r.get("duration")),
             ("Dogs", f"{pop.get('n'):,}" if pop.get("n") else None), ("Population note", pop.get("n_note")), ("Breed", pop.get("breed")),
             ("Age", pop.get("age")), ("Other", pop.get("other")), ("Primary outcome", r.get("primary_outcome")),
             ("Result (as reported)", r.get("result")), ("Lead organisation", r.get("lead_organization")),
             ("Sponsor or funder", r.get("sponsor_or_funder")), ("Start year", r.get("start_year")), ("End year", r.get("end_year")),
             ("Registrations", ", ".join(f"{x.get('registry')} {x.get('id')}" for x in r.get("registration") or []) or None),
             ("Parent study", f'<a href="{esc(r["parent_id"])}.html">{esc(r["parent_id"])}</a>' if r.get("parent_id") in all_ids else None),
             ("Tags", ", ".join(r.get("tags") or []) or None)]
    parts.append("<h2>Record</h2><table><tbody>" + "".join(
        f"<tr><th>{esc(k)}</th><td>{v if k == 'Parent study' else esc(v)}</td></tr>" for k, v in facts if v not in (None, "")) + "</tbody></table>")
    if r.get("notes"):
        parts.append(f"<p class=\"notes\">Notes: {esc(r['notes'])}</p>")
    parts.append("<h2>Sources and verbatim quotes</h2>")
    for src in r.get("sources") or []:
        parts.append(f"<h3>{source_link(src)}" + (f" <small>({esc(src.get('role'))})</small>" if src.get("role") else "") + "</h3>")
        parts.append("<ul>" + "".join(f"<li><q>{esc(q)}</q></li>" for q in src.get("quotes") or []) + "</ul>")
    parts.append(f"<p class=\"repro\">Reproduce: <code>canine_trial_search(trial_id=\"{esc(r['id'])}\")</code> in dog-geroscience-mcp; "
                 f"dataset <a href=\"{HF}/canine-trial-registry\">canine-trial-registry</a>.</p>")
    title = f"{r['name']}: canine aging trial registry record"
    desc = (r.get("summary") or "")[:300]
    ld = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc,
          "about": {"@type": "MedicalStudy", "name": r["name"], "status": r.get("status")},
          "license": "https://creativecommons.org/licenses/by/4.0/", "isBasedOn": f"{HF}/canine-trial-registry"}
    return title, desc, "\n".join(parts), {"jsonld": ld}


def build_trials(out: Path, urls: list[str]) -> list[dict]:
    if not TRIALS_PATH.exists():
        return []
    records = [json.loads(l) for l in TRIALS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    ids = {r["id"] for r in records}
    for r in records:
        title, desc, body, meta = render_trial(r, ids)
        write(out, f"trials/{r['id']}.html", page(title, desc, body, f"trials/{r['id']}.html", meta["jsonld"], depth=1))
        urls.append(f"trials/{r['id']}.html")
    by_kind = defaultdict(list)
    for r in records:
        by_kind[r.get("kind")].append(r)
    n_completed = sum(1 for r in records if r.get("status") == "completed")
    n_ongoing = sum(1 for r in records if r.get("status") == "ongoing")
    body = ["<h1>Canine aging trial registry</h1>",
            f"<p class=\"lede\">{len(records)} interventional studies and cohorts on aging in dogs ({n_completed} completed, {n_ongoing} ongoing): "
            "lifespan and healthspan trials, cognitive-aging and mobility trials in senior dogs, immunosenescence and organ-decline "
            "interventions, lifetime cohorts and company regulatory programs. Each record is typed and every field is backed by a "
            "verbatim quote from its source; veterinary trials have no ClinicalTrials.gov, so this is the only such registry.</p>"]
    order = ["randomized_controlled_trial", "controlled_trial", "crossover_trial", "single_arm_trial", "pilot_study", "regulatory_program", "longitudinal_cohort"]
    for kind in order + [k for k in by_kind if k not in order]:
        rows = by_kind.get(kind)
        if not rows:
            continue
        body.append(f"<h2>{esc(KIND_LABEL.get(kind, kind)).capitalize()}s</h2>")
        body.append("<table><thead><tr><th>Study</th><th>Intervention</th><th>Dogs</th><th>Status</th><th>Years</th><th>Result (as reported)</th></tr></thead><tbody>")
        for r in sorted(rows, key=lambda x: (x.get("start_year") or x.get("end_year") or 0, x["name"])):
            pop = r.get("population") or {}
            years = "–".join(str(y) for y in (r.get("start_year"), r.get("end_year")) if y) if (r.get("start_year") or r.get("end_year")) else ""
            body.append(f'<tr><td><a href="{esc(r["id"])}.html">{esc(r["name"])}</a></td><td>{esc(r.get("intervention") or "")}</td>'
                        f'<td>{pop.get("n") or ""}</td><td>{esc(r.get("status"))}</td><td>{esc(years)}</td><td>{esc((r.get("result") or "")[:220])}</td></tr>')
        body.append("</tbody></table>")
    write(out, "trials/index.html", page("Canine aging trial registry",
                                         f"Registry of {len(records)} interventional studies and cohorts on aging in dogs, each typed and backed by verbatim source quotes.",
                                         "\n".join(body), "trials/index.html", depth=1))
    urls.append("trials/index.html")
    return records


def trials_for_compound(records: list[dict], names: list[str]) -> list[dict]:
    keys = [n.lower() for n in names if n]
    out = []
    for r in records:
        hay = " ".join(str(x) for x in (r.get("name"), r.get("intervention"), " ".join(r.get("tags") or []))).lower()
        if any(k in hay for k in keys):
            out.append(r)
    return out


# ------------------------------------------------------------------ site

CSS = """
:root{--fg:#1d1d1f;--muted:#5d5d63;--bg:#fff;--line:#d9d9de;--link:#0b57d0;--q:#f4f4f6}
@media(prefers-color-scheme:dark){:root{--fg:#e8e8ea;--muted:#a0a0a8;--bg:#121214;--line:#34343a;--link:#8ab4f8;--q:#1c1c20}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header,main,footer{max-width:960px;margin:0 auto;padding:12px 16px}
nav a{color:var(--link);text-decoration:none}nav{border-bottom:1px solid var(--line);padding-bottom:8px}
h1{font-size:1.6rem;line-height:1.25}h2{font-size:1.2rem;margin-top:1.6em;border-bottom:1px solid var(--line)}h3{font-size:1rem;margin-bottom:.3em}
h2 small{font-weight:normal;color:var(--muted);font-size:.8rem}
.lede{color:var(--muted)}.none{color:var(--muted);font-style:italic}.notes,.repro{color:var(--muted);font-size:.9rem}
table{border-collapse:collapse;width:100%;font-size:.9rem;margin:.5em 0}th,td{border:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}
q{quotes:'“' '”'}blockquote{margin:.4em 0 .8em;padding:.4em .8em;background:var(--q);border-left:3px solid var(--line);font-size:.92rem}
footer{color:var(--muted);font-size:.85rem;border-top:1px solid var(--line);margin-top:2em}
a{color:var(--link)}code{font-size:.9em}ul{padding-left:1.2em}section.record{margin-top:1.5em}
figure{margin:1em 0}figure svg{max-width:100%;height:auto}figcaption{color:var(--muted);font-size:.85rem}
.calc{border:1px solid var(--line);border-radius:6px;padding:.6em 1em;margin:1em 0}.calc label{display:inline-block;margin:.3em 1.2em .3em 0}.calc select,.calc input{font:inherit;padding:2px 4px}
.refs{font-size:.88rem}.refs li{margin:.3em 0}sup a{text-decoration:none}
"""


def build(db: Path, out: Path) -> dict:
    global BUILD_DATE
    conn = queries.connect(db)
    info = queries.build_info(conn)
    BUILD_DATE = (info.get("built_at") or dt.datetime.now(dt.timezone.utc).isoformat())[:10]
    out.mkdir(parents=True, exist_ok=True)
    write(out, "style.css", CSS.strip() + "\n")
    write(out, ".nojekyll", "")
    og_images.default_image(out / "og-default.png", "Canine geroscience evidence",
                            "Source-linked pages on aging research in companion dogs: interventions, trials, FDA reviews, and why dogs are the route to human geroscience.",
                            "w0lph.github.io/k9")
    verification_meta = ""
    if STATIC_DIR.is_dir():
        for f in sorted(STATIC_DIR.iterdir()):
            if f.name == "verification.json":
                tokens = json.loads(f.read_text(encoding="utf-8"))
                verification_meta = "".join(f'<meta name="{esc(k)}" content="{esc(v)}">\n' for k, v in sorted(tokens.items()) if v)
            elif f.is_file() and f.name != "README.md":
                (out / f.name).write_bytes(f.read_bytes())

    # FOI ingredient pages
    rows = [dict(r) for r in conn.execute(
        "SELECT s.*, d.proprietary_name, d.sponsor, d.approval_type, d.approval_date, d.pdf_url, d.species_flag "
        "FROM foi_structured s LEFT JOIN foi_dog d ON d.foi_id = s.foi_id")]
    by_ing: dict[str, list[dict]] = defaultdict(list)
    display: dict[str, str] = {}
    for r in rows:
        key = (r.get("ingredient") or "").strip().lower()
        if not key:
            continue
        by_ing[key].append(r)
        display.setdefault(key, (r.get("ingredient") or "").strip())
    ingredient_slugs = {k: slugify(display[k]) for k in by_ing}
    foi_index = []
    urls = []
    for key, recs in sorted(by_ing.items(), key=lambda kv: display[kv[0]].lower()):
        slug = ingredient_slugs[key]
        title, desc, body, meta = render_ingredient(display[key], recs)
        write(out, f"fda-foi/{slug}.html", page(title, desc, body, f"fda-foi/{slug}.html", meta["jsonld"], depth=1))
        foi_index.append((display[key], slug, meta))
        urls.append(f"fda-foi/{slug}.html")
    body = ["<h1>FDA CVM FOI summaries for dog products, by ingredient</h1>",
            f"<p class=\"lede\">{len(foi_index)} ingredients, {len(rows)} summaries. Each page lists the products and, for every summary, "
            "the dose regimen, pharmacokinetic values, target-animal-safety study, effectiveness study and adverse reactions, "
            "each value with the verbatim passage it came from.</p>", "<ul>"]
    for name, slug, meta in foi_index:
        body.append(f'<li><a href="{slug}.html">{esc(name)}</a> — {meta["n_records"]} summar{"y" if meta["n_records"] == 1 else "ies"}, '
                    f'{meta["n_pk"]} PK values, {meta["n_ar"]} adverse-reaction rows; species: {esc("; ".join(meta["species"]) or "not stated")}</li>')
    body.append("</ul>")
    write(out, "fda-foi/index.html", page("FDA FOI summaries for dog products, by ingredient",
                                          f"Index of {len(foi_index)} active ingredients with FDA CVM FOI summaries for dog products, as typed, quote-grounded records.",
                                          "\n".join(body), "fda-foi/index.html", depth=1))
    urls.append("fda-foi/index.html")

    # Trial registry pages
    trial_records = build_trials(out, urls)

    # Intervention pages: every ITP compound + veterinary comparators
    itp = [r[0] for r in conn.execute("SELECT DISTINCT compound_name FROM drugage WHERE itp='Yes' ORDER BY 1")]
    compounds = list(dict.fromkeys(itp + VET_COMPARATORS))
    inter_index = []
    for c in compounds:
        slug = slugify(c)
        title, desc, r = render_intervention(conn, c, ingredient_slugs, trial_records)
        write(out, f"interventions/{slug}.html", page(title, desc, r["html"], f"interventions/{slug}.html", r["jsonld"], depth=1))
        inter_index.append((c, slug, r))
        urls.append(f"interventions/{slug}.html")
    n_itp_compounds = len(itp)
    n_with_dog = sum(1 for c, _, r in inter_index if c in itp and r["n_dog"])
    n_with_corpus = sum(1 for c, _, r in inter_index if c in itp and r["n_corpus"])
    body = ["<h1>Interventions: what is known in dogs</h1>",
            f"<p class=\"lede\">Every compound the NIA Interventions Testing Program has tested for lifespan in mice "
            f"({n_itp_compounds} compounds in DrugAge), plus veterinary comparators. For each: DrugAge experiments by species, "
            f"dog-equivalent doses by the FDA Km method, the canine aging literature, FDA FOI summaries, and the gaps.</p>",
            f"<p>Of the {n_itp_compounds} ITP compounds, {n_with_dog} {'has' if n_with_dog == 1 else 'have'} a dog lifespan experiment in DrugAge and "
            f"{n_with_corpus} {'is' if n_with_corpus == 1 else 'are'} mentioned anywhere in the {conn.execute('SELECT COUNT(*) FROM corpus_records').fetchone()[0]:,}-record canine aging corpus.</p>",
            "<table><thead><tr><th>Compound</th><th>ITP rows</th><th>Dog lifespan rows</th><th>Canine papers mentioning it</th><th>FDA FOI summaries</th></tr></thead><tbody>"]
    for c, slug, r in inter_index:
        body.append(f'<tr><td><a href="{slug}.html">{esc(c)}</a></td><td>{r["n_itp"]}</td><td>{r["n_dog"]}</td><td>{r["n_corpus"]}</td><td>{r["n_foi"]}</td></tr>')
    body.append("</tbody></table>")
    write(out, "interventions/index.html", page("Interventions tested for lifespan: the dog evidence",
                                                 f"For each of the {n_itp_compounds} NIA ITP compounds and veterinary comparators: DrugAge experiments, dog-equivalent doses, canine literature, FDA FOI summaries and gaps.",
                                                 "\n".join(body), "interventions/index.html", depth=1))
    urls.append("interventions/index.html")

    # Why dogs: the canonical argument page
    wd_title, wd_desc, wd_body, wd_svg, wd_stats = why_dogs.render(conn, inter_index, esc)
    why_dogs.preview_image(out / "og-why-dogs.png", wd_stats)
    write(out, "why-dogs.html", page(wd_title, wd_desc, wd_body, "why-dogs.html", {"@context": "https://schema.org", "@type": "Article", "headline": wd_title, "description": wd_desc,
                                                                        "license": "https://creativecommons.org/licenses/by/4.0/", "isBasedOn": [u for _, _, u in why_dogs.REFS],
                                                                        "image": f"{BASE_URL}/og-why-dogs.png"}, depth=0, image="og-why-dogs.png"))
    write(out, "why-dogs-years-to-answer.svg", wd_svg + chr(10))
    urls.append("why-dogs.html")

    # Home
    n_corpus = conn.execute("SELECT COUNT(*) FROM corpus_records").fetchone()[0]
    n_foi = conn.execute("SELECT COUNT(*) FROM foi_dog").fetchone()[0]
    body = f"""<h1>Canine geroscience evidence</h1>
<p class="lede">Companion dogs are the one model in which a lifespan intervention can be read out in years rather than decades, in animals that share our environment and our age-related diseases. This site lays out, page by page and with sources, what the aging-research databases, the canine literature and the FDA's veterinary drug reviews actually hold for dogs. It is generated from a database, not written by a model: every figure sits next to the passage it came from.</p>
<h2>Sections</h2>
<ul>
<li><a href="why-dogs.html">Why the path to human longevity runs through dogs</a>: the argument, every claim cited, with the years-to-answer chart and a calculator that sizes the same lifespan trial in dogs and in people.</li>
<li><a href="interventions/index.html">Interventions</a>: for every compound the NIA Interventions Testing Program tested in mice ({n_itp_compounds}) plus veterinary comparators, the dog evidence and the gaps. {n_with_dog} of {n_itp_compounds} {'has' if n_with_dog == 1 else 'have'} a dog lifespan experiment on record.</li>
<li><a href="trials/index.html">Canine aging trial registry</a>: {len(trial_records)} interventional studies and cohorts on aging in dogs, typed and quote-backed, including the company programs that have no publication.</li>
<li><a href="fda-foi/index.html">FDA FOI summaries by ingredient</a>: {len(foi_index)} active ingredients, {n_foi} summaries for dog products, as typed records of dose, pharmacokinetics, target-animal safety, effectiveness and adverse reactions with verbatim quotes. The only public, regulator-reviewed source of canine PK and safety-margin data.</li>
</ul>
<h2>Sources and tools</h2>
<ul>
<li>Canine aging corpus: {n_corpus:,} Europe PMC records, <a href="{HF}/canine-aging-corpus">dataset</a>.</li>
<li>FDA CVM FOI summaries for dog products and their structured extraction: <a href="{HF}/foi-summaries-dog">dataset</a>.</li>
<li>HAGR AnAge, DrugAge and GenAge (CC BY 3.0), Dog Aging Project codebooks, Ensembl orthologs, FDA Km dose table: bundled in the <a href="{HF}/dog-geroscience-mcp-data">server database</a>.</li>
<li>Agent tools: <code>uvx dog-geroscience-mcp</code> (PyPI), Claude Desktop extension and Claude Code plugin in the <a href="{REPO}">repository</a>. The pages name the tool call that reproduces them.</li>
<li>Machine-readable index for language-model crawlers: <a href="llms.txt">llms.txt</a>.</li>
</ul>
"""
    write(out, "index.html", page("Canine geroscience evidence", "Source-linked evidence pages on aging research in companion dogs: lifespan interventions, dog-equivalent doses, the canine literature, and FDA veterinary drug reviews.",
                                  body, "index.html", depth=0, head_extra=verification_meta))
    urls.insert(0, "index.html")

    # llms.txt, sitemap, robots
    llms = ["# Canine geroscience evidence", "",
            "> Source-linked, model-free evidence pages on aging research in companion dogs, generated from the dog-geroscience-mcp database. Every figure is shown with its verbatim quote and identifier (PMID, foi_id, NADA). Text CC BY 4.0; data per source.", "",
            "## Start here", f"- [Why the path to human longevity runs through dogs]({BASE_URL}/why-dogs.html): the case for companion dogs as the route to human geroscience, every claim cited, with a trial-size calculator", "",
            "## Sections", f"- [Interventions]({BASE_URL}/interventions/index.html): the dog evidence for every NIA ITP compound",
            f"- [FDA FOI summaries by ingredient]({BASE_URL}/fda-foi/index.html): dose, PK, safety and effectiveness data from FDA CVM reviews of dog products",
            f"- [Canine aging trial registry]({BASE_URL}/trials/index.html): interventional studies and cohorts on aging in dogs, typed and quote-backed", "",
            "## Trials and cohorts"]
    llms += [f"- [{r['name']}]({BASE_URL}/trials/{r['id']}.html): {KIND_LABEL.get(r.get('kind'), r.get('kind'))}, {r.get('status')}" for r in trial_records]
    llms += ["", "## Interventions"]
    llms += [f"- [{c}]({BASE_URL}/interventions/{slug}.html): {r['n_itp']} ITP rows, {r['n_dog']} dog lifespan rows, {r['n_corpus']} canine papers, {r['n_foi']} FDA FOI summaries" for c, slug, r in inter_index]
    llms += ["", "## FDA FOI summaries by ingredient"]
    llms += [f"- [{name}]({BASE_URL}/fda-foi/{slug}.html): {meta['n_records']} summaries, {meta['n_pk']} PK values, {meta['n_ar']} adverse-reaction rows" for name, slug, meta in foi_index]
    llms += ["", "## Data and tools", f"- [canine-aging-corpus]({HF}/canine-aging-corpus)", f"- [foi-summaries-dog]({HF}/foi-summaries-dog)",
             f"- [dog-geroscience-mcp-data]({HF}/dog-geroscience-mcp-data)", f"- [canine-trial-registry]({HF}/canine-trial-registry)", f"- [canine-geroscience-questions]({HF}/canine-geroscience-questions)",
             f"- [dog-geroscience-mcp source]({REPO}/tree/main/mcp)"]
    write(out, "llms.txt", "\n".join(llms) + "\n")
    today = BUILD_DATE
    write(out, "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"<url><loc>{BASE_URL}/{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    write(out, "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n")
    return {"pages": len(urls), "interventions": len(inter_index), "ingredients": len(foi_index), "foi_records": len(rows), "trials": len(trial_records), "why_dogs": wd_stats,
            "itp_compounds": n_itp_compounds, "with_dog_rows": n_with_dog, "with_corpus_mentions": n_with_corpus,
            "db_built_at": info.get("built_at")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "dog_geroscience.sqlite")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "docs")
    a = ap.parse_args(argv)
    print(json.dumps(build(a.db, a.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
