"""The canonical page: why the path to human longevity runs through dogs.

Everything numeric on the page is computed here from cited sources (the two life tables, the
DrugAge ITP rows and the database counts) so the argument is reproducible; the prose cites a
source for every claim. Rendered by build_site.py as docs/why-dogs.html, with the chart also
written as a standalone SVG for reuse (CC BY 4.0).
"""

from __future__ import annotations

import html
import json
import math
import sqlite3
import statistics

from dog_geroscience_mcp import dossier

import og_images

# Annual probability of death by age interval for UK companion dogs, all breeds and both sexes,
# Teng et al. 2022, Scientific Reports, Table 2 (VetCompass, 30,563 deaths 2016-2020).
DOG_QX = {0: 0.017, 1: 0.016, 2: 0.016, 3: 0.017, 4: 0.020, 5: 0.024, 6: 0.033, 7: 0.047, 8: 0.069,
          9: 0.096, 10: 0.134, 11: 0.188, 12: 0.244, 13: 0.336}
# Probability of dying within each five-year age group, United States 2019, both sexes,
# WHO Global Health Observatory life tables (indicator LIFE_0000000030).
HUMAN_Q5 = {50: 0.0224, 55: 0.0348, 60: 0.0504, 65: 0.0701, 70: 0.1043, 75: 0.1632, 80: 0.2556}

Z_ALPHA, Z_BETA = 1.959964, 0.841621  # two-sided 0.05, power 0.80

