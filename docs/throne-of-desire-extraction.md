# Throne of Desire 模型导出说明

## 结论

Steam 版 `ThroneOfDesire` 不是 Unity 或 Unreal 游戏。它采用 X-Legend 的 `HyenaPC` 封包层，模型与动画资源属于 Gamebryo/NetImmerse 系列：

- 模型：`.nif`，本机样本版本为 `20.3.3.2`；
- 动画集合：`.kfm`；
- 封包：`mobilepack/packageindex`、`mobilepack/FileListPC.txt` 和 `mobilepack/nfs`；
- 模型压缩：带 X-Legend 块头的 zlib；
- 贴图压缩：五字节标记后的 LZHAM raw stream；
- 贴图格式：自定义 FourCC `ETC2`、`ETCA`、`EAC4` DDS。

因此 FModel、UModel 和 AssetStudio 不适合这个游戏。本仓库已经实现从 NFS 到 Blender 3.6/FBX 的独立导出流程。

## 本机资源统计

本次扫描的是：

`D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire\mobilepack`

| 项目 | 数量 |
|---|---:|
| `FileListPC.txt` 声明记录 | 38,756 |
| 带原始路径的普通文件 | 3,547 |
| 哈希 NFS 行 | 35,209 |
| 当前 `packageindex` 成功映射 | 32,780 |
| 磁盘 NFS 包文件 | 2,603 |
| 已识别 NIF | 5,957 |
| 已识别 KFM 模型组 | 323 |

323 个可选模型编号见 [`throne-of-desire-model-list.md`](throne-of-desire-model-list.md)。名称取自 KFM 内部的基础 NIF 路径，游戏封包没有给出可可靠恢复的角色中文名。

## h005 验证结果

`h005` 已完成从游戏封包到 Blender 3.6 和 FBX 的端到端验证：

- KFM 哈希：`c351923786ae5d5f`；
- NIF 哈希：`f0804b2488e19ca8`；
- NIF 所在 NFS 包：`7d41fbcd`；
- 漏索引的实体块已在偏移 `5453264` 恢复；
- 实际 NIF 大小：8,073,911 字节；
- 7 个基础网格、15 个附件网格；
- 67,468 个顶点、115,328 个三角形、219 根静止骨骼；
- 包内共有 35 个贴图流；其中 34 个被当前 NIF 引用并已按文件名精确映射，包尾 1 个未引用旧流只记录在清单中；
- 34 个已引用贴图均已解压为 DDS，并转换为 Blender 可读的 TGA；
- NIF 材质块已经逐网格映射到底色、法线、光泽和高光贴图。底色默认连接；未完全验证的 EAC 法线只保留在节点中，不再默认驱动着色器。

稳定输出路径：

```text
D:\throneofdesire_exports\h005\h005_blender36.blend
D:\throneofdesire_exports\h005\h005.fbx
D:\throneofdesire_exports\h005\h005_preview.png
D:\throneofdesire_exports\h005\export_manifest.json
D:\throneofdesire_exports\h005\source\
D:\throneofdesire_exports\h005\textures\
```

此前“模型只有一个颜色”的原因不是 UV 丢失，而是贴图使用了游戏自定义的 LZHAM 和 ETC/EAC 格式，Blender 不能直接读取。随后出现的“眼球贴到头发、脸贴到身体”则来自旧脚本错误地采用 NIF 字符串顺序。当前脚本会按 NFS 包归属筛选文件名，再按封包的字典序精确配对物理流，最后按 NIF 材质关系连接节点。

## 首次安装

需要：

- Python 3；
- Blender 3.6，本机验证版本为 3.6.15；
- WSL 及其中可用的 `g++`，用于编译两个小型解码辅助程序。

在仓库根目录执行：

```powershell
python scripts\throneofdesire\build_codecs.py
```

构建脚本下载 LZHAM 和 Ericsson ETCPACK 上游源码，并生成：

```text
.tmp\lzham_v1_decode_raw
.tmp\etc_dds_decode
```

