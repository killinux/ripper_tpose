# 蒙皮权重怎么做：业内方法、Blender 技巧和本仓库的做法

> 2026-09-27。起因：用户觉得 Blender 刷权重不顺手，问业内有什么更好的办法。
> 本文整理了三部分：业内常用的几类做法；Blender 里马上能用的插件、设置和快捷键；它们和本仓库导出管线的关系。
> Blender 的菜单名、中文译名、提示文字和快捷键，都是从本机装的 3.6.15、4.2、4.5、5.1 自带文件里核对的
> （`scripts/startup/bl_ui`、`keymap_data/blender_default.py`、`locale/zh_*/blender.mo`、RNA 描述）。
> 插件的版本和价格是 2026-09-27 查的。

## 0. 结论

- **业内很少从零一笔笔刷。** 常见流程是：
  1. 先自动生成，或者从身体传递过来；
  2. 再用填数值或脚本修关键部位；
  3. 笔刷只修最后一点；
  4. 弯折处再用辅助骨或别的蒙皮方式兜底。
- **Blender 的短板有三处：**
  - 自动权重（骨骼热度）对游戏模型经常失败或串权重；
  - 没有权重图层；
  - 填精确数值、只平滑过渡带这类操作藏得深。

  4.5 到 5.2 在权重绘制上只有小改动，升级解决不了这些问题。
- **最值得装的插件：**
  - Robust Weight Transfer（免费，3.6 能用）：衣服、配饰从身体取权重，取不准的地方自动平滑补齐；
  - Easy Weight（免费，Blender Studio 出品，要 4.2 以上）：日常刷权重的一组便利功能；
  - Voxel Heat Diffuse Skinning（30 美元）：替代 Blender 自带的自动权重，不会报"解算出错"。
- **对本仓库：** 导出的模型都带着游戏原本的权重，不需要从零刷。要处理的是四件事：
  - 衣服跟随新加的骨；
  - 接缝两边的权重统一；
  - 每点 4 根骨的上限；
  - 源模型没有的物理骨。

  这些都更适合写成脚本：可复现，参数有默认值、可调。见第 4 节。

## 1. Blender 刷权重为什么别扭

1. **自动权重对游戏模型容易出错。**
   - 原理：「使用自动权重」（With Automatic Weights）用的是骨骼热度算法（Baran 和 Popović，SIGGRAPH 2007）。每根骨当一个热源，热量沿网格表面扩散，扩散到哪里，那根骨的权重就到哪里。
   - 适用范围：它最适合一整块封闭、不自交的网格。游戏模型的衣服是层叠的，眼睛和睫毛是单独的块，发片是单面的，常见结果有两种：
     - 报错「骨骼热权重: 为一个或多个骨骼解算时出错」（Bone Heat Weighting: failed to find solution for one or more bones），有的部件完全没分到权重；
     - 串权重：裙子粘到另一条腿上，胸口两边互相拉扯，腋下被躯干和手臂一起拉。
   - 报错原文还提示"检查模型重叠点与缩放"。常见的处理是合并重叠顶点、应用缩放，或者临时把模型放大再算。
   - 小技巧：权重菜单里的「自动按骨骼指定」只重算**选中骨骼**的权重，可以只修一部分。
2. **没有权重图层。** 每根骨对应一个顶点组，改一处常常连带改坏别处，也没法先存一版、再试别的刷法。
3. **填精确数值不顺手。** 笔刷边缘有衰减，很难刷出准确的 0.25。要填准确的数，得用下面两种办法之一：
   - 切到编辑模式，在侧栏「条目 → 顶点权重」面板里改；
   - 选中顶点，在「物体数据属性 → 顶点组」面板里设好「权重」值，再点「指定」。
4. **平滑要先圈范围。** 权重菜单里的「光滑」作用于选中的点。想只平滑关节处的过渡带，得先开顶点遮罩、选好点、锁住不相关的组。
5. **升级也解决不了。** 近几个版本在权重绘制上的改动：

| 版本 | 权重绘制的改动 |
|---|---|
| 4.5 | 在权重、顶点绘制模式里改属性可以撤销 |
| 5.0 | 刷出来小于 0.0001 的权重自动归零；「零权重」显示默认改成「活动项」 |
| 5.1 | 没有改动 |
| 5.2 | 用球形衰减时，笔刷光标贴着表面画 |

