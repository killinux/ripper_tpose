# FF7 Remake：从游戏数据生成 MMD 表情（PMX 顶点表情）

> 2026-09-26。起因：用户问 `mod1707_PC0002_00_Tifa_Gantz_Basic_Suit_Skimpy_Hair_and_Ma` 能不能有 MMD 表情，
> 先拿这一个模型做试验，确认后再推广。本文记录做法、数据来源、验证结果和限制。
> 仓库里只有脚本和说明；游戏数据（姿势矩阵、口型数值）、AES key、导出物都不进仓库。
> **怎么用**（MMD 里用 PMX、插件按钮、命令行、常见问题）见 [ff7-face-morphs-usage.md](ff7-face-morphs-usage.md)。

## 0. 结论

- 可以。转换出的 PMX 现在带 **43 个顶点表情**：目 10（まばたき、笑い、ウィンク、ウィンク右、ウィンク２、ｳｨﾝｸ２右、
  じと目、びっくり、はぅ、なごみ）、眉 6（真面目、困る、にこり、怒り、上、下）、口 13（あ、い、う、え、お、ん、ワ、
  にっこり、にやり、∧、口角上げ、口角下げ、口横広げ）、其他 14（游戏原样的整脸表情 F_Smile01、F_Glad01、
  F_Surprise01、F_Sad01、F_Angry01/02、F_Serious01、F_Disgust01、F_Sneer01、F_Tired01、F_Dmg01/02、
  F_Attack01/02）。
- 表情形状全部来自游戏自己的数据，不是手调的：眼、眉、整脸表情取自 Tifa 的表情姿势动画，あいうえお 取自游戏的口型
  （lip-sync）数据。
- 试验版输出在 `E:\game_export\FF7Remake\_face_trial\<label>\`，原来的 PMX 没动。

## 1. 为什么以前没有表情

Remake 的脸是骨骼驱动的：`C_FaceBase_a` 下面约 104 根脸部骨骼（上眼皮 Ulid A–E、下眼皮 Dlid A–C、睫毛 Ulash、
眉 Brow A–C、嘴唇 Ulip/Dlip/in/out、嘴角 Ucor/Dcor、下巴 Chin、上下牙、舌根舌尖、脸颊、鼻翼、法令纹……），
每根都有真实的蒙皮权重，但**网格上没有任何形态键**。`export_ff7_pmx_blender.py` 转 PMX 时会把这些骨骼并进头骨
（否则 Convert_to_MMD5 会把这些皮肤分给最近的眼球骨，眼皮就会跟着视线转），所以之前的 PMX 表情数是 0。

## 2. 游戏里的表情数据

用自己写的 pak 索引读取（v4、索引 AES 加密）列出全部约 96 万个文件后找到两类：

1. **表情姿势** `End/Content/GameContents/Motion/Player/PC0002_Tifa/Facial00/F_*.uasset`：25 个 AnimSequence，
   每个只有 1 帧、非叠加（`AdditiveAnimType = AAT_None`，`SequenceLength = 0.0333`），就是一张完整的脸部姿势：
   眨眼、半闭眼、笑、开心、惊讶、悲伤、生气、严肃、厌恶、冷笑、疲倦、受击、喊叫、眉毛上下/单侧上扬等。
   `F_Idle01` 是游戏的"平静脸"。UE Viewer（FF7 intergrade v8 版）可以直接导出成 .psa。
2. **口型** `End/Content/GameContents/LipSync/LipMap/Player/PC0002_Tifa/Tifa_Default.uasset`（还有 _Loud、_Smile）：
   类 `HSFLipMap`（插件 `/Script/HSFLipSyncRuntime`），7 个口型 aa / ee / oo / sh / fv / ln / bmp，每个口型给出
   几十根嘴部骨骼的 Maya 通道值：Translate 是在 `C_FaceBase_a` 下的**绝对位置**（厘米，X 左 / Y 上 / Z 前），
   Rotate 是角度，不驱动的通道就不写；`DefaultShape` 是静止值（和骨骼静止位置逐根吻合，比如下唇 −2.58 / 8.26）。
   这个包用的是 unversioned 属性序列化（没有属性 tag，靠 uint16 片段头 + 零值掩码），UE Viewer 不认这个类，
   所以 `ff7_face_data.py` 里自带了一个最小解析器。

## 3. 做法

```
游戏 ──UE Viewer──> F_*.psa + 同骨架 PSK + LipMap 原始包
     ──ff7_face_data.py──> 表情数据 JSON（E:\game_export\FF7Remake\_meta\face\PC0002_Tifa.json）
