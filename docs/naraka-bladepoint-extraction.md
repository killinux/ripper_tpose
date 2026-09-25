# NARAKA: BLADEPOINT（永劫无间）提取

2026-09-25。脚本在 `scripts/naraka/`，用法见那里的 README。这里记录「怎么做到的」和踩过的坑。

## 1. 资源在哪、长什么样

- 游戏：Unity 2019.4.41f2（bundle 头里写的是 2019.4.14f1），IL2CPP。
- `NarakaBladepoint_Data\StreamingAssets` 下 12818 个 bundle，文件名是哈希
  （`0/0/0001f46d2a9dbc1f`、`c/o/common_character_res`、`dlc/32e342eacb85413d` …），共 89 GB。
- `StreamingAssets\AppRes.info` 是 zip，里面唯一的成员 `data` 是清单。

### 1.1 bundle 格式：改过头的 UnityFS，没加密

和标准 UnityFS 逐项对比，只差四处：

| 项 | 标准 | NARAKA |
|---|---|---|
| 签名（8 字节） | `UnityFS\0` | `15 1E 1C 0D 0D 23 21 00` |
| 头部 `size` | 文件大小 | 文件大小 + 0x1E |
| 头部 blocks-info 压缩尺寸 | 精确值 | 比实际大 150 左右；未压缩尺寸字段恒为 0x1082，是垃圾值 |
| 压缩类型 | 2/3 = LZ4 | **6**，其实就是普通 LZ4 block |
| 布局 | blocks-info 后数据块紧挨着 | blocks-info 从 0x1000 开始，**每个数据块都对齐到 4 KB**，中间补零 |

所以解包是：读头 → 在 0x1000 处按「未知输出长度」解 LZ4，遇到补零（match offset = 0，非法）就停，
得到标准的 blocks-info（16 字节哈希、块表、节点表）→ 每个块先把文件位置对齐到 4 KB 再解。
12818 个 bundle 的目录全部能解析，解出来的 SerializedFile 是完全标准的，UnityPy 直接能读。

一个英雄 bundle 约 0.8 GB，公共包 `common_character_res` 1.7 GB，一个外观要拉上百个依赖 bundle。
所以 `naraka_bundle.open_lazy()` 返回可 seek 的流，只解压实际读到的块（每个 bundle 缓存 64 块），
UnityPy 的 `load_file` 接受这种流。

### 1.2 清单 `AppRes.info`

.NET BinaryWriter 格式（字符串 7-bit 长度前缀）。每个 bundle 一条：

```
u24     文件大小 >> 8
string  bundle 路径（相对 StreamingAssets）
i32 -1, i32 7
u16     资源数，后面这么多条资源路径（assets/res/...prefab / .fbx / .mat / .png）
u8, u16, u32 crc, string md5, string md5, u8      （固定 74 字节）
```

最后是按序号的依赖表，没解——每个 bundle 自己的 `AssetBundle` 对象里有 `m_Dependencies`
（bundle 路径），直接用它递归加载依赖。

## 2. 角色是怎么拼起来的

一个英雄在游戏里是几个 prefab 在运行时拼起来的：

| 部件 | 资源 |
|---|---|
| 骨架 | `actor_visual_part/ch_dummy_body/ch_f_dummy_body.prefab`（男 `ch_m_`） |
| 外观（身体 + 衣服） | `actor_visual_part/<家族>/<家族>_lv_<款>.prefab` |
| 配套发型 | `actor_visual_part/<家族>/<家族>_hair_lv_<款>.prefab` |
| 脸（脸、眼睛、睫毛） | `actor_visual_part/face/ch_f_face_battle.prefab` |

骨骼是 3ds Max Biped 命名（`MotionRoot/gMan Pelvis/gMan Spine/...`）。

### 2.1 外观网格：骨骼按「路径 CRC32」绑定

