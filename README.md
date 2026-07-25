# ripper_tpose

用 **Ninja Ripper** 抓取游戏角色、导出 **T-pose / A-pose** 模型做动画的调研笔记。

核心在于**「pose」**:抓出来到底是可用于绑定的中性姿势,还是当前帧的动画姿势——这决定了整条动画流程走不走得通。

> **本仓库落地的实际方案**:目标游戏 Rise of Eros 是 Unity,按下文结论走了**文件级提取**而非 NR——
> 用 **AssetStudio(命令行版 AssetStudioModCLI)** 直出带骨架 FBX,再转 XPS。可跑的脚本在 `scripts/`,
> 流程见 [docs/rise-of-eros-extraction.md](docs/rise-of-eros-extraction.md) 与 [scripts/README.md](scripts/README.md)。
> （评估过 AssetRipper 但**没采用**;名字相近,别和 AssetStudio 记混。）本页是背后的通用调研笔记。

---

## TL;DR(先看这段)

> 1. **你抓出来是不是 T/A-pose,不是你能自由选的**——取决于目标游戏「在哪一步做蒙皮(skinning)」。顶点着色器里蒙皮 → 抓到 bind pose(T/A);CPU 或 compute 预处理里先蒙皮好再提交 → 只能抓到动画姿势。
> 2. **Ninja Ripper 永远不抓骨骼/权重/绑定**(官方 FAQ:*"Animations/bones/weights are not saved at the moment."*)。所以它的产物必须**从零重新绑定**。
> 3. **对「做动画」这个目标,NR 往往是最后手段。** 如果游戏是 Unity / Unreal / Source 引擎,用**文件级提取**工具(AssetStudio / FModel / UModel / Crowbar)能直接拿到美术做好的、带骨架 + bind pose + 蒙皮权重(常含动画)的完整角色,远胜 NR 抓一具「静态雕像」再手工重绑。

**一句话决策:先判断引擎 → 能文件级提取就别用 GPU 抓取 → 只有引擎未知/加密/提取失败时才退回 Ninja Ripper,并做好全流程手工重绑的准备。**

---

## 目录

