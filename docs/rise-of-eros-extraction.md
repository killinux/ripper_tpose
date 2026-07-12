# Rise of Eros —— 抓取带骨架模型做动画的最佳方案

> 目标机器上的实测调研(2026-07)。配套通用调研见仓库根目录 [`README.md`](../README.md)。
> 本文针对**具体游戏 Rise of Eros**,给出可直接照做的提取流程。

---

## 0. 结论(TL;DR)

**放弃用 Ninja Ripper 抓静态网格 + 手搓 `NR_Rig`;改用 Unity 资产提取工具(AssetStudioMod / AssetRipper)从游戏自带的 AssetBundle 里直接导出「带骨架 + bind pose + 蒙皮权重 + 表情 blendshape」的原始模型,并可顺带导出游戏原生动画。** 你现在手工建骨架、刷权重的活儿基本全省——拿到的就是美术做好的绑定角色。

三条独立证据(经对抗性复核未被推翻):

1. Ninja Ripper 2.x 按其[官方 FAQ](https://www.ninjaripper.com/faq)**根本不抓骨骼/权重/bind pose**,你在 Blender 里重建的正是 bundle 里现成就有的。
2. 角色资产是 Unity 引擎原生类(`Mesh`/`SkinnedMeshRenderer`/`Transform`/`Texture2D`/`AnimationClip`),AssetStudio 用内置模板读取,**完全不依赖 IL2CPP 元数据**——IL2CPP 不挡模型导出。
3. 社区早有成品:Lezisell 的 `PC_C01_LD` XPS、Shrubbery333 的 MMD 版(带 IK、表情 morph、物理)——只有从原始绑定网格提取才做得到。

---

## 1. 已在目标机器上验证的事实

| 项 | 结果 | 佐证 |
|---|---|---|
| 引擎 | **Unity 2022.3.62f2**,IL2CPP | `UnityPlayer.dll`、`GameAssembly.dll`(180MB)、`il2cpp_data`、`globalgamemanagers` |
| Bundle 是否加密 | **否**(可直接打开) | 5 个 `chara_*.ab` 头部 flags = `0x243`(LZ4HC 压缩 + dirCombined + padStart),**UnityCN 加密位 `0x400` 未置位** |
| `dtdata.key` | 与模型 bundle **无关** | bundle 头已证明未加密;该 key 应属其它层(Addressables 目录/存档/网络) |
| 安装目录 | `D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros` | Steam 版 |
| 资产位置① | `...\RiseOfEros_Data\StreamingAssets\AssetBundles`(~30GB,13,544 文件) | 安装自带 |
| 资产位置② | `C:\Users\haoni\AppData\LocalLow\Pinkcore\Rise of Eros\AssetBundles`(~3.9GB) | 运行时下载缓存(事件/新装可能只在这) |
| 角色结构 | 模块化:`chara_armor_pc_<id>_hd`(网格,含 hd/ld LOD)、`chara_tex_*`(贴图)、`chara_mat_*`(材质)、`bare/suit/accessory`、`*_share`(共享骨架/动画),`avg_animation.ab` 等 | 命名与社区 rip 的 `PC_C01_LD` 对得上 |

> **加密位小知识**:UnityCN 加密的 bundle 同样以明文 `UnityFS...2022.3.62f2` 开头,光看 magic 不能判断加不加密;必须看 header flags 的 `0x400` 位。本作该位为 0 → 确认未加密。

---

## 2. 工具选择

| 工具 | 定位 | 对本任务 |
|---|---|---|
| **AssetStudioMod**(aelurum 分支) | 直接从场景层级导出**单个角色的绑定 FBX** | **首选**——最直达"一个角色 → 一个带骨架 FBX",可退役 NR 流程 |
| **AssetRipper**(你已下载) | 导出 **GLB(glTF)** 或整个 Unity 工程 | **可用**,GLB 保留骨架/权重/blendshape,Blender 原生可导入;也是排查"炸开"问题的交叉验证工具 |
| 原版 Perfare/AssetStudio | 2023 已归档,不支持 2022.3 | **别用** |
| Ninja Ripper | 只抓静态网格,无骨架 | 退居边角(见 §7) |

### 2.1 你下载的 AssetRipper 现状(`E:\code\othercode\AssetRipper`)

**你下的是源码仓库,不是能运行的版本**(里面是 `Source\`、`AssetRipper.slnx`,**没有任何 .exe**)。而且这台机**只有 .NET 运行时(6/7/8/9),没有 .NET SDK**,所以**当前既不能直接跑,也不能本地编译**。两条路:

**A.(推荐)直接下预编译发行版——不用编译**
1. 到 <https://github.com/AssetRipper/AssetRipper/releases> 下 `AssetRipper_win_x64.zip`(或 `AssetRipper.GUI.Free`)。
2. 解压,双击 `AssetRipper.GUI.Free.exe` → 它会在浏览器里开一个本地 Web 界面。运行时已就绪,免装。
3. 源码那份留着无妨,但提取用发行版。

**B.(仅当你想从源码编译)先装 .NET 9 SDK**
```powershell
winget install Microsoft.DotNet.SDK.9      # 或去 dotnet.microsoft.com 下 SDK 9
cd E:\code\othercode\AssetRipper\Source
dotnet run -c Release --project AssetRipper.GUI.Free
```
（GUI 工程路径已确认为 `Source\AssetRipper.GUI.Free\AssetRipper.GUI.Free.csproj`。）比方案 A 麻烦,不推荐。

> 结论:**你的 AssetRipper 能用,但得先"变可运行"——最快是下发行版 zip。** 若想要最直达的绑定 FBX 流程,建议同时抓一份 AssetStudioMod。

---

## 3. 提取流程 —— AssetStudioMod(首选,最直达)

> 三个新手必翻的坑已并进步骤:**别 load 整个 30GB、要 stage 含 `*share*` 的子集**;**骨架只能靠 Scene Hierarchy 勾选 + `Model` 菜单导出,别在 Asset List 里对 Mesh 用 Export**;**导出时一个 AnimationClip 都别选**。

1. **装工具**:aelurum **AssetStudioMod —— Windows GUI 版**(≥ v0.19.0,<https://github.com/aelurum/AssetStudio/releases>)。整包解压,别把 exe 挪出目录(FBX 导出要同目录的原生 FBX SDK DLL)。
2. **选一个角色做冒烟测试**,先列 ID:
   ```powershell
   Get-ChildItem "D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros\RiseOfEros_Data\StreamingAssets\AssetBundles" `
     -Recurse -Filter "chara_armor_pc_*.ab" | ForEach-Object Name | Sort-Object -Unique
   ```
3. **stage 子集**(替代"load 30GB"):把该角色的所有 bundle **加上所有 `chara_*share*.ab`** 拷到临时夹:
   ```powershell
   $src="D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros\RiseOfEros_Data\StreamingAssets\AssetBundles"
   $dst="D:\roe_stage_a01"; New-Item -ItemType Directory -Force $dst
   Get-ChildItem $src -Recurse -Include "*a01*.ab","chara_*share*.ab" | Copy-Item -Destination $dst
   ```
   （把 `a01` 换成你的 ID。含全部 `chara_*share*.ab` 是保证共享骨架能解析的关键;若骨架仍残缺,就把范围放宽到整套 `chara_*.ab`。）
4. AssetStudioMod → `File > Load folder` 指向临时夹(自动识别 2022.3.62f2;若问 assembly/Il2Cpp 目录 **跳过**——模型用不到)。
5. **一次性诊断 Humanoid/Generic**:Asset List → Filter Type = **Avatar**。有带肌肉数据的 Avatar = Humanoid(好重定向);只有普通骨骼树 = Generic(本类游戏多为此)。记下来,决定后面外部动捕怎么接。
6. Asset List → Filter Type = **GameObject/Animator** → 搜角色 ID → 右键 **Show in scene hierarchy**。
7. **Scene Hierarchy 标签**里勾选**骨架/预制体根**(整棵子树:骨骼 Transform + 所有 SkinnedMeshRenderer)。**不选任何 AnimationClip。**
8. `Options`:FBX = Binary、Scale = 1、**开 blendshape/morph 导出** → **`Model > Export selected objects (merge)`**。得到一个含骨架 + bind pose + 权重 + 形态键的 FBX(无 clip = 作者的原始中性 pose)。
   - 想让 body/suit/accessory 分件保留就用 `Export selected objects (split)`(仍共享同一骨架)。
9. 贴图:Filter Type = **Texture2D** → 搜 ID → `Export > Selected assets` → PNG(BC7/BC1/BC3/BC5 自动解码)。
10. Blender 3.6 导入 FBX:**Automatic Bone Orientation = ON**,Scale = 1。

---

## 4. 提取流程 —— AssetRipper(你已下载的这条路)

先按 §2.1 把它变成可运行(下发行版)。然后:

1. 启动 `AssetRipper.GUI.Free.exe` → 浏览器打开本地界面。
2. 载入游戏文件夹或直接拖 `AssetBundles` 文件夹(自动解析 `.ab`)。
3. **Settings → `Mesh Export Format` → `Glb`(glTF binary)**。这是关键设置:GLB 保留顶点/法线/切线/多套 UV/**骨骼权重/层级/blendshape**,Blender 3.6 原生可导入并带真骨架。(默认导出的是 Unity 工程,需要再开 Unity 转 FBX,更绕。)
4. 侧栏浏览到 `GameObject/`(带材质的完整模型)或 `Mesh/`(挑 `hd`/LOD0 高模)→ **Export**(Export All 或选中导出)。
5. Blender:`File > Import > glTF 2.0 (.glb)` → 得到 Armature + 权重 + 形态键。

**与 AssetStudio 的取舍**:AssetRipper 没有"在场景树里选中一个角色就给一个 FBX"的直达流程,单角色绑定导出没 AssetStudio 顺手;但它的 **GLB 常常比 FBX 更干净(更少 bind-pose/权重怪问题)**,是排查"炸开"的好交叉验证工具。建议:AssetStudioMod 做主力,遇到某角色 FBX 有问题就用 AssetRipper 导 GLB 对照。

---

## 5. 冒烟测试(5 条全过才放量抓整个角色表)

Blender 导入那一个角色后,逐条核对:

- [ ] 只有**一具 Armature**,且 rest pose 是真 **T/A-pose**(不是塌在原点、也不是战斗姿势)。**记下是 A 还是 T**(写实角色多为 A-pose)。
- [ ] 骨骼数**几十根**、含面部/胸部/物理骨。只有 2-3 根 = `*share*` 骨架没 stage → 回 §3 步骤 3 放宽范围。
- [ ] 每个网格已带 **Armature 修改器 + 按骨骼命名的顶点组**(权重白送,无需刷)。
- [ ] 有**形态键**(Object Data Properties → Shape Keys:Basis + 表情)。没有 = 步骤 8 没开 blendshape 导出,重导。
- [ ] **贴图**导出非黑、albedo 能对上 UV。

全过 → 流程验证通过,再批量;顺便审 LocalLow 缓存里 StreamingAssets 没有的事件装。

---

## 6. Blender 侧:合体 / 材质 / 动画(已验证的坑与对策)

- **rest pose 多为 A-pose**:若动画源是 T-pose(Mixamo),重定向前先把骨架掰成 T,或在帧 0 做 pose-match 后"从当前"而非"从 rest"重定向,否则四肢会拧。
- **网格"炸开"/错位**(FBX rest pose 与 `m_BindPose` 不一致):用 **AssetRipper 导同角色 GLB** 交叉验证(GLB 按 bind pose 重建几何,常能避开)。
- **模块化合体**:body/suit/accessory 共享骨架、同名骨。最好在提取器里一次性 merge 导出。若分开导了:留 body 那具骨架,孤儿网格 **`Ctrl+P > Armature Deform`(别用 Automatic Weights,权重已在)**;配件多出来的骨用 **Fuse Skeletons** 插件并进去。分件保留、别急着 `Ctrl+J`,方便换装。
- **材质**:游戏是自定义 toon/NPR shader,提取器只给贴图不给 shader,只能重建 **PBR 近似**。关键:**Roughness = 1 − Smoothness(要反相)**;法线/金属/遮罩贴图设 **Non-Color**;Unity 常把 metallic 放 R、smoothness 放 alpha,遮罩是 RGBA 打包,需拆通道。要动漫质感走 toon 节点(你已装 `mmd_tools`,思路相同)。
- **动画**:骨骼动画能随 FBX takes / GLB 导入;但**表情/口型的 blendshape 动画曲线不走 FBX**,得在 Blender 里对形态键重新 key。游戏自带 clip 对同骨架 **1:1 可用**;外部动捕按 Humanoid/Generic 建一次骨骼映射存预设(全角色共享骨架,可复用)。
- **Humanoid vs Generic**:§3 步骤 5 查 Avatar 资产确定。本类游戏(物理骨 + 面部骨 + 跨角色共享 clip)**多为 Generic**;Generic 只影响外部动捕重定向的便利性,不影响提取,也不给 NR 加分。

---

## 7. Ninja Ripper 的成果怎么处理

**`NR_Rig` 基本作废**——它重建的正是 bundle 里现成的骨架+权重,属沉没成本,别再投入,也别在 NR 网格与提取模型之间互传权重(没有收益)。

NR **只在极少数场景仍有用,且只当静态几何/姿势参考,永不作为骨架来源**:
1. 运行时才合成、本地 bundle + 缓存里都没有的资产(最强用例);
2. 某帧布料/形变后的外形;
3. 想复刻的某个游戏内姿势(当视觉参考)。

做法:把现有 NR 输出**存档一份**以防第 1 种情况,然后丢开 `NR_Rig`。

---

## 8. 端到端顺序

1. 备好可运行的提取器(AssetStudioMod GUI,或让 AssetRipper 变可运行=下发行版)。
2. stage 一个角色的 bundle(含 `*share*`)。
3. 导出合并后的绑定 FBX(**不选 clip**)+ 贴图 PNG。
4. Blender 导入(Automatic Bone Orientation ON,Scale 1)→ 跑 §5 冒烟测试。
5. 合体、重建材质(smoothness→roughness 反相)、确认形态键。
6. 导入游戏 clip 或接外部动捕(建骨骼映射预设)。
7. 存档 NR 输出作参考,弃 `NR_Rig`。

---

## 来源

**工具**
- AssetStudioMod(aelurum):<https://github.com/aelurum/AssetStudio> · [releases](https://github.com/aelurum/AssetStudio/releases)
- AssetRipper:<https://assetripper.org/> · [releases](https://github.com/AssetRipper/AssetRipper/releases) · [GLB 导出/用法讨论](https://github.com/AssetRipper/AssetRipper/discussions/732)
- Ninja Ripper 官方 FAQ(不存骨骼/权重/动画):<https://www.ninjaripper.com/faq>

**本作 rip 先例(证明可提取带绑定)**
- Lezisell「Rise of Eros PC_C01_LD XPS」:<https://www.patreon.com/posts/rise-of-eros-pc-81762574>
- Shrubbery333 MMD(IK/表情/物理):<https://www.deviantart.com/shrubbery333/art/MMD-Rise-of-Eros-Inase-1224773847>

**技术参考**
- IL2CPP 不影响引擎原生类导出:<https://deepwiki.com/aelurum/AssetStudio/1.1-key-features-and-capabilities>
- UnityCN 加密 header(为何要看 flags 位):<https://github.com/AXiX-official/UnityCN-Helper>
- 为什么要 T/A-pose 才好自动绑定/重定向:<https://www.meshy.ai/tutorials/character-auto-rigging-workflow>
- Blender FBX 导入(Automatic Bone Orientation):<https://docs.blender.org/manual/en/latest/addons/import_export/scene_fbx.html>
- Auto-Rig Pro Remap(任意目标骨架重定向):<https://www.lucky3d.fr/auto-rig-pro/doc/remap_doc.html>
