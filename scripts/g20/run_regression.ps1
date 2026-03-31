param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\\..")
Set-Location $repoRoot

$args = @(
    "run",
    "python",
    "-m",
    "datacloud_analysis.release.g20_regression"
)

if ($DryRun) {
    $args += "--dry-run"
}

Write-Host "[G20] Running regression suite from $repoRoot"
uv @args

