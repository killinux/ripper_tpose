# Faceit ARKit —— 给模型补 52 个 ARKit 表情并接上 Faceit 实时捕捉（Blender 插件）

让 iPhone 上的 **Face Cap**（或 Live Link Face / iFacialMocap）通过 Blender 的 **Faceit** 插件实时控制模型表情。
Faceit 实时捕捉驱动的是 52 个 ARKit 形态键，这个插件负责把模型准备好：

**（可选）恢复完整蒙皮权重 → 用 MetaHuman DNA 算出 52 个 ARKit 表情、存成形态键 → 注册到 Faceit（目标表、头部骨骼、实时源）**

操作步骤（带截图）见 [docs/faceit-arkit-guide.md](../../../docs/faceit-arkit-guide.md)；这里讲原理和参数。

```
scripts/blender_addons/faceit_arkit/
  __init__.py     插件入口：侧栏 ARKit 页签 → Faceit ARKit 面板（分析 / 恢复权重 / 生成表情 / 预览 / 注册 / 一键完成）
  api.py          脚本入口（面板按钮调用的也是它）：analyze / restore_weights / bake_arkit / register_faceit / run_all
  dna.py          MetaHuman DNA v2.1 读取 + 按 RigLogic 求值（纯 numpy；从 scripts/vindictus/metahuman_dna.py 拷来）
  arkit.py        52 个 ARKit 名字；每个 ARKit 表情对应的 MetaHuman 控制量配方；认别的写法（eyeBlink_L、Eye_Blink_L …）
  bake.py         DNA 关节姿势 → 模型骨骼 → 形态键
  ue_weights.py   从 UE5 烘焙网格包里读完整蒙皮权重，按顶点位置写回（补 UE Viewer 截掉的权重）
  faceit_link.py  注册到 Faceit（不走它的界面操作符，后台也能用）；找头部骨骼；本机局域网 IP
  cli.py          命令行批处理（同一套函数）
```

## 1. 适用范围

| 模型 | 能做什么 |
|---|---|
| **MetaHuman 脸**：有 `FACIAL_*` 面部骨骼，并且有这张脸的 DNA 文件 | 全自动：52 个表情由 DNA 算出，再注册到 Faceit。Vindictus 的 Fiona（15 套服装 + 裸模共用一张脸）、MetaHuman Creator 导出的角色都属于这一类 |
| **本身已有 ARKit 形态键**（名字写法不限） | 只需要「注册到 Faceit」。例：剑星 Eve 有 49 个（缺 noseSneer 左右和 tongueOut） |
| 两样都没有 | 插件做不了，要走 Faceit 自己的流程（标定特征点 → 绑定 → 生成表情 → 烘焙）。例：Vindictus 的 Lethita（脸不是 MetaHuman，包里没有 DNA） |

需要 **Blender 3.6** + **Faceit 2.3**（本机只在 3.6 里装了 Faceit；插件本身 3.6 以上都能跑）。

## 2. 原理

### 2.1 MetaHuman 的表情在哪

MetaHuman 从 LOD1 起没有表情形态键：UE 运行时由 **RigLogic** 按这张脸的 **DNA** 把约 270 个原始控制量
（`CTRL_expressions.eyeBlinkL`、`jawOpen` ……）换算成约 600 根 `FACIAL_*` 关节的位移和旋转。DNA 里是：

原始控制量 → PSD（多个控制量的乘积，钳到 0..1，给组合表情做修正）→ 关节组矩阵（每组一个稠密矩阵）→
每根关节的局部增量（平移 cm、欧拉角 °）→ 局部变换 = 中性平移 + 增量、中性旋转 × 增量旋转（Maya xyz 顺序，
R = Rz·Ry·Rx）→ 正向运动学。

UE Viewer / PSK 只导出骨骼和蒙皮，不导出 DNA，所以导出的模型骨骼齐全但没有东西驱动它们。
DNA 的完整说明（三层名字、文件各段、每帧怎么算、LOD、读取示例）见 [docs/metahuman-dna.md](../../../docs/metahuman-dna.md)。
Vindictus 的 DNA 嵌在脸网格包 `SK_Fiona_Face01.uasset` 的 DNAAsset 里（v2.1 流，以 `DNA\0\2\0\1` 开头、`AND` 结尾），
`scripts/vindictus/extract_face_data.py` 把它切出来。Fiona 这份 DNA 没有修正形态（blend shape 通道 0 个），
网格包里也没有 morph target —— 游戏本身就是纯骨骼表情，DNA 就是全部表情数据。

### 2.2 ARKit 52 → MetaHuman 控制量

