# Rise of Eros 脚本说明

Rise of Eros 角色提取、材质整理与格式转换脚本。整体链路：

```
游戏 AssetBundle
   │  ① extract_character.ps1      （游戏机 PowerShell，调 AssetStudioModCLI）
   │      ├─ convert_fbx.py        （加 -Format 时被它自动调用，白模转换）
   │      └─ export_nude_models.ps1（nude:<id> 时被它自动委派，带材质批量导出）
   ▼
FBX + 贴图 PNG  （D:\roe_exports\<角色>\）
   │
   ├─ ② roe_xps_addon.py           （Blender 插件：导入 → 挂材质 → 导出 XPS）
   │     ▼
   │  .mesh + 贴图  （XNALara / XPS 直接打开）
   │
   └─ ③ export_character_models.ps1（无头批量：挂材质 → 打包贴图 → 渲预览）
         ▼
      .blend + 预览 PNG  （D:\roe_exports\<角色>\blend\）
```

> 提取内核是 **AssetStudio**（命令行版 AssetStudioModCLI，aelurum 维护分支）。
> **不是 AssetRipper**——那个只当过备选、没用上（名字相近，别记混）。背景见
> [rise-of-eros-extraction.md](../../docs/rise-of-eros-extraction.md) §2。

| 脚本 | 在哪运行 | 作用 | 详细文档 |
|---|---|---|---|
| `extract_character.ps1` | 游戏机 PowerShell | 从 AssetBundle 提取带骨架 FBX（+贴图/格式转换/裸模入口） | [usage.md](../../docs/usage.md) |
| `export_nude_models.ps1` | 游戏机 PowerShell | A–M 基础裸模批量生成带材质 Blend/FBX/XPS/PMX/GLB | 本页 §4 |
| `export_nude_model_blender.py` | 被上一脚本调用（Blender 无头） | 裸模身体/脸六槽分区、材质校验、贴图打包 | 内部 worker |
| `export_character_models.ps1` | 游戏机 PowerShell | **穿衣**角色批量生成带材质 .blend + 预览图 | 本页 §5 |
| `export_character_model_blender.py` | 被上一脚本调用（Blender 无头） | 穿衣角色材质重建、贴图打包、三视图预览合成 | 内部 worker |
| `html/make_gallery.py` | 任意 Python 3 | 按 manifest 生成可浏览的模型总览网页 | 本页 §5 |
| `prune_exports.py` | 任意 Python 3 | 清理导出目录里的重复贴图副本与 Blender 备份 | 本页 §5 |
| `roe_xps_addon.py` | Blender 3.6 插件 | HD 角色一步步转带材质的 XPS（**主推**） | [xps-addon.md](../../docs/xps-addon.md) |
| `blender_face_materials.py` | Blender 脚本 | 挂材质（插件第 2 步的独立脚本版） | [face-eye-materials.md](../../docs/face-eye-materials.md) |
| `convert_fbx.py` | 被 ps1 调用（Blender 无头） | FBX → XPS/PMX/GLB **白模**转换 | 本页 §8 |

功能新增、操作变化和实现原理统一追加到 [更新日志](../../docs/CHANGELOG.md)。

---

## 1. 环境准备（一次性）

依赖工具的路径写死为脚本参数默认值，环境不同用参数覆盖：

| 依赖 | 默认路径 | 覆盖参数 | 用途 |
|---|---|---|---|
| 游戏本体 | `D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros` | `-GameRoot` | AssetBundle 来源 |
| 运行时资源缓存 | `%USERPROFILE%\AppData\LocalLow\Pinkcore\Rise of Eros\AssetBundles` | `-CacheRoot` | 运行时下载的新角色 |
| AssetStudioModCLI | `E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe` | `-CliExe` | FBX/贴图提取 |
| Blender 3.6 | `D:\Program Files\blender-3.6.15-windows-x64\blender.exe` | `-BlenderExe` | 格式转换、裸模导出、插件宿主 |
| Noesis | `E:\tools\noesisv\Noesis.exe` | `-NoesisExe` | 可选，XPS 快速通道 |
| 输出根目录 | `D:\roe_exports` | `-OutputRoot` / `-SourceRoot` | 所有提取产物 |

