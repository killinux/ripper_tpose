# The First Descendant（第一后裔）模型导出

Nexon 的《The First Descendant》(内部代号 **M1**，Steam `2074920`，UE5)。游戏用
一个 IoStore 容器 `M1-Windows.{utoc,ucas,pak}`：**utoc v5 / pak v11 / Oodle 压缩 /
目录索引 AES 加密**。本目录的脚本直接解密并读它的目录索引，把里面的骨骼网格按
游戏的组织方式归类，再用 UE Viewer 导出网格、Blender 合骨架出 `.blend` + 预览图。

> **贴图注意：** 本作的贴图是 UE5 **虚拟贴图（Virtual Texture）**，UE Viewer 解不了
> （导出时会报 `it's a virtual texture` 跳过）。所以**这条 umodel 线只出几何 + 骨架，
> 是白模**。要带贴图，走 FModel + usmap（见文末「完整贴图」）。

## 快速开始

在本目录里跑（PowerShell 先 `cd 〈仓库〉\scripts\firstdescendant`）。

### 看有哪些模型（查看列表）

```powershell
python .\list_models.py                       # 全表：id / kind / char / 部件 / umodel / blend
python .\list_models.py --kind descendant     # 只看一类：descendant/skin/monster/boss/npc/weapon/accessory/fellow/vehicle
python .\list_models.py --char Bunny          # 某个后裔的默认装 + 所有皮肤
python .\list_models.py --resolve Bunny --json    # 某个模型：每个部件的包路径、PSK 是否已导
python .\list_models.py --raw --path-filter /Monster/UNQ/   # 容器里的原始路径（找没归类到的）
```

当前编目 **2067 个模型**：33 个后裔（含 Ultimate 变体）、1075 套皮肤、201 只普通/精英怪、
54 个 Boss 部件、99 个 NPC、250 把武器、248 件配饰、58 个宠物件、49 个载具件。

- 后裔代号 → 名字来自 `PC/MESH/PRESET/<名字>/PC_<编号>_<A|U>0101`（A = 标准，U = Ultimate）。
- **后裔默认装** = 一整块合并网格（身体+头+头发+脸），导出最干净。
- **皮肤** = `SKIN/<类别>/<序号>/..._(BODY|HEAD)` 的一套（BODY + HEAD + 该后裔的 Face），
  类别有 F / M / MF / CMN / AGT / BOS / CLB / EVO / VAR 等（Makeup 只是材质，跳过）。

### 导出一个模型

```powershell
.\export_model.ps1 Bunny                 # 后裔默认装
.\export_model.ps1 Bunny_CMN_001         # 一套皮肤（自动配脸）
.\export_model.ps1 MOB_CMN_1001_A001     # 一只怪
.\export_model.ps1 BOS_1001_A001 -IncludeExtras   # Boss 连同它的 Parts 一起
.\export_model.ps1 Bunny -Force          # 重做
```

一条命令三步：`list_models.py` 解析包 → UE Viewer(`-game=first`) 逐包导出 PSK/PSKX
到 `D:\tfd_exports\umodel_exports\` → Blender 无头跑 `build_blend.py` 合骨架、渲预览、
存 `.blend`。产物：

```text
D:\tfd_exports\blend\<id>\<id>.blend      一副骨架 + 全部部件（白模）
D:\tfd_exports\blend\<id>\preview.png / preview_face.png
```

常用参数：`-Force`（重做）、`-NoBlend`（只到 UE Viewer）、`-NoPreview`、`-Smooth`
（平滑法线）、`-IncludeExtras`（把 Parts/Separate_Parts 也并进来）、`-Kind` / `-Char`
（配合 `-List`）；路径都有默认值（`-GameRoot`、`-ExportRoot D:\tfd_exports`、
`-UmodelExe`、`-BlenderExe`、`-AesKeyFile`）。

### AES key（只做一次）

脚本从 `TFD_AES_KEY` 环境变量或 `D:\tfd_exports\_keys\aes_key.txt` 读密钥。key 不在
安装目录里明文存着（Nexon 用 8 条 `mov imm32` 在运行时拼出来，跟 Vindictus 一样），
用 `find_aes_key.py` 从 shipping exe 里重建：

```powershell
python .\find_aes_key.py --out D:\tfd_exports\_keys\aes_key.txt   # 约 60 秒
```

**key 绝不写进仓库 / CHANGELOG / 画廊**（与 FF7R、Vindictus 同规矩）。

## 已验证环境

```text
游戏：E:\SteamLibrary\steamapps\common\The First Descendant（Paks 在 M1\Content\Paks）
UE Viewer：spiritovod 的 UE5 build，umodel_materials_ue5.exe（build 1579 fix282，自带 Oodle）
           E:\tools\umodel_specific\materials\umodel_materials_ue5.exe，游戏 tag = first
Blender：3.6.15 + io_scene_psk_psa（PSK/PSKX 导入器）
Python：3.13 + cryptography（解 utoc 目录索引用）
```

已跑通：后裔 Bunny（270 骨 / 111438 顶点，单块合并网格）、皮肤 Bunny_CMN_001
（Body+Head+Face 合成 348 骨）、怪 MOB_CMN_1001_A001（101 骨）。

## 目前的限制

- **白模**：贴图是虚拟贴图，umodel 导不出（见下）。几何、骨架、材质槽划分都在。
- **皮肤的头部配件**偶尔会掉在脚边：皮肤的 `HEAD` 部件里若含一个只挂 socket 的小件
  （头盔/面具），它的骨在底模里没有对应位置时会留在原点。身体 + 脸是对的。后裔默认装
  没有这个问题（本来就是一整块）。
- 面部 morph（PSK 不带；需要 `-morphs` 且 umodel 对本作 morph 支持有限）暂未验证保留。

## 完整贴图（FModel + usmap，后续）

本仓库已有 FModel（`E:\tools\fmodel\FModel.exe`，FF7 Remake/Rebirth/Stellar Blade 都用它）。
FModel 的 CUE4Parse 能解虚拟贴图，但要一份 **.usmap** 映射表来解 zen 包属性（社区版在
Nexus `thefirstdescendant/mods/5`）。思路同 FF7 Rebirth 那条线（`scripts/final/fmodel_export_player.py`
用 pywinauto 驱动 FModel「Save Folder's Packages」）：在 FModel 里加 TFD 目录 + AES + usmap，
导 PNG 贴图，再让 `build_blend.py` 按材质槽挂上去。尚未接上——这版先交几何。

功能更新统一追加到 [更新日志](../../docs/CHANGELOG.md)。utoc 解密器与 `find_aes_key.py`
来自 [scripts/vindictus](../vindictus)（同为 Nexon UE5 IoStore 游戏）。
