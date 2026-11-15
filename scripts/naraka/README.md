# NARAKA: BLADEPOINT（永劫无间）模型列表与导出

网易 24 Entertainment 的 Unity 2019.4 游戏。资源在
`NarakaBladepoint_Data\StreamingAssets` 下约 1.3 万个以哈希命名的 AssetBundle 里（89 GB）。
bundle 改过文件头但没加密，脚本自己解包，只用 UnityPy + numpy + lz4（+ Blender 3.6 建 `.blend`），
不需要 AssetStudio、不需要进游戏。原理和各种坑见
[NARAKA 提取](../../docs/naraka-bladepoint-extraction.md)。

| 脚本 | 运行环境 | 作用 |
|---|---|---|
| `list_models.py` | Python 3 | 按清单列出可导出的模型（外观、发型、怪物/NPC、武器……），可筛选，可写 CSV / JSON / HTML 画廊；约 1 秒 |
| `export_model.py` | Python 3（UnityPy），调 Blender | 导出外观（自动配套发型 + 默认脸）/ 任意 prefab 为 `.blend`（+ 可选 FBX）和预览图 |
| `build_blend.py` | Blender 3.6 无头 | `export_model.py` 调用：`scene.json` → 骨架、蒙皮网格、材质、预览渲染 |
| `naraka_bundle.py` | 库 | 改版 UnityFS 解包（签名、LZ4 编号 6、4 KB 对齐、偏移过的头部尺寸）；按需解压的流 |
| `naraka_manifest.py` | 库 | `AppRes.info` 清单：bundle 文件 ↔ 资源路径（`assets/res/...prefab`） |
| `naraka_env.py` | 库 | UnityPy 环境：按资源路径加载 bundle 及其依赖 |
| `naraka_catalog.py` | 库 | 清单 → 分组（outfit / hair / full_body / weapon …），外观 ↔ 配套发型 |
| `naraka_mesh.py` | 库 | 直接从 typetree 解 Mesh 顶点流（UnityPy 的 Mesh 类在这个游戏上会报错） |
| `naraka_scene.py` | 库 | 把外观、发型、脸挂到同一套骨架上（路径 CRC32、bindpose 反推父骨），烘眼睛/眉毛，写 `scene.json` |
| `export_pmx_blender.py` | Blender 3.6 无头 | 存档里的 `.blend` → MMD 的 `.pmx`（眼部表情、视线、胸 / 裙 / 发 / 飘带物理），见「导出 PMX」 |

默认路径：游戏 `E:\SteamLibrary\steamapps\common\NARAKA BLADEPOINT`（改 `naraka_env.py` 或
`--game-data <StreamingAssets>`），导出 `D:\naraka_exports`（`--out` 或环境变量 `NARAKA_OUT`），
Blender `D:\Program Files\blender-3.6.15-windows-x64\blender.exe`（`--blender` 或 `BLENDER`）。

## 看有哪些模型

```bash
python list_models.py                           # 摘要：各组数量、32 个外观家族（对应 29 位英雄）
python list_models.py --group outfit            # 834 套外观
python list_models.py --hero 宁红夜 --group outfit  # 也可以 --hero ninghongye
python list_models.py --family ch_f_japan_yaodaoji
python list_models.py --search stonewolf
python list_models.py --group weapon --search katana
python list_models.py --exported --group outfit # 标出已导出的
python list_models.py --html                    # D:\naraka_exports\_list\index.html（已导出的显示预览图）
python list_models.py --all --csv D:\naraka_exports\_list\models.csv
```

| 组 | 内容 | 数量 |
|---|---|---|
| `outfit` | 英雄外观 `<家族>_lv_<款>` | 834 |
| `hair` | 外观配套发型 `*_hair_lv_<款>`（家族目录里） | 643 |
| `outfit_part` | 外观附件、国服/扩展变体 | 115 |
| `default_hair` | 默认发型 | 45 |
| `cosmetic` | 脸、眉、眼影、胡子 | 79 |
| `full_body` | 怪物、NPC 整体模型（去掉编号变体约 128 种） | 175 |
| `dummy_body` | 骨架/替身身体 | 118 |
| `other_body` | 其他角色部件（活动 NPC 等） | 43 |
| `weapon` | 武器（63 类；`chain_arrow` 里混有投射物/特效） | 1526 |

`_ui` 结尾的是大厅/界面用的副本，默认不列（`--ui` 加上）。

