[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string[]] $Package,

    [string] $GameRoot = 'D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE',
    [string] $OutputRoot = 'D:\ff7remake_exports\umodel_original',
    [string] $UmodelExe = 'E:\tools\umodel_ff7remake\umodel_FFVII_intergrade_v8.exe',
    [string] $AesKey = $env:FF7REMAKE_AES_KEY,

    [switch] $WithAnimations,
    [switch] $AllLods,
    [switch] $AllWeights,
    [switch] $IncludeMods,
    [switch] $NoOverwrite
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($AesKey)) {
    throw 'AES key is required. Set FF7REMAKE_AES_KEY or pass -AesKey.'
}

$paksRoot = Join-Path $GameRoot 'End\Content\Paks'
$modsRoot = Join-Path $paksRoot '~mods'

if (-not (Test-Path -LiteralPath $UmodelExe -PathType Leaf)) {
    throw "UE Viewer executable not found: $UmodelExe"
}
if (-not (Test-Path -LiteralPath $paksRoot -PathType Container)) {
    throw "Game Paks directory not found: $paksRoot"
}
if (Get-Process -Name 'ff7remake' -ErrorAction SilentlyContinue) {
    throw 'FINAL FANTASY VII REMAKE is running. Close the game before exporting.'
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$temporaryKey = Join-Path ([System.IO.Path]::GetTempPath()) ("ff7remake-aes-{0}.txt" -f [guid]::NewGuid())
[System.IO.File]::WriteAllText($temporaryKey, $AesKey)

$arguments = @(
    '-export'
    '-png'
    '-game=ue4.18'
    "-path=$paksRoot"
    "-aes=@$temporaryKey"
    "-out=$OutputRoot"
)
if (-not $WithAnimations) { $arguments += '-noanim' }
if ($AllLods) { $arguments += '-lods' }
if ($AllWeights) { $arguments += '-weights' }
if ($NoOverwrite) { $arguments += '-nooverwrite' }

$disabledMods = [System.Collections.Generic.List[object]]::new()

try {
    if (-not $IncludeMods -and (Test-Path -LiteralPath $modsRoot -PathType Container)) {
        $resolvedModsRoot = (Resolve-Path -LiteralPath $modsRoot).Path.TrimEnd('\') + '\'
        foreach ($mod in Get-ChildItem -LiteralPath $modsRoot -File -Filter '*.pak') {
            $resolvedMod = (Resolve-Path -LiteralPath $mod.FullName).Path
            if (-not $resolvedMod.StartsWith($resolvedModsRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to move an unexpected mod path: $resolvedMod"
            }

            $disabledPath = "$resolvedMod.codex-disabled"
            if (Test-Path -LiteralPath $disabledPath) {
                throw "Temporary disabled path already exists: $disabledPath"
            }

            Move-Item -LiteralPath $resolvedMod -Destination $disabledPath
            $disabledMods.Add([pscustomobject]@{
                Original = $resolvedMod
                Disabled = $disabledPath
            })
        }
    }

    foreach ($packageName in $Package) {
        if ([string]::IsNullOrWhiteSpace($packageName)) {
            throw 'Package paths must not be empty.'
        }

        Write-Host "Exporting $packageName"
        & $UmodelExe @arguments $packageName
        if ($LASTEXITCODE -ne 0) {
            throw "UE Viewer failed with exit code $LASTEXITCODE while exporting $packageName"
        }
    }
}
finally {
    if (Test-Path -LiteralPath $temporaryKey) {
        Remove-Item -LiteralPath $temporaryKey -Force
    }

    for ($index = $disabledMods.Count - 1; $index -ge 0; $index--) {
        $entry = $disabledMods[$index]
        if ((Test-Path -LiteralPath $entry.Disabled) -and -not (Test-Path -LiteralPath $entry.Original)) {
            Move-Item -LiteralPath $entry.Disabled -Destination $entry.Original
        }
    }
}

Write-Host "Export complete: $OutputRoot"
