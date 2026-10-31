# AION2（永恒之塔 2）模型提取

AION2 是 NCSOFT 的 MMORPG，Unreal Engine 5.3，Steam app `3393110`。本机安装在
`D:\Program Files (x86)\Steam\steamapps\common\AION2`。这套脚本做三件事：

1. 列出游戏里所有模型并分类计数；
2. 把一个模型（例如一个女性角色穿一套时装）导出成带完整材质的 `.blend`，附预览图；
3. 把导出的 `.blend` 转成 MMD 的 PMX（裙子、胸部和带骨骼的头发有物理，表情是游戏原版的）和 XNALara 的 XPS。

## 快速开始

```powershell
cd E:\code\othercode\ripper_tpose\scripts\aion2
python list_models.py --scan                          # 第一次：读全部 48 万个包头，约 1 分钟
python list_models.py                                 # 按类别统计模型数量
python list_models.py --kind costume --gender GF      # 女性时装列表（GF = 女，GM = 男）
python list_models.py --resolve GF_Angel_01           # 一个模型由哪些部件拼成
python list_models.py --women --kind npc              # 女性 NPC（性别怎么判断见下面「NPC 和怪物的性别」）
python list_models.py --find yustiel leda siel        # 按名字找模型（支持 * ? 通配符）
python export_model.py GF_Angel_01 --hair GF_Hair_308 # 导出：天使时装 + 308 号长卷发
python export_model.py NPC_Yustiel_01                 # 导出一个 NPC（身体、头、头发都是它自己的）
python html\make_gallery.py                           # 画廊：scripts\aion2\html\index.html（见下面「画廊」）
python face_data.py                                   # 转 PMX 前第一次：游戏的表情数据（见下面「转 PMX / XPS」）
```

导出结果在 `E:\aion2_exports\blend\<模型>\`：

| 文件 | 内容 |
|---|---|
| `<模型>.blend` | 一副骨架（Bip001，3ds Max Biped 命名）+ 各部件网格 + 材质，贴图在 `textures\`，相对路径 |
| `preview.png` / `preview_back.png` / `preview_face.png` | 正面、背面全身和脸部预览（EEVEE） |
| `materials.json` | 每个材质的类型和烘焙结果 |
| `spec.json` / `build.log` | 用了哪些部件、提示和告警 |

裸体版本是 `python export_model.py GF_Nude --hair GF_Hair_308`（做法见下面"裸体版本"一节）。
`--head GF_Head_006`、`--hair GF_Hair_308` 换脸和发型（输出目录名会加后缀），`--variant B` 用部件的 B 版本（如猫咪装的兜帽），
`--keep-hair` 不按头盔规则换发型或剪头发，`--force` 重新从游戏导出。

模型总目录：`list_models.py --catalogue` 写到 `E:\aion2_exports\_meta\aion2_models.json`（每个模型的类别、性别、部件；画廊读它）。

## 画廊

`python html\make_gallery.py` 生成 `scripts\aion2\html\index.html`，每次导出后重跑（约 5 秒）：

- 页首「怎么导出模型」：最短的三条命令，然后第 0–4 步——准备什么（每样东西标「本机已有 / 本机没找到」）、怎么找模型和 id 规则、
  导出命令做了什么（附在全新空目录里实测的终端输出）、结果在哪怎么打开、出问题时终端里的话是什么意思；
- 「已导出」：每个导出一张卡片（预览图、部件、骨骼数、顶点数、重做命令、`.blend` 位置）；
- 「全部模型」：6,426 个模型一张表，搜索、类别、「只看女性」「只看已导出」，每行「复制命令」。

页面用 `file://` 链接本机文件，缩略图写在 `E:\aion2_exports\_meta\gallery\thumbs\`，游戏素材不进仓库。
没有模型总目录时脚本会先调 `list_models.py --catalogue`。

## NPC 和怪物的性别

游戏只给玩家部件标了性别（`GF` / `GM`）。NPC、怪物、过场模型由 `list_models.model_genders` 判断，四条依据按顺序，先成立的算数：

1. 名字里有单独的 `F` / `M` 词：`NPC_F_Refugee_01`、`MOB_Lepharist_F_01`；`NPC_M_LegionF_01` 是男的（`M` 在前）；
2. 名字里有以 F / M 结尾的词：`VillagerF`、`ShugoAF`、`FighterF`、`KoboWorkF`、`ShugoM`；
3. 网格引用了玩家女性（`/Player/GF/`）的部件、没有引用男性的（包头的导入表）：Yustiel 的脸是 `GF_Head_041` 的贴图，
   Leda 戴的是 `GF_Hair_402`；
