# DOA5LR 一键出带材质 .blend：TMC（封包内或外部 mod 文件）→ FBX+DDS → Blender 组装 + 预览
#
# 用法：
#   # A 官方内容：按名字从封包提取
#   .\export_full.ps1 KASUMI_DLC_011 -Archive chara_initial -Hair 001
#   .\export_full.ps1 HONOKA_COS_001 -Hair HONOKA_HAIR_002 -Label Honoka_战衣
#
#   # B 外部 mod：直接喂 .TMC 文件（同目录需有同名 .TMCL 贴图库）
#   .\export_full.ps1 -TmcFile D:\mods\KasumiNude.TMC -Label KAS_Nude
#   .\export_full.ps1 -TmcFile D:\mods\body.TMC -HairTmc D:\mods\hair.TMC -Label X
#   # 也可混用：mod 身体 + 官方发型
#   .\export_full.ps1 KASUMI_DLC_011 -TmcFile D:\mods\nude.TMC -Hair 001 -Label KAS_Nude
#
# DOA5LR 的服装 TMC 已含身体+脸+贴图（FBX 自带材质连接，不需要材质映射），
# 但**头发是独立 TMC**（<角色>_HAIR_00N），不加 -Hair/-HairTmc 出来是光头。
# -Hair 可给编号（001）或完整名（KASUMI_HAIR_001）；不确定有哪些用：
#   python extract_lnk.py "<游戏>\chara_initial.bin" --list --filter "KASUMI_HAIR*"
#
# 产物：<OutRoot>\_blends\<Label>.blend + <Label>_preview.png

param(
    [Parameter(Position = 0)] [string] $Name = "",
    [string] $TmcFile = "",
    [string] $HairTmc = "",
    [string] $FaceTmc = "",
    [string] $Face = "",
    [string] $Archive = "chara_common",
    [string] $Label = "",
    [string] $Hair = "",
    [string] $GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 5 Last Round",
    [string] $OutRoot = "D:\doa5lr_exports",
    [string] $PythonExe = "D:\openclaw\python\python.exe",
    [string] $NoesisExe = "E:\tools\noesisv\Noesis.exe",
    [string] $BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [switch] $Force,
    [switch] $NoPreview
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Name -and -not $TmcFile) { throw "需要给出角色/服装名，或用 -TmcFile 指定外部 .TMC" }
if ($Name) { $Name = $Name.ToUpper() }
if (-not $Label) {
    $Label = if ($TmcFile) { [IO.Path]::GetFileNameWithoutExtension($TmcFile) } else { $Name }
}
$blendDir = Join-Path $OutRoot "_blends"
$null = New-Item -ItemType Directory -Force $blendDir
$outBlend = Join-Path $blendDir "$Label.blend"
$outPrev = Join-Path $blendDir "$Label`_preview.png"

if ((Test-Path $outBlend) -and -not $Force) {
    Write-Host "SKIP: $outBlend 已存在（-Force 覆盖）" -ForegroundColor Yellow
    return
}

# --- 部件来源：外部 TMC 文件 ---
function New-PartFromTmc([string] $tmcPath) {
    if (-not (Test-Path $tmcPath)) { throw "找不到 TMC：$tmcPath" }
    # 允许传目录：取其中第一个 .TMC
    if ((Get-Item $tmcPath).PSIsContainer) {
        $found = Get-ChildItem $tmcPath -Recurse -File | Where-Object { $_.Extension -ieq ".tmc" } | Select-Object -First 1
        if (-not $found) { throw "目录里没有 .TMC：$tmcPath" }
        $tmcPath = $found.FullName
    }
    $src = Get-Item $tmcPath
    $base = [IO.Path]::GetFileNameWithoutExtension($src.Name)
    $pd = Join-Path $OutRoot "_mods\$base"
    if (Test-Path $pd) { Remove-Item $pd -Recurse -Force -Confirm:$false }
    $null = New-Item -ItemType Directory -Force $pd

    Copy-Item $src.FullName (Join-Path $pd "$base.TMC") -Force
    # 贴图库：同目录同名 .TMCL（扩展名大小写不定）
    $tmcl = Get-ChildItem $src.DirectoryName -File | Where-Object {
        $_.Extension -ieq ".tmcl" -and [IO.Path]::GetFileNameWithoutExtension($_.Name) -ieq $base
    } | Select-Object -First 1
    if ($tmcl) {
        Copy-Item $tmcl.FullName (Join-Path $pd "$base.TMCL") -Force
    } else {
        Write-Host "  WARN: 同目录找不到 $base.TMCL，模型会是白模" -ForegroundColor Yellow
    }

    & $NoesisExe ?cmode (Join-Path $pd "$base.TMC") (Join-Path $pd "$base.fbx") | Out-Null
    if (-not (Test-Path (Join-Path $pd "$base.fbx"))) { throw "TMC 转 FBX 失败：$($src.FullName)" }
    Write-Host "外部 TMC: $($src.Name) -> $pd" -ForegroundColor Cyan
    return $pd
}

