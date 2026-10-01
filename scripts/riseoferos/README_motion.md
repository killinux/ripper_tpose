# Rise of Eros 动作导出（VMD）

把游戏里每套服装自带的动作导出成 VMD，套在本仓库导出的 PMX 上用（MMD，或 Blender + mmd_tools）。
导出和出视频分开，都可以手动运行；服装动作（展示、战斗）和 H 场景各有一对脚本。

| 脚本 | 做什么 | 每段耗时 |
|---|---|---|
| `export_roe_motions.py <id>` | 服装动作：解码游戏动作，生成 VMD，并逐帧核对 | 约 6 秒 |
| `render_roe_motion_videos.py <id>` | 服装动作：每段出对照视频和物理预览，再拼成合集 | 约 1 分钟 |
| `export_roe_eros.py <id>` | H 场景：女方、男方各一个 VMD，并逐帧核对（见第 3 节） | 约 10 秒 |
| `render_roe_eros_videos.py <id>` | H 场景：两人一起的对照视频和物理预览 | 约 1 分钟 |

`<id>` 是服装代号，例如 `a08`（Inase）、`g04`、`g05`（Luf）。

## 准备

默认路径都是这台机器上的，不一样时用环境变量改：

| 需要 | 默认位置 | 环境变量 |
|---|---|---|
| Blender 3.6 + mmd_tools（视频那一步用你自己的 Blender 设置，mmd_tools 要处于启用状态） | `D:\Program Files\blender-3.6.15-windows-x64\blender.exe` | `ROE_BLENDER` |
| 游戏 | `D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros`（另会查下载缓存 `LocalLow\Pinkcore\Rise of Eros`） | `ROE_GAME` |
| 导出归档（PMX 从这里找，VMD 也写在这里） | `E:\game_export\RiseOfEros` | `ROE_ARCHIVE` |
| 游戏 FBX（对照视频里「游戏原版」那一侧） | `D:\roe_exports\<id>\...\pc_<id>_hd.fbx` | `ROE_EXPORTS` |
| ffmpeg | `D:\Program Files\ffmpeg\bin\ffmpeg.exe` | `ROE_FFMPEG` |

Python 需要装 UnityPy（`pip install UnityPy`）。

## 1. 导出动作

```powershell
cd E:\code\othercode\ripper_tpose
python scripts\riseoferos\export_roe_motions.py a08 --list        # 先看有哪些动作
python scripts\riseoferos\export_roe_motions.py a08               # 全部导出
python scripts\riseoferos\export_roe_motions.py a08 --clips skill_01,die   # 只导几段
```

常用参数：

| 参数 | 作用 |
|---|---|
| `--stem pc_a08_outfit1_hd` | 同一套服装的其他配色。动作相同，换一个 PMX |
| `--pmx <文件>` | 指定 PMX。默认是归档里的 `<角色>\pmx\<stem>\<stem>.pmx` |
| `--out <文件夹>` | 指定输出位置 |
| `--no-scale-morphs` | 不动 PMX；被缩放的道具会保持原大（见下面「会改 PMX 的情况」） |

