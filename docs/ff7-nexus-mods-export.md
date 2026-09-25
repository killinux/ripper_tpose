# FF7 Remake / Rebirth：Nexus mod 导出到 Blender / XPS / PMX，以及 Rebirth 画廊补全

> 2026-09-25。起因：用户要把 Nexus 上两作里跟 GANTZ（杀戮都市）相关的 mod 下载下来，导出成
> Blender、XPS、PMX，并补全两作的画廊。本文记录实际做法、每个坑和验证结果。
> 仓库里只有脚本和说明；mod、游戏资源、AES key、导出物都不进仓库。

## 0. 结果一览

| 游戏 | mod | 文件 → 模型 |
|---|---|---|
| Remake | #967 Tifa - Gantz Suit（MonkeyMan Mods，成人向） | 全身版、性感版 → 2 |
| Remake | #1707 Tifa Gantz Basic Suit（TheWolfster） | 普通、Skimpy、两者各配发型妆容附加包 → 4；附加包单独装在原版上 → 2（只进画廊） |
| Rebirth | #817 GANTZ Basic Suit (Tifa)（TheWolfster） | 独立版 4 个变体 + DRESSCODE 版 4 套（全身 / 全身紫 / Skimpy / Skimpy 紫） → 8 |
| Rebirth | #1613 Gantz - Reika (DRESSCODE)（SeeS，成人向） | 5 个网格（含裸体版） → 5 |

- Blender：Remake 8、Rebirth 13；XPS、PMX 各 19（不含附加包单独效果那 2 个）。
- Rebirth 画廊从 71 变成 85：Player 目录的 85 个主模型包全部进了画廊（FModel 读不了的 13 个 + 以前材质化失败的红十三全息版，改走 CUE4Parse CLI）。
- Remake 画廊加了 mod 分类：上面这些，外加 8 月手动导出、一直没进画廊的 zzTifaNudeNatural。

产物位置：

```text
D:\ff7_mods\                         下载清单页、selection.json、collected.json、各 mod 解压目录
D:\ff7remake_exports\mods\<modId>_<名>\<fileId>_<名>\   .blend / _preview.png / 报告 / 中间件
D:\ff7remake_exports\mods\xps\<label>\  D:\ff7remake_exports\mods\pmx\<label>\
D:\ff7rebirth_exports\mods\...        同上
D:\ff7rebirth_exports\cli_exports\    CLI 补导的 14 个官方包（FModel 同构目录）
D:\ff7rebirth_exports\cli_materialized\  它们的 .blend + 预览
```

## 1. 找 mod 和下载（scripts/final/nexus_mod_batch.py）

- 先走偏过一次：「gantz 的 mod」被理解成上传者 Gantz79（609 个 mod，FF7 两作 129 个）。用户要的是
  **GANTZ 主题**的 mod：按名字 `WILDCARD gantz` 和简介 `MATCHES gantz` 搜。简介搜索误报很多（发型包、
  存档、致谢里提到 gantz 的），要人工筛。注意 `gameDomainName` 列表里放两个值是 AND，永远 0 条，要逐个游戏查。
- Nexus 只给 Premium API key 发下载链接，所以文件由用户在浏览器里点。`nexus_mod_batch.py`：
  `select --mods domain:modId=fileId+fileId` 写 selection.json；`page` 生成每个文件一个直达链接的清单页
  （`?tab=files&file_id=`）；`watch` 每 15 秒扫 `E:\Downloads`，大小对上就**复制**出来（原件不动）再解压
  （UnRAR / 7zr / zipfile）。
- 文件名匹配：老文件浏览器存成 API 的 `uri`（`名-模组号-版本-时间.ext`）；**新存储的文件 uri 是哈希路径**，
  浏览器存成 `名 模组号 版本 时间 随机串.ext`（空格分隔），按「模组号 token + 文件名前缀」认，并排除同 mod
  其它文件的已知名字。
- 选择：每个 mod 只要当前 MAIN 文件；同内容的旧游戏版本（1613 的 1.004 版）不要；#817 的 DRESSCODE 1.004 被 1.005 取代。

## 2. Remake mod（ff7_mod_export.py remake）

