<#
.SYNOPSIS
  List PRISM character-candidate G1M models and convert chosen ones on demand.

.DESCRIPTION
  ROE-style front end over export_model.py + gust_stuff + Blender:

    -List shows all 71 character candidates (skeleton >= 50 joints) from the
    probed inventory, with internal names where the hash mapping proved one,
    plus whether the model is already converted locally.

    Passing indices / 0xKTIDs / internal names converts each target:
    FDATA -> .g1m -> basic glTF (geometry + skeleton + weights, no textures)
    -> .blend with front/back preview PNGs.  Nothing is batch-converted;
    you pick entries from -List as you need them.

  Character-profile complete exports (BODY+FACE+HAIR with textures) remain
  .\export_character.ps1 — this script is for browsing raw candidates.

.EXAMPLE
  .\export_model.ps1 -List
.EXAMPLE
  .\export_model.ps1 830
.EXAMPLE
  .\export_model.ps1 830,833 -Force
.EXAMPLE
  .\export_model.ps1 FACE_FON_000
.EXAMPLE
  .\export_model.ps1 0x7ce546e8
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string[]]$Targets,

    [string]$GameRoot = 'D:\Program Files (x86)\Steam\steamapps\common\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -',
    [string]$OutputRoot = 'D:\venusvacationprism_exports',
    [string]$BlenderExe = 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe',
    [switch]$List,
    [switch]$AllModels,
    # Render a labeled contact sheet of every converted model's front view
    # (thumbnails are rendered for any converted glTF that lacks one).
    [switch]$Sheet,
    [switch]$NoBlend,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = [IO.Path]::GetFullPath((Join-Path $scriptDir '..\..'))
$exportPy = Join-Path $scriptDir 'export_model.py'
$listPy = Join-Path $scriptDir 'list_models.py'
$mapPy = Join-Path $scriptDir 'map_characters.py'
$previewPy = Join-Path $scriptDir 'gltf_to_blend_preview.py'
$gltfTool = Join-Path $repoRoot '.tmp\gust_stuff\g1m_to_basic_gltf.py'
$gustDeps = Join-Path $repoRoot '.tmp\gust_deps'
$inventoryDir = Join-Path $OutputRoot 'inventory'
$modelsJson = Join-Path $inventoryDir 'models.json'
$charJson = Join-Path $inventoryDir 'character_models.json'
$modelsRoot = Join-Path $OutputRoot 'models'