4. 自己的骨架里有女性胸部的抖动骨（`b_L_Breast_Base`、`Breast_L_Bone01`、`Bone_Breast`……）：Kromede、Protect、Drana 妖精。
   男性骨架的胸大肌叫 `L_Breast` / `R_breast`（Israphel 也是），猫头鹰的 `Chest_L_Bone_*`，都不算。

名字或文件夹里有 Kid / Child 的标成儿童，`--women` 和画廊的「只看女性」都不含。结果缓存在 `_meta\aion2_genders.json`
（游戏更新后自动重判，`--regender` 强制重判）。2026-10-25 的版本：NPC 里成年女性 83 个（含修果族、Shulack 等非人类），
女性怪物 / Boss 22 个。没逐个看图，可能差一两个。

## 模型数量（2026-10-25 的游戏版本）

全游戏 9,822 个骨骼网格（SkeletalMesh）、9,610 个静态网格（StaticMesh，场景 6,286、角色相关 1,447、特效 1,426 等）。
骨骼网格按游戏的拼装方式归成 6,426 个模型：

| 类别 | 女（GF） | 男（GM） | 说明 |
|---|---:|---:|---|
| 编号盔甲 `outfit` | 145 | 150 | `Armor/<编号>/<性别>_<编号>_T<阶>`，每套 Body、Pants、Glove、Boots、Helmet、Shoulder、Cape |
| 时装 `costume` | 97 | 100 | `Armor/Special`：天使、女仆、旗袍、泳装、韩服、内衣…… |
| 帽子 `hat` | 99 | — | `Armor/Helmet` |
| 变身套装 `polymorph` | 8 | 8 | |
| 共用部件 `outfit_common` | 78 | 60 | 多套共用的裙摆、发箍 |
| 发型 `hair` | 103 | 102 | 每款还带 `_Type1/_Type2`（戴帽子时用的版本） |
| 脸 `head` | 59 | 61 | 拓扑相同，可互换 |
| 饰品 `acc` | 601 | 588 | 耳环、项链、戒指…… |
| 底模 `base` | 7 | 6 | 默认上衣 + 裙子、腿、鞋、头 |

| 类别 | 数量 | 说明 |
|---|---:|---|
| 武器 `weapon` | 1,013 | 左右手一对算一把 |
| 怪物 `monster` | 820 | 另有新手区怪物 93 |
| NPC `npc` | 268 | 共 571 个部件（身体、头、头发、裤子……） |
| 翅膀 `wing` | 79 | |
| 坐骑 / 宠物 `veh` | 43 | |
| 道具外观 `etc` | 620 | 附魔、掉落物 |
| 其他 `other_skeletal` | 1,156 | 过场动画、任务物件、家园摆设 |

## 怎么做到的

### 1. 容器和密钥（`aion2_pak.py`）

- `Aion2\Content\Paks` 里有 282 个 IoStore 容器（utoc v5，Oodle 压缩），其中 245 个用默认密钥（GUID 全 0）做了
  AES-256 加密：目录索引和每个压缩块都加密。解开后共 710,336 个文件。
- **密钥不在仓库里**：放在 `E:\tools\aion2\_keys\aes_key.txt`（一行 `0x…`），或环境变量 `AION2_AES_KEY`。
- 密钥没法像 TFD / Vindictus 那样从 exe 里扫：`AION2.exe` 加了 NCSOFT 的 NCGuard 壳（区段名 `.ncg0`…`.ncg6`，
  代码在磁盘上是加密的）。用的是网上公开的密钥：2025-11 Pastebin 上那把对现在的版本已经无效，
  2026-10-12 SCSKiller 项目 issue #158 里贴出的那把（从运行中的游戏里取的）能解开全部容器。游戏更新换了密钥时，
  `python aion2_pak.py --info` 会报错或解出 0 个路径。
- 包头解析不需要 usmap：UE 5.3 的 zen 包头（52 字节）+ 名字表 + 导出表，类名从 `global.utoc` 的脚本对象表查。
  `list_models.py --scan` 用 6 个进程读完 480,500 个包头约 1 分钟（2026-10-25 在空目录实测 53 秒），结果缓存在 `E:\aion2_exports\_meta\aion2_classes.json`
  （按容器的大小和日期判断是否过期）。

