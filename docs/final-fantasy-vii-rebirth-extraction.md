# FINAL FANTASY VII REBIRTH 模型导出

## 为什么不能复用 Rise of Eros 脚本

本机安装目录已确认包含 `End\Content\Paks\global.utoc/global.ucas`，以及大量
`pakchunk*-WindowsNoEditor.utoc/.ucas`。这是 Unreal IoStore，不是 Unity
AssetBundle：

- ROE：AssetStudioModCLI 读取 `.ab`，可由 PowerShell 自动按角色 ID 组包；
- FFVII Rebirth：FModel/CUE4Parse 读取 `.pak/.utoc/.ucas`，包索引、引擎版本、
  mapping 和可能的加密状态都由具体游戏版本决定。

因此 FFVII Rebirth 使用独立的 `scripts\final\`，不向
`scripts\riseoferos\` 加任何分支。

## 1. 准备隔离的输出目录

在 PowerShell 中运行：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
.\prepare_fmodel.ps1
```

默认参数：

| 参数 | 默认值 |
|---|---|
| `-GameRoot` | `D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH` |
| `-WorkspaceRoot` | `D:\ff7rebirth_exports` |
| `-FModelExe` | `E:\tools\FModel\FModel.exe` |

如果 FModel 已放在默认位置，可直接检查并启动：

```powershell
.\prepare_fmodel.ps1 -LaunchFModel
```

脚本只做以下事情：

1. 验证游戏根目录和 `End\Content\Paks`；
2. 检查 `.utoc` 是否有同名 `.ucas`；
3. 建立 `fmodel_exports/blender/xps` 三个隔离目录；
4. 可选启动用户已有的 FModel。

它不会读取或修改大体积资源文件，也不会下载、提取或保存 AES key/mapping。

## 2. 只生成一次稳定 mapping

FModel 读取 IoStore 文件时需要 `.usmap` 来解释 Unreal 属性布局。游戏安装包没有附带
可直接使用的 mapping；本次使用 UE4SS 在游戏进程里读取运行时反射信息，再将结果复制到
独立目录。**生成 mapping 时需要启动游戏，之后使用 FModel 导出时不需要让游戏保持运行。**

### 2.1 UE4SS 最小配置

本次验证使用 UE4SS `v3.0.1 Beta #0`，Git SHA `c838a8ac`，目录为：

```text
D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH\
└─ End\Binaries\Win64\ue4ss\
```

为减少 FFVII Rebirth 因注入和额外回调而出现 `Fatal Error` 的概率：

1. 在 `ue4ss\UE4SS-settings.ini` 中将**所有名称以 `Hook` 开头的设置**改为 `0`，
   即 `Hook*=0`。本次验证的 14 个 Hook 项全部关闭。
2. 同一文件使用 `bUseUObjectArrayCache = false`，并关闭文本/GUI Console。
3. 在 `ue4ss\Mods\mods.txt` 中禁用其他 Mod，只保留最后一项：

   ```text
   Keybinds : 1
   ```

`Hook*=0` 是 UE4SS 配置项的简写说明，不是要原样粘贴进 INI。实际做法是逐项把
`HookProcessInternal`、`HookLoadMap`、`HookUObjectProcessEvent` 等现有
`Hook...` 行设为 `0`。

### 2.2 生成并固定文件

1. 从 Steam 启动游戏，等到游戏已进入可响应键盘的界面。
2. 按住 `Ctrl`，按小键盘 `6`（`Ctrl+Numpad6`）。Keybinds 的
   `DumpUSMAP` 会执行 UE4SS 的 `DumpUSMAP()`。
3. 等待 `ue4ss\UE4SS.log` 出现：

   ```text
   Mappings Generation Completed Successfully!
   Output file: --c838a8ac.usmap
   ```

4. 关闭游戏，把临时生成物复制并改为稳定、可识别的名字：

   ```powershell
   $source = "D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH\End\Binaries\Win64\ue4ss\--c838a8ac.usmap"
   $mappingDirectory = "D:\ff7rebirth_exports\mappings"
   $target = Join-Path $mappingDirectory "FF7Rebirth-4.26-20260726-c838a8ac.usmap"
   New-Item -ItemType Directory -Path $mappingDirectory -Force | Out-Null
   Copy-Item -LiteralPath $source -Destination $target -Force
   Get-FileHash -Algorithm SHA256 -LiteralPath $target
   ```

