# Venus Vacation PRISM 原始资源解包

这组脚本直接读取游戏的 `fdata_package/*.fdata`，不注入游戏进程，也不修改安装目录。它能枚举原生 G1M 模型，并把选中的条目从 PRISM 的分块 Zlib 数据中还原出来。

## 快速上手（与 riseoferos/extract_character.ps1 相同的操作方式）

```powershell
cd scripts\venusvacationprism
.\export_character.ps1 -List                 # 查看可导出角色（中/英/代码名）
.\export_character.ps1 Nanami                # 按名字一键导出（blend+fbx+glb）
.\export_character.ps1 七海,菲欧娜            # 逗号分隔多名
.\export_character.ps1 Fiona -Format blend,glb
.\export_character.ps1 Tamaki -Plan          # 只打印将用的模型/工具/路径
.\export_character.ps1 Honoka -Resume        # 断点续跑
.\export_character.ps1 -ListModels           # 生成原生 G1M 清单（models.csv/json/md）
.\export_character.ps1 -ListModels -Probe    # 逐个解压补充骨骼数/版本（慢）
```

游戏目录与输出目录自动解析（`-GameRoot`/`-OutputRoot` 可覆盖；输出默认
`D:\venusvacationprism_exports\<角色>\complete_auto`）。旧的 GNU 风格调用
（`.\export_character.ps1 --name 穗香 ...`）原样透传，继续可用。

浏览原生模型（不经过角色 profile）用 `export_model.ps1`——按需转换，不批量：

```powershell
.\export_model.ps1 -List            # 71 个角色候选：索引/KTID/骨骼数/大小/已知名称/已转换
.\export_model.ps1 -List -AllModels # 全部 1,527 个 G1M
.\export_model.ps1 830              # 转换一个：FDATA→G1M→glTF→.blend+前后预览图
.\export_model.ps1 830,833 -Force   # 多个 / 重转
.\export_model.ps1 FACE_FON_000     # 也接受内部名称或 0xKTID
```

输出在 `D:\venusvacationprism_exports\models\model_<索引>_<KTID>\`。注意
两点：①这是 gust_stuff basic glTF 管线，只有几何+骨架+权重（灰模无贴图），
识别模型内容够用；带材质的完整人物仍走 `export_character.ps1`。②所有 BODY
模型**没有头**是游戏设计（头在 FACE、头发在 HAIR 组件），不是导出不全。
首次运行会自动构建 probe 清单和角色名对应表（一次性，几分钟）。

## 当前验证结果

在 2026-08-08 的本机 Steam 安装中：

- G1M 条目：1,527
- 唯一 G1M ID：1,527
- 含 G1M 的 FDATA 包：69
- 解压后 G1M 总量：约 2.09 GiB
- 含至少 50 个骨骼节点的角色候选：71
- 已由内部名称哈希确认的六名角色分件：35

“角色候选”是按骨骼数量得到的技术筛选结果，不等于 71 个不同角色。游戏会把身体、脸、服装、头发等拆成独立模型，也存在共用组件。

## 0. 素体（nude）结论与完整组装

71 个角色候选逐个转换目检后确认：官方资产中**素体只有一组**，位于
`0x8baaa1ce.fdata` 的模块化展示套件——

| 索引 | 内容 | 说明 |
|---|---|---|
| 836 | 带头假人素体 | 皮肤贴图躯干为灰色（试衣底模），不适合直接用 |
| **840** | **无头全裸素体** | **完整皮肤贴图**，26,226 顶点 / 355 骨 |
| 843 | 配套展示头（含脸） | 69 槽标准脸布局，但静置位置比标准 FACE 高约 6.7 |
| 844 | 配套发型 | 半扎公主头；前发束是物理骨绑定姿态，静置垂在脸前 |
| 852 | 配套手臂 | 备用件 |

另有 114/118/849 三个内衣/塑身衣体（半裸）。其余候选均为服装体。

已验证的完整组装（840+843+发型，全贴图、虹膜烘焙、透明卡片）：

```powershell
# 组件提取（含 843 缺失贴图豁免与虹膜槽位覆写，见 profiles/nude840.json）
python character_assets.py --game <游戏目录> --output D:\venusvacationprism_exports\nude840\components `
  --gust-dir ..\..\.tmp\gust_stuff --converter-deps ..\..\.tmp\gust_deps --python-deps ..\..\.tmp\pydeps `
  --profile profiles\nude840.json --resume
# Blender 组装（--face 现为可选；无 FACE 的身体可只配 --hair）
blender --background --python-exit-code 1 --python blender_assemble_character.py -- `
  --character Nude840_NNMHair --body <BODY_NUDE_840.gltf> --face <HEAD_NUDE_843.gltf> `
  --hair <HAIR_NNM_001.gltf> --face-alpha 1,4,5,7,8,9 --hair-alpha 0,1,2 `
  --output-dir <out> --formats blend fbx glb
```