REFS = [
    ("kaeberlein2016", "Kaeberlein M, Creevy KE, Promislow DEL. The dog aging project: translational geroscience in companion animals. Mammalian Genome 2016.", "https://doi.org/10.1007/s00335-016-9638-7"),
    ("harrison2009", "Harrison DE et al. Rapamycin fed late in life extends lifespan in genetically heterogeneous mice. Nature 2009.", "https://doi.org/10.1038/nature08221"),
    ("colman2009", "Colman RJ et al. Caloric restriction delays disease onset and mortality in rhesus monkeys. Science 2009.", "https://doi.org/10.1126/science.1173635"),
    ("mattison2012", "Mattison JA et al. Impact of caloric restriction on health and survival in rhesus monkeys from the NIA study. Nature 2012.", "https://doi.org/10.1038/nature11432"),
    ("barzilai2016", "Barzilai N, Crandall JP, Kritchevsky SB, Espeland MA. Metformin as a tool to target aging. Cell Metabolism 2016.", "https://doi.org/10.1016/j.cmet.2016.05.011"),
    ("creevy2022", "Creevy KE et al. An open science study of ageing in companion dogs. Nature 2022.", "https://doi.org/10.1038/s41586-021-04282-9"),
    ("triad2025", "Test of Rapamycin in Aging Dogs (TRIAD): study design and rationale. GeroScience 2025.", "https://doi.org/10.1007/s11357-024-01484-7"),
    ("teng2022", "Teng KT et al. Life tables of annual life expectancy and mortality for companion dogs in the United Kingdom. Scientific Reports 2022.", "https://doi.org/10.1038/s41598-022-10341-6"),
    ("who2019", "WHO Global Health Observatory. Life tables by country: probability of dying between age x and x+n, United States, 2019.", "https://www.who.int/data/gho/data/indicators/indicator-details/GHO/gho-ghe-life-tables-by-country"),
    ("kraus2013", "Kraus C, Pavard S, Promislow DEL. The size-life span trade-off decomposed: why large dogs die young. The American Naturalist 2013.", "https://doi.org/10.1086/669665"),
    ("kealy2002", "Kealy RD et al. Effects of diet restriction on life span and age-related changes in dogs. JAVMA 2002.", "https://doi.org/10.2460/javma.2002.220.1315"),
    ("lawler2008", "Lawler DF et al. Diet restriction and ageing in the dog: major observations over two decades. British Journal of Nutrition 2008.", "https://doi.org/10.1017/S0007114507871686"),
    ("ruehl1997", "Ruehl WW et al. Treatment with L-deprenyl prolongs life in elderly dogs. Life Sciences 1997.", "https://doi.org/10.1016/s0024-3205(97)00611-5"),
    ("urfer2017", "Urfer SR et al. A randomized controlled trial to establish effects of short-term rapamycin treatment in 24 middle-aged companion dogs. GeroScience 2017.", "https://doi.org/10.1007/s11357-017-9972-z"),
    ("lowdose2023", "A masked, placebo-controlled, randomized clinical trial evaluating safety and the effect on cardiac function of low-dose rapamycin in 17 healthy client-owned dogs. Frontiers in Veterinary Science 2023.", "https://doi.org/10.3389/fvets.2023.1168711"),
    ("reporter_triad", "NIH RePORTER. R01AG090843, Test of Rapamycin in Aging Dogs, Texas A&M AgriLife Research, project period 2024-12-01 to 2029-11-30.", "https://reporter.nih.gov/project-details/11027111"),
    ("gfi261", "FDA Center for Veterinary Medicine. GFI #261: Eligibility criteria for expanded conditional approval of new animal drugs (2021).", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/cvm-gfi-261-eligibility-criteria-expanded-conditional-approval-new-animal-drugs"),
    ("loy001", "dvm360. FDA determines drug for lifespan extension in large dogs to have a reasonable expectation of effectiveness (2023).", "https://dvm360.com/view/fda-determines-drug-for-lifespan-extension-in-large-dogs-to-have-a-reasonable-expectation-of-effectiveness"),
    ("loy002", "Loyal. FDA accepts the Target Animal Safety technical section for LOY-002 (13 January 2026).", "https://loyal.com/posts/loy-002-tas"),
    ("stay", "Loyal. The STAY study: 1,300 dogs at 70 veterinary practices, up to four years.", "https://loyal.com/stay"),
    ("horvath2022", "Horvath S et al. DNA methylation clocks for dogs and humans. PNAS 2022.", "https://doi.org/10.1073/pnas.2120887119"),
    ("schoenfeld1983", "Schoenfeld DA. Sample-size formula for the proportional-hazards regression model. Biometrics 1983.", "https://doi.org/10.2307/2531021"),
    ("km2005", "FDA Center for Drug Evaluation and Research. Estimating the maximum safe starting dose in initial clinical trials (2005): body-surface-area conversion factors (Km).", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/estimating-maximum-safe-starting-dose-initial-clinical-trials-therapeutics-adult-healthy-volunteers"),
]
REF_INDEX = {k: i + 1 for i, (k, _, _) in enumerate(REFS)}


def cite(*keys: str) -> str:
    return "".join(f'<sup><a href="#ref-{k}">[{REF_INDEX[k]}]</a></sup>' for k in keys)


# ------------------------------------------------------------------ life-table arithmetic

def dog_annual_qx(age: int) -> float:
    if age in DOG_QX:
        return DOG_QX[age]
    last = max(DOG_QX)
    # extrapolate beyond the table with the fitted Gompertz slope
    return min(0.95, DOG_QX[last] * math.exp(dog_gompertz_slope() * (age - last)))


def human_annual_qx(age: int) -> float:
    grp = 50 + 5 * ((age - 50) // 5)
    grp = max(50, min(80, grp))
    q5 = HUMAN_Q5[grp]
    return 1 - (1 - q5) ** (1 / 5)


def _slope(points: list[tuple[int, float]]) -> float:
    xs = [p[0] for p in points]
    ys = [math.log(p[1]) for p in points]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


def dog_gompertz_slope() -> float:
    return _slope([(a, q) for a, q in DOG_QX.items() if 7 <= a <= 13])


def human_gompertz_slope() -> float:
    return _slope([(a + 2.5, 1 - (1 - q) ** (1 / 5)) for a, q in HUMAN_Q5.items() if 60 <= a <= 80])


def median_survival_years(qx, start_age: int) -> float:
    """Years until half of a cohort starting at start_age has died (annual steps, linear within the year)."""
    alive, t = 1.0, 0
    while alive > 0.5 and t < 60:
        q = qx(start_age + t)
        nxt = alive * (1 - q)
        if nxt <= 0.5:
            return t + (alive - 0.5) / (alive - nxt)
        alive, t = nxt, t + 1
    return float(t)


def cumulative_mortality(qx, start_age: int, years: int) -> float:
    alive = 1.0
    for t in range(years):
        alive *= 1 - qx(start_age + t)
    return 1 - alive


def trial_size(qx, slope: float, start_age: int, years: int, extension_pct: float) -> dict:
    """Participants needed to detect a proportional lifespan extension in a fixed follow-up.

    Model: the intervention shifts the mortality curve later in time by a fraction of the
    starting age (a p% lifespan extension at age a delays mortality by a*p/(1+p) years). Under
    Gompertz mortality with slope b, that delay is a constant hazard ratio exp(-b*delay).
    Events needed from Schoenfeld's formula; participants = events / control-arm cumulative
    mortality over the follow-up (both arms pooled, 1:1).
    """
    p = extension_pct / 100
    delay = start_age * p / (1 + p)
    hr = math.exp(-slope * delay)
    events = 4 * (Z_ALPHA + Z_BETA) ** 2 / math.log(hr) ** 2
    cm = cumulative_mortality(qx, start_age, years)
    return {"delay_years": delay, "hazard_ratio": hr, "events": events, "cumulative_mortality": cm, "participants": events / cm}


# ------------------------------------------------------------------ data for the calculator

def itp_compounds(conn: sqlite3.Connection, inter_index: list[tuple]) -> list[dict]:
    """ITP compounds with their mouse rows, dog-equivalent doses and the dog evidence counts."""
    counts = {c: r for c, _, r in inter_index}
    out = []
    for (name,) in conn.execute("SELECT DISTINCT compound_name FROM drugage WHERE itp='Yes' ORDER BY 1"):
        rows = [dict(r) for r in conn.execute(
            "SELECT species, dosage, age_at_initiation, gender, avg_lifespan_change_percent, avg_lifespan_significance, pubmed_id "
            "FROM drugage WHERE itp='Yes' AND compound_name=? ORDER BY pubmed_id", (name,))]
        changes = []
        for r in rows:
            try:
                changes.append(float(r["avg_lifespan_change_percent"]))
            except (TypeError, ValueError):
                pass
        sig = [r for r in rows if (r.get("avg_lifespan_significance") or "").strip().upper() == "S"]
        d = dossier.build_dossier(conn, name, include_openfda=False, corpus_limit=1)
        doses = [{"species": x["species"], "reported": x["dosage_as_reported"], "mg_per_kg": x["mg_per_kg"], "dog_mg_per_kg": x["dog_equivalent_mg_per_kg"]}
                 for x in d["dog_equivalent_doses"]["rows"]]
        c = counts.get(name, {})
        out.append({
            "name": name,
            "rows": [{"species": r["species"], "dose": r["dosage"], "age": r["age_at_initiation"], "sex": r["gender"],
                      "change": r["avg_lifespan_change_percent"], "sig": r["avg_lifespan_significance"], "pmid": r["pubmed_id"]} for r in rows],
            "mean_change": round(statistics.mean(changes), 1) if changes else None,
            "best_change": max(changes) if changes else None,
            "n_sig": len(sig), "n_rows": len(rows),
            "dog_doses": doses, "n_corpus": c.get("n_corpus", 0), "n_foi": c.get("n_foi", 0), "n_dog_lifespan": c.get("n_dog", 0),
        })
    return out


# ------------------------------------------------------------------ chart

def chart_bars(dog_median: float, human_median: float) -> list[tuple[str, float, str, str]]:
    return [("Mice (ITP, rapamycin from 600 days)", 1.5, "last deaths about a year and a half after a start at 600 days", "harrison2009"),
            ("Dogs (from age 8)", dog_median, f"{dog_median:.1f} years until half the dogs have died", "teng2022"),
            ("Rhesus monkeys (calorie restriction)", 20, "20-year longitudinal study", "colman2009"),
            ("People (from age 65)", human_median, f"{human_median:.0f} years until half the people have died", "who2019")]


def preview_image(path, stats: dict) -> None:
    """1200x630 PNG of the chart for link previews (generated once; delete the file to redraw)."""
    dm, hm = stats["dog_median_from_8"], stats["human_median_from_65"]
    bars = [("Mice (ITP)", 1.5, "about 1.5 years to the last deaths"),
            ("Dogs (from age 8)", dm, f"{dm:.1f} years until half have died"),
            ("Rhesus monkeys (CR)", 20.0, "20-year study"),
            ("People (from age 65)", hm, f"{hm:.0f} years until half have died")]
    og_images.years_chart_image(path, "Years from the first dose to a lifespan answer", bars,
                                "Why the path to human longevity runs through dogs · w0lph.github.io/k9/why-dogs.html · CC BY 4.0")


def years_chart(dog_median: float, human_median: float, with_title: bool = True) -> str:
    bars = chart_bars(dog_median, human_median)
    w, h, left, top, rowh = 900, 40 + 46 * len(bars) + 30, 250, 36, 46
    maxv = 22
    scale = (w - left - 300) / maxv
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="system-ui, sans-serif" font-size="14" role="img" aria-label="Years from the first dose to a lifespan answer">']
    if with_title:
        parts.append('<title>Years from the first dose to a lifespan answer</title>')
    parts.append(f'<text x="{left}" y="22" font-size="16" font-weight="600">Years from the first dose to a lifespan answer</text>')
    for i, (label, v, note, _) in enumerate(bars):
        y = top + i * rowh
        fill = "#0b57d0" if label.startswith("Dogs") else "#9aa0a6"
        parts.append(f'<text x="{left - 10}" y="{y + 20}" text-anchor="end">{html.escape(label)}</text>')
        parts.append(f'<rect x="{left}" y="{y + 6}" width="{max(2, v * scale):.1f}" height="22" fill="{fill}" rx="3"/>')
        parts.append(f'<text x="{left + v * scale + 8:.1f}" y="{y + 22}" fill="#333">{html.escape(note)}</text>')  # bar ends by x=left+22*scale, leaving 300px for the note
    parts.append(f'<text x="{left}" y="{h - 10}" font-size="11" fill="#666">Sources: Harrison 2009; Teng 2022 (UK dog life table); Colman 2009; WHO life tables, USA 2019. CC BY 4.0, w0lph.github.io/k9/why-dogs.html</text>')
    parts.append("</svg>")
    return "\n".join(parts)


# ------------------------------------------------------------------ page

def render(conn: sqlite3.Connection, inter_index: list[tuple], esc) -> tuple[str, str, str, str, dict]:
    """Return (title, description, body_html, chart_svg, stats)."""
    dog_med8 = median_survival_years(dog_annual_qx, 8)
    human_med65 = median_survival_years(human_annual_qx, 65)
    bd, bh = dog_gompertz_slope(), human_gompertz_slope()
    dog_t = trial_size(dog_annual_qx, bd, 8, 4, 10)
    hum_t = trial_size(human_annual_qx, bh, 65, 4, 10)
    compounds = itp_compounds(conn, inter_index)
    n_itp = len(compounds)
    n_itp_dog = sum(1 for c in compounds if c["n_corpus"])
    n_itp_lifespan = sum(1 for c in compounds if c["n_dog_lifespan"])
    svg = years_chart(dog_med8, human_med65, with_title=True)      # standalone file
    svg_inline = years_chart(dog_med8, human_med65, with_title=False)
    data = {"compounds": compounds, "dog_qx": DOG_QX, "human_q5": HUMAN_Q5, "dog_slope": bd, "human_slope": bh, "z": [Z_ALPHA, Z_BETA]}

    body = f"""<h1>Why the path to human longevity runs through dogs</h1>
<p class="lede">Laboratory aging research has produced interventions that extend the lifespan of mice, and the field's stated barrier is moving those results to people{cite("kaeberlein2016")}. In people, the first proposed trial of a drug against aging, TAME, tests metformin as an initial step toward later drugs{cite("barzilai2016")}, and the life-table arithmetic below shows why no human trial has read out a lifespan effect. Companion dogs are the one species in which a lifespan trial of a drug against aging is being run outside the laboratory{cite("triad2025")}, in the human environment, with a regulator that has accepted lifespan extension as something a drug can be approved for{cite("loy001")}. The numbers below are computed from the cited sources so that the comparison can be checked rather than believed.</p>

<h2>The clock problem</h2>
<p>A lifespan intervention has to be judged on deaths. In mice that takes a year or two: the Interventions Testing Program's rapamycin result came from feeding genetically heterogeneous mice from 600 days of age and reading the age at which 90% had died, a 14% gain for females and 9% for males{cite("harrison2009")}. In rhesus monkeys the calorie-restriction answer took a 20-year longitudinal study{cite("colman2009", "mattison2012")}. In people, using the United States 2019 life table, half of a cohort enrolled at 65 is still alive {human_med65:.0f} years later{cite("who2019")}. In companion dogs, using the UK life table built from 30,563 deaths, half of a cohort enrolled at 8 has died after {dog_med8:.1f} years{cite("teng2022")}. A dog trial started this year has its lifespan answer within a single five-year grant period{cite("reporter_triad")}.</p>
<figure>{svg_inline}<figcaption>Years from the first dose to a lifespan answer, by species. <a href="why-dogs-years-to-answer.svg">SVG</a>, CC BY 4.0.</figcaption></figure>

<h2>What dogs share with us that mice do not</h2>
<p>Companion dogs live in our homes, eat our food, breathe our air and have a sophisticated healthcare system of their own, and they develop the same age-related diseases, which is the rationale of the Dog Aging Project{cite("creevy2022")} and of the first rigorous test of a drug against biological aging with lifespan endpoints to be run outside a laboratory in any species{cite("triad2025")}. The domestic dog is among the most variable mammals in size, disease risk and life expectancy{cite("creevy2022")}: breeds span almost two orders of magnitude in body size and a twofold range in life expectancy, and the large breeds die young mainly because they age faster{cite("kraus2013")}. That is a natural experiment on growth and aging that no inbred laboratory strain offers.</p>

<h2>Lifespan has already been moved in dogs</h2>
<p>Restricting food intake by 25% from eight weeks of age gave 48 Labrador Retrievers a median lifespan 1.8 years longer and delayed chronic disease{cite("kealy2002", "lawler2008")}. L-deprenyl started between 10 and 15 years of age lengthened survival in beagles{cite("ruehl1997")}. Rapamycin, the mouse result replicated at the ITP's three sites{cite("harrison2009")}, was well tolerated in two placebo-controlled trials in middle-aged companion dogs{cite("urfer2017", "lowdose2023")}, and TRIAD, a randomized, double-masked, placebo-controlled, multicenter trial with lifespan and healthspan endpoints, is funded from December 2024 to November 2029{cite("triad2025", "reporter_triad")}.</p>

<h2>A regulator has already said yes</h2>
<p>The FDA Center for Veterinary Medicine's expanded conditional approval pathway allows a drug with a reasonable expectation of effectiveness to reach the market while the pivotal study completes{cite("gfi261")}. In 2023 it accepted that a drug intended to extend lifespan in large dogs has a reasonable expectation of effectiveness, the first such acceptance for any species{cite("loy001")}; in January 2026 it accepted the target-animal-safety section for a daily pill intended to extend healthy lifespan in senior dogs{cite("loy002")}, whose pivotal study follows 1,300 dogs at 70 veterinary practices for up to four years{cite("stay")}. There is no equivalent indication for people. If that pipeline holds, the first approved longevity drug in any species will be a dog drug, and its effectiveness data will be the first lifespan-trial data in a mammal that lives with us.</p>

<h2>Dog results read across</h2>
<p>Epigenetic clocks built on the same methylation array estimate age in both dogs and humans, including dual-species clocks, so an intervention's effect on biological age can be measured with one instrument in both species{cite("horvath2022")}. Doses translate by body-surface area with the published conversion factors{cite("km2005")}. The registry of trials, the FDA summaries and the literature on this site exist so that a result in dogs can be carried into a human protocol with its sources attached.</p>

<h2>Run the comparison yourself</h2>
<p>Pick a compound the Interventions Testing Program has tested in mice. The calculator shows the mouse results from DrugAge, what is known in dogs from this site's database, the dog-equivalent dose, and the trial it would take to detect the same lifespan extension in dogs starting at 8 and in people starting at 65, over the same follow-up. Of the {n_itp} ITP compounds, {n_itp_dog} are mentioned anywhere in the canine aging literature and {n_itp_lifespan} have a dog lifespan study.</p>
<div id="calc" class="calc">
<label>Compound <select id="compound"></select></label>
<label>Lifespan extension to detect <input id="ext" type="number" min="1" max="50" step="1" value="10"> %</label>
<label>Follow-up <input id="years" type="number" min="1" max="30" step="1" value="4"> years</label>
<div id="calc-out"></div>
</div>
<p class="notes">Model: a p% lifespan extension starting at age a delays mortality by a·p/(1+p) years; under Gompertz mortality fitted to each life table (dogs, ages 7-13{cite("teng2022")}; people, ages 60-84{cite("who2019")}) that delay is a constant hazard ratio; events needed follow Schoenfeld's formula at two-sided α = 0.05 and 80% power{cite("schoenfeld1983")}; participants are events divided by the control arm's cumulative mortality over the follow-up, with 1:1 allocation. With these defaults a 10% extension needs about {dog_t['participants']:,.0f} dogs over four years and about {hum_t['participants']:,.0f} people over the same four years, and the people are then still {human_med65 - 4:.0f} years short of a median-lifespan readout. Change the inputs; the arithmetic is in the page source.</p>

<h2>Forecast it</h2>
<p>Five play-money prediction markets put the same comparison to forecasters, in pairs: a dog question next to its human twin. Trade them on Manifold and the crowd's numbers appear here over time.</p>
<ul>
<li><a href="https://manifold.markets/w0lph/will-the-fda-conditionally-approve">Will the FDA conditionally approve a drug to extend lifespan or healthspan in dogs before 2028?</a> and its twin, <a href="https://manifold.markets/w0lph/will-the-fda-approve-any-drug-for-a">will the FDA approve any drug for an aging indication in humans before 2035?</a></li>
<li><a href="https://manifold.markets/w0lph/will-the-triad-trial-report-that-ra">Will TRIAD report a significant lifespan extension from rapamycin in dogs by 2031?</a> and its twin, <a href="https://manifold.markets/w0lph/will-a-human-antiaging-drug-trial-w">will a human anti-aging drug trial with mortality or lifespan as its primary endpoint be registered before 2030?</a></li>
<li><a href="https://manifold.markets/w0lph/will-loyal-report-that-loy002-met-t">Will Loyal report that LOY-002 met the STAY study's primary effectiveness endpoint by 2029?</a></li>
<li><a href="https://manifold.markets/w0lph/which-species-will-get-the-first-re">Which species will get the first regulator-approved drug with lifespan extension as the indication?</a> Dogs, humans, another species, or none before 2035.</li>
</ul>

<h2>References</h2>
<ol class="refs">
{''.join(f'<li id="ref-{k}">{esc(text)} <a href="{esc(url)}">{esc(url)}</a></li>' for k, text, url in REFS)}
</ol>
<script id="why-dogs-data" type="application/json">{json.dumps(data, ensure_ascii=False)}</script>
<script>
(function () {{
  const D = JSON.parse(document.getElementById('why-dogs-data').textContent);
  const sel = document.getElementById('compound'), ext = document.getElementById('ext'), yrs = document.getElementById('years'), out = document.getElementById('calc-out');
  D.compounds.forEach((c, i) => {{ const o = document.createElement('option'); o.value = i; o.textContent = c.name + (c.mean_change !== null ? ' (mean ' + c.mean_change + '%)' : ''); sel.appendChild(o); }});
  sel.value = D.compounds.findIndex(c => c.name.toLowerCase() === 'rapamycin');
  const dogQ = a => D.dog_qx[a] !== undefined ? D.dog_qx[a] : Math.min(0.95, D.dog_qx[13] * Math.exp(D.dog_slope * (a - 13)));
  const humQ = a => {{ const g = Math.max(50, Math.min(80, 50 + 5 * Math.floor((a - 50) / 5))); return 1 - Math.pow(1 - D.human_q5[g], 1 / 5); }};
  function cum(q, a, n) {{ let alive = 1; for (let t = 0; t < n; t++) alive *= 1 - q(a + t); return 1 - alive; }}
  function median(q, a) {{ let alive = 1, t = 0; while (alive > 0.5 && t < 60) {{ const nxt = alive * (1 - q(a + t)); if (nxt <= 0.5) return t + (alive - 0.5) / (alive - nxt); alive = nxt; t++; }} return t; }}
  function size(q, slope, a, n, p) {{ p = p / 100; const delay = a * p / (1 + p); const hr = Math.exp(-slope * delay); const ev = 4 * Math.pow(D.z[0] + D.z[1], 2) / Math.pow(Math.log(hr), 2); const cm = cum(q, a, n); return {{ delay, hr, ev, cm, n: ev / cm }}; }}
  const fmt = x => Math.round(x).toLocaleString('en-US');
  function render() {{
    const c = D.compounds[sel.value]; const p = parseFloat(ext.value) || 10; const n = parseInt(yrs.value) || 4;
    const dog = size(dogQ, D.dog_slope, 8, n, p), hum = size(humQ, D.human_slope, 65, n, p);
    const rows = c.rows.map(r => '<tr><td>' + r.species + '</td><td>' + (r.dose || '') + '</td><td>' + (r.age || '') + '</td><td>' + (r.sex || '') + '</td><td>' + (r.change ?? '') + '</td><td>' + (r.sig || '') + '</td><td>' + (r.pmid ? '<a href="https://pubmed.ncbi.nlm.nih.gov/' + r.pmid + '/">PMID ' + r.pmid + '</a>' : '') + '</td></tr>').join('');
    const doses = c.dog_doses.length ? c.dog_doses.map(d => d.reported + ' (' + d.species + ') → ' + (d.dog_mg_per_kg !== null && d.dog_mg_per_kg !== undefined ? d.dog_mg_per_kg + ' mg/kg in dogs' : 'not translatable')).join('; ') : 'reported as ppm of diet; conversion needs an intake assumption';
    out.innerHTML =
      '<h3>' + c.name + ' in mice (DrugAge, ITP rows)</h3><table><thead><tr><th>Species</th><th>Dose</th><th>Age at start</th><th>Sex</th><th>Mean lifespan Δ%</th><th>Sig.</th><th>Source</th></tr></thead><tbody>' + rows + '</tbody></table>' +
      '<p>' + c.n_sig + ' of ' + c.n_rows + ' ITP rows significant' + (c.mean_change !== null ? '; mean change ' + c.mean_change + '%' : '') + '. Dog-equivalent dose by body-surface area: ' + doses + '.</p>' +
      '<p>In dogs today: ' + c.n_corpus + ' papers in the canine aging corpus mention it, ' + c.n_foi + ' FDA summaries cover a dog product with it, ' + c.n_dog_lifespan + ' dog lifespan experiments in DrugAge.</p>' +
      '<h3>The trial that would detect a ' + p + '% lifespan extension over ' + n + ' years</h3>' +
      '<table><thead><tr><th></th><th>Dogs, enrolled at 8</th><th>People, enrolled at 65</th></tr></thead><tbody>' +
      '<tr><th>Control-arm mortality over the follow-up</th><td>' + (dog.cm * 100).toFixed(0) + '%</td><td>' + (hum.cm * 100).toFixed(1) + '%</td></tr>' +
      '<tr><th>Mortality delay implied by the extension</th><td>' + dog.delay.toFixed(2) + ' years</td><td>' + hum.delay.toFixed(1) + ' years</td></tr>' +
      '<tr><th>Hazard ratio under Gompertz mortality</th><td>' + dog.hr.toFixed(2) + '</td><td>' + hum.hr.toFixed(2) + '</td></tr>' +
      '<tr><th>Deaths needed (α 0.05, power 0.8)</th><td>' + fmt(dog.ev) + '</td><td>' + fmt(hum.ev) + '</td></tr>' +
      '<tr><th>Participants needed</th><td><strong>' + fmt(dog.n) + ' dogs</strong></td><td><strong>' + fmt(hum.n) + ' people</strong></td></tr>' +
      '<tr><th>Years until half the control arm has died</th><td>' + median(dogQ, 8).toFixed(1) + '</td><td>' + median(humQ, 65).toFixed(0) + '</td></tr>' +
      '<tr><th>Regulatory path for a lifespan indication</th><td>FDA CVM expanded conditional approval; first acceptances 2023 and 2026</td><td>none</td></tr>' +
      '</tbody></table>';
  }}
  [sel, ext, yrs].forEach(e => e.addEventListener('input', render)); render();
}})();
</script>"""
    title = "Why the path to human longevity runs through dogs"
    desc = (f"Computed from the cited life tables and trials: a lifespan answer takes {dog_med8:.1f} years in dogs and {human_med65:.0f} in people; "
            "dogs share our environment and diseases, lifespan has already been extended in dogs, and a regulator has accepted lifespan extension as an indication for dog drugs.")
    stats = {"dog_median_from_8": round(dog_med8, 2), "human_median_from_65": round(human_med65, 1), "dog_gompertz_slope": round(bd, 3), "human_gompertz_slope": round(bh, 3),
             "dogs_for_10pct_4y": round(dog_t["participants"]), "people_for_10pct_4y": round(hum_t["participants"]), "itp_compounds": n_itp}
    return title, desc, body, svg, stats