照 Epic 给 Live Link Face 驱动 MetaHuman 用的映射（`arkit.py` 的 `metahuman_recipes()`）。ARKit 的 Left/Right
和 MetaHuman 的 L/R 都指**角色自己**的左右：

| ARKit | MetaHuman 控制量 |
|---|---|
| eyeBlink / eyeLookUp / eyeLookDown / eyeWide | eyeBlink / eyeLookUp / eyeLookDown / eyeWiden（同侧） |
| eyeLookIn / eyeLookOut | 左眼 In = eyeLookRightL，Out = eyeLookLeftL；右眼反过来 |
| eyeSquint / cheekSquint | eyeSquintInner / eyeCheekRaise |
| browDown | browDown + browLateral；browInnerUp = 两侧 browRaiseIn；browOuterUp = browRaiseOuter |
| jawOpen / jawForward / jawLeft / jawRight | jawOpen / jawFwd / jawLeft / jawRight |
| mouthSmile / mouthFrown / mouthDimple / mouthStretch | mouthCornerPull / mouthCornerDepress / mouthDimple / mouthStretch |
| mouthUpperUp / mouthLowerDown / mouthPress | mouthUpperLipRaise / mouthLowerLipDepress / mouthPressU + mouthPressD |
| mouthLeft / mouthRight / mouthFunnel / mouthPucker | mouthLeft / mouthRight / 四片 mouthFunnel / 四片 mouthLipsPurse |
| mouthRollUpper / Lower、mouthShrugUpper / Lower | mouthUpper/LowerLipRollIn、jawChinRaiseU / D |
| cheekPuff / noseSneer / tongueOut | mouthCheekBlow / noseWrinkle / tongueOut |
| **mouthClose** | (jawOpen + 四片 mouthLipsTogether) **减去** jawOpen —— ARKit 的 mouthClose 是「张着下巴时把嘴唇合上」，要叠在 jawOpen 上用 |

### 2.3 姿势 → 形态键

1. **对位**：DNA 中性骨架里的关节和模型骨骼按名字配对（Fiona 620 对），做一次相似变换拟合（缩放 + 旋转 + 平移），
   把 DNA 空间（cm、Y 轴朝上）映射到骨架空间。Fiona 平均误差 0.38 mm，所以换成米为单位、轴向不同的模型也能直接用。
2. 对每个表情：DNA 求出所有关节的世界矩阵，取每根关节「姿势 × 中性⁻¹」的世界增量，换到骨架空间，
   施加到对应骨骼的静止矩阵上（旋转绕骨骼自己的头部，位移用 DNA 的位移），再按父子关系换算成 `matrix_basis`。
   这样与 Blender 骨骼的轴向朝向无关。
3. 形态键 = 该姿势下求值后的网格 − 静止姿势下求值后的网格。形态键在骨架修改器**之前**生效，
   所以算的时候整副骨架必须在静止姿势：插件临时把所有骨骼归零、静音约束、关掉骨架以外的修改器、把已有形态键归零，
   算完原样恢复。已连接的面部骨骼会先断开（Blender 里连接的骨骼不能平移）。
4. 所有被面部骨骼带动的网格都会生成形态键（MetaHuman 导出时头、牙、眼、睫毛常是分开的对象，Faceit 会按名字一起驱动）。

线性叠加的局限：ARKit 形态键是线性相加的，MetaHuman 的 PSD 组合修正（例如「笑 + 张嘴」同时出现时的额外修正）不会出现。
所有 ARKit 形态键方案都是这样，一般看不出来。

### 2.4 UE Viewer 把权重截成了 4 个（最重要的坑）

UE Viewer 内部顶点格式每个顶点只存 **4** 个骨骼权重，而 MetaHuman 的脸每个顶点最多用 **12** 个
（Fiona：66305 个渲染顶点，一共 418000 条权重，平均 6.3 个）。权重被截断后，一做表情脸颊就一块块鼓起来
（张嘴、嘴巴左右移、单侧微笑、鼓腮最明显）。另一个窗口做的 PMX 骨骼表情也是这个原因。

CUE4Parse 读不了 Vindictus（没有 usmap），所以 `ue_weights.py` 直接按特征在网格包字节里找数据（UE 5.x zen 包，LOD0）：