1. **单独挂载 mod**：mod 的 .pak 硬链接进 `<工作目录>\mount\`，UE Viewer 只看这一个目录。整个 Paks
   目录一起给它时，原版包可能盖过 mod（见 `ff7remake-mod-manual-export.md`）。
2. `umodel -list -game=ue4.18 -path=mount *` 每个包后面列出它的导出对象和类名，直接按 `SkeletalMesh` /
   `Texture2D` / `MaterialInstanceConstant` 分类，不用猜。
3. 贴图和材质：`-export -png -nomesh -noanim *` 整个 mod 导一遍（mod_assets）。
4. 网格：先试 `-export`；四个 GANTZ 网格全部触发专用 UE Viewer v8 的
   `assertion failed: LODModels.Num() == LODInfo.Num()`，自动改走 `-save` 原始包 +
   [FF7R-mesh-importer](https://github.com/matyalatte/FF7R-mesh-importer)（v0.2.1 + 仓库补丁
   `ff7r_mesh_importer_large_mesh_cm.patch`，克隆在 `E:\tools\FF7R-mesh-importer`）转 glTF。
5. `validate_ff7remake_model.py` 新增 `--overlay-root`：mod 的贴图和 .mat 按名字盖过原版导出
   （`D:\ff7remake_exports\player`），mod 没带的材质仍用原版的；也能直接导入 glTF。
6. 只有贴图的 mod（1707 的发型妆容附加包）：没有网格就套在它改动的原版包网格上。
   `--combine 5649+5651` 把附加包和战斗服一起挂载，出组合版。
7. 注意：#967 不是替换 `PC0002_00`，而是把新网格 `Tifa_Mod` 放进紫裙目录，再改 `PlayerTable` 指过去。
8. **透明遮罩按参数名判断**：UE Viewer 写的 .mat 只列贴图、不写参数名，老规则是「材质引用了同名 `_A` 就当透明遮罩」。#967 的整套战斗服都在 `PC0002_01_MarineCharm` 材质上，它引用的 `MarineCharm_A` 绑在 `0:5:DetailOpacity`（自发光细节层的遮罩，父材质是不透明的 Standard_Emissive_Detail），当成透明度后全身 52% 被挖空，绿幕渲染才看出来（灰背景下像白色花纹，头发从洞里透出来像棕斑）。现在 `ff7_mod_export.py` 对 mod 里每个材质实例跑 `umodel -dump`，把 {参数名: 贴图} 写进 `mod_assets/material_params.json`，`validate_ff7remake_model.py --material-params` 只把绑在 Opacity / Coverage / Alpha 类参数上的贴图当遮罩；读不到参数的材质（原版）沿用老规则。

原版 Tifa 标准服装的手套 / 手掌是独立武器网格（WE0002_00），画廊里原版 Tifa 本来就没手掌；
GANTZ 战斗服的网格自己包含手，不受影响。

## 3. Rebirth mod（ff7_mod_export.py rebirth + ff7rb_cli_export.py）

FModel 只有图形界面，这次整条改走 CUE4Parse CLI：

1. **暂存目录**：`D:\ff7_mods\_stage\rebirth\End\Content\Paks\` 里硬链接游戏的 150 个容器（同盘，不占空间），
   mod 的 pak/utoc/ucas 放进 `~mods`。CLI 日志里 mod 容器 order 10303、原版 3，mod 的同名包会赢。
2. **mod 网格读不出来**：`RawArray item size mismatch: expected 8, serialized 4`。官方网格的切线是 SE 的
   4 字节压缩格式（CUE4Parse 2026-08-24 起用 `SerializeTangentsFF7R` 按 4 字节读），mod 是用原版
   UE 4.26 编辑器烘的，切线还是 8 字节（两个 FPackedNormal）。用通用 `GAME_UE4_26` 读更早就失败
   （mod 其余部分是 SE 格式）。修法：读 Rebirth 切线前先看数组元素大小，4 字节走 SE 读法，8/16 字节
   交给后面原版 UE4 的读法。补丁 `scripts/final/cue4parse_ff7_mod_tangents.patch`（打在
   joric/CUE4Parse.CLI ab447bb 上），用装在 `E:\tools\dotnet` 的 .NET 10 SDK 编译到
   `E:\tools\cue4parse_cli_ff7\cue4parse.exe`（没改系统 PATH）。官方网格结果不变（蛤蟆 psk 逐字节同大小）。
3. **材质表是空的**：CLI 导网格时写的材质 JSON 全是 `{}`。`ff7rb_cli_export.py` 用 `-f json` 读每个材质实例的
   原始属性，沿 `Parent` 链一直到基础 `Material`，重建 FModel 格式的 `{"Textures": {...}}`：
   - 先填基础材质的**贴图参数默认值**：`CachedExpressionData.Parameters.RuntimeEntries[2].ParameterInfos`
     与 `TextureValues` 一一对应（RM_Surface 有 67 个，比如 `Coverage` → `FFFFFFFF_BC4`）；
   - 再填 `CachedReferencedTextures`（按贴图名），最后 `TextureParameterValues`（按参数名，子覆盖父）。
   默认值不能省：worker 只有看到「这个角色只有占位图」才不按名字猜；第一版没填，头、睫毛、上衣都被
   猜成 `PC0002_00_Hair_A` 当透明遮罩，脸上透出后面的头发。
4. **DRESSCODE 插件 mod**：插件挂在 `End/Mods/<插件>/Content/...`，但 CLI 输出按对象路径写
   （`<插件>/MetaData/fullsuit.pskx`），两边要换算；网格不在 `Model/` 目录，所以先把 mod 全部包导出，
   再按实际写出的 .psk/.pskx 认网格；`*_condition` / `Reika_FinalcompletCOndition` 这类辅助网格跳过。
   插件网格也用原版材质（眼睛、口腔），worker 通过 `FF7RB_EXTRA_ROOTS` 环境变量多看一个目录。
5. worker（ff7rebirth_tools.py）顺带补了三处：
   - `OxygenSaturation` 算底色候选（血迹贴花的颜色参数）；
   - 父链带 Glass 的薄玻璃壳（Reika 的角膜 `cafe_glass`）给 0.08 的固定透明度，不再用白图的 alpha 盖住眼睛；
   - 父链带 `Unlit_Hologram` 的材质（红十三全息版）没有底色贴图，给固定青蓝自发光，Coverage 作透明。

## 4. XPS（blender2xps）

```text
blender -b --python E:\code\othercode\blender2xps\tools\batch_export_blends.py -- ^
    --out D:\ff7rebirth_exports\mods\xps --scale 0.01 --bake AUTO <blend> ...