本次已验证的稳定文件：

| 项目 | 值 |
|---|---|
| 路径 | `D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap` |
| 大小 | `2,205,102` bytes |
| SHA256 | `5675ABC2024CA3ABC98F078B000FEE1C48EC65C015D02EB1D6CC8D107FA4BFD0` |

源文件和稳定副本的 SHA256 已核对一致。若 mapping 已生成且哈希匹配，即使游戏随后因
UE4SS 注入出现 Fatal Error，也不需要为 FModel 再次启动游戏。游戏或 UE4SS 更新后，
文件内容可能变化，应重新生成并记录新的日期、UE4SS SHA 和文件哈希。

## 3. 在 FModel 中配置专用解析 profile

本次验证使用 FModel `4.4.4.0`（commit
`b2708293f64ffc858b4901ff785a9078b99c67f4`）。

1. 打开 FModel，在 **Directory Selector** 中添加游戏根目录：
   `D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH`。
   不要选择 `End\Content\Paks`。
2. 对这个目录手动选择 FModel/CUE4Parse 的专用游戏 profile
   **Final Fantasy VII Rebirth**。内部枚举值应为：

   ```text
   GAME_FinalFantasy7Rebirth = 68812805
   ```

   不要改用通用的 `GAME_UE4_26` 或 `GAME_UE4_LATEST`。专用 profile 除基础
   UE4.26 序列化外，还启用 FFVII Rebirth 的骨骼网格/静态网格特殊处理。
   本机可在
   `C:\Users\haoni\AppData\Roaming\FModel\AppSettings.json` 中复核
   `PerDirectory[游戏根目录].UeVersion` 为 `68812805`（十六进制
   `0x041A0005`）。
3. 在 mapping 设置中选择：
   `D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap`。
4. 打开 **Settings > Models**，使用本次已实测可导出 Tifa 的设置：

   | FModel 项目 | 选择 |
   |---|---|
   | Model Export Directory | `D:\ff7rebirth_exports\fmodel_exports` |
   | Mesh Format | `ActorX (psk / pskx)` |
   | Level Of Detail Format | `First Level Only` |
   | Texture Format | `PNG` |
   | Keep Directory Structure | 开启 |

5. 应用目录/profile/mapping 后重新打开 FModel。日志应同时出现
   `GAME_FinalFantasy7Rebirth` 和
   `Mappings pulled from 'FF7Rebirth-4.26-20260726-c838a8ac.usmap'`。

更改模型导出格式本身不要求重启；更换游戏 profile 或 mapping 后重开 FModel，可避免
旧解析状态留在当前会话。

## 4. 定位 Tifa 标准版

本次在 FModel 的**虚拟 IoStore 包索引**中核对到；这些数字不是已经写入
`fmodel_exports` 的 Windows 目录数：

- `End/Content/Character/Player` 下有 `109` 个角色/服装变体目录；
- 其中有 `12` 个名称含 Tifa 的直接变体目录：`10` 个 PC0002 变体，另有
  `PC0099_03_Toad_Tifa` 和 `PC7002_00_Tifa_StandardCFEnd2`；
- 截至 2026-07-26，本机输出目录已有 `14` 个 Player 一级目录，另有 `95` 个尚未
  写入磁盘。完整差集、状态判断和逐项手动导出步骤见
  [`ff7rebirth-player-export-inventory.md`](ff7rebirth-player-export-inventory.md)；
- 标准版目录是
  `End/Content/Character/Player/PC0002_00_Tifa_Standard`；
- 标准版虚拟目录共 `65` 个 packages：
  `Material = 13`、`Model = 7`、`Texture = 45`；
- 其中 `Model` 子目录的 `7` 个 packages 是
  `PC0002_00_BNM`、`PC0002_00_Condition`、`PC0002_00_KDI_Extra1`、
  `PC0002_00_KDI`、`PC0002_00_Skeleton`、`PC0002_00_vfx` 和
  `PC0002_00`；`PC0002_00` 与 `PC0002_00_Condition` 这 `2` 个是
  SkeletalMesh。

