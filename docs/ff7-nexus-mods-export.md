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
- 原版 Remake Tifa 标准服装没有手掌（手套是独立武器网格），原画廊里的官方卡片还是这样；mod 导出（PC0002_00）
  从 2026-09-26 起自动装原版手套（见第 9 节）。
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
# 画廊（Remake 的 D 盘导出归档删掉以后照样能跑，见第 9 节末尾），然后归档到 E 盘 + 链接改到 E 盘
python scripts\final\html\collect_manifest.py && python scripts\final\html\make_gallery.py
python scripts\final\html_rebirth\collect_manifest.py && python scripts\final\html_rebirth\make_gallery.py
python scripts\archive\archive_exports.py ff7remake
# Remake 原版资源（key 只放仓库外）
python scripts\firstdescendant\find_aes_key.py --exe <游戏>\End\Binaries\Win64\ff7remake_.exe ^
    --pak <游戏>\End\Content\Paks\pakchunk0-WindowsNoEditor.pak --out E:\tools\umodel_ff7remake\_keys\ff7remake_aes.txt
$env:FF7REMAKE_AES_KEY = (Get-Content E:\tools\umodel_ff7remake\_keys\ff7remake_aes.txt -Raw).Trim()
scripts\final\ff7remake_export.ps1 -Package <包路径> ... -OutputRoot D:\ff7remake_exports\player
```

## 9. 2026-09-26：Remake 的 Tifa 裸体 mod（8 个）

用户从 Nexus 裸体 mod 清单里挑了 8 个 Remake 的 Tifa mod，在浏览器里下载，要求装进游戏并导出 Blender / XPS / PMX。
`nexus_mod_batch.py select --mods finalfantasy7remake:589=2357,...` 按文件号选（先用 `modFiles` 把下载文件名对上文件号），
`collect` 复制解压到 `D:\ff7_mods\remake\`，然后照第 2、4、5 节出模型。

| mod | 文件 | 改的服装 | 样子 |
|---|---|---|---|
| #589 Tifa 4K Hi-Poly Nude Mod（Jenovation） | v1.3 | 紫裙 PC0002_01 | 全裸 |
| #661 Tifa Nude Natural（SweetFluff3D） | 8.0.0 | 标准服 PC0002_00 | 去掉上衣和吊带，留手套、丝袜、靴子 |
| #1312 Tifa Nude By ShinyRoseMods | Second Upload | 标准服 | 裸体 + 手套、丝袜、靴子 |
| #1266 Nude Thicc Tifa | Tifa Nude Thicc | 紫裙 | 丰满型全裸 |
| #382 Nude-ish Tifa | tifa_seminude | 紫裙（只有贴图） | 紫裙贴图改成暴露的蓝色小衣服 |
| #1343 Tifa Nude Smaller Proportions | Shorter Hair | 紫裙 | 小一号身材的全裸、短发 |
| #668 Topless Tifa | Topless Tifa | 标准服 | 上空，吊带短裙、手套、丝袜、靴子 |
| #1358 Tifa Seethrough Dress | pink | 紫裙 | 粉色蕾丝透视裙（镂空花纹在 mod 自带的遮罩 `PurpleDress_A` 里，第 10 节修正前导出成了不透明的裙子），项链被 mod 藏掉 |

**装进游戏**：同一套衣服同时只能一个 mod 生效（同名网格 / 贴图谁后加载谁赢，混装会出现 A 的网格配 B 的贴图）。
标准服的 #661 本来就装着（和这次下载的逐字节相同），紫裙装了 #589；其余解压在 `D:\ff7_mods\remake\<mod>\<文件>\x\`，
换的时候把 .pak 拷进 `~mods`、删掉同一套衣服的另一个。#382 只有紫裙贴图，也不能和紫裙网格类的一起装。

**原版 key**：Remake 原版 pak 的索引是加密的（pak v4），以前是手动 `Read-Host` 输入。这次用
`scripts/firstdescendant/find_aes_key.py` 扫 `End\Binaries\Win64\ff7remake_.exe`，43 秒找到（exe 里用 dword 立即数拼出来，
不是连续的 32 字节），用 pak 索引解出挂载点 `../../../` 验证。key 存在仓库外 `E:\tools\umodel_ff7remake\_keys\`。
`D:\ff7remake_exports` 被归档窗口清掉以后，mod 导出要的原版资源按包重新提取：两套衣服的网格（顺带材质和贴图）、
手套武器 `WE0002_00`、`PC0002_01_MarineCharm` 材质，每个几秒。`ff7remake_export.ps1` 提取时会临时把 `~mods`
里的 pak 改名停用、结束后改回。

**这次修的三个坑**

1. **批量导贴图被一个坏包打断**（#1343）：`umodel -export ... *` 遇到 mod 里读不了的包（缺 .uexp 的材质、武器蓝图）报
   `TArray: index 1 is out of range`，随后把刚写出的贴图删掉——25 张只剩 5 张。mod 把换成裸体皮肤的贴图沿用了
   `PC0002_01_PurpleDress_C` 这些原名，没导出来就退回原版，身体套上了紫裙的布料（像紫色紧身衣）。
   现在批量导完按 `packages.json` 核对，缺的贴图 / 材质实例包逐个单独导。
2. **遮罩把整段挖空**（#668）：作者把丝袜、靴子、护臂、耳环放在同一段里，用的是原版 `PC0002_00_Earring` 材质；
   它的 Coverage 图 `BodyA_A` 只有耳环那几小块是白的，接成透明度以后这一段 98% 没了（没腿、没手臂）。Nexus 上作者的
   游戏截图里这些都在。规则：**遮罩来自原版材质、又会把分到它的面挖掉 90% 以上**（每个面的角点和中心都落在 < 0.5
   的像素上）时不接遮罩，报告里记 `masks_dropped`。mod 自己的材质实例里明确绑的 Coverage 照样生效——#1358 就是用它
   把项链整段藏掉的；头发 / 睫毛 / 眉毛是细发丝贴片（角点和中心常落在发丝之间），不做这个检查。
   走过的弯路：先按 UV 能对上 mod 的皮肤图集，把这一段改挂 mod 的 BodyA 材质，结果靴子和护臂成了肤色；
   截图（`mod { thumbnailLargeUrl }`，不用登录）说明游戏里用的就是原版图集、只是没挖洞。
3. **标准服没有手**（#661、#1312、#668）：游戏用独立的皮手套武器网格 `WE0002_00_Tifa_LeatherGlove` 画手。
   `fix_ff7remake_tifa_gloves.py` 本来就能装，但它要求手套和身体每根骨的静止矩阵完全一致；mod 身体走
   FF7R-mesh-importer 的 glTF 导入，骨头朝向约定和 PSK 导入器不同（骨头位置分毫不差，`R_Hand_a` 的 Y 轴一个沿手指、
   一个沿世界 -X），整矩阵比较在 `R_Ring_a` 差 1.41 就拒绝了。手套是用身体自己的骨头蒙皮的（每根骨的姿势 × 静止的逆），
   骨头朝向不影响，只需要位置一致——改成只比骨头头部位置，容差 1 mm。`ff7_mod_export.py` 对 PC0002_00 的 mod 模型
   自动装手套、重渲预览。

**验证**：8 个 .blend 预览逐个看过（和 #668 的 Nexus 游戏截图对照过）；XPS 8 个全部通过 blender2xps 自检（无权重顶点 0、
权重未归一 0；#661 头发 / 头部、#1343 裙子单个部件超过 65535 顶点，只有很老的 XNALara 读不了）；PMX 8 个：

| 模型 | 身高 m | 骨骼 | 刚体 / 关节 | 撕裂 | 付与 | 漂移 cm |
|---|---:|---:|---:|---:|---:|---:|
| mod1266 Tifa Nude Thicc | 1.726 | 396 | 76 / 58 | 0 | 0 | 1.5 |
| mod1312 ShinyRose（Second Upload） | 1.726 | 480 | 80 / 64 | 0 | 0 | 0.9 |
| mod1343 Tifa Nude Shorter Hair | 1.726 | 400 | 70 / 54 | 0 | 0 | 0.9 |
| mod1358 Tifa seethrough pink dress | 1.726 | 400 | 100 / 82 | 0 | 0 | 1.4 |
| mod382 tifa seminude | 1.726 | 421 | 100 / 82 | 0 | 0 | 1.4 |
| mod589 Tifa 4K Hi-Poly Nude Mod v1.3 | 1.726 | 400 | 76 / 58 | 0 | 0 | 1.4 |
| mod661 Tifa Nude Natural 8.0.0 | 1.726 | 480 | 80 / 64 | 0 | 0 | 0.9 |
| mod668 Topless Tifa | 1.726 | 480 | 112 / 96 | 0 | 0 | 0.9 |

胸部物理都是第 5 节那套（每侧一个球形刚体 + 弹簧关节）。跳舞预览（preview_dance.png）看过 #1266、#1312、#661、#668。
PMX 同样只在 Blender 里导回验证过。

**画廊和归档**：8 个都进了 Remake 画廊（`scripts/final/html/index.html`，45 → 53 张卡片，每张带 XPS / PMX / 舞蹈预览
链接），`.blend` / XPS / PMX 归档到 `E:\game_export\FF7Remake\Tifa\{blend,xps,pmx}\<label>\`
（`archive_exports.py ff7remake`：拷 304 个文件 3.05 GB，打包 16 个 .blend 的外部贴图，24 个造型自检全过，画廊链接改到 E 盘）。
这时 D 盘的原版导出（`player\_blends`、`_gallery`）已经归档后删掉了，原来的两条画廊命令会停在「找不到 _blends」，
而直接拿新的 `gallery_mods.json` 生成会只剩 8 张卡片。所以：

- `collect_manifest.py`：D 盘上没有的条目沿用归档里的 manifest（`E:\game_export\FF7Remake\_meta\ff7remake_models_manifest.json`），
  同名条目以 D 盘新导出的为准；
- `make_gallery.py`：D 盘 `_gallery\thumbs` 不在时，缩略图读写归档里的 `_meta\gallery\thumbs`；预览图已经不在 D 盘时沿用已有的缩略图。

生成的页面里 D 盘路径由归档那一步按账本逐个文件改到 E 盘。顺带修好了画廊原来的 35 张官方卡片：它们的 blend / 预览
链接全指向 `Cloud\blend\PC0000_00_Cloud_Standard\` 下不存在的文件（70 个死链接）。原因在归档工具的改链接：
`player\_blends` 是 36 个模型共用的源目录，它在账本对不上逐个文件时，会退回到「这个源目录只归档出一个造型」的
目录级映射；某次只登记了 Cloud 标准服一个造型时改过链接，整个目录就都映射到了它的目录下，之后这些已经是 E 盘的
链接不会再被改。检查办法：把页面里每个 `file:///` 链接解码后看文件在不在（这次 201 个链接，0 个不存在）。

