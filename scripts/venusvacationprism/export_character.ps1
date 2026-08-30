<#
.SYNOPSIS
  Export complete Venus Vacation PRISM characters by name (ROE-style CLI).
.EXAMPLE
  .\export_character.ps1 Nanami
  .\export_character.ps1 七海,菲欧娜                  # multiple, comma-separated
  .\export_character.ps1 Fiona -Format blend,glb
  .\export_character.ps1 Tamaki -Plan                 # dry run: profile/tools/paths
  .\export_character.ps1 Honoka -Resume
  .\export_character.ps1 -List                        # character names + status
  .\export_character.ps1 -ListModels                  # raw G1M inventory (fast scan)
  .\export_character.ps1 -ListModels -Probe           # + per-G1M joints/version

  Legacy GNU-style calls keep working and are passed through unchanged:
  .\export_character.ps1 --name 穗香 --formats blend,fbx,glb
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string[]]$Names,

    # Defaults resolved by export_character.py: Steam install auto-discovery
    # and D:\venusvacationprism_exports\<character>\complete_auto.
    [string]$GameRoot = '',
    [string]$OutputRoot = '',
    [string[]]$Format,
    [switch]$List,
    [switch]$ListModels,
    [switch]$Probe,
    [switch]$Plan,
    [switch]$Resume,
    [switch]$AssetsOnly,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$exportPy = Join-Path $PSScriptRoot 'export_character.py'
$namesPy = Join-Path $PSScriptRoot 'list_character_names.py'
$modelsPy = Join-Path $PSScriptRoot 'list_models.py'
$defaultGame = 'D:\Program Files (x86)\Steam\steamapps\common\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -'
$defaultExportRoot = 'D:\venusvacationprism_exports'

# ── Legacy passthrough: .\export_character.ps1 --name ... ──
$rawArgs = @()
if ($Names) { $rawArgs += $Names }
if ($Rest) { $rawArgs += $Rest }
if ($rawArgs -and ($rawArgs[0] -like '--*')) {
    & python $exportPy @rawArgs
    exit $LASTEXITCODE
}

# ── -List: character names + export status ──
if ($List) {
    & python $namesPy
    exit $LASTEXITCODE
}

# ── -ListModels: raw G1M inventory ──
if ($ListModels) {
    $game = if ($GameRoot) { $GameRoot } else { $defaultGame }
    $inventory = if ($OutputRoot) { Join-Path $OutputRoot 'inventory' }
        else { Join-Path $defaultExportRoot 'inventory' }
    $modelArgs = @('--game', $game, '--output', $inventory)
    if ($Probe) { $modelArgs += '--probe' }
    & python $modelsPy @modelArgs
    if ($LASTEXITCODE -eq 0) {
        Write-Host ''
        Write-Host ("Inventory: " + $inventory + '  (models.csv / models.json / models.md)') `
            -ForegroundColor Green
        Write-Host '  Export one raw model: python export_model.py --index <N> / --id 0x<KTID> / --name <internal>' `
            -ForegroundColor DarkGray
    }
    exit $LASTEXITCODE
}

if (-not $Names -or $Names.Count -eq 0) {
    Write-Error 'Specify character name(s), e.g.: .\export_character.ps1 Nanami   (use -List to see all)'
    exit 1
}

# ── Comma-separated names, ROE-style ──
$allNames = @()
foreach ($raw in $Names) {
    $allNames += $raw -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}

$failed = @()
foreach ($name in $allNames) {
    Write-Host ''
    Write-Host '========================================' -ForegroundColor Yellow
    Write-Host ("  Exporting character: " + $name) -ForegroundColor Yellow
    Write-Host '========================================' -ForegroundColor Yellow

    $exportArgs = @('--name', $name)
    if ($GameRoot) { $exportArgs += @('--game', $GameRoot) }
    if ($OutputRoot) {
        $exportArgs += @('--output', (Join-Path $OutputRoot ($name + '\complete_auto')))
    }
    if ($Format) {
        $formats = @()
        foreach ($f in $Format) {
            $formats += $f -split '[,;]' | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }
        }
        $exportArgs += @('--formats', ($formats -join ','))
    }
    if ($Plan) { $exportArgs += '--plan' }
    if ($Resume) { $exportArgs += '--resume' }
    if ($AssetsOnly) { $exportArgs += '--assets-only' }

    & python $exportPy @exportArgs
    if ($LASTEXITCODE -ne 0) {
        $failed += $name
        Write-Host ("  FAILED: " + $name) -ForegroundColor Red
    }
}

Write-Host ''
if ($failed) {
    Write-Host ("Done with failures: " + ($failed -join ', ')) -ForegroundColor Red
    exit 1
}
Write-Host 'Done.' -ForegroundColor Green
