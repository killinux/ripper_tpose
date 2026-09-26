# MetaHuman DNA（.dna）是什么、做什么用、原理

`.dna` 是 Epic 为 **MetaHuman** 设计的文件，存的是一张脸的**表情绑定**：脸上有哪些表情控制，每个控制会让哪些骨骼怎么动。

模型文件里只有网格、骨骼和蒙皮权重，也就是"脸长什么样、哪块皮肤跟哪根骨头走"；DNA 管的是"**脸怎么动**"。
没有 DNA，模型的面部骨骼都在，却不知道"眨眼"要动哪些骨骼、动多少。

仓库里用到它的地方：

- [Faceit ARKit 插件](faceit-arkit-guide.md)：用 DNA 算出 52 个 ARKit 表情，存成形态键，给 iPhone Face Cap 驱动；
- `scripts/vindictus/export_pmx.py`：用 DNA 算出 MMD 标准表情，做成 PMX 骨骼表情。

下文的数字都来自 Vindictus 的 Fiona（`SK_Fiona_Face01.dna`）。

---

## 1. 从哪来

- **MetaHuman Creator** 给每个角色生成一份 DNA。虚幻引擎运行时有个叫 **RigLogic** 的模块，每一帧读它来算表情；
  Maya 的 MetaHuman 插件也用它。
- **游戏里**：DNA 嵌在脸部模型包里。Fiona 的在 `SK_Fiona_Face01.uasset` 的 `DNAAsset` 里，和网格放在同一个包。
- **UE Viewer 不导出它**，所以导出的 blend / PSK 有骨骼却不会做表情。
- 提取：DNA 在包里是一段完整的二进制，以 `DNA\0\2\0\1` 开头（第 2 代、第 1 版，即 v2.1），以 `AND` 结尾，
  按这个特征就能切出来。

  ```
  python scripts\vindictus\extract_face_data.py --list          # 哪些脸带 DNA（Vindictus 目前只有 Fiona）
  python scripts\vindictus\extract_face_data.py --face Fiona    # -> E:\game_export\Vindictus\_meta\face\SK_Fiona_Face01.dna
  ```

## 2. 三层名字

| 层 | 例子 | 说明 |
|---|---|---|
| 面板控制器（GUI） | `CTRL_L_eye_blink.ty`、`CTRL_C_jaw.ty` | 动画师在面板上拖的滑杆，Fiona 有 174 个 |
| 表情控制量（raw） | `CTRL_expressions.eyeBlinkL`、`jawOpen`、`mouthCornerPullL` | 基本动作单元（类似 FACS 动作单元，和 ARKit 的 52 个表情是同一种思路），每个 0–1，Fiona 有 269 个 |
| 骨骼（joint） | `FACIAL_L_EyelidUpperA`、`FACIAL_C_Jaw` | 真正带动皮肤的骨骼，Fiona 有 647 根（面部 620 根） |

## 3. 文件里有什么

二进制、大端序。开头是签名，接着是一张段偏移表，后面依次是各段；字符串和数组都是"长度 + 内容"。

| 段 | 内容 | Fiona | 在文件里的位置 |
|---|---|---|---|
| 描述 | 名字、性别年龄、单位、坐标系、LOD 数、数据库版本 | 名字 "Archetype"，性别女，年龄 24；厘米和角度；x 右 / y 上 / z 前（Y 轴朝上）；4 级 LOD；MH.4 | 第 39 字节起 |
| 定义 | 面板控制器、表情控制量、骨骼名字；骨骼父子关系；**中性姿势**（静止时每根骨骼的位置和朝向）；网格名、修正形态名、皱纹贴图名；每级 LOD 用哪些骨骼 | 174 个控制器、269 个控制量、647 根骨骼；25 个网格名（LOD1/3/4/6 的头、牙、眼、睫毛……）；0 个修正形态；82 张皱纹贴图遮罩（如 `head_wm2_browsDown_L`） | 109 起 |
| 行为·控制 | 控制器 → 控制量的换算表；组合修正（PSD） | 259 条换算，545 个组合修正 | 54148 起 |
| 行为·骨骼 | 骨骼响应矩阵 | 124 组（117 组非空），3673 行，85 万个系数 | 70806 起，占到 3530472 —— **整个文件的 98%** |
| 行为·修正形态 / 皱纹贴图 | 控制量 → 修正形态键权重、皱纹贴图遮罩权重 | 修正形态 0 个，皱纹贴图 82 张 | 3530472 / 3530492 起 |
| 几何 | 网格顶点、修正形态键的顶点位移 | 空（游戏里剥掉了） | 3535608 起，文件共 3535615 字节 |

