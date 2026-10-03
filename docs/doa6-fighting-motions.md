# DOA6 / DOA5LR 格斗动作提取（不知火舞）

2026-10-03。起因：ROE 格斗游戏想要不知火舞的招式。用户问本机装的 DOA5LR 和 DOA6 里"是否能提取格斗的动作"。

## 结论

| 游戏 | 能不能 | 情况 |
|---|---|---|
| **DOA6** | **能，已打通** | 动作全在 `RRPreview.rdb`，14053 个，文件名带角色代号。不知火舞（`MAI`）269 个，另有全角色通用的 876 个（`CMN`）。格式是 G2A（扩展名写成 `.g1a`），没有现成的命令行工具，照 Project G1M 插件源码写了 Python 解码器 `scripts/doa6/g2a.py`，套到她自己的 DOA6 模型上验证过 |
| DOA5LR | 理论上能，但要从头逆向 | 招式按流派打包（`M_<流派>.MOT`，社区名表里登记了约 40 个），但现在 Steam 版的封包里这些名字一个都对不上；内容应该在没名字的 `char_dat` 包里（2–5 MB 一个）。格式没有公开的解码器。不知火舞在 DOA5LR 里也有（`patch_25_catalog` 里有一套带扇子 `WGT_uchiwa`、前后垂布 `WGT_acs_tare` 的模型），但动作要自己破解，不值得 |

## DOA6：文件在哪

- `RRPreview.rdb`（名字有点误导，不只是预览）：`--types g1a` 共 14053 条，几乎都有名字（封包自带名表）。
- 命名：`<角色代号><5 位编号>_<角色代号>.g1a`。后缀 `_CMN` = 配对动作里**对手**那一半（投技、Fatal Rush 的被打方，播在对手身上）；
  `<代号>_FACIAL_*` 是表情（脸部骨骼），`<代号>_CAMERA_*` 是镜头。
- 不知火舞的编号段（**按数据推测**，没对照官方招式表；`scratchpad mai_describe.py` 量的胯部高度 / 位移 / 手脚速度）：

  | 编号 | 推测 | 依据 |
  |---|---|---|
  | 00000 | 站架循环 | 1.3 秒，原地，胯部 0.63–0.79 米小幅起伏 |
  | 00020–00062、00200–00310 | 走、冲、横移、蹲 | 0.3–1 秒，位移 0.2–2 米，脚不离地 |
  | 00050 | 跑 | 1 秒向前 6.6 米 |
  | 00150、00151、00160、00407、00410 | 跳 | 胯部升到 1.9–2.1 米 |
  | 01000–01920（约 100 个） | 打击技 | 0.6–1.4 秒；手速或脚速高；有的离地（01090、01370、01620 胯部 2 米以上），有的突进（01004、01340 向前 5.2 米） |
  | 01700–01702 | 挑衅之类 | 2–4 秒，原地，速度很低 |
  | 02002 + 02003_CMN | 长连段（可能是 Fatal Rush / Break Blow） | 4.9 秒，向前 4.7 米，带对手那一半 |
  | 04000–04515 | 投技 | 偶数是自己，下一个奇数 `_CMN` 是被投的一方；04024 跳到 3.7 米 |
  | 05000–05700 | 带 `_CMN` 的配对动作（可能是反击 / hold） | |
  | 07000 / 07001 | 选人画面 | `_CHRSEL` |
  | 07010、07110 | 出场 | `_ENT`，07010 从 4 米高跳下来 |
  | 07020、07120 / 07030 | 胜利 / 失败 | `_WIN` / `_LOSE`，8.8–19 秒 |

## DOA6：格式（G2A v0300）

照 `E:\tools\doa6\project_g1m\Project-G1M-main\Source\Public\G2A.h`、`G1A.h`、`G1M\G1MS.h`、`Utils.h` 移植。

- 魔数 `_A2G`，版本 `0300`。头部：帧率（float，DOA6 都是 60）；一个打包的 u32：低 14 位 = 动作长度（最后一帧的序号），
  `(>>18) & 0x3FFC` = 骨骼信息段字节数；然后时间段字节数、条目数（v0400/0500 还多 4 字节）。
