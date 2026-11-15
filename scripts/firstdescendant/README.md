# The First Descendant（第一后裔）模型导出

Nexon 的《The First Descendant》(内部代号 **M1**，Steam `2074920`，UE 5.2 定制版)。游戏用
一个 IoStore 容器 `M1-Windows.{utoc,ucas,pak}`：**utoc v5 / pak v11 / Oodle / 目录索引 AES
加密**，贴图全部是 **UE5 虚拟贴图（Virtual Texture）**。本目录的脚本：直接解密并读容器的
目录索引来编目模型；用 CUE4Parse 命令行导网格（带真实材质槽名和面部 morph）并解码虚拟贴图；
自己读 zen 包头把材质槽连到贴图；Blender 合骨架、建材质、渲预览，出 `.blend` + `textures\`。

## 快速开始

在本目录里跑（PowerShell 先 `cd 〈仓库〉\scripts\firstdescendant`）。

### 看有哪些模型（查看列表）

```powershell
python .\list_models.py                       # 全表：id / kind / char / 部件 / 已导 / blend
python .\list_models.py --kind descendant     # 一类：descendant/skin/monster/boss/npc/weapon/accessory/fellow/vehicle
python .\list_models.py --char Bunny          # 某后裔的默认装 + 所有皮肤
python .\list_models.py --resolve Bunny --json    # 某个模型：每个部件的包路径、pskx 是否已导
python .\list_models.py --raw --path-filter /Monster/UNQ/   # 容器里的原始路径
```

当前编目 **2067 个模型**：33 个后裔（21 个角色 + 12 个 Ultimate 变体）、1075 套皮肤、
201 只怪、54 个 Boss 部件、99 个 NPC、250 把武器、248 件配饰、宠物/载具。

- 后裔代号 → 名字来自 `PC/MESH/PRESET/<名字>/PC_<编号>_<A|U>0101`（A 标准，U Ultimate）。
  **默认装就是这一整块合并网格**（身体+头+头发+脸，带 111 个表情 morph），导出最干净。
- 皮肤 = `SKIN/<类别>/<序号>/..._(BODY|HEAD)` + 该后裔的 Face；类别 F / M / MF / CMN / AGT /
  BOS / CLB / EVO / VAR（Makeup 只有材质，跳过）。
- 女性体型 12 个：Viessa、Bunny、Freyna、Gley、Sharen、Valby、Luna、Hailey、Ines、Serena、
  Nell、Harris（按 `Breast_PoseAsset` / `SKIN/F` / F 系动画三条数据判的，不是猜的）。

### 导出一个模型

```powershell
.\export_model.ps1 Viessa                # 后裔默认装（带贴图、表情 morph）
.\export_model.ps1 Bunny_CMN_001         # 一套皮肤（Body + Head 配件 + Face 合成一副骨架）
.\export_model.ps1 MOB_CMN_1001_A001     # 一只怪
.\export_model.ps1 BOS_1001_A001 -IncludeExtras   # Boss 连同它的 Parts
.\export_model.ps1 Viessa -Force         # 重做
```

一条命令四步：`list_models.py` 解析包 → **CUE4Parse** 逐包导 ActorX pskx（真实材质槽名 +
morph + 顶点色）到 `D:\tfd_exports\cue4_exports\` → `resolve_textures.py` 把每个槽连到材质实例、
读它引用的贴图名、用 CUE4Parse 解码虚拟贴图成 PNG、用 UE Viewer 读材质参数 → Blender 无头跑
`build_blend.py` 合骨架、建材质、渲预览、存 `.blend`。产物：

```text
D:\tfd_exports\blend\<id>\<id>.blend      一副骨架 + 全部部件 + 材质（贴图相对路径）
D:\tfd_exports\blend\<id>\textures\       用到的 PNG
D:\tfd_exports\blend\<id>\preview.png / preview_face.png
D:\tfd_exports\blend\<id>\materials.json  槽 → 材质实例 → 贴图 / 参数（排查用）
```

整个 `blend\<id>\` 目录可以直接拷给别人。常用参数：`-Force`、`-NoBlend`（只到贴图这步）、
`-NoPreview`、`-Smooth`、`-IncludeExtras`（把 Parts/Separate_Parts 并进来）、`-Kind`/`-Char`
（配合 `-List`）；路径都有默认值（`-GameRoot`、`-ExportRoot D:\tfd_exports`、`-Cue4ParseExe`、
`-UsmapFile`、`-UmodelExe`、`-BlenderExe`、`-AesKeyFile`）。

已跑通：**12 个女性后裔全套**（Viessa、Bunny、Freyna、Gley、Sharen、Valby、Luna、Hailey、
Ines、Serena、Nell、Harris）+ 皮肤 Bunny_CMN_001（Body 495 骨 + Head 配件 + Face 446 骨 →
504 骨）+ 怪 MOB_CMN_1001_A001，渲图逐个目检：布料/皮甲/金属/皮肤/头发/眼睛/眉睫/头盔面罩都对。

### 批量

```powershell
foreach ($id in 'Viessa','Bunny','Freyna','Gley','Sharen','Valby','Luna','Hailey','Ines','Serena','Nell','Harris') {
    .\export_model.ps1 $id
}
```

一个约 1–2 分钟，已经有 `.blend` 的会跳过（要重做加 `-Force`）。只想重跑贴图和 Blender、
不重导网格：删掉该模型目录下的 `materials.json` 和 `<id>.blend` 再跑一次即可（第 2 步会发现
pskx 都在，自动跳过）。

## 画廊（一页 HTML 总览）

```powershell
cd .\html
python .\collect_manifest.py      # 读 blend\*\build.log -> D:\tfd_exports\tfd_models_manifest.json
python .\make_gallery.py          # 缩略图 -> D:\tfd_exports\_gallery\thumbs，页面 -> html\index.html
```

`index.html` 是自包含的一页：每个模型一张卡片（正身预览 + 圆形脸部小图、骨骼/顶点/材质/贴图
统计、说明、blend 路径一键复制），顶部可按 kind、体型筛选、全文搜索、只看告警，末尾附一份完整的
手工导出教程。图片和 blend 都是本机 `file://` 路径，**不进仓库**；换机器要重新导出再重新生成。