## 2. 业内的几类办法

| 办法 | 一句话原理 | 代表工具 | 适合 |
|---|---|---|---|
| 体积自动绑定 | 把模型变成实心体，在体内算热扩散或测地距离 | Maya Geodesic Voxel；3ds Max Voxel / Heat Map；Blender 插件 Voxel Heat Diffuse Skinning；Houdini Bone Capture Biharmonic | 从零绑新角色 |
| 传递 + 补洞 | 只在可信的点复制身体权重，其余的点平滑地补出来 | Robust Weight Transfer | 衣服、配饰 |
| 权重图层 | 像 PS 图层，每层只管一个部位 | Maya 的 ngSkinTools；Houdini 的 Capture Layer Paint | 大量手工精修 |
| 选点填数值 | 关节处按环线填固定数值 | 3ds Max 的 Weight Tool；Maya 的 Component Editor | 游戏低模 |
| 平滑变形后烘焙 | 先用平滑变形器让弯折处变自然，再反算回普通权重 | Maya 的 Delta Mush + Bake Deformer；EA 的 Dem Bones | 追求平滑变形的角色 |
| 辅助骨、换蒙皮算法 | 不死抠权重：加扭转骨、校正骨，或者换成 SDEF、双四元数 | MMD 的腕捩 / 手捩和 SDEF；UE 的 Pose Driver | 手肘、膝盖、肩、手腕 |
| AI 自动绑骨 | 神经网络同时预测骨架和权重 | Mixamo、AccuRIG、UniRig、Tripo、Meshy | 裸身人形 |

### 2.1 体积自动绑定

- **原理：**
  1. 把模型体素化（或四面体化），变成一个实心的"雕像"；
  2. 在体内算每个体素到每根骨的热扩散或测地距离；
  3. 把结果读回表面顶点。

  因为是在体内算，衣服层叠、破面、部件分开都不影响。多个网格一起算时，接缝两边的权重也是连续的。
- **代表工具：**
  - **Maya**：Geodesic Voxel 绑定，Maya 2015 起内置。出自 Autodesk 的 Dionne 和 de Lasa 2013 年的论文（SCA 2013）。
  - **3ds Max**：Skin 修改器的 Voxel 和 Heat Map 两种求解器，2016 起内置，可以只算选中的顶点。
  - **Blender**：付费插件 Voxel Heat Diffuse Skinning（Mesh Online，30 美元）。4.1.0 版（2026-09-08）支持 Blender 3.6 到 5.2。思路是"体素化 + Blender 自带的热扩散"，号称从不报失败。
  - **Houdini**：Bone Capture Biharmonic，用双调和权重（思路同 Jacobson 等人 SIGGRAPH 2011 的有界双调和权重）。
- **缺点：** 只能给出一个不错的起点，关节处仍要手修。体素分辨率低时，贴得很近的两条腿、手指仍会串权重。

### 2.2 从身体传递 + 补洞（Robust Skin Weights Transfer）

这是 EA 的 Abdrashitov、Raichstat、Monsen、Hill 在 SIGGRAPH Asia 2023 发表的方法，专门解决"衣服从身体取权重"时最头疼的几处：两腿之间的裙子、胸口中间、腋下。

1. **只信可信的点。** 衣服上每个点找身体表面最近点。只有距离够近、法线夹角也够小时，才直接复制身体在那一点的权重。
2. **补洞。** 剩下的点不去硬找最近点。已匹配点的权重当作固定边界，在衣服网格上解一个平滑方程，让权重从四周平滑地"流"进来。
   - 参考代码解的是 `min wᵀ(−L + L·M⁻¹·L)w`：L 是余切拉普拉斯矩阵，M 是质量矩阵；
   - 也就是一阶平滑能量加二阶平滑能量。
3. **局部平滑（可选）。** 参考代码对补出来的点和它们附近的点再平滑 10 次，系数 0.2。

**Blender 插件 Robust Weight Transfer**