Blender 侧插件（装进 **被调用的那个** Blender 3.6）：

| 插件 | 需要它的功能 |
|---|---|
| **roe_xps_addon.py**（本仓库） | HD 角色带材质 XPS（§6）；裸模 worker 也复用它的算子 |
| **XNALaraMesh**（或 b2xps） | 一切 XPS 导出；addons 目录名 `XNALaraMesh` / `XNALaraMesh-master` 均可识别 |
| **mmd_tools** | 仅 PMX 导出 |

`roe_xps_addon.py` 安装：`Edit > Preferences > Add-ons > Install...` 选本文件并勾选启用
（实际复制到 `%APPDATA%\Blender Foundation\Blender\3.6\scripts\addons\`）。

> **⚠️ 更新插件后必须重启 Blender**——Install 覆盖的只是磁盘文件，内存里跑的还是
> 旧代码。旧版遗留的残缺 'XPS Shader' 节点组会让导入 .mesh 报 `KeyError: 'Alpha'`
> （新版会自愈，但前提是新代码真的加载了）。

> **⚠️ 脚本放置：所有 .ps1 与它们的 worker 必须在同一目录。** 每个 ps1 都按
> **自身所在目录**找同伴：`extract_character.ps1` 要 `convert_fbx.py`、
> `export_nude_models.ps1`、`export_nude_model_blender.py`、`roe_xps_addon.py`；
> `export_character_models.ps1` 要 `export_character_model_blender.py` 和
> `roe_xps_addon.py`。拆开搬运会报 `... not found`（目录整体放哪都行，文件要成组搬）。

---

## 2. 快速开始

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos

# 列出全部可提取角色 ID + 17 套材质化裸模
.\extract_character.ps1 -List

# 场景 A：提取一个 HD 角色（FBX + 贴图，之后进 Blender 挂材质）
.\extract_character.ps1 g11 -ExportTextures

# 场景 B：导出一套带材质的基础裸模（缺源时自动先补常规提取）
.\extract_character.ps1 nude:b01 -Format blend,fbx,xps,glb

# 场景 C：HD 角色快速转白模 XPS（无材质，一般不如走插件）
.\extract_character.ps1 g11 -Format xps

# 场景 D：把已提取的穿衣角色批量做成带材质 .blend + 预览图（无头，不用开 Blender）
.\export_character_models.ps1 -Only g11
```