.blend ──export_ff7_pmx_blender.py --face-data <json>──> PMX（形态键 → 顶点表情）
```

- **姿势取样**（`ff7_face_poses_blender.py`）：psk_psa 插件的 PSA 导入依赖它自己导入 PSK 时写在骨骼上的静止数据，
  而 mod 模型是 glTF 导入的、骨骼朝向不同，所以在一个新导入的官方骨架上取样（Tifa 用 PC0002_04 标准装无手套——
  UE Viewer 也会加载 ~mods，要选一个没被 mod 替换的网格）。每根脸部骨骼存成"相对 `C_FaceBase_a` 的刚体变化"
  D = FaceBase_rest · FaceBase_pose⁻¹ · Bone_pose · Bone_rest⁻¹，去掉了动画里身体和头本身的动作；
  再换算到"脸部坐标系"（原点 FaceBase，X 前 / Y 左 / Z 上），这样换模型、换朝向、换单位都能用。
  官方骨架和这个 mod 骨架的脸部骨骼位置最大差 0.36 mm。
- **减去平静脸，而不是绑定姿势**：游戏的 F_Idle01 和模型的绑定姿势并不一样（舌头后缩 5 mm、内唇 1.5 mm），
  如果直接减绑定姿势，每个表情都会带上这点偏移，叠加时还会翻倍。所以姿势表情 = F_X · F_Idle⁻¹。
  口型 = 通道值 − DefaultShape。
- **按区域拆**（插件 `scripts/blender_addons/ff7_face_morphs/core.py` 的 REGIONS / RECIPES）：MMD 的目 / 眉 / 口 表情是分开的，所以同一个游戏姿势
  只取对应区域的骨骼：まばたき = F_Eyelid_blink01 的眼皮 + 睫毛骨；困る = F_Sad01 的眉骨；
  にっこり = F_Smile01 的嘴部骨；あ = 口型 aa；え = 0.5·aa + 0.6·ee；お = oo + 0.45·aa；はぅ 用 F_Dmg02
  （F_Dmg01 只挤一只眼）。其他 14 个是游戏整脸表情原样放进"其他"。
- **烘成形态键**：在脸部骨骼还没被并掉的时候，把骨骼摆成表情、取蒙皮后的网格、减去静止网格，存成形态键。
- **形态键要躲开两次"烘焙"**：Convert_to_MMD5 的 `_bake_pose_delta_to_rest()`（A 字姿势、手臂/手指对齐都用它）
  会**跳过带形态键的网格**——SB 的头是单独网格所以没事，FF7 全身是一个网格，带着形态键手臂就不会被烘焙。
  所以在 A 字姿势之前把形态键按稀疏偏移暂存并删除，Convert_to_MMD5 转换完成后再恢复（恢复前检查脸部顶点
  有没有被动过：这次 0 位移；若整体刚体移动会自动换算，若变形则放弃并报告）。
- **登记**：转换后给每个表情设英文名和面板（EYE / EYEBROW / MOUTH / OTHER），按 RECIPES 排序，重建"表情"显示框。
  mmd_tools 导出时会把网格上所有形态键都写成顶点表情，偏移小于 0.001 PMX 单位（约 0.08 mm）的顶点自动丢弃。

## 4. 验证（试验模型 mod1707 Skimpy + 发型妆容）

| 检查 | 结果 |
|---|---|
| 形态键生成 | 43 个；眼部约 4.7 万顶点在动（这个模型的睫毛网格很密），眉 / 嘴 2–3 千 |
| 转换过程中脸部顶点位移 | 0（暂存 / 恢复 43 个全部原样恢复） |
| PMX 读回（mmd_tools 自带读取器） | 43 个顶点表情，面板正确，越界索引 0，"表情"显示框 43 项 |
| 幅度 | まばたき 最大 0.17 PMX 单位 ≈ 1.4 cm（眼皮褶皱），あ ≈ 2 cm |
| 其他指标 | 撕裂 0、付与顺序错误 0、刚体 80 / 关节 64、静止物理漂移 0.9 cm（和原版一致）|
| 文件大小 | 17 MB → 34 MB |
| VMD 驱动 | 用 `meeynara手势舞` 的 VMD（あ 21 帧、まばたき 11、ウィンク右 5、笑い 3）导入到 PMX，
  在峰值帧渲染跟随头部的特写：眨眼、右眼单眨、笑眼、说话口型都按名字正确驱动 |

对照图：`preview_morphs.png`（PMX 导入后逐个拨表情）；形态键逐个渲染的对照图在试验时生成（脚本见第 6 节）。

## 5. 限制和待定

- 眉部表情是游戏原始幅度，比较含蓄；在 MMD 里看着不明显可以放大（插件面板的"眉 强度"，或批量导出的
  `--face-strength EYEBROW=1.5`）。
- 没有的 MMD 表情：瞳小、ハイライト消し、照れ（这些要改贴图或另加网格，骨骼数据给不出来）、あ２、ω、▲、□，
  以及左右单侧的眉 / 口角变体。本机的舞蹈 VMD 里这些只在第 0 帧写了一个 0 值关键帧，实际没驱动。
- 只做了 Tifa（数据 = `PC0002_Tifa` 的姿势 + `Tifa_Default` 口型）。其他角色要用各自的 `Motion/Player/<角色>/Facial00`
  和 `LipMap`；Rebirth 还没看。
- 只在 Blender 里验证，没有在 MMD 本体里打开过。

## 6. 命令

```powershell
# 1) 从游戏提取 Tifa 的表情数据（只读游戏；key 从 FF7REMAKE_AES_KEY 或 --key-file 读，不进仓库）
python scripts/final/ff7_face_data.py --out E:\game_export\FF7Remake\_meta\face\PC0002_Tifa.json

