# extract_character.ps1 使用文档

一键从 Rise of Eros 的 AssetBundle 中提取指定角色的**带骨架绑定模型**。

---

## 前置条件

远程游戏机(haoni)上需要以下工具已就绪:

| 工具 | 路径 | 用途 |
|---|---|---|
| AssetStudioModCLI | `E:\tools\AssetStudioModCLI_net472\...\AssetStudioModCLI.exe` | 解析 Unity AssetBundle、导出 FBX |
| Blender 3.6 | `D:\Program Files\blender-3.6.15-windows-x64\blender.exe` | 格式转换(XPS/PMX/GLB) |
| Noesis | `E:\tools\noesisv\Noesis.exe` | XPS 转换备选(更快) |
| Rise of Eros | `D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros` | 游戏资产来源 |

> 以上路径已写为默认值。若安装位置不同,用 `-CliExe`/`-BlenderExe`/`-NoesisExe`/`-GameRoot` 参数覆盖。

---

## 基本用法

```powershell
cd E:\tools   # 或脚本所在目录
```

### 列出所有可提取角色(103 个)

```powershell
.\extract_character.ps1 -List
```

输出:
```
Found 103 character IDs:
a01, a02, a03, ... k06, l01
```

### 提取单个角色(默认 FBX)

```powershell
.\extract_character.ps1 a01
```

产物: `D:\roe_exports\a01\` 下一批 FBX(带骨架+蒙皮权重+bind pose)。

### 提取多个角色

```powershell
.\extract_character.ps1 a01,b02,c03
```

每个角色输出到各自子目录(`D:\roe_exports\a01\`、`D:\roe_exports\b02\`…)。

---

## 格式转换(`-Format`)

默认只输出 FBX。加 `-Format` 自动转换为其他格式(在 FBX 基础上,自动挑选主体 body 网格做转换):

### 转 XPS(XNALara)

```powershell
.\extract_character.ps1 a01 -Format xps
```

优先用 Noesis 转(快、无 addon 依赖);Noesis 失败时自动回退 Blender + b2xps_addon。
产物: `D:\roe_exports\a01\xps\pc_a01_nk_bs.mesh.ascii`

### 转 PMX(MikuMikuDance)

```powershell
.\extract_character.ps1 a01 -Format pmx
```

用 Blender + mmd_tools 导出。
产物: `D:\roe_exports\a01\pmx\pc_a01_nk_bs.pmx`

### 转 GLB(glTF Binary)

```powershell
.\extract_character.ps1 a01 -Format glb
```

用 Blender 内置 glTF 导出(不依赖额外 addon)。
产物: `D:\roe_exports\a01\glb\pc_a01_nk_bs.glb`

### 同时导出多种格式

```powershell
.\extract_character.ps1 a01 -Format xps,pmx,glb
```

一次提取,FBX + 三种转换全出。

---

## 附加选项

### 导出贴图(`-ExportTextures`)

```powershell
.\extract_character.ps1 a01 -ExportTextures
```

同时导出角色相关的 Texture2D 为 PNG(BC7/DXT 自动解码)。
产物: `D:\roe_exports\a01\_textures\`

### 加载共享骨架包(`-IncludeShare`)

```powershell
.\extract_character.ps1 a01 -IncludeShare
```

同时加载 `chara_*share*` 包(共享骨架/动画)。通常**不需要**——骨架已内嵌在角色自身 bundle 里。如果发现导出的 FBX 骨骼残缺(只有 2-3 根骨),加上这个选项再试。

> 注意: `-IncludeShare` 会显著增加加载量(~1-2GB 额外),导出时间翻倍。

### 保留 stage 目录(`-KeepStage`)

```powershell
.\extract_character.ps1 a01 -KeepStage
```

默认提取完自动清理临时 stage 目录。加 `-KeepStage` 保留,方便调试或用 GUI 版 AssetStudio 再探索。

### 自定义输出路径(`-OutputRoot`)

```powershell
.\extract_character.ps1 a01 -OutputRoot E:\my_models
```

---

## 完整示例

```powershell
# 提取 a01 角色,含 XPS + GLB 格式转换 + 贴图
.\extract_character.ps1 a01 -Format xps,glb -ExportTextures

# 批量提取 5 个角色,只要 FBX
.\extract_character.ps1 a01,b01,c01,d01,e01

# 提取并保留 stage(之后用 GUI 探索其他资产)
.\extract_character.ps1 f01 -KeepStage -IncludeShare
```

---

## 输出目录结构

```
D:\roe_exports\a01\
  pc_a01_nk_bs\          # 主体 body(裸体+骨架+blendshape 标记)
    FBX_GameObjects\
      pc_a01_nk_bs\
        pc_a01_nk_bs.fbx       ← 3.5 MB, 158 骨骼, 385 skin cluster
  Prefab_pc_a01_nk_M01\   # 表情变体 #1
    ...
  Prefab_pc_a01_nk_M28\   # 表情变体 #28
    ...
  pc_a01_hd\               # HD 服装
    ...
  (配件类 ~300 个)
  xps\                     # -Format xps 时生成
    pc_a01_nk_bs.mesh.ascii
  pmx\                     # -Format pmx 时生成
    pc_a01_nk_bs.pmx
  glb\                     # -Format glb 时生成
    pc_a01_nk_bs.glb
  _textures\               # -ExportTextures 时生成
    *.png
```

---

## 导出的 FBX 包含什么

经二进制验证(a01):

| 项 | 数据 |
|---|---|
| 骨骼 | 158 根命名骨骼(Bip001 全身 + AC 面部,含物理/扭曲/道具骨) |
| 蒙皮权重 | 385 Cluster / 2 Skin deformer / BindPose 存在 |
| Bind pose | 作者原始中性 pose(A-pose 或 T-pose,不含动画) |
| 表情 | 28 个 morph target 作为独立 FBX(`Prefab_pc_<id>_nk_M01..M28`) |
| 服装 HD | 同骨架,可共享 Armature |

> **注意**: CLI `splitObjects` 模式把 blendshape 导成独立 FBX。
> 若要 blendshape 内嵌为 Shape Key,改用 GUI 版 AssetStudioMod
> 的 `Model > Export selected objects (merge)` 导出。

---

## Blender 导入

```
File > Import > FBX
  Automatic Bone Orientation: ON
  Scale: 1.0
```

导入后检查:
- Armature 存在,rest pose 是 T/A-pose
- 每个 mesh 有 Armature 修改器 + 按骨骼命名的顶点组(权重已在)
- Shape Keys(若用 GUI 导出)

---

## 故障排查

| 现象 | 原因 | 解法 |
|---|---|---|
| FBX 只有 2-3 根骨 | 共享骨架 bundle 没加载 | 加 `-IncludeShare` |
| PMX 导出失败 | mmd_tools 不在 Blender 3.6 addon 路径 | 把 mmd_tools 从 3.5 复制到 3.6 的 addons |
| XPS 导出失败(Noesis+Blender 都不行) | XPS addon 未启用 | 在 Blender 里 Edit > Preferences > Add-ons 搜 XPS 并启用 |
| 转换很慢 | Blender 无头启动约 5-10 秒开销 | 正常,每格式约 10-20 秒 |
| 角色 ID 不在 -List 里 | 可能是事件/限定角色,在 LocalLow 缓存而非 StreamingAssets 中 | 手动搜 `C:\Users\haoni\AppData\LocalLow\Pinkcore\Rise of Eros\AssetBundles` |