# --- 部件来源：封包内按名字提取 ---
function New-PartFromArchive([string] $entryName) {
    # 注意：内部脚本的 stdout 必须消费掉，否则会混进本函数的返回值（$partDirs 会脏）
    & (Join-Path $scriptDir "export_character.ps1") $entryName -Archive $Archive -OutputRoot $OutRoot -Force |
        ForEach-Object { Write-Host $_ }
    $pd = Join-Path $OutRoot "$entryName\$entryName"
    if (-not (Test-Path (Join-Path $pd "$entryName.fbx"))) {
        # export_character.ps1 按 TMC 名建子目录；名字匹配多套时取第一个含 FBX 的
        $cand = Get-ChildItem (Join-Path $OutRoot $entryName) -Directory -ErrorAction SilentlyContinue |
            Where-Object { Get-ChildItem $_.FullName -Filter "*.fbx" -ErrorAction SilentlyContinue } |
            Select-Object -First 1
        if (-not $cand) { throw "没有生成 FBX：$entryName（检查名字/封包，用 extract_lnk.py --list --filter 查）" }
        $pd = $cand.FullName
    }
    Write-Host "部件目录: $pd" -ForegroundColor Cyan
    return $pd
}

# 组装顺序必须是 服装 → 脸 → 头发：
# 服装是对齐基准；脸在身体坐标系里就位后充当头部锚点；头发再挪到锚点顶部。
$partDirs = @()
if ($TmcFile) { $partDirs += New-PartFromTmc $TmcFile }
elseif ($Name) { $partDirs += New-PartFromArchive $Name }

# 脸：DOA5LR 的 COS 系服装不含头部，需要单独的 <角色>_FACE
if ($FaceTmc) {
    $partDirs += New-PartFromTmc $FaceTmc
} elseif ($Face) {
    # 脸 TMC 没有编号（就叫 <角色>_FACE）：给完整名就用完整名，
    # 给任意占位值（auto/yes/1…）就按角色名推导
    $faceName = if ($Face -match '_') { $Face.ToUpper() } else {
        if (-not $Name) { throw "-Face 需要同时给出角色名，或改用 -FaceTmc 指定文件" }
        ($Name -split '_')[0] + "_FACE"
    }
    $partDirs += New-PartFromArchive $faceName
}

if ($HairTmc) {
    $partDirs += New-PartFromTmc $HairTmc
} elseif ($Hair) {
    $hairName = if ($Hair -match '^[A-Za-z]') { $Hair.ToUpper() } else {
        if (-not $Name) { throw "-Hair 用编号时需要同时给出角色名（或改用 -HairTmc 指定文件）" }
        ($Name -split '_')[0] + "_HAIR_$Hair"
    }
    $partDirs += New-PartFromArchive $hairName
}

# DDS → PNG（Blender 读不了部分 BC 格式，预转同名 PNG 供组装脚本优先使用）
foreach ($pd in $partDirs) {
    $dds = Get-ChildItem $pd -Filter "*.dds" -File
    foreach ($d in $dds) {
        $png = Join-Path $pd ($d.BaseName + ".png")
        if (-not (Test-Path $png)) { & $NoesisExe ?cmode $d.FullName $png | Out-Null }
    }
    Write-Host "  贴图: $($dds.Count) DDS -> $((Get-ChildItem $pd -Filter '*.png').Count) PNG"
}

# Blender 组装 + 预览
$prevArg = if ($NoPreview) { "-" } else { $outPrev }
& $BlenderExe --background --factory-startup --python (Join-Path $scriptDir "build_blend.py") -- $outBlend $prevArg @partDirs 2>$null |
    Select-String "FBX_IMPORTED|PART_ALIGNED|SCALE_NORMALIZED|MATERIALS_REBUILT|IMAGES_PACKED|SAVED_|PASS|Traceback" | ForEach-Object { $_.Line }
if (-not (Test-Path $outBlend)) { throw "blend 未生成：$Label" }
Write-Host "OK $Label ($([math]::Round((Get-Item $outBlend).Length / 1MB, 1)) MB) -> $outBlend" -ForegroundColor Green