```

- 场景是厘米，`--scale 0.01` 后身高 1.726。
- blender2xps 的骨骼别名表原来不认 SE 命名（只有眼球和辅助骨改了名，XPS 姿势套不上），补了
  `C_Hip_a / C_Spine_a,b,d / C_Neck_a / C_Head_a / L_Shoulder_a / L_UpperArm_a / L_Forearm_a / L_Hand_a /
  L_UpperLeg_a / L_Foreleg_a / L_Foot_a / L_Toe_a / L_Thumb_a..c ...`（blender2xps 仓库 bone_names.py）。
- 坑：用 Python 在 Windows 写的列表文件是 CRLF，bash `mapfile` 读进来每个路径尾巴带 `\r`，Blender 报
  `Invalid argument`，只有最后一行成功。读之前 `tr -d '\r'`。

## 5. PMX（export_ff7_pmx_blender.py + ff7_mod_pmx_batch.py）

整条链复用 Stellar Blade 的 `export_pmx_blender.py`（它又复用 ROE 的 PMX worker）：mmd_tools 写 PMX，
Convert_to_MMD5 建 MMD 骨架和身体刚体，mmd_cloth_physics 做头发 / 布料链，blender2xps 烘节点颜色。
FF7 专用的部分：

| 问题 | 做法 |
|---|---|
| 骨骼槽位 | SE 命名一一对应：`C_Hip_a`→下半身，`C_Spine_a/b/d`→上半身/上半身2/上半身3，`C_Neck_a`→首，`C_Head_a`→頭，`L_Shoulder_a`→肩，`L_UpperArm_a`→腕，`L_Forearm_a`→ひじ，`L_Hand_a`→手首，`L_UpperLeg_a`→足，`L_Foreleg_a`→ひざ，`L_Foot_a`→足首，`L_Toe_a`→つま先，手指 a/b/c（拇指 0/1/2，其它 1/2/3），`L_Eye/R_Eye`→目（両目 由 ROE 流程加） |
| 4 节脊椎 | `C_Spine_c` 的权重并进 `C_Spine_b`、子骨挂到 b 上，脊椎链变成 3 节 |
| 脸部骨 | `C_FaceBase_a/b` 下面 104 根表情骨的权重并进頭（眼球和头发链除外）。不并的话 Convert_to_MMD5 会把它们的皮交给最近的骨头头部——眼球骨，眼皮会跟着视线转。代价：PMX 暂无表情 morph |
| 胸部物理 | SE 把左右两根胸部物理骨（`L/R_Breast_Spo` → `L/R_Breast_a_Phy`）都放在脊椎后 12 cm 的同一个点，游戏自带的解算器能处理，MMD 刚体就成了 28 cm 长的摆锤。转换前把每侧的旋转中心挪到该侧胸部皮肤重心往里 8 cm（只改静止骨位置，网格不动），再用 Eve 那套球形刚体 + 弹簧关节 |
| 支撑骨进了布料 | `*_Spo` 是肌肉 / 扭转辅助骨，布料插件却把三角肌的 `DeltoidB/C_Spo` 当飘带加了刚体。FF7 脚本在转换前把 `_spo$` 加进插件的 LIMB_HELPER 跳过表（只在本脚本里改，不动共用插件） |
| 大腿护甲被扯开 | TheWolfster 的两个战斗服（#817、#1707）把大腿护甲下半截绑在原版裙摆骨（`C_SkirtA_b / L_SkirtB_b / R_SkirtA_b_Phy`）上，靠游戏的裙摆解算器晃；MMD 里这些链挂在下半身上，抬腿时护甲留在原地。`--skirt-to-legs`：裙摆骨上的顶点把权重交给最近的大腿。真裙子不能这么做（前摆也在两腿之间），所以只对这两个 mod 打开 |
| 朝向和单位 | PSK / glTF 导入面朝 +X、厘米：按两只脚 脚→脚尖 的方向转到 -Y，缩放 0.01，导出 Scale 12.5 |

验证：`stellarblade/preview_pmx_blender.py` 把 PMX 带物理导回 Blender，套「来杯好茶」VMD，出
preview.png / preview_dance.png / preview_gaze.png / preview_morphs.png；静止 60 帧看物理链漂移。

19 个 PMX 的结果（撕裂按边长变化判定；付与 = 付与顺序违规数；漂移 = 静止 60 帧物理链根部最大位移）：

| 游戏 | 模型 | 身高 m | 骨骼 | 刚体 / 关节 | 撕裂 | 付与 | 漂移 cm | 裙摆骨转大腿 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Remake | mod1707 PC0002 00 Tifa Gantz Basic Suit | 1.726 | 476 | 80 / 64 | 0 | 0 | 0.9 | 是 |
| Remake | mod1707 PC0002 00 Tifa Gantz Basic Suit Hair and Makeup Ad | 1.726 | 476 | 80 / 64 | 0 | 0 | 0.9 | 是 |
| Remake | mod1707 PC0002 00 Tifa Gantz Basic Suit Skimpy | 1.726 | 476 | 80 / 64 | 0 | 0 | 0.9 | 是 |
| Remake | mod1707 PC0002 00 Tifa Gantz Basic Suit Skimpy Hair and Ma | 1.726 | 476 | 80 / 64 | 0 | 0 | 0.9 | 是 |
| Remake | mod967 Tifa Mod Tifa Gantz Suit Full suit version | 1.726 | 400 | 76 / 58 | 0 | 0 | 1.5 | - |
| Remake | mod967 Tifa Mod Tifa Gantz Suit Sexy version | 1.726 | 404 | 76 / 58 | 0 | 0 | 1.5 | - |
| Rebirth | mod1613 Reika Final Gantz Reika Dresscode for 1 005 | 1.730 | 1731 | 75 / 59 | 0 | 0 | 0.9 | - |
| Rebirth | mod1613 Reika Finalcomplet Gantz Reika Dresscode for 1 005 | 1.730 | 1386 | 77 / 61 | 0 | 0 | 0.9 | - |
| Rebirth | mod1613 Reika NUDE Gantz Reika Dresscode for 1 005 | 1.730 | 1394 | 75 / 59 | 0 | 0 | 0.9 | - |
| Rebirth | mod1613 Reika ViesassuitNosuit Gantz Reika Dresscode for 1 | 1.730 | 1731 | 77 / 61 | 0 | 0 | 0.9 | - |
| Rebirth | mod1613 Reika Viesassuit Gantz Reika Dresscode for 1 005 | 1.730 | 1394 | 77 / 61 | 0 | 0 | 0.9 | - |
| Rebirth | mod817 PC0002 00 Tifa GANTZ Basic Suit | 1.726 | 547 | 75 / 59 | 0 | 0 | 0.9 | 是 |
| Rebirth | mod817 PC0002 00 Tifa GANTZ Basic Suit Skimpy | 1.726 | 547 | 75 / 59 | 0 | 0 | 0.9 | 是 |
| Rebirth | mod817 PC0002 00 Tifa GANTZ Basic Suit Skimpy Standard Ha | 1.721 | 547 | 78 / 62 | 0 | 0 | 0.9 | 是 |
| Rebirth | mod817 PC0002 00 Tifa GANTZ Basic Suit Standard Hair | 1.721 | 547 | 78 / 62 | 0 | 0 | 0.9 | 是 |
| Rebirth | mod817 fullsuit Tifa GANTZ DRESSCODE 1 005 | 1.721 | 547 | 78 / 62 | 0 | 0 | 0.9 | 是 |
| Rebirth | mod817 fullsuit purple Tifa GANTZ DRESSCODE 1 005 | 1.726 | 547 | 75 / 59 | 0 | 0 | 0.9 | 是 |
| Rebirth | mod817 skimpy Tifa GANTZ DRESSCODE 1 005 | 1.721 | 547 | 78 / 62 | 0 | 0 | 0.9 | 是 |
| Rebirth | mod817 skimpy purple Tifa GANTZ DRESSCODE 1 005 | 1.726 | 547 | 75 / 59 | 0 | 0 | 0.9 | 是 |

舞蹈帧逐个看过；#817 大腿护甲打开 `--skirt-to-legs` 前后的特写对比、#967 透明遮罩修复前后的绿幕渲染都留在 `D:/ff7_mods/`。#967 自定义骨架（410 根）槽位照样全部解析出来。

## 6. Rebirth 画廊补全（71 → 85）

FModel 4.4.4 读不了的 13 个 Player 主模型（`Read incorrect amount of tangent bytes`）用 CUE4Parse CLI
读得出来，加上以前材质化失败的 `PC0004_06_RedXIII_OnceHologram`，一共 14 个：

```text
python scripts\final\ff7rb_cli_export.py --out D:\ff7rebirth_exports\cli_exports --package <14 个 Model 包>
scripts\final\export_ff7rb_models.ps1 -SourceRoot D:\ff7rebirth_exports\cli_exports `
    -OutputDir D:\ff7rebirth_exports\cli_materialized -Only <14 个编号> -Force
blender -b --python scripts\final\html\render_blend_preview.py -- D:\ff7rebirth_exports\cli_materialized
```

