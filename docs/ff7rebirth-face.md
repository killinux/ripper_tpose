# FF7 Rebirth 的脸：游戏里的表情怎么做、能拿到什么、怎么接到 Faceit

> 2026-10-01（10-02 补：表情姿势改为直接从游戏解）。起因：用户问 Rebirth 的 Tifa 能不能接 Faceit。本文是对游戏数据的调研（Tifa 为例），
> 以及据此做的提取脚本 `scripts/final/ff7rb_face_data.py`。Blender 一侧的插件在 Convert_to_MMD5 的
> 表情页（「FF7 脸骨」来源 + 手调），见那边的 `docs/expression_design.md`。
> 仓库里只有脚本和说明；游戏数据（姿势矩阵、口型数值）、导出物都不进仓库。

## 0. 结论

- **脸完全靠骨骼**：`C_FaceBase_a`（挂在 `C_Head_a` 下）直接带 103 根平级的脸骨，没有一根是相连骨；
  导出的网格上没有形态键（Tifa 标准版全身一个网格，18.9 万顶点，蒙皮到其中 101 根脸骨，每顶点最多 8 个权重）。
- **游戏里的表情分三层**，都在角色的动画蓝图里叠加：
  1. **表情姿势**：`Facial00` 里的单帧姿势动画，放在「FacialSlot」槽里播；由三个 BlendSpace 混合——
     情绪二维网格（10 个姿势）、眉、眼皮跟随视线；
  2. **口型**：`HSFLipMap`（7 个口型的骨骼通道值）× 每句台词的 `HSFLipSyncDataPack`（时间轴、音素、口型权重、音量）；
  3. **过场**：每个镜头一段逐帧的脸部骨骼动画（`…_FA`），日语、英语各一套（口型不同）。
- **能读到的**（CUE4Parse CLI + Rebirth 的 .usmap，原始属性导成 JSON）：口型表、语音口型数据、BlendSpace 的轴和样本、
  动画蓝图里节点的设置、骨架。
- **AnimSequence 的骨骼轨道** CUE4Parse 1.2.2 解不了（Rebirth 改过的序列化：`Read size is bigger than remaining
  archive length`，随后 `Unsupported compressed data type`；FModel 用的是同一个库）。2026-10-02 起
  `ff7rb_face_data.py` **自己解表情姿势**：原始包里是 ACL 1.3 压缩的片段，单帧姿势的两帧相同，所有轨道都是默认或
  常量，常量值按全精度存——只要读位集和常量数据，不用解变码率部分（见 §3）。Tifa 24 个姿势里 23 个这样解出，
  和 Remake 的同名姿势逐骨差 ≤ 0.4 mm（两作脸骨相同，表情没重做）；带动态轨道的 F_Angry02 用 `--poses-from` 从
  Remake 补。过场表情、情绪动作是真正的动画（动态轨道），仍然解不了。口型 Rebirth 改过几个（oo / ln / bmp 的个别
  通道），用的是 Rebirth 自己的。

## 1. 脸骨

| 部位 | 骨（L_ / R_ 成对，C_ 居中） |
|---|---|
| 眼球 | `L_Eye` `R_Eye`（视线） |
| 上眼皮 / 睫毛 / 褶 | `Ulid_A`–`E`、`Ulash_A` `B`、`Fold_A` `B` |
| 下眼皮 / 眼袋 | `Dlid_A`–`C`、`Eyebag_A` `B` |
| 眉 / 额 / 眉间 | `Brow_A`–`C`、`Forehead`、`Glabella`、`C_Forehead`、`C_Glabella` |
| 颧 / 脸颊 | `Cheek_A`、`Zygoma`（上）；`Cheek_B` `C`（下） |
| 鼻 / 法令纹 | `Nose_A` `B`、`C_Nose_A`；`Laughline_A` `B` |
| 嘴角 | `Ucor` `Ucorin`、`Dcor` `Dcorin` |
| 上唇 | `C_Ulip` `C_Ulipin` `C_Ulipout`、`Ulip_A` `B`、`Ulipin_A` `B` |
| 下唇 | `C_Dlip` `C_Dlipin` `C_Dlipout`、`Dlip_A` `B`、`Dlipin_A` `B`、`Dlipout_A` `B` |
| 下巴 / 牙 / 舌 / 喉 | `C_Chin`、`C_Dteeth` `C_Uteeth`、`C_Tongroot` `C_Tongtip`、`C_Throat_A`、`Gonion` |
| 其他 | `C_Ex_A` `B`（不参与表情） |