外观 prefab 里的 SkinnedMeshRenderer **没有骨骼引用**（`m_Bones` 为空）。Mesh 的
`m_BoneNameHashes` 是骨骼 transform 路径（相对角色根，例如
`MotionRoot/gMan Pelvis/gMan Spine/gMan Spine1/gMan Spine2`）的 CRC32。对骨架 prefab 的每个路径算
`zlib.crc32` 建表就能反查——身体 76 根骨全中。

骨架里没有的骨（胸、裙摆、飘带）作为「散装」子物体放在外观 prefab 里，游戏运行时把它们挂到骨架上。
它们的父骨通过哈希找：对每个骨架路径 P，看 `crc32(P + "/" + 名字)` 是否在网格要的哈希里
（`L_breast` → `.../gMan Spine2`，`L_skirt_01` → `gMan Pelvis`）。

### 2.2 发型和脸：运行时网格

发型、脸的 SkinnedMeshRenderer 连 `m_Mesh` 都是空的。同物体上的 `LXRendererAssistant`（MonoBehaviour）
的 `avatarMeshAsset` 指向一个 `AvatarFaceMeshData`：顶点（position/normal 的列表）、`m_UVData`
或 `m_HairUVSetData`、`m_Indices`、`m_BindPoses`、`m_AnimSkinData`（4 骨权重）。typetree 完整，
直接读就行。

- 脸的渲染器有 `m_Bones`（`gMan Head`、`gMan Neck`、`Face_L_Yanqiu` 眼球……），按对象引用解析；
  `Face_*` 骨挂在脸 prefab 自己的简化链（`MotionRoot/gMan Pelvis/gMan Neck/gMan Head`）下，拼的时候挂到
  真骨架的 `gMan Head` 下。
- 发型既没有骨骼名也没有哈希。办法：**bindpose 反推**。`renderer_world @ inverse(bindpose)` 就是这根骨的
  静止世界矩阵；对发型 prefab 的每棵散装子树，逐个尝试骨架里的父骨，看子树里有几根骨精确落在某个
  bindpose 上（误差 < 1e-3），取最多的那个（平局取路径最短的，避开 `HeadEnvCollider` 这种和头重合的节点）。
  结果：发辫挂 `gMan Spine2`（背后长发），耳坠挂 `gMan Head`。

  两个补充，都是抽样时碰到的：
  - **先比位置，再比整个矩阵。** 有的飘带/发带链在 prefab 里存的是「甩起来」的姿势：链根的位置在
    父骨下是对的，但旋转偏了，往下每一节误差累加（李寻欢脑后的 `M_belt_01`：根部位置误差 3×10⁻⁷，
    末端 15 cm）。所以先找「子树根的位置正好落在某个 bindpose 上」的父骨（局部偏移为 0 的节点除外，
    否则挂哪都对得上）；找不到再按整矩阵命中数，容差 1 mm → 1 cm → 5 cm 逐级放宽。
  - **散装骨可能挂在别的散装骨下**（耳坠挂在发辫上）。所以分三轮：前两轮只接受精确匹配，挂上的骨加入
    候选父骨，剩下的再试；最后一轮才放宽容差，还不行就挂根上。

  然后给每个 bindpose 认骨：**自上而下按位置匹配**。一根骨对上后，把它的静止姿势设成 bindpose
  （`rest ... rotated onto its bind pose`），它的子骨跟着归位，下一轮再对它们。这样上面那条发带链
  整条都能对上。最后还剩没对上的才按最近矩阵硬配，记为 `off by`，计入 `unresolved_bones`。

### 2.3 静止姿势 = 绑定姿势

每根骨的静止世界矩阵取 `renderer_world @ inverse(bindpose)`。实测：同一根骨在所有网格上的这个值完全
一致；和 `ch_f_dummy_body` 的 transform 差几微米（膝盖、脚差 2–3 cm——那是骨架 prefab 的站姿，不是绑定姿势）；
而 `art/characters/_common/avatar/base_model_female_165cm_skeleton.fbx` 差十几厘米，不能用。
没有任何网格用到的骨取骨架 prefab 的局部变换。这样所有顶点只要乘渲染器的世界矩阵就在静止姿势上，不用蒙皮运算。

