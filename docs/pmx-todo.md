# PMX 处理：待做清单

2026-10-25 盘点仓库里的 PMX 工具和 E 盘成品后列的（抽读 15 个各游戏 PMX 的结构，FF7 三作、星刃全扫，对魔忍 Squad 抽 16 个）。

**规矩**：每做完一项，先问用户下一项挑哪个，不自己开工。做完的项写上日期和结果，不删。

| # | 方向 | 状态 |
|---|---|---|
| 1 | 在 MMD 本体里验证 | 待挑 |
| 2 | MMD 里的材质 | 待挑 |
| 3 | 换装 / 换头的后半程 | **10-31 开始做**：挑零件做完（删零件时骨骼、刚体、关节、表情项一起清掉），跨游戏还没做 |
| 4 | PMX 覆盖面 | 待挑 |
| 5 | 表情 | **10-25 做了「表情移植」插件 + FF7 第一批 2 个，等用户看效果** |
| 6 | 手肘、膝盖的变形（SDEF） | 待挑 |
| 7 | 动作适配体型 | 待挑 |
| 8 | 标准化小缺口 + 整批体检 | 待挑 |

## 1. 在 MMD 本体里验证

- **现状**：所有效果（物理、表情、材质）都只在 Blender（mmd_tools）里看过，从没在 MMD 本体里检查过。
  09-27 的物理标定模型（`scripts/mmd_physics/physics_calibration_pmx.py`）一直在等 MMD 截图。
  Blender 和 MMD 的关节限位软硬、物理步长不一样，现在的调参是按 Blender 调的。
- **要做**：脚本驱动 MMD 本体（`E:\tools\MikuMikuDanceE_v932x64\MikuMikuDance.exe`）载入模型和 VMD、输出视频，
  和 Blender 的视频并排比。以后物理、材质、表情可以先在 MMD 里看过再交。
- **注意**：会在桌面上弹 MMD 窗口，挑用户不用电脑的时候跑。

## 2. MMD 里的材质

- **现状**（抽查）：

  | | ROE | Vindictus | FF7 三作 | 星刃 | 对魔忍 Squad |
  |---|---|---|---|---|---|
  | toon | 无 | 无 | 无 | 无 | 有（游戏的） |
  | 高光按材质区分 | 否（13 个材质全是 1.0 / 11.9） | 是 | 部分 | 部分 | 统一关掉 |
  | sphere / 描边 | 无 | 无 | 基本无 | 基本无 | 有 |

  MMD 的明暗主要靠 toon，没有 toon 时脸和身体发平；高光 1.0 / 11.9 是一层大白光，皮肤、头发、眼睛一样亮。
  游戏原版材质只做进了 Blender 插件（ROE / 星刃 / Vindictus 游戏材质）。
- **要做**：
  - 先按材质类别（皮肤、头发、眼睛、布、金属）配 toon、高光、sphere、描边：把 Vindictus 的 `scripts/vindictus/pmx_materials.py` 推广到所有游戏；
  - 再进一步：用 `E:\game_export\RiseOfEros\_meta\_hq_materials` 等处已有的法线、粗糙度、金属度贴图生成 ray-mmd 材质，MMD 里也有游戏质感。

## 3. 换装 / 换头的后半程

- **挑零件**：换装说明让用户在 PMXEditor 里删材质，但那只删顶点，那件衣服的骨骼、刚体、关节还在，
  看不见的布照样算物理，还可能挡别的刚体。要一个「勾选零件 → 连骨骼 / 刚体 / 关节 / 表情项一起清掉」的按钮。
- **跨游戏**：两个插件都只在 ROE ↔ ROE 之间试过。换头要求脸网格带着脖子、身体材质叫 `*_nk_body`；
  脸只到下巴的模型（多数别的游戏）现在换不了。
