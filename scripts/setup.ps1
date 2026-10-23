$ErrorActionPreference = 'Stop'
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python "$PSScriptRoot/manage.py" setup @args
} else {
    & py -3 "$PSScriptRoot/manage.py" setup @args
}
exit $LASTEXITCODE