- 场景 A 之后 → 打开 Blender，按 §6 的插件三步得到带材质 XPS。
- 场景 B 产物在 `D:\roe_exports\nude_materials\`，`.blend` 内嵌贴图开箱即用。
- 场景 C 产物是**白模**；要材质必须走 §6 或场景 D。
- 场景 D 产物在 `D:\roe_exports\g11\blend\`，`.blend` 旁边就是预览图；不加
  `-Only` 就是全量批处理（见 §5）。

---

## 3. extract_character.ps1 —— 提取角色

在**游戏所在机器**上用 PowerShell 运行。

### 参数

| 参数 | 说明 |
|---|---|
| `<ids>`（位置参数） | 角色 ID，逗号分隔（`a01,b02`）；`nude:<id>` 走裸模流程 |
| `-Format` | 普通角色：`xps,pmx,glb`（FBX 之外追加转换）；裸模：`blend,fbx,xps,pmx,glb`，缺省 `blend` |
| `-ExportTextures` | 同时导出全部贴图 PNG 到 `_textures\`（**推荐**，后面挂材质要用） |
| `-IncludeShare` | 加载 `*share*` 公共包（慢，个别角色缺件时用） |
| `-List` | 列出全部角色 ID 与 17 套 `nude:<id>` |
| `-KeepStage` | 保留中间 stage 目录（排查用） |
| `-Force` | **仅作用于 `nude:<id>`**：覆盖已有裸模产物；普通提取本来就总是重跑并覆盖 |
| 路径参数 | 见 §1 依赖表 |

常用命令：

```powershell
.\extract_character.ps1 -List                    # 列出全部可提取角色 ID
.\extract_character.ps1 g11 -ExportTextures     # FBX + 全部贴图
.\extract_character.ps1 nude:b01 -Format xps,fbx # 导出材质化 B01 裸模
```

脚本会合并游戏安装目录与运行时下载缓存；同名 AssetBundle 优先使用更新时间更晚的
版本，同时从安装目录补齐公共包。`-List` 同时识别 armor 和 bare 模型，因此新角色、
活动角色和只有裸模的 NPC 不需要等待 Steam 安装目录更新。

`nude:<id>` 会委派给 `export_nude_models.ps1`（§4），并在 `D:\roe_exports\<id>\`
缺少 FBX 或 Albedo 贴图时**自动先补一次带 `-ExportTextures` 的常规提取**——新机器上
直接 `nude:b01` 即可，无需手动预热。

### 提取结果中的关键目录（以 a07 为例）

`D:\roe_exports\a07\` 里用于 Blender 挂材质的关键内容是：

- **模型来源**：`pc_a07_hd (1)\FBX_GameObjects\pc_a07_hd\pc_a07_hd.fbx`
- **ROE 贴图目录**：`D:\roe_exports\a07\_textures\`

`(1)` 不是模型版本号，而是 AssetStudio 遇到同名 Unity 根对象时自动添加的防覆盖
后缀。当前 a07 的无后缀 `pc_a07_hd` 只有一个身体材质槽，会导致双腿和服装错误地
共用 `body1`；`pc_a07_hd (1)` 才保存了正确的四槽 `body1/body2` 面分区。因此在
ROE 面板中不要只凭目录名选择第一份 FBX，应优先选择这份带 `(1)` 且包含完整材质
分区的 FBX，并把 `_textures` 指定为贴图目录。

> **⚠️ 重跑会清空输出目录：** 再次提取同一角色时，`D:\roe_exports\<角色>\`
> **整个目录**（含 `_textures\`）先删后建。自己的产物——XPS 导出、烘焙贴图、
> 改过的文件——**不要放在这个目录里**，放到外面（如 `D:\roe_exports\xps_export\`）。
> 踩过的坑：导出的 .mesh 旁边的贴图被重提取连带清空，导回全黑。

### 旧导出出现白脸

如果身体已有贴图，但脸或头发仍为白色，先检查 `_textures` 是否包含当前体型的
公共头部贴图。例如 g03 至少需要：

```text
pc_g_nk_face_rgbx_Albedo.png
pc_g_nk_eye_iris_rgbx_Albedo.png
pc_g_nk_eyebrow_rgbx_Albedo.png
pc_g_nk_hair_rgbx_Albedo.png
```

缺少这些文件通常表示角色目录由旧版流程或不完整的 AssetBundle 集合导出。当前
脚本会自动合并 `pc_g_common` 公共包，备份自己的产物后重新运行
`.\extract_character.ps1 g03 -ExportTextures`，再在 Blender 中重新点击
“检查并准备材质”即可。不要通过修改 UV、权重或把身体贴图强行挂到脸上来处理；
那些数据并没有损坏。

---

## 4. export_nude_models.ps1 —— 批量导出带材质裸模

游戏的角色编号按字母共享基础裸体：`a02/a03/...` 使用 `a01` 基础体，B–M 同理。
本脚本一次处理 17 套：

- `a00`（独立通用体，两网格/两材质）；
- `a01` 至 `m01` 的 13 套字母基础体；
- `e01_fm`、`f01_fm`、`g01_fm` 三套额外变体。

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
.\export_nude_models.ps1                 # 全部 17 套，默认输出内嵌贴图的 .blend
```