- 骨骼信息每根 4 字节：低 4 位 = 曲线条数，接着 10 位骨骼编号（v0500 是 8 位）、剩下的是时间数据偏移。编号回绕时加 1024（v0500 加 256）
  —— 这是**全局编号**。
- 每条曲线：`u16 类型`（0 旋转 / 1 位移 / 2 缩放）、`u16 关键帧数`、`u32 首个数据下标`，后面是每个关键帧的 u16 帧号（4 字节对齐）。
  数据在 `骨骼信息段 + 时间段` 之后，每个关键帧 32 字节 = 4 个 u64，分别是三次多项式的常数 / 一次 / 二次 / 三次项。
  每个 u64：最高 4 位是指数（`((r>>37) & 0x7800000) + 0x32000000` 当 float 用作比例），然后三个 20 位有符号数（x 在 40–59 位、y 在 20–39 位、z 在 0–19 位）。
  两个关键帧之间 `t = (帧 - 起始帧) / 段长`，值 = c0 + c1·t + c2·t² + c3·t³。最后一个关键帧不在动作末尾时，最后一段延长到末尾。
- 旋转曲线给的是**轴角向量**，转成四元数 (x, y, z, w)。
- 骨架（G1M 里的 `G1MS` 段）：每节骨 48 字节 = 缩放 3f、父骨 u32、四元数 4f、位置 3f、1 个 float；另有一张 全局编号 -> 局部编号 的表。
  **四元数直接按列向量约定当局部旋转用就对**（Project G1M 给 Noesis 时 G1MS 取逆、G2A 取共轭，两边一致）：
  按这个约定正向算出来的静止姿势，和 Noesis 导出、Blender 里的 `bone_<全局编号>` 骨头头部位置最大差 0.0001（G1M 单位是厘米）。
- 动作里的位移是**局部位置的绝对值**（不是相对静止姿势的偏移），没有位移曲线的骨用静止位置。
- 老的 G1A（`_A1G`）也支持：每个分量一条 float 三次样条（`read_g1a`），DOA6 的角色动作没见到。

## 用法

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa6
$G = 'D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 6'

# 1. 取动作（MAI = 不知火舞，CMN = 通用）和骨架（用 .blend 里那件衣服的 g1m）
python extract_rdb.py "$G\RRPreview.rdb" -o E:\game_export\DOA6\MaiShiranui\g1a --flat --types g1a --filter "MAI*"
python extract_rdb.py "$G\RRPreview.rdb" -o E:\game_export\DOA6\_common\g1a --flat --types g1a --filter "CMN*"
python extract_rdb.py "$G\CharacterEditor.rdb" -o E:\game_export\DOA6\MaiShiranui\g1m_src --flat --filter "MAI_COS_004*"

# 2. 看动作 / 骨架
python g2a.py info E:\game_export\DOA6\MaiShiranui\g1a\MAI01004_MAI.g1a
python g2a.py skeleton E:\game_export\DOA6\MaiShiranui\g1m_src\MAI_COS_004.g1m
python g2a.py dump <clip.g1a> --out clip.json        # 每根骨逐帧（60 fps）的局部 旋转/位移/缩放

# 3. 套到已导出的角色 .blend 上，渲染预览（每个动作一串 PNG）
blender -b E:\game_export\DOA6\MaiShiranui\blend\MAI_MaiShiranui\MAI_MaiShiranui.blend --python g2a_blender.py -- `
  --g1m E:\game_export\DOA6\MaiShiranui\g1m_src\MAI_COS_004.g1m --clips <a.g1a> <b.g1a> ... `
  --render-dir E:\game_export\DOA6\MaiShiranui\_preview_frames [--save 带动作.blend] [--droop 0.8] [--cam 3.6,2.2,0.55]
