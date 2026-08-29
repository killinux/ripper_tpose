<#
.SYNOPSIS
  Batch-export the Throne of Desire nude female base models with materials.

.DESCRIPTION
  PowerShell entry point over batch_export_female.py, matching the ROE
  export_nude_models.ps1 conventions (-List, -Only, -Format, -ValidateOnly,
  -Force) with this machine's default paths.

  Throne of Desire's female h-group models ARE the nude bases: clothing ships
  as attachment meshes that the importer parks in a hidden *_Attachments
  collection, and the FBX export selects only the base body + armature.  No
  extra stripping step exists or is needed.

  -ValidateOnly reopens the already exported Blend/FBX artifacts in Blender
  (validate_female_exports36.py) instead of re-exporting; its report is the
  standalone female_export_validation.json snapshot.

.EXAMPLE
  .\export_nude_models.ps1 -List

.EXAMPLE
  .\export_nude_models.ps1                      # all 13 female bases -> blend+fbx+preview

.EXAMPLE
  .\export_nude_models.ps1 -Only h005,h020 -Force

.EXAMPLE
  .\export_nude_models.ps1 -ValidateOnly
#>
[CmdletBinding()]
param(
    [string]$GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire",
    [string]$BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [string]$OutputDir = "D:\throneofdesire_exports\female_all",
    [string]$PythonExe = "python",
    [string[]]$Only,
    [string[]]$Format,
    [switch]$List,
    [switch]$ValidateOnly,
    [switch]$Force,
    [switch]$NoRender,
    [switch]$IncludeHelpers
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
$batchPy = Join-Path $scriptDir 'batch_export_female.py'
$validatePy = Join-Path $scriptDir 'validate_female_exports36.py'

foreach ($required in @($batchPy, $validatePy)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required script not found: $required"
    }
}

# Single source of truth: read the classified female IDs from the Python module.
$modelIds = @(& $PythonExe -c "import sys; sys.path.insert(0, r'$scriptDir'); from batch_export_female import FEMALE_MODEL_IDS as M; print('\n'.join(M))" 2>&1 |
    Where-Object { $_ -is [string] -and $_ -match '^h\d+$' })
if (-not $modelIds) {
    throw "Could not read FEMALE_MODEL_IDS via '$PythonExe' from $batchPy"
}

function Get-ModelStatus {
    param([string]$ModelId)
    $modelDir = Join-Path $OutputDir $ModelId
    $blend = Join-Path $modelDir ($ModelId + '_blender36.blend')
    $fbx = Join-Path $modelDir ($ModelId + '.fbx')
    $preview = Join-Path $modelDir ($ModelId + '_preview.png')
    $have = @($blend, $fbx, $preview | Where-Object { Test-Path -LiteralPath $_ })
    if ($have.Count -eq 3) { return 'COMPLETE' }
    if ($have.Count -gt 0) { return 'PARTIAL' }
    return 'MISSING'
}

if ($List) {
    Write-Host ("Nude female bases: " + $modelIds.Count) -ForegroundColor Cyan
    $modelIds | ForEach-Object {
        [pscustomobject]@{
            Id     = $_
            Status = Get-ModelStatus $_
            Output = Join-Path $OutputDir $_
        }
    } | Format-Table -AutoSize
    Write-Host 'Formats: blend, fbx (default: both, plus a front preview PNG).' -ForegroundColor DarkGray
    Write-Host 'The exported base body IS the nude model; clothing attachments stay in a hidden collection and are excluded from FBX.' -ForegroundColor DarkGray
    exit 0
}

$wanted = @()
if ($Only) {
    $wanted = @($Only | ForEach-Object {
        $_ -split '[,;]' | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ }
    })
    $unknown = @($wanted | Where-Object { $_ -notin $modelIds })
    if ($unknown) {
        throw "Unknown -Only model id(s): $($unknown -join ', ') (use -List)"
    }
}

if ($ValidateOnly) {
    # Reopen the existing artifacts in Blender and write the standalone report.
    if (-not (Test-Path -LiteralPath $BlenderExe)) {
        throw "Blender not found: $BlenderExe"
    }
    $reportPath = Join-Path $OutputDir 'female_export_validation.json'
    $validateArguments = @(
        '--background', '--factory-startup', '--python', $validatePy, '--',
        '--root', $OutputDir,
        '--output', $reportPath
    )
    if ($wanted) {
        $validateArguments += @('--models') + $wanted
    }
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $BlenderExe @validateArguments 2>&1 | Where-Object {
            $_ -is [string] -and $_ -match '^(h\d+:|Error|Traceback)'
        } | ForEach-Object { Write-Host ('  ' + $_) }
    }
    finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    if (-not (Test-Path -LiteralPath $reportPath)) {
        throw "Validation report was not written: $reportPath"
    }
    $report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Host ""
    Write-Host ("Validated: PASS=" + $report.passed + " FAIL=" + $report.failed) `
        -ForegroundColor $(if ($report.failed) { 'Yellow' } else { 'Green' })
    Write-Host ("Report: " + $reportPath)
    if ($report.failed) {
        throw "$($report.failed) export(s) failed validation; see report."
    }
    exit 0
}

# Texture decoders are required for real exports (build once via build_codecs.py).
$lzham = Join-Path $repoRoot '.tmp\lzham_v1_decode_raw'
$etc = Join-Path $repoRoot '.tmp\etc_dds_decode'
$missingDecoders = @($lzham, $etc | Where-Object { -not (Test-Path -LiteralPath $_) })
if ($missingDecoders) {
    throw ("Texture decoder(s) missing: " + ($missingDecoders -join ', ') +
        ". Build them first: python scripts\throneofdesire\build_codecs.py (needs g++ in WSL)")
}
foreach ($required in @($GameRoot, $BlenderExe)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path not found: $required"
    }
}

$batchArguments = @(
    $batchPy,
    '--game', $GameRoot,
    '--blender', $BlenderExe,
    '--output', $OutputDir
)
if ($wanted) { $batchArguments += @('--models') + $wanted }
if ($Format) {
    $formats = @($Format | ForEach-Object {
        $_ -split '[,;]' | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ }
    } | Select-Object -Unique)
    $invalid = @($formats | Where-Object { $_ -notin @('blend', 'fbx') })
    if ($invalid) {
        throw "Unknown format(s): $($invalid -join ', '). Valid: blend, fbx (XPS is not supported by the ToD pipeline)"
    }
    $batchArguments += @('--formats') + $formats
}
if ($Force) { $batchArguments += '--force' }
if ($NoRender) { $batchArguments += '--no-render' }
if ($IncludeHelpers) { $batchArguments += '--include-helpers' }

& $PythonExe @batchArguments
$exitCode = $LASTEXITCODE
Write-Host ""
Write-Host ("Manifest: " + (Join-Path $OutputDir 'female_export_manifest.json'))
if ($exitCode -ne 0) {
    throw "batch_export_female.py exited with code $exitCode; see manifest."
}
