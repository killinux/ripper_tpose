# Expression Kit（表情工具箱）—— 多种来源、多种输出的角色表情（Blender 插件）

一个插件管表情，三种输出，可以同时用，也可以只用其中一种：

- **MMD 骨骼表情**：PMX bone morph，体积小，下巴、眼皮是真正的转动；
- **MMD 顶点表情**：形态键，导出后是 PMX vertex morph，在 MMD 里和 Blender 里一模一样；
- **52 个 ARKit 形态键**：注册到 **Faceit**，iPhone Face Cap / Live Link Face 实时驱动。

MMD 表情还有「自动」方式：逐个表情算出做成骨骼表情时 PMX 会偏多少，偏得少的用骨骼表情，偏得多的用顶点表情。

表情从哪来，有四种来源：MetaHuman **DNA**、模型**已有的 ARKit 形态键**、自己摆的**姿势库**、
没有任何表情数据的**骨骼脸自动配方**。

操作步骤（带截图）见 [docs/expression-kit-guide.md](../../../docs/expression-kit-guide.md)，这里讲原理、兼容性和验证。
业内其他做法的调研：[reports/面部表情实现方式调研.md](../../../reports/面部表情实现方式调研.md)。

```
scripts/blender_addons/expression_kit/
  __init__.py     插件入口（3D 视图侧栏「表情」页签），重载子模块
  ui.py           面板和按钮；按钮只调 api.py
  api.py          脚本入口：analyze / build / estimate / clear / preview / check / register_faceit /
                  restore_weights / stash / restore / export_pmx / capture
  engine.py       来源 + 配方 → 骨骼表情 / 形态键；同一个名字只留一种；自动模式
  sources.py      四种来源：DNA、已有形态键、姿势库、骨骼脸
  recipes.py      配方：MMD 60 个名字、ARKit 52 个，每个名字按来源各有一份；可导出成 JSON 改完再载入
  names.py        ARKit 52 名单、各种写法的识别、PMX 表情面板分类
  roles.py        骨骼脸：按「角色」找骨骼，加上标定过的动作（移植自 mmd_face_morphs）
  bake.py         姿势 → 形态键；PMX 4 权重误差估算
  mmd.py          mmd_tools：骨骼表情、顶点表情登记、「表情」显示枠、morph slider、暂存 / 恢复、导出 PMX
  faceit.py       注册到 Faceit（移植自 faceit_arkit）
  dna.py          MetaHuman DNA v2.1 读取 + RigLogic 求值（与 scripts/vindictus/metahuman_dna.py 同一份）
  ue_weights.py   从 UE5 游戏包恢复完整蒙皮权重（移植自 faceit_arkit，加了拆开的网格和改过名的骨骼）
  tools/          render_sheet.py 逐个表情渲染、make_sheet.py 拼成带标签的对照图
```

## 1. 来源 × 输出

| 来源 | 什么模型 | MMD 骨骼表情 | MMD 顶点表情 | ARKit 52（Faceit） |
|---|---|---|---|---|
| **MetaHuman DNA** | 有 `FACIAL_*` 骨骼，并且有这张脸的 `.dna`（Vindictus Fiona、MetaHuman Creator 导出的角色） | 可以 | 可以（用完整权重烘焙） | 52 个 |
| **已有形态键** | 模型自带 ARKit 形态键，写法不限（星刃 mod、VRoid 的 Perfect Sync、CC4 ……） | 不行（没有骨骼动作） | 可以（按配方混合） | 已经有了，直接注册 |
| **姿势库** | 任何骨骼脸：自己摆好姿势记录下来，或者带姿势标记的动作，名字用 MMD / ARKit 名 | 可以 | 可以 | 可以（名字用 ARKit 名） |
| **骨骼脸自动** | 没有任何表情数据，只有眼皮、眉、下巴、嘴唇、舌头骨骼（Rise of Eros 这种） | 可以 | 可以 | 48 个（实验性，见 §6） |

实测：
- Fiona（DNA）：MMD 顶点表情 56 个（含 瞳小），骨骼表情 55 个，ARKit 52 个；
- 星刃 Fiona mod（49 个 ARKit 键）：MMD 50 个；
- ROE b14（骨骼脸）：MMD 59 个，ARKit 48 个。

