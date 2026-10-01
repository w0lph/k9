# Publishing guide

Status (2026-09-30): GitHub repository, the four Hugging Face datasets, PyPI
`dog-geroscience-mcp 0.1.0`, the MCP registry entry `io.github.w0lph/dog-geroscience-mcp`,
the Glama listing, the Claude Desktop extension and Claude Code plugin (section 3b) and the
GitHub Pages evidence site (section 4b) are live.

Three targets, in dependency order: the **Hugging Face Hub** hosts the datasets and the
prebuilt database the server downloads on first run; **PyPI** plus the **MCP registry** make
`uvx dog-geroscience-mcp` discoverable; **Glama** indexes the GitHub repository and builds
the root `Dockerfile`, which fetches the database from the Hub. Everything below is prepared
and tested offline; each step that touches an external service needs your account.

Assumptions baked into the files (change them before publishing if they are wrong):

| Assumption | Where it lives |
|---|---|
| GitHub user `w0lph` (from `gh auth status`), repository `w0lph/k9` | `mcp/server.json`, `mcp/pyproject.toml` (`[project.urls]`), `mcp/README.md` marker, `glama.json`, `Dockerfile`, the cards in `publish/cards/` |
| Hugging Face user also `w0lph` | `mcp/src/dog_geroscience_mcp/paths.py` (`HF_DATA_REPO`), `Dockerfile` (`DOG_GERO_DB_URL`), `mcp/server.json` |

`grep -rn "w0lph" --include=*.py --include=*.json --include=*.toml --include=*.md --include=Dockerfile .`
lists every occurrence.

## 0. Git repository and GitHub

The folder is not a git repository. Glama and the registry both point at a public GitHub
repository, so do this first:

Run these **from the project directory** (`git add .` in the wrong directory stages
everything under it, and `--push` would publish it):

```bash
cd /d D:\OneDrive\k9 && git init && git add . && git status --short | head -40
```

Check that the listing shows only project files (no `data/` payloads), then:

```bash
cd /d D:\OneDrive\k9 && git commit -m "canine longevity AI tooling: corpus, MCP server, question set, FOI dataset" && gh repo create w0lph/k9 --public --source . --push
```

`.gitignore` keeps the large derived data out (`corpus/data`, `mcp/data`, FOI PDFs and text,
`publish/stage`); the structured FOI drafts, the question set and the FOI index are small
and versioned. Add a `LICENSE` file (MIT, your name) at the root and in `mcp/`.

## 1. Hugging Face Hub (datasets and the server database)

Four dataset repositories. Cards (with YAML metadata and viewer configs) are in
`publish/cards/`; `publish/hf_stage.py` assembles each repository under `publish/stage/`,
filtering the corpus full text to CC BY / CC0 articles and building the redistributable
SQLite (`--fulltext-licences "cc by,cc0"`).

```bash
hf auth login
```

```bash
uv run --directory mcp python ../publish/hf_stage.py --owner w0lph
```

```powershell
.\publish\hf_upload.ps1 -Owner w0lph
```

| Repository | Contents | Size |
|---|---|---|
| `canine-aging-corpus` | `records.jsonl`, `manifest.parquet`, `corpus_version.json`, `fulltext.parquet` + `fulltext/md/` (788 CC BY / CC0 articles), `fulltext_manifest.json` | ~60 MB |
| `canine-geroscience-questions` | `canine_geroscience_v0_1.jsonl` (default), `canine_geroscience_v0.jsonl`, `schema.json` | < 1 MB |
| `foi-summaries-dog` | `foi_summaries_dog.jsonl`, `structured_dog.jsonl`, `foi_index.jsonl`, `dataset_version.json`, `text/` | ~30 MB |
| `canine-trial-registry` | `canine_trials.jsonl`, `canine_trials.csv`, `schema.json`, `sources/` (web snapshots, Europe PMC abstracts) | < 1 MB |
| `dog-geroscience-mcp-data` | `dog_geroscience.sqlite`, `build_summary.json` (viewer disabled) | ~90 MB |

Then prove the first-run download works from a clean directory (this is what every PyPI
and Docker user will hit):

```powershell
$env:DOG_GERO_DATA = "$env:TEMP\dg-test"; uv run --directory mcp dog-geroscience-mcp fetch-data; Remove-Item Env:DOG_GERO_DATA
```

Add each dataset to a Hub collection ("Canine longevity research tooling") so they link to
each other; the cards already cross-reference by `{owner}`.

## 2. PyPI

```bash
cd mcp && uv build && uv publish
```

`uv publish` reads `UV_PUBLISH_TOKEN` (a PyPI API token) or prompts. The wheel contains only
the package (`uv build` verified: 32 KB) and the README, which carries the registry
ownership marker `mcp-name: io.github.w0lph/dog-geroscience-mcp`. Version `0.1.0` in
`pyproject.toml`, `__init__.py` and `server.json` must stay in step.

Check: `uvx dog-geroscience-mcp fetch-data` from any directory downloads the database into
the per-user cache (`%LOCALAPPDATA%\dog-geroscience-mcp` on Windows).

## 3. MCP registry

`mcp/server.json` is written against schema `2025-12-11` and validates locally. The registry
verifies PyPI ownership through the README marker, and the `io.github.w0lph/` namespace
through GitHub login.

Install the publisher (Windows PowerShell; macOS/Linux: `brew install mcp-publisher`):

```powershell
$arch = if ([System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -eq "Arm64") { "arm64" } else { "amd64" }; Invoke-WebRequest -Uri "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_windows_$arch.tar.gz" -OutFile "mcp-publisher.tar.gz"; tar xf mcp-publisher.tar.gz mcp-publisher.exe; rm mcp-publisher.tar.gz
```

