<#
.SYNOPSIS
  Batch-export the canonical Rise of Eros nude base models with materials.

.DESCRIPTION
  Exports a00, the A-M ``01`` nude bases, and the optional E/F/G ``fm``
  variants. Blend files pack their referenced images; FBX/GLB embed textures,
  while XPS/PMX receive portable PNG sidecars and a baked eye texture.

  The script uses roe_xps_addon.py for the same face/eye/lash/brow and body
  material reconstruction as the interactive Blender workflow.  It collects
  only same-family textures and fails rather than silently using another
  character family's face.

.EXAMPLE
  .\export_nude_models.ps1

.EXAMPLE
  .\export_nude_models.ps1 -Only a01,b01,l01 -ValidateOnly

.EXAMPLE
  .\export_nude_models.ps1 -OutputDir E:\roe_nude_materials -Force

.EXAMPLE
  .\export_nude_models.ps1 -Only b01 -Format blend,fbx,xps,glb -Force

.EXAMPLE
  .\export_nude_models.ps1 -List
#>
[CmdletBinding()]
param(
    [string]$SourceRoot = "D:\roe_exports",
    [string]$OutputDir = "D:\roe_exports\nude_materials",
    [string]$GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros",
    [string]$CacheRoot = "$env:USERPROFILE\AppData\LocalLow\Pinkcore\Rise of Eros\AssetBundles",
    [string]$BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [string]$CliExe = "E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe",
    [string[]]$Only,
    [string[]]$Format,
    [bool]$IncludeA00 = $true,
    [bool]$IncludeFm = $true,
    [switch]$List,
    [switch]$ValidateOnly,
    [switch]$Force,
    [switch]$KeepTemp
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$workerPy = Join-Path $scriptDir 'export_nude_model_blender.py'
$addonPy = Join-Path $scriptDir 'roe_xps_addon.py'
$installBundleRoot = Join-Path $GameRoot 'RiseOfEros_Data\StreamingAssets\AssetBundles'

function New-ModelEntry {
    param(
        [string]$Key,
        [string]$CharacterId,
        [string]$Family,
        [string[]]$FbxNames
    )
    [pscustomobject]@{
        Key         = $Key
        CharacterId = $CharacterId
        Family      = $Family
        FbxNames    = $FbxNames
    }
}

$models = @()
if ($IncludeA00) {
    $models += New-ModelEntry 'a00' 'a00' 'a' @(
        'pc_a00_nk.fbx', 'Prefab_pc_a00_nk_model.fbx')
}
foreach ($family in 'a','b','c','d','e','f','g','h','i','j','k','l','m') {
    $id = $family + '01'
    $models += New-ModelEntry $id $id $family @(
        "pc_${id}_nk_bs.fbx",
        "pc_${id}_nk.fbx",
        "Prefab_pc_${id}_nk_model.fbx"
    )
}
if ($IncludeFm) {
    foreach ($family in 'e','f','g') {
        $id = $family + '01'
        $models += New-ModelEntry ($id + '_fm') $id $family @(
            "pc_${id}_fm_nk_bs.fbx",
            "pc_${id}_fm_nk.fbx"
        )
    }
}
$canonicalModelKeys = @($models.Key)

if ($List) {
    Write-Host ("Materialized nude bases: " + $models.Count) -ForegroundColor Cyan
    $models | ForEach-Object {
        [pscustomobject]@{
            Id = 'nude:' + $_.Key
            Character = $_.CharacterId
            Family = $_.Family.ToUpperInvariant()
            Source = $_.FbxNames[0]
        }
    } | Format-Table -AutoSize
    Write-Host 'Formats: blend, fbx, xps, pmx, glb' -ForegroundColor DarkGray
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
$validFormats = @('blend', 'fbx', 'xps', 'pmx', 'glb')
$unknownFormats = @($formats | Where-Object { $_ -notin $validFormats })
if ($unknownFormats) {
    throw "Unknown format(s): $($unknownFormats -join ', '). Valid: $($validFormats -join ', ')"
}

foreach ($required in @($SourceRoot, $BlenderExe, $workerPy, $addonPy)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path not found: $required"
    }
}

if ($Only) {
    $wanted = @($Only | ForEach-Object {
        $_ -split '[,;]' | ForEach-Object {
            $_.Trim().ToLowerInvariant() -replace '^nude[:-]', ''
        }
    } | Where-Object { $_ })
    $models = @($models | Where-Object { $_.Key -in $wanted })
    $unknown = @($wanted | Where-Object { $_ -notin $models.Key })
    if ($unknown) {
        throw "Unknown -Only model key(s): $($unknown -join ', ')"
    }
}
if (-not $models) {
    throw 'No nude models selected.'
}

function Find-Fbx {
    param($Model)
    $characterDir = Join-Path $SourceRoot $Model.CharacterId
    if (-not (Test-Path -LiteralPath $characterDir)) {
        return $null
    }
    foreach ($name in $Model.FbxNames) {
        $hits = @(Get-ChildItem -LiteralPath $characterDir -Recurse -Filter $name -File |
            Sort-Object Length -Descending)
        if ($hits) {
            return $hits[0]
        }
    }
    return $null
}

function Add-TextureFile {
    param(
        [System.IO.FileInfo]$File,
        [string]$Destination,
        [hashtable]$Seen
    )
    $key = $File.Name.ToLowerInvariant()
    if ($Seen.ContainsKey($key)) {
        return
    }
    Copy-Item -LiteralPath $File.FullName -Destination (Join-Path $Destination $File.Name)
    $Seen[$key] = $File.FullName
}

function Add-RelevantTextures {
    param(
        [string]$SearchRoot,
        $Model,
        [string]$Destination,
        [hashtable]$Seen
    )
    if (-not (Test-Path -LiteralPath $SearchRoot)) {
        return
    }
    $familyPrefix = 'pc_' + $Model.Family + '_'
    $idPrefix = 'pc_' + $Model.CharacterId + '_'
    Get-ChildItem -LiteralPath $SearchRoot -Recurse -Filter '*.png' -File |
        Where-Object {
            $name = $_.Name.ToLowerInvariant()
            ($name.StartsWith($familyPrefix) -or $name.StartsWith($idPrefix)) -and
            ($name -match '_(?:albedo|abedo)')
        } |
        ForEach-Object { Add-TextureFile $_ $Destination $Seen }
}

function Find-CommonHeadTexture {
    param([string]$Family, [string]$RolePattern)
    $pattern = "pc_${Family}_${RolePattern}"
    $familyDirs = @(Get-ChildItem -LiteralPath $SourceRoot -Directory |
        Where-Object { $_.Name -match ('^' + [regex]::Escape($Family) + '\d+$') } |
        Sort-Object Name)
    foreach ($dir in $familyDirs) {
        $textureDir = Join-Path $dir.FullName '_textures'
        if (-not (Test-Path -LiteralPath $textureDir)) {
            continue
        }
        $hit = Get-ChildItem -LiteralPath $textureDir -Recurse -Filter '*.png' -File |
            Where-Object { $_.Name -like $pattern } | Select-Object -First 1
        if ($hit) {
            return $textureDir
        }
    }
    return $null
}

function Export-CommonHeadTextures {
    param([string]$Family, [string]$Destination)
    if (-not (Test-Path -LiteralPath $CliExe)) {
        return
    }
    $roots = @($installBundleRoot, $CacheRoot) |
        Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    $bundles = @($roots | ForEach-Object {
        Get-ChildItem -LiteralPath $_ -Recurse -Filter "chara_tex_bare_pc_${Family}_common*.ab" -File
    } | Sort-Object LastWriteTime -Descending)
    if (-not $bundles) {
        return
    }
    # A family can have both a current and a tutorial-only common head bundle.
    # Export all matching bundles into the isolated texture stage; identical
    # filenames are harmless and AssetStudio overwrites only within that stage.
    foreach ($bundle in $bundles) {
        $cliOutput = @(& $CliExe $bundle.FullName -m export -t tex2d `
            --image-format png -g none -o $Destination --log-level warning 2>&1)
        if ($cliOutput -match '\[Error\]') {
            Write-Host ("  Texture export warning: " + ($cliOutput -join ' ')) `
                -ForegroundColor Yellow
        }
    }
}

function Test-HeadTextureSet {
    param([string]$Directory, [string]$Family)
    $names = @(Get-ChildItem -LiteralPath $Directory -Filter '*.png' -File |
        ForEach-Object { $_.Name.ToLowerInvariant() })
    $hasFace = @($names | Where-Object {
        $_ -like "pc_${Family}_nk_face*albedo*.png" -or
        $_ -like "pc_${Family}_ld_face*albedo*.png"
    }).Count -gt 0
    $hasEye = @($names | Where-Object {
        $_ -like "pc_${Family}_nk_eye*albedo*.png" -or
        $_ -like "pc_${Family}_nk_eyes*albedo*.png" -or
        $_ -like "pc_${Family}_ld_eyes*albedo*.png"
    }).Count -gt 0
    [pscustomobject]@{ Face = $hasFace; Eye = $hasEye }
}

$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$runTemp = Join-Path $tempBase ('roe_nude_materials_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runTemp | Out-Null
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$results = @()

try {
    foreach ($model in $models) {
        Write-Host ""
        Write-Host ("[" + $model.Key + "] locating FBX and textures...") -ForegroundColor Cyan
        $fbx = Find-Fbx $model
        if (-not $fbx) {
            $results += [pscustomobject]@{
                model = $model.Key; status = 'FAIL'; error = 'FBX not found'
            }
            Write-Host '  FBX not found' -ForegroundColor Red
            continue
        }

        $textureStage = Join-Path $runTemp $model.Key
        New-Item -ItemType Directory -Path $textureStage | Out-Null
        $seen = @{}

        # The FBX sibling directory normally contains the body plus common head
        # Albedos.  Old b01/l01 exports only contain the body, so supplement it
        # from any newer same-family _textures directory.
        Add-RelevantTextures $fbx.DirectoryName $model $textureStage $seen
        $ownTextureDir = Join-Path (Join-Path $SourceRoot $model.CharacterId) '_textures'
        Add-RelevantTextures $ownTextureDir $model $textureStage $seen
        $commonRoot = Find-CommonHeadTexture $model.Family 'nk_face*Albedo*.png'
        if ($commonRoot) {
            Add-RelevantTextures $commonRoot $model $textureStage $seen
        }

        $headSet = Test-HeadTextureSet $textureStage $model.Family
        if (-not ($headSet.Face -and $headSet.Eye)) {
            Write-Host '  Shared head textures incomplete; reading common bundle...' `
                -ForegroundColor DarkYellow
            Export-CommonHeadTextures $model.Family $textureStage
            $headSet = Test-HeadTextureSet $textureStage $model.Family
        }

        # The .blend path is also the naming anchor used by the Blender worker;
        # non-Blender formats live in a same-name subdirectory per format.
        $outputBlend = Join-Path $OutputDir ($fbx.BaseName + '.blend')
        $outputPaths = [ordered]@{}
        foreach ($fmt in $formats) {
            switch ($fmt) {
                'blend' { $outputPaths[$fmt] = $outputBlend }
                'fbx' { $outputPaths[$fmt] = Join-Path (Join-Path $OutputDir 'fbx') ($fbx.BaseName + '.fbx') }
                'xps' { $outputPaths[$fmt] = Join-Path (Join-Path $OutputDir 'xps') ($fbx.BaseName + '.mesh') }
                'pmx' { $outputPaths[$fmt] = Join-Path (Join-Path $OutputDir 'pmx') ($fbx.BaseName + '.pmx') }
                'glb' { $outputPaths[$fmt] = Join-Path (Join-Path $OutputDir 'glb') ($fbx.BaseName + '.glb') }
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
                model = $model.Key; status = 'SKIP'; source = $fbx.FullName
                output = $outputPaths.Values | Select-Object -First 1
                outputs = [pscustomobject]$outputPaths
                reason = 'all requested outputs already exist (use -Force)'
            }
            continue
        }

        $mode = if ($ValidateOnly) { 'validate' } else { 'export' }
        Write-Host ("  Blender " + $mode + ': ' + $fbx.Name +
            $(if ($ValidateOnly) { '' } else { ' -> ' + ($formats -join ', ') })) `
            -ForegroundColor White
        # Blender writes Python tracebacks to stderr and may still return exit
        # code 0. Capture both streams without allowing PowerShell's global
        # Stop preference to abort the remaining batch entries.
        $previousErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $blenderOutput = @(& $BlenderExe --background --python $workerPy -- `
                $fbx.FullName $textureStage $outputBlend $addonPy $mode `
                ($formats -join ',') 2>&1)
        }
        finally {
            $ErrorActionPreference = $previousErrorPreference
        }
        $resultLine = $blenderOutput | Where-Object {
            $_ -is [string] -and $_.StartsWith('ROE_NUDE_EXPORT=')
        } | Select-Object -Last 1
        if (-not $resultLine) {
            $message = ($blenderOutput | Select-Object -Last 20) -join [Environment]::NewLine
            $results += [pscustomobject]@{
                model = $model.Key; status = 'FAIL'; source = $fbx.FullName
                error = 'Blender produced no result marker'; log = $message
            }
            Write-Host '  Blender produced no result marker' -ForegroundColor Red
            continue
        }

        $payload = $resultLine.Substring('ROE_NUDE_EXPORT='.Length) | ConvertFrom-Json
        $results += [pscustomobject]@{
            model = $model.Key
            status = $payload.status
            source = $fbx.FullName
            output = $payload.output
            outputs = $payload.outputs
            formats = $payload.formats
            meshes = $payload.meshes
            armatures = $payload.armatures
            materials = $payload.materials
            textures = $payload.textures
            diagnostic = $payload.diagnostic
            nudeSplit = $payload.nude_split
            transparentHelpers = $payload.transparent_helpers
            portableEye = $payload.portable_eye
            error = $payload.error
            traceback = $payload.traceback
        }
        if ($payload.status -eq 'PASS') {
            Write-Host ("  PASS: " + $payload.meshes + " meshes / " +
                $payload.materials + " materials / " + $payload.textures.Count +
                " textures") -ForegroundColor Green
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

    $manifestPath = Join-Path $OutputDir 'nude_models_manifest.json'
    if ($ValidateOnly) {
        # Validation results carry no output paths; merging them into the real
        # manifest would erase the recorded per-format export locations.  Each
        # validate run writes its own standalone snapshot instead.
        $manifestPath = Join-Path $OutputDir 'nude_models_manifest.validate.json'
    }
    $manifestResults = @($results)
    $manifestFormats = @($formats)
    if (-not $ValidateOnly -and $Only -and (Test-Path -LiteralPath $manifestPath)) {
        try {
            $previousManifest = Get-Content -LiteralPath $manifestPath -Raw `
                -Encoding UTF8 | ConvertFrom-Json
            $updatedKeys = @($results | ForEach-Object { $_.model })
            $manifestResults = @(
                @($previousManifest.results | Where-Object {
                    $_.model -notin $updatedKeys
                }) + @($results)
            )
            $manifestFormats = @(
                @($previousManifest.formats) + @($formats) |
                    Where-Object { $_ } | Select-Object -Unique
            )
            $modelOrder = @{}
            for ($index = 0; $index -lt $canonicalModelKeys.Count; $index++) {
                $modelOrder[$canonicalModelKeys[$index]] = $index
            }
            $manifestResults = @($manifestResults | Sort-Object {
                if ($modelOrder.ContainsKey($_.model)) {
                    $modelOrder[$_.model]
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
        sourceRoot = [IO.Path]::GetFullPath($SourceRoot)
        outputDir = [IO.Path]::GetFullPath($OutputDir)
        validateOnly = [bool]$ValidateOnly
        formats = $manifestFormats
        requestedFormats = $formats
        materialScope = 'Nude body + face + procedural eyes + lash/brow alpha; packed images'
        results = $manifestResults
    }
    [IO.File]::WriteAllText(
        $manifestPath,
        ($manifest | ConvertTo-Json -Depth 8),
        [Text.UTF8Encoding]::new($false))

    $passed = @($results | Where-Object status -eq 'PASS').Count
    $failed = @($results | Where-Object status -eq 'FAIL').Count
    $skipped = @($results | Where-Object status -eq 'SKIP').Count
    Write-Host ""
    Write-Host ("Complete: PASS=$passed FAIL=$failed SKIP=$skipped") `
        -ForegroundColor $(if ($failed) { 'Yellow' } else { 'Green' })
    Write-Host ("Manifest: " + $manifestPath)
    if ($failed) {
        throw "$failed nude model export(s) failed; see manifest."
    }
}
finally {
    if (-not $KeepTemp -and (Test-Path -LiteralPath $runTemp)) {
        $resolvedTemp = [IO.Path]::GetFullPath($runTemp)
        if (-not $resolvedTemp.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove non-temp path: $resolvedTemp"
        }
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
}