function Get-Inventory {
    # The probed inventory carries skeleton_joints/category per entry; build
    # it (and the character-name mapping) automatically on first use.
    $needProbe = $true
    if (Test-Path -LiteralPath $modelsJson) {
        $data = Get-Content -LiteralPath $modelsJson -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($data.summary.categories.PSObject.Properties.Name -notcontains 'unprobed') {
            $needProbe = $false
        }
    }
    if ($needProbe) {
        Write-Host 'Probed inventory missing; scanning all G1M entries (a few minutes, one-off)...' `
            -ForegroundColor Yellow
        & python $listPy --game $GameRoot --output $inventoryDir --probe | Out-Null
        $data = Get-Content -LiteralPath $modelsJson -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    if (-not (Test-Path -LiteralPath $charJson)) {
        Write-Host 'Character-name mapping missing; building it...' -ForegroundColor Yellow
        & python $mapPy --game $GameRoot --output $inventoryDir | Out-Null
    }
    $data
}

function Get-NameIndex {
    $names = @{}
    if (Test-Path -LiteralPath $charJson) {
        $mapping = Get-Content -LiteralPath $charJson -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($entry in $mapping.models) {
            $names[[int]$entry.model_index] = [pscustomobject]@{
                InternalName = $entry.internal_name
                Character    = $entry.character_en
                CharacterZh  = $entry.character_zh
            }
        }
    }
    $names
}

function Get-ConvertedIndexSet {
    $converted = @{}
    foreach ($root in @($modelsRoot, (Join-Path $OutputRoot '_nude_probe'))) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Get-ChildItem -LiteralPath $root -Recurse -Filter 'model_*.gltf' -File |
            ForEach-Object {
                if ($_.BaseName -match '^model_0*(\d+)_') {
                    $converted[[int]$Matches[1]] = $_.FullName
                }
            }
    }
    $converted
}

$inventory = Get-Inventory
$nameIndex = Get-NameIndex
$convertedSet = Get-ConvertedIndexSet

if ($List) {
    $rows = $inventory.models | Where-Object {
        $AllModels -or $_.category -eq 'character_candidate'
    } | ForEach-Object {
        $known = $nameIndex[[int]$_.index]
        [pscustomobject]@{
            Index     = $_.index
            KTID      = $_.file_id
            Joints    = $_.skeleton_joints
            MiB       = [math]::Round($_.uncompressed_size / 1MB, 2)
            Name      = if ($known) { $known.InternalName } else { '' }
            Character = if ($known) { $known.Character } else { '' }
            Converted = if ($convertedSet.ContainsKey([int]$_.index)) { 'yes' } else { '' }
        }
    } | Sort-Object -Property @{Expression = 'Name'; Descending = $false },
        @{Expression = 'MiB'; Descending = $true }
    $rows | Format-Table -AutoSize
    $candidateCount = @($rows).Count
    Write-Host ("{0} entries ({1}). Convert with: .\export_model.ps1 <Index|0xKTID|Name>" -f `
        $candidateCount, $(if ($AllModels) { 'all models' } else { 'character candidates; -AllModels for every G1M' })) `
        -ForegroundColor Cyan
    Write-Host 'Unnamed BODY-sized entries are outfit/base body variants; convert to identify them.' `
        -ForegroundColor DarkGray
    exit 0
}