`collect_manifest.py` 会顺手读一次容器编目给每条打上 kind / 角色 / 编号，没有 AES key 时加
`--no-catalogue` 退化成按 id 前缀猜。模型的中文说明写在 `collect_manifest.py` 的 `NAMES` 表里。

## 前提（只做一次）

| 依赖 | 路径 | 说明 |
|---|---|---|
| 游戏 | `E:\SteamLibrary\steamapps\common\The First Descendant` | Paks 在 `M1\Content\Paks` |
| AES key | `D:\tfd_exports\_keys\aes_key.txt` | `python .\find_aes_key.py --out <路径>` 从 shipping exe 重建（~60 秒）。**绝不进仓库** |
| CUE4Parse CLI | `E:\tools\cue4parse_cli\cue4parse.exe` | joric/CUE4Parse.CLI 0.2.0（CUE4Parse 1.2.2）；首次运行自动下 `oodle-data-shared.dll` / `zlib-ng2.dll` 到 `%LOCALAPPDATA%\Temp`，已拷到同目录 |
| usmap 映射表 | `E:\tools\tfd\Mappings_2024-07-16_gildor.usmap` | 见下「usmap 从哪来」 |
| UE Viewer | `E:\tools\umodel_specific\materials\umodel_materials_ue5.exe` | 只用来读材质实例的参数（`-game=first`） |
| Blender | 3.6.15 + `io_scene_psk_psa` | PSK/PSKX 导入（含 morph） |
| Python | 3.13 + `cryptography`、`Pillow` | 前者解 utoc 索引、读 zen 包头，后者出画廊缩略图 |

### usmap 从哪来（重要）

CUE4Parse 解本作**任何**属性都必须有 `.usmap`（包是 unversioned properties，我直接读包头标志
确认的）。Nexus 上原来的 `thefirstdescendant/mods/1`、`mods/5` 两个映射文件**已被下架**（2026-09
查时整个板块只剩一个壁纸 mod）。现在用的是 Gildor 论坛 TFD 帖第 7 页（2024-07-16）网友发的
MediaFire 文件 `Mappings.usmap`（1.46 MB）。**它是发售版的映射，两年后已部分过期**：

