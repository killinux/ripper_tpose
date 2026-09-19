# Vindictus: Defying Fate（2024-03 Pre-Alpha）模型导出

Nexon 的《洛奇英雄传：反抗命运》还没发售（Steam 商店页写 2027）。能拿到的只有 2024-03-14
那次 Pre-Alpha 的客户端（archive.org 项目 `vindictus-defying-fate.-7z`，14.1 GB 7z）；2025-06 的
Alpha Demo（Steam `3576170`）测试结束后被替换成 348 MB 空壳，已经拿不到了。本目录针对
Pre-Alpha 客户端：**UE 5.3、IoStore（utoc/ucas）、Oodle 压缩、索引 AES 加密**。

## 快速开始

所有命令都在本目录里跑（PowerShell 先 `cd 〈仓库〉\scripts\vindictus`）。

### 看有哪些模型

```powershell
python .\list_models.py                             # 全表：id / kind / body / 部件数 / umodel 已导 / blend 已建
python .\list_models.py --kind outfit               # 只看一类：player / outfit / base / monster / npc
python .\list_models.py --resolve PCF_003 --json    # 某一个模型：每个部件的包路径、PSK 是否已导
python .\list_models.py --raw --path-filter /Character/AI/   # 容器里的原始路径（找没归类到的东西）
.\export_model.ps1 -List                            # 同一张表
```

直接解密并读游戏 `Paks\*.utoc` 的目录索引，不开任何工具。当前 36 个模型：`Fiona`、`Lethita`、
女装 `PCF_001`…`PCF_067` + `Shiningwill_legacy`、男装 `PCM_00x_Temp`、`Fiona_BaseBody` /
`PCM_BaseBody`、13 只怪（如 `Gnoll_type3_Tribe_Boss_01`）、2 个 NPC。

### 导出一个模型

```powershell
.\export_model.ps1 Fiona                 # 主角默认装
.\export_model.ps1 PCF_003               # 一套服装（自动配 Fiona 的脸和头发）
.\export_model.ps1 PCF_067 -Force        # 已导过想重做：重导包 + 重建 blend
.\export_model.ps1 Gnoll_type3_Tribe_Boss_01 -NoPreview
```

一条命令做完三步：`list_models.py` 解析包 → UE Viewer 逐包导出 PSK + PNG + 材质参数到
`D:\vindictus_exports\umodel_exports\` → Blender 无头跑 `build_blend.py` 合骨架、建材质、渲预览。
结束时打印骨骼数、各部件顶点、材质/贴图数、告警。产物：

```text
D:\vindictus_exports\blend\<id>\<id>.blend       一副骨架 + 全部部件 + 材质
D:\vindictus_exports\blend\<id>\textures\        贴图
D:\vindictus_exports\blend\<id>\preview.png / preview_face.png
```

整个 `blend\<id>\` 目录可以直接拷给别人。常用参数：`-Force`（重做）、`-NoBlend`（只到 UE Viewer）、
`-NoPreview`、`-Smooth`（平滑法线）、`-IncludeWeapons`（把武器并进来）；路径都有默认值
（`-GameRoot E:\tools\vindictus`、`-ExportRoot D:\vindictus_exports`、`-UmodelExe`、`-BlenderExe`）。

### 批量

```powershell
# 先顺序把包导完（UE Viewer 并发会互相覆盖共享贴图，这一步不能并行）
python .\list_models.py --kind outfit --json | ConvertFrom-Json | Where-Object body -eq PCF | ForEach-Object { .\export_model.ps1 $_.id -NoBlend }
# 再分几路并行跑 Blender，每套 2–3 分钟
foreach ($id in 'PCF_001','PCF_002','PCF_003') { .\export_model.ps1 $id }
```

### 更新画廊

```powershell
cd html
python .\collect_manifest.py     # 汇总 blend\*\build.log
python .\make_gallery.py         # -> html\index.html
```

### 前提（只做一次）

- 客户端在 `E:\tools\vindictus`，UE Viewer 用 `E:\tools\umodel_specific\materials\umodel_materials_ue5.exe`，
  Blender 3.6 装了 `io_scene_psk_psa`——本机都已就位，细节见下面「已验证环境」。
- AES key：脚本从 `VINDICTUS_AES_KEY` 环境变量或 `E:\tools\vindictus\_download\aes_key.txt` 读。
  换机器或丢了就 `python .\find_aes_key.py --out <路径>` 重新算（80 秒）。key 别放进仓库。

## 已验证环境

```text
客户端：E:\tools\vindictus（Vindictus.exe 为游戏根；Paks 在 Vindictus\Content\Paks，ucas 15.04 GB）
UE Viewer：spiritovod 的 UE5 specific build，umodel_materials_ue5.exe（build 1579 based fix282，2026-09-05，自带 Oodle）
            E:\tools\umodel_specific\materials\umodel_materials_ue5.exe