- **基本信息：** 作者 SentFromSpaceVR，免费，GPL-3 许可，1.1.9 版。`bl_info` 写的最低版本是 Blender 3.1，所以 3.6 能用。
- **位置：** 3D 视图侧栏的 SENT 标签。
- **依赖：** 要 scipy、libigl 2.5.1、robust-laplacian 三个包。插件自带安装按钮，会用 pip 下载，需要联网。
- **默认参数：** 最大距离 0.05、法线夹角 30°、每点最多 4 根骨。
- **比论文多做的两处：**
  - 允许法线翻转（默认开）：衣服法线朝里、和身体法线正好相反时也算匹配；
  - 补洞多了 Point 模式（默认）：用点云拉普拉斯来算，能跨过断开的部件。另一种 Surface 模式直接在网格上算。
- **可以限定范围：** 用顶点组指定"哪些点参与传递""哪些点需要补洞"。
- **Blender 5.2 以后：** 有人另做了分支 protoco-jp/robust-weight-transfer。

**和 Blender 自带的传递有什么不同：** 自带的是权重菜单里的「传递权重」和「数据传递」修改器，默认每个点都取最近点。虽然能设最大距离，但超出距离的点只是不传，不会平滑补齐。所以两腿之间的裙子会一半取左腿、一半取右腿，一走路就撕开。

### 2.3 权重图层

- **原理：** 像 PS 图层。每层只管一个部位（比如手臂、手指、裙摆），带遮罩和透明度，最终结果是各层叠加。改一层不会碰到别的层，任意姿势下都能镜像。
- **代表工具：**
  - Maya 的 ngSkinTools：技术已被 Autodesk 收购，现在免费下载；
  - Houdini 的 Capture Layer Paint。
- **Blender：** 没有现成的。只能用多个顶点组加「顶点权重混合」修改器（Vertex Weight Mix）拼出来，很麻烦。

### 2.4 选点填数值

- **原理：** 游戏低模关节处的边线很少，与其刷，不如按环线直接填数：
  - 关节中心那一圈填 0.5；
  - 往两边依次填 0.75 和 0.25；
  - 再往外填 1 和 0。

  结果干净、左右对称、可复现。
- **代表工具：**
  - 3ds Max Skin 的 Weight Tool：有一排 0、0.1、0.25、0.5、0.75、0.9、1 的按钮，配合 Loop、Ring 按钮一次选一整圈顶点；
  - Maya 的 Component Editor：在表格里直接改数。
- **Blender 的对应做法：**
  - 权重绘制模式里开顶点遮罩，只改选中的点；
  - 「权重 → 设置权重」（Set Weight）：用当前笔刷的权重值填充活动顶点组（开遮罩时只填选中的点）；
  - 编辑模式侧栏「条目 → 顶点权重」面板：直接改当前顶点每根骨的数值；点面板里的「复制」，把当前顶点的权重复制到所有选中的点。

### 2.5 平滑变形后，再烘焙回权重

- **Delta Mush 是什么：** Rhythm & Hues 2014 年提出的一种变形器。它先把变形后的网格平滑一遍，再把原来的细节加回去。所以即使底下的权重很粗糙，弯折处也很圆顺。
- **怎么烘焙：** Delta Mush 本身导不出去。于是摆若干个姿势，用最小二乘反算出一组普通的线性权重，让普通蒙皮尽量复现 Delta Mush 的效果。
- **代表工具：**
  - Maya：Delta Mush 变形器 + Bake Deformer 工具；
  - EA 开源的 Dem Bones（BSD-3 许可）：从一段网格动画（比如布料模拟、形态键）反算骨骼和权重，基于 Le 和 Deng 的 SSDR 方法（SIGGRAPH Asia 2012）；
  - EA 的 Direct Delta Mush（Le 和 Lewis，SIGGRAPH 2019）。
- **Blender：** 「矫正平滑」修改器（Corrective Smooth）相当于 Delta Mush，但没有"烘焙回权重"的按钮。要用得自己写脚本（摆姿势 + 最小二乘）。

### 2.6 辅助骨和更好的蒙皮算法

很多"权重怎么刷都不好看"的地方，其实是普通线性蒙皮（LBS）本身的毛病：手腕一拧就像糖纸一样变细，手肘一弯就塌。业内的做法是不死抠权重，改用下面这些办法：

