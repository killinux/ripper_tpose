# MMD 舞蹈视频（跨游戏）

把小王动画的 MMD 动作合集（`E:\4090\小王动画2026年2月11日以前MMD动作合集`，只读）里的舞，一支一支做成视频。
Taimanin Squad 的角色跳了 125 支（`scripts/taimaninsquad/dance_batch.py`），剩下的 119 支由 Rise of Eros（ROE）的服装来跳，
就是这个目录的 `roe_dances.py`。以后所有舞蹈会放进一个公共页面，按舞蹈列出。

## 最短用法

```
cd scripts\mmd_dances
python roe_backgrounds.py            # 第一次用：从游戏里取出剧情背景图（几分钟，之后不用再跑）
python roe_dances.py --plan          # 只排"哪套衣服跳哪支舞、站在哪张背景前"，写列表，不渲染
python roe_dances.py --count 5       # 按顺序渲染接下来 5 个还没有视频的
```

做出来的视频在 `E:\game_export\RiseOfEros\_videos\`，文件名是"舞名_角色_服装.mp4"，比如 `瓦纳哟哒哒哒电摇舞_Sera_i02_hd.mp4`。
同一个目录的 `_列表.md` 写着谁跳哪支、站在哪张背景前、做完了哪些、哪些衣服没参加以及原因。

## 其他命令

```
python roe_dances.py pc_j01_swim pc_b04_hd          # 只渲染这几套衣服（各跳分给它的那支舞）
python roe_dances.py pc_j01_swim --force            # 重做已经有的视频
python roe_dances.py --count 5 --full-speed         # 正常优先级（默认低优先级，见下面"速度"）
python roe_dances.py --list                         # 只重写列表
python roe_dances.py --drop pc_b01_jeans --why "裙子穿模"   # 看过后不要这套：它的视频删掉，它的舞让给下一套
python roe_dances.py --undrop pc_b01_jeans          # 放回来
python roe_dances.py --prune                        # 删掉不再参加跳舞的衣服留下的视频（运行时会先列出来）
python roe_dances.py --bust-pmx main                # 用原版 PMX（胸部几乎不晃），默认用 _bustB.pmx
python roe_dances.py --no-backdrop                  # 纯灰背景
python roe_dances.py --kinds main,suit,full         # 让"完整裸体版"也参加（默认只有穿衣服的）
python roe_dances.py --keep-loose                   # 让有"不跟身体走的部件"的衣服也参加（默认排除）
python roe_backgrounds.py --sheets                  # 重画背景图的缩略图总览
python pmx_rig_check.py E:\game_export\RiseOfEros   # 只检查 PMX：有没有部件不跟身体走
```

所有参数都有默认值，`python roe_dances.py -h` 列出全部。

## 谁来跳

- **默认是穿衣服的版本**：主模型（`pc_xNN_hd`、`pc_xNN_outfitN_hd`）和时装（泳装、女仆、婚纱……）。
  裸体版、完整裸体版、裸体基础模型和 fm 版不参加。哪个文件夹算哪类，看文件夹名字，规则在 `KINDS`。
- **排除有"不跟身体走的部件"的衣服。** 见下面"已知问题"。现在 173 套里排除 11 套，剩 162 套。
- **轮流分。** 13 个角色排成一圈，每轮每人出一套衣服，衣服少的角色出完就跳过。
  这样每个角色分到的舞差不多，Amano、SFox、Sera 衣服少，分得少一些。
- **分配只排一次。** 结果存在 `plan.json`，以后再运行不会换舞、不会换背景。

## 跳什么

- 合集里能用的舞，规则和 Squad 一样：单人舞、有配乐、不短于 8 秒，同一支舞发布过几次只取最新的。
- 减去 Squad 已经用掉的 125 支，读的是 Squad 的 `plan.json`，可以用 `--taken` 换成别的批次。
- 不能用的 81 个文件夹，列表里写了原因：不到 8 秒、几段动作分不清、没有配乐或配乐不止一个、多人舞、旧版、只有适配别的体型的版本。

## 胸部物理（乳摇）：默认用 `_bustB.pmx`

ROE 归档里每套衣服的 PMX 旁边，大多还有一个 `<id>_bustB.pmx`（`scripts/mmd_physics/tune_bust_pmx.py` 生成）。两者的网格、骨骼、
表情逐字节相同，只有胸部的刚体和关节不同：

| | 原版 `<id>.pmx` | `<id>_bustB.pmx` |
|---|---|---|
| 胸部关节 | 能转 ±10°，**没有弹簧** | 上下 ±25°、左右 ±20°，有弹簧（按重力算好，静止时下垂 15°） |
| 刚体阻尼 | 0.5 | 0.95 |
| 实际效果 | 重力把胸部压在转动限位上停住，几乎不晃 | 会弹、会晃，几下后停住 |

用你的测试动作（适配瓦雷莎.vmd，10 秒）给 Lynn 泳装做胸部特写，量胸部相对上半身的运动：

| | 原版 | bustB |
|---|---|---|
| 左右 | 1.9 厘米 | 2.5 厘米 |
| 前后 | 0.9 厘米 | 1.7 厘米 |
| 上下 | 0.3 厘米 | 2.4 厘米 |
| 每帧平均移动 | 0.04 厘米 | 0.29 厘米 |

左右并排的对比视频：`E:\game_export\RiseOfEros\_videos\_检查\乳摇对比_Lynn泳装_原版PMX_vs_bustB.mp4`。
在舞蹈里差别更大：Lynn 跳"小虎队爱"，原版上下 2.3 厘米，bustB 上下约 4 厘米。

所以舞蹈视频默认用 `_bustB.pmx`，没有的才用原版（`--bust-pmx main` 全部改用原版）。173 套穿衣服的 PMX 里：

- 155 套是上面"锚点下挂一个会摆的刚体"的做法，原版没有弹簧，bustB 有弹簧。
- 4 套的"左胸 / 右胸"本身就是会摆的刚体，直接挂在上半身上：g09、g10（Luf）、c01、c02（Misa）。原版一样没有弹簧，
  bustB 一样加了弹簧。其中 **g09 只有左胸有刚体**，右胸在两个版本里都不会晃。
- 14 套**根本没有胸部骨骼**，胸部直接蒙在上半身上，怎么都不会晃，也没有 bustB：
  a03 到 a06（Inase）、b01 到 b06（Kart）、c03 到 c06（Misa）。

## 背景：游戏自己的剧情背景图，随机分

`roe_backgrounds.py` 从游戏的 `avg_background_image_*.ab`（剧情对话场景的背景，149 个普通 Unity 资源包，
在 `StreamingAssets\AssetBundles` 里，2048 × 1152 或 3840 × 2160）里取出背景图，存到 `E:\game_export\RiseOfEros\_backgrounds\`：

- **419 张写出来**（JPEG，共约 200 MB），缩略图总览在 `_backgrounds\_sheets\`。
- **19 张没写**：名字带 cg 的剧情插画（带人物，有的是裸体）和别的商店的重复版本。
- **16 张看过后排除**（`EXCLUDE`，每张写了原因）：界面底图、全黑、回忆特效、带黑边的重复版本、近景特写、从高处俯视的平台、
  中央是怪物的。
- **剩 403 张可用。** 每套衣服随机分一张，所有图用完之前不重复，119 个视频各不相同。

图放在人物后面填满画面（和 Squad 的视频一样），地面透明，只在人物脚下留影子。人物的打光不变，所以夜景前的人还是亮的。

## 怎么渲染

直接用 Taimanin Squad 的渲染器（`dance_video.py` 和它在 Blender 里的 `render_dance_blender.py`），这里只是把 ROE 的 PMX 交给它：

1. Blender 3.6 + mmd_tools 导入 PMX，带物理、表情和描边。
2. 动作前加 30 帧过渡，让头发和裙子从静止姿势慢慢进入第一个动作。
3. 关节按 MMD 的方式跑：去掉 Blender 默认的 0.5 阻尼，转动弹簧换算到 PMX 单位，重力 98。
4. 先把整段物理烘焙好再渲染。
5. 镜头跟着人走，竖屏 1080 × 1920，配上音乐，背景是上面分到的图。不存 .blend。

**速度。** 一次只渲染一个，空闲内存少于 6 GB 时会等。默认进程是低优先级，好让有人在用电脑时不卡；
但别的窗口开着十几个正常优先级的 Blender 时，低优先级几乎分不到 CPU（实测 25 分钟只算了 2 分钟），这时用 `--full-speed`。

| 实测，正常优先级 | 用时 |
|---|---|
| 18 秒的舞 | 2.5 分钟（机器较闲时）到 6.7 分钟（别的窗口在跑 4 个 Blender 时） |
| 16 秒的舞 | 4.4 到 4.5 分钟 |
| 119 支舞合计 25 分钟长 | 约 5 到 10 小时 |

## 输出

```
E:\game_export\RiseOfEros\_videos\
    舞名_角色_服装.mp4             视频
    _列表.md                       谁跳哪支、背景、做完哪些、不参加的衣服和原因
    _检查\                         检查用的视频（乳摇对比）
    _meta\plan.json                服装 -> 舞、背景
    _meta\videos.json              做了什么、用的哪个 PMX、用了多久
    _meta\dropped.json             看过后不要的衣服和原因
    _meta\rig_check.json           每个 PMX 的部件检查结果（缓存，文件变了才重查）
    _meta\dances.json              合集里每段动作的长度（缓存）
    _meta\list.json                列表的数据，公共页面读它
    _meta\reports\  thumbs\  logs\ 每个视频的渲染报告、缩略图、Blender 日志
