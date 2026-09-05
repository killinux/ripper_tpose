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
`python html\make_gallery.py` → `html\index.html`；亮预览由
`..\final\html\render_blend_preview.py -- D:\stellarblade_exports\blender --suffix _gallery` 补渲
（`validate_eve.py` 自己的渲染偏暗，仍保留在 `validation\`）。

## 裸模（EveOriginalProportions Mod）

原版没有 nude 资产；裸模来自本机安装的 EveOriginalProportions Mod（覆盖
`CH_P_EVE_InnerSuit`）。四个变体已用专用 UE Viewer 导出到
`D:\stellarblade_exports\umodel_mod_exports\<variant>\`（Mod 是独立 IoStore
三件套，导出时需在 staging 目录放游戏的 `global.utoc/ucas`）。组装复用
`validate_eve.py`，但 UE Viewer PSK 不含 socket、裸模骨架缺 `SC_Hair`，需加
`--alignment-reference <标准验证报告.json>` 复用其中记录的发型根变换；马尾
仍按共有的 `Ab-TL-HairB01` 原生对齐。产物：
`D:\stellarblade_exports\blender\Eve_Nude_Barefoot.blend`。

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
