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

## 一键导出

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
