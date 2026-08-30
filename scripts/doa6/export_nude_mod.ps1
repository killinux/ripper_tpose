# DOA6 nude/mod 变体一键导出：REDELBE layer2 mod（zip 或目录）→ 带材质 .blend + 预览
#
# 与 export_full.ps1（官方服装）互补：本脚本吃社区 mod 的服装 g1m/g1t，
# 自动接上本机已导出的官方发型/脸（默认 <CHR>_HAIR_001 / <CHR>_FACE_001，
# 需先跑过 export_full.ps1 <CHR> 或单独导出这两个部件）。
#
# 两条材质路线自动选择：
#   A 精确：mod 替换的服装编号在本机游戏数据里（如 HEL_COS_001）→ 原版 ktid 链
#     （g1m_matmap.py），mod 贴图覆盖原版同名底图。
#   B 启发式：替换的是未安装 DLC（如 MOM_COS_105）→ mod_matmap.py 按网格大小
#     分配部位。皮肤/衣物弄反时用 -Assign "3=body,5=f01" 纠正后重跑。
#
# 用法：
#   .\export_nude_mod.ps1 <mod.zip 或已解压目录> -Chr HEL -Label HEL_Helena_Nude
#   .\export_nude_mod.ps1 D:\mods\x.zip -Chr AYA -Label AYA_Malf -Assign "3=f01,5=body"

param(
    [Parameter(Position = 0, Mandatory = $true)] [string] $Mod,
    [Parameter(Mandatory = $true)] [string] $Chr,
    [Parameter(Mandatory = $true)] [string] $Label,
    [string] $Hair = "001",
    [string] $Face = "001",
    [string] $Assign = "",
    [string] $OutRoot = "D:\doa6_exports",
    [string] $GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 6",
    [string] $PythonExe = "D:\openclaw\python\python.exe",
    [string] $NoesisExe = "E:\tools\noesisv\Noesis64.exe",
    [string] $BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
)

$ErrorActionPreference = "Stop"
$scripts = Split-Path -Parent $MyInvocation.MyCommand.Path
$Chr = $Chr.ToUpper()

# 0) mod 解包/定位 Character\*.g1m 与 Material\
$modDir = $Mod
if ($Mod -match '\.zip$') {
    $modDir = Join-Path $env:TEMP ("doa6mod_" + [IO.Path]::GetFileNameWithoutExtension($Mod))
    if (Test-Path $modDir) { Remove-Item $modDir -Recurse -Force -Confirm:$false }
    Expand-Archive $Mod -DestinationPath $modDir -Force
}
$g1m = Get-ChildItem $modDir -Recurse -Filter "*.g1m" | Where-Object { $_.Directory.Name -eq "Character" } | Select-Object -First 1
if (-not $g1m) { $g1m = Get-ChildItem $modDir -Recurse -Filter "*.g1m" | Select-Object -First 1 }
if (-not $g1m) { throw "mod 里没有 g1m" }
$matDir = Get-ChildItem $modDir -Recurse -Directory -Filter "Material" | Select-Object -First 1
if (-not $matDir) { throw "mod 里没有 Material 目录" }
$cosId = $g1m.BaseName
Write-Host "mod 服装: $cosId  贴图: $((Get-ChildItem $matDir.FullName -Filter '*.g1t').Count) 个 g1t" -ForegroundColor Cyan

# 1) 部件目录 + FBX
$pd = Join-Path $OutRoot "$Label`_cos"
if (Test-Path $pd) { Remove-Item $pd -Recurse -Force -Confirm:$false }
$null = New-Item -ItemType Directory -Force "$pd\_textures", "$pd\_png"
Copy-Item $g1m.FullName "$pd\$Label`_cos.g1m"
& $NoesisExe ?cmode "$pd\$Label`_cos.g1m" "$pd\$Label`_cos.fbx" | Out-Null
if (-not (Test-Path "$pd\$Label`_cos.fbx")) { throw "mod g1m 转 FBX 失败" }

function Convert-G1tDir([string] $srcDir, [string] $filter) {
    foreach ($g in (Get-ChildItem $srcDir -Filter $filter -ErrorAction SilentlyContinue)) {
        if ($g.Length -lt 200) { continue }
        $sub = "$pd\_conv"
        $null = New-Item -ItemType Directory -Force $sub
        & $NoesisExe ?cmode $g.FullName "$sub\t.dds" | Out-Null
        $dds = Get-ChildItem $sub -Filter "*.dds"
        if ($dds.Count -eq 1) { Move-Item $dds[0].FullName "$pd\_textures\$($g.BaseName).dds" -Force }
        Remove-Item $sub -Recurse -Force -Confirm:$false
    }
}

