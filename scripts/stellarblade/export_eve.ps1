<#
.SYNOPSIS
  One-command Stellar Blade Eve standard-model assembly and validation.

.DESCRIPTION
  Wraps the verified Eve pipeline the same way riseoferos/extract_character.ps1
  and export_nude_models.ps1 wrap theirs:

    1. Check the manual FModel exports (body PSK, Face_003 .uemodel, body
       diffuse PNG).  FModel is a GUI application, so these three cannot be
       produced headlessly; the script prints the exact FModel settings when
       they are missing and stops.
    2. Re-export missing hair/tail PSKs, the ponytail alpha, and the Face_003
       texture set with the Stellar Blade-specific UE Viewer build (CLI).
    3. Resolve a Blender 3.6-compatible UEFormat importer source; if none is
       present it downloads the official source and applies
       ueformat-blender36.patch automatically.
    4. Run Blender 3.6 headless with validate_eve.py: header checks, 53-morph
       verification, SC_Hair / Ab-TL-HairB01 anchor assembly, preview renders
       and a JSON report.

  Existing validated outputs are skipped unless -Force is given.

.EXAMPLE
  .\export_eve.ps1                      # assemble + validate with defaults

.EXAMPLE
  .\export_eve.ps1 -List               # show the component inventory

.EXAMPLE
  .\export_eve.ps1 -Check              # verify every input, run nothing

.EXAMPLE
  .\export_eve.ps1 -Force              # re-run Blender even if outputs exist

.EXAMPLE
  .\export_eve.ps1 -RefreshHair -Force # re-export hair via UE Viewer first
