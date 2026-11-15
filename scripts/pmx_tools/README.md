# PMX 小工具

除了 `texture_alpha_blender.py`（给导出脚本在 Blender 里调用），这里的脚本都直接读写 PMX 文件：用的是 mmd_tools 自带的 PMX 读写模块（自动从
`%APPDATA%\Blender Foundation\Blender\<版本>\scripts\addons\mmd_tools\core\pmx\__init__.py` 加载），
用系统 Python 跑，不需要打开 Blender。**原文件只读，结果都写成新文件。**

保存时沿用原文件的附加 UV 数（`add_uv_count=model.header.additional_uvs`），贴图路径照原样相对于 PMX 所在文件夹。

例外是 `pmx_textures.py`。它只改文件里的贴图表，就地改（先备份），不经过 mmd_tools，其余字节原样保留，见下一节。

## pmx_textures.py：只改贴图表（绝对路径改相对、给没贴图的材质接上贴图）

```
python pmx_textures.py list <文件.pmx>
python pmx_textures.py relative <文件.pmx | 文件夹 | @清单.txt> ... [--backup 文件夹] [--dry-run]
python pmx_textures.py set <文件.pmx> <材质名> <贴图（相对 PMX）> [--backup 文件夹] [--dry-run]
```

- `relative`：把写成绝对路径的贴图（`E:\game_export\...\textures\x.png`）改成相对 PMX 所在文件夹（`textures\x.png`）。
  这样整个文件夹拷到哪里都能用。文件夹会递归找 PMX；`@清单.txt` 是一行一个 PMX。
  - 在别的盘上、或者文件不存在的路径不改，只列出来。
  - 起因：ROE 的 310 个「裙子碰撞修正」PMX 都是绝对路径。`mmd_physics/cloth_batch_fix.py` 在工作文件夹里导出，
    再拷到原文件旁边，工作文件夹和归档不在一个盘，mmd_tools 算不出相对路径，就写了绝对路径。
  - 2026-11-15 已全部改好，原文件在 `E:\game_export\RiseOfEros\_meta\backup_替换前_20261115`。
    `cloth_batch_fix.py` 拷完也会调这个工具，以后新写的不会再是绝对路径。
- `set`：给一个材质换颜色贴图，贴图表里没有就加一条。
  - 用于导出时漏了贴图的材质。2026-11-15 修了两处，用的都是它们全套版文件夹里同一材质的贴图：
    - ROE e10 的透明小部件（172 面）；
    - j06 的武器。
- 每次写之前都检查：新文件重新解析一遍，贴图表以外（`set` 再除去改的那个贴图编号）必须和原文件逐字节相同。
  - 先写 `.part`，再替换原文件；
  - `--backup` 把原文件按去掉盘符的路径拷进备份文件夹，已有的备份不覆盖。

## fix_wink_sides.py：ウィンク 左右对调

MMD 的惯例：`ウィンク`（和 `ウィンク２`）闭的是**模型自己的左眼**（左腕那一侧，PMX 里 +X），`ウィンク右` 闭右眼。
日本模型、Expression Kit、我们自己的 ROE / FF7 / 剑星 / Vindictus / AION2 导出都是这样。
下载的欧美 "18" 系列（Daz / XPS 转来的 Fiona 18、Reika 18、Tifa 18 等）正好反过来，跳舞时一眨眼就闭错眼。

做法：每个 PMX 里，看 ウィンク 和 ウィンク右 各自动的是哪一边（顶点表情看顶点位移，骨骼表情看骨骼移动，
组合表情展开成员，按移动量加权求 X 的平均）。如果 ウィンク 动的是右眼、ウィンク右 动的是左眼，就把这两个表情的
日文名和英文名对调；`ウィンク２` / `ｳｨﾝｸ２右`（也有写成 `ウィンク２右` 的）同样处理。
本来就对的、缺一个的、两只眼都动的，不改。

```
python fix_wink_sides.py <文件或文件夹> ... --out <输出文件夹> [--base <文件夹>] [--suffix _winkfix]
                         [--contains 文字] [--dry-run] [--skip-existing] [--report out.json]
```

