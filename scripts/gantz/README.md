# GANTZ 主题 mod 画廊

把几个游戏里 **GANTZ（杀戮都市）主题** 的 Nexus mod 导出的模型放在一页里看：`html\index.html`。
只收 GANTZ 相关的，其它 mod 各自在所属游戏的画廊里。

```powershell
python scripts\gantz\html\make_gallery.py
```

| 游戏 | mod | 作者 | 角色 | 模型 | 身材 |
|---|---|---|---|---:|---|
| FF7 Remake | #967 Tifa - Gantz Suit | MonkeyMan Mods | Tifa | 2 | 原版 Tifa |
| FF7 Remake | #1707 Tifa Gantz Basic Suit (Custom Emission) | TheWolfster | Tifa | 6（2 个是发型妆容附加包单独套在原版服装上，只有 blend） | 原版 Tifa |
| FF7 Rebirth | #817 GANTZ Basic Suit (Tifa) | TheWolfster | Tifa | 8（替换版 4 + Dresscode 版 4） | 原版 Tifa |
| FF7 Rebirth | #1613 Gantz - Reika (DRESSCODE) | SeeS | Reika | 5 | 夸张（mod 原设计，作者截图也是这样；没有瘦的版本） |
| Stellar Blade | #3561 Gantz Reika (CNS) | Hawkins（hwahwa） | Reika | 2 | 正常（Eve 的身体） |

## 数据从哪来

全部读 `E:\game_export` 归档，不碰 D 盘：

- 各游戏 `_meta\models.json`：按 `<角色>/<格式>/<造型>` 查主文件（`.blend` / `.xps` / `.pmx`）和预览图；
- 各游戏的画廊清单（`_meta\ff7remake_models_manifest.json`、`ff7rebirth_gallery_manifest.json`、
  `stellarblade_models_manifest.json`）：顶点 / 骨骼 / 材质，FF7 两作还有 PMX 检查结果（身高、刚体、撕裂、漂移）；
- 缩略图直接用各游戏画廊生成好的 `_meta\gallery\thumbs\<label>.jpg`，这里不另生成。

页面用 `file://` 链接指向本机文件，游戏素材不进仓库。筛选：游戏、mod、身材，搜索框搜模型名 / 说明 / 作者。

## 以后又导了 GANTZ mod

1. 照所属游戏的流程导出 Blender / XPS / PMX（FF7 两作见 `docs\ff7-nexus-mods-export.md`，Stellar Blade 见
   `scripts\stellarblade\README.md`），并用 `scripts\archive\archive_exports.py <游戏>` 归档到 E 盘；
2. 在 `html\make_gallery.py` 的 `MODS` 里加一行（游戏、mod 号、角色目录、造型名前缀、身材），
   `NOTES` 里给每个造型写一句缩略图看不出来的差别；
3. 重跑 `make_gallery.py`。