做不出来的名字会列出原因，例如 ω 没有 DNA 配方、模型没有 tongueOut、瞳小 要缩放所以做不成骨骼表情。

## 2. MMD 和 Faceit 能不能一起用

能。一个 `.blend` 里可以同时有 MMD 表情和 52 个 ARKit 形态键，名字不一样，互不相干。插件把它们做成**分开的按钮**，
想要哪种点哪种。真正会冲突的地方有这些，插件都处理了，「兼容性检查」会把现存的问题列出来：

| 冲突 | 后果 | 插件怎么处理 |
|---|---|---|
| 同一个 MMD 名字既有骨骼表情又有顶点表情 | MMD 两个都执行，脸动两次 | 生成一种时删掉同名的另一种（「替换同名」开着时；关掉则跳过已有的） |
| mmd_tools 导出 PMX 时把**所有**形态键写成顶点表情 | 52 个 ARKit 键进 PMX 当「其他」表情（Fiona：15 MB → 20 MB） | 「导出 PMX」默认把 ARKit 键暂时拿开；要带就勾「带 ARKit 形态键」，并排在 MMD 表情后面 |
| Convert to MMD 转换时跳过带形态键的网格的姿势烘焙（A 姿势、对齐手臂） | 带着形态键转换，手臂会歪 | 转换前「暂存」（形态键存进一个隐藏副本），转换后「恢复」（模型被转向或缩放成米也跟着换算）；或者先转换再生成 |
| PMX 每个顶点只存 4 个骨骼权重，MetaHuman 脸最多 12 个 | 骨骼表情在 MMD 里鼓包：Fiona 恢复完整权重后，あ２ 偏 7.8 mm，ぺろっ 5.2 mm，あ 4.7 mm | 「骨骼表情误差预估」先算；「自动」按阈值逐个选；顶点表情没有这个问题 |
| UE Viewer 导出时就把权重截成了 4 个 | 在 Blender 里烘焙的表情也带着鼓包 | 「恢复完整权重」（要游戏包 `.uasset.bin`）；分析时提示 |
| Faceit 只驱动 ARKit 形态键 | Blender 里用 Faceit 实时捕捉时，MMD 骨骼表情不参与 | 各管各的：Faceit 用 ARKit 键，MMD 用 PMX 里的表情 |

## 3. 原理

### 3.1 MetaHuman DNA

MetaHuman 的脸没有表情形态键，UE 运行时由 RigLogic 按 DNA 把约 270 个原始控制量换算成约 600 根 `FACIAL_*` 关节的动作。
DNA 格式、求值公式和 Fiona 的数据量见 [docs/metahuman-dna.md](../../../docs/metahuman-dna.md)。插件的做法：

1. DNA 关节和模型骨骼配对：同名 → 忽略大小写 → 转换加的 `unused_` 前缀 → XPS / MMD 改的名字（眼球、下巴）→
   还没配上的，看相似变换拟合后的位置，1 mm 内有一根面部骨骼就配它。Fiona：620/620，平均误差 0.38 mm。
2. 每个表情是一组原始控制量（配方），**整组一起**送进 RigLogic：PSD 组合修正（例如同时张嘴和笑）自然算进去；
   ARKit 形态键是线性叠加的，做不到这一点。
3. 每根关节的世界增量施加到对应骨骼的静止矩阵上，换算成 `matrix_basis`（与 Blender 骨骼轴向无关）。
   这就是骨骼表情的位移 + 旋转；烘焙成形态键时摆上这个姿势求值网格。
4. ARKit 的 mouthClose 是「张着下巴时把嘴唇合上」，量的是（jawOpen + 合唇）减去 jawOpen。
5. DNA 的缩放输出也算进去了（另外两份 DNA 代码丢掉了缩放）：
   - Fiona 只有两根瞳孔关节会缩放：`eyePupilNarrow` 为 1 时缩到 0.3 倍，`eyePupilWide` 为 1 时放大到 2.1 倍；
   - `瞳小` = `eyePupilNarrow` 0.6，眼球上 401 个顶点跟着缩；
   - PMX 骨骼表情不能缩放，所以 `瞳小` 只能做成顶点表情。骨骼方式会跳过它并说明原因，「自动」直接选顶点。
   - 查过的调研统计：483 支 MMD 动作里有 19.9% 用到 `瞳小`。

