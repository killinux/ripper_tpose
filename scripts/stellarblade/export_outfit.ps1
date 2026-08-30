<#
.SYNOPSIS
  Export one Eve outfit by package name and assemble it into a Blender scene.

.DESCRIPTION
  One command from outfit package name to a complete .blend:

    1. UE Viewer exports the outfit SkeletalMesh (PSK) and its textures if
       they are not already under <ExportRoot>\umodel_outfit_exports.
    2. Blender 3.6 runs validate_eve.py with the outfit as --body: the shared
       Face_003 (53 morphs), default hair, ponytail and nape strands attach to
       the outfit's own skeleton; per-material albedos are matched from the
       outfit's texture folder; renders and a JSON report are written.

  Outfit package names come from docs/stellar-blade-eve-outfits.md
  (CH_P_EVE_45_TypeB, CH_P_EVE_Nikke_06, ...).  The shared components must
  already exist (run export_eve.ps1 once first).

.EXAMPLE
  .\export_outfit.ps1 CH_P_EVE_45_TypeB

.EXAMPLE
  .\export_outfit.ps1 CH_P_EVE_Nikke_06 -Force
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Package,
    [string]$GameRoot = 'D:\Program Files (x86)\Steam\steamapps\common\StellarBlade',
    [string]$ExportRoot = 'D:\stellarblade_exports',
    [string]$BlenderExe = 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe',
    [string]$UmodelExe = 'E:\tools\umodel_stellarblade\umodel_stellar_blade_v6.exe',
    [string]$UEFormatSource = '',
    # Optional explicit diffuse (file or directory). Default: the outfit's
    # texture folder next to the exported PSK.
    [string]$Diffuse = '',
    # Default output is one merged, poseable rig; pass this to keep the
    # original per-component armatures instead.
    [switch]$KeepSeparateArmatures,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$validatePy = Join-Path $scriptDir 'validate_eve.py'
$outfitRoot = Join-Path $ExportRoot 'umodel_outfit_exports'

# Shared components produced by export_eve.ps1 / the verified standard build.
$shared = @{
    Head        = Join-Path $ExportRoot 'fmodel_exports\SB\Content\Art\Character\PC\CH_P_EVE_Head\CH_P_EVE_Face_003.uemodel'
    Hair        = Join-Path $ExportRoot 'umodel_exports\Art\Character\PC\00_HR\EVE_HR_01\EVE_HR_01.psk'
    Tail        = Join-Path $ExportRoot 'umodel_exports\Art\Character\PC\00_HR\EVE_HR_01\EVE_HR_01_Tail.psk'
    TailShort   = Join-Path $ExportRoot 'umodel_exports\Art\Character\PC\00_HR\EVE_HR_01\EVE_HR_Tail_Short.psk'
    FaceAssets  = Join-Path $ExportRoot 'umodel_face_exports'
    HairAlpha   = Join-Path $ExportRoot 'umodel_exports\Art\Character\PC\CH_P_EVE_Hair\Textures\PonyTail_Alpha.png'
    AlignmentRef = Join-Path $ExportRoot 'validation\Eve_Standard_validation.json'
}
$missingShared = @($shared.GetEnumerator() | Where-Object { -not (Test-Path -LiteralPath $_.Value) })
if ($missingShared) {
    Write-Error ("Shared Eve components missing (run .\export_eve.ps1 first):" +
        [Environment]::NewLine + '  ' +
        (($missingShared | ForEach-Object { $_.Key + ': ' + $_.Value }) -join ([Environment]::NewLine + '  ')))
    exit 1
}

# UEFormat source: reuse the snapshot export_eve.ps1 maintains.
if (-not $UEFormatSource) {
    $UEFormatSource = Join-Path $ExportRoot '_tools\UEFormat-58d1abf52d6b2e5ad8d00e7c31bc98495231e642\plugins\blender\io_scene_ueformat'
}
if (-not (Test-Path -LiteralPath $UEFormatSource)) {
    Write-Error ("Patched UEFormat source not found: " + $UEFormatSource +
        " (run .\export_eve.ps1 once, or pass -UEFormatSource)")
    exit 1
}