### 2. 导出网格（UE Viewer）

属性是"无版本"格式（unversioned），CUE4Parse / FModel 需要 usmap，生成 usmap 要往带 NCGuard 反作弊的游戏里注入，
有封号风险，没做。改用 spiritovod 的 UE5 特制版 UE Viewer（`E:\tools\umodel_specific\materials\umodel_materials_ue5.exe`，
`-game=ue5.3`），它不需要 usmap 就能导出 SkeletalMesh / 贴图 / 材质参数（`.props.txt`）。
UE Viewer 不支持通配符，`export_model.py` 一个包调用一次（每次约 5–10 秒，主要花在扫目录）。

### 3. 拼角色（`list_models.resolve`）

- 女性 / 男性玩家角色是拼装的：套装的部件 + 脸 + 发型。套装没有 Body / Pants 时用底模的 `GF_BaseBody` / `GF_BasePants` 补上
  （时装的 Body / Pants 自带皮肤，所以有这两件时不用底模）。没有 Boots 就是光脚（底模的腿自带脚）。
- 同一槽位有 `_A` / `_B` 两个版本（猫咪装、企鹅装的兜帽等）时默认用 A。
- **头盔规则**（`export_model.helmet_rules`）：头盔的 `EPS_<套装>_Helmet`（`AionEquipPartsSettingData`）属性读不了，
  但它的名字表就够用：
  - 名字表里有 `<性别>_Hair_NNN`：戴这顶头盔时换成这款发型（全盔 GF_0001_T04、泳装泳帽 → `GF_Hair_009`，贴头皮的短发）；
  - 有 `<部件>_Clip`：那是一个四边形平面，头发在头顶一侧的面删掉（GF_0010_T05）；
  - 都没有（光环、女仆头饰、圣诞帽）：头发不动。

### 4. 材质烘焙（`bake_materials.py`）

AION2 的角色材质在运行时合成，直接用 UE Viewer 导出的贴图是灰的或不对，所以烘成普通 PBR 贴图（底色、ORM、自发光），
Blender 里只接 Principled BSDF，转 XPS / PMX 也能直接用。按父材质链分类：

| 类型 | 父材质 | 做法 |
|---|---|---|
| 盔甲 / 时装 | `CM_Armor*` | `BaseColor` 是灰色明暗图；颜色来自染色：`Cstm` 遮罩的 R/G/B/A 各选一块区域，乘 `CustomMask<通道>_Color`。ARM = AO / 粗糙度 / 金属度，各遮罩通道再按 `Detail<通道>_Metalic` / `_RoughOffset` 调；`SE` 的 G 通道 × `EmissiveDay_intensity` = 自发光（光环 5）；`_DO` 的 A 通道 = 透明度 |
| 皮肤 | `CM_Body_Cstm` | 底色 + `ARS(C)`（AO / 粗糙度 / 高光） |
| 脸 | `CM_Head_Cstm` | 共用的 `GF_Head_D`（已带唇色、腮红）+ 每款脸自己的法线；眉毛从 `Cstm_EyeBrow_T2A` 取第 `EyeBrow_NUMBER` 张（B = 眉毛、A = 眉笔），按 `BROW_BOX` 贴到右眉位置再镜像；`Use_EyeBrow = 0`（NPC 自己的脸贴图已画了眉毛）时不画 |
| 眼球 | `CM_Eye` | 程序化虹膜：`IrisColor_Mid` → `IrisColor_Edge`，纹理取 `Iris_02_M`；虹膜 UV 半径 = `IRIS_UV_PER_SCALE` × `Iris_Scale`（越大虹膜越大），瞳孔色 `Pupil_Color` |
| 睫毛壳 | `CM_EyeAO_Cstm` | `Eye_AO_M_*`：G = 上睫毛，B = 下睫毛，R = 眼角阴影 → 黑色带透明度 |
| 泪线 | `CM_EyeAO_Trans` | 全透明 |
| 头发 | `CM_HairCard*` | 发根 / 发中 / 发梢颜色 × `DIRO` 的 R（发丝明暗），A 透明度按 `OpacityFar` 放大 |

几个坑（都已在脚本里处理）：

