$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "export_character.py"
& python $scriptPath @args
exit $LASTEXITCODE
