# Vindictus Game Materials（Blender 3.6 插件）

导入 Vindictus（洛奇英雄传：Defying Fate）的 PMX 以后，一键把材质换成**游戏原始的完整材质**，用来在 Blender 里做动画、出渲染。
和 ROE 的插件（`roe_game_materials`）是同一个用法：

- 法线：布料纹理、蕾丝、盔甲的刻纹、皮肤的凹凸；
- 粗糙度 / 金属度（游戏的 ORM / ARM 贴图）：金饰、盔甲的金属光泽，丝绸的反光；
- 皮肤：游戏的肤色调整和透光（次表面散射）；
- 头发：游戏的发色（发根 / 发中 / 发梢三色）和发丝透明；
- 眉毛、睫毛的透明，眼睛的虹膜、眼白和高光。

PMX 格式本身只装得下一张颜色贴图，这些效果只能在 Blender 里加回来。插件不删 mmd_tools 的任何节点：
随时能切回 MMD 着色，用 mmd_tools 再导出 PMX 也和原来一样。

## 安装

仓库里的插件用目录联接装进 Blender，和 ROE 的插件一样。本机已经装好：

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\3.6\scripts\addons\vindictus_game_materials" `
         -Target "E:\code\othercode\ripper_tpose\scripts\blender_addons\vindictus_game_materials"
```

然后在「编辑 → 偏好设置 → 插件」里搜 `Vindictus Game Materials` 勾选。
面板在 3D 视图侧栏（按 `N`）的 **MMD** 标签页，标题「Vindictus 游戏材质」。

需要：
- mmd_tools，用来导入 PMX；
- Vindictus 的存档：`E:\game_export\Vindictus\<角色>\blend\<模型>\<模型>.blend`（`build_blend.py` 做的，带游戏材质和贴图）。
  材质就是从这些 .blend 里搬过来的，不用再读游戏文件。

## 用法

1. 用 mmd_tools 导入 PMX，缩放 0.08。
2. 选中模型：点模型的根、骨架或网格都行。
3. 点「**换上游戏原始材质**」。
   - 第一次用要扫一遍存档里的 .blend（30 个，十几秒），之后几秒。
   - 面板下方会显示「PCF_005：换了 15 个材质……」。
4. 「**游戏材质 / MMD 着色**」两个按钮来回切，方便对比。
5. 在「调整」里拖滑块，**实时生效**。1.0 是游戏原始值，「参数恢复默认」回到原始值。
6. 照常做动画、渲染。要再导出 PMX，就照常用 mmd_tools 导出，PMX 里还是原来那张颜色贴图。
7. 不想要了点「**去掉游戏材质**」，恢复原样。

| 参数 | 默认 | 作用 |
|---|---|---|
| 法线强度 | 1.0 | 游戏法线强度的倍数：布料纹理、缝线、褶皱、皮肤的凹凸 |
| 粗糙度 | 1.0 | 越小越亮、反光越清楚 |
| 金属度 | 1.0 | 金饰、盔甲这类金属部分 |
| 皮肤透光 | 1.0 | 皮肤次表面散射的倍数；0 = 关 |

「高级」里可以改存档目录。存档里加了或改了 .blend 以后点「重新扫描存档」。

## 支持哪些模型

- 存档里 Fiona 的全部 PMX：`Fiona`、`Fiona_BaseBody`、`PCF_001` … `PCF_067`、`Shiningwill_legacy`，以及手臂 / 肘部修正版；
  19 个都试过，材质全部找到。
- 爆衣插件的 `Fiona_full` / `Fiona_burst`（两个身体）：
  - 衣服、脸、头发从 `Fiona.blend` 来，裸体从 `Fiona_BaseBody.blend` 来（那份修过脖子和肤色）；
  - 裸体平时是隐藏的，「衣服非表示」这类表情把它显示出来，换上游戏材质以后也一样。
- 胸部六种对比的 PMX（`bust_variants.py` 做的）。
- 别的游戏不行：只有 Vindictus 的存档里有这套材质。

## 原理

- **认材质**：PMX 的材质名是导出时 Blender2XPS 改的，`4_Face-MI-Fiona-Face01-EyeBall_0.1_0_0` 就是
  `PCF_005_Face` 上的 `MI_Fiona_Face01_EyeBall`，`_` 写成了 `-`。按这个规则倒回去，在存档的 .blend 里找同名材质。
  - 一个部件只有一个材质时只留部件名（`4_Head_0.1_0_0`）。这种就看存档 .blend 里 `PCF_005_Head` 这个网格用的是哪个材质：
    把物体短暂链接进来读一下（0.1 秒），马上移除，不会留在文件里。
  - 同一个材质在一个部件上出现多次，后面加 ` 2`、` 3`。两个部件共用的材质，导出时拆成了 `<材质>_<部件>`。
  - 每套衣服都有同一张脸，所以模型名（「Fiona PCF_067」）里写着的那个 .blend 优先。
  - 每个 .blend 里有哪些材质，记在 `%APPDATA%\Blender Foundation\Blender\3.6\config\vindictus_game_materials_index.json`，
    .blend 没变就不再打开。
- **搬材质**：从存档 .blend 里追加那个游戏材质，把它整套节点复制进 PMX 的材质里，节点名都以 `vhq_` 开头，
  带一个自己的输出节点，再删掉追加进来的那份。切换靠「哪个输出节点是激活的」。
  MMD 的节点一个不删，两边都一直连着，所以 mmd_tools 改材质时不会把输出抢回去，导出 PMX 读的 `mmd_base_tex` 也原封不动。
- **隐藏的材质**：PMX 可以用透明度 0 把材质藏起来，再用材质表情显示（爆衣版的裸体）。
  - 游戏材质的透明度乘上 MMD 的透明度。表情绑定以后，就接 mmd_tools 的 `mmd_bind` 节点，表情一动就跟着变。
  - 这种材质在游戏材质下也用 mmd_tools 的混合模式，并且关掉次表面散射。
  - 原因：试过用 alpha clip / alpha hashed，或者让透明度驱动次表面散射，EEVEE 都会把藏起来的那张脸画成黑的，盖住底下那张脸。
- 代码：`scripts/vindictus/game_materials_blender.py`。存档 .blend 里的节点是 `scripts/vindictus/build_blend.py` 按游戏的
  材质实例做的。也可以单独跑：

```powershell
& "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" -b --factory-startup --python scripts\vindictus\game_materials_blender.py -- `
    E:\game_export\Vindictus\Fiona\pmx\PCF_005\PCF_005.pmx --render C:\tmp\pcf005 --out C:\tmp\pcf005.blend
```

## 注意

- 只在 Blender 3.6 上测过。
- 爆衣版的裸体显示出来以后没有次表面散射，皮肤比穿衣服时那层略「干」一点（游戏值本来就只有 0.02）。