### 家族 = 英雄

游戏里有 29 位英雄（`gui/art_source/herocareerdata_img` 每人一张），每位英雄一个外观家族（另有
`ch_f/ch_m_luotihuaban` 和 `ch_m_taotie` 三个特殊家族）。开服那批英雄的家族按外观系列命名，其余的
就是英雄名；对应关系来自英雄选择图标（`icon_hero_<家族>_01`）和同时带两个名字的特效/材质路径
（如 `_fashion/cuisanniang/fx_ch_f_ming_haikou_lv_s26.anim`）：

| 家族 | 英雄 | 家族 | 英雄 |
|---|---|---|---|
| `ch_f_ming_mangjianke` | 宁红夜 | `ch_m_ming_haoxia` | 季沧海 |
| `ch_f_hanhaimomin` | 迦南 | `ch_m_ming_youseng` | 天海 |
| `ch_f_japan_onmyoji` | 胡桃 | `ch_m_hunni_caoyuan` | 特木尔 |
| `ch_f_ming_haikou` | 崔三娘 | `ch_m_ming_guanningtieqi` | 岳山 |
| `ch_f_ming_xiakenv` | 顾清寒 | `ch_m_japan_samurai` | 武田信忠 |
| `ch_f_ming_shenjiying` | 沈妙 | `ch_m_ming_wuchen` | 无尘 |
| `ch_f_japan_yaodaoji` | 妖刀姬 | `ch_m_ming_huwei` | 胡为 |
| `ch_f_ming_yinziping` | 殷紫萍 | `ch_m_ming_liulian` | 刘炼 |
| `ch_f_ming_yulinglong` | 玉玲珑 | `ch_m_hadi` | 哈迪 |
| `ch_f_ming_jiyingying` | 季莹莹 | `ch_m_lixunhuan` | 李寻欢 |
| `ch_f_ming_weiqing` | 魏轻 | `ch_m_zhangqiling` | 张起灵 |
| `ch_f_ming_fengzhao` | nangongjin | `ch_m_yexiu` | 叶修 |
| `ch_f_jiantianshi` | ganxuan | `ch_m_wanjun` | wanjun |
| `ch_f_lanmeng` / `ch_f_xila` / `ch_f_ming_wuzhen` | lanmeng / xila / wuzhen | | |

只写了拼音的是没能确认汉字的。中文外观名（「XX·某某」）在服务器下发的物品表里，客户端没有 prefab ↔
名字的映射，所以列表只能用代号。

## 导出

```bash
python export_model.py --outfit ch_f_ming_haikou_lv_s0              # 崔三娘：外观 + 配套发型 + 默认女脸
python export_model.py --outfit ch_f_ming_haikou_lv_s0 --hair ch_f_hair_05
python export_model.py --outfit ch_m_ming_haoxia_lv_s1 --no-hair --no-face
python export_model.py --family ch_f_japan_yaodaoji                  # 一个家族的全部外观
python export_model.py --all-outfits --sex f                         # 全部女性外观（几小时）
python export_model.py --prefab mo_pve_a_bigstonewolf_01             # 怪物 / NPC / 武器，名字或资源路径
python export_model.py --group full_body --limit 20
```

通用选项：`--fbx`（同时写 FBX，贴图内嵌）、`--keep-fx`（保留 `fx_` 特效网格：拖尾、光片）、
`--no-preview`、`--no-blend`（只写 `scene.json` + 部件 + 贴图）、`--force`（已有也重做）、`--ui`。

产物：

```
D:\naraka_exports\
  outfits\<外观>\<外观>.blend  _preview.png _side.png _back.png _face.png
                 scene.json  parts\*.npz  textures\*.png  export.json  build.log
  items\<prefab>\...          怪物、NPC、武器、单独的发型
  _list\index.html            画廊（每次 export_model.py 结束自动重建）
```

配发型的顺序：同款（`*_hair_lv_s0`）→ 款号去掉后缀（`s0_02` → `s0`）→ 家族基础款 `b0` → 家族第一款 →
默认发型 `ch_f_hair_02` / `ch_m_hair_02`；实际选了哪个会打印出来（`hair: ... (family b0)`），也写进
`export.json`。834 套外观里 398 套同款、191 套去后缀、240 套 `b0`、3 套家族第一款、2 套默认。