输出在 `E:\game_export\RiseOfEros\<角色>\vmd\<stem>\`：

```
pc_a08_hd_idle_02.vmd …            展示动作（idle_02、idle_ur01、react_01、react_02，每套服装不一定都有）
battle\pc_a08_hd_skill_01.vmd …    战斗动作（idle_01 战斗待机、skill_01..03 技能、hurt 受击、die 倒下、rip 破衣倒地）
export_summary.txt                 每段的检查结果
_clips\                            中间数据（解码后的动作、日志），出视频时要用
```

## 2. 出视频

```powershell
python scripts\riseoferos\render_roe_motion_videos.py a08                   # 全部
python scripts\riseoferos\render_roe_motion_videos.py a08 --clips skill_01  # 只重做一段，合集会用现有的分段重新拼
python scripts\riseoferos\render_roe_motion_videos.py a08 --what physics    # 只出物理预览
```

| 文件 | 内容 |
|---|---|
| `对照_游戏原版vsPMX_展示动作N段.mp4`、`battle\对照_…_战斗动作N段.mp4` | 左边是游戏模型直接播放解码出的动作，右边是 PMX 加这个 VMD（经 mmd_tools 导入）。实体着色、正交相机、不开物理，只看身体动得一不一样 |
| `preview_展示动作N段_MMD物理.mp4`、`battle\preview_…` | 带贴图和 MMD 式物理，按整段动作的范围取景 |
| `_clips\videos\compare_<片段>.mp4`、`physics_<片段>.mp4` | 每段单独的视频 |

物理预览走仓库里的 `render_pmx_dance.py`。每段开头有 30 帧从静止姿势过渡的引入段，用来让物理先稳定下来。
这一段参与模拟，但不渲染进视频；早先的视频带着它，H 场景每段一开始，人就从站姿「掉」进画面。

## 3. H 场景

一部分服装带一段 H 场景，例如 g04 是 eros07（5 个阶段），a08 是 eros15（5 个阶段加 5 段过渡）。
场景里有两个人，分别套在两个模型上：

- **女方**：该角色的裸体底模 PMX，例如 `Luf\pmx\pc_g01_nk_bs\`、`Inase\pmx\pc_a01_nk_bs\`。游戏里 H 场景用的就是这个身体；
- **男方**：`Inase\pmx\pc_a00_nk\pc_a00_nk.pmx`。

```powershell
python scripts\riseoferos\export_roe_eros.py a08 --list      # 这套服装有哪些场景、哪些阶段
python scripts\riseoferos\export_roe_eros.py a08             # 导出
python scripts\riseoferos\render_roe_eros_videos.py a08      # 对照视频 + 物理预览 + 合集
```

g01、a01 这类基础服装的包里还有角色本身的场景（Luf 有 eros01、eros02），同样能导出：
`export_roe_eros.py g01 --scenes eros02`。没有 H 场景的服装（例如 g05）会直接说明。

输出在 `<角色>\vmd\pc_<id>_hd\<场景>\`，例如 `Inase\vmd\pc_a08_hd\eros15\`：

```
pc_a01_nk_bs_eros15_p1.vmd    女方，每个阶段一个
pc_a00_nk_eros15_p1.vmd       男方，每个阶段一个
对照_游戏原版vsPMX_eros15_10段.mp4、preview_eros15_10段_MMD物理.mp4
export_summary.txt
```

**在 MMD 里用**：两个模型都放在原点，不要挪；各自读入自己的 VMD，同一阶段的两个文件一起放。
游戏里两人的位置就是这样摆的。

**导出时会改 PMX**（文件末尾追加表情，其他字节不动，重复运行不会重复加）：
- **女方**：加上场景里的形状，做成顶点表情，例如 `E07_Pussy_Open`；VMD 逐帧写入游戏里的权重。
  这些形状是游戏运行时从 `bare_blend_shape_pc_<id>_nk.ab` 加上去的，原本不在模型里；
- **男方**：加上「縮小_liquid011」。游戏把精液特效的骨骼缩到 0 来隐藏它，MMD 骨骼不能缩放，就用这个表情把它收起来。
  VMD 里这个表情一直是 1；
- 改的是归档里的 PMX、旁边的 `_bustB` 版本，以及 D 盘导出源里的同一组文件，免得下次归档又把旧文件拷回来。

## 在 MMD / Blender 里用

- **MMD**：读入 PMX，再把 VMD 拖进去。
- **Blender（mmd_tools）**：
  1. 导入 PMX，缩放用 0.08，和本仓库其他脚本一致；
  2. 选中模型的根对象（mmd_tools 建的空物体）；
  3. 导入 VMD，缩放同样 0.08；
  4. 「边距」（Margin）是在动作前空出的帧数，设为 0 时动作从 Blender 的第 1 帧开始
     （mmd_tools 把 VMD 的第 0 帧放在 Blender 第 1 帧）。

## 会改 PMX 的情况：骨骼缩放

MMD 的骨骼不能缩放，但有的动作会缩放道具。例如 g04 的展示动作把战斗用的巨型扇子缩到 15%，变成手持折扇。

- **脚本怎么处理**：导出时会找出这类「整组按同一比例缩放」的骨骼，给 PMX 加一个顶点表情（例如「扇子縮小」），
  再在 VMD 里逐帧写这个表情的值。缩放比例是任意值、甚至随时间变化，都能准确还原。
- **怎么写进 PMX**：表情直接追加进 PMX 文件，其他内容一个字节都不动。同目录的 `_bustB.pmx` 和 D 盘导出源
  `D:\roe_exports\<id>\blend\pmx\<stem>\` 也一起加。PMX 里已经有这个表情就跳过。
- **注意**：重新导出 PMX 之后，要再跑一次 `export_roe_motions.py`（或 `pmx_add_scale_morph.py`）把表情补回去，
  否则扇子会恢复原大。
- 不加 `--no-scale-morphs` 时，脚本会修改归档里的 PMX，并在 `export_summary.txt` 里写明。
- 各轴比例不一样的缩放（大腿肌肉辅助骨）无法用表情还原，只会在摘要里列出来。

## 检查结果怎么看

`export_summary.txt` 里每段有三行 `round trip`：VMD 重新导回 PMX 后，与游戏原版逐帧比较的最大误差。

- `body joints`：身体关节。
  - 一般在 1 mm 以内；
  - `下半身` 固定约 50 mm，是转换器把它的根部挪到了腰上，不是动作误差；
  - 大动作或倒地时，腿会差 1–1.5 cm：游戏的大腿挂在脊椎上，PMX 挂在下半身上。
- `rotations`：旋转。头发、裙摆、胸部辅助骨这类骨骼这里偏差会大一些，原因见下面的限制。
- `other joints`：飘带根部、道具等。

## 已知限制

- **物理骨不写关键帧**：头发、飘带、裙摆、胸部交给 PMX 自己的物理，动起来和游戏里动画控制的效果不完全一样。
- **骨骼名**：VMD 给骨骼名只留 15 字节（Shift-JIS）。2026-10-01 起 PMX 里的骨骼名都在 15 字节以内，且互不重名；
  原名写在骨骼的英文名里。之前导出的 PMX 已经全部改过。所以眉毛、眼皮、脸颊、扭转辅助骨现在都有关键帧，
  Blender 里也都能驱动。旧 PMX 可以用 `pmx_short_bone_names.py <文件或文件夹>` 改。
- **腿部 IK 在 VMD 里是关的**：播放的是游戏原本的腿部动作。要在 MMD 里手动调腿，先把 IK 打开。
- **位移已经包含在动作里**：技能的冲刺、跃起，倒下时的位移，都记在根骨骼里，由 センター 带出来，没有额外的根运动。
- **H 场景的特效没有导出**：精液、喷水这些由游戏另外的特效时间轴控制，不在动作里。男方的精液网格在 VMD 里始终收起。

## 文件

| 文件 | 作用 |
|---|---|
| `export_roe_motions.py` | 入口 1：服装动作导出 VMD |
| `render_roe_motion_videos.py` | 入口 2：服装动作出视频 |
| `export_roe_eros.py` | 入口 3：H 场景导出（两人各一套 VMD） |
| `render_roe_eros_videos.py` | 入口 4：H 场景出视频 |
| `roe_motion_common.py` | 入口共用的路径、名字和查找 |
| `decode_roe_clip.py` | 从资源包解码 Unity 动作片段（也能单独用：`--list`，`<包> <片段> <out.json> [--skeleton <包> --root <名字>]`） |
| `roe_motion_scale.py` | Blender：找出被缩放的骨骼 |
| `pmx_add_scale_morph.py` | 给 PMX 追加缩放表情（二进制原地追加） |
| `roe_blendshapes.py` | H 场景的形状 → PMX 顶点表情（`--list` 可单独看） |
| `pmx_bone_names.py` / `pmx_short_bone_names.py` | 骨骼名改短的规则 / 改已有 PMX 文件 |
| `make_roe_vmd.py` | Blender：把动作套到 PMX 上、写 VMD、往返检查 |
| `roe_vmd_compare.py` | Blender：对照视频（可以同时放多个模型） |
| `roe_refit_camera.py` | Blender：物理预览按整段动作重新取景 |
| `roe_eros_preview.py` | Blender：多个模型一起的物理预览 |

原理（世界空间对齐、A 字站姿修正、肩膀位置帧、D 骨、帧号对齐、缩放表情等）和每个坑的来历，
见 [docs/roe-motion-to-vmd.md](../../docs/roe-motion-to-vmd.md)。