这些程序是 Linux 可执行文件，Windows 侧脚本会自动通过 `wsl.exe` 调用。

## 一键导出模型

把 `--model` 改为模型列表中的编号即可：

```powershell
python scripts\throneofdesire\export_model.py `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --model h005 `
  --blender 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' `
  --output 'D:\throneofdesire_exports' `
  --formats blend fbx `
  --render
```

参数说明：

- `--formats blend fbx`：保存 Blender 文件并导出 FBX；
- `--render`：生成正面预览 PNG；
- `--include-helpers`：把碰撞体或调试辅助网格也导入；
- `--lzham-decoder`、`--etc-decoder`：覆盖默认解码器路径。

一次执行会依次完成 NIF/KFM 提取、贴图解压、ETC/EAC 转换、Blender 材质建立、打包贴图、Blend/FBX 保存和清单生成。

## 手动分步导出

### 1. 扫描并查看模型列表

```powershell
python scripts\throneofdesire\extract_nfs.py scan `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --output '.tmp\throneofdesire\inventory.json'

python scripts\throneofdesire\extract_nfs.py list-models `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --inventory '.tmp\throneofdesire\inventory.json' `
  --output 'docs\throne-of-desire-model-list.md'
```

### 2. 提取 NIF/KFM

```powershell
python scripts\throneofdesire\extract_nfs.py extract-model `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --model h005 `
  --output '.tmp\throneofdesire\h005\source'
```

脚本会按 X-Legend 包哈希定位 KFM 和目标 NIF。若 `packageindex` 漏掉了仍存在于 NFS 的记录，会按资源哈希扫描 16 字节对齐的物理块头，并在格式验证通过后恢复偏移。

### 3. 提取并转换贴图

```powershell
python scripts\throneofdesire\extract_model_textures.py `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --model h005 `
  --nif '.tmp\throneofdesire\h005\source\h005.nif' `
  --decoder '.tmp\lzham_v1_decode_raw' `
  --etc-decoder '.tmp\etc_dds_decode' `
  --output '.tmp\throneofdesire\h005\textures'
```

输出目录会同时保留原始 DDS 和转换后的 TGA。`textures_manifest.json` 记录资源哈希、物理尺寸、解压尺寸和输出文件。

### 4. 用 Blender 3.6 导入并导出 FBX

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' `
  --background `
  --python 'E:\code\othercode\ripper_tpose\scripts\throneofdesire\import_xlegend_nif36.py' `
  -- `
  --input '.tmp\throneofdesire\h005\source\h005.nif' `
  --textures '.tmp\throneofdesire\h005\textures' `
  --output '.tmp\throneofdesire\h005\h005_blender36.blend' `
  --fbx '.tmp\throneofdesire\h005\h005.fbx' `
  --render '.tmp\throneofdesire\h005\h005_preview.png'
```

导入器会把基础部件放到 `<编号>_Base` 集合，把附件放到默认隐藏的 `<编号>_Attachments` 集合。Blend 保存前会打包已使用的贴图，移动 `.blend` 文件后仍能显示材质。

## 当前支持范围与遗留问题

已验证支持：

- 静态几何、三角面、法线和 UV；
- 基础部件与附件分类；
- 正确底色材质；法线、高光和光泽贴图保留在材质节点及自定义属性中；
- 可检查的静止骨架；
- Blender 3.6 `.blend` 和 FBX；
- 可选预览渲染。

仍未完成：

- NIF 蒙皮权重恢复；
- KFM 动画曲线导入；
- X-Legend EAC 法线通道约定的最终验证；当前默认断开法线节点以避免皮肤斑驳；
- XPS 直接导出。

因此当前 FBX 适合查看、静态渲染和后续手工处理，但不是已经绑定并可直接播放原游戏动画的完整角色。XPS 暂未列为已验证格式；需要交换格式时请使用 FBX。

## 版权说明

游戏资源版权归原权利人所有。本仓库只提交提取与转换脚本、哈希和操作说明，不提交 NIF、KFM、贴图或游戏封包。