```

`g2a_blender.py` 的做法：每帧按 G1MS 父子关系正向算出 G1M 坐标里每节骨的世界变换 W_anim；Blender 骨头的静止矩阵和 G1MS 静止世界变换只差
FBX 导入带来的固定轴向修正，所以 `pose = W_anim · W_rest⁻¹ · rest`，再换成 pose bone 的局部变换写关键帧。身体 / 脸 / 头发三个骨架同源，三个都套。

## 坑

- 文件扩展名是 `.g1a`，内容是 G2A（魔数 `_A2G`）。按魔数分。
- 动作只带身体的 57 根骨（DOA6 的不知火舞：根、胯、腿、脊椎、头、手臂、手指；带位移的只有 1、21、22 号）。
  布料（`nuno*`）、头发、背后的流苏、两侧的布条都是游戏里实时模拟或由 `.rigbin` 驱动的，动作里没有：
  - 物理骨（Noesis 导出成 `nuno1_p_*` / `nunv1_p_*`）跟着父骨刚性走会支棱着；
  - 流苏（800–812 号）在 G1MS 里不是一条链，而是 13 根**并列**挂在 9 号骨（腰）下面的骨，按位置排成一串。
  预览里两种都用 `--droop`（默认 0.8）绕链根往下垂：物理链按链根，并列的那种按"同一父骨下、相邻 20 厘米内连成串、至少 5 根、铺开 30 厘米以上"
  找出来整串一起垂（胸部、背后绳结那种一团的不动）。这只是为了预览好看，不是游戏里的物理。
- 静止姿势里角色朝 G1M 的 +Z；动作第 0 帧她朝 -X 附近（根骨带了朝向），镜头按第 0 帧胯部的朝向摆。
- 骨架在静止时胯部在原点、脚在 -91 厘米；动作里 1 号骨的位移把她抬到地面上（胯部约 0.8 米）。

## 验证

- `MAI_COS_004.g1m`：G1MS 144 节骨，全局编号最大 830；静止姿势和 Blender 骨头对齐误差最大 0.0001。
- 不知火舞 269 个动作全部解码成功（G2A v0300，60 fps）。
- 预览视频 `E:\game_export\DOA6\MaiShiranui\video\mai_doa6_moves_test.mp4`：14 个动作（站架、跑、拳、高踢、突进、空中招、连段、投技、出场、挑衅、胜利），
  套在她自己的 DOA6 模型上（EEVEE，960×540，60 fps）。

## 下一步（给 ROE 格斗游戏）

1. 认骨：DOA6 骨架的骨头只有编号，要按层级和静止位置认出 胯 / 脊椎 / 头 / 左右腿 / 左右臂 / 手指（例：2 = 胯，3·5·7 = 左腿，4·6·8 = 右腿，
   9·10 = 脊椎，12 = 头；左右按 G1M 的 +X = 角色左侧）。
2. 导出给 Unity：Humanoid FBX（或者 BVH，走游戏里现成的通用 BVH 导入），在 `RoeMotionPacks` 的 JSON 里写一个 `doa6_mai` 包：
   站架 / 前进 / 后退 / 跑用 00000、00020 一类，四个攻击键挑几个打击技，超必杀挑突进或连段。
3. 投技、Fatal Rush 这类配对动作要两个人一起播（自己 + `_CMN`），先不做。

## DOA5LR 查到的情况（没继续）

- 动作包：社区名表 `file5lr.dat` 里有 `M_ZACK.MOT`、`M_TINA.MOT`、`M_NINJA.MOT` …… 约 40 个，按流派分；`MOT_VERSION.BIN`、`ANM_VERSION.BIN` 也在表里。
  但 36 个封包、12661 个条目里这些混淆名一个都没出现（名表是 2016 年 3 月的，后来的补丁可能改过）。
- 按内容扫了所有条目（`scratchpad doa5_magic_scan.py`）：`DATA` / `DATA2` 是 `_L1G` 音频包；`MPM` = `char_dat` 容器，有名字的是过场动画和场景物件的动作；
  另有 12 个**没名字**的 `char_dat`，2–5 MB，里面是量化曲线一样的数据，像是流派动作包（`patch_25_catalog #116` 4.7 MB，和不知火舞的模型在同一个补丁包里）。
- `char_dat` 里面的动作格式没有公开资料，要逆向。DOA6 那边已经能用，DOA5LR 先不做。
