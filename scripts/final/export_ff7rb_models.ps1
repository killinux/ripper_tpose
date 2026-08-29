<#
.SYNOPSIS
  Batch-export materialized FF7 Rebirth player models from FModel output.

.DESCRIPTION
  Scans the FModel export tree for Player variants (PC????_*), imports each
  ActorX model headlessly in Blender 3.6 via ff7rebirth_tools.py, matches the
  FModel material JSONs and textures, and exports Blend (packed images), FBX,
  or GLB.  Variants without a Model directory (material/texture-only packs)
  are recorded as NO_MODEL and skipped.

  Upstream extraction stays manual: FModel has no CLI, so variants that were
  never saved from FModel cannot be auto-extracted here.  The pending list
  lives in docs/ff7rebirth-player-export-inventory.md.

.EXAMPLE
  .\export_ff7rb_models.ps1 -List

.EXAMPLE
  .\export_ff7rb_models.ps1 -ValidateOnly

.EXAMPLE
  .\export_ff7rb_models.ps1 -Only PC0002_00 -Format blend,fbx,glb -Force
#>
[CmdletBinding()]
param(
    [string]$SourceRoot = "D:\ff7rebirth_exports\fmodel_exports",
    [string]$PlayerSubPath = "End\Content\Character\Player",
    [string]$OutputDir = "D:\ff7rebirth_exports\materialized",
    [string]$BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [string[]]$Only,
    [string[]]$Format,
    [switch]$List,
    [switch]$ValidateOnly,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$workerPy = Join-Path $scriptDir 'export_ff7rb_model_blender.py'
$toolsPy = Join-Path $scriptDir 'ff7rebirth_tools.py'
$playerRoot = Join-Path $SourceRoot $PlayerSubPath

foreach ($required in @($playerRoot, $BlenderExe, $workerPy, $toolsPy)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path not found: $required"
    }
}

function Get-VariantModel {
    param([string]$VariantDir)
    $modelDir = Join-Path $VariantDir 'Model'
    if (-not (Test-Path -LiteralPath $modelDir)) {
        return $null
    }
    # Prefer .pskx over .psk, then the largest file (mirrors model_score).
    $candidates = @(Get-ChildItem -LiteralPath $modelDir -Recurse -File |
        Where-Object { $_.Extension -in '.pskx', '.psk' } |
        Sort-Object @{ Expression = { $_.Extension -eq '.pskx' }; Descending = $true },
                    @{ Expression = 'Length'; Descending = $true })
    if ($candidates) {
        return $candidates[0]
    }
    return $null
}

$variants = @(Get-ChildItem -LiteralPath $playerRoot -Directory |
    Where-Object { $_.Name -match '^PC\d{4}_' } |
    Sort-Object Name |
    ForEach-Object {
        $model = Get-VariantModel $_.FullName
        [pscustomobject]@{
            Name     = $_.Name
            Root     = $_.FullName
            Model    = $model
            HasModel = [bool]$model
        }
    })
if (-not $variants) {
    throw "No PC????_* variant directories found under: $playerRoot"
}
$canonicalNames = @($variants.Name)

if ($List) {
    Write-Host ("Player variants on disk: " + $variants.Count) -ForegroundColor Cyan
    $variants | ForEach-Object {
        [pscustomobject]@{
            Variant = $_.Name
            Status  = if ($_.HasModel) { 'MODEL' } else { 'NO_MODEL' }
            Model   = if ($_.Model) { $_.Model.Name } else { '' }
        }
    } | Format-Table -AutoSize
    Write-Host 'Formats: blend (default), fbx, glb.  NO_MODEL = material/texture-only variant.' -ForegroundColor DarkGray
    Write-Host 'Variants never saved from FModel are NOT listed here; see docs/ff7rebirth-player-export-inventory.md.' -ForegroundColor DarkGray
    exit 0
}

$formats = @()
if ($Format) {
    foreach ($entry in $Format) {
        $formats += $entry -split '[,;]' | ForEach-Object {
            $_.Trim().ToLowerInvariant()
        } | Where-Object { $_ }
    }
}
if (-not $formats) {
    $formats = @('blend')
}
$formats = @($formats | Select-Object -Unique)
$validFormats = @('blend', 'fbx', 'glb')
$unknownFormats = @($formats | Where-Object { $_ -notin $validFormats })
if ($unknownFormats) {
    throw "Unknown format(s): $($unknownFormats -join ', '). Valid: $($validFormats -join ', ') (XPS/PMX are not validated for FF7RB yet)"
}