- 能解：Texture2D / 虚拟贴图、SkeletalMesh（含材质槽名、morph）→ 网格和贴图都靠它。
- 不能解：MaterialInstanceConstant（报 `Invalid bool value`），所以材质实例引用了哪些贴图、
  参数是什么，CUE4Parse 读不出来。这块由下面两条补：

1. **`iostore.py`**：自己读容器（AES-ECB 分块解密 + Oodle）和 zen 包头的名字表，**不需要 usmap**。
   一个材质实例的名字表里就列着它引用的全部贴图名（`_C/_N/_P/_ID/_FX`、共享的 `T_*`、
   `Female_HairTex_*`），`resolve_textures.py` 靠这个把槽连到贴图。
2. **UE Viewer** 读材质实例的标量/向量参数没问题（头发根/梢色、自发光颜色、粗糙度范围、
   虹膜参数），只是它解不了虚拟贴图。

自己生成新 usmap 要往带 EAC + Nexon 反作弊的游戏进程里注入 dumper，有封号风险，没做。

## 贴图约定（build_blend.py 按这个建材质）

| 后缀 | 内容 | 用法 |
|---|---|---|
| `_C` | 颜色 | Base Color（sRGB） |
| `_N` | 法线，**DirectX 约定** | 翻绿通道再进 Normal Map |
| `_P` | 打包图 **R=AO, G=粗糙度, B=金属度**（alpha≈0） | 按 Channel Packed 读，否则 alpha 预乘会把 RGB 抹黑；皮肤的 `_P` 是另一个母材质，B 恒 255，金属度强制 0 |
| `_ID` | 六色硬边区域遮罩（红/绿/蓝/品红/黄/青 = 染色区 A–F） | 玩家染色系统用；默认外观直接用 `_C`，没接 |
| `_FX` | 自发光遮罩（R） | × 材质里的 `Emissive_col` |
| `Female/Male_HairTex_NNN_P` | 共享发丝图：A=透明度，G=发根→发梢，R/B=深度/AO | 颜色 = `Hair_RootColor`→`Hair_TipColor` 按 G 混合 |
| 眼睛 | `T_Sclera_D` + `T_Veins_D` + `T_Eye_N`；虹膜在游戏里是程序化（MetaHuman 参数：`IrisColor1U/V` 查 `iris_color_picker`） | 巩膜贴图 + 程序化虹膜圆盘（颜色目前是近似棕色，还没接取色图） |
| 眉/睫 | 母材质共享的 `T_eyebrow_d` / `T_eyelash2_D`：**发丝形状在 alpha 通道里**，RGB 是一张几乎均匀的灰卡 | 接 **Alpha → Alpha**（接 Color 会让整块面片半透明，眉毛变成一坨黑楔子）。颜色：睫毛恒为近黑；眉毛取本角色 `Hair_RootColor`（有两套头发时取最暗的） |
| `*Glass_MI` | 面罩 | 参数 `Color`/`Opacity`/`Roughness` → 半透明 |
| `EyeOCC` / `TearLine` | 眼部遮挡壳 / 泪线 | 全透明 |

材质实例名就是 pskx 的槽名（`PC_003_A0101_PartA_MI` 这种），`classify()` 按名字**和贴图**判类型。
游戏方的拼写很不统一，按名字判会漏，几处都踩过：

- `_Ml`（小写 L）是 `_MI` 的笔误，Gley、Harris 整套都这么写 → 先归一化再做后缀判断；
- 贴图后缀可以多一位数字：Gley 的脸部颜色图叫 `PC_007_A0101_Face_C1`，不认就整张脸没颜色；
- 槽名里可以夹序号：`PC_018_A_EYE_000_MI` 是眼球，按 `_eye_mi$` 判会漏 → 另加「有 `Sclera` 贴图就是眼球」；
- `Eyeblow` = 眉毛，`Eyeleash` = 睫毛，`Fur` 也是眉毛（贴 `T_eyebrow_d`）；
- `Head_999_MI` 这种没带 hair 字样的按 `HairTex` 贴图识别；
- 名字像贴图但容器里根本没有同名包的（`Face_Dyed_Mask`），一律当参数名丢掉，不算「没解析到」；
- 眉/睫的材质实例把 `texture` 参数置为 None、**从母材质继承发丝图**，所以它的名字表里一张贴图都没有
  → `resolve_textures.py` 按材质名补上母材质那两张（`T_eyelash2_D` / `T_eyebrow_d`）。
