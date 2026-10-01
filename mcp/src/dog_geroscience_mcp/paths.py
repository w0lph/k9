"""Filesystem layout, upstream source URLs and where the published database lives.

Environment overrides:

* ``DOG_GERO_DATA``      — directory holding the built SQLite database and raw downloads.
                           Default: ``<project>/data`` inside a source checkout; otherwise a
                           per-user cache directory (``%LOCALAPPDATA%\\dog-geroscience-mcp`` on
                           Windows, ``$XDG_CACHE_HOME/dog-geroscience-mcp`` or
                           ``~/.cache/dog-geroscience-mcp`` elsewhere), so a ``uvx`` or ``pip``
                           install never writes inside site-packages.
* ``DOG_GERO_CORPUS``    — the canine-aging-corpus ``data/`` directory (records.jsonl,
                           fulltext/md, corpus_version.json). Needed to *build* the database;
                           at serve time it is only a fallback, because the built database
                           carries the redistributable Markdown full text.
* ``DOG_GERO_FOI``, ``DOG_GERO_FOI_STRUCTURED`` — foi-summaries inputs for ``build``.
* ``DOG_GERO_DB_URL``    — where ``fetch-data`` (and the first ``serve``) downloads the
                           prebuilt database from. Default: the Hugging Face dataset below.
* ``DOG_GERO_AUTO_FETCH`` — ``0`` makes ``serve`` fail when the database is missing instead
                           of downloading it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# True when imported from a source checkout (uv run / editable install); False from a wheel.
IS_SOURCE_CHECKOUT = (PROJECT_ROOT / "pyproject.toml").exists()

DB_FILENAME = "dog_geroscience.sqlite"


def user_cache_dir() -> Path:
    """Per-user cache directory for an installed (non-checkout) copy of the server."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "dog-geroscience-mcp"


def default_data_dir(env: dict[str, str] | None = None, source_checkout: bool | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("DOG_GERO_DATA"):
        return Path(env["DOG_GERO_DATA"])
    checkout = IS_SOURCE_CHECKOUT if source_checkout is None else source_checkout
    return PROJECT_ROOT / "data" if checkout else user_cache_dir()


DATA_DIR = default_data_dir()
CORPUS_DIR = Path(os.environ.get("DOG_GERO_CORPUS", PROJECT_ROOT.parent / "corpus" / "data"))

RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / DB_FILENAME

# foi-summaries dataset (dog products); optional at build time.
FOI_PATH = Path(os.environ.get("DOG_GERO_FOI", PROJECT_ROOT.parent / "foi" / "data" / "foi_summaries_dog.jsonl"))
# Structured (typed, quote-grounded) extraction over those summaries; optional at build time.
FOI_STRUCTURED_PATH = Path(os.environ.get("DOG_GERO_FOI_STRUCTURED", PROJECT_ROOT.parent / "foi" / "data" / "structured_dog.jsonl"))
# canine-trials registry (optional; the trials table and canine_trial_search tool).
TRIALS_PATH = Path(os.environ.get("DOG_GERO_TRIALS", PROJECT_ROOT.parent / "trials" / "data" / "canine_trials.jsonl"))

# Prebuilt database published on the Hugging Face Hub (see publish/ at the repository root).
HF_DATA_REPO = "w0lph/dog-geroscience-mcp-data"
DB_URL = os.environ.get(
    "DOG_GERO_DB_URL", f"https://huggingface.co/datasets/{HF_DATA_REPO}/resolve/main/{DB_FILENAME}"
)

USER_AGENT = "dog-geroscience-mcp/0.1 (research tooling)"

# Human Ageing Genomic Resources (CC BY 3.0; commercial use permitted with attribution).
HAGR_SOURCES: dict[str, tuple[str, str]] = {
    # name: (url, member file inside the zip)
    "anage": ("https://genomics.senescence.info/species/dataset.zip", "anage_data.txt"),
    "drugage": ("https://genomics.senescence.info/drugs/dataset.zip", "drugage.csv"),
    "genage_human": ("https://genomics.senescence.info/genes/human_genes.zip", "genage_human.csv"),
    "genage_models": ("https://genomics.senescence.info/genes/models_genes.zip", "genage_models.csv"),
}

# Dog Aging Project public codebooks (GitHub, dogagingproject/dataRelease).
DAP_CODEBOOK_API = "https://api.github.com/repos/dogagingproject/dataRelease/contents/Codebooks"
DAP_CODEBOOK_RAW = "https://raw.githubusercontent.com/dogagingproject/dataRelease/master/Codebooks/"

ENSEMBL_REST = "https://rest.ensembl.org"
REPORTER_API = "https://api.reporter.nih.gov/v2/projects/search"