第一次加载一个外观要 30–40 秒（它依赖的公共 bundle 有上百个，按需解压），同一进程里后面的每个
10–25 秒（公共部分已在内存，只解它自己的网格和贴图），所以批量导出一次跑完比逐个调用快得多。
`export.json` 里的 `unresolved_bones` 应为 0。

### 并行批量导出

```bash
python batch_export.py --sex f --out E:\game_export\NARAKA          # 全部女性外观（495 套）
python batch_export.py --out E:\game_export\NARAKA                  # 全部 834 套
python batch_export.py --family ch_f_ming_haikou --jobs 4
python batch_export.py --sex f --out E:\game_export\NARAKA --dry-run    # 只看怎么分批
```

按家族切成每批不超过 12 套（`--chunk`），每批一个 `export_model.py` 进程，同时跑 `--jobs` 个（默认 8）。
不让一个进程导到底，是因为进程会留着打开过的全部 bundle，内存随导出数量涨；12 套一批峰值约 2.2 GB。
空闲内存低于 `--reserve`（默认 6 GB）时不开新批。已有 `.blend` 的跳过，中途断了原样再跑一次即可；
失败的在最后各用一个新进程重试一次。日志在 `<out>\_logs\<家族>_<n>.log`，汇总在
`<out>\_logs\batch_summary.json`（每套的状态、耗时、未解析骨数），列表页 `<out>\_list\index.html`
在全部结束后写一次（各批进程带 `--no-html`，免得同时写一个文件）。`--fbx`、`--no-preview`、`--keep-fx`、
`--force` 原样传给 `export_model.py`。

## 导出 PMX（MMD，2026-10-31 起，样品：宁红夜默认外观）

```powershell
& "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" -b `
  E:\game_export\NARAKA\宁红夜\blend\ch_f_ming_mangjianke_lv_a0\ch_f_ming_mangjianke_lv_a0.blend `
  --factory-startup --python scripts\naraka\export_pmx_blender.py -- `
  --out E:\game_export\NARAKA\宁红夜\pmx --model-name 宁红夜_lv_a0
```

写出 `<out>\<外观>\<外观>.pmx` + `textures\` + `<外观>.report.json`（每一步做了什么）+ `<外观>_converted.blend`
（转换后的场景）。`--model-name` 是 MMD 里显示的名字，`--comment` 是模型备注。要加 `--factory-startup`：
不加的话 Blender 会按偏好设置载入布料插件的开发版，物理结果跟着别的窗口的改动变。看效果：

```powershell
# 正面、眼部表情、视线、跳舞 4 帧 -> PMX 旁边的 preview*.png
blender -b --factory-startup --python scripts\stellarblade\preview_pmx_blender.py -- --pmx <PMX> --vmd <VMD> `
  --morphs まばたき 笑い ウィンク ウィンク右 ウィンク２ びっくり じと目 はぅ
# 跳舞视频（MMD 式物理）
blender -b --factory-startup --python scripts\riseoferos\render_pmx_dance.py -- <PMX> <VMD> <WAV> <out.mp4> 0 full mmd
```

**做法**：和 TFD、星刃同一条链（`scripts/stellarblade/export_pmx_blender.py` → ROE 的
`export_character_model_blender.py`：Convert_to_MMD5 建 MMD 骨架和身体碰撞体，mmd_cloth_physics 给头发、裙摆、
飘带做物理，blender2xps 把节点算出来的颜色烘成一张贴图，mmd_tools 按 12.5 倍写 PMX）。NARAKA 的不同之处：

- **骨名**：3ds Max Biped，前缀 `gMan `，挂在 Unity 的 `MotionRoot` 下。改成 `Bip001 ` / `Bip001` 后，
  ROE 的骨骼对照直接能用。
- **游戏运行用的节点**：受击 / 环境碰撞体、武器 / 瞄准 / 镜头 / 锁定挂点、`body_dummy`、`UpAnchor` 都不带蒙皮，
  连同下面没蒙皮的子骨一起删掉（宁红夜删了 34 根）。
