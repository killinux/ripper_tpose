# HoneySelect 2 (Libido DX) 模型列表与导出

Illusion 的 Unity 游戏，资源在 `abdata\` 下的 `.unity3d` AssetBundle 里（不加密）。脚本只用
UnityPy + numpy（+ Blender 3.6 建 `.blend`），不需要 AssetStudio、不需要进游戏。原理、各贴图
通道含义、拼装规则见 [HoneySelect 2 提取](../../docs/honey-select-2-extraction.md)。

| 脚本 | 运行环境 | 作用 |
|---|---|---|
| `list_models.py` | Python 3（UnityPy） | 列出底模、全部带网格的物品（按类别）、`UserData\chara` 里的角色卡；可筛选，可写 JSON / CSV / 带游戏缩略图的 HTML |
| `export_model.py` | Python 3（UnityPy），调 Blender | 导出单个物品 / 底模 / 整张角色卡（穿好或裸）为 `.blend`（+ 可选 FBX）和预览图 |
| `build_blend.py` | Blender 3.6 无头 | `export_model.py` 调用：`scene.json` → 骨架、蒙皮网格、形态键、材质 |
| `hs2_data.py` | 库 | 物品清单（`list\characustom\*.unity3d` 里 MessagePack 的 `ChaListData`）、依赖清单、角色卡解析 |
| `hs2_bundle.py` | 库 | 从 bundle 取 prefab，按游戏规则挂到同一套骨架上，蒙皮烘到静止姿势 |
| `hs2_msgpack.py` | 库 | 最小 MessagePack 解码器（免装 msgpack） |
| `html/make_gallery.py` | Python 3（Pillow） | 汇总已导出的 `.blend` 与预览，生成画廊 `html/index.html`（缩略图写在 `D:\hs2_exports\_gallery\thumbs`） |

游戏目录默认 `E:\SteamLibrary\steamapps\common\HoneySelect2Libido DX`（`--game` 或环境变量
`HS2_ROOT` 改），导出根目录默认 `D:\hs2_exports`（`--out` 改），Blender 默认
`D:\Program Files\blender-3.6.15-windows-x64\blender.exe`（`--blender` 或 `BLENDER` 改）。

## 看有哪些模型

```bash
python list_models.py                          # 摘要：底模、31 个类别各多少件、15 张角色卡
python list_models.py --category fo_top        # 某一类的每一件（list key 或类别号 240）
python list_models.py --group hair --search 马尾
python list_models.py --cards                  # 每张卡穿戴了哪些物品
python list_models.py --exported               # 标出已经导出过的
python list_models.py --html                   # D:\hs2_exports\_list\index.html，812 张游戏缩略图 + 搜索框
python list_models.py --all --csv D:\hs2_exports\_list\models.csv
```

第一列的引用（`fo_top:28`、`so_hair_b:9`、`ao_glasses:0` …）就是 `export_model.py --item` 的参数。

| 组 | 类别（list key） |
|---|---|
| 脸型 | `fo_head` 女 4、`mo_head` 男 1 |
| 衣服 | 女 `fo_top` `fo_bot` `fo_inner_t` `fo_inner_b` `fo_gloves` `fo_panst` `fo_socks` `fo_shoes`；男 `mo_top` `mo_bot` `mo_gloves` `mo_shoes` |
| 头发 | `so_hair_b` 后发、`so_hair_f` 前发、`so_hair_s` 侧发、`so_hair_o` 附加发 |
| 饰品 | `ao_head` `ao_ear` `ao_glasses` `ao_face` `ao_neck` `ao_shoulder` `ao_chest` `ao_waist` `ao_back` `ao_arm` `ao_hand` `ao_leg` `ao_kokan` |

## 导出

```bash
python export_model.py --card HS2_ill_F_000              # 角色卡，穿好（卡名可省 .png，也可给完整路径）
python export_model.py --card HS2_ill_F_000 --nude       # 同一个人不穿衣服、不戴饰品（--keep-accessories 保留饰品）
python export_model.py --all-cards [--nude]              # UserData\chara 下全部角色卡
python export_model.py --body female                     # 裸底模 + 默认脸（--head 选脸型）
python export_model.py --item fo_top:28 --item so_hair_b:9   # 单件，自带骨骼
python export_model.py --item fo_top:28 --with-body          # 单件穿在默认底模上
python export_model.py --all-items --group hair              # 批量：一整组 / --category 一整类
```

通用选项：`--fbx`（同时写 FBX）、`--no-preview`、`--no-blend`（只写 `scene.json` + 部件 + 贴图）、
`--state half`（衣服用「半脱」状态）、`--force`（已有也重做）。

产物：

```
D:\hs2_exports\
  cards\<卡名>[_nude]\<卡名>.blend  _preview.png  _side.png  _face.png  scene.json  parts\  textures\  build.log
  bodies\body_female\...
  items\<list key>\<key>_<id>_<prefab>[_with_body]\...
  _list\index.html  thumbs\          (list_models.py --html)
  _cache\lists.json                  (清单缓存，按清单包大小/时间自动失效)
  _exports.jsonl                     (每次导出一行：PASS / WARN / FAIL)
```

`.blend` 内：一个骨架（`cf_J_*` 游戏骨名，米制，Z 朝上、角色面向 -Y）、每个部件一个网格物体（顶点组 =
骨名、Armature 修改器；脸、睫毛、泪、牙、舌带游戏里的形态键，如 `eye_face.f00_def_cl`）、贴图打包在
文件里。

## 画廊

```bash
python html\make_gallery.py        # 每批导出后重跑；打开 scripts\honeyselect2\html\index.html
```

按「角色卡·穿好 / 角色卡·裸 / 底模 / 单件」分类、可搜索，卡片上有正面 / 3/4 / 脸部预览、组成物品、
规格和 `.blend` 链接。

## 转 PMX（`export_pmx_blender.py`，2026-10-31，样品 Akina Obata）

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' -b --factory-startup `
  "E:\game_export\HoneySelect2\Akina Obata\blend\HS2_ill_F_000\HS2_ill_F_000.blend" `
  --python scripts\honeyselect2\export_pmx_blender.py -- `
  --out "E:\game_export\HoneySelect2\Akina Obata\pmx" --name HS2_ill_F_000 --model-name "Akina Obata"