```bash
cd mcp && mcp-publisher validate server.json && mcp-publisher login github && mcp-publisher publish server.json
```

The listing appears at `https://registry.modelcontextprotocol.io/v0/servers?search=dog-geroscience`
and is picked up by aggregators (Smithery, PulseMCP, Glama's registry mirror). To release a
new version: bump the three version fields, `uv publish`, `mcp-publisher publish`.

## 3b. Claude Desktop extension, Claude Code plugin, skill

- `mcp/mcpb/` is the MCPB source (manifest `0.4`, server type `uv`, depends on the PyPI
  package). Build and attach to a GitHub release:

```bash
cd mcp && npx @anthropic-ai/mcpb validate mcpb/manifest.json && npx @anthropic-ai/mcpb pack mcpb dist/dog-geroscience-mcp-0.1.0.mcpb
```

```bash
gh release create mcp-v0.1.0 mcp/dist/dog-geroscience-mcp-0.1.0.mcpb --title "dog-geroscience-mcp 0.1.0" --notes "Claude Desktop extension bundle (.mcpb) for dog-geroscience-mcp 0.1.0."
```

  Optional: submit the bundle to Anthropic's extension directory (Claude Desktop → Settings →
  Extensions → "Submit" link, or the form linked from https://code.claude.com/docs/en/plugins/publish).
- The Claude Code plugin lives at `plugins/dog-geroscience/` with the marketplace file at
  `.claude-plugin/marketplace.json`; users run `/plugin marketplace add w0lph/k9`. Validate with
  `claude plugin validate plugins/dog-geroscience` and `claude plugin validate .` after edits.
  Bump `version` in `plugin.json` and the marketplace entry to push an update to users.

## 4. Glama

Glama lists open-source servers from GitHub and requires the maintainer to sign in with
GitHub and hold write access to the repository. `glama.json` at the root declares the
maintainer; the root `Dockerfile` is what Glama builds and runs in its sandbox for protocol
introspection (tool schemas, behavioural analysis, the Tool Definition Quality Score).

1. Push the repository (step 0) and publish the database (step 1); the Docker build
   downloads it.
2. Open https://glama.ai/mcp/servers/add, sign in with GitHub, submit `w0lph/k9`.
3. On the listing, check the build log; if Glama cannot infer the server directory, point it
   at `mcp/` (the Dockerfile already installs from there).

Local check when Docker Desktop is running:

```bash
docker build -t dog-geroscience-mcp . && docker run -i --rm dog-geroscience-mcp
```

## 4b. Evidence site (GitHub Pages)

`docs/` is generated, never edited by hand: `mcp/scripts/build_site.py` renders one page per
ITP compound and veterinary comparator (from `intervention_dossier`) and one per FDA FOI
ingredient (from `foi_structured` joined with `foi_dog`), plus `llms.txt`, `sitemap.xml`,
`robots.txt` and `.nojekyll`. Every value is templated from a database row and printed next
to its verbatim quote and identifier; the footer and sitemap carry the database build date, so
a rebuild from the same database is byte-identical.

```bash
cd mcp && uv run python scripts/build_site.py && git add ../docs && git commit -m "docs: rebuild evidence site"
```

Pages serves `main:/docs` (enabled once with
`gh api -X POST repos/w0lph/k9/pages -f build_type=legacy -f "source[branch]=main" -f "source[path]=/docs"`);
each push to `main` redeploys within a minute or two. Rebuild after every database rebuild.

## 4c. Monthly refresh (GitHub Actions)

`.github/workflows/refresh.yml` runs `scripts/refresh.sh` on the 3rd of every month (and on
demand from the Actions tab): fresh Europe PMC metadata and full text, the FDA FOI pipeline
(falling back to the published dataset if the FDA site is unreachable), the HAGR and Dog
Aging Project downloads, the database build and tests, the Hub staging, and the evidence
site. It then uploads the staged datasets to the Hub and commits `docs/` plus the FOI index
files. Guards abort the run instead of publishing a truncated corpus (below 95% of the
published record count) or a smaller FOI dataset.

One secret is needed for the upload step, set once from a terminal where `gh` is logged in
(paste the token at the prompt; it is a Hub token with write access to the datasets):

```bash
gh secret set HF_TOKEN --repo w0lph/k9
```

Without the secret the workflow still rebuilds and commits the site; only the upload is
skipped. First run (2026-10-01, run 36796965817): 2.5 minutes end to end, 3,564 records,
1,140 full texts, 28 tests, 219 pages committed. The FDA catalogue API answered HTTP 500 to
the GitHub runner (it works from a residential connection), so that run used the published
FOI dataset; if that persists, the FOI refresh stays a local step: `cd foi && uv run foi run`,
then `.\publish\hf_upload.ps1 -Owner w0lph -Only foi-summaries-dog`. The structured FOI extraction is not automated (it needs a model): new FOI
summaries arrive as unstructured records until the next manual extraction pass
(`foi/README.md`). Installed servers keep the database they downloaded; `uvx
dog-geroscience-mcp fetch-data --force` picks up the latest one.

The same script runs locally (`bash scripts/refresh.sh`) and is what `.\rebuild.ps1 -Fresh`
does on Windows, plus the staging and site steps.

## 5. The write-up

The plan's deliverable includes a short post showing five real questions answered with
citations versus a baseline model. Inputs are ready: `questions/data/canine_geroscience_v0_1.jsonl`,
`mcp/data/dossier_eval.json` for the coverage table, and `mcp/examples/rapamycin_briefing.md`
for the narrated example.

## 6. Where to announce

Animal Longevity Summit and ARDD's Pet and Animal Longevity Forum (both early October), the
Dog Aging Institute, Insilico's longevitybenchmarks.org (offer the question set as a dog
subset), the MCP community showcase, and the Hugging Face datasets forum.
