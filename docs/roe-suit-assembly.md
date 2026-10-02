# Rise of Eros：把「套装」(suit) 拼装成一个模型

ROE 的一个角色有多套「服装变体」(游戏内部叫 *suit*)。跟默认服装 (`chara_armor_pc_<id>_hd`
是一个整体 FBX) 不同，**一套 suit 不是一个整体模型**：它 = 角色的裸体底模 + 头发 +
一堆分开的服装部件网格，全部蒙皮到同一副骨架，游戏在运行时把它们叠在底模上。所以想导出
「林恩·冷艳主管」这种套装，得自己把部件拼回底模。

本文记录这条拼装线，以林恩 (`j01`) 的 **ProUniform**（冷艳主管职业制服，2026-09-12 更新
加入）为第一个实例。

## 数据在哪

| 内容 | Bundle |
|---|---|
| 裸体底模 + 头发 | `chara_bare_pc_<id>_nk.ab` → `pc_<id>_nk.fbx` |
| 该角色**所有** suit 的部件网格 | `chara_components_pc_<id>.ab`（一个包里上百个网格） |
| 某套 suit 由哪些部件组成 | `accessory_components_pc_<id>_suit_<suit>.ab`（几十 KB 的存根，
  根 GameObject 用 PPtr 指向 components 包里的真网格） |
| 该套 suit 的贴图 | `chara_tex_components_pc_<id>_suit_<suit>.ab`（`Lynn_<部件>_rgbx_Albedo` 等） |
| 脸/眼/身体/头发公共贴图 | `chara_tex_bare_pc_<id>_nk*` + `chara_tex_bare_pc_<体型>_common_head*` |

`extract_character.ps1 <id> -ExportTextures` 的收集规则已经会把 `bare`/`components`/
`accessory`/`vertex`/`suit` 以及 `chara_tex_*_suit_*` 一起 stage，所以正常提取一次该角色
就能拿到全部输入（AssetStudio splitObjects 会把每个部件导成
`<name>/FBX_GameObjects/<name>/<name>.fbx`）。

## 两个必须知道的坑

拼装难点全在部件 FBX 上（`chara_components_pc_<id>.ab` splitObjects 出来的那些）：

1. **部件 FBX 不带材质。** 原始 `import_scene.fbx` 进来后 `data.materials` 是空的。
   所以每个槽的贴图要**按部件名**去 suit 贴图目录里找 `Lynn_<部件>_rgbx_Albedo.png`
   （见 `assemble_suit_blender.py` 的 `resolve_albedo`；个别部件复用别人的图集，例如吊袜带
   `Garter` 用的是 `Lynn_EggVibrator` 的图）。

2. **蒙皮部件的顶点在正确的模型空间，但物体 `matrix_world` 是错的。** AssetStudio 把
   四肢部件的导出根设成一根肢体骨（如手套根是 `Bip001 L UpperArm`），于是 FBX 里给网格
   烘了一个多余的物体变换，导入后网格会**飘到离骨头约 1.5 m 的地方**（手套飘到身体正前方）。
   验证：手套的**局部**顶点质心 = (0.587, −0.056, 1.408)，几乎正是底模左手位置
   (0.575, −0.059, 1.391)；被错误的 `matrix_world` 推到世界 (0.612, 1.42, 1.453) 才飘的。
   躯干件的导出根是 `Root_G`（顶层，变换是单位阵），所以它们本来就对得上——这也是为什么
   外套、马甲一开始就在正确位置、手套/长袜/高跟/领饰却飘在脚边。

   **修法**：蒙皮部件——丢掉物体变换（`matrix_world = 单位阵`），把网格重新绑到底模骨架
   （顶点组名与底模骨名一一对应，静止姿势下形变=恒等，网格正好落在模型空间静止位）。
   **静态部件**（如桂冠是个 `MeshFilter`，没有骨架）正相反：它的顶点是局部坐标、靠物体变换
   定位，所以这种要**保留**自己的变换，只把它挂到底模骨架下跟着走。判据就看这个部件有没有
   自带骨架。

