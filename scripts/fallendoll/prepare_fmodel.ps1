<#
.SYNOPSIS
  Validate an Operation LOVECRAFT: Fallen Doll install and prepare an
  isolated FModel workspace.

.DESCRIPTION
  Fallen Doll (UE4.26, project "Paralogue") ships a single ~5.4 GiB
  AES-encrypted pak (index encrypted, pak version 9) under both Desktop\ and
  VR\.  This script does NOT decrypt anything and never handles an AES key.
  It confirms the install, reports the pak state via probe_pak.py, creates an
  isolated output workspace, and prints the exact FModel settings needed
  (engine version + AES key) before assets can be listed or exported.

  The AES key is not stored in this repo.  Configure it directly in FModel
  (Settings -> Game -> AES) on the machine that owns the game.

.EXAMPLE
  .\prepare_fmodel.ps1

.EXAMPLE
  .\prepare_fmodel.ps1 -LaunchFModel
#>
[CmdletBinding()]
param(
    [string]$GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\Operation Lovecraft Fallen Doll Demo",
    [string]$WorkspaceRoot = "D:\fallendoll_exports",
    [string]$FModelExe = "E:\tools\FModel\FModel.exe",
    [string]$PythonExe = "python",
    [ValidateSet("Desktop", "VR")]
    [string]$Variant = "Desktop",
    [switch]$LaunchFModel
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$probePy = Join-Path $scriptDir "probe_pak.py"

$paksRoot = Join-Path $GameRoot "$Variant\WindowsNoEditor\Paralogue\Content\Paks"
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    Write-Error "Game directory not found: $GameRoot"
    exit 1
}
if (-not (Test-Path -LiteralPath $paksRoot -PathType Container)) {
    Write-Error "Paks directory not found: $paksRoot"
    exit 1
}

$gamePak = Join-Path $paksRoot "Paralogue-WindowsNoEditor.pak"
if (-not (Test-Path -LiteralPath $gamePak)) {
    Write-Error "Fallen Doll pak not found: $gamePak"
    exit 1
}

$fmodelOutput = Join-Path $WorkspaceRoot "fmodel_exports"
$materializedRoot = Join-Path $WorkspaceRoot "materialized"
foreach ($directory in @($WorkspaceRoot, $fmodelOutput, $materializedRoot)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

Write-Host "== Fallen Doll pak probe ($Variant) ==" -ForegroundColor Cyan
if (Test-Path -LiteralPath $probePy) {
    & $PythonExe $probePy --pak $gamePak
} else {
    Write-Warning "probe_pak.py not found next to this script: $probePy"
}

Write-Host ""
Write-Host "== FModel configuration required ==" -ForegroundColor Cyan
Write-Host "  1. Directory selection -> Add Undetected Game:" -ForegroundColor White
Write-Host "       Name:      Fallen Doll (Paralogue)"
Write-Host "       Directory: $paksRoot"
Write-Host "  2. UE Versions -> select GAME_UE4_26 (this build is UE4.26, pak v9)."
Write-Host "  3. AES -> add the game's main AES-256 key (0x...)." -ForegroundColor White
Write-Host "       The pak index is encrypted; without the key FModel lists nothing."
Write-Host "       The key is NOT stored in this repo; configure it here on this machine."
Write-Host "  4. Load the archive, then Save the SkeletalMesh models + Materials + Textures"
Write-Host "     (keep the Unreal folder structure) into:" -ForegroundColor White
Write-Host "       $fmodelOutput"
Write-Host ""
Write-Host "Workspace ready:" -ForegroundColor Green
Write-Host "  FModel export target: $fmodelOutput"
Write-Host "  Materialized output:  $materializedRoot"
Write-Host ""
Write-Host "Next: after saving models from FModel, run export_models.ps1 to" -ForegroundColor DarkGray
Write-Host "materialize them (Blend/FBX/GLB), the same downstream as FF7 Rebirth." -ForegroundColor DarkGray

if ($LaunchFModel) {
    if (Test-Path -LiteralPath $FModelExe) {
        Write-Host ""
        Write-Host "Launching FModel..." -ForegroundColor Cyan
        Start-Process -FilePath $FModelExe
    } else {
        Write-Warning "FModel not found: $FModelExe"
    }
}