1. [pose 的本质:决定成败的唯一机制](#一pose-的本质决定成败的唯一机制)
2. [用 NR 拿到干净 T/A-pose 的技巧(按效果排序)](#二用-nr-拿到干净-ta-pose-的技巧按效果排序)
3. [致命限制:NR 完全不抓骨骼](#三致命限制nr-完全不抓骨骼)
4. [更优路线:按引擎选文件级提取工具(决策表)](#四更优路线按引擎选文件级提取工具决策表)
5. [走 NR 的完整 Blender 流程:导入 → 清理 → 重绑定](#五走-nr-的完整-blender-流程导入--清理--重绑定)
6. [法律与伦理](#六法律与伦理)
7. [完整来源](#完整来源)

---

## 一、pose 的本质:决定成败的唯一机制

**为什么「绑定姿势(bind pose)」通常就是 T-pose 或 A-pose。** 美术建模和绑定时都摆成一个中性参考姿势:

- **T-pose**——四肢与坐标轴对齐,肩、肘、胯、膝关节中心暴露,骨骼容易沿主轴对齐,对绑定师最省事;
- **A-pose**——手臂微下垂、肘微弯,更接近平均游戏姿势,能减少肩部 UV 拉伸、形变更自然。

选哪个主要看动画组偏好。关键是:**游戏文件里存的角色网格就是这个 bind-pose 网格**,动画是运行时把骨骼矩阵叠加上去。你偶尔看到的「角色卡成 T 字」bug,其实就是动画没加载、原始资产直接露出来了——中性姿势始终存在于管线某一环,问题只是**你抓的是哪一环**。

**决定性事实:Ninja Ripper 抓的是「提交给 draw call 的顶点缓冲区」,也就是顶点着色器的输入。** 于是分两种情况:

- **游戏在顶点着色器里做蒙皮(经典 GPU skinning)**:输入缓冲里装的是 bind-pose 顶点 + 骨骼索引/权重。**这时不管屏幕上在播什么动画,抓出来都是 T/A-pose。**
- **游戏在 CPU 或 compute 预处理里先蒙皮好、再把已变形的顶点提交**:抓出来就是当前帧的**动画姿势**,bind pose 拿不回来。

官方 FAQ 原文:

> *"In short: not all games support T-Pose ripping. Full answer: if the vertices are submitted for rendering already modified (CPU-skinning), then there will be no T-Pose."*

Ninja Ripper 最初的定位就是「提取 T-pose 模型用于 3D 打印」,所以 T-pose 抓取是它的老本行——但**能不能成,是逐游戏的经验问题,不是保证**。(VG-Resource 甚至维护过一个「Games that are T-Posable with Ninja Ripper」的合集帖。)

**按引擎预判(重要):**

| 引擎 | 蒙皮位置 | GPU 抓取通常得到 |
|---|---|---|
| Unreal(GPUSkinVertexFactory,UE4 时代常见) | 顶点着色器 | **bind pose(T/A)** ✅ |
| Unreal(Skin Cache,UE5 硬件光追/头发需要,越来越多) | compute 预处理 | 动画姿势 ❌ |
| Unity(GPU / compute 蒙皮为主) | 提交前已变形 | 多为**动画姿势** ❌ |
| 老 PC 游戏、PS2/GC/Wii 模拟器 | CPU / 向量单元 | **永远拿不到 T-pose** ❌ |

**结论:** UE4 老游戏对 NR 的 T-pose 抓取最友好;Unity、现代 UE5、以及模拟器,GPU 侧往往只能抓到动画姿势。

---

## 二、用 NR 拿到干净 T/A-pose 的技巧(按效果排序)

1. **首选:别用 GPU 抓取,改走文件级提取**(见[第四部分](#四更优路线按引擎选文件级提取工具决策表))。引擎已知时这是最好的结果。

2. **抓 pre-skinning 缓冲 + Local Space 导入。** 这是 NR 的正解。**NR2 同时抓两种空间,导入时可选:**
   - **Local Space import = 默认 T-pose**(所有部件堆在原点);
   - **World Space import = 屏幕上的姿势**(在关卡里的位置)。
   - 实操套路:先用 **World Space** 在几百个 rip 里**辨认/定位**角色,再对同一批网格用 **Local Space** 拿 T/A-pose 版本。
   - (NR1.7.1 没有这个选项,只输出输入缓冲:GPU-skin 游戏得 bind pose、CPU-skin 游戏得动画姿势,没得选。)

3. **在渲染「接近 rest pose」的界面抓**:角色创建、角色/干员选择、登录界面、主菜单、衣柜。好处是通常只有一个角色、背景干净。缺点:这些界面多半有 idle 呼吸动画,得到的是「接近中性」而非精确 T-pose(和第 2 条合用最好)。

4. **冻结动画帧**:暂停/照相模式、Cheat Engine 速度设 0、模拟器暂停/存档,或用禁用动画的作弊码。只能得到屏幕上的姿势——适合游戏本身有中性站姿或可摆姿的照相模式。(极端案例:有人用 Cheat Engine 在 Dolphin/PCSX2 上强行把《真人快打》摆成 T-pose 再抓。)

5. **空场景抓(辅助手段)**:先把角色带到空房间再抓,减少背景网格干扰。

6. **最后手段**:抓到动画姿势后在 Blender 里手动重摆(见[第五部分](#五走-nr-的完整-blender-流程导入--清理--重绑定)末尾,最费力)。

---

## 三、致命限制:NR 完全不抓骨骼

官方 FAQ 原文:**"Animations/bones/weights are not saved at the moment."** 导进 Blender 的是**一堆静态网格 + UV + 贴图 + 着色器**,没有骨架、没有骨骼层级、没有绑定矩阵、没有顶点组。

一个容易被误解的版本细节:NR1 的 `.rip` 里**物理上可能**含有 `BLENDWEIGHT` / `BLENDINDICES`(逐顶点的骨骼权重/索引,是从游戏顶点声明里原样拷出来的),但**没有任何导入器把它变成可用的顶点组**,而且真正难的是「生成骨架并把它和网格关联起来」——这部分数据从来没被抓到。

**对做动画的意义:** 骨架和蒙皮权重是角色 TA(技术美术)里最费工的部分,而文件级提取能直接白送给你。NR 的产物必须从零重绑,这正是它对「做动画」这个目标最不划算的地方。

---

## 四、更优路线:按引擎选文件级提取工具(决策表)

这些工具直接读磁盘上的资产文件,拿到的是美术做好的**骨骼网格:bind pose(几乎必是 T/A)+ 命名骨架 + 蒙皮权重,常含形态键和整套动画**。对做动画而言全面碾压 GPU 抓取。

**先判断引擎**(看游戏文件):
- 有 `UnityPlayer.dll` / `*_Data` 目录 → **Unity**
- 有 `.pak` + `Engine/` 目录 或 `.uasset` → **Unreal**
- 有 `.vpk` + `.mdl` → **Source**
- 拿不准 → 查 PCGamingWiki / SteamDB

**然后按下表选工具:**

| 引擎 | 用什么 | 你得到 | 做动画就绪度 |
|---|---|---|---|
| **Unity** | AssetStudio(维护版 AssetStudioMod)直出 FBX,或 AssetRipper 出 GLB / Unity 工程 | 骨骼网格(bind pose)+ 骨架 + 权重 + AnimationClips | 极好——可直接重定向/动画 |
| **Unreal UE1–UE4** | UModel(UE Viewer),导 PSK/PSA | 骨骼网格 + 骨架 + 权重 + 动画集 | 极好 |
| **Unreal UE4/UE5** | FModel(glTF/PSK/UEFormat;加密包需 AES key) | 同上,含形态键、动画 | 极好 |
| **Source / GoldSrc** | Crowbar 反编译 → Blender Source Tools | 原始骨架 + 权重 + 动画 SMD | 极好 |
| **其他已知格式**(RE 引擎、很多主机游戏) | Noesis + 对应插件,或逐游戏 Blender 插件(去 ResHax / GitHub 找) | 通常含骨架 + 权重,常含动画 | 好,视插件而定 |
| **未知/自定义引擎、资产加密、提取失败** | **这时才用 Ninja Ripper**(或 RenderDoc) | 静态姿势网格碎块 + 贴图 | 差——要清理、重摆、重绑、重刷权重 |
| **只需要形状**(3D 打印 / 参考 / kitbash) | NR / RenderDoc 就够 | 网格 + 贴图 | 无所谓,丢骨架不影响 |

> **原则:对做动画,Ninja Ripper 是「最后手段」。** 先穷尽引擎专用的文件级提取,只有引擎未知/不支持时才退回 GPU 抓取。连 NR 自己的 FAQ 都建议先看社区有没有能连骨骼一起提取的逐游戏工具。

---

## 五、走 NR 的完整 Blender 流程:导入 → 清理 → 重绑定

### 5.1 导入

- **导入器**:NR2 自带 Blender 导入器(在安装目录 `.../importers`,当插件装);NR1.7.1 用社区的 `kree-nickm/ninjaripper-blender-import`。
- **输出格式**:NR1 是**每 draw call 一个 `.rip` + `.dds`**(一帧能出几百个文件);NR2 是 `.nr`。两者都不直接导 FBX/OBJ。

### 5.2 常见清理问题与修法

| 问题 | 成因 | 修法 |
|---|---|---|
| **缩放 / 轴向错** | 游戏是 DirectX 风格(Y-up 左手),Blender 是 Z-up 右手 | 导入器默认按 `(-X, Z, Y)` 重排顶点、UV 按 `(U, -V+1)` 翻 V;导入后常需绕 X 轴 ±90°、整体缩小,然后 **Ctrl+A 应用所有变换** |
| **网格碎成很多块** | 每 draw call 一块:身体/头发/脸/衣服/配件分开,混在几百个场景/UI 物体里 | 线框视图 + 正交框选找出角色,其余移走/删掉;选中角色所有部件 **Ctrl+J 合并**,再 **Merge by Distance** 焊接接缝 |
| **重复几何** | 阴影 pass、深度 pre-pass、多光源 pass、LOD 各抓一份 | 用导入器去重选项或 `NinjaRipperFix` 插件;或手动 Alt+Click 循环选择,留有贴图的那份、删其余 |
| **法线丢失 / 翻转** | 三角形绕序不一致 | 开 **Face Orientation** 叠加层诊断(蓝=朝外、红=朝内),Edit 模式全选 **Shift+N 重算**,顽固面手动 Flip(开放壳重算不总灵,需手动补) |
| **UV 选错通道** | rip 带多个 texcoord 通道,真正的反照率 UV 不一定是 0 号,有些是光照图 UV 或**屏幕空间投影 UV** | 在导入器里换 UV 通道、切 Local/World Space texcoord 试 |
| **松散 / 非流形几何** | 退化三角形、其他 pass 掉落的散点、内壁 | Select All by Trait → Loose;Clean Up → Delete Loose / Degenerate Dissolve;删口腔、被剔除的内壁等隐藏几何(否则干扰自动权重) |

### 5.3 重绑定(骨架从零重建)——四条主流路线

| 方案 | 成本 | 输入要求 | 特点 |
|---|---|---|---|
| **Mixamo** | 免费 | 干净的单一 humanoid 网格,T/A-pose,脚踩地、面朝前,面数别太高 | 最快「能走起来」;放下巴/手腕/肘/膝/胯 5 个标记,约 2 分钟出绑定 + 海量免费动作库。不是电影级(无面部绑定) |
| **Rigify**(Blender 自带) | 免费 | 任意网格,手动摆骨 | 全 IK/FK 动画级控制;手工最多 |
| **Auto-Rig Pro**(付费 ~$40) | ~$40 | T/A-pose,面朝 -Y,居中,变换已应用 | Blender 内自动化与质量最佳;**Voxelized 绑定**对脏的多壳游戏 rip 尤其好;含 Mixamo 动作重定向 |
| **AccuRig / ActorCore**(免费独立软件) | 免费 | OBJ/FBX,biped,T/A/扫描姿势均可 | 对不完美网格**最鲁棒**;支持多网格;导 FBX(Blender 预设) |

### 5.4 为什么 T/A-pose 是硬性要求(这就是「关键在 pose」的原因)

自动绑定器靠分析**网格轮廓/体积**来定位关节——它假设**四肢和躯干在空间上是分开的**:

- 手臂下垂或动作姿势会让肘/膝/脊柱关节**落进躯干内部**,骨骼摆错位;
- 蒙皮权重求解器按邻近/热扩散分配,**手贴着胯、胳膊贴着胸**时,躯干顶点会被错分到手臂权重上,形变全乱。

所以:**能抓到 T/A-pose,后面自动绑定才顺;抓到动画姿势,几乎注定要手工返工。**

### 5.5 只有动画姿势时的兜底(最费力)

等于给一具雕像重新做绑定,没有「一键复位到 bind pose」这种东西:

1. 清理合并(Ctrl+J、Merge by Distance、重组散件);
2. 加一个 Rigify 人形元骨架,把骨头对进弯曲的肢体;
3. Parent → With Automatic Weights;
4. Pose 模式把角色掰直成 T-pose;
5. **应用骨架修改器**把 T-pose 烤成新基础网格 → 删临时骨架 → 再正式绑定。

**真实难度**:轻微 idle 姿势花一晚上;战斗姿势可能比重新建模还慢。而且非对称会毁掉 UV(Symmetrize 会破坏 UV 映射)。所有教程的第一条建议都是「别走到这一步」。

---

## 六、法律与伦理

抓取的游戏资产仍归开发商/发行商**版权**所有,提取通常也违反游戏 EULA/ToS。实践中:

- **个人、非商业的学习/研究/私人同人** —— 被广泛容忍;
- **再分发(哪怕免费)和任何商用** —— 构成侵权。

别把抓取资产放进 mod、资产包或产品里,只当私人参考/学习材料用。

---

## 完整来源

**Ninja Ripper 官方 / 机制**
- 官方 FAQ(T-pose/CPU-skinning、不存骨骼、导入选项):https://www.ninjaripper.com/faq
- 下载页 + 更新日志(2.0.4 "saving meshes in local space (T-pose)"):https://www.ninjaripper.com/download
- About(历史、1.7.1 起于 T-pose 3D 打印、支持的 API):https://ninjaripper.com/about
- Boosty(API/更新日志):https://boosty.to/ninjaripper
- NR1.x GitHub README(抓取的数据含 BLENDWEIGHT/BLENDINDICES;骨架「只是个问题」):https://github.com/riccochicco/ninjaripper
- 1.x 教程(注入/wrapper 模式、快捷键):https://cgig.ru/2012/10/ho-to-use-ninja-ripper/
- 官方视频 "Ninja Ripper 2.0.5 | T-Pose ripping":https://www.youtube.com/watch?v=YHa2gmTqSqc
- OpenGL/Vulkan Ripper 手册(pre-shader T/A-pose vs post-shader、`bLocalSpace`、transform feedback):https://www.patreon.com/VulkanRipper/posts/opengl-ripper-1-89804446 · https://www.patreon.com/posts/vulkanripper-87598927

**Blender 导入器**
- kree-nickm(NR1,选项/去重/轴向 `(-X,Z,Y)`/UV `(U,-V+1)`):https://github.com/kree-nickm/ninjaripper-blender-import
- angavrilov(NR1.5,过滤冗余副本):https://github.com/angavrilov/blender-import-ninjaripper
- Dummiesman RipImport(已归档):https://github.com/Dummiesman/RipImport
- Akaito(NR1.1):https://github.com/Akaito/blender-ninjaripper-importer
- NinjaRipperFix(仿射变换修正 + 去重):https://github.com/Frissj/NinjaRipperFix

**清理教程**
- 完整 rip→Blender 清理(0curtain0 / XCurtainX):https://0curtain0.github.io/ninja_ripper.html · https://www.deviantart.com/xcurtainx/journal/Rip-Your-Favorite-3D-Game-Character-Models-FREE-753410159
- Darktide 抓取指南(Local=T-pose / World=游戏姿势 实证;菜单/角色创建界面抓取):https://steamcommunity.com/sharedfiles/filedetails/?id=2918680531
- Blender Clean Up 工具手册:https://docs.blender.org/manual/en/latest/modeling/meshes/editing/mesh/cleanup.html
- 「Games that are T-Posable with Ninja Ripper」合集:https://archive.vg-resource.com/thread-32972.html

**重绑定**
- Mixamo(Adobe 帮助 / 工作流 / 标记):https://helpx.adobe.com/creative-cloud/help/mixamo-rigging-animation.html · https://whatmakeart.com/3d-modeling/blender/auto-rig-with-mixamo-import-blender/
- Auto-Rig Pro 文档(Smart、pose/朝向、Heat Maps vs Voxelized 绑定):https://www.lucky3d.fr/auto-rig-pro/doc/auto_rig.html
- Rigify 基础:https://docs.blender.org/manual/en/latest/addons/rigging/rigify/basics.html
- AccuRig / ActorCore:https://actorcore.reallusion.com/auto-rig/accurig
- 为什么要 T/A-pose 才好自动绑定:https://www.meshy.ai/tutorials/character-auto-rigging-workflow
- 手动把 rip 掰成 T-pose(PIXXO Human Meta-Rig / Tripo3D):https://www.youtube.com/watch?v=WpgDjKIxYOA · https://www.tripo3d.ai/blog/collect/transforming-a--d-model-into-a-t-pose-using-blender-and-armatures-q5hdnoper8o

**替代工具(文件级提取)**
- AssetStudio(Unity 出带骨架 FBX):https://github.com/Perfare/AssetStudio · 维护版 https://github.com/aelurum/AssetStudio
- AssetRipper(Unity,含骨架/权重/形态键):https://github.com/AssetRipper/AssetRipper
- UModel / UE Viewer(UE1–UE4 骨骼网格 + 动画):https://www.gildor.org/en/projects/umodel
- FModel(UE4/UE5,glTF/PSK/UEFormat):https://github.com/4sval/FModel
- Crowbar(Source .mdl 反编译):https://valvedev.info/tools/crowbar/
- Noesis(多格式,保留骨架/动画的 FBX 导出):https://appnee.com/noesis/
- RenderDoc(与 NR 同类,仅网格;VS Input=原始 / VS Output=变形):https://renderdoc.org/docs/window/mesh_viewer.html · https://reshax.com/topic/18581-ripping-3d-models-using-renderdoc/

**引擎蒙皮机制**
- UE 蒙皮路径(GPUSkinVertexFactory vs Skin Cache):https://dev.epicgames.com/documentation/unreal-engine/skeletal-mesh-rendering-paths-in-unreal-engine
- Unity Skinned Mesh Renderer / GPU 蒙皮:https://docs.unity3d.com/6000.2/Documentation/Manual/class-SkinnedMeshRenderer.html

**pose / bind pose 概念**
- T-pose(Wikipedia):https://en.wikipedia.org/wiki/T-pose
- T 还是 A pose 的取舍(Polycount):https://polycount.com/discussion/202303/to-t-pose-or-not-to-t-pose
- bind pose 与 A/T 权衡(Ask a Game Dev):https://askagamedev.tumblr.com/post/694298319820849152/are-there-any-differences-between-an-a-pose-and-a

**法律**
- 抓取模型的合法性:https://gamedesignskills.com/game-art/rip-models-from-games/