本脚本读取 `-SourceRoot`（默认 `D:\roe_exports`）里各角色的常规提取产物。经
`extract_character.ps1 nude:<id>` 入口调用时，缺失的角色会自动先补一次带
`-ExportTextures` 的常规提取；**直接运行本脚本时请先自行提取对应角色**。

### 参数

| 参数 | 说明 |
|---|---|
| `-Only` | 只处理指定基础体（`a01,b01` 或 `nude:b01` 写法均可） |
| `-Format` | `blend,fbx,xps,pmx,glb` 任意组合，缺省 `blend` |
| `-ValidateOnly` | 只导入 + 校验材质，不写任何产物 |
| `-Force` | 覆盖已有产物（缺省时全部产物已存在的模型会 SKIP） |
| `-List` | 列出 17 套可选裸模 |
| `-IncludeA00` / `-IncludeFm` | 布尔，缺省 `$true`；排除 a00 或 fm 变体 |
| `-KeepTemp` | 保留贴图临时归集目录 |
| `-OutputDir` | 输出目录，缺省 `D:\roe_exports\nude_materials` |
| 其余路径参数 | 见 §1 依赖表 |

常用检查：

```powershell
.\export_nude_models.ps1 -ValidateOnly                            # 只验证
.\export_nude_models.ps1 -Only a01,b01,l01                        # 只处理指定基础体
.\export_nude_models.ps1 -List                                    # 查看 17 套清单
.\export_nude_models.ps1 -Only b01 -Format blend,fbx,xps,pmx,glb -Force  # B01 全格式
```

### 产物与 manifest

输出的每个 `.blend` 都把用到的图片打包进文件，不依赖原 `_textures` 路径；FBX、XPS、
PMX、GLB 分别进入同名子目录。便携格式会先把 Blender 程序化眼球烘成眼白+虹膜贴图；
XPS/PMX 同目录保留所需 PNG，FBX 与 GLB 内嵌纹理。同目录另有
`nude_models_manifest.json`，记录源 FBX、各格式路径、材质数、贴图名、身体/脸分区、
便携眼球烘焙状态和失败原因（含 traceback）。`-ValidateOnly` 的结果单独写入快照
`nude_models_manifest.validate.json`，不会触碰正式 manifest 里已记录的导出路径。
`-Only` 补导单个模型/格式时按 17 套规范顺序**合并**进已有 manifest，不会把完整清单
覆盖成一条。

### 六槽分区原理与限制

裸模与 HD 服装不同：头、身体、眼睛和口腔部件在同一个 `*_nk_body` 网格中。普通 ROE
材质操作会把未识别区域都当作 face；批处理 worker 因此额外建立六槽分区：
`body / face / eye / lash / brow / overlay`，并在对象上写 `roe_nude_slots` 标记供 XPS
导出识别（XPS 内部分件为 `5_body / 5_face / 5_eye / 7_lash / 7_brow`，overlay 不导出）。
身体、脸和眼球必须同时有非零面数，否则该模型判定失败。B01 的眼球约为 80% `Eyeball`、
20% `Head` 权重；脚本会同时检查球体拓扑和完整 0–1 虹膜 UV，不会再因旧版 90% 权重
门槛把眼球误分到脸。贴图归集只接受同字母体型；缺少公共脸部贴图时从
`chara_tex_bare_pc_<字母>_common*` 临时解码，不会错误回退到其他角色的脸。

材质范围是当前仓库已验证的 Blender 近似：身体与脸 Albedo、皮肤饱和度、程序化眼球、
睫毛/眉毛透明和头发 Alpha。Unity 原生 Toon/NPR Shader、MGAC 全通道和法线表现没有
1:1 复刻；因此这里的“带材质”不等于游戏渲染器逐像素一致。

---

## 5. export_character_models.ps1 —— 批量导出穿衣角色 blend + 预览图

