# Dead or Alive 5 Last Round 脚本说明

DOA5LR（Team Ninja 私有引擎）角色提取与转换。链路：

```
游戏 .bin/.lnk 封包
   │  ① extract_lnk.py        （解混淆文件名 + XOR 解密 + 分块 zlib 解压）
   ▼
TMC（模型+贴图引用） + TMCL（贴图库）
   │  ② Noesis + doa5pc_custom.py 插件（export_character.ps1 自动调用）
   ▼
FBX + DDS 贴图  （D:\doa5lr_exports\<名字>\<服装>\）
   │  ③ build_blend.py        （export_full.ps1 自动调用：材质重建+打包+渲预览）
   ▼
带材质 .blend + 预览图  （D:\doa5lr_exports\_blends\）
```

> 提取内核是**自研 Python 移植**（`extract_lnk.py`），算法来自社区 Archive Tool 1.2.1
> 附带的 C# 源码；不依赖 GUI 工具，可脚本化批量。Archive Tool/Texture Tool 原版
> 保留在 `E:\tools\doa5lr\` 作对照与修 mod 用。

## 1. 环境准备（一次性，已部署）

| 依赖 | 路径 | 说明 |
|---|---|---|
| 游戏本体 | `D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 5 Last Round` | `.bin`（LFMO 索引）+ `.lnk`（CHCM 数据）成对 |
| doaKey | `E:\tools\doa5lr\doaKey` | 522 字节 XOR 密钥（Archive Tool 资源内提取） |
| file5lr.dat | `E:\tools\doa5lr\file5lr.dat` | 混淆名 → 真实名 + flags 数据库（社区维护） |
| Noesis | `E:\tools\noesisv\Noesis.exe` | 已装 `plugins\python\doa5pc_custom.py`（TMC）、`fmt_doa5pc_tex.py`（--H/--P）、`fmt_doa5pc_tmcmesh.py` |
| Python 3 | `D:\openclaw\python\python.exe` | 标准库即可，无第三方依赖 |
| 输出 | `D:\doa5lr_exports\` | |

Blender 侧插件（可选，做 mod 或精修用）：`E:\tools\doa5lr\blender_tmc_importer\io_import_tmc_pc.py`
（Blender 2.80+ 的 TMC 直接导入，与 Noesis 链路互为备选）。

## 2. 快速开始

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa5lr

# 列出 chara_common 全部条目（2867 条）
.\export_character.ps1 -List

# 一个角色全部服装+发型（HONOKA 前缀）
.\export_character.ps1 HONOKA

# 只要一套服装 / 多个目标
.\export_character.ps1 HONOKA_COS_001,KASUMI_COS_002

# 只提取 TMC/TMCL，不转 FBX
.\export_character.ps1 HONOKA -NoConvert
```

产物：`D:\doa5lr_exports\<目标>\<服装>\` 内 `*.fbx` + `Tex_NN(L_x).dds`（L=全尺寸，
M=小 mip 变体，同名 L/M 是同一张图）。

`extract_lnk.py` 也可单独使用（其他 `.bin/.lnk` 对同样适用，如 `patch_XX_catalog`）：

```powershell
python extract_lnk.py "<游戏目录>\chara_common.bin" --list --filter "MARIE*"
python extract_lnk.py "<游戏目录>\patch_25_catalog.bin" -o D:\out --filter "*.TMC*"
```

## 2.5 出带材质 .blend（export_full.ps1 + build_blend.py）

```powershell
# A 官方内容：按名字从封包提取（服装 + 头发 → 一个带贴图的 .blend + 预览图）
.\export_full.ps1 KASUMI_DLC_011 -Archive chara_initial -Hair 001

# -Hair 可给编号或完整名；不加就是光头（服装 TMC 不含头发）
.\export_full.ps1 HONOKA_COS_001 -Hair HONOKA_HAIR_002 -Label Honoka_战衣

# B 外部 mod（nude mod 等）：直接喂 .TMC 文件
.\export_full.ps1 -TmcFile D:\mods\KasumiNude.TMC -Label KAS_Nude
.\export_full.ps1 -TmcFile D:\mods\body.TMC -HairTmc D:\mods\hair.TMC -Label X