- **扭转骨：** 把前臂的扭转分给几根骨。MMD 的腕捩、手捩就是这个。PMXEditor 的"準標準ボーン"插件会自动加骨并分配权重。
- **校正骨：** UE 的 Pose Driver 按当前姿势（RBF 插值）驱动几根校正骨，把手肘、肩膀撑回来。
- **换蒙皮算法：**
  - 双四元数（DQS，Kavan 等人 2007）：Blender 骨架修改器的「维持体积」（Preserve Volume）就是它；
  - SDEF：MMD 自己的球面变形，只对受两根骨影响的顶点起作用，手肘、膝盖更圆。
- **校正形态键：** 按关节角度驱动形态键。PMX 做不到按角度驱动。

**导出格式能带走什么：**

| | Blender | PMX（MMD） | XPS |
|---|---|---|---|
| 普通线性蒙皮 | 有 | 有（BDEF1 / 2 / 4，每点最多 4 根） | 有（每点 4 根） |
| SDEF | mmd_tools 的 SDEF 驱动 | 有 | 没有 |
| 双四元数（维持体积） | 有 | 没有（PMX 2.1 虽有 QDEF，MMD 不支持） | 没有 |
| 矫正平滑 / Delta Mush | 有 | 没有 | 没有 |
| 扭转骨、辅助骨 | 有（约束） | 有（付与、捩骨） | 只有骨骼本身，不会自动跟随 |

所以只在 Blender 里看着好的东西（维持体积、矫正平滑），导出 PMX、XPS 后会消失。

### 2.7 AI 自动绑骨

- **原理：** 用大量绑好的模型训练神经网络。输入网格，输出骨架和每个顶点的权重。
- **代表：**
  - Mixamo：Adobe 的在线服务，只支持人形；
  - AccuRIG：Reallusion 出的免费桌面软件；
  - UniRig：清华大学和 Tripo 发表于 SIGGRAPH 2025，开源，可以本地跑；
  - Tripo、Meshy：在线自动绑骨服务。
- **现状：** 裸身人形可以当起点。衣服、头发、配饰效果差。
- **注意：** 在线服务要上传模型。本仓库的模型都是从游戏里提取的，不要上传。

## 3. 在 Blender 里怎么刷得顺手

本机装了 3.6 到 5.1 多个版本，导出管线用的是 3.6.15。mmd_tools 装在 3.6、4.5、5.0 里，5.1 没装。

注意：用新版本保存的 .blend 回到 3.6 打开可能丢数据，因为 Blender 不保证旧版本能读新文件。在新版本里刷权重时，另存一份再做。

### 3.1 插件

| 插件 | 作者 | 价格 | 支持版本 | 用途 |
|---|---|---|---|---|
| Robust Weight Transfer | SentFromSpaceVR | 免费（GPL-3） | 3.1 起（3.6 可用） | 衣服、配饰从身体取权重 + 补洞（见 2.2） |
| Easy Weight | Blender Studio | 免费 | 扩展平台，4.2 起 | 日常刷权重的便利功能 |
| Voxel Heat Diffuse Skinning | Mesh Online | 30 美元 | 3.6–5.2 | 替代自带的自动权重（见 2.1） |

Easy Weight 在「偏好设置 → 获取扩展」里直接搜就能装，主要功能：

- 进权重模式时不用先显示、选中骨架，插件会处理；
- 每刷一笔，自动清掉权重为 0 的项；
- 用镜像修改器时，自动补齐对侧的顶点组；
- 可以强制一直开着「零权重」显示、「自动规格化」、「多次绘制」；
- 提供几个按钮：只看形变骨（Focus Deforming Bones）、规格化形变组（Normalize Deform Groups）、平滑顶点权重（Smooth Vertex Weights）。

### 3.2 自带但常被忽略的功能

以中文界面为准，括号里是英文名。3.6 和 5.1 的译名基本一样，不一样的地方单独注明了。

