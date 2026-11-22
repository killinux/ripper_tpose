# Stellar Blade 模型导出与 Blender 3.6 验证

Stellar Blade PC 版使用 UE4 IoStore。它与 FFVII Rebirth/Remake 的 profile、mapping
和资源路径都不同，因此本目录单独维护验证脚本。完整的 FModel、专用 UE Viewer 和
手动 Blender 流程见
[`docs/stellar-blade-extraction.md`](../../docs/stellar-blade-extraction.md)。

## 已验证环境

```text
游戏：Stellar Blade 1.4.1 / Steam build 19963153
游戏目录：D:\Program Files (x86)\Steam\steamapps\common\StellarBlade
FModel：4.4.4 b270829，GAME_StellarBlade
Blender：3.6.15
PSK 导入器：io_scene_psk_psa 5.0.6
头部格式：FModel UEFormat v9（Face_003，53 个 Morph）
```

## `export_eve.ps1`（一键封装）

与 `riseoferos/extract_character.ps1`、`export_nude_models.ps1` 相同的组织方式，
把下面的手动流程包成一条命令：

```powershell
.\export_eve.ps1              # 组装 + 验证（输出已存在时自动跳过）
.\export_eve.ps1 -List        # 查看组件清单与输出状态
.\export_eve.ps1 -Check       # 只检查全部输入，不执行任何导出
.\export_eve.ps1 -Force       # 重建 Blender 输出
.\export_eve.ps1 -RefreshHair -Force   # 先用专用 UE Viewer 重导头发再重建
```

脚本按顺序执行：

1. 检查 FModel 手动导出（身体 PSK、Face_003 `.uemodel`、身体漫反射 PNG，
   并校验 `ACTRHEAD`/`UEFORMAT` 文件头）。FModel 是 GUI 程序无法无头运行，
   缺失时打印精确的 FModel 配置步骤后退出。
2. 头发/马尾 PSK、马尾透明贴图、Face_003 贴图集缺失时，用专用 UE Viewer
   （`-UmodelExe`，默认 `C:\Tools\umodel_stellar_blade_v6.exe`）自动补导，
   并校验 `Found N game files` 数量以识别错误构建；`~mods` 内有 Mod 时告警。
3. 解析 Blender 3.6 兼容的 UEFormat 导入器源码：`-UEFormatSource` 未指定且
   本地不存在时，自动下载钉住的官方快照
   `58d1abf52d6b2e5ad8d00e7c31bc98495231e642`（`ueformat-blender36.patch`
   的制作基线；上游 main 已重构 `importer/logic.py`，不能跟踪 main）到
   `<ExportRoot>\_tools\` 并用 `git apply` 打补丁。
4. 无头运行下节的 `validate_eve.py`，解析 `STELLARBLADE_EVE_REPORT=` 结果行，
   输出组件统计、Morph 数与锚点误差。

主要参数：`-GameRoot`、`-ExportRoot`（默认 `D:\stellarblade_exports`）、
`-BlenderExe`、`-UmodelExe`、`-UEFormatSource`、`-OutputName`。

Eve 全部服装的编号→名称对照、粉色判定，以及**按包名一条命令导出任意服装的
示例**见 [`docs/stellar-blade-eve-outfits.md`](../../docs/stellar-blade-eve-outfits.md)。

## `list_models.py`（模型清单与未导出差集）

直接解析 Paks 下每个 `.utoc` 的 IoStore 目录索引（只读；Stellar Blade 索引未加密，
不需要 AES key，也不需要 FModel/UE Viewer 在场），列出全部包路径，并与
`D:\stellarblade_exports` 里已有的 `.psk/.uemodel/.fbx/.glb/.blend` 按文件名做差集：

```powershell
python .\list_models.py                        # 角色树下尚未导出的模型包
python .\list_models.py --include-exported     # 全表 + 每个包对应的本地导出文件
python .\list_models.py --glob 'CH_P_EVE_*'    # 只看 Eve 服装
python .\list_models.py --path-filter 'SB/Content/Art/' --csv models.csv
python .\list_models.py --all-files --path-filter '00_HR/'   # 原始路径列表
```

`.utoc` 目录索引只有路径没有资产类型，"模型包"判定是命名启发式（排除
Tex/MA/MI 贴图材质、AnimSequence/Facial/Montage 动画、PhysicsAsset/Collision、
CameraBone 等）；本机 1.4.1 实测：7 个 `.utoc` 共索引 224,322 个文件，
`SB/Content/Art/Character/` 下筛出约 1,957 个模型包候选（PC 384 / NPC 339 /
Monster 390 / Etc 610 / Generic 209 / Weapon 18），其中已导出 6 个 Eve 组件。
拿到包路径后按第 3/4 节用 FModel 或专用 UE Viewer 导出即可。

## `export_outfit.ps1`（任意服装一键出 Blender）

按包名把任意一套服装导成完整 `.blend`（服装身体 + Face_003 + 发型 + 马尾 +
短发束），本机已验证：

```powershell
.\export_outfit.ps1 CH_P_EVE_45_TypeB        # Pink Bear
.\export_outfit.ps1 CH_P_EVE_Nikke_06        # NIKKE Alice（DLC 同样直接用包名）
.\export_outfit.ps1 CH_P_EVE_20_TypeC -Force # 重建已有输出
```

流程：PSK 不存在时先用专用 UE Viewer 导出到
`<ExportRoot>\umodel_outfit_exports\`，再无头运行 `validate_eve.py`——
`--body-diffuse` 传服装贴图目录时会按材质名自动匹配各槽位的 `*_A` albedo
（如 `MI_CH_P_EVE_Nikke_06_UV2` → `CH_P_EVE_Nikke_06_UV2_A.png`）。输出
`blender\Eve_<包名>.blend` 与 `validation\Eve_<包名>.png/_face.png/.json`。

默认输出**单一主骨骼**（`Eve_Armature`）：各组件骨架合并进身体骨架，重名骨
去重（权重落到身体同名骨）、发型/马尾的 `Root` 改名为携带骨挂到
`SC_Hair`/`Bip001-Head`/`Ab-TL-HairB01` 锚点，整体可直接 pose（已通过转头
渲染验证）。要保留旧的"每组件独立骨架"验证结构，加 `-KeepSeparateArmatures`
（`export_eve.ps1` 同样支持；对应 `validate_eve.py` 的 `--merge-armatures`）。
依赖 `export_eve.ps1` 已跑过一次（共享的脸/发型/贴图与 UEFormat 快照、
`--alignment-reference` 用的标准验证 JSON 都来自它）。

## 全部服装批量（2026-09-05：146 套，含 10 套联动 DLC）

`export_outfit.ps1` 按包名循环即可；清单来自 `list_models.py`：本体
`--glob 'CH_P_EVE_*'`，DLC 加 `--path-filter 'SB/Content/DLC'`，去掉 `CtlRig / IKDefo /
LODSettings / Physics / Shadow / _sample / Test / Taper / NoHair / Clothdata` 和脸、发、牙的
部件包，再去掉 `CH_P_EVE_39_TYPE-A / A1`（四个材质槽全是 `MI_CH_Delete` 占位、贴图叫 `del`
的废弃开发网格），剩 146 个服装包（编号 01–63 及变体、7 个特殊目录、Nier 4 + Nikke 6）。
三路并行每套 7–16 s，PSK 已在时 6 s。

这一批修掉的三个问题（都在 `export_outfit.ps1` / `validate_eve.py` 里）：

| 症状 | 原因 | 处理 |
|---|---|---|
| 79 套报「UE Viewer produced no *.psk」 | 顶点多 / 多 UV 的网格 UE Viewer 写的是 `.pskx` | 查找时 `.psk` 与 `.pskx` 都认 |
| 20 / 26 装上头发时报 `Ab-TL-HairB01 is missing` | 目录下还有 `Temp\CH_P_EVE_20` 同名子包，按名导出只出了它，且它的骨架没有马尾锚点 | 查找排除 `\Temp\`；按名导不出网格时用 `list_models.py` 查出完整包路径再按路径导 |
| 01–06 系整身灰白、部分服装皮肤贴成布料 | 贴图只按 `*_A.png` 猜名；01–06 用共享的 `ScanCloth_*_D`，还导在别的服装目录下 | `find_material_albedo` 先读材质自己的 `.mat`：`Diffuse=` 是真颜色图就用它，是 `T_*` / 引擎图标 / `del` 之类就在其它槽位里找 `_D/_A/_BaseColor/_ADIR`，整个导出根（含 DLC_N 上一级）去找；猜名只作兜底，且猜名时惩罚材质名里没有的 TypeB/TypeC 换色标记（01_Body 原来会拿到 TypeB 的贴图） |
| 11_1（Raven 变体）头上两套头发 | 这个包自带 NA_53 的发型网格，管线又照常装上 Eve 默认发型/马尾 | 未处理，属已知局限；它自己的头发贴图已按 `.mat` 的 `_ADIR` 正确接上 |

画廊：`python html\collect_manifest.py`（读 `validation\*.json`，不开 Blender）+
`python html\make_gallery.py` → `html\index.html`；有 `xps\<名>\<名>.xps` / `pmx\<名>\<名>.pmx` 的卡片多出
「XPS」「PMX」两行和徽章，PMX 一行附回读预览（正面 / 表情 / 视线 / 跳舞）链接，页尾附录有「Nexus 服装 mod →
Blender / XPS / MMD」一节；亮预览由
`..\final\html\render_blend_preview.py -- D:\stellarblade_exports\blender --suffix _gallery` 补渲
（`validate_eve.py` 自己的渲染偏暗，仍保留在 `validation\`）。

## 打包给别人（`package_outfits.py`，2026-09-05：148 个独立文件夹）

`blender\Eve_*.blend` 的贴图是 `//..\umodel_*_exports\...` 相对外链，单拷一个 .blend 到别的机器
会整身丢图。`package_outfits.py` 把每个模型打成一个**自足的文件夹**，整个文件夹拷走就能开：

```
D:\stellarblade_exports\packages\Eve_CH_P_EVE_45_TypeB\
├─ Eve_CH_P_EVE_45_TypeB.blend   贴图全部改成 //textures/ 相对路径；对象上记录的源 PSK 路径也改成相对
├─ textures\                     材质节点里接着的 12–17 张 PNG（服装 + 脸 + 眼 + 发）
│  └─ extra\                     服装自己 Textures\ 目录里没接节点的 _N / _ORM / _Mask / 换色贴图
├─ preview.png / preview_face.png
├─ README.txt                    中英双语：内容、怎么摆姿势 / 表情 / 导出、材质说明、来源
└─ package.json                  贴图来源清单 + 网格统计
```

```powershell
cd E:\code\othercode\ripper_tpose\scripts\stellarblade
blender --background --factory-startup --python package_outfits.py            # 全部，已有 package.json 的跳过
blender --background --factory-startup --python package_outfits.py -- --only Eve_CH_P_EVE_45_TypeB --force
blender --background --factory-startup --python package_outfits.py -- --lane 0 --lanes 3   # 三路并行各开一个（0/1/2）
python package_outfits.py --index                                             # 汇总 packages\README.md + packages_index.json
```

`--factory-startup` 必须带：不带的话存进 .blend 的界面来自本机启动文件（中文工作区名、文件浏览器里的
`C:\Users\<你>\Documents`）。即使带了，Blender 也会把文件浏览器默认目录填成本机 Documents，脚本在最终
保存后按字节把用户目录 / 导出根的残留填成 NUL（`scrub_blend_bytes`，未压缩 .blend 的定长缓冲区，不改结构）。