# ── Step 1: outfit PSK via UE Viewer ──
Write-Host ""
Write-Host "[1/2] Outfit PSK: $Package" -ForegroundColor Cyan
function Find-OutfitPsk {
    @(Get-ChildItem -LiteralPath $outfitRoot -Recurse -Filter ($Package + '.psk') `
        -File -ErrorAction SilentlyContinue) | Select-Object -First 1
}
$psk = $null
if (Test-Path -LiteralPath $outfitRoot) { $psk = Find-OutfitPsk }
if (-not $psk) {
    if (-not (Test-Path -LiteralPath $UmodelExe)) {
        Write-Error ("Stellar Blade UE Viewer build not found: " + $UmodelExe)
        exit 1
    }
    Write-Host "  Not exported yet; running UE Viewer..." -ForegroundColor Yellow
    $umodelCmd = ('"{0}" -export "-path={1}" -game=ue4.26 -noanim -psk -png "-out={2}" "{3}" 2>&1' `
        -f $UmodelExe, $GameRoot, $outfitRoot, $Package)
    $umodelOutput = @(cmd /c $umodelCmd)
    $umodelOutput | Where-Object { $_ -match 'Exported \d+/\d+|ERROR|WARNING' } |
        Select-Object -Last 4 | ForEach-Object { Write-Host ("    " + $_) -ForegroundColor DarkGray }
    $psk = Find-OutfitPsk
    if (-not $psk) {
        Write-Error ("UE Viewer produced no " + $Package + ".psk. Check the package name " +
            "(see docs/stellar-blade-eve-outfits.md or list_models.py --glob '" + $Package + "*').")
        exit 1
    }
} else {
    Write-Host ("  Reusing " + $psk.FullName) -ForegroundColor Green
}

# Diffuse default: the texture folder exported next to the mesh (Tex/Textures).
if (-not $Diffuse) {
    $textureDir = @('Tex', 'Textures') | ForEach-Object { Join-Path $psk.DirectoryName $_ } |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $textureDir) { $textureDir = $psk.DirectoryName }
    $Diffuse = $textureDir
}
Write-Host ("  Diffuse source: " + $Diffuse)

# ── Step 2: Blender assembly ──
$outputBlend = Join-Path (Join-Path $ExportRoot 'blender') ('Eve_' + $Package + '.blend')
$outputRender = Join-Path (Join-Path $ExportRoot 'validation') ('Eve_' + $Package + '.png')
$outputReport = Join-Path (Join-Path $ExportRoot 'validation') ('Eve_' + $Package + '.json')

Write-Host ""
Write-Host "[2/2] Blender assembly..." -ForegroundColor Cyan
$existing = @($outputBlend, $outputRender, $outputReport | Where-Object { Test-Path -LiteralPath $_ })
if ($existing.Count -eq 3 -and -not $Force) {
    Write-Host '  Outputs exist, skipped (use -Force to rebuild):' -ForegroundColor Yellow
    Write-Host ("    " + $outputBlend)
    exit 0
}

$blenderArgs = @(
    '--background', '--python', $validatePy, '--',
    '--body', $psk.FullName,
    '--head-uemodel', $shared.Head,
    '--ueformat-source', $UEFormatSource,
    '--hair', $shared.Hair,
    '--tail', $shared.Tail,
    '--tail-short', $shared.TailShort,
    '--face-assets', $shared.FaceAssets,
    '--body-diffuse', $Diffuse,
    '--hair-alpha', $shared.HairAlpha,
    '--alignment-reference', $shared.AlignmentRef,
    '--output', $outputBlend,
    '--render', $outputRender,
    '--report', $outputReport
)
if (-not $KeepSeparateArmatures) { $blenderArgs += '--merge-armatures' }
$previousErrorPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $blenderOutput = @(& $BlenderExe @blenderArgs 2>&1 | ForEach-Object { "$_" })
}
finally {
    $ErrorActionPreference = $previousErrorPreference
}
$resultLine = $blenderOutput | Where-Object { $_.StartsWith('STELLARBLADE_EVE_REPORT=') } |
    Select-Object -Last 1
if (-not $resultLine) {
    Write-Host 'Blender produced no result marker; last output lines:' -ForegroundColor Red
    $blenderOutput | Select-Object -Last 20 | ForEach-Object { Write-Host ("  " + $_) }
    exit 1
}
$report = $resultLine.Substring('STELLARBLADE_EVE_REPORT='.Length) | ConvertFrom-Json

Write-Host ''
Write-Host 'Assembly PASS:' -ForegroundColor Green
Write-Host ("  Totals: " + $report.totals.meshes + " meshes / " + $report.totals.vertices +
    " vertices / " + $report.totals.polygons + " polygons / " + $report.totals.bones + " bones")
$body = $report.components | Where-Object label -eq 'Body'
Write-Host ("  Outfit mesh: " + $body.vertices + " vertices, materials: " +
    ($body.materials -join ', '))
Write-Host ''
Write-Host ("  Blend : " + $report.output_blend) -ForegroundColor Green
Write-Host ("  Render: " + $report.render) -ForegroundColor Green
Write-Host ("  Face  : " + $report.face_render) -ForegroundColor Green
Write-Host ("  Report: " + $outputReport) -ForegroundColor Green