要点：①843 的眼贴图在槽 27/28、37/38（标准脸是 25/26、35/36），profile 的
`postprocess.face_v1_iris_pairs` 可覆写虹膜烘焙槽位对；②这套展示件的
静置位置**彼此不共位**：843 头比标准脸高 ~6.7，而 840 身体的领口
（zmax 134.7）又低于标准脖口，所以组装后需要把头下移 −16.5、发型下移
−9.58（保持发-头相对 +6.92 的贴合）才能颈胸无缝——成品
`*_Aligned.blend` 已按此对位并目检（颈部黑缝消失）；③843 的原生发型
844 无需相对偏移，但其前发束受绑定姿态所限垂在脸前，与 Fiona NUN
布料同类限制。

## 1. 生成模型清单

```powershell
python scripts\venusvacationprism\list_models.py `
  --game "D:\Program Files (x86)\Steam\steamapps\common\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -" `
  --output "D:\venusvacationprism_exports\inventory" `
  --probe
```

输出：

- `models.json`：完整机器可读清单，含 G1M 区块信息
- `models.csv`：便于 Excel 筛选
- `models.md`：便于直接阅读

不加 `--probe` 时只扫描索引，速度更快；加上后会逐个解压 G1M，并补充版本、骨骼数和候选分类。

## 2. 生成角色—模型对应表

```powershell
python scripts\venusvacationprism\map_characters.py `
  --game "D:\Program Files (x86)\Steam\steamapps\common\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -" `
  --output "D:\venusvacationprism_exports\inventory"
```

输出 `character_models.json`、`character_models.csv` 和 `character_models.md`。当前安装可确认
35 个海咲、菲欧娜、伊莉丝、环、七海和穗香的脸部、头发及少量服装/身体 G1M。每条记录均要求
恢复的内部基名同时命中 G1M，并至少命中 MTL、GRP、OID 中两项；没有名称证据的共用基础身体
不会强行分配给某个角色。

可用中文名、英文名或内部代码只列一名或多名角色，例如：

```powershell
python scripts\venusvacationprism\map_characters.py `
  --game "D:\Program Files (x86)\Steam\steamapps\common\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -" `
  --output "D:\venusvacationprism_exports\fiona" `
  --character 菲欧娜
```

## 3. 按角色名导出完整人物

完整人物由 BODY、FACE、HAIR 三组资源组成。`export_character.py` 会从经过人工验证的
角色 profile 中选择默认组合，解析全部纹理，修补人物材质，然后让 Blender 输出绑定模型。

完整的查看名称、导出、断点续跑和输出说明见
[`README_CHARACTER_EXPORT.md`](README_CHARACTER_EXPORT.md)。

查看当前支持情况：

```powershell
scripts\venusvacationprism\list_character_names.ps1
```

加 `--exportable-only` 只显示当前能一键导出的名字；加 `--details` 显示默认
BODY/FACE/HAIR 的清单索引和 G1M ID；加 `--json` 输出机器可读列表。统一导出入口原有的
`python scripts\venusvacationprism\export_character.py --list-characters` 也继续保留。

按英文名、中文名或内部角色代码导出，例如：

```powershell
python scripts\venusvacationprism\export_character.py `
  --name Nanami `
  --game "D:\Program Files (x86)\Steam\steamapps\common\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -" `
  --output "D:\venusvacationprism_exports\nanami\complete_auto" `
  --formats blend,fbx,glb
```

`--name 七海`、`--name NNM` 与上例等价。

也可以使用较短的 PowerShell 入口；其参数与 Python 命令完全相同：

```powershell
scripts\venusvacationprism\export_character.ps1 `
  --name 穗香 `
  --output "D:\venusvacationprism_exports\honoka\complete_auto" `
  --formats blend,fbx,glb
