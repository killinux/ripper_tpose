# FINAL FANTASY VII REBIRTH / REMAKE 模型导出使用说明

本目录集中保存《FINAL FANTASY VII REBIRTH》和《FINAL FANTASY VII REMAKE
INTERGRADE》的最终导出工具。两款游戏都使用 Unreal，但封包和序列化方式不同，不能混用
导出工具或资源路径。

> 本说明按本机在 2026-08-01 已验证的环境编写。只处理本机已安装游戏和个人研究用途；
> 不在仓库中保存或分发 AES key、游戏资产及其他受版权保护的数据。

## 1. 先判断该走哪条流程

| 项目 | FFVII Rebirth | FFVII Remake Intergrade |
|---|---|---|
| 游戏封包 | UE4.26 IoStore：`.utoc/.ucas` | UE4.18 变体：传统 `.pak` |
| 导出工具 | FModel/CUE4Parse | Remake Intergrade 专用 UE Viewer |
| 必要解析数据 | 专用游戏 profile + `.usmap` | `-game=ue4.18` + AES key |
| 模型格式 | ActorX `.psk/.pskx` | ActorX `.pskx` |
| 角色根路径 | `End/Content/Character/Player` | `End/Content/GameContents/Character/Player` |
| 默认输出根目录 | `D:\ff7rebirth_exports\fmodel_exports` | `D:\ff7remake_exports\umodel_original` |
| 自动化程度 | FModel 中手动保存，Blender 插件自动整理 | PowerShell 批量导出，Blender 手动导入/配材质 |

目录中的文件：

| 文件 | 作用 |
|---|---|
| `prepare_fmodel.ps1` | 检查 Rebirth IoStore 文件并建立隔离的输出目录，可选启动 FModel |
| `ff7rebirth_tools.py` | Blender 3.6 插件：扫描 Rebirth 导出、导入 PSK、匹配基础贴图和绑定同骨架配件 |
| `ff7remake_export.ps1` | 使用专用 UE Viewer 安全导出 Remake 的一个或多个资源包 |
| `fix_ff7remake_tifa_gloves.py` | Blender 3.6 后台脚本：校验并把 Remake Tifa 独立手套绑定到主体骨架 |
| `validate_ff7remake_model.py` | Blender 3.6 后台脚本：导入 Remake PSK、连接基础材质并生成 blend、预览和报告 |
| [`docs/ff7remake-mod-manual-export.md`](../../docs/ff7remake-mod-manual-export.md) | Remake Mod 手动导出：Mod-only 挂载、原始包转 32 位 glTF、Blender 3.6 材质和手套合并 |
| `ff7r_mesh_importer_large_mesh_cm.patch` | FF7R-mesh-importer v0.2.1 补丁：大网格 32 位索引和厘米坐标 |
| `tests/test_ff7rebirth_helpers.py` | Rebirth Blender 插件的纯 Python 辅助逻辑测试 |

## 2. 公共准备

### 2.1 已验证的本机软件

```text
Blender 3.6.15
D:\Program Files\blender-3.6.15-windows-x64\blender.exe

FModel
E:\tools\FModel\FModel.exe

Remake 专用 UE Viewer
E:\tools\umodel_ff7remake\umodel_FFVII_intergrade_v8.exe
```

Blender 3.6 使用 `io_scene_psk_psa 5.0.6` 导入 `.psk/.pskx`。安装方法：

