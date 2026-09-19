# ROE 角色手动转 PMX（标准流程）

2026-09-19。目标：不靠批处理脚本，在 Blender 里一步步把一个 Rise of Eros 角色转成
MMD 能直接用的 PMX——骨骼是 MMD 标准骨、权重完整、带布料物理和表情。四步，每步之后
都能在视口里检查，出问题停在哪一步就清楚。

批处理（`scripts\riseoferos\export_character_models.ps1 -Only <id> -Format pmx -Force`）
做的是同一套事，同一份代码；手动流程只是把它拆成了按钮。

## 1. 准备

Blender 3.6，Preferences → Add-ons 里这几个都要启用：

| 插件 | 作用 | 装在哪 |
|---|---|---|
| **mmd_tools** | PMX 导入导出、MMD 数据结构 | 第三方 |
| **Convert_to_MMD5** | 一键把普通骨架转成 MMD 标准骨 | `E:\code\othercode\Convert_to_MMD5` |
| **ROE XPS Tools**（`roe_xps_addon.py`） | 导入 ROE 的 FBX、挂材质、分头部槽 | `scripts\riseoferos\roe_xps_addon.py`，Install 单文件 |
| **ROE PMX Tools** | 本流程的四个按钮 | `scripts\blender_addons\roe_pmx_tools`，目录联接到 addons |
| **MMD Cloth Physics** / **MMD Face Morphs** | 布料、表情（③ 会自动调，也可以之后手动调） | `scripts\blender_addons\mmd_cloth_physics` / `mmd_face_morphs`，目录联接 |

联接命令（换机器时）：

```
mklink /J "%APPDATA%\Blender Foundation\Blender\3.6\scripts\addons\roe_pmx_tools" "E:\code\othercode\ripper_tpose\scripts\blender_addons\roe_pmx_tools"
```

模型来源：`extract_character.ps1 <id>` 提取出的 FBX，例如
`D:\roe_exports\b14\pc_b14_outfit1_hd\FBX_GameObjects\pc_b14_outfit1_hd\pc_b14_outfit1_hd.fbx`；
贴图目录是同一角色的 `D:\roe_exports\b14\_textures`。

## 2. 四步

3D 视图按 N → **ROE** 页签。上面是 XPS 面板，下面是 **PMX 导出（MMD）** 面板。

