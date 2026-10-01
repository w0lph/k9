#!/usr/bin/env bash
# Rebuild every derived artefact from the public sources, from a clean checkout.
#
# This is what .github/workflows/refresh.yml runs monthly; it also works locally in Git Bash
# or any POSIX shell (each directory is its own uv project):
#
#   bash scripts/refresh.sh
#
# Steps, in dependency order:
#   1. corpus/   fetch Europe PMC metadata, JATS full text (NCBI batched, then Europe PMC for
#                leftovers), convert to Markdown, write the manifest and corpus_version.json
#   2. foi/      FDA CVM FOI catalogue, dog PDFs, text, dataset; merge the versioned structured
#                drafts. If the FDA site is unreachable, fall back to the published dataset so
#                the rest of the refresh still happens.
#   3. mcp/      download HAGR and Dog Aging Project sources, build the database, run the tests
#   4. publish/  stage the Hub repositories (corpus, foi, mcp-data); the upload itself is a
#                separate step that needs a token (see the workflow)
#   5. docs/     regenerate the static evidence site
#
# Guards: the refresh aborts rather than publish a truncated corpus (fewer than
# CORPUS_MIN_FRACTION of the published record count) or a smaller FOI dataset than before.
#
# Environment: HF_OWNER (default w0lph), REFRESH_FOI=0 to skip the FDA pipeline and use the
# published dataset, UV_CACHE_DIR as usual.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HF_OWNER="${HF_OWNER:-w0lph}"
HF="https://huggingface.co/datasets/${HF_OWNER}"
CORPUS_MIN_FRACTION="${CORPUS_MIN_FRACTION:-0.95}"
REFRESH_FOI="${REFRESH_FOI:-1}"
export PYTHONIOENCODING=utf-8
SUMMARY="$ROOT/refresh_summary.json"
STAGE_ONLY="corpus,mcp-data"

step() { printf '\n=== %s ===\n' "$*"; }
jsonget() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d[sys.argv[2]] if sys.argv[2] in d else "")' "$1" "$2"; }
count_lines() { grep -c . "$1" 2>/dev/null || echo 0; }
fetch() { curl -fsSL --retry 3 --retry-delay 5 -o "$2" "$1"; }

# ----------------------------------------------------------------------------- 1. corpus
step "corpus: metadata and full text"
cd "$ROOT/corpus"
uv sync --extra dev --quiet
uv run cac fetch-metadata --data-dir data --page-size 500
uv run cac fetch-fulltext --data-dir data --source ncbi
set +e
uv run cac fetch-fulltext --data-dir data --source europepmc --max-attempts 2 --breaker 12
rc=$?
set -e
if [ "$rc" -eq 3 ]; then echo "Europe PMC leftovers unavailable (publisher-restricted or service down); continuing"; elif [ "$rc" -ne 0 ]; then exit "$rc"; fi
uv run cac convert --data-dir data
uv run cac manifest --data-dir data
uv run cac stats --data-dir data

new_records=$(count_lines data/records.jsonl)
fetch "$HF/canine-aging-corpus/resolve/main/corpus_version.json" data/published_corpus_version.json || true
published_records=$(python3 - <<'EOF'
import json, pathlib
p = pathlib.Path("data/published_corpus_version.json")
try:
    d = json.loads(p.read_text(encoding="utf-8"))
    c = d.get("counts") or {}
    print(c.get("records") or d.get("records") or 0)
except Exception:
    print(0)
EOF
)
echo "corpus records: new=$new_records published=$published_records"
python3 - "$new_records" "$published_records" "$CORPUS_MIN_FRACTION" <<'EOF'
import sys
new, pub, frac = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])
if pub and new < frac * pub:
    sys.exit(f"ABORT: corpus has {new} records, below {frac:.0%} of the published {pub}; Europe PMC probably returned partial results")
EOF

# ----------------------------------------------------------------------------- 2. foi
step "foi: FDA CVM FOI summaries"
cd "$ROOT/foi"
uv sync --quiet
prev_foi=$(jsonget data/dataset_version.json records)
foi_ok=0
if [ "$REFRESH_FOI" = "1" ]; then
  set +e
  ( set -e
    uv run foi index
    uv run foi download --workers 3
    uv run foi text
    uv run foi dataset
  )
  rc=$?
  set -e
  if [ "$rc" -eq 0 ]; then
    new_foi=$(jsonget data/dataset_version.json records)
    if [ "${new_foi:-0}" -ge "${prev_foi:-0}" ]; then foi_ok=1; else echo "FOI dataset shrank ($new_foi < $prev_foi); using the published dataset instead"; fi
  else
    echo "FOI pipeline failed (exit $rc); using the published dataset instead"
  fi
fi
if [ "$foi_ok" = "1" ]; then
  uv run foi merge-structured data/structured/drafts/batch_*.jsonl
  uv run foi validate-structured data/structured_dog.jsonl
  STAGE_ONLY="$STAGE_ONLY,foi"
else
  git -C "$ROOT" checkout -- foi/data
  fetch "$HF/foi-summaries-dog/resolve/main/foi_summaries_dog.jsonl" data/foi_summaries_dog.jsonl
fi
echo "foi records: $(count_lines data/foi_summaries_dog.jsonl) (structured: $(count_lines data/structured_dog.jsonl))"

# ----------------------------------------------------------------------------- 3. mcp
step "mcp: sources, database, tests"
cd "$ROOT/mcp"
uv sync --quiet
mkdir -p data
uv run dog-geroscience-mcp build | tee data/build_stdout.json
uv run pytest -q

# ----------------------------------------------------------------------------- 4. stage
step "publish: stage Hub repositories ($STAGE_ONLY)"
cd "$ROOT"
uv run --directory mcp python ../publish/hf_stage.py --owner "$HF_OWNER" --only "$STAGE_ONLY"

# ----------------------------------------------------------------------------- 5. site
step "docs: evidence site"
uv run --directory mcp python scripts/build_site.py | tee docs_build.json

# ----------------------------------------------------------------------------- summary
python3 - "$SUMMARY" "$new_records" "$published_records" "$foi_ok" "$STAGE_ONLY" <<'EOF'
import json, sys, pathlib
out, new_records, published_records, foi_ok, stage_only = sys.argv[1:]
root = pathlib.Path(out).parent
def load(p):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}
cv = load(root / "corpus/data/corpus_version.json")
db = load(root / "mcp/data/build_stdout.json")
site = load(root / "docs_build.json")
foi = load(root / "foi/data/dataset_version.json")
s = {
    "corpus": {"version": cv.get("corpus_version"), "records": int(new_records), "published_records": int(published_records),
               "counts": {k: v for k, v in (cv.get("counts") or {}).items() if k in ("by_tier", "with_pmcid", "open_access", "fulltext_md")}},
    "foi": {"refreshed": foi_ok == "1", "records": foi.get("records"), "built_at": foi.get("built_at")},
    "db": {k: db.get(k) for k in ("corpus", "foi", "foi_structured", "built_at") if k in db},
    "site": site,
    "staged": stage_only.split(","),
}
pathlib.Path(out).write_text(json.dumps(s, indent=2), encoding="utf-8")
print(json.dumps(s, indent=2))
EOF
rm -f "$ROOT/docs_build.json"
echo "refresh complete; summary in $SUMMARY"