## 怎么用

```bash
# 1) 正常提取该角色（会顺带把 components / suit 贴图 stage 出来）
.\extract_character.ps1 j01 -ExportTextures

# 2) 列出这套 suit 由哪些部件组成
python suit_parts.py --game "<AssetBundles 目录>" --id j01 --suit prouniform
#   或： python suit_parts.py accessory_components_pc_j01_suit_prouniform.ab

# 3) 从列表里挑「穿好」的部件（去掉替代态和道具），拼装
blender --background --factory-startup --python assemble_suit_blender.py -- \
    --root <提取目录> --tex <贴图目录> --out D:\roe_exports\j01\blend\pc_j01_prouniform.blend \
    --base pc_j01_nk --parts <逗号分隔的部件名> --glb 1
```

产物：内嵌贴图的 `.blend` + 三视图 `_preview.png`（+ 可选 `glb/`），全部部件绑在底模的
`Root_G` 骨架上（可摆姿、后续可做 PMX）。

### ProUniform 实例（林恩·冷艳主管）

存根列出 17 个部件。「穿好」状态用 13 个，去掉 4 个：`EggVibrator`（道具）、`OpenVest`
（`CloseVest` 的敞开替代态）、`LLaceBra`/`RLaceBra`（敞开时才露的乳贴）。用的 13 个：
`UniformJacket, CloseVest, Ruff, L/RUniformGloves, LacePanties, Garter,
L/RUniformStockings, L/RUniformHighHeels, LaurelWreath, LaceBra`。
成品：白金职业制服 + 高领 frill + 长手套 + 吊袜带黑丝 + 金饰高跟 + 桂冠，
在 `D:\roe_exports\j01\blend\pc_j01_prouniform.blend`。

## 2026-09-19 晚：67 套全部拼完——改成直接读 bundle

上面的 FBX 路线只验证了 ProUniform 一套。要把 13 个角色的 80 个存根（去掉 13 个 `common`
——那是季节配件池，不是套装）全部拼出来时，AssetStudio 的逐对象 FBX 有三个绕不过的坑：

1. **同名覆盖**：AssetStudio 按 GameObject 名建目录，不同套装里都叫 `Underwear_obj001`、
   `Skirt_obj001` 的部件互相覆盖，剩下的那个顶点数和存根里的对不上（c01 学生装的裙子
   2104 顶点 vs 存根 2429，g01 两套的内裤 1382 vs 3318/527）；
2. **更新后的套装根本没提取**：09-12 加入的 j01 ProUniform、b01 武林在 08-30 的提取里一个
   FBX 都没有；
3. **贴图全靠猜名字**：`Iynn_`/`lynn_`/`Lynn_` 三种前缀、`_obj001rgbx`、`rbgx` 拼错、
   `IynnLDefeatGodRing` 漏下划线……

而存根本身就用 PPtr 精确指向网格和材质，所以新路线不再经过 AssetStudio：

| 脚本 | 作用 |
|---|---|
| `suit_bundle.py` | UnityPy 读存根 + `chara_components_pc_<id>.ab` + `chara_components_common.ab` + 该套的 `chara_tex_components_*`：每个部件的网格（顶点/法线/UV0/三角/子网格）、蒙皮骨名和权重、静态件的放置矩阵、渲染器材质里**真正引用**的贴图名（`_BaseMap` 基色、`_BumpMap` 法线、`_MetallicGlossMap`），贴图直接从 bundle 解码成 PNG；再按规则算「穿好」状态。产物 `D:\roe_exports\_suits\<id>\<suit>\{suit.json, parts\*.npz, textures\}` |
| `assemble_suit_blender.py --suit suit.json` | 新增的 bundle 模式：底模照旧走六槽材质，部件从 npz 建网格、按骨名建顶点组绑到底模骨架，静态件按算好的放置烘进世界坐标再骨骼父子到最近的 `Bip001` 骨；材质 = 基色 + 法线贴图，没贴图的槽用材质的 `_BaseColor`（镜片/护目镜则做成半透明玻璃） |
| `export_suits.py` | 批量驱动：`--list` / `--only a01:teacher,b01:*` / `--exclude fm` / `--force` / `--lanes 4`，产物 `D:\roe_exports\<id>\blend\pc_<id>_<suit>.blend` + `_preview.png`，清单 `_suits\manifest.json`，`_suits\_contact.png` 拼图 |
| `suit_overrides.json` | 规则判错时按 `<id>:<suit>` 手工 `include` / `exclude` 部件 |

