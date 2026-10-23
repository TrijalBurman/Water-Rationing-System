# Forward every argument to the portable Python build entry point.
$ErrorActionPreference = "Stop"
$pythonPrefix = @()
$python = $null
foreach ($candidate in @(
    (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
    (Join-Path $PSScriptRoot "..\..\.venv\Scripts\python.exe")
)) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $python = $candidate
        break
    }
}
if (-not $python) {
    $launcher = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $python = $launcher.Source
    } else {
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) {
            $python = $launcher.Source
            $pythonPrefix = @("-3")
        }
    }
}
if (-not $python) {
    Write-Error "Python was not found. Install Python 3.12 and follow firmware/README.md."
    exit 1
}
& $python @pythonPrefix (Join-Path $PSScriptRoot "build.py") @args
exit $LASTEXITCODE
