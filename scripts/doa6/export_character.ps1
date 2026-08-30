# DOA6 角色批量导出：.rdb -> G1M/G1T -> FBX + DDS
#
# 用法：
#   .\export_character.ps1 -List                    # 列出 CharacterEditor 全部 g1m
#   .\export_character.ps1 HON_COS_001              # 单套服装：模型+贴图+FBX
#   .\export_character.ps1 HON_COS_001,KAS_COS_002
#   .\export_character.ps1 HON_HAIR_001 -NoTextures # 发型多数没有 MaterialEditor 贴图
#
# 命名规则：模型/配套在 CharacterEditor.rdb 里叫 HON_COS_001.*；
# 服装贴图在 MaterialEditor.rdb 里叫 *HONCOS001_*（去下划线拼接），脚本自动换算。
# 依赖：extract_rdb.py（同目录）、E:\tools\doa6\cethleann\filelist-*.csv（文件名映射）、
#       Noesis64 + plugins\x64\ProjectG1M.dll（g1m->FBX、g1t->DDS）。

param(
    [Parameter(Position = 0)] [string[]] $Names,
    [string] $GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 6",
    [string] $OutputRoot = "D:\doa6_exports",
    [string] $PythonExe = "D:\openclaw\python\python.exe",
    [string] $NoesisExe = "E:\tools\noesisv\Noesis64.exe",
    [switch] $List,
    [switch] $NoConvert,
    [switch] $NoTextures,
    [switch] $Force
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$extractPy = Join-Path $scriptDir "extract_rdb.py"
$charRdb = Join-Path $GameRoot "CharacterEditor.rdb"
$matRdb = Join-Path $GameRoot "MaterialEditor.rdb"

if (-not (Test-Path $extractPy)) { throw "extract_rdb.py not found next to this script" }
if (-not (Test-Path $charRdb)) { throw "not found: $charRdb" }

if ($List) {
    & $PythonExe $extractPy $charRdb --list --types g1m
    return
}
if (-not $Names) { throw "请给出服装/部件名（如 HON_COS_001），或用 -List 查看" }

foreach ($name in $Names) {
    $name = $name.ToUpper()
    $outDir = Join-Path $OutputRoot $name
    if ((Test-Path $outDir) -and -not $Force) {
        Write-Host "SKIP $name (已存在，-Force 覆盖)" -ForegroundColor Yellow
        continue
    }
    if (Test-Path $outDir) { Remove-Item $outDir -Recurse -Force -Confirm:$false }
    $null = New-Item -ItemType Directory -Force $outDir

    Write-Host "== $name : CharacterEditor 模型/配套 ==" -ForegroundColor Cyan
    & $PythonExe $extractPy $charRdb -o $outDir --filter "$name.*" --flat
    if ($LASTEXITCODE -ne 0) { throw "extract_rdb.py failed for $name" }

    if (-not $NoTextures -and (Test-Path $matRdb)) {
        # HON_COS_001 -> *HONCOS001_*（MaterialEditor 贴图命名不带下划线）
        $texKey = ($name -replace "_", "")
        $texDir = Join-Path $outDir "_textures"
        Write-Host "== $name : MaterialEditor 贴图 (*$texKey*) ==" -ForegroundColor Cyan
        & $PythonExe $extractPy $matRdb -o $texDir --filter "*${texKey}_*" --types g1t --flat
    }

    if (-not $NoConvert) {
        foreach ($g1m in (Get-ChildItem $outDir -Filter "*.g1m" -File)) {
            $fbx = Join-Path $outDir ($g1m.BaseName + ".fbx")
            Write-Host "  Noesis: $($g1m.Name) -> FBX"
            & $NoesisExe ?cmode $g1m.FullName $fbx | Out-Null
            if (-not (Test-Path $fbx)) { Write-Host "  WARN: $($g1m.Name) 转换失败" -ForegroundColor Yellow }
        }
        $texDir = Join-Path $outDir "_textures"
        if (Test-Path $texDir) {
            foreach ($g1t in (Get-ChildItem $texDir -Filter "*.g1t" -File)) {
                # ProjectG1M 把 g1t 内的每张图导成 <索引>.dds，先进子目录再改名防互相覆盖
                $sub = Join-Path $texDir $g1t.BaseName
                $null = New-Item -ItemType Directory -Force $sub
                Move-Item $g1t.FullName $sub
                $inPath = Join-Path $sub $g1t.Name
                & $NoesisExe ?cmode $inPath (Join-Path $sub "tex.dds") | Out-Null
                $dds = Get-ChildItem $sub -Filter "*.dds" -File
                if ($dds.Count -eq 1) {
                    Move-Item $dds[0].FullName (Join-Path $texDir ($g1t.BaseName + ".dds"))
                    Remove-Item $sub -Recurse -Force -Confirm:$false
                }
            }
        }
    }
    Write-Host "完成 -> $outDir" -ForegroundColor Green
}
