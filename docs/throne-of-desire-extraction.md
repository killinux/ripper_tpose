# Throne of Desire 模型提取调研

## 结论

Throne of Desire 不是 Unity，也不是 Unreal。当前 Steam 安装版使用 X-Legend 的
`HyenaPC` PC 包装层，模型和动画资源是 Gamebryo/NetImmerse 系列格式：

- 模型：`.nif`，本机样本版本为 `20.3.3.2`；
- 动画集合：`.kfm`，内部引用基础 NIF 和动画；
- 封包：`mobilepack/packageindex` + `mobilepack/FileListPC.txt` +
  `mobilepack/nfs/<首字符>/<8位包名>`；
- 压缩：模型样本使用带 16 字节 X-Legend 头的 zlib；部分其他资源使用自定义
  `LZMA` 流或尚未识别的纹理/二进制编码。

因此推荐路线是：

```text
packageindex + FileListPC.txt
  -> 本仓库 NFS 解包器
  -> NIF/KFM
  -> X-Legend/Aura Kingdom 专用查看器或兼容的 Noesis NIF 插件
  -> FBX/DAE
  -> Blender 3.6
```

不要用 FModel、UModel 或 AssetStudio；它们分别面向 Unreal/Unity，不识别本游戏的
X-Legend NFS 和 Gamebryo NIF。

## 本机资产统计

扫描目录：

`D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire\mobilepack`

当前安装版验证结果：

| 项目 | 数量 |
|---|---:|
| `FileListPC.txt` 声明记录 | 38,756 |
| 有原始路径的普通文件 | 3,547 |
| 哈希 NFS 行 | 35,209 |
| 当前 `packageindex` 记录/成功映射 | 32,780 |
| 磁盘上的 NFS 包文件 | 2,603 |
| 当前索引实际引用的 NFS 包 | 2,569 |
| zlib 资源 | 15,377 |
| 自定义 LZMA 资源 | 1,877 |
| 未识别压缩/二进制资源 | 15,526 |
| 已识别 NIF | 5,957 |
| 已识别 KFM | 323 |
| 已识别 XML | 295 |

`FileListPC.txt` 比当前索引多 2,429 个哈希行。它们没有可用的当前
`packageindex` 记录，可能是旧版本、可选下载或增量清单残留；脚本会跳过，不会猜测
偏移后强行读取。

## 使用本仓库解包器

脚本位于
[`scripts/throneofdesire/extract_nfs.py`](../scripts/throneofdesire/extract_nfs.py)。
它只读游戏目录，支持当前 `0x20190503` 索引版本，并反解偏移/大小字段的低 32 位
XOR。

### 全量扫描

```powershell
cd E:\code\othercode\ripper_tpose

python scripts\throneofdesire\extract_nfs.py scan `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --output '.tmp\throneofdesire\inventory.json'
```

### 按哈希提取

```powershell
python scripts\throneofdesire\extract_nfs.py extract-hash `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --hash e909a93c518a9e7c `
  --output '.tmp\throneofdesire\h001\h001.nif'
```

### 按编号模型组提取

X-Legend 的模型组常用 `m001`、`h001`、`hm003` 一类编号。脚本会：

1. 用模型名前四个字符计算 NFS 包名；
2. 找到内部确实引用目标 NIF 的 KFM；
3. 选择紧随该 KFM 的基础 NIF；
4. 输出文件和记录哈希、偏移、大小、SHA-256 的 `manifest.json`。

```powershell
python scripts\throneofdesire\extract_nfs.py extract-model `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --model h001 `
  --output '.tmp\throneofdesire\h001'
```

## 已完成的验证

### `m001` 基础样本

- KFM 哈希：`faea5a22c3f46510`；
- NIF 哈希：`2542cd900e981fd1`；
- 解压后：`m001.kfm` 3,657 字节，`m001.nif` 235,058 字节；
- KFM 内部引用 `.\model\m001.nif`；
- NIF 文件头为 `Gamebryo File Format`，版本 `20.3.3.2`。

### `h001` 角色候选组

这只是按资源命名识别的角色候选组，尚未把它认定为某个具体剧情角色。

- KFM 哈希：`df0fbe6d7bb0a5e3`；
- NIF 哈希：`e909a93c518a9e7c`；
- 解压后：`h001.kfm` 62,650 字节，`h001.nif` 906,860 字节；
- 本地路径：
  `E:\code\othercode\ripper_tpose\.tmp\throneofdesire\h001\`；
- 两个文件大小与清单一致，SHA-256 已写入同目录 `manifest.json`。

## 导入 Blender 3.6 的现状

Gamebryo NIF 本身已有 Blender NifTools 和 Noesis 路线，但 X-Legend 的新 NIF 版本及
自定义块并不保证能被通用导入器完整解析。当前机器没有安装 Noesis、NifSkope 或
Blender NifTools，因此这次验证止于正确解出 NIF/KFM，没有伪造一个 `.blend` 结果。

推荐按以下顺序测试：

1. 先用 2026 年发布的 Aura Kingdom 专用 NIF/FSM 查看器检查模型、骨架、权重和 KFM
   动画；它明确面向同一 X-Legend/Gamebryo 资源族，但其 Blender 导出功能目前仍标为
   unfinished。
2. 再用 Noesis 的 NIF 支持尝试转 FBX/DAE；旧版 Aura Kingdom 社区流程已有成功案例，
   但本游戏的 `20.3.3.2` 变体必须逐个验证。
3. 若通用 NIF 转换器拒绝该版本或丢自定义蒙皮块，使用运行时 Ninja Ripper 作为兜底；
   这条路线只能保证屏幕网格，不保证原骨架、权重或动画。

参考：

- [LegendToolX NFS extractor source](https://github.com/davedevils/LegendToolX/tree/main/NFS-EXTRACTOR/NfsExtractor)
- [Blender NifTools 安装说明](https://blender-niftools-addon.readthedocs.io/en/latest/user/install.html)
- [Aura Kingdom 专用 NIF/KFM/FSM 查看器发布说明](https://www.reddit.com/r/AuraKingdom/comments/1u25gnj/nif_models_fsm_mapterrain_viewer/)
- [Aura Kingdom NIF/Noesis 社区提取记录](https://archive.vg-resource.com/archive/index.php/thread-35243.html)

游戏资源版权仍归原权利人所有。本仓库只提交提取脚本、哈希和操作说明，不提交 NIF、
KFM、贴图或游戏封包。
