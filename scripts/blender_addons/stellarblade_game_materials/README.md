# Stellar Blade Game Materials（Blender 3.6 插件）

导入剑星（Stellar Blade）Eve 的 PMX 以后，一键把材质换成**游戏原始的完整材质**，用来在 Blender 里做动画、出渲染。
用法和 Vindictus、ROE 的插件（`vindictus_game_materials`、`roe_game_materials`）一样。换上以后有：

- 法线：缝线、褶皱、夹克的绗缝，还有夹克上的针织纹理（游戏的 `Knitted_N`，平铺 8 次）；
- 粗糙度 / 金属度（游戏的 ORM 贴图）：扣具、金属件的光泽；
- 清漆：乳胶连体衣那层亮面（游戏 ShadingModelMask 里的 ClearCoat 通道）；
- 绒毛光泽（Sheen）：布料边缘的那层绒光（FuzzMask）；
- 自发光；
- 贴花的透明裁切：腿上的「SUPER」白字。

PMX 格式只装得下一张颜色贴图。导出时已经把游戏颜色乘上了 AO，还把亮的部分拆成了 `<材质>_gloss`，用 sphere 贴图加高光
（见 `scripts/stellarblade/README.md`「高清材质」）。其余效果只能在 Blender 里加回来。插件不删 mmd_tools 的任何节点：
随时能切回 MMD 着色，用 mmd_tools 再导出 PMX 也和原来一样。

效果对比图：`E:\game_export\StellarBlade\Eve\pmx\CH_P_EVE_Nikke_06\插件效果_游戏材质对比.jpg`
（游戏材质 / MMD 着色 / 调整示例，Blender 3.6 EEVEE）。

## 安装

仓库里的插件用目录联接装进 Blender，和另外两个材质插件一样。本机已经装好：

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\3.6\scripts\addons\stellarblade_game_materials" `
         -Target "E:\code\othercode\ripper_tpose\scripts\blender_addons\stellarblade_game_materials"