```

走的是剑星 / ROE 那条转换链（Convert_to_MMD5 建 MMD 骨架、身体碰撞体和捩骨，mmd_cloth_physics 加头发物理，
blender2xps 把节点算出来的颜色烘成一张贴图，mmd_tools 按 12.5 写 PMX）。Illusion 的骨架不是 Biped，这个脚本先做这些：

- **骨骼对照**：`cf_J_Hips` = 全ての親的来源、`cf_J_Kosi01` = 下半身、`cf_J_Spine01..03` = 上半身 / 上半身2 / 上半身3、
  `cf_J_Neck` / `cf_J_Head`、`cf_J_Shoulder` / `ArmUp00` / `ArmLow01` / `Hand`、`cf_J_LegUp00` / `LegLow01` / `Foot01` / `Toes01`、
  手指 `Thumb` / `Index` / `Middle` / `Ring` / `Little` 01–03、`cf_J_eye_rs` = 眼睛（带着眼球）、`cf_J_Mune00` = 胸。`_L` 是角色自己的左边。
- **辅助骨的蒙皮并回主关节**：Illusion 的主关节本身不带蒙皮，身体蒙在游戏脚本驱动的缩放 / 阻尼辅助骨上
  （`cf_J_ArmUp01_s`、`cf_J_LegUp02_s`、`cf_J_Spine02_s`、`cf_J_Mune02_s`、`cf_J_Siri_s` …）。这些权重并到上面的槽位骨；
  手臂再由 Convert_to_MMD5 自己的捩骨分配把 腕 / ひじ 分到 腕捩 / 手捩。膝盖、手肘的垫骨（`cf_J_LegKnee_*`、`cf_J_ArmElbo*`）
  保留，交给 ROE 的辅助骨规划按位置分到关节的一半左右（0.50–0.54）。脸部骨骼并到 頭（表情用游戏的形态键），
  胸部的子骨并到 `cf_J_Mune00`，饰品骨并到上面的骨；没有蒙皮的骨骼删掉（353 → 73 根，转换后 179 根）。
- **头发**：头皮骨（`c_J_hair*_top`）并到 頭；每束头发在游戏里只挂一根骨（DynamicBone 晃它），物理插件至少要两节，
  所以按这束头发蒙皮的范围拆成一条链（每节约 6 cm，最多 6 节，权重在相邻两节之间线性过渡）。
- **烘焙前的两处修正**：头发、眼镜的 UV 是平铺的（−2.99 … 1.07），烘焙只填 0–1 的范围，结果是空的，被当成全透明藏掉了；
  所以先把第一层 UV 的每个面按整格平移回 0–1（贴图是重复的，采到的颜色不变），PMX 保留平移后的 UV。
  睫毛的透明度在角色卡 .blend 里是 min(R, G, B) × A，可它的遮罩只有红色通道，结果全透明（Blender 预览里睫毛其实也没有）；
  这种遮罩的 MINIMUM 节点改成 MAXIMUM。
- **表情**：游戏的形态键在头、睫毛、泪膜上同名（`e*` 眼、`g*` 眉、`k*` 嘴），`RECIPES` 在每个带这些键的网格上
  混出同名的 MMD 表情（29 个：まばたき、笑い、ウィンク 两种、びっくり、じと目、はぅ、なごみ、眉毛 6 个、あいうえお、
  にっこり、にやり、∧、口角、口横広げ、ワ、ぺろっ），游戏原来的形态键也一起导出（「その他」）。
  牙齿和舌头只有张嘴的三档（`k01_open0` / `k02_open1` / `k03_open2`），每个嘴型按它自己下巴下降多少去开牙齿和舌头
  （游戏里头部 `k09_open1` 配牙齿 `k02_open1`，下降比约 1.12）。
- **贴图透明度**（`scripts/pmx_tools/texture_alpha_blender.py`）：只被不透明材质用的贴图透明度补成 1。

样品（`E:\game_export\HoneySelect2\Akina Obata\pmx\HS2_ill_F_000\`）：`HS2_ill_F_000.pmx`、`textures\`、`表情一览.jpg`、
`Akina_Obata_手势舞.mp4`、`_converted.blend`、`_report.json`。其余卡（穿衣 / 裸体各一）等用户看过样品再做。

## 已验证（2026-09-24）

15 张角色卡穿好 + 裸各一份、男女底模、31 个类别各一件单独导出，全部 PASS；逐张看过预览。

## 已知限制

- 体型滑块（`shapeValueBody/Face`）没应用：导出的是默认体型、脸型 prefab 的默认形状。
- 衣服图案（pattern）、脸部妆（腮红 / 口红 / 眼影 / 痣 / 彩绘）、晒痕、身体遮罩（被衣服盖住的身体部分
  不隐藏）没做；肤色按卡里颜色与默认肤色的比例乘上去，是近似。
- 虹膜 / 瞳孔大小由卡里滑块换算成 UV 缩放，是看图调出来的近似公式。
- 饰品卡里的位移（`addMove`）按「加在 `N_move` / `N_move2` 上、位置 × 0.1」处理。
- 物理骨（头发、裙摆、胸部 `cf_J_Mune*`）只作为普通骨骼导出，没有动态骨 / 刚体设置。
