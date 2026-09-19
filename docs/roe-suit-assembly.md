# Rise of Eros：把「套装」(suit) 拼装成一个模型

ROE 的一个角色有多套「服装变体」(游戏内部叫 *suit*)。跟默认服装 (`chara_armor_pc_<id>_hd`
是一个整体 FBX) 不同，**一套 suit 不是一个整体模型**：它 = 角色的裸体底模 + 头发 +
一堆分开的服装部件网格，全部蒙皮到同一副骨架，游戏在运行时把它们叠在底模上。所以想导出
「林恩·冷艳主管」这种套装，得自己把部件拼回底模。

本文记录这条拼装线，以林恩 (`j01`) 的 **ProUniform**（冷艳主管职业制服，2026-09-12 更新
加入）为第一个实例。

## 数据在哪

| 内容 | Bundle |
|---|---|
| 裸体底模 + 头发 | `chara_bare_pc_<id>_nk.ab` → `pc_<id>_nk.fbx` |
| 该角色**所有** suit 的部件网格 | `chara_components_pc_<id>.ab`（一个包里上百个网格） |
| 某套 suit 由哪些部件组成 | `accessory_components_pc_<id>_suit_<suit>.ab`（几十 KB 的存根，
  根 GameObject 用 PPtr 指向 components 包里的真网格） |
| 该套 suit 的贴图 | `chara_tex_components_pc_<id>_suit_<suit>.ab`（`Lynn_<部件>_rgbx_Albedo` 等） |
| 脸/眼/身体/头发公共贴图 | `chara_tex_bare_pc_<id>_nk*` + `chara_tex_bare_pc_<体型>_common_head*` |

`extract_character.ps1 <id> -ExportTextures` 的收集规则已经会把 `bare`/`components`/
`accessory`/`vertex`/`suit` 以及 `chara_tex_*_suit_*` 一起 stage，所以正常提取一次该角色
就能拿到全部输入（AssetStudio splitObjects 会把每个部件导成
`<name>/FBX_GameObjects/<name>/<name>.fbx`）。

## 两个必须知道的坑

拼装难点全在部件 FBX 上（`chara_components_pc_<id>.ab` splitObjects 出来的那些）：

1. **部件 FBX 不带材质。** 原始 `import_scene.fbx` 进来后 `data.materials` 是空的。
   所以每个槽的贴图要**按部件名**去 suit 贴图目录里找 `Lynn_<部件>_rgbx_Albedo.png`
   （见 `assemble_suit_blender.py` 的 `resolve_albedo`；个别部件复用别人的图集，例如吊袜带
   `Garter` 用的是 `Lynn_EggVibrator` 的图）。

2. **蒙皮部件的顶点在正确的模型空间，但物体 `matrix_world` 是错的。** AssetStudio 把
   四肢部件的导出根设成一根肢体骨（如手套根是 `Bip001 L UpperArm`），于是 FBX 里给网格
   烘了一个多余的物体变换，导入后网格会**飘到离骨头约 1.5 m 的地方**（手套飘到身体正前方）。
   验证：手套的**局部**顶点质心 = (0.587, −0.056, 1.408)，几乎正是底模左手位置
   (0.575, −0.059, 1.391)；被错误的 `matrix_world` 推到世界 (0.612, 1.42, 1.453) 才飘的。
   躯干件的导出根是 `Root_G`（顶层，变换是单位阵），所以它们本来就对得上——这也是为什么
   外套、马甲一开始就在正确位置、手套/长袜/高跟/领饰却飘在脚边。

   **修法**：蒙皮部件——丢掉物体变换（`matrix_world = 单位阵`），把网格重新绑到底模骨架
   （顶点组名与底模骨名一一对应，静止姿势下形变=恒等，网格正好落在模型空间静止位）。
   **静态部件**（如桂冠是个 `MeshFilter`，没有骨架）正相反：它的顶点是局部坐标、靠物体变换
   定位，所以这种要**保留**自己的变换，只把它挂到底模骨架下跟着走。判据就看这个部件有没有
   自带骨架。

## 怎么用

```bash
# 1) 正常提取该角色（会顺带把 components / suit 贴图 stage 出来）
.\extract_character.ps1 j01 -ExportTextures

# 2) 列出这套 suit 由哪些部件组成
python suit_parts.py --game "<AssetBundles 目录>" --id j01 --suit prouniform
#   或： python suit_parts.py accessory_components_pc_j01_suit_prouniform.ab

# 3) 从列表里挑「穿好」的部件（去掉替代态和道具），拼装
blender --background --factory-startup --python assemble_suit_blender.py -- \
    --root <提取目录> --tex <贴图目录> --out D:\roe_exports\j01\blend\pc_j01_prouniform.blend \
    --base pc_j01_nk --parts <逗号分隔的部件名> --glb 1
```

产物：内嵌贴图的 `.blend` + 三视图 `_preview.png`（+ 可选 `glb/`），全部部件绑在底模的
`Root_G` 骨架上（可摆姿、后续可做 PMX）。

### ProUniform 实例（林恩·冷艳主管）

存根列出 17 个部件。「穿好」状态用 13 个，去掉 4 个：`EggVibrator`（道具）、`OpenVest`
（`CloseVest` 的敞开替代态）、`LLaceBra`/`RLaceBra`（敞开时才露的乳贴）。用的 13 个：
`UniformJacket, CloseVest, Ruff, L/RUniformGloves, LacePanties, Garter,
L/RUniformStockings, L/RUniformHighHeels, LaurelWreath, LaceBra`。
成品：白金职业制服 + 高领 frill + 长手套 + 吊袜带黑丝 + 金饰高跟 + 桂冠，
在 `D:\roe_exports\j01\blend\pc_j01_prouniform.blend`。

## 目前的限制

- **「穿好 / 脱到哪一层」是人工选的**：存根只说这套 suit 有哪 17 个部件，不说默认穿哪几个。
  哪些是替代态 / 道具要看名字或渲染一眼定。运行时的 `CharacterAccessorySetting` 里应有精确
  的初始显隐，尚未解析。
- 目前只出 `.blend`/`preview`/`glb`。XPS / PMX 未做——部件已绑到单一底模骨架，接
  `export_character_model_blender.py` 的 XPS/PMX 通道应可行，但还没接。
- 只在 `j01` ProUniform 上验证过。别的角色 suit 走同一条线，`Lynn_` 前缀要换成对应角色的
  贴图前缀（`resolve_albedo` 目前写死 `Lynn_`）。