# 2) 带表情转 PMX（其余参数和 ff7_mod_pmx_batch.py 一样；可选 --face-categories / --face-strength EYEBROW=1.5）
blender -b <model>.blend --python scripts/final/export_ff7_pmx_blender.py -- --out <dir> --name <label> `
    --model-name "<name>" --comment "<comment>" --skirt-to-legs --face-data E:\game_export\FF7Remake\_meta\face\PC0002_Tifa.json

# 3) 只看效果：在 .blend 上生成形态键并逐个渲染脸部特写（不改原文件）
blender -b <model>.blend --python scripts/final/ff7_face_morph_sheet.py -- --face-data <json> --out <out_dir>
```

## 7. Blender 插件 FF7 Face Morphs

同一套代码也做成了插件 `scripts/blender_addons/ff7_face_morphs/`（批量导出脚本调的就是插件里的 `core.py`，
所以手动和批量结果一致）。安装、按钮和手动转换的顺序见插件的 [README](../scripts/blender_addons/ff7_face_morphs/README.md)。
面板在 3D 视图侧栏 MMD 标签页，按钮：查找表情数据、分析模型、生成表情（目/眉/口/其他 + 每类强度）、清除、
预览（选表情拖权重）、导出带表情的 PMX（后台 Blender 跑第 2 条命令，不动当前文件）、转换前暂存 / 恢复并登记。

插件验证（2026-09-26，后台 Blender 逐个调用按钮）：生成 43 个 6 秒；预览 / 归零正确；暂存后恢复与原来逐位相同；
模拟"转 90° + 缩放成米"后恢复，误差 6e-8；清除只删插件生成的形态键（别的形态键保留）；面板导出按钮带眉 1.5 倍：
PMX 顶点 174,375、43 个表情、撕裂 0，5 个眉表情正好 1.50 倍，其余和试验版完全相同；面板 draw() 用模拟布局在
5 种状态下调用无错误。实际界面还没在窗口里看过。

导出时会先清掉 .blend 里之前生成过的表情，再按面板上的类别和强度重新生成。以前留在文件里的旧形态键会被 mmd_tools
一起导出，面板上取消的类别也会进 PMX。验证：全部 43 个生成后取消"口"和"其他"再导出，PMX 读回正好 16 个
（目 10 + 眉 6），撕裂 0。