- **眼睛**：`Face_L_Yanqiu` / `Face_R_Yanqiu` → 左目 / 右目 + 両目；它们的父骨 `Face_*_YanZ`（空挂点）去掉。
- **胸**：`L_breast` / `R_breast` → 左胸 / 右胸 + 胸部物理（和星刃 Eve 一样的球形刚体）。
- **表情**：所有女英雄共用的战斗脸（`ch_f_face_battle`）没有形态键，也没有嘴和眉毛的骨骼，只有上、下眼皮骨
  （`Face_*_Shangyanpi01` / `Face_*_Xiayanpi`，转轴都在眼球中心）。脚本先量出睁眼时上下眼睑边缘的夹角
  （宁红夜 35.5°），按比例转眼皮骨，存成 ARKit 名字的形态键（`eyeBlink` / `eyeWide` / `eyeSquint`，左右各一），
  再用星刃的配方混出 9 个 MMD 眼部表情：まばたき、笑い、ウィンク、ウィンク右、ウィンク２、ｳｨﾝｸ２右、びっくり、
  じと目、はぅ。闭眼时上眼皮走 3/4、下眼皮走 1/4，再多 0.5° 合严。睫毛跟着眼皮动，先并进脸的网格。
  笑い / ウィンク / はぅ 里的「眯眼」成分比星刃少：眼皮只能绕一根轴转，混多了上下眼皮会互相穿过去。
- **骨链保住**：Convert_to_MMD5 会把「挂在脊柱上、在中线上、名字不像布料或头发」的骨当成脊柱中段并掉。
  NARAKA 的链多用拼音命名（`belt_`、`piaodai_`（飘带）、`daizi_`（带子）、`M_ribbon_` ……，495 套女性外观里都有）。
  宁红夜腰前的带子 `belt_01-04` 第一次导出时就这样并进了上半身，没了物理。脚本里改成：链上的骨（有子骨，
  或父骨不是标准骨）一律保留。
- **睫毛染黑**：游戏的睫毛着色器（`LX22_Standard_Charactor_Eyelash`）用 `_EyelashColorL` / `_R`（战斗脸是纯黑，
  捏脸里可以改）给睫毛上色。哪里算睫毛，由 `_SpecGlossMap`（mrav）的红通道标出，而 `_MainTex` 里的睫毛丝本身是纯白的。
  存档的 `.blend` 直接拿 `_MainTex` 当颜色，所以上下睫毛都是白的。导出前按红通道把 `scene.json` 里的睫毛颜色混进去，
  再烘焙；睫毛下面那圈眼窝阴影（红通道约 0.08）保持原色。对比图 `睫毛修复对比.jpg` 放在 PMX 旁边。
- **共用一个材质的网格先合并再烘焙**：星刃脚本的 `bake_node_colours` 只按第一个用到该材质的网格烘
  （blender2xps 一次只烘一个物体的 UV 岛），其余网格在那张贴图上采到的是空白。胡桃 lv_a0 的百褶裙
  （`body02_1` 和 `cloth01` 共用一个材质）因此整条看不见；迦南 lv_a0 的腰布和披布（3 个网格共用一个材质）
  在填满 alpha 后变成纯黑。现在烘焙前，把没有形态键、又共用材质的网格合并成一个（PMX 本来就是一整个网格）。
  报告里新增 `opaque_holes`：不透明材质上贴图 alpha < 0.5 的三角形占比，在填 alpha 之前量；不为空就是烘空了。
- **跨格的 UV 先挪回 0–1**：烘焙只填 0–1 那一格。胡桃的头皮 UV 在 v 1.13–1.93，烘出来全透明，被当成空壳隐藏；
  宁红夜的外套有 6,014 个面在格子外面。贴图是重复平铺的，所以烘焙前把 UV 中心不在 0–1 的面整格平移回来，
  颜色不变（报告 `uv_tiles_wrapped`）。
- **不透明材质的贴图 alpha 填满**：MMD 会把贴图的 alpha 乘进材质。游戏贴图的 alpha 常放遮罩（高光、SSS），
  原样写出的话，PMX 在 MMD 里会半透明，而 Blender 的预览看不出来。导出后，凡是只给不透明材质
  （原 `.blend` 里 `OPAQUE`）用的贴图，alpha 一律填成 1，颜色不动；头发、睫毛、头皮这些本来就透明的不碰。
  宁红夜填了 5 张：外套接缝处原有 0.2% 的采样点 alpha 为 0，身体和脸是 254。