| 找什么 | 特征 |
|---|---|
| 名字表 | zen 包头（5.3 是 52 字节，5.2 是 44 字节）后面的 name batch |
| 参考骨架 | `TArray<FMeshBoneInfo>`：数量 + 每项（FName 下标、编号 0、父骨骼），根骨骼父级 −1，其余父级都在自己前面 |
| 渲染分段 | …… bCastShadow、bVisibleInRayTracing、**BaseVertexIndex**、ClothMappingDataLODs（0）、**BoneMap**（数量 + u16）、NumVertices、MaxBoneInfluences —— 从顶点 0 开始一段段接到 N，接不上就换下一个候选 |
| 顶点位置 | Stride 12、N、bulk(12, N)、float xyz |
| 权重数据 | bVariableBonesPerVertex=1、MaxBoneInfluences、总条数、N、16 位骨骼下标、16 位权重、bulk(1, 字节数)；每个顶点先 k 个下标再 k 个权重（和为 255） |
| 查找表 | 紧跟权重数据：2 字节 strip flags、N、bulk(4, N)，每项 = 偏移 << 8 \| k |

写回时按**顶点位置**配对（自动找 UE → Blender 的轴向：Fiona 是 (x, −y, z)；也试 0.01 / 100 倍缩放），
同一位置的重复顶点全部配上。只改写「当前权重正好是游戏权重里某几根骨骼重新归一化」的顶点（UE Viewer 截断的样子），
后来手工改过的区域（比如脖子接缝加了身体骨骼的权重）保持不动。Fiona_BaseBody：15020 个顶点补全，
脖子修复挪过位置的约 900 个顶点配不上，自然不动。

## 3. 注册到 Faceit 做了什么

Faceit 的「Register Selected Object」「Smart Match」要用界面区域，后台会报错，所以 `faceit_link.py` 直接写它的数据（按 Faceit 2.3.40）：

- `scene.faceit_face_objects`：登记带 ARKit 形态键的网格（已登记的保留）；`faceit_body_armature` = 模型骨架。
- `scene.faceit_arkit_retarget_shapes`：52 项，每项的目标形态键按名字匹配（别的写法也认），再调 Faceit 自己的
  `set_base_regions_from_dict` 分好脸部区域。
- 头部：`faceit_head_target_object` = 骨架，`faceit_head_sub_target` = 头部骨骼（没填就自动找：`FACIAL_C_FacialRoot` 的父骨骼 →
  常见名字 head / Bip001 Head / J_Bip_C_Head / 頭 … → 脸上权重最大的非面部骨骼）。
- 实时源（默认 Face Cap，端口 9001）：转头开，头部位移关（容易漂），**眼睛用形态键、不转眼球骨骼**——
  eyeLook 形态键里已经包含眼球转动和眼皮跟随，再转骨骼就转两次。
- Faceit 实时接收时会读它自己的插件偏好，所以必须在偏好设置里启用 Faceit（命令行里临时启用即可）。

## 4. 验证记录（2026-09-26，Fiona_BaseBody）

- 52 个表情逐个渲染正面和 3/4 侧面对照；数值核对方向：Left 形态只动角色左半脸（+X），jawLeft / mouthLeft 往 +X，
  眼珠 In/Out/Up/Down 方向正确，jawForward 往前，tongueOut 往前。
- 权重恢复前后对照：张嘴、嘴巴右移、左侧微笑、鼓腮的鼓包全部消失。
- 插件输出和手工流程的文件逐点比较：53 个形态键坐标差 0，32481 个顶点权重完全一致（改进并列判定之前）。
- Faceit 实时链路：在 Blender 窗口里启动 Faceit 接收器，用脚本冒充 Face Cap 往 127.0.0.1:9001 发 OSC（`/W 序号 数值`、`/HR 度数`）：
  形态键数值和发送值一致；转头 20° 绕竖直轴，点头 15° 绕左右轴，歪头 10° 绕前后轴。
- 界面：面板「一键完成」→ 权重补全 15020、52 个表情、Faceit 52/52、面板直接显示手机要填的 IP 和端口。
- 另外两个模型：Fiona 默认铠甲（同一张脸，32481 个顶点全部配上）；剑星 Eve（已有 49 个 ARKit 形态键，只注册）。

## 5. 命令行

```
blender -b --factory-startup <model.blend> --python scripts\blender_addons\faceit_arkit\cli.py -- ^
    --dna E:\game_export\Vindictus\_meta\face\SK_Fiona_Face01.dna --out <输出.blend> [--no-backup]
```

`--package` 不给时自动找 DNA 旁边同名的 `.uasset.bin`；`--no-weights` / `--no-faceit` 跳过对应步骤；
`--head` 指定头部骨骼；`--source FACECAP|EPIC|IFACIALMOCAP|TILE`。结果打印成一行 `FACEIT_ARKIT_REPORT={json}`。