**LOD**：这份 DNA 的最高级对应 MetaHuman 的 **LOD1**（描述段里 maxLOD = 1），四级分别是 MetaHuman 的 LOD1 / 3 / 4 / 6，
用到的骨骼数依次是 617 / 301 / 84 / 41。MetaHuman 只有 LOD0 带几百个修正形态键，LOD1 起全靠骨骼，
所以 Fiona 在游戏里的表情就是纯骨骼驱动的，DNA 就是全部表情数据。骨骼矩阵每一组也按 LOD 分行，
例如某组在 LOD0 用 18 行、LOD1 用 6 行、更低的不用。

## 4. 原理：RigLogic 每一帧做的事

```
面板控制器(174) ──换算表──▶ 表情控制量(269) ──相乘──▶ 组合修正(545)
                                  │                          │
                                  └───────▶ 骨骼响应矩阵 ◀────┘
                                                 ▼
                       620 根面部骨骼的位移和旋转 → 蒙皮 → 皮肤变形
                       （完整版还有：修正形态键、皱纹贴图）
```

1. **面板控制器 → 表情控制量**：每条换算是一段直线（起点、终点、斜率、截距）。
   - `CTRL_L_eye_blink.ty` 往一边推，0→1 就是左眼闭上（`eyeBlinkL` 0→1）；往另一边推，0→−1 就是左眼睁大（`eyeWidenL` 0→1）。
   - `CTRL_C_jaw.ty` 0→1 就是张嘴（`jawOpen` 0→1）。
2. **表情控制量**：眨左眼、张嘴、左嘴角上提……每个取值 0 到 1。实时捕捉（Live Link Face）和我们的插件都是直接给这一层赋值。
3. **组合修正（PSD）**：把两到六个控制量相乘，钳在 0–1，得到一个修正量。Fiona 的 545 个里：两个相乘的 301 个、三个的 166 个、
   四个的 62 个、五个的 14 个、六个的 2 个。
   - 例：`jawOpen × mouthCornerPullL` = 张着嘴笑时的额外修正；`jawOpen × mouthCornerPullL × jawOpenExtreme` = 大张嘴笑。
   - 只做单个表情时，乘积里有 0，修正不起作用。
4. **骨骼响应矩阵**：每组一个矩阵，输入是若干控制量和修正量，输出是若干骨骼的属性增量（每根骨骼 9 个：平移 xyz、旋转 xyz、缩放 xyz）。
   **增量 = 矩阵 × 输入**，是**线性**的：控制量翻倍，骨骼动得也翻倍。实际数字：
   - 眨左眼（`eyeBlinkL` = 1）：67 根骨骼在动，上眼皮骨 `FACIAL_L_EyelidUpperA` 转了 (43.8°, −4.4°, −11.3°)；
   - 张嘴（`jawOpen` = 1）：470 根骨骼在动，最大位移 5 cm，最大转角 23.7°；
   - 左嘴角上提（`mouthCornerPullL` = 1）：352 根骨骼在动。
5. **最终姿势**：每根骨骼的局部位置 = 中性位置 + 位移增量；局部朝向 = 中性朝向 × 增量旋转（欧拉角按 Maya 的 xyz 顺序，
   R = Rz·Ry·Rx）；再按父子关系逐级相乘（正向运动学），得到每根骨骼在空间里的位置。骨骼带着蒙皮权重把皮肤拉成表情。
   完整版 MetaHuman 这一步还会按第 4 步同样的方式算出修正形态键和皱纹贴图的权重；Fiona 这份没有修正形态键，
   皱纹贴图属于游戏材质的效果，我们导出的材质没有用上。