- **`fresnel_col` 不是发丝颜色**，是掠射角的边缘染色。美术偶尔会把它设成亮桃色（Gley/Nell 的睫毛、
  Bunny/Hailey 的眉毛），当底色用就渲出一圈白睫毛。发丝底色写死在母材质里读不到，所以睫毛取近黑、
  眉毛取角色自己的 `Hair_RootColor`。

## 多部件怎么合

- 同骨架部件（皮肤的 Body / Face）：按骨名并入底模骨架，缺的骨按父子关系补进去。
  Blender 坑：跨 edit-mode 切换后不能再读旧的骨引用（会 `UnicodeDecodeError`），合骨前先把
  骨名/坐标拉成普通值。
- **socket 配件**（皮肤 HEAD 里的头盔：自带 `Head_Root → Pt_Head → Bn_Socket_*` 三根骨，和
  角色骨架无交集，网格画在原点）：不能蒙皮，整体骨父级到底模的 `Bn_Socket_Head`（退而求其次
  `Bip001-Head`）。不这么做它会掉在脚边。
- 部件自己的骨和底模同名骨位置不一致时，用最靠根的共享骨算刚体差把部件挪过去（同骨架时为恒等）。

## 导出 PMX（MMD，2026-10-31 起，样品 Viessa）

```powershell
& "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" -b E:\game_export\TheFirstDescendant\Viessa\blend\Viessa\Viessa.blend `
  --factory-startup --python scripts\firstdescendant\export_pmx_blender.py -- --out E:\game_export\TheFirstDescendant\Viessa\pmx