| 功能 | 在哪 | 作用 |
|---|---|---|
| 自动规格化（Auto Normalize） | 权重绘制模式 → 工具设置 → 选项 | 刷一根骨时，其它骨自动让出份额，每个点的形变骨权重总和保持 1。**建议一直开着**。5.1 里顶点组面板也有这个勾选 |
| 锁定相对（Lock-Relative） | 同上 | 显示时把锁住的形变组当作不存在，剩下的组重新按总和 1 显示 |
| 多次绘制（Multi-Paint） | 同上 | 同时选中多根骨时，把它们当成一个整体来刷，并保持它们之间的比例 |
| 顶点组的锁 | 顶点组列表每行的锁图标；权重菜单 → 锁定；K 键饼菜单 | 锁住的组刷不动；自动规格化时别的骨让份额，也不会从锁住的组里扣 |
| 遮罩 | 3.6：M 键面遮罩、V 键顶点遮罩；4.2 起：1 键面遮罩、2 键顶点遮罩、3 键骨骼选区 | 只改选中的面或点 |
| 零权重（Zero Weights） | 视图叠加层 → 权重绘制 | 设成「活动项」后，当前组没有权重的点显示成黑色，能看清刷到了哪里 |
| 显示权重轮廓线（Show Weight Contours） | 同上 | 画出等权重线，能看出过渡带宽不宽、匀不匀 |
| 衰减形状（Falloff Shape）：投射 / 球形 | 笔刷设置 → 衰减 | 「投射」按屏幕投影刷。再关掉「仅前面的面」（Front Faces Only），能一笔刷透到背面 |
| 权重菜单 | 权重绘制模式顶部的「权重」 | 常用的：全部规格化；清理（3.6 译作「清空」，去掉很小的权重）；总限值（每点最多几根骨，默认 4）；光滑；层级（给当前组的权重加一个偏移、乘一个增益）；数值化；镜像；传递权重；设置权重。5.1 的菜单里还有采样权重、采样组、渐变（线性 / 径向） |
| 顶点权重面板 | 编辑模式，侧栏「条目」→「顶点权重」 | 直接改当前顶点每根骨的数值。「复制」把它的权重复制到所有选中的点 |
| 顶点组面板 | 物体数据属性 → 顶点组 | 设好下面的「权重」值，选中顶点后点「指定」 |
| 修改器 | 修改器属性 | 数据传递（Data Transfer，自带的权重传递）；顶点权重邻近（Vertex Weight Proximity，按到某个物体的距离生成权重）；矫正平滑（Corrective Smooth，即 Delta Mush）；骨架修改器的「维持体积」（即双四元数） |

### 3.3 快捷键：3.6 和 4.2 以后不一样

默认键位，左键选择：

| 操作 | 3.6 | 4.2、4.5、5.1 |
|---|---|---|
| 刷 | 左键 | 左键 |
| 反向刷（减权重） | 没有默认快捷键，在笔刷设置里改混合模式 | Ctrl + 左键 |
| 平滑 | 切到「模糊」工具 | Shift + 左键（临时切成平滑） |
| 吸取权重 | Ctrl + 右键 | Shift + X |
| 吸取顶点组（从鼠标下的组里挑一个设为当前） | Shift + 右键 | Ctrl + Shift + X |
| 线性渐变 | Alt + 左键拖 | Shift + A |
| 径向渐变 | Ctrl + Alt + 左键拖 | Shift + Alt + A |
| 设置权重（填充当前组） | Shift + K | Ctrl + X |
| 调笔刷权重值 | Ctrl + F | Ctrl + F |
| 锁定饼菜单 | K | K |
| 在权重模式里选骨 | Ctrl + 左键 | Alt + 左键 |
| 面遮罩 / 顶点遮罩 | M / V | 1 / 2（3 = 骨骼选区） |

### 3.4 推荐流程

1. **进模式：** 物体模式下先选骨架，再 Shift 选网格（网格是活动物体），然后切到「权重绘制」模式。这样在权重模式里可以直接选骨、转骨。装了 Easy Weight 就不用这一步。
2. **打开这些：**
   - 自动规格化；
   - 叠加层里「零权重」设成「活动项」；
   - 打开「显示权重轮廓线」。
