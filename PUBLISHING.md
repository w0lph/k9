# Publishing guide

Status (2026-09-30): GitHub repository, the four Hugging Face datasets, PyPI
`dog-geroscience-mcp 0.1.0` and the MCP registry entry `io.github.w0lph/dog-geroscience-mcp`
are live. Glama submission is the remaining step (section 4).

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

## 5. The write-up

The plan's deliverable includes a short post showing five real questions answered with
citations versus a baseline model. Inputs are ready: `questions/data/canine_geroscience_v0_1.jsonl`,
`mcp/data/dossier_eval.json` for the coverage table, and `mcp/examples/rapamycin_briefing.md`
for the narrated example.

## 6. Where to announce

Animal Longevity Summit and ARDD's Pet and Animal Longevity Forum (both early October), the
Dog Aging Institute, Insilico's longevitybenchmarks.org (offer the question set as a dog
subset), the MCP community showcase, and the Hugging Face datasets forum.
