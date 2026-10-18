# 剑星：Eve 以外的女角色（17 个角色，18 个造型）

2026-10-18。把《剑星》里 Eve 以外的女性角色各导出一套最性感的衣服，顺便查有没有裸体；
做成独立的 .blend，存进 `E:\game_export\StellarBlade\<角色>\blend\<造型>\`，并加进剑星画廊（分类「其他角色」）。

和 Eve 的流程（`../export_outfit.ps1` + `validate_eve.py`）不同：这些角色的身体、脸、头发各是一个完整网格，
不需要拼 Eve 的脸和马尾，所以这里不用 UE Viewer，全部用 CUE4Parse CLI 直接导。

## 结果

| 角色 | 造型 | 藏起衣服和头发以后剩下什么（`preview_nude.png`） |
|---|---|---|
| 渡鸦 Raven | 白色紧身战衣；**另有游戏自带的完整裸体网格 `CH_M_NA_53_1`**（造型 `Raven_Nude`） | 战衣版：只剩头和胸口一块；**裸体版：完整的裸体** |
| 卡雅 Kaya | 军装外套 + 短裤 | 两条腿 + 画在皮肤上的骑行短裤、领口一小块，没有躯干 |
| 母亲领域 Mother Sphere | 白色荷叶边裙 | 两条腿 + 画在皮肤上的内裤，没有躯干 |
| 罗克珊 Roxanne | 黑色大衣（左腿是机械义肢） | 一条腿、一只胳膊、肚子 + 画在皮肤上的内裤 |
| 莉莉 Lily | 比基尼 + 网衣（`CH_NPC_01_Lilly`），另有 12 个变体 | 躯干和肩膀，网衣直接画在皮肤贴图上，没有腿 |
| 红莲 Scarlet（NIKKE 联动） | 原装 | 胸口、几块大腿 |
| 拉埃尔 Rael | 红色紧身衣 + 披风 | 胸口开口、几块大腿 |
| 塔琪 Tachy（NPC / Boss）、恩雅 Enya、伊贝丽斯 Iberis、卡拉 Kara、女仆、拾荒者奥利维亚、西翁女市民 | 黑色紧身战衣 / Boss 战甲（不戴头盔、不带翅膀披风）/ 仿生人外壳 / 原装 | 只剩头和手 |
| 苏 Su | 全脸头盔 + 皮草大衣 | 看不出性别（骨架没有胸部骨骼） |
| 空降部队女兵 | Eve 同款白色战衣 | 游戏里这个网格**没有头**（关卡蓝图另外挂） |

也就是说，**只有 Raven 有真正的裸体**；其它角色衣服下面只做了露出来的那几块皮肤。

颜色和游戏图鉴里的官方立绘（`SB/Content/Art/UI/Texture/Album/NPC/image/*`）对过：Raven 黑发、Lily 棕红短发、
恩雅和母亲领域银发、卡雅紫发。

## 用法

```powershell
cd scripts\stellarblade\npc
python export_npc_raw.py                       # 1. 导出 npc_characters.json 里的 82 个网格 + 贴图 + 材质 JSON
python build_npc_looks.py --lanes 3            # 2. npc_looks.json 里的每个造型 -> D:\stellarblade_npc\looks\<造型>\
python archive_npc_looks.py                    # 3. 存进 E:，写画廊清单，重新生成画廊
```

单个造型：

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' -b --factory-startup --python build_npc_blend.py -- `
  --name Raven_Nude --out D:\stellarblade_npc\looks\Raven_Nude --nude `
  --parts SB/Content/Art/Character/Monster/CH_M_NA_53/CH_M_NA_53_1,SB/Content/Art/Character/Monster/CH_M_NA_53/CH_M_NA_53_Facial,SB/Content/Art/Character/Monster/CH_M_NA_53/CH_M_NA_53_Hair
```

加 `--quick` 只渲正面（挑衣服时用：82 个网格各渲一张，拼成每个角色一张对比图）。

## 文件

| 文件 | 做什么 |
|---|---|
| `npc_characters.json` | 17 个角色的游戏目录里所有网格（82 个；武器、瓶子、玻璃、动画序列不要） |
| `npc_looks.json` | 每个角色选定的造型：由哪几个网格组成（身体在前，单独的脸、头发在后）、中文名、说明、告警 |
| `export_npc_raw.py` | CUE4Parse CLI：网格（.psk / .pskx）+ 贴图 -> `raw\`；网格和它用到的每个材质实例的 JSON，顺着父材质一直到主材质 -> `json\`；最后把材质里引用、网格导出时没带上的贴图补导 |
| `build_npc_blend.py` | Blender 3.6：导入各个网格，建材质，渲预览，存 .blend |
| `build_npc_looks.py` | 按 `npc_looks.json` 并行跑上一个 |
| `archive_npc_looks.py` | 用 `scripts/archive/blend_package.py` 把 .blend 做成独立目录（贴图拷进 `textures\`，相对路径，存完重新打开核对），写 `package.json`、`README.txt`，更新画廊清单，重新生成画廊 |

## 材质怎么建（预览版）

材质实例的参数顺着父材质往上合并（子的值盖住父的）。主材质本身的贴图（`CachedExpressionData.ReferencedTextures`）
在实例没给贴图时顶上，眉毛、睫毛就是这种。

| 类别 | 判断 | 做法 |
|---|---|---|
| 隐藏 | 眼睛水膜、眼影壳（`M_Eye_Occlusion` / `M_EyeBlend`）、泪线、牙齿遮挡、`Hide` / `MA_Clear` 槽、玻璃 | 透明 |
| 眼睛 | 主材质 `M_EyeRefractive` | 游戏的虹膜 / 眼白网络（`../eye_material.py`，只读调用），用这个角色自己的实例参数：`Iris UV Radius`、`ScaleByCenter`、`PupilScale`、亮度、`IrisHueTint` |
| 眉毛 / 睫毛 | 名字带 brow / lash，或主材质是眉毛 / 睫毛材质 | 自己的颜色（`BaseColour` / `Colour` / `root color`），没有就用头发颜色 × 0.7；按遮罩裁剪（有 alpha 用 alpha，否则用红通道） |
| 头发 | `MA_CH_Hair` 一族、`MA_CH_MetaLowHair`、`Mat_Hair_V1` | 颜色 = (发根 + 发梢) / 2 × Brightness × 2（和格斗游戏 `tools/sb_textures.py` 一样）；按发片贴图裁剪：`*_ADIR` 的红通道，否则 `Alpha` 图；**覆盖率先 × 3 再按 0.35 裁** |
| 其它 | 皮肤、衣服 | 颜色图（× `BaseTint`）+ 法线图；`MA_DitherAlpha` / `OpacityMask` 按 alpha 裁剪；皮肤加一点次表面散射 |

「藏起衣服」的预览（`preview_nude.png`）把衣服和头发的槽全部透明（头发也藏，长发会挡住躯干，2026-10-18 一开始就因此误判过卡雅和母亲领域「上身裸露」），剩下的就是衣服下面有没有身体。

## 踩过的坑

| 现象 | 原因 | 处理 |
|---|---|---|
| CLI 导网格时写出的材质 JSON 是空的 `{}` | 网格导出只带贴图 | 另跑一遍 `-f json` 导材质实例，顺着 `Parent` 一层层导到主材质 |
| 眉毛是白的、没有形状 | 眉毛的贴图写在主材质的节点里，不是实例参数；而且网格导出没带这张图 | 读主材质的 `ReferencedTextures`；`export_npc_raw.py` 最后补导所有被引用、还没导出的贴图（125 张） |
| 头发稀疏 | 游戏里多层发片是抖动半透明，按 0.35 一刀裁掉，细发丝就没了 | 覆盖率 × 3 后再裁 |
| `Scarlet` 的 `NonBottle` 没出现在对比图里 | 网格清单按名字排除了 `Bottle`（瓶子），把 `NonBottle` 也排除了 | 不影响：`CH_M_NA_961` 本身就是完整造型 |
| 头顶秃了（Raven、恩雅、塔琪 Boss） | 发片贴图 `*_ADIR` 的 alpha 通道存的是发根渐变，不是覆盖率；取了 alpha，靠近发根的头顶发片全被裁掉 | `*_ADIR` 一律用红通道 |
| 用存好的 .blend 补渲全身图，只剩一只手 | 存档时相机停在头部特写，远裁剪距离只有约 4 m | 换机位时一起改 `clip_end` |
| 预览网格（`*_Preview`）没有眼睛 | 预览网格把脸合进了头的材质，没有眼球、睫毛 | 用身体 + `_Facial` + `_Hair` 三个网格拼 |

## 还没做

- **高清版**：要用另一个窗口的剑星高清脚本（`../hq_materials.py` → `../hq_materials_blender.py`）。
  它们现在还会把 Eve 的眼睛参数套到所有角色上，另一个窗口正在改成读每个角色自己的眼睛参数；
  `hq_materials.py` 也只认识 `MA_CH_Standard_Ver03` 这一种主材质，这些角色用的 `MA_CH_Standard_Cloth_Ver02`、
  `MA_Skin_EVE`、`MA_Skin_NPC`、`MA_CH_Hair` 等还要它补上。
- PMX / XPS。
- 表情：脸部网格的 morph 没导（PSK 不带 morph）。
