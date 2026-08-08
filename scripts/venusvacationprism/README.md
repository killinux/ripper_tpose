# Venus Vacation PRISM 原始资源解包

这组脚本直接读取游戏的 `fdata_package/*.fdata`，不注入游戏进程，也不修改安装目录。它能枚举原生 G1M 模型，并把选中的条目从 PRISM 的分块 Zlib 数据中还原出来。

## 当前验证结果

在 2026-08-08 的本机 Steam 安装中：

- G1M 条目：1,527
- 唯一 G1M ID：1,527
- 含 G1M 的 FDATA 包：69
- 解压后 G1M 总量：约 2.09 GiB
- 含至少 50 个骨骼节点的角色候选：71

“角色候选”是按骨骼数量得到的技术筛选结果，不等于 71 个不同角色。游戏会把身体、脸、服装、头发等拆成独立模型，也存在共用组件。

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

## 2. 导出一个原生模型

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

输出 `.g1m` 原始模型和 `.json` 来源/结构清单。脚本索引是一基索引，和 `models.csv` 的 `index` 列一致。

## 3. 可选转换为 glTF

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

模型名数据库所引用的外部 RDX 包没有随当前安装提供，因此清单使用稳定的 KTID（例如 `0x7ce546e8`），无法可靠恢复开发期文件名。