§4 只处理 17 套**裸模基础体**。本脚本是它的**穿衣角色**对应物：把
`extract_character.ps1` 提取出来的每个角色目录挑出最合适的模型 FBX，用插件算子重建
材质，写出内嵌贴图的 `.blend`，并在旁边渲染**一张**三视图预览 PNG（3/4 + 正面 +
头部特写）。

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos

.\export_character_models.ps1 -List          # 看有哪些可转、各自用哪份 FBX
.\export_character_models.ps1                # 全部转换，已有产物跳过
.\export_character_models.ps1 -Only m02,g11  # 只转指定角色
.\export_character_models.ps1 -Force -Format blend,glb
```

### 参数

| 参数 | 说明 |
|---|---|
| `-Only` | 只处理指定角色；写 `<id>` 会连同该角色的 `outfit` 变体一起选中，写 `<id>_outfit1` 只选那一套 |
| `-Format` | `blend`、`glb` 或两者，缺省 `blend` |
| `-IncludeOutfits` | 布尔，缺省 `$true`；关掉则只转每个角色的主模型 |
| `-NoPreview` | 不渲染预览图。省下的时间很少（实测 g11 单模型 5.1s → 4.7s，约 9%），耗时大头是导入和打包，一般没必要关 |
| `-ValidateOnly` | 只导入 + 检查材质，不写任何产物 |
| `-Force` | 覆盖已有产物（缺省时 `.blend` 与预览图都在的模型会 SKIP） |
| `-List` | 列出可转模型、源 FBX 和输出目录 |
| `-ManifestPath` | 自定义 manifest 路径；**多进程分片并行时必须给每个分片各一个**，默认那一个文件不支持并发写 |
| `-SourceRoot` / `-BlenderExe` | 见 §1 依赖表 |

### 产物

每个角色的产物都留在自己的目录里，不集中到一处：

```text
D:\roe_exports\<id>\blend\<stem>.blend          # 贴图已打包进文件
D:\roe_exports\<id>\blend\<stem>_preview.png    # 三视图合成预览
D:\roe_exports\<id>\blend\glb\<stem>.glb        # 仅 -Format glb 时
D:\roe_exports\character_models_manifest.json   # 全量清单
```

manifest 逐模型记录源 FBX、产物路径、网格/材质槽/贴图数与三个检查字段：

| 字段 | 含义 |
|---|---|
| `untexturedSlots` | 最终仍没有 Base Color 的槽（纯透明槽不算），需要人工确认 |
| `recoveredSlots` | 被下面的二次解析补挂的槽，格式 `网格[槽] <- 贴图名` |
| `familyMismatches` | 挂上了**别的**字母体型的公共脸/发贴图——出现即异常，必须排查 |

失败条目另带 `error` 与完整 traceback。

### 选模规则

- 候选按 `pc_<id>_hd.fbx` → `pc_<id>_ld.fbx` → `pc_<id>_nk.fbx` →
  `Prefab_pc_<id>_nk_model.fbx` → `pc_<id>_nk_bs.fbx` 收集**全部**匹配项，
  同名多份按体积取大的那份（即 §3 说的带 `(1)`、材质分区完整的那份）。
- worker 按顺序逐个导入，**先检查真有网格再挂材质**，第一个出网格的胜出。
  `*_nk_bs.fbx` 常常只是骨架壳，放在最后正是为此。
- `pc_<id>_outfit<N>_hd.fbx` 作为独立条目追加，key 为 `<id>_outfit<N>`。
- 贴图目录取 `<id>\_textures\`，没有该目录时退回角色目录本身。

### NOMESH：不是失败

两种角色不产出模型，记为 `NOMESH`：只有 `chara_bare_pc_<id>_nk.ab` 的活动 NPC
（包里只有场景/道具数据），以及全部候选都是纯骨架壳的（d10 / e11 / i06 只有
0.3 MB 的 `*_nk_bs.fbx`）。这两类的本体都复用同字母基础体，是资源本身的性质。

### 二次贴图解析

插件挂完材质后，仍没有 Base Color 的槽会再查一次 Albedo 索引，探针逐级放宽：
原名 → 去尾部 `hd/ld` → 去尾部数字 → 武器再试角色自己的 `wp_<id>` 图集。这解决
网格比图集编号更细的情况（`pc_h08_hd_armor01` ← `pc_h08_hd_armor`）以及武器网格
按手部插槽命名的情况（`wp_a_R` ← `wp_a_12`）。

> **只在唯一命中时才补挂。** 能匹配到两张图的一律留灰——挂错贴图比留灰更糟。
> e10 只出 body1/body2 两张图却有三个身体槽，第三个就按这条留空。

### 总览网页

`html\make_gallery.py` 读 manifest，把 120 张预览图缩成 JPEG 缩略图，生成一页可搜索、
可按体型筛选的总览：

```powershell
python html\make_gallery.py          # 产出 html\index.html，浏览器直接打开
python html\make_gallery.py --force  # 预览图变了但时间戳没变时强制重建缩略图
```

每张卡片给出模型名、源 FBX、blend 完整路径（带复制按钮）、网格/材质槽/贴图数与体积，
缺贴图和被二次解析补挂的槽各有一个角标；附录是导出脚本用法；末尾列出 17 个
NOMESH 的 ID。页面用 `file://` 链接本机文件，**缩略图写到
`D:\roe_exports\_gallery\thumbs\` 而不是仓库**——仓库不收任何游戏素材。换机器或换
导出根目录后重新跑一次即可（`--source-root` 可改）。

### 清理导出目录（prune_exports.py）

`extract_character.ps1` 每次运行都会把**每张贴图存两遍**：一份进 `<id>\_textures\`，
另一份跟着每个对象再复制到 `<id>\<对象>\FBX_GameObjects\` 下。管线只读 `_textures`，
后者纯属占地方——128 个角色的树上这部分有 **18 GB**。重新提取会再长回来，所以这是
一个需要不时跑一次的维护脚本。

```powershell
python prune_exports.py            # 空跑，只报告
python prune_exports.py --apply    # 真删
```

删除前逐个文件校验，不靠猜：

- 贴图副本**必须**在本角色 `_textures` 里有同名文件、且两者**哈希一致**才删；
- `.blend1` **必须**对应的 `.blend` 还在才删（孤儿备份是唯一副本，保留）；
- `_textures\` 与 `blend\` **不进入遍历**，成品和贴图本体碰不到。

缺省是空跑，`--apply` 才动手；`--skip-textures` / `--skip-backups` 可单独关掉某一类。
回归测试 `tests\test_prune_exports.py`（纯 Python，无需 Blender 和素材）用合成目录
覆盖了同名不同内容、无 `_textures` 的角色、受保护目录里的同名文件、孤儿 `.blend1`
等情形，并验证重复执行是幂等的。

> 顺带一提：**清理之前必须先有"只打包用到的贴图"那个修复**（见
> [避坑手册 #17](../../docs/roe-material-pitfalls.md)）。旧版 `pack_images()` 会去碰
> FBX 导入器创建、但没有任何材质使用的图片数据块，副本一删就打包失败。

### 限制

与 §4 一样，本脚本不复刻 Unity 的 Toon/NPR Shader、MGAC 全通道和法线表现，
“带材质”不等于游戏渲染器逐像素一致。预览图用 **Standard** 视图变换而不是 Blender
默认的 Filmic——Filmic 会把 Albedo 图集去饱和，那样的预览没法用来判断有没有挂错图。

---

## 6. roe_xps_addon.py —— HD 角色带材质 XPS（主推）

安装见 §1。3D 视口按 `N` → **ROE** 页签，按序点：
**1 导入 FBX → 2 检查并准备材质 → 3 导出 XPS(.mesh)**。

首次导入或不确定问题范围时使用完整的“检查并准备材质”。只有某一区域异常时，
可分别点击 **“修复脸部 / 修复身体 / 修复翅膀”**；三个按钮只替换各自识别到的材质槽，
不会顺带重建另外两类。翅膀与身体共用 mesh（如 g09）也按原始槽名隔离。
若眼球仍为纯白或脸色，点 **「修复眼睛」**，它会兼容骨骼权重缺失但仍保留
原始 `eye/eyes/iris` 材质名的角色（如 a08），只重新识别和设置眼球面。
**4 修正XPS骨架方向** 是导回 .mesh 后骨架躺地上时用的。
字段说明和故障排查见 [xps-addon.md](../../docs/xps-addon.md)。

> **⚠️ 路径填写：**
> - 「模型来源」→ a07 使用
>   `D:\roe_exports\a07\pc_a07_hd (1)\FBX_GameObjects\pc_a07_hd\pc_a07_hd.fbx`；
>   无后缀的 `pc_a07_hd` 缺少身体四槽材质分区。
> - 「贴图目录」→ 提取时 `-ExportTextures` 生成的 `D:\roe_exports\<角色>\_textures\`。
> - 「XPS 输出」→ **别放进 `D:\roe_exports\<角色>\`**（重提取会被清空，见 §3）。
>   输出目录和贴图目录不同时，插件会把用到的贴图自动复制过去；
>   之后手动挪 `.mesh` 的话同目录的 PNG 必须一起挪（XPS 按同目录文件名找贴图）。

自动准备后仍有局部材质错误时，按
[ROE 材质手动修复指南](../../docs/roe-manual-material-repair.md) 修复身体槽、透明罩
或头部所选面，不要直接删除几何或修改 UV/权重。

---

## 7. blender_face_materials.py —— 挂材质独立脚本

插件第 2 步的独立版本，**用插件就不需要它**；适合无头批处理或单独调参。

- 用法 A（GUI）：导入 FBX 后，Text Editor 打开本文件，
  **改文件头部的 `TEX_DIR`** 为贴图目录，再 Run Script。
- 用法 B（无头）：
  `blender --background --python blender_face_materials.py -- <fbx路径> <贴图目录> [输出.blend]`

眼球/睫毛/眉毛的原理和可调参数（虹膜半径、降饱和等）见
[face-eye-materials.md](../../docs/face-eye-materials.md)。

---

## 8. convert_fbx.py —— 格式转换助手（白模）

一般不直接用：`extract_character.ps1 <id> -Format xps/pmx/glb` 时被自动调用。手动调用：

```
blender --background --python convert_fbx.py -- <输入.fbx> <输出目录> <xps|pmx|glb>
```

| 格式 | 依赖（装在被调用的那个 Blender 里） |
|---|---|
| xps | XNALaraMesh（或 b2xps）插件已启用 |
| pmx | mmd_tools 插件 |
| glb | 无（Blender 内置） |

> **注意：这条转换不处理材质/贴图，导出的是白模。**
> 要带材质（含眼球/睫毛/眉毛修复）的 XPS，用 §6 的 roe_xps_addon.py；
> 要带材质的裸模多格式，用 §4 的 export_nude_models.ps1。

FBX 里没有网格/骨架时会明确报错退出（有的角色的 `nk_bs` 是纯空节点层级，
如 g02）；ps1 调用时会自动换下一个候选 FBX（一般是 `pc_<id>_hd`）重试。

---

## 9. 已知兼容坑速查

历史踩坑的根因、正确基线和禁止做法统一维护在
[ROE Blender 材质兼容避坑手册](../../docs/roe-material-pitfalls.md)；这里只留
「看到什么症状 → 做什么」的速查（自对应插件版本起自动处理，只需更新插件、重启
Blender 后重做对应步骤，**不要**改贴图文件名/UV/权重）：

| 角色 | 症状 | 自版本 | 操作 |
|---|---|---|---|
| g02 | body 贴图名把 `Albedo` 拼成 `Abedo`，身体白模 | v1.1.4 | 重新“检查并准备材质” |
| b02 | 左眼“眼镜片”状物（实为 `pc_b_nk_tears` 罩层）、下睫毛肤色 | v1.1.6 | 重新“检查并准备材质”；正确头部分槽 face `13920` / eye `864` / lash `804` / brow `228` / overlay `116`，身体 tear 槽 `32` 面纯透明 |
| g07 | 身体槽名含 `_hd_` 但 PNG 名省略，body1/body2 匹配失败 | v1.1.7 | 重新“检查并准备材质” |
| g09 | 翅膀黑底/实心卡片/黑色散点 | v1.1.9 | 重新准备材质并导出；wing 槽 Alpha Clip + RG7，身体仍 RG5 |
| e06 | 导入报 `KeyError: Root`，留下 4 个无材质半成品 | v1.1.10 | 删除半成品，用 `pc_e06_hd (1)` FBX 重新导入 |
| F10 | 身体正常但脸大面积消失/透明 | v1.1.11 | 点“修复脸部”；正确五槽 `15354/864/900/228/390` |
| i03/i04 | face 无贴图，日志报缺 `eye_iris`/`eyebrow` | v1.1.12 | 点“修复脸部”；i 体型回退 `pc_i_ld_eyes`，眉毛已烘进 face |
| B01 裸模 | 眼球槽存在但无面（80/20 权重混合） | nude 流程 | `nude:b01` 自动处理，worker 有 `eye > 0` 硬校验 |

---

## 10. 测试

`tests/` 下是 Blender 3.6 无头回归。**5 个合成 fixture 测试**无需任何素材：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
& "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" --background --factory-startup --python tests\test_head_material_semantics_blender.py
```