- 6 个 `PC7xxx_00_*_StandardCFEnd2`：复古 Q 版低多边形的 Cloud / Barret / Tifa / Yuffie / Debumoogle / Sephiroth；
- `PC0099_00_Toad_Standard`：蛤蟆；
- 6 个血迹 / 伤口贴片（`CutBrood*`、`NoRibbonBlood`、`BloodPSBL00910`）：几百到几千顶点、贴在身上的小网格，
  画廊里归「血迹/泪痕贴片」；颜色在 `OxygenSaturation` 参数上，PC0000_13 借用的是 Sonon 目录的贴图；
- 红十三全息版：无光照全息着色器，没有底色贴图，按全息规则出青蓝色。

`html_rebirth/collect_manifest.py` 现在同时读 `materialized`（FModel 路线）、`cli_materialized`（CLI 路线，
同名变体以它的 PASS 为准）和 `mods\gallery_mods.json`，不改原来那份 manifest；卡片上 CLI 路线的有
「CLI 补导」标记，mod 卡片有 Nexus 链接和 XPS / PMX / PMX 舞蹈预览链接。

## 7. 已知限制

- PMX 没有表情 morph（脸部骨并进了頭）；视线（両目 / 左目 / 右目）可用。
- 原版 Remake Tifa 标准服装没有手掌（手套是独立武器网格），原画廊就是这样，这次没动。
- 血迹贴片颜色偏暗：`OxygenSaturation` 本来是给着色器算血色的参数图，不是颜色图。
- PMX 只在 Blender 里导回验证过，还没在 MMD / PMXEditor 里实际打开。
- Reika 的夸张身材是 mod 本身的设计。

## 8. 命令速查

```text
# 下载清单（用户在浏览器点，脚本复制解压）
python scripts\final\nexus_mod_batch.py select --title "..." --mods finalfantasy7remake:967=3326+3327,...
python scripts\final\nexus_mod_batch.py watch
# Blender
python scripts\final\ff7_mod_export.py remake
python scripts\final\ff7_mod_export.py remake --combine 5649+5651 --combine 5650+5651
python scripts\final\ff7_mod_export.py rebirth
# 已有的 .blend 进画廊
python scripts\final\ff7_mod_export.py register --game remake --blend X.blend --label ... --name ...
# PMX（+ 预览）
python scripts\final\ff7_mod_pmx_batch.py remake
python scripts\final\ff7_mod_pmx_batch.py rebirth
# 画廊
python scripts\final\html\collect_manifest.py && python scripts\final\html\make_gallery.py
python scripts\final\html_rebirth\collect_manifest.py && python scripts\final\html_rebirth\make_gallery.py
```
