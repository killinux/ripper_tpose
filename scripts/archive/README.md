# 导出归档：把 D 盘的导出搬到 `E:\game_export`

D 盘快满了（2026-09-26 只剩 91 GB），各游戏的导出一共约 470 GB（其中 153 GB 是 FF7 的 pak 硬链接，
不占额外空间）。这里的脚本把**已经做好的模型**按 `<游戏>\<角色>\<格式>\<造型>\` 复制到
`E:\game_export`，逐个校验、逐个在 Blender 里打开自检，然后列出 D 盘哪些目录已经可以整个删掉。
**删除由人手动做**，脚本只拷不删。

以后某个游戏又导出了新角色（新文件照旧先落在 D 盘各自的导出目录），再跑一次同样的命令：只会拷新的和
改过的文件，目录清单、可删除清单、画廊链接一起更新。

## 用法

```powershell
cd scripts\archive
python archive_exports.py --list                  # 已登记的游戏、D 盘来源、归档过没有
python archive_exports.py doa6 --dry-run          # 只看计划：哪些造型、归到哪个角色、拷 / 打包 / 移动多少
python archive_exports.py doa6                    # 拷贝 + 校验 + 自检 + 改画廊链接 + 刷新两份清单
python archive_exports.py all                     # 全部已登记的游戏
python archive_exports.py doa6 --only Ayane       # 只处理一个角色（或一个造型 id）
python archive_exports.py naraka --recheck        # E 盘上登记过的造型全部重新自检（包括 D 盘已经删掉的）
python archive_exports.py --report                # 不拷贝，只按 D 盘现状重算两份清单
python archive_exports.py --relink                # 只改画廊页里的 D 盘链接（画廊重新生成过以后用）
python tests\test_archive.py                      # 离线测试，最后一行 ARCHIVE_TEST=PASS
```

其它选项：`--dest`（默认 `E:\game_export`）、`--blender`（默认 3.6.15）、`--no-check`、`--workers`（拷贝线程，默认 4）、
`--lanes`（并行 Blender 进程，默认 6）。

## 归档后的结构

```
E:\game_export\
  README.md                  总目录：每个游戏有哪些角色、多少造型、哪些格式（自动生成）
  catalog.json               同样内容的 JSON
  D盘可删除清单.md            每次运行现算
  <游戏>\
    README.md                每个角色一张表：造型、说明、各格式的主文件链接、大小、预览；自检问题 / 源文件本来就缺的东西
    <角色>\<格式>\<造型>\     一个能单独打开的完整目录
    _meta\
      ledger.json            账本：每个 D 盘源文件的大小 / 修改时间 / md5 / 在 E 盘的位置
      models.json            每个造型的说明、主文件、预览、来源、自检结果（D 盘删了也还在）
      dirmap.json / moves.json   源目录 -> 归档位置（改画廊链接用）
      原来的清单、缩略图、日志、mod 原文件、对照图……