- **头发图集上半张是发片、下半张是头皮**。发片的 UV 占满整张高度，头皮部分的 v 在 -1 到 0，游戏材质把 v 压成一半。
  `build_blend.py` 直接改网格 UV（`v' = 0.5 + 0.5·v`）。不改的话发片下端会落在头皮色块上，变成深色方块（203 / 208 / 412 号发型）。
- **很多发型的材质槽导出来叫 `material_0`**（UE Viewer 解析不了网格里的材质引用）：`export_model.py` 先看网格包头的导入表
  （`material_imports`），没有再退回到网格旁边的 `Materials\MI_<网格名>`，单独导出并把槽位改名。
  - NPC 用玩家发型时只看文件夹会猜错：Leda 的头发旁边只有她衣服的材质，原来套上了裙子的布料；导入表里写的是
    `GF_Hair_402/Materials/MI_GF_Hair`。
  - 导入名和文件名可以对不上：游戏包里那个文件叫 `MI_GF_Hair_402.uasset`，按同文件夹的名字前缀找。
  - 每款发型都有一个叫 `MI_GF_Hair` 的材质实例，同名的按路径区分（Blender 里叫 `MI_GF_Hair__GF_Hair_402`），烘焙按路径找。
- **虹膜大小**：`Iris_Scale` 越大虹膜越大。原来当成 UV 缩放（半径 0.47 / `Iris_Scale`），只有默认脸（1.75）对，Yustiel（0.8）的瞳孔
  撑满了整个眼睛，看起来全黑。用射线测过头部网格：眼球露出来的部分在 UV 上横向约 ±0.25、上下约 0.1，玩家和 NPC 的眼球 UV 一样。
- 发丝透明度不放大的话，001 号寸头会露出大片头皮。
- 时装各部件的骨架摆放偏差最大约 1.2 cm（披风），超过 0.5 cm 的部件会先摆到主骨架的静止姿势再绑定。

### 5. 拼装（`build_blend.py`，Blender 3.6 + io_scene_psk_psa）