#>
[CmdletBinding()]
param(
    [string]$GameRoot = 'D:\Program Files (x86)\Steam\steamapps\common\StellarBlade',
    [string]$ExportRoot = 'D:\stellarblade_exports',
    [string]$BlenderExe = 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe',
    # Community build from umodel_stellar_blade_v6.zip; the stock UE Viewer
    # only sees ~7,275 of the 228,867 IoStore files and must not be used.
    [string]$UmodelExe = 'C:\Tools\umodel_stellar_blade_v6.exe',
    # Directory containing the PATCHED io_scene_ueformat sources.  Leave empty
    # to auto-resolve (and, if necessary, auto-download + patch).
    [string]$UEFormatSource = '',
    [string]$OutputName = 'Eve_Standard_validation',
    [switch]$List,
    [switch]$Check,
    [switch]$RefreshHair,
    # Default output is one merged, poseable rig; pass this to keep the
    # original per-component armatures instead.
    [switch]$KeepSeparateArmatures,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$validatePy = Join-Path $scriptDir 'validate_eve.py'
$ueformatPatch = Join-Path $scriptDir 'ueformat-blender36.patch'
# ueformat-blender36.patch was cut against this UEFormat commit (importer/
# logic.py blob 5020309).  Upstream main has since restructured the importer,
# so the auto-download must pin the snapshot instead of tracking main.
$ueformatCommit = '58d1abf52d6b2e5ad8d00e7c31bc98495231e642'

$fmodelRoot = Join-Path $ExportRoot 'fmodel_exports'
$umodelRoot = Join-Path $ExportRoot 'umodel_exports'
$umodelFaceRoot = Join-Path $ExportRoot 'umodel_face_exports'

# ── Component inventory ──
# Origin 'fmodel' entries are manual GUI exports (checked, never generated
# here); origin 'umodel' entries are re-exported automatically when missing.
function New-ComponentEntry {
    param(
        [string]$Key,
        [string]$Origin,
        [string]$Path,
        [string]$Header,
        [string]$Package
    )
    [pscustomobject]@{
        Key     = $Key
        Origin  = $Origin
        Path    = $Path
        Header  = $Header      # ACTRHEAD / UEFORMAT / '' (no magic check)
        Package = $Package     # UE package exported to produce this file
    }
}

$components = @(
    New-ComponentEntry 'body' 'fmodel' `
        (Join-Path $fmodelRoot 'SB\Content\Art\Character\PC\CH_P_EVE_01\CH_P_EVE_01_Body.psk') `
        'ACTRHEAD' 'SB/Content/Art/Character/PC/CH_P_EVE_01/CH_P_EVE_01_Body'
    New-ComponentEntry 'head' 'fmodel' `
        (Join-Path $fmodelRoot 'SB\Content\Art\Character\PC\CH_P_EVE_Head\CH_P_EVE_Face_003.uemodel') `
        'UEFORMAT' 'SB/Content/Art/Character/PC/CH_P_EVE_Head/CH_P_EVE_Face_003'
    New-ComponentEntry 'body-diffuse' 'fmodel' `
        (Join-Path $fmodelRoot 'SB\Content\Art\Character\PC\CH_P_EVE_01\Tex\Body\CH_P_EVE_01_Body_D.png') `
        '' 'SB/Content/Art/Character/PC/CH_P_EVE_01/Tex/Body/CH_P_EVE_01_Body_D'
    New-ComponentEntry 'hair' 'umodel' `
        (Join-Path $umodelRoot 'Art\Character\PC\00_HR\EVE_HR_01\EVE_HR_01.psk') `
        'ACTRHEAD' 'SB/Content/Art/Character/PC/00_HR/EVE_HR_01/EVE_HR_01'
    New-ComponentEntry 'tail' 'umodel' `
        (Join-Path $umodelRoot 'Art\Character\PC\00_HR\EVE_HR_01\EVE_HR_01_Tail.psk') `
        'ACTRHEAD' 'SB/Content/Art/Character/PC/00_HR/EVE_HR_01/EVE_HR_01_Tail'
    New-ComponentEntry 'tail-short' 'umodel' `
        (Join-Path $umodelRoot 'Art\Character\PC\00_HR\EVE_HR_01\EVE_HR_Tail_Short.psk') `
        'ACTRHEAD' 'SB/Content/Art/Character/PC/00_HR/EVE_HR_01/EVE_HR_Tail_Short'
    New-ComponentEntry 'hair-alpha' 'umodel' `
        (Join-Path $umodelRoot 'Art\Character\PC\CH_P_EVE_Hair\Textures\PonyTail_Alpha.png') `
        '' 'SB/Content/Art/Character/PC/CH_P_EVE_Hair/Textures/PonyTail_Alpha'
)

# Face preview assets validate_eve.py resolves relative to --face-assets.
# All of them come out of one UE Viewer export of the Face_003 package
# (referenced eye master-material textures land under Generic/...).
$faceAssetRelPaths = @(
    'Art\Character\PC\CH_P_EVE_Head\Textures\Tex_P_EVE_Head_A.png'
    'Art\Character\PC\CH_P_EVE_Head\Textures\Tex_P_EVE_Head_N.png'
    'Art\Character\PC\CH_P_EVE_Head\Textures\S_EyeIrisBaseColor.png'
    'Art\Character\Generic\GlobalMasterMaterials\Eye\T_EyeScleraBaseColor.png'
    'Art\Character\Generic\GlobalMasterMaterials\Eye\T_EYE_NORMALS.png'
    'Art\Character\Generic\GlobalMasterMaterials\Eye\EyeLight.png'
    'Art\Character\PC\CH_P_EVE_Head\Textures\Tex_P_EVE_eyebrow_O.png'
    'Art\Character\PC\CH_P_EVE_Head\Textures\Tex_P_EVE_Teeth_A.png'
    'Art\Character\PC\CH_P_EVE_Head\Textures\Tex_P_EVE_Teeth_N.png'
    'Art\Character\PC\CH_P_EVE_Head\CH_P_EVE_Face_003.props.txt'
)

$outputBlend = Join-Path (Join-Path $ExportRoot 'blender') ($OutputName + '.blend')
$outputRender = Join-Path (Join-Path $ExportRoot 'validation') ($OutputName + '.png')
$outputFaceRender = Join-Path (Join-Path $ExportRoot 'validation') ($OutputName + '_face.png')
$outputReport = Join-Path (Join-Path $ExportRoot 'validation') ($OutputName + '.json')

function Test-FileHeader {
    param([string]$Path, [string]$Magic)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    if (-not $Magic) { return $true }
    $stream = [IO.File]::OpenRead($Path)
    try {
        $buffer = New-Object byte[] 8
        if ($stream.Read($buffer, 0, 8) -lt 8) { return $false }
        return ([Text.Encoding]::ASCII.GetString($buffer) -eq $Magic)
    }
    finally { $stream.Dispose() }
}

function Get-ComponentStatus {
    param($Component)
    if (-not (Test-Path -LiteralPath $Component.Path)) { return 'MISSING' }
    if (-not (Test-FileHeader $Component.Path $Component.Header)) { return 'BAD-HEADER' }
    return 'OK'
}

# ── -List: inventory only ──
if ($List) {
    Write-Host 'Stellar Blade Eve standard components:' -ForegroundColor Cyan
    $components | ForEach-Object {
        [pscustomobject]@{
            Component = $_.Key
            Origin    = $_.Origin
            Status    = Get-ComponentStatus $_
            Package   = $_.Package
        }
    } | Format-Table -AutoSize
    Write-Host ("Face preview assets: " + $faceAssetRelPaths.Count +
        " files under " + $umodelFaceRoot) -ForegroundColor Cyan
    Write-Host 'Outputs:' -ForegroundColor Cyan
    foreach ($output in @($outputBlend, $outputRender, $outputFaceRender, $outputReport)) {
        $mark = if (Test-Path -LiteralPath $output) { 'exists ' } else { 'pending' }
        Write-Host ("  [" + $mark + "] " + $output)
    }
    exit 0
}

$stepCount = 4

# ── Step 1: manual FModel exports ──
Write-Host ""
Write-Host "[1/$stepCount] Checking manual FModel exports..." -ForegroundColor Cyan
$fmodelComponents = @($components | Where-Object Origin -eq 'fmodel')
$fmodelBad = @()
foreach ($component in $fmodelComponents) {
    $status = Get-ComponentStatus $component
    $color = if ($status -eq 'OK') { 'Green' } else { 'Red' }
    Write-Host ("  {0,-10} {1,-12} {2}" -f $status, $component.Key, $component.Path) `
        -ForegroundColor $color
    if ($status -ne 'OK') { $fmodelBad += $component }
}
if ($fmodelBad) {
    Write-Host ""
    Write-Host 'FModel exports are missing or invalid. FModel is GUI-only; export them manually:' `
        -ForegroundColor Yellow
    Write-Host ("  1. Start FModel, add archive directory: " +
        (Join-Path $GameRoot 'SB\Content\Paks'))
    Write-Host '  2. Profile: GAME_StellarBlade; local mapping: StellarBlade_1.1.0.usmap; no AES key.'
    Write-Host '  3. Models: LOD First Level Only, Texture PNG, PSK -> Don''t Export Bone Sockets.'
    Write-Host ("  4. Output directory: " + $fmodelRoot)
    Write-Host '  5. Save Model for the packages listed above (body as ActorX PSK,'
    Write-Host '     Face_003 as UEFormat .uemodel), Save Texture for the body diffuse.'
    Write-Host '  Details: docs/stellar-blade-extraction.md section 3.'
    if (-not $Check) { exit 1 }
}

# ── Step 2: UE Viewer hair/tail/face assets ──
Write-Host ""
Write-Host "[2/$stepCount] Checking UE Viewer exports (hair, tail, face assets)..." -ForegroundColor Cyan

$modsDir = Join-Path $GameRoot 'SB\Content\Paks\~mods'
$modFiles = @()
if (Test-Path -LiteralPath $modsDir) {
    $modFiles = @(Get-ChildItem -LiteralPath $modsDir -Recurse -File `
        -Include '*.pak', '*.utoc', '*.ucas' -ErrorAction SilentlyContinue)
}

$umodelComponents = @($components | Where-Object Origin -eq 'umodel')
$missingFaceAssets = @($faceAssetRelPaths | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $umodelFaceRoot $_))
})
$umodelJobs = @()
foreach ($component in $umodelComponents) {
    $status = Get-ComponentStatus $component
    $needsExport = $RefreshHair -or ($status -ne 'OK')
    $shown = if ($needsExport) { $status + ' -> export' } else { $status }
    $color = if ($status -eq 'OK') { 'Green' } else { 'Yellow' }
    Write-Host ("  {0,-22} {1,-12} {2}" -f $shown, $component.Key, $component.Path) `
        -ForegroundColor $color
    if ($needsExport) {
        # PonyTail_Alpha rides along with the hair mesh export (-png exports
        # referenced textures); only queue mesh packages.
        if ($component.Key -in @('hair', 'tail', 'tail-short')) {
            $umodelJobs += [pscustomobject]@{ Package = $component.Package; Out = $umodelRoot }
        } elseif ($component.Key -eq 'hair-alpha') {
            $umodelJobs += [pscustomobject]@{
                Package = 'SB/Content/Art/Character/PC/00_HR/EVE_HR_01/EVE_HR_01_Tail'
                Out = $umodelRoot
            }
        }
    }
}
if ($missingFaceAssets) {
    Write-Host ("  MISSING " + $missingFaceAssets.Count + '/' + $faceAssetRelPaths.Count +
        " face preview assets under " + $umodelFaceRoot) -ForegroundColor Yellow
    $umodelJobs += [pscustomobject]@{
        Package = 'SB/Content/Art/Character/PC/CH_P_EVE_Head/CH_P_EVE_Face_003'
        Out = $umodelFaceRoot
    }
} else {
    Write-Host ("  OK         face-assets  " + $faceAssetRelPaths.Count +
        " files under " + $umodelFaceRoot) -ForegroundColor Green
}
$umodelJobs = @($umodelJobs | Sort-Object Package, Out -Unique)

if ($umodelJobs -and -not $Check) {
    if (-not (Test-Path -LiteralPath $UmodelExe)) {
        Write-Error ("Stellar Blade UE Viewer build not found: " + $UmodelExe + [Environment]::NewLine +
            "Download umodel_stellar_blade_v6.zip via the Stellar Blade Modding Guide wiki " +
            "(Extracting game files) and pass -UmodelExe. The stock gildor.org build cannot " +
            "read this game's IoStore.")
        exit 1
    }
    if ($modFiles.Count -gt 0) {
        Write-Host ("  WARNING: " + $modFiles.Count + " mod archive(s) in ~mods may override " +
            "vanilla assets during the scan. Temporarily move them out (see docs section 2) " +
            "for guaranteed-vanilla exports.") -ForegroundColor Yellow
    }
    foreach ($job in $umodelJobs) {
        Write-Host ("  UE Viewer export: " + $job.Package) -ForegroundColor White
        # UE Viewer writes progress to stderr; run via cmd /c so PowerShell's
        # Stop preference does not turn that into a terminating error.
        $umodelCmd = ('"{0}" -export "-path={1}" -game=ue4.26 -noanim -psk -png "-out={2}" "{3}" 2>&1' `
            -f $UmodelExe, $GameRoot, $job.Out, $job.Package)
        $umodelOutput = @(cmd /c $umodelCmd)
        $foundLine = $umodelOutput | Where-Object { $_ -match 'Found (\d+) game files' } |
            Select-Object -First 1
        if ($foundLine -and $foundLine -match 'Found (\d+) game files') {
            $foundCount = [int]$Matches[1]
            if ($foundCount -lt 200000) {
                Write-Host ("    WARNING: only " + $foundCount + " game files visible; expected " +
                    "~228,867. This looks like the wrong UE Viewer build or a broken " +
                    ".pak/.utoc/.ucas base-name pairing.") -ForegroundColor Yellow
            } else {
                Write-Host ("    " + $foundLine.Trim()) -ForegroundColor DarkGray
            }
        }
        $umodelOutput | Where-Object { $_ -match 'Export|Error|WARNING' } |
            Select-Object -First 6 | ForEach-Object {
                Write-Host ("    " + $_) -ForegroundColor DarkGray
            }
    }

    # Re-verify everything the jobs were supposed to produce.
    $stillBad = @()
    foreach ($component in $umodelComponents) {
        if ((Get-ComponentStatus $component) -ne 'OK') { $stillBad += $component.Path }
    }
    $stillBad += @($faceAssetRelPaths | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $umodelFaceRoot $_))
    } | ForEach-Object { Join-Path $umodelFaceRoot $_ })
    if ($stillBad) {
        Write-Error ("UE Viewer export finished but these files are still missing/invalid:" +
            [Environment]::NewLine + '  ' + ($stillBad -join ([Environment]::NewLine + '  ')))
        exit 1
    }
    Write-Host '  UE Viewer exports verified.' -ForegroundColor Green
}

# Skip a fully cached run before touching UEFormat setup or Blender.
$allOutputs = @($outputBlend, $outputRender, $outputFaceRender, $outputReport)
$existingOutputs = @($allOutputs | Where-Object { Test-Path -LiteralPath $_ })
if (-not $Check -and $existingOutputs.Count -eq $allOutputs.Count -and -not $Force) {
    Write-Host ""
    Write-Host 'All outputs exist, skipped (use -Force to rebuild):' -ForegroundColor Yellow
    foreach ($output in $allOutputs) { Write-Host ("  " + $output) }
    exit 0
}

# ── Step 3: UEFormat importer source (Blender 3.6 patched) ──
Write-Host ""
Write-Host "[3/$stepCount] Resolving patched UEFormat importer source..." -ForegroundColor Cyan

function Test-UEFormatPatched {
    param([string]$SourceDir)
    $logicPy = Join-Path $SourceDir 'importer\logic.py'
    if (-not (Test-Path -LiteralPath $logicPy)) { return $false }
    $marker = Select-String -LiteralPath $logicPy -Pattern 'bpy\.app\.version >= \(4, 0, 0\)' `
        -SimpleMatch:$false -Quiet
    return [bool]$marker
}

$ueformatCandidates = @()
if ($UEFormatSource) {
    $ueformatCandidates += $UEFormatSource
} else {
    $ueformatCandidates += Join-Path $ExportRoot ('_tools\UEFormat-' + $ueformatCommit + '\plugins\blender\io_scene_ueformat')
    $ueformatCandidates += Join-Path $scriptDir '..\..\.tmp\ueformat-main-src\UEFormat-main\plugins\blender\io_scene_ueformat'
}
$resolvedUEFormat = $null
foreach ($candidate in $ueformatCandidates) {
    if (Test-Path -LiteralPath $candidate) {
        $resolvedUEFormat = [IO.Path]::GetFullPath($candidate)
        break
    }
}

if ($resolvedUEFormat -and -not (Test-UEFormatPatched $resolvedUEFormat)) {
    Write-Host ("  Found unpatched source, applying ueformat-blender36.patch: " + $resolvedUEFormat) `
        -ForegroundColor Yellow
    if (-not $Check) {
        # importer source dir = <repo>\plugins\blender\io_scene_ueformat
        $ueformatRepoRoot = [IO.Path]::GetFullPath((Join-Path $resolvedUEFormat '..\..\..'))
        # The patch carries zero context lines; git apply rejects those
        # without --unidiff-zero.
        git -C $ueformatRepoRoot apply --unidiff-zero --verbose $ueformatPatch
        if ($LASTEXITCODE -ne 0 -or -not (Test-UEFormatPatched $resolvedUEFormat)) {
            Write-Error ("Could not apply ueformat-blender36.patch under " + $ueformatRepoRoot +
                ". Apply it manually (see scripts/stellarblade/README.md).")
            exit 1
        }
    }
}

if (-not $resolvedUEFormat -and -not $Check) {
    $ueformatToolsRoot = Join-Path $ExportRoot '_tools'
    Write-Host ("  No UEFormat source found; downloading pinned snapshot " +
        $ueformatCommit.Substring(0, 10) + '...') -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $ueformatToolsRoot | Out-Null
    $zipPath = Join-Path $ueformatToolsRoot 'UEFormat-snapshot.zip'
    Invoke-WebRequest -Uri ('https://github.com/h4lfheart/UEFormat/archive/' + $ueformatCommit + '.zip') `
        -OutFile $zipPath
    Expand-Archive -LiteralPath $zipPath -DestinationPath $ueformatToolsRoot -Force
    Remove-Item -LiteralPath $zipPath
    $ueformatRepoRoot = Join-Path $ueformatToolsRoot ('UEFormat-' + $ueformatCommit)
    git -C $ueformatRepoRoot apply --unidiff-zero --verbose $ueformatPatch
    $resolvedUEFormat = Join-Path $ueformatRepoRoot 'plugins\blender\io_scene_ueformat'
    if ($LASTEXITCODE -ne 0 -or -not (Test-UEFormatPatched $resolvedUEFormat)) {
        Write-Error ("Could not patch the pinned UEFormat snapshot under " + $ueformatRepoRoot +
            ". Apply ueformat-blender36.patch manually and pass -UEFormatSource " +
            "(see scripts/stellarblade/README.md).")
        exit 1
    }
    Write-Host ("  Downloaded and patched: " + $resolvedUEFormat) -ForegroundColor Green
}

if ($resolvedUEFormat) {
    $patchState = if (Test-UEFormatPatched $resolvedUEFormat) { 'patched' } else { 'NOT patched' }
    Write-Host ("  UEFormat source (" + $patchState + "): " + $resolvedUEFormat) `
        -ForegroundColor $(if ($patchState -eq 'patched') { 'Green' } else { 'Yellow' })
} else {
    Write-Host '  MISSING: no UEFormat source (auto-download runs outside -Check).' -ForegroundColor Yellow
}

if ($Check) {
    $fmodelOk = ($fmodelBad.Count -eq 0)
    $umodelOk = ($umodelJobs.Count -eq 0)
    $ueformatOk = ($resolvedUEFormat -and (Test-UEFormatPatched $resolvedUEFormat))
    $blenderOk = (Test-Path -LiteralPath $BlenderExe)
    Write-Host ""
    Write-Host "[4/$stepCount] Check summary (no exports were run):" -ForegroundColor Cyan
    Write-Host ("  FModel inputs : " + $(if ($fmodelOk) { 'OK' } else { 'MISSING' }))
    Write-Host ("  UE Viewer set : " + $(if ($umodelOk) { 'OK' } else { 'needs export' }))
    Write-Host ("  UEFormat 3.6  : " + $(if ($ueformatOk) { 'OK' } else { 'needs setup' }))
    Write-Host ("  Blender       : " + $(if ($blenderOk) { 'OK' } else { 'MISSING: ' + $BlenderExe }))
    if ($fmodelOk -and $umodelOk -and $ueformatOk -and $blenderOk) { exit 0 } else { exit 1 }
}

# ── Step 4: Blender assembly + validation ──
Write-Host ""
Write-Host "[4/$stepCount] Blender assembly and validation..." -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $BlenderExe)) {
    Write-Error ("Blender not found: " + $BlenderExe)
    exit 1
}
if (-not (Test-Path -LiteralPath $validatePy)) {
    Write-Error ("validate_eve.py not found: " + $validatePy)
    exit 1
}

$componentPath = @{}
foreach ($component in $components) { $componentPath[$component.Key] = $component.Path }

$blenderArgs = @(
    '--background', '--python', $validatePy, '--',
    '--body', $componentPath['body'],
    '--head-uemodel', $componentPath['head'],
    '--ueformat-source', $resolvedUEFormat,
    '--hair', $componentPath['hair'],
    '--tail', $componentPath['tail'],
    '--tail-short', $componentPath['tail-short'],
    '--face-assets', $umodelFaceRoot,
    '--body-diffuse', $componentPath['body-diffuse'],
    '--hair-alpha', $componentPath['hair-alpha'],
    '--output', $outputBlend,
    '--render', $outputRender,
    '--report', $outputReport
)
if (-not $KeepSeparateArmatures) { $blenderArgs += '--merge-armatures' }
Write-Host ("  " + $BlenderExe) -ForegroundColor DarkGray
Write-Host ("    " + ($blenderArgs -join ' ')) -ForegroundColor DarkGray

# Blender writes Python tracebacks to stderr and may still exit 0.  Capture
# both streams without letting the global Stop preference abort the run.
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
    Write-Host ''
    Write-Host 'Blender produced no result marker; last output lines:' -ForegroundColor Red
    $blenderOutput | Select-Object -Last 25 | ForEach-Object { Write-Host ("  " + $_) }
    exit 1
}
$report = $resultLine.Substring('STELLARBLADE_EVE_REPORT='.Length) | ConvertFrom-Json

# ── Final: report ──
Write-Host ''
Write-Host 'Validation PASS:' -ForegroundColor Green
$report.components | ForEach-Object {
    [pscustomobject]@{
        Component = $_.label
        Format    = $_.source_format
        Vertices  = $_.vertices
        Polygons  = $_.polygons
        Bones     = ($_.bones_per_armature | Measure-Object -Sum).Sum
    }
} | Format-Table -AutoSize
Write-Host ("  Totals: " + $report.totals.meshes + " meshes / " +
    $report.totals.vertices + " vertices / " + $report.totals.polygons +
    " polygons / " + $report.totals.bones + " bones")
Write-Host ("  Face morphs: " + $report.source_morph_targets.source_count +
    " source -> " + $report.source_morph_targets.blender_shape_key_count +
    " shape keys (with Basis)")
Write-Host ("  Hair anchor error: cap=" + $report.alignment.hair_anchor_error +
    "  tail=" + $report.alignment.tail_anchor_error)
Write-Host ''
Write-Host ("  Blend : " + $report.output_blend) -ForegroundColor Green
Write-Host ("  Render: " + $report.render) -ForegroundColor Green
Write-Host ("  Face  : " + $report.face_render) -ForegroundColor Green
Write-Host ("  Report: " + $outputReport) -ForegroundColor Green