Blender：3.6.15 + io_scene_psk_psa 5.0.6（PSK/PSKX 导入器）
Python：3.13 + cryptography（解 utoc 目录索引用）
输出：D:\vindictus_exports
```

## AES key（不在仓库里）

pak/utoc 的索引用主 key（GUID 全 0）加密。key **只放本地**，脚本按下面顺序取：

1. 环境变量 `VINDICTUS_AES_KEY`（`0x` + 64 位十六进制）；
2. `-AesKeyFile`（默认 `E:\tools\vindictus\_download\aes_key.txt`，一行）。

`export_model.ps1` 把 key 写进临时文件再以 `-aes=@file` 交给 UE Viewer，命令行里不出现 key。
仓库、CHANGELOG、画廊页面里都不能出现 key（和 FF7 Remake 的规矩一样）。

key 不是明文躺在 exe 里的：`Vindictus.exe` 用 8 条 `mov dword [..], imm32` 指令把 32 字节拼出来
（`.text` 文件偏移 `0x47745EB`），所以「找连续 32 字节」的扫描器找不到。`find_aes_key.py` 按指令
模式（imm64×4 / imm32×8 / imm8×32 / 成对 xmm 常量）重组候选，再拿 `Vindictus-Windows.pak`
的加密索引试解密，解出 `../../../` 挂载点即命中（先扫一遍连续窗口再扫指令模式，共约 80 秒）：

```powershell
python find_aes_key.py            # 默认扫 E:\tools\vindictus 的 exe + pak，命中后写 aes_key.txt 到 --out
python find_aes_key.py --exe <Game>.exe --pak <any>.pak --out D:\keys\game_aes.txt
```

## 三个脚本

### `export_model.ps1`（一键：UE Viewer → Blender）

```powershell
.\export_model.ps1 -List                 # 模型清单 + 导出状态（= list_models.py）
.\export_model.ps1 Fiona                 # 女主：脸 + 发 + Shiningwill 全套（Upper/Lower/Hand/Foot）
.\export_model.ps1 Lethita               # 男主：脸 + 发 + 盔甲（含 Head）
.\export_model.ps1 PCF_067 -Force        # 女服装 067 + Fiona 脸/发，重建
.\export_model.ps1 Gnoll_type3_Tribe_Boss_01 -NoPreview
```

步骤：

1. `list_models.py --resolve <id> --json` 解析出该模型的骨骼网格包（Content 相对路径，
   UE Viewer 接受 `VindictusRoot/Character/.../SK_xxx` 这种写法，避免 178 个重名 stem 的歧义）；
2. 对缺失的包逐个执行 `umodel -game=ue5.3 -path=<Paks> -aes=@tmp -export -png -out=<ExportRoot>\umodel_exports <package>`
   → PSK/PSKX + PNG 贴图 + `.mat`/`.props.txt`（材质实例的贴图、向量、标量参数）；
3. 写 `<ExportRoot>\blend\<id>\spec.json`，无头跑 `build_blend.py`；解析 `VINDICTUS_REPORT=` 行打印
   骨骼数、各部件顶点数、材质/贴图数、未解析贴图、警告。

参数：`-GameRoot`、`-ExportRoot`、`-UmodelExe`、`-BlenderExe`、`-AesKeyFile`、`-PythonExe`、
`-IncludeWeapons`（把武器也并进来）、`-Force`（重导 + 重建）、`-NoBlend`、`-NoPreview`、
`-Smooth`（丢掉 PSK 自带的拆分法线改平滑着色）。输出已存在且未 `-Force` 时跳过。

### `list_models.py`（清单）

直接解密并解析 Paks 下每个 `.utoc` 的 IoStore 目录索引（TOC v5：ChunkIds → OffsetLengths →
PerfectHashSeeds → ChunksWithoutPerfectHash → CompressionBlocks → 方法名 → 签名块 → 目录索引），
不需要 UE Viewer 在场。索引只有路径没有类型，所以「部件」= `Model/` 目录下名为 `SK_*` 且不是
`_Skeleton/_Physics/_PhysicsAsset` 的资源。按游戏的拼装方式分组：

| kind | 目录 | 组成 |
| --- | --- | --- |
| player | `Character/Player/<Name>/` | `Face/Model/SK_<Name>_Face01` + `SK_<Name>_Hair01` + `Armor/Model/SK_<Name>_*_master` |
| outfit | `Character/Outfit/PC{F,M}_Outfit/<Id>/Model/` | 服装部件 + 对应身体的脸/发（PCF→Fiona，PCM→Lethita；由 UE Viewer 加载的骨架 `SK_PCF/PCM_BaseBody01_Skeleton` 核实）；`Player/Outfit/<Name>/Mesh/` 下的旧版整套记作 `<Name>_legacy` |
| base | `BaseBody_PCM` 四件 / Fiona `SK_female_base` | 裸体基础身体 + 脸/发 |
| monster | `Character/AI/<Race>/<Type>/<Variant>/Model/` | 目录下全部 SK（武器标为 weapon） |
| npc | `Character/Npc/**` | 单个 SK |

```powershell
python list_models.py                         # 表：id / kind / body / 部件数 / umodel 已导 / blend 已建
python list_models.py --json --kind outfit
python list_models.py --resolve PCF_067 --json
python list_models.py --raw --path-filter /Character/AI/   # 原始路径
```

武器（`Weapon/` 下的 SK）默认放在 `extras`，`--include-weapons` 才并入部件。

### `build_blend.py`（Blender 3.6 无头组装）

```powershell
blender --background --factory-startup --python build_blend.py -- --spec spec.json [--no-preview] [--smooth]
```

1. 逐个导入 PSK（`io_scene_psk_psa`，材质按 PSK 的 MATT 槽命名，同名复用）；
2. **合并骨架**：UE Viewer 给每个网格导的是它自己的参考骨架子集（Fiona 脸 658 根、头发 274、
   上身 531、脚 30……），取最多的一副为底，其余按名字补缺（父子关系、rest 变换照抄），所有网格
   重新绑定到这一副——Fiona 合成 1415 根一副可摆姿势的骨架，共享骨骼 rest 位置偏差 0；
3. **材质**从 `.mat`（Diffuse/Normal/Opacity/Other[n]）和 `.props.txt`（贴图参数名、向量、标量、Parent）重建：

| 母材质 | 处理 |
| --- | --- |
| `M_PC_Outfit` 服装 / 怪物 | `_D` 基色（有 Opacity 时 alpha 作 UE Masked 裁切，阈值 1/3）、`_N` 法线（翻 G 通道）、`_ORM`/`_ARM`：G 粗糙度、B 金属度 |
| `M_PC_Skin_Body` / `M_PC_Skin_Head` 皮肤 | `_D` × `Basecolor Tint`、`_N`（强度 0.6）、少量次表面；`_Mask` 未用 |
| `M_PC_Hair` 头发卡片 | `ODI` 的 R 作 alpha（HASHED），`FR` 的 B（发根→发梢）驱动 ColorRamp，颜色取实例的 `Color Root/Mid/Tip` |
| `M_PC_Skin_Eyebrow` 眉毛/睫毛 | `T_Eyebrow01_ODI` 的 R 作 alpha，深色 |
| `M_PC_Skin_EyeRefractive_Old`（Fiona）/ `M_PC_Skin_Eye`（Lethita）眼球 | `build_eye()`：巩膜贴图 × 血丝贴图（0.4）；虹膜是**程序化**的——以 UV 中心半径 0.2 为虹膜盘（MetaHuman 惯例），两种虹膜色沿半径渐变（Fiona：实例的 `IrisColor1/2 U,V` 在 `T_PC_Iris_color_picker` 上采样，**采样值是 sRGB 编码要先转线性**，再乘 `IrisBrightness`×1.35；Lethita：`Iris Color Inner/Outer` 向量），× 虹膜贴图 G 通道的纤维结构（`T_Iris_A_M` B 通道是径向渐变、G 是纤维；`T_EyeMap01` R 渐变、G 纤维），外缘 limbus 变暗（`LimbusDarkAmount`+0.1），瞳孔按半径 0.32×`PupilScale` 抠黑；粗糙度 0.12、高光 0.5、`T_PC_Eye_N` 法线 0.4 |
| 眼部遮蔽壳 / 泪线 / 假反射片 | 半透明黑 0.12（无高光）/ 透明高光 / 贴图 alpha × 0.4 |
| `M_Outfit`（`Character/public/`，NPC 套装，`PCM_00x_Temp` 男装复用）**分层材质** | 没有基色贴图：`Sub Mat Map` 的 R 选子材质 A（黑）/B（白）、G 选 C，每个子材质是一个纯色 `A/B/C L1 Color`；`GDO Map` 的 R 是灰度细节（0.5 为中性，×2 乘上去）、B 是不透明度（CLIP）；有 `Layer Color Map` 时直接当基色；`ARM Map`、`Normal Map` 同普通 PBR。`T_White_MK` 当 Sub Mat Map 表示整件都是 B |
| `M_Mob_Base` / `M_Mob_Outfit` / `M_NPC_Outfit`（怪物、NPC） | 参数名 `BaseColor / Opacity`、`ARM / E`、`Normal Map`；基色乘 `Basecolor Brightness`（怪物 D 图故意做得很暗，2–3.5 倍是常态）并按 `Basecolor Saturation` 去饱和、再乘 `Basecolor Tint`；粗糙度通道重映射到 `[Roughness Min, Roughness Max]`，金属度乘 `Metallic Intensity`。`Basecolor Contrast`、`Emissive` 没有用 |
| `M_Mob_Skin_Body_Old`（狗头人皮肤） | 走皮肤分支（母板名含 skin）：`BaseColor` × 亮度，`Mask`（DRCS）未用 |
| `MA_HairStyle` 怪物毛发卡片 | `Alpha`（`Fur_A`）R 作 alpha（HASHED），`Root`（`Fur_root`，发根处白）反相驱动 `RootColor → TipColor` 渐变，颜色乘 `Brightness` 但把最大通道压到 0.8 以内（Carminegust 红毛 ×3 会成粉色）；`Fur_Depth/Direction/ID/Gradient`、`DyeColor` 没有用 |
| `M_EyeRefractive`（怪物眼球） | 与 Fiona 的 MetaHuman 眼一样的参数集，直接走 `build_eye()`（`IrisColor1/2 U,V` 在 `T_PC_Iris_color_picker` 采样）；`M_EyeOcclusion` 走遮蔽壳 |

4. 用到的贴图复制到 `textures\`，`.blend` 存相对路径（整个 `<ExportRoot>\blend\<id>\` 目录可单独拷走）；
5. 渲 `preview.png`（全身 900×1400）与 `preview_face.png`（头骨 `head` 取景）。相机方向不是写死的
   +X：UE 骨骼网格资源朝 -Y，脚本用 `foot_l/r → ball_l/r` 的方向判断角色朝向再放相机。
6. 只有一根骨的部件不蒙皮，挂到插槽骨上：那根骨在底骨架里存在就挂那根（豺狼人的锤子
   `Anim_Attachment_RH` → 右手，带骨的完整 rest 变换）；只有 `root` 的（Lethita 头发）挂到 `head`（只平移）。

## 输出

```text
D:\vindictus_exports\umodel_exports\VindictusRoot\...   UE Viewer 原始导出（按游戏目录结构）
D:\vindictus_exports\blend\<id>\<id>.blend               一副骨架 + 全部部件 + 材质
D:\vindictus_exports\blend\<id>\textures\                贴图（PNG）
D:\vindictus_exports\blend\<id>\preview.png / preview_face.png / spec.json / build.log
D:\vindictus_exports\vindictus_models_manifest.json      画廊 manifest；_gallery\thumbs\ 缩略图
```

## 画廊（`html/`）

```powershell
cd html
python .\collect_manifest.py     # 读 blend\*\build.log 的 VINDICTUS_REPORT -> manifest（只有路径和统计）
python .\make_gallery.py         # 缩略图写到导出根下，页面 -> html\index.html（自包含，file:// 链接）
```

和其它游戏的画廊同一套：卡片 = 预览 + 说明 + 部件 + 规格（顶点/面/骨骼/材质/贴图/体积）+ blend 路径
+ 脸部预览；徽章标出类型、身体、隐藏的头发、重定位过的部件数、告警；顶部可按类型/身体筛选、搜索。
页面底部是完整的手工导出教程（客户端来源、key 计算、三个脚本、批量、参数表、产物目录、坑）。
`NAMES` 表里的中文说明是看着预览写的——Pre-Alpha 资源没有正式服装名。

## 已知限制

- 静态网格贴图是 virtual texture，UE Viewer 导不出（角色不受影响）；Nanite 只有基础几何；
  umodel 不导 morph target（脸包里的 MetaHuman `DNAAsset` 也不导），面部没有形态键。
- 服装的 `Head` 部件五花八门：项链/颈圈（001、007、009）、耳机（002、004）、帽子（003、012）、发带（006）、
  发冠 + 头皮片（005，头发照常显示）、自带发型（001_Temp、008、010 里打包了 Fiona 的头发）、全盔（067、Lethita）。
  规则：Head 部件里有头发材质，或 `list_models.py` 的 `HEAD_REPLACES_HAIR`（067）标了的，才隐藏默认
  头发（仍留在文件里，`<id>_Hair`）；其余保留。几何启发式（贴头皮比例、盖脸比例）试过，分不开耳机/帽子和发型。
- 部分服装的部件绑在**另一版骨架**上（Head 的脊柱链到 head 差 6.9 cm，Shiningwill 旧版差 6 cm）：
  `build_blend.py` 先把该部件自己的骨架摆到底骨架的 rest 姿势再烘焙网格（等价于游戏运行时的蒙皮），
  报告里记为 `reposed_parts`。
- `Shiningwill_legacy` 整套和 Fiona 素体是 3ds Max Biped 骨架（`Root → Bip001_*`）。合并进 Fiona 的脸骨架
  （UE 命名，没有 Bip 骨）后它成了第二棵根子树，而且朝向和 UE 骨架差 90°（面朝 +X），直接合并会身体
  侧着、脸朝前。`align_secondary_hierarchies()` 把第二棵根子树连同绑在上面的网格按脚趾方向转到 UE
  朝向、再按 `Bip001_Head`→`head` 平移对齐（报告 `aligned_hierarchies`，日志里打印转正后的朝向）；旧装
  自带的旧发型是给旧头做的，会盖住新脸的眼睛，所以隐藏旧发型、保留默认头发。
- `SK_Fiona_Lower01_master` 里有一个 `PCF_005_Onepiece` 材质段，是 master 网格自带的，渲染上被裙甲盖住。
- 基础身体：`Fiona_BaseBody` 用的是 `Player/Fiona/Model/Mesh/SM_pc_fiona_basebody`（名字带 SM_ 其实是
  SkeletalMesh；旁边的 `SK_female_base` 反而是 Skeleton 资源，导不出网格）。它是旧版素体（白 T 恤 + 短裤，
  Biped 骨架，自带一个没贴图的旧头），脚本按上面的对齐规则转正后，把旧头/脖子（`Bip001_Head/Neck`
  权重的 5.8 万顶点）切掉换成现在的脸，领口处能看到接缝。`PCM_BaseBody` 是新骨架的四件，直接能用。
- 材质参数名匹配用整词：`"rma"` 曾经作为子串匹配到 `Normal Map`，把法线贴图当 ORM 接了进去
  （B 通道≈1 → 金属度 1），没有 ARM 参数的服装（PCF_012、旧版 Shiningwill 上衣、素体）全成了金属；
  `find_role(..., whole_words=True)` 修掉。
- `T_pc_fiona_basebody_01_D`（`M_female_skin_body_01` 的基色）是 virtual texture 导不出，这类皮肤材质用纯肤色代替；
  BC6H 贴图 UE Viewer 写成 `.hdr`（PCF_012 的 `_B` 基色），已按 `.hdr` 索引。
- 眼球是近似：没有折射（游戏用角膜折射 + 视差），虹膜半径 0.2 是按这批头的眼裂宽度定的
  （0.17 偏小、0.22 偏大），`IrisSaturation`（0.21）没有采用——按它做会灰掉；皮肤 `_Mask`、
  头发 `Specular Highlight Randomness` 等参数没有用上。
- 怪物/NPC 的材质母板（`M_Mob_*`、`M_NPC_Outfit`、`MA_HairStyle`、`M_EyeRefractive`、分层 `M_Outfit`）按上表
  近似，都是看参数名和贴图通道猜的，没有 UE 里的对照：毛发的 `Brightness` 语义不确定（"orange" 毛是 0.15、
  "black" 毛的发根色反而是浅的），Carminegust 的红毛偏粉。两只哥布林（`Goblin_Type2_FieldBoss02` 和
  `Goblin_type3_NamedBoss01` 是同一个 25 万顶点的网格）和 NPC `Male_Knight` 在包里**没有任何材质**，
  导出来是白模——不是导出问题，查过：`umodel -dump` 里两个 section 都是 `Material=None`，SK 包只
  import 骨架、PhysicsAsset 和 AnimBP（`umodel -save` 抠出原始包、扫 imported package names），角色蓝图
  `BP_Goblin_Type3_NamedBoss_01` 只引用 VFX、DataAsset、AIC、SK 和**豺狼人的** `ABP_Gnoll`，武器蓝图借的是
  `AS_Gnoll_Type1_NamedBoss01_weapon`，整个容器 `Character/AI/Goblin/` 下 180 条里没有一个 M_/MI_/T_，
  顶点色也全白——这版客户端里哥布林就是个占位高模。`NPCM_RoyalArmy_sword` 只有一把剑。多骨的武器
  （`Gnoll_Type2_Named_Boss_03` 的弓，16 根自己的骨）合并后留在原点。

## 已验证

- `Fiona`：6 部件 103,180 顶点，骨架 1415 根（合并 757），19 材质 41 贴图，0 未解析，rest 偏差 0。
- `Lethita`：7 部件，476 根（脸骨架 `SK_Lethita_Face01_Skeleton` 与 PCM 身体 rest 差 0.25 cm，可接受），19 材质 33 贴图。
- **全部 15 套女装**（Fiona 默认装、`Shiningwill_legacy`、`PCF_001`…`PCF_012`、`PCF_067`）一次批量导出：
  先 `-NoBlend` 顺序导 61 个包，再 3 路并行 Blender。逐张看过 `blend\*\preview.png`（拼图脚本在
  `_download` 之外的临时目录）：002/003/004/006/007/009/010/012 的部件都做了重定位烘焙（Head 6.9 cm、
  Upper/Lower 到脚趾 13 cm），帽子、耳机、颈圈位置正确；005/008/010/067 隐藏默认头发，其余保留；
  PCF_012 的 `.hdr` 基色生效；`PCF_001_Temp` 裤子是资源自带的彩虹占位贴图（WIP 服装），不是导出问题。
- **剩下的 12 个**（3 套男装 `PCM_001/002/004_Temp`、7 只怪、2 个 NPC）2026-09-19 一次导完，共 30 个 `.blend`：
  `PCM_001_Temp` 的整体网格 `SK_PCM_001_Temp`（把脸、发、五件都合在一起的副本）被 `list_models.py` 跳过；
  三套男装是 Swordwind / RoyalArmy 的 NPC 甲（分层材质，面甲、锁子甲、羽饰头盔、红披风都对）；四只豺狼人
  的毛、皮、甲、眼都有色，狗头人首领的重甲和钩爪正常；白模的三个见上一节。狗头人其余 6 条只有武器，没有导。