### 坐标系：五种「部件在哪」

这是这条线里唯一真正难的地方。数据本身不说部件是在什么坐标系里建的，看了 752 个部件后
归纳出五种情况，`assemble_suit_blender.import_suit_part` 对每个部件把可能的读法都算一遍，
**取质心离该部位对应骨骼（`Area` → 骨名表 `AREA_BONES`）最近的一种**，并用原始坐标的
分布先筛掉说不通的读法（质心在身体范围内 → 允许「模型系原样」；`y` 为高度 → 允许「Unity
世界 Y-up」；质心贴着原点 → 允许「挂到骨骼」）：

| 情况 | 例子 | 放置 |
|---|---|---|
| 蒙皮件，Z-up 建在模型空间 | 绝大多数衣物 | `BoneWorld × BindPose`（= 渲染器变换 `R_x(-90°)`）转回模型系正好是单位阵，原样用 |
| 蒙皮件，Y-up 建在 Unity 世界 | c01 泳装胸衣 | 同上公式给出单位阵 → 乘 `R_x(+90°)` 翻回 Z-up；不处理会掉到脚边 |
| 静态件（`MeshFilter`），局部坐标 + 组件包里的放置变换 | 眼镜、猫耳、桂冠、翅膀 | 组件包同名对象的变换链（含 -90° 旋转和单位缩放）烘进顶点 |
| 配件池道具（`chara_components_common.ab`） | 魔化（fm）的角、光环、毛、腿环 | 按 **厘米** 建模、放置变换里带 0.01 缩放；存根把同一网格实例化成 `<x>_L` / `<x>_R`，`_R` 是镜像（跳过 X 翻转即可） |
| 只有自带物理骨的配件 | 圣诞帽、牛尾、乳饰流苏、耳坠、护士发箍、头纱、翅膀 | 运行时把存根根节点挂到 `Area` 指的身体骨下（`HairArea`→`Bip001 Head`，`NippleArea`→`Nipple_L/R`…）。放置 = 该骨的静止矩阵（取**身体网格的 BindPose 逆**，bare 包里的 Transform 是某个动作姿势，不能用）× 存根算出的绑定位置。见下面「2026-10-02：自带物理骨的配件」 |

Unity → Blender 始终只是镜像 X（j01 底模逐顶点核对过），镜像后三角形绕序要反过来，
法线用 `inv(M)ᵀ` 变换。蒙皮部件只引用自己物理骨（`ChineseKnot_Bone001`、`Earrings_Bone01x`）
的，权重回退到组件包变换链里最近的、底模也有的祖先骨。

### 「穿好」规则（`suit_bundle.select_dressed`）

- 道具：`vibrator|dildo|plug|eggvib` 去掉；
- 替代态：部件名含 `Open/Pull/Broken/Hole/R18/openbelow/openup` 且去掉该词（或 Open→Close）后
  同套里有同名部件的，去掉（`OpenVest`→`CloseVest`、`SleepwearPull`→`Sleepwear`、
  `StockingsBroken`→`Stockings`）；同一网格被存根用两个根实例化的（`WeddingTights` /
  `WeddingTightsBroken` 只是换材质）按根名判；
- 乳环/乳贴：胸区有遮盖件（不是绳/挂饰/围巾/领带）时去掉，否则保留。

规则判错的（看预览定）都记在 `suit_overrides.json`：c01 学生装黑白两双长袜留黑的；
c01 囚服、d01 SM、e01 护士的上衣不遮胸，乳环/乳贴要留；e01 乳胶装四个变体是同一件的四个
状态，三种都渲了一遍选 `LatexLeotardOpen`（闭合连体）；j01 空姐装 `ShirtOpen`/`braUp`、
k01 圣诞装的第二个眼罩去掉。

