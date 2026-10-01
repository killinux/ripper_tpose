# Rise of Eros 动作 → VMD（MMD / Blender mmd_tools 可用）

把游戏里角色自带的动作，转成能套在本仓库导出的 PMX 上的 VMD 文件。
第一个样例（2026-10-01）：Luf `pc_g05_hd` 的 `idle_ur01`（UR 浮空待机，5.33 秒）。产出位于
`E:\game_export\RiseOfEros\Luf\vmd\pc_g05_hd\`：

| 文件 | 说明 |
|---|---|
| `pc_g05_hd_idle_ur01.vmd` | 动作本体，在 MMD 里拖到 `pmx\pc_g05_hd\pc_g05_hd.pmx` 上即可 |
| `对照_游戏原版vsPMX_idle_ur01.mp4` | 左：游戏模型直接播解码出的动作；右：PMX + 这个 VMD（经 mmd_tools 导入），无物理 |
| `preview_idle_ur01_MMD物理.mp4` / `.blend` | 贴图 + MMD 式物理的预览；`.blend` 可直接在 Blender 打开看 |

## 动作在哪

每套服装的 bundle 自带动作（Unity *generic* AnimationClip，60 fps）：

- `chara_armor_pc_<id>_hd & ld_hd.ab`：展示用，`idle_02`、`idle_ur01`（部分服装有）、`react_01`、`react_02`
- `chara_armor_pc_<id>_hd & ld_ld*.ab`：战斗用，`idle_01`、`skill_01..03`、`hurt`、`die`、`rip`
- `chara_bare_pc_<id>_nk.ab` / `eros_pro_*.ab`：H 场景的 `pc_xxx_nk@erosNN_*`（尚未试）

AssetStudio 的 `-m animator --fbx-animation all` 导出的 FBX **不带动画**（Blender 里 0 个 action），
所以动作由 `scripts/riseoferos/decode_roe_clip.py` 自己解码：

- 曲线按「骨骼路径的 CRC32」绑定到 Transform（`Bip001/Bip001 Pelvis/...`，相对 Animator 根节点）；
- 数据分 `m_StreamedClip`（三次 Hermite 段：每帧 `time, 键数, (曲线号, c0..c3)`，值 = `((c0·dt+c1)·dt+c2)·dt+c3`）、
  `m_DenseClip`（采样）和 `m_ConstantClip`（常量）三段，曲线号按 binding 顺序排列（位置 3、旋转 4、缩放 3 个分量）；
- 输出 JSON：骨架（名字、父子、静止 TRS）+ 每帧（默认 30 fps）各骨骼的局部 TRS，Unity 坐标系。

## 怎么套到 PMX 上（`make_roe_vmd.py`）

PMX 不是游戏骨架：Convert_to_MMD5 改了名（`Bip001 L UpperArm` → 左腕），加了 センター / 腕捩 / 手捩 / D 骨 / IK，
还把手臂压成 MMD 的 A 字站姿后烘焙进静止姿势。所以不能照抄局部旋转，做法是：

1. **对应关系**：主干骨骼用导出脚本的 `resolve_roe_slots()` 找到 Biped 角色，再按 Convert_to_MMD5 的表对到日文名；
   头发、飘带、脸部、道具等保留原名的骨骼按名字对应。
2. **世界空间旋转增量**：`D_pmx(t) = D_game(t) · S⁻¹`，`D_game = G(t)·G_rest⁻¹`。S 是把游戏骨骼静止方向转到
   PMX 骨骼静止方向的摆动（手臂约 37–41°，其余为 0）。坐标换算 Unity → Blender：`(x, y, z) → (-x, -z, y)`。
   没有对应的骨骼跟随父骨骼，写入的姿势 = `Rrest⁻¹ · D_parent⁻¹ · D · Rrest`。
3. **MMD 习惯**：
   - 腕 只取上臂的摆动，扭转给 腕捩；手捩 取手相对前臂的扭转；
   - 腿 IK 和脚尖 IK 在 VMD 里关闭，播放游戏原本的腿部 FK。
4. **位置**：
   - センター 让 上半身 的根部落在游戏脊椎关节上。转换器把 下半身 的根部上移到了脊椎处，所以不能用骨盆当支点；
   - 道具（花环 Prop1 / Leaf_Dummy）、眉毛、嘴唇等在动作里会位移，这些骨骼带位置帧；
   - **肩**：PMX 把 肩P 挂在 上半身2 上，游戏的锁骨却挂在脖子上。只抄旋转的话，胸部一弯肩就落后 4–12 cm。
     这些 PMX 的 肩 是可移动骨骼，所以给它位置帧，把肩头放到游戏锁骨的位置。
     先后试过把胸部旋转合并到 上半身2、对 上半身2 做 Kabsch 拟合、用 上半身1+上半身2 联合求解，
     误差都在 2–12 cm，最后弃用。
5. **不写帧的骨骼**：
   - PMX 自己驱动的骨骼：带附加变换的（D 骨、腕捩1–3 等），以及挂在动态刚体上的（头发、飘带，交给物理）；
   - **VMD 骨骼名只有 15 字节**（Shift-JIS），MMD 只比较这 15 字节。截断后重名的一组全部不写，否则会套到同一根骨头上。
     样例里有 38 根：8 根 `Bip001 eyebrow_*`、眼皮、脸颊、扭转辅助骨、`Riband_B_Dummy0*`。
     代价是脸部微动和少量扭转辅助骨的动作丢失。要彻底解决，需要在 PMX 导出时把长名改成 15 字节内的唯一名字。

## 第二个样例 g04 带出来的三个修正（2026-10-01）

Luf `pc_g04_hd` 的 `idle_ur01`（2.5 秒）手持一把大折扇，扇子会翻转，暴露出三个问题：

1. **静止姿势要用绑定姿势（bindpose），而不是预制体里 Transform 的初始值。**
   - 身体上两者一致，所以 g05 没看出来；
   - 扇子的载体骨骼 All_Fan_ctrl 在 Transform 里缩放是 2.19，绑定时并不是这个状态；
   - 我们的 FBX/PMX 都是按绑定姿势建的。现在 `decode_roe_clip.py` 会从蒙皮网格读出每根骨骼的 `m_BindPose`，
     算出 `骨骼世界矩阵 = 渲染器世界矩阵 · bindpose⁻¹`，之后所有增量都从这个姿势算起。
2. **站姿摆动 S 只在「子骨骼正好接在尾端」时才算。**
   道具骨骼的尾端是随便摆的。原来允许偏差到骨长的 25%，在 1.36 m 长的扇子载体上算出了一个假的 3.6°，
   把扇子甩出去 15 cm。
3. **D 骨等带附加旋转的骨骼要按 MMD 的规则算**：附加旋转 = 源骨骼相对其父骨骼的旋转 × 影响系数。
   之前把它们当作「跟随父骨骼」，结果挂在 足首D 下的 足先EX（脚尖）偏了 47°。

另外两点：
- 对照视频改用正交相机。两个模型相距 1.7 m，透视相机看两边的角度差约 19°，
  同一个姿势下一边的扇子是侧面、另一边是正面，看起来像出了错，实际两边一样（网格法线差 < 0.005）。
- 往返检查增加了旋转比较。扇子绕自身轴的自转不会改变任何关节的位置，只检查位置是看不出来的。

## 战斗动作（2026-10-01，g05 共 7 段）

战斗动作在 `chara_armor_pc_<id>_hd & ld_ld.ab` 里，和低模（ld）预制体放在一起：
`idle_01`（战斗待机 1.5 s）、`skill_01..03`（3.9 / 4.2 / 5.0 s）、`hurt`（受击 1 s）、`die`（倒下 2.5 s）、
`rip`（破衣后的倒地静止 0.5 s）。产出在 `E:\game_export\RiseOfEros\Luf\vmd\pc_g05_hd\battle\`：
每段一个 VMD，外加一个拼好的对照视频和一个物理预览。

- **骨架取 hd 的**：`decode_roe_clip.py <ld 包> <片段> <out.json> --skeleton <hd 包>`。
  - ld 和 hd 的身体骨骼绑定姿势完全一致（0.00 mm）；
  - ld 预制体里头发网格的节点偏在 2.47 m 之外，用它算出的头发绑定位置是错的；
  - 曲线按路径 CRC 绑定，两个预制体的骨骼路径相同，所以 0 条曲线对不上。
- **根运动不用另外处理**：Animator 上的 7 条曲线（属性 7–9 = RootT、10–13 = RootQ）只是根骨骼 `Bip001` 的
  位置/旋转副本，位移本身已在骨骼曲线里，由 センター 带出来。
  - `skill_01` 跃起约 1 m、前冲 1.2 m 后回到原位；
  - `die` 向前倒地 1.17 m，`rip` 从倒地姿势开始。
- **腿的残差**：大幅动作中腿最多偏 14 mm。游戏的大腿挂在 Spine 下，PMX 的 足 挂在 下半身 下；
  而 PMX 的腿网格绑在只复制旋转的 D 骨上，所以不能像肩那样用位置帧补。

### 骨骼缩放：g04 的扇子（`pmx_add_scale_morph.py`）

g04 的 4 个展示动作（idle_ur01、idle_02、react_01、react_02）把整把扇子缩到绑定尺寸（战斗用的巨型扇）的
**15%**，也就是手里拿一把普通折扇；战斗动作里则保持原大。

- **怎么查出来的**：`bl_scale_check` 比较的是蒙皮骨骼在动画中的世界缩放和它绑定时的缩放。
  对照视频的游戏一侧原先也丢掉了缩放，所以两边都显示成大扇子，没暴露出来；现在会如实应用缩放。
- **为什么用表情**：MMD 的骨骼不能缩放，所以改用顶点表情。
  `pmx_add_scale_morph.py` 给 PMX 加一个表情「扇子縮小」：扇骨（fan_01、Left_fan_01..03、Right_fan_01..03）
  上的顶点以骨骼根部为中心乘 0.15。
  - 扇骨都绕同一根扇轴转，缩放系数在一段动作里又是恒定的，所以在静止空间里做缩放，蒙皮后和游戏完全一致；
  - 名字用「縮」，因为 VMD 的表情名是 Shift-JIS，简体「缩」编码不了。
- **怎么写进文件**：直接在 PMX 二进制里把这个表情追加到表情表末尾，并挂进「表情」显示枠，其他字节不变。
  原文件备份在 `E:\game_export\RiseOfEros\_meta\pmx_old\g04_before_fanmorph_20261001\`。
- **VMD 里怎么用**：`make_roe_vmd.py --morph 扇子縮小=1` 在第 0 帧写入表情关键帧。
  展示动作写 1，战斗动作写 0，这样连着播放也不会串。
- **注意**：如果以后重新导出 g04 的 PMX，需要再跑一次这个脚本，否则展示动作里又会是巨型扇子。

### 丢帧问题（所有 VMD 都受影响，已修正并重新生成）

mmd_tools 约定 **Blender 第 1 帧 = VMD 第 0 帧**：导出时帧号减 1、丢掉第 0 帧，导入时帧号加 1。
最初从 Blender 第 0 帧开始写关键帧，结果 VMD 少了第一帧，整段动作也早了一帧。
往返检查的「导出 −1、导入 +1」正好抵消，所以只在第 0 帧露出来：
- 待机动作变化慢，只差 3 mm；
- 战斗动作在第 0 帧差了 16 cm，才被发现。

现在关键帧写在 `f + FRAME0`（FRAME0 = 1），检查和对照视频也按同样的偏移采样。
检查结果：每段 VMD 都有 0..N 共 N+1 个关键帧，第 0 帧误差 1 mm。

## 验证

`make_roe_vmd.py` 导出后会把 VMD 经 mmd_tools 重新导入到干净的 PMX 上，逐帧比较关节位置与游戏原版：

- 修正丢帧之后（9 段：g05 的 idle_ur01 和 7 段战斗动作，g04 的 idle_ur01；骨骼名改短之后见下面一节）：
  - 旋转全部为 0°（舌头 ≤ 0.1°）；
  - 身体关节 ≤ 0.7 mm；die / rip / g04 的腿 ≤ 5 mm；skill_01 跃起时腿 14 mm（原因见战斗动作一节）；
- 下半身 差 50 mm，是它的根部被转换器挪过，不是动作误差；
- 飘带根部差 1–4 cm，刘海和胸部辅助骨有转角差，这些都交给物理。

拟合出的比例 1.0000、残差 0.0 mm，说明 PMX 骨架就是游戏骨架。

## 命令

日常用两个入口脚本（用法见 [scripts/riseoferos/README_motion.md](../scripts/riseoferos/README_motion.md)）：

```powershell
python scripts\riseoferos\export_roe_motions.py a08 --list     # 有哪些动作
python scripts\riseoferos\export_roe_motions.py a08            # 全部导出 + 往返检查 → <角色>\vmd\pc_a08_hd\
python scripts\riseoferos\render_roe_motion_videos.py a08      # 对照视频 + 物理预览 + 合集
python scripts\riseoferos\export_roe_eros.py a08 --list        # H 场景：有哪些场景、阶段
python scripts\riseoferos\export_roe_eros.py a08               # H 场景导出 → <角色>\vmd\pc_a08_hd\eros15\
python scripts\riseoferos\render_roe_eros_videos.py a08        # H 场景的两人对照视频 + 物理预览
python scripts\riseoferos\pmx_short_bone_names.py <PMX 或文件夹> [--dry-run]   # 旧 PMX 的骨骼名改短
```

它们内部依次调用的单步工具，也可以单独用：

```powershell
# 解码（战斗动作的曲线取 ld 包，骨架和绑定姿势取 hd 包）
python scripts\riseoferos\decode_roe_clip.py <hd 包> --list
python scripts\riseoferos\decode_roe_clip.py <ld 包> skill_01 skill_01.json --skeleton <hd 包>
# 找出被缩放的骨骼
blender -b --factory-startup --python scripts\riseoferos\roe_motion_scale.py -- scale.json skill_01.json
# 给 PMX 加缩放表情
python scripts\riseoferos\pmx_add_scale_morph.py <in.pmx> <out.pmx> 扇子縮小 0.15 fan_01 Left_fan_01 ...
# 生成 VMD + 往返检查（--morph 名字=值 或 --morphs 文件.json 写表情帧；--compare 顺带出对照视频）
blender -b --factory-startup --python scripts\riseoferos\make_roe_vmd.py -- skill_01.json <pmx> <out.vmd>
# 对照视频 / 物理预览 / 重新取景
blender -b --factory-startup --python scripts\riseoferos\roe_vmd_compare.py -- <clip.json> <pmx> <vmd> <游戏 fbx> <out.mp4>
blender -b --python scripts\riseoferos\render_pmx_dance.py -- <pmx> <vmd> - <out.mp4> 0 full mmd
blender -b <out.blend> --python scripts\riseoferos\roe_refit_camera.py -- <out.mp4>
# H 场景：解码男方那段（同名动作按骨架挑），场景形状做成表情，两人一起出视频
python scripts\riseoferos\decode_roe_clip.py <chara_bare_pc_g04_nk.ab> eros07_p1 m.json --skeleton <chara_bare_pc_a00_nk_tutorial.ab> --root pc_a00_nk
python scripts\riseoferos\roe_blendshapes.py <bare_blend_shape_pc_g04_nk.ab> <chara_bare_pc_g01_nk_prelude.ab> <女方 pmx>
blender -b --factory-startup --python scripts\riseoferos\roe_vmd_compare.py -- f.json <女 pmx> <女 vmd> <女 fbx> m.json <男 pmx> <男 vmd> <男 fbx> <out.mp4> --gap 1.1
blender -b --python scripts\riseoferos\roe_eros_preview.py -- <out.mp4> <女 pmx> <女 vmd> <男 pmx> <男 vmd>
```

## 已导出（2026-10-01）

| 模型 | 展示动作（`vmd\<stem>\`） | 战斗动作（`vmd\<stem>\battle\`） |
|---|---|---|
| Luf g05 | idle_ur01、idle_02、react_01、react_02 | idle_01、skill_01..03、hurt、die、rip |
| Luf g04 | 同上 4 段（扇子縮小 = 1） | 同上 7 段（扇子縮小 = 0） |
| Inase a08 | idle_02、react_01、react_02 | 同上 7 段 |

每个文件夹都有 `export_summary.txt`（每段的往返检查）。展示和战斗两组各有一个拼好的对照视频和物理预览
（g05：展示 4 段 17.6 秒、战斗 7 段 18.8 秒）。物理预览在每段前面先模拟 1 秒（`render_pmx_dance.py` 的
30 帧 MARGIN），模型从静止姿势过渡到第一帧，免得物理链被一下甩飞。这 1 秒不渲染进视频：
- 早先的视频带着它，倒下、破衣倒地这类躺着的动作，开头会先站起来再倒下去；
- H 场景每段一开始，两人从站姿「掉」进画面，用户看到的是「头在中间掉下来」。
`roe_refit_camera.py` 和 `roe_eros_preview.py` 现在都从动作的第一帧开始渲染。

预览的地板早先只是一张画面，物理不知道它在那里。a08 战斗动作里出了两个问题：
- 倒下（die）：人躺下以后，裙摆穿过地板挂到下面；
- 破衣倒地（rip）：穿到地板下面的裙摆、甩出去的碎块都算进取景范围，镜头被拉远、拉低到贴地平视，人几乎看不见
  （`refit: bbox (-0.55, -2.14, -0.85) .. (0.98, 1.2, 1.71)`）。

g04、g05 的破衣倒地更糟：镜头落到了地板以下（`camera (-0.51, -5.32, -0.17)`）。

现在两个预览共用 `roe_preview_scene.py`：
- `add_floor_collider`：一个隐藏的被动刚体盒子，顶面就是地板（z = 0），和所有碰撞组都碰；
- `rebake`：加了地板以后重新烘焙物理（`roe_refit_camera.py` 打开的是 `render_pmx_dance.py` 存下的、已经烘焙过的场景）；
- `motion_box`：取景范围按每个轴 99.5% 的顶点算，被缩放表情收起来的顶点不算（a00 的精液网格平时停在 1 米外）。

地板只在预览场景里，PMX 和 VMD 都没有动。

坑：Blender 的方盒碰撞形状以物体原点为中心，不管网格画在哪里。第一版把原点放在盒子顶面，碰撞盒实际是
z = -0.5 .. +0.5，顶面高出地板半米。a08 的长裙下摆一开始就埋在盒子里，引入段第 1 帧就被弹到半空，
之后一直横着飘在 0.55 米高（正好搁在那个看不见的顶面上）。现在原点放在盒子中心（z = -0.5）。
查的办法：逐帧打印裙摆刚体链的位置（加地板和不加地板各一遍），一眼就能看到第 2 帧整条链跳了 0.9 米。

取景：`roe_refit_camera.py` 原来一律平视，镜头高度是动作范围的中间。整段都躺在地上的动作（破衣倒地）
范围不到 0.4 米高，镜头就贴着地面，看到的只是一条。现在动作范围低于 0.8 米时改成从前上方 35° 俯拍，
距离按范围盒 8 个角的投影算。

g04 的 VMD 先按 `_hq_trial` 的高清 PMX 生成，后来又按归档里的高清 PMX 重新生成了一遍。两个 PMX 来自同一版导出程序，
旧的 9 月 6 日 PMX 也能用：
- 骨架相同：共有的 136 根骨骼，按两边各自生成的关键帧最多差 0.07°；
- 按高清 PMX 生成的 VMD 多驱动了头发根部、裙摆上段和脚尖骨。它们在旧 PMX 里是物理骨，MMD 会忽略这些关键帧。

## H 场景（2026-10-01）

### 资源在哪

| 内容 | 位置 |
|---|---|
| 场景动作 | 服装的 `chara_bare_pc_<id>_nk.ab`（g04 → eros07，a08 → eros15；基础服装 g01 里还有 eros01、eros02） |
| 女方身体（预制体 + 绑定姿势） | Luf `chara_bare_pc_g01_nk_prelude.ab`，Inase `chara_bare_pc_a01_nk_tutorial.ab` |
| 男方身体 | `chara_bare_pc_a00_nk_tutorial.ab` |
| 场景摆放 | `eros_naked_pc_<id>.ab`：`pc_g01_e07.naked`、`pc_a00g01e07.naked` 两个预制体都在原点，无旋转 |
| 场景形状 | `bare_blend_shape_pc_<id>_nk.ab`：每个场景一个 TextAsset（E07、E15），游戏运行时加到身体网格上 |

场景动作按阶段分段：`erosNN_p1..p5`，有的场景还有过渡段 `t1_in / t1_out …`。
- 每个名字有两段动作：女方约 650 条曲线，男方约 190 条；
- 另有 `pc_<身体>@erosNN_pN`，只有 6–11 条曲线，是场景形状的权重。

游戏里的场景模型（`Prefab_pc_g01_nk_M07` 等）和裸体底模的网格、骨骼完全一样。所以女方用裸体底模的 PMX：
`pc_g01_nk_bs`、`pc_a01_nk_bs`，是另一个窗口用裸体流程导出的。男方用 `pc_a00_nk`。

### 解码和套用

- **同名动作分男女**：`decode_roe_clip.py` 的 `pick_clip()` 拿每段动作的绑定 CRC 去对骨架，命中多的那段就是这个骨架的。
- **选对骨架**：裸体模型的包里还挂着特效时间轴的 Animator，所以骨架用 `--root pc_g01_nk` 指定；
  不指定时，取下面骨骼最多的那个 Animator。
- **男方的生殖器跟不上身体**：游戏把 `Bip000 Xtra01/02` 挂在 Biped 根上，转换器把它们放到了「全ての親」下，
  PMX 里身体一动它们就留在原地。`make_roe_vmd.py` 现在给这类上面没有被驱动骨骼的骨头写位置帧，误差 0.1 mm。
  同样的情况还出现在若干服装的道具、披风根上（`Bip001 Prop1`、g12 的 `CapeL_L_base` 等），
  用其他 VMD（舞蹈）时它们同样跟不上。这是导出 PMX 时的问题，还没改。
- **精液特效**：`liquid01_T` 在动作里被缩成 0 来隐藏。MMD 骨骼不能缩放，所以给男方 PMX 加缩放表情
  （`縮小_liquid011+` 管 5 根骨骼）：
  - g04 的 eros07 全程是 1，网格收起来；
  - a08 的 eros15_p4 里 5 根骨骼各自从 0 长到 1（喷出来），这时用每根骨骼各自的表情 `縮小_liquid011..015`。
  - 分组规则：在每一段里都一起缩放的骨骼才合成一个表情（`scale_classes()`）。名字后面带 `+` 的是一组骨骼；
    表情的英文名记录了它缩放哪些骨骼，同名但骨骼不同时会换一个名字。
  - 这些骨骼在原型里和整段动作中都离开了绑定位置。新增的「漂移」检查会发现这一点，给它们写位置帧。
- **场景形状**：TextAsset 是 protobuf 格式：网格 → 形状 → 帧（权重 100）→（顶点号，dx，dy，dz），单位米，Z 朝上。
  `roe_blendshapes.py` 把它们做成 PMX 顶点表情：
  - 裸体 PMX 保持游戏网格的顶点顺序，用 UV 核对过，29013 个顶点里 25893 个 UV 完全一致，其余是眼睛贴图重排；
  - 网格到 PMX 的换算在躯干上拟合（比例 12.49），每个顶点的偏移再按邻近 12 个顶点做 Kabsch 转动，
    因为导出时手臂转成了 A 字姿势，手臂修正形状要跟着转；
  - 动作曲线的属性是形状名的 CRC32（不带 `blendShape.` 前缀），权重 0..100 → 表情 0..1；
  - 名字按骨骼名的规则缩到 15 字节：`E07_Pussy_fixShape` → `E07_Pussy_fixSh`；英文名保留原名。

### 已导出

| 服装 | 场景 | 阶段 | VMD（`vmd\pc_<id>_hd\<场景>\`） |
|---|---|---|---|
| Luf g04 | eros07 | p1–p5 | `pc_g01_nk_bs_eros07_pN.vmd` + `pc_a00_nk_eros07_pN.vmd` |
| Inase a08 | eros15 | p1–p5，t1_in/out、t2_in/out、t3_in | `pc_a01_nk_bs_eros15_*.vmd` + `pc_a00_nk_eros15_*.vmd` |

g05 没有 H 场景。用法：两个 PMX 都放在原点，各读自己的 VMD。

## 骨骼名改短（2026-10-01）

VMD 给每根骨骼只留 15 字节（Shift-JIS）的名字。原来的 ROE PMX 每个模型有 40–60 根骨骼名字超长
（扭转辅助骨、脸、头发、裙链），会出两种问题：
- **Blender**：mmd_tools 拿完整名字精确查找，超长的骨骼任何 VMD 都驱动不了；
- **MMD**：按前 15 字节匹配，前 15 字节相同的会撞名（8 根 `Bip001 eyebrow_*` 都成了 `Bip001 eyebrow_`），
  所以 `make_roe_vmd.py` 只好不给它们写关键帧。

全部 253 个 ROE PMX 里一共有 722 种超长名字。改名规则在 `scripts/riseoferos/pmx_bone_names.py`，依次是：
1. 去掉 Biped 前缀：`Bip001 R ForeTwist1` → `R ForeTwist1`；
2. `(mirrored)` → `_m`；
3. 去掉单独的 bone 一词：`AC cheek_bone_L01` → `AC cheek_L01`。如果这个名字已经有别的骨骼在用，就跳过这一步；
4. 还超长，就从最长的单词起一次删一个字母：`AC eyelid_bone_BL` → `AC eyel_bone_BL`；
5. 实在撞名，最后用 `~序号` 兜底。

结果：所有模型里同一个原名都改成同一个新名，0 次撞名，0 次用到兜底。原名写进骨骼的英文名（ROE PMX 原本都是空的），
`make_roe_vmd.py` 按英文名就能对回游戏骨骼。

用在三个地方：
- **导出程序**：`export_character_model_blender.py` 的 `export_pmx()` 在交给 mmd_tools 之前调用 `shorten_bone_names()`；
  插件 roe_pmx_tools 的「④ 导出 PMX」也一样。以后导出的 PMX 自动就是短名。
- **已经导出的文件**：用 `pmx_short_bone_names.py` 原地改写，只动骨骼名字段，改写后逐字段比对、确认其余字节不变才替换。
  2026-10-01 改了 E 盘归档的 234 个和 D 盘导出源的 285 个，原文件备份在
  `E:\game_export\RiseOfEros\_meta\pmx_old\longnames_20261001\`。
- **乳摇调参**：`tune_bust_pmx.py` 按「胸|乳|chest|breast」匹配，改名后照样找得到。

效果（g04 react_01）：
- 能写关键帧的骨骼 117 → 157 根，撞名 40 → 0；
- 往返检查里旋转误差最大的 `hair_BR02` 从 32.5° 降到 0.1° 以内；
- 眉毛、眼皮、脸颊这些表情骨现在跟着动作走。

## 已知限制

- 浮空类动作在游戏里由动画控制飘带；PMX 中飘带由物理驱动，会自然下垂，和游戏不完全一样。
- Animator 的根运动曲线（typeID 95）没有用；待机和展示动作基本是原地的，战斗动作如有位移需再看。
- 每个 VMD 按某一个 PMX 算出来：S（站姿摆动）和位置都取自那个 PMX。要套到别的服装上，就用那套的 PMX 重新跑
  `make_roe_vmd.py`，对应关系会自动重算。不同服装、不同角色之间能否通用，还没有测过。