### 3.1b 左右：ウィンク 闭哪只眼

插件和仓库里其他表情工具的约定一样：`ウィンク`、`ウィンク２` 闭**模型自己的左眼**（PMX 里 +X，也就是 `左腕` 那一侧），
`ウィンク右`、`ｳｨﾝｸ２右` 闭右眼；`～左`/`～右` 的单侧表情同理。

2026-09-27 读了本机 409 个带 `ウィンク` 的 PMX 核对：
- **和插件一致**：
  - 日本 / 东亚作者的模型都是这个约定：大人ミク（GANTZ / 素体）、fubuki（两个版本）、碧蓝航线 圣路易斯（恋活转换，
    组合表情指向 `KK Eyes_wink_left_op`）；
  - 我们自己导出的 121 个 ROE 模型也是（本来就用这个约定，不算独立证据）。
- **反的**：下载目录里西方转换作者的「18」系列（84 个角色、279 个文件）是镜像的，`ウィンク` 闭右眼。

MMD 的表情名来自日本的初代模型，舞蹈动作也是按它们做的，所以插件按前者。核对脚本在 session 草稿 `ek/wink_side.py`。

### 3.2 已有形态键

每个网格按配方加权求和：Σ 权重 ×（形态键 − 它的参考键）。ARKit 名字的各种写法都认（`eyeBlink_L`、`EyeBlinkLeft`、
`Eye_Blink_L` ……）。配方里以 `?` 开头的是可选键：模型有就用，没有就跳过（星刃的下牙单独有个 `TeethLowerDown`，
张嘴的配方要带上它）。

### 3.3 姿势库

- **记录**：摆好脸部骨骼，起名（用 MMD 名或 ARKit 名）→「记录」。存在骨架对象的自定义属性 `expression_kit_poses` 里（JSON），
  随 `.blend` 保存。
- **动作**：选一个动作。有姿势标记时，每个标记是一个姿势（用标记名）；没有标记时，整个动作的第一帧算一个姿势（用动作名）。
  直接读 F 曲线求值，不改当前帧。
- **中性姿势**：游戏的「无表情」不一定是绑定姿势。填了中性姿势名，其余姿势都减掉它。
- 名字和目标一样的姿势直接用；配方文件里也可以写 `"names": {"姿势A": 0.6, "姿势B": 0.4}` 混合。
  混合方式和 MMD 叠加骨骼表情一样：位移相加，旋转按权重缩放后相乘。

### 3.4 骨骼脸自动

移植自 `mmd_face_morphs`（在 ROE 头上标定）：
- 按角色找骨骼：upper_lid_L、chin、corner_R 等，三种拼写都认。`AC` 辅助骨跳过，挂在别处的算跟随骨。
- 每个表情写成几条 `(角色, pitch/roll/yaw/move, 量)`：
  - 距离以两眼间距为单位；
  - 正方向是转 1° 实测出来的，不靠猜骨骼朝向。
- ARKit 52 的骨骼脸配方是新写的：
  - 眼球转向用眼骨的 pitch / yaw，眨眼和眯眼用眼皮，下巴、嘴角、嘴唇各自移动；
  - Fiona 和 ROE 上各有 23 个带方向的形态键，方向用数值检查过，全部正确。

### 3.5 姿势 → 形态键（烘焙）

整副骨架先回到静止状态：约束静音、骨架以外的修改器关掉、已有形态键归零。然后逐个表情摆姿势，算出整个网格的新位置，
减去静止时的位置，存成形态键。结束后全部恢复原样。算的时候用的是网格上的**全部**权重，所以形态键就是骨骼脸真实做出来的样子。
Blender 里相连的骨骼不能平移，所以要平移的骨骼会先断开连接。

### 3.6 PMX 误差和「自动」

mmd_tools 导出 PMX 时，超过 4 个的权重只保留最大的 4 个，再重新归一化。插件在相同姿势下对这些顶点做两次线性蒙皮：
- 一次用全部权重；
- 一次只用前 4 个权重。

两者差得最大的那个值，就是这个表情做成骨骼表情时在 MMD 里的偏差。「自动」逐个表情比较：误差不超过阈值（默认 0.3 mm）
就做骨骼表情，超过就做顶点表情。

