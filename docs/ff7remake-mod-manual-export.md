# FINAL FANTASY VII REMAKE Mod 模型手动导出到 Blender 3.6

本文记录已经在本机验证成功的 Remake Intergrade Mod 导出流程。它适用于 Mod `.pak`
覆盖了角色 `SkeletalMesh`、而 Remake 专用 UE Viewer 能保存原始包却不能直接导出该网格的
情况。

本文以已经安装的 Tifa Mod 为例：

```text
D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE\
└─ End\Content\Paks\~mods\zzTifaNudeNatural_V8_SF3D.pak
```

最终验证结果：

| 项目 | 结果 |
|---|---:|
| 主体网格 | 356,320 顶点 / 587,370 面 |
| 独立手套 | 14,526 顶点 / 19,634 面 |
| 合并后 | 370,846 顶点 / 607,004 面 |
| 主体骨架 | 481 骨骼 |
| Blender | 3.6.15 |
| 材质槽 | 主体 10 / 手套 2 |
| 外部图像 | 16 个实际使用、0 个缺失 |

> 不要把 AES key、游戏原始资产、Mod 资产或导出的贴图提交到 Git。仓库只保存说明、脚本和
> 补丁。只处理自己有权访问的本机游戏与 Mod。

## 1. 为什么不能直接使用普通导出流程

原版 Remake 模型可以由专用 UE Viewer 导出为 ActorX `.psk/.pskx`。这个 Mod 的主体包则有
两个额外问题：

1. 把游戏的整个 `Paks` 目录交给 UE Viewer 时，基础游戏 Pak 可能在 Mod 之后被扫描，最后
   选中的仍是原版 `PC0002_00`。仅使用 `-IncludeMods` 并不能证明结果来自 Mod。
2. 确认选中 Mod 后，专用 UE Viewer v8 会在解析这个大网格时触发：

   ```text
   assertion failed: LODModels.Num() == LODInfo.Num()
   ```

解决方法是：

```text
Mod-only 挂载
  → UE Viewer -save 保存原始 .uasset/.uexp
  → FF7R-mesh-importer 转换为 32 位索引 glTF
  → Blender 3.6 导入
```

FModel 可以确认 Mod 的包内容，但没有匹配的 Remake `.usmap` 时不能解析这个模型，因此这里
不依赖 FModel 导出网格。

## 2. 工具和路径

本机已验证路径：

```text
游戏：
D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE

Remake 专用 UE Viewer：
E:\tools\umodel_ff7remake\umodel_FFVII_intergrade_v8.exe

Blender 3.6：
D:\Program Files\blender-3.6.15-windows-x64\blender.exe

项目：
E:\code\othercode\ripper_tpose
```

