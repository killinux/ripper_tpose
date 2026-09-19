<#
.SYNOPSIS
  Export one The First Descendant model (CUE4Parse -> textures -> Blender 3.6) in one command.

.DESCRIPTION
  1. list_models.py resolves the model id (Bunny, Ultimate_Viessa, Bunny_AGT_001,
     MOB_CMN_1001, BOS_1001_A001, NPC_001, RW_AR_1001_A001, ...) into its skeletal
     mesh packages.
  2. CUE4Parse CLI (-g GAME_TheFirstDescendant + the community .usmap) exports each
     missing package as ActorX pskx with REAL material slot names and morph targets
     into <ExportRoot>\cue4_exports.
  3. resolve_textures.py maps every slot to its material instance, reads the textures
     it references straight from the container (zen name maps, no usmap needed),
     decodes them - they are UE5 virtual textures - to PNG with CUE4Parse, and dumps
     the instance parameters with UE Viewer.
  4. Blender 3.6 runs build_blend.py: one merged rig, textured materials, previews,
     saved to <ExportRoot>\blend\<Model>\ with a textures\ folder.
  The pak AES key is read from TFD_AES_KEY or -AesKeyFile (it is passed to CUE4Parse
  on its command line, which has no key-file option).

.EXAMPLE
  .\export_model.ps1 -List
  .\export_model.ps1 Bunny
  .\export_model.ps1 Bunny_AGT_001 -Force
  .\export_model.ps1 MOB_CMN_1001 -NoPreview
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Model = '',
    [switch]$List,
    [switch]$Json,
    [string]$Kind = '',
    [string]$Char = '',
    [string]$GameRoot = 'E:\SteamLibrary\steamapps\common\The First Descendant',
    [string]$ExportRoot = 'D:\tfd_exports',
    [string]$UmodelExe = 'E:\tools\umodel_specific\materials\umodel_materials_ue5.exe',
    [string]$Cue4ParseExe = 'E:\tools\cue4parse_cli\cue4parse.exe',
    [string]$UsmapFile = 'E:\tools\tfd\Mappings_2024-07-16_gildor.usmap',
    [string]$BlenderExe = 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe',
    [string]$AesKeyFile = 'D:\tfd_exports\_keys\aes_key.txt',
    [string]$PythonExe = 'python',
    [switch]$IncludeExtras,
    [switch]$Force,
    [switch]$NoBlend,
    [switch]$NoPreview,
    [switch]$Smooth
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$listPy = Join-Path $scriptDir 'list_models.py'
$buildPy = Join-Path $scriptDir 'build_blend.py'
$paksDir = Join-Path $GameRoot 'M1\Content\Paks'
$umodelRoot = Join-Path $ExportRoot 'umodel_exports'
$cue4Root = Join-Path $ExportRoot 'cue4_exports'
$resolvePy = Join-Path $scriptDir 'resolve_textures.py'

# ---- AES key: env wins, then the key file; never printed, never on the command line ----
$aesKey = $env:TFD_AES_KEY
if (-not $aesKey -and (Test-Path -LiteralPath $AesKeyFile -PathType Leaf)) {
    $aesKey = (Get-Content -LiteralPath $AesKeyFile -Raw).Trim()
}
if (-not $aesKey) {
    throw "AES key missing: set TFD_AES_KEY or pass -AesKeyFile (recover it with find_aes_key.py; keep it out of the repo)."
}
$env:TFD_AES_KEY = $aesKey

$listArgs = @($listPy, '--game-root', $GameRoot, '--export-root', $ExportRoot)

if ($List -or -not $Model) {
    if ($Kind) { $listArgs += @('--kind', $Kind) }
    if ($Char) { $listArgs += @('--char', $Char) }
    if ($Json) { $listArgs += '--json' }
    & $PythonExe @listArgs
    exit $LASTEXITCODE
}

