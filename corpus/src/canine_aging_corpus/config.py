"""Query definitions and filesystem layout.

Queries are Europe PMC search-syntax strings. Each query has a *tier* name; a record can
match several tiers and the manifest records all of them. The ``core`` tier is the
narrow, high-precision definition used in the opportunity analysis; ``extended`` widens
it to clinical-geriatric and intervention vocabulary and is expected to pull in more
noise, so downstream consumers can filter on tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SPECIES_CLAUSE = 'TITLE_ABS:(dog OR dogs OR canine OR "Canis familiaris")'

CORE_AGING_CLAUSE = "TITLE_ABS:(aging OR ageing OR lifespan OR longevity OR geroscience)"

EXTENDED_AGING_CLAUSE = (
    "TITLE_ABS:(aging OR ageing OR lifespan OR longevity OR geroscience OR geriatric "
    'OR senior OR "age-related" OR healthspan OR frailty OR senescence '
    'OR "cognitive dysfunction" OR rapamycin OR "life expectancy")'
)

QUERIES: dict[str, str] = {
    "core": f"({SPECIES_CLAUSE} AND {CORE_AGING_CLAUSE})",
    "extended": f"({SPECIES_CLAUSE} AND {EXTENDED_AGING_CLAUSE})",
}

EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"

# Identify the pipeline to the service. No personal contact details are sent unless the
# operator sets CAC_CONTACT in the environment.
USER_AGENT = "canine-aging-corpus/0.1 (+https://github.com/; research pipeline)"


@dataclass(frozen=True)
class DataPaths:
    """All pipeline outputs live under one data directory (git-ignored)."""

    root: Path = field(default_factory=lambda: Path("data"))

    @property
    def raw_search(self) -> Path:
        return self.root / "raw" / "europepmc" / "search"

    @property
    def records(self) -> Path:
        return self.root / "records.jsonl"

    @property
    def fulltext_xml(self) -> Path:
        return self.root / "fulltext" / "xml"

    @property
    def fulltext_md(self) -> Path:
        return self.root / "fulltext" / "md"

    @property
    def fulltext_log(self) -> Path:
        return self.root / "fulltext" / "fetch_log.jsonl"

    @property
    def fulltext_sources(self) -> Path:
        """Sidecar: which service each XML file came from (europepmc | ncbi)."""
        return self.root / "fulltext" / "sources.jsonl"

    @property
    def manifest_parquet(self) -> Path:
        return self.root / "manifest.parquet"

    @property
    def manifest_csv(self) -> Path:
        return self.root / "manifest.csv"

    @property
    def version_file(self) -> Path:
        return self.root / "corpus_version.json"

    def ensure(self) -> None:
        for p in (self.raw_search, self.fulltext_xml, self.fulltext_md):
            p.mkdir(parents=True, exist_ok=True)
