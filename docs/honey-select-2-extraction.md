# HoneySelect 2 (Libido DX) 提取

脚本在 [`scripts/honeyselect2/`](../scripts/honeyselect2/)，用法见那里的 README。本文记录数据在哪、
怎么读、游戏怎么把一个角色拼起来，以及导出时每一步为什么这样做。

## 1. 资源布局

- `abdata\` 下 2474 个 `.unity3d`（UnityFS、LZ4，不加密），Unity 2018/2019 系，UnityPy 1.25 直接读。
- 角色部件：`abdata\chara\<发行包号>\<类别>_<号>.unity3d`，例如 `chara\00\fo_top_00.unity3d`
  （一个包里几十个 prefab）；`00` 是本体，`02 … 60` 是后续追加包（DLC / DX）。
- 底模：`chara\oo_base.unity3d` 里有骨架 `p_cf_anim`、身体网格 `p_cf_body_00`（女）/
  `p_cm_body_00`（男）和头部骨架 `p_cf_head_bone`；`chara\mm_base.unity3d` 是空壳。
  只用身体 prefab 自带的骨骼会缺饰品挂点（`N_Chest_f` 等只在 `p_cf_anim` 上——实际踩到过）。
- 物品清单：`abdata\list\characustom\<号>.unity3d`，每个 TextAsset 是一类物品的 **MessagePack**
  （MessagePack-CSharp 写的 `ChaListData`：`categoryNo`、`lstKey` 列名、`dictList` 行）。
- 依赖：`abdata\abdata`（以及 `add*` 等无扩展名文件）是 `AssetBundleManifest`，给出每个包依赖哪些包。
  脸的材质引用 `st_eye_00` 等包里的贴图，身体引用 `ft_skin_b_00` 等，所以取 prefab 时要把依赖包
  一起装进同一个 UnityPy `Environment`，跨包 PPtr 才能解析。
- 角色卡：`UserData\chara\{female,male}\*.png`，PNG `IEND` 之后是 `【AIS_Chara】` 块（AI 少女同格式）。

## 2. 清单 → 模型

`ChaListData` 每行的关键列：`MainAB`（包）+ `MainData`（prefab 名）。只有这两列有效（不是 `0` /
`p_dummy`）的行才是模型；皮肤、妆、眼睛等清单只给贴图（`MainTex` / `AddTex` …）。
`hs2_data.MODEL_CATEGORIES` 列出了 31 个带网格的类别（共 812 件）：

| categoryNo | 内容 |
|---|---|
| 210 / 110 | 脸型（女 `fo_head` / 男 `mo_head`） |
| 240–247 / 140,141,144,147 | 衣服：上衣、下装、内衣上、内衣下、手套、连裤袜、袜子、鞋（男只有 4 类） |
| 300–303 | 头发：后、前、侧、附加 |
| 351–363 | 饰品：头、耳、眼镜、脸、颈、肩、胸、腰、背、臂、手、腿、股间（350 = 无） |

同一 ID 在后面的发行包里重复出现时，后面的覆盖前面的（`mo_head:0` 实际在 `chara\38`）。

找 prefab：优先查包里 `AssetBundle.m_Container`（路径以 `<prefab>.prefab` 结尾），找不到再扫根
Transform。

## 3. 角色卡

`IEND` 之后：`int32 productNo`、7-bit 长度字符串 `【AIS_Chara】`、版本、`int32 语言`、userID、dataID、
`int32 头长度` + MessagePack 头（`lstInfo`：各块 name/pos/size）、`int64 数据长度`，然后是各块：

- `Custom`：三段「int32 长度 + MessagePack」= face（`headId`、`skinId`、`eyebrowId`、`pupil[2]`、
  `hlId`、`eyelashesId`、各种颜色 …）、body（`skinId`、`detailId`、`skinColor`、`nipId`、
  `underhairId` …）、hair（`parts[4]`：id + base/top/under 颜色）。
- `Coordinate`：两段 = clothes（`parts[8]`：top、bot、inner_t、inner_b、gloves、panst、socks、shoes，
  类别号 = 240+i / 140+i，每件 3 个 `colorInfo`）、accessory（`parts[20]`：`type` = 类别号，`id`，
  `parentKey`，`addMove`，4 个颜色）。
- `Parameter`：`sex`（0 男 1 女）、`fullname` 等。

## 4. 游戏怎么拼一个角色（导出照做）

| 部件 | 挂在哪 | 骨骼 |
|---|---|---|
| 骨架 `p_cf_anim` | 原点 | 运行时骨架，男女共用：277 根 `cf_J_*` + 40 个身体挂点 `N_Chest_f`、`N_Waist`、`N_Hand_L` … |
| 身体 `p_cf_body_00` / `p_cm_body_00` | 原点 | 自带一份与 `p_cf_anim` 同姿势（误差 ≤ 0.001）的骨骼拷贝，**按名字并到骨架上** |
| 头骨 `p_cf_head_bone` | `cf_J_Head_s` | `cf_J_FaceRoot…`、`N_*` 挂点 |
| 脸 `fo_head` 的 prefab | `cf_J_Head_s` | 与头骨同名的骨**按名字合并** |
| 衣服 | 原点 | prefab 里带一份身体骨的拷贝，**按名字换成身体骨**，多出来的（裙摆等）保留 |
| 头发 | `N_hair_Root`（头骨） | 自带 `c_J_hair*` |
| 饰品 | 清单 `Parent` 列或卡里 `parentKey`（`N_Megane` 等） | 自带；卡里 `addMove`（位置、欧拉角、缩放）加在 `N_move` / `N_move2` 上，**位置单位是 0.1**（F_007 的鞭子 `(0,-14,4)` 按原值会偏 1.4 m） |

单位：Unity 10 单位 = 1 m（`cf_J_Hips` 在 y = 11.4）。

**蒙皮烘到静止姿势**：每个蒙皮网格顶点按 `Σ wᵢ · (Worldᵢ × BindPoseᵢ) · v` 算一次，`Worldᵢ` 取**目标骨架**
（衣服取身体骨）在 prefab 姿势下的世界矩阵——正是 Unity 在 prefab 姿势下画出来的位置。身体、脸大多
`World × BindPose = I`，但有的发型骨在 prefab 里不在绑定姿势（偏差到 0.22 单位），只能这样逐顶点算。
法线用线性部分的逆转置，形态键增量用线性部分。于是 Blender 里骨架静止姿势 = prefab 姿势，网格
直接对上，Armature 修改器零偏移。

**Unity → Blender**：`(x, y, z) → (-x, -z, y) × 0.1`，行列式 -1，三角形绕序反过来；角色面向 -Y。

**衣服的状态**：衣服 prefab 根上的 `CmpClothes`（MonoBehaviour，typetree 可读）里 `objTopDef` /
`objTopHalf`、`objBotDef` / `objBotHalf` 指向「穿好」和「半脱」两组物体，默认隐藏 Half 组
（`--state half` 反过来）；`defMainColor01..04` / `defGloss` / `defMetallic` 是没有卡时的默认色。

两个取 prefab 的坑：很多 prefab **根物体存成 inactive**（游戏 Instantiate 后才打开），根自己的
`m_IsActive` 要忽略，否则整件（如小丑鼻子）什么都不导；少数饰品用 Unity **内置网格**（`Sphere` 等，
PPtr 指向 `unity default resources`，path_id 10202–10210），包里没有，`hs2_bundle.builtin_mesh` 按
Unity 的尺寸程序化生成（球半径 0.5、圆柱高 2 …）。

不画的东西：`O_hit_*`（碰撞）、`o_silhouette*`、女体里的 `cm_o_dan*` / `o_tang`、超出子网格数量的
材质（湿身等叠加 pass）。

## 5. 材质

Illusion 的 shader 不在包里能直接用，按贴图通道和属性重建成 Principled BSDF。**所有颜色（材质
`_Color*`、卡里的颜色）都是 sRGB，填进 Blender 前转线性**——不转的话 0.33 的深灰会变成浅灰，整体发白。

| 部位 | 做法 |
|---|---|
| 衣服 / 饰品 | 分色遮罩 `*_mc` **不在 prefab 材质里**，是清单行 `ColorMaskTex`（`02`/`03` 对第二、三组）运行时塞进去的。遮罩语义：**黑 = 颜色 1、R = 颜色 2、G = 颜色 3、B = 颜色 4**（全黑遮罩 = 整件颜色 1），各自乘进灰色主贴图。颜色优先级：卡 `colorInfo` > `CmpClothes` 默认 > 材质 `_Color*` |
| 镜片 / 透明件 | Standard shader `_Mode ≥ 2`、无主贴图：颜色 4（带 alpha，卡里常是 0.1）→ 半透明玻璃 |
| 头发 | 主贴图 **R 恒为 1，G/B 是发丝细节，A 是透明度**，不带颜色。颜色 = 卡 baseColor，按渐变遮罩 G 混 topColor（发根）、B 混 underColor（发梢），乘 AO（`_Occlusion`），再按主贴图 G 轻微调亮暗 |
| 皮肤 | 主贴图就是有色皮肤（卡 `skinId` 换）；卡里肤色按与默认肤色 (0.78, 0.683, 0.624) 的线性比例相乘 |
| 眉毛 | 脸的 **UV1** 正好把眉区映到眉毛贴图（两侧镜像共用），叠加色 = 卡 `eyebrowColor` |
| 乳晕 | 身体 **UV1**（每侧乳头映到贴图中心），遮罩 **B**、明暗 R，色 = 卡 `nipColor` |
| 阴毛 | 身体 **UV2**，色 = 卡 `underhairColor` |
| 眼睛 | 眼球 UV0 以角膜为中心铺满贴图；眼白 × `whiteColor`，虹膜（遮罩 B、明暗 R、色 `pupilColor`）和瞳孔（alpha、色 `blackColor`）按卡里 `pupilW/H`、`blackW/H` 以中心缩放，高光按 `hlColor.a` 叠加 |
| 睫毛 | 纯色（卡 `eyelashesColor`），透明度 = 遮罩 |
| `o_eyeshadow` | 不是眼影妆，是眼睑投在眼球上的影子壳（`c_m_eyekage`）：暗色、贴图 alpha 做遮罩、60% |
| `o_namida`（泪） | 完全透明（保留物体与形态键） |

「发丝一类」的遮罩（眉毛、阴毛、睫毛、高光）打包方式不统一：有的黑底灰度、有的 RGB 全白 + alpha、
有的只在 B 通道（`c_t_eyebrow_17` 的 R 是 0.71 灰底）。统一取 **min(R, G, B) × A**，三种都对；
只读 R 会在整个 UV1 岛上盖一层眉毛色（脸上一块暗色矩形——实际踩到过）。

## 6. 验证

- 15 张角色卡穿好 / 裸、男女底模、31 类各第一件单独导出，全部 PASS，逐张看预览
  （正面、3/4、脸部特写）。
- 定位问题的办法：在 `.blend` 上逐个隐藏脸部物体重新渲染（眉毛矩形、眼睑影子白雾都是这样找到的）。

## 7. 限制

体型 / 脸型滑块未应用；衣服图案、脸部妆、晒痕、衣服下的身体遮罩未做；虹膜缩放公式是近似；
物理骨没有设置动态。
