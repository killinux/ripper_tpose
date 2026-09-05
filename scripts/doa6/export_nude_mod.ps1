# DOA6 nude/mod 变体一键导出：REDELBE layer2 mod（zip 或目录）→ 带材质 .blend + 预览
#
# 与 export_full.ps1（官方服装）互补。mod 里给什么部件就换什么部件：
#   只有服装（最常见）      -> mod 服装 + 官方发型/脸
#   只有发型 / 脸+发型      -> 官方服装 + mod 发型(/脸)
#   服装+发型（如 Yor Forger）-> 两件都用 mod，脸用官方
# 缺的部件默认取 <CHR>_COS_001 / _HAIR_001 / _FACE_001，本机没导出过会现场导；
# -Cos/-Face/-Hair 给编号（030）或完整部件名（AYA_FACE_001，body swap 类 mod 用别人的脸）。
# mod 若额外带了官方部件的贴图（如 PHFFACE001_face_kidsalb），会叠到官方件上。
# 角色不在本机游戏里（如 SKD 丹羽 Tamaki 是未装 DLC）时只出 mod 自带的部件并警告。
#
# 每个部件的材质路线自动选择：
#   A 精确：部件编号在本机游戏数据里（HEL_COS_001、MOM_HAIR_005…）→ 原版 ktid 链
#     （g1m_matmap.py），mod 贴图覆盖原版同名底图。
#   B 启发式：编号是未安装 DLC（MOM_COS_105…）→ mod_matmap.py 按网格大小分配部位。
#     皮肤/衣物弄反时用 -Assign "3=body,5=f01" 纠正后重跑（只作用于服装）。
#
# 用法：
#   .\export_nude_mod.ps1 <mod.zip 或已解压目录> -Chr HEL -Label HEL_Helena_Nude
#   .\export_nude_mod.ps1 D:\mods\x.zip -Chr AYA -Label AYA_Malf -Assign "3=f01,5=body"
#   .\export_nude_mod.ps1 D:\mods\hair.zip -Label MOM_Momiji_LooseHair     # -Chr 可省略，按 g1m 名推断

param(
    [Parameter(Position = 0, Mandatory = $true)] [string] $Mod,
    [string] $Chr = "",
    [string] $Label = "",
    [string] $Cos = "001",
    [string] $Hair = "001",
    [string] $Face = "001",
    [string] $Assign = "",
    [switch] $NoPreview,
    [string] $OutRoot = "D:\doa6_exports",
    [string] $GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 6",
    [string] $PythonExe = "D:\openclaw\python\python.exe",
    [string] $NoesisExe = "E:\tools\noesisv\Noesis64.exe",
    [string] $BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
)

$ErrorActionPreference = "Stop"
$scripts = Split-Path -Parent $MyInvocation.MyCommand.Path

# 0) mod 解包/定位 Character\*.g1m 与 Material\
$modDir = $Mod
if ($Mod -match '\.zip$') {
    $modDir = Join-Path $env:TEMP ("doa6mod_" + [IO.Path]::GetFileNameWithoutExtension($Mod))
    if (Test-Path $modDir) { Remove-Item $modDir -Recurse -Force -Confirm:$false }
    Expand-Archive $Mod -DestinationPath $modDir -Force
}
$g1ms = @(Get-ChildItem $modDir -Recurse -Filter "*.g1m" -File | Where-Object { $_.Directory.Name -eq "Character" })
if ($g1ms.Count -eq 0) { $g1ms = @(Get-ChildItem $modDir -Recurse -Filter "*.g1m" -File) }
if ($g1ms.Count -eq 0) { throw "mod 里没有 g1m" }
$matDir = Get-ChildItem $modDir -Recurse -Directory -Filter "Material" | Select-Object -First 1
if (-not $matDir) { throw "mod 里没有 Material 目录" }
$matPath = $matDir.FullName