整套可以概括成：**一小层非线性（换算表、相乘、钳位）+ 一大块线性（矩阵）**。所以计算很快，游戏里每帧都能算；
我们用纯 Python 算一个表情也只要几十毫秒。

## 5. 在我们流程里怎么用

**第 1 步：对位。** DNA 的中性骨架（厘米、Y 轴朝上）和模型骨架（Blender，Z 轴朝上，单位可能是厘米也可能是米）不在同一个空间。
按骨骼名字配对（Fiona 620 对），做一次相似变换拟合（缩放 + 旋转 + 平移）。Fiona 的平均误差 0.38 mm，
说明 DNA 的中性姿势就是这副骨架的静止姿势。

**第 2 步：求值。** 给出一组控制量（例：`mouthCornerPullL = 1`），按第 4 节算出每根骨骼的姿势，取"姿势 × 中性⁻¹"的增量，
换到模型空间，施加到对应的 Blender 骨骼上。

**第 3 步：存下来。**
- **Faceit ARKit 插件**：每个 ARKit 表情写成一组控制量（mouthSmileLeft = `mouthCornerPullL` 1.0 …，映射表见插件 README），
  把皮肤变形存成**形态键**，Faceit 和 Face Cap 驱动的就是它们。
- **PMX**（`export_pmx.py`）：每个 MMD 表情写成一组控制量，把骨骼姿势存成 PMX 的**骨骼表情**。

**代价**：形态键和 PMX 表情都是线性相加的，第 3 步的**组合修正**丢了（例：张着嘴笑时少了那一点修正）。
所有 ARKit 形态键方案都是这样，一般看不出来。

**另外一个坑**：DNA 只管骨骼怎么动，皮肤跟骨骼的关系（蒙皮权重）在网格里。UE Viewer 导出的网格每个顶点只留 4 个权重，
MetaHuman 的脸最多 12 个，用截断的权重做出来的表情会起包。插件的「恢复完整权重」从游戏包里补回来，见插件 README 2.4。

## 6. 自己读一份 DNA

插件里的 `dna.py` 只依赖 numpy，Blender 里外都能用：

```python
import sys
sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\blender_addons\faceit_arkit")
import dna        # 直接导入 dna.py（导入整个插件包会先 import bpy，Blender 外面用不了）

face = dna.DnaFace(open(r"E:\game_export\Vindictus\_meta\face\SK_Fiona_Face01.dna", "rb").read())
print(face.descriptor["name"], len(face.joints), "joints,", len(face.raw), "controls")
move, turn, _scale = face.deltas({"eyeBlinkL": 1.0})      # 每根骨骼的局部增量（厘米、度）
world = face.posed({"jawOpen": 0.5, "mouthCornerPullL": 1.0})   # 每根骨骼的世界矩阵（DNA 空间，厘米）
```

`dna.read()` 返回描述、定义、控制（换算表 + 组合修正）、骨骼矩阵四部分（字典 + numpy 数组）；
修正形态、皱纹贴图和几何这几段只记了位置，没有解析（Fiona 用不到）。

## 7. 相关工具

- Epic 在 GitHub 上开源了 **MetaHuman-DNA-Calibration**：官方的 DNA 读写库（C++ / Python），还能改中性姿势等；
- 虚幻引擎的 **RigLogic** 插件、Maya 的 **MetaHuman** 插件：用 DNA 实时驱动表情；
- 仓库里：`scripts/vindictus/metahuman_dna.py`（提取 + 读取 + 求值，另一个窗口写的）、
  `scripts/blender_addons/faceit_arkit/dna.py`（读取 + 求值，插件自带的一份）。自己写的解析只支持 v2.1，别的版本会报错。

## 8. 注意事项

- **版本**：只认 v2.1（开头 `DNA\0\2\0\1`）。
- **DNA 和网格要配套**：骨骼名字对不上（例如 XPS 转过一圈，`FACIAL_L_Eye` 被改名）就无法对位。要用游戏导出的原始模型。
- **名字不代表角色**：Fiona 这份描述段写的是 "Archetype"，但中性姿势和她的骨架误差只有 0.38 mm，确实是她自己的。
- **单位和轴向**：DNA 是厘米、度、Y 轴朝上；对位那一步会自动换算，模型是米还是厘米都可以。
