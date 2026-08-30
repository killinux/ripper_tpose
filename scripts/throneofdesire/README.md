# Throne of Desire 导出工具

本目录用于读取 Steam 版 `ThroneOfDesire` 的 X-Legend `HyenaPC` 封包，并把 Gamebryo NIF 模型导入 Blender 3.6、导出 FBX。工具只读取游戏目录，导出结果写到用户指定目录。

## 首次准备

需要 Python、Blender 3.6，以及可在 WSL 中调用的 `g++`。首次运行先构建 LZHAM 与 ETC/EAC 解码辅助程序：

```powershell
python scripts\throneofdesire\build_codecs.py
```

脚本会从上游源码构建：

- `.tmp\lzham_v1_decode_raw`
- `.tmp\etc_dds_decode`

## 批量导出裸模（export_nude_models.ps1，推荐入口）

与 ROE 的同名脚本约定一致的 PowerShell 入口，包装 `batch_export_female.py`：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\throneofdesire

.\export_nude_models.ps1 -List           # 13 套女性基础体与产物状态
.\export_nude_models.ps1                 # 全部 13 套 -> blend + fbx + 预览
.\export_nude_models.ps1 -Only h005,h020 -Force
.\export_nude_models.ps1 -ValidateOnly   # 用 Blender 重开已导出的 Blend/FBX 复检
```

Throne of Desire 的女性 h 系模型**本体就是裸模**：衣服是附件网格，导入时进入默认
隐藏的 `*_Attachments` 集合，FBX 只导出基础身体和骨架——不需要 mod，也没有额外
剥离步骤。`-Format blend,fbx`、`-NoRender`、`-IncludeHelpers` 透传给 Python 批处理；
路径参数（`-GameRoot`/`-BlenderExe`/`-OutputDir`，默认
`D:\throneofdesire_exports\female_all`）覆盖本机默认值。真实导出前会检查两个贴图
解码器是否已构建（缺失时提示先运行 `build_codecs.py`）。

`--models`/`-Only` 子集重导现在**合并更新** `female_export_manifest.json`，按 13 套
规范顺序保留未重导出的记录，不再把完整清单覆盖成一条；`-ValidateOnly` 的结果写入
独立报告 `female_export_validation.json`，不改动导出 manifest。

## html/ —— 导出总览画廊

和 `scripts\riseoferos\html\`、`scripts\doa5lr\html\`、`scripts\doa6\html\` 同款：
manifest → 缩略图 → 自包含单页。

```powershell
blender --background --factory-startup --python html\collect_manifest.py
python html\make_gallery.py            # 加 --force 重建缩略图
```

`collect_manifest.py` 递归扫导出根下全部 `.blend` 并逐个打开，统计网格/面数/骨架/
材质/贴图（含打包数），按路径分组：`female_all\` 下的归为**批量裸模**，其余归为
**单独导出**；同时并入 `female_export_manifest.json` 里的批量状态。
`make_gallery.py` 读它生成 `html\index.html`（搜索、按组筛选、告警筛选、点图看原图、
一键复制 blend 路径）。

缩略图写在 `D:\throneofdesire_exports\_gallery\thumbs\`，按 `<组>_<模型>.jpg` 命名
（同名模型可能既在批量里又有单独导出，不这样会互相覆盖）；**不进仓库**。

## 一键导出（单模型底层命令）

```powershell
python scripts\throneofdesire\export_model.py `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --model h005 `
  --blender 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' `
  --output 'D:\throneofdesire_exports' `
  --formats blend fbx `
  --render
```

输出目录为 `<output>\<model>`，包含源 NIF/KFM、DDS/TGA 贴图、`.blend`、`.fbx`、可选预览图和 `export_manifest.json`。

## 单步命令

扫描资源：

```powershell
python scripts\throneofdesire\extract_nfs.py scan `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --output '.tmp\throneofdesire\inventory.json'
```

列出 323 个 KFM 模型组：

```powershell
python scripts\throneofdesire\extract_nfs.py list-models `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --inventory '.tmp\throneofdesire\inventory.json' `
  --output 'docs\throne-of-desire-model-list.md'
```

只提取一个模型的 NIF/KFM：

```powershell
python scripts\throneofdesire\extract_nfs.py extract-model `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --model h005 `
  --output '.tmp\throneofdesire\h005\source'
```

Blender 导入器支持 X-Legend 加密字符串表、散列块表、紧凑 AV-object 布局、24 位块大小、XOR-delta 三角形索引，以及自定义材质引用。贴图提取器按 NFS 包归属和文件名字典序匹配物理流，并能够解码游戏的 LZHAM 数据和 `ETC2`、`ETCA`、`EAC4` DDS。

当前可导出静态几何、法线、UV、正确底色材质和可检查的静止骨架。EAC 法线图会保留在材质节点中，但在通道约定完全验证前默认断开，避免产生皮肤斑驳。蒙皮权重与 KFM 动画曲线尚未恢复，因此当前 FBX 是静态网格加未蒙皮的静止骨架。脚本暂不直出 XPS；已验证的交换格式是 FBX。

完整操作说明见 [`docs/throne-of-desire-extraction.md`](../../docs/throne-of-desire-extraction.md)。