**样品**（`E:\game_export\NARAKA\宁红夜\pmx\ch_f_ming_mangjianke_lv_a0\`，32 MB）：
- 导出约 3 分钟；26,931 顶点、179 骨，9 个 MMD 眼部表情 + 6 个 ARKit 眼部形态键；
- 62 刚体 / 44 关节：裙摆 6 条、腰前带子、头发 3 条（马尾 10 节）、胸；
- 撕裂 0、零权重洞 0、没有权重被转给不相干的骨，付与顺序检查通过；
- 预览：正面、9 个表情、视线 5 个方向都对；
- 手势舞视频（MMD 式物理，11.2 s）每秒 2 帧看过，没有撕裂，物理没有炸开。

**另外两个样品**（10-31 晚，用户点名）：都是默认外观，各带预览图和手势舞视频，撕裂 0、零权重洞 0、不透明材质无烘空。
- 胡桃 `E:\game_export\NARAKA\胡桃\pmx\ch_f_japan_onmyoji_lv_a0\`：42 刚体 / 24 关节，长袖摆 2 条、头发 3 条、胸。
  百褶裙没有骨链，靠蒙皮跟着腿动。游戏把袖摆骨的左右名字起反了（`R_sleeve_*` 挂在左臂上），层级本身没错，物理照常。
- 迦南 `E:\game_export\NARAKA\迦南\pmx\ch_f_hanhaimomin_lv_a0\`：26 刚体 / 10 关节，头发 1 条（8 节）、胸。
  腰布和吊坠没有骨链，靠蒙皮跟着动。

## 已知限制

- 发色取发型 `hair_custom_data` 里的默认色（和游戏图标对得上），是平涂色加发丝明暗，不是游戏的各向异性头发着色。
- 脸是默认捏脸（`ch_f_face_battle` / `ch_m_face_battle`）+ 默认妆容；英雄各自的捏脸骨骼偏移和妆容没做。
- 眼睛虹膜、眉毛是按着色器参数烘进贴图的近似；自发光（`_EmissionMap`）、布料/丝绸的特殊着色没做。
- 部分人形 NPC（`mo_m_songbing_*` 等）自己不带脸，导出后是光头无五官。
- 「稀有」变色皮肤（`assets/design/rareskin/<外观>_rule.asset`，女性 11 套：宁红夜 s19、胡桃 s24、崔三娘 s18、
  迦南 s19、季莹莹 ss1、沈妙 s24、魏轻 ss1、顾清寒 ss1、殷紫萍 ss1、玉玲珑 ss1、jiantianshi s6）的颜色在游戏里由每件
  物品的 8 位编号按规则抽出（`Mutatable/*` 着色器，`_pm` 分区），导出的是没按编号上色的底色。
- 外观和发型是分开的物品，游戏里可以自由搭配；这里给外观配的是「同款」发型，想换用 `--hair`。
- **PMX**：
  - 没有口型和眉毛表情，因为战斗脸本来就没有这些骨骼和形态键；
  - 站着不动时，腰前带子的结会往下坠约 5 cm（链根是动态的）；
  - 在 Blender 里打方向光时，外套上有零星小白点：这是 MMD 材质的高光，TFD、星刃转出来的也有；
  - 金属和丝绸看着更平、更暗：迦南的银色袖套成了深灰，金饰成了浅黄。MMD 材质没有金属和光泽，
    烘出来的只是底色（以后可以用 sphere 贴图补，属于待做清单第 2 项）；
  - 目前只做了宁红夜一套样品，其余 494 套等用户看过样品再批量。
- 存档里 495 套 `.blend` 的睫毛都是白的（`build_blend.py` 没用睫毛着色器的颜色参数）；PMX 导出时已经修正，
  `.blend` 本身还没改。

## 验证

2026-09-25：32 个家族各一套外观 + 石狼、金色狂战士、宋兵、太刀、双节棍、默认发型，共 40 个，
全部 `unresolved_bones` = 0，预览逐个看过。

同日全部女性外观（17 个家族 495 套）：`batch_export.py --sex f --out E:\game_export\NARAKA`，8 路并行
26 分钟，495 套全部成功，共 41 GB（每套平均约 85 MB，其中散装贴图约 25 GB）。单进程内存峰值 2.25 GB。只有
沈妙 `lv_s14` 的发型有 8 根骨按最近位置配上（偏 4.2–4.4 cm，预览里看不出）。按家族拼的缩略图总览
（`_list\overview\<家族>.jpg`）逐张看过：构图显得小的是宽袖 / 翅膀的横版预览，偏灰白的正好是上面那 11 套
稀有变色皮肤。
