# 一批 Nexus mod 换到 Eve 身上：批处理脚本（2026-11-15）

用户下载的 12 个剑星 mod（`E:\Downloads\eve_mod_download`，只读）→ 48 套造型（每种网格一份）的 Blender、高清 Blender、PMX、XPS，
外加画廊。做法和踩过的坑见 [`../README.md`](../README.md)「一批 Nexus mod」一节；这里是脚本怎么用。

**画廊**：[`index.html`](index.html)（本文件夹，链接都是 `file:///E:/game_export/...`，和 `../html/index.html` 一样；缩略图在存档的
`_mod画廊\thumbs\`）。存档里另有一份 `E:\game_export\StellarBlade\_mod画廊\index.html`（相对链接，跟着存档走）。两份都由
`finish.py gallery ALL_READY` 生成，每导完一批重跑一次。

| 脚本 | 做什么 |
|---|---|
| `looks.py` | 清单（11-15 那批 48 套，11-22 加上 Vindictus 那批 6 套）：每套的 mod、要放进 staging 的 `.pak/.utoc/.ucas` 文件夹、网格的虚拟路径、换进哪个已归档的原版成品、显示名。缺依赖的套标 `needs`；依赖下好、用 `add_dep.py` 解进 `unzipped\_dep_*\` 后自动并进来 |
| `stage.py` | 把下载的压缩包拷到 `D:\stellarblade_exports\mods\<mod>\` 解开，列出每个 `.utoc` 里的包路径（清单里也可以写完整路径：2026-11-22 那批 Vindictus mod 在 `E:\Downloads` 别处） |
| `export_variants.py` | 合集包的每个变体分别用 UE Viewer 导出，按 PSK 顶点的 md5 分组（Crimson Wings BBB：40 个变体 16 种网格） |
| `run_look.py` | 一套的各步：stage → umodel → cue（CUE4Parse 带游戏 Paks 读网格，各槽的材质实例、父链、贴图）→ swap（`../swap_mod_mesh.py`）→ fill（`fill_materials.py`）→ texfix → cloth（`hang_cloth.py`）→ hair（`attach_hair.py` + 补材质）→ xps → pmx → preview；每步结果记在 `<mod>\looks\<label>\status.json` |
| `attach_hair.py` | 清单里写了 `hair`（mod 的发型）或 `acc`（饰品）的套：挂在游戏的 `SC_Hair` 挂点上（就在 `Bip001-Head`），发型换掉 Eve 原来的头发和它的骨骼，饰品整个绑在头骨上 |
| `hang_cloth.py` | 游戏里用布料模拟的网格段（PSK 里是绑定姿势）：长条按挂接点转成自然下垂 |
| `fill_materials.py` | Blender 里补材质：空槽拿最近一层父材质的游戏材质（本文件或任何归档 .blend，索引 `_meta\material_index.json`），再换上实例自己设的贴图；抄来的底色图不是实例自己的（母材质的默认图），或者都没有，就用实例的游戏贴图 + 颜色 / 粗糙度 / 不透明度现做；头发（母材质 `MA_CH_Hair`）按发根 → 发梢颜色和 Alpha 贴图做；CNS 默认贴图选项和默认颜色；默认隐藏的部件去掉；重渲预览 |
| `batch.py` | 多套并行跑 `run_look.py`（同一 staging 的 umodel 只跑一次） |
| `finish.py` | 收尾：archive（`../../archive/archive_exports.py`）、sources（mod 原件拷到 `_meta\mod_sources\<mod>\`）、registry（`_meta\hq_materials\mod_outfits.json`）、hq（`../hq_mod_outfits.py`）、addon（`test_addon.py` + `make_sheet.py` → `插件效果_游戏材质对比.jpg`）、readme、gallery（`../mod_gallery.py`） |
| `material_index.py` | 扫所有归档 .blend 的材质名 → `_meta\material_index.json` |
| `retex.py` | 实例在「抄来的祖先材质」之上自己设的贴图（fill 步用它把这些图换进副本）；`python retex.py ALL` 只读扫一遍已导的套，看哪些槽受影响 |
| `add_dep.py` / `wait_deps.py` | 依赖文件：解包 / 在下载目录按 mod 号 + 精确字节数等它出现（只读） |
| `progress.py` | 跑批时每套到了哪一步、有没有报错 |
| `inventory.py` / `cns_meshes.py` | 只读清点：压缩包里有哪些三件套；CNS 的 `.dekcns.json` 里每个变体用哪个网格 |

```powershell
python -I -X utf8 batch.py --jobs 4 ALL_READY                    # 不缺依赖的全部，从头到预览
python -I -X utf8 finish.py archive ALL_READY                    # 然后依次 sources / registry / hq / addon / readme
python -I -X utf8 finish.py gallery ALL_READY                    # E:\game_export\StellarBlade\_mod画廊\index.html
python -I -X utf8 add_dep.py CakeUnveiledCS "E:\Downloads\eve_mod_download\All in One for CNS-1183-0-1-1-1770964697.zip" _dep_1183
```

`-I`：读的是下载来的文件，不让 Python 从当前目录加载模块；`-X utf8` 让中文输出不出错（`-I` 会忽略 `PYTHONIOENCODING`）。