# 1) 按名字分类 mod 部件：<CHR>_<COS|HAIR|FACE>_<NNN>
$modParts = @{}
foreach ($g in $g1ms) {
    if ($g.BaseName -match '^([A-Z0-9]{3})_(COS|HAIR|FACE)_(\d+)$') {
        $kind = $Matches[2]
        if ($modParts.ContainsKey($kind)) { Write-Host "  跳过重复 $kind 部件 $($g.Name)" -ForegroundColor Yellow; continue }
        $modParts[$kind] = $g
        if (-not $Chr) { $Chr = $Matches[1] }
    } else {
        Write-Host "  跳过无法归类的 g1m: $($g.Name)" -ForegroundColor Yellow
    }
}
if ($modParts.Count -eq 0) { throw "mod 的 g1m 都不是 <CHR>_<COS|HAIR|FACE>_<NNN> 命名" }
$Chr = $Chr.ToUpper()
if (-not $Label) {
    $base = if ($Mod -match '\.zip$') { [IO.Path]::GetFileNameWithoutExtension($Mod) } else { Split-Path -Leaf $modDir }
    $Label = $Chr + "_" + (($base -replace '^\d+_+', '') -replace '[^\w]+', '_').Trim('_')
}
$partList = ($modParts.Keys | Sort-Object | ForEach-Object { $modParts[$_].BaseName }) -join ", "
$g1tCount = (Get-ChildItem $matPath -Filter "*.g1t").Count
Write-Host "mod 部件: $partList  贴图: $g1tCount 个 g1t  -> $Label" -ForegroundColor Cyan

