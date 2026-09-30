# Upload the staged dataset repositories to the Hugging Face Hub.
#
#   hf auth login                                   # once; needs a token with write access
#   uv run --directory mcp python ../publish/hf_stage.py --owner <hf-username>
#   .\publish\hf_upload.ps1 -Owner <hf-username> [-Only canine-aging-corpus,...] [-Private]
#
# `hf upload` creates a repository when it does not exist (private if -Private is given) and
# commits the whole staged folder; re-running uploads only what changed.
param(
    [Parameter(Mandatory = $true)][string]$Owner,
    [string[]]$Only = @("canine-aging-corpus", "canine-geroscience-questions", "foi-summaries-dog", "dog-geroscience-mcp-data"),
    [switch]$Private
)
# Windows PowerShell 5.1 turns a native command's stderr into a terminating error when it is
# redirected; `hf` prints advisory warnings there, so rely on the exit code instead.
$ErrorActionPreference = "Continue"
$stage = Join-Path $PSScriptRoot "stage"

foreach ($name in $Only) {
    $dir = Join-Path $stage $name
    if (-not (Test-Path $dir)) { throw "missing $dir; run publish/hf_stage.py first" }
    $hfArgs = @("upload", "$Owner/$name", $dir, ".", "--repo-type", "dataset", "--commit-message", "Publish $name")
    if ($Private) { $hfArgs += "--private" }
    Write-Host "hf $($hfArgs -join ' ')"
    & hf @hfArgs
    if ($LASTEXITCODE -ne 0) { throw "upload of $name failed" }
    Write-Host "  https://huggingface.co/datasets/$Owner/$name"
}
