<#
.SYNOPSIS
  Compatibility entry point for the Rise of Eros extractor.
.DESCRIPTION
  The maintained implementation moved to scripts\riseoferos.
  Existing commands that call scripts\extract_character.ps1 keep working.
#>

$target = Join-Path $PSScriptRoot "riseoferos\extract_character.ps1"
if (-not (Test-Path -LiteralPath $target)) {
    Write-Error "Rise of Eros extractor not found: $target"
    exit 1
}

& $target @args
exit $LASTEXITCODE