```

然后在「编辑 → 偏好设置 → 插件」里搜 `Stellar Blade Game Materials`，勾选。Blender 已经开着、列表里却没有它时，
点插件页右上角的「刷新」，或者重开 Blender。
面板在 3D 视图侧栏（按 `N`）的 **MMD** 标签页，标题「剑星游戏材质」，和「Vindictus 游戏材质」「ROE 游戏材质」并排，互不影响。

需要：
- mmd_tools，用来导入 PMX；
- 剑星的存档：`E:\game_export\StellarBlade\<角色>\blend\<服装包>\*_HQ.blend`。这些高清 .blend 是
  `scripts/stellarblade/hq_materials_blender.py` 按游戏的材质实例做的，材质就从这里搬，不用再读游戏文件。
  贴图直接引用高清 .blend 旁边 `textures\` 里的文件，不复制。

## 用法

1. 用 mmd_tools 导入 PMX（缩放多少都行，常用 0.08）。
2. 选中模型：点模型的根、骨架或网格都行。
3. 点「**换上游戏原始材质**」。
   - 第一次用要扫一遍存档里的高清 .blend，只读材质名，几秒钟。
   - 面板下方会显示「Eve_CH_P_EVE_Nikke_06_HQ：换了 17 个材质，没找到 0 个，错误 0」。
4. 「**游戏材质 / MMD 着色**」两个按钮来回切，方便对比。
5. 在「调整」里拖滑块，**实时生效**。1.0 是游戏原始值，「参数恢复默认」回到原始值。
6. 照常做动画、渲染。要再导出 PMX，照常用 mmd_tools 导出，PMX 里还是原来那张颜色贴图。
7. 不想要了点「**去掉游戏材质**」，恢复原样。

| 参数 | 默认 | 范围 | 作用 |
|---|---|---|---|
| 法线强度 | 1.0 | 0–3 | 游戏法线强度的倍数：缝线、褶皱、绗缝、针织纹理，脸和牙齿的凹凸 |
| 粗糙度 | 1.0 | 0–2 | 越小越亮、反光越清楚。头发、脸这些没有粗糙度贴图的材质也跟着乘（结果最大到 1） |
| 金属度 | 1.0 | 0–2 | 扣具、金属件 |
| 清漆 | 1.0 | 0–2 | 乳胶亮面那层；0 = 关掉 |
| 绒毛光泽 | 1.0 | 0–5 | 布料边缘的绒光 |
| 自发光 | 1.0 | 0–10 | 自发光强度；0 = 关掉 |

「高级」里可以改存档目录，或者直接指定一个高清 .blend（不在存档里找）。存档里加了或改了高清 .blend 以后，点「重新扫描存档」。

## 支持哪些模型

- **Eve 的 Cooling Suit**（Alice，`CH_P_EVE_Nikke_06`）：`E:\game_export\StellarBlade\Eve\pmx\CH_P_EVE_Nikke_06\Eve_CH_P_EVE_Nikke_06.pmx`。
  17 个材质全部找到：
  - 连体衣（`…_UV1`）、夹克（`…_UV2`）、贴花（`MI_VietaCos004_Decal`）是这次按游戏材质实例做的完整材质；
  - 连体衣的亮面部分 `…_UV1_gloss` 跟着 `…_UV1` 走，用同一套游戏材质，混合模式不透明；
  - 头、头发、眉毛、眼睛、牙齿是存档 .blend 原来的网络（09-26 导出时做的）：
    - 脸：法线和一点次表面散射；
    - 眼睛：按游戏眼睛材质的参数重做的虹膜和眼白（2026-10-17 起虹膜大小和游戏一致；2026-10-18 起也乘游戏材质的色调 `IrisHueTint`），加法线；
    - 头发、眉毛：颜色贴图加透明度，粗糙度是常数。
- **Gantz Reika A / B**（Nexus mod，`E:\game_export\StellarBlade\Reika\pmx\Mod_GantzReika_*\`）：2026-10-18 起全部材质都换得上，
  A 15 个、B 16 个，从它们自己的高清 .blend（`Reika\blend\Mod_GantzReika_*\Eve_Mod_GantzReika_*_HQ.blend`）搬：
  - 衣服（`SuitA_Body`、`SuitA_Mesh`、`SuitB`）：mod 自己的材质实例，继承游戏 Planet Diving Suit 的 `MI_P_EVE_09_Metal02_Layered`。
    接了 ORM（粗糙度、金属度、高光遮蔽）、DirectX 法线、发光：发光贴图的红通道乘 mod 设的蓝色 HDR 发光色（0, 0.56, 271），原样保留。
    嫌太亮就把「自发光」滑块往下拉；
  - B 露出来的皮肤（`EveSKin`，Eve 身体皮肤材质的实例）：ORSS 贴图的粗糙度和高光、法线，次表面散射和脸一样；
  - 头、头发、眼睛和 Cooling Suit 那套一样。
  - 高清 .blend 是 `scripts/stellarblade/hq_mod_outfits.py` 做的，见 `scripts/stellarblade/README.md`「高清材质」。
  - 对比图：`Reika\pmx\Mod_GantzReika_A\插件效果_游戏材质对比.jpg`、`…_B\…`。
- **Eve 的裸体**（EveOriginalProportions 赤足 mod，`E:\game_export\StellarBlade\Eve\pmx\Nude_Barefoot\Eve_Nude_Barefoot.pmx`）：
  2026-10-24 起 14 个材质全部换得上。身体 `SkinEve` 是 mod 自己的材质实例（继承游戏 Eve 身体的 `MI_Basebody_V02_F2`），
  接 mod 的 ORSS（粗糙度、高光）和法线，次表面散射和脸一样；高清 .blend 是 `Eve\blend\Nude_Barefoot\Eve_Nude_Barefoot_HQ.blend`
  （`hq_mod_outfits.py`，mod 没装进游戏，直接从下载的压缩包读）。
- **几层衣服叠在一个 PMX 里**（`scripts/clothes_burst/pmx_layers.py`，例：`Reika\pmx\Mod_GantzReika_Layers\`，Reika A 套在 B 外面、
  B 套在裸体外面）：2026-10-24 起（插件 0.2）19 个材质全部换得上，见下面「分层模型」。
- **Fiona**（`Mod_VindictusFiona`）：头、头发、眼睛 13 个材质换得上；mod 自己的衣服材质还没有高清 .blend，保持 MMD 着色。
- **其他服装**：先照 `scripts/stellarblade/README.md`「高清材质」那节做出 `*_HQ.blend`，放进存档
  （`<角色>\blend\<服装包>\`），再点「重新扫描存档」。
- 别的游戏不行。XPS 也不行，因为 XPS 导出会改材质名。

## 分层模型（0.2，2026-10-24）

`pmx_layers.py` 把同一个角色的几套衣服叠进一个 PMX，用表情面板里的步骤滑块一层一层脱（`1_A脱ぎ`、`2_B脱ぎ`……）。
这种模型换游戏材质要多管两件事：

- **每层从自己的高清 .blend 拿材质**：每个层材质的 PMX 备注里写着 `layer=B; source=SuitA_Body`（mmd_tools 导入后在
  材质的 MMD 属性「注释」里）。插件按层分组，每层找同名材质最多的那个 .blend：Reika 的 A 层从
  `Eve_Mod_GantzReika_A_HQ`、B 层从 `…_B_HQ`、裸体从 `Eve_Nude_Barefoot_HQ`；头、头发、眼睛跟最外层。改过名的材质
  （`SuitA_Body_B`）按 `source=` 找原名。一个 .blend 里缺的材质再去别的 .blend 找。面板上写「分层模型：A → B → 裸体」，
  完成后显示「Eve_Mod_GantzReika_A_HQ + …_B_HQ + Eve_Nude_Barefoot_HQ：换了 19 个材质……；6 个跟着滑块显示 / 隐藏」。
- **跟着步骤滑块显示 / 隐藏**：层是用材质表情藏起来、换上去的。游戏材质原来不认材质表情的透明度，一换上，藏着的 B 和裸体
  就都露出来了。现在会被材质表情改透明度的材质，游戏材质的 Alpha 前面乘一个 `sbhq_mmd_alpha`：游戏的透明度 × MMD 着色器
  那一刻的透明度（mmd_tools 的表情滑块绑定以后，它的表情节点算好接在 MMD 着色器的 Alpha 上，插件接的就是那根线）。
- **藏起来的层不画细线**：插件挂了两个处理函数（场景一有变化、每一帧开始之前），按表情滑块算出每个层材质现在的透明度
  （MMD 的算法：文件里的透明度 × 乘算 + 加算，组合表情按系数算进去；渲染动画时直接读这一帧的动画曲线，不会晚一帧）：
  - 透明度 0（藏着）：混合模式 Blend、显示背面（不做深度预渲染）、不投影、次表面散射 0；
  - 1（显示）：换回游戏材质自己的设置（MMD 着色时是 mmd_tools 的）；中间（淡出）：不透明的改成 Alpha Hashed。
  原来用 Alpha Hashed 藏着的裸体贴在 B 的皮肤下面，EEVEE 会在两层交界处画出细黑线（10-18 只用 mmd_tools 时就有）；
  藏着的层带次表面散射会把它上面那层画黑（Vindictus 插件碰到过）。只有藏着时换设置，显示出来的层效果不变。
  游戏材质、MMD 着色两种显示都管，所以装了插件、换过材质的分层模型在 MMD 着色下也没有细线。
- **爆衣插件的碎片**（`<材质>_burst`）也认得：去掉后缀找原材质，跟着它的表情显示 / 隐藏。先换材质还是先生成爆衣都行。

检查（scratch `test_layers_addon.py`）：三个状态的正面、背面、劈腿时的胯部特写，游戏材质和 MMD 着色都没有细线；
把步骤滑块打成关键帧渲染动画，每一帧都是这一帧的状态。单独的 A、B、Cooling Suit、裸体 PMX 照旧全部换上
（15 / 16 / 17 / 14 个，一个家）。

## 原理

- **认材质**：剑星的 PMX 材质名就是游戏材质实例的名字（`export_pmx_blender.py` 原样保留），只有导出时拆出来的
  `<名字>_gloss` 要去掉后缀。插件在存档所有 `*_HQ.blend` 里找同名材质：
  - 头、头发、眼睛每套衣服都有，所以按衣服自己的材质定：同名材质最多的那个 .blend 就是这个模型的「家」，
    所有材质都从它那里搬。打平时，模型名里写着哪个服装包，就选那个；
  - 每个 .blend 有哪些材质，记在 `%APPDATA%\Blender Foundation\Blender\3.6\config\stellarblade_game_materials_index.json`，
    按文件大小加修改时间判断，.blend 没变就不再打开。
- **搬材质**：
  - 从「家」里追加这些游戏材质，把整套节点复制进 PMX 的材质里，节点名都以 `sbhq_` 开头，带一个自己的输出节点；
  - 然后删掉追加进来的那份，和追加时 Blender 留下的空库条目。要是你自己从那个 .blend 链接了东西，库条目就留着；
  - 切换靠「哪个输出节点是激活的」，再换上那一边的混合模式。游戏一边：贴花是 alpha 裁切，头发是 alpha hashed；
    MMD 一边是 mmd_tools 原来的设置。两边的设置以 JSON 存在材质的 `sbhq_game_settings` / `sbhq_mmd_settings` 里。
  - MMD 的节点一个不删，所以导出 PMX 读的 `mmd_base_tex`、材质颜色、sphere 都原封不动。
    实测在游戏材质和 MMD 着色两种状态下各导出一次，都和原 PMX 一致：17 个材质的贴图、sphere、颜色、面数，以及顶点、面、骨骼、表情。
    Reika A 两种状态导出的文件逐字节一样。
    Reika B 肚脐上有一个退化顶点，mmd_tools 每次导出给它的法线在两个值之间随机变（只差这 12 个字节）。
    不装插件、连着导出也一样会变，和插件无关。
  - **长度按模型大小换算**（2026-10-18）：存档的 .blend 是厘米单位，Eve 高约 172；PMX 按 0.08 导入后差不多是米。
    搬过来的网络里，次表面散射半径照原样会大 100 倍：脸的 1 cm 散射变成 1 m，脸糊成一片蜡色。
    现在乘上「导入模型的高度 ÷ 172」再用，日志里写着 `lengths x0.0100`。
- **调整**：
  - 接了贴图的输入：在 Principled 的 Roughness / Metallic / Clearcoat / Sheen 前面插一个乘法节点 `sbhq_gain_*`；
  - 常数输入（比如头发粗糙度 0.28）：原值记在节点上，直接乘；
  - 法线强度、自发光强度：原值记在节点上，乘上滑块的倍数。
- 代码：`scripts/stellarblade/game_materials_blender.py`。高清 .blend 里的节点是 `scripts/stellarblade/hq_materials_blender.py` 做的。
  也可以不开界面单独跑，导入 PMX 换上材质，再存一个 .blend 看：

```powershell
& "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" -b --factory-startup --python scripts\stellarblade\game_materials_blender.py -- `
    E:\game_export\StellarBlade\Eve\pmx\CH_P_EVE_Nikke_06\Eve_CH_P_EVE_Nikke_06.pmx --out C:\tmp\eve_nikke06_game.blend
```

## 注意

- 只在 Blender 3.6 上测过。
- 头发是常数粗糙度 0.28，在很亮、很均匀的环境光下，刘海会反出一层灰白。觉得太亮就把「粗糙度」调到 1.5 左右，
  或者换一个有明暗的环境光。
- 存档挪了位置，贴图会找不到：在「高级」里改存档目录，点「重新扫描存档」，再「去掉游戏材质」后重新换一次。
- Blender 开着的时候：
  - 存档里新加的高清 .blend 不用重开，下次点「换上游戏原始材质」就会找到；
  - 插件的代码（`game_materials_blender.py`、0.2 起还有 `__init__.py` 里的处理函数）更新了，要在「偏好设置 → 插件」里
    把它关掉再打开，或者重开 Blender，才会用上新代码；
  - 已经换过材质的模型，再点一次「换上游戏原始材质」就会按新的重换。