3. **先打底，不要从零刷：**
   - 衣服、配饰：用 Robust Weight Transfer 从身体取；
   - 新角色：用 Voxel Heat Diffuse Skinning 或自带的自动权重；
   - 游戏导出的模型：直接用原权重。
4. **边摆姿势边修：** 选一根骨（3.6 用 Ctrl + 左键，4.2 起用 Alt + 左键），按 R 转到极端角度，在弯折状态下修。极端角度比如手肘弯 120°、手臂抬过头、两腿劈开。这是业内的标准做法。
5. **修的顺序：**
   1. 锁住不相关的组；
   2. 关节处开顶点遮罩，按环线填数；
   3. 最后用平滑把过渡带抹匀。
6. **收尾：**
   1. 「总限值」限到 4 根；
   2. 「全部规格化」；
   3. 「清理」掉很小的权重；
   4. 再摆几个姿势检查一遍。

## 4. 和本仓库导出管线的关系

### 4.1 起点是游戏原权重

本仓库导出的模型都带着游戏原本的权重。这是最好的起点，**不要重新自动绑定**。例如：

- ROE 每个顶点最多 4 根骨，游戏数据本来就是 4 根（见 `docs/roe-hq-materials.md`）；
- Vindictus 的 MetaHuman 脸原本每点最多 12 根骨，UE Viewer 导出时只留 4 根，表情会坑坑洼洼。`faceit_arkit` 和 `expression_kit` 里的 `ue_weights.py` 会从游戏包里把完整权重恢复回来。

导出格式的限制：

- **mmd_tools 导出 PMX：** 超过 4 根骨时只留权重最大的 4 根，再重新归一化。SDEF 只写给恰好受两根骨影响、带 SDEF 数据的顶点。见 mmd_tools 的 `core/pmx/exporter.py`。
- **XPS：** 每点只存 4 根。

### 4.2 已有的权重代码

| 位置 | 做什么 | 属于第 2 节哪一类 |
|---|---|---|
| `scripts/riseoferos/export_character_model_blender.py` 的 `follow_breast_skin` | 离皮肤 2 cm 以内的衣服点，改成皮肤在最近点上"躯干 / 胸"的权重分配（在皮肤三角形上插值）。衣服链上的份额保留，最多留 4 根 | 传递，但只有第一步 |
| 同上 `relax_shoulder_weights` | 烘焙 A 字姿势前，平滑肩、上臂、前臂的组。系数 0.35、4 次，比 Convert_to_MMD5 默认的 0.5、8 次轻 | 平滑 |
| 同上 `restore_stray_weight_transfers` | Convert_to_MMD5 退役骨骼时，按几何位置把权重分给别的骨，偶尔会分给从来不带皮肤的骨（比如护肘）。这里把那些点的原权重还回去 | 保护原权重 |
| 同上 `skin_rotation_share` | 算一根辅助骨该跟随关节转动多少 | 辅助骨 |
| `scripts/vindictus/export_pmx.py` 的 `boost_bust_weights` | 把胸骨的峰值权重拉到目标值。增益随权重的平方变化，边缘几乎不变；多出来的份额从同一点的其它骨里按比例扣 | 数值调整 |
| `scripts/vindictus/fix_basebody_neck.py` 的 `blend_in_weights` | 接缝处按系数 t 把原权重混向目标权重。试过限成 4 根：XPS 里一样，Blender 里更差，所以默认不限 | 接缝 |
| `scripts/blender_addons/faceit_arkit/ue_weights.py`、`scripts/blender_addons/expression_kit/ue_weights.py` | 从 UE 包里恢复完整权重（最多 12 根） | 保护原权重 |
| `scripts/blender_addons/expression_kit/bake.py` 的 `WeightModel` | 在当前姿势下，量"全部权重"和"只留 4 根"两种蒙皮的最大位置差 | 检查 4 骨上限的误差 |

### 4.3 可以改进的地方

