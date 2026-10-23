$ErrorActionPreference = 'Stop'
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python "$PSScriptRoot/manage.py" demo @args
} else {
    & py -3 "$PSScriptRoot/manage.py" demo @args
}
exit $LASTEXITCODE
