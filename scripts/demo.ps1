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

Write-Host "Publishing '$Scenario' telemetry for $Seconds seconds..."

$job = Start-Job -ScriptBlock {
    param($BackendDir, $PythonPath, $ScenarioName, $SampleMinutesValue)
    Set-Location $BackendDir
    & $PythonPath -m app.simulator --scenario $ScenarioName --interval 1 --sample-minutes $SampleMinutesValue
} -ArgumentList $backendDir, $python, $Scenario, $SampleMinutes

try {
    Start-Sleep -Seconds $Seconds
}
finally {
    Stop-Job $job -ErrorAction SilentlyContinue
    Receive-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -ErrorAction SilentlyContinue
}

Write-Host "Current backend status:"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/status" | ConvertTo-Json -Depth 5
