<#
.SYNOPSIS
  List and export Virt-A-Mate (VaM) looks and clothing to .blend + preview PNG.

.DESCRIPTION
  Thin wrapper around export_vam_models.py (which does the real work with
  Python 3 + numpy and drives Blender headless).  Mirrors the ROE
  export_character_models.ps1 interface:

    -List             show every look (Person atom in a scene / appearance
                      preset), clothing item and hair item with a # index
    -Only <keys>      export the named entries (exact key or unique substring)
    -Index <numbers>  export by the # shown in -List
    -All              export every look and every clothing item with a mesh

  Outputs land in <OutRoot>\looks\<key>\blend\ and
  <OutRoot>\clothings\<key>\blend\ next to the assembled model.json,
  model.npz and _textures the Blender step consumed.

.EXAMPLE
  .\export_vam_models.ps1 -List

.EXAMPLE
  .\export_vam_models.ps1 -List -Type clothing -Filter cheongsam

.EXAMPLE
  .\export_vam_models.ps1 -Only VAMSOY.Angela.1~Angela~Person

.EXAMPLE
  .\export_vam_models.ps1 -Index 12,15 -Format blend,glb -Force

.EXAMPLE
  .\export_vam_models.ps1 -Prepare        # build the cache up front (~3-5 min)
#>
[CmdletBinding()]
param(
    [string]$GameRoot = "E:\tools\vam\vam1.22\vam1.22\1.22",
    [string]$OutRoot = "D:\vam_exports",
    [string]$BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [string]$AssetStudioExe = "E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe",
    [string]$PythonExe = "python",
    [string[]]$Only,
    [int[]]$Index,
    [switch]$All,
    [ValidateSet('look', 'clothing', 'hair', 'all')]
    [string]$Type = 'all',
    [string]$Filter,
    [string[]]$Format,
    [string]$ManifestPath,
    [switch]$IncludePoseMorphs,
    [switch]$NoClothing,
    [switch]$NoPreview,
    [switch]$ValidateOnly,
    [switch]$Force,
    [switch]$List,
    [switch]$Prepare
)

# Keep every string literal in this file ASCII: PowerShell 5.1 reads a BOM-less
# .ps1 with the OEM code page and mangled multi-byte text inside quotes breaks
# the parser.  Non-ASCII package names travel fine as *arguments*.
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$cli = Join-Path $scriptDir 'export_vam_models.py'
foreach ($required in @($GameRoot, $cli)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path not found: $required"
    }
}

$common = @('--game-root', $GameRoot, '--out', $OutRoot)
if ($AssetStudioExe) { $common += @('--assetstudio', $AssetStudioExe) }

# Python prints UTF-8; make the console agree so Chinese package names survive.
$previousEncoding = [Console]::OutputEncoding
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
try {
    if ($Prepare) {
        & $PythonExe $cli @common prepare
        exit $LASTEXITCODE
    }
    if ($List) {
        $listArgs = @('list', '--kind', $Type)
        if ($Filter) { $listArgs += @('--filter', $Filter) }
        & $PythonExe $cli @common @listArgs
        exit $LASTEXITCODE
    }
    if (-not $Only -and -not $Index -and -not $All) {
        throw 'Nothing selected: use -List to browse, then -Only <key>, -Index <#> or -All.'
    }
    if (-not (Test-Path -LiteralPath $BlenderExe)) {
        throw "Blender not found: $BlenderExe"
    }

    $formats = @()
    foreach ($entry in @($Format)) {
        if ($entry) {
            $formats += $entry -split '[,;]' | ForEach-Object { $_.Trim().ToLowerInvariant() } |
                Where-Object { $_ }
        }
    }
    if (-not $formats) { $formats = @('blend') }
    $invalid = @($formats | Where-Object { $_ -notin @('blend', 'glb') })
    if ($invalid) { throw "Unknown format(s): $($invalid -join ', '). Valid: blend, glb" }

    $exportArgs = @('export', '--kind', $Type, '--blender', $BlenderExe,
        '--format', ($formats -join ','))
    if ($Only) {
        $exportArgs += '--only'
        foreach ($entry in $Only) {
            $exportArgs += ($entry -split '[;]' | ForEach-Object { $_.Trim() } |
                Where-Object { $_ })
        }
    }
    if ($Index) { $exportArgs += @('--index') + @($Index | ForEach-Object { [string]$_ }) }
    if ($All) { $exportArgs += '--all' }
    if ($IncludePoseMorphs) { $exportArgs += '--include-pose-morphs' }
    if ($NoClothing) { $exportArgs += '--no-clothing' }
    if ($NoPreview) { $exportArgs += '--no-preview' }
    if ($ValidateOnly) { $exportArgs += '--validate' }
    if ($Force) { $exportArgs += '--force' }
    if ($ManifestPath) { $exportArgs += @('--manifest', $ManifestPath) }

    & $PythonExe $cli @common @exportArgs
    exit $LASTEXITCODE
}
finally {
    [Console]::OutputEncoding = $previousEncoding
}
