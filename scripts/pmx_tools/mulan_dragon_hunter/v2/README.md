# 水晶猎龙者 v2：六处差距全部补上（2026-11-01 下午）

用户看过 v1 后说「123456都继续改」：护胸、龙爪手甲、鳞甲短裙、真的水晶件、大剑、颜色深浅。v2 的做法：
底座换成 Inase a08 的**裸体版**（衣服版的皮肤贴图上画着链子和黑手套，露腰后会穿帮），零件从 Vindictus NA 的四个高清版模型拿，
水晶和剑刃用程序生成。成品 `E:\game_export\RiseOfEros\_混搭\仿制_王者荣耀_花木兰_水晶猎龙者\花木兰_水晶猎龙者_仿制v2.pmx`。

## 零件

| 部位 | 来源 | 处理 |
|---|---|---|
| 身体、脸 | Inase `pc_a08_hd_nude_bustB.pmx` | 去掉自带头发和右手剑 |
| 高马尾 | 星刃 Eve 两个头发材质 | 同 v1（`--no-fit --no-rotation --no-follow-body --min-gap 0`） |
| 翼冠、耳饰 | a08 outfit1 按骨骼拆出的 `_頭`、`_Accessories_ear` | 同骨架，不贴合 |
| 龙鳞肩甲 | Vindictus Miri「Dragon Rises」`upper_metal` 按骨骼拆开，只取肩 / 上臂的 6 块 | 默认贴合（供体身体 `miri_skin_body01` → 目标 `pc_a01_nk_body`） |
| 右手龙爪 | Vindictus Miul「Devil Hunter」`hand_metal` | 默认贴合 |
| 左护腕、刺甲短裤、刺甲靴、膝甲 | Vindictus Bel「White Shark」`hand_metal` `lower` `foot` `foot_metal` | 默认贴合 |
| 黑马甲 | Vindictus Sanyaa「Dark Knight」`onepiece_上半身`（蓝披肩领切掉）+ `onepiece_metal_上半身`（吊坠） | `cut_collar.py` 再贴合；马甲是镂空网格，`under_plate.py` 在下面垫一块皮肤外推 4 mm 的黑板 |
| 水晶 | `add_crystals.py`：肩甲顶 / 外缘 / 后缘、龙爪小臂和肘、护腕、胯、膝、头冠角、额前，胸口一颗粉晶 | 六棱锥碎晶，平面着色，权重跟它长在的那个顶点 |
| 大剑 | a08 `wp_a08_l` 剑柄 + `crystal_blade.py` 的水晶刃（护手以外的旧刃删掉） | `place_sword.py`（v2 支持多个材质一起搬） |
| 颜色 | `recolor2.py` | 见下 |

## 步骤

