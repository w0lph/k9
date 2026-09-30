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
    llms.txt, sitemap.xml, robots.txt
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

BASE_URL = "https://w0lph.github.io/k9"
REPO = "https://github.com/w0lph/k9"
HF = "https://huggingface.co/datasets/w0lph"
VET_COMPARATORS = ["selegiline", "carprofen"]


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


def page(title: str, description: str, body: str, path: str, jsonld: dict | None = None, depth: int = 1) -> str:
    root = "../" * depth if depth else "./"
    canonical = f"{BASE_URL}/{path}"
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
<link rel="stylesheet" href="{root}style.css">
{ld}
</head>
<body>
<header><nav>
<a href="{root}index.html">Canine geroscience evidence</a> ·
<a href="{root}interventions/index.html">Interventions</a> ·
<a href="{root}fda-foi/index.html">FDA FOI summaries</a> ·
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


def render_intervention(conn: sqlite3.Connection, compound: str, ingredient_slugs: dict[str, str]) -> tuple[str, str, dict]:
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
"""


def build(db: Path, out: Path) -> dict:
    global BUILD_DATE
    conn = queries.connect(db)
    info = queries.build_info(conn)
    BUILD_DATE = (info.get("built_at") or dt.datetime.now(dt.timezone.utc).isoformat())[:10]
    out.mkdir(parents=True, exist_ok=True)
    write(out, "style.css", CSS.strip() + "\n")
    write(out, ".nojekyll", "")

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

    # Intervention pages: every ITP compound + veterinary comparators
    itp = [r[0] for r in conn.execute("SELECT DISTINCT compound_name FROM drugage WHERE itp='Yes' ORDER BY 1")]
    compounds = list(dict.fromkeys(itp + VET_COMPARATORS))
    inter_index = []
    for c in compounds:
        slug = slugify(c)
        title, desc, r = render_intervention(conn, c, ingredient_slugs)
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

    # Home
    n_corpus = conn.execute("SELECT COUNT(*) FROM corpus_records").fetchone()[0]
    n_foi = conn.execute("SELECT COUNT(*) FROM foi_dog").fetchone()[0]
    body = f"""<h1>Canine geroscience evidence</h1>
<p class="lede">Companion dogs are the one model in which a lifespan intervention can be read out in years rather than decades, in animals that share our environment and our age-related diseases. This site lays out, page by page and with sources, what the aging-research databases, the canine literature and the FDA's veterinary drug reviews actually hold for dogs. It is generated from a database, not written by a model: every figure sits next to the passage it came from.</p>
<h2>Sections</h2>
<ul>
<li><a href="interventions/index.html">Interventions</a>: for every compound the NIA Interventions Testing Program tested in mice ({n_itp_compounds}) plus veterinary comparators, the dog evidence and the gaps. {n_with_dog} of {n_itp_compounds} {'has' if n_with_dog == 1 else 'have'} a dog lifespan experiment on record.</li>
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
                                  body, "index.html", depth=0))
    urls.insert(0, "index.html")

    # llms.txt, sitemap, robots
    llms = ["# Canine geroscience evidence", "",
            "> Source-linked, model-free evidence pages on aging research in companion dogs, generated from the dog-geroscience-mcp database. Every figure is shown with its verbatim quote and identifier (PMID, foi_id, NADA). Text CC BY 4.0; data per source.", "",
            "## Sections", f"- [Interventions]({BASE_URL}/interventions/index.html): the dog evidence for every NIA ITP compound",
            f"- [FDA FOI summaries by ingredient]({BASE_URL}/fda-foi/index.html): dose, PK, safety and effectiveness data from FDA CVM reviews of dog products", "",
            "## Interventions"]
    llms += [f"- [{c}]({BASE_URL}/interventions/{slug}.html): {r['n_itp']} ITP rows, {r['n_dog']} dog lifespan rows, {r['n_corpus']} canine papers, {r['n_foi']} FDA FOI summaries" for c, slug, r in inter_index]
    llms += ["", "## FDA FOI summaries by ingredient"]
    llms += [f"- [{name}]({BASE_URL}/fda-foi/{slug}.html): {meta['n_records']} summaries, {meta['n_pk']} PK values, {meta['n_ar']} adverse-reaction rows" for name, slug, meta in foi_index]
    llms += ["", "## Data and tools", f"- [canine-aging-corpus]({HF}/canine-aging-corpus)", f"- [foi-summaries-dog]({HF}/foi-summaries-dog)",
             f"- [dog-geroscience-mcp-data]({HF}/dog-geroscience-mcp-data)", f"- [canine-geroscience-questions]({HF}/canine-geroscience-questions)",
             f"- [dog-geroscience-mcp source]({REPO}/tree/main/mcp)"]
    write(out, "llms.txt", "\n".join(llms) + "\n")
    today = BUILD_DATE
    write(out, "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"<url><loc>{BASE_URL}/{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    write(out, "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n")
    return {"pages": len(urls), "interventions": len(inter_index), "ingredients": len(foi_index), "foi_records": len(rows),
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
