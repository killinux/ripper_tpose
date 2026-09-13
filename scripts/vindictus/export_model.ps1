<#
.SYNOPSIS
  Export one Vindictus: Defying Fate character model (UE Viewer -> Blender 3.6) in one command.

.DESCRIPTION
  1. list_models.py resolves the model id (Fiona, Lethita, PCF_067, Gnoll_type3_Tribe_Boss_01, ...)
     into its skeletal-mesh packages (face + hair + armor / outfit parts, or every mesh of a monster).
  2. UE Viewer (spiritovod's UE5 specific build) exports each missing package as PSK + PNG textures
     + .mat/.props.txt into <ExportRoot>\umodel_exports (the pak AES key is read from
     VINDICTUS_AES_KEY or -AesKeyFile and handed to umodel through a temporary file).
  3. Blender 3.6 runs build_blend.py: one merged rig, rebuilt materials, textures copied next to the
     .blend, preview.png / preview_face.png, all under <ExportRoot>\blend\<Model>\.

.EXAMPLE
  .\export_model.ps1 -List
  .\export_model.ps1 Fiona
  .\export_model.ps1 PCF_067 -Force
  .\export_model.ps1 Gnoll_type3_Tribe_Boss_01 -NoPreview
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Model = '',
    [switch]$List,
    [switch]$Json,
    [string]$GameRoot = 'E:\tools\vindictus',
    [string]$ExportRoot = 'D:\vindictus_exports',
    [string]$UmodelExe = 'E:\tools\umodel_specific\materials\umodel_materials_ue5.exe',
    [string]$BlenderExe = 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe',
    [string]$AesKeyFile = 'E:\tools\vindictus\_download\aes_key.txt',
    [string]$PythonExe = 'python',
    [switch]$IncludeWeapons,
    [switch]$Force,
    [switch]$NoBlend,
    [switch]$NoPreview,
    [switch]$Smooth
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$listPy = Join-Path $scriptDir 'list_models.py'
$buildPy = Join-Path $scriptDir 'build_blend.py'
$paksDir = Join-Path $GameRoot 'Vindictus\Content\Paks'
$umodelRoot = Join-Path $ExportRoot 'umodel_exports'

# ---- AES key: env wins, then the key file; never printed, never in the command line ----
$aesKey = $env:VINDICTUS_AES_KEY
if (-not $aesKey -and (Test-Path -LiteralPath $AesKeyFile -PathType Leaf)) {
    $aesKey = (Get-Content -LiteralPath $AesKeyFile -Raw).Trim()
}
if (-not $aesKey) {
    throw "AES key missing: set VINDICTUS_AES_KEY or pass -AesKeyFile (the key is not stored in the repo)."
}
$env:VINDICTUS_AES_KEY = $aesKey

$listArgs = @($listPy, '--game-root', $GameRoot, '--export-root', $ExportRoot)
if ($IncludeWeapons) { $listArgs += '--include-weapons' }

if ($List -or -not $Model) {
    if ($Json) { $listArgs += '--json' }
    & $PythonExe @listArgs
    exit $LASTEXITCODE
}

foreach ($required in @(@('UE Viewer', $UmodelExe), @('Paks folder', $paksDir))) {
    if (-not (Test-Path -LiteralPath $required[1])) { throw ($required[0] + ' not found: ' + $required[1]) }
}

# ---- 1. resolve the model ----
$resolved = & $PythonExe @($listArgs + @('--resolve', $Model, '--json')) 2>&1
if ($LASTEXITCODE -ne 0) { throw ("list_models.py failed: " + ($resolved -join [Environment]::NewLine)) }
$spec = ($resolved -join "`n") | ConvertFrom-Json
Write-Host ("[1/3] " + $spec.id + " (" + $spec.kind + ", " + $spec.parts.Count + " parts)") -ForegroundColor Cyan
foreach ($p in $spec.parts) {
    $mark = if ($p.exported) { 'have' } else { 'need' }
    Write-Host ("      " + $mark + "  " + $p.name.PadRight(10) + $p.package)
}

$blendPath = $spec.blend
if (-not $Force -and (Test-Path -LiteralPath $blendPath)) {
    Write-Host ("SKIP  " + $blendPath + " exists (use -Force)") -ForegroundColor Yellow
    exit 0
}

# ---- 2. UE Viewer export of the missing packages ----
$keyFile = Join-Path ([System.IO.Path]::GetTempPath()) ("vindictus-aes-{0}.txt" -f [guid]::NewGuid())
[System.IO.File]::WriteAllText($keyFile, $aesKey)
try {
    New-Item -ItemType Directory -Force -Path $umodelRoot | Out-Null
    $todo = @($spec.parts | Where-Object { $Force -or -not $_.exported })
    Write-Host ("[2/3] UE Viewer: " + $todo.Count + " package(s) to export") -ForegroundColor Cyan
    foreach ($p in $todo) {
        $umodelArgs = @('-game=ue5.3', "-path=$paksDir", "-aes=@$keyFile", '-export', '-png', "-out=$umodelRoot", $p.package)
        $out = & $UmodelExe @umodelArgs 2>&1
        $summary = ($out | Select-String -Pattern '^Exported \d+/\d+' | Select-Object -Last 1)
        if (-not $summary) {
            $tail = ($out | Select-Object -Last 8) -join [Environment]::NewLine
            throw ("UE Viewer did not export " + $p.package + [Environment]::NewLine + $tail)
        }
        Write-Host ("      " + $p.name.PadRight(10) + $summary.Line)
    }
}
finally {
    Remove-Item -LiteralPath $keyFile -Force -ErrorAction SilentlyContinue
}

# re-resolve so every part carries its actual .psk/.pskx path
$resolved = & $PythonExe @($listArgs + @('--resolve', $Model, '--json')) 2>&1
if ($LASTEXITCODE -ne 0) { throw ("list_models.py failed: " + ($resolved -join [Environment]::NewLine)) }
$spec = ($resolved -join "`n") | ConvertFrom-Json
$missing = @($spec.parts | Where-Object { -not $_.exported })
if ($missing.Count -gt 0) {
    throw ("PSK still missing after export: " + (($missing | ForEach-Object { $_.package }) -join ', '))
}
if ($NoBlend) {
    Write-Host "Done (no Blender step requested)." -ForegroundColor Green
    exit 0
}

# ---- 3. Blender assembly ----
if (-not (Test-Path -LiteralPath $BlenderExe)) { throw ('Blender not found: ' + $BlenderExe) }
$outDir = $spec.out_dir
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$buildSpec = @{
    id            = $spec.id
    out_dir       = $outDir
    texture_roots = @($umodelRoot)
    hide_hair     = [bool]$spec.hide_hair
    parts         = @($spec.parts | ForEach-Object { @{ name = $_.name; psk = $_.psk } })
}
$specPath = Join-Path $outDir 'spec.json'
[System.IO.File]::WriteAllText($specPath, ($buildSpec | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))

$blenderArgs = @('--background', '--factory-startup', '--python', $buildPy, '--', '--spec', $specPath)
if ($NoPreview) { $blenderArgs += '--no-preview' }
if ($Smooth) { $blenderArgs += '--smooth' }
Write-Host ("[3/3] Blender: " + $outDir) -ForegroundColor Cyan
$log = Join-Path $outDir 'build.log'
& $BlenderExe @blenderArgs 2>&1 | Tee-Object -FilePath $log | Where-Object { $_ -match '^\[vindictus\]|Traceback|Error' } | ForEach-Object { Write-Host ("      " + $_) }
$reportLine = Select-String -Path $log -Pattern '^VINDICTUS_REPORT=' | Select-Object -Last 1
if (-not $reportLine) {
    throw ("build_blend.py produced no report; see " + $log)
}
$report = $reportLine.Line.Substring('VINDICTUS_REPORT='.Length) | ConvertFrom-Json

Write-Host ""
Write-Host ("Model     : " + $report.id) -ForegroundColor Green
Write-Host ("Rig       : " + $report.rig.bones + " bones (" + $report.rig.added_from_parts + " merged from parts, rest-pose deviation " + $report.rig.rest_pose_max_deviation + ")")
Write-Host ("Parts     : " + (($report.parts | ForEach-Object { $_.name + ' ' + $_.vertices + 'v' }) -join ', '))
Write-Host ("Materials : " + (@($report.materials.PSObject.Properties).Count) + "  textures: " + $report.textures_total)
if ($report.missing_textures.Count -gt 0) {
    Write-Host ("Unresolved textures: " + ($report.missing_textures -join ', ')) -ForegroundColor Yellow
}
foreach ($w in $report.warnings) { Write-Host ("Warning   : " + $w) -ForegroundColor Yellow }
Write-Host ("Blend     : " + $report.blend)
if ($report.preview) { Write-Host ("Preview   : " + $report.preview + "  " + $report.preview_face) }