```

- **角色**：同一个角色的所有造型（服装、裸体基础、mod、变体）放在一起。怪物按种族、物品归到 `Items` / `武器` 这类组。
- **格式**：`blend` / `xps` / `pmx` / `fbx` / `glb` / `vam` / `duf` ……，每种格式各自一套完整目录，
  所以同一套贴图在 blend 和 xps 里各存一份——这是“每个目录都能单独拷走”的代价。
- **造型**：沿用导出时的 id（`PCF_003`、`pc_j01_prouniform`），说明文字在游戏的 `README.md` 里。

## 各游戏怎么归（`games.py`）

| 游戏 | E 盘目录 | 角色从哪来 | 特殊处理 |
|---|---|---|---|
| Vindictus | `Vindictus` | 清单 `body`（PCF → Fiona，PCM → Lethita），怪物按种族 | VaM 版 Fiona（`bring_to_vam.py`）放 `Fiona\vam\FionaDF` |
| The First Descendant | `TheFirstDescendant` | 清单 `char` | AES key 拷到 `E:\tools\firstdescendant\_keys`（不进归档目录） |
| Throne of Desire | `ThroneOfDesire` | h-编号 | 每个模型拆成 `blend`（贴图已打包）和 `fbx`（+ `textures\`） |
| DOA6 / DOA5LR | `DOA6` / `DOA5LR` | 清单 `char` 代码 → 本体名（mod 归到本体角色下） | `D:\doa_mods`、`D:\doa_mod_fbx` 的 mod 原文件进 `DOA6\_meta\mod_sources` |
| FF7 Remake | `FF7Remake` | 清单 `char` | `.blend` 贴图外链到 `player\GameContents` → **打包** |
| FF7 Rebirth | `FF7Rebirth` | 清单 `char`；Reika mod 单独一个角色 | pmx 目录里的 `_converted.blend` 用绝对路径 → 打包；`D:\ff7_mods` 的 mod 原文件和零散文件进 `_meta` |
| Stellar Blade | `StellarBlade` | Eve；Vindictus Fiona / Gantz Reika mod 各自一个角色 | 用 `packages\`（独立包），`blender\` 那份贴图外链、算重复；画廊里 `blender\*.blend` 指到包 |
| VaM | `VaM` | VaM 包名（作者.包.版本 的中间段） | 只拷 `blend\`，贴图缓存 `_textures\` 和 `.blend1` 不要；Fiona 18 的 `.duf` 放 `Fiona18\duf` |
| NARAKA | `NARAKA` | 服装家族 → 英雄中文名（`naraka_catalog.FAMILY_HERO`） | E 盘原来的 `outfits\<id>` **直接移动**；D 盘样本和 E 盘批量重复的不拷 |
| HoneySelect 2 | `HoneySelect2` | 角色卡里的名字（`scene.json` 的 `character`） | `parts\`（npz 中间数据）不拷 |
| Venus Vacation PRISM | `VenusVacationPRISM` | 目录名 | 每个角色的 `complete\` 交付包整个拿走（里面 .blend + .fbx + .glb） |
| Rise of Eros | `RiseOfEros` | 代号字母 → 名字（`character-roster.md`） | pmx 下的跳舞 / 布料 / 表情场景和视频放进对应造型的 `_scenes\` 并打包；官方裸体基础模型在 `nude_materials` |
| Hotel VIP | `HotelVIP` | —（2D 游戏，没有 3D 模型） | 2D 美术按类别放 `2D\png\<类别>` |
| 零散目录 | `_misc` | — | `D:\export` 的视频进 `_misc\_meta`；`D:\test`、`D:\tmp`、`D:\_claude_wip` 算可删 |

## 怎么保证“单独能打开”

复制只是第一步，拷完以后在 **E 盘这份** 上逐个自检：

| 格式 | 自检 |
|---|---|
| `.blend` | Blender 无头打开（`blend_selfcheck.py`），`bpy.utils.blend_paths(absolute=True, packed=False)` 列出全部外部文件（贴图、声音、链接库、缓存……），每个都必须存在而且在这个造型目录里面 |
| `.xps` / `.mesh` | 从二进制里找贴图名（7-bit 长度前缀的字符串），逐个在目录里找 |
| `.pmx` | 解析 PMX 头、跳过顶点和面，读贴图表，逐个找 |
| VaM | 预设 / 物品 JSON 里的 `Custom/...`（含 `SELF:/`）引用逐个找 |

缺的文件会换算回 D 盘再看一次（按账本找到引用它的文件在 D 盘的位置）：D 盘上也没有 = **源文件本来就缺**
（例如 ROE 早先清理掉的 `pc_<id>_hd (1)\` 法线贴图），只记为提醒；D 盘上有 = 归档漏拷了，记为问题。
没过的造型在游戏 `README.md` 里标 ⚠。

**打包（`package=True`）**：`.blend` 引用了造型目录外的文件时，不按字节拷，而是 `blend_package.py` 在
Blender 里打开源文件，把外部贴图 / 声音拷进造型目录（目录内的按原相对位置，目录外的进 `textures\`，重名且
内容不同就加 `_2`），改成绝对路径 `save_as` 到 E 盘，`make_paths_relative` 再存一次，重新打开核对。
`save_version = 0`，不留 `.blend1`。声音轨（VSE 里的 BGM）按新路径重建，见下面的坑。

**自动补救**：规则里没标 `package` 的 `.blend` 按字节拷过来以后，如果自检发现它还引用着造型目录外的文件，或者缺的
文件在 D 盘上其实有（例如 ROE 的 `pc_f10_hd.blend` 引用了原始解包目录 `pc_f10_hd (1)\` 里的法线贴图），就自动改用打包
重做这一个文件，再查一次。

## 校验和账本

- 每个文件边拷边算 md5，写进 `.part` 再改名，然后从 E 盘读回来再算一次，对不上就报错停下。
- 拷贝前后各取一次源文件的大小 / 修改时间，变了（别的窗口正在写）就不记账，报出来，下次再拷。
- 账本 `_meta\ledger.json` 记下源文件的大小、修改时间、md5 和去向。重跑时大小 / 修改时间都没变、E 盘副本还在的
  文件直接跳过；D 盘上重新导出过的文件（修改时间变了）会重新拷。E 盘上用户改过的文件不会被旧的 D 盘版本覆盖
  （只要 D 盘那份没变）。E 盘多出来的旧文件不会自动删，只增不减。
- 源在 E 盘的（NARAKA 的 `outfits\`）直接改名移动，记在 `_meta\moves.json`。

## D 盘可删除清单怎么算

每次运行都重新走一遍登记过的 D 盘来源目录，逐个文件判断：

1. 在（任何一个游戏的）账本里、大小和修改时间没变、E 盘副本还在 → 已归档；
2. 属于登记过的中间产物（`games.py` 的 `regenerable`，可以带通配符：原始解包、探测输出、`.blend1` 备份、
   已被更新版本取代的早期演示）→ 可以用仓库脚本重新生成；
3. 其它 → 还没归档。

一个目录里全是 1 或 2 才算“可以整个删除”，清单里只列最上层的那一级；不能整个删的目录会列出其中可以整个删的
子目录和还没归档的文件。另外：

- **能腾出**：16 MB 以上、硬链接数 > 1 的文件（和游戏安装目录共用数据，比如 `D:\ff7_mods\_stage` 里 153 GB 的
  pak）删了不腾空间，不计入。
- **最近还有写入**：目录里两小时内有文件被改过，清单上加粗提醒“可能有别的窗口在用”。
- 最后一节是还没登记的导出目录和大小。

中间产物删掉以后，想重新构建某个模型要先重新解包（需要游戏客户端，有的还要 AES key）。只是打开、使用已经
归档的模型不需要它们。

要我来删的时候用 `delete_archived.py`（2026-09-26 用它删了除 `D:\roe_exports` 外的 23 个目录，D 盘 97.7 → 311.9 GB）：

```powershell
python delete_archived.py                                   # 只列：能不能删、多大、能腾出、最近写入
python delete_archived.py --delete D:\hs2_exports           # 删指定的
python delete_archived.py --delete-all --keep D:\roe_exports
```

每个目录删之前的一刻再核对一遍（每个文件都已归档且没改过、或是登记过的中间产物），有 junction / 符号链接的不删
（递归删除不能顺着链接删到别处），最近 30 分钟（`--min-age`）内有写入的不删。

## 画廊链接

各游戏的画廊页（`scripts\<游戏>\html\index.html`）里的图片和链接是 `file:///D:/...` 绝对路径。归档后
`--relink`（归档时自动做）按账本 / `dirmap.json` / `moves.json` 把能对上的改成 E 盘位置：URL 形式、反斜杠形式、
小写的搜索文本都改，`<pre>` / `<code>` 里的命令示例不动，换行符保持原样。画廊用各自的 `make_gallery.py` 重新
生成后又会指回 D 盘，再跑一次 `python archive_exports.py --relink` 即可。