- 输出按 `--base` 下的相对路径放到 `--out` 里，文件名加 `_winkfix`；改完会重新检查一次。
- `--skip-existing`：已经有修好的副本就跳过（批量中断后接着跑）。副本先写成同一文件夹里的 `*.tmp`，读回检查过才改名，
  所以中途被停下不会留下半个文件（10-31 第一次批量被强制停下时留过一个截断的文件，接着跑时被当成已完成，后来重做了）。
  `fill_standard_morphs.py` 同样先写临时文件。
- 副本不带贴图：保存时贴图路径写成从副本指回原文件夹的相对路径（同一个盘），所以原文件夹不能挪走或改名；
  要单独拷走就把原文件夹的贴图一起拷过去，放在相同的相对位置。

## fill_standard_morphs.py：补齐缺的 MMD 标准表情

用模型已有的顶点表情按配方混合出缺的标准表情，写成原文件旁边的 `<名字>_表情补全.pmx`。
起因是 Taimanin Squad 的 PMX 只有 30 个常用名里的 14 个（游戏是动画风格的脸，眼睛画在贴图上，
没有眼球网格，所以 PMX Expression Transfer 插件读不了）。

| 补的表情 | 配方 |
|---|---|
| じと目 | まばたき × 0.45 |
| びっくり | まばたき × −0.3（眼睑张得更开） |
| なごみ | 笑い × 0.75（没有笑い 时 まばたき × 0.7） |
| はぅ | 笑い 0.5 + まばたき 0.5 + 怒り 0.3 |
| 真面目 / 下 / 上 | 怒り × 0.5 / × 0.7 / × −0.6（眉毛往上、往外） |
| にこり | smile_face 只取眉毛区域；那样什么都不动时用 怒り × −0.3 |
| ∧ / 口角上げ / 口横広げ | 口角下げ / にっこり × 0.5 / い × 0.6 |
| にやり / ワ / ん | にっこり + い × 0.3 / あ + い × 0.5 / い × 0.25 + う × 0.15 |

- 区域（眉 / 眼 / 嘴）按 まばたき 动到的顶点高度来分。两个闭眼形状按加起来等于 1 的比例混，眼睑不会穿过去。
- 某个配方的原料缺了就试下一个备选，都缺就跳过；已有的名字从不覆盖。新表情放进「表情」显示框。

```
python fill_standard_morphs.py <文件或文件夹> ... [--suffix _表情补全] [--contains 文字] [--only じと目,ワ]
                               [--dry-run] [--report out.json]
```

## texture_alpha_blender.py：PMX 贴图透明度（在 Blender 里被导出脚本调用）

MMD 会把贴图的透明度乘进材质。导出脚本在写 PMX 之前用 `source_alpha_modes()` 记下源材质的混合方式，
写完后用 `fix_texture_alpha(pmx, clip, opaque)` 处理 PMX 文件夹里的贴图：

- 只被**不透明**材质用的贴图：透明度全部设成 1（游戏贴图常把高光 / 次表面遮罩放在透明通道里，PMX 会半透明）；
- 只被**裁切**材质用的贴图（游戏里的头发卡片等）：按游戏的裁切值重新映射，低于「裁切值 − 0.05」为 0，
  高于「裁切值 + 0.05」为 1，中间线性过渡；剑星 Raven 的长发原来透明度中位数只有 0.25，MMD 里又稀又透；
- 被混合材质用到的贴图不动。只改 PMX 自己文件夹里的文件。
- 补 1 会把「烘焙时根本没写到」的空白处也变成不透明（画出来是黑块，空的烘焙就被掩盖了），所以补之前先按三角形中心
  采样每个不透明材质：透明度低于 0.5 的三角形超过 2% 时，报告里写 `HOLES <材质> N%`，提醒检查烘焙。

用到它的：`scripts/stellarblade/npc/export_npc_pmx.py`、`scripts/honeyselect2/export_pmx_blender.py`。

## hq_materials/：MMD 材质和 ray-mmd 高清材质