下巴不是转轴式的：`C_Chin` 张嘴时主要往下、往后**平移**（口型 aa：后 1.0 cm、下 0.9 cm），下唇骨各自平移跟上
（aa：下 1.7 cm）。所有脸骨平级，嘴唇不会自动跟下巴走——这是做 ARKit 的 jawOpen / mouthClose 时要注意的。

## 2. 动画蓝图里的脸（`BluePrint/Animation/Player/PC0002_00_Tifa_Standard_Animation`）

自定义节点在 `/Script/EndGame`（End = 这个系列的内部代号）：

| 节点 | 设置 | 作用 |
|---|---|---|
| `AnimNode_EndFacialPrimary` | `SlotName = "FacialSlot"`，`bAlwaysUpdateSourcePose = true` | 在脸部槽里播表情姿势 / BlendSpace（表情由游戏逻辑或过场触发） |
| `AnimNode_EndFacialSecondary` | `LipMaps`、`Input{Pack, KeyName, MappingName="Default", EvaluateTime}`、`DummyShape{AudioMin/Max/Power, BlendIn/Out, bRandomize…}` | 口型：按台词的 LSD 关键帧去混合口型表 |
| 类默认值 | `LipMapDefault/Loud/Smile` = `Tifa_Default/Loud/Smile` | 三种说话口型（普通 / 大声 / 带笑） |
| `AnimNode_EndCharacterMovementExpression` | Alpha 混合 | 移动时的表情（身体） |
| `AnimNode_ControlRig` | `CommonHuman00_Rig_C` | 身体 Control Rig（不是脸） |

## 3. 表情姿势：`Motion/Player/PC0002_Tifa/Facial00`

`Facial00.uasset` 是一个 `EndAnimSet`（名字 → 动画资产的表），共 28 项：

- 25 个 AnimSequence：`bPoseAnimation = true`、2 帧、1/30 秒、ACL 压缩，114 条骨骼轨道（骨架的 0–111 号：
  `Trans` … `C_Head_a`、`C_FaceBase_a` 和它的 103 根脸骨，再加 `C_FaceBase_b`、`C_Throat_B`）。
  `F_Idle01` 是游戏的「平静脸」（不等于绑定姿势：舌头后缩约 5 mm、内唇约 1.5 mm），其余都要相对它算。
  F_Angry01/02、F_Attack01/02、F_Brow_down01、F_Brow_up01、F_Brow_up_left01、F_Brow_up_right01、F_Disgust01、
  F_Dmg01/02、F_Eyelid_blink01、F_Eyelid_down01、F_Eyelid_left01、F_Eyelid_right01、F_Eyelid_up01、F_Glad01、
  F_Idle01、F_Sad01、F_Serious01、F_Smile01、F_Sneer01、F_Surprise01、F_Tired01；另有必杀技的表情动画
  `B_AtkLimit01_0_FA`（多帧）。
- 3 个 BlendSpace：

| BlendSpace | 轴 | 样本 |
|---|---|---|
| `F_Eyelid_move01`（眼皮跟随视线） | 水平 −22…22°、竖直 | Idle (0,0)、up01 (0, **+13°**)、down01 (0, **−20°**)、left01 (**+22°**, 0)、right01 (**−22°**, 0) |
| `F_Brow` | −1…1 两轴 | down01 (0,−1)、up01 (0,1)、up_left01 (1,0)、up_right01 (−1,0) |
| `F_Emotion01`（情绪网格，8 格） | 两轴 0…100 | Sad (0,0)、Disgust (0,50)、Angry (0,100)、Tired (50,0)、Idle (50,50)、Surprise (50,100)、Sneer (100,0)、Smile (100,50)、Glad (100,100)、Serious (25,50) |

