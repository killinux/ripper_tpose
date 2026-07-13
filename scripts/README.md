# scripts 说明

Rise of Eros 角色提取 → XPS 的四个脚本，整体链路：

```
游戏 AssetBundle
   │  ① extract_character.ps1   （游戏机 PowerShell，调 AssetStudioModCLI）
   │      └─ convert_fbx.py     （加 -Format 时被它自动调用）
   ▼
FBX + 贴图 PNG  （D:\roe_exports\<角色>\）
   │  ② roe_xps_addon.py       （Blender 插件：导入 → 挂材质 → 导出 XPS）
   ▼
.mesh + 贴图  （XNALara / XPS 直接打开）
```

> 提取内核是 **AssetStudio**（命令行版 AssetStudioModCLI，aelurum 维护分支）。
> **不是 AssetRipper**——那个只当过备选、没用上（名字相近，别记混）。背景见
> [rise-of-eros-extraction.md](../docs/rise-of-eros-extraction.md) §2。

| 脚本 | 在哪运行 | 作用 | 详细文档 |
|---|---|---|---|
| `extract_character.ps1` | 游戏机 PowerShell | 从 AssetBundle 提取带骨架 FBX（+贴图/格式转换） | [usage.md](../docs/usage.md) |
| `convert_fbx.py` | 被 ps1 调用（Blender 无头） | FBX → XPS/PMX/GLB 白模转换 | 本页 |
| `roe_xps_addon.py` | Blender 3.6 插件 | 一步步转带材质的 XPS（**主推**） | [xps-addon.md](../docs/xps-addon.md) |
| `blender_face_materials.py` | Blender 脚本 | 挂材质（插件第 2 步的独立脚本版） | [face-eye-materials.md](../docs/face-eye-materials.md) |

---

## extract_character.ps1 —— 提取角色

在**游戏所在机器**上用 PowerShell 运行。

> **⚠️ 放置位置：必须和 `convert_fbx.py` 在同一目录。**
> 脚本按自身所在目录找 convert_fbx.py，分开放会报
> `convert_fbx.py not found`（目录本身放哪都行，两个文件要成对搬）。

依赖工具的路径写死为参数默认值，环境不同用参数覆盖：

| 依赖 | 默认路径 | 覆盖参数 |
|---|---|---|
| 游戏本体 | `D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros` | `-GameRoot` |
| AssetStudioModCLI | `E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe` | `-CliExe` |
| Blender 3.6 | `D:\Program Files\blender-3.6.15-windows-x64\blender.exe` | `-BlenderExe`（仅 `-Format xps/pmx` 需要） |
| Noesis | `E:\tools\noesisv\Noesis.exe` | `-NoesisExe`（可选，XPS 快速通道） |
| 输出根目录 | `D:\roe_exports` | `-OutputRoot` |

常用命令：

```powershell
.\extract_character.ps1 -List                    # 列出全部可提取角色 ID
.\extract_character.ps1 g11 -ExportTextures     # FBX + 全部贴图（推荐，后面挂材质要用）
```

> **⚠️ 重跑会清空输出目录：** 再次提取同一角色时，`D:\roe_exports\<角色>\`
> **整个目录**（含 `_textures\`）先删后建。自己的产物——XPS 导出、烘焙贴图、
> 改过的文件——**不要放在这个目录里**，放到外面（如 `D:\roe_exports\xps_export\`）。
> 踩过的坑：导出的 .mesh 旁边的贴图被重提取连带清空，导回全黑。

---

## convert_fbx.py —— 格式转换助手（白模）

一般不直接用：`extract_character.ps1 -Format xps/pmx/glb` 时被自动调用。手动调用：

```
blender --background --python convert_fbx.py -- <输入.fbx> <输出目录> <xps|pmx|glb>
```

| 格式 | 依赖（装在被调用的那个 Blender 里） |
|---|---|
| xps | XNALaraMesh（或 b2xps）插件已启用 |
| pmx | mmd_tools 插件 |
| glb | 无（Blender 内置） |

> **注意：这条转换不处理材质/贴图，导出的是白模。**
> 要带材质（含眼球/睫毛/眉毛修复）的 XPS，用下面的 roe_xps_addon.py。

FBX 里没有网格/骨架时会明确报错退出（有的角色的 `nk_bs` 是纯空节点层级，
如 g02）；ps1 调用时会自动换下一个候选 FBX（一般是 `pc_<id>_hd`）重试。

---

## roe_xps_addon.py —— Blender 插件（主推）

### 安装

1. Blender **3.6** → `Edit > Preferences > Add-ons > Install...` → 选本文件 → 勾选启用。
2. Install 实际是把文件复制到用户 addons 目录：
   `%APPDATA%\Blender Foundation\Blender\3.6\scripts\addons\roe_xps_addon.py`
   （更新 = 再 Install 一次覆盖，或直接替换这个文件后重启）。

> **⚠️ 更新插件后必须重启 Blender**——Install 覆盖的只是磁盘文件，内存里
> 跑的还是旧代码。旧版遗留的残缺 'XPS Shader' 节点组会让导入 .mesh 报
> `KeyError: 'Alpha'`（新版会自愈，但前提是新代码真的加载了）。

**依赖**：XNALaraMesh 插件已安装并启用（第 3/4 步用到），
addons 目录名叫 `XNALaraMesh` 或 `XNALaraMesh-master` 都能识别。

### 使用

3D 视口按 `N` → **ROE** 页签，四个按钮按序点：
**1 导入 FBX → 2 挂材质(修眼睛) → 3 导出 XPS(.mesh)**；
**4 修正XPS骨架方向** 是导回 .mesh 后骨架躺地上时用的。
字段说明和故障排查见 [xps-addon.md](../docs/xps-addon.md)。

> **⚠️ 路径填写：**
> - 「贴图目录」→ 提取时 `-ExportTextures` 生成的 `D:\roe_exports\<角色>\_textures\`。
> - 「XPS 输出」→ **别放进 `D:\roe_exports\<角色>\`**（重提取会被清空，见上）。
>   输出目录和贴图目录不同时，插件会把用到的贴图自动复制过去；
>   之后手动挪 `.mesh` 的话同目录的 PNG 必须一起挪（XPS 按同目录文件名找贴图）。

---

## blender_face_materials.py —— 挂材质独立脚本

插件第 2 步的独立版本，**用插件就不需要它**；适合无头批处理或单独调参。

- 用法 A（GUI）：导入 FBX 后，Text Editor 打开本文件，
  **改文件头部的 `TEX_DIR`** 为贴图目录，再 Run Script。
- 用法 B（无头）：
  `blender --background --python blender_face_materials.py -- <fbx路径> <贴图目录> [输出.blend]`

眼球/睫毛/眉毛的原理和可调参数（虹膜半径、降饱和等）见
[face-eye-materials.md](../docs/face-eye-materials.md)。

---

## 当前部署速查（远程游戏机 haoni）

| 内容 | 位置 |
|---|---|
| 仓库同步副本 | `E:\code\othercode\ripper_tpose`（脚本在 `scripts\` 下，成对齐全） |
| 提取脚本副本 | `E:\tools\extract_character.ps1` + `convert_fbx.py`（从仓库复制，两处均可运行） |
| 插件（已装） | `C:\Users\haoni\AppData\Roaming\Blender Foundation\Blender\3.6\scripts\addons\roe_xps_addon.py` |
| XNALaraMesh | 同上 addons 目录下 `XNALaraMesh-master\` |
| 提取输出 | `D:\roe_exports\<角色>\` |