function Convert-G1tDir([string] $srcDir, [string] $filter, [string] $dstDir) {
    foreach ($g in (Get-ChildItem $srcDir -Filter $filter -File -ErrorAction SilentlyContinue)) {
        if ($g.Length -lt 200) { continue }
        $sub = Join-Path $dstDir "_conv"
        $null = New-Item -ItemType Directory -Force $sub
        & $NoesisExe ?cmode $g.FullName (Join-Path $sub "t.dds") | Out-Null
        $dds = Get-ChildItem $sub -Filter "*.dds" -File
        if ($dds.Count -eq 1) { Move-Item $dds[0].FullName (Join-Path $dstDir ("_textures\" + $g.BaseName + ".dds")) -Force }
        Remove-Item $sub -Recurse -Force -Confirm:$false
    }
}

function Convert-Png([string] $pd, [switch] $Redo) {
    # matmap 里用到的 alb/nmh -> PNG（$Redo 时先删掉已有 PNG，用于贴图被覆盖后重做）
    $mm = Get-Content (Join-Path $pd "matmap.json") -Raw | ConvertFrom-Json
    $texNames = $mm.submeshes | ForEach-Object { $_.textures } | Where-Object { $_.channel -in @("alb", "nmh") } | ForEach-Object { $_.name } | Sort-Object -Unique
    $n = 0
    foreach ($t in $texNames) {
        $stem = $t -replace '\.g1t$', ''
        $dds = Join-Path $pd ("_textures\" + $stem + ".dds")
        $png = Join-Path $pd ("_png\" + $stem + ".png")
        if ($Redo -and (Test-Path $png)) { Remove-Item $png -Force }
        if ((Test-Path $dds) -and -not (Test-Path $png)) { & $NoesisExe ?cmode $dds $png | Out-Null }
        if (Test-Path $png) { $n++ }
    }
    Write-Host "  PNG: $n/$($texNames.Count)"
}

# mod 自带的部件：FBX + 材质映射（路线 A/B）
function Convert-ModPart([System.IO.FileInfo] $g1m, [string] $kind) {
    $id = $g1m.BaseName
    $texKey = ($id -replace "_", "")
    $pn = $Label + "_" + $kind.ToLower()
    $pd = Join-Path $OutRoot $pn
    if (Test-Path $pd) { Remove-Item $pd -Recurse -Force -Confirm:$false }
    $null = New-Item -ItemType Directory -Force (Join-Path $pd "_textures"), (Join-Path $pd "_png")
    $g1mOut = Join-Path $pd ($pn + ".g1m")
    $fbxOut = Join-Path $pd ($pn + ".fbx")
    $ktidOut = Join-Path $pd ($pn + ".ktid")
    $mmOut = Join-Path $pd "matmap.json"
    Copy-Item $g1m.FullName $g1mOut
    & $NoesisExe ?cmode $g1mOut $fbxOut | Out-Null
    if (-not (Test-Path $fbxOut)) { throw "$id 转 FBX 失败" }

    # ktid 优先级：mod 自带（g1m 旁的 <id>.ktid，槽位可能比原版多）> 本地已导出的部件目录 > CharacterEditor.rdb
    $ktidLocal = Join-Path $g1m.DirectoryName ($id + ".ktid")
    $haveKtid = Test-Path $ktidLocal
    if ($haveKtid) { Write-Host "  [$kind $id] 用 mod 自带的 ktid" -ForegroundColor DarkGray }
    if (-not $haveKtid) {
        $ktidLocal = Join-Path $OutRoot ($id + "\" + $id + ".ktid")
        $haveKtid = Test-Path $ktidLocal
    }
    if (-not $haveKtid) {
        & $PythonExe (Join-Path $scripts "extract_rdb.py") (Join-Path $GameRoot "CharacterEditor.rdb") -o $pd --filter "$id.ktid" --flat 2>$null | Out-Null
        $ktidTmp = Join-Path $pd ($id + ".ktid")
        if (Test-Path $ktidTmp) { $ktidLocal = $ktidTmp; $haveKtid = $true }
    }

    $texFilter = "*_" + $texKey + "_*.g1t"
    if ($haveKtid) {
        Write-Host "  [$kind $id] 路线 A：原版 ktid 链（精确映射）" -ForegroundColor Green
        Copy-Item $ktidLocal $ktidOut -Force
        $baseTex = Join-Path $OutRoot ($id + "\_textures")
        if (Test-Path $baseTex) {
            Copy-Item (Join-Path $baseTex "*.dds") (Join-Path $pd "_textures\") -Force -ErrorAction SilentlyContinue
        } else {
            $rawDir = Join-Path $pd "_g1t_base"
            & $PythonExe (Join-Path $scripts "extract_rdb.py") (Join-Path $GameRoot "MaterialEditor.rdb") -o $rawDir --filter ("*" + $texKey + "_*") --types g1t --flat 2>$null | Out-Null
            Convert-G1tDir $rawDir "*.g1t" $pd
            Remove-Item $rawDir -Recurse -Force -Confirm:$false -ErrorAction SilentlyContinue
        }
        Convert-G1tDir $matPath $texFilter $pd     # mod 贴图覆盖同名
        & $PythonExe (Join-Path $scripts "g1m_matmap.py") $g1mOut $ktidOut -o $mmOut | ForEach-Object { Write-Host "    $_" }
        # 有顶点的材质却没解析到 alb（mod 改了槽位 / ktid 不配套）-> 退回启发式
        $mmA = Get-Content $mmOut -Raw | ConvertFrom-Json
        $bad = @($mmA.submeshes | Where-Object { $_.vertexCount -gt 0 -and -not (@($_.textures | Where-Object { $_.channel -eq "alb" })).Count })
        if ($bad.Count -gt 0) {
            Write-Host "  [$kind $id] 路线 A 有 $($bad.Count) 个 submesh 没贴图，改用启发式" -ForegroundColor Yellow
            $haveKtid = $false
        }
    }
    if (-not $haveKtid) {
        Write-Host "  [$kind $id] 路线 B：启发式映射（预览不对用 -Assign 纠正）" -ForegroundColor Yellow
        Convert-G1tDir $matPath $texFilter $pd
        if ((Get-ChildItem (Join-Path $pd "_textures") -Filter "*.dds").Count -eq 0) { Convert-G1tDir $matPath "*.g1t" $pd }
        $extra = @("--key", $texKey)
        if ($Assign -and $kind -eq "COS") { $extra += @("--assign", $Assign) }
        # 注意：函数内的 stdout 会混进返回值，python 输出必须用 Write-Host 消费掉
        & $PythonExe (Join-Path $scripts "mod_matmap.py") $g1mOut $matPath $mmOut @extra | ForEach-Object { Write-Host "    $_" }
    }
    if ($LASTEXITCODE -ne 0) { throw "$id matmap 失败" }
    Convert-Png $pd
    return $pd
}

# 官方部件补位；mod 若带了它的贴图则复制一份叠上去
function Resolve-OfficialPart([string] $kind, [string] $num) {
    # $num 可以是编号（001）或完整部件名（AYA_FACE_001，用于跨角色 body swap 类 mod）
    $id = if ($num -match "_") { $num.ToUpper() } else { $Chr + "_" + $kind + "_" + $num }
    $texKey = ($id -replace "_", "")
    $src = Join-Path $OutRoot $id
    if (-not (Test-Path (Join-Path $src "matmap.json"))) {
        $inGame = & $PythonExe (Join-Path $scripts "extract_rdb.py") (Join-Path $GameRoot "CharacterEditor.rdb") --list --filter "$id.g1m" 2>$null | Select-String -Quiet ("^" + $id + "\.g1m")
        if (-not $inGame) {
            Write-Host "  [$kind] 本机游戏里没有 $id（角色是未安装的 DLC？），这部件留空" -ForegroundColor Yellow
            return $null
        }
        # 本机有但还没导出过 -> 现场导（模型+贴图+FBX，再做 matmap 与 PNG）
        Write-Host "  [$kind] 官方 $id 尚未导出，现在导出" -ForegroundColor Cyan
        & (Join-Path $scripts "export_character.ps1") $id -OutputRoot $OutRoot -Force | ForEach-Object { Write-Host "    $_" }
        if (-not (Test-Path (Join-Path $src ($id + ".fbx")))) { throw "官方部件 $id 导出失败" }
        & $PythonExe (Join-Path $scripts "g1m_matmap.py") (Join-Path $src ($id + ".g1m")) (Join-Path $src ($id + ".ktid")) -o (Join-Path $src "matmap.json") | ForEach-Object { Write-Host "    $_" }
        if ($LASTEXITCODE -ne 0) { throw "$id matmap 失败" }
        $null = New-Item -ItemType Directory -Force (Join-Path $src "_png")
        Convert-Png $src
    }
    $texFilter = "*_" + $texKey + "_*.g1t"
    $override = @(Get-ChildItem $matPath -Filter $texFilter -File | Where-Object { $_.Length -ge 200 })
    if ($override.Count -eq 0) {
        Write-Host "  [$kind] 官方 $id" -ForegroundColor DarkGray
        return $src
    }
    Write-Host "  [$kind] 官方 $id + mod 覆盖 $($override.Count) 张贴图" -ForegroundColor Green
    $pn = $Label + "_" + $kind.ToLower()
    $pd = Join-Path $OutRoot $pn
    if (Test-Path $pd) { Remove-Item $pd -Recurse -Force -Confirm:$false }
    $null = New-Item -ItemType Directory -Force (Join-Path $pd "_textures"), (Join-Path $pd "_png")
    Copy-Item (Join-Path $src ($id + ".fbx")) (Join-Path $pd ($pn + ".fbx"))
    Copy-Item (Join-Path $src "matmap.json") (Join-Path $pd "matmap.json")
    Copy-Item (Join-Path $src "_textures\*.dds") (Join-Path $pd "_textures\") -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $src "_png\*.png") (Join-Path $pd "_png\") -Force -ErrorAction SilentlyContinue
    $before = @{}
    Get-ChildItem (Join-Path $pd "_textures") -Filter "*.dds" | ForEach-Object { $before[$_.Name] = $_.LastWriteTimeUtc }
    Convert-G1tDir $matPath $texFilter $pd
    foreach ($d in (Get-ChildItem (Join-Path $pd "_textures") -Filter "*.dds")) {
        if (-not $before.ContainsKey($d.Name) -or $before[$d.Name] -ne $d.LastWriteTimeUtc) {
            $png = Join-Path $pd ("_png\" + $d.BaseName + ".png")
            if (Test-Path $png) { Remove-Item $png -Force }
        }
    }
    Convert-Png $pd
    return $pd
}

# 2) 逐部件处理，顺序 COS / FACE / HAIR
$partDirs = @()
$nums = @{ COS = $Cos; FACE = $Face; HAIR = $Hair }
foreach ($kind in @("COS", "FACE", "HAIR")) {
    if ($modParts.ContainsKey($kind)) {
        $partDirs += (Convert-ModPart $modParts[$kind] $kind)
    } else {
        $d = Resolve-OfficialPart $kind $nums[$kind]
        if ($d) { $partDirs += $d }
    }
}

# 3) 组装
$null = New-Item -ItemType Directory -Force (Join-Path $OutRoot "_blends")
$blend = Join-Path $OutRoot ("_blends\" + $Label + ".blend")
$prev = if ($NoPreview) { "-" } else { Join-Path $OutRoot ("_blends\" + $Label + "_preview.png") }
$log = Join-Path $OutRoot ("_blends\" + $Label + ".log")
& $BlenderExe --background --factory-startup --python (Join-Path $scripts "build_blend.py") -- $blend $prev @partDirs 2>&1 | ForEach-Object { "$_" } | Set-Content $log -Encoding UTF8
Get-Content $log | Select-String "SAVED_|PASS" | ForEach-Object { $_.Line }
if (-not (Test-Path $blend)) { Get-Content $log | Select-Object -Last 15; throw "blend 未生成（完整日志 $log）" }
Write-Host "OK $Label ($([math]::Round((Get-Item $blend).Length/1MB,1)) MB) -> $blend" -ForegroundColor Green
if (-not $NoPreview) { Write-Host "预览: $prev （皮肤/衣物贴图弄反时加 -Assign 重跑，材质号见上方 assign 输出）" }