# 2) 判断路线：原版 ktid 是否可得
$ktidLocal = Join-Path $OutRoot "$cosId\$cosId.ktid"
$haveKtid = Test-Path $ktidLocal
if (-not $haveKtid) {
    & $PythonExe "$scripts\extract_rdb.py" "$GameRoot\CharacterEditor.rdb" -o $pd --filter "$cosId.ktid" --flat 2>$null | Out-Null
    if (Test-Path "$pd\$cosId.ktid") { $ktidLocal = "$pd\$cosId.ktid"; $haveKtid = $true }
}

if ($haveKtid) {
    Write-Host "路线 A：原版 ktid 链（精确映射）" -ForegroundColor Green
    Copy-Item $ktidLocal "$pd\$Label`_cos.ktid" -Force
    # 原版全套贴图打底（本地部件目录有就复制；否则从 MaterialEditor 抽）
    $baseTex = Join-Path $OutRoot "$cosId\_textures"
    if (Test-Path $baseTex) {
        Copy-Item "$baseTex\*.dds" "$pd\_textures\" -Force -ErrorAction SilentlyContinue
    } else {
        $texKey = ($cosId -replace "_", "")
        $rawDir = "$pd\_g1t_base"
        & $PythonExe "$scripts\extract_rdb.py" "$GameRoot\MaterialEditor.rdb" -o $rawDir --filter "*$texKey`_*" --types g1t --flat 2>$null | Out-Null
        Convert-G1tDir $rawDir "*.g1t"
    }
    Convert-G1tDir $matDir.FullName "*.g1t"   # mod 贴图覆盖同名
    & $PythonExe "$scripts\g1m_matmap.py" "$pd\$Label`_cos.g1m" "$pd\$Label`_cos.ktid" -o "$pd\matmap.json"
} else {
    Write-Host "路线 B：未安装 $cosId 对应 DLC，用启发式映射（预览不对用 -Assign 纠正）" -ForegroundColor Yellow
    Convert-G1tDir $matDir.FullName "*.g1t"
    $assignArg = @()
    if ($Assign) { $assignArg = @("--assign", $Assign) }
    & $PythonExe "$scripts\mod_matmap.py" "$pd\$Label`_cos.g1m" $matDir.FullName "$pd\matmap.json" @assignArg
}
if ($LASTEXITCODE -ne 0) { throw "matmap 失败" }

# 3) alb/nmh -> PNG
$mm = Get-Content "$pd\matmap.json" -Raw | ConvertFrom-Json
$texNames = $mm.submeshes | ForEach-Object { $_.textures } | Where-Object { $_.channel -in @("alb", "nmh") } | ForEach-Object { $_.name } | Sort-Object -Unique
foreach ($t in $texNames) {
    $dds = "$pd\_textures\" + ($t -replace '\.g1t$', '.dds')
    $png = "$pd\_png\" + (($t -replace '\.g1t$', '') + ".png")
    if ((Test-Path $dds) -and -not (Test-Path $png)) { & $NoesisExe ?cmode $dds $png | Out-Null }
}
Write-Host "  PNG: $((Get-ChildItem "$pd\_png" -Filter '*.png').Count)/$($texNames.Count)"

# 4) 组装（官方发型/脸）
foreach ($need in @("$Chr`_HAIR_$Hair", "$Chr`_FACE_$Face")) {
    if (-not (Test-Path (Join-Path $OutRoot "$need\matmap.json"))) {
        throw "缺部件 $need（先跑 .\export_full.ps1 $Chr 或单独导出）"
    }
}
$blend = Join-Path $OutRoot "_blends\$Label.blend"
$prev = Join-Path $OutRoot "_blends\$Label`_preview.png"
& $BlenderExe --background --factory-startup --python "$scripts\build_blend.py" -- $blend $prev $pd (Join-Path $OutRoot "$Chr`_HAIR_$Hair") (Join-Path $OutRoot "$Chr`_FACE_$Face") 2>$null | Select-String "SAVED_|PASS" | ForEach-Object { $_.Line }
if (-not (Test-Path $blend)) { throw "blend 未生成" }
Write-Host "OK $Label ($([math]::Round((Get-Item $blend).Length/1MB,1)) MB) -> $blend" -ForegroundColor Green
Write-Host "预览: $prev （皮肤/衣物贴图弄反时加 -Assign 重跑，材质号见上方 assign 输出）"
