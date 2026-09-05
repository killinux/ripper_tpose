<#
.SYNOPSIS
  Batch-materialize extracted Rise of Eros characters into .blend + preview PNG.

.DESCRIPTION
  For every character directory produced by extract_character.ps1 this picks the
  best model FBX, rebuilds materials with the ROE add-on, packs the textures into
  a .blend and renders one composite preview image (3/4 + front + head) beside it.

  Outputs land in <SourceRoot>\<id>\blend\, so each character keeps its own
  models, textures and previews together.  Characters whose bundles ship no
  standalone mesh (bare-only event NPCs) are reported as SKIP, not failures.

.EXAMPLE
  .\export_character_models.ps1 -List

.EXAMPLE
  .\export_character_models.ps1 -Only m02,g11

.EXAMPLE
  .\export_character_models.ps1                       # everything, skip existing

.EXAMPLE
  .\export_character_models.ps1 -Force -Format blend,glb
  .\export_character_models.ps1 -Format xps -NoPreview   # add XPS beside existing blends
#>
[CmdletBinding()]
param(
    [string]$SourceRoot = "D:\roe_exports",
    [string]$BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [string[]]$Only,
    [string[]]$Format,
    # Shard several runs across processes by giving each its own manifest;
    # the default single-file manifest is not safe for concurrent writers.
    [string]$ManifestPath,
    [switch]$IncludeOutfits = $true,
    [switch]$NoPreview,
    [switch]$List,
    [switch]$ValidateOnly,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$workerPy = Join-Path $scriptDir 'export_character_model_blender.py'
$addonPy = Join-Path $scriptDir 'roe_xps_addon.py'

foreach ($required in @($SourceRoot, $workerPy, $addonPy)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path not found: $required"
    }
}
if (-not $List -and -not (Test-Path -LiteralPath $BlenderExe)) {
    throw "Blender not found: $BlenderExe"
}

$formats = @()
if ($Format) {
    foreach ($entry in $Format) {
        $formats += $entry -split '[,;]' | ForEach-Object { $_.Trim().ToLowerInvariant() } |
            Where-Object { $_ }
    }
}
if (-not $formats) { $formats = @('blend') }
$formats = @($formats | Select-Object -Unique)
$invalid = @($formats | Where-Object { $_ -notin @('blend', 'glb', 'xps', 'pmx') })
if ($invalid) { throw "Unknown format(s): $($invalid -join ', '). Valid: blend, glb, xps, pmx" }

function Get-FbxCandidates {
    param([string]$Directory, [string]$Id)
    # Preference order mirrors what the bundles actually ship: the dressed HD
    # model, then the LD stand-in, then a bare/prefab body.  Duplicated names
    # (same model in two bundles) are resolved by size.  All matches are kept in
    # order so the worker can skip a rig-only file and try the next one.
    $all = @(Get-ChildItem -LiteralPath $Directory -Recurse -Filter '*.fbx' -File `
        -ErrorAction SilentlyContinue)
    $candidates = @()
    foreach ($pattern in @("pc_${Id}_hd.fbx", "pc_${Id}_ld.fbx", "pc_${Id}_nk.fbx",
                           "Prefab_pc_${Id}_nk_model.fbx", "pc_${Id}_nk_bs.fbx")) {
        $hit = @($all | Where-Object { $_.Name -eq $pattern } |
            Sort-Object Length -Descending | Select-Object -First 1)
        if ($hit) { $candidates += $hit[0] }
    }
    return $candidates
}

function Get-OutfitFbx {
    param([string]$Directory, [string]$Id)
    @(Get-ChildItem -LiteralPath $Directory -Recurse -File `
        -Filter "pc_${Id}_outfit*_hd.fbx" -ErrorAction SilentlyContinue |
        Group-Object Name | ForEach-Object {
            $_.Group | Sort-Object Length -Descending | Select-Object -First 1
        } | Sort-Object Name)
}