```powershell
$T = "scripts\blender_addons\pmx_outfit_transfer"; $V = "scripts\pmx_tools\mulan_dragon_hunter\v2"
# 底座：a08 裸体版去头发、去右手剑；Eve 马尾；a08 翼冠 + 耳饰
python $T\pick_cli.py ...\pc_a08_hd_nude\pc_a08_hd_nude_bustB.pmx build\b1_nude.pmx --remove "pc_a_nk_hair,wp_a08_r"
python $T\cli.py ...\Eve_Nude_Barefoot.pmx build\b1_nude.pmx build\b2_hair.pmx --materials "MI_Hair_New_Ponytail_4,MI_EVE_HR_01_TypeA" --prefix eve --split none --no-fit --no-rotation --no-follow-body --min-gap 0
python $T\pick_cli.py <v1 的 build\s5_onesword.pmx> build\s5_split.pmx --split "pc_a08_hd_body1_01_body_mat,pc_a08_hd_body2_00_body_mat" --split-mode bone --min-piece 20
python $T\cli.py build\s5_split.pmx build\b2_hair.pmx build\b3_crown.pmx --materials "pc_a08_hd_body2_00_body_mat_頭,pc_a08_hd_body2_00_body_mat_Accessories_ear" --prefix a08 --split none --no-fit --no-rotation --no-follow-body --min-gap 0
# 供体准备（都拷到 donors\ 再拆：拆开的模型要和原模型同文件夹）
python $T\pick_cli.py donors\Miri_DragonRises_HD\Miri_DragonRises_HD.pmx donors\Miri_DragonRises_HD\miri_split.pmx --split pc_female_dragon_rises_upper_metal --split-mode bone --min-piece 20
python $T\pick_cli.py donors\Sanyaa_DarkKnight_HD\Sanyaa_DarkKnight_HD.pmx donors\Sanyaa_DarkKnight_HD\sanyaa_split.pmx --split "pc_female_darknight_onepiece,pc_female_darknight_onepiece_metal" --split-mode bone --min-piece 20
python $V\cut_collar.py donors\Sanyaa_DarkKnight_HD\sanyaa_split.pmx donors\Sanyaa_DarkKnight_HD\sanyaa_cut.pmx pc_female_darknight_onepiece_上半身 --skin miri_skin_body01 --min-y 134 --gap-cm 2.0 --blue
# 四个 Vindictus 供体，默认贴合
python $T\cli.py donors\Bel_WhiteShark_HD\Bel_WhiteShark_HD.pmx build\b3_crown.pmx build\b4_bel.pmx --materials "pc_female_white_shark_hand_metal,pc_female_white_shark_lower,pc_female_white_shark_foot,pc_female_white_shark_foot_metal" --prefix bel --split none --donor-body miri_skin_body01 --target-body pc_a01_nk_body
python $T\cli.py donors\Miul_DevilHunter_HD\Miul_DevilHunter_HD.pmx build\b4_bel.pmx build\b5_miul.pmx --materials pc_female_devilhunter_hand_metal --prefix miul --split none --donor-body miri_skin_body01 --target-body pc_a01_nk_body
python $T\cli.py donors\Miri_DragonRises_HD\miri_split.pmx build\b5_miul.pmx build\b6_miri.pmx --materials "pc_female_dragon_rises_upper_metal_Bip001 L Shoulder,pc_female_dragon_rises_upper_metal_Bip001 R Shoulder,pc_female_dragon_rises_upper_metal_右肩,pc_female_dragon_rises_upper_metal_左肩,pc_female_dragon_rises_upper_metal_Bip001 R UpperArm,pc_female_dragon_rises_upper_metal_Bip001 L UpperArm" --prefix miri --split none --donor-body miri_skin_body01 --target-body pc_a01_nk_body
python $T\cli.py donors\Sanyaa_DarkKnight_HD\sanyaa_cut.pmx build\b6_miri.pmx build\b7_san.pmx --materials "pc_female_darknight_onepiece_上半身,pc_female_darknight_onepiece_metal_上半身" --prefix san --split none --donor-body miri_skin_body01 --target-body pc_a01_nk_body
# 剑：水晶刃 + 背到背上；水晶；马甲底板；改色；组装
python $V\crystal_blade.py build\b7_san.pmx build\b8_blade.pmx wp_a08_l Point007_L --width 7 --thick 2.2
python $V\place_sword.py build\b8_blade.pmx build\b9_sword.pmx "wp_a08_l,crystal_blade" Point007_L --tilt 35 --gap 3 --centre-y 100
python $V\add_crystals.py build\b9_sword.pmx build\b10_crystals.pmx $V\crystals_orange.json
python $V\add_crystals.py build\b10_crystals.pmx build\b11_pink.pmx $V\crystals_pink.json
python $V\under_plate.py build\b11_pink.pmx build\b12_plate.pmx --skin pc_a01_nk_body --over san_pc_female_darknight_onepiece_上半身 --reach 3.5 --offset 0.4 --margin-y 1.0 --color 0.10,0.05,0.14
python $V\recolor2.py build\textures
python $V\assemble2.py build\b12_plate.pmx out\ 花木兰_水晶猎龙者_仿制v2
```

看零件用 `mat_views.py`（Blender，把模型按材质拆成独立物体后逐块渲染正 / 背面，`--all-in-one` 整体渲染）和 `sheet.py` 拼图。

## 改色规则（recolor2.py）

- 头发：亮度 → 「暖灰阴影 → 铂金 → 近白」渐变，比 v1 更白、更不黄；
- Miri 肩甲：金色里最亮的四分之一（明度 > 0.87）→ 橙色水晶，其余金色 → 黑紫金属（明度 ×0.36）；
- Miul 龙爪：红色纹路 → 橙；Bel 四件：白色布料 / 板甲 → 黑紫（明度 ×0.2）、藏青 → 紫、青色 → 橙；
- Sanyaa 马甲：蓝色花纹 → 暗紫，吊坠蓝宝石 → 粉；翼冠、剑柄、眼睛沿用 v1 规则。

## 水晶（add_crystals.py）

JSON 里每簇给材质名 + 一个大概的点（cm），脚本吸附到该材质最近的顶点，用它的法线当生长方向（可 `dir` 覆盖、`up_bias` 往上掰），
`count` 颗六棱碎晶（`len_cm` / `r_cm` 范围、`spread_deg` 散开角、`radius_cm` 簇半径、`sink_cm` 埋入深度），`mirror` 镜像到另一侧
（材质名和骨骼名左右互换，或 `mats_mirror` 指定）。顶点 BDEF1 到吸附点最重的骨骼，所以跟着肩甲 / 龙爪一起动。
贴图是脚本画的渐变（尖端亮、根部深橙），材质环境光 1.0/0.8/0.55、共用 toon 0、描边暗红；PMX 面的绕向从文件里现有的面测出来。