还需要 [FF7R-mesh-importer](https://github.com/matyalatte/FF7R-mesh-importer)。本文按它的
`v0.2.1` 源码布局编写。该项目可以直接从 FF7R 的 `.uexp` 导出 glTF，不需要 `.usmap`。

建议工作目录：

```powershell
$work = 'D:\ff7remake_exports\tifa_mod_manual'
New-Item -ItemType Directory -Force -Path $work | Out-Null
```

## 3. 建立 Mod-only 挂载

不要为了提高优先级而长期把额外副本放进游戏的 `Paks` 根目录。建立一个只包含目标 Mod 的
临时目录，最容易保证 UE Viewer 不会回退到原版。

源文件和临时目录位于同一个 `D:` 卷时，可以创建不额外占空间的硬链接：

```powershell
$mod = 'D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE\End\Content\Paks\~mods\zzTifaNudeNatural_V8_SF3D.pak'
$mount = Join-Path $work '.mod_mount'

New-Item -ItemType Directory -Force -Path $mount | Out-Null
New-Item -ItemType HardLink `
  -Path (Join-Path $mount 'zzTifaNudeNatural_V8_SF3D.pak') `
  -Target $mod | Out-Null
```

如果源文件和工作目录不在同一个卷，改用 `Copy-Item`。不要移动或重命名 `~mods` 中的原始
Mod。

先列出 Mod 内容：

```powershell
$umodel = 'E:\tools\umodel_ff7remake\umodel_FFVII_intergrade_v8.exe'

& $umodel '-list' '-game=ue4.18' "-path=$mount" '*'
if ($LASTEXITCODE -ne 0) { throw 'UE Viewer list failed' }
```

PowerShell 中应把 `-game=ue4.18` 作为一个完整字符串传入。已验证的 Mod 应至少列出：

```text
/End/Content/GameContents/Character/Player/PC0002_00_Tifa_Standard/
├─ Model/PC0002_00.uasset
└─ Texture/
   ├─ PC0002_00_BodyA_*.uasset
   ├─ PC0002_00_BodyB_*.uasset
   ├─ PC0002_00_Eye_C.uasset
   └─ PC0002_00_Head_*.uasset
```

本 Mod 一共包含 1 个模型包和 13 个 Texture2D 包。

## 4. 保存 Mod 原始模型

这里必须使用 `-save`，不要使用 `-export`。`-save` 只把 `.uasset/.uexp` 从 Pak 中取出，
不会进入发生 LOD 断言的网格导出代码。

```powershell
$raw = Join-Path $work 'raw_body'
$bodyPackage = 'End/Content/GameContents/Character/Player/PC0002_00_Tifa_Standard/Model/PC0002_00.uasset'

& $umodel '-save' '-game=ue4.18' "-path=$mount" "-out=$raw" $bodyPackage
if ($LASTEXITCODE -ne 0) { throw 'Saving Mod body failed' }
```

检查结果：

```powershell
$bodyDir = Join-Path $raw 'End\Content\GameContents\Character\Player\PC0002_00_Tifa_Standard\Model'
Get-Item `
  (Join-Path $bodyDir 'PC0002_00.uasset'), `
  (Join-Path $bodyDir 'PC0002_00.uexp')
```

本次验证的文件大小为：

| 文件 | 字节 |
|---|---:|
| `PC0002_00.uasset` | 16,048 |
| `PC0002_00.uexp` | 52,393,908 |

## 5. 导出 Mod 贴图

对 Mod-only 挂载使用 `*`，同时用 `-nomesh` 跳过会崩溃的主体网格：

```powershell
$modAssets = Join-Path $work 'mod_assets'

& $umodel `
  '-export' '-png' '-nomesh' '-noanim' '-game=ue4.18' `
  "-path=$mount" "-out=$modAssets" '*'

if ($LASTEXITCODE -ne 0) { throw 'Exporting Mod textures failed' }
```

应得到 13 张 PNG。不要使用 `Texture/*` 作为包参数；该 Mod 有自定义 mount point，实测
`Texture/*` 可能匹配不到，`*` 配合 `-nomesh` 更稳定。

## 6. 准备 FF7R-mesh-importer

克隆工具：

```powershell
git clone https://github.com/matyalatte/FF7R-mesh-importer.git `
  (Join-Path $work 'FF7R-mesh-importer')

Set-Location (Join-Path $work 'FF7R-mesh-importer')
```

上游 `v0.2.1` 默认把三角形索引写成 16 位。这个 Mod 单个 primitive 会引用大于
`65,535` 的顶点，因此原版工具会出现：

```text
struct.error: 'H' format requires 0 <= number <= 65535
```

仓库附带了已经验证的补丁：

```powershell
git apply 'E:\code\othercode\ripper_tpose\scripts\final\ff7r_mesh_importer_large_mesh_cm.patch'
```

补丁做两件事：

- 三角形索引 accessor 从 `UNSIGNED_SHORT (5123)` 改为 `UNSIGNED_INT (5125)`，二进制从
  Python `struct` 的 `H` 改为 `I`；
- 保持 FF7R 原始厘米单位，使 Mod 主体和后面单独导出的官方手套能与项目既有 PSK/Blender
  流程对齐。

补丁不会修改 `JOINTS_0/JOINTS_1`。骨骼索引仍是 16 位，这是正确的。

## 7. 把 Mod 主体转换为 glTF

```powershell
$converter = Join-Path $work 'FF7R-mesh-importer\src\main.py'
$bodyUexp = Join-Path $bodyDir 'PC0002_00.uexp'
$bodyGltfRoot = Join-Path $work 'gltf_body'

python $converter $bodyUexp $bodyGltfRoot --mode=export
if ($LASTEXITCODE -ne 0) { throw 'Body glTF conversion failed' }
```

输出文件：

```text
D:\ff7remake_exports\tifa_mod_manual\gltf_body\PC0002_00\PC0002_00.gltf
D:\ff7remake_exports\tifa_mod_manual\gltf_body\PC0002_00\PC0002_00.bin
```

注意：旧版工具会捕获部分异常后仍返回退出码 `0`，所以还要检查 `.gltf/.bin` 是否都存在：

```powershell
$bodyGltf = Join-Path $bodyGltfRoot 'PC0002_00\PC0002_00.gltf'
$bodyBin = Join-Path $bodyGltfRoot 'PC0002_00\PC0002_00.bin'

if (-not (Test-Path -LiteralPath $bodyGltf) -or
    -not (Test-Path -LiteralPath $bodyBin)) {
    throw 'Body glTF output is incomplete'
}
```

再检查所有 primitive 的索引类型：

```powershell
$json = Get-Content -LiteralPath $bodyGltf -Raw | ConvertFrom-Json
$indexTypes = $json.meshes[0].primitives | ForEach-Object {
  $json.accessors[[int]$_.indices].componentType
} | Sort-Object -Unique

$indexTypes
```

本 Mod 必须只输出：

```text
5125
```

## 8. 准备原版材质依赖

这个 Mod 只覆盖部分贴图，不包含完整 Material、头发、口腔和公共眼球贴图。先用项目已有的
原版导出脚本保存依赖：

```powershell
Set-Location 'E:\code\othercode\ripper_tpose\scripts\final'
$env:FF7REMAKE_AES_KEY = Read-Host 'FF7 Remake AES key'

try {
  .\ff7remake_export.ps1 `
    -Package 'End/Content/GameContents/Character/Player/PC0002_00_Tifa_Standard/Model/PC0002_00.uasset' `
    -OutputRoot (Join-Path $work 'base_assets')
}
finally {
  Remove-Item Env:FF7REMAKE_AES_KEY -ErrorAction SilentlyContinue
}
```

这里不要加 `-IncludeMods`。Mod 主体已经通过 Mod-only 挂载保存；此步骤只需要不会被覆盖的
原版材质依赖。

建立组合素材目录：

```powershell
$baseCharacter = Join-Path $work 'base_assets\GameContents\Character\Player\PC0002_00_Tifa_Standard'
$combinedCharacter = Join-Path $work 'assets_combined\GameContents\Character\Player\PC0002_00_Tifa_Standard'
$modTexture = Join-Path $modAssets 'GameContents\Character\Player\PC0002_00_Tifa_Standard\Texture'

New-Item -ItemType Directory -Force -Path $combinedCharacter | Out-Null
Copy-Item -LiteralPath (Join-Path $baseCharacter 'Material') `
  -Destination $combinedCharacter -Recurse -Force
Copy-Item -LiteralPath (Join-Path $baseCharacter 'Texture') `
  -Destination $combinedCharacter -Recurse -Force

Get-ChildItem -LiteralPath $modTexture -Filter '*.png' -File |
  Copy-Item -Destination (Join-Path $combinedCharacter 'Texture') -Force
```

### 8.1 必须移除原版 BodyA Alpha

该 Mod 没有提供 `PC0002_00_BodyA_A`。如果把原版的同名 Alpha 遮罩用于 Mod BodyA，前臂和
小腿会被裁掉，预览看起来像断肢。

只删除组合素材副本，不要删除原版导出：

```powershell
$wrongAlpha = Join-Path $combinedCharacter 'Texture\PC0002_00_BodyA_A.png'
Remove-Item -LiteralPath $wrongAlpha -Force -ErrorAction SilentlyContinue
```

## 9. Blender 3.6 手动导入主体

1. 启动 Blender 3.6。
2. 选择 `File > Import > glTF 2.0 (.glb/.gltf)`。
3. 选择 `PC0002_00.gltf`。
4. 导入后应得到一个主体 Mesh 和一个 481 骨骼 Armature。
5. 不要对主体执行自动权重；glTF 已经带有原始蒙皮权重。
6. 如果后面要合并手套，不要单独缩放主体。补丁已经让两者统一使用厘米坐标。

主体材质的基础连接关系：

| 材质 | Base Color | Normal | Alpha |
|---|---|---|---|
| `PC0002_00_BodyA` | `BodyA_C` | `BodyA_N` | 不连接原版 `BodyA_A` |
| `PC0002_00_BodyB` | `BodyB_C` | `BodyB_N` | 无 |
| `PC0002_00_Skin` | `BodyB_C` | `BodyB_N` | 无 |
| `PC0002_00_Earring` | `BodyA_C` | `BodyA_N` | 无 |
| `PC0002_00_Eye` | `Eye_C` | `Common_Eye_Player_NO` | 无 |
| `PC0002_00_Head` | `Head_C` | `Head_N` | 无 |
| `PC0002_00_Eyelash` | `Head_C` | `Head_N` | 按贴图 Alpha |
| `PC0002_00_Hair` | 原版 `Hair_C` | 原版 `Hair_N` | 原版 `Hair_A` |
| `PC0002_00_Eyebrow` | 原版 `Hair_C` | 原版 `Hair_N` | 原版 `Hair_A` |
| `PC0002_00_Mouth` | `Common_LightMouth_Player_C` | `Common_Mouth_Player_N` | 无 |

Normal 贴图在 Image Texture 节点中设为 `Non-Color`。UE 使用 DirectX 法线；在 Blender 中
需要反转绿色通道后再进入 Normal Map 节点。

## 10. 导出并合并 Tifa 的独立手套

标准服装 Tifa 的完整手掌和拳套不在 `PC0002_00` 主体中，而是在：

```text
End/Content/GameContents/Character/Weapon/WE0002_00_Tifa_LeatherGlove/
└─ Model/WE0002_00.uasset
```

如果主体预览中手掌悬空或护腕末端没有完整手套，不要手工平移那些顶点，也不要自动权重。

### 10.1 从原版 Pak 保存手套原始包

原版 Pak 已加密。下面把 AES key 写入一次性临时文件，避免把 key 放进命令行和仓库：

```powershell
$game = 'D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE'
$paks = Join-Path $game 'End\Content\Paks'
$rawGlove = Join-Path $work 'raw_glove'
$glovePackage = 'End/Content/GameContents/Character/Weapon/WE0002_00_Tifa_LeatherGlove/Model/WE0002_00.uasset'
$key = Read-Host 'FF7 Remake AES key'
$keyFile = Join-Path ([IO.Path]::GetTempPath()) ("ff7remake-aes-{0}.txt" -f [guid]::NewGuid())

try {
  [IO.File]::WriteAllText($keyFile, $key)
  & $umodel `
    '-save' '-game=ue4.18' "-aes=@$keyFile" `
    "-path=$paks" "-out=$rawGlove" $glovePackage
  if ($LASTEXITCODE -ne 0) { throw 'Saving glove package failed' }
}
finally {
  Remove-Item -LiteralPath $keyFile -Force -ErrorAction SilentlyContinue
  Remove-Variable key -ErrorAction SilentlyContinue
}
```

### 10.2 用同一个转换器生成手套 glTF

必须使用与主体相同、已经应用厘米补丁的转换器：

```powershell
$gloveUexp = Join-Path $rawGlove 'End\Content\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.uexp'
$gloveGltfRoot = Join-Path $work 'gltf_glove'

python $converter $gloveUexp $gloveGltfRoot --mode=export
if ($LASTEXITCODE -ne 0) { throw 'Glove glTF conversion failed' }
```

输出应包含：

```text
gltf_glove\WE0002_00\WE0002_00.gltf
gltf_glove\WE0002_00\WE0002_00.bin
```

不要把 Mod glTF 主体与 PSK 手套直接改绑到同一个骨架。PSK 和 glTF 导入器会用不同方式
重建 bone roll；虽然模型静止时可能接近，实测最坏 rest matrix 差达到 `1.409555`。主体和
手套都走同一个 glTF 转换器后，最坏差降到 `7.63e-6`。

### 10.3 在 Blender 中手动改绑

1. 在已经打开主体的 Blender 文件中，再导入 `WE0002_00.gltf`。
2. 确认主体和手套都处于相同位置、旋转和缩放；不要手工移动手套。
3. 记下主体 Armature，通常名为 `PC0002_00`。
4. 选中手套 Mesh，执行 `Alt+P > Clear Parent (Keep Transform)`。
5. 在手套的 Armature modifier 中，把 `Object` 从新导入的手套 Armature 改为主体
   `PC0002_00`。
6. 只建立普通对象父子关系：手套 Mesh 先选、主体 Armature 最后选，执行
   `Ctrl+P > Object (Keep Transform)`。
7. 确认手套仍使用原来的 vertex groups 后，删除新导入的重复手套 Armature。

不要选择 `Armature Deform > With Automatic Weights`，否则会覆盖游戏原始权重。

手套材质：

| 材质 | 连接 |
|---|---|
| `WE0002_00_Body` | `WE0002_00_Body_C` + `WE0002_00_Body_N`，按需使用 `_A` |
| `WE0002_00_Materia` | 红色低粗糙度材质，可增加少量 Emission |

## 11. 保存和验证

建议把贴图目录和 `.blend` 放在同一个导出根目录，并在 Blender 中执行
`File > External Data > Make All Paths Relative` 后再保存：

```text
D:\ff7remake_exports\tifa_mod_manual\final\
├─ Tifa_Mod_Natural.blend
├─ Tifa_Mod_Natural_preview.png
└─ assets_combined\
```

打开 `Overlays > Statistics`，检查：

| 检查项 | 预期 |
|---|---:|
| Mesh | 2：主体 + 手套 |
| Armature | 1 |
| 主体骨骼 | 481 |
| 总顶点 | 370,846 |
| 总面数 | 607,004 |
| 主体材质槽 | 10 |
| 手套材质槽 | 2 |

姿势验证：

1. 进入主体 Armature 的 Pose Mode。
2. 选择 `L_ForearmrollA_Spo` 或手腕附近任意实际加权骨骼。
3. 临时旋转约 `5°`。
4. 主体和手套都应连续变形，不应留在原地或爆开。
5. 使用 Undo 恢复。

## 12. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 导出的主体只有约 82,059 顶点 | 实际选中了原版 | 使用 Mod-only 挂载；不要只相信 `-IncludeMods` |
| UE Viewer 报 `LODModels.Num() == LODInfo.Num()` | 专用构建不能直接导出该 Mod 网格 | 使用 `-save`，再用 FF7R-mesh-importer |
| Python 报 `'H' format requires ... 65535` | 三角形索引仍是 16 位 | 应用仓库的 32 位索引补丁 |
| glTF 只有 `.bin`，没有 `.gltf` | 转换中途失败，但旧工具可能仍返回 0 | 同时检查两个文件和日志 |
| FModel 能看到包但打不开模型 | 缺少匹配 Remake 的 `.usmap` | 使用原始 `.uasset/.uexp` 转换路线 |
| 前臂、小腿消失 | 错用了原版 `BodyA_A` | 从组合素材副本移除该 Alpha |
| 手掌或护腕不完整 | Tifa 手套是独立 Weapon 网格 | 导出并合并 `WE0002_00` |
| 手套骨架 rest 差约 1.4 | 混用了 PSK 与 glTF 骨架 | 主体和手套使用同一 glTF 转换器和单位补丁 |
| 主体高约 1.72、手套高约 172 | 米/厘米混用 | 对两者应用同一厘米补丁后重新转换 |
| 头发或口腔无贴图 | Mod 只覆盖了部分 Texture2D | 从原版导出 Material、Hair、Eye、Mouth 公共依赖 |

## 13. 清理临时挂载

确认 `.blend` 和组合素材已保存后，删除临时硬链接目录。下面只删除 `$work` 中创建的副本，
不会删除 `~mods` 中的原始 Mod：

```powershell
$resolvedMount = (Resolve-Path -LiteralPath $mount).Path
$resolvedWork = (Resolve-Path -LiteralPath $work).Path.TrimEnd('\') + '\'

if (-not $resolvedMount.StartsWith($resolvedWork, [StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing unexpected mount path: $resolvedMount"
}

Remove-Item -LiteralPath $resolvedMount -Recurse -Force
```

原始 `.uasset/.uexp`、glTF 和未合并贴图可以在最终验证后删除；最终 `.blend` 若仍使用外部
贴图，则必须保留 `assets_combined`。

## 14. 参考

- [FF7R-mesh-importer](https://github.com/matyalatte/FF7R-mesh-importer)
- [FF7R-mesh-importer Command Line Usage](https://github.com/matyalatte/FF7R-mesh-importer/wiki/Command-Line-Usage)
- [UE Viewer](https://www.gildor.org/en/projects/umodel)
- [Remake 原版模型导出说明](final-fantasy-vii-remake-extraction.md)
- [Remake 玩家模型清单](ff7remake-player-model-inventory.md)