# 混用：mod 身体 + 官方发型（-Hair 用编号时要同时给角色名作前缀来源）
.\export_full.ps1 KASUMI_DLC_011 -TmcFile D:\mods\nude.TMC -Archive chara_initial -Hair 001 -Label KAS_Nude
```

**外部 mod 说明**：DOA5LR 的 mod 就是替换用的 `.TMC` + 同名 `.TMCL`（贴图库），
和官方格式完全一致，所以 `-TmcFile` 直接吃即可（`-TmcFile` 也接受目录，会取其中
第一个 `.TMC`）。找不到同名 `.TMCL` 会警告并出白模。产物中转目录：
`D:\doa5lr_exports\_mods\<TMC名>\`。

> 官方内容**没有** nude：全部 36 个封包、12,625 个条目名搜
> `nude/naked/bare/skin/under/lingerie` 零命中。nude 只能用社区 mod，
> 而 DOA5LR 的 mod 在 GameBanana 上是 0 个，主要在 LoversLab（需登录手动下载）。

产物：`D:\doa5lr_exports\_blends\<Label>.blend`（贴图已打包，单文件可搬走）
+ `<Label>_preview.png`。

实现要点（与 DOA6 的差异）：

- **不需要材质映射**。Noesis 的 doa5pc 插件已在 FBX 里写好每个材质的
  Diffuse/Normal/Specular 贴图连接；`build_blend.py` 只是按统一接法重建
  （法线转 Non-Color 走 Normal Map 节点）。语义在**图像数据块名**
  （`Diffuse Texture.NNN`）上，不是节点名。
- **Alpha 要按数据判断，不能无差别接**。DOA5LR 很多贴图把高光/混合遮罩塞在 diffuse
  的 alpha 通道里；无差别接到 Principled.Alpha 会让皮肤和衣服变成半透明抖动噪点。
  `has_real_transparency()` 用 numpy 采样，要求**同时**满足两条才认定为镂空遮罩：
  **>2% 全透明像素** 且 **>4% 全不透明像素**（镂空必然"该实的全实、该空的全空"）。
  实测冒充者：霞 `Tex_27`（0.00~0.91 连续，两端占比都是 0%）、穗香 `Tex_01`
  （62% 全透明但最大只有 0.34）、穗香脸部贴图（3% 全透明、max 0.99，但均值仅
  0.12 → 几乎没有实心区域）。真遮罩实测：头发卡片 全不透明 6~54% / 全透明 30~40%。
- **三部件**：服装 `COS_NNN`（不含头部）+ 脸 `FACE`（无编号）+ 头发 `HAIR_NNN`。
- **尺度归一化**：Noesis 的 DOA5 FBX 以 scale 0.01 导出，角色只有 ~1.6cm 高，
  会整个落在相机默认近裁剪面内（渲染全空）。脚本把根物体统一缩放到约 1.7 单位。
- **部件对齐：默认不动**。实测**绝大多数角色的脸/头发本来就和服装同处一个坐标系**
  （脸 Z 已接在颈口上方、头发顶端已到头顶），直接叠加即正确。早期版本无条件按
  包围盒对齐，反而把对的挪歪了——马尾的包围盒顶端是发梢而非头顶、中心也不在头
  中心，于是头发被压到脸前面（红叶、穗香就是这么坏的）。女天狗更严重：她的翅膀
  把身体包围盒撑大，导致脸被误判为"不在位"而整个挪走 → 表现为没有脸。
  现在只在部件确实不在身体坐标系时才搬，判定用部件**顶端**是否够到身体顶端
  （用底端会被马尾误导）。少数角色（霞，来自 `chara_initial`）的脸有 X 存储偏置、
  头发用自己的局部原点，这类才需要居中/搬运。搬运时锚点优先级：服装自带的
  `*Head*` 网格 > 已就位的脸 > 身体包围盒顶部，故部件顺序必须是
  **服装 → 脸 → 头发**（`export_full.ps1` 已保证）。
- **DDS→PNG**：Blender 读不了部分 BC 压缩格式，`export_full.ps1` 会先用 Noesis
  转一份同名 PNG，组装脚本优先使用。

## 2.6 html/ —— 导出总览画廊

和 `scripts\riseoferos\html\` 同款：manifest → 缩略图 → 自包含单页。

```powershell
blender --background --factory-startup --python html\collect_manifest.py
python html\make_gallery.py            # 加 --force 重建缩略图
```

`collect_manifest.py` 在 Blender 无头下逐个打开 `_blends\*.blend`，按网格名前缀
（`WGT_body*`/`WGT_face*`/`WGT_hair*`）统计部件、材质、透明材质与贴图数，
写出 `D:\doa5lr_exports\doa5lr_models_manifest.json`；`make_gallery.py` 读它生成
`html\index.html`（搜索、按封包筛选、告警筛选、点图看原图、一键复制 blend 路径）。

封包徽标由脚本现扫 `chara_common`/`chara_initial` 的索引得出，对应 `-Archive` 参数。
注意匹配必须**精确**到 `<角色>_COS_001.TMC`——用子串匹配会被
`KASUMI_BOSS_COS_001.TMC` 命中，把霞误标成 `chara_common`。

缩略图写在 `D:\doa5lr_exports\_gallery\thumbs\`，**不进仓库**。

## 3. 格式与实现要点

- `.bin` = `LFMO` 索引：0x30 起每 12 字节一条 `(offset+1)` 指向混淆名（`/` 前缀跳过）；
  真实名/flags 查 `file5lr.dat`（TSV：混淆名/真实名/flags/索引，`end_flag` 后为历史行）。
- `.lnk` = `CHCM` 数据体：0x20 起每 32 字节 `(offset, _, size, ...)`。
- flags 首字符：`0`=原样存储；`E`/`C`=XOR 加密+压缩；其他（如 `4`）=仅压缩。
- 解密：动态 key = uint32 运算 `(((n+0x3E7)*7)/0xB)+(n%0x11)+0x1AC`（n=解压大小），
  取小端字节倒序去零；与 doaKey 循环 XOR；0 字节与等于 key 流的字节不变。条目前
  4 字节是解压大小头，不参与。
- 解压：`[u32 解压大小][块]...`，块头 u32 >0x8000 时减 0x8000 为 zlib 块长，否则原样
  块；每块后按 `(pos-4)` 16 字节对齐。
- DLC/后期服装在 `patch_XX_catalog` 里，名称仍由 file5lr.dat 解析。

## 4. 已验证

- HONOKA_COS_001：TMC 魔数正确（`TMC\0`），Noesis 转出 FBX 1MB + 30 张 DDS。
- HONOKA_HAIR_001：`export_character.ps1` 全链路（提取→FBX+DDS）exit 0。
- KASUMI_DLC_011 + KASUMI_HAIR_001：`export_full.ps1` 出 13.7MB .blend
  （59 材质重建、82 贴图打包、头发对齐 dz=0.005），渲染正常。
- 全 36 个封包可解析，TMC 模型合计 **1099** 个（chara_common 572、rtm_common 265、
  chara_initial 106、stage_* 141、patch_* 14、common 1）；角色模型 678 个 / 34 名角色。

## 4.5 封包分布（哪个角色在哪）

模型分散在多个 `.bin/.lnk`，`export_character.ps1 -Archive` 要选对：

| 封包 | 内容 |
|---|---|
| `chara_initial` | **常规服装/发型的主场**（如 `KASUMI_DLC_011`、`KASUMI_HAIR_001`） |
| `chara_common` | BOSS 变体（`KASUMI_BOSS_*`）与公共件 |
| `rtm_common` | 过场动画版角色（265 个） |
| `patch_XX_catalog` | 后期 DLC |
| `stage_*` | 场景 |

不确定就先查：
`python extract_lnk.py "<游戏>\chara_initial.bin" --list --filter "KASUMI*"`

## 5. 坑

- **.ps1 必须带 UTF-8 BOM**：Windows PowerShell 5.1 读无 BOM 中文脚本按 GBK 解析会
  报"missing terminator"。本仓库两个 DOA 脚本已带 BOM，重存时别丢。
- Noesis 的 DOA5 插件是 32 位 `Noesis.exe` + `plugins\`（Python 插件两边都能用）；
  不要与 DOA6 的 `Noesis64.exe` + `plugins\x64\ProjectG1M.dll` 混淆。
- `--filter "HONOKA*"` 会同时匹配 `--H/--HL`（物理/头发辅助文件）；批量脚本只取
  `*.TMC*`，需要 `--H` 时手动跑 `extract_lnk.py`。
