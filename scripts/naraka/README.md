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

## 已知限制

- 发色取发型 `hair_custom_data` 里的默认色（和游戏图标对得上），是平涂色加发丝明暗，不是游戏的各向异性头发着色。
- 脸是默认捏脸（`ch_f_face_battle` / `ch_m_face_battle`）+ 默认妆容；英雄各自的捏脸骨骼偏移和妆容没做。
- 眼睛虹膜、眉毛是按着色器参数烘进贴图的近似；自发光（`_EmissionMap`）、布料/丝绸的特殊着色没做。
- 部分人形 NPC（`mo_m_songbing_*` 等）自己不带脸，导出后是光头无五官。
- 「稀有」变色皮肤（`assets/design/rareskin/<外观>_rule.asset`，女性 11 套：宁红夜 s19、胡桃 s24、崔三娘 s18、
  迦南 s19、季莹莹 ss1、沈妙 s24、魏轻 ss1、顾清寒 ss1、殷紫萍 ss1、玉玲珑 ss1、jiantianshi s6）的颜色在游戏里由每件
  物品的 8 位编号按规则抽出（`Mutatable/*` 着色器，`_pm` 分区），导出的是没按编号上色的底色。
- 外观和发型是分开的物品，游戏里可以自由搭配；这里给外观配的是「同款」发型，想换用 `--hair`。

## 验证

2026-09-25：32 个家族各一套外观 + 石狼、金色狂战士、宋兵、太刀、双节棍、默认发型，共 40 个，
全部 `unresolved_bones` = 0，预览逐个看过。

同日全部女性外观（17 个家族 495 套）：`batch_export.py --sex f --out E:\game_export\NARAKA`，8 路并行
26 分钟，495 套全部成功，共 41 GB（每套平均约 85 MB，其中散装贴图约 25 GB）。单进程内存峰值 2.25 GB。只有
沈妙 `lv_s14` 的发型有 8 根骨按最近位置配上（偏 4.2–4.4 cm，预览里看不出）。按家族拼的缩略图总览
（`_list\overview\<家族>.jpg`）逐张看过：构图显得小的是宽袖 / 翅膀的横版预览，偏灰白的正好是上面那 11 套
稀有变色皮肤。
