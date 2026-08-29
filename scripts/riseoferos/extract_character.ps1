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
  .\extract_character.ps1 nude:b01 -Format blend,fbx,xps,glb
  .\extract_character.ps1 nude:b01 -Force          # overwrite existing nude outputs
  .\extract_character.ps1 a01 -ExportTextures      # also export PNG textures
  .\extract_character.ps1 a01 -IncludeShare        # load *share* bundles (slower)
  .\extract_character.ps1 -List                    # list all available character IDs
#>
param(
    [Parameter(Position=0)]
    [string[]]$CharacterIds,

    [string]$GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros",
    [string]$CacheRoot = "$env:USERPROFILE\AppData\LocalLow\Pinkcore\Rise of Eros\AssetBundles",
    [string]$OutputRoot = "D:\roe_exports",
    [string]$CliExe = "E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe",
    [string]$BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [string]$NoesisExe = "E:\tools\noesisv\Noesis.exe",

    [string[]]$Format,
    [switch]$IncludeShare,
    [switch]$ExportTextures,
    [switch]$List,
    [switch]$KeepStage,
    # Only nude:<id> exports honor -Force (overwrite existing outputs);
    # regular extraction always re-runs and overwrites its own output.
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$convertPy = Join-Path $scriptDir "convert_fbx.py"
$installAbDir = Join-Path $GameRoot "RiseOfEros_Data\StreamingAssets\AssetBundles"
$assetBundleDirs = @()
foreach ($candidateDir in @($installAbDir, $CacheRoot)) {
    if ($candidateDir -and (Test-Path -LiteralPath $candidateDir) -and
        $candidateDir -notin $assetBundleDirs) {
        $assetBundleDirs += $candidateDir
    }
}

if ($assetBundleDirs.Count -eq 0) {
    Write-Error "No AssetBundle directories found. Checked: $installAbDir ; $CacheRoot"
    exit 1
}

# Build one merged inventory. SourcePriority breaks timestamp ties in favor of
# runtime-downloaded bundles, while the install directory supplies base/common data.
$bundleFiles = @()
for ($priority = 0; $priority -lt $assetBundleDirs.Count; $priority++) {
    $root = $assetBundleDirs[$priority]
    $bundleFiles += Get-ChildItem -LiteralPath $root -Recurse -Filter "*.ab" -File | ForEach-Object {
        [pscustomobject]@{
            Name           = $_.Name
            BaseName       = $_.BaseName
            FullName       = $_.FullName
            Length         = $_.Length
            LastWriteTime  = $_.LastWriteTime
            SourceRoot     = $root
            SourcePriority = $priority
        }
    }
}

function Select-PreferredBundle {
    param([object[]]$Candidates)

    $sortProperties = @(
        @{ Expression = { $_.LastWriteTime }; Descending = $true }
        @{ Expression = { $_.SourcePriority }; Descending = $true }
    )
    @($Candidates | Group-Object Name | ForEach-Object {
        $_.Group | Sort-Object -Property $sortProperties | Select-Object -First 1
    })
}

if (-not $List -and -not (Test-Path $CliExe)) {
    Write-Error "AssetStudioModCLI not found: $CliExe"
    exit 1
}

# ── Parse -Format ──
$formats = @()
if ($Format) {
    foreach ($f in $Format) {
        $formats += $f -split '[,;]' | ForEach-Object { $_.Trim().ToLower() } | Where-Object { $_ }
    }
    $valid = @('blend','fbx','xps','pmx','glb')
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
    # Only model-bearing bundles count. This includes bare-only/NPC models while
    # excluding IDs that occur solely in voice, SFX, metadata, or video bundles.
    $ids = $bundleFiles |
        ForEach-Object {
            if ($_.BaseName -match '^chara_(?:armor|bare)_pc_([a-z]\d+)(?:_|$)') {
                $Matches[1].ToLowerInvariant()
            }
        } |
        Sort-Object -Unique
    Write-Host ("Found " + $ids.Count + " character IDs across " +
                $assetBundleDirs.Count + " AssetBundle source(s):") -ForegroundColor Cyan
    $ids -join ', '
    Write-Host ""
    $nudeKeys = @('a00') + @(
        'a','b','c','d','e','f','g','h','i','j','k','l','m' |
            ForEach-Object { $_ + '01' }
    ) + @('e01_fm','f01_fm','g01_fm')
    Write-Host ("Materialized nude bases: " + $nudeKeys.Count) -ForegroundColor Cyan
    ($nudeKeys | ForEach-Object { 'nude:' + $_ }) -join ', '
    Write-Host "  Use: .\extract_character.ps1 nude:b01 -Format blend,fbx,xps,glb" `
        -ForegroundColor DarkGray
    Write-Host "  Missing FBX/texture sources are extracted automatically first." `
        -ForegroundColor DarkGray
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

$knownNudeKeys = @('a00') + @(
    @('a','b','c','d','e','f','g','h','i','j','k','l','m') |
        ForEach-Object { $_ + '01' }
) + @('e01_fm','f01_fm','g01_fm')
$nudeIds = @()
$regularIds = @()
foreach ($id in $allIds) {
    if ($id -match '^nude[:-](.+)$') {
        $nudeIds += $Matches[1]
    } else {
        $regularIds += $id
    }
}
$unknownNude = @($nudeIds | Where-Object { $_ -notin $knownNudeKeys })
if ($unknownNude) {
    Write-Error "Unknown nude model ID(s): $($unknownNude -join ', ') (use -List)"
    exit 1
}

if ($regularIds -and 'blend' -in $formats) {
    Write-Error "Format 'blend' is available for nude:<id> entries; regular character extraction always outputs FBX."
    exit 1
}

if ($nudeIds) {
    $nudeScript = Join-Path $scriptDir 'export_nude_models.ps1'
    if (-not (Test-Path -LiteralPath $nudeScript)) {
        Write-Error "Nude export script not found: $nudeScript"
        exit 1
    }

    # nude:<id> builds on this script's own FBX + _textures output.  On a
    # machine that never extracted the base character, run the regular
    # extraction (textures included) first instead of failing downstream
    # with 'FBX not found'.
    $missingSources = @()
    foreach ($nudeId in $nudeIds) {
        $charId = $nudeId -replace '_fm$', ''
        if ($charId -in $missingSources) { continue }
        $characterDir = Join-Path $OutputRoot $charId
        $hasFbx = $false
        $hasAlbedo = $false
        if (Test-Path -LiteralPath $characterDir) {
            $hasFbx = @(Get-ChildItem -LiteralPath $characterDir -Recurse `
                -Filter "*pc_${charId}*_nk*.fbx" -File -ErrorAction SilentlyContinue).Count -gt 0
            $hasAlbedo = @(Get-ChildItem -LiteralPath $characterDir -Recurse `
                -Filter "pc_${charId}*lbedo*.png" -File -ErrorAction SilentlyContinue).Count -gt 0
        }
        if (-not ($hasFbx -and $hasAlbedo)) {
            $missingSources += $charId
        }
    }
    if ($missingSources) {
        Write-Host ("Nude source FBX/textures missing under " + $OutputRoot +
            "; extracting first: " + ($missingSources -join ', ')) -ForegroundColor Cyan
        $extractArguments = @{
            CharacterIds   = $missingSources
            GameRoot       = $GameRoot
            CacheRoot      = $CacheRoot
            OutputRoot     = $OutputRoot
            CliExe         = $CliExe
            BlenderExe     = $BlenderExe
            NoesisExe      = $NoesisExe
            ExportTextures = $true
        }
        if ($IncludeShare) { $extractArguments.IncludeShare = $true }
        if ($KeepStage) { $extractArguments.KeepStage = $true }
        & $PSCommandPath @extractArguments
    }

    $nudeOutput = Join-Path $OutputRoot 'nude_materials'
    $nudeArguments = @{
        SourceRoot = $OutputRoot
        OutputDir = $nudeOutput
        GameRoot = $GameRoot
        CacheRoot = $CacheRoot
        BlenderExe = $BlenderExe
        CliExe = $CliExe
        Only = $nudeIds
        Format = $(if ($formats) { $formats } else { @('blend') })
    }
    if ($Force) { $nudeArguments.Force = $true }
    if ($KeepStage) { $nudeArguments.KeepTemp = $true }
    & $nudeScript @nudeArguments
}

if (-not $regularIds) {
    exit 0
}
$regularFormats = @($formats | Where-Object { $_ -in @('xps','pmx','glb') })
$allIds = $regularIds

$stepCount = 4
if ($regularFormats.Count -gt 0) { $stepCount = 5 }

foreach ($id in $allIds) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "  Extracting character: $id" -ForegroundColor Yellow
    if ($regularFormats.Count -gt 0) {
        Write-Host ("  Formats: FBX + " + ($regularFormats -join ', ')) -ForegroundColor Yellow
    }
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host ""

    $stageDir = Join-Path $OutputRoot "_stage_$id"
    $outDir   = Join-Path $OutputRoot $id

    # ── Stage 1: collect bundles ──
    Write-Host "[1/$stepCount] Collecting bundles..." -ForegroundColor Cyan
    if (Test-Path $stageDir) { Remove-Item -Recurse -Force $stageDir }
    New-Item -ItemType Directory -Force $stageDir | Out-Null

    $idPattern = [regex]::Escape($id)
    $charFiles = $bundleFiles | Where-Object {
        $_.Name -match "_${idPattern}_" -or $_.Name -match "_${idPattern}\." -or
        $_.Name -match "^(bare|eros|suit|accessory|vertex).*${idPattern}"
    }
    $commonFiles = $bundleFiles | Where-Object { $_.Name -like "chara_armor_common*.ab" }

    # 体型共享包：脸/眼球/眉毛/头发贴图在 chara_tex_bare_pc_<体型>_common*（不含角色 ID）
    $bodyType = ($id -replace '[0-9].*$', '')
    $bodyCommonFiles = @()
    if ($bodyType) {
        $bodyTypePattern = [regex]::Escape($bodyType)
        $bodyCommonFiles = $bundleFiles | Where-Object {
            $_.Name -match "chara_.*_pc_${bodyTypePattern}_common"
        }
    }

    $collected = @($charFiles) + @($commonFiles) + @($bodyCommonFiles)

    if ($IncludeShare) {
        $shareFiles = $bundleFiles | Where-Object {
            $_.Name -match "chara_.*_share" -and $_.Name -notmatch "chara_tex_enemy" -and $_.Name -notmatch "chara_enemy"
        }
        $collected += @($shareFiles)
        Write-Host "  (including share bundles, enemy textures excluded)"
    }

    $collected = Select-PreferredBundle -Candidates $collected
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
        # 不按角色名过滤：脸/眼/眉/发等共享贴图叫 pc_<体型>_nk_*（不含角色 ID），
        # 过滤会漏掉它们；stage 里本来就只有该角色的 bundle
        $texArgs = @(
            $stageDir,
            '-m', 'export',
            '-t', 'tex2d',
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
    if ($regularFormats.Count -gt 0) {
        Write-Host ""
        Write-Host "[4/$stepCount] Converting formats..." -ForegroundColor Cyan

        $fbxFiles = Get-ChildItem $outDir -Recurse -Filter "*.fbx" -File -ErrorAction SilentlyContinue
        $pcFbx = @($fbxFiles | Where-Object { $_.Name -match "^pc_$id" -or $_.Name -match "^Prefab_pc_$id" })

        if ($pcFbx.Count -eq 0) {
            Write-Host "  No character FBX found to convert" -ForegroundColor Red
        } else {
            # 候选转换源：nk(裸模)优先、其余按大小排。有的角色 nk_bs 是空层级
            # (无网格无骨架，如 g02)，转换失败时自动换下一个候选
            $nkFbx   = @($pcFbx | Where-Object { $_.Name -match "nk_bs|nk_model|_nk\." } | Sort-Object Length -Descending)
            $restFbx = @($pcFbx | Where-Object { $_.FullName -notin $nkFbx.FullName } | Sort-Object Length -Descending)
            $candidates = @(@($nkFbx) + @($restFbx) | Select-Object -First 3)

            foreach ($fmt in $regularFormats) {
                $convertDir = Join-Path $outDir $fmt
                New-Item -ItemType Directory -Force $convertDir | Out-Null

                if ($fmt -eq 'glb') {
                    Write-Host ("  -> GLB via Blender...") -ForegroundColor White
                }
                elseif ($fmt -eq 'xps') {
                    Write-Host ("  -> XPS via Blender + XNALaraMesh...") -ForegroundColor White
                }
                elseif ($fmt -eq 'pmx') {
                    Write-Host ("  -> PMX via Blender + mmd_tools...") -ForegroundColor White
                }

                $done = $false
                foreach ($src in $candidates) {
                    Write-Host ("    Source: " + $src.Name + " (" + [math]::Round($src.Length/1MB,2) + " MB)")

                    # Use cmd /c to isolate Blender stderr from PowerShell ErrorAction
                    $blenderCmd = ('"{0}" --background --python "{1}" -- "{2}" "{3}" {4} 2>&1' -f $BlenderExe, $convertPy, $src.FullName, $convertDir, $fmt)
                    cmd /c $blenderCmd |
                        Select-String '\[convert\]' | ForEach-Object { Write-Host ("    " + $_.Line) -ForegroundColor DarkGray }

                    $converted = Get-ChildItem $convertDir -File -ErrorAction SilentlyContinue
                    if ($converted) {
                        foreach ($cf in $converted) {
                            Write-Host ("    " + [math]::Round($cf.Length/1MB,3) + " MB  " + $cf.Name) -ForegroundColor Green
                        }
                        $done = $true
                        break
                    }
                    Write-Host ("    " + $src.Name + " produced no output, trying next candidate...") -ForegroundColor Yellow
                }
                if (-not $done) {
                    Write-Host ("    No output for $fmt (check Blender logs)") -ForegroundColor Red
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
    foreach ($fmt in $regularFormats) {
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