$entries = @()
$skipped = @()
foreach ($dir in @(Get-ChildItem -LiteralPath $SourceRoot -Directory |
        Where-Object { $_.Name -match '^[a-z]\d+$' } | Sort-Object Name)) {
    $id = $dir.Name
    $textureDir = Join-Path $dir.FullName '_textures'
    if (-not (Test-Path -LiteralPath $textureDir)) { $textureDir = $dir.FullName }
    $candidates = @(Get-FbxCandidates $dir.FullName $id)
    if (-not $candidates) {
        $skipped += [pscustomobject]@{
            model = $id; status = 'NOMESH'
            reason = 'no standalone character mesh in this character''s bundles'
        }
        continue
    }
    $best = $candidates[0]
    $entries += [pscustomobject]@{
        Key = $id; Id = $id; Fbx = $best; Candidates = $candidates
        TextureDir = $textureDir
        OutputDir = (Join-Path $dir.FullName 'blend')
    }
    if ($IncludeOutfits) {
        foreach ($outfit in Get-OutfitFbx $dir.FullName $id) {
            if ($outfit.FullName -eq $best.FullName) { continue }
            $suffix = [regex]::Match($outfit.BaseName, 'outfit\d+').Value
            $entries += [pscustomobject]@{
                Key = $id + '_' + $suffix; Id = $id; Fbx = $outfit
                Candidates = @($outfit)
                TextureDir = $textureDir
                OutputDir = (Join-Path $dir.FullName 'blend')
            }
        }
    }
}