| 参数 | 作用 |
|---|---|
| `--only A B` | 只打这些 label（`blender\` 里的文件名去掉 .blend） |
| `--force` | 已有的重做（会先清空该包的 `textures\`） |
| `--lane I --lanes N` | 按排序后的 label 分片并行 |
| `--no-extra` | 不附带 `textures\extra\`（每包少 50–100 MB） |
| `--zip` | 每个文件夹再打一个同名 .zip 到 `packages\` |
| `--include-probe` | 连 `Eve_Face003_UEFormat36_test`（UEFormat 导入探针，无贴图）也打 |
| `--index` | 不开 Blender，扫 `package.json` 写总索引 |

实现：`open_mainfile` → 收集每张 `FILE` 图片的来源，同名不同源的**两边都**加上一级目录名前缀
（`Old_Tex_P_EVE_Head_A.png` / `CH_P_EVE_Head_Tex_P_EVE_Head_A.png`，与枚举顺序无关）→ 拷进 `textures\`
→ 图片路径先指到新绝对位置 → `save_as_mainfile` 到目标 → `bpy.ops.file.make_paths_relative()` →
路径统一成 `//textures/x.png` 正斜杠 → 再存一次 → **重新打开校验**每张图都在包内；对象 / 材质自定义
属性里以导出根开头的绝对路径改成相对、Scene 上 `faceit_*` 残留删掉（`relativize_custom_props`），
`save_version=0` 不留 `.blend1`。`textures\extra\` 从已接贴图的来源往上找 `CH_P_EVE_<服装>` 目录
（排除共享的 Head / Hair / ReferenceBody），整棵树递归收（01 系在 `Tex\Body`、`Tex\Boost`，49_TypeB
在 `Textures\TypeB`）。网格 / 顶点 / 骨骼 / 表情直接从打开的文件数，验证 JSON 只用来交叉核对。
`package.json` 做完才写（`.part` + `os.replace`），重做先删旧的，中途被杀不会留下假的"已完成"；
`--zip` 在 marker 写完后打包。148 个包三路并行约 10 分钟。
校验：14 个样本包拷到 C 盘另一路径，用 `--factory-startup`（不带任何插件）打开、逐图加载、
从副本渲染与预览比对，审查代理另外在 Blender 4.5 / 5.1 打开无误；全部 .blend 二进制里已无
用户目录和 `stellarblade_exports` 字样。60 / 60NH 原来接了 CH_P_EVE_55 的同名 `CH_P_EVE_BB_A.png`
（`validate_eve._export_index` 同名只记第一个），已改成优先取服装自己目录的并重导。
画廊卡片上的「独立包」一行就是这个文件夹（`collect_manifest.py` 记 `packageDir`）。

## 裸模（EveOriginalProportions Mod）

原版没有 nude 资产；裸模来自本机安装的 EveOriginalProportions Mod（覆盖
`CH_P_EVE_InnerSuit`）。四个变体已用专用 UE Viewer 导出到
`D:\stellarblade_exports\umodel_mod_exports\<variant>\`（Mod 是独立 IoStore
三件套，导出时需在 staging 目录放游戏的 `global.utoc/ucas`）。组装复用
`validate_eve.py`，但 UE Viewer PSK 不含 socket、裸模骨架缺 `SC_Hair`，需加
`--alignment-reference <标准验证报告.json>` 复用其中记录的发型根变换；马尾
仍按共有的 `Ab-TL-HairB01` 原生对齐。产物：
`D:\stellarblade_exports\blender\Eve_Nude_Barefoot.blend`。

## Nexus 服装 Mod（`build_standalone.py`，2026-09-24：Vindictus Fiona）

以 [stellarblade/mods/1145「Vindictus Fiona」](https://www.nexusmods.com/stellarblade/mods/1145)（zdimwit）为例，
一个 Mod = 一套 IoStore 三件套（`FionaV_p.pak/.utoc/.ucas`）。流程：

1. **装进游戏**：三件套拷到 `SB\Content\Paks\~mods\`。zip 原件留在下载目录不动，先拷到
   `D:\stellarblade_exports\mods\<名字>\` 再解。
2. **看它顶替了什么**：`python list_models.py --paks <解压目录> --all-files --path-filter ''`。
   Mod 的挂载名可以是任意的（这里是 `test/Content/...`），IoStore 按包路径哈希覆盖，所以看
   `Art/Character/PC/CH_P_EVE_XX` 那一段即可。Fiona 顶替的是 **CH_P_EVE_09（Planet Diving Suit
   7th）**，另外改了 16 / 21 的几个材质实例。以后导原版 09 时要先把它从 `~mods` 挪开。
3. **导出**：staging 目录里放 Mod 三件套 + 游戏的 `global.utoc/ucas`，
   `umodel_stellar_blade_v6.exe -export -path=<staging> -game=ue4.26 -noanim -psk -png -out=<...> "*"`
   → `umodel_mod_exports\<名字>\`（42/42 对象，2 秒）。
4. **判断头归谁**：按材质槽算包围盒。Fiona 的 `face` 槽只在 z 140–154（脖子/下颌过渡），`head` 槽是
   发冠和羽毛——**没有脸**，游戏里仍显示 Eve 的 Face_003 和发型。这种就先用 `validate_eve.py` 按普通
   服装组装（Face_003 + 发型 + 马尾挂到 Mod 骨架上）。真正自带整颗头的 Mod 则直接
   `build_standalone.py --psk ...` 单独出，避免两个头。
5. **重建材质**：`validate_eve.py` 按材质名猜贴图，Mod 作者的材质名是 `body` / `face` / `amt` / `phy`
   这种通用名，会猜成别的图（腿上一片黄粉花纹、裙子全黑）。`build_standalone.py --blend <组装好的
   .blend> --object Eve_Body_Mesh_01` 只对这个网格按 UE Viewer 的 `.mat` 精确接图：Diffuse（alpha 真有
   镂空才接 Alpha，HASHED）、Normal（DirectX 翻绿）、`Other[0]=*_ARM`（G 粗糙 / B 金属）；颜色图是纯黑
   的槽（`phy` 物理代理，贴 `a.png`）拆成隐藏对象，不删。
6. `package_outfits.py -- --only Eve_Mod_<名字> --force` 打成自足文件夹。报「validation meshes=5 but
   blend has 6」是预期的——多出来的就是那个隐藏的代理对象。

产物：`D:\stellarblade_exports\packages\Eve_Mod_VindictusFiona\`（377 MB，30 张贴图 + 15 张附带）。
朝向：Biped 骨名带连字符（`Bip001-L-Toe0`），按「脚趾指向」判前方时要按词匹配，不然人是侧着的。

### CNS 类 Mod（2026-09-25：Gantz Reika，mod 3561）

名字里带「CNS」的 mod 是给 [CNS - Custom Nanosuit System](https://www.nexusmods.com/stellarblade/mods/1496)
（DekitaRPG）做的：**不顶替任何原版服装**，资源放在自己的路径下（`/Game/OutfitMods/GantzReika/...`），
另附一个 `*.dekcns.json` 登记显示名和各变体的网格路径（`OutfitPaths`，这里 A / B 两个版本）。
与上面流程的不同点：

- **安装**：zip 里的整个文件夹（三件套 + json）放进 `~mods\`（子文件夹可以）。游戏里要看到还得装
  UE4SS for Stellar Blade（`ue4ss\` + `dwmapi.dll` 放 `SB\Binaries\Win64`）和 CNS 本体（`SB` 文件夹并进游戏根目录），
  按 N 键开 CNS 菜单换装。这两个都要自己去 Nexus 下。
- **导出不用挪 `~mods`**：不覆盖原版，原版照常导。
- **每个变体一个网格**：`GantzReika_A.psk` / `_B.psk`，分别跑 `validate_eve.py`（`--body` 指 PSK、
  `--body-diffuse` 指 mod 的导出目录，其余参数同 `export_outfit.ps1`），输出 `Eve_Mod_GantzReika_A/B`。
  两个都只到脖子（z ≤ 151 cm），用 Eve 的 Face_003 + 发型。
- **材质**：贴图叫 `_Base_Color` / `_Normal_OpenGL_DX` / `_ORM` / `_Emissive`，mod 自带一套皮肤
  `EveSKin`（`_N_ORSS`）。`build_standalone.py` 为此补了三点：`_ORM` 同 `_ARM`（G 粗糙 / B 金属），`_ORSS` 只取
  G 作粗糙度，`Emissive` 接 Principled 自发光（强度 2，战斗服上的蓝色光圈）。
- XPS / PMX 与 Fiona 相同，对 `packages\Eve_Mod_GantzReika_A|B\*.blend` 各跑一次。

### 只换一套衣服网格的 mod：`swap_mod_mesh.py`（2026-11-14：Gantz Sling suit）

[Gantz Sling suit](https://www.patreon.com/posts/134367203)（Patreon「m.tsqn」，免费帖）是 IoStore 覆盖型 mod，四个包都只换一套原版衣服的骨骼网格和其中几个材质实例：

| 包 | 换掉的原版 | 网格做在哪个骨架上 | 产物 |
|---|---|---|---|
| `gantz_sling_suit.zip` | `CH_P_EVE_15_V02_TypeB`（Orca Techie） | 15 号 | `Eve_Mod_GantzSling` |
| `gantz_sling_suit_more_jiggle.zip` | 同上，网格逐字节相同，只是 `CH_P_EVE_62_AnimBP` 摇得更厉害 | — | 只出 PMX `Eve_Mod_GantzSling_MoreJiggle`（`--bust-spring 45 --bust-limits 24,8,18`） |
| `breaks_zss_suit_gantz_sling_suit_red_keyhole_suit.zip` | `CH_P_EVE_29`（Keyhole Suit），连 29_03 那组贴图也换了 | 62 号（泳装） | `Eve_Mod_GantzSling_RedKeyholeSuit` |
| `breaks_zss_suit_gantz_sling_keyhole_dress.zip` | `CH_P_EVE_29` | 62 号 | `Eve_Mod_GantzSling_KeyholeDress` |

`validate_eve.py` 要的公共文件（FModel 导出的 Face_003 等）已经不在 D 盘，`build_standalone.py` 又会把 mod 没带的材质槽（原版皮肤）当代理藏掉，所以另写了这个脚本：

```powershell
# 1. UE Viewer 导出 mod（staging = mod 三件套 + 游戏的 global.utoc/ucas）
umodel_stellar_blade_v6.exe -export -path=D:\sbm\st_<包> -game=ue4.26 -noanim -psk -png -out=D:\sbm\out_<包> "*"
# 2. 材质槽的真名：UE Viewer 只看 mod 包，解析不到游戏里的材质，写成 material_1 / material_2；CUE4Parse 读得到引用名
cue4parse.exe -i D:\sbm\st_<包> -g GAME_UE4_26 -m <StellarBlade.usmap> -f json -o D:\sbm\json_<包> -p SB/Content/Art/Character/PC/CH_P_EVE_15/CH_P_EVE_15_V02_TypeB.uasset
# 3. 换进已归档的成品
blender -b --factory-startup --python swap_mod_mesh.py -- --base E:\game_export\StellarBlade\Eve\blend\CH_P_EVE_15_V02_TypeB `
  --psk <out>\...\CH_P_EVE_15_V02_TypeB.pskx --tex-root <out> --mesh-json <json> `
  --material-from E:\game_export\StellarBlade\Eve\blend\CH_P_EVE_62\Eve_CH_P_EVE_62.blend `
  --out D:\stellarblade_exports\packages --label Eve_Mod_GantzSling
```

