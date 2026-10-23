# Forward every argument to the portable Python native-test entry point.
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
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $python = $launcher.Source
        $pythonPrefix = @("-3")
    } else {
        $launcher = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($launcher) { $python = $launcher.Source }
    }
}
if (-not $python) {
    Write-Error "Python was not found. Install Python 3.12 and follow firmware/README.md."
    exit 1
}
& $python @pythonPrefix (Join-Path $PSScriptRoot "test_native.py") @args
exit $LASTEXITCODE
