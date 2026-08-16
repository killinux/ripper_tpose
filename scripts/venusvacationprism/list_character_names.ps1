$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "list_character_names.py"
& python $scriptPath @args
exit $LASTEXITCODE