导出标准角色主体时：

1. 在 Folders/Packages 中进入
   `End/Content/Character/Player/PC0002_00_Tifa_Standard/Model`。
2. 双击 `PC0002_00.uasset`，等待 3D Viewer 打开。
3. 在 3D Viewer 的 **Outliner** 中右键模型，选择 **Save Model**。
4. 再保存该标准版目录下相关 `MaterialInstance`，让 FModel 输出材质 JSON 与被引用的
   PNG 贴图。
5. 保留 FModel 生成的完整目录层级，不要只移动单个 `.pskx`。

`PC0002_00_Condition` 也是 SkeletalMesh，但不是这次标准主体的首选导出项。

## 5. glTF 切线错误与 ActorX workaround

### 5.1 两个独立问题

双击 `PC0002_00` 时，日志仍可能先出现：

```text
Read incorrect amount of tangent bytes, at 1388948,
should be: 1171396 behind: -217552
```

差值 `217,552 = 27,194 × 8`。该 LOD 有 `27,194` 个顶点，bulk header 表示每顶点
切线占 `8` 字节（低精度），但 CUE4Parse 按
`UseHighPrecisionTangentBasis` 选择了每顶点 `16` 字节的读取方式，因而每个顶点多读
8 字节。这是 FFVII Rebirth 自定义序列化与通用 reader 之间的 stride/precision
不一致；不是贴图、材质槽或 Blender 引起的。

如果将导出格式设为 glTF，保存时还会出现另一条独立错误：

```text
SharpGLTF.Validation.DataException:
Accessor[2] TANGENT[18]: Invalid Tangent
```

CUE4Parse 的 glTF 转换当前对整个 tangent `Vector4` 做归一化，连同表示手性的
`W` 一起缩放。glTF 要求 tangent 的 XYZ 为单位向量且 `W` 必须精确为 `+1` 或 `-1`；
因此 SharpGLTF 1.0.6 的 Strict 校验拒绝该数据。`TANGENT[18]` 是发现非法值的位置，
并不表示模型只有 18 条切线。

### 5.2 当前可用操作

对 `PC0002_00` 使用：

1. **Settings > Models > Mesh Format**：
   `ActorX (psk / pskx)`；
2. **Level Of Detail Format**：`First Level Only`；
3. 回到 `PC0002_00.uasset`，在 3D Viewer 的 Outliner 中右键模型；
4. 点击 **Save Model**。

ActorX 分支写出位置、法线、UV、骨架、权重和可用的 morph 数据，但不经过
SharpGLTF 的 glTF `VEC4 TANGENT` 严格校验，所以能绕开第二个错误。`First Level Only`
减少最终输出的 LOD 数量，但它不是 reader 修复；第一条 tangent bytes 日志仍可能出现。
本次 FModel 在记录该解析错误后保留了可用网格，并成功完成 ActorX 导出。

长期代码修复应分别处理两处：

- reader 仅在 `GAME_FinalFantasy7Rebirth` 下依据 tangent bulk 的 `itemSize`
  选择 8/16 字节精度；
- glTF 转换只归一化 tangent XYZ，并把 W 单独保持/钳为 `±1`，或者写出时使用
  SharpGLTF `ValidationMode.TryFix`。`ValidationMode.Skip` 只跳过检查，不修坏数据，
  不建议使用。

### 5.3 已验证输出

```text
D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Player\PC0002_00_Tifa_Standard\Model\PC0002_00.pskx
```

| 项目 | 本次结果 |
|---|---:|
| 文件大小 | `20,480,844` bytes |
| 顶点 | `188,921` |
| 三角面 | `226,086` |
| 材质 | `12` |
| 骨骼 | `536` |
| 权重记录 | `480,494` |
| 额外 UV 集 | `2` |

PSKX 的各 chunk 边界已逐项检查，末尾偏移与文件长度完全相等；不是空文件或截断文件。
本次输出 SHA256 为
`568B7280E0CB556BB7280CE18E67786257E19E0471E1221CF124C6D625DA1980`。