## 10. 2026-09-26（晚）：Rebirth 的 Tifa 裸体 mod（9 个）+ Remake 追加 2 个

用户接着从清单里下了 11 个文件，要求 Rebirth 的「都装进去」，导出 Blender / XPS / PMX，补画廊。

**先认清是哪一作**：文件名里的 mod 号两作都有（#575 在 Remake 是一首背景音乐，在 Rebirth 是 Tifa Nude Natural），
要拿下载文件名 / 大小去两作的 `modFiles` 里对。11 个里 #1364、#884 其实是 Remake 的。

| mod | 下载的文件 | 类型 | 导出的模型 |
|---|---|---|---|
| #575 Tifa Nude Natural (Dresscode)（SweetFluff3D） | 9.5.0（Dresscode V1.005） | Dresscode 插件 ×4 | 12：4 套衣服 × M / XL / XXL 身材 |
| #1083 Tifa Striped Bikini (Dresscode)（hwahwa） | Dresscode Version | Dresscode 插件 BunnyOasis | 10：各色比基尼、上空、凉鞋款 |
| #1369 Tifa topless in 4 variants (dresscode)（f80h） | 2.0.0 | Dresscode 插件 | 4：default / classic / costa1 / costa2 |
| #1198 Eve Skin Suit (Dresscode)（hwahwa） | 1.1 | Dresscode 插件 | 1 |
| #1352 Cybernetic Bondage（hwahwa） | 1.1 | Dresscode 插件 | 1，头和身体的材质在同 mod 另一个文件「PC0002 TifaSkin」里 |
| #363 Tifa Hi-Poly Nude Mod port（jmedia） | Nude Tifa V1.8 | `~mods` 替换 | 8：PC0002_00 / 04 / 05 / 06 / 08 / 09 / 10 / 11 |
| #679 Tifa Naked Re（nukog） | Tifa_Naked_Jiggle | `~mods` 替换 | 1：PC0002_00 |
| #1361 Tifa ND alternative（ogadori） | a. Tifa ND alt | `~mods` 替换 | 1：PC0002_08 |
| #2335 Tifa Nude（kuangsam135） | 9299 Tifa Nude (No Model) | `~mods`，只有新目录 `PC0002_99_Tifa_Nude` 的贴图和 4 个材质 | 0：模型在同 mod 的 9200（标准服）/ 9208（Costa）文件里 |
| Remake #1364 Tifa Purple Seethrough Bikini（frostbitere） | 1.0 | `~mods` | 1：透视紫色比基尼 |
| Remake #884 Tifa reforge by Aerosmith | reshape sandal 1.4 | `~mods`（紫裙；要 #597 才会盖到所有服装上） | 1：高模裸体 + 凉鞋 |