```

写出 `<out>\<名字>\<名字>.pmx` + `textures\` + `<名字>.report.json` + `<名字>_converted.blend`（`--name` / `--model-name` /
`--comment` 可改名字和说明）。Viessa 约 5 分钟（大部分在烘焙材质颜色）。看效果：

```powershell
# 正面、12 个表情、视线、跳舞 4 帧 -> PMX 旁边的 preview*.png
blender -b --factory-startup --python scripts\stellarblade\preview_pmx_blender.py -- --pmx <PMX> --vmd <VMD>
# 跳舞视频（MMD 式物理）
blender -b --factory-startup --python scripts\riseoferos\render_pmx_dance.py -- <PMX> <VMD> <WAV> <out.mp4> 0 full mmd
```

**做法**：和星刃 / FF7 / CCFF7R 同一条链（`scripts/stellarblade/export_pmx_blender.py` → ROE 的
`export_character_model_blender.py`：Convert_to_MMD5 建 MMD 骨架和身体碰撞，mmd_cloth_physics 建头发 / 布料链，ARKit 形态键混成
MMD 标准表情，blender2xps 把节点算出来的颜色烘成一张贴图，mmd_tools 按 12.5 写 PMX）。TFD 的继承者也是带连字符的 3ds Max
Biped（`Bip001-L-Clavicle`），这个脚本只补 TFD 自己的：

- **眼睛**：眼球挂在 `Bn_FEye_L1` / `Bn_FEye_R1`（不是 `Bn_FEye_L`），按哪根骨带着眼球材质（`*_Eyes_MI`）的权重来选 →
  左目 / 右目 + 両目；没有这两根骨的模型按眼球材质给它补眼骨（星刃的做法）。
- **胸部**：`Bn_Shape_Chest_L` / `_R` → 左胸 / 右胸 + 星刃那种球形刚体和弹簧关节。
- **整个角色是一个网格**，带 52 个 ARKit 形态键（共 111 个）。Convert_to_MMD5 摆 A 姿势时会跳过带形态键的网格——
  骨架放下手臂、网格还是原样——所以借用 ROE 的 `keep_shape_keys_in_rest_bakes`（`scripts/riseoferos/export_suit_pmx_blender.py`）
  连形态键一起烘进 A 姿势。
- **表情**：没有 MetaHuman 的 `TeethLowerDown`（牙齿在同一个网格里，`jawOpen` 自己会带动），配方里去掉这一项，
  否则あいうえお 会整个被跳过。
- **不是布料的辅助骨**：`Bn_Shape_*`（游戏按姿势驱动的修形骨）、`Bn_Twist_*`、`Bn_Pos_*`、护甲的 `Pt_*`、挂点
  （`Bn_Socket_*`、`Bn_Weapon_*`、`Bn_Acc_Hang*`）不让 mmd_cloth_physics 当布料；扭转骨和带皮肤的修形骨由 ROE 的辅助骨规划按
  皮肤位置分到肢体上（Viessa：19 根，例如 `Bn_Shape_Hip_L` 跟 左足 转 53 %）。
- 骨骼上挂的刚性部件（头盔挂在 `Bn_Socket_Head`）改成 100 % 蒙皮到那根骨；`.blend` 里预览用的 `Cube` 等非角色网格不导出。
- 厘米 → 米；按两只脚的朝向转成面向 -Y（TFD 的 `.blend` 本来就是）。
- **不透明材质的贴图 alpha 填满**（10-31 下午补的）：MMD 会把贴图的 alpha 乘进材质，游戏贴图的 alpha 常放遮罩。
  Viessa 牙齿的 `PC_003_A0101_T_Mouth_C.png` 在牙齿的 UV 上 alpha 平均只有 0.75，MMD 里张嘴时牙齿是半透明的，
  而 Blender 的预览看不出来。导出后，凡是只给不透明材质（原 `.blend` 里 `OPAQUE`）用的贴图，alpha 一律填成 1，
  颜色不动（星刃脚本里的 `opaque_materials` / `fill_opaque_alpha`）。
- **共用一个材质的网格先合并再烘焙**（同日，NARAKA 上发现的）：`bake_node_colours` 只按第一个用到该材质的网格烘，
  其余网格采到空白。烘焙前把共用材质的网格合并（`join_meshes_sharing_materials`），报告里的 `opaque_holes` 列出
  不透明材质上烘空的三角形占比。Viessa 整个人是一个网格，不受影响；其余继承者批量时会自动处理。

**样品 Viessa**（`E:\game_export\TheFirstDescendant\Viessa\pmx\Viessa\`）：98,530 顶点，739 骨，26 个 MMD 表情 + 111 个
ARKit，42 刚体 / 26 关节（头发 6 条链、腰带、锁骨挂件、胸部），零权重洞 0，A 姿势 37°，Spine3 并进 Spine2（MMD 的 上半身3
已用 Spine2），撕裂 1 条边。预览、表情、视线、手势舞视频都看过，动作里没有撕裂或物理炸开。

## 已知限制

- PMX：Gley、Harris、Nell 没有 `Bn_Shape_Chest_*`，这三个没有胸部物理；`Bunny_CMN_001`（身体 / 脸 / 头分开的三个网格）和
  Monster 没试过。金属护甲在 MMD 里偏白（MMD 没有金属质感）。Blender 里打方向光时皮肤、头发上会有零星小白点：是
  MMD 材质的高光（高光关掉就没了，星刃 / FF7 转出的 PMX 一样），不是破洞。`_converted.blend` 里的贴图是绝对路径，直接
  导到存档目录（`--out E:\game_export\...\pmx`）就不会指向临时文件夹。
- 虹膜颜色是近似值（游戏用 `IrisColor1U/V` 去 `iris_color_picker` 取色，图已解出来在
  `cue4_exports\M1\Content\BaseMaterials\Character\Material\Eyes\Texture\`，还没接采样）。
- 染色系统（`_ID` + `ID_A..F_col`）没接；默认外观就是 `_C` 的颜色。
- usmap 是 2024 年的：新加的类（后续赛季的材质母版）若改了布局，个别贴图/网格可能解不出，
  `materials.json` 的 `missing_textures` 和 `export_model.ps1` 的 `Missing textures:` 行会报。
- AES key 会出现在 cue4parse 的命令行上（它没有 key 文件参数），本机使用可接受。

功能更新统一追加到 [更新日志](../../docs/CHANGELOG.md)。utoc 解密器与 `find_aes_key.py`
来自 [scripts/vindictus](../vindictus)（同为 Nexon UE5 IoStore 游戏）。
