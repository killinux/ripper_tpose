# FF7 Remake INTERGRADE：官方 Player 主模型批量导出 -> 带贴图 .blend + 预览 + 报告
#
# 两段流程串起来：
#   ① ff7remake_export.ps1（umodel 逐包提取 PSKX + PNG + .mat，需要 AES key）
#   ② validate_ff7remake_model.py（Blender 3.6 导入 PSKX、按 .mat 接贴图、渲预览、写报告）
#
# 用法：
#   $env:FF7REMAKE_AES_KEY = '<key>'          # 只放本机环境变量，不要写进仓库
#   .\export_ff7remake_models.ps1                # 清单里全部 36 个包（docs\ff7remake-player-model-files.txt）
#   .\export_ff7remake_models.ps1 -Only PC0002   # 只要 Tifa 系
#   .\export_ff7remake_models.ps1 -SkipExtract -Lane 1 -Lanes 3   # 已提取过，只做材质化，三路并行之一
#   .\export_ff7remake_models.ps1 -List
#
# 产物：<OutputRoot>\_blends\<PC0002_01_Tifa_PurpleDress>.blend / _preview.png / .json
# 提取物：<OutputRoot>\GameContents\Character\Player\<包目录>\{Model,Texture,Material}\
#         （所有包共用一个根，Common 的眼/口贴图只提取一次）

param(
    [string] $ListFile = "",
    [string[]] $Only = @(),
    [string] $OutputRoot = "D:\ff7remake_exports\player",
    [string] $AesKey = $env:FF7REMAKE_AES_KEY,
    [string] $BlenderExe = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe",
    [int] $Lane = 0,
    [int] $Lanes = 1,
    [switch] $SkipExtract,
    [switch] $NoPreview,
    [switch] $Force,
    [switch] $List
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ListFile) { $ListFile = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "docs\ff7remake-player-model-files.txt" }
if (-not (Test-Path $ListFile)) { throw "找不到清单：$ListFile" }

# 清单：每行一个 Unreal 包路径，末段 PCxxxx_yy.uasset，倒数第三段是包目录名（含角色与服装名）
$packages = @()
foreach ($line in (Get-Content $ListFile)) {
    $line = $line.Trim()
    if (-not $line -or $line.StartsWith("#")) { continue }
    $parts = $line -split "/"
    $folder = $parts[$parts.Count - 3]
    $id = [IO.Path]::GetFileNameWithoutExtension($parts[$parts.Count - 1])
    if ($Only.Count -gt 0 -and -not ($Only | Where-Object { $folder -like "*$_*" })) { continue }
    $packages += [pscustomobject]@{ path = $line; folder = $folder; id = $id }
}
if ($List) { $packages | Format-Table folder, id, path -AutoSize; return }
if ($packages.Count -eq 0) { throw "清单里没有匹配的包" }

$blendDir = Join-Path $OutputRoot "_blends"
$null = New-Item -ItemType Directory -Force $blendDir
$playerRoot = Join-Path $OutputRoot "GameContents\Character\Player"

# ① 提取（一次性把所有包交给 ff7remake_export.ps1，它负责隔离 ~mods 与 AES 临时文件）
if (-not $SkipExtract) {
    $todo = @($packages | Where-Object {
        $Force -or -not (Get-ChildItem (Join-Path $playerRoot "$($_.folder)\Model") -Filter "$($_.id).psk*" -ErrorAction SilentlyContinue)
    })
    if ($todo.Count -gt 0) {
        Write-Host "== 提取 $($todo.Count) 个包 -> $OutputRoot ==" -ForegroundColor Cyan
        & (Join-Path $scriptDir "ff7remake_export.ps1") -Package @($todo.path) -OutputRoot $OutputRoot -AesKey $AesKey |
            ForEach-Object { Write-Host $_ }
    } else {
        Write-Host "提取物已齐全，跳过 umodel（-Force 重提）" -ForegroundColor DarkGray
    }
}

# ② 材质化（按 -Lane/-Lanes 取子集，便于多开并行）
$i = -1
$ok = 0; $fail = @()
foreach ($p in $packages) {
    $i++
    if (($i % $Lanes) -ne $Lane) { continue }
    $label = $p.folder
    $blend = Join-Path $blendDir "$label.blend"
    if ((Test-Path $blend) -and -not $Force) { Write-Host "SKIP $label（已存在）" -ForegroundColor DarkGray; $ok++; continue }
    $pkgDir = Join-Path $playerRoot $label
    $model = Get-ChildItem (Join-Path $pkgDir "Model") -Filter "$($p.id).psk*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $model) { Write-Host "FAIL $label：没有提取出 PSK（$pkgDir\Model）" -ForegroundColor Red; $fail += $label; continue }
    $matDir = Join-Path $pkgDir "Material"
    if (-not (Test-Path $matDir)) { Write-Host "FAIL $label：没有 Material 目录" -ForegroundColor Red; $fail += $label; continue }
    $prev = if ($NoPreview) { "" } else { Join-Path $blendDir "$label`_preview.png" }
    $report = Join-Path $blendDir "$label.json"
    $log = Join-Path $blendDir "$label.log"
    $t0 = Get-Date
    $args = @("--background", "--python", (Join-Path $scriptDir "enable_psk_addon.py"),
              "--python", (Join-Path $scriptDir "validate_ff7remake_model.py"), "--",
              "--model", $model.FullName, "--asset-root", (Join-Path $OutputRoot "GameContents"),
              "--material-dir", $matDir, "--output", $blend, "--report", $report)
    if ($prev) { $args += @("--render", $prev) }
    & $BlenderExe @args 2>&1 | ForEach-Object { "$_" } | Set-Content $log -Encoding UTF8
    if (Test-Path $blend) {
        $sec = [int]((Get-Date) - $t0).TotalSeconds
        $miss = ""
        if (Test-Path $report) {
            $r = Get-Content $report -Raw | ConvertFrom-Json
            if ($r.missing_preview_textures.Count -gt 0) { $miss = "  缺贴图 $($r.missing_preview_textures.Count)" }
        }
        Write-Host "OK $label ($([math]::Round((Get-Item $blend).Length/1MB,1)) MB, ${sec}s)$miss" -ForegroundColor Green
        $ok++
    } else {
        Write-Host "FAIL $label（日志 $log）" -ForegroundColor Red
        Get-Content $log | Select-Object -Last 8 | ForEach-Object { Write-Host "    $_" }
        $fail += $label
    }
}
Write-Host "== lane $Lane/$Lanes：成功 $ok，失败 $($fail.Count) $(if ($fail) { '-> ' + ($fail -join ', ') }) ==" -ForegroundColor Cyan
