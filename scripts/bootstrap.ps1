$ErrorActionPreference = 'Stop'
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python "$PSScriptRoot/manage.py" bootstrap @args
} else {
    & py -3 "$PSScriptRoot/manage.py" bootstrap @args
}
exit $LASTEXITCODE