foreach ($required in @(@('CUE4Parse CLI', $Cue4ParseExe), @('usmap', $UsmapFile), @('UE Viewer', $UmodelExe), @('Paks folder', $paksDir))) {
    if (-not (Test-Path -LiteralPath $required[1])) { throw ($required[0] + ' not found: ' + $required[1]) }
}

# ---- 1. resolve the model ----
$resolved = & $PythonExe @($listArgs + @('--resolve', $Model, '--json')) 2>&1
if ($LASTEXITCODE -ne 0) { throw ("list_models.py failed: " + ($resolved -join [Environment]::NewLine)) }
$spec = ($resolved -join "`n") | ConvertFrom-Json
$exportParts = @($spec.parts)
if ($IncludeExtras) { $exportParts += @($spec.extras) }
Write-Host ("[1/4] " + $spec.id + " (" + $spec.kind + ", " + $exportParts.Count + " parts)") -ForegroundColor Cyan
foreach ($p in $exportParts) {
    $mark = if ($p.exported) { 'have' } else { 'need' }
    Write-Host ("      " + $mark + "  " + $p.name.PadRight(12) + $p.package)
}

$blendPath = $spec.blend
if (-not $Force -and (Test-Path -LiteralPath $blendPath)) {
    Write-Host ("SKIP  " + $blendPath + " exists (use -Force)") -ForegroundColor Yellow
    exit 0
}

