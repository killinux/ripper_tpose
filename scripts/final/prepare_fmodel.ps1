<#
.SYNOPSIS
  Validate a FINAL FANTASY VII REBIRTH installation and prepare FModel output folders.
.DESCRIPTION
  FFVII Rebirth uses Unreal IoStore archives (.utoc/.ucas). This script does not
  decrypt or extract archives itself. It validates the local installation, creates
  an isolated workspace, and can launch an existing FModel installation.
.EXAMPLE
  .\prepare_fmodel.ps1
  .\prepare_fmodel.ps1 -FModelExe E:\tools\FModel\FModel.exe -LaunchFModel
#>
[CmdletBinding()]
param(
    [string]$GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH",
    [string]$WorkspaceRoot = "D:\ff7rebirth_exports",
    [string]$FModelExe = "E:\tools\FModel\FModel.exe",
    [switch]$LaunchFModel
)

$ErrorActionPreference = "Stop"
$paksRoot = Join-Path $GameRoot "End\Content\Paks"
$fmodelExportRoot = Join-Path $WorkspaceRoot "fmodel_exports"
$blenderRoot = Join-Path $WorkspaceRoot "blender"
$xpsRoot = Join-Path $WorkspaceRoot "xps"

if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    Write-Error "Game directory not found: $GameRoot"
    exit 1
}
if (-not (Test-Path -LiteralPath $paksRoot -PathType Container)) {
    Write-Error "IoStore directory not found: $paksRoot"
    exit 1
}

$utocFiles = @(Get-ChildItem -LiteralPath $paksRoot -File -Filter "*.utoc")
$ucasFiles = @(Get-ChildItem -LiteralPath $paksRoot -File -Filter "*.ucas")
$pakFiles = @(Get-ChildItem -LiteralPath $paksRoot -File -Filter "*.pak")

if ($utocFiles.Count -eq 0 -or $ucasFiles.Count -eq 0) {
    Write-Error "No .utoc/.ucas archive pairs were found under: $paksRoot"
    exit 1
}

$missingPairs = @()
foreach ($utoc in $utocFiles) {
    $partner = [System.IO.Path]::ChangeExtension($utoc.FullName, ".ucas")
    if (-not (Test-Path -LiteralPath $partner -PathType Leaf)) {
        $missingPairs += $utoc.Name
    }
}
if ($missingPairs.Count -gt 0) {
    Write-Warning ("Missing .ucas partner for: " + ($missingPairs -join ", "))
}

foreach ($directory in @($WorkspaceRoot, $fmodelExportRoot, $blenderRoot, $xpsRoot)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$archiveBytes = ($ucasFiles | Measure-Object -Property Length -Sum).Sum
$archiveGiB = [math]::Round($archiveBytes / 1GB, 2)
$bundledMappings = @(Get-ChildItem -LiteralPath $GameRoot -Recurse -File -Filter "*.usmap" -ErrorAction SilentlyContinue)

Write-Host ""
Write-Host "FINAL FANTASY VII REBIRTH archive check" -ForegroundColor Cyan
Write-Host "  Game root:       $GameRoot"
Write-Host "  IoStore root:    $paksRoot"
Write-Host "  UTOC / UCAS:     $($utocFiles.Count) / $($ucasFiles.Count)"
Write-Host "  Legacy PAK:      $($pakFiles.Count)"
Write-Host "  UCAS total:      $archiveGiB GiB"
Write-Host "  Bundled mappings:$($bundledMappings.Count)"
Write-Host ""
Write-Host "Prepared isolated workspace:" -ForegroundColor Green
Write-Host "  FModel exports:  $fmodelExportRoot"
Write-Host "  Blender files:   $blenderRoot"
Write-Host "  XPS exports:     $xpsRoot"
Write-Host ""
Write-Host "FModel setup:" -ForegroundColor Yellow
Write-Host "  1. Directory Selector -> add the GAME ROOT shown above (not the Paks folder)."
Write-Host "  2. Select the dedicated Final Fantasy VII Rebirth profile (GAME_FinalFantasy7Rebirth = 68812805)."
Write-Host "     Do not substitute generic UE4.26 or Latest; revalidate this profile after game/FModel updates."
Write-Host "  3. Load the verified local mapping:"
Write-Host "     $WorkspaceRoot\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap"
Write-Host "  4. Settings -> Models -> output directory: $fmodelExportRoot"
Write-Host "  5. For PC0002_00 use ActorX (PSK/PSKX) + First Level Only; current glTF export rejects invalid tangents."
Write-Host "  6. Export textures as PNG and keep the generated folder hierarchy."
Write-Host ""
Write-Host "This helper never downloads or supplies AES keys/mappings; FModel does not need the game running." -ForegroundColor DarkYellow

if ($LaunchFModel) {
    if (-not (Test-Path -LiteralPath $FModelExe -PathType Leaf)) {
        Write-Error "FModel.exe not found: $FModelExe"
        exit 1
    }
    Start-Process -FilePath $FModelExe -WorkingDirectory (Split-Path -Parent $FModelExe)
    Write-Host "FModel started: $FModelExe" -ForegroundColor Green
}
