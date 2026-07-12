<#
.SYNOPSIS
  Extract rigged FBX model from Rise of Eros AssetBundles by character ID.
.EXAMPLE
  .\extract_character.ps1 a01
  .\extract_character.ps1 a01,b02,c03
  .\extract_character.ps1 a01 -OutputRoot E:\my_exports
  .\extract_character.ps1 a01 -IncludeShare    # load *share* bundles (slower but more complete)
  .\extract_character.ps1 a01 -ExportTextures  # also export PNG textures
  .\extract_character.ps1 -List                # list all available character IDs
#>
param(
    [Parameter(Position=0)]
    [string[]]$CharacterIds,

    [string]$GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros",
    [string]$OutputRoot = "D:\roe_exports",
    [string]$CliExe = "E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe",

    [switch]$IncludeShare,
    [switch]$ExportTextures,
    [switch]$List,
    [switch]$KeepStage
)

$ErrorActionPreference = 'Stop'
$abDir = Join-Path $GameRoot "RiseOfEros_Data\StreamingAssets\AssetBundles"

if (-not (Test-Path $abDir)) {
    Write-Error "AssetBundle dir not found: $abDir"
    exit 1
}
if (-not (Test-Path $CliExe)) {
    Write-Error "AssetStudioModCLI not found: $CliExe"
    exit 1
}

# ── List all character IDs ──
if ($List) {
    $ids = Get-ChildItem $abDir -Recurse -Filter "chara_armor_pc_*.ab" -File |
        ForEach-Object { if ($_.BaseName -match 'pc_([a-z]\d+)_') { $Matches[1] } } |
        Sort-Object -Unique
    Write-Host ("Found " + $ids.Count + " character IDs:") -ForegroundColor Cyan
    $ids -join ', '
    exit 0
}

if (-not $CharacterIds -or $CharacterIds.Count -eq 0) {
    Write-Error "Specify character ID, e.g.: .\extract_character.ps1 a01   (use -List to see all)"
    exit 1
}

# ── Support comma-separated IDs ──
$allIds = @()
foreach ($raw in $CharacterIds) {
    $allIds += $raw -split '[,;]' | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }
}

foreach ($id in $allIds) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "  Extracting character: $id" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host ""

    $stageDir = Join-Path $OutputRoot "_stage_$id"
    $outDir   = Join-Path $OutputRoot $id

    # ── Stage 1: collect bundles ──
    Write-Host "[1/4] Collecting bundles..." -ForegroundColor Cyan
    if (Test-Path $stageDir) { Remove-Item -Recurse -Force $stageDir }
    New-Item -ItemType Directory -Force $stageDir | Out-Null

    $charFiles = Get-ChildItem $abDir -Recurse -File | Where-Object {
        $_.Name -match "_${id}_" -or $_.Name -match "_${id}\." -or $_.Name -match "^(bare|eros|suit|accessory|vertex).*${id}"
    }
    $commonFiles = Get-ChildItem $abDir -Recurse -File -Filter "chara_armor_common*.ab"

    $collected = @($charFiles) + @($commonFiles)

    if ($IncludeShare) {
        $shareFiles = Get-ChildItem $abDir -Recurse -File | Where-Object {
            $_.Name -match "chara_.*_share" -and $_.Name -notmatch "chara_tex_enemy" -and $_.Name -notmatch "chara_enemy"
        }
        $collected += @($shareFiles)
        Write-Host "  (including share bundles, enemy textures excluded)"
    }

    $collected = $collected | Sort-Object FullName -Unique
    foreach ($f in $collected) {
        Copy-Item -LiteralPath $f.FullName -Destination $stageDir -Force
    }

    $stageMB = [math]::Round((Get-ChildItem $stageDir -File | Measure-Object Length -Sum).Sum / 1MB, 1)
    Write-Host ("  Collected " + $collected.Count + " bundles (" + $stageMB + " MB) -> " + $stageDir)

    # ── Stage 2: export FBX (splitObjects, no animation = bind pose) ──
    Write-Host ""
    Write-Host "[2/4] Exporting FBX (bind pose, no animation)..." -ForegroundColor Cyan
    if (Test-Path $outDir) { Remove-Item -Recurse -Force $outDir }

    $cliArgs = @(
        $stageDir,
        '-m', 'splitObjects',
        '--fbx-animation', 'skip',
        '--fbx-scale-factor', '1',
        '-g', 'sceneHierarchy',
        '-o', $outDir,
        '--log-level', 'warning'
    )
    & $CliExe @cliArgs 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

    # ── Stage 3: export textures ──
    if ($ExportTextures) {
        Write-Host ""
        Write-Host "[3/4] Exporting textures (PNG)..." -ForegroundColor Cyan
        $texDir = Join-Path $outDir "_textures"
        $texArgs = @(
            $stageDir,
            '-m', 'export',
            '-t', 'tex2d',
            '--filter-by-name', $id,
            '--image-format', 'png',
            '-g', 'none',
            '-o', $texDir,
            '--log-level', 'warning'
        )
        & $CliExe @texArgs 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
        $texCount = (Get-ChildItem $texDir -Recurse -Filter "*.png" -ErrorAction SilentlyContinue | Measure-Object).Count
        Write-Host ("  Textures: " + $texCount + " PNGs -> " + $texDir)
    } else {
        Write-Host ""
        Write-Host "[3/4] Skipping textures (add -ExportTextures to enable)" -ForegroundColor DarkGray
    }

    # ── Stage 4: report ──
    Write-Host ""
    Write-Host "[4/4] Results:" -ForegroundColor Cyan
    $fbxFiles = Get-ChildItem $outDir -Recurse -Filter "*.fbx" -File -ErrorAction SilentlyContinue
    $pcFbx = $fbxFiles | Where-Object { $_.Name -match "^pc_$id" -or $_.Name -match "^Prefab_pc_$id" }
    $totalFbx = $fbxFiles.Count
    $pcCount  = @($pcFbx).Count

    Write-Host ("  Total FBX: " + $totalFbx + " (character-related: " + $pcCount + ")")
    Write-Host ""
    Write-Host "  Character FBX (by size):" -ForegroundColor White

    $pcFbx | Sort-Object Length -Descending | ForEach-Object {
        $mb = [math]::Round($_.Length / 1MB, 3)
        Write-Host ("    {0,7} MB  {1}" -f $mb, $_.Name)
    }

    if (-not $KeepStage) {
        Remove-Item -Recurse -Force $stageDir -ErrorAction SilentlyContinue
        Write-Host ""
        Write-Host "  Stage dir cleaned up"
    }

    Write-Host ""
    Write-Host ("  Output: " + $outDir) -ForegroundColor Green
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