1. **`follow_breast_skin` 的 2 cm 边界。** 现在 2 cm 以内整段替换，2 cm 以外完全不动，中间没有过渡，边界上可能出现权重突变。补上 2.2 的"补洞"这一步，或者至少按距离渐变，就能平滑过渡。距离和过渡宽度做成参数，有默认值、可调。
2. **接缝统一。** 头和身体之间、衣服拼接处，位置重合的顶点必须权重完全相同，否则一摆姿势就裂开。可以写成通用脚本：找出位置重合的顶点（容差比如 0.01 mm），权重取平均后写回。
3. **4 骨上限。** 现在靠 mmd_tools 导出时直接截断。可以改成导出前自己截断，只对变化大的点做局部平滑，再用 `WeightModel` 在几个弯曲姿势下量一下误差。
4. **源模型没有的物理骨。** ROE 的胸、裙、头发骨都来自游戏，带原权重，直接用。只有源模型没有这些骨时，才需要生成权重。办法有两种：
   - 按 2.2 的方法从模板身体取；
   - 按到骨段的距离和沿链的位置，用脚本算。

这些可以放进之前记下的"胸部物理插件"讨论里，做成一组权重按钮。

## 5. 名词对照

| 名词 | 意思 |
|---|---|
| 线性蒙皮（LBS） | 每个顶点的位置 = 各骨变换按权重加权平均。PMX 的 BDEF1 / 2 / 4、XPS、游戏引擎都用它 |
| BDEF1 / 2 / 4 | PMX 里每个顶点受 1 / 2 / 4 根骨影响 |
| SDEF | MMD 的球面变形，只用于受两根骨影响的顶点，手肘、膝盖不塌 |
| 双四元数（DQS） | 用对偶四元数混合骨骼变换，拧手腕时不变细。Blender 里叫「维持体积」 |
| 骨骼热度（Bone Heat） | Blender 自动权重用的算法，热量沿表面扩散 |
| 测地体素（Geodesic Voxel） | 在体素化的实心体内算测地距离，Maya 的自动绑定 |
| 有界双调和权重（BBW） | 解双调和方程得到的平滑权重 |
| 补洞（Inpainting） | 已知一部分点的权重，平滑地推出其余点 |
| Delta Mush / 矫正平滑 | 变形后先平滑、再加回细节的变形器 |
| 蒙皮分解（SSDR） | 从一组示例网格反算骨骼和权重，Dem Bones 用的方法 |

## 6. 参考

- Robust Weight Transfer 插件：<https://github.com/sentfromspacevr/robust-weight-transfer>
  （参数说明 <https://deepwiki.com/sentfromspacevr/robust-weight-transfer/3-user-guide>，
  5.2 以后的分支 <https://github.com/protoco-jp/robust-weight-transfer>）
- 论文参考代码：<https://github.com/rin-23/RobustSkinWeightsTransferCode>；
  论文主页：<https://www.dgp.toronto.edu/~rinat/projects/RobustSkinWeightsTransfer/index.html>
- Easy Weight：<https://extensions.blender.org/add-ons/easyweight/>、<https://studio.blender.org/tools/addons/easy_weight>
- Voxel Heat Diffuse Skinning：<https://superhivemarket.com/products/voxel-heat-diffuse-skinning>、<https://www.mesh-online.net/voxel.html>
- Maya Geodesic Voxel：<https://help.autodesk.com/view/MAYAUL/2023/ENU/?guid=GUID-E9FC4C94-CDEB-41DC-AF8E-95469EC69BEE>；
  论文：<https://diglib.eg.org/items/3d3458d9-bdf2-41c7-8b84-5da16b5cd637>
- 3ds Max Voxel / Heat Map：<https://help.autodesk.com/cloudhelp/2016/ENU/3DSMax/files/GUID-B94BF35E-4AC5-4C46-B61B-566BB80BAA60.htm>
- ngSkinTools：<https://www.ngskintools.com/>
- Dem Bones：<https://github.com/electronicarts/dem-bones>、<https://www.ea.com/seed/news/open-source-dem-bones>
- UniRig：<https://github.com/VAST-AI-Research/UniRig>
- Blender 各版本权重绘制改动：
  [4.5](https://developer.blender.org/docs/release_notes/4.5/sculpt/) ·
  [5.0](https://developer.blender.org/docs/release_notes/5.0/sculpt/) ·
  [5.1](https://developer.blender.org/docs/release_notes/5.1/sculpt/) ·
  [5.2](https://developer.blender.org/docs/release_notes/5.2/sculpt/)
