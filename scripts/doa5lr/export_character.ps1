# DOA5LR 角色批量导出：.bin/.lnk -> TMC/TMCL -> FBX + DDS 贴图
#
# 用法：
#   .\export_character.ps1 -List                       # 列出 chara_common 全部条目
#   .\export_character.ps1 HONOKA                      # 提取+转换 HONOKA 全部服装
#   .\export_character.ps1 HONOKA_COS_001,KASUMI_COS_002
#   .\export_character.ps1 HONOKA -NoConvert           # 只提取 TMC/TMCL 不转 FBX
#
# 依赖：extract_lnk.py（同目录）、E:\tools\doa5lr\{doaKey,file5lr.dat}、
#       Noesis + doa5pc_custom.py 插件（TMC->FBX，自动读同目录 TMCL 出 DDS）。

param(
    [Parameter(Position = 0)] [string[]] $Names,
    [string] $GameRoot = "D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 5 Last Round",
    [string] $Archive = "chara_common",
    [string] $OutputRoot = "D:\doa5lr_exports",
    [string] $PythonExe = "D:\openclaw\python\python.exe",
    [string] $NoesisExe = "E:\tools\noesisv\Noesis.exe",
    [switch] $List,
    [switch] $NoConvert,
    [switch] $Force
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$extractPy = Join-Path $scriptDir "extract_lnk.py"
$binPath = Join-Path $GameRoot "$Archive.bin"

if (-not (Test-Path $extractPy)) { throw "extract_lnk.py not found next to this script" }
if (-not (Test-Path $binPath)) { throw "archive not found: $binPath" }

if ($List) {
    & $PythonExe $extractPy $binPath --list
    return
}
if (-not $Names) { throw "请给出角色/文件名前缀（如 HONOKA 或 HONOKA_COS_001），或用 -List 查看" }

foreach ($name in $Names) {
    $outDir = Join-Path $OutputRoot $name.ToUpper()
    if ((Test-Path $outDir) -and -not $Force) {
        Write-Host "SKIP $name (已存在，-Force 覆盖)" -ForegroundColor Yellow
        continue
    }
    if (Test-Path $outDir) { Remove-Item $outDir -Recurse -Force -Confirm:$false }
    $null = New-Item -ItemType Directory -Force $outDir

    Write-Host "== 提取 $name*.TMC/TMCL <- $Archive ==" -ForegroundColor Cyan
    & $PythonExe $extractPy $binPath -o $outDir --filter "$name*.TMC*"
    if ($LASTEXITCODE -ne 0) { throw "extract_lnk.py failed for $name" }

    $tmcs = Get-ChildItem $outDir -Filter "*.TMC" -File
    if (-not $tmcs) {
        Write-Host "WARN: $name 没有匹配到 TMC 条目" -ForegroundColor Yellow
        continue
    }

    if (-not $NoConvert) {
        foreach ($tmc in $tmcs) {
            # 每套服装单独子目录，Noesis 会把 TMCL 贴图解成同目录 DDS
            $costume = [System.IO.Path]::GetFileNameWithoutExtension($tmc.Name)
            $costumeDir = Join-Path $outDir $costume
            $null = New-Item -ItemType Directory -Force $costumeDir
            Move-Item $tmc.FullName $costumeDir
            $tmcl = Join-Path $outDir "$costume.TMCL"
            if (Test-Path $tmcl) { Move-Item $tmcl $costumeDir }
            $tmcPath = Join-Path $costumeDir $tmc.Name
            $fbxPath = Join-Path $costumeDir "$costume.fbx"
            Write-Host "  Noesis: $costume.TMC -> FBX"
            & $NoesisExe ?cmode $tmcPath $fbxPath | Out-Null
            if (-not (Test-Path $fbxPath)) {
                Write-Host "  WARN: $costume FBX 未生成（无 TMCL 或插件不识别）" -ForegroundColor Yellow
            }
        }
    }
    Write-Host "完成 -> $outDir" -ForegroundColor Green
}
