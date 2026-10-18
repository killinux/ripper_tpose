# PMX 眼睛按游戏公式重烘（瞳孔修正）

工具：`scripts/riseoferos/pmx_game_eye.py`（2026-10-18，Luf g05 第一次用）

## 为什么要修

ROE 导出的 PMX，眼睛是一张烘好的平面贴图（材质 `eye_portable`），做法很简单：纯色眼白，加上原尺寸贴上去的虹膜。结果和游戏里有三处不一样：

- 瞳孔只有虹膜的 11%，游戏里约 27–29%；
- 没有角膜缘的深色圈，眼白没有血丝和明暗；
- 虹膜颜色没乘游戏材质里的 `_IrisColor`。g05 原来偏粉，游戏里是金棕。

游戏每一帧用 5 张贴图合成眼球：虹膜、眼白、虹膜遮罩、眼睑遮蔽、眼白凹凸。Blender 里可以用 ROE 插件的「2.6 游戏原版眼睛」按钮还原，但 MMD 跑不了节点着色器，所以要把这个结果烘成一张贴图交给 PMX。

## 做法

在眼球的 UV 方格里，从正前方逐像素套一遍游戏公式。算法和 `roe_eye_blender.build`（2.6 按钮）完全相同，只有两点不同：

- 角膜视差取 0；
- 不算光照。

公式的具体内容：
- 虹膜按 `(_PupilMinSizeInv + (_PupilMaxSizeInv - _PupilMinSizeInv) × 瞳孔) × _IrisLimbusScaleInv` 放大，瞳孔默认取 0，即游戏展示视频里的大小。g 族的放大倍数是 0.75 × 0.59 = 0.4425。
- 虹膜乘以 `_IrisColor`。
- 角膜缘圈按 `_LimbusPivot` / `_LimbusPivotWidth` / `_LimbusFadeRatio` / `_LimbusSizeIris` / `_LimbusSizeSclera` 计算，颜色用 `_LimbusColor`。
- 眼白贴图按 `_ScleraSizeInv` 缩放。
- 眼睑遮蔽：游戏里它也贴在眼球 UV 上，所以一并烘进去。

验证：在 UV 空间，这张图和在 Blender 里用 Cycles 烘出的 2.6 节点 Base Color 逐像素一致，瞳孔半径都是 0.062。

## 用法

```powershell
cd scripts\riseoferos
python pmx_game_eye.py 原.pmx 新.pmx            # 默认 1024×1024，瞳孔 0
python pmx_game_eye.py 原.pmx 新.pmx --pupil 0.56 --size 512
```

- 新贴图写到 `<新 PMX 所在文件夹>\textures\<模型名>_eye_game.png`。新 PMX 只把 `eye_portable` 的贴图换成它，别的都不动。
- 不会覆盖已有文件，原 PMX 不变。
- 角色代号从文件名里读（`pc_g05_...` → `g05`），也可以用 `--cid` 指定。眼睛材质的选法和 2.6 按钮一样：先找角色自己的，再找套装的，最后用家族的 `pc_<x>_nk_eyes`，从不用战斗用的低模眼睛（`_ld_`）。
- 需要 HQ 材质缓存（`hq_cache.py` 找到的 `E:\game_export\RiseOfEros\_meta\_hq_materials`）里有这个家族的 5 张眼睛贴图。缺虹膜贴图时，在 Blender 里对这个家族点一次 2.6 按钮，或运行 `hq_material_data.py`，它会自动从游戏包读出来。

## 和 2.6 按钮的区别

| | 2.6 按钮（Blender） | 本工具（PMX，给 MMD） |
|---|---|---|
| 瞳孔大小、角膜缘、眼白、虹膜颜色 | 有 | 有（同一个公式） |
| 角膜视差（侧看时瞳孔跟着偏移） | 有 | 没有（贴图做不到） |
| 高光 | 游戏的粗糙度 / 金属度 | MMD 自己的着色 |

侧面看时，2.6 的瞳孔显得小一点，原因是角膜高光和视差，不是贴图本身不同。

## 验证（g05，10-18）

- 对比图：`E:\game_export\RiseOfEros\Luf\pmx\pc_g05_hd\pc_g05_hd_瞳孔_修正前后对比.jpg`。用 Blender 的 MMD 着色渲染，正面和侧 35°，上原版、下修正后。
- 用最终文件读回的贴图是 1024×1024，`eye_portable` 指向它，贴图齐全。
- 交付的 g05 用的是本工具同一套算法：本工具重算的贴图与交付的那张逐像素相同。a08 上也能直接用。