## 踩过的坑

- **mmd_tools 保存 PMX 时把贴图路径写成相对 PMX 的路径：如果 `Texture.path` 本身是相对路径，它用 `os.path.relpath`
  对当前工作目录算，结果指到别的文件夹，整模型洋红**。给 `Texture.path` 赋绝对路径再保存（assemble2.py）。
- 拆开的模型要和原模型放同一文件夹（贴图按相对路径找），所以供体先拷到 `donors\`。
- Sanyaa 的马甲镂空是网格上的洞（贴图 alpha 全是 1），不是贴图透明：垫底板，不是补 alpha。
- a08 的剑「插在地上」：剑尖在 y=0；PCA 主轴上护手是刃侧最宽的一段（t=-15，半宽 7.5 cm），刃只有 194 个面。
- Miri 右肩甲的主骨骼是她自己的辅助骨 `GeoSphere002`（换装插件一并搬来），手势舞里没问题。
- `blender -b --factory-startup` 渲染要先设共用 toon 文件夹（见 v1 README / pmx-head-swap.md）。

## v3（同日傍晚，用户「左手也换成龙爪；短裤换成鳞甲裙；水晶做成原画那种不规则大块；龙头剑柄；肩甲的紫色深浅」）

成品 `花木兰_水晶猎龙者_仿制v3.pmx`（贴图 `textures_v3\`），和 v1 / v2 并排。相对 v2 的改动：

| 项 | 做法 | 脚本 |
|---|---|---|
| 左手龙爪 | 在供体上把 Miul 的 `hand_metal` 镜像成 `_mirror`（x 取反、绕向翻转、权重换到 左/右 对应骨骼），两只一起走贴合 | `mirror_material.py` |
| 鳞甲裙 | Miri（Dragon Rises）连衣裙的裙摆：按骨骼拆开后裙子散在 `上半身` / `下半身` / `左足D` 三块里，各取质心 y ≤ 106 cm 的面（`cut_y.py`），三块一起贴合；下面垫 Sanyaa 的黑短裤（`onepiece_下半身`） | `cut_y.py` |
| 大块水晶 | `add_crystals.py` 新的 `"style": "chunk"`：5–8 条不等边、鼓肚、两个错开顶点的凿形尖、更大的尺寸（肩 11–19 cm、冠 11–18 cm） | `crystals_orange3.json` `crystals_pink3.json` |
| 龙头剑柄 | `crystal_blade.py --remove-guard` 连护手一起删；`dragon_hilt.py` 在刃根处放一个低模龙头（头骨 / 上下颌 / 颊鳍 / 双角放样，眼、牙、眉刺、鼻刺、顶刺是水晶），刃从张开的嘴里出来；四个材质一起 `place_sword.py` | `dragon_hilt.py` |
| 肩甲紫色 | 金色暗部 → 黑紫的明度 ×0.36 改成 ×0.26（接近原画的黑） | `recolor2.py` |

```powershell
python $V\mirror_material.py donors\Miul_DevilHunter_HD\Miul_DevilHunter_HD.pmx donors\Miul_DevilHunter_HD\miul_mirror.pmx pc_female_devilhunter_hand_metal
python $T\pick_cli.py donors\Miri_DragonRises_HD\miri_split.pmx donors\Miri_DragonRises_HD\miri_split2.pmx --split pc_female_dragon_rises_upper --split-mode bone --min-piece 20
python $V\cut_y.py donors\Miri_DragonRises_HD\miri_split2.pmx donors\Miri_DragonRises_HD\miri_skirt2a.pmx pc_female_dragon_rises_upper_下半身 --max-y 106   # 再对 _上半身、_左足D 各做一次
python $T\cli.py donors\Bel_WhiteShark_HD\Bel_WhiteShark_HD.pmx build\b3_crown.pmx build3\c4_bel.pmx --materials "pc_female_white_shark_foot,pc_female_white_shark_foot_metal" --prefix bel --split none --donor-body miri_skin_body01 --target-body pc_a01_nk_body
python $T\cli.py donors\Miul_DevilHunter_HD\miul_mirror.pmx build3\c4_bel.pmx build3\c5_miul.pmx --materials "pc_female_devilhunter_hand_metal,pc_female_devilhunter_hand_metal_mirror" --prefix miul --split none --donor-body miri_skin_body01 --target-body pc_a01_nk_body
# 肩甲同 v2 -> c6；裙子三块 -> d7；Sanyaa 马甲 + 吊坠 + 短裤 -> d8
python $V\crystal_blade.py build3\d8_san.pmx build3\d9_blade.pmx wp_a08_l Point007_L --width 7 --thick 2.2 --remove-guard
python $V\dragon_hilt.py build3\d9_blade.pmx build3\d10_dragon.pmx --blade crystal_blade --hilt wp_a08_l --bone Point007_L
python $V\place_sword.py build3\d10_dragon.pmx build3\d11_sword.pmx "wp_a08_l,crystal_blade,dragon_head,dragon_head_crystal" Point007_L --tilt 35 --gap 3 --centre-y 100
python $V\add_crystals.py build3\d11_sword.pmx build3\d12_crystals.pmx $V\crystals_orange3.json
python $V\add_crystals.py build3\d12_crystals.pmx build3\d13_pink.pmx $V\crystals_pink3.json
# 底板、改色、组装同 v2（out\ 名字 花木兰_水晶猎龙者_仿制v3）
```

看剑柄用 `mat_views2.py --cx -0.07 --cdepth 0.22 --centre 1.06 --size 0.5 --views back back34 sidel`（龙头在背中央、剑的中点处，马尾会挡住一半）。
坑：Blender 自己的 Cycles 启动脚本也用 argparse 扫 `--` 后面的参数，`--cy` 会被当成 `--cycles-*` 的缩写报 ambiguous，所以叫 `--cdepth`。

## v4（同日晚，用户「继续优化」，我挑的）

成品 `花木兰_水晶猎龙者_仿制v4.pmx`（贴图 `textures_v4\`）。相对 v3：

| 项 | 做法 | 脚本 |
|---|---|---|
| 剑刃 | 不再是一整块橙板：`crystal_blade.py` 给六角刃画专用贴图 `crystal_blade.png`（两个宽面 = 发光的橙色晶芯、面的两侧渐暗成晶边，四个斜面黑紫带橙色纹），碎晶另成材质 `crystal_blade_shards` | `crystal_blade.py` |
| 龙头 | 不用放样的低模了：Miri 肩甲贴图上有个真正雕刻的龙首（肩甲顶上 4 cm 的装饰），`uv_part.py` 按 UV 矩形（u 0–0.17, v 0.14–0.43）把那 922 个面从肩甲材质里抠出来，`place_prop.py` 放大 7 倍、按「吻部 = 刃方向、头顶 = 刃宽方向」摆到刃根，刃从嘴里出来；贴图和肩甲同一张，改色自动跟着变 | `uv_part.py` `place_prop.py` |
| 靴子 | Bel 的露趾靴换成 Vindictus（Defying Fate）Fiona PCF_067 的全板甲护胫 + 龙翼膝甲 + 尖头铁靴（`4_Foot`）；供体没有身体，用 `--donor-body-pmx` 指到 Fiona 的裸体 PMX 做贴合 | 换装插件 |
| 剑的位置 | `place_sword.py --centre-x -12`：整把剑往右挪 12 cm，龙头从马尾后面露出来 | `place_sword.py` |
| 项链 | Sanyaa 吊坠材质在脖子后面那截（像纹身）用 `cut_y.py --axis z --max-y 2.5` 切掉 | `cut_y.py` |
| 头发 | 铂金再白一点 | `recolor2.py` |

```powershell
python $V\uv_part.py donors\Miri_DragonRises_HD\miri_split.pmx donors\Miri_DragonRises_HD\miri_dragonhead.pmx "pc_female_dragon_rises_upper_metal_Bip001 L Shoulder" 0.0 0.14 0.17 0.43 --name dragon_head_src --largest
python $V\cut_y.py donors\Sanyaa_DarkKnight_HD\sanyaa_cut.pmx donors\Sanyaa_DarkKnight_HD\sanyaa_cut2.pmx pc_female_darknight_onepiece_metal_上半身 --axis z --max-y 2.5
python $T\cli.py donors\PCF_067\PCF_067.pmx build\b3_crown.pmx build4\e4_067.pmx --materials 4_Foot_0.1_0_0 --prefix vdf --split none --donor-body-pmx E:\game_export\Vindictus\Fiona\pmx\Fiona_BaseBody\Fiona_BaseBody_nophysics.pmx --donor-body "4_BaseBody-MI-pc-female-body05_0.1_0_0,4_BaseBody-MI-pc-female-handfoot05_0.1_0_0" --target-body pc_a01_nk_body
# 双龙爪 e5、肩甲 e6、裙子 e7、Sanyaa（sanyaa_cut2）e8 同 v3
python $V\crystal_blade.py build4\e8_san.pmx build4\f9_blade.pmx wp_a08_l Point007_L --width 7 --thick 2.2 --remove-guard
python $V\place_prop.py donors\Miri_DragonRises_HD\miri_dragonhead.pmx dragon_head_src build4\f9_blade.pmx build4\f10_dragon.pmx --bone Point007_L --snout 0.12,-0.99,0 --up 0.99,0.12,0 --scale 7 --offset 5 --lift -4 --name dragon_head
python $V\place_sword.py build4\f10_dragon.pmx build4\f11_sword.pmx "wp_a08_l,crystal_blade,crystal_blade_shards,dragon_head" Point007_L --tilt 35 --gap 3 --centre-y 100 --centre-x -12
python $V\add_crystals.py build4\f11_sword.pmx build4\f12_crystals.pmx $V\crystals_orange4.json     # 膝盖的簇改吸附 vdf_4_Foot
# 粉晶、底板、改色（新增 PCF_067 靴子的规则：钢 → 黑紫、皮带 → 暗橙）、组装同前
```

坑：`uv_part.py` 第一次把矩形里零散的 2 个面也带上了，包围盒中心偏了 → 龙头放到剑柄上去；`--largest` 只留最大的连通块。
龙头的吻部 / 头顶方向是看渲染猜的（吻部 (0.12,-0.99,0)，头顶 (0.99,0.12,0)），第一次猜偏 30 度，按渲染里的歪斜角反推修正。

## v5（同日晚，用户「盔甲还是锐利一点，不要像石头」）

成品 `花木兰_水晶猎龙者_仿制v5.pmx`（贴图 `textures_v5\`）。v4 像石头的原因：肩甲改色用阈值把金色切成花斑状的橙 / 紫（原贴图是带划痕的金鳞），
水晶又是鼓肚的不规则块。改法：

| 项 | 做法 | 脚本 |
|---|---|---|
| 鳞甲贴图 | `recolor2.metal_smooth`：底色是暗紫金属，明度跟着**模糊后**的原亮度走（鳞片的明暗形体保留，花斑没了）；只有高通（原亮度 − 更大半径的模糊）超过阈值的鳞片边缘亮线变成橙色 —— 干净的橙色描边。Miri 肩甲 / 龙头、PCF_067 板甲靴都用这条 | `recolor2.py` |
| 水晶 | `"style": "sharp"`：几乎不抖动的细长六棱柱（长 / 半径 ≈ 8），尖端是干净的六面尖；肩上 12–22 cm、冠 13–21 cm；贴图加大相邻面的明暗差、一条硬亮线 | `add_crystals.py` `crystals_orange5.json` `crystals_pink5.json` |
| 材质 | `sharpen_materials.py`：盔甲 / 水晶材质开描边（0.55，深紫 / 暗红）、提高高光（盔甲 0.55/0.5/0.65 × 40，水晶 1/0.95/0.85 × 60）、加**加算**球面贴图（脚本生成：金属一个小而硬的高光斑，晶体高光 + 一点边缘亮） | `sharpen_materials.py` |

```powershell
python $V\add_crystals.py build4\f11_sword.pmx build4\g12_crystals.pmx $V\crystals_orange5.json
python $V\add_crystals.py build4\g12_crystals.pmx build4\g13_pink.pmx $V\crystals_pink5.json
# 底板、改色（metal_smooth）、组装同前 -> out\花木兰_水晶猎龙者_仿制v5.pmx
python $V\sharpen_materials.py out\花木兰_水晶猎龙者_仿制v5.pmx
```

坑：球面贴图第一版太亮（高光瓣 spec^18×0.55 + 宽的 spec^4×0.12 + 边缘光 0.18），整套盔甲发灰发亮像塑料；改成只留一个小硬高光（spec^28×0.30，边缘光 0.05）才是黑紫金属。
Blender 的 mmd_tools 着色器对加算球面贴图的表现和 MMD 接近，可以拿 `mat_views.py` 的渲染判断。

## v6（用户「大小也看看，太大了」）

`crystals_orange6.json` / `crystals_pink6.json` = v5 的 JSON 全部长度 / 半径 × 0.65、簇半径和埋深 × 0.8（肩上 8–14 cm、头冠角 9–14 cm）；
`place_prop.py --scale 5.5 --offset 4 --lift -3`（龙头 15 × 22 × 11 cm）。其余同 v5。成品 `花木兰_水晶猎龙者_仿制v6.pmx`。

## v7（用户给了游戏内 3D 展示视频 BV1iqKTepEDC，要按游戏里的 3D 还原）

游戏里的 3D 和原画的差别（`bili\model_closeups.jpg`）：全身黑甲（手臂肩到手全包、腿到脚全板甲、只露腰）、黑色尖刺肩甲尖端带橙晶、黑板甲裙衬橙色板片、
领口橙晶、整体近黑。改动：

| 项 | 做法 |
|---|---|
| 手臂 | Miul `upper_metal`（尖刺臂甲，右臂）`mirror_material.py` 镜像出左臂，和双龙爪一起贴合（`miul_mirror2.pmx`）；Miri 金鳞肩甲不要了（龙头仍从 Miri 肩甲抠） |
| 腿 | PCF_067 `4_Lower`（黑板甲裤）和 `4_Foot` 一次贴合（同样借 Fiona 裸体 PMX 当供体身体）；Sanyaa 短裤不要 |
| 水晶 | `crystals_orange7.json`：肩簇改吸附 Miul 臂甲（刺尖 (±20,152,2)、外侧 (±30,143,2)），胸口三颗橙晶代替粉晶，其余 v6 尺寸 |
| 颜色 | `metal_smooth` 底色更暗更灰（`base_s 0.38, base_v (0.07, 0.27)`）；Miri 裙摆红 → 黑紫 v×0.2；新贴图 `MI_PCF_067_lower_baked.png`（同靴子规则）、`pc_female_devilhunter_upper_metal_baked.png`（红 → 橙） |

B 站视频：yt-dlp 能解析，视频流在 `upos-sz-mirrorcosov` / `akamaized` 两个 CDN 都回 HTTP 567（风控页），音频流正常；
把 URL 的主机换成 `upos-sz-mirrorali.bilivideo.com`（路径和签名不动）、Referer 用视频页、带 `Range: bytes=0-`，curl 就 206 下来了；`ffmpeg -vf fps=1` 抽帧看。

## v8（用户「要完全一样，继续改」）

游戏帧放大（`bili\game_zoom.jpg`）：胯部是一圈黑板片、每片一块橙→黄火焰面板；腿黑甲、膝盖和小腿橙晶条；胸甲边缘橙色；白马尾到腰。

| 项 | 做法 | 脚本 |
|---|---|---|
| 板甲裙 | `tassets.py`：取腰线（`--top` ± 4 cm）皮肤顶点按角度算胯部半径，8 片板沿轮廓外 1.5 cm 挂下来、向外张 12°，每片 = 黑板（双面 + 边）+ 内嵌 72 % 的火焰面板（贴图左半黑、右半橙→黄渐变）；前后片 BDEF1 下半身，侧片 BDEF2 混 左足D / 右足D 最多 0.7 | `tassets.py` |
| 板甲裤 / 靴 | `--no-fit --min-gap 2`（贴合的皮肤包裹把膝甲小片拉碎）；a08 腿比 Fiona 粗、脚长，会顶出来 → `hide_skin.py --below-y 99` 删掉腿脚皮肤 | `hide_skin.py` |
| 小腿橙晶 | `crystals_orange8.json`：`shin_L` (±8,38,-10) 两颗、`shin2_L` (±8,28,-9) 一颗，镜像；胯部簇去掉（板甲裙自带橙面板） | — |
| 马尾 | `cut_hair.py --y 92 --jitter 8`：面质心低于 92 + 按 x/z 哈希的 0–8 cm 抖动就删，发尾错落 | `cut_hair.py` |
| 马甲 | 蓝花纹 → 橙色滚边（`SANYAA` 规则） | `recolor2.py` |

```powershell
python $T\cli.py donors\PCF_067\PCF_067.pmx build\b3_crown.pmx build8\m4_067.pmx --materials "4_Foot_0.1_0_0,4_Lower_0.1_0_0" --prefix vdf --split none --no-fit --min-gap 2 --donor-body-pmx ...\Fiona_BaseBody_nophysics.pmx --donor-body "4_BaseBody-MI-pc-female-body05_0.1_0_0,4_BaseBody-MI-pc-female-handfoot05_0.1_0_0" --target-body pc_a01_nk_body
python $V\tassets.py build8\m4_067.pmx build8\m4b_tass.pmx --skin pc_a01_nk_body --n 8 --top 101 --length 24 --width 11 --flare 12 --gap 1.5   # 先于删皮肤（要腰线皮肤）
python $V\hide_skin.py build8\m4b_tass.pmx build8\m4c_skin.pmx --skin pc_a01_nk_body --below-y 99
# Miul 臂甲 + 龙爪 m5、Sanyaa m8、剑 / 龙头 m9–m11 同 v7；
python $V\add_crystals.py build8\m11_sword.pmx build8\m12_crystals.pmx $V\crystals_orange8.json
python $V\under_plate.py ... ; python $V\cut_hair.py build8\m13_plate.pmx build8\m14_hair.pmx --materials "eve_MI_Hair_New_Ponytail_4,eve_MI_EVE_HR_01_TypeA" --y 92 --jitter 8
# 改色、组装、sharpen_materials（--metal 正则加上 tassets）
```

## v9（用户「肩甲也改成黑底橙晶片的样子」）

`add_crystals.py` 新样式 `"style": "plate"`（簇级或全局）：`shard_mesh_sharp(..., aniso=(2.2, 0.3))` 把六棱柱截面压扁成晶片，
放置时薄轴 = 吸附点的表面法线去掉生长方向的分量、宽轴 = 生长方向 × 薄轴，所以晶片宽面贴着甲面、尖端沿生长方向（法线 + `up_bias` 往上掰）。
`crystals_orange9.json`：Miul 臂甲四排晶片（(±20,152,2) 4 片、(±26,146,2) 4 片、(±30,140,3) 3 片、(±22,146,9) 2 片，长 6–11 cm），头冠 3 片晶翼（11–15 cm），
其余簇同 v8。成品 `花木兰_水晶猎龙者_仿制v9.pmx`。

## v10（2026-11-14，用户下了两个 Nexus mod：「把这两个mod转成高清材质的blender，然后衣服加入到这个木兰的改造中」）

两个 mod 先用 `scripts/pmx_tools/mod_import/` 转成 PMX + 高清 .blend（11-01），再挑零件拼进 v9，改成游戏里的黑底橙晶。

| 零件 | 来自 | 在 v10 里 | 改色（`recolor10.py`） |
|---|---|---|---|
| 头冠 | 怪物猎人世界 Velkhana `f_helm085`（两侧垂到肩上的长水晶耳坠用 `cut_bone.py` 按骨删掉） | 换掉 a08 翼冠，v9 的 3 片晶翼留着 | 整张按亮度 → 橙晶渐变（取自 `crystal_orange.png`） |
| 护臂 | Velkhana `f_arm085`（2 件） | 叠在 Miul 臂甲 / 龙爪上 | CMM 遮罩满红、低饱和的冰晶簇 → 橙晶；深蓝 → 黑 + 线稿变橙线；白甲 → 黑紫甲 + 细橙边 |
| 大腿甲 | Velkhana `f_leg085` 的 `_5_1` | 叠在 PCF_067 板甲裤上 | 深蓝 V 纹整块 → 橙色火焰（`panels="fill"`），像游戏里大腿的橙 V |
| 护腿 / 靴 | Velkhana `f_leg085` 的 `_6_0` | 换掉 PCF_067 的靴 | 深蓝 → 黑 + 橙线（`panels="lines"`）；膝盖冰刺（贴图上的两个矩形）→ 橙晶 |
| 领口 | Velkhana `f_body085` 的 `_4_0` / `_4_9` | 换掉 Sanyaa 的吊坠 | 同护腿 |
| 带角肩甲 | 上古卷轴 SE COCO Mulan `Shoulder_Metal` | 叠在 Miul 肩甲上 | 暗银 → 黑紫 + 橙边（`metal_smooth`） |

没用的：Velkhana 胸甲（SkimpyER 版只有胸下一圈）、腰部水晶垂饰（试过，和板甲裙叠在一起显乱）；COCO 的高领、蕾丝披肩、紫裙、手套、丝袜（游戏里没有）。
护腿换不换比过两版：换（A）膝盖有刺、黑甲上有橙纹；留 v9 的靴（B）小腿是光滑黑甲。选了 A。

**先修的工具**（第一次整套试搬只对了一半，原因都在骨架）：
- `mod_import/mod3_to_pmx.py`：MHW 骨盆根骨（function 13）原来叫「センター」，腰甲权重挂在它上面——a08 的センター在 43 cm，按骨名搬过去腰甲掉到小腿；
  脊椎 / 头也错了一节（function 2 = 上半身2、3 = 首、4 = 頭），胸甲、头冠低 5–27 cm。改成标准 MMD 树：全ての親（地面）→ 新的センター（无权重）→ 下半身 / 上半身，
  关节上的辅助骨把权重交给关节的 MMD 骨。
- `mod_import/nif_to_pmx.py`：Skyrim 的辅助骨（扭转、胸、臀、SMP 链）原来全挂在センター上；改成编号链的上一节，或离它最近的标准骨段；没蒙皮的形状节点不建骨。
- 两个转换器的骨都没有尾端（`displayConnection = -1`）：换装插件比不了骨的方向，T 字姿势的护臂只被逐段平移、不会转到 A 字。新的 `pmxlib.connect_tails()` 补上。
- 换装插件 `core.py`（0.4.1）：扭转骨（`左腕捩`、`右手捩1`……）按它在臂段上的比例对位（Skyrim 的上臂扭转骨在肩关节、a08 的在上臂 80 %，
  原来骨头对骨头把 COCO 的肩甲拉到了肘部）；不带物理的衣服骨不再按位置吸附到目标的物理骨（Velkhana 头冠的侧骨吸到了 a08 的耳饰骨和 Eve 的辫子骨）；
  只带衣服真正挂着的物理链（头冠挂在「頭」上，原来把供体头发的 17 个刚体也复制了一份）。

```powershell
# 1. 两个 mod 各自整套「按体形贴合」搬到 a08 的完整裸体（v9 删了腿部皮肤，不能直接贴合到 v9 上）
python $T\cli.py mods\velkhana_pmx2\Velkhana_SkimpyER_withskin.pmx build\b3_crown.pmx build11\q4_velk_fit.pmx --materials "<19 个盔甲材质>" --donor-body "f_body085_0000_Ch_Skin_Mt__7_10,f_leg085_0000_Ch_Skin_Mt__7_2" --target-body pc_a01_nk_body --split none --prefix vk
python $T\cli.py mods\cocomulan_pmx2\COCO_Mulan_clean.pmx build\b3_crown.pmx build11\q5_coco_fit.pmx --materials "Shoulder_Metal_3BA_sho_m,..." --donor-body "Dress_SMP_3BA_3BA,Gloves_3BA_Hands,Shoes_Feet" --target-body pc_a01_nk_body --split none --prefix coco
# 2. 挑出的零件原样移植到 v9（同一副骨架 = 恒等变换）
$G = "--no-fit --no-rotation --no-follow-body --min-gap 0 --split none --donor-body pc_a01_nk_body --target-body pc_a01_nk_body --prefix g"
python $T\cli.py build11\q4_velk_fit.pmx build8\n14_hair.pmx build11\r1_vk.pmx --materials "vk_f_helm085_...,vk_f_arm085_...,vk_f_leg085_..._6_0,vk_f_leg085_..._5_1,vk_f_body085_..._4_0,vk_f_body085_..._4_9" $G
python $T\cli.py build11\q5_coco_fit.pmx build11\r1_vk.pmx build11\r2_coco.pmx --materials "coco_Shoulder_Metal_3BA_sho_m" $G
# 3. 头冠耳坠、被替换的 v9 零件
python $V\cut_bone.py build11\r2_coco.pmx build11\r3_cut.pmx g_vk_f_helm085_0000_Ch_Pl_Standard_Mt__2_0 --bones "mhw_f_helm08_f153,Accessories_ear"
python $T\pick_cli.py build11\r3_cut.pmx build11\r4_v10.pmx --remove "a08_body2_00_body_mat_頭,vdf_4_Foot_0.1_0_0,san_pc_female_darknight_onepiece_metal_上半身"
# v9 给 PCF_067 靴子加的膝盖 / 小腿晶簇换了护腿后只露出几个小橙点：去掉（膝盖的橙晶现在是 Velkhana 护腿的冰刺）
python $V\cut_y.py build11\r4_v10.pmx build11\r5_v10.pmx crystals --min-y 70
# 4. 改色、组装、双面、锐化
python $V\recolor2.py build11\textures; python $V\recolor10.py build11\textures mods\velkhana_png
python $V\assemble2.py build11\r5_v10.pmx out_v10 花木兰_水晶猎龙者_仿制v10
python $V\mat_flags.py out_v10\花木兰_水晶猎龙者_仿制v10.pmx --double "^g_(vk|coco)_"
python $V\sharpen_materials.py out_v10\花木兰_水晶猎龙者_仿制v10.pmx --metal "^(miri_|miul_|vdf_|san_|a08_body2|wp_a08|dragon_head$|chest_plate|tassets|g_vk_f_(arm|leg|body)|g_coco_)" --crystal "^(crystals|crystal_pink|crystal_blade|crystal_blade_shards|dragon_head_crystal|g_vk_f_helm.*)$"
```

新脚本：`recolor10.py`（上表的改色）、`cut_bone.py`（按挂的骨删一个材质里的面）、`mat_flags.py`（按正则设双面 / toon）、
`mat_shots.py`（一次导入渲染多组特写，每组可以隐藏某些材质——拿来比 A / B 方案）、`probe_mats.py` / `probe_weights.py`（列材质包围盒、看一个材质挂在哪些骨上）。

## 还可以改的

鳞甲裙没有物理（Miri 原模型里裙子就是刚性的）；板甲靴脚踝处是 Fiona 的脚型，和 a08 的脚有一点缝；鳞甲贴图上还有少量划痕造成的橙色小点（`rim_thresh` 调高一点就没了，代价是边线变细）。