if ($Only) {
    $wanted = @($Only | ForEach-Object {
        $_ -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    })
    $selected = @()
    $unmatched = @()
    foreach ($token in $wanted) {
        # Accept the full variant name or a PC-number prefix (PC0002_00).
        $hits = @($variants | Where-Object {
            $_.Name -eq $token -or $_.Name -like ($token + '_*') -or $_.Name -like ($token + '*')
        })
        if ($hits) {
            $selected += $hits
        } else {
            $unmatched += $token
        }
    }
    if ($unmatched) {
        throw "Unknown -Only variant(s): $($unmatched -join ', ') (use -List)"
    }
    $variants = @($selected | Sort-Object Name -Unique)
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$results = @()

foreach ($variant in $variants) {
    Write-Host ""
    Write-Host ("[" + $variant.Name + "]") -ForegroundColor Cyan
    if (-not $variant.HasModel) {
        # Material/texture-only packs (wet skin, tears) or FModel ActorX
        # conversion failures (PC7002_00).  Not an error for full runs.
        $results += [pscustomobject]@{
            variant = $variant.Name; status = 'NO_MODEL'
            reason = 'no ActorX model in Model\; save it from FModel first (see ff7rebirth-player-export-inventory.md)'
        }
        Write-Host '  NO_MODEL: material/texture-only variant, skipped' -ForegroundColor DarkYellow
        continue
    }

    $outputBlend = Join-Path $OutputDir ($variant.Name + '.blend')
    $outputPaths = [ordered]@{}
    foreach ($fmt in $formats) {
        switch ($fmt) {
            'blend' { $outputPaths[$fmt] = $outputBlend }
            'fbx' { $outputPaths[$fmt] = Join-Path (Join-Path $OutputDir 'fbx') ($variant.Name + '.fbx') }
            'glb' { $outputPaths[$fmt] = Join-Path (Join-Path $OutputDir 'glb') ($variant.Name + '.glb') }
        }
    }
    $existingOutputs = @($outputPaths.Values | Where-Object {
        Test-Path -LiteralPath $_
    })
    if ($existingOutputs.Count -eq $outputPaths.Count -and -not $Force -and
            -not $ValidateOnly) {
        Write-Host ("  All requested outputs exist, skipped: " +
            ($formats -join ', ')) -ForegroundColor Yellow
        $results += [pscustomobject]@{
            variant = $variant.Name; status = 'SKIP'
            source = $variant.Model.FullName
            outputs = [pscustomobject]$outputPaths
            reason = 'all requested outputs already exist (use -Force)'
        }
        continue
    }

    $mode = if ($ValidateOnly) { 'validate' } else { 'export' }
    Write-Host ("  Blender " + $mode + ': ' + $variant.Model.Name +
        $(if ($ValidateOnly) { '' } else { ' -> ' + ($formats -join ', ') })) `
        -ForegroundColor White
    # Blender writes Python tracebacks to stderr and may still exit 0; capture
    # both streams without letting Stop preference abort the batch.
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $blenderOutput = @(& $BlenderExe --background --python $workerPy -- `
            $variant.Model.FullName $variant.Root $outputBlend $toolsPy $mode `
            ($formats -join ',') 2>&1)
    }
    finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    $resultLine = $blenderOutput | Where-Object {
        $_ -is [string] -and $_.StartsWith('FF7RB_EXPORT=')
    } | Select-Object -Last 1
    if (-not $resultLine) {
        $message = ($blenderOutput | Select-Object -Last 20) -join [Environment]::NewLine
        $results += [pscustomobject]@{
            variant = $variant.Name; status = 'FAIL'
            source = $variant.Model.FullName
            error = 'Blender produced no result marker'; log = $message
        }
        Write-Host '  Blender produced no result marker' -ForegroundColor Red
        continue
    }

    $payload = $resultLine.Substring('FF7RB_EXPORT='.Length) | ConvertFrom-Json
    $results += [pscustomobject]@{
        variant = $variant.Name
        status = $payload.status
        source = $variant.Model.FullName
        output = $payload.output
        outputs = $payload.outputs
        formats = $payload.formats
        meshes = $payload.meshes
        armatures = $payload.armatures
        bones = $payload.bones
        vertices = $payload.vertices
        polygons = $payload.polygons
        materials = $payload.materials
        preparedMaterials = $payload.prepared_materials
        texturesFound = $payload.textures_found
        indexedTextures = $payload.indexed_textures
        missingBase = $payload.missing_base
        layeredEyes = $payload.layered_eyes
        repairedShading = $payload.repaired_shading
        simplified = $payload.simplified
        error = $payload.error
        traceback = $payload.traceback
    }
    if ($payload.status -eq 'PASS') {
        Write-Host ("  PASS: " + $payload.meshes + " meshes / " +
            $payload.materials + " materials / " + $payload.textures_found +
            " textures" +
            $(if ($payload.missing_base) {
                '; no base texture: ' + ($payload.missing_base -join ', ')
            } else { '' })) -ForegroundColor Green
        if (-not $ValidateOnly -and $payload.outputs) {
            $payload.outputs.PSObject.Properties | ForEach-Object {
                Write-Host ("    " + $_.Name.ToUpperInvariant() + ': ' +
                    $_.Value) -ForegroundColor DarkGreen
            }
        }
    } else {
        Write-Host ("  FAIL: " + $payload.error) -ForegroundColor Red
    }
}

$manifestPath = Join-Path $OutputDir 'ff7rb_models_manifest.json'
if ($ValidateOnly) {
    # Validation results carry no output paths; merging them into the real
    # manifest would erase recorded export locations.  Standalone snapshot.
    $manifestPath = Join-Path $OutputDir 'ff7rb_models_manifest.validate.json'
}
$manifestResults = @($results)
$manifestFormats = @($formats)
if (-not $ValidateOnly -and $Only -and (Test-Path -LiteralPath $manifestPath)) {
    try {
        $previousManifest = Get-Content -LiteralPath $manifestPath -Raw `
            -Encoding UTF8 | ConvertFrom-Json
        $updatedKeys = @($results | ForEach-Object { $_.variant })
        $manifestResults = @(
            @($previousManifest.results | Where-Object {
                $_.variant -notin $updatedKeys
            }) + @($results)
        )
        $manifestFormats = @(
            @($previousManifest.formats) + @($formats) |
                Where-Object { $_ } | Select-Object -Unique
        )
        $variantOrder = @{}
        for ($index = 0; $index -lt $canonicalNames.Count; $index++) {
            $variantOrder[$canonicalNames[$index]] = $index
        }
        $manifestResults = @($manifestResults | Sort-Object {
            if ($variantOrder.ContainsKey($_.variant)) {
                $variantOrder[$_.variant]
            } else {
                [int]::MaxValue
            }
        })
    }
    catch {
        Write-Host ("  Existing manifest could not be merged: " +
            $_.Exception.Message) -ForegroundColor Yellow
    }
}
$manifest = [pscustomobject]@{
    generatedAt = [DateTime]::Now.ToString('o')
    sourceRoot = [IO.Path]::GetFullPath($playerRoot)
    outputDir = [IO.Path]::GetFullPath($OutputDir)
    validateOnly = [bool]$ValidateOnly
    formats = $manifestFormats
    requestedFormats = $formats
    materialScope = 'FModel material JSONs: base/eye layering, DirectX normals, ORM, opacity; portable formats bake eyes and pre-flip normals'
    results = $manifestResults
}
[IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 8),
    [Text.UTF8Encoding]::new($false))

$passed = @($results | Where-Object status -eq 'PASS').Count
$failed = @($results | Where-Object status -eq 'FAIL').Count
$skipped = @($results | Where-Object status -eq 'SKIP').Count
$noModel = @($results | Where-Object status -eq 'NO_MODEL').Count
Write-Host ""
Write-Host ("Complete: PASS=$passed FAIL=$failed SKIP=$skipped NO_MODEL=$noModel") `
    -ForegroundColor $(if ($failed) { 'Yellow' } else { 'Green' })
Write-Host ("Manifest: " + $manifestPath)
if ($failed) {
    throw "$failed FF7RB model export(s) failed; see manifest."
}