**Rebirth 的两种 mod**：
- Dresscode 插件：一个带 `<名>.uplugin` 的文件夹（`Content\Paks\WindowsNoEditor\<名>End-WindowsNoEditor.pak/utoc/ucas`），
  放 `<游戏>\End\Mods\`。要先装 Reunion Mod Loader（#1061 主文件 + Game Instance Loader 的 pak 进 `~mods`）和
  Dresscode（#1062），进游戏按 L3+R3 打开菜单换装。它是**加**服装、不替换，所以可以全部同时装。插件都是纯内容插件
  （没有模块、没有依赖声明），框架没装时不会报错，只是选不到。
- `~mods` 替换：直接盖原版服装，同一套衣服只能一个生效。#363 盖了 8 套，和 #679（标准服）、#1361（PC0002_08）冲突。

**安装**（`D:\ff7_mods\installed_rebirth.json` 记了每个复制进去的文件）：`End\Mods` 放 8 个插件文件夹（#575 的 4 个 +
#1198、#1352、#1369、#1083 各 1 个）；`~mods` 放 #363（覆盖面最全，也是 Remake 里装的 #589 的移植版）。
#679、#1361 留在 `D:\ff7_mods\rebirth\` 随时可换。Remake 的两个都和已装的冲突（#1364 替换全部服装，#884 替换紫裙），没装。

**这次修的坑**

1. **mod 重画的透明遮罩被丢掉**（Remake #1364、#1358）。`validate_ff7remake_model.py` 对 mod 的「身体 / 衣服」类材质一律不接
   `_A` 遮罩（防 #967 那种借来的遮罩），可这两个 mod 恰恰是把紫裙原版材质本来就在读的 `PC0002_01_PurpleDress_A` 重画了：
   #1364 把裙身涂黑、只留比基尼，#1358 画成蕾丝镂空。新规则：mod 自己带了这张遮罩、原版材质又引用它，就接上，也不做
   「挖掉九成」的检查（那条只针对原版遮罩）。第 9 节导出的 #1358 因此是不透明的粉裙，这次重导（blend / XPS / PMX）。
2. 透明材质在 EEVEE 里仍按不透明投影：隐藏的裙身在大腿上投出暗斑。接了遮罩的材质 `shadow_method = "HASHED"`。
3. mod 的材质实例只改遮罩（#1364 的 MarineCharm 只覆盖 Coverage）时，底色和法线要沿用原版实例，不再报「缺贴图」。
4. **Rebirth：材质表写了、文件却没导出的贴图被「按名字找替身」**（#1198）。Eve_Skin 的金属度是原版
   `PC0002_00_Skin_Mr`，网格导出没带它，worker 找了个名字最像的——紧身衣的 `ORM_B_metallic`，皮肤成了镜面。
   `ff7rb_cli_export.py` 现在把材质表里引用、导出目录里没有的贴图再导一遍（每个 mod 补了几张到几十张）；
   `ff7rebirth_tools.py` 对法线 / 粗糙度 / 金属度 / 透明 / 自发光，表里声明了却找不到时不再猜（底色照旧猜并记告警）。
5. **Rebirth：材质表在别的目录**。#363 的 PC0002_04..11 身体、#1361 都用标准服目录的 `PC0002_00_Head/_Hair/_Arms`，
   #1361 还用 Cloud 的 `PC0000_00_Shoulder`，worker 只看网格自己的目录 → 白模；#575 的四个插件共用只在
   PrideOfSeventhHeaven 插件里的 `PC0002_00_Skin_NoScar_Hair` / `PC0002_00_HeadNN`，名字里带 Hair / Head，被配成了
   原版头发的贴图（脸和身体上全是发丝）。`ff7_mod_export.py` 现在给每个网格的 `FF7RB_EXTRA_ROOTS` 加上整个导出的
   角色目录、`End\Mods` 和同一文件的所有插件目录。
6. 游戏里装了 `~mods` 替换以后，`ff7rb_cli_export.py` 导**原版**时直接读游戏目录会把 mod 也读进去；现在一律读
   硬链接暂存目录（只链游戏自己的容器）。
7. 需要配套文件的 mod：Rebirth 也支持 `--combine A+B`（B 一起挂载，模型只取 A 的）。#1352 等 TifaSkin（10357）下好后
   `ff7_mod_export.py rebirth --combine 10356+10357`；#2335 等模型文件（11458）后 `--combine 11458+11457`。

**顺带确认的**：#1083 叫 `BunnyOasis_nude` 的网格默认材质就是完整比基尼，叫 `000000FF` 的 Coverage 贴图其实全白——
导出和 mod 数据一致。#1198 与 Nexus 作者截图对照过（奶白色紧身衣 + 铜色胸甲）。

**验证**：Rebirth 37 个 .blend 的预览逐个看过（#1198、#575 对照了 Nexus 作者截图），XPS 37 个全过 blender2xps 自检
（只有老问题：头发部件超过 65535 顶点）；Remake 三个（#1364、#884、重导的 #1358）同样出了 XPS / PMX。PMX：

| mod | 模型数 | 身高 m | 骨骼 | 刚体 / 关节 | 撕裂 | 付与 | 漂移 cm |
|---|---:|---:|---:|---:|---:|---:|---:|
| Rebirth #575 | 12 | 1.721–1.741 | 1008–1012 | 78–167 / 62–151 | 0 | 0 | 0.8–0.9 |
| Rebirth #1083 | 10 | 1.741 | 649 | 123 / 107 | 0 | 0 | 0.8 |
| Rebirth #363 | 8 | 1.721–1.733 | 460–547 | 28–78 / 12–62 | 0 | 0 | 0.9（PC0002_05 为 2.9） |
| Rebirth #1369 | 4 | 1.721–1.741 | 580–681 | 78–167 / 62–151 | 0 | 0 | 0.7–1.0 |
| Rebirth #1198 | 1 | 1.721 | 885 | 78 / 62 | 0 | 0 | 0.9 |
| Rebirth #679 | 1 | 1.721 | 1377 | 113 / 97 | 0 | 0 | 1.0 |
| Rebirth #1361 | 1 | 1.731 | 949 | 80 / 64 | 0 | 0 | 0.9 |
| Remake #1358 / #1364 / #884 | 3 | 1.726 | 400 | 100 / 82、100 / 82、70 / 54 | 0 | 0 | 1.4 / 1.4 / 0.9 |

#363 的 PC0002_05 是士兵服款：头发收在头盔里，头发刚体只剩 28 个，漂移来自这几撮短发，跳舞预览正常。
PMX 同样只在 Blender 里导回验证过。

**画廊和归档**：Remake 画廊 53 → 55 张（#1358 换成透视版），Rebirth 画廊 98 → 135 张（本次 37 个）。两边都照第 9 节末尾的
流程：`collect_manifest.py` + `make_gallery.py`（D 盘上没有的条目、缩略图沿用 E 盘归档）+ `archive_exports.py <游戏>`。
Rebirth 的 `collect_manifest.py` 也加了同样的归档兜底。顺带把归档清单里两条过时的告警去掉：Cloud 17（缺底色 9）和
Sephiroth 变身（缺底色 1）的材质在 09-26 已从游戏里重建（`ff7rb_rematerialize.py`），在 Blender 里核对过每个材质都有底色。

**并行导出的坑**：XPS 用三个 Blender 并行时，第一版驱动把三个进程的输出都接到管道上、再按顺序等它们结束——后两个
的管道缓冲区写满就卡住不动（CPU 0%），只有第一个在跑。每个进程的输出直接写日志文件就好。`ff7_mod_pmx_batch.py`
现在写 `gallery_mods.json` 前先重读、只替换自己处理过的条目，几个 `--only` 批次可以同时跑。