如果 FModel 显示 archive disabled，说明该 archive 需要合法取得的 AES key；本项目
不提供或抓取密钥。FModel 导出阶段只读取磁盘上的 `.pak/.utoc/.ucas` 和 mapping，
不需要游戏进程。

## 6. 安装 Blender 插件

1. Blender 3.6 → `Edit > Preferences > Add-ons > Install...`。
2. 选择 `scripts\final\ff7rebirth_tools.py`，勾选启用。
3. 3D 视口按 `N`，打开 **FF7RB** 页签。

当前文档对应 FF7 Rebirth Tools `0.3.0`。从旧版覆盖插件文件后，应在 Add-ons 中
禁用再启用该插件，或重启 Blender；只覆盖磁盘文件不会替换当前会话已加载的旧代码。

若 FModel 只导出了 `.psk/.pskx`，还需安装
[io_scene_psk_psa](https://github.com/DarklightGames/io_scene_psk_psa)。
Blender 3.6 使用官方
[5.0.6 release](https://github.com/DarklightGames/io_scene_psk_psa/releases/tag/5.0.6)：
下载该版本的插件 ZIP，在 Blender 3.6 的
`Edit > Preferences > Add-ons > Install...` 中选择 ZIP 并勾选启用。FF7RB 插件
兼容 5.0.6 注册的 `import_scene.psk`，也兼容其他版本可能提供的
`psk.import_file`。若只有 glTF/FBX，则不需要额外 PSK 插件；但当前 Tifa 主体的
FModel glTF 会因非法 tangent 失败，所以本次使用已验证的 ActorX 文件。

## 7. Blender 中一步步导入

1. 面板最上方“FModel 导出目录”选择
   `D:\ff7rebirth_exports\fmodel_exports\`。
2. 点击“扫描导出目录”。插件递归查找
   `.glb/.gltf/.fbx/.pskx/.psk/.obj`。当前版本先验证 `.psk/.pskx` 至少
   `32` bytes 且文件头以 `ACTRHEAD` 开始；有效 PSKX、PSK 的选择分数高于
   FFVII Rebirth 当前可能损坏的 glTF，再考虑 LOD0 和文件大小。
3. 检查“模型文件”是否为已验证的 `PC0002_00.pskx`。扫描器不会选中结构无效的
   ActorX 文件；但手动指定路径代表明确的用户选择，导入时不会再次替换该路径。
4. 保持“替换上次导入”开启，可避免反复测试时叠加模型；它只删除这个插件上次导入
   且带批次标记的对象。替换采用事务顺序：先尝试导入新模型并完成法线、缩放、材质
   等后处理；只有这些步骤全部成功后才发布新批次并删除旧批次。导入异常、取消、
   零对象或后处理失败都会移除本次产生的残留对象，原模型不动。
5. glTF 通常把“导入缩放”保持 `1.0`。PSK 没有单位元数据，如果尺寸不合适，再按
   所用 PSK 导入器的设置调整，不要盲目应用对象变换。
6. 保持默认勾选“PSK 导入后修复三角反光”，点击“导入选中模型”。该选项只在
   `.psk/.pskx` 导入后执行，不影响 glTF/FBX。
7. 若模型只有材质槽名而没有贴图连接，将“贴图目录”指向角色导出的 PNG 根目录，
   点击“重新匹配基础贴图”。
8. v0.3.0 以前保存的旧 FF7RB 场景无需重新导入：在“基础材质”区点击
   “修复 PSK 三角反光”，即可处理当前批次的已有网格。

### 7.1 为什么正确贴图仍会出现三角形金属反光

`io_scene_psk_psa 5.0.6` 会把 FF7 PSK 的自定义分裂法线带入 Blender，并同时启用
`30° Auto Smooth`。对 Tifa 这类高密度网格，30° 阈值与分裂法线会暴露大量三角面
边界；在材质预览灯光下表现为皮肤/衣物像皱纸、碎金属片或一块块三角反光。这个现象
不是 `Arms_O` 贴图误判，也不是 Roughness 单独造成的。

自动修复对每个新导入 PSK Mesh 执行两件事：

1. 将所有 polygon 设为 Smooth；
2. 关闭 Mesh Data 上的 Auto Smooth，使表面使用连续平滑的顶点法线。

它不改顶点位置、拓扑、UV、材质槽、骨架或权重。若确实需要保留某个资产自己的硬
边，可在导入前关闭该选项，或之后手工重新建立硬边/法线。

## 8. 材质匹配原理与限制

### 8.1 JSON 引导的语义解析

FModel 保存 MaterialInstance 时会生成 JSON。插件同时递归扫描“FModel 导出目录”和
“贴图目录”，读取 JSON 顶层 `Textures` 字典，并按 Unreal 参数语义处理：

- `Color`、`BaseColor`、`PM_Diffuse` 等 → Base Color；
- `Normal`、`NormalMap` 等 → Normal；
- `Roughness` 与 `Metallic` → 独立数据图；
- `ORM/RMA/MRA` → G 接 Roughness、B 接 Metallic；
- `Coverage`、`Opacity`、`AlphaMask` 等 → Alpha。

JSON 中的 `/Game/...` 引用先去掉 Unreal 对象后缀，再按完整包路径在保留目录层级的
FModel 输出中定位 PNG。多个包有同名图片、而路径证据又同样弱时，插件宁可不连接，
也不会随意选择。`/Game/Renderer/Texture/...` 下的白/黑占位图会被忽略。Base Color
使用 `sRGB`；Normal、Roughness、Metallic、ORM、Opacity 使用 `Non-Color`。

只有没有可用 JSON 时才回退到材质名和贴图文件名的公共词段匹配。该回退支持
Base Color / Albedo / Diffuse、Normal、Roughness、Metallic、ORM/RMA 和
Opacity/Alpha，也识别本游戏导出的 `Mg` 为 Roughness、`Mr` 为 Metallic。

旧实现把 `PC0002_00_Arms_O` 当成 ORM，是因为在 `Arms` 中做子串搜索时命中了
三字母通道标记 `ARM`，于是把该图片的 G/B 通道错误地接到 Roughness/Metallic，
表现为腿、手臂或衣物像皱缩金属箔。现在 `ARM/RMA/MRA/ORM` 只有作为完整尾部词元
时才成立，因此 `Arms_O` 不再误判为打包通道图。

已有 Base Color 连接默认不会覆盖。只有确认旧连接错误时才启用“覆盖已有基础贴图”。
强制重匹配会先删除本插件旧版本生成的 `FF7RB_` 图片和辅助节点、还原自动设置的
不透明状态，再建立当前 JSON 对应的连接；可重复执行，不会不断叠加本插件节点。

### 8.2 Tifa 眼睛的巩膜/虹膜组合

FF7 Player Eye 的颜色不是一张完整眼球贴图：

- Material JSON 的 `Color` 指向共享巩膜 `Common_Eye_Player_C`；
- `IrisColor` 指向角色虹膜 `PC0002_00_Eye_C`；
- `Normal` 指向共享眼睛法线（本次为 `Common_Eye_Player_NO`）。

如果把 `PC0002_00_Eye_C` 直接铺满 Base Color，虹膜图会覆盖眼白，结果就是暗红/棕色
整眼。插件现在使用 `VTXW0000` UV，对每个点计算其到 `(0.5, 0.5)` 的距离，以径向
蒙版混合两张颜色图：

- 距离不大于 `0.18`：虹膜；
- 距离不小于 `0.22`：共享巩膜；
- `0.18` 至 `0.22`：用 `EASE` 色带平滑过渡。

因此 `Eye` 材质会生成共享巩膜、角色虹膜、UV、Distance、ColorRamp 和 MixRGB 节点，
再把结果接到 Principled Base Color。该节点组恢复的是稳定的 Blender 预览，不是游戏
角膜折射、湿润层、视线变形和运行时参数的完整复制。

### 8.3 DirectX 法线绿通道翻转与强度

Unreal 的切线空间 Normal 使用 DirectX `Y-` 约定，Blender 的 Normal Map 节点按
OpenGL `Y+` 约定解释。直接连接会使凹槽看起来凸起、凸起看起来凹下。v0.3.0 为每张
法线图建立以下节点链：

```text
Normal Image (Non-Color)
  → Separate RGB
  → R 保持 / G 执行 1-G / B 保持
  → Combine RGB
  → Normal Map
  → Principled Normal
```

插件按材质名设置 Normal Map Strength：

| 材质类别 | 识别词元 | Strength |
|---|---|---:|
| 皮肤、头脸、手臂、眼睛、口腔 | `skin/head/arms/eye/mouth` | `0.35` |
| 衣物、头发、手套及其他材质 | 其他 | `0.7` |

`0.35` 可避免皮肤和眼睛的高频 Normal 在 Blender 灯光下过度起伏；`0.7` 保留其他
材质更明确的织物/硬表面细节。该转换与强度只存在于 Blender 节点中，不覆写 FModel
导出的原始 PNG。

### 8.4 修复当前已导入的主体

1. “FModel 导出目录”保留为完整的
   `D:\ff7rebirth_exports\fmodel_exports\`，不要只指向孤立 PNG 文件夹。
2. 确认 FModel 已保存 Tifa 相关 MaterialInstance JSON 和引用图片，并保留目录层级。
3. 在 **FF7RB > 基础材质** 中勾选“覆盖已有基础贴图”。
4. 点击一次“重新匹配基础贴图”。
5. 检查 Legs 使用 `Legs_C/Mg/Mr/N`，Eye 同时出现白色巩膜与居中虹膜，
   `Arms_O` 没有作为 ORM 接入 Roughness/Metallic；Normal 节点包含绿色通道反转，
   皮肤/眼睛 Strength 为 `0.35`，其他材质默认 `0.7`。
6. 如果旧场景仍有三角形皱纸/金属反光，点击“修复 PSK 三角反光”。
7. 确认结果后关闭“覆盖已有基础贴图”，避免以后无意覆盖手工节点。

这一步恢复的是 Blender Principled BSDF 的基础 PBR 外观，不等价于游戏的自定义
Unreal Shader。皮肤次表面、眼球多层折射、头发各向异性、材质参数集合和运行时
效果仍需按角色逐项校正。与 ROE 不同，不能把 ROE 的眼球 UV 烘焙、五槽头部分类或
身体 `body1/body2` 规则直接套到 FFVII Rebirth。

## 9. Tifa 默认手套：独立资产导出与共骨架重绑

### 9.1 为什么主体看起来缺少掌部

`PC0002_00.pskx` 的权重记录是完整的，主体网格只提供与装备衔接的手指段。Tifa
标准服装的掌部/手套在独立 Weapon SkeletalMesh 中，并非 PSK 导入器漏顶点，也不是
修复材质能够补回的几何体。默认皮手套的精确 FModel 虚拟路径是：

```text
End/Content/Character/Weapon/WE0002_00_Tifa_LeatherGlove/Model/WE0002_00.uasset
```

其他编号（`01–05`、`11–16`）是其他手套/武器变体；标准外观先用 `WE0002_00`。

### 9.2 在 FModel 导出手套

1. 使用已配置好的 FFVII Rebirth profile、mapping、ActorX 和 First Level Only。
2. 精确搜索 `WE0002_00_Tifa_LeatherGlove`，进入其 `Model` 子目录。
3. 双击 `WE0002_00.uasset`，确认预览为左右手套；本次预览显示 `229` bones、
   `17` sockets、`3` materials。
4. 在 3D Viewer Outliner 中右键 `WE0002_00`，选择 **Save Model**。
5. 再保存/导出同目录引用的材质与图片，保留：

   ```text
   WE0002_00_Body.json
   WE0002_00_Alpha.json
   WE0002_00_Materia.json
   WE0002_00_Body_A.png
   WE0002_00_Body_C.png
   WE0002_00_Body_Mg.png
   WE0002_00_Body_Mr.png
   WE0002_00_Body_N.png
   WE0002_00_Body_O.png
   ```

本机实际生成的模型文件是 `.psk`（不是 `.pskx`）：

```text
D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk
```

大小为 `1,380,580` bytes。扩展名不同不影响 ActorX 数据用途，Blender 3.6 的
`io_scene_psk_psa 5.0.6` 可导入两者。

### 9.3 用 v0.3.0 一键导入并绑定

1. 先用 **“导入选中模型”** 完成 `PC0002_00.pskx` 主体导入。配件按钮以 FF7RB
   当前批次的 Armature 为目标，因此不能在主体尚未导入时单独使用。
2. “贴图目录”可以留空，让插件从完整 FModel 导出根目录扫描 JSON/PNG；保持
   “导入后匹配基础贴图”和“PSK 导入后修复三角反光”开启。
3. 在面板 **“4. 独立配件/武器”** 的“配件/武器模型”中选择上述
   `WE0002_00.psk`。
4. 点击 **“导入并绑定同骨架配件”**。
5. 成功时状态栏会报告绑定的配件网格数、目标主体骨架和准备的材质数。配件已经加入
   主体当前批次，Outliner 中不会留下手套的重复 Armature。
6. 在主体骨架 Pose Mode 轻微旋转腕/手指骨验证手套随动，随后撤销测试并另存
   `.blend`。

这里不需要更改主体的“模型文件”，也不需要关闭“替换上次导入”；配件有独立的路径
字段和操作符，不会把主体当作待替换批次。

### 9.4 自动验证、重绑与失败回滚原理

按钮不会计算自动权重，而是保留手套 PSK 已有的 vertex group 权重，让它们由主体的
同名骨骼驱动。内部按以下顺序执行：

1. 从 FF7RB 当前批次选择主体 Armature；若当前活动对象是该批次骨架则优先使用，
   否则选择骨骼数最多的 Armature。
2. 临时导入配件 PSK/PSKX，要求至少生成一套 Armature 和一个 Mesh。
3. 对每个配件 Mesh，从 Armature modifier 或 Parent 找到其导入骨架；收集权重大于
   `1e-8` 的实际使用 vertex group。
4. 检查主体骨架是否包含全部同名 bone；再比较两套骨架同名骨骼的
   `Bone.matrix_local`，任一矩阵元素最大差值不得超过 `0.01`。
5. 全部通过后，保持配件相对原骨架的局部变换，把 Armature modifier 与 Parent 改为
   主体骨架，删除临时导入的配件 Armature。
6. 将配件 Mesh 标记为主体同一批次；如果对应选项开启，再自动执行 PSK 三角反光
   修复和 JSON 材质准备。

任何网格缺少同名权重骨骼、找不到导入骨架、静止姿势超出容差，或导入器失败/取消，
都会删除本次创建的全部配件对象并报告原因；原主体和已有配件保持不变。这是事务式
配件导入，不会留下半绑定网格。

只比较骨骼总数没有意义：手套的 `229` bones 可以是主体 `536` bones 的子集。真正
的兼容条件是“实际使用骨名存在 + 同名骨骼 local rest/bind 矩阵在容差内”。

### 9.5 WE0002_00 实测结果

v0.3.0 已用本机导出的 `WE0002_00.psk` 完成实际测试：

- 配件权重骨骼和静止姿势自动验证通过；
- 手套网格自动改绑 `PC0002_00` 主体骨架；
- 手套导入产生的重复骨架自动删除；
- 手套保留原 PSK 权重和相对位置，并加入主体当前批次；
- JSON 材质准备与“PSK 导入后修复三角反光”同时执行。

因此标准 Tifa 的推荐流程就是使用该按钮；只有按钮明确报告骨骼/静止姿势不兼容时，
才需要进入 Outliner 和骨架数据做人工诊断，不应先手工改 modifier 或重新计算权重。

材质与骨架仍是独立问题：JSON 重匹配决定手套表面使用哪些贴图；同骨架配件操作决定
网格如何随动作变形。两项都成功才算完成配件合并。

## 10. 目录与兼容性

- `scripts\riseoferos\`：ROE 正式源码；
- `scripts\final\`：FFVII Rebirth 正式源码；
- `scripts\extract_character.ps1`：旧 ROE 命令的兼容转发入口；
- 已经安装在 Blender 用户目录中的 ROE 插件不受这次目录整理影响；
- 两个 Blender 插件使用不同的 Scene 属性和侧边栏页签，可以同时启用。
