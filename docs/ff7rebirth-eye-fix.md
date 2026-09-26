# FF7 Rebirth：眼睛「大黑瞳」和借用材质的修复（2026-09-26）

用户对比 Remake 和 Rebirth 的 Tifa，觉得眼睛不对。查下来是 Rebirth 整条导出线的问题，
另外顺带查出 3 个模型的材质是按文件名猜的。本文记录怎么查、怎么修、怎么验证。

## 0. 结论

| 问题 | 影响 | 修法 |
|---|---|---|
| 虹膜贴图没按游戏的方式缩放：瞳孔几乎占满虹膜，只剩一圈细边 | Rebirth 所有用「眼白 + 虹膜」拼法的模型：E 盘归档 98 个里的 70 个（含 Tifa #817 的 8 个 mod） | 虹膜贴图单独一套 UV：以 (0.5, 0.5) 为中心放大 2 倍；虹膜/眼白分界改为 UV 半径 0.225–0.25 |
| Vincent 的眼睛材质叫 `PC0011_00_EyeL` / `EyeR`，没被认成眼睛 | 虹膜贴图铺满整个眼球（整颗红眼球） | `is_eye_material_name` 认 `eyel` / `eyer`；从游戏重建这两个材质 |
| 模型借用别的角色目录里的材质实例，导出时没有它们的材质表，贴图靠文件名猜 | PC0000_17 Cloud（Loveless 无面具）全灰；PC0010_10 Sephiroth 变身形态头发变黑、眼睛挂着翅膀的透明贴图、没有虹膜 | `ff7rb_rematerialize.py` 从游戏找到材质实例、重建材质表、导出贴图，用原来的材质构建函数重做 |

Remake 没有这个问题（它的眼睛贴图本身就是整只眼睛，见下）。

## 1. 怎么发现的

同一套相机/灯光给两边的眼睛拍特写（`scripts/final/render_eye_closeup.py`，模型自己的灯全关、只用一盏太阳光，
所以不同模型、修前修后可以直接对比）：

- PMX 的视线检查图 `preview_gaze.png`：Remake #1707 是红棕色、有纹理的虹膜；Rebirth #817 只剩黑点。
- 回到 Blender 原始 `.blend` 也一样 → 不是 PMX 转换的问题，是 Rebirth 的材质。
- Aerith 同样（绿色细环 + 大黑瞳）→ 整条 Rebirth 线的问题，不是 Tifa 或 mod 特有。

## 2. Rebirth 的眼睛是怎么做的

用 CUE4Parse CLI 读游戏里的材质实例（`-f json`，沿 Parent 链到基础材质）：

```
PC0002_00_Eye (MaterialInstanceConstant)
  Color          = /Game/Character/Common/Eye/Texture/Common_Eye_Player_C    眼白（眼球 UV）
  Normal         = Common_Eye_Player_NO
  ScrelaNormal   = Common_Eye_Player_NI
  GazeNormal     = Common_Eye_Player_NG
  IrisColor      = /Game/Character/Player/PC0002_00_Tifa_Standard/Texture/PC0002_00_Eye_C
  IrisNormal     = Common_Eye_Player_N
  IrisOcclusion  = Common_Eye_Player_O
→ RMI_Surface_Eye_Migration   静态开关 Eye_ / EyeMigration_ / Coordinate0_ / IrisColor_ ... 全开
→ RM_Surface (Material)       没有任何标量参数（没有 IrisUVRadius、PupilScale 之类）
```

- `IrisColor` / `IrisNormal` / `IrisOcclusion` 三张都是**只有虹膜**的图：瞳孔在正中，虹膜纤维铺满整张。
- 眼球网格只有一套有效 UV（`VTXW0000`；`EXTRAUV0` 不是虹膜 UV，`EXTRAUV1` 是常数 (0, 1)），
  和眼白共用。所以虹膜的缩放只能写在着色器里（静态开关路径，没有参数）。
- **Remake 的 `PC0002_00_Eye_C` 同名但内容不同**：一张完整的眼睛（眼白 + 虹膜 + 瞳孔），按原 UV 直接贴就对。
  `EyeMigration`（从 Remake 迁移）+ 两边眼球 UV 布局完全一致（`EXTRAUV0` 拟合系数相同；几何上角膜凸起都在
  UV 半径约 0.22 结束：dist/R 在 0.20 处 1.006、0.24 处 0.986，两边一样）→ Rebirth 的虹膜应当落在 Remake 同样的位置。