E:\game_export\RiseOfEros\_backgrounds\
    *.jpg                          游戏的剧情背景图
    _index.json                    每张图来自哪个包；没写的图和原因
    _sheets\sheet_N.jpg            缩略图总览（排除的打了红叉）
```

动作合集、游戏文件和 PMX 只读不写。已经有的视频不会重做，除非加 `--force`。

## 检查过的东西

- **骨骼。** 抽查了 11 个 ROE 的 PMX，舞蹈要用的标准 MMD 骨骼都在，比 Squad 的还全。
- **bustB 和原版只差物理。** 159 对文件逐个比过，物理之前的部分逐字节相同。
- **胸部测量。** ROE 的胸部是"跟着骨骼走的固定锚点 + 下面挂一个能摆的刚体"。渲染报告原来只量名叫"左胸 / 右胸"的刚体，
  量到的是锚点，所以是 0。现在量挂在下面真正在摆的刚体（`tsquad_blender.bust_bodies`）。Squad 的模型不受影响。
- **裙子和挂件。** 在 Miri e08 上逐帧量过：有刚体的花和裙摆之间的距离一直保持在 2 厘米左右，物理本身是好的。

## 已知问题：有部件不跟身体走

有 11 套衣服的 PMX 里，一部分网格绑在**没有父骨骼**的骨骼上。VMD 只会移动 `全ての親` 下面的那棵骨骼树，
这些部件就停在静止姿势的位置不动，身体跳走了，它们还悬在半空。换到 MMD 里也一样，是模型的问题，不是渲染器的问题。
大多是游戏里运行时才用代码挂到手上的道具。

| 服装 | 角色 | 不跟身体走的部件 |
|---|---|---|
| pc_e08_hd | Miri | 裙子上的四朵花（`flowe_BL_01Root` 等，导出时丢了父骨骼） |
| pc_e07_hd | Miri | 两把枪（`wp_L_all`、`wp_R_all`） |
| pc_j01_hd | Lynn | 武器（`prop_L_Dummy`） |
| pc_j03_hd | Lynn | 手枪（`AC_pistol`） |
| pc_j07_hd、pc_j07_outfit1_hd | Lynn | 右手戒指（`Dummy001`） |
| pc_f09_hd | Rana | 酒杯和酒瓶（`Bip001 Prop1`） |
| pc_c08_hd | Misa | 脚甲、臀环（`AC_footArmour_L/R`、`AC_pantRing_L/R`） |
| pc_i04_hd | Sera | 脚链（`AC_feet_chain`） |
| pc_b12_hd | Kart | 三个球和两条蕾丝（`Ball_01Root` 等） |
| pc_h04_hd | Fen | 一个球（`Root`） |

这些衣服默认不参加跳舞，`--keep-loose` 可以让它们照跳。要真正修好，得在导出 PMX 时把这些骨骼挂到对应的手、脚或裙子骨骼下面。
检查是自动的：PMX 重新导出、文件变了，下次运行就会重查，修好的衣服自动回到跳舞名单里。

## 试做记录（2026-10-04）

| 舞 | 服装 | 结果 |
|---|---|---|
| 瓦纳哟哒哒哒电摇舞 | Sera pc_i02_hd | 第一次用原版 PMX、灰背景；重做用 bustB，背景是夜晚的霓虹街道 |
| 小虎队爱 | Miri pc_e08_hd | 裙子上的花悬在空中，这套衣服因此被排除，视频还留着没删 |
| 小虎队爱 | Lynn pc_j01_swim | 替换上面那个；重做用 bustB，背景是哥特大厅的红地毯 |

## 测试

```
python -m unittest discover -s scripts/mmd_dances/tests      # 在仓库根目录运行，不需要游戏、Blender 和归档
```