### 2.4 LOD、特效、代理网格

`<名字>_L1/_L2/_L3` 是 LOD，根上的 `ActorBodyVisualCell.lod0RendererAssistants` 列出 LOD0 的渲染器
（`LXRendererAssistant._renderer`），只导它们。`fx_` 开头的是特效拖尾/光片网格，默认跳过（`--keep-fx`）。
被禁用的渲染器和没有材质的渲染器（`cloth01_sim` 这类布料模拟代理网格）也跳过。

### 2.5 发型的命名

配套发型不一定叫 `<家族>_hair_lv_<款>`：沈妙的在 `ch_f_ming_shenjiying` 目录里叫
`ch_f_shenmiao_hair_lv_*`，岳山的在 `ch_m_ming_guanningtieqi` 里叫 `ch_m_yueshan_hair_*`，还有
`ch_f_yinziping_hair_*`、`ch_f_fengzhao_hair_*`。所以家族目录里名字带 `_hair_lv_` 的都算这个家族的发型。
一开始按严格前缀认，沈妙、岳山、殷紫萍这几个家族的外观导出来全是光头。

### 2.6 怪物、NPC、武器

`full_body/*.prefab` 和英雄同一套机制：骨架在 `ch_dummy_body/<名字>_dummy_body.prefab`（逐级去掉 `_NN`
后缀找），找不到用 `art/characters/_common/avatar/<名字>_skeleton.fbx`，人形 NPC（`mo_m_`/`mo_f_`）
都没有就用英雄骨架。武器、道具自带层级，直接用 prefab 自己的 transform 当骨架。

## 3. 材质

着色器是自研的 `LX22/General/Charactor/*`，只能近似到 Principled BSDF：

| 贴图 | 含义 |
|---|---|
| `_MainTex` `*_d` | 颜色；A 是镂空（关键字 `_USE_CUTOUT`） |
| `_BumpMap` `*_n` | BC5 双通道法线，要补 B = √(1−R²−G²) |
| `_SpecGlossMap` `*_mrav` | R 金属度、G 粗糙度、B AO、A 其他 |
| `_NormalBentMap` `*_nx` | 皮肤的 bent normal，当普通法线用会满脸斑块——不用 |
| `_AdvIDTex` `*_mask`、`_EmissionMap` `*_em` | 分区遮罩、自发光（没用上） |

几个着色器实时合成的东西，导出时烘进贴图：

- **眼睛**：`_MainTex` 是眼白（眼球 UV 是以 (0.5, 0.5) 为中心的整圆），虹膜 `_IrisDiffuseTex` 是灰度图，
  在半径 `_IrisDail`（0.24）内按 `_IrisColor` 着色叠上去 → `*_eye_composite.png`。
- **眉毛**：脸材质的 `_EyeBrowDecalTex`（R = 覆盖度）按 `_EyeBrowDecalTransform = (u, v, 宽, 高)` 贴在脸 UV 上，
  再镜像到另一半（脸 UV 左右对称）→ `*_brows.png`。脸 UV 有负值，靠贴图平铺。
- **剔除**：通用着色器的参数叫 `_Culling`，特效类角色着色器叫 `_Cull`（Unity CullMode：0 不剔、1 剔正面、
  2 剔背面）。双层布料是同一份几何两套材质：`*_cb` 剔背面画外表面，`*_cf` 剔正面画里衬。两面都画会在同一
  位置互相穿插，所以按游戏来：剔背面的材质开 Blender 的背面剔除；剔正面的把三角形翻过来（法线取反）再开背面
  剔除，效果就是只看得到原来的背面。EEVEE 认这个设置，Cycles 不认。