逐个导入 PSK，按骨骼名把各部件的骨架合进骨骼最多的那副（脸部、头发、披风的骨骼会补进去），接材质，
拷贝贴图到 `textures\`，保存 `.blend`，渲染三张预览。角色面朝 -Y，单位是厘米（和其他游戏的流程一致）。

## 裸体版本（`GF_Nude`）

```powershell
python nude_survey.py --gender GF --write              # 一次：量底子的开口、存各套时装的皮肤做参考（约 15 秒）
python export_model.py GF_Nude --hair GF_Hair_308      # 裸体 + 001 号脸 + 308 号头发，约 1 分钟
```

游戏里**没有现成的裸体**：底模 `GF_BaseBody` 是默认上衣加裙子，`GF_BasePants` 是紧身裤，`GF_RootMesh` 只有 1,120 个面，
商店人台 `ETC/Mannequin/GF` 是完整的裸体，但网格不同（和时装身体差 0.7–1.4 cm）、手臂截断。所以裸体是拼出来的：

1. **底子**：内衣时装 `GF_Underwear_01` 的上身和下身，只留皮肤材质槽（`GF_BaseBody`），两件在腰线处顶点完全重合，焊上。
   剩 5 个洞：两个罩杯、两道背后的内衣带缝、内裤区（加上脖子开口，留给头）。
2. **罩杯和背带缝**（小洞）：封口、细分、平滑，再沿法线投影到**一套**别的时装露出来的皮肤上。
   - 选法：先挑洞口边缘离它最近的 5 套（同一家族的偏差为 0），再取其中能覆盖 90% 的那套；现在罩杯选的是 `GF_Xmas_03_Body`。
   - 只用一套：把上百套时装的皮肤混在一起当参考时，罩杯坑坑洼洼（每套的乳房形状略有不同）。
   - 这几处的 UV 落在同一块 UV 岛里，直接插值，皮肤纹理连续。
3. **内裤区**（没有任何时装露出来）：用人台自己的面补。
   - 选面：人台面离它最近的皮肤点就在洞口上，或者沿法线 1.6 cm 内碰不到皮肤（裆部要靠这条）。
   - 缝合：两圈各自按弧长参数化，用动态时间规整（DTW）求单调对应；补片边缘挪到洞口折线上，内部用调和位移跟着动；
     两圈在对方的参数处互相切边，再焊接（`zipper_stitch`）。试过的其他做法都留了开关 `BRIDGE`，问题记在注释里：
     `bridge_loops` 在裆部扭了，按序号配对会剪切，弧长直接对应会整片滑动。
   - 人台太稀（内裤区只有 27 个内部点），先把补片内部细分到约 1 cm，再贴回露出最多那块皮肤的时装（`GF_Swimsuit_07_Pants`，
     能盖住补片的 41%）。拉力从接缝往里 2 cm 渐入，否则接缝旁会折出锯齿；最后整片平滑 15 轮（接缝固定）。
   - 颜色：这块 UV 跨了好几个岛，没法插值。改用单独的材质 `GF_BaseBody_fill`，颜色来自顶点色 `fill_color`：
     在洞口处从皮肤贴图取色（先由 sRGB 换成线性），再往里扩散，所以洞口处没有色差。
4. **清理**：删掉重复面和退化面，对非流形边处重新封口。最后除了脖子没有开口，非流形边 0 条。

补出来的面带面属性 `nude_fill`（> 0，按洞编号），在 Blender 编辑模式里可以按属性选中，拿来重画或雕刻。

## 转 PMX / XPS

```powershell
$blender = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
python face_data.py        # 第一次：游戏的表情数据 -> E:\aion2_exports\_meta\face（要 CUE4Parse CLI 和类型映射，见下）
& $blender -b E:\aion2_exports\blend\NPC_Yustiel_01\NPC_Yustiel_01.blend --python export_pmx_blender.py -- --out E:\aion2_exports\pmx --model-name Yustiel
& $blender -b E:\aion2_exports\blend\NPC_Yustiel_01\NPC_Yustiel_01.blend --python export_xps_blender.py -- --out E:\aion2_exports\xps
```

输入是 `export_model.py` 导出的 `.blend`（不改它）。PMX 在 `E:\aion2_exports\pmx\<模型>\<模型>.pmx`（贴图在 `textures\`，
旁边的 `<模型>_converted.blend` 是转换后的场景），XPS 在 `E:\aion2_exports\xps\<模型>\`。一个人的 PMX 转换 40–100 秒。
重新导出时只替换 PMX、`textures\` 和转换后的场景，文件夹里别的东西（视频、截图）不动。

2026-10-31 导出的 7 位（都在 `E:\aion2_exports\pmx` 和 `xps` 下）：

| 模型 | `.blend` | 刚体 | 表情 | 说明 |
|---|---|---|---|---|
| Yustiel | `NPC_Yustiel_01` | 94 | 89 | 头发是生成的骨骼链（7 条 × 5–7 节） |
| Leda | `NPC_Leda_01` | 152 | 89 | 披风、头发、裙子；另有 AI 放大版 `NPC_Leda_01_AI4x` |
| Hadar | `NPC_Hadar_01` | 61 | 89 | |
| Satia | `NPC_Satia_01__Head_006` | 35 | 89 | 游戏里是幽灵，见下 |
| Snotra | `NPC_Snotra_01` | 37 | 89 | 光头是原设计；左右眼两个材质 |
| Urd | `NPC_Urd_01` | 74 | 89 | 肩上的松鼠并成一根骨骼 |
| Siel | `NPC_Siel_01` | 157 | 0 | 过场模型：缩小 0.612 倍，武器球去掉，没有表情骨 |

（表情 89 = 26 个标准 MMD 表情 + 11 个过场表情 + 52 个 ARKit 表情；刚体数含按腿拟合时大腿、小腿各拆成两半的碰撞体。）

PMX 转换复用 Rise of Eros / Stellar Blade / FF7 / CCFF7R 那套（Convert_to_MMD5 建 MMD 骨骼和身体碰撞体、手臂放到 37° 的 A 姿势、
付与骨、mmd_cloth_physics 给裙子和头发链加物理、mmd_tools 写 PMX），`export_pmx_blender.py` 只补 AION2 自己的差别：

- **骨骼**：Biped 骨骼名带连字符（`Bip001-L-Clavicle`），改成空格写法；眼球骨 `b_L_Eye_0` / `b_R_Eye_0`（过场骨架是
  `Bone_eye_L` / `_R`）当左右目；`Face_Root` 下 120 多根表情骨和 `Helmet` 挂点并进头；胸部 `b_L_Breast_Base` + `_001`
  并成一根，加胸部物理；肌肉辅助骨（`Bipceps`、`Triceps`、`Deltoid`、`Butt` → `Butt_Jiggle` ……）算肢体辅助骨，不当布料
  （两根连着的会被当成一条布链乱甩）；`Skirt_Root` 下的链改名 `Skirt_*`、长袖 `LinkFore_*` 改名 `Sleeve_*`、名字带 `cloth`
  的链改名 `Drape_*`，物理插件才会选裙子、袖子、飘带的预设（`cloth` 不在 Convert_to_MMD5 的布料词表里：Siel 背后那段披帛
  `B_hand_cloth` 被当成脊椎辅助骨并进了脊椎，手臂放下时撕开了 13 条边）。
- **头发没有骨骼**（Yustiel：长发蒙皮挂在头、脊椎、骨盆、锁骨上）：`hair_chains.py` 先在头发上生成骨骼链再转换——按头顶看的
  方位角把长发均匀分成 7 条，每条按高度约 8 cm 一节，关节放在该条头发的中心；原来挂在脊椎、锁骨上的权重按方位角分给相邻
  两条、按高度分给相邻两节，挂在头上的部分不动，搭在肩上的短发（方位角 55°–75° 以外）保持原样。骨骼名 `Hair_Gen_<条>_<节>`，
  物理插件按头发预设加刚体（Yustiel 42 个）。`--hair-chains off` 不生成。头发自带骨骼链的（玩家发型、Leda、Hadar、Siel）不动。
- **第二套 Biped**（Urd 肩上的松鼠：`Bip002-*`）整套并成一根骨骼，挂在原来的肩上；不然物理插件会把它的 30 根骨骼当成一件外套甩。
- **武器**：挂在根骨骼上、名字带 `weapon` 的骨骼，它的网格删掉（Siel 的金球在过场的初始姿势里离她 3.4 米）；`--keep-weapon` 保留。
- **巨人**：头部骨骼高过 2 米的模型缩到和其他人一样（头部骨骼 1.67 米）。Siel 在过场里头高 2.73 米，缩小 0.612 倍；MMD 的动作
  是按普通身高做的。
- **身体碰撞体按实际的腿和身体拟合**（写完 PMX 后的最后一步，`scripts/mmd_physics/cloth_collision_pmx.py --skin … --thigh-halves`）：
  Convert_to_MMD5 按穿着衣服的网格量碰撞体，物理插件对「一开始就压在碰撞体里」的布不检测和那类碰撞体的碰撞——Hadar 的裙子前面
  是开口的两片，压在大腿上却不撞大腿，两腿一分开大腿就从两片裙子里穿了出来（跳舞第 110 帧起整条腿露在前面）。拟合的表面是
  皮肤和脸的材质 + `*_Pants` 部件的材质（被绑腿盖住的腿，腿的表面就是绑腿），`*_Boots` 部件的材质管小腿；拟合后裙子一直挡在腿前。
  皮肤和衣服共用一个材质的（Siel）跳过。`--no-collider-fit` 不做。转换后的 `.blend` 里还是拟合前的碰撞体，以 PMX 为准。
  物理插件的 `legs_inside="collide"`（`--legs-inside collide`）对 Hadar 没用，留作选项。
- **贴图透明度**（10-31 加，`scripts/pmx_tools/texture_alpha_blender.py`）：MMD 会把贴图的透明度乘进材质。写完 PMX 后，
  只被裁切材质用的贴图按游戏的裁切值（0.33）把边缘变干净（Hadar 的身体和裤子、Leda 的披风、Urd 的身体、Siel 的镂空部分），
  只被不透明材质用的贴图透明度补成 1（这 7 位本来就没有这个问题）。10-31 已经对 14 个 PMX（含 AI4x）补做过一遍。
- **表情**（全是顶点表情）：游戏的女性头部带一份 ARKit 表情姿势表 `GF_Head_006_FACS_PA`（52 个：`eyeBlinkLeft`、`jawOpen`、
  `mouthSmileLeft` ……，每个是脸部骨骼的叠加姿势）。脚本在脸部骨骼还在的时候逐个摆出来，存成形态键（`facs_morphs.py`），
  转换手臂时先收起来（转换会跳过带形态键的网格），转换完放回，然后
  - 26 个标准 MMD 表情（まばたき、笑い、ウィンク、あいうえお、眉……）按 Stellar Blade 的配方从 ARKit 表情混合；
  - 11 个过场动画的整脸表情（`GF_CineFacial_PoseAsset_01`：`Face_Smile`、`Face_Angry`、`Face_Sad`、`Mouth_A` ……，
    游戏动画师调的 ARKit 比例），放在「其他」栏；
  - 52 个 ARKit 表情原样放在「其他」栏。

  姿势表在 UE 5.3 里是稀疏存的：`Tracks[t]` 是骨骼名，`TrackPoseInfluenceIndices[t]` 列出（姿势号，变换号），变换在
  `Poses[姿势号].LocalSpacePose[变换号]` 里；叠加方式是 R = dR × R_ref，T = T_ref + dT。各骨骼的参考姿势从头部那个部件的 PSK 读：
  UE Viewer 把骨架按 Y 轴镜像写出（位置 (x, -y, z)，旋转取共轭），脚本先核对 PSK 骨骼和 Blender 骨架的位置（Yustiel 误差
  0.0000 cm），对不上就报错。`--facs none` 不做表情，`--game-faces none` 不要过场表情。
- **贴图**：MMD 只画一张颜色贴图，没有法线贴图和 AO。衣服（`armor` / `phantom` 类材质）把法线贴图的凹凸明暗乘进颜色
  （系数 = 1 − 0.6 ×（1 − nz²），nz 是法线的竖直分量，斜面变暗），衣服、皮肤、脸再补乘 ORM 贴图的 AO，写成 `<材质>_pmx.png`。
  `bake_materials.py` 给 `.blend` 烘颜色时已经乘过一部分 AO（颜色 ×（k + (1 − k) × AO），衣服 k = 0.55，皮肤和脸 0.65），
  PMX 只补剩下的 AO ÷（k + (1 − k) × AO），合起来正好是完整的 AO 一次；AO 通道中位数低于 0.25 的不当 AO（Snotra 脸上的金属
  饰件那张图 AO 通道全是 0，乘了就成了黑的）。Yustiel 的裙子在游戏里是纯色缎面，刺绣、饰纹、褶皱全在法线贴图里，不乘的话
  MMD 里是一片光滑的纯色。`--relief 0` 不乘凹凸，`--no-ao` 不乘 AO。
- **高清**：贴图用的是游戏里最大的那一级——实测各贴图包头里记的尺寸（`aion2_pak` 读包，找 `PF_` 像素格式字符串前面的宽高）：
  NPC 的衣服 1024（Leda、Siel），共用的身体和脸 2048，UE Viewer 导出的已经是最高一级，游戏里没有更大的。想要更大只能 AI 放大：
  `E:\tools\upscale\esrgan.py`（4x-UltraSharp）把 `.blend` 的 `textures\*_albedo.png` 放大到另一个文件夹，再加
  `--albedo-dir <那个文件夹>` 转换，同名的颜色贴图就换成放大的（凹凸和 AO 跟着放大的尺寸算）。放大出来的细节是 AI 画的。
  Leda 的样品：`E:\aion2_exports\pmx\NPC_Leda_01_AI4x\`（贴图 4096，文件夹 246 MB，原版 85 MB），对比图在同一文件夹。

**Satia** 在游戏里是幽灵：她的材质只有 `*_LT` 一套，父材质 `CM_Mob_Phantom`（边缘发光、半透明），头部也只有一个这种材质，
眼睛也画成了皮肤。`bake_materials.py` 把这种材质当盔甲烘（`phantom` 类，用它底下的颜色 / ARM / `Normal_BC5` 贴图，衣服用的是
男性盔甲 `GM_0042_T04` 的灰色底图，没有染色，所以是白银色），头换成她材质里引用的 006 号玩家脸：
`python export_model.py NPC_Satia_01 --head GF_Head_006`（给 NPC 指定 `--head` 就替换它自己的头，目录名加 `__Head_006`）。
幽灵效果本身没有做。

**表情数据**：`face_data.py` 用 CUE4Parse CLI（`E:\tools\cue4parse_cli\cue4parse.exe`）读游戏包，AES 密钥和 `aion2_pak.py`
读法一样，不打印。AION2 的包没有属性标签，CUE4Parse 要类型映射（usmap），AION2 没有公开的（得从运行中的游戏里导，
游戏有 NCGuard，不做）。姿势表用到的类（`PoseAsset`、`PoseData`、`Transform`）是 UE 5.3 引擎自带的，给 Vindictus 拼的 UE 5.3
映射（TFD 的 5.2 映射 + `scripts/vindictus/levels/patch_usmap.py`）就能读，放在 `E:\tools\aion2\vdf53_patched.usmap`。
同时导出的还有 `GF_Head_023_FACS_PA`（另一款女性头）和 `GM_Head_004_FACS_Pose`（男性头）。

**XPS**：`export_xps_blender.py` 用 Blender2XPS 导出。骨骼名换成 XPS 标准名（`arm left shoulder 2` ……，所以 XPS 姿势能用），
颜色贴图 + 法线贴图（XNALara 会用法线贴图），单位缩小 100 倍（Yustiel 1.84）。XPS 没有表情，表情在 PMX 里。

**在 Blender 里看 PMX**：用 mmd_tools 导入 PMX 渲染时，它把半透明材质设成「哈希」透明，EEVEE 下头发和它投的影子会有白色闪点；
改成「裁剪」就没有了。MMD 里不会这样。

## 已知限制

- **裸体是光滑的"芭比"身体**：游戏的皮肤贴图在胸部和私处本来就没有画任何细节（`GF_BaseBody_D` 实测），裆部形状来自商店人台。
  后腰的内裤线和臀沟顶端还能看到很淡的痕迹。内裤区的颜色用的是顶点色，导出 XPS / PMX 前需要先烘成贴图（还没做）。
  目前只做了女性（`GF`）；男性 `GM_Nude` 要先导出男性内衣时装再跑 `nude_survey.py --gender GM`，还没试过。

- 脸部妆容只做了眉毛：眼影、眼线、唇妆图层（`MK_Head_EEE/HBS/LFL`）没有烘，底色贴图本身已带唇色和腮红；眉毛位置是对着
  `GF_Head_D` 估的（`--brow-box` 可调）。
- 眼睛的虹膜大小、巩膜颜色是按参数近似的，没有折射和高光贴图。
- 头发只用了一个颜色（`MidColor`），发根到发梢的渐变（顶点色、`RootColor` / `TipColor`）没有做。
- `EPS` 的数值属性（比如帽子用 `_Type1` 还是 `_Type2` 发型）读不了；`Body` / `Boots` / `Glove` 的 `_Clip` 平面还没用上。
- 脸部的捏脸变形（`MorphTarget`，如 `Mph_Smile`、`EarShapeChange`）UE Viewer 的 PSK 里没有。
- 染色用的是材质里的默认颜色，游戏里玩家可以改。
- NPC 只按自己文件夹里的部件拼。Yustiel、Leda、Hadar、Satia、Snotra、Urd 头和身体都在，导出完整；Grisilla、Hitanie 只有头，
  Chloris 只有头盔，`NPC_F_Daeva_04` 这类路人没有头和头发——剩下的部分游戏按 NPC 外观数据用玩家的脸和发型拼，这部分数据还没解。
- NPC 用的玩家发型（Leda 的 `GF_Hair_402`）颜色是那款发型材质的默认色，游戏里可能另外调过。
- 过场模型（`NPC_Siel_01`）是一个整网格，皮肤和衣服共用一个材质；裙子的亮片是自发光贴图 × 8，静止的图里比游戏里亮。
- PMX：过场骨架（Siel）没有 `Face_Root` 那套表情骨，游戏的 ARKit 表情用不上（可以用表情移植插件从别的 PMX 搬）。
  Leda 的披风在手臂放到 A 姿势时有 3 条边被拉长（最多 16 mm，物理会带开）。Satia 的幽灵效果没有做。

## 依赖

- Python 3：`numpy`、`Pillow`、`cryptography`；Oodle 解压用 `E:\tools\cue4parse_cli\oodle-data-shared.dll`（`--oodle` 可改）。
- UE Viewer：`E:\tools\umodel_specific\materials\umodel_materials_ue5.exe`（Gildor 论坛 spiritovod 的 UE5 特制版）。
- Blender 3.6.15（`D:\Program Files\blender-3.6.15-windows-x64`）+ 插件 `io_scene_psk_psa`。
- 转 PMX：Blender 3.6 里装好 `mmd_tools`、`Convert_to_MMD5` 和本仓库的 `scripts/blender_addons/mmd_cloth_physics`；
  表情数据要 CUE4Parse CLI（`E:\tools\cue4parse_cli\cue4parse.exe`）和 `E:\tools\aion2\vdf53_patched.usmap`。
- 转 XPS：Blender2XPS（`E:\code\othercode\blender2xps`，环境变量 `BLENDER2XPS` 可改）。