- 把底板成品文件夹拷成 `packages\<label>\`，导入 mod 的 PSK，按同名骨骼求一个相似变换（旋转 + 平移 + 均匀缩放）对齐到 `Eve_Armature`，
  报告残差：在同一个骨架上做的 mod 残差约 0.002 cm。两个 keyhole 包放到 29 号成品上残差 0.4 cm，还缺一根 `Ab-L-Pectro1`，
  放到 62 号（泳装）成品上降到 0.002 cm，所以它们是在泳装骨架上做的（四个包都带 62 号的动画蓝图），用 62 号当底板。
- 材质：mod 带了 `.mat` 的槽用 mod 的贴图新建（颜色、DirectX 法线翻绿、ORM = R 遮蔽 / G 粗糙 / B 金属、自发光 ×2，贴图拷进 `textures\mod\`）；
  mod 没带、但贴图被 mod 换掉的游戏材质实例（红色 keyhole 的 `MI_CH_P_EVE_29_03`）按 `<名>_A/_N/_ORM/_E` 用 mod 的图；
  其余槽沿用底板里同名的游戏材质，底板里没有的从 `--material-from` 的成品里搬（皮肤 `MI_CH_P_EVE_62_BaseBody_A` 来自泳装，所以身上有晒痕）。
- 原来的衣服对象删掉，新网格接它的名字 `Eve_Body_Mesh_01`（PMX / XPS 那两步按这个名字找）；按脚尖方向渲正面和背面预览。
- 之后照常：`blender2xps\tools\batch_export_blends.py --scale 0.01`、`export_pmx_blender.py`、`preview_pmx_blender.py --dance-views front,back`。
- 没还原：游戏里两个 keyhole 版的节点会发红光 / 蓝光（游戏材质参数决定颜色），这里是白色节点。

`export_pmx_blender.py` 的胸部物理参数可以在命令行改：`--bust-spring`（默认 120，越小越软）、`--bust-limits 弹跳,翻滚,摆动`（度，默认 15,5,12）。
`preview_pmx_blender.py --dance-views front,side,back` 每个跳舞帧从这几面各拍一张（看头发、披风甩到哪里）。

## 导出 MMD（PMX）：`export_pmx_blender.py`（2026-09-25：Vindictus Fiona、Gantz Reika A / B）

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' -b `
  'D:\stellarblade_exports\packages\Eve_Mod_VindictusFiona\Eve_Mod_VindictusFiona.blend' `
  --python export_pmx_blender.py -- --out D:\stellarblade_exports\pmx `
  --model-name 'Eve Vindictus Fiona' --comment '出处/作者……（\n 换行）'
```

输入是任何一个组装好的 Eve `.blend`（`validate_eve.py` / `package_outfits.py` 的产物），输出
`<out>\<名字>\`：`.pmx` + `textures\`（相对路径，整个文件夹可拷走）+ `_converted.blend`，末行打印
`SB_PMX_REPORT={json}`；再跑 `preview_pmx_blender.py`（见下文「回读验证」）在同一文件夹出四张 `preview*.png`。
**注意：它每次先清空 `<out>\<名字>\`**，预览要在导出之后重跑。

现有产物（`D:\stellarblade_exports\pmx\`，日志在 `pmx\_logs\`，2026-09-25 全部按下面两处物理修复重导）：

| 模型 | 高 | 骨 | 表情 | 刚体 / 关节 | 改成跟随骨骼的分叉根 | 取消的静止穿插 | 静止 60 帧链根最大漂移 |
|---|---|---|---|---|---|---|---|
| `Eve_Mod_VindictusFiona` | 1.73 m | 381 | 26 + ARKit 53 | 56 / 40 | `Hair_Root`、`Ab-TL-HairB01` | `HairTail_Root`/頭 9.1 cm，侧发 5 节 0.2–0.4 cm | 1.1 cm |
| `Eve_Mod_GantzReika_A` | 1.72 m | 348 | 26 + ARKit 53 | 56 / 40 | 同上 | `HairTail_Root`/頭 9.4 cm，侧发 8 节 0.3–1.2 cm | 1.1 cm |
| `Eve_Mod_GantzReika_B` | 1.71 m | 350 | 26 + ARKit 53 | 56 / 40 | 同上 | `HairTail_Root`/頭 9.4 cm，侧发 8 节 0.3–0.5 cm | 1.1 cm |

三个都是撕裂 0、付与顺序违规 0、权重空洞 0、`stray_recipients` 空。

**2026-10-17 三个都重导了**，存档在 `E:\game_export\StellarBlade\{Fiona,Reika}\pmx\`，日志在 `_meta\pmx_logs\`：
- 眼睛按游戏参数重做（见下文「眼睛」）；
- 骨骼多了 2 根脚尖骨 `左つま先` / `右つま先`（Fiona 313 → 315，Reika A / B 286 → 288）。这是 Convert_to_MMD5 09-26 修的（`convert/ik.py`）：没有这根骨，mmd_tools 导出时找不到 `つま先ＩＫ` 的目标，09-25 那版的 `つま先ＩＫ` 导出后其实不是 IK；
- 其余不变：顶点、UV、面、材质、表情、刚体、关节都一样，权重按骨名比完全一致。

**骨架转换整条复用 Rise of Eros 的 PMX worker**（`scripts/riseoferos/export_character_model_blender.py`，
按函数 import，不复制）：Eve 也是 3ds Max Biped，槽位解析、肢体辅助骨按比例挂回（付与）、肩部权重
放松、37° A-pose、Convert_to_MMD5 一键转换、身体碰撞体、`mmd_cloth_physics` 头发物理、撕裂检查、
mmd_tools 以 12.5 倍导出、付与顺序回读检查，全部同一套代码。Eve 专属的只有下面这些，每条都是实打实
踩出来的：

| 问题 | 现象 | 处理 |
|---|---|---|
| Biped 骨名是连字符 `Bip001-L-Clavicle` | ROE 解析器和 Convert_to_MMD5 只认空格写法 | 改名（顶点组跟着改） |
| 场景单位是厘米 | — | 缩成米再转 |
| PSK 导进来人面朝 ±X | A-pose 绕世界 Y 轴放手臂，绕错轴把手臂拧成 57° / 49°；MMD 里人侧着站 | 按**两只脚**的脚尖方向转成面朝 -Y（单看一只脚有约 10° 外八偏差） |
| UE 挂点骨离身体很远（无人机起点 6 m、`FX_GunFire_Rail_End` 在地下 22 m） | Convert_to_MMD5 认为骨架高于 10 m 就是厘米模型，**把整个人缩小 10 倍**（导出只有 2.2 个单位高） | 转换前删掉「自身和子骨都没有权重、且伸出身体包围盒 25%」的骨（22 根） |
| mmd_tools 每个材质只留一张贴图 | 两个头发材质拿到灰度遮罩 `PonyTail_Alpha`（灰白头发），程序虹膜变全黑，口腔没贴图是灰的 | 转换**前**用 blender2xps 把节点算出来的颜色烘焙成贴图（转换后材质上多了 MMD 着色器组，blender2xps 会当成「原生处理」而不烘焙），转换后接成 `mmd_base_tex`；没贴图的用 Principled 底色 |
| 半透明辅助壳（眼部遮挡、泪液、牙齿阴影） | 被写成不透明灰色，眼周一圈白、张嘴嘴里一片白 | alpha 0 |
| mmd_tools 默认漫反射 0.4、高光 1.0 | 偏暗、皮肤像抹了油 | 漫反射 1、环境 0.5、高光 0.12（头发 0.3） |
| 胸部蒙皮骨叫 `Ab-L/R-Breast`，挂在 UE AnimDynamics 的四节短链末端（`Spine2 → Dm-*-Breast-Point → Dm-*-Breast → Ab-*-Breast-Link → Ab-*-Breast`，起点都在胸廓内同一点） | ROE 解析器不认这个名字；而且整条工具链**没有建胸部物理的环节**（Convert_to_MMD5 只把胸部槽位改名，原版的物理部分没搬过来），胸部跟着上半身僵硬地动 | 填进胸部槽位 → 改名 `左胸 / 右胸`；`add_breast_physics()` 每边一个球形刚体（放在蒙皮加权重心、半径按蒙皮实测，约 5 cm）、模式「物理+骨骼位置对齐」、第 15 组不和任何东西碰撞，关节在骨头起点、拴到上半身刚体，带角度限制和回弹弹簧（参数在 `BUST`） |
| Convert_to_MMD5 退役辅助骨时，把权重交给「起点最近、且是变形骨」的骨，而 UE 导进来的骨**全都**标成变形骨 | `Ab-NeckSub` 的脖子权重被分给了 `Sc_LookAtTarget`（挂在 Root 下的注视挂点）：头一转，脖子和领口的 94 个顶点留在原地，拉成一圈肤色的扁「领子」；另有一部分落到受物理驱动的侧发骨上 | ① 不带自身蒙皮的非 Biped 骨全部标成非变形（不能接权重）；② 用它自己的分类器预判会被退役的脊柱辅助骨（`Ab-NeckSub` / `Ab-*-Shoulder0` / `Ab-*-Trape0`），转换前把权重并进父骨——没有 UE 驱动时它们本来就跟父骨僵硬一起动，这是静止等价；③ 转换后审计「原来没权重、现在有了」的骨（`stray_recipients`，必须为空） |
| 眼球是头网格里的两个球，100% 绑在头骨上 | MMD 的视线动作（両目 / 左目 / 右目）完全不起作用，头一转眼睛还直直盯着脸的正前方；眼球在 MMD 里还会接到眼皮投下的自阴影、没有眼神光（UE 靠高光 + 法线贴图，MMD 都没有），完全透明的 `EyeLight_Inst` 高光片以不透明度 1 写出，是一块挡在眼前、还会投影的隐形片 | `add_eye_bones()` 在每个眼球的旋转中心（后缘往前一个半径，包围盒中心被角膜顶偏了）建 `Bip001 L/R Eye`，眼球顶点改绑上去——正好是 ROE 解析器认的眼睛槽位写法，Convert_to_MMD5 改名为 `左目 / 右目`，ROE 流程自动加 `両目`（付与 1.0、变形层级 1，顺序检查 0 违规）；眼球材质关掉接收/投射自阴影、单面、加一张加算 sphere 眼神光（`catchlight_sphere()`：视线轴左上一颗小亮点 + 右下一颗淡的；第一版放在约 30° 外、太大，铺成一层白雾）；烘焙结果完全透明的材质一律不透明度 0 |
| 脸是 MetaHuman 式头，52 个 **ARKit** 形态键、没有脸骨 | ROE 的骨骼表情插件无从下手 | 按配方混出 26 个 MMD 标准**顶点表情**（まばたき / 笑い / ウィンク / あいうえお / にやり / 眉 …），ARKit 原始形态也一起导出；表情面板里标准表情排最前 |
| 头皮头发的根骨 `Hair_Root`（挂在「頭」下，带着 4 条刘海 + 2 条侧发链）被 mmd_cloth_physics 当成链的一节，建成了**纯物理**刚体（2026-09-25 发现） | 一开物理整片头皮头发往下掉：不动站着 60 帧就沉 12 cm，跳舞时每一帧都是光头、头发团在脑后（Fiona 的第一版 PMX 也是这样，当时没看出来） | `anchor_hub_roots()`：父骨无刚体或是「跟随骨骼」、自己是动态、且下面有 ≥2 条动态链的「分叉根」改成模式 0（跟随骨骼），链挂在跟着头走的锚点上；报告字段 `anchored_hub_roots`（马尾第一节 `Ab-TL-HairB01` 也按这条改成跟随骨骼，从第二节开始摆） |
| 马尾上段的 `HairTail_Root`（Gantz 上蒙着 2,046 个顶点）在静止姿势下就嵌在头部碰撞球里 9.1–9.4 cm | 一开物理就被顶开，站着不动漂 9.3 cm | `release_rest_overlaps()`：静止时就嵌进「会碰撞的跟随骨骼碰撞体」超过 2 mm 的动态刚体，把那个碰撞组加进它的不碰撞列表（MMD 作者手工也是这么处理的）；报告字段 `released_rest_overlaps` |
| 手臂的 UE 辅助骨下面挂着小件（2026-10-17，Cooling Suit：`Ab-*-Deltoid` 下的细绳 `Deltoid-Fr-String01/02`，`Ab-*-UpperArm-Tw0` 下的小布片 `Ab-Axup*`） | mmd_cloth_physics 把整条链连同辅助骨本身建成了物理。辅助骨上挂着夹克的肩部（蒙皮 629）和上臂（885），下面的小件只有 98 / 110，一开物理整只袖子跟着甩 | `anchor_skin_helpers()`：物理链的链根是 `Ab-L-` / `Ab-R-` 辅助骨，而且它的蒙皮至少是下面所有骨的 3 倍时，改成跟随骨骼，只让下面的小件摆；报告字段 `anchored_skin_helpers`。头发链的根（`Ab-TL-*`、`Ab_SHair`）名字不匹配，不受影响 |
| 眼睛贴图里的虹膜（2026-10-17，用户：「眼仁有点小」） | `validate_eve.py` 当初凭目测把虹膜半径定成 UV 0.07、亮度提 2.6 倍。虹膜宽度只有游戏的 41%，上下碰不到眼皮，四周一大圈眼白；颜色也偏暗偏灰 | 按游戏材质 `MI_EyeRefractive1` 的参数和 `M_EyeRefractive` 的算法重做（新模块 `eye_material.py`，见下文「眼睛」）。`rewire_eyes()` 在烘焙前把 .blend 里旧的眼睛节点换掉，存档的 .blend 不用重做；报告字段 `eyes_rewired` |

**回读验证**（`preview_pmx_blender.py`）：mmd_tools 带物理导回 PMX，在 `.pmx` 旁边出
`preview.png`（正面）、`preview_morphs.png`（中性 + 11 个表情的脸部特写）、`preview_gaze.png`（`両目` 中性 /
左右 20° / 上下 15°，按世界方向转，与骨骼 roll 无关）、`preview_dance.png`（套「来杯好茶」
VMD、物理逐帧跑，取 150/400/650/900 帧），末行 `PMX_PREVIEW={json}`；其中 `rest_drop_test` 是不加动作站 60 帧
后每条链第一节刚体的漂移，超过 3 cm 的会列出来（链根本该挂在固定锚点上）。VMD 按 mmd_tools 的 `margin`
（默认 30 帧）导入，前面是从静止姿势过渡到舞蹈第一帧——`margin=0` 时人物一帧之内从静止姿势跳到舞蹈姿势，
关节把每条头发链猛拽一下，之后整段都是刘海翻到头顶、马尾甩离头部的样子，但模型本身没问题（MMD 开播时按当时姿势
重置物理，不会这样）。

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' -b --python preview_pmx_blender.py -- `
  --pmx 'D:\stellarblade_exports\pmx\Eve_Mod_GantzReika_A\Eve_Mod_GantzReika_A.pmx'
