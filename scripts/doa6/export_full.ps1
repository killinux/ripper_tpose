# DOA6 完整角色一键导出：三部件提取 -> 材质映射 -> PNG -> 组装带贴图 .blend + 预览图
#
# 用法：
#   .\export_full.ps1 KAS                        # 默认 COS_001/HAIR_001/FACE_001
#   .\export_full.ps1 MOM -Cos 002 -Hair 003     # 指定部件编号
#   .\export_full.ps1 KAS -Label KAS_Kasumi      # 输出文件名 KAS_Kasumi.blend
#
# 产物：<OutRoot>\_blends\<Label>.blend + <Label>_preview.png
# 依赖：export_character.ps1 / g1m_matmap.py / build_blend.py（同目录）、
#       D:\doa6_exports\_objdb\*.kidssingletondb（首次需先解出，见 README §3.5）

param(
    [Parameter(Position = 0, Mandatory = $true)] [string] $Chr,
    [string] $Cos = "001",
    [string] $Hair = "001",
    [string] $Face = "001",
    [string] $Label = "",
    [string] $OutRoot = "D:\doa6_exports",
    [string] $PythonExe = "D:\openclaw\python\python.exe",
    [string] $NoesisExe = "E:\tools\noesisv\Noesis64.exe",
    [string] $BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [switch] $Force,
    [switch] $NoPreview
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Chr = $Chr.ToUpper()
if (-not $Label) { $Label = $Chr + "_full" }
$parts = @("$($Chr)_COS_$Cos", "$($Chr)_HAIR_$Hair", "$($Chr)_FACE_$Face")
$blendDir = Join-Path $OutRoot "_blends"
$null = New-Item -ItemType Directory -Force $blendDir
$outBlend = Join-Path $blendDir "$Label.blend"
$outPrev = Join-Path $blendDir "$Label`_preview.png"

if ((Test-Path $outBlend) -and -not $Force) {
    Write-Host "SKIP: $outBlend 已存在（-Force 覆盖）" -ForegroundColor Yellow
    return
}

# ① 三部件：模型+配套+贴图 DDS + FBX
& (Join-Path $scriptDir "export_character.ps1") $parts -OutputRoot $OutRoot -Force:$Force
foreach ($p in $parts) {
    if (-not (Test-Path (Join-Path $OutRoot "$p\$p.fbx"))) { throw "部件缺 FBX：$p（检查编号是否存在，用 extract_rdb.py --list --filter '$($Chr)_*' 查）" }
}

# ② 每部件材质映射 + ③ alb/nmh 转 PNG
foreach ($p in $parts) {
    $pd = Join-Path $OutRoot $p
    & $PythonExe (Join-Path $scriptDir "g1m_matmap.py") "$pd\$p.g1m" "$pd\$p.ktid" -o "$pd\matmap.json"
    if ($LASTEXITCODE -ne 0) { throw "matmap 失败：$p" }
    $mm = Get-Content "$pd\matmap.json" -Raw | ConvertFrom-Json
    $texNames = $mm.submeshes | ForEach-Object { $_.textures } | Where-Object { $_.channel -in @("alb", "nmh") } | ForEach-Object { $_.name } | Sort-Object -Unique
    $pngDir = Join-Path $pd "_png"
    $null = New-Item -ItemType Directory -Force $pngDir
    foreach ($t in $texNames) {
        $dds = Join-Path "$pd\_textures" ($t -replace '\.g1t$', '.dds')
        $png = Join-Path $pngDir (($t -replace '\.g1t$', '') + ".png")
        if ((Test-Path $dds) -and -not (Test-Path $png)) { & $NoesisExe ?cmode $dds $png | Out-Null }
    }
    $made = (Get-ChildItem $pngDir -Filter "*.png" -ErrorAction SilentlyContinue).Count
    Write-Host "  $p : $made/$($texNames.Count) PNG"
}

# ④ 组装 .blend + 预览
$prevArg = if ($NoPreview) { "-" } else { $outPrev }
$partDirs = $parts | ForEach-Object { Join-Path $OutRoot $_ }
& $BlenderExe --background --factory-startup --python (Join-Path $scriptDir "build_blend.py") -- $outBlend $prevArg @partDirs 2>$null | Select-String "SAVED_|PASS|Traceback" | ForEach-Object { $_.Line }
if (-not (Test-Path $outBlend)) { throw "blend 未生成：$Label" }
$sz = [math]::Round((Get-Item $outBlend).Length / 1MB, 1)
Write-Host "OK $Label : $outBlend ($sz MB)" -ForegroundColor Green
