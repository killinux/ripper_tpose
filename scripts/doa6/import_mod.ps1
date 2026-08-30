# DOA 通用 mod 转换：把下载的 mod（zip 或已解压目录）里的模型/贴图转成 FBX + DDS。
#
# 同时支持两种 mod：
#   DOA6  REDELBE Layer2：*.g1m + *.g1t   -> Noesis64 + ProjectG1M
#   DOA5LR             ：*.TMC + *.TMCL   -> Noesis(32) + doa5pc_custom
# 自动按扩展名判别，无需指定游戏。
#
# 用法：
#   .\import_mod.ps1 D:\doa_mods\doa6\_zips          # 目录下所有 zip 逐个解压+转换
#   .\import_mod.ps1 D:\doa_mods\doa6\some_mod_dir   # 已解压目录，直接转换
#   .\import_mod.ps1 D:\path\mod.zip                 # 单个 zip
#   .\import_mod.ps1 <路径> -OutRoot D:\doa_mod_fbx  # 指定 FBX/DDS 输出根

param(
    [Parameter(Position = 0, Mandatory = $true)] [string] $Path,
    [string] $OutRoot = "D:\doa_mod_fbx",
    [string] $Noesis64 = "E:\tools\noesisv\Noesis64.exe",   # g1m/g1t
    [string] $Noesis32 = "E:\tools\noesisv\Noesis.exe",     # TMC
    [switch] $KeepExtracted
)

$ErrorActionPreference = "Stop"

function Convert-ModDir {
    param([string] $ModDir, [string] $Label)
    $outDir = Join-Path $OutRoot $Label
    $null = New-Item -ItemType Directory -Force $outDir

    $g1ms = Get-ChildItem $ModDir -Recurse -Filter "*.g1m" -File -ErrorAction SilentlyContinue
    $tmcs = Get-ChildItem $ModDir -Recurse -Filter "*.TMC" -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -ieq ".TMC" }
    $g1ts = Get-ChildItem $ModDir -Recurse -Filter "*.g1t" -File -ErrorAction SilentlyContinue

    $nModel = 0; $nTex = 0

    foreach ($g in $g1ms) {
        $fbx = Join-Path $outDir ($g.BaseName + ".fbx")
        & $Noesis64 ?cmode $g.FullName $fbx | Out-Null
        if (Test-Path $fbx) { $nModel++ } else { Write-Host "  WARN g1m 失败: $($g.Name)" -ForegroundColor Yellow }
    }
    foreach ($t in $tmcs) {
        # TMC 需同目录 TMCL；Noesis 自动找。产出 DDS 在同目录，复制过去
        $fbx = Join-Path $outDir ($t.BaseName + ".fbx")
        & $Noesis32 ?cmode $t.FullName $fbx | Out-Null
        if (Test-Path $fbx) {
            $nModel++
            Get-ChildItem $t.Directory -Filter "Tex_*.dds" -File -ErrorAction SilentlyContinue | ForEach-Object {
                Copy-Item $_.FullName (Join-Path $outDir $_.Name) -Force
            }
        } else { Write-Host "  WARN TMC 失败: $($t.Name)" -ForegroundColor Yellow }
    }
    # g1t 贴图：每个转成 <基名>.dds（ProjectG1M 输出 <索引>.dds，单图时改名）
    $texDir = Join-Path $outDir "_textures"
    foreach ($g in $g1ts) {
        if ((Get-Item $g.FullName).Length -lt 200) { continue }  # 占位空 g1t
        $null = New-Item -ItemType Directory -Force $texDir
        $sub = Join-Path $texDir $g.BaseName
        $null = New-Item -ItemType Directory -Force $sub
        & $Noesis64 ?cmode $g.FullName (Join-Path $sub "t.dds") | Out-Null
        $dds = Get-ChildItem $sub -Filter "*.dds" -File -ErrorAction SilentlyContinue
        if ($dds.Count -ge 1) {
            if ($dds.Count -eq 1) {
                Move-Item $dds[0].FullName (Join-Path $texDir ($g.BaseName + ".dds")) -Force
            } else {
                $dds | ForEach-Object { Move-Item $_.FullName (Join-Path $texDir ($g.BaseName + "_" + $_.Name)) -Force }
            }
            $nTex += $dds.Count
            Remove-Item $sub -Recurse -Force -Confirm:$false
        }
    }
    Write-Host "  $Label : $nModel 模型, $nTex 贴图 -> $outDir" -ForegroundColor Green
}

$item = Get-Item $Path
$work = "D:\doa_mods\_extract_tmp"

# 收集要处理的“单元”：每个 zip = 一个单元；目录若直接含模型也算一个单元；
# 否则把目录下每个 zip 当单元。
$units = @()
if ($item.PSIsContainer) {
    $zips = Get-ChildItem $item.FullName -Filter "*.zip" -File
    $hasModel = Get-ChildItem $item.FullName -Recurse -Include "*.g1m","*.TMC" -File -ErrorAction SilentlyContinue
    if ($zips -and -not $hasModel) {
        foreach ($z in $zips) { $units += @{ type="zip"; path=$z.FullName; label=$z.BaseName } }
    } else {
        $units += @{ type="dir"; path=$item.FullName; label=$item.Name }
    }
} elseif ($item.Extension -ieq ".zip") {
    $units += @{ type="zip"; path=$item.FullName; label=$item.BaseName }
} else {
    throw "不支持的输入：$Path（给 zip、含 zip 的目录，或已解压的 mod 目录）"
}

Write-Host "== 待处理 $($units.Count) 个单元 -> $OutRoot ==" -ForegroundColor Cyan
$idx = 0
foreach ($u in $units) {
    $idx++
    $label = ($u.label -replace '[^\w.\-()]', '_')
    Write-Host "[$idx/$($units.Count)] $label"
    if ($u.type -eq "zip") {
        $ex = Join-Path $work $label
        if (Test-Path $ex) { Remove-Item $ex -Recurse -Force -Confirm:$false }
        $null = New-Item -ItemType Directory -Force $ex
        try { Expand-Archive $u.path -DestinationPath $ex -Force } catch { Write-Host "  解压失败，跳过: $_" -ForegroundColor Yellow; continue }
        Convert-ModDir -ModDir $ex -Label $label
        if (-not $KeepExtracted) { Remove-Item $ex -Recurse -Force -Confirm:$false }
    } else {
        Convert-ModDir -ModDir $u.path -Label $label
    }
}
Write-Host "== 完成，FBX/DDS 在 $OutRoot ==" -ForegroundColor Cyan