参考：Fiona 这张脸在 XPS 路线里只剩 4 个权重，误差全部小于 0.01 mm。恢复完整权重后，54 个表情全部超过 0.3 mm，
嘴部表情有 3–8 mm。

### 3.7 恢复完整权重（UE5）

UE Viewer 每个顶点只导出 4 个权重。插件直接从游戏包的字节里读出完整权重（UE5 zen 包，按特征查找，不需要 usmap），
再按顶点位置写回。只改写「当前权重正好是游戏权重截断后重新归一化」的顶点，手工改过的地方不动。

为了在转换过的模型上也能用，加了两点：
- **拆开的网格**：XPS 把眼球、牙、睫毛拆成了单独的网格，匹配时按这个网格自己的顶点来检查。
- **改了名的骨骼**：游戏骨名在模型里找不到时，看已配上的顶点上权重重叠最多的是哪根骨头：
  - Fiona 转换后：head → 頭，FACIAL_C_Jaw → head jaw，clavicle_out_l → unused_clavicle_out_l；
  - 结果：脸部补全 4835 个顶点，眉毛补全 7184 个。

### 3.8 写进 mmd_tools

- **骨骼表情**：`root.mmd_root.bone_morphs`，每项存骨骼名、位移和四元数（姿势空间）。
- **顶点表情**：形态键本身，再登记到 `vertex_morphs` 里（英文名、面板分类、顺序）。
  - 没登记的形态键在 PMX 里会排在最前面，所以 ARKit 键登记在 MMD 表情后面，归「其他」。
- 改完后重建「表情」显示枠，MMD 的表情面板读的是它。
- 改动前后会先解绑 morph slider，再重新建立。
- 每个网格和根对象上都记着本插件做过哪些（`expression_kit`）。「删除」只删这些，别人做的同名表情不动。

## 4. 脚本

```python
import sys; sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\blender_addons")
from expression_kit import api
obj = bpy.context.object                     # 模型的骨架、网格或 mmd_tools 根对象都行
api.analyze(obj, dna_path=DNA)
api.restore_weights(obj, r"...\SK_Fiona_Face01.uasset.bin")          # 可选
api.build(obj, "MMD", "DNA", output="VERTEX", dna_path=DNA)           # 或 "BONE" / "AUTO"
api.build(obj, "ARKIT", "DNA", dna_path=DNA)
api.register_faceit(obj)
api.export_pmx(obj, r"out\Fiona.pmx", include_arkit=False)
```

`build` 的其他参数：`categories=["EYE", "EYEBROW", "MOUTH", "OTHER"]`、`extras`（扩展表情）、
`strengths={"EYE": 1.2}`、`replace`、`threshold_mm`、`recipe_file`，以及姿势库用的 `action` / `use_markers` / `neutral`。
报告里有做了哪些、跳过哪些（带原因）、替换了哪些、每个表情的 PMX 误差。

对照图：

```powershell
blender -b <model.blend> --python tools\render_sheet.py -- <输出目录> --set MMD --hide hair
python tools\make_sheet.py <输出目录> sheet.jpg --cols 9
```

## 5. 验证记录（2026-09-27，Blender 3.6.15 + mmd_tools 1.0.2 UuuNyaa + Faceit 2.3.40）

- **Fiona_BaseBody.blend（UE 骨架）+ DNA**：
  - ARKit 52 个，和 `faceit_arkit` 的结果逐点对比，最大差 0.005 mm（只是零值阈值不同）；
  - MMD 顶点表情 54 个；每组不到 2 秒。
- **Fiona 转换后的 MMD 模型**（昨晚 v7 的 `_converted.blend`）：
  - 骨骼表情：v7 那 26 个和原来一致（偏差 ≤ 0.01 mm），现在一共 54 个；
  - 顶点表情：替换掉了同名的骨骼表情；
  - PMX 读回：不带 ARKit 是 54 个顶点表情、15 MB；带 ARKit 是 106 个、20 MB；
  - Faceit 注册 52/52，头骨认成 `頭`，端口 9001。
- **同一模型恢复完整权重**：
  - 5 个拆开的网格全部配上；
  - 误差预估：あ２ 7.84 mm、てへぺろ 5.34 mm、ぺろっ 5.16 mm、あ 4.71 mm；
  - 「自动」因此 54 个全选了顶点表情。