- 换装、换头两个成品（`E:\game_export\RiseOfEros\_混搭\`）的效果还等用户看。
- **10-31 挑零件做完**（换装插件 0.3，`parts.py` + `pick_cli.py`，侧栏 MMD →「挑零件（删掉不要的零件）」，任何 PMX 都能用）：
  勾掉的材质连同只给它用的骨骼（MMD 标准骨除外）、刚体、关节、表情项、贴图一起删；full 版删了贴身那份身体，裸体那份自动默认显示。
  验证：v2 成品删掉 g05 的 37 个零件 = 换装前的 a08 full（顶点、权重、骨骼、刚体、关节、表情逐项相同）。
  示例 `_混搭\挑零件示例_a08只穿g05衣服\`（a08 的裸体穿 g05 的衣服，打开就是）。做法见 [pmx-outfit-transfer.md](pmx-outfit-transfer.md)「挑零件」。
  跨游戏还没做。

## 4. PMX 覆盖面

- **现状**：7 家游戏的归档里一个 PMX 都没有，只有 .blend：
  TFD 13、NARAKA 34、HoneySelect 2 17、DOA6 21、DOA5LR 19、VVP 7、Throne of Desire 15。
  星刃 19 个角色里只有 3 个有 PMX；Action Taimanin 918 套里只有 1 套。
- 这些模型现在用不上换装、换头、爆衣、物理这一整套。
- TFD 是 Biped 骨名（和 ROE 一样），ROE 的转换链可能直接能用；HS2（cf_J_）、DOA（KTGL）、NARAKA 要先做骨骼对照。

## 5. 表情（10-25 开始做，第一步做完）

- **现状**：

  | | 表情数 | MMD 标准表情（抽查的 30 个里有几个） |
  |---|---|---|
  | ROE | 59 | 26 |
  | Vindictus | 56 | 26 |
  | 星刃 | 79 | 22 |
  | 对魔忍 Squad | 27–35 | 14 |
  | 对魔忍 Collection / Action | 36–37 | 16 |
  | FF7 Rebirth / Remake / CCFF7R | **87 个 PMX 里只有 1 个有**（09-26 的试做） | — |

  FF7 三作的 PMX 里脸只绑在「頭」一根骨上（没有脸部骨骼），只能做顶点表情。
- **已有的表情插件**：`expression_kit`（09-27，侧栏「表情」：骨骼 / 顶点 / ARKit，来源是 MetaHuman DNA、ARKit 形态键、姿势库、骨骼脸）、
  `ff7_face_morphs`（09-26，FF7 Remake 游戏自己的表情数据，只提取了 Tifa）、`mmd_face_morphs`（ROE 骨骼脸）、`faceit_arkit`。
- **等用户拍板的旧事项**：下载的「18」系列 84 个角色 279 个文件，ウィンク 左右反了，样品 `Fiona 18 V1_winkfix.pmx` 做过，批量没做。
- **以后可选**（09-27 调研报告里的）：VRM 1.0 表情预设、ARKit 曲线导入、VRChat 口型。
- **10-25 做了**：新插件 `scripts/blender_addons/pmx_expression_transfer`（侧栏 MMD →「表情移植」，用户选的做法），
  把一个 PMX 的表情移到另一个网格完全不同的 PMX 脸上。原理见 [pmx-expression-transfer.md](pmx-expression-transfer.md)，
  用法见 [pmx-expression-transfer-usage.md](pmx-expression-transfer-usage.md)。
  第一批：FF7R Tifa 试做的 43 个游戏表情 → CCFF7R Aerith、FF7 Rebirth Tifa（mod1083），成品在 `E:\game_export\_表情移植\`，
  等用户看效果。
- **接下来可做**（等用户拍板）：
  - FF7 三作剩下的 85 个 PMX 批量补表情；
  - 对魔忍 Squad 缺的标准表情：它们的眼睛画在贴图上、没有眼球网格，这个插件做不了，要另想办法；
  - 「18」系列 ウィンク 左右修正的批量。

## 6. 手肘、膝盖的变形（SDEF）

- **现状**：只有 Vindictus 用了（Fiona 2036 个顶点）；ROE、FF7、星刃、对魔忍都是 0。
- MMD 本体自己会算 SDEF，用上以后手肘、膝盖大角度弯曲不会捏扁。
- `scripts/vindictus/pmx_sdef.py` 本来任何 PMX 都能用，只是没用到别家。

## 7. 动作适配体型

- **现状**：第三方 VMD 套到我们的模型上没有任何适配：腿长不同会脚滑或悬空，胸大会手臂穿胸。
  现在只是在文件名里挑带「适配」字样的动作版本（`scripts/taimaninsquad/dance_batch.py`）。
- **要做**：按模型的腿长、肩宽、胸围改 VMD（センター / 足ＩＫ 按腿长缩放，手臂按胸宽外展）。

## 8. 标准化小缺口 + 整批体检

- 每个模型都缺 腰キャンセル、ダミー、操作中心 这三种骨。
- 両目、肩P、腕捩、手捩 等 27 根骨不在显示枠里，MMD 的骨骼列表里点不到。
- FF7 系没有 つま先ＩＫ，踮脚的动作脚不跟着动；对魔忍 Squad 没有 両目，眼睛的动作不起作用。
- 检查工具散在 6 个脚本里（`pmx_rig_check.py`、`cloth_check_pmx.py`、`chest_clip_blender.py`、`skin_clip_blender.py`、
  `clip_test_blender.py`、`pmx_morph_check.py`），没有一个对整批成品出报告的。

## 其他等用户拍板的

- 胸部跟随工具（`pmx_body_follows_cups.py`）要不要铺到另外约 116 个 ROE 模型；
- Vindictus 剩下 12 套服装；
- ROE 舞蹈视频 117 个 + 画廊。