**姿势包的格式**（UE4.26 IoStore 包，一个导出）：未版本化属性里有 `TrackToSkeletonMapTable`（轨道 → 骨架骨序号），
其后的原生数据里是 ACL 1.3 的 compressed clip（标签 `0xAC10AC10`、版本 5、均匀采样）：ClipHeader 里骨数 114、
1 段、旋转 QuatDropW_Variable、平移 / 缩放 Vector3_Variable、有缩放、2 个采样、30 fps，接着 6 个 16 位偏移（段起始、
段头、默认位集、常量位集、常量数据、范围数据）。位集每骨 3 位（旋转 / 平移 / 缩放），按 32 位字从高位起；常量数据
按骨依次是非默认的旋转（x y z，w ≥ 0 补出）、平移、缩放，各 3 个 float。脸骨有缩放轨道（如 (1, 0.9986, 1)）。
所有角色的扫描：标准姿势都是常量轨道（Cloud 25、Barret 23、Tifa 23、Aerith 24、Red XIII 23、Yuffie 23、
Cait Sith 23、Zack 24、Sephiroth 24、Vincent 25、Cid 25 个）；有动态轨道的只有 Tifa 的 F_Angry02、Yuffie 的
F_BurstChain_04_05_01、Zack 的 F_Talk_idle01、Cloud 的 9 个待机 / 必杀表情。

情绪是**两个连续参数**驱动的：横轴大致是「负面 → 正面」，纵轴「低落 → 激动」，游戏在两者之间连续插值。
眼皮跟随：left01 那一格的眼皮整体往角色自己的左边偏，即 +22° = 往角色左边看；眼皮在往下看时下垂最多
（上眼皮下移 3.4 mm），往上看几乎不动（0.3 mm）。

## 4. 口型

**`HSFLipMap`**（`LipSync/LipMap/Player/PC0002_Tifa/Tifa_{Default,Loud,Smile}`，Version `0120180604`）：

- 7 个口型 aa / ee / oo / sh / fv / ln / bmp，每个列出几十根骨的 Maya 通道值（TranslateX/Y/Z = 在 `C_FaceBase_a` 下的
  **绝对**位置，厘米，X 左 / Y 上 / Z 前；RotateX/Y/Z 角度），不驱动的通道不写；`DefaultShape` 是静止值。
- 每个口型还带音量阈值 `AudioMin/AudioMax/AudioPower` 和淡入淡出 `BlendIn/BlendOut`（aa：55–100、0.2 s / 0.133 s；
  bmp：95–100、0.033 s）。
- 2018 年的 Remake 用 UE Viewer 读不了这个类（无版本属性序列化），ff7_face_data.py 自带解析器；Rebirth 有 .usmap，
  CUE4Parse 直接导成 JSON。

**`HSFLipSyncDataPack`**（`LipSync/Lsd/<US|JP|DE|FR>/Character/Player/LSD_PC0002_00_Tifa`，每种语言一份，约 5–7 MB）：
每句台词一条（如 `LSD_bt003_001_001_tif_0`），`Info{Version 0120220617, KeyOrder [fv,bmp,aa,ee,oo,ln,sh],
AudioLength, AvgAudioPower, MaxAudioPower}` + `KeyFrames[{StartTime, EndTime, Center, Power, Phoneme, Shapes{口型: 权重}}]`。
运行时按时间取关键帧、按音量缩放、用口型表的骨骼值混合——所以游戏的口型是「音素 → 7 个口型 → 骨骼」两级映射。

## 5. 过场与情绪动作

- `Cut/Game/<章节>/<事件>/Facial/{JP,US}/EV_…_PC0002_00_C<镜头>_FA`：每个镜头一段脸部骨骼动画（例：119 帧、114 条轨道），
  按语言分开（口型对不同语言的配音）。Tifa 一人就有 3166 段（日语 2453、英语 713）。
- `Motion/Player/PC0002_Tifa/Emotion00/E_*`：身体 + 脸的情绪小动作（E_Talk01、E_Unazuki01 点头、E_Hitei01 摇头、
  E_CoverFace01 捂脸、E_Look01 …），59 条轨道。
- 这两类是真正的动画（ACL 动态轨道，变码率），§3 的常量解码不够用，还解不出来。

## 6. 提取：`scripts/final/ff7rb_face_data.py`