归档过来的列表页（NARAKA / HS2 的 `_list\index.html`，用相对链接）按页面原来的位置解析每个相对链接，改成从新位置
出发的相对路径。

## 加一个游戏

在 `games.py` 里写一个 `Game(...)` 并加进 `GAMES`：

- `sources`：要报告能不能删的 D 盘目录；
- `regenerable`：其中可以重新生成的中间产物（列表或返回列表的函数），每项带一句为什么，路径可以带 `*`；
- `collect()`：返回 `(products, metas)`。`Product(角色, 格式, 造型, 源目录, main=主文件, preview=预览图, desc=说明)`
  默认拷整个源目录；`include=[(源相对路径, 目标相对路径)]` 只挑几项并改名（可以用 `..\` 取上一级的文件）；
  `exclude` 按通配符排除；`package=True` 打包外链贴图；`move=True` 同盘移动。`Meta(源, 名字, dest=别处)` 放进 `_meta\`；
- `galleries`：要改链接的画廊页；`list_pages`：归档过来的相对链接列表页；`aliases(game_dir)`：额外的 旧路径 → 新路径；
- `character_names`：角色的中文说明；`notes`：写进可删除清单的备注。

先 `--dry-run` 看分组对不对，再正式跑。

## 踩过的坑

- **`bpy.utils.blend_paths(packed=...)` 的文档是反的**：Blender 3.6 实测 `packed=False` 才跳过已打包的数据
  （一个 30 张贴图全打包的 .blend：`packed=False` 返回 0 条，`packed=True` 返回 30 条）。第一版用反了，把打包贴图的
  原路径当成外部文件，报了一堆假缺失。
- **声音轨自己还记着一份路径**：VSE 的声音轨除了引用 `Sound` 数据块，内部还存着添加时的目录 + 文件名；
  `blend_paths()` 报的是它，播放用的是数据块。只改数据块的 `filepath`，自检仍会报“引用了目录外的文件”
  （ROE 跳舞场景的 `E:\Downloads\mmd\...\BGM.wav`）。Python 改不到那份路径，只能按新路径 `sequences.new_sound()`
  重建声音轨（名字、通道、起止帧、音量照搬）。
- **目录名里的 `[` `]`**：VaM 的 `BooMoon.[Looks]_Miya` 被 `glob` 当成字符集，两个外观漏掉；`glob.escape` 目录部分。
- **Blender 存两次会留 `.blend1`**：打包时先 `save_as` 再 `make_paths_relative` 后 `save`，要先把
  `preferences.filepaths.save_version` 设成 0。
- **硬链接**：`D:\ff7_mods\_stage` 是 FF7 Rebirth 游戏 pak 的硬链接（`fsutil hardlink list` 可查），目录大小 153 GB，
  删了一个字节都不腾。
- **别在导出还在跑的时候归档那个游戏**：拷贝前后比对大小 / 修改时间能挡住正在写的文件，但它会一直显示“还没归档”，
  等那边做完再跑一次。
- `E:\game_export\NARAKA\outfits\` 被移走以后，NARAKA 的 `batch_export.py`（按 `outfits\<id>` 是否存在跳过）再跑会重导
  全部；新导出的仍落在 `outfits\`，再跑一次归档就会移到英雄目录下。
