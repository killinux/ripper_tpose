# AION2（永恒之塔 2）模型提取

AION2 是 NCSOFT 的 MMORPG，Unreal Engine 5.3，Steam app `3393110`。本机安装在
`D:\Program Files (x86)\Steam\steamapps\common\AION2`。这套脚本做两件事：

1. 列出游戏里所有模型并分类计数；
2. 把一个模型（例如一个女性角色穿一套时装）导出成带完整材质的 `.blend`，附预览图。

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

## 依赖

- Python 3：`numpy`、`Pillow`、`cryptography`；Oodle 解压用 `E:\tools\cue4parse_cli\oodle-data-shared.dll`（`--oodle` 可改）。
- UE Viewer：`E:\tools\umodel_specific\materials\umodel_materials_ue5.exe`（Gildor 论坛 spiritovod 的 UE5 特制版）。
- Blender 3.6.15（`D:\Program Files\blender-3.6.15-windows-x64`）+ 插件 `io_scene_psk_psa`。