倍数是量出来的：以贴图中心为圆心，每 0.01 半径一圈取平均亮度（和红减蓝），看亮度在哪一圈跳变
（`render_eye_closeup.py --dump-textures` 能把眼睛用到的贴图连打包的一起写出来；Rebirth 的虹膜/遮罩贴图也可以用
CLI 直接导：`cue4parse.exe -i <游戏> -g GAME_FinalFantasy7Rebirth -m <usmap> -o <目录> -p End/Content/Character/Common/Eye/Texture/Common_Eye_Player_O.uasset`）：

| | 瞳孔边缘 | 虹膜外缘 |
|---|---|---|
| Remake 完整眼睛（眼球 UV） | 0.068 | 0.245（之后是眼白） |
| Rebirth 虹膜贴图（虹膜 UV） | 0.135 | 0.5（贴图边缘） |

0.135 / 0.068 ≈ 2.0，0.5 / 2 = 0.25 ≈ 0.245，两个数对上 → 虹膜 UV = (眼球 UV − 0.5) × 2 + 0.5。
旧代码用原 UV 采虹膜贴图，眼球中心半径 0.2 的圆里只取到贴图中心，正好是瞳孔，所以虹膜区几乎全黑。

## 3. 改了什么

- `scripts/final/ff7rebirth_tools.py`
  - `EYE_IRIS_UV_SCALE = 2.0`，`EYE_IRIS_INNER_RADIUS / OUTER = 0.225 / 0.25`（原来 0.18 / 0.22）。
  - `connect_eye_base()` 给虹膜贴图加一个 Mapping 节点 `FF7RB_EyeIrisUV`（缩放 2、位移 −0.5），贴图边缘用 EXTEND。
  - `repair_eye_iris_uv(material)`：给已经生成过的旧节点图补上这个节点（幂等）。
  - `EYE_NAME_TOKENS = {"eye", "eyel", "eyer"}`：Vincent 一只眼一个材质。
- `scripts/final/export_ff7rb_model_blender.py`：导 FBX/GLB 时把眼睛预先烘成一张图（`blend_eye_arrays`），
  同样按节点里的倍数采虹膜；没有这个节点的旧图按 1 倍。
- `scripts/final/fix_ff7rb_eyes.py`（新）：修已经导出的 `.blend`。逐个开 Blender，只补虹膜 UV 节点、改遮罩，
  原地保存（不压缩，和原文件一样；不留 `.blend1`），`--backup` 先把原件拷走。只处理带 `FF7RB_EyeColorMix`
  的材质，其它文件原样不动。
- `scripts/final/ff7rb_rematerialize.py`（新）：从游戏重建指定材质。
  1. 选材质：`--material` / `--no-base`（Base Color 没接图）/ `--no-record`（没对上材质表、贴图是猜的）；
  2. CLI 列表 `End/Content/*/Material/<名字>.uasset` 找到材质实例（一个名字对应多个包就跳过）；
  3. 在临时目录放一个空 `{}` 表，调用 `ff7rb_cli_export.fix_materials` 按原逻辑重建（Parent 链 + 基础材质默认值），
     再导出表里引用的贴图（跳过 `/Game/Renderer/Texture/` 占位图）；
  4. Blender 里对这些材质跑 `prepare_material(force=True)`（和批量导出同一段代码），新贴图打包进 `.blend`，原地保存。
- `scripts/final/render_eye_closeup.py`（新）：眼睛特写 + 眼睛材质报告（节点、贴图、UV 范围），见第 1 节。
- `scripts/final/export_ff7_pmx_blender.py`：打包在 `.blend` 里的贴图先写到临时目录再导 PMX（见第 5 节）。
- `scripts/final/ff7rb_cli_export.py`：`.usmap` 先找 D 盘，D 盘删了就用 E 盘归档里那份
  （`E:\game_export\FF7Rebirth\_meta\mappings\`）。
- 测试：`tests/test_export_ff7rb_worker.py`（虹膜按倍数采样）、`tests/test_ff7rebirth_helpers.py`
  （贴图边缘落在遮罩外缘；EyeL/EyeR 是眼睛，Eyebrow/Eyelash 不是）。21 个全过。

## 4. 对已导出模型做了什么（E 盘归档）

```
python scripts\final\fix_ff7rb_eyes.py E:\game_export\FF7Rebirth --backup E:\_backup\ff7rebirth_eyes_20260926
  -> 98 个：70 个修好；28 个没有「眼白 + 虹膜」拼法，不动：
     只有身体的过场/Avatar 模型（PC70xx、PC0005_06）、伤口/血迹贴片、莫古利（自己的黑眼睛）、Cait Sith、
     Red XIII 全息形态、Reika mod（mod 自带整张眼睛贴图 ojos）、以及下面 3 个
