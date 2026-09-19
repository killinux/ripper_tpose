<#
.SYNOPSIS
  Export one The First Descendant model (UE Viewer -> Blender 3.6) in one command.

.DESCRIPTION
  1. list_models.py resolves the model id (Bunny, Ultimate_Viessa, Bunny_AGT_001,
     MOB_CMN_1001, BOS_1001_A001, NPC_001, RW_AR_1001_A001, ...) into its skeletal
     mesh packages.
  2. UE Viewer (spiritovod's UE5 build, -game=first) exports each missing package as
     PSK/PSKX (+ material .props.txt) into <ExportRoot>\umodel_exports.  The pak AES
     key is read from TFD_AES_KEY or -AesKeyFile and handed to umodel via a temp file.
     NOTE: The First Descendant textures are UE5 virtual textures; UE Viewer cannot
     decode them, so this route is geometry + rig only (see README for the FModel
     + .usmap route to full textures).
  3. Blender 3.6 runs build_blend.py: one merged rig, neutral materials, preview.png,
     saved to <ExportRoot>\blend\<Model>\.

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

foreach ($required in @(@('UE Viewer', $UmodelExe), @('Paks folder', $paksDir))) {
    if (-not (Test-Path -LiteralPath $required[1])) { throw ($required[0] + ' not found: ' + $required[1]) }
}

# ---- 1. resolve the model ----
$resolved = & $PythonExe @($listArgs + @('--resolve', $Model, '--json')) 2>&1
if ($LASTEXITCODE -ne 0) { throw ("list_models.py failed: " + ($resolved -join [Environment]::NewLine)) }
$spec = ($resolved -join "`n") | ConvertFrom-Json
$exportParts = @($spec.parts)
if ($IncludeExtras) { $exportParts += @($spec.extras) }
Write-Host ("[1/3] " + $spec.id + " (" + $spec.kind + ", " + $exportParts.Count + " parts)") -ForegroundColor Cyan
foreach ($p in $exportParts) {
    $mark = if ($p.exported) { 'have' } else { 'need' }
    Write-Host ("      " + $mark + "  " + $p.name.PadRight(12) + $p.package)
}

$blendPath = $spec.blend
if (-not $Force -and (Test-Path -LiteralPath $blendPath)) {
    Write-Host ("SKIP  " + $blendPath + " exists (use -Force)") -ForegroundColor Yellow
    exit 0
}

# ---- 2. UE Viewer export of the missing packages ----
$keyFile = Join-Path ([System.IO.Path]::GetTempPath()) ("tfd-aes-{0}.txt" -f [guid]::NewGuid())
[System.IO.File]::WriteAllText($keyFile, $aesKey)
try {
    New-Item -ItemType Directory -Force -Path $umodelRoot | Out-Null
    $todo = @($exportParts | Where-Object { $Force -or -not $_.exported })
    Write-Host ("[2/3] UE Viewer: " + $todo.Count + " package(s) to export") -ForegroundColor Cyan
    foreach ($p in $todo) {
        $umodelArgs = @('-game=first', "-path=$paksDir", "-aes=@$keyFile", '-export', '-png', '-morphs',
                        "-out=$umodelRoot", $p.package)
        $out = & $UmodelExe @umodelArgs 2>&1
        $summary = ($out | Select-String -Pattern '^Exported \d+/\d+' | Select-Object -Last 1)
        if (-not $summary) {
            $tail = ($out | Select-Object -Last 8) -join [Environment]::NewLine
            throw ("UE Viewer did not export " + $p.package + [Environment]::NewLine + $tail)
        }
        Write-Host ("      " + $p.name.PadRight(12) + $summary.Line)
    }
}
finally {
    Remove-Item -LiteralPath $keyFile -Force -ErrorAction SilentlyContinue
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
if ($NoBlend) {
    Write-Host "Done (no Blender step requested)." -ForegroundColor Green
    exit 0
}

# ---- 3. Blender assembly ----
if (-not (Test-Path -LiteralPath $BlenderExe)) { throw ('Blender not found: ' + $BlenderExe) }
$outDir = $spec.out_dir
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$buildSpec = @{
    id      = $spec.id
    out_dir = $outDir
    parts   = @($exportParts | ForEach-Object { @{ name = $_.name; psk = $_.psk } })
}
$specPath = Join-Path $outDir 'spec.json'
[System.IO.File]::WriteAllText($specPath, ($buildSpec | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))

$blenderArgs = @('--background', '--factory-startup', '--python', $buildPy, '--', '--spec', $specPath)
if ($NoPreview) { $blenderArgs += '--no-preview' }
if ($Smooth) { $blenderArgs += '--smooth' }
Write-Host ("[3/3] Blender: " + $outDir) -ForegroundColor Cyan
$log = Join-Path $outDir 'build.log'
& $BlenderExe @blenderArgs 2>&1 | Tee-Object -FilePath $log | Where-Object { $_ -match '^\[tfd\]|Traceback|Error' } | ForEach-Object { Write-Host ("      " + $_) }
$reportLine = Select-String -Path $log -Pattern '^TFD_REPORT=' | Select-Object -Last 1
if (-not $reportLine) { throw ("build_blend.py produced no report; see " + $log) }
$report = $reportLine.Line.Substring('TFD_REPORT='.Length) | ConvertFrom-Json

Write-Host ""
Write-Host ("Model : " + $report.id) -ForegroundColor Green
Write-Host ("Rig   : " + $report.rig.bones + " bones, " + $report.meshes + " mesh object(s)")
Write-Host ("Parts : " + (($report.parts | ForEach-Object { $_.name + ' ' + $_.vertices + 'v/' + $_.slots + 'slots' }) -join ', '))
foreach ($w in $report.warnings) { Write-Host ("Warn  : " + $w) -ForegroundColor Yellow }
Write-Host ("Blend : " + $report.blend)
if ($report.preview) { Write-Host ("Preview: " + $report.preview) }
Write-Host "Textures are UE5 virtual textures (not exported by UE Viewer) - see README for the FModel route." -ForegroundColor DarkYellow