```powershell
python scripts\final\ff7rb_face_data.py --out E:\game_export\FF7Rebirth\_meta\face\PC0002_Tifa.json `
       --poses-from E:\game_export\FF7Remake\_meta\face\PC0002_Tifa.json      # 可选：补解不出的姿势
```

- 用 `E:\tools\cue4parse_cli_ff7\cue4parse.exe`（Rebirth .usmap，`D:\ff7_mods\_stage\rebirth` 硬链接目录，不带
  ~mods）：`-f raw` 导出 `Facial00/F_*` 原始包，`-f json` 导出 3 张口型表、`F_Eyelid_move01` 和姿势包里写的骨架。
  CUE4Parse 加载索引第一次约 50 秒，之后几秒。
- 姿势：每个 F_* 包读出轨道表和 ACL 常量轨道（§3），按骨架的参考姿势算成和 Remake 一样的形式：每根脸骨
  D = FaceBase_rest · FaceBase_pose⁻¹ · Bone_pose · Bone_rest⁻¹，再换到脸坐标系（UE 的 Y 取反，和 PSK / 游戏导出
  进 Blender 时一样）。两眼间距也从骨架算。有动态轨道的、不止 2 帧的跳过，记在 `skipped_clips`。
- `--poses-from`：Remake 的表情数据（`scripts/final/ff7_face_data.py` 生成），只补游戏里解不出的姿势（Tifa：F_Angry02）。
  其他角色：`--motion PC0003_Aerith --lipmap Aerith` 之类，不需要 Remake 也有姿势。
- 输出格式和 Remake 的一样（`poses` 相对绑定姿势的 4×4、脸坐标系：原点 `C_FaceBase_a`、X 前 / Y 左 / Z 上、厘米；
  `lipmap{DefaultShape, shapes}`），另加 `lipmaps`（Default/Loud/Smile 三张）、`lid_gaze`（眼皮姿势对应的视线角度）、
  `poses_from`（哪些姿势来自 Rebirth、哪些从 Remake 补）、`skeleton`。ff7_face_morphs（MMD）也能直接读。

Tifa 已生成：`E:\game_export\FF7Rebirth\_meta\face\PC0002_Tifa.json`（23 个 Rebirth 姿势 + F_Angry02 取自 Remake，
7 口型 × 3，视线角度）。和之前全用 Remake 姿势的版本比，Convert_to_MMD5 做出的 83 个形态键逐顶点差 ≤ 0.09 mm。

## 7. 接到 Faceit

Faceit 实时面捕驱动的是 52 个 ARKit 形态键，所以要把骨骼表情烘焙成这 52 个形态键。做法在 Convert_to_MMD5 表情页：

1. 打开 Rebirth 模型的 .blend（带脸骨的原始 blend，如 `E:\game_export\FF7Rebirth\Tifa\blend\<模型>\<模型>.blend`），
   选骨架，Convert to MMD 面板第 3 页「表情」。来源「自动」会认出 FF7 脸骨并在 `<游戏>/_meta/face` 里找到表情数据。
2. 勾「Faceit（ARKit 52）」，点「生成表情」：52 个形态键按配方由游戏姿势、口型和少量按骨骼算的动作组成
   （眼皮用游戏的眨眼 / 视线跟随姿势，眼球按 BlendSpace 的角度转；张嘴用口型 aa；单侧笑、皱鼻用对应姿势的一侧……），
   Faceit 已启用就顺带注册（头骨 `C_Head_a`）。注册时模型会被绕 Z 轴转 -90°：导出的 `.blend` 朝 +X，而 Faceit
   按角色朝 -Y 换算手机的头部转动，不转的话点头会变成歪头（只改物体旋转，报告里写明）。
3. 不满意的表情在「手调」里逐个载入到骨架、在姿势模式里改、保存；左右成对的可以镜像到另一侧；再点生成就用手调版。

已在 Rebirth Tifa 标准版上验证：52 个全部生成（约 3 秒）、方向逐个渲染核对，Faceit 注册 52/52。
端到端（2026-10-02）：用 Faceit 自己的接收器收模拟手机发的 Face Cap 数据、用它的导入操作符导入一段 Live Link Face
录制文件，52 个通道都只驱动自己的形态键，头部俯仰 / 左右 / 侧倾绕角色自己的轴转（转向前俯仰和侧倾是对调的）。
