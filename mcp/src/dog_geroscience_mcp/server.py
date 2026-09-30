"""MCP server exposing dog-specific aging tools.

Data tools read a prebuilt SQLite file (see ``dog-geroscience-mcp build``); two tools make
live calls (Ensembl, NIH RePORTER). Every result carries its source.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from mcp.server.mcpserver import Context, MCPServer

from . import __version__, dose, dossier, live, queries
from .data_fetch import ensure_db
from .foi_store import FoiStore
from .paths import CORPUS_DIR, DB_PATH, FOI_PATH

INSTRUCTIONS = """Dog-specific aging (geroscience) tools. Use them when a question involves
companion dogs as a model of aging, canine lifespan or longevity interventions, translating a
human or mouse intervention to dogs, the Dog Aging Project's survey variables, or NIH funding
for canine aging research.

Ground truth tables: AnAge (species longevity records), DrugAge (lifespan-extension
experiments, with the NIA Interventions Testing Program flag), GenAge (human aging genes and
model-organism longevity genes) — all from HAGR, CC BY 3.0. Dog Aging Project codebooks come
from the project's public GitHub. The corpus is the canine aging literature from Europe PMC
(abstracts for all records; Markdown full text for the open-access subset).

Typical workflow for "what do we know about intervention X in dogs": drugage_search(compound=X)
across species -> corpus_search(X) for dog evidence -> genage_search / dog_ortholog for the
target's conservation -> dose_translate for a starting dose -> nih_reporter_search for who is
funded to study it."""


@dataclass
class AppState:
    """Per-server state. Sync tools run on worker threads, so each thread gets its own
    read-only SQLite connection (SQLite connections must not be shared across threads
    without serialisation)."""

    db_path: Path
    corpus_dir: Path
    foi_store: FoiStore = field(default_factory=lambda: FoiStore(FOI_PATH), repr=False)
    _local: threading.local = field(default_factory=threading.local, repr=False)
    _conns: list[sqlite3.Connection] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = queries.connect(self.db_path)
            self._local.conn = c
            with self._lock:
                self._conns.append(c)
        return c

    def close(self) -> None:
        with self._lock:
            for c in self._conns:
                with contextlib.suppress(sqlite3.Error):
                    c.close()
            self._conns.clear()


def create_server(db_path: Path = DB_PATH, corpus_dir: Path = CORPUS_DIR, foi_path: Path = FOI_PATH,
                  auto_fetch: bool | None = None) -> MCPServer:
    """``auto_fetch`` (default: env ``DOG_GERO_AUTO_FETCH`` != "0") downloads the published
    database on first start when ``db_path`` is missing, so ``uvx dog-geroscience-mcp`` works
    with no build step."""
    if auto_fetch is None:
        auto_fetch = os.environ.get("DOG_GERO_AUTO_FETCH", "1") != "0"

    @contextlib.asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[AppState]:
        if not db_path.exists():
            if not auto_fetch:
                raise FileNotFoundError(
                    f"database not found at {db_path}; run `dog-geroscience-mcp fetch-data` "
                    "(download) or `dog-geroscience-mcp build` (from sources) first"
                )
            ensure_db(db_path)
        state = AppState(db_path=db_path, corpus_dir=corpus_dir, foi_store=FoiStore(foi_path, db_path=db_path))
        try:
            yield state
        finally:
            state.close()

    mcp = MCPServer(
        "dog-geroscience",
        title="Dog Geroscience",
        description="Dog-specific aging tools: HAGR dog rows, dog orthologs, dose translation, DAP codebooks, NIH grants, canine aging corpus search.",
        instructions=INSTRUCTIONS,
        version=__version__,
        log_level="WARNING",
        lifespan=lifespan,
    )

    def _state(ctx: Context) -> AppState:
        return ctx.request_context.lifespan_context

    # -- info -----------------------------------------------------------------------

    @mcp.tool()
    def corpus_info(ctx: Context) -> dict:
        """Describe the data behind this server: build time, source URLs and fetch dates,
        corpus counts (records, core tier, open access, full text) and per-year histogram."""
        st = _state(ctx)
        return {"build": queries.build_info(st.conn), "corpus": queries.corpus_stats(st.conn), "db_path": str(st.db_path)}

    # -- HAGR -----------------------------------------------------------------------

    @mcp.tool()
    def anage_species(ctx: Context, species: str = "Canis familiaris", limit: int = 5) -> list[dict]:
        """AnAge longevity record(s) for a species. Match on scientific name, common name or
        genus (substring); aliases accepted: "dog", "Canis lupus familiaris", "wolf", "human",
        "mouse", "rat", "cat", "naked mole rat". Default is the domestic dog (AnAge name
        "Canis familiaris"). Fields include maximum longevity (yrs), adult weight (g), IMR
        (initial mortality rate/yr), MRDT (mortality rate doubling time, yrs), maturity, gestation,
        litter size, metabolic rate, data quality. Use species="human" or "mouse" for comparison rows."""
        return queries.anage_species(_state(ctx).conn, species, limit)

    @mcp.tool()
    def drugage_search(
        ctx: Context,
        compound: str | None = None,
        species: str | None = None,
        itp_only: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        """Lifespan-extension experiments from DrugAge. Filter by compound (substring, e.g.
        "rapamycin"), species (substring, e.g. "Canis" for dog, "Mus musculus" for mouse), and
        itp_only=True for NIA Interventions Testing Program results. Each row: compound, species,
        strain, dosage, age at initiation, treatment duration, average and maximum lifespan change
        (%) with significance, sex, weight change, ITP flag, PubMed id. Note: DrugAge has very
        few dog experiments; the absence of a dog row is itself informative."""
        return queries.drugage_search(_state(ctx).conn, compound, species, itp_only, limit)

    @mcp.tool()
    def drugage_species_summary(ctx: Context) -> list[dict]:
        """How many DrugAge experiments and distinct compounds exist per species (shows how
        thin the dog evidence base is relative to mouse, fly, worm)."""
        return queries.drugage_species_summary(_state(ctx).conn)

    @mcp.tool()
    def genage_search(ctx: Context, query: str, limit: int = 25) -> dict:
        """Aging-associated genes from GenAge: human entries (symbol, name, Entrez id, UniProt,
        and 'why' the gene is in GenAge, e.g. 'mammal' for mammalian lifespan evidence) plus
        model-organism longevity genes (organism, lifespan effect, longevity influence).
        Query by symbol (e.g. "IGF1R", "MTOR") or name substring. Follow with dog_ortholog to
        map a hit to the dog genome."""
        return queries.genage_search(_state(ctx).conn, query, limit)

    # -- cross-species ----------------------------------------------------------------

    @mcp.tool()
    async def dog_ortholog(ctx: Context, gene_symbol: str, from_species: str = "human") -> dict:
        """Dog (Canis lupus familiaris, Ensembl reference ROS_Cfam_1.0) orthologs of a gene
        symbol from human or mouse, via Ensembl Compara: dog gene id and symbol, orthology type
        (ortholog_one2one etc.), percent identity, description, genomic location. Live call,
        cached in the database. Use to check whether a human/mouse aging target is conserved
        before proposing a canine study."""
        st = _state(ctx)
        return live.dog_ortholog(gene_symbol, from_species, cache_db=st.db_path)

    @mcp.tool()
    def dose_translate(dose_mg_per_kg: float, from_species: str, to_species: str = "dog") -> dict:
        """Convert a mg/kg dose between species with the FDA body-surface-area (Km) method
        (2005 guidance, Table 1): dose_out = dose_in × Km[from] / Km[to]. Species: human, mouse,
        rat, dog, rabbit, monkey, hamster, guinea pig, ferret, marmoset, baboon, mini-pig, micro-pig.
        Example: 4 mg/kg in mouse → dog = 4 × 3/20 = 0.6 mg/kg. A heuristic starting point only;
        confirm with dog pharmacokinetic data (e.g. FDA FOI summaries)."""
        try:
            return dose.translate(dose_mg_per_kg, from_species, to_species)
        except ValueError as exc:
            return {"error": str(exc), "known_species": sorted(dose.KM_TABLE)}

    # -- Dog Aging Project ------------------------------------------------------------

    @mcp.tool()
    def dap_releases(ctx: Context) -> list[dict]:
        """List the Dog Aging Project curated-data releases whose public codebooks are loaded
        (release id, year, version, number of variables and data files)."""
        return queries.dap_releases(_state(ctx).conn)

    @mcp.tool()
    def dap_codebook_search(
        ctx: Context, query: str, release: str = "latest", data_file: str | None = None, limit: int = 25
    ) -> dict:
        """Full-text search of Dog Aging Project codebook variables (variable name, survey
        question text, value labels). Use to find which HLES/AFUS/CSLB/EOLS/Dog Overview variables
        capture a concept (e.g. "rapamycin", "dental", "cause of death", "body condition").
        release: "latest" (default), a year like "2024", or a full id like "2025_v1.0".
        data_file narrows to a table name substring (e.g. "HLES_health", "EOLS")."""
        return queries.dap_codebook_search(_state(ctx).conn, query, release, data_file, limit)

    @mcp.tool()
    def dap_variable(ctx: Context, variable: str, release: str = "latest") -> dict:
        """Full codebook entry for one Dog Aging Project variable (question text, value coding,
        labels) and the list of releases it appears in — useful for checking a variable exists
        before writing analysis code against a Terra release."""
        return queries.dap_variable(_state(ctx).conn, variable, release)

    # -- funding ----------------------------------------------------------------------

    @mcp.tool()
    async def nih_reporter_search(
        query: str = "companion dog aging", fiscal_years: list[int] | None = None, limit: int = 25, offset: int = 0
    ) -> dict:
        """Search NIH RePORTER (live) for funded projects matching a phrase in title, terms or
        abstract, optionally restricted to fiscal years. Returns project number, PI(s),
        organization, institute, award amount, dates, truncated abstract and a link. Good queries:
        "Dog Aging Project", "companion dog aging", "canine geroscience", "rapamycin dogs"."""
        return live.reporter_search(query, fiscal_years, limit, offset)

    # -- composition ------------------------------------------------------------------

    @mcp.tool()
    async def intervention_dossier(
        ctx: Context, compound: str, target_gene: str | None = None, corpus_limit: int = 10, include_openfda: bool = True
    ) -> dict:
        """One structured evidence package for an intervention in dogs, composed from the other
        tools: DrugAge lifespan experiments across species (ITP rows and dog rows separated),
        allometric dog-equivalent doses for every mg/kg animal dose, canine aging corpus hits and
        any randomized/placebo dog trials, the target gene's GenAge entries and dog ortholog
        (if target_gene given), openFDA adverse-event reports in dogs (a marketed-veterinary-drug
        proxy), FDA FOI summaries for dog products with the ingredient, and an explicit list of
        evidence gaps. Deterministic: no model inference; every block names its source. Use it
        first for questions like "what do we know about X in dogs?" or "could X be trialled in dogs?"."""
        st = _state(ctx)
        return dossier.build_dossier(
            st.conn, compound, target_gene=target_gene, corpus_limit=corpus_limit, cache_db=st.db_path,
            include_openfda=include_openfda,
        )

    @mcp.tool()
    def foi_summary_get(ctx: Context, foi_id: int, sections: list[str] | None = None, max_chars: int = 30000) -> dict:
        """Full parsed text of one FDA FOI summary by foi_id (from foi_summary_search or
        intervention_dossier): General Information fields plus the section texts
        (general_information, effectiveness, target_animal_safety, human_food_safety, user_safety,
        agency_conclusions, ...). Pass sections=["target_animal_safety"] to fetch just one; long
        sections are truncated to max_chars in total. Use this to read the actual dose-multiple
        safety study or pharmacokinetic results before citing them."""
        st = _state(ctx)
        if not st.foi_store.available:
            return {"error": f"FOI dataset not found at {st.foi_store.path}; run `foi run` in the foi project"}
        rec = st.foi_store.get(foi_id, sections, max_chars)
        return rec if rec is not None else {"error": f"no FOI summary with foi_id {foi_id}"}

    @mcp.tool()
    def foi_structured_search(ctx: Context, query: str, limit: int = 10) -> list[dict]:
        """Typed extraction records from FDA FOI summaries of dog products (a curated subset):
        dose regimen (dose, route, frequency), pharmacokinetic values (half-life, Tmax, Cmax, AUC,
        bioavailability), the target-animal-safety study (dose multiples, duration, animals,
        findings), the pivotal effectiveness study (design, n, endpoint, result) and adverse
        reactions with treated/control rates. Every value carries a verbatim quote from the summary,
        checked by a validator. Match on ingredient, product name or indication."""
        return queries.foi_structured_search(_state(ctx).conn, query, limit)

    @mcp.tool()
    def foi_summary_search(ctx: Context, query: str, limit: int = 10) -> list[dict]:
        """FDA Freedom of Information summaries for approved dog products whose ingredient,
        proprietary name or indication matches the query: application number, sponsor, approval
        type/date, recommended dosage, indications, route, dosage form, pharmacokinetic and
        target-animal-safety candidate sentences, and the PDF URL. Public-domain FDA CVM
        documents; the only regulator-reviewed source of dog PK and safety-margin data."""
        return queries.foi_search(_state(ctx).conn, query, limit)

    # -- corpus -----------------------------------------------------------------------

    @mcp.tool()
    def corpus_search(
        ctx: Context,
        query: str,
        tier: str | None = "core",
        year_from: int | None = None,
        year_to: int | None = None,
        open_access_only: bool = False,
        limit: int = 20,
    ) -> list[dict]:
        """BM25 keyword search over the canine aging literature corpus (Europe PMC; titles,
        abstracts, keywords, MeSH). tier="core" (default) restricts to papers matching
        dog AND (aging|lifespan|longevity|geroscience); tier="extended" adds geriatric/senior/
        frailty/cognitive-dysfunction/rapamycin/life-expectancy vocabulary; tier=None searches all.
        Results include identifiers, whether Markdown full text is available (has_fulltext_md),
        and a highlighted abstract snippet. Follow with corpus_record for the abstract or full text."""
        return queries.corpus_search(_state(ctx).conn, query, tier, year_from, year_to, open_access_only, limit)

    @mcp.tool()
    def corpus_record(ctx: Context, key: str, include_fulltext: bool = False, max_chars: int = 20000) -> dict:
        """Fetch one corpus record by key ("MED:38263575"), PMID, PMCID or DOI: full metadata,
        abstract, MeSH, keywords, grants-free fields, and optionally the Markdown full text
        (open-access subset only; truncated to max_chars)."""
        st = _state(ctx)
        rec = queries.corpus_record(st.conn, key)
        if rec is None:
            return {"error": f"no record for {key!r}"}
        if include_fulltext and rec.get("pmcid"):
            rec["fulltext"] = queries.corpus_fulltext(st.conn, st.corpus_dir, rec["pmcid"], max_chars)
        return rec

    # -- prompts ----------------------------------------------------------------------

    @mcp.prompt()
    def dossier_briefing(compound: str, target_gene: str | None = None) -> str:
        """Write an evidence briefing on an intervention for dogs from the intervention_dossier tool."""
        gene = f', target_gene="{target_gene}"' if target_gene else ""
        return (
            f'Call intervention_dossier(compound="{compound}"{gene}). Then write a briefing for a scientist '
            "planning a canine study, with these sections and nothing invented beyond the tool output:\n"
            "1. What is known in other species — summarise DrugAge rows by species; state the ITP result if "
            "any (compound, sex, lifespan change) with PubMed ids.\n"
            "2. What is known in dogs — list corpus hits (title, year, PMID) and any randomized/placebo trials; "
            "if there are none, say so explicitly.\n"
            "3. Dosing — report every dog-equivalent dose with its source species dose, and label them as "
            "allometric starting points, not recommendations.\n"
            "4. Target conservation — if a target gene was given, report the dog ortholog, orthology type and "
            "percent identity.\n"
            "5. Veterinary use and safety signals — openFDA dog adverse-event total and top reactions; FDA FOI "
            "summaries for dog products (call foi_summary_get on the target_animal_safety section when a dose-"
            "multiple safety study matters).\n"
            "6. Evidence gaps — reproduce the tool's gaps list and add what a canine trial would need to "
            "establish first.\n"
            "Cite identifiers (PMID, PMCID, foi_id, application number) inline. If the tool returned an error "
            "block for a live source, say which source was unavailable rather than guessing."
        )

    return mcp


def run_stdio(db_path: Path = DB_PATH, corpus_dir: Path = CORPUS_DIR) -> None:
    create_server(db_path, corpus_dir).run(transport="stdio")
