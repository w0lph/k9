# Rebuild everything in dependency order. Run from D:\OneDrive\k9 in PowerShell.
#   .\rebuild.ps1            # incremental (skips downloads already on disk)
#   .\rebuild.ps1 -Fresh     # re-fetch metadata and re-download sources
param([switch]$Fresh)
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$root = $PSScriptRoot

function Step($name, $script) { Write-Host "`n=== $name ===" -ForegroundColor Cyan; & $script }

Step "corpus: metadata" {
  Set-Location "$root\corpus"
  uv sync --extra dev | Out-Null
  if ($Fresh) { uv run cac fetch-metadata --data-dir data --page-size 500 } else { uv run cac rebuild-records --data-dir data }
}
Step "corpus: full text (NCBI batched, then Europe PMC for leftovers)" {
  uv run cac fetch-fulltext --data-dir data --source ncbi
  uv run cac fetch-fulltext --data-dir data --source europepmc --max-attempts 2 --breaker 12
  if ($LASTEXITCODE -eq 3) { Write-Host "Europe PMC unavailable; leftovers are publisher-restricted or retry later" }
  uv run cac convert --data-dir data
  uv run cac manifest --data-dir data
}
Step "foi: FDA FOI summaries" {
  Set-Location "$root\foi"
  uv sync | Out-Null
  if ($Fresh) { uv run foi index }
  uv run foi download --workers 3
  uv run foi text
  uv run foi dataset
  $drafts = Get-ChildItem data\structured\drafts\batch_*.jsonl -ErrorAction SilentlyContinue
  if ($drafts) { uv run foi merge-structured @($drafts.FullName) ; uv run foi validate-structured data\structured_dog.jsonl }
}
Step "mcp: database" {
  Set-Location "$root\mcp"
  uv sync | Out-Null
  if ($Fresh) { uv run dog-geroscience-mcp build } else { uv run dog-geroscience-mcp build --skip-download }
  uv run pytest -q
}
Step "questions: validate + baseline" {
  Set-Location "$root\questions"
  uv sync | Out-Null
  $set = if (Test-Path data\canine_geroscience_v0_1.jsonl) { "data\canine_geroscience_v0_1.jsonl" } else { "data\canine_geroscience_v0.jsonl" }
  uv run cgq validate $set --require-ids
  uv run cgq evaluate $set
}
Set-Location $root
Write-Host "`nDone." -ForegroundColor Green