python scripts\final\ff7rb_rematerialize.py <Vincent blend> --material PC0011_00_EyeL --material PC0011_00_EyeR --backup ...
python scripts\final\ff7rb_rematerialize.py <PC0010_10 blend> --no-base --no-record --backup ...   8 个材质，35 张贴图
python scripts\final\ff7rb_rematerialize.py <PC0000_17 blend> --no-base --no-record --backup ...   10 个材质，48 张贴图
```

全量检查（98 个 `.blend` 逐个列出缺底色 / 没有材质表的材质）后，剩下的都不是导出错误：
5 套 SOLDIER 装的 `PCxxxx_0x_Emissive`、13 个 mod 借用的 Tifa 耳环 `PC0002_00_Jewelry`
在游戏的材质表里本来就没有底色贴图（重建返回「没有底色」、不改文件）；Red XIII 全息形态走全息规则，本来就不记表。

Tifa #817 的 8 个 mod 重导了 XPS 和 PMX（它们把眼睛材质烘成了 `PC0002_00_Eye_baked.png`，旧图就是大黑瞳）。
画廊预览图（每个 `.blend` 旁的 `_preview.png`）和缩略图（`_meta\gallery\thumbs\`）按新文件重渲。

原件备份：`E:\_backup\ff7rebirth_eyes_20260926\<角色>\blend\<模型>\<模型>.blend`（73 个，约 7 GB），核对后可删。

## 5. 坑

- **从 E 盘归档导 PMX 会丢贴图**：归档后的 `.blend` 把图片打包在文件里，mmd_tools 的 PMX 导出按图片路径
  拷贴图文件，拷不到就只剩现烘的几张图（整张脸洋红）。XPS 不受影响（blender2xps 能写出打包的图）。
  现在 `export_ff7_pmx_blender.py` 开头先把打包的图写到临时目录、让图片指向那里，存 `_converted.blend`
  之前再打包回去；这次的 8 个是先复制到临时目录解包再导的。
- 同名不同物：两个游戏的 `PC0002_00_Eye_C` 名字一样、内容不同，别拿 Remake 的经验套 Rebirth。
- `is_eye_material_name` 按词判断，`EyeL` 这种连写不是 `eye`；Eyebrow / Eyelash 也不能误判成眼睛。
- 借用材质：FModel 只写模型自己目录下的材质表，借用别的目录的材质实例就没有表，工具会按文件名猜
  （猜错了也不报错）。`ff7rb_rematerialize.py --no-record` 能把这类材质找出来重做。

## 6. 验证

- 眼睛特写（同一相机、灯光）：Tifa、Aerith、Sephiroth（竖瞳）、Cloud、Vincent、Sephiroth 变身、Cloud 17 修前 / 修后，
  Remake 同角色作对照：修后瞳孔大小和 Remake 一致，Tifa 红棕、Aerith 绿、Cloud 蓝绿、Sephiroth 青绿竖瞳。
  Rebirth 的 Tifa 虹膜比 Remake 偏淡，是游戏贴图本身的差别。
- 修复脚本：副本上试运行 → 正式修 → 再跑一遍显示「already ok」（幂等）；文件只多约 3 KB，头部仍是
  `BLENDER-v306`（不压缩），没有 `.blend1`。
- PMX（8 个 #817）：撕裂 0、付与顺序违规 0、静置漂移 0.9 cm（和 09-25 相同），PMX 贴图表里每一项都在；
  `preview_gaze.png` 目检。
- 单元测试 21 个通过。

## 7. 没做的

- 游戏的 `IrisNormal` / `IrisOcclusion` / `GazeNormal`（虹膜凹凸、虹膜遮蔽、视线法线）Blender 里没接，只接了颜色。
- 画廊页面文字里 Cloud 17 仍写着旧的「缺底色贴图 9」提示，重新生成画廊（再 `archive_exports.py --relink`）后才会消失；
  预览图和缩略图已经是新的。