- **姿势库**：
  - 把 DNA 的まばたき姿势手工摆出来记录，再生成顶点表情，和直接用 DNA 做的只差 0.005 mm；
  - 带姿势标记的动作（あ、い）也能用。
- **星刃 Fiona mod（自带 49 个 ARKit 键）**：
  - MMD 顶点表情 49 个；まばたき 和 eyeBlinkLeft + eyeBlinkRight 的差在 0.003 mm 以内；
  - 跳过 9 个：没有 tongueOut，ARKit 的 browInnerUp 不分左右，ω 等没有 ARKit 配方。
- **ROE b14 PMX（骨骼脸）**：
  - 认出 28 个角色；58 个骨骼表情和 `mmd_face_morphs` 做的完全一致（差 2e-6）；
  - ARKit 48 个；
  - 顶点表情 58 个（替换掉骨骼表情）。
- **方向检查**：两张脸各 23 个带方向的 ARKit 形态键全部正确。
- **瞳小**：原始 blend 和转换后的模型上都做成了顶点表情（眼球 401 个顶点，最大 0.7 mm）；眼睛特写前后对比，瞳孔明显变小；
  骨骼方式跳过并说明原因，「自动」选了顶点，误差预估里单独列出。加上缩放以后，其余表情的输出和之前逐点一致。
- **表情名**：内置的 MMD 名字都在 VMD 的 15 字节以内。52 个 ARKit 名里有 10 个超长，它们只给 Faceit 用，所以不影响。
- **对照图**：渲染后逐张看过：
  - Fiona：MMD 54 个、ARKit 52 个；
  - 星刃：49 个；
  - ROE：ARKit 48 个。
- **界面**：窗口模式下面板正常显示，「分析模型」「骨骼表情误差预估」从面板运行正常；插件启用、停用各两次正常。

## 6. 限制与后续

- **DNA 只认 v2.1**（Vindictus 的就是这一版）。MetaHuman 5.6 以后的 DNA 是 v2.2+ 的分段格式，要新写读取。
  Epic 2026 年以 MIT 许可开源的 OpenRigLogic 可以作参考。
- **骨骼脸 → ARKit 是实验性的**：
  - 没有脸颊、鼻翼骨的脸做不出 cheekPuff、noseSneer，mouthClose 也没有配方，所以 ROE 是 48 个；
  - tongueOut 只动舌头，单独用时会从合着的嘴里穿出来。面捕时它总和 jawOpen 一起来，所以没有加张嘴。
- **顶点表情在中间值是直线插值**：半程时下巴、眼皮走的是弦，不是弧。
  - 估算：下巴转 18°、半径 10 cm 时，中点约差 1.2 mm；眼皮约 0.4 mm。
  - 调研里提到的「组合表情」可以兼顾：大骨骼（下巴、眼球）用骨骼表情，其余用顶点表情补差，打成一个组合表情。还没做。
- FF7 的游戏表情数据（`ff7_face_morphs` 的 JSON）还不能直接当来源。可以先导成动作，走姿势库。
- 调研建议的新输出和新输入（VRM 1.0 预设、VRChat 口型、ARKit 权重曲线导入、音频驱动等）见调研报告。

## 7. 和仓库里其他表情插件的关系

| 插件 / 脚本 | 做什么 | 这里的对应 |
|---|---|---|
| `faceit_arkit` | DNA → 52 个 ARKit + Faceit 注册 + 恢复权重 | 同一套代码移植过来，输出一致；恢复权重多了拆开的网格和改过名的骨骼 |
| `mmd_face_morphs` | ROE 骨骼脸 → 58 个 MMD 骨骼表情 | 同一套代码，输出一致；多了顶点表情和 ARKit |
| `ff7_face_morphs` | FF7 游戏表情姿势 → MMD 顶点表情 | 还没接进来（见 §6） |
| `scripts/vindictus/export_pmx.py` | DNA → 26 个 MMD 骨骼表情（整条 PMX 流水线的一步） | 同样的算法；这里多了顶点表情、自动模式和 28 个扩展表情 |

原来的插件都没有改动。要不要把它们合并到这一个插件里，由用户决定。