### 验证

66 套一次批量（4 路并行，每套 7–17 秒）0 失败 + 已有的 ProUniform = 67 套 `.blend`。
逐角色拼预览图（`_suits\_sheet_<id>.png`）看了五轮，每一轮修一类放置问题（Y-up 胸衣、
配件池厘米单位、按部位挂骨、脚上骨头太多导致「最近骨」误判）。18 条 WARN 全是没有
基色贴图的槽：13 套 fm 的 `FMRear` 是 298 顶点、1 mm 大的占位网格；镜片；乳胶第二层。

### 目前的限制

- 「穿好」仍是启发式 + 人工覆盖；运行时的初始显隐没有在存根里（没有 MonoBehaviour），
  真要精确得反编译 `Assembly-CSharp`。
- 只出 `.blend` / `preview`（`--glb` 可选）。XPS / PMX 未接。
- fm 的挂点按「根骨与身体骨对齐」假设，朝向可能差一点；`FMRear` 占位没贴图。位置只在 f01 身上对，
  别的角色要按骨头平移，见下面「2026-10-02：魔化部件是按 f01 的身材建的」。
- 组件包里没有的贴图（j01 偶像装发髻）回退到 `D:\roe_exports\<id>\_textures\` 按材质名找。
- 自带物理骨的配件刚性地跟着挂点骨走，游戏里的摆动（Magica Bone Cloth）没有接，PMX 里也没有它们自己的物理。

## 2026-10-02：自带物理骨的配件

**问题**：j01 新年装的两只耳环都藏在头的正中间；a01 婚纱的头纱向后平伸。
全游戏只挂在自己物理骨上的配件共 18 个，把 E 盘旧版和重拼的逐个渲出来对比，结果分三类：
- **放错了（6 套 8 个）**：网格建在根骨附近（坐标贴着原点），拼装选了挂点读法，而旧的挂点公式是错的：
  - j01 新年装两只耳环、k01 战斗装两只耳环：都在头里；
  - a01 婚纱头纱：向后平伸；
  - f01 2024 圣诞帽：挂在后脑勺下面。
- **一对里少了一只**：网格建在原位（模型系），拼装选了原位读法。这种读法不管存根节点，而另一侧那只需要的平移只写在节点里，所以两只叠在同一侧：
  - f01 新年装的右流苏叠在左流苏上；
  - h01 护士装的左耳环叠在右耳环上。
- **本来就对**：d01 魅魔翅膀、f01 牛头箍和牛尾、h01 护士头箍和翅膀、j01 defeatgod 头纱。
  它们建在原位，原位读法放得对，新旧读法结果相同。

（当天先按「旧挂点公式会放到哪」推算，说翅膀、头箍转了 90°、流苏离乳头 14 cm。但拼装当时并没有给它们选挂点读法，
渲染对比后改正。）

**存根怎么建的**：

```
NYearring_R_obj001                      根节点，单位变换
└─ Lynn_Head_EarsArea_NYearring_obj001  中间节点 = 头骨在 Unity 世界里的静止变换的逆
   ├─ （渲染器）
   └─ NYearring_Bone001 → Bone002 → …   位置是 Unity 世界坐标（耳垂处）
