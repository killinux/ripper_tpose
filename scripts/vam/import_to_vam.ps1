<#
.SYNOPSIS
  Take a Blender mesh into Virt-A-Mate: write the DAZ .duf its in-game
  Clothing Creator / Hair Creator imports.

.DESCRIPTION
  The reverse of export_vam_models.ps1.  VaM 1.22 has no mesh importer, but
  it ships an in-game creator (DAZRuntimeCreator) that reads one file type, a
  DAZ .duf scene, fits the mesh to the body itself and stores the result as
  the .vam / .vaj / .vab triple.  This writes that .duf straight out of
  Blender - no DAZ Studio and no Unity involved.

    -Reference        build the modelling reference: VaM's own base Genesis 2
                      body as a .blend, in Blender axes and metres.  Model
                      the garment around this exact mesh - the creator wraps
                      onto the base body, not onto a morphed character.
    -Source <file>     .blend to open, or .obj / .fbx / .glb / .dae to import
                      (default: whatever -Objects names in a -Source .blend)
    -Out <file>       .duf to write (default <OutRoot>\<name>.duf)
    -Morph <name>     write a Genesis 2 morph .dsf instead of a .duf: the
                      deltas between the chosen object and the base body.
                      Sculpt a copy of the -Reference body without adding or
                      deleting vertices.
    -Install clothing|hair|morph
                      write into the VaM install instead, under
                      Custom\Clothing|Hair\<Gender>\<Author>\ (where the
                      creator's file browser can see it) or
                      Custom\Atom\Person\Morphs\<gender>\<Author>\
    -Objects a,b      objects to export (default: the selection, else every
                      mesh in the file)
    -Separate         one .duf per object instead of one merged item
    -Name             item name inside the DUF
    -Plain            leave the .duf uncompressed (easier to inspect; VaM
                      reads both, DAZ and VaM's own samples are gzipped)

  In VaM: load the Clothing Creator (or Hair Creator) onto a Person, point
  its dufFile browser at the .duf, press Import, then Store to create the
  item.  Keep the mesh under 50000 vertices for the wrap and under 25000 if
  you also want the cloth sim - the creator refuses to be quiet about it.

.EXAMPLE
  .\import_to_vam.ps1 -Reference

.EXAMPLE
  .\import_to_vam.ps1 -Source D:\work\jacket.blend -Name jacket

.EXAMPLE
  .\import_to_vam.ps1 -Source D:\work\jacket.obj -Install clothing -Author me

.EXAMPLE
  .\import_to_vam.ps1 -Source D:\work\set.blend -Separate -Objects hat,scarf

.EXAMPLE
  .\import_to_vam.ps1 -Source D:\work\belly.blend -Morph "Belly Out" -Install morph
#>
[CmdletBinding()]
param(
    [string]$GameRoot = "E:\tools\vam\vam1.22\vam1.22\1.22",
    [string]$OutRoot = "D:\vam_imports",
    [string]$CacheDir = "D:\vam_exports\_cache",
    [string]$BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [string]$Source,
    [string]$Out,
    [string[]]$Objects,
    [string]$Name,
    [string]$Author = "ripper_tpose",
    [string]$Morph,
    [string]$MorphGroup = "/Morphs/ripper_tpose",
    [ValidateSet('clothing', 'hair', 'morph')]
    [string]$Install,
    [ValidateSet('female', 'male')]
    [string]$Gender = 'female',
    [switch]$Separate,
    [switch]$NoModifiers,
    [switch]$Plain,
    [switch]$Reference
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$worker = Join-Path $here 'blender_to_duf.py'

if (-not (Test-Path -LiteralPath $BlenderExe)) { throw "Blender not found: $BlenderExe" }
if (-not (Test-Path -LiteralPath $worker)) { throw "worker not found: $worker" }
if (-not $Reference -and -not $Source) {
    throw "nothing to do: pass -Source <file> to export, or -Reference to build the base body"
}

function Invoke-Worker {
    param([string[]]$BlenderArgs, [string[]]$ScriptArgs)
    $all = @('--background') + $BlenderArgs + @('--python', $worker, '--') + $ScriptArgs
    Write-Host "blender $($ScriptArgs -join ' ')" -ForegroundColor DarkGray
    $output = & $BlenderExe @all 2>&1
    $marker = $output | Where-Object { $_ -is [string] -and $_.StartsWith('VAM_DUF=') } | Select-Object -Last 1
    if (-not $marker) {
        $output | ForEach-Object { Write-Host $_ }
        throw "Blender did not report a result"
    }
    return ($marker.Substring(8) | ConvertFrom-Json)
}

if ($Reference) {
    $dir = Join-Path $OutRoot '_reference'
    foreach ($g in @('female', 'male')) {
        $blend = Join-Path $dir ("Genesis2" + $g.Substring(0, 1).ToUpper() + $g.Substring(1) + ".blend")
        $result = Invoke-Worker -BlenderArgs @('--factory-startup') -ScriptArgs @(
            '--clean', '--base-body', $g, '--cache', $CacheDir, '--save-blend', $blend)
        $body = $result.baseBody
        Write-Host ("  {0}: {1} vertices, {2} polygons -> {3}" -f $body.object, $body.vertices, $body.polygons, $blend) -ForegroundColor Green
    }
    Write-Host "Model the garment around this body, then re-run with -Source." -ForegroundColor Cyan
    if (-not $Source) { return }
}

$ext = [System.IO.Path]::GetExtension($Source).ToLower()
if (-not (Test-Path -LiteralPath $Source)) { throw "input not found: $Source" }
$stem = if ($Name) { $Name } else { [System.IO.Path]::GetFileNameWithoutExtension($Source) }

$suffix = if ($Morph) { 'dsf' } else { 'duf' }
if ($Morph) { $stem = $Morph }
if (-not $Out) {
    if ($Install -eq 'morph') {
        $Out = Join-Path $GameRoot ("Custom\Atom\Person\Morphs\{0}\{1}\{2}.dsf" -f $Gender, $Author, $stem)
    }
    elseif ($Install) {
        $folder = if ($Install -eq 'hair') { 'Hair' } else { 'Clothing' }
        $genderDir = $Gender.Substring(0, 1).ToUpper() + $Gender.Substring(1)
        $Out = Join-Path $GameRoot ("Custom\{0}\{1}\{2}\{3}.{4}" -f $folder, $genderDir, $Author, $stem, $suffix)
    }
    else {
        $Out = Join-Path $OutRoot ("{0}.{1}" -f $stem, $suffix)
    }
}
$outDir = Split-Path -Parent $Out
if ($outDir -and -not (Test-Path -LiteralPath $outDir)) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}

$blenderArgs = @()
$scriptArgs = @('--out', $Out, '--name', $stem, '--author', $Author)
if ($ext -eq '.blend') { $blenderArgs += $Source } else { $blenderArgs += '--factory-startup'; $scriptArgs += @('--load', $Source) }
if ($Morph) { $scriptArgs += @('--morph', $Morph, '--gender', $Gender, '--morph-group', $MorphGroup, '--cache', $CacheDir) }
if ($Objects) { $scriptArgs += @('--objects') + $Objects }
if ($Separate) { $scriptArgs += '--separate' }
if ($NoModifiers) { $scriptArgs += '--no-modifiers' }
if ($Plain) { $scriptArgs += '--plain' }

$result = Invoke-Worker -BlenderArgs $blenderArgs -ScriptArgs $scriptArgs
foreach ($item in $result.written) {
    if ($item.kind -eq 'morph') {
        Write-Host ("  {0}: {1} moved vertices, largest {2} m, {3} {4}" -f `
                $item.name, $item.deltas, $item.largestMove, $item.gender, $item.group) -ForegroundColor Green
    }
    else {
        Write-Host ("  {0}: {1} vertices, {2} polygons, materials {3}" -f `
                $item.name, $item.vertices, $item.polygons, ($item.materials -join ', ')) -ForegroundColor Green
    }
    Write-Host ("    -> {0}" -f $item.path)
}
foreach ($w in $result.warnings) { Write-Host ("  warning: {0}" -f $w) -ForegroundColor Yellow }
if ($Install -eq 'morph') {
    Write-Host "Restart VaM: it compiles new .dsf morphs into .vmi/.vmb on startup, then the morph shows up under $MorphGroup." -ForegroundColor Cyan
}
elseif ($Install) {
    Write-Host "In VaM: add the Clothing Creator (or Hair Creator) to a Person, browse to this .duf, Import, then Store." -ForegroundColor Cyan
}
