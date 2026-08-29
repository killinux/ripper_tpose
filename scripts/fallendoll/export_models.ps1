<#
.SYNOPSIS
  Batch-materialize FModel-exported Operation LOVECRAFT: Fallen Doll models.

.DESCRIPTION
  Scans an FModel export tree for ActorX SkeletalMesh models (Model\*.psk /
  *.pskx) and materializes each headlessly in Blender 3.6, then exports packed
  Blend, FBX, or GLB.  Fallen Doll is UE4.26; the material pipeline (FModel
  material JSON matching, DirectX->OpenGL normals, ORM split, layered eyes,
  portable eye bake) is identical to FF7 Rebirth, so this reuses the verified
  export_ff7rb_model_blender.py worker and ff7rebirth_tools.py helpers.

  Upstream extraction is manual and needs the AES key configured in FModel
  (the pak index is encrypted; see prepare_fmodel.ps1).  This script never
  handles a key -- it starts from what FModel has already saved to disk.

.EXAMPLE
  .\export_models.ps1 -List

.EXAMPLE
  .\export_models.ps1                          # all discovered models -> blend

.EXAMPLE
  .\export_models.ps1 -Only DollBody -Format blend,fbx,glb -Force
#>
[CmdletBinding()]
param(
    [string]$SourceRoot = "D:\fallendoll_exports\fmodel_exports",
    [string]$OutputDir = "D:\fallendoll_exports\materialized",
    [string]$BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [string[]]$Only,
    [string[]]$Format,
    [switch]$List,
    [switch]$ValidateOnly,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$finalDir = Join-Path (Split-Path -Parent $scriptDir) 'final'
$workerPy = Join-Path $finalDir 'export_ff7rb_model_blender.py'
$toolsPy = Join-Path $finalDir 'ff7rebirth_tools.py'

foreach ($required in @($SourceRoot, $workerPy, $toolsPy)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path not found: $required"
    }
}

# A "model" is any directory containing a Model\ subfolder with an ActorX file.
# FModel keeps each SkeletalMesh under <AssetName>\Model\<AssetName>.pskx with
# sibling Material\ and Texture\ folders, the same shape as FF7 Rebirth.
function Get-VariantModel {
    param([string]$VariantDir)
    $modelDir = Join-Path $VariantDir 'Model'
    if (-not (Test-Path -LiteralPath $modelDir)) {
        return $null
    }
    $candidates = @(Get-ChildItem -LiteralPath $modelDir -Recurse -File |
        Where-Object { $_.Extension -in '.pskx', '.psk' } |
        Sort-Object @{ Expression = { $_.Extension -eq '.pskx' }; Descending = $true },
                    @{ Expression = 'Length'; Descending = $true })
    if ($candidates) { return $candidates[0] }
    return $null
}

$variants = @(Get-ChildItem -LiteralPath $SourceRoot -Directory -Recurse |
    ForEach-Object {
        $model = Get-VariantModel $_.FullName
        if ($model) {
            [pscustomobject]@{
                Name  = $_.Name
                Root  = $_.FullName
                Model = $model
            }
        }
    } | Sort-Object Name -Unique)

if ($List) {
    if (-not $variants) {
        Write-Host "No models found under: $SourceRoot" -ForegroundColor Yellow
        Write-Host "Export SkeletalMesh models from FModel first (see prepare_fmodel.ps1)." -ForegroundColor DarkGray
        exit 0
    }
    Write-Host ("Fallen Doll models on disk: " + $variants.Count) -ForegroundColor Cyan
    $variants | ForEach-Object {
        [pscustomobject]@{ Model = $_.Name; File = $_.Model.Name; Dir = $_.Root }
    } | Format-Table -AutoSize
    Write-Host 'Formats: blend (default), fbx, glb.  Materials use the generic UE4.26 (FF7RB) pipeline.' -ForegroundColor DarkGray
    exit 0
}

if (-not $variants) {
    throw "No ActorX models found under $SourceRoot. Export from FModel first (prepare_fmodel.ps1)."
}
$canonicalNames = @($variants.Name)

$formats = @()
if ($Format) {
    foreach ($entry in $Format) {
        $formats += $entry -split '[,;]' | ForEach-Object {
            $_.Trim().ToLowerInvariant()
        } | Where-Object { $_ }
    }
}
if (-not $formats) { $formats = @('blend') }
$formats = @($formats | Select-Object -Unique)
$validFormats = @('blend', 'fbx', 'glb')
$unknownFormats = @($formats | Where-Object { $_ -notin $validFormats })
if ($unknownFormats) {
    throw "Unknown format(s): $($unknownFormats -join ', '). Valid: $($validFormats -join ', ')"
}

