# hq_materials：PMX 的 MMD 材质（第一步）和 ray-mmd 高清材质（第二步）

做法、原理和踩过的坑见 [docs/pmx-hq-materials.md](../../../docs/pmx-hq-materials.md)，这里只写怎么用。

| 文件 | 做什么 |
|---|---|
| `make_hq_materials.py` | 入口：给 PMX 写第一步的 `<名字>_材质.pmx`，和第二步的 ray-mmd 版 |
| `extract_pbr_blender.py` | 在 Blender 里读 PMX 的源 .blend，找出每个材质的法线 / 粗糙度 / 金属度 / 高光 / 自发光（入口自动调用） |
| `mmd_drive.py` | 用脚本驱动 MMD 本体：载入模型、ray-mmd、.emm，出图，存 .pmm，记录 MMD / MME 弹出的每个对话框 |
| `batch_all.py` | 整个归档（`E:\game_export`）的 PMX 一次做完：后台、一次一个、能接着跑，不开 MMD |

## 整批（batch_all.py）

```powershell
python scripts\pmx_tools\hq_materials\batch_all.py [--games EldenRing,Sekiro] [--skip-games RiseOfEros] [--dry-run] [--limit N]
```

- 处理归档里所有 PMX，跳过：任何一层以 `_` 开头的文件夹（主题合集的硬链接、`_meta` 备份、`_混搭` 试验、
  别的窗口管的 `_18系列_ウィンク修正`、输出目录 `_raymmd` 本身）、我们自己的输出（`*_材质.pmx`、`*_raymmd.pmx`）。
- 一次一个模型，正常优先级（低优先级时会被别的窗口的渲染饿住，像卡死）；模型少的游戏先做。
- 记账 `E:\game_export\_raymmd\_batch\ledger.jsonl`：每做完一个记一行（带 `make_hq_materials.VERSION`）。
  中途停了再跑一遍就接着做；改了输出就把 `VERSION` 改掉，旧版本做的会重做。出错的下次重试。
- 日志在同一个文件夹的 `run_<日期_时间>.log`。
- 同一个源 .blend 的几个变体（ROE 的 `_bustB`、`_裙子碰撞修正` 等）只读一次 .blend：结果缓存在
  `E:\game_export\_raymmd\_cache\`。

## 用法

```powershell
python scripts\pmx_tools\hq_materials\make_hq_materials.py <PMX 文件或文件夹> ...
       [--steps 1,2] [--blend <源 .blend>] [--values 覆盖值.json] [--force] [--dry-run] [--report 报告.json]
       [--raymmd-root <英文路径的文件夹>]
```

- 只读原文件，结果都是新文件：
  - 第一步，写在 PMX 旁边：`<名字>_材质.pmx`（普通 MMD 直接看）和 `mmd_materials\`（生成的 toon / sphere 图，
    同一文件夹的模型共用）。
  - 第二步，写在 `E:\game_export\_raymmd\<游戏>\<角色>_<模型>_<哈希>\`（只能是英文路径，原因见文档）：
    `model.pmx`（原文件的硬链接）、`textures\`（贴图硬链接）、`fx\`（每个材质一个 ray-mmd 的 `.fx`）、
    `scene.emm`（MME 的材质分配）、`README.txt`。不在 `E:\game_export` 里的 PMX 用 `--raymmd-root` 指定位置。
- 源 .blend 自动找：PMX 旁边的 `<名字>_converted.blend`（我们的 PMX 导出脚本都会留），或者归档里同角色的
  `blend\<造型>\*.blend`（Rise of Eros）。都没有时第二步按材质类别给预设值（没有游戏贴图）。
- `--dry-run`：只分类、打印，不写文件（不跑 Blender，只按名字分）。
- `--values`：按类别覆盖默认值，例如 `{"skin": {"specular": 0.1, "edge": 0}, "metal": {"sphere": ["metal", "add"]}}`。
  类别和默认值见 `make_hq_materials.py` 里的 `DEFAULT_VALUES`（第一步）和 `RAY_PRESETS`（第二步没有游戏数据时）。
- `--force`：自带 toon / sphere 的材质（对魔忍 Squad 的游戏 toon）也重做；默认保留。
- 需要：Blender 3.6（`--blender`，默认 `D:\Program Files\blender-3.6.15-windows-x64\blender.exe`）、
  ray-mmd 1.5.2（`--ray-mmd`，默认 `E:\tools\MikuMikuDanceE_v932x64\ray-mmd-1.5.2`）、Pillow、numpy。

## 在 MMD 里看

- 第一步：直接载入 `<名字>_材质.pmx`。
- 第二步（MMD 要装好 MME 和 ray-mmd，这台电脑 11-14 装在 `E:\tools\MikuMikuDanceE_v932x64`）：
  - 有 `scene.pmm` 的：「文件 → 打开」选它，全部设好；
  - 或者自己来：载入 `ray-mmd-1.5.2\ray.x`（配件）→ 天空盒 `ray-mmd-1.5.2\Skybox\Helipad GoldenHour\Sky with box.pmx`
    → `model.pmx`，然后菜单 MMEffect → Effect Mapping，窗口里 File → Open 选 `scene.emm`，按 OK。

## 用脚本驱动 MMD（mmd_drive.py）

```powershell
# 对比图：原 PMX、_材质.pmx（普通 MMD，灰背景），再 ray.x + 天空盒 + model.pmx + scene.emm
python scripts\pmx_tools\hq_materials\mmd_drive.py compare <原.pmx> <输出前缀> --step1 <_材质.pmx> --raymmd-dir <ray-mmd 文件夹>
# 让 MMD 存 scene.pmm（一键打开的场景）
python scripts\pmx_tools\hq_materials\mmd_drive.py scene <ray-mmd 文件夹> ...
```

MMD 的窗口会在桌面上弹出（全靠窗口消息，不动鼠标键盘，但别在这时候点它）；MMD / MME 弹出的对话框都记在结果里
（`problems` = 模型信息框和删除确认以外的，比如 MME 的编译错误）。`compare` 会读回 MME 的 MaterialMap 分页，
`info.subsets_assigned` / `info.subsets` = 有几个材质真的用上了我们的 .fx。
