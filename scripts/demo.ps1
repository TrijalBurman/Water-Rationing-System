param(
    [ValidateSet("normal", "shortage", "leak")]
    [string]$Scenario = "normal",

    [int]$Seconds = 30,

    [double]$SampleMinutes = 30
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$backendDir = Join-Path $repoRoot "backend"

if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt"
}

$samples = [Math]::Max(2, $Seconds)
Write-Host "Publishing '$Scenario' telemetry with $samples samples..."

Push-Location $backendDir
try {
    & $python -m app.simulator --scenario $Scenario --interval 0.25 --sample-minutes $SampleMinutes --samples $samples --end-at-now
}
finally {
    Pop-Location
}

Write-Host "Current backend status:"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/status" | ConvertTo-Json -Depth 5