# ---- 2. CUE4Parse export of the missing packages (ActorX + morph targets, real slot names) ----
New-Item -ItemType Directory -Force -Path $cue4Root | Out-Null
$todo = @($exportParts | Where-Object { $Force -or -not $_.exported })
Write-Host ("[2/4] CUE4Parse: " + $todo.Count + " package(s) to export") -ForegroundColor Cyan
foreach ($p in $todo) {
    $pkg = 'M1/Content/' + $p.package + '.uasset'
    $cueArgs = @('-i', $paksDir, '-k', $aesKey, '-g', 'GAME_TheFirstDescendant', '-m', $UsmapFile,
                 '-o', $cue4Root, '-p', $pkg, '--mesh-format', 'ActorX', '--export-materials', '-y')
    # CUE4Parse logs to stderr; under $ErrorActionPreference = 'Stop' PowerShell 5.1 would
    # turn its first log line into a terminating NativeCommandError.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $out = & $Cue4ParseExe @cueArgs 2>&1 } finally { $ErrorActionPreference = $previousPreference }
    $joined = ($out | ForEach-Object { [string]$_ }) -join "`n"
    $expected = Join-Path $cue4Root (('M1/Content/' + $p.package).Replace('/', '\') + '.pskx')
    $expected2 = [System.IO.Path]::ChangeExtension($expected, '.psk')
    if (-not (Test-Path -LiteralPath $expected) -and -not (Test-Path -LiteralPath $expected2)) {
        $tail = (($joined -split "`n") | Where-Object { $_ -match 'ERR|Exception|Could not' } | Select-Object -Last 6) -join [Environment]::NewLine
        throw ("CUE4Parse did not export " + $p.package + [Environment]::NewLine + $tail.Replace($aesKey, '<KEY>'))
    }
    Write-Host ("      " + $p.name.PadRight(12) + 'ok')
}

# re-resolve so every part carries its actual .psk/.pskx path
$resolved = & $PythonExe @($listArgs + @('--resolve', $Model, '--json')) 2>&1
$spec = ($resolved -join "`n") | ConvertFrom-Json
$exportParts = @($spec.parts)
if ($IncludeExtras) { $exportParts += @($spec.extras) }
$missing = @($exportParts | Where-Object { -not $_.exported })
if ($missing.Count -gt 0) {
    throw ("PSK still missing after export: " + (($missing | ForEach-Object { $_.package }) -join ', '))
}
$outDir = $spec.out_dir
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# ---- 3. textures: slot -> material instance -> texture packages -> PNG (virtual textures decoded) ----
$materialsJson = Join-Path $outDir 'materials.json'
if ($Force -or -not (Test-Path -LiteralPath $materialsJson)) {
    Write-Host "[3/4] Textures: resolving material slots and decoding virtual textures" -ForegroundColor Cyan
    $resolveArgs = @($resolvePy, '--out', $outDir, '--game-root', $GameRoot, '--export-root', $ExportRoot,
                     '--aes-key-file', $AesKeyFile, '--cue4parse', $Cue4ParseExe, '--usmap', $UsmapFile, '--umodel', $UmodelExe)
    if ($spec.number) { $resolveArgs += @('--hint', ('/PC/MESH/' + $spec.number + '/')) }
    foreach ($p in $exportParts) { $resolveArgs += @('--pskx', $p.psk) }
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $PythonExe @resolveArgs 2>&1 | ForEach-Object { Write-Host ("      " + [string]$_) } }
    finally { $ErrorActionPreference = $previousPreference }
    if ($LASTEXITCODE -ne 0) { throw "resolve_textures.py failed" }
} else {
    Write-Host "[3/4] Textures: materials.json exists, reusing (use -Force to redo)" -ForegroundColor DarkGray
}

if ($NoBlend) {
    Write-Host "Done (no Blender step requested)." -ForegroundColor Green
    exit 0
}

# ---- 4. Blender assembly ----
if (-not (Test-Path -LiteralPath $BlenderExe)) { throw ('Blender not found: ' + $BlenderExe) }
$buildSpec = @{
    id        = $spec.id
    out_dir   = $outDir
    materials = $materialsJson
    parts     = @($exportParts | ForEach-Object { @{ name = $_.name; psk = $_.psk } })
}
$specPath = Join-Path $outDir 'spec.json'
[System.IO.File]::WriteAllText($specPath, ($buildSpec | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))

$blenderArgs = @('--background', '--factory-startup', '--python', $buildPy, '--', '--spec', $specPath)
if ($NoPreview) { $blenderArgs += '--no-preview' }
if ($Smooth) { $blenderArgs += '--smooth' }
Write-Host ("[4/4] Blender: " + $outDir) -ForegroundColor Cyan
$log = Join-Path $outDir 'build.log'
# Tee-Object would write the log as UTF-16; other tools (collect_manifest.py) read it
# as UTF-8, so capture and write it ourselves. Blender logs to stderr like CUE4Parse does.
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try { $blenderOut = @(& $BlenderExe @blenderArgs 2>&1 | ForEach-Object { [string]$_ }) }
finally { $ErrorActionPreference = $previousPreference }
[System.IO.File]::WriteAllLines($log, $blenderOut, (New-Object System.Text.UTF8Encoding($false)))
$blenderOut | Where-Object { $_ -match '^\[tfd\]|Traceback|Error' } | ForEach-Object { Write-Host ("      " + $_) }
$reportLine = Select-String -Path $log -Pattern '^TFD_REPORT=' | Select-Object -Last 1
if (-not $reportLine) { throw ("build_blend.py produced no report; see " + $log) }
$report = $reportLine.Line.Substring('TFD_REPORT='.Length) | ConvertFrom-Json

Write-Host ""
Write-Host ("Model : " + $report.id) -ForegroundColor Green
Write-Host ("Rig   : " + $report.rig.bones + " bones, " + $report.meshes + " mesh object(s)")
Write-Host ("Parts : " + (($report.parts | ForEach-Object { $_.name + ' ' + $_.vertices + 'v/' + $_.slots + 'slots/' + $_.shape_keys + 'morphs' }) -join ', '))
Write-Host ("Materials: " + (@($report.materials.PSObject.Properties).Count) + "  textures: " + $report.textures_total)
if ($report.missing_textures.Count -gt 0) { Write-Host ("Missing textures: " + ($report.missing_textures -join ', ')) -ForegroundColor Yellow }
foreach ($w in $report.warnings) { Write-Host ("Warn  : " + $w) -ForegroundColor Yellow }
Write-Host ("Blend : " + $report.blend)
if ($report.preview) { Write-Host ("Preview: " + $report.preview) }