同样方式可跑 `test_texture_aliases`、`test_body_texture_variants`、
`test_xps_alpha_slots`、`test_fbx_missing_bind_compat`。每个测试成功时最后打印
`*_TEST=PASS` 标记。

`test_prune_exports.py` 是**纯 Python**、不需要 Blender：

```powershell
python tests	est_prune_exports.py
```

> **⚠️ Blender 在 Python 异常后仍可能以退出码 0 结束**，判断通过与否必须看
> `*_TEST=PASS` 标记，不能只看退出码。

**3 个集成测试**需要 `--` 之后传真实素材路径与期望值（按各文件头部的 assert 提示）：

| 测试 | 参数 |
|---|---|
| `test_face_family_matrix_blender.py` | `<fbx> <贴图目录> <face图> <eye图> <槽面数json> <transparent\|textured> [brow图]` |
| `test_i_family_materials_blender.py` | `<i体型fbx> <贴图目录> <期望face图名> <期望face面数>` |
| `test_source_texture_hint_body_blender.py` | `<pc_i03_hd.fbx> <i03贴图目录>` |

`test_fbx_missing_bind_compat` 也接受可选 `<E06 FBX> <贴图目录>` 做真实导入集成。
期望基线（面数矩阵）见[避坑手册](../../docs/roe-material-pitfalls.md)的回归矩阵表。

---

## 11. 当前部署速查（远程游戏机 haoni）

| 内容 | 位置 |
|---|---|
| 仓库同步副本 | `E:\code\othercode\ripper_tpose`（脚本在 `scripts\riseoferos\` 下，成对齐全） |
| 提取脚本副本 | `E:\tools\extract_character.ps1` + `convert_fbx.py`（从仓库复制；**只有这两个文件，`nude:<id>` 在这份副本上不可用**——裸模请在仓库目录运行，或把 §1 列出的脚本成组补齐） |
| 插件（已装） | `C:\Users\haoni\AppData\Roaming\Blender Foundation\Blender\3.6\scripts\addons\roe_xps_addon.py` |
| XNALaraMesh | 同上 addons 目录下 `XNALaraMesh-master\` |
| 提取输出 | `D:\roe_exports\<角色>\` |
| 裸模产物 | `D:\roe_exports\nude_materials\` |