if ($List) {
    Write-Host ("Materializable character models: " + $entries.Count) -ForegroundColor Cyan
    $entries | ForEach-Object {
        [pscustomobject]@{
            Key = $_.Key
            Source = $_.Fbx.Name
            SizeMB = [math]::Round($_.Fbx.Length / 1MB, 2)
            Output = $_.OutputDir
        }
    } | Format-Table -AutoSize
    if ($skipped) {
        Write-Host ("No standalone mesh (skipped): " + $skipped.Count) -ForegroundColor DarkYellow
        ($skipped | ForEach-Object { $_.model }) -join ', '
    }
    Write-Host 'Formats: blend, glb, xps, pmx   Preview: <stem>_preview.png beside the .blend' `
        -ForegroundColor DarkGray
    exit 0
}

if ($Only) {
    $wanted = @($Only | ForEach-Object {
        $_ -split '[,;]' | ForEach-Object { $_.Trim().ToLowerInvariant() }
    } | Where-Object { $_ })
    $entries = @($entries | Where-Object { $_.Key -in $wanted -or $_.Id -in $wanted })
    $unknown = @($wanted | Where-Object { $_ -notin @($entries.Key) -and $_ -notin @($entries.Id) })
    if ($unknown) { throw "Unknown -Only key(s): $($unknown -join ', ')" }
}
if (-not $entries) { throw 'No character models selected.' }

$results = @()
$index = 0
foreach ($entry in $entries) {
    $index++
    $stem = $entry.Fbx.BaseName
    $outputBlend = Join-Path $entry.OutputDir ($stem + '.blend')
    $previewPath = Join-Path $entry.OutputDir ($stem + '_preview.png')
    # Mirror the worker's output layout so an unchanged model can be skipped.
    $expected = @{
        blend = $outputBlend
        glb = Join-Path (Join-Path $entry.OutputDir 'glb') ($stem + '.glb')
        xps = Join-Path (Join-Path (Join-Path $entry.OutputDir 'xps') $stem) ($stem + '.mesh')
        pmx = Join-Path (Join-Path (Join-Path $entry.OutputDir 'pmx') $stem) ($stem + '.pmx')
    }
    $missing = @($formats | Where-Object { -not (Test-Path -LiteralPath $expected[$_]) })
    Write-Host ""
    Write-Host ("[$index/" + $entries.Count + "] " + $entry.Key + ': ' + $entry.Fbx.Name) `
        -ForegroundColor Cyan

    if (-not $Force -and -not $ValidateOnly -and -not $missing -and
            ($NoPreview -or (Test-Path -LiteralPath $previewPath))) {
        Write-Host '  exists, skipped (use -Force)' -ForegroundColor Yellow
        # Record which outputs exist so the manifest merge can pick up a
        # format produced by an earlier run (e.g. a single-model test).
        $present = [ordered]@{}
        foreach ($fmt in @('blend', 'xps', 'glb', 'pmx')) {
            if (Test-Path -LiteralPath $expected[$fmt]) { $present[$fmt] = $expected[$fmt] }
        }
        $results += [pscustomobject]@{
            model = $entry.Key; status = 'SKIP'; source = $entry.Fbx.FullName
            output = $outputBlend; outputs = [pscustomobject]$present
            preview = $previewPath
            reason = 'output already exists (use -Force)'
        }
        continue
    }

    $mode = if ($ValidateOnly) { 'validate' } else { 'export' }
    $previewFlag = if ($NoPreview) { '0' } else { '1' }
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $candidateArgument = (@($entry.Candidates | ForEach-Object { $_.FullName }) -join ';')
    try {
        $blenderOutput = @(& $BlenderExe --background --python $workerPy -- `
            $candidateArgument $entry.TextureDir $outputBlend $addonPy $mode `
            ($formats -join ',') $previewFlag 2>&1)
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    # Blender interleaves stderr with stdout, so match the marker across the
    # joined output rather than trusting one line to arrive intact.
    $joined = ($blenderOutput | ForEach-Object { [string]$_ }) -join "`n"
    $match = [regex]::Match($joined, 'ROE_CHAR_EXPORT=(\{.*?\})\s*(?:\n|$)',
        [Text.RegularExpressions.RegexOptions]::Singleline)
    if (-not $match.Success) {
        $tail = ($blenderOutput | Select-Object -Last 15) -join [Environment]::NewLine
        $results += [pscustomobject]@{
            model = $entry.Key; status = 'FAIL'; source = $entry.Fbx.FullName
            error = 'Blender produced no result marker'; log = $tail
        }
        Write-Host '  FAIL: no result marker' -ForegroundColor Red
        continue
    }

    $payload = $match.Groups[1].Value | ConvertFrom-Json
    $results += [pscustomobject]@{
        model = $entry.Key
        status = $payload.status
        source = $entry.Fbx.FullName
        output = $payload.output
        outputs = $payload.outputs
        preview = $payload.preview
        meshes = $payload.meshes
        armatures = $payload.armatures
        materials = $payload.materials
        textures = $payload.textures
        packedImages = $payload.packed_images
        untexturedSlots = $payload.untextured_slots
        recoveredSlots = $payload.recovered_slots
        headSlots = $payload.head_slots
        headFacePolygons = $payload.head_face_polygons
        fusedHeadEyes = $payload.fused_head_eyes
        familyMismatches = $payload.family_mismatches
        diagnostic = $payload.diagnostic
        error = $payload.error
        traceback = $payload.traceback
    }
    if ($payload.status -eq 'NOMESH') {
        Write-Host ("  NOMESH: rig-only prefab(s), no geometry -> " +
            (@($payload.empty_candidates) -join ', ')) -ForegroundColor DarkYellow
    } elseif ($payload.status -eq 'PASS') {
        $textureCount = @($payload.textures).Count
        Write-Host ("  PASS: " + $payload.meshes + " meshes / " + $payload.materials +
            " slots / " + $textureCount + " textures") -ForegroundColor Green
        # Keep every string literal in this file ASCII: PowerShell 5.1 reads a
        # BOM-less .ps1 with the OEM code page, and mangled multi-byte text
        # inside quotes breaks the parser (comments survive it, strings do not).
        # Only 'face' and 'eye' are always-wrong when empty.  An empty 'brow' is
        # normal for the i family (brows are baked into the face atlas) and an
        # empty 'lash' is normal for a character whose eyes are covered, so
        # those stay in headSlots for inspection rather than raising an alarm.
        foreach ($critical in @('face', 'eye')) {
            if ($payload.head_slots -and
                    ($payload.head_slots.PSObject.Properties.Name -contains $critical) -and
                    $payload.head_slots.$critical -eq 0) {
                Write-Host ("    !! head '" + $critical + "' slot has 0 polygons" +
                    " - check head classification") -ForegroundColor Red
            }
        }
        if ($payload.fused_head_eyes) {
            Write-Host ("    fused-head eyes: " +
                ($payload.fused_head_eyes -join '; ')) -ForegroundColor DarkCyan
        }
        if ($payload.recovered_slots) {
            Write-Host ("    recovered: " + ($payload.recovered_slots -join '; ')) `
                -ForegroundColor DarkCyan
        }
        if ($payload.untextured_slots) {
            Write-Host ("    untextured: " + ($payload.untextured_slots -join '; ')) `
                -ForegroundColor DarkYellow
        }
        if ($payload.family_mismatches) {
            Write-Host ("    foreign-family textures: " +
                ($payload.family_mismatches -join ', ')) -ForegroundColor DarkYellow
        }
        if (-not $ValidateOnly) {
            if ($payload.outputs.blend) {
                Write-Host ("    BLEND: " + $payload.outputs.blend) -ForegroundColor DarkGreen
            }
            if ($payload.outputs.xps) {
                Write-Host ("    XPS: " + $payload.outputs.xps) -ForegroundColor DarkGreen
            }
            if ($payload.outputs.glb) {
                Write-Host ("    GLB: " + $payload.outputs.glb) -ForegroundColor DarkGreen
            }
            if ($payload.outputs.pmx) {
                Write-Host ("    PMX: " + $payload.outputs.pmx) -ForegroundColor DarkGreen
            }
            if ($payload.preview) {
                Write-Host ("    PREVIEW: " + $payload.preview) -ForegroundColor DarkGreen
            }
        }
    } else {
        Write-Host ("  FAIL: " + $payload.error) -ForegroundColor Red
    }
}

if ($ManifestPath) {
    $manifestPath = $ManifestPath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $manifestPath) | Out-Null
} else {
    $manifestName = if ($ValidateOnly) {
        'character_models_manifest.validate.json'
    } else {
        'character_models_manifest.json'
    }
    $manifestPath = Join-Path $SourceRoot $manifestName
}
$manifestResults = @($results) + @($skipped)
$manifestFormats = $formats
if (-not $ValidateOnly -and (Test-Path -LiteralPath $manifestPath)) {
    # Merge with the previous manifest: a run that only adds a format (or that
    # skipped unchanged models) must not erase the blend/preview details, and
    # the gallery reads those from here.
    try {
        $previous = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 |
            ConvertFrom-Json
        $previousByModel = @{}
        foreach ($item in @($previous.results)) { $previousByModel[$item.model] = $item }
        $merged = @()
        foreach ($item in @($results)) {
            $old = $previousByModel[$item.model]
            if ($old -and $item.status -eq 'SKIP' -and $old.status -eq 'PASS') {
                # Keep the previous PASS details, but adopt any output that is
                # on disk now and was not in the manifest yet.
                $outputs = [ordered]@{}
                foreach ($source in @($old.outputs, $item.outputs)) {
                    if ($source) {
                        foreach ($prop in $source.PSObject.Properties) {
                            $outputs[$prop.Name] = $prop.Value
                        }
                    }
                }
                $old.outputs = [pscustomobject]$outputs
                $merged += $old
                continue
            }
            if ($old -and $item.status -eq 'PASS' -and $old.status -eq 'PASS') {
                if (-not $item.preview -and $old.preview) { $item.preview = $old.preview }
                $outputs = [ordered]@{}
                foreach ($source in @($old.outputs, $item.outputs)) {
                    if ($source) {
                        foreach ($prop in $source.PSObject.Properties) {
                            $outputs[$prop.Name] = $prop.Value
                        }
                    }
                }
                $item.outputs = [pscustomobject]$outputs
                if (-not $item.output -and $outputs.blend) { $item.output = $outputs.blend }
            }
            $merged += $item
        }
        $updated = @($merged | ForEach-Object { $_.model }) + @($skipped | ForEach-Object { $_.model })
        $manifestResults = @(
            @($previous.results | Where-Object { $_.model -notin $updated }) +
            $merged + @($skipped)
        ) | Sort-Object model
        $manifestFormats = @(@($previous.formats) + $formats |
            Where-Object { $_ } | Select-Object -Unique)
    }
    catch {
        Write-Host ("  Existing manifest could not be merged: " + $_.Exception.Message) `
            -ForegroundColor Yellow
    }
}
$manifest = [pscustomobject]@{
    generatedAt = [DateTime]::Now.ToString('o')
    sourceRoot = [IO.Path]::GetFullPath($SourceRoot)
    validateOnly = [bool]$ValidateOnly
    formats = $manifestFormats
    preview = (-not $NoPreview)
    results = $manifestResults
}
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8),
    [Text.UTF8Encoding]::new($false))

$passed = @($results | Where-Object status -eq 'PASS').Count
$failed = @($results | Where-Object status -eq 'FAIL').Count
$skippedCount = @($results | Where-Object status -eq 'SKIP').Count
$noMesh = @($results | Where-Object status -eq 'NOMESH').Count + $skipped.Count
Write-Host ""
Write-Host ("Complete: PASS=$passed FAIL=$failed SKIP=$skippedCount NOMESH=$noMesh") `
    -ForegroundColor $(if ($failed) { 'Yellow' } else { 'Green' })
Write-Host ("Manifest: " + $manifestPath)
if ($failed) { throw "$failed character model export(s) failed; see manifest." }
