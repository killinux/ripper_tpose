# Vindictus Fiona：XPS → PMX 的两种做法（对比，待合并）

2026-09-26，同一个输入 `E:\game_export\Vindictus\Fiona\xps\Fiona_BaseBody\Fiona_BaseBody.xps`，
两个 Claude 窗口各做了一版带物理的 PMX，**都还没提交**。本文逐项对比两种做法和实测结果，给下次合并用。

- 所有数字都在 Blender 3.6.15 里测的，**两版都还没在 MMD 里打开过**。
- 物理一律按 MMD 单位导入测（缩放 1.0），原因见第 5 节。

## 1. 两种做法

| | A：插件窗口 | B：本仓库窗口 |
|---|---|---|
| 会话 | Convert to MMD 5 的项目会话（`E:\code\othercode\Convert_to_MMD5`） | ripper_tpose（Vindictus 这条线） |
| 思路 | 改进插件本身，做成任何 XPS 都能用的按钮；参数照 11 个参考 PMX（「18」系列）实测 | 给 Vindictus 写专用脚本，重点是表情，以及保住发型、胸型 |
| 代码 | `skeleton_identifier.py`（XPS 标准骨名优先）<br>新增 `convert/breast.py`、`convert/hair.py`<br>`ui.py` 加按钮<br>插件仓库里未提交；已经装进你的 Blender（面板 build 号 `2026-09-26 xps-names+breast+hair`） | `scripts/vindictus/metahuman_dna.py`（取出并计算脸的 DNA）<br>`scripts/vindictus/export_pmx.py`（整条流程）<br>复用 ROE worker（`add_both_eyes_bone`、`release_rest_overlaps`、`verify_grant_order`）和 `mmd_cloth_physics` |
| 怎么跑 | Blender 界面里依次点：一键转换 → 身体碰撞刚体 → 胸部物理 → 头发物理 | 命令行：`metahuman_dna.py extract`，再 `blender -b --python export_pmx.py -- --xps … --dna … --out …` |
| 输出 | `E:\game_export\Vindictus\Fiona\pmx\Fiona_BaseBody\`<br>`Fiona_BaseBody.pmx`（22:07）、`_nohair.pmx`、`_nophysics.pmx`、`_mmd.blend` | 临时目录 `…\scratchpad\pmx\v7\Fiona_BaseBody\`<br>`Fiona_BaseBody.pmx`、`_converted.blend`、`.pmx.report.json`；预览在 `…\scratchpad\pmx\final_preview\` |
| 设计记录 | 插件仓库 `docs/skirt_physics_design.md` 的 v7 头发一节（未提交）、`docs/使用说明.md` | `scripts/vindictus/README.md`「导出 PMX」、本文 |

## 2. 结果一览（同一套测试）

| 项目 | A：插件 | B：本仓库 |
|---|---|---|
| 頭 / 目 / 下半身 | 自动识别直接对 | 自动识别后改 4 行槽位 |
| 骨架结果 | 頭 = `head neck upper`（父级 首1）；左目 挂在 `FACIAL_C_FacialRoot` 下；臀部权重在 下半身（3955 个顶点，权重和 1923） | 同左；下半身 4093 个顶点，权重和 1925 |
| PMX 骨数 | 1064 | 1063 |
| 表情 | 0 | 26 个骨骼表情，「表情」显示框里 26 项 |
| 両目 | 没有 | 有 |
| 付与计算顺序 | 0 处违规 | 0 处违规 |
| 胸部骨 | 新建 `左胸` / `右胸`（挂在 上半身3 下）；每侧约 2950 个顶点、权重和约 1428；原来 `bust_2` 的权重被分走（和只剩 82） | 沿用游戏的 `Bip001_*_bust_1/2`；`bust_2` 权重放大到最高 0.75，每侧约 2150 个顶点、权重和约 836 |
| 胸部刚体 | 每侧一个动态球：半径 5.1 cm（0.64 单位），模式 1；关节 ±10°，无弹簧；组 15 | 每侧一个静态球（`bust_1`，半径 2.4 cm）加一个动态球（`bust_2`，半径 3.7 cm，模式 1）；关节 ±10°，弹簧 450；组 15 |
| 头发刚体 | 254 个，全部动态；胶囊，质量 1，阻尼 0.9 / 0.99，组 9 / 10；关节 ±10°，无弹簧 | 244 个：139 个跟随头骨（模式 0）、99 个动态（模式 1）、6 个物理 + 骨位置（模式 2）；盒子，阻尼 0.95 / 0.99，组 10 / 11；关节 5～8°，弹簧（PMX 里是 1～5） |
| 刚体 / 关节总数 | 272 / 256 | 264 / 246 |
| 站立 150 帧：头发发梢位移 | 中位数 3.0 cm，90% 9.1 cm，最大 22.7 cm；右侧 d 组发束往前下滑，右眼前垂下一缕 | 中位数 1.1 cm，90% 3.2 cm，最大 5.2 cm；发型不变 |
| 站立 150 帧：胸部偏转 | 10.0°（压在限位上） | 6.4° |
| 摇晃舞 480 帧：胸部偏转 | 中位数 21～25°，最大 37～58°；96% 的帧 ≥ 9.5° | 中位数 12～14°，最大 18～22°；86% 的帧 ≥ 9.5° |

- 摇晃舞指「来杯好茶摇一摇」，用它的 `适配【原神】芙宁娜.vmd`。
- 这支舞里，两版在 Blender 中都会冲破 ±10° 限位：约束没压住，而且冲破后不会撞到限位就停。数值只适合互相比较，MMD 的 Bullet 表现会不同。
- A 自己的测试是左右摇头 ±40°、点头 ±25°：Fiona 每节头发偏离的 95% 分位是 25.2°，最大 36.2°，骨头漂移 3.3 mm。参考 PMX 在同样测试下，95% 分位是 19～49°。
- 头发对比图：`…\scratchpad\pmx\final_preview\hair_compare.jpg`。上两排是 A，下两排是 B；分别是静止时和站立 150 帧后，从前、后、右、左四个方向看。

## 3. 逐项说明

### 3.1 转换

**A**：`skeleton_identifier._prefer_xps_standard_names()` 在拓扑识别之后，让带 XNALara 标准名的骨头优先占角色。
- 名字表来自 `presets/xna_lara.json`。
- 只有和另一根标准名骨在同一条父子链上时才算数，孤立的 `root ground` 这种不算。
- 在这个 XPS 上的自动结果：
  - 全ての親 = `root ground`；
  - センター = `root hips`（没有权重）；
  - 上半身 = `spine lower`，首 = `head neck lower`；
  - 頭 = `head neck upper`；
  - 目 = `head eyeball left / right`；
  - 下半身 留空，由插件新建，转移步骤把 `Bip001_Pelvis` 的权重交给它（导出后 `Bip001_Pelvis` 权重为 0）。

**B**：`export_pmx.py` 的 `SLOT_FIX`，在自动识别之后改 4 行，和教程 6.10 的手工步骤一样：
- センター 清空；
- 下半身 = `Bip001_Pelvis`；
- 頭 = `head neck upper`；
- 目 = `head eyeball left / right`。

然后一键转换时关掉自动识别。

**结论**：两边得到的骨架等价。A 更通用，不用手改。B 的 `SLOT_FIX` 只对旧版插件有用，教程 6.10 已补注。

### 3.2 表情和 両目（只有 B 有）

**原理**：
- Fiona 的脸是 MetaHuman：约 630 根 `FACIAL_*` 骨，由 269 个原始控制（`CTRL_expressions.*`）经 RigLogic 驱动。
- 驱动数据（DNA v2.1）嵌在 `SK_Fiona_Face01.uasset` 的 `DNAAsset` 里，UE Viewer 不导出。

**B 的做法**：
1. `metahuman_dna.py` 从 IoStore 容器里切出 DNA，并按 RigLogic 的方式求值：
   - 原始控制 → PSD（带权输入相乘，限制在 0～1）；
   - → 关节增量（每组一个稠密矩阵，LOD 0）；
   - → 正向运动学。
2. 把 DNA 的中性骨架拟合到模型骨架上：620 根骨，平均误差 0.38 mm。
3. 每个 MMD 表情按配方求出每根骨从静止到摆好的变化，写成骨骼表情：
   - 配方沿用星刃那套 ARKit 配方，换成 MetaHuman 的控制名，见 `export_pmx.py` 的 `RECIPES`；
   - 在模型自己的关节位置上施加变化；
   - 换算成相对于父骨的 `matrix_basis`。
4. 両目 用 ROE worker 的 `add_both_eyes_bone`：付与率 1，两只眼放到变形阶层 1。

**验证**：
- 转换后的 `.blend` 里逐个渲染，都正确；「にやり」在 1.0 时脸颊鼓包，降到 0.8。
- PMX 重新导入后，用 mmd_tools 的表情滑块驱动，结果一致。

**合并时**：这一步和插件无关，可以接在 A 的转换后面跑。需要的骨名：`FACIAL_*`、`左目` / `右目`、`head jaw`，映射在 `XPS_NAMES` / `MMD_NAMES`。

### 3.3 胸部

**A（`convert/breast.py`）**：按参考 PMX 的规律，数值都按身高 H 归一。
- 骨：每侧新建一根，骨头在乳尖正后方 0.058H，骨尾在乳尖。
- 权重：按到乳尖距离的高斯 `exp(-(d/0.052H)²)` 分配，只从胸部骨（上半身系骨及其辅助骨）的权重里按比例分出，顶点总权重不变。
- 刚体：球，半径 0.029H，球心在骨头前方 0.024H；质量 1，阻尼 0.5 / 0.5；组 15，不和任何组碰撞。
- 关节：父骨刚体到胸刚体，恒等朝向，±10°，锁平移，零弹簧。
- 模型已有胸骨时会直接复用，条件是：
  - 骨名像胸；
  - 子树里至少 20 个顶点权重大于 0.3；
  - 权重重心在胸前。

  Fiona 的 `bust_2` 最高只有 0.24，不满足，所以走了新建（`_find_existing`）。

**B（`export_pmx.py` 的 `BUST`）**：刚体布局按你的 MMD 模板（`标准骨骼与刚体.pmx` 的 乳奶1/乳奶2），改了两处。
- **加弹簧 450**：
  - 不加弹簧时，乳房站着就压在 10° 限位上：整体下坠，右侧上缘还折出凹痕（摇晃舞第 80、360 帧）。
  - 弹簧值按 MMD 单位估算：球离转轴约 1.56 单位，重力力矩约 15。
  - 星刃 Fiona 用的 120，在 MMD 单位下仍会下坠 10°。
- **权重**：游戏里 `bust_2` 最高只有 0.24。放大到 0.75，放大倍数随权重平方增长（边缘约 1.2 倍）；整体按一个倍数放大时，边缘过渡变陡会折出凹痕。T 恤同样处理。

**取舍**：
- A：用 MMD 标准骨名（`左胸` / `右胸`），和参考模型一致；但不加弹簧，平时压在限位上。参考模型本来就是这个约定。
- B：沿用游戏骨骼，有弹簧，平时保持原形；参数是估算的，没有参考模型依据。

**待定**：
1. 用 A 的骨骼和权重，再给它加一个弹簧选项？
2. 还是保留 B 的做法，只把骨名改成 `左胸` / `右胸`？

最好在 MMD 里用一支平缓的舞和这支摇晃舞各看一遍再定。

### 3.4 头发

**A（`convert/hair.py`）**：
- 识别：`頭` 下名字像头发的骨，排除 `facial`、`brow`、`lash`、发饰等。
- 子树分叉的骨（Fiona 的 `hair_root` 系，共 6 根）跟着头走，只有单链部分进物理（46 条链）；链首、链尾没有权重的骨去掉。
- 刚体：胶囊，半径 0.2×段长（下限 0.006H），质量 1，阻尼 0.9 / 0.99，组 9。
- 链首那节和出生就贴着身体刚体的节不撞身体（组 10）。
- 关节：±10°，零弹簧。

**B**：
- 用 `mmd_cloth_physics` 找发束：`FACIAL_*` 算身体骨，因为 MetaHuman 发际线关节的名字里带 Hair；预设用 `ornament`（盒子、带弹簧、5～8°）。
- 然后 `anchor_scalp_hair()`：每条链从根部起，骨尾还在双眼下方 3 cm 以上的节改成模式 0（跟随头骨），从第一节低于这条线开始才参与物理。

**关键发现**：Fiona 最长的一组发束（`Fiona_hair_d_*`，8～9 节，20～27 cm）是从头顶分缝斜扫到侧面、停在眼睛附近的，整段贴在头皮上。
- 从根部就模拟的话，站一秒就整条滑下来盖到脸上。
- 关掉碰撞照样滑，所以不是碰撞造成的。
- 插件的头部碰撞体只是下巴高度一个 7 cm 的球，挡不住。
- A 用加粗胶囊压下来一部分，站立测试仍有 22.7 cm；B 把贴头皮的部分固定后是 5.2 cm。代价是 B 只有发尾在动。

**合并建议**：
1. 头发用 A 的 `hair.py`（按参考标定，已经集成在插件里、带清除按钮）。
2. 在 A 里加一个"贴头皮部分跟头走"的选项，把 B 的规则移植过去。
3. 通用做法可以不用"眼睛下方 3 cm"这条线，改成判断骨尾到头部皮肤网格的距离：贴着头皮就跟头走。

### 3.5 相关的第三套：Faceit / ARKit（又一个窗口）

同一天另一个窗口做了用 iPhone Face Cap 实时驱动表情的工具，也是从 Fiona 的 DNA 出发。
- `scripts/vindictus/extract_face_data.py`：把 DNA 和原始网格包取到 `E:\game_export\Vindictus\_meta\face\`。
- 插件 `scripts/blender_addons/faceit_arkit/`：
  - `ue_weights.py` 恢复完整蒙皮权重；
  - `arkit.py` 从 DNA 算出 52 个 ARKit 形态键；
  - `faceit_link.py` 注册到 Faceit。
- 文档：`docs/faceit-arkit-guide.md`。

它记录的一个关键事实：UE Viewer 导出的脸每顶点只留 **4** 个骨骼权重，游戏里最多 **12** 个。
- B 的骨骼表情建在截断后的权重上，张嘴、单侧微笑、鼓腮时脸颊会起包。B 把「にやり」降到 0.8，缓解的就是这个问题。
- **PMX 每顶点最多只能存 4 个骨骼权重**，所以只要表情做成骨骼表情，就绕不开截断。

对合并的影响：
1. **DNA 代码并成一套**：现在仓库里有两份取 DNA 的代码（`metahuman_dna.py extract`、`extract_face_data.py`）和两份 DNA 读取器（`metahuman_dna.py`、`faceit_arkit/dna.py`）。
2. **表情可以改成顶点表情**：用完整权重把 DNA 表情算成网格形变（`faceit_arkit` 做 ARKit 形态键就是这样），再按 `RECIPES` 混成 MMD 表情，存成 PMX 的顶点表情。
   - 顶点表情是逐顶点的位移，不受 4 权重限制，脸颊不会起包。
   - 星刃 Fiona 就是这么做的（`scripts/stellarblade/export_pmx_blender.py` 的 `add_arkit_morphs`，把 ARKit 形态键混成 MMD 顶点表情）。
   - 代价：
     - PMX 文件变大，26 个表情 × 约 7000 个脸部顶点；
     - XPS 那一版脸的顶点顺序要和原始网格对上。

### 3.6 其它

- 身体碰撞刚体：两边都用 Convert to MMD 5 的 `add_body_rigids`。
- 导出：
  - A 另外导出了去掉头发物理、去掉全部物理的两个版本；
  - B 只出一个，外加报告 JSON 和转换后的 `.blend`。
- 模型名：A 是 `Fiona_BaseBody`；B 是 `Fiona`，外加一段说明来源的 comment。

## 4. 合并方案（下次决定）

建议的流程：

1. **转换**：用 A 改好的插件，自动识别直接对。B 的 `SLOT_FIX` 改成只在旧版插件上兜底（例如 頭 槽位不是 `head neck upper` 时才改），或者等 A 提交后删掉。
2. **両目 + 表情**：保留 B 的 `export_pmx.py` 后处理（`add_both_eyes_bone`、`build_face_morphs`），接在转换后面。DNA 是 Vindictus 专有的，留在本仓库。
   - 考虑把表情从骨骼表情改成顶点表情：用完整权重算形变，见 3.5，可以去掉脸颊鼓包。
   - 两份 DNA 读取和提取代码并成一份。
3. **身体碰撞刚体**：插件。
4. **胸部**：二选一，或者组合（见 3.3「待定」），在 MMD 里对比后定。
5. **头发**：A 的 `hair.py`，加上"贴头皮跟头走"选项（见 3.4）。
6. **导出和检查**：付与计算顺序检查、MMD 单位下的站立测试和舞蹈预览、表情检查，脚本见第 5 节。

要你决定的：
- 表情用骨骼表情（现在的，文件小，但会起包）还是顶点表情（不起包，文件大）；
- 胸部用哪种；
- 头发要"更多动感"（A）还是"保形"（B），或者按发束分别设置；
- 合并后的代码放哪边：插件放通用部分，本仓库放 Vindictus 专有的 DNA 表情。

## 5. 怎么重测

脚本在 `scripts/vindictus/checks/`。除 `compare_pmx.py` 外都用 `blender -b --python <脚本> -- <参数>` 运行。

| 脚本 | 用途 |
|---|---|
| `compare_pmx.py a.pmx b.pmx` | 两个 PMX 的骨骼、表情、刚体、关节、权重对照。直接用 Python 跑，不需要 Blender |
| `physics_standing.py <pmx>` | 站立 150 帧，统计头发发梢、胸部的位移和偏转。环境变量：`SCALE`（默认 1.0 即 MMD 单位）、`NOHAIRCOLL=1` |
| `physics_look.py <pmx> <输出目录> <标签> [帧数]` | 头部四个方向在第 1 帧和第 N 帧的渲染 |
| `bust_swing.py <pmx> <vmd> <末帧>` | 跳舞时胸部骨每帧的偏转。环境变量：`BUSTNAMES`（A 用 `左胸,右胸`）、`SPRING`、`LIMIT`、`MODE`、`SUBSTEPS`、`MASS`、`ANGDAMP`、`LINDAMP` |
| `dance_mmdscale.py <pmx> <vmd> <输出目录> <标签> <末帧> <帧列表或 video> [chest\|full]` | 按 MMD 单位出静帧或视频，物理先烘焙。环境变量：`BGM` |
| `morph_sheet.py` / `make_sheet.py` | 在转换后的 `.blend` 里逐个渲染表情，拼成总览图 |
| `pmx_morph_check.py <pmx> <输出目录>` | 从 PMX 导入后用表情滑块驱动，渲染几个表情 |

付与计算顺序：用 ROE worker 的 `verify_grant_order(<pmx>)`。

**两点注意**：
- **按 1.0 导入**：mmd_tools 按 0.08 导回米制时不改重力，所以 Blender 里的物理比 MMD 硬得多（同一个弹簧，力矩差 12.5 倍）。要看接近 MMD 的效果，PMX 和 VMD 都按 1.0 导入。
- **最终在 MMD 里确认**：就算按 1.0 导入，Blender 的 Bullet 版本和步长也和 MMD 不同，关节限位在 Blender 里会被冲破。