if ($Sheet) {
    $thumbsPy = Join-Path $scriptDir 'render_model_thumbs.py'
    $sheetPy = Join-Path $scriptDir 'make_contact_sheet.py'
    $byIndex = @{}
    foreach ($model in $inventory.models) { $byIndex[[int]$model.index] = $model }

    $jobs = @()
    foreach ($item in ($convertedSet.GetEnumerator() | Sort-Object Key)) {
        $index = [int]$item.Key
        $gltf = $item.Value
        $png = [IO.Path]::ChangeExtension($gltf, $null) + 'thumb.png'
        $entry = $byIndex[$index]
        $known = $nameIndex[$index]
        $labelParts = @([string]$index)
        if ($entry) { $labelParts += ('{0:n1}MiB' -f ($entry.uncompressed_size / 1MB)) }
        if ($known) { $labelParts += $known.InternalName }
        $jobs += [pscustomobject]@{
            gltf  = $gltf
            png   = $png
            label = ($labelParts -join '  ')
        }
    }
    if (-not $jobs) {
        Write-Error 'No converted models found; convert some first (e.g. .\export_model.ps1 830).'
        exit 1
    }
    function Invoke-ThumbPass {
        param([object[]]$PassJobs)
        $jobsJson = Join-Path $env:TEMP ('prism_thumb_jobs_' + [guid]::NewGuid().ToString('N') + '.json')
        # PS 5.1 ConvertTo-Json turns a 1-element array into an object; build manually.
        ('[' + (($PassJobs | ForEach-Object {
            '{"source":' + ($_.source | ConvertTo-Json) + ',"png":' + ($_.png | ConvertTo-Json) + '}'
        }) -join ',') + ']') | Out-File $jobsJson -Encoding utf8
        $previousErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $blenderOutput = @(& $BlenderExe --background --python $thumbsPy -- $jobsJson 2>&1 |
                ForEach-Object { "$_" })
        }
        finally {
            $ErrorActionPreference = $previousErrorPreference
            Remove-Item $jobsJson -Force -ErrorAction SilentlyContinue
        }
        # stderr tracebacks interleave with stdout; regex the single-line marker
        # out of the combined text instead of trusting line boundaries.
        $joined = $blenderOutput -join "`n"
        $match = [regex]::Match($joined, 'PRISM_THUMBS=(\[[^\r\n]*\])')
        if (-not $match.Success) {
            Write-Error ('Thumbnail render produced no marker; last lines: ' +
                (($blenderOutput | Select-Object -Last 6) -join ' | '))
            exit 1
        }
        ,@($match.Groups[1].Value | ConvertFrom-Json)
    }

    Write-Host ("Rendering thumbnails for " + $jobs.Count + " converted model(s)...") -ForegroundColor Cyan
    foreach ($job in $jobs) {
        $job | Add-Member -NotePropertyName source -NotePropertyValue $job.gltf -Force
    }
    $results = Invoke-ThumbPass $jobs

    # glTFs from the basic converter occasionally carry out-of-range joint
    # indices that crash Blender's importer; fall back to Noesis+ProjectG1M
    # FBX for exactly those entries.
    $failedPngs = @($results | Where-Object { $_.status -eq 'import-failed' } |
        ForEach-Object { $_.png })
    # Belt and braces: only retry thumbnails that are genuinely missing.
    $failedPngs = @($failedPngs | Where-Object { -not (Test-Path -LiteralPath $_) })
    if ($failedPngs) {
        $noesis = 'E:\tools\noesisv\Noesis64.exe'
        $retryJobs = @()
        foreach ($job in ($jobs | Where-Object { $failedPngs -contains $_.png })) {
            $g1m = [IO.Path]::ChangeExtension($job.gltf, '.g1m')
            if (-not (Test-Path -LiteralPath $g1m)) { continue }
            $fbx = [IO.Path]::ChangeExtension($g1m, '.noesis.fbx')
            if (-not (Test-Path -LiteralPath $fbx)) {
                & $noesis ?cmode $g1m $fbx | Out-Null
            }
            if (Test-Path -LiteralPath $fbx) {
                $retryJobs += [pscustomobject]@{ source = $fbx; png = $job.png }
            }
        }
        if ($retryJobs -and (Test-Path -LiteralPath $noesis)) {
            Write-Host ("Retrying " + $retryJobs.Count + " via Noesis FBX fallback...") `
                -ForegroundColor Yellow
            Invoke-ThumbPass $retryJobs | Out-Null
        }
    }

    $tilesJson = Join-Path $env:TEMP ('prism_sheet_tiles_' + [guid]::NewGuid().ToString('N') + '.json')
    ('[' + (($jobs | ForEach-Object {
        '{"png":' + ($_.png | ConvertTo-Json) + ',"label":' + ($_.label | ConvertTo-Json) + '}'
    }) -join ',') + ']') | Out-File $tilesJson -Encoding utf8
    $sheetPrefix = Join-Path $modelsRoot 'contact_sheet'
    New-Item -ItemType Directory -Force -Path $modelsRoot | Out-Null
    $sheetResult = & python $sheetPy $tilesJson $sheetPrefix
    Remove-Item $tilesJson -Force -ErrorAction SilentlyContinue
    Write-Host ("Contact sheet(s): " + $sheetResult) -ForegroundColor Green
    exit 0
}

if (-not $Targets -or $Targets.Count -eq 0) {
    Write-Error 'Specify model index/0xKTID/internal name, e.g.: .\export_model.ps1 830   (use -List first)'
    exit 1
}

foreach ($required in @($exportPy, $gltfTool, $gustDeps)) {
    if (-not (Test-Path -LiteralPath $required)) {
        Write-Error ("Required path not found: " + $required)
        exit 1
    }
}

$allTargets = @()
foreach ($raw in $Targets) {
    $allTargets += $raw -split '[,;]' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}

$failed = @()
foreach ($target in $allTargets) {
    Write-Host ''
    Write-Host ("[{0}] resolving..." -f $target) -ForegroundColor Cyan

    # Resolve to an inventory row for stable output naming.
    $entry = $null
    if ($target -match '^\d+$') {
        $entry = $inventory.models | Where-Object { $_.index -eq [int]$target }
        $selector = @('--index', $target)
    } elseif ($target -match '^0x[0-9a-fA-F]+$') {
        $entry = $inventory.models | Where-Object { $_.file_id -eq $target.ToLower() }
        $selector = @('--id', $target)
    } else {
        $named = $nameIndex.GetEnumerator() | Where-Object { $_.Value.InternalName -eq $target }
        if ($named) {
            $entry = $inventory.models | Where-Object { $_.index -eq $named.Key }
        }
        $selector = @('--name', $target)
    }
    if (-not $entry) {
        Write-Host '  Not present in inventory index; passing through to export_model.py anyway.' `
            -ForegroundColor DarkYellow
    }

    $label = if ($entry) { 'model_{0:d4}_{1}' -f [int]$entry.index, $entry.file_id } else { 'model_' + $target }
    $outDir = Join-Path $modelsRoot $label
    $gltf = Join-Path $outDir ($label + '.gltf')
    $blend = Join-Path $outDir ($label + '.blend')

    if ((Test-Path -LiteralPath $gltf) -and -not $Force) {
        Write-Host ("  glTF exists, skipped conversion: " + $gltf) -ForegroundColor Yellow
    } else {
        $exportArgs = @('--game', $GameRoot) + $selector + @(
            '--output', $outDir,
            '--gltf-tool', $gltfTool,
            '--converter-pythonpath', $gustDeps
        )
        & python $exportPy @exportArgs
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $gltf)) {
            # export_model.py names the gltf itself; accept whatever it wrote
            $written = @(Get-ChildItem -LiteralPath $outDir -Filter '*.gltf' -File `
                -ErrorAction SilentlyContinue) | Select-Object -First 1
            if ($written) {
                $gltf = $written.FullName
                $blend = [IO.Path]::ChangeExtension($gltf, '.blend')
            } else {
                Write-Host ("  FAILED: no glTF produced for " + $target) -ForegroundColor Red
                $failed += $target
                continue
            }
        }
    }

    if (-not $NoBlend) {
        if ((Test-Path -LiteralPath $blend) -and -not $Force) {
            Write-Host ("  Blend exists, skipped: " + $blend) -ForegroundColor Yellow
        } else {
            $previousErrorPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $blenderOutput = @(& $BlenderExe --background --python $previewPy -- `
                    $gltf $blend 2>&1 | ForEach-Object { "$_" })
            }
            finally {
                $ErrorActionPreference = $previousErrorPreference
            }
            $marker = $blenderOutput | Where-Object { $_.StartsWith('PRISM_MODEL_PREVIEW=') } |
                Select-Object -Last 1
            if (-not $marker) {
                Write-Host '  Blender preview failed; glTF is still available:' -ForegroundColor Red
                $blenderOutput | Select-Object -Last 8 | ForEach-Object { Write-Host ("    " + $_) }
                $failed += $target
                continue
            }
            $stats = $marker.Substring('PRISM_MODEL_PREVIEW='.Length) | ConvertFrom-Json
            Write-Host ("  {0} meshes / {1} vertices / {2} bones / height {3} cm" -f `
                $stats.meshes, $stats.vertices, $stats.bones, $stats.height) -ForegroundColor Green
        }
    }

    Write-Host ("  Output: " + $outDir) -ForegroundColor Green
    Get-ChildItem -LiteralPath $outDir -File | ForEach-Object {
        Write-Host ("    {0,9:n1} KB  {1}" -f ($_.Length / 1KB), $_.Name)
    }
}

Write-Host ''
if ($failed) {
    Write-Host ("Done with failures: " + ($failed -join ', ')) -ForegroundColor Red
    exit 1
}
Write-Host 'Done.' -ForegroundColor Green
