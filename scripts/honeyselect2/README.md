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

## 已验证（2026-09-24）

15 张角色卡穿好 + 裸各一份、男女底模、31 个类别各一件单独导出，全部 PASS；逐张看过预览。

## 已知限制

- 体型滑块（`shapeValueBody/Face`）没应用：导出的是默认体型、脸型 prefab 的默认形状。
- 衣服图案（pattern）、脸部妆（腮红 / 口红 / 眼影 / 痣 / 彩绘）、晒痕、身体遮罩（被衣服盖住的身体部分
  不隐藏）没做；肤色按卡里颜色与默认肤色的比例乘上去，是近似。
- 虹膜 / 瞳孔大小由卡里滑块换算成 UV 缩放，是看图调出来的近似公式。
- 饰品卡里的位移（`addMove`）按「加在 `N_move` / `N_move2` 上、位置 × 0.1」处理。
- 物理骨（头发、裙摆、胸部 `cf_J_Mune*`）只作为普通骨骼导出，没有动态骨 / 刚体设置。