```

若目标目录里已有阶段结果，加入 `--resume` 会先校验再复用；脚本不会默认覆盖非空目录。

当前无人值守完整导出已开放：

- `Honoka` / `穗香` / `HON`
- `Nanami` / `七海` / `NNM`
- `Fiona` / `菲欧娜` / `FON`
- `Tamaki` / `环` / `TAM`

Misaki 与 Elise 的来源组合也已记录，但前者的旧材质流程尚待迁移，后者有 24 个游戏运行时
纹理句柄无法从安装包的 OBJDB 静态恢复；脚本会明确拒绝，而不是输出一个看似成功但材质错误
的模型。

依赖：Python 3.10+、Pillow 12+、NumPy、pyquaternion、Blender 3.6 LTS，以及
`eArmada8/gust_stuff`。可用 `--gust-dir`、`--blender`、`--python-deps` 和
`--converter-deps` 指定位置。本仓库当前工作环境中的 `.tmp/gust_stuff`、`.tmp/pydeps`
和 `.tmp/gust_deps` 会被自动发现。先加 `--plan` 可以只查看将使用的模型 ID、工具和输出路径。

Python 依赖可按下列方式安装；如果只想解包三组件而暂不启动 Blender，可再加
`--assets-only`：

```powershell
python -m pip install -r scripts\venusvacationprism\requirements-character-export.txt
```

输出包括：

- `{Character}_Complete_Rigged.blend`（使用中贴图已打包）
- `{Character}_Complete_Rigged.fbx`、FBX 材质映射与 Blender 重连脚本
- `{Character}_Complete_Rigged.glb`
- BODY/FACE/HAIR 的原始五件套、逐槽 G1T/DDS/PNG 和 patched glTF
- 四视图、FBX/GLB 回读报告、来源清单和 SHA-256 清单

Nanami 的默认衣装使用已验证的 dry/static 近似：布料 UV1、slot21/22 overlay、slot23
局部法线，以及排除 wet/DT2 条件 pass。它只应用于 BODY722 profile，不会误套到其他模型。

Fiona 使用 BODY857、FACE_FON_001 与 HAIR_FON_001；高领会遮住三套独立组件之间未焊接的
颈部接口。BODY857 的 40 个网格中有 32 个连接骨架，另外 8 个 NUN 布料网格以完整静态
bind pose 保留，游戏内布料模拟没有被还原。Tamaki 使用 BODY842、FACE_TAM_001 与
HAIR_TAM_001。BODY842 当前安装缺少的
纹理槽 26/27/32 未被任何可见 PBR 材质引用，因此会在严格验证后剪除；其左裤腿 NUN 面板
保留完整静态几何，但因源物理 driver 索引不是骨骼权重，不会随之后的骨骼动画变形。它是
该回退新增解绑的唯一网格；转换后 32 个 BODY 网格中有 25 个连接身体骨架，mesh 19–24
原本就是静态转换输出。

## 4. 导出一个原生模型

按清单中的一基序号导出：

```powershell
python scripts\venusvacationprism\export_model.py `
  --game "D:\Program Files (x86)\Steam\steamapps\common\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -" `
  --index 836 `
  --output "D:\venusvacationprism_exports\model_0836_0x7ce546e8"
```

也可以按十六进制 KTID 导出：

```powershell
python scripts\venusvacationprism\export_model.py `
  --game "D:\Program Files (x86)\Steam\steamapps\common\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -" `
  --id 0x7ce546e8 `
  --output "D:\venusvacationprism_exports\model_0836_0x7ce546e8"
```

角色对应表生成后，还可直接按恢复的内部名称导出：

```powershell
python scripts\venusvacationprism\export_model.py `
  --game "D:\Program Files (x86)\Steam\steamapps\common\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -" `
  --name FACE_FON_000 `
  --output "D:\venusvacationprism_exports\FACE_FON_000"
```

输出 `.g1m` 原始模型和 `.json` 来源/结构清单。脚本索引是一基索引，和 `models.csv` 的 `index` 列一致。

## 5. 可选转换为 glTF

原始解包本身不依赖第三方库。若另行下载了 [eArmada8/gust_stuff](https://github.com/eArmada8/gust_stuff)，可把其转换脚本传给导出器：

```powershell
python scripts\venusvacationprism\export_model.py `
  --game "D:\Program Files (x86)\Steam\steamapps\common\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -" `
  --index 836 `
  --output "D:\venusvacationprism_exports\model_0836_0x7ce546e8" `
  --gltf-tool "D:\tools\gust_stuff\g1m_to_basic_gltf.py" `
  --converter-pythonpath "D:\tools\gust_stuff_deps"
```

转换器失败时，已经还原的 G1M 和 manifest 仍会保留。复杂布料模型可能需要 Project-G1M/Noesis 或转换器的额外兼容处理。

## 格式说明

PRISM 使用 KTGL 的 RDB/FDATA 容器。当前安装中的资源条目标志为 `0x00400000`：内容由若干不超过 16 KiB 的 Zlib 块组成，每块前有 10 字节头，其中前 2 字节是小端压缩长度；长度为零表示结束。`prism_rdb.py` 会校验块边界、Zlib 数据以及最终解压尺寸。

模型名数据库所引用的外部 RDX 包没有随当前安装提供，因此全量清单仍使用稳定的 KTID
（例如 `0x7ce546e8`）。不过标准角色资源遵循 KTGL 的确定性名称哈希；只在 G1M 与多个同名
伴随资源同时存在时，`map_characters.py` 才把内部基名和角色归属写入对应表。