```

- 中间节点正好是挂点骨世界变换的逆，所以运行时把根节点直接挂到头骨下，这条链在静止姿势时就把耳环放回建模时的位置。
- 18 个配件里有 10 个，这个节点和挂点骨的逆完全一致（误差 0 mm、0°），而且每个都和按 `Area` 挑的骨一样。
- 另一侧的那一只（`NYearring_L`、护士装 `REarrings`、右边的流苏、k01 `Earrings_R`）在这个节点里多带一个转角和位移：
  游戏用同一个网格，绕竖直轴转一下再平移到另一侧（j01 左耳环转 −48°、平移约 9 cm）。

**放法**（`suit_bundle.read_suit`）：

- 模型系放置 = 挂点骨的静止矩阵（身体 BindPose 的逆）× 存根的绑定位置（`world_matrix`，即整条链 × 网格 BindPose）。
- 以前是先把网格换算到它自己根骨（`NYearring_Bone001`）的空间，再把这根骨对齐到身体骨，丢掉了中间节点里的位移和转角，于是有了上面那些错。
- 拼装器给的读法名叫 `attach:<骨名>`，耳环、头纱、圣诞帽都选中它。
- 建在原位的网格，挂点读法和原位读法结果一样（节点正好是挂点骨的逆），所以「本来就对」的那些不受影响。

**另外三处**：
- **一对里的另一只**（`assemble_suit_blender.part_side`）：名字标了左右（`REarrings`、`NYearring_R`、`RightChineseKnot`）的这类配件，
  即使网格建在原位，也给它挂点读法。哪种读法把它放到了身体另一侧（质心的 X 和名字标的左右相反），就加 1 m 的罚分。
  于是右流苏、左耳环选中挂点读法，回到自己那一侧；不标左右的（翅膀、头箍、牛尾）还和以前一样打分。
- 名字带 `_R` 的配件原来一律当作配件池镜像件，跳过 X 翻转。
  这对配件池道具（静态件）是对的，但对自带骨的蒙皮件，左右已经写在中间节点里，再翻一次会把右耳环翻回左耳、和左耳环叠在一起。
  现在镜像只认静态件。
- 这类配件引用的骨身体骨架里都没有，权重全被丢掉，网格不跟头动。
  拼装器现在直接把它们 100% 绑到挂点骨（`bound_to`）。`fix_suit_slots_blender.py` 的 `fix_unweighted_pieces` 只给以前拼的文件用。

**验证**：
- 18 个配件逐个算了新挂点公式的位置：耳环左右各在耳朵外侧约 6 cm 且对称，流苏和中国结在乳头下方竖直下垂，
  翅膀和头箍左右展开，圣诞帽在头顶。
- 受影响的 6 套都重做了：a01 婚纱、j01 新年装、f01 2024 圣诞、f01 新年、h01 护士、k01 战斗。
  E 盘旧版和新版放在一起渲染特写对比：
  - 耳环左右各一只挂在耳垂下；
  - 头纱罩在头上，顺着后脑垂到肩膀；
  - 圣诞帽戴在头顶，两边乳头各一个流苏；
  - a01、j01 的 PMX 导入后也一样。
- 魅魔、牛装重拼后和旧版一模一样，E 盘上的没换。
- j01 defeatgod 的头纱是在模型原位建的（读法 `model-frame`），位置本来就对，以前只缺权重。
- 对比图在 `E:\game_export\RiseOfEros\_hq_trial\suits_agj\ownbone_fix_*.png`。

## 2026-10-02：贴图名只差大小写，缓存里会串

- k01 战斗装的眼罩在游戏材质版里是黑的，拼出来是青金色。
- 原因：战斗装的贴图叫 `Clara_Eyemask_obj001_rgbx_Albedo`，2025 圣诞装的叫 `Clara_EyeMask_obj001_rgbx_Albedo`（大写 M）。
  `hq_material_data.py` 的贴图缓存是 Windows 文件夹，不分大小写，这两张是同一个文件，先跑的那套给后跑的套装用了自己的眼罩。
- 修法：同名检测改成不分大小写，内容不同的两种拼写各自换成带摘要的唯一文件名（`Clara_Eyemask_obj001__c8051455_rgbx_Albedo`）。
- 全游戏只有 k01 有这种情况：
  - 战斗装和圣诞装的眼罩；
  - 战斗装和婚纱装的袖子（`Clara_Sleeves` / `Clara_sleeves`）；
  - 各三张贴图（基色、法线、MGAC）。
- k01 的缓存数据已重做，战斗装已重做并归档。

## 2026-10-02：魔化部件是按 f01 的身材建的

**问题**：转高清版时把新旧预览并排看，c01 魔化装的蓝色羊角挂在脖子两侧，红色小角在太阳穴，光环套在脸上；
b01、d01 等也一样，旧版就是这样。

**原因**：魔化（fm）部件是配件池里的公共道具，13 个角色共用同一份网格，顶点是照着 f01 的身体建的
（f01 偏矮：头骨静止位置比 c01 低 20 cm，大腿低 18 cm，前臂低 19 cm）。`suit.json` 里它们的 `world_matrix` 是单位阵，
拼装按原样坐标放，挂到最近的骨头上。于是不论哪个角色，部件都停在它们在 f01 身上的位置：
在三个角色的文件里逐个量，除了 10-01 已经挪过的耳朵，十几个部件的世界坐标分毫不差。

| 部件 | 在 f01 身上 | 在 c01 身上（修之前） |
|---|---|---|
| 羊角 `FMRhorn`、红角 `FMMhorn` | 头顶两侧、光环上 | 脖子两侧、太阳穴 |
| 光环 `FMLhead` | 头顶 | 套在脸上 |
| 臂环 `FMRcuff` | 贴着上臂（最近 1 mm） | 离手臂 6 cm |
| 腿环、小腿环、腿毛 | 贴着腿 | 偏低 8–18 cm，偏松 |

**修法**（`fix_suit_slots_blender.fix_fm_placement`，在游戏材质那一步之前跑，存进 `.blend`）：
- 每个部件按名字找挂它的骨头：头上的（耳、两对角、光环）→ `Bip001 Head`，臂毛 → 前臂，臂环 → 上臂，
  腿环 → 大腿，小腿环和腿毛 → `CalfSub`（没有就用小腿）；左右按部件质心在哪一侧；
- 平移量 = 当前角色这根骨的静止位置 − f01 的（f01 的值写在脚本的 `F01_BONES` 里，取自 `pc_f01_fm.blend`），
  只平移不旋转，和 10-01 挪耳朵的做法一样；
- 平移后改挂到这根骨头上。角原来挂在脸颊 / 嘴唇骨上，做表情时会跟着动，现在跟头走；
- 挪过的部件打上 `roe_fm_moved`，再跑不会重复挪；10-01 已经挂到头骨上的耳朵算作挪过。f01 自己的平移量是 0。

**验证**：
- 量每个部件和身体表面的距离，修完后和 f01 一样：臂环最近 2 mm（修之前 6 cm），腿环 2 mm，
  臂毛底部贴着手臂（最近 3 mm），向上长出约 15 cm（f01 上也是这样，是一簇竖起来的毛）；
- c01 特写：羊角在头顶两侧，红角在光环上，光环在头顶，和 f01 一致；
- 11 套魔化装（a01 b01 c01 d01 e01 f01 g01 j01 k01 l01 m01）都已重出 `.blend` / PMX / XPS。

**还没做**：没有旋转。角色的骨头朝向差别不大，看不出来；真要精确，得按游戏运行时的挂点
（存根节点相对骨头的变换）重新算，而配件池存根里这一层是单位阵，暂时没有数据可用。

**同一次发现的另一处：魔化身体的脸和头发**。e01、f01、g01 的魔化套底模不是普通身体，而是魔化身体
（`pc_<id>_fm_nk`，也是魔化裸模的身体）。它在游戏里有自己的脸和头发贴图（`pc_<id>_fm_nk_face/_hair`）：
肤色更红，身体自带的那对角画在脸部贴图里（深蓝），头发更浅。拼装用插件挂材质，插件按家族给的是普通的
`pc_f_nk_face/_hair`：f01 魔化的角在普通脸部贴图里对到一块灰米色，换上游戏材质（再乘上 AO）后几乎是黑的。
`fix_suit_slots_blender.fix_fm_body_textures` 把还挂着家族贴图的脸、头发和魔化耳朵换成魔化贴图，
游戏材质那一步就按贴图名选中魔化材质。g01 的魔化身体只有自己的头发，没有自己的脸，脸不换。
f01 的魔化套里，配件池的羊角和身体自带的角形状、位置完全重合，两层叠在一起，换对贴图以后看不出来。
