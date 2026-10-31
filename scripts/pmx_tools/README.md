# PMX 小工具

除了 `texture_alpha_blender.py`（给导出脚本在 Blender 里调用），这里的脚本都直接读写 PMX 文件：用的是 mmd_tools 自带的 PMX 读写模块（自动从
`%APPDATA%\Blender Foundation\Blender\<版本>\scripts\addons\mmd_tools\core\pmx\__init__.py` 加载），
用系统 Python 跑，不需要打开 Blender。**原文件只读，结果都写成新文件。**

保存时沿用原文件的附加 UV 数（`add_uv_count=model.header.additional_uvs`），贴图路径照原样相对于 PMX 所在文件夹。

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

## 跑过的批次

- **2026-10-31 Taimanin Squad**（`E:\game_export\TaimaninSquad`，151 个 PMX）：写出 142 个 `*_表情补全.pmx`，0 个出错。
  直方图：88 个补了 14 个，其余 1–13 个不等（原料不全）；9 个一个都补不了：它们没有 まばたき
  （Deathknight、Gsoldier1、Harbinger、Library ×2、Paladin、Paladin2、Rin、Yeager）。
  にこり 起初有 31 个因为 smile_face 不动眉毛而没做，改成「没动静就用下一个备选」后又补了 11 个。