- **头发**：`_MainTex` 不是颜色，是公用的发丝 ID 图（A = 发丝覆盖）；`_MainSHMap` 是均值 128 的有符号数据，
  也不是颜色（最初用它的平均色，所有人都成了银灰发）。真正的发色在
  `character/hair_custom_data/<发型>/hair_custom_data_01.asset` 的 `serializedCustomHairData[].BaseColorA`
  （染色系统的默认色）。拿 8 个游戏物品图标核对：黑发、红发（0.61, 0.05, 0.05）、金发都对得上。

## 4. 坑

- UnityPy 的 `Mesh` 类读这个游戏的网格会抛 `'UnknownObject' object has no attribute 'm_Colors'`，
  改为 `read_typetree()` 后自己解顶点流（`naraka_mesh.py`，2019 的 VertexFormat 编号）。
- `.fbx` 资源路径在 container 里对应多个对象（GameObject、Avatar、若干 Mesh），按类型取。
- 清单里 bundle 路径不全是 `x/y/<16位哈希>`，还有 `c/o/common_*_res`、`dlc/...`、多级哈希目录。
- Python 里往文件写 `b"\0"` 的替换字符串时被转成了真 NUL，模块导不进（`source code string cannot contain null bytes`）。
- 外观图标按物品 ID 命名，中文外观名在服务器物品表里，客户端没有 prefab ↔ 名字的映射；发型图标
  （`gui/art_source/icon_item/<发型 prefab 名>.png`）倒是按 prefab 名的。
- 一个进程导到底会越来越占内存：`naraka_env.Game` 留着打开过的每个 bundle（UnityPy 的文件对象 + 每个
  bundle 最多 64 个解压块的缓存），外观各有各的 bundle。所以 `batch_export.py` 按家族切成 12 套一批、每批一个
  进程，8 个并行；单进程是单线程，8 个并行时 CPU 只占 2 成左右，瓶颈不在 CPU。

## 5. 家族 ↔ 英雄

29 位英雄的代号取自 `gui/art_source/herocareerdata_img/bg_herospecialdata_<英雄>.png`（故事背景
`herostory_bg/img_storybg_<英雄>_N` 也是同一批）。英雄选择图标 `icon_hero_select/icon_hero_<X>_01` 里，
开服那 6 位用的是家族名（`haoxia`、`youseng`、`caoyuan`、`hanhaimomin`、`mangjianke`、`onmyoji`），其余用
英雄名。剩下对不上的，统计同时含英雄代号和家族名的资源路径，每对都有明显的主导项（`shenmiao` +
`shenjiying` 382 条，`yueshan` + `guanningtieqi` 216 条，`cuisanniang` + `haikou` 20 条……），结果写在
`naraka_catalog.FAMILY_HERO`，表见 `scripts/naraka/README.md`。

## 6. 没做的

英雄专属捏脸（`avatar_face_custom_*` 配置 + 脸骨偏移）和妆容、自发光、布料物理参数（`Cloth` 组件、
`BoneShakeDriver`）、动画。

「稀有」变色皮肤：`assets/design/rareskin/<外观>_rule.asset`（MonoBehaviour）按物品的 8 位编号分档
（`dimensionIdConfigs`：第 0–3 位 0–4999 / 5000–7999 / 8000–9499 / 9500–9999 对应品质 2–5），`ruleGroups`
（如「泡泡袖变色」）下每条规则（「区域R_颜色R」「区域R_透明度R」「区域R_金属度R」……）按编号区间给颜色 /
数值（起止两端插值）。材质用 `LX22/Effect/Character/Mutatable/*` 或各皮肤自己的 shadergraph
（`assets/1stparty/packageext/shadergraph/shaders/effect/character/mutatable/`，94 个），`_MainTex` 可以只存明暗
（`_SEPARATE_LUMINACE`），颜色按 `_MutateMaskTexture`（`_pm`）分区上。规则 ↔ 材质属性的对应要逐个读 shadergraph，
没做；这些外观导出的是底色。另有 `character/cloth_custom_data/<外观>/cloth_custom_data_NN.asset`（基础款 a0 / b0
等的染色预设），默认外观的颜色已在贴图里，也没用上。