1. 从 [io_scene_psk_psa 5.0.6](https://github.com/DarklightGames/io_scene_psk_psa/releases/tag/5.0.6)
   下载插件 ZIP；
2. Blender 打开 `Edit > Preferences > Add-ons > Install...`；
3. 选择 ZIP，安装后勾选启用；
4. 确认 `File > Import` 中出现 `Unreal PSK (.psk/.pskx)`。

### 2.2 操作前检查

- 导出时关闭对应游戏，避免封包被占用或 UE4SS/Mod 状态干扰结果；
- 输出目录不要放进游戏安装目录；
- 保留 Unreal 原始目录层级，不能把不同角色的同名贴图打平到一个文件夹；
- 先导出单个 Tifa 主体验证环境，再批量处理其他角色；
- 模型、材质 JSON/`.mat` 和贴图需要作为一组保留；只有模型往往无法正确还原材质。

---

# A. FINAL FANTASY VII REBIRTH

## A1. 已验证配置

| 项目 | 值 |
|---|---|
| 游戏目录 | `D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH` |
| 游戏 profile | `GAME_FinalFantasy7Rebirth = 68812805` |
| mapping | `D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap` |
| mapping SHA256 | `5675ABC2024CA3ABC98F078B000FEE1C48EC65C015D02EB1D6CC8D107FA4BFD0` |
| FModel 输出 | `D:\ff7rebirth_exports\fmodel_exports` |
| 模型格式 | `ActorX (psk / pskx)` |
| LOD | `First Level Only` |
| 贴图格式 | PNG |

Rebirth 必须使用 FModel/CUE4Parse 的专用 `Final Fantasy VII Rebirth` profile；不要用
通用 `UE4.26` 或 `Latest` 替代。Tifa 的 glTF 导出会因 tangent 数据校验失败，当前应使用
ActorX。

## A2. 准备输出目录

打开 PowerShell：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
.\prepare_fmodel.ps1
```

脚本会验证 `.utoc/.ucas` 配对并建立：

```text
D:\ff7rebirth_exports\
├─ fmodel_exports\   # FModel 的模型、JSON 和贴图输出
├─ blender\          # 自己保存的 .blend
└─ xps\              # 后续转换结果；不要和 FModel 原始输出混放
```

如果 FModel 位于默认路径，可以一并启动：

```powershell
.\prepare_fmodel.ps1 -LaunchFModel
```

如果游戏、工具或输出位置不同，可显式传参：

```powershell
.\prepare_fmodel.ps1 `
  -GameRoot 'D:\Games\FINAL FANTASY VII REBIRTH' `
  -WorkspaceRoot 'D:\ff7rebirth_exports' `
  -FModelExe 'E:\tools\FModel\FModel.exe' `
  -LaunchFModel
```

此脚本不解密、不提取游戏资产，也不会下载或保存 AES key/mapping。

## A3. mapping：正常使用可跳过，版本变化时重新生成

本机已经有上表所列且哈希验证通过的 `.usmap`，当前游戏版本下不需要再次生成。只有以下
情况才重新生成：

- 游戏更新后旧 mapping 解析报错；
- FModel 显示大量属性无法反序列化；
- 切换了游戏版本或重新安装了不兼容版本。

重新生成的详细流程：

1. 在游戏的 `End\Binaries\Win64\ue4ss\UE4SS-settings.ini` 中，把现有的所有
   `Hook...` 设置逐项改为 `0`，并使用 `bUseUObjectArrayCache = false`；
2. 在 `ue4ss\Mods\mods.txt` 中禁用其他 Mod，只保留 `Keybinds : 1`；
3. 从 Steam 启动游戏，进入可响应键盘的界面；
4. 按 `Ctrl+Numpad6` 调用 `DumpUSMAP()`；
5. 等待 `UE4SS.log` 出现 `Mappings Generation Completed Successfully!`；
6. 关闭游戏，把生成的 `.usmap` 复制到
   `D:\ff7rebirth_exports\mappings`，使用带日期/版本的稳定名称；
7. 用 `Get-FileHash -Algorithm SHA256` 记录哈希，并在 FModel 中重新选择该文件。

mapping 生成需要游戏进程；生成完成以后，FModel 离线读取 IoStore，不需要继续运行游戏。
更完整的 UE4SS 配置和生成记录见
[`docs/final-fantasy-vii-rebirth-extraction.md`](../../docs/final-fantasy-vii-rebirth-extraction.md)。

## A4. 配置 FModel

1. 在 `Directory Selector` 中添加游戏**根目录**：
   `D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH`；
   不要选 `End\Content\Paks`。
2. 游戏 profile 选择 **Final Fantasy VII Rebirth**，内部值应为
   `GAME_FinalFantasy7Rebirth = 68812805`。
3. mapping 选择
   `D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap`。
4. 在 `Settings > Models` 设置：

   | 设置 | 值 |
   |---|---|
   | Model Export Directory | `D:\ff7rebirth_exports\fmodel_exports` |
   | Mesh Format | `ActorX (psk / pskx)` |
   | Level Of Detail Format | `First Level Only` |
   | Texture Format | `PNG` |
   | Keep Directory Structure | 开启 |

5. Properties、Texture、Model 等输出根目录都设置为
   `D:\ff7rebirth_exports\fmodel_exports`。
6. 更换 profile 或 mapping 后重开 FModel。日志应同时出现
   `GAME_FinalFantasy7Rebirth` 和所选 mapping 文件名。
7. 如果 archive 显示 disabled，需要在 FModel 中配置自己合法取得的 AES key；不要把
   key 写进仓库、脚本、截图或聊天记录。

## A5. 用 Tifa 标准版验证导出

Tifa 标准版虚拟路径：

```text
End/Content/Character/Player/PC0002_00_Tifa_Standard/
├─ Model/
├─ Material/
└─ Texture/
```

### A5.1 导出主体模型

1. 在 FModel 进入
   `End/Content/Character/Player/PC0002_00_Tifa_Standard/Model`；
2. 双击 `PC0002_00.uasset`；
3. 等待 3D Viewer 打开，确认 Outliner 中目标是 `SkeletalMesh`；
4. 在 3D Viewer 的 Outliner 中右键网格，选择 **Save Model**；
5. 不要把 `PC0002_00_Condition`、Skeleton、BNM、KDI 或 VFX 辅助包当成主模型。

已验证输出：

```text
D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Player\PC0002_00_Tifa_Standard\Model\PC0002_00.pskx
```

验证数据：`188,921` 顶点、`226,086` 三角面、`12` 个材质、`536` 根骨骼、
`480,494` 条权重记录和 `2` 组额外 UV。日志即使出现 tangent bulk stride 警告，只要
ActorX 文件完整写出且文件头为 `ACTRHEAD`，就可以继续 Blender 验证。

### A5.2 导出材质属性和贴图

主体模型导出后继续处理同一变体：

1. 右键 `Material` 文件夹，选择
   **Save Folder's Packages Properties (.json)**；
2. 右键 `Texture` 文件夹，选择 **Save Folder's Packages Textures**；
3. 对共享依赖按 FModel 引用继续保存，保持 `Character/Common`、Renderer 或其他目录的
   原始层级；
4. 不要只留 PNG：MaterialInstance JSON 中的完整 `/Game/...` 引用是 Blender 插件
   正确区分同名贴图的依据。

### A5.3 导出 Tifa 默认手套

标准皮手套是独立 Weapon SkeletalMesh，主体没有完整掌部并不是导入器丢顶点。FModel
搜索：

```text
WE0002_00_Tifa_LeatherGlove
```

模型路径：

```text
End/Content/Character/Weapon/WE0002_00_Tifa_LeatherGlove/Model/WE0002_00.uasset
```

按与主体相同的方法执行 **Save Model**，并保存对应 Material JSON 和 Texture。已验证输出：

```text
D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk
```

## A6. 导出其他角色或服装

Player 资源一般位于：

```text
End/Content/Character/Player/<角色编号_服装编号_名称>/
```

每次只处理一个一级变体目录：

1. 进入其 `Model` 子目录；
2. 优先打开与目录编号同名的 `.uasset`，例如
   `PC0003_00_Aerith_Standard` 优先检查 `PC0003_00.uasset`；
3. 确认是 `SkeletalMesh` 后执行 **Save Model**；
4. 分别保存 `Material` 的 Properties JSON 和 `Texture` 的 PNG；
5. 检查输出中非空 `.psk/.pskx` 的文件头是否为 `ACTRHEAD`；
6. 没有 `Model` 子目录的 Tear/Wet/Hologram 等资源可能只是材质效果，不能把“无独立
   网格”误判为导出失败；
7. 保存失败时记录 FModel 日志，不要把仅有 `.uasset` 的结果标成 Blender 可用模型。

完整的 `109` 个 Player 变体、已导出项和待处理项见
[`docs/ff7rebirth-player-export-inventory.md`](../../docs/ff7rebirth-player-export-inventory.md)。

## A7. 在 Blender 中导入 Rebirth

### A7.1 安装项目插件

1. Blender 3.6 打开 `Edit > Preferences > Add-ons > Install...`；
2. 选择
   `E:\code\othercode\ripper_tpose\scripts\final\ff7rebirth_tools.py`；
3. 勾选启用 `FF7 Rebirth Tools`；
4. 3D 视口按 `N`，打开 **FF7RB** 页签。

覆盖更新插件文件后，需要在 Add-ons 中禁用再启用，或重启 Blender。

### A7.2 导入主体

1. “FModel 导出目录”选择 `D:\ff7rebirth_exports\fmodel_exports`；
2. 点击“扫描导出目录”；如果目录里有多个角色，手动确认“模型文件”是本次目标；
3. 保持“导入后匹配基础贴图”和“PSK 导入后修复三角反光”开启；
4. 点击“导入选中模型”；
5. 首次修复旧材质时，可临时开启“覆盖已有基础贴图”，点击“重新匹配基础贴图”，确认
   腿部、眼睛和法线正确后关闭该选项；
6. 旧场景仍有皱纸/金属三角反光时，点击“修复 PSK 三角反光”；
7. 保存到 `D:\ff7rebirth_exports\blender\<角色名>.blend`。

插件会根据 MaterialInstance JSON 选择 Base Color、Normal、Roughness、Metallic、ORM 和
Opacity。Unreal 法线是 DirectX `Y-`，插件会把绿色通道转换为 `1-G`。复杂皮肤、眼睛、
头发和布料 Shader 仍只是 Blender 基础预览近似，需要人工校正。

### A7.3 绑定 Tifa 手套或同骨架配件

1. 先用插件导入主体；
2. 在“4. 独立配件/武器”的“配件/武器模型”选择 `WE0002_00.psk`；
3. 点击“导入并绑定同骨架配件”；
4. 插件会验证实际权重骨名和 local rest/bind 矩阵，成功后把配件改绑主体骨架并删除
   重复配件骨架；不兼容时会回滚本次配件，保留主体；
5. 在主体骨架 Pose Mode 轻微旋转腕部/手指测试随动，撤销测试后保存 `.blend`。

这里复用的是 PSK 自带权重，不要对手套重新计算自动权重。

---

# B. FINAL FANTASY VII REMAKE INTERGRADE

## B1. 已验证配置

| 项目 | 值 |
|---|---|
| 游戏目录 | `D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE` |
| Paks 目录 | `D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE\End\Content\Paks` |
| UE Viewer | `E:\tools\umodel_ff7remake\umodel_FFVII_intergrade_v8.exe` |
| 引擎覆盖 | `ue4.18` |
| 默认输出 | `D:\ff7remake_exports\umodel_original` |
| 模型格式 | ActorX `.pskx` |
| 贴图格式 | PNG；HDR 保留 `.hdr` |

通用 FModel 可以浏览 Remake 目录，但该版本使用未版本化属性和自定义 bulk data；没有完全
匹配的 `.usmap` 时不能可靠反序列化角色。实际模型导出使用 Remake Intergrade 专用的
UE Viewer v8，不要用普通 UModel 或 Rebirth 的 FModel profile 替代。

## B2. 配置 AES key

包装脚本要求通过参数或环境变量提供自己合法取得的 AES key。推荐只在当前 PowerShell
会话中临时读取：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
$env:FF7REMAKE_AES_KEY = Read-Host 'FF7 Remake AES key'
```

不要把 key 直接写进 `ff7remake_export.ps1`、README、Git 配置或命令历史。脚本会把 key
写入随机临时文件，用 `-aes=@file` 传给 UE Viewer，并在 `finally` 中删除临时文件，避免
key 直接出现在 UE Viewer 进程命令行。

完成全部 Remake 导出后清除当前会话变量：

```powershell
Remove-Item Env:FF7REMAKE_AES_KEY
```

## B3. 用 Tifa 标准版验证导出

运行：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
$env:FF7REMAKE_AES_KEY = Read-Host 'FF7 Remake AES key'

.\ff7remake_export.ps1 -Package `
  'End/Content/GameContents/Character/Player/PC0002_00_Tifa_Standard/Model/PC0002_00.uasset'

Remove-Item Env:FF7REMAKE_AES_KEY
```

默认导出原版资源。脚本会暂时把
`End\Content\Paks\~mods` 顶层的 `.pak` 改成 `.pak.codex-disabled`，无论成功或异常都在
`finally` 中恢复。除非明确要导出 Mod 覆盖后的模型，否则不要加 `-IncludeMods`。

已验证的 Tifa 主模型：

```text
D:\ff7remake_exports\umodel_original\GameContents\Character\Player\PC0002_00_Tifa_Standard\Model\PC0002_00.pskx
```

同批次还会导出引用的 `.mat`、PNG 和 HDR 贴图。已验证结果为 `82,059` 顶点、
`103,206` 个多边形、`481` 根骨骼、`10` 个材质槽和 `3` 个 UV 层。

## B4. 导出 Cloud、Barret、Tifa 和服装变体

Remake Player 根路径比 Rebirth 多一层 `GameContents`：

```text
End/Content/GameContents/Character/Player/<角色或服装>/Model/
```

标准角色示例：

```text
Cloud  : PC0000_00_Cloud_Standard/Model/PC0000_00.uasset
Barret : PC0001_00_Barret_Standard/Model/PC0001_00.uasset
Tifa   : PC0002_00_Tifa_Standard/Model/PC0002_00.uasset
```

多个模型可以一次传入：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
$env:FF7REMAKE_AES_KEY = Read-Host 'FF7 Remake AES key'

.\ff7remake_export.ps1 -Package @(
  'End/Content/GameContents/Character/Player/PC0000_00_Cloud_Standard/Model/PC0000_00.uasset',
  'End/Content/GameContents/Character/Player/PC0001_00_Barret_Standard/Model/PC0001_00.uasset',
  'End/Content/GameContents/Character/Player/PC0002_00_Tifa_Standard/Model/PC0002_00.uasset'
)

Remove-Item Env:FF7REMAKE_AES_KEY
```

Tifa 的常见服装目录包括：

```text
PC0002_01_Tifa_PurpleDress
PC0002_02_Tifa_ChinaDress
PC0002_03_Tifa_WutaiDress
PC0002_04_Tifa_NoGlove
```

服装主网格通常与目录前面的编号同名，但仍应先在 FModel/UE Viewer 目录树中确认实际
`.uasset` 名称，再把完整包路径交给脚本。不要一次导出整个 `Player` 根目录：它会带入
大量动画和共享依赖，产物难以核对且可能占用几十 GB。

本机原版 pak 实际枚举出的 `36` 个 Player 主模型见
[`docs/ff7remake-player-model-inventory.md`](../../docs/ff7remake-player-model-inventory.md)。

## B5. Remake 包装脚本参数

```text
-Package <string[]>       必填；一个或多个完整 Unreal 包路径
-GameRoot <path>          覆盖默认游戏根目录
-OutputRoot <path>        覆盖默认输出根目录
-UmodelExe <path>         覆盖专用 UE Viewer 路径
-AesKey <string>          不推荐；优先使用临时环境变量
-WithAnimations           允许导出动画；默认关闭
-AllLods                  导出全部 LOD
-AllWeights               保留全部骨骼影响
-IncludeMods              不隔离 ~mods，导出 Mod 覆盖后的资源
-NoOverwrite              跳过已存在文件
```

例如另存到独立目录并跳过已有文件：

```powershell
.\ff7remake_export.ps1 `
  -Package 'End/Content/GameContents/Character/Player/PC0002_01_Tifa_PurpleDress/Model/PC0002_01.uasset' `
  -OutputRoot 'D:\ff7remake_exports\tifa_dresses' `
  -NoOverwrite
```

默认不导出动画，因为角色包的引用范围可能产生巨大的 `.psa`。只有明确知道目标动画包时
才使用 `-WithAnimations`，并先确认磁盘剩余空间。

## B6. 在 Blender 中导入 Remake

Remake 当前不使用 `ff7rebirth_tools.py` 自动配材质，因为两作的目录和材质语义不同。

1. Blender 选择 `File > Import > Unreal PSK (.psk/.pskx)`；
2. 选择目标角色的 `.pskx`；
3. 保持 Vertex Normals、Extra UVs、Vertex Colors 和 Skeleton 开启；
4. 检查场景中生成一个网格和一个骨架，确认网格有 Armature modifier 和顶点组；
5. 根据导出目录中的 `.mat` 连接基础材质：
   - `Diffuse` → Principled BSDF 的 Base Color；
   - `Normal` → Normal Map 节点 → Normal；
   - 明确的 `*_A`/Opacity → Alpha，并按需要设置材质 Blend Mode；
   - `_M`、`_B`、`_O` 等游戏专用打包/遮罩图要逐材质检查通道，不能统一猜测；
6. 保存到独立 `.blend`，不要覆盖原始 `.pskx`、`.mat` 和贴图目录。

已完成的 Tifa 验证文件：

```text
D:\ff7remake_exports\umodel_original\Tifa_Remake_validation.blend
D:\ff7remake_exports\umodel_original\Tifa_Remake_validation.png
D:\ff7remake_exports\umodel_original\Tifa_Remake_validation.json
```

验证模型是接近 A-pose 的游戏 bind pose。原验证图中的“手腕断开”并不是
KineDriver/Bonamik 或主体权重错误，而是标准服装把完整手掌和护臂放在独立 Weapon
SkeletalMesh 中；只导入 `PC0002_00.pskx` 会缺少这层网格。默认皮手套的准确路径是：

```text
End/Content/GameContents/Character/Weapon/WE0002_00_Tifa_LeatherGlove/
```

其中主网格为 `Model/WE0002_00.uasset`，还需要保留同目录的 Material 和 Texture。UE Viewer
不能完整重建 Remake 的 Renderer 复杂 Shader，因此基础材质仍只是预览近似。

### B6.1 用 Blender 3.6 合并默认手套

已导出的手套 ActorX 和贴图位于：

```text
D:\ff7remake_exports\umodel_glove_raw\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk
D:\ff7remake_exports\umodel_glove_raw\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Texture\
```

运行自动校验和绑定脚本：

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background `
  'D:\ff7remake_exports\umodel_original\Tifa_Remake_validation.blend' `
  --python 'E:\code\othercode\ripper_tpose\scripts\final\fix_ff7remake_tifa_gloves.py' -- `
  --glove 'D:\ff7remake_exports\umodel_glove_raw\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk' `
  --textures 'D:\ff7remake_exports\umodel_glove_raw\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Texture' `
  --output 'D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed.blend' `
  --render 'D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed.png' `
  --closeup 'D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed_gloves.png' `
  --report 'D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed.json'
```

脚本不会重新计算自动权重。它会校验手套的实际权重骨名与主体 local rest/bind 矩阵，
复用 PSK 自带权重改绑主体骨架，删除重复骨架，并临时旋转一根权重骨骼验证实际形变后复位。
本机结果为 `13,110` 个手套顶点、`19,634` 个多边形、`30` 根权重骨骼，缺失骨骼为
`0`，最坏 rest 矩阵差为 `6.56e-7`。

---

## 3. 导出完成后的统一验收

### 3.1 检查 ActorX 文件头

把 `$model` 改成实际文件：

```powershell
$model = 'D:\ff7remake_exports\umodel_original\GameContents\Character\Player\PC0002_00_Tifa_Standard\Model\PC0002_00.pskx'
$bytes = [IO.File]::ReadAllBytes($model)
[Text.Encoding]::ASCII.GetString($bytes, 0, 8)
```

正确结果：

```text
ACTRHEAD
```

同时确认：

- 文件大小不是 `0`；
- Blender 能创建 Mesh、Armature、材质槽、UV 和顶点组；
- 旋转一根非辅助骨骼时网格随动，撤销后恢复；
- 贴图路径没有被打平，JSON/`.mat` 仍能定位引用；
- 原版导出后 `~mods` 中不存在遗留的 `.codex-disabled`；
- Remake PowerShell 会话结束前已经执行
  `Remove-Item Env:FF7REMAKE_AES_KEY`。

### 3.2 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| Rebirth FModel 看不到包或 archive disabled | profile/mapping/AES 未正确配置 | 选择专用 Rebirth profile，重新加载匹配的 `.usmap`，在 FModel 本地配置合法 key |
| Rebirth glTF 报 `Invalid Tangent` | 当前 CUE4Parse glTF tangent 路径不兼容 | 改用 ActorX + First Level Only |
| Rebirth 皮肤出现三角形金属反光 | PSK 分裂法线/Auto Smooth 不兼容 | 使用 FF7RB 面板“修复 PSK 三角反光” |
| Rebirth Tifa 手掌缺失 | 手套是独立 Weapon 网格 | 导出 `WE0002_00`，用“导入并绑定同骨架配件” |
| Remake FModel 能浏览但模型打开失败 | 缺少匹配未版本化属性布局 | 使用专用 `umodel_FFVII_intergrade_v8.exe` 导出 |
| Remake 导出的是 Mod 模型 | 使用了 `-IncludeMods` 或 Mod 未隔离 | 默认不加 `-IncludeMods`，检查 `~mods` 后重新导出到新目录 |
| Remake 脚本提示缺少 AES key | 当前会话未设置环境变量 | 用 `Read-Host` 设置 `FF7REMAKE_AES_KEY`，结束后清除 |
| Remake Tifa 手腕断开或手掌缺件 | 默认皮手套是独立 Weapon 网格，只导出了主体 | 导出 `WE0002_00_Tifa_LeatherGlove`，运行 `fix_ff7remake_tifa_gloves.py` |
| 模型有材质槽但全白 | 只导出了网格，或贴图路径被打平 | 补导 JSON/`.mat` 和贴图，恢复完整目录层级 |
| PSK 菜单不存在 | `io_scene_psk_psa` 未安装或版本不兼容 | Blender 3.6 安装并启用 5.0.6 |

## 4. 进一步资料

- Rebirth 完整原理、mapping、tangent 与材质说明：
  [`docs/final-fantasy-vii-rebirth-extraction.md`](../../docs/final-fantasy-vii-rebirth-extraction.md)
- Rebirth Player 导出清单：
  [`docs/ff7rebirth-player-export-inventory.md`](../../docs/ff7rebirth-player-export-inventory.md)
- Remake 专用 UE Viewer 与 Tifa 验证记录：
  [`docs/final-fantasy-vii-remake-extraction.md`](../../docs/final-fantasy-vii-remake-extraction.md)
- FModel 官方入门：
  [FModel Getting Started](https://github.com/4sval/FModel/wiki/Getting-Started)
- UE Viewer 官方项目：
  [UE Viewer / UModel](https://www.gildor.org/en/projects/umodel)