if ($Only) {
    $wanted = @($Only | ForEach-Object {
        $_ -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    })
    $selected = @()
    $unmatched = @()
    foreach ($token in $wanted) {
        $hits = @($variants | Where-Object { $_.Name -eq $token -or $_.Name -like ('*' + $token + '*') })
        if ($hits) { $selected += $hits } else { $unmatched += $token }
    }
    if ($unmatched) {
        throw "Unknown -Only model(s): $($unmatched -join ', ') (use -List)"
    }
    $variants = @($selected | Sort-Object Name -Unique)
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$results = @()

foreach ($variant in $variants) {
    Write-Host ""
    Write-Host ("[" + $variant.Name + "]") -ForegroundColor Cyan
    $outputBlend = Join-Path $OutputDir ($variant.Name + '.blend')
    $outputPaths = [ordered]@{}
    foreach ($fmt in $formats) {
        switch ($fmt) {
            'blend' { $outputPaths[$fmt] = $outputBlend }
            'fbx' { $outputPaths[$fmt] = Join-Path (Join-Path $OutputDir 'fbx') ($variant.Name + '.fbx') }
            'glb' { $outputPaths[$fmt] = Join-Path (Join-Path $OutputDir 'glb') ($variant.Name + '.glb') }
        }
    }
    $existingOutputs = @($outputPaths.Values | Where-Object { Test-Path -LiteralPath $_ })
    if ($existingOutputs.Count -eq $outputPaths.Count -and -not $Force -and -not $ValidateOnly) {
        Write-Host ("  All requested outputs exist, skipped: " + ($formats -join ', ')) -ForegroundColor Yellow
        $results += [pscustomobject]@{
            variant = $variant.Name; status = 'SKIP'; source = $variant.Model.FullName
            outputs = [pscustomobject]$outputPaths
            reason = 'all requested outputs already exist (use -Force)'
        }
        continue
    }

    $mode = if ($ValidateOnly) { 'validate' } else { 'export' }
    Write-Host ("  Blender " + $mode + ': ' + $variant.Model.Name +
        $(if ($ValidateOnly) { '' } else { ' -> ' + ($formats -join ', ') })) -ForegroundColor White
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
            variant = $variant.Name; status = 'FAIL'; source = $variant.Model.FullName
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
        bones = $payload.bones
        vertices = $payload.vertices
        polygons = $payload.polygons
        materials = $payload.materials
        preparedMaterials = $payload.prepared_materials
        texturesFound = $payload.textures_found
        indexedTextures = $payload.indexed_textures
        missingBase = $payload.missing_base
        layeredEyes = $payload.layered_eyes
        error = $payload.error
        traceback = $payload.traceback
    }
    if ($payload.status -eq 'PASS') {
        Write-Host ("  PASS: " + $payload.meshes + " meshes / " + $payload.materials +
            " materials / " + $payload.textures_found + " textures" +
            $(if ($payload.missing_base) { '; no base texture: ' + ($payload.missing_base -join ', ') } else { '' })) `
            -ForegroundColor Green
        if (-not $ValidateOnly -and $payload.outputs) {
            $payload.outputs.PSObject.Properties | ForEach-Object {
                Write-Host ("    " + $_.Name.ToUpperInvariant() + ': ' + $_.Value) -ForegroundColor DarkGreen
            }
        }
    } else {
        Write-Host ("  FAIL: " + $payload.error) -ForegroundColor Red
    }
}

$manifestPath = Join-Path $OutputDir 'fallendoll_models_manifest.json'
if ($ValidateOnly) {
    $manifestPath = Join-Path $OutputDir 'fallendoll_models_manifest.validate.json'
}
$manifestResults = @($results)
$manifestFormats = @($formats)
if (-not $ValidateOnly -and $Only -and (Test-Path -LiteralPath $manifestPath)) {
    try {
        $previousManifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $updatedKeys = @($results | ForEach-Object { $_.variant })
        $manifestResults = @(
            @($previousManifest.results | Where-Object { $_.variant -notin $updatedKeys }) + @($results)
        )
        $manifestFormats = @(@($previousManifest.formats) + @($formats) | Where-Object { $_ } | Select-Object -Unique)
        $variantOrder = @{}
        for ($index = 0; $index -lt $canonicalNames.Count; $index++) {
            $variantOrder[$canonicalNames[$index]] = $index
        }
        $manifestResults = @($manifestResults | Sort-Object {
            if ($variantOrder.ContainsKey($_.variant)) { $variantOrder[$_.variant] } else { [int]::MaxValue }
        })
    }
    catch {
        Write-Host ("  Existing manifest could not be merged: " + $_.Exception.Message) -ForegroundColor Yellow
    }
}
$manifest = [pscustomobject]@{
    generatedAt = [DateTime]::Now.ToString('o')
    sourceRoot = [IO.Path]::GetFullPath($SourceRoot)
    outputDir = [IO.Path]::GetFullPath($OutputDir)
    validateOnly = [bool]$ValidateOnly
    formats = $manifestFormats
    requestedFormats = $formats
    materialScope = 'Generic UE4.26 (FF7RB) pipeline: FModel material JSONs, DirectX normals, ORM, opacity, layered eyes; portable formats bake eyes and pre-flip normals'
    results = $manifestResults
}
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))

$passed = @($results | Where-Object status -eq 'PASS').Count
$failed = @($results | Where-Object status -eq 'FAIL').Count
$skipped = @($results | Where-Object status -eq 'SKIP').Count
Write-Host ""
Write-Host ("Complete: PASS=$passed FAIL=$failed SKIP=$skipped") -ForegroundColor $(if ($failed) { 'Yellow' } else { 'Green' })
Write-Host ("Manifest: " + $manifestPath)
if ($failed) {
    throw "$failed Fallen Doll model export(s) failed; see manifest."
}
