<#
.SYNOPSIS
  Extract rigged model from Rise of Eros AssetBundles by character ID.
.EXAMPLE
  .\extract_character.ps1 a01
  .\extract_character.ps1 a01,b02,c03
  .\extract_character.ps1 a01 -Format xps         # FBX + auto-convert to XPS
  .\extract_character.ps1 a01 -Format pmx          # FBX + auto-convert to PMX
  .\extract_character.ps1 a01 -Format glb          # FBX + auto-convert to GLB
  .\extract_character.ps1 a01 -Format xps,pmx,glb  # FBX + all three
  .\extract_character.ps1 a01 -ExportTextures      # also export PNG textures
  .\extract_character.ps1 a01 -IncludeShare        # load *share* bundles (slower)
  .\extract_character.ps1 -List                    # list all available character IDs
#>
param(
    [Parameter(Position=0)]
    [string[]]$CharacterIds,

    [string]$GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros",
    [string]$OutputRoot = "D:\roe_exports",
    [string]$CliExe = "E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe",
    [string]$BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [string]$NoesisExe = "E:\tools\noesisv\Noesis.exe",

    [string[]]$Format,
    [switch]$IncludeShare,
    [switch]$ExportTextures,
    [switch]$List,
    [switch]$KeepStage
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$convertPy = Join-Path $scriptDir "convert_fbx.py"
$abDir = Join-Path $GameRoot "RiseOfEros_Data\StreamingAssets\AssetBundles"

if (-not (Test-Path $abDir)) {
    Write-Error "AssetBundle dir not found: $abDir"
    exit 1
}
if (-not (Test-Path $CliExe)) {
    Write-Error "AssetStudioModCLI not found: $CliExe"
    exit 1
}

# ── Parse -Format ──
$formats = @()
if ($Format) {
    foreach ($f in $Format) {
        $formats += $f -split '[,;]' | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }
    }
    $valid = @('xps','pmx','glb')
    foreach ($f in $formats) {
        if ($f -notin $valid) {
            Write-Error "Unknown format '$f'. Valid: $($valid -join ', ')"
            exit 1
        }
    }
    if (($formats | Where-Object { $_ -in 'xps','pmx' }) -and -not (Test-Path $BlenderExe)) {
        Write-Error "Blender not found at $BlenderExe (needed for XPS/PMX conversion)"
        exit 1
    }
    if (-not (Test-Path $convertPy)) {
        Write-Error "convert_fbx.py not found at $convertPy"
        exit 1
    }
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

$stepCount = 4
if ($formats.Count -gt 0) { $stepCount = 5 }

foreach ($id in $allIds) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "  Extracting character: $id" -ForegroundColor Yellow
    if ($formats.Count -gt 0) {
        Write-Host ("  Formats: FBX + " + ($formats -join ', ')) -ForegroundColor Yellow
    }
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host ""

    $stageDir = Join-Path $OutputRoot "_stage_$id"
    $outDir   = Join-Path $OutputRoot $id

    # ── Stage 1: collect bundles ──
    Write-Host "[1/$stepCount] Collecting bundles..." -ForegroundColor Cyan
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

    # ── Stage 2: export FBX ──
    Write-Host ""
    Write-Host "[2/$stepCount] Exporting FBX (bind pose, no animation)..." -ForegroundColor Cyan
    if (Test-Path $outDir) { Remove-Item -Recurse -Force $outDir }

    $cliArgs = @(
        $stageDir,
        '-m', 'splitObjects',
        '--fbx-animation', 'skip',
        '--fbx-scale-factor', '100',
        '-g', 'sceneHierarchy',
        '-o', $outDir,
        '--log-level', 'warning'
    )
    & $CliExe @cliArgs 2>&1 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

    # ── Stage 3: export textures ──
    if ($ExportTextures) {
        Write-Host ""
        Write-Host "[3/$stepCount] Exporting textures (PNG)..." -ForegroundColor Cyan
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
        Write-Host "[3/$stepCount] Skipping textures (add -ExportTextures to enable)" -ForegroundColor DarkGray
    }

    # ── Stage 4: format conversion ──
    if ($formats.Count -gt 0) {
        Write-Host ""
        Write-Host "[4/$stepCount] Converting formats..." -ForegroundColor Cyan

        $fbxFiles = Get-ChildItem $outDir -Recurse -Filter "*.fbx" -File -ErrorAction SilentlyContinue
        $pcFbx = @($fbxFiles | Where-Object { $_.Name -match "^pc_$id" -or $_.Name -match "^Prefab_pc_$id" })

        if ($pcFbx.Count -eq 0) {
            Write-Host "  No character FBX found to convert" -ForegroundColor Red
        } else {
            # Pick the main body FBX (largest pc_<id>_nk* or pc_<id>_hd*)
            $mainFbx = $pcFbx | Where-Object { $_.Name -match "nk_bs|nk_model|_nk\." } |
                       Sort-Object Length -Descending | Select-Object -First 1
            if (-not $mainFbx) {
                $mainFbx = $pcFbx | Sort-Object Length -Descending | Select-Object -First 1
            }

            Write-Host ("  Source: " + $mainFbx.Name + " (" + [math]::Round($mainFbx.Length/1MB,2) + " MB)")

            foreach ($fmt in $formats) {
                $convertDir = Join-Path $outDir $fmt
                New-Item -ItemType Directory -Force $convertDir | Out-Null

                if ($fmt -eq 'glb') {
                    # GLB: use Blender headless (built-in glTF, no addon needed)
                    Write-Host ("  -> GLB via Blender...") -ForegroundColor White
                    & $BlenderExe --background --python $convertPy -- $mainFbx.FullName $convertDir glb 2>&1 |
                        Select-String '\[convert\]' | ForEach-Object { Write-Host ("    " + $_.Line) -ForegroundColor DarkGray }
                }
                elseif ($fmt -eq 'xps') {
                    # XPS: try Noesis first (faster, no addon dependency), fallback to Blender
                    Write-Host ("  -> XPS via Blender + XNALaraMesh...") -ForegroundColor White
                    & $BlenderExe --background --python $convertPy -- $mainFbx.FullName $convertDir xps 2>&1 |
                        Select-String '\[convert\]' | ForEach-Object { Write-Host ("    " + $_.Line) -ForegroundColor DarkGray }
                }
                elseif ($fmt -eq 'pmx') {
                    Write-Host ("  -> PMX via Blender + mmd_tools...") -ForegroundColor White
                    & $BlenderExe --background --python $convertPy -- $mainFbx.FullName $convertDir pmx 2>&1 |
                        Select-String '\[convert\]' | ForEach-Object { Write-Host ("    " + $_.Line) -ForegroundColor DarkGray }
                }

                $converted = Get-ChildItem $convertDir -File -ErrorAction SilentlyContinue
                if ($converted) {
                    foreach ($cf in $converted) {
                        Write-Host ("    " + [math]::Round($cf.Length/1MB,3) + " MB  " + $cf.Name) -ForegroundColor Green
                    }
                } else {
                    Write-Host ("    No output for $fmt (check Blender/Noesis logs)") -ForegroundColor Red
                }
            }
        }
    }

    # ── Final: report ──
    $lastStep = $stepCount
    Write-Host ""
    Write-Host "[$lastStep/$stepCount] Results:" -ForegroundColor Cyan
    $fbxFiles = Get-ChildItem $outDir -Recurse -Filter "*.fbx" -File -ErrorAction SilentlyContinue
    $pcFbx = $fbxFiles | Where-Object { $_.Name -match "^pc_$id" -or $_.Name -match "^Prefab_pc_$id" }
    $totalFbx = $fbxFiles.Count
    $pcCount  = @($pcFbx).Count

    Write-Host ("  Total FBX: " + $totalFbx + " (character-related: " + $pcCount + ")")
    Write-Host ""
    Write-Host "  Character FBX (by size):" -ForegroundColor White

    $pcFbx | Sort-Object Length -Descending | Select-Object -First 15 | ForEach-Object {
        $mb = [math]::Round($_.Length / 1MB, 3)
        Write-Host ("    {0,7} MB  {1}" -f $mb, $_.Name)
    }

    # Show converted files
    foreach ($fmt in $formats) {
        $fmtDir = Join-Path $outDir $fmt
        if (Test-Path $fmtDir) {
            $fmtFiles = Get-ChildItem $fmtDir -File -ErrorAction SilentlyContinue
            if ($fmtFiles) {
                Write-Host ""
                Write-Host ("  " + $fmt.ToUpper() + ":") -ForegroundColor White
                foreach ($cf in $fmtFiles) {
                    Write-Host ("    {0,7} MB  {1}" -f [math]::Round($cf.Length/1MB,3), $cf.Name)
                }
            }
        }
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