给 PMX 配 MMD 自己的材质（toon / sphere / 高光 / 描边，写 `<名字>_材质.pmx`），并用源 .blend 里的游戏贴图做 ray-mmd 材质包
（`E:\game_export\_raymmd\<游戏>\<模型>\`，带 `scene.emm` / `scene.pmm`）；还有用脚本驱动 MMD 本体出图的 `mmd_drive.py`。
用法见 [hq_materials/README.md](hq_materials/README.md)，做法见 [docs/pmx-hq-materials.md](../../docs/pmx-hq-materials.md)。

## sdef_compare_video.py + compose_sdef_video.py：SDEF 前后对比视频

`pmx_sdef_rings.py`（PMX 待做清单第 6 项）把手肘、膝盖一圈的顶点改成 SDEF，写一份旁边的 `*_SDEF.pmx`。
这两个脚本让人**亲眼看**改前改后的差别：同一个动作，原版和 SDEF 版并排；每帧再量一次关节塌了多少。

```powershell
$B = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
# 1) 渲染（Blender 3.6 后台，要 mmd_tools）：舞蹈，或者 --bend 弯曲测试（右手肘 0→140°、左膝 0→130°）
& $B -b --python scripts\pmx_tools\sdef_compare_video.py -- <原版.pmx> <SDEF.pmx> <工作目录> --vmd <动作.vmd>
& $B -b --python scripts\pmx_tools\sdef_compare_video.py -- <原版.pmx> <SDEF.pmx> <工作目录2> --bend
# 2) 拼视频（系统 Python + Pillow + ffmpeg）：上排原版、下排 SDEF；三栏是全身、右手肘、左膝
python -I scripts\pmx_tools\compose_sdef_video.py <工作目录> <输出.mp4> --bgm <音乐.wav>
python -I scripts\pmx_tools\compose_sdef_video.py <工作目录> <对比图.jpg> --sheet     # 只出塌得最厉害的两帧
```

- **特写镜头**每帧都正对关节的弯曲平面（上臂 × 前臂的法线），正交相机，只渲关节前后 ±11 cm 的一片，躯干、另一条腿不挡。
  关节伸直（弯曲小于 15°）时没有弯曲平面，镜头保持上一帧的方向；平时做平滑，不会乱转。
- **数字**：`距离比` = 关节一圈的 SDEF 顶点到关节中心的距离 ÷ 静止时。1.00 是不塌，越小塌得越多。画面下方标红的是小于 0.8 的。
  Black Sling 的静止图：手肘弯 120° 时原版平均 0.90、最塌 0.51，SDEF 1.00。
  2026-11-15 的视频（样品旁边的 `SDEF对比_舞蹈.mp4`、`SDEF对比_弯曲.mp4`）：
  - 手肘弯到 130–140° 时原版最塌 0.33–0.37，膝盖弯到约 100° 时 0.28；SDEF 都是 1.00；
  - SDEF 也有自己的痕迹：大弯时肘尖鼓出一个带棱角的包，膝盖后面的折痕更深；
  - 默认测试舞里膝盖最多弯约 50°，两版几乎一样。
- **Blender 里的 SDEF**：mmd_tools 把 SDEF 做成一个形态键，由脚本驱动器每帧重算（`FnSDEF.bind`）。后台 Blender 默认不执行脚本驱动器，
  所以这里绑定后把驱动器去掉，每帧自己调一次 `FnSDEF.driver_function`。MMD 本体自己会算 SDEF，不需要这些。
- 不开物理：比的是关节，头发和布料不动。

## 跑过的批次

- **2026-10-31 Taimanin Squad**（`E:\game_export\TaimaninSquad`，151 个 PMX）：写出 142 个 `*_表情补全.pmx`，0 个出错。
  直方图：88 个补了 14 个，其余 1–13 个不等（原料不全）；9 个一个都补不了：它们没有 まばたき
  （Deathknight、Gsoldier1、Harbinger、Library ×2、Paladin、Paladin2、Rin、Yeager）。
  にこり 起初有 31 个因为 smile_face 不动眉毛而没做，改成「没动静就用下一个备选」后又补了 11 个。