| 步骤 | 做什么 | 这一步之后看什么 |
|---|---|---|
| 在 XPS 面板填 **FBX** 和 **贴图目录** | 两个面板共用这两个字段 | — |
| **① 导入 FBX 并挂材质** | 等于 XPS 面板的第 1、2 步，再补批处理才有的两件事：材质过程漏掉的贴图按名字补回，头和身体融在一起的模型（a00 那种）给眼球补材质 | 视口里贴图对不对；面板报「头部已分槽」。脸不对就点 XPS 面板的「修复脸部」 |
| **② 骨架预处理** | 认 Biped 骨位（`Bip001 Pelvis` 之类，大小写和空格的各种拼法都认）；烘正骨架朝向；**把挂错父级的肢体辅助骨按比例交还给关节**（`ForeTwist`、`ThighTwist`、`knee_L` 这些挂在上臂或脊柱上的，不处理就会手腕撕开、膝盖一圈接缝）；松肩膀权重；手臂放到 **37°** A-pose（MMD 的标准站姿，T-pose 的话所有 VMD 手臂都高 37°） | 面板报重新挂了几根辅助骨、手臂角度。视口里看 A-pose，手腕肘膝有没有撕裂 |
| **③ 转 MMD 骨架 + 物理 + 表情** | Convert_to_MMD5 一键转换（センター、IK、D 骨、捩骨、肩 P 等）；辅助骨在新骨架上加付与；被转移到无关骨上的权重放回去；加 **両目**；**mmd_face_morphs** 建 58 个表情；身体碰撞胶囊；**mmd_cloth_physics** 给裙子袖子飘带头发建刚体关节；算撕裂边 | 面板报骨数、両目、表情数、权重空洞、物理件数、撕裂边数。撕裂边 >0 看 README §5 的分诊表。想调物理或表情，此时去 **MMD** 页签用 Cloth Physics / Face Morphs 面板，调完再 ④ |
| **④ 导出 PMX** | 眼球程序化材质烘成 PNG；纯透明槽（eye_overlay、部分睫毛眉毛）设 alpha 0，否则导出成灰片；mmd_tools 按 **12.5** 倍导出并复制贴图；回读 PMX 校验付与顺序；旁边写 `*.report.json` | 面板报路径、付与顺序违规数（应为 0）。**PMX 输出**留空写到 `D:\roe_exports\pmx_manual\<模型名>\`，别放进 `D:\roe_exports\<角色>\pc_xxx\`（重新提取会清空） |

**一键 ①→④** 四步连跑；**重来** 忘掉中间结果（换模型前点，场景要自己 File → New）。

## 3. 验证

- **看一眼**：mmd_tools 导入刚导出的 PMX（勾 Physics），Ctrl+Tab 姿态模式转转 `左腕`、`左ひざ`，
  皮肤要跟着走，手腕肘膝不撕。
- **跳舞**：`scripts\riseoferos\render_pmx_dance.ps1 -Only <角色> -Force` 用真 VMD 渲一段（物理、
  眨眼都跑），或者在 Blender 里导入 PMX → Morph Tools **Bind** → 导入 VMD → 播放。
- **表情**：`docs\mmd-face-morphs-guide.md`。
- **MMD 本体**：`E:\tools\MikuMikuDanceE_v932x64\MikuMikuDance.exe` 读模型和动作。

## 4. 常见问题

| 现象 | 原因 | 办法 |
|---|---|---|
| ② 报 `rig lacks joints the MMD conversion needs` | 不是 Biped 骨架，或骨名拼法没见过 | 看控制台缺哪个骨位，`resolve_roe_slots` 里补拼法 |
| 手腕/膝盖撕裂、皮肤留在原地 | 肢体辅助骨没交给关节（跳过了 ②，或手动直接用 Convert_to_MMD5） | 走 ②；已转好的用 `scripts\riseoferos\fix_limb_helpers.py --input x.blend --fix` |
| ③ 表情数 0 | 男模没有脸骨（a00、a03–a06），属正常 | — |
| 脸上出现一块灰白色 | 透明槽没设 alpha 0（没走 ④ 直接用 mmd_tools 导出） | 走 ④ |
| 导出后眼睛全白 | 眼球还是程序化材质 | ④ 会烘；若报 skipped，先在 XPS 面板点「修复眼睛」 |
| 付与顺序违规 >0 | 両目/辅助骨的变形层级不对，MMD 里视线和辅助骨不动 | ③ 已按规则设，出现就把 `*.report.json` 贴给我 |
| 布料整段不动 / 穿模 | 预设不合适 | MMD 页签 Cloth Physics：Strip → Analyze → 改预设 → Build → Drop test，再 ④ |
| ③ 报 `物体 '.dummy_armature' 不在视图层` | 同一个 .blend 里还有别的场景（比如 morph slider 留下的代理骨架），旧版 worker 按整个文件找骨架 | 2026-09-19 起 worker 只在当前场景找；仍遇到就 File → New 换个干净文件再来 |
| ④ 报 `bake_eye_texture() got an unexpected keyword argument` | 磁盘上的 `roe_xps_addon.py` 更新了，但 Blender 内存里还是启动时那份 | 重启 Blender（Preferences 里禁用再启用也行）。PMX 面板自己那部分和 worker 在每次 ① 时会自动重载，XPS 插件不会 |
| 换了个模型，② 报的还是上一个 | 中间结果留在内存里 | 点 **重来**，File → New 再从 ① 开始 |

## 5. 它和批处理的关系

`export_character_models.ps1` 对每个模型做的就是这四步（worker
`export_character_model_blender.py`），外加渲预览图、写 manifest、重建画廊。手动流程调的是
worker 里同一批函数，所以两条路出来的 PMX 是一样的；批处理适合全量，手动适合单个模型
边看边调。