```

表情配方在脚本顶部 `RECIPES`：`ウィンク` = 模型自己的左眼（ARKit `eyeBlinkLeft`），`あ/え/お` 带上
`TeethLowerDown` 让下排牙跟着下巴走。实测（Vindictus Fiona）：高 21.7 单位 / 310 骨 / 22 材质 / 79 表情 /
56 刚体（马尾 9 节 + 前发 + 短发束 + 两个胸部 + 身体碰撞体）/ 40 关节；两臂 37.3°、权重空洞 0、撕裂 0、付与顺序
违规 0；导回 Blender 套「来杯好茶」舞蹈，四肢、马尾物理、表情逐项目检。——那次舞蹈回读其实已经拍到了头发问题
（第 2–5 帧都是光头、头发团在脑后），当时没看出来；2026-09-25 查明是上表最后两行的两处物理问题加上预览时
`margin=0` 的首帧拽动，修好后三个模型全部重导，新的四张预览在各自文件夹里。

视线：`両目` 转 ±20° 左右看、±15° 上下看都正常；这个角色眼球半径 1.8 cm，比真人大，往上看 15° 虹膜就基本进了上眼皮，往下看时上眼皮不跟随（MMD 模型的常态）。`eyeLook*` 形态键仍在「其它」里。裙子没有骨骼，跟随大腿和胯部，不做物理。
胸部实测（导回 Blender 套舞蹈 570 帧）：相对上半身偏转平均 5.6° / 3.7°，最大 19° / 12°（关节限制内），
约 80% 的帧在动；嫌晃得少/多就调 `BUST` 的 `spring`（回弹）和 `limit_deg`（幅度），最终手感以 MMD 本体为准。

### 眼睛：虹膜大小和颜色（`eye_material.py`，2026-10-17；按角色读参数、色调 2026-10-18）

游戏里所有角色的眼睛都是母材质 `M_EyeRefractive` 的实例。它是 UE 的折射眼睛，Shift Up 加了色调等参数，用 CUE4Parse 读，不要密钥。
Eve 用的实例是 `MI_EyeRefractive1`（`SB/Content/Art/Character/PC/CH_P_EVE_Head/Materials/`）。实例没写的参数取母材质自己的值：

| 参数 | Eve | 母材质 | 作用 |
|---|---|---|---|
| `Iris UV Radius` | 0.145 | 0.15 | 虹膜贴图铺满的圆的半径（在缩放后的 UV 里） |
| `ScaleByCenter` | 0.849798 | 1 | 整只眼睛的 UV 绕中心缩放。UE 的 ScaleUVsByCenter 是 `(uv - 0.5) / s + 0.5`，即**内容缩到 85%** |
| `PupilScale` | 0.861905 | 0.7 | 瞳孔收小（虹膜外缘不动） |
| `LimbusUVWidthColor` | 0.045 | 0.035 | 虹膜外缘往里这一段从虹膜过渡到眼白 |
| `IrisHueShift` | 0 | 0 | 虹膜颜色绕灰轴旋转（UE 的 HueShift，1 = 转一整圈） |
| `IrisHueTint` | (0.656, 0.598, 1) | 白 | 虹膜颜色逐通道乘的色调 |
| `IrisBrightness` | 5 | 1 | 虹膜颜色的倍数（虹膜贴图本身画得很暗） |
| `ScleraTint` / `ScleraBrightness` | 白 / 1.6 | 白 / 0.9 | 眼白的色调和倍数 |
| `IrisColor` / `ScleraColor` | `S_EyeIrisBaseColor` / `T_EyeScleraBaseColor` | `T_EyeIrisBaseColor_Example_2` / `T_EyeScleraBaseColor` | 虹膜、眼白贴图 |
| `DepthScale` | 0.8 | 1.2 | 角膜折射的深度（没做，见下） |

- **眼球的 UV**：角膜顶点在 (0.5, 0.5)。离正前方越远 UV 半径越大，大约每度 0.005，90° 时到 0.36；后半球折回同一个圆盘。
  所以虹膜外缘在网格上是 UV 半径 0.145 × 0.85 = **0.123**（约 22°）。旧的 0.07 只到 13°。
- **游戏的算法**（2026-10-18 反汇编游戏的着色器确认）：
  - 虹膜 = HueShift(虹膜贴图, `IrisHueShift`) × `IrisHueTint` × `IrisBrightness`，再乘角膜缘变暗（Eve 的 `LimbusDarkScale` 是 0）；
  - 眼白 = 眼白贴图 × `ScleraTint` × `ScleraBrightness`；
  - 两者在角膜缘按 smoothstep 混合，最后乘 `EyeCornerDarknessColor` 做的眼角阴影。
  - 色调是给共用贴图上色用的。`S_EyeIrisBaseColor` 是橙棕色；游戏的 `MI_MetaEyes_BlueEyes` / `GreenEyes` / `BrownEyes` 用的是同一张贴图，
    分别靠色调 (0.05, 0.30, 0.89) / (0.35, 0.86, 0.91) / (0.22, 0.26, 0.44) 变成蓝、绿、棕眼。蓝眼的亮度提到 14.9，补回变暗的部分。
  - 怎么查的：材质资产文件的最后 20 字节是它的 shader map 哈希。Eve 的 `MI_EyeRefractive1` 和 `MI_MetaEyes_BlueEyes` 是同一个 shader map，
    在游戏的 `SB/Content/ShaderArchive-SB-PCD3D_SM5.ushaderbytecode` 里排第 69。
    它的像素着色器是 DX12 的 DXIL，用 DXC 的 `dxcompiler.dll` 反汇编，再从 GBuffer 的底色输出往回追。
    工具在 `E:\tools\sb_shaders\`：`scan_archive.py` 读着色器库，`dxil_dis.py` 反汇编，`trace_ll.py` 追表达式。
- **核对**：游戏自带几张引擎渲染的 Eve：`SB/Content/DLC_2/Art/UI/Texture/ClearReward_Nikke_01`（NIKKE 联动通关奖励图），
  以及 `SB/Content/Art/UI/Texture/Boss/ClearReward_*`（Boss 通关奖励图，脸很小）。
  - 尺寸：虹膜宽度 ÷ 眼角到眼角的宽度，游戏 0.49，按这套参数 0.50，旧的约 0.38。虹膜上下都碰到眼皮，和游戏一样。
  - 颜色：
    - 游戏截图屏幕上的虹膜约 (91, 46, 16)。
    - 按游戏算法烘出的贴图上，虹膜是 (114, 68, 56)；不乘色调是 (133, 86, 56)。
    - 截图比贴图暗、偏金，差在游戏的光照、环境反射和色调映射上。
    - 在 Blender 里用 Filmic 渲染时，反而是不乘色调的更像截图。对比图：`E:\game_export\StellarBlade\Eve\pmx\CH_P_EVE_Nikke_06\眼睛色调对比.jpg`（两张游戏截图 / 不乘色调 / 乘色调）。
  - 走过的弯路：一开始以为 ScaleByCenter 是把 UV 乘 0.85（虹膜外缘到 0.1706，正好落在眼球网格角膜凸起的边缘那圈顶点上），渲染出来虹膜几乎占满整个眼裂。
- **其他角色**：
  - 每个角色有自己的眼睛实例，通常在头部文件夹，很多还用自己的虹膜贴图。
    例如 Lily 是 `NPC/CH_NPC_01/Materials/MI_CH_NPC_Lilly_Eyes`，Raven 是 `Monster/CH_M_NA_53/Materials/MI_CH_M_NA_53_Eyes`。
  - **高清材质的路线**：
    - 把实例的 JSON 一起放进 `hq_materials.py --mi-json` 的文件夹。`materials.json` 里会多出两项：
      - `eyes`：按实例名列出所有眼睛实例；
      - `eye`：游戏里实际用的那个，跳过 `_Cin` / `_subiris` / `_Die`。
    - 贴图先在 `--textures` 里找，再到 `E:\game_export\StellarBlade\_meta\hq_materials\_eye_textures\` 找。
      那里放着母材质的两张默认贴图和 Eve 的虹膜，都是 CUE4Parse 导出的。
  - **`hq_materials_blender.py` / `export_pmx_blender.py --hq-materials` 怎么选参数**：
    - 名字和 `eyes` 里某个实例相同的材质（忽略 `.001`），用那个实例的参数和贴图；材质里缺贴图就从文件加载。
    - 名字里有 `eye…refract` / `eyeball` 的其他眼睛材质，用 `eye`。
    - 都没有时用 Eve 的。
  - `export_pmx_blender.py` 也把名字对得上实例的材质当成眼球：加眼球骨骼 左目 / 右目，加高光球面贴图。名字里没有 refract 也算。
  - **没有 materials.json 时**：
    - `--eye-mi <实例的 JSON>`：可以写多个，第一个也当默认；
    - `--keep-eye`：保留 .blend 里原来的眼睛不动。
- **没做**：角膜折射（游戏里瞳孔会被放大一点）、角膜缘变暗（`LimbusDarkScale`）和眼角阴影（`ShadowRadius`、`EyeCornerDarknessColor`）。
- **哪里生效**：
  - `validate_eve.py` 的 `link_eye_color()` 直接用它，以后新导出的 .blend 就是对的；
  - `export_pmx_blender.py` 的 `rewire_eyes()` 烘焙前把 .blend 里的眼睛节点换成这一套，从旧 .blend 导出的 PMX 也是对的；
  - `hq_materials_blender.py` 做高清 .blend 时也换，剑星材质插件拿到的也就是对的。
- **已有成品**：
  - 存档里 148 个 Eve 的 .blend 还是 10-17 之前的旧眼睛（就地改要用户同意）。
  - Cooling Suit 的 PMX 和高清 .blend、Fiona / Reika A / B 的 PMX 和 XPS：2026-10-18 按游戏材质的算法（乘色调）重导，替换了存档。
    这是用户在「不乘色调、更像截图」和「严格按游戏材质」之间选的后者。
- 对比图：`E:\game_export\StellarBlade\Eve\pmx\CH_P_EVE_Nikke_06\眼睛修复对比.jpg`（游戏渲染 / 修复前 / 修复后，加两张脸部近景）。

## 高清材质（`hq_materials.py` → `hq_materials_blender.py` / `export_pmx_blender.py --hq-materials`，2026-10-17：Cooling Suit）

存档里每套服装的 .blend 只接了底色。服装自己的法线 / ORM / 遮罩 / 自发光贴图在 `textures\extra\`，打包时不知道哪张该接哪里，就没接。这条线从游戏里读服装的材质实例，按游戏的接法接回去。

1. **读游戏的材质实例**（CUE4Parse，不要密钥）：
   ```powershell
   cue4parse.exe -i "<StellarBlade>\SB\Content\Paks" -g GAME_UE4_26 `
     -m E:\game_export\StellarBlade\_meta\mappings\StellarBlade_1.1.0.usmap -f json -y -o <dir> `
     -p "SB/Content/DLC_2/Art/Character/PC/CH_P_EVE_Nikke_06/Mat/*"
   ```
   - 服装的材质实例都继承 `MA_CH_Standard_Ver03`。实例没写的参数取母材质的默认值（它的 `CachedExpressionData`），例如 `Pattern01_Tiling` = 8。
   - 共享的花纹法线（如 `Art/Character/Generic/MF/Fabric/Knitted_N`）用 `-f png` 单独导出。
2. **整理参数、生成 PMX 贴图**：
   `python hq_materials.py --mi-json <dir> --textures <服装文件夹>\textures --pattern Knitted_N=<png> --out <dir>`，输出：
   - `materials.json`：每个材质的底色、ORM、法线、遮罩、自发光、花纹法线，以及游戏外用得上的参数；
   - 每个材质一张 `<底色>_pmx.png`：底色 × AO（ORM 的红通道，在线性空间乘）+ 自发光遮罩（`Emissive_CH` 那个通道）处的自发光颜色，原尺寸（4K）。
3. **Blender 高清版**：
   `blender -b <服装.blend> --python hq_materials_blender.py -- --materials materials.json --save <服装文件夹>\<名>_HQ.blend`
   接成 Principled：
   - ORM：G → 粗糙度（落在实例的最小–最大值之间）；B → 金属度 × `Metallic`；R（AO）→ 高光遮蔽，高光 = 0.5 × AO。
   - 法线：UE 是 DirectX，翻绿通道。
   - `MaterialLayerMask` 的清漆通道 → Clearcoat（粗糙度用 `ClearCoatRoughness Min`）。
   - `FuzzMask` 的绒毛通道 × `Fuzz_01_INTENSITY` → Sheen。
   - 自发光：自发光贴图里 `Emissive_CH` 选的那一个通道（Ver03 默认红通道）× `EmissiveColor`，强度 2。
     `EmissivePower` 为 0 或颜色是黑色（母材质的默认值）时不接：游戏里这种不发光。2026-10-18 起才这样，之前用整张图，Iberis 的丝袜因此发了光（ROE_pmx 发现）。Cooling Suit 的贴图三个通道一样，结果几乎不变。
   - `Pattern01_Normal`（针织等花纹）按 `Pattern01_Tiling` 平铺，只在绒毛区叠到法线上。
   - `BLEND_Masked` 的材质（贴花）按 1/3 裁切，和游戏一样。
   - 眼睛按游戏参数重做（`eye_material.py`，见上文「眼睛」）：materials.json 里有角色自己的眼睛实例（`eyes` / `eye`）就用它的，没有就用 Eve 的。

   贴图都用相对路径；`--copy-textures` 会把文件夹外的贴图先复制进来。原来的 .blend 不动。
4. **PMX**：`export_pmx_blender.py … --hq-materials materials.json`
   - 转换前，每个材质的底色换成它的 `_pmx.png`（MMD 一个材质只有一张贴图）。
   - PMX 写出后，有清漆遮罩的材质按遮罩拆成两份。判断时先把遮罩模糊 1/256 图宽，不然缝线上的细灰线会把落在上面的面分成哑光，在乳胶上留下一串斑点。
     - UV 中心落在清漆区的面进 `<名>_gloss`：排在原材质后面、贴花前面；高光 0.55，光泽度 60，加算球面贴图 `gloss_sph.png`（左上一片柔光加一个亮点）。
     - 其余面留在原材质里，保持哑光。
   - 用 PMX 模块改完存盘时，要带上附加 UV 的个数：mmd_tools 给 Eve 写了 1 组附加 UV，`save()` 默认按 0 写文件头，顶点数据就错位了，回读时报 `invalid weight type`。
5. **在 Blender 里给导入的 PMX 换回游戏材质**：插件 **Stellar Blade Game Materials**（`scripts/blender_addons/stellarblade_game_materials`，用法见它的 README）。
   - 用 mmd_tools 导入 PMX，在侧栏 MMD 标签页「剑星游戏材质」里点「换上游戏原始材质」。插件按材质名从存档的 `*_HQ.blend` 里把第 3 步那套节点搬进来。
   - 可以随时切回 MMD 着色。法线、粗糙度、金属度、清漆、绒毛光泽、自发光都能拖滑块调。
   - 再导出 PMX 不受影响。
   - 2026-10-18 起，搬过来的次表面散射半径会乘「导入模型的高度 ÷ 172」：存档是厘米，PMX 导入后约是米。
     之前脸的 1 cm 散射变成了 1 m，游戏材质下整张脸糊成蜡色。

**Cooling Suit（Alice，`CH_P_EVE_Nikke_06`）**，三个材质：

| 材质 | 游戏材质实例里的内容 | PMX |
|---|---|---|
| UV1（乳胶连体衣、袜子、鞋、手套） | 底色、ORM、法线、`UV1_M`（R = 清漆，G = 绒毛 0.17）、`Metallic` 1 | 底色 × AO；清漆区拆出 `_gloss`：36280 个面，其余 23716 个面哑光 |
| UV2（泡泡袖夹克、扣带） | 底色、ORM、法线、`UV2_M`（R = 绒毛 0.7，粉色）、`UV2_E` 自发光（红，`EmissivePower` 10）、`Knitted_N` 针织花纹（×8，强度 5） | 底色 × AO（平均 0.65，绗缝的鼓包很明显）+ 自发光 |
| 贴花「SUPER」 | 底色带透明通道、`BLEND_Masked`，最大粗糙度 0.53 | 透明通道照用 |

- **存档原版的贴花错了**：贴花材质不透明，透明部分画成了一块黑色方牌。游戏里是白字直接印在衣服上（贴图里黑色部分的透明度只有 0.05）；高清版和 PMX 都改对了。
- **物理**：这件衣服的手臂辅助骨下面挂着小件，处理办法见上面「导出 MMD」表格的最后一行（`anchor_skin_helpers()`）。
- **回读**：
  - 324 骨 / 70 刚体 / 52 关节，26 个 MMD 表情加上 ARKit 表情；
  - 撕裂 0、权重空洞 0、付与顺序违规 0；
  - 不加动作站 60 帧，15 条链的链根最多漂 1.1 cm；
  - 套「来杯好茶」跳舞正常。
- **已知**：Eevee 预览里，夹克袖子上有几粒高光白点，是铆钉、缝线这类小结构反光，不是贴图问题。
- **文件**：
  - PMX：`E:\game_export\StellarBlade\Eve\pmx\CH_P_EVE_Nikke_06\`（PMX + `textures\` + `_converted.blend` + 四张预览 + `高清材质对比.jpg` + `插件效果_游戏材质对比.jpg`）；
  - 高清 .blend：`E:\game_export\StellarBlade\Eve\blend\CH_P_EVE_Nikke_06\Eve_CH_P_EVE_Nikke_06_HQ.blend`（`Knitted_N.png` 已复制进 `textures\extra\`）；
  - 游戏数据：材质实例 JSON 和 `materials.json` 在 `E:\game_export\StellarBlade\_meta\hq_materials\CH_P_EVE_Nikke_06\`。

**Nexus mod 服装：Gantz Reika A / B（2026-10-18，`hq_mod_outfits.py`）**

用户问 Reika 的 PMX 能不能在 Blender 里用插件换上高清材质。之前只换得上头、头发、眼睛（13 个，借 Cooling Suit 的高清 .blend）。
mod 自己的衣服和 B 的皮肤没有高清 .blend，保持 MMD 着色。

- mod 装在 `~mods\Hawkins_GantzReika\`，CUE4Parse 读得到。材质实例在 `SB/Content/OutfitMods/GantzReika/`。
  它们都继承游戏自己的材质：
  - 衣服 `SuitA_Body` / `SuitA_Mesh` / `SuitB` → `MI_P_EVE_09_Metal02_Layered`（Planet Diving Suit 的金属件）→ 母材质 `MA_CH_P_EVE_09`。
    mod 只换了底色、ORM、法线、发光四张图，以及发光色 `ML_GlowEm_EyeCoreHDRTint`：游戏是黄绿 (117, 271, 2.36)，mod 改成蓝 (0, 0.56, 271)。
  - B 的皮肤 `EveSKin` → `MI_Basebody_V02_F2`（Eve 身体）→ `MA_Skin_EVE`。
    mod 换了底色、法线和 `ORSS Mask`（R 遮蔽、G 粗糙度、B 高光、A 次表面），粗糙度范围 0.229–1.108 来自父实例。
- `python hq_mod_outfits.py [--only Mod_GantzReika_B]`，每套衣服做五步：
  1. 读游戏：CUE4Parse 导出 mod 文件夹的 JSON，再顺着 `Parent` 一层层导出父实例和母材质，放进 `_meta\hq_materials\<包名>\mi_json\`。
  2. 合并：只取这套衣服的骨骼网格实际用到的实例，按 UE 的规则合并。子实例的值优先；谁都没设的取母材质的默认值（`CachedExpressionData`）。
     结果写成 `staged\MI_<名>.json`。另做一处 `hq_materials.py` 没有的翻译：
     - `MA_CH_P_EVE_09` 的发光不走 `EmissivePower` / `EmissiveColor`（父实例设成 0 和黑色），走的是 GlowEmissive 层，静态开关 `UseGlowEmissive`。
     - 写法：`ML_GlowEmissive_CH` 选的那个通道（红）→ `Emissive_CH`，HDR 颜色原样 → `EmissiveColor`，`EmissivePower` 写 1，只用来打开接线。
     - 发光层的菲涅耳、Boost 这些项不照做。
  3. `hq_materials.py`（不改）→ `materials.json`。
  4. `hq_materials_blender.py`（不改），作用在存档的 .blend 上，生成同一文件夹里的 `<名>_HQ.blend`。眼睛顺带按游戏参数重做。
  5. 再开一次 Blender（`--post`）：
     - 皮肤实例由本脚本自己接：粗糙度 = G 映射到 MinRoughness–MaxRoughness，高光 = B × `BaseSpecularValue`，DirectX 法线 × `NormalStrength`。
       次表面照抄脸（`MI_EVE_Head_V02`）的设置：脸用的是存档原来的网络，抄过来接缝处才对得上。
       `MicroNormal`（毛孔，平铺 40 次）、`NC_E Mask` 没接，记在 `skin.json` 里。
     - 存档原来按文件名猜着接的 ORM、法线、发光节点，被新接线顶掉以后没人用了，删掉（每个材质 7–8 个）。
- 结果（插件实测，`Reika\pmx\Mod_GantzReika_*\插件效果_游戏材质对比.jpg`）：
  - A 15/15、B 16/16 个材质换上，贴图不缺，没有留下库条目。
  - 两种状态再导出：A 逐字节一致。B 肚脐处一个退化顶点的法线，mmd_tools 每次导出都在两个值之间随机变，不装插件也一样。
  - 「去掉游戏材质」后插件节点清零。
  - Cooling Suit 复测 17/17，导出一致。
- 存档原来的 Reika .blend 衣服其实已经接了 ORM / 法线 / 发光，是按文件名猜的。发光用的是贴图本身的青色（最亮处 R 0.22、G 0.69、B 1.0）×2。
  游戏只取红通道，乘蓝色 HDR，所以高清版的发光是纯蓝的。
- PMX 不用重导：mod 的 ORM 红通道（AO）全是 1，「底色 × AO」等于原图，只多几个发光点，所以 PMX 里的颜色基本不变。
- **文件**：
  - 高清 .blend：`E:\game_export\StellarBlade\Reika\blend\Mod_GantzReika_A\Eve_Mod_GantzReika_A_HQ.blend`、`…_B\…_B_HQ.blend`（贴图就是旁边 `textures\` 里的）；
  - 数据：`E:\game_export\StellarBlade\_meta\hq_materials\Mod_GantzReika_A|B\`，包括 `mi_json\`、`staged\`、`materials.json`、`skin.json`、`chains.json`、`hq_log.txt`、`*_pmx.png`；
  - 各自 `README.txt` 加了「高清版 / HQ」一节。

**裸体：EveOriginalProportions 赤足（2026-10-24，`hq_mod_outfits.py --only Nude_Barefoot`）**

Reika 的三层模型（A + B + 裸体，`scripts/clothes_burst/pmx_layers.py`）里，裸体那层也要高清材质。
- 这个 mod 替换的是 Eve 的内衣身体（`CH_P_EVE_InnerSuit`），没装进游戏。脚本直接从下载的压缩包
  `E:\tools\setup\mods\EveOriginalProportions-30-2-1-1750283806.rar` 读 `Barefoot\` 那一份（.pak / .utoc / .ucas，用 Windows
  自带的 `tar` 解，它认得 RAR5），解到临时文件夹。旁边建一个目录联接指向游戏的 `Paks`，CUE4Parse 一起读，
  mod 的材质实例才找得到游戏里的父实例。读完删掉临时文件夹，联接只删联接本身。
- mod 自己的身体实例 `SkinEve` → `MI_Basebody_V02_F2`（和 Reika B 的 `EveSKin` 同一个父实例）→ `MA_Skin_EVE`。
  它换了底色 `custombody_A`、法线 `custombody_N`、`ORSS Mask` `custombody_ORSS`、`NC_E Mask` `custombody_DMSE`。粗糙度范围、
  高光 1.0、`BaseSSS` 都和 B 的皮肤一样；只有 `Detail Strength` 是 0（B 是 1，毛孔细节，本来就没接）。
- 骨骼网格还留着鞋（`Heels`）和阴毛（`MI_Pubic`）的材质槽，赤足这一份里没有面，`slots` 只取 `SkinEve`。
- 只读两个包：`SkinEve.uasset` 和 `CH_P_EVE_InnerSuit.uasset`。用 `.*` 通配时，游戏自己那份网格的 `.ubulk` 也匹配，
  CUE4Parse 并行写同一个 JSON 会崩。
- 结果：`E:\game_export\StellarBlade\Eve\blend\Nude_Barefoot\Eve_Nude_Barefoot_HQ.blend`，身体接了 ORSS（粗糙度 0.229–1.108、
  高光 ×1）、法线，次表面和脸一样（0.055）。数据在 `_meta\hq_materials\Nude_Barefoot\`。
  插件：单独的裸体 PMX 14/14；三层模型 19/19（每层从自己的高清 .blend 拿，见插件 README「分层模型」）。
- 没照做：mod 设的 `BaseTint`（F6D7D9，偏粉）。B 的皮肤从父实例继承同一个值，两边都没乘，保持一致；母材质里它乘在哪儿还没查。

**Nexus mod 服装：Vindictus Fiona（2026-11-14，`hq_mod_outfits.py --only Mod_VindictusFiona`）**

用户问 Eve 穿 Vindictus Fiona（Nexus 1145）的 PMX 是不是高清版、能不能在 Blender 里换上高清材质。
- 贴图本来就是原尺寸：和 Vindictus: Defying Fate 的 PCF_005 逐像素比过，衣服、身体 4096，脸 2048。
- 插件之前只换得上头、头发、眼睛 13 个材质；衣服和皮肤 9 个没有高清 .blend。

mod 的结构：
- 装在 `~mods\FionaV_p.*`，挂载名是 `test/Content`（io store mod 的挂载名随意）。只读 `test/Content/*.uasset`。
- 网格 `CH_P_EVE_09` 替换 Planet Diving Suit 7th。材质实例放在 09 / 16 / 21 三个文件夹，名字是 `body`、`amt` 这种通用名。
- 继承关系：
  - 衣服 `Ahand` / `head` / `acc` / `amt` → `MI_CH_P_EVE_16_Suit` → `MA_CH_P_EVE_16`。
  - `shoes` → `MI_EVE_Cos_21_Shirt_TypeB` → `MA_CH_Standard_Cloth_Ver02`。
  - 衣服的底色、ORM、`Baked NormalMap` 都是 Defying Fate 的 PCF_005 贴图。
  - 皮肤 `body` / `lowbody` / `hand` / `face` → `MI_P_EVE_09_Skin` → `MA_Skin_EVE`。mod 只设了底色和法线（Defying Fate 的 `T_PCF_*`、`T_Fiona_Face01`）。
- 父实例里 Eve 服装 16 / 21 的发光贴图和遮罩贴图（`CH_EVE_Cos_16_01_E` / `_Mask`、`EVE_Cos_21_*`），mod 都换成了 256² 的纯黑图。
  所以游戏里不发光，遮罩控制的布纹、丝绸层都关着。高清版同样不接。

这次加了三条规则（`hq_mod_outfits.py`、`hq_materials.py`）。对 Reika A / B、裸体做过离线复查：合并结果、贴图、法线判断都没变，皮肤本来就不透明。
1. **参数名不分大小写**：UE 的参数名是 FName，比较时不分大小写。
   - 鞋子的 mod 实例写的是 `BaseColor`，父实例写的是 `Basecolor`，两者按同一个参数合并。
   - 之前鞋子拿到的是父实例里 Eve 衬衫的贴图 `EVE_Cos_21_Shirt_A_TypeB`。
2. **法线贴图方向自动判断**（`normal_convention()`，结果在 `normals.json`）。
   - 原理：由高度场生成的法线贴图，只有按它自己的绿通道方向去读，梯度场的旋度才接近 0。
   - UE 的贴图都是 DirectX。mod 的连衣裙法线 `PCF_005_Onepiece_N` 被反成了 OpenGL：旋度 0.069 对 0.125。
     Defying Fate 原版和这套衣服另外三张都是 DirectX，所以游戏里裙子的凹凸是上下颠倒的。
   - 判为 OpenGL（旋度比 DirectX 小 1.4 倍以上）的贴图，`--post` 里按 OpenGL 读（`flip_green()`）。这一处高清版和游戏不同。
   - Eve 裸体的 `custombody_N` 两个方向只差 4%，按 DirectX 不动。
3. **皮肤**：
   - mod 的皮肤沿用父实例的 `CH_P_EVE_BB_V01_ORSS`。这是 Eve 身体的遮罩，按 Eve 的 UV 画，套在 Fiona 的 UV 上是错位的：
     Eve 的乳下线、肚脐、UV 空隙会乱落到 Fiona 身上。
   - 这套衣服自己的贴图里没有 ORSS 时，导出父实例那张（`<数据>\orss\`），取 UV 岛内的平均值（G 0.278、B 0.508）当常数：
     粗糙度 0.473，高光 0.508。
   - 母材质不透明的皮肤，如果存档接了底色的透明通道，就断开、改成不透明。
     Fiona 的 `T_PCF_Hand01_D` / `T_PCF_Lower01_D` 透明通道只是 UV 覆盖范围（岛内全白）。

结果（插件实测，对比图 `Fiona\pmx\Mod_VindictusFiona\插件效果_游戏材质对比.jpg`，浅灰环境光）：
- 22/22 个材质换上，贴图不缺，没有留下库条目。
- 两种状态再导出，PMX 逐字节一致。「去掉游戏材质」后插件节点清零。
- 裙子是白缎面加蕾丝暗纹，和 Defying Fate 原版的预览一致。
- 头发偏灰是剑星高清版头发的老问题：粗糙度是常数，见上面 Cooling Suit。
- PMX 不用重导。

**文件**：
- 高清 .blend：`E:\game_export\StellarBlade\Fiona\blend\Mod_VindictusFiona\Eve_Mod_VindictusFiona_HQ.blend`（`README.txt` 加了「高清版 / HQ」一节）。
- 数据：`_meta\hq_materials\Mod_VindictusFiona\`，包括 `mi_json\`、`staged\`、`materials.json`、`skin.json`、`normals.json`、`chains.json`、`orss\`、`hq_log.txt`。

**Nexus mod 服装：Vindictus Demon Maiden（2026-11-14，CNS，样品）**

[stellarblade/mods/1807](https://www.nexusmods.com/stellarblade/mods/1807)（AlomX）的「Outfit」文件。带角的头发是另一个文件「Hair」，还没下。
- mod 没装进游戏：zip 拷到 `D:\stellarblade_exports\mods\DemonMaiden\`，解出 `AlomXCNS-VindictusDemonMaiden-1700.*` 和
  `.dekcns.json`（挂在 `/Game/OutfitMods/VindictusDemonMaidenOutfit/`，网格 `CH_P_EVE_DemonMaiden`）。
- CUE4Parse 读网格：骨架是 `CH_P_EVE_01_Skeleton`，7 个槽全用 mod 自己的材质实例（皮肤 `MI_Basebody_V02_F1_Inst`、
  衣服 `MI_Rav_*`）。UE Viewer 单看 mod 读不到父材质，`.props.txt` 里 `Parent = None`、`Skeleton = None`。
- `swap_mod_mesh.py --base ...\Eve\blend\CH_P_EVE_01_Body`：骨骼对齐误差 0.07 cm，最差的是约束骨 `SC_BurstStanceConstraint`（0.78 cm，不参与变形）。
  **CNS 服装不要加 `--mesh-json`**：那个参数按槽名（`MI_CH_P_EVE_35_BB`、`0_nt_mat`……）去找 `.mat`，CNS 的 `.mat` 是按材质实例名起的，
  7 个槽全找不到，只剩 PSK 自带的空材质。不加时 PSK 里的材质名就是实例名，全部接上。脚本新建的材质名后面带 `_mod`。
- 之后照常：XPS（233 骨、16 个网格）、PMX（353 骨、26 个表情、62 刚体 / 52 关节、撕裂 0；mod 自带的肩部装饰骨 `Ab-*-AX1T`
  自动建成装饰物理）、`preview_pmx_blender.py --dance-views front,back`（静站 60 帧链根最大漂移 0.7 cm）、
  `archive_exports.py stellarblade --only Mod_VindictusDemonMaiden`（只归档这一个；zip 和解包另外拷到 `_meta\mod_sources\DemonMaiden\`）。

高清版（`hq_mod_outfits.py --only Mod_VindictusDemonMaiden`）这次补了三处：
1. **没装进游戏、文件在 zip 根目录的 mod**：`archive` 不给 `member` 时整包解到临时 `Paks\mod\`，旁边照旧建游戏 Paks 的联接。
   读的是 `_meta\mod_sources\DemonMaiden\` 里那份 zip。
2. **`_mod` 后缀的材质名**：`swap_mod_mesh.py` 的成品里材质叫 `MI_Rav_Outfit_mod` 这样，PMX 里也是。`hq_materials_blender.py` 和 `--post`
   先按实例名找，找不到再找 `<名字>_mod`（之前 7 个全报「not in this .blend」）。贴图也去 `textures\mod\` 找。
3. **父材质的 ORSS 遮罩能不能直接用**（`layout_kept()`）：
   - mod 皮肤设的 `CH_EVE_BaseBody_V02_F1_ORSS` 不是母材质 `MA_Skin_EVE` 的参数，游戏里不起作用，实际用的是父材质 `MI_Basebody_V02_F1` 的
     `CH_P_EVE_ReferenceBody/.../CH_EVE_BaseBody_V02_F1_ORSS`。
   - 判断方法：mod 皮肤的法线图和父材质的法线图各缩到 256 px，比 x / y 斜率的相关系数。Demon Maiden 0.92（Eve 原版身体 V02_F1 重画了颜色和法线），
     Fiona 四个皮肤 -0.01–0.01（Fiona 自己的身体）。≥ 0.5 直接接父材质的遮罩（拷进 `textures\extra\`），否则照旧取平均值当常数，Fiona 不变。
   - 先试过「皮肤面的 UV 中心落在遮罩有内容的像素上的比例」，分不开：V02_F1 的遮罩整张填满（100%），Fiona 的手对不上也有 97%。

结果：
- 插件实测（真实的插件按钮）：20/20 个材质换上，挑中的就是这套的高清 .blend；贴图不缺，没有留下库条目；两种状态再导出 PMX 逐字节一致；去掉后节点清零。
- 对比图 `Eve\pmx\Mod_VindictusDemonMaiden\插件效果_游戏材质对比.jpg`：黑色紧身衣、裤袜粗糙度约 0.27，是有光泽的非金属，浅灰环境光下泛灰；
  MMD 着色是纯黑。白色饰件是金属，银白。
- 高清 .blend 引用的 30 张贴图都在自己的文件夹里。

**文件**（`E:\game_export\StellarBlade\Eve\`）：`blend\Mod_VindictusDemonMaiden\`（.blend、`_HQ.blend`、`README.txt`）、`xps\Mod_VindictusDemonMaiden\`、
`pmx\Mod_VindictusDemonMaiden\`；数据 `_meta\hq_materials\Mod_VindictusDemonMaiden\`。

**一批 Nexus mod（2026-11-15：12 个 mod、48 套，`hq_mod_outfits.py` 的登记表 + `mod_gallery.py`）**

用户下载到 `E:\Downloads\eve_mod_download` 的 12 个 mod（Nikke Plus、Cake Unveiled 冷却服、Crimson Wings BBB / OP、YoRHa 礼服 / 2B 制服、
Black Sling、Albion Nell、Nude Natural、Skin Suit Undressed、Original Proportions、Revealing Crimson Wings）拆开有 72 种变体；
用户选了「每种网格一份」：48 套（Crimson Wings BBB 的 40 个替换包按 PSK 顶点 md5 只有 16 种网格）。每套走 Demon Maiden 那条线
（`swap_mod_mesh.py` 换进已归档的原版成品 → XPS / PMX / 预览 → 归档 → 高清版 → 插件实测），中间多了一步「补材质」。
批处理脚本在 [`nexus_batch/`](nexus_batch/README.md)；这里记做法和坑。

- **读网格要带上游戏的 Paks，mod 的文件要当补丁**：CUE4Parse 并行挂载，两个容器里有同一路径的包（替换型 mod，如 Revealing Crimson Wings
  的 `CH_P_EVE_39`）时取「读取顺序」高的；名字带 `_P` 的是补丁，高于游戏的 pakchunk。不带 `_P` 时谁赢是随机的（3 次里 2 次读成了
  游戏原版网格）。现在硬链接时一律命名成 `<名>_P.*`（`hq_mod_outfits.py` 的 `files` 也是）。
- **UE Viewer 的 PSK 是「每段网格一个材质」**：LOD0 每个 section 一个，按 section 顺序；没有面的槽不写（Nikke Plus 无外套款的
  `MI_Basebody_V02_F2`、裸体的空鞋 / 阴毛槽），两段共用的槽写两次，游戏里关掉的段也写（Crimson Wings OP：UV2 两段 + 1766 个三角形的代理段）。
  所以槽名要按 section 对，用每段的三角形数核对；关掉的段按游戏去掉。
- **只改参数的 mod 材质实例**（YoRHa 礼服把原版 5 个材质拆成 25 个部件，各自只改参数）UE Viewer 不写 `.mat`：沿 `Parent` 链往上，
  拿最近一层在已归档 .blend 里有的游戏材质，复制一份按 mod 实例的名字命名（高清版和插件按这个名字找）。哪个 .blend 里有哪个材质，先扫一遍
  存档建索引（197 个 .blend、603 个材质名，只读名字）。都没有的（Black Sling 的墨镜 `MI_ACC_GLA_13`）用 CUE4Parse 导出它的贴图现做；
  连贴图都没有的（深色镜片）取实例的颜色值。
  - **抄来的祖先材质要换上实例自己的贴图；底色图不是实例的就别抄**（2026-11-21，Crimson Wings 裸体款）：
    - 底层贴图包里的 `Inst_1` / `Inst_2` 是游戏透明乳胶 `MI_EVE_Cos_08_Vinyl` 的实例（GlassColor 黑，正面不透明度 0.32），
      自己只改了 `Baked NormalMap`，换成 Crimson Wings 的 UV1 / UV2 法线。
    - 归档里这个乳胶的简化材质只有一张漫反射：NPC 的皮肤图 `MI_CH_NPC_Lilly_01_Skin_2_A`。它是母材质节点里默认引用的，
      不是这条链上任何实例的参数，贴到 Crimson Wings 的 UV 上，领口就成了一片花纹。
    - 现在 `fill_materials.py` 抄完祖先，先按图名换上实例自己设的贴图（`nexus_batch/retex.py`），再检查底色图。底色图不在实例的贴图里，
      就不抄祖先，改用实例自己的贴图和数值现做：颜色向量、粗糙度、半透明材质的正面不透明度。做出来是半透明的黑色乳胶。
    - `python retex.py ALL` 扫过已导出的套：另外只有 YoRHa 2B 制服的 5 个透明版槽。它们 CNS 默认关掉，面已经去掉，不用重做。
  - **现做的材质没有底色贴图，要生成一张纯色贴图**（2026-11-21）：
    - XPS / PMX 导出（blender2xps 的 `material_is_translucent_shell`）把「透明度是 0.001 到 0.5 之间的常数」的材质当成辅助壳，
      也就是眼部遮挡壳、泪液这类，PMX 里透明度直接写 0。
    - Crimson Wings 的乳胶（0.32）和 Black Sling 的深色镜片因此在 MMD 里看不见；只有法线图的材质，PMX 还会把法线图当成颜色贴图。
    - 现在 `fill_materials.py` 给这种材质生成一张 8×8 的 `<材质>_colour.png`（颜色加透明度），接到 Base Color，半透明的也接到 Alpha。
      PMX 里就是漫反射 1 加这张贴图，透明度在贴图里。
    - 每套 PMX 日志（`pmx\_logs\<包名>.log`）里的 `shells` 应该只有面部那 6 个辅助壳。
- **父材质叫 `Hide`** 的槽游戏里不画（YoRHa 礼服的手臂 / 腿 / 手的皮肤藏在手套、丝袜下面，阴毛默认关），这些面去掉。
- **CNS 的默认选项**：`.dekcns.json`（有尾逗号，要宽松解析）的 `TextureOptions` 按 `Value` 取默认贴图（Nikke Plus 默认粉色衣服 + 粉色外套，
  Cake 的肤色），底色在普通 .blend 里就换上，ORM / 法线 / 遮罩写进登记表的 `overrides`，高清版里换；`MaterialToggles` 默认关的槽
  （YoRHa 2B 制服 12 个：透明版、手、大腿、靴子下的腿、高跟鞋、阴毛）去掉。
  - 同一个游戏材质实例挂在两个槽上、两个槽的 CNS 选项又不同时（Nikke Plus 无外套款：槽 0 和槽 1 都是 `MI_CH_P_EVE_Nikke_06_UV1`，一个配衣服颜色、
    一个配上身颜色），游戏里每个槽是各自的动态实例；Blender 里共用一个材质，后一个选项会盖掉前一个（鞋子变粉、腰侧一块白）。所以后面的槽
    复制一份材质，叫 `<材质>__slot<槽号>`；登记表里写进 `slot_materials`，高清版按这个名字单独展开（插件 17/17）。
- **缺依赖的 mod 先不导**：Crimson Wings BBB 要作者的「Base Textures For Replacement」（皮肤槽 `SkinEve` 在里面），Cake 的皮肤在另一个 mod
  #1183「Reusable Skin Material」里，Skin Suit Undressed 只下了网格没下贴图。2026-11-21 这几个依赖文件下齐了，`add_dep.py` 解开后
  补导了 26 套。
  - Crimson Wings 的「Nude and Stocking」更新包把裸体、裸体加丝袜两个三件套放在同一个文件夹里，包路径相同。按文件夹放进 staging
    会两个都挂上，就是第一条的随机问题。所以 `looks.py` 按文件名只放不带丝袜的那个（staging 条目可以写成 `(mod, 文件夹, 文件名)`）。
- `hq_mod_outfits.py` 新增登记表 `_meta\hq_materials\mod_outfits.json`（键同 `OUTFITS`，另有 `files`：存档里 mod 源文件的分组，`any_mount`：
  mod 自己的挂载名，`/Game/<路径>` 按 `*/Content/<路径>` 找，`overrides`：CNS 默认贴图）；`read_game` 也跟进网格槽直接引用的游戏材质实例；
  归档成品里没有的贴图（替换型 mod 用到的游戏贴图、`swap_mod_mesh.py` 没用到的 mod 贴图）导出到 `textures\extra\`。
- 画廊：`python mod_gallery.py --looks <清单.json>` → `E:\game_export\StellarBlade\_mod画廊\index.html`（缩略图在 `thumbs\`，链接都是相对路径）。

**Vindictus 那批 mod（2026-11-22：5 个 mod、6 套，同一套批处理脚本）**

11-14 调研的剑星 Vindictus mod，当时只做了 Demon Maiden 一个样品。用户下齐以后补完：

| 一套 | mod | 底包 | 另外做了什么 |
|---|---|---|---|
| `Mod_HeraldOfGoddess` | #1670 CNS | `CH_P_EVE_23` | — |
| `Mod_VindictusLaniakea` | #2233 CNS | `CH_P_EVE_01_Body` | 换上它的 CNS 发型；前臂上的布料飘带转成下垂 |
| `Mod_EvilMaid` | #1347 替换型 | `CH_P_EVE_37_TypeB` | 加上它的角（替换圣诞 DLC 的雪橇耳饰） |
| `Mod_SummerVacation`、`_Tits` | #1487 替换型 | `CH_P_EVE_51` | — |
| `Mod_VindictusDemonMaiden_Hair` | #1807 CNS + 发型替换 | `CH_P_EVE_01_Body` | 换上它的发型（替换游戏的 `EVE_HR_Nikke_03`，带角） |

- **CNS 服装的底包按它引用的物理资产挑**：Herald of Goddess 的网格写的是 `CH_P_EVE_23_Physics` / `CH_P_EVE_23_AnimBP`，
  裙摆挂在 23 号的 34 根 `Ab-*-Skirt*` 骨上。换进身体底包时这些骨没有，裙子会不跟着动；换进 23 号，234 根骨全对上，误差 0.003 cm。
  Laniakea 的参考骨架整体大 0.35%，试了 7 个底包（含 6 个 Nikke 服装）误差都在 0.4 cm 上下，用身体底包。
- **songeda 的替换型 mod 挂载名是自己起的**（`evilmaid2337/Content/art/...`、`summer651/Content/...`），对应游戏的 `/Game/...`。
  `any_mount` 按 `*/Content/<路径>` 找，mod 的容器带 `_P` 优先，cue 那步按分段三角形数核对，确认读到的是 mod 的网格。
  它们还换了身体贴图（`CH_EVE_BaseBody_V02_*`），texfix 按同名替换。
- **发型挂在 `SC_Hair` 上，`SC_Hair` 就在 `Bip001-Head`，没有偏移**（`CH_P_EVE_01_Skeleton` 的挂点表）。
  - 游戏挂的是发型网格的组件坐标系，发型根骨自己的朝向不起作用。
  - 归档包里默认发型的根骨叫 `Hair_Root`，当初是把它对到挂点上的。
  - 直接把新发型的根骨对到 `Hair_Root`，只对根骨朝向和默认发型一样的发型成立：Nikke_03 发型这样放上去转了 180°，前发在脑后，左右也对调了。
  - 现在的做法：挂点坐标系 = `Hair_Root` 的骨骼矩阵去掉导入器的骨骼轴约定，是一个轴的循环置换（`attach_hair.py` 的 `SOCKET_FROM_HAIR_ROOT`）。
  - Laniakea 的侧马尾、Evil maid 的角也按这个放，位置都对。
- **游戏头发材质 `MA_CH_Hair`**：颜色是发根色 → 发梢色。走向按 `HairTexture` 那张 ADIR 贴图的第 4 个通道，发根是 0、发梢是 1；
  另外 R 是发丝遮罩，G 是深度，B 是发束编号。透明用 `Alpha` 参数那张图。CNS 发型的默认颜色在 `VectorControls` 里，游戏运行时套上，这里也套。
  Laniakea 是金发加蓝色发梢。
- **布料模拟的段**（网格分段的 `CorrespondClothAssetIndex >= 0`，游戏用 NvCloth 模拟）：网格里存的是绑定姿势。
  Laniakea 前臂上两条 1 米多长的飘带，在绑定姿势里水平伸在身后。`hang_cloth.py` 把这种长条按挂接点转成垂直下垂，
  再顺着它加一串骨骼（`Streamer_L/R_01..`，每节 15 cm 左右），PMX 导出的 mmd_cloth_physics 按飘带做物理。
  只转不加骨骼时，飘带刚性跟着前臂，跳舞一抬手就竖到头顶上。
- **发型的物理靠骨骼名**：PMX 导出的 mmd_cloth_physics 只给头骨下面名字像头发的骨骼做物理
  （`hair|ponytail|twintail|braid|bang|fringe`）。Laniakea 的 `joint2..30`、Nikke_03 的 `Ab-Front-*` 起初都没有物理，
  `attach_hair.py` 给它们加了 `Hair_` 前缀以后：Demon Maiden 27 条链，Laniakea 3 条。
- Laniakea 的侧马尾在 Blender 里用 mmd_tools 默认物理时，一开始就翻到头顶上；用预览的 `--physics mmd`
  （按 MMD 本体的 Bullet）是正常的。这一套的跳舞预览按 MMD 方式渲染（`looks.py` 的 `preview_args`）。

**画廊补齐 + 高清版的两个坑（2026-11-22 下午）**

画廊里有 4 张卡片发灰，都是之前做的，各少一种格式：Gantz Sling 三套（11-14 用 `swap_mod_mesh.py` 做的）没有高清版，
Original Proportions 赤足没有 XPS。

- 赤足：`blender2xps` 从归档的 `Eve_Nude_Barefoot.blend` 导出（189 根骨、10 个网格、11.3 万顶点，没有警告），
  再 `archive_exports.py stellarblade --only Nude_Barefoot` 归档。
- Gantz Sling：三个 zip 解到 `_meta\mod_sources\GantzSling_mtsqn\unzipped\<zip 名>\`（挂载名 `SB/Content`），登记进
  `_meta\hq_materials\mod_outfits.json`（槽取 `mod_swap.json` 的 `slot_names`），再 `hq_mod_outfits.py --only <包名>`。
- **坑 1：CUE4Parse 的列表不跨容器合并。** 替换型 mod 的包和游戏自己的包路径一样，`-l` 会各列一次（游戏 229267 个 + mod 16 个，
  一个没去重）。按通配符要，两份都导出，并行写同一个 JSON：要么文件被占用崩溃（Gantz Sling 第一次就是），要么谁后写完算谁。
  精确路径只取读取顺序最高的那份（mod 的 `_P`，试了 3 次都是 mod 的）。
  - `hq_mod_outfits.py` 现在先 `-l` 把通配符换成精确的 `.uasset` 路径再导出（`listed()`）：不分大小写去重；同一个 `/Game` 路径
    在两个挂载名下时，取这个 mod 自己的那份，没有就取游戏的 `SB/Content`（不取 `~mods` 里别的 mod 的）。贴图（`fetch_textures()`）也这样。
  - 查过这批 54 套：mod 自带的、游戏里也有的材质实例，高清版没有一个读成游戏那份，只有 Gantz Sling 撞上了。
- **坑 2：同名贴图先找到游戏那份。** `hq_materials.py` 的 `find_texture()` 按 `--textures` 的顺序找，每个目录先找本层再找 `extra\`。
  `hq_mod_outfits.py` 原来把 `textures\mod`（换网格那步放的 mod 自己的贴图）排在最后。替换型 mod 的贴图用的是游戏原名，就被
  `textures\` / `extra\` 里底包的游戏原版顶掉了。现在 `textures\mod` 排第一个（皮肤贴图的 `skin_record()` 也是）。
  - 已经交付的高清版里有 12 套受影响：Crimson Wings BBB 的 8 套（Lux / Vinyl / Nude）两张法线
    `CH_P_EVE_OneMillion_01_UV1_N` / `UV2_N`，Crimson Wings OP 的 4 套底色 `UV1_A`。其余同名的两份内容一样，或者高清版没用到。
    这 12 套的 PMX 带的是 mod 自己的贴图（md5 核对过），只有插件切到「游戏材质」时用的高清版不对。
    11-22 已重做（`finish.py hq` + `finish.py addon`）：插件每套 16–18 个材质全换上、没缺图，存档里同名贴图接错的 24 处 → 0 处。
- Keyhole dress 的第 4 个槽（21896 个面）：mod 的网格挂的是 `CH_P_EVE_09_V02` 的 `MI_CH_P_EVE_V02_TypeB_Back`，
  `swap_mod_mesh.py` 按槽名 `MI_CH_P_EVE_29_03` 拿了 29 号的材质。高清版这块沿用普通版，4 个材质换了 3 个。

## `validate_eve.py`

脚本导入 Eve 的标准身体、完整 Face_003、默认发型和独立长马尾。身体/头发 PSK 会检查
`ACTRHEAD`，头部会检查 `UEFORMAT` 并核对 53 个源 Morph 与 Blender 的 54 个 Shape Keys
（含 Basis），再按原骨骼锚点组合组件、保存 `.blend`、渲染 PNG 并写出 JSON 报告。

- 主发型的本地原点对齐身体骨架的 `SC_Hair`；
- 长马尾按双方共有的 `Ab-TL-HairB01` 完整静置骨矩阵恢复位置和旋转；
- 每个组件保留自己的原始骨架、蒙皮权重和对象层级；
- 脸、眼、眉、牙齿、身体和头发连接验证用材质，不覆盖原始导出文件。

当前官方 UEFormat Blender 插件声明 Blender 4.x。Blender 3.6 使用方法：下载
[官方 UEFormat 源码](https://github.com/h4lfheart/UEFormat)，在源码根目录应用
[`ueformat-blender36.patch`](ueformat-blender36.patch)，然后把
`--ueformat-source` 指向 `plugins\blender\io_scene_ueformat`。补丁只跳过 Blender 4
专用骨骼调色 API；解析器、网格、骨架、权重和 Morph 数据不改写。

本机已验证命令：

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background `
  --python 'E:\code\othercode\ripper_tpose\scripts\stellarblade\validate_eve.py' -- `
  --body 'D:\stellarblade_exports\fmodel_exports\SB\Content\Art\Character\PC\CH_P_EVE_01\CH_P_EVE_01_Body.psk' `
  --head-uemodel 'D:\stellarblade_exports\fmodel_exports\SB\Content\Art\Character\PC\CH_P_EVE_Head\CH_P_EVE_Face_003.uemodel' `
  --ueformat-source 'C:\Tools\UEFormat\plugins\blender\io_scene_ueformat' `
  --hair 'D:\stellarblade_exports\umodel_exports\Art\Character\PC\00_HR\EVE_HR_01\EVE_HR_01.psk' `
  --tail 'D:\stellarblade_exports\umodel_exports\Art\Character\PC\00_HR\EVE_HR_01\EVE_HR_01_Tail.psk' `
  --face-assets 'D:\stellarblade_exports\umodel_face_exports' `
  --body-diffuse 'D:\stellarblade_exports\fmodel_exports\SB\Content\Art\Character\PC\CH_P_EVE_01\Tex\Body\CH_P_EVE_01_Body_D.png' `
  --hair-alpha 'D:\stellarblade_exports\umodel_exports\Art\Character\PC\CH_P_EVE_Hair\Textures\PonyTail_Alpha.png' `
  --output 'D:\stellarblade_exports\blender\Eve_Standard_validation.blend' `
  --render 'D:\stellarblade_exports\validation\Eve_Standard_validation.png' `
  --report 'D:\stellarblade_exports\validation\Eve_Standard_validation.json'
```

已验证结果为 5 个网格、5 套原始骨架、114,589 顶点、141,084 个面和 346 根骨骼
（含 2026-08-29 补齐的后颈短发束 `EVE_HR_Tail_Short`，经 `--tail-short` 按
`Bip001-Head` 静置骨对齐；早期 4 组件数据见 CHANGELOG）。
Face_003 单独包含 24,350 顶点、35,992 个面、11 个材质槽和 53 个 Morph；脸部近景
`D:\stellarblade_exports\validation\Eve_Standard_validation_face.png` 已视觉复核。

仓库只保存脚本和说明，不保存游戏 PSK、贴图、mapping 或第三方可执行文件。
