# 更新日志

本文件记录会改变提取结果、Blender 操作或导出行为的更新，最新内容放在最前面。

今后每次功能更新必须同时补充一条记录，并至少写明：

1. 日期与版本；
2. 新增或修复内容；
3. 用户如何操作；
4. 实现原理与兼容性；
5. 已执行的验证。

日期按项目当前使用时区 `Asia/Shanghai` 记录。

---

## 2026-09-26 — Faceit ARKit 插件：52 个 ARKit 表情 + Faceit 实时捕捉（iPhone Face Cap）；补全 UE Viewer 截断的蒙皮权重

1. **新增**：
   - `scripts/blender_addons/faceit_arkit/`（Blender 插件，侧栏 **ARKit**；`cli.py` 命令行同一套函数）：
     - 用 MetaHuman DNA 算出 52 个 ARKit 表情，存成形态键（ARKit → MetaHuman 控制量按 Epic 的 Live Link 映射；
       mouthClose 以 jawOpen 为基准）；
     - 从 UE5 烘焙网格包补全蒙皮权重：UE Viewer 每顶点只留 4 个，MetaHuman 脸最多 12 个，截断后表情全是鼓包；
     - 注册到 Faceit：脸部网格、52 个目标（别的写法也认）、头部骨骼、实时源（Face Cap 端口 9001；眼睛走形态键）；
     - 已有 ARKit 形态键的模型（如剑星 Eve，49 个）只做注册。
   - `scripts/vindictus/extract_face_data.py`：从 Vindictus 容器取出脸的 DNA 和原始网格包（`--list` 查哪些脸带 DNA，目前只有 Fiona）。
   - `E:\game_export\Vindictus\Fiona\blend\Fiona_BaseBody\Fiona_BaseBody_faceit.blend`：第一个做好的模型（用户自己复制的一份）。
2. **用户如何操作**：[`docs/faceit-arkit-guide.md`](faceit-arkit-guide.md)（装插件、面板每个按钮、连 Face Cap、适配别的模型、批量命令）。
   `.dna` 文件是什么、原理：[`docs/metahuman-dna.md`](metahuman-dna.md)（三层名字、文件各段及 Fiona 的实际数字、
   RigLogic 每帧的计算、LOD、读取示例、相关工具）。
3. **原理与兼容性**：见插件 README。DNA 求值与 `scripts/vindictus/metahuman_dna.py` 相同（插件里拷了一份，独立可用）；
   权重恢复按特征读 UE 5.x zen 包（参考骨架、渲染分段、位置、可变权重 + 查找表），按顶点位置写回，只改被截断的顶点；
   Faceit 按 2.3.40 的数据结构直接写（它的界面操作符在后台会报错）。需要 Blender 3.6 + Faceit。
   **Fiona_BaseBody.blend、它的 XPS 和 `export_pmx.py` 做的 PMX 表情仍是截断的权重**，鼓包同样存在，未改。
4. **验证**：52 个表情正面 / 3/4 对照图；数值核对左右和方向；权重恢复前后对照；插件输出与手工流程逐点一致；
   Blender 窗口里用脚本冒充 Face Cap 发 OSC，Faceit 接收后形态键数值、转头轴向正确；Fiona 默认铠甲、剑星 Eve 各跑一遍。

## 2026-09-26 — FF7 Remake / Rebirth：Nexus 裸体 mod 批量导出（Rebirth 9 个 mod、37 个模型）；画廊在 D 盘导出删掉后可重建；GANTZ 跨游戏画廊

1. **新增 / 修复**：
   - **Rebirth mod 材质**：替换网格用的是标准服或别的角色目录里的材质，Dresscode 插件共用同一文件里另一个插件的材质。
     `ff7_mod_export.py` 让 worker 看整个导出的角色目录和所有插件目录；`ff7rb_cli_export.py` 补导材质表里缺的原版贴图，
     并且始终用硬链接暂存目录（游戏 `~mods` 里的替换 mod 不再混进官方模型的导出）；`ff7rebirth_tools.py` 不再给法线 /
     粗糙度 / 金属度 / 透明这类贴图按名字找替身（#1198 的皮肤曾因此变成镜面）。
   - `ff7_mod_export.py`：`--combine` 两作都支持（`rebirth --combine 10356+10357` = #1352 紧身衣 + 它单独的 TifaSkin 插件）；
     角色按 mod 名 + 文件名 + 目录一起识别。`ff7_mod_pmx_batch.py`：几路并行时写 manifest 不再互相覆盖。
   - **Remake**：`validate_ff7remake_model.py` 认出 mod 重画的遮罩（#1364 比基尼、#1358 蕾丝透视裙不再是不透明的紫裙）；
     透明材质的阴影用 HASHED（被遮罩隐藏的几何不再投黑影）；mod 材质缺的漫反射 / 法线从原版材质继承。
     `fix_ff7remake_tifa_gloves.py` 只比较骨骼头的位置（mod 身体经 glTF 导入，骨骼轴向不同，原来手套一律套不上）。
   - **画廊**：两个 `collect_manifest.py` 在 D 盘导出删掉后从 E 盘归档的 manifest 补回条目，`make_gallery.py` 沿用归档里的
     缩略图。Remake 53 张卡片（修好 35 张官方卡片的失效链接），Rebirth 135 张。
   - **新画廊** `scripts/gantz/html/`：GANTZ 主题 mod 导出的 23 个模型（FF7 Remake / Rebirth / 剑星），卡片上有 blend / XPS / PMX
     的完整路径和 PMX 检查结果（胸部 / 头发物理、表情）。
   - `html/nexus_nude_mods.html`：本机游戏在 Nexus 上的裸体 mod 清单，标注已装进游戏 / 已导出。
2. **用户如何操作**：[`docs/ff7-nexus-mods-export.md`](ff7-nexus-mods-export.md) 第 8–10 节（Rebirth 的 mod 种类和安装、
   导出命令、画廊与归档）；`scripts/final/README.md` 新增三条；GANTZ 画廊见 `scripts/gantz/README.md`。
3. **兼容性**：官方模型的导出行为不变（暂存目录只是不再读游戏的 `~mods`）；画廊脚本在 D 盘导出还在时和以前一样。
   Dresscode 框架（Reunion Mod Loader + Dresscode）和 #1352、#2335 的配套文件还没下载，这两个 mod 未导出。
4. **验证**：Rebirth 37 个模型 blend / XPS / PMX 全部读回检查；画廊里每个 `file:///` 链接逐个检查（Remake 213、Rebirth 555、
   GANTZ 197、清单页 143，0 失效）；归档自检（Remake 30/30、Rebirth 111/111）。

## 2026-09-26 — Vindictus：XPS → PMX 带表情（MetaHuman DNA）、胸部物理、头发物理

1. **新增**：
   - `scripts/vindictus/metahuman_dna.py`：
     - 从游戏 IoStore 容器里直接取出脸网格包里嵌的 MetaHuman DNA（UE Viewer 不导出）；
     - 解析 DNA v2.1；
     - 按 RigLogic 的方式求值：原始控制 → PSD → 关节增量 → 正向运动学。
   - `scripts/vindictus/export_pmx.py`：XPS → Convert to MMD 5（教程 6.10 的槽位修正）→ 両目 →
     26 个标准 MMD 骨骼表情（由 DNA 算出）→ 身体碰撞体 + 胸部 + 头发物理 → PMX（12.5 倍）+ 报告 JSON。
2. **用户如何操作**：
   1. `python scripts\vindictus\metahuman_dna.py extract --out <dna>`；
   2. `blender -b --python scripts\vindictus\export_pmx.py -- --xps <xps> --dna <dna> --out <目录>`。

   说明在 `scripts/vindictus/README.md`「导出 PMX」，教程 6.6、6.10 加了指引。

   同一天 Convert to MMD 5 插件窗口也做了一套通用做法（XPS 标准名识别、胸部 / 头发物理按钮）。
   - 两边对比和合并建议：`docs/vindictus-fiona-pmx-approaches.md`；
   - 重测脚本：`scripts/vindictus/checks/`；
   - 教程 6.10 补注：插件是新版时不用手改槽位。
3. **原理**：
   - **表情**：DNA 的中性骨架先拟合到模型骨架上（相似变换）。每个表情按配方（星刃那套 ARKit 配方，换成 MetaHuman 的控制名）求出每根 `FACIAL_*` 骨从静止到摆好的变化，换算成骨骼表情的位移和旋转。
   - **胸部**：刚体布局按用户的 MMD 模板（乳奶1/乳奶2）：`bust_1` 放静态体，`bust_2` 放动态球，关节 ±10°。
     - 另加角度弹簧 450（按 MMD 单位算，静止下坠约 3°）。不加弹簧时乳房一直压在限位上，看起来下坠还带凹痕。
     - 游戏里 `bust_2` 的权重最高只有 0.24，放大到 0.75。放大倍数随权重平方增长，边缘几乎不变。T 恤同样处理。
   - **头发**：用 mmd_cloth_physics 建 46 条发束，改用 `ornament` 预设。每条从根部起，骨尾还在眼睛下方 3 cm 以上的部分跟随头骨（139 个刚体），下面的参与物理（105 个）。
4. **兼容性**：
   - 依赖 Convert to MMD 5、mmd_tools、XNALaraMesh、mmd_cloth_physics，以及 ROE worker 的 `add_both_eyes_bone` / `release_rest_overlaps` / `verify_grant_order`（只调用，不改）。
   - 目前只在 Fiona 的脸上验证过。
5. **验证**（Fiona_BaseBody）：
   - **转换**：15/15 步，1107 根骨，付与计算顺序 0 处违规，PMX 6.4 MB。
   - **DNA 拟合**：620 根骨，平均误差 0.38 mm。
   - **表情**：26 个逐个渲染检查，眨眼、单眼、笑眼、眉毛、あいうえお 都正确；「にやり」在 1.0 时脸颊鼓包，改成 0.8。
   - **头发**：
     - 用原来的 `hair` 预设时，头顶斜扫到侧面的长发束站着不动就滑下来盖到脸上（发梢 24 cm）；
     - 关掉头发和身体的碰撞后照样滑，排除了碰撞的原因；
     - 改成跟随头皮之后，站立时发梢最多 5 cm，四个方向看发型不变。
   - **胸部**：
     - 不加弹簧（模板原样）时：站立下坠 13°，跳舞时右侧上缘折出凹痕；
     - 弹簧 120：按 MMD 单位仍下坠 10°；
     - 弹簧 450：静止下坠 3°。
     - 「来杯好茶摇一摇」这支舞里，弹簧 450～1500 胸部都常被甩到限位，这是舞本身的效果。
     - 权重改成中心放大后，第 80、360 帧的变形消失。
   - **注意**：mmd_tools 按 0.08 导回米制时不改重力，Blender 里的物理预览比 MMD 硬得多。物理的判断都以 MMD 单位（导入缩放 1.0）为准。

## 2026-09-26 — FF7 Remake：PMX 加上 MMD 表情（游戏自己的表情姿势 + 口型数据，先在一个模型上试验）

1. **新增**：`export_ff7_pmx_blender.py --face-data <json>` 让 Remake 模型的 PMX 带上 43 个顶点表情——
   目 10（まばたき、笑い、ウィンク…）、眉 6、口 13（あいうえお、ん、ワ、にっこり…）和游戏整脸表情 14 个。
   形状全部来自游戏数据：`Motion/Player/PC0002_Tifa/Facial00/F_*`（25 个单帧、非叠加的表情姿势）和
   `LipSync/LipMap/Player/PC0002_Tifa/Tifa_Default`（HSFLipMap：aa/ee/oo/sh/fv/ln/bmp 七个口型的嘴部骨骼通道）。
   新脚本 `scripts/final/ff7_face_data.py`（从游戏提取表情数据，内含 unversioned 属性的 HSFLipMap 解析器）、
   `ff7_face_poses_blender.py`（在官方 PSK 骨架上取样姿势）、`ff7_face_morph_sheet.py`（逐个渲染表情对照图）。
   **Blender 插件 `scripts/blender_addons/ff7_face_morphs`（FF7 Face Morphs）**：侧栏 MMD 标签页里查找表情数据、
   分析模型、按 目/眉/口/其他 生成表情（每类可调强度）、预览、清除、一键后台导出带表情的 PMX、手动转换用的
   "转换前暂存 / 恢复并登记"；批量脚本调的是插件里同一个 `core.py`。说明：`docs/ff7-face-morphs.md`（原理）、
   **`docs/ff7-face-morphs-usage.md`（使用说明：MMD 里读模型 / 打表情关键帧 / 套 VMD、43 个表情一览、面板每个按钮、
   三种流程、命令行、常见问题）**、插件 README。
2. **用户操作**：先 `python scripts/final/ff7_face_data.py --out E:\game_export\FF7Remake\_meta\face\PC0002_Tifa.json`，
   再给 `export_ff7_pmx_blender.py` 加 `--face-data <json>`（可选 `--face-strength EYEBROW=1.5`）；或者在 Blender
   里启用插件（已用目录联接装进 Blender 3.6 的 addons），打开模型 .blend 点按钮。表情数据是游戏数据，放在仓库外。
3. **原理**：姿势换成"相对 C_FaceBase_a 的刚体变化"并换算到脸部坐标系；表情 = 姿势 × F_Idle01⁻¹（游戏平静脸
   不是绑定姿势：舌头差 5 mm）；按眼 / 眉 / 嘴区域取骨骼；在脸部骨骼并进头骨之前摆姿势、取蒙皮网格差值存成形态键。
   Convert_to_MMD5 的 `_bake_pose_delta_to_rest()` 会跳过带形态键的网格（FF7 全身一个网格，手臂会烘不上），
   所以 A 字姿势前暂存形态键、转换后恢复。不加 `--face-data` 时行为和以前完全一样。
4. **验证**：试验模型 `mod1707_PC0002_00_Tifa_Gantz_Basic_Suit_Skimpy_Hair_and_Ma` →
   `E:\game_export\FF7Remake\_face_trial\`（原 PMX 未动）：43 个表情，转换中脸部 0 位移，mmd_tools 读回面板正确、
   越界索引 0、"表情"框 43 项；撕裂 0、付与顺序 0、刚体 80 / 关节 64、静止漂移 0.9 cm；17 MB → 34 MB；
   舞蹈 VMD（meeynara手势舞）驱动眨眼 / 单眨 / 笑眼 / 口型，按峰值帧渲染确认。仓库脚本重新从游戏提取的数据和
   试验用数据一致（矩阵差 8e-5）。插件：后台 Blender 逐个调用按钮全部通过（暂存/恢复逐位相同，模拟转向 + 缩放后
   恢复误差 6e-8，清除不碰别的形态键，面板导出带眉 1.5 倍：眉表情正好 1.50 倍、其余与试验版相同、撕裂 0），面板
   draw() 用模拟布局检查无错；实际界面没在窗口里看过，也没在 MMD 本体里打开过。
5. **修正（写使用说明时发现）**：`.blend` 里已经生成过表情时，面板上取消的类别在导出时仍会进 PMX（mmd_tools 导出
   网格上所有形态键）。现在 `export_ff7_pmx_blender.py` 在生成前先清掉插件生成过的形态键（报告字段
   `face_morphs_cleared`）。验证：全部 43 个生成后取消"口""其他"再导出 → PMX 读回正好 16 个（目 10 + 眉 6），撕裂 0。
   另外统计了本机 `E:\Downloads` 的 320 个 VMD：246 个带表情关键帧，其中 217 个（88%）用到的表情这个模型全有。

---

## 2026-09-26 — CRISIS CORE –FINAL FANTASY VII– REUNION：模型列表 + 导出 .blend / XPS / PMX（新游戏），女性角色全部导出

### 新增 / 变化

- 新目录 `scripts/ccff7r/`（Steam 版，build 10871899，`E:\SteamLibrary\steamapps\common\CCFF7R`）：
  - `list_models.py`：直接从游戏容器列出 **266** 个模型——主要角色 34、召唤兽（DMW）3、NPC 41、敌人 121、道具 / 武器 67，
    标出已导出的；`--details` 读出顶点、三角面、材质槽、身高；全量清单写到 `E:\game_export\CCFF7R\_meta\model_list.md`；
  - `export_model.py`：CUE4Parse CLI 导 PSK + PNG + 材质实例 JSON → `build_blend.py`（Blender 3.6）建材质、渲全身和脸部预览、
    贴图打包 → `E:\game_export\CCFF7R\<组>\blend\<id>\<id>.blend`（按归档约定，目录可单独拷走）；一个模型 6–10 秒；
  - `export_model.py --xps --pmx`：再从 `.blend` 转 XPS（`export_xps_blender.py`，Blender2XPS）和 MMD PMX
    （`export_pmx_blender.py`，FF7 / Stellar Blade 那条转换链 + CCFF7R 骨架适配），PMX 转完自动导回 Blender 套舞蹈跑物理渲预览；
    `--preview-only` 只渲预览图不存 `.blend`（用来快速看一整类）；
  - `ccff7r_common.py`（路径、CLI 调用、包清单缓存、模型发现、名字表）、`tests/test_ccff7r.py`（12 个离线测试）、`README.md`。
- 全部 266 个模型的预览逐个看过，确认**女性模型 21 个**：主要角色 6（蒂法、爱丽丝、西丝妮 ×2、尤菲、吉莉安）、NPC 成年女性 10、
  女孩 4、敌人 1（女神米涅瓦）。这 21 个都已导出 `.blend` + XPS + PMX（`E:\game_export\CCFF7R\<组>\{blend,xps,pmx}\<id>\`），
  总览图 `E:\game_export\CCFF7R\_meta\female_models.png`。另有试验用的扎克斯 s12、萨菲罗斯 ×2、贝希摩斯、破坏剑（只有 `.blend`）。

### 用户如何操作

```
cd scripts\ccff7r
python list_models.py [--category named] [--find tifa zack*] [--details]
python export_model.py tifa [aerith ...] [--category named] [--force] [--views] [--xps] [--pmx]
python export_model.py --category npc --preview-only
```

一次性准备：AES key（`scripts\firstdescendant\find_aes_key.py` 对游戏 exe 和 `pakchunk0`，41 秒，存
`E:\tools\ccff7r\_keys\`，不进仓库）+ usmap（TheNaeem/Unreal-Mappings-Archive 的 `CCFF7R/Mappings.usmap`，存
`E:\tools\ccff7r\mappings\`）。详见 `scripts/ccff7r/README.md`。

### 实现原理与坑

- UE 4.27.2 IoStore，pak 索引 AES 加密，属性未版本化：不带 key CLI 列出 0 个资源，不带 usmap 每个包都是
  `Could not load standard asset`。社区 usmap 是 2022-12-17（发售后第 4 天）的，比当前 build 旧，但网格 / 贴图 / 材质实例
  都是引擎类，实测全部能解析。
- 每个角色文件夹一个 `SK_CH_<id>` + 一个 `_SW` 版：几何完全相同，只换了 `*_Lite` 简化材质，默认导主模型。
- CLI 按网格导出时材质文件是空的 `{}`（同 Rebirth）：另用 `-f json` 导网格和整条材质实例链，子覆盖父合并参数；1,945 个
  角色材质实例全部来自 8 类公共父材质（`MI_ch_*`，小写 ch），据此分 7 个家族还原。通道是在贴图上量出来的：standard 的
  MultiMask R = 金属度（破坏剑刃口、护肩包边、铆钉）、G = 粗糙度、B = AO；skin 的 R = 次表面量（皮肤 ≈0.58）；`_MM2` 的
  R = 自发光遮罩、G = 毛孔遮罩；眼睛贴图是完整眼球。
- 头发：实例的 `Brightness`（Tifa 3.35）是给 UE 头发着色模型补亮的，原样乘到 Principled 上黑发变中灰；对比渲染后用
  `Brightness^0.15`，高光 × 0.6。
- 武器（破坏剑、正宗、手里剑）是身体网格的一部分，跟随的 `wpn` / `pivot` 骨在绑定姿势里在原点，T 姿势下平躺在脚边 →
  拆成单独的 `<id>_weapon` 物体，预览不渲染它。
- CLI 并行导出：同一个包出现两次（两个通配符都匹配）会并发写同一个文件，`IOException` 后整批中止 → 先去重再用 `-c` 列表。
- 单位保持 UE 厘米，和 Rebirth / TFD 的 `.blend` 一致。
- XPS：骨骼是 HumanIK 命名，blender2xps 的别名表本来就认，直接映射成 XPS 标准骨名（姿势能套），×0.01 成米。
- PMX：HumanIK 名字对 MMD 槽位；镇民 / 村民 / 职员 / 女孩这类 NPC 骨架**没有脖子**（头挂在 `Spine1` 上）、没有手指脚趾 →
  补一根不带权重的 `Neck`（MMD 必须有 首）；`hi_face` 下的脸部骨（除两眼）并进头；Tifa 的 `L_bustB → L_bustA` 合成一根挂
  胸部物理（只有她有胸部骨）；转换器不认的缩写先改名（`skt` → `skirt`、`ribon` → `ribbon`、`mant` → `mantle`、
  `Cloth` → `Cloak`），`Roll` / `Sub` 扭转辅助骨标成四肢辅助骨。
- 女性判断：只有 Tifa 的骨架有胸部骨，不能靠骨骼；NPC 名字里 `b` / `d` 结尾的镇民、村民是女性（身高 168–170 cm），
  `a` / `c` 是男性（184–187 cm），最后以预览图为准。

### 验证

- 9 个 `.blend` 用 `scripts/archive/blend_selfcheck.py` 自检：外部引用 0（贴图全打包）。
- Tifa：全身 6 个角度 + 脸部 4 张特写；头发亮度 / 高光做了 4+4 组对比；靴子的橄榄棕是贴图本色（UV 取样 65/56/36）。
- 6 个模型的衣服材质逐面取 MultiMask R：80–100% 的面 < 0.1，金属件（扣子、手里剑、刃口）> 0.65。
- 女性 21 个：`.blend` 21、XPS 21、PMX 20。20 个 PMX 的网格撕裂全部为 0、骨骼继承顺序冲突 0，导回 Blender 套舞蹈跑物理
  逐个看过（总览 `E:\game_export\CCFF7R\_meta\female_pmx_check.png`）；Tifa 两侧胸部物理，爱丽丝 66 / 西丝妮 48 / Tifa 42 个刚体
  （头发、裙摆、项链），尤菲的短发是单节骨、头上的丝带在头部下面，都没挂上物理。米涅瓦**没有 PMX**：翅膀、旗帜、弓的骨骼
  前后伸得比身高还远，ROE 转换器的方向检查（`bake_rig_transforms`：骨头 Z 跨度 < Y 跨度就拒绝）判她不是站立的——她是一整座
  全身甲 Boss，MMD 骨架套不上，只出 `.blend` 和 XPS。西丝妮的手里剑（`tian_weapon`）不进 XPS / PMX。21 个共 2.25 GB。
- `python -m unittest discover -s scripts/ccff7r/tests`：12 个测试通过。

---

## 2026-09-26 — FF7 Rebirth：眼睛「大黑瞳」修复（虹膜贴图放大 2 倍）+ 借用材质从游戏重建

### 新增 / 变化

- 修复：Rebirth 所有「眼白 + 虹膜」拼法的眼睛，瞳孔几乎占满虹膜、只剩一圈细边（Tifa、Aerith、Cloud、Sephiroth……
  全部如此，Remake 没有）。`ff7rebirth_tools.py` 给虹膜贴图加一套以中心放大 2 倍的 UV（`FF7RB_EyeIrisUV`），
  虹膜/眼白分界 0.18–0.22 → 0.225–0.25；导 FBX/GLB 时的眼睛烘焙（`export_ff7rb_model_blender.py`）同样处理。
- 修复：Vincent 的眼睛材质 `PC0011_00_EyeL / EyeR` 没被认成眼睛，虹膜铺满整颗眼球。
- 新脚本（`scripts/final/`）：
  - `fix_ff7rb_eyes.py`：修已经导出的 `.blend`（只补节点，原地保存，`--backup` 先备份原件）；
  - `ff7rb_rematerialize.py`：从游戏重建 `.blend` 里指定的材质（`--material` / `--no-base` / `--no-record`）——
    模型借用别的角色目录的材质实例时导出没有材质表、贴图是按文件名猜的；
  - `render_eye_closeup.py`：统一相机和灯光给眼睛拍特写 + 列出眼睛材质的节点和贴图。
- `export_ff7_pmx_blender.py`：`.blend` 里打包的贴图先写到临时目录再导 PMX，存 `_converted.blend` 前再打包回去
  （从 E 盘归档直接导 PMX 时整张脸是洋红色）。
- `ff7rb_cli_export.py`：`.usmap` 在 D 盘找不到就用 E 盘归档里那份。
- E 盘归档（`E:\game_export\FF7Rebirth`）已处理：98 个 `.blend` 里 70 个修了眼睛；Vincent、PC0010_10 Sephiroth 变身形态
  （8 个材质）、PC0000_17 Cloud Loveless 无面具（10 个材质，原来整个模型是灰的）从游戏重建；Tifa #817 的 8 个 mod
  重导 XPS / PMX；画廊预览图和缩略图重渲。原件备份在 `E:\_backup\ff7rebirth_eyes_20260926\`（73 个，约 7 GB）。

### 用户如何操作

```
python scripts\final\fix_ff7rb_eyes.py <blend 或目录> [--backup <目录>] [--dry-run]
python scripts\final\ff7rb_rematerialize.py <blend> --no-base --no-record [--backup <目录>] [--dry-run]
blender -b X.blend --factory-startup --python scripts\final\render_eye_closeup.py -- --out <目录>
```

新导出的 Rebirth 模型不用再修（`ff7rebirth_tools.py` 已经按新做法生成）。详见 `docs/ff7rebirth-eye-fix.md`。

### 实现原理与坑

- Rebirth 的眼睛材质（`RMI_Surface_Eye_Migration` → `RM_Surface`，静态开关 `Eye_` / `EyeMigration_`，没有标量参数）
  用两套贴图：眼白 `Common_Eye_Player_C` 贴在眼球 UV 上，`IrisColor` / `IrisNormal` / `IrisOcclusion` 是只有虹膜、
  铺满整张的图。眼球网格只有一套 UV，缩放写在着色器里。
- 倍数是量的：Remake 的同名 `PC0002_00_Eye_C` 是整只眼睛（瞳孔边缘 UV 半径 0.068、虹膜外缘 0.245），Rebirth 的虹膜图
  瞳孔边缘 0.135、虹膜铺到 0.5；两边眼球 UV 布局和几何一致 → 2 倍，0.5 / 2 = 0.25 正好落在 Remake 的虹膜外缘。
- 借用材质：FModel 只写模型自己目录下的材质表；`ff7rb_rematerialize.py` 用 CLI 列表按名字找到材质实例，
  沿用 `ff7rb_cli_export.fix_materials` 重建表、导出贴图，再调用批量导出同一个 `prepare_material`。
  全量检查后，其余缺底色的材质（SOLDIER 装的发光件、mod 借用的 Tifa 耳环）在游戏表里本来就没有底色贴图。
- 归档后的 `.blend` 贴图是打包的：mmd_tools 导 PMX 按文件路径拷贴图，拷不到就只剩现烘的几张（洋红脸）；XPS 不受影响。

### 验证

- 眼睛特写（同一相机、灯光）修前 / 修后，Remake 同角色对照：Tifa、Aerith、Cloud、Sephiroth（竖瞳）、Vincent、
  Sephiroth 变身、Cloud 17；修后瞳孔大小与 Remake 一致。
- `fix_ff7rb_eyes.py` 幂等（第二遍 already ok），文件只多约 3 KB，仍是不压缩的 `BLENDER-v306`，无 `.blend1`。
- Tifa #817 的 8 个 PMX：撕裂 0、付与顺序违规 0、静置漂移 0.9 cm、PMX 贴图表每项都在，`preview_gaze.png` 目检。
- 单元测试 21 个通过（新增：虹膜按倍数采样、贴图边缘落在遮罩外缘、EyeL/EyeR 是眼睛而 Eyebrow/Eyelash 不是）。

## 2026-09-26 — 文档：Vindictus Fiona 全手工导出教程（游戏文件 → Blender → XPS / PMX）

### 新增 / 变化

- `docs/vindictus-fiona-manual-export.md`：以 `Fiona_BaseBody` 为例，每一步都在图形界面里手工完成，覆盖：
  - UE Viewer 解包（UE 5.3、key 从文件读、三个包的路径）；
  - Blender 手工组装：导入 PSK、素体转正、合并骨架、切旧头保留 T 恤、照 `.props.txt` 建材质；
  - 修脖子：用修改器做到和 `fix_basebody_neck.py` 一样的效果；
  - 把 Biped 身体和 UE 脸并成一副骨架；
  - Blender2XPS 导出 XPS；
  - Convert to MMD 5 + mmd_tools 导出 PMX。

  每节都写了对应的自动脚本，最后是常见问题表。`scripts/vindictus/README.md` 加了链接。
- 教程新增 6.10「直接从 XPS 转 PMX」，从 XNALaraMesh 导入开始：
  - 先清掉骨架缩放；
  - 自动识别后要改 4 行槽位：センター、下半身、頭、目；
  - 一键转换后在左下角面板取消勾选「自动识别骨架」，状态栏应显示 15/15 步，16/16 说明槽位被盖掉了；
  - 材质不用改，贴图自动带上。
- `scripts/vindictus/fix_basebody_neck.py`：
  - 命令行加 `--face` / `--body`，可以对物体名不同的手工组装文件跑；
  - 旧身体的三角面改存普通元组，不再引用网格数据。输出不变。

### 验证

- 在 Blender 3.6.15 后台，用 GUI 按钮调用的同一批操作符，把第 2、4、5、6 节的关键步骤重放了一遍：
  - 骨数和自动构建一致（1027）；
  - 并成一副骨架后，XPS 标准骨名都落在 Biped 骨上；
  - Convert to MMD 5 15/15 步，PMX 回读 1088 根骨、高 21.9。
- 第 3 节在没做脖子修复的构建上重放，和脚本结果对比：各段偏移中位数相差 < 0.06 cm，外沿都压在旧皮下 0.05 cm，
  贴图、白模渲染看不出差别。
- 脚本改动前后，同一输入的输出逐位一致；在手工组装的文件上用 `--face/--body` 跑通。
- 6.10 用归档的 `Fiona_BaseBody.xps` 重放：
  - 转换：15/15 步，1099 根骨，0 个权重孔；
  - PMX 回读：1103 根骨，高 21.90，9 个材质都有贴图；
  - 缩放没清就转：PMX 有 214.8 单位高；
  - 摆姿势：抬臂、抬腿时被拉长的边，原始 XPS 和转换后一样多（如抬臂 60° 都是 9 条），来自源权重；
  - 撤销后改过的槽位能恢复：在有界面的 Blender 里验证过。
- 没实测的部分（UE Viewer 对话框、GUI 里手搭材质、両目、胸部物理、在 XPS / PMXEditor / MMD 里查看等）在文档里逐条标了「未实测」。

---

## 2026-09-26 — 导出归档：D 盘各游戏的导出按「游戏\角色\格式\造型」搬到 `E:\game_export`

### 新增 / 变化

- 新目录 `scripts/archive/`：`archive_exports.py`（归档、自检、目录清单、D 盘可删除清单、改画廊链接）、`games.py`
  （15 个游戏的规则：产物在哪、归到哪个角色 / 格式、哪些是能重新生成的中间产物）、`blend_selfcheck.py`、
  `blend_package.py`、`tests/test_archive.py`、`README.md`。
- `E:\game_export` 现在有 14 个游戏、1,589 个造型（按格式分共 1,914 个目录）、163 GB：Vindictus 31、The First Descendant 14、
  Throne of Desire 17、DOA6 64、DOA5LR 291、FF7 Remake 45、FF7 Rebirth 98、Stellar Blade 151、VaM 68、NARAKA 517、
  HoneySelect 2 66、Venus Vacation PRISM 9、Hotel VIP 8（2D）、Rise of Eros 210。每个造型目录都能单独打开。
- `E:\game_export\D盘可删除清单.md`：D 盘 22 个导出目录都可以整个删，能腾出约 257 GB（`D:\ff7_mods` 的 153 GB 是 FF7 Rebirth
  游戏 pak 的硬链接，删了只腾 2.8 GB；`D:\roe_exports` 标了“ROE_pmx 窗口还在用”）。`D:\vindictus_exports`、
  `D:\vam_imports\FionaDF` 已由用户删除。
- NARAKA：E 盘原来的 `outfits\<服装>` 同盘移动成 `NARAKA\<英雄>\blend\<服装>`（495 套），列表页链接一并改好。
- 12 个画廊页（doa5lr、doa6、final、final/html_rebirth、firstdescendant、honeyselect2、hotelvip、riseoferos、stellarblade、
  throneofdesire、vam、vindictus）里指向 D 盘的图片 / 模型链接改成 E 盘的归档位置。
- `scripts/vam/README.md`：`bring_to_vam` 的源 `Fiona.blend` 改成 E 盘路径。

### 用法

```powershell
cd scripts\archive
python archive_exports.py --list
python archive_exports.py <游戏> --dry-run      # 看分组
python archive_exports.py <游戏>                # 或 all；新导出了角色就再跑一次，只拷新的 / 改过的
python archive_exports.py --report              # 删 D 盘之前刷新可删除清单
python archive_exports.py --relink              # 画廊重新生成后把链接再指回 E 盘
```

### 实现与兼容性

- 只拷不删。边拷边算 md5，写 `.part` 再改名、读回再比；拷贝前后源文件大小 / 修改时间变了（别的窗口在写）就不记账。
  账本 `<游戏>\_meta\ledger.json`，重跑按大小 + 修改时间跳过。
- 自检在 E 盘这份上做：Blender 打开每个 `.blend`，`blend_paths(packed=False)` 的每个外部文件都得在造型目录里；
  `.xps` / `.mesh` / `.pmx` 解析贴图表；VaM 查 `Custom/` 引用。缺的文件换算回 D 盘看：D 盘也没有 = 源文件本来就缺（提醒）。
- 贴图外链的 `.blend`（FF7 Remake、各 PMX 目录的 `_converted.blend`、ROE 的跳舞场景）在 Blender 里把外部贴图 / 声音收进
  造型目录后另存；按字节拷的 `.blend` 自检发现还指向目录外时自动改走这条路（ROE f10 / g10）。
- 可删除清单扣掉硬链接（nlink > 1），两小时内有写入的目录加粗提醒。
- 坑：Blender 3.6 的 `bpy.utils.blend_paths(packed=...)` 文档写反了（`packed=False` 才跳过已打包数据）；VSE 声音轨自己
  还存着一份旧路径，只能按新路径重建声音轨；VaM 目录名里的 `[Looks]` 会被 `glob` 当成字符集；打包时存两次会留 `.blend1`。

### 验证

- `python scripts\archive\tests\test_archive.py` → `ARCHIVE_TEST=PASS`。
- 1,914 个造型目录自检全部通过；从 E 盘打开 FF7 Remake 的 Cloud（打包过贴图）和 ROE 的 f10（自动补救过）渲染，贴图完整。
- 重跑同一个游戏时所有文件都跳过；NARAKA 两个列表页 1,070 个相对链接改到新位置。
- 之后按用户要求删掉了除 `D:\roe_exports` 以外的 23 个 D 盘目录（删之前逐个再核对一遍：每个文件都已归档且没改过、
  或是登记过的中间产物，没有 junction / 符号链接，17 小时内没有写入），D 盘可用空间 97.7 GB → 311.9 GB。

### 同时修了：Vindictus `Fiona_BaseBody` 的脖子接缝

- 用户看了归档后的 `Fiona_BaseBody` 让再检查一下。归档本身没问题（E 盘 29 个文件和 D 盘原件 md5 一致），毛病在
  09-13 的构建：新脸自带的颈部 / 锁骨“围兜”和旧身体互相穿插（前面浮在外面，穿着 T 恤时胸口一块方形肤色；后背沉在
  里面），按权重切旧脖子时把 T 恤领口的 6 个顶点也切了，旧脖子皮和 100 个旧脸碎面露出来。
- 用户的要求：这个素体要能脱掉 T 恤当裸体用，身体本身必须完整。前两轮都被否掉——第一轮按领口高度切掉整片围兜
  （“脖子还是不对呀”，领口两侧各一条深色带）；第二轮按遮挡删（“把白衣服去掉，只看身体，脖子缺了一部分”）。
- `scripts/vindictus/build_blend.py`：`cut_legacy_head()` 不再切衣服层（材质 `inner`）；随后调用新脚本
  `scripts/vindictus/fix_basebody_neck.py`：`fit_face_to_body()` 把围兜按身体骨骼权重贴到旧身体表面（过渡带平滑、
  外沿压进旧皮下面由旧皮盖住），重写挪过的顶点的自定义法线，删掉被围兜盖住的旧身体面和旧脸残片（删面前后旧身体的
  法线原样写回）；材质建好后 `match_bib_tone()` 逐顶点匹配肤色（顶点颜色 `bib_tone` + Mix MULTIPLY）。原理和
  试错过程见 `scripts/vindictus/README.md` 和脚本开头。脚本也能单独修已经构建好的 .blend；环境变量
  `VINDICTUS_NO_NECK_FIT=1` 关掉这一步（调试用）。
- 第三版之后又修掉三处：按权重只贴一半留下的后背凹坑、没重写法线造成的后背围兜下沿弧线（挪完顶点后围兜和身体的
  法线差 18°）、围兜外沿浮在旧皮上从侧面贴着肩膀看的一道细黑线；最后把过渡带拉宽并平滑，脖子根的折痕变柔和。
- 验证：藏掉 T 恤和穿着两种状态，正 / 3/4 / 侧 / 后 / 俯视各看 70 cm 全身、45 cm 85 mm 近景和肩膀 7 cm 特写，材质效果、
  白模、按材质上色都干净；贴好的围兜和旧身体法线差 0°，旧身体其余部分的法线变化 < 0.05°。
- 重新解包（`export_model.ps1 Fiona_BaseBody -Force`）并构建，重新归档到
  `E:\game_export\Vindictus\Fiona\blend\Fiona_BaseBody`（09-13 的原版备份在 `Vindictus\_meta\backup\Fiona_BaseBody_2026-09-13`），
  画廊缩略图一并更新，临时的 `D:\vindictus_exports` 归档后删掉。
- 之后按用户要求导出 XPS（先按手工教程第 4 节把 Biped 身体和 UE 脸并成一副骨架），摆姿势时发现左肩领口有皮肤从
  T 恤里穿出来：围兜只贴了形状，权重还是脸的。`fix_basebody_neck.py` 加了两步——贴好的围兜改用旧身体在同一点的
  骨骼权重（过渡带按 t 混合，领口附近按离衣服的距离用身体权重），T 恤在盖住围兜的地方往外放到至少 4 mm（XPS 每顶点
  只存 4 个权重，围兜插值来的权重被截断后会多偏 2 mm 左右）；V 领下面过渡带里 8 个离衣服不到 2 mm 的顶点往里收。
  静止姿势的形状、法线、肤色都不变。重新构建、归档。
- 用户让检查眼睛：眼球、虹膜、瞳孔、眼皮贴合都正常，**睫毛发白**。原因在 `build_blend.py` 的材质分类顺序——睫毛
  实例（`M_EyeLash_HigherLODs_Inst`）有 `ODI Map`，先命中了头发规则，接了头发的发根→发梢渐变却没有 FR 贴图驱动，
  一直是中间的浅棕色。改成眉毛 / 睫毛的判断放在头发前面，Base Color 用实例里的 `Color`（0.0039，接近黑）。
  Fiona_BaseBody 已重建、重新导出 XPS 并归档（烘焙出的睫毛贴图 RGB ≈ 13/255）。归档里另外 15 个用 Fiona 脸的模型
  （Fiona、PCF_001～010、PCF_001_Temp、PCF_012、PCF_067、Shiningwill_legacy）和它们的 XPS 也是白睫毛，等用户决定是否批量重建；
  Lethita、PCM_BaseBody 本来就对。
- 新的 XPS：`E:\game_export\Vindictus\Fiona\xps\Fiona_BaseBody\`（1013 骨、9 个部件、高 1.75，警告 0，脸部皮肤烘焙时
  把肤色修正一起带进贴图）。验证：用 XNALara 导入插件读回 Blender，静止穿着 / 脱掉 T 恤、弯腰 + 转头 + 抬左臂的
  姿势都渲染检查；Blender 里 30 个姿势（每只手臂三个轴 ±45°、锁骨、头、脊柱）从 T 恤外往里打射线，脸 / 围兜穿出
  从 19 处降到 2 处（都在手臂绕自身轴拧 45° 的极端姿势），旧身体本身在这些姿势里穿 T 恤的地方远比这多。

---

## 2026-09-25 — FF7 Remake / Rebirth：GANTZ 主题 mod 导出到 Blender / XPS / PMX，Rebirth 画廊补齐 85 个

### 新增 / 变化

- 两作 Nexus 上 GANTZ 主题的 4 个 mod（Remake #967、#1707；Rebirth #817、#1613）共 11 个文件，导出成 21 个
  `.blend`（Remake 8、Rebirth 13），其中 19 个再出 XPS 和 PMX（附加包单独套在原版上的 2 个只进画廊）。
- 新脚本（`scripts/final/`）：`nexus_mod_batch.py`（公开 GraphQL 选文件 → 浏览器下载清单页 → 从下载目录复制解压）、
  `ff7_mod_export.py`（mod → .blend + 画廊条目；Remake 单独挂载 + glTF 兜底，Rebirth CLI 暂存目录，含 DRESSCODE 插件 mod，
  `--combine` 附加包组合）、`ff7rb_cli_export.py`（Rebirth 无界面导出 + 材质表重建）、`export_ff7_pmx_blender.py` +
  `ff7_mod_pmx_batch.py`（FF7 → PMX + MMD 预览）、`cue4parse_ff7_mod_tangents.patch`（CUE4Parse 读 mod 网格）。
- Rebirth 画廊 71 → 85：FModel 读不了的 13 个 Player 主模型 + 红十三全息版改走 CUE4Parse CLI，Player 主模型全齐。
- Remake 画廊加「mod」分类：GANTZ 这批 + 8 月手动导出的 zzTifaNudeNatural；两个画廊的 mod 卡片带 Nexus 链接和
  XPS / PMX / PMX 舞蹈预览链接。
- 现有工具的改动：`validate_ff7remake_model.py` 加 `--overlay-root`、能导入 glTF；`ff7rebirth_tools.py` 认
  `OxygenSaturation`（血迹贴花颜色）、薄玻璃壳和无光照全息材质、读材质表里的父链；`export_ff7rb_model_blender.py`
  认 `FF7RB_EXTRA_ROOTS`；两个 `collect_manifest.py` / `make_gallery.py` 读 mod 条目和 CLI 路线结果。

### 用户如何操作

见 `docs/ff7-nexus-mods-export.md` 第 8 节命令速查。产物在 `D:\ff7remake_exports\mods\`、`D:\ff7rebirth_exports\mods\`
（各自的 `xps\`、`pmx\` 子目录），画廊 `scripts/final/html/index.html`、`scripts/final/html_rebirth/index.html`。

### 实现原理与坑

- mod 网格：Remake 的专用 UE Viewer v8 对四个 GANTZ 网格都报 `LODModels.Num() == LODInfo.Num()`，自动走 FF7R-mesh-importer；
  Rebirth 的 mod 网格是原版 UE 4.26 烘的 8 字节切线，CUE4Parse 只认 SE 的 4 字节压缩切线（`RawArray item size mismatch:
  expected 8, serialized 4`），补丁按元素大小分流，重编的 CLI 在 `E:\tools\cue4parse_cli_ff7`（.NET 10 SDK 装在 `E:\tools\dotnet`）。
- CLI 写的材质 JSON 全是 `{}`：沿材质实例父链重建，**必须带上基础材质的贴图参数默认值**，否则 worker 把头发的透明遮罩
  猜给了头和上衣，脸是透的。
- DRESSCODE 插件挂在 `End/Mods/<插件>/Content`，CLI 却按对象路径写文件；网格在 MetaData 目录；condition 辅助网格跳过。
- PMX：SE 骨骼槽位、4 节脊椎并 3 节、104 根脸部骨并进頭（暂无表情 morph）、眼球骨直接用、胸部物理骨的支点从脊椎后
  12 cm 挪到各自胸部里 8 cm、`*_Spo` 不进布料物理、TheWolfster 两个战斗服的大腿护甲从裙摆骨转给大腿（`--skirt-to-legs`）。
- Remake 透明遮罩：.mat 不带参数名，#967 整套衣服所在材质引用的 `MarineCharm_A` 其实绑在 `DetailOpacity`（不透明着色器的自发光细节遮罩），当透明度后全身被挖空；改为 `umodel -dump` 读材质实例参数名（`material_params.json`），只认 Opacity / Coverage / Alpha 类参数。破洞要用绿色背景渲染才看得出来。
- 下载：Nexus 新存储的文件名是 `名 模组号 版本 时间 随机串.ext`（空格），和旧的连字符格式都认；E:\Downloads 只复制不动。
- blender2xps 骨骼别名表补了 SE 命名（blender2xps 仓库单独提交），XPS 姿势能套上。

### 验证

- Blender：21 个 mod 模型 + 14 个 CLI 补导模型逐张看预览（脸部特写两轮：透明脸、Reika 白眼、DRESSCODE 版眼睛都修过）。
- XPS：19 / 19 导出成功，身高 1.726。
- PMX：见 `docs/ff7-nexus-mods-export.md` 第 5 节的结果表（撕裂、付与顺序、静止漂移、刚体数），舞蹈帧与大腿护甲特写目检。
- CUE4Parse 补丁不影响官方网格：蛤蟆 psk 与 0.2.0 发布版逐字节同大小。

## 2026-09-25 — NARAKA: BLADEPOINT：全部女性外观批量导出 + 并行批导脚本

### 新增 / 变化

- 新增 `scripts/naraka/batch_export.py`：按家族切成每批不超过 12 套，每批一个 `export_model.py` 进程，默认 8 路并行；
  空闲内存低于 `--reserve` 时不开新批，已导出的跳过，失败的最后各重试一次；汇总写 `_logs\batch_summary.json`，
  列表页在全部结束后写一次。
- `export_model.py` 加 `--no-html`（并行的各批不同时写同一个列表页）。
- 17 位女性英雄的 495 套外观全部导出到 `E:\game_export\NARAKA`（`.blend` + 四视图预览 + 列表页）。
- 文档：`scripts/naraka/README.md` 新增「并行批量导出」、补验证结果和「稀有」变色皮肤的限制；
  `docs/naraka-bladepoint-extraction.md` §4 补批量导出的内存问题，§6 写稀有皮肤的规则文件结构。

### 用户如何操作

`python scripts\naraka\batch_export.py --sex f --out E:\game_export\NARAKA`（`--dry-run` 只看分批；`--jobs` / `--chunk` /
`--reserve` 调并行度和内存；中途断了原样再跑一次即可）。

### 实现原理与坑

- 一个进程会留着打开过的全部 bundle，内存随导出数量上涨，所以分批、多进程；12 套一批峰值 2.25 GB。单个进程是
  单线程 Python，8 路并行时 CPU 也只占 2 成左右。
- 「稀有」变色皮肤（`assets/design/rareskin/<外观>_rule.asset`，女性 11 套）的颜色在游戏里按每件物品的 8 位编号
  抽取，规则经各皮肤自己的 shadergraph 生效，没有还原，导出的是底色（偏灰白）。

### 验证

495 / 495 成功，26 分钟，共 41 GB。只有沈妙 `lv_s14` 的发型有 8 根骨按最近位置配上（偏 4.2–4.4 cm，预览看不出）。
按家族拼的 17 张缩略图总览（`_list\overview\`）逐张看过，没有坏的。

## 2026-09-25 — VaM：把游戏角色整套搬进 VaM（直接写物品，不经过创作器）——Vindictus Fiona

### 新增 / 变化

- `scripts/vam/` 新增一条「游戏角色 → VaM」的线：
  - `bring_to_vam.py`：流程（profile `fiona_df`）；
  - `vam_items.py`：`.vam / .vaj / .vab` 与 morph（`.vmi / .vmb`）的写出；
  - `face_fit.py`：脸（头部 morph、脸部贴图、眉毛、虹膜）；
  - `blender_dump_skinned.py`：从 `.blend` 导出蒙皮网格、骨骼、材质，`--bake` 把程序化材质的底色烘成图；
  - `blender_preview_items.py`：在 Blender 里按 VaM 的规则重建（物品从 `.vab` 的包裹记录重建，morph 可叠加，贴上预设的
    脸和眼睛），渲预览和缩略图。
- Vindictus: Defying Fate 的 Fiona 已装进 VaM（作者 `VindictusDF`）：
  - 四件盔甲 + 头发，直接出现在衣服 / 头发列表里；
  - 体型 morph `Fiona DF Body` 和头部 morph `Fiona DF Head`；
  - 脸部 / 眼睛贴图；
  - 外观预设 `Preset_Fiona DF`，底模 Evey。
- 9-06 那条 `.duf` 路（`import_to_vam.ps1`）保留，它产出的只是创作器的输入。

### 用户如何操作

VaM 里选一个女性 Person → Appearance → Presets → `VindictusDF` → `Preset_Fiona DF`。脱掉盔甲时把 morph
`Fiona DF Body` 调回 0（它是只为穿盔甲准备的收缩体型）。重新生成或换角色见 `scripts/vam/README.md` §9：
先跑 `blender_dump_skinned.py`（带 `--bake <眼球材质>`），再跑 `python bring_to_vam.py --profile fiona_df --install`。

### 实现原理与坑

- **物品格式**：`.vab` 的接缝映射表是三元组；包裹记录是「三角形 + 三个顶点 + 法线/切向框架里的 6 个系数」，三角形按
  Unity 子网格顺序编号。本机 224 件不带布料模拟的物品用 `write_vab` 重写，与原文件逐字节一致。
- **静止体 morph**：盔甲往外推会把硬甲片推瘪、裙甲外翻，所以反过来把 G2F 往里收到每件衣服的间隙以内，存成
  `Fiona DF Body`，物品对着它算包裹，预设开到 1，盔甲原样重建。
  - 收缩上限按皮肤材质分部位，并按到骨轴的距离封顶。
  - 衣服点固定在起始身体的三角形上，大三角形内部也加采样点。
  - 皮肤这一侧也要查：衣服点只推它锚定的三角形，乳头尖旁边的乳晕原本还在胸甲前面 17 mm。
  - 收缩方向用平滑过的法线场；耳朵最多收 3 mm。
- **包裹记录的朝向**（修了第一阶段的 bug）：记录的法线按皮肤顶点法线定朝向，VaM 是在当时的身体上定的。
  - 静止体收得深，部分三角形翻面或与顶点法线接近垂直，用基础身体法线算的记录在 VaM 里朝向反了。
  - 第一阶段装进去的五件共 952 个顶点被甩到皮肤另一侧（最远 20 cm），耳边头发炸开就是它。
  - 现在按静止体自己的法线算，并只锚在三种形状下朝向都明确的三角形上；流程最后用写出去的 `.vmb` 和 `.vab` 自检。
- **脸按地标来**（9-06 试过最近点投影，会把鼻子剪掉）。
  - 步骤：G2F 从材质岛找地标、Fiona 用 MetaHuman 的 `FACIAL_*` 骨 → 相似变换（保留 VaM 的头大小）→ 薄板样条
    → 由粗到细的表面贴合。
  - 贴合的三条护栏：
    - 朝向差超过 60° 的点对不拉（否则嘴唇翻折）；
    - 耳朵不拉，跟着周围走（投上去会皱成一团）；
    - 最后把翻面处的位移调和平均清零。
  - 睫毛、泪线、口腔跟着附近皮肤走。眼球整体平移，morph 里写 `lEye/rEye` 的 BoneCenter（已拿作者们的 morph 标定：
    米、VaM 轴）。
- **脸部贴图**：烘到 G2F 的 Face/Lips/Nostrils 上，每个像素取 Fiona 皮肤的最近点、按她的 UV 采色。
  - Fiona 在发际线上画的深棕「发底」换成底模皮肤并羽化，否则金发下露黑发根。
  - 外缘一圈把颜色过渡到底模的：脸在耳朵、脖子、头皮处接的是 Evey 的躯干贴图。
  - 眉毛发片在 G2F 的 UV 空间里重新光栅化，按 ODI 覆盖率叠上。
  - 虹膜：Fiona 的眼球材质是程序化的，先用 Cycles 烘出底色，再按「瞳孔边 → 虹膜外缘」的半径映射进底模的眼睛贴图。
- **最近三角形搜索**：2048 贴图一次查 290 万个点，现在分块，不分块要 3.5 GB。密网格的格子用 1.5 倍中位边长，与 64 候选
  暴力搜索逐点一致，快约 4 倍。
- **顺手修的旧文档**：本文件 TFD 与 ROE 两节有六行路径（`D:\tfd_exports\blend`、`scripts\firstdescendant`、`.\find_aes_key.py`、`\aes_key.txt`、
  `D:\roe_exports\j01\blend`）在早先写入时，反斜杠转义被吃成了制表 / 退格 / 换页 / 响铃 / 回车字符，已改回。

### 验证

- **写出与自检**
  - `write_vab` 对本机 224 件物品逐字节一致。
  - 流程末尾的自检：用写出去的两个 `.vmb` 叠出身体、从 `.vab` 重建五件，全部在 0.3 mm 表面偏移之外
    ≤ 0.002 mm。同一检查对第一阶段装进 VaM 的版本报出 952 个顶点偏出 5 mm 以上。
- **头部拟合**
  - 地标残差中位 3.3 mm，表面贴合后中位 0.04 mm。
  - 脸、嘴唇、鼻孔、耳朵、头皮、睫毛、脖子全部 0 翻面；耳朵边长比最大 2.4，改前 11.6。
  - 头部 morph 8836 个顶点。
- **脸部贴图**：290 万个像素到 Fiona 皮肤中位 0.15 mm；眉毛 3592 片全部贴皮。
- **胸甲遮挡**：从正面看，194 个乳头顶点全部被挡住；改前有 50 个露在外面，最远 17 mm。
- **Blender 预览目检**：全身正 / 侧 / 背、头、脸三个角度、手 / 胸 / 脚特写，按 VaM 规则重建、贴预设贴图。
  - 头发不再炸开，耳朵干净。
  - 胸甲不透肉。
  - 虹膜是 Fiona 的绿褐色，眉毛、疤、痣都在。
- **已知问题**：靴子为高跟设计，脚趾从护脚甲前端下露出。
- **尚未在 VaM 里亲眼看过。**

## 2026-09-25 — Stellar Blade：Gantz Reika（CNS mod）导出 + PMX 头发物理修复 + 画廊列出 XPS / PMX

### 新增 / 变化

- 装上 Nexus mod 3561「Gantz Reika (CNS)」（Hawkins）：`SB\Content\Paks\~mods\Hawkins_GantzReika\`。这是 CNS 类 mod，
  新增一套服装、不顶替原版；游戏里要看到还得装 UE4SS for Stellar Blade 与 CNS（mod 1496）。
- 两个版本（A 全套战斗服、B 露肤版）导出 Blender（`packages\Eve_Mod_GantzReika_A|B\`）、XPS（`xps\…`）、PMX（`pmx\…`）。
- `build_standalone.py`：`_ORM` 与 `_ARM` 同样处理（G 粗糙 / B 金属），皮肤 `_ORSS` 取 G 作粗糙度，`Emissive` 接自发光。
- `export_pmx_blender.py` 修两处头发物理（`anchor_hub_roots()`、`release_rest_overlaps()`），Vindictus Fiona 与 Gantz A / B 全部重导。
- 新增 `preview_pmx_blender.py`：带物理导回 PMX，出 `preview.png` / `_morphs` / `_gaze` / `_dance`，并报告静止 60 帧的链根漂移。
- 画廊卡片列出 XPS / PMX 路径和四张回读预览链接，附录新增「Nexus 服装 mod → Blender / XPS / MMD」一节。

### 用户如何操作

见 `scripts/stellarblade/README.md`「Nexus 服装 Mod」（含 CNS 小节）与「导出 MMD（PMX）」；PMX 导完再跑一次
`preview_pmx_blender.py` 看四张预览。

### 实现原理与坑

- CNS mod 的资源在 `/Game/OutfitMods/<名>/`，`*.dekcns.json` 的 `OutfitPaths` 列出各变体网格；UE Viewer 照常导，
  每个变体按普通服装组装（网格只到脖子，用 Eve 的 Face_003 + 发型 + 马尾）。
- 头皮头发的根骨 `Hair_Root`（「頭」下，带 4 条刘海 + 2 条侧发链）被 mmd_cloth_physics 建成纯物理刚体，不动站着 60 帧就沉
  12 cm、跳舞时像光头 → 「父骨固定、自己动态、下面 ≥2 条动态链」的分叉根改成跟随骨骼（马尾第一节 `Ab-TL-HairB01` 同理）。
- 马尾上段的 `HairTail_Root` 静止时就嵌在头部碰撞球里 9.1–9.4 cm，一开物理就被顶开 → 静止时嵌进会碰撞的跟随骨骼碰撞体
  超过 2 mm 的动态刚体，把那个碰撞组加进它的不碰撞列表。
- 预览的坑：`import_vmd(margin=0)` 让第一帧从静止姿势直接跳到舞蹈姿势，关节把每条头发链猛拽一下，之后整段都像头发坏了
  （刘海翻上头顶、马尾甩离头部），模型本身没问题；预览改用 30 帧 margin。Fiona 第一版的舞蹈预览其实已经拍到光头，当时没看出来。

### 验证

三个 PMX：撕裂 0、付与顺序违规 0、权重空洞 0、`stray_recipients` 空、26 个 MMD 表情；导回 Blender 静止 60 帧链根最大漂移
1.1 cm（修前 12 cm），跳舞 4 帧、12 个表情、5 个视线方向目检。Gantz 两版 XPS 用 `xpsdump.py` 回读 verify OK；
两版组装、重接材质都 0 缺图。

## 2026-09-25 — NARAKA: BLADEPOINT（永劫无间）：模型列表 + 导出脚本

### 新增 / 变化

- 新增 `scripts/naraka/`：`list_models.py` 按清单列出 3,578 个可导出模型（29 位英雄的 834 套外观、643 款发型、175 个怪物 /
  NPC、1,526 把武器……），可按组 / 家族 / 英雄 / 关键词筛选，出 CSV / JSON / HTML 画廊；`export_model.py` 把外观 + 配套发型 +
  默认脸拼成 `.blend`（+ FBX）并渲预览，怪物、NPC、武器、单件发型同样能导。
- 文档：`scripts/naraka/README.md`（用法、家族 ↔ 英雄表）、`docs/naraka-bladepoint-extraction.md`（原理与坑）。

### 用户如何操作

`python scripts\naraka\list_models.py`（摘要，`--hero 宁红夜`、`--html` …），
`python scripts\naraka\export_model.py --outfit ch_f_ming_haikou_lv_s0`（`--family` / `--all-outfits` / `--prefab` 批量）。

### 实现原理与坑

- bundle 是改了头的 UnityFS：签名 `15 1E 1C 0D 0D 23 21 00`、压缩编号 6 = LZ4、数据块 4 KB 对齐、头部尺寸带偏移，不加密。
  按需解压（一套外观要拉约 200 个 bundle，公共包最大 1.7 GB）；`AppRes.info` 清单给出哈希文件 ↔ 资源路径。
- UnityPy 的 Mesh 类读这个游戏会报错，顶点流从 typetree 自己解。
- 外观网格的骨骼按「变换路径的 CRC32」对到骨架 `ch_dummy_body`；散装骨（胸、裙、飘带）按哈希或绑定姿势找父骨
  （先比位置：飘带链存的是甩起来的姿势）；发型和脸是运行时网格（`AvatarFaceMeshData`），按绑定姿势自上而下认骨。
- 发色取 `hair_custom_data` 的 `BaseColorA`（与游戏物品图标核对过），`_MainSHMap` 不是颜色；虹膜、眉毛贴花按着色器参数
  烘进贴图；`_NormalBentMap` 当普通法线会满脸斑块；`*_cb` / `*_cf` 双层布料按游戏的剔除设置处理。
- 家族 ↔ 英雄：29 位英雄（`herocareerdata_img`），开服 6 位的家族按外观系列命名（mangjianke = 宁红夜 …），
  由英雄选择图标和同时带两个名字的资源路径确定；另 6 位只确认了拼音。

### 验证

32 个外观家族各一套 + 石狼、金色狂战士、宋兵 + 两把武器 + 一款默认发型，共 40 个导出，全部 0 根未解析骨，预览逐个目检；
清单解析出的 12,818 个 bundle 与磁盘一一对应、目录全部能解。

## 2026-09-25 — Stellar Blade PMX：眼睛（眼球骨 + 视线 + MMD 下的眼神光与阴影）

### 新增 / 变化

- `export_pmx_blender.py` 给 Eve 加上眼球骨：每个眼球的旋转中心建 `Bip001 L/R Eye`，眼球顶点改绑上去，
  转换后成为 `左目 / 右目`，ROE 流程自动补 `両目`——MMD 的视线动作和手动调视线从此生效（之前完全不起作用）。
- 眼球材质按 MMD 渲染器的习惯处理：不接收/不投射自阴影、单面、加一张加算 sphere 眼神光；完全透明的
  `EyeLight_Inst` 高光片改为不透明度 0，不再是一块挡在眼前、还会投影的隐形片。
- 成品目录多一张 `preview_gaze.png`（正视、左、右、上、下）。

### 用户如何操作

重跑 `export_pmx_blender.py`；`D:\stellarblade_exports\pmx\Eve_Mod_VindictusFiona\` 已更新。

### 实现原理与坑

- 眼球是头网格里两个独立的球，802 顶点、直径 3.6 cm，100% 绑在头骨上。旋转中心取「后缘往前一个半径」，
  包围盒中心会被角膜顶偏。骨名故意用 `Bip001 L/R Eye`：ROE 解析器本来就把这个写法映射到眼睛槽位，
  其余（改名、両目、付与、变形层级）全走现成代码。
- 对照原版渲染：烘焙出来的虹膜大小和原版一致（UV 半径 0.07），差在 MMD 没有法线贴图和镜面高光，瞳孔成了
  纯黑的洞、眼睛没神；MMD 给眼睛提亮的标准做法是 sphere 贴图。第一版光斑放在视线轴外约 30°、σ 0.045，
  那里眼球法线几乎不变，一颗光斑铺成一层白雾盖住虹膜；改成轴旁的小光斑（σ 0.018）后才像眼神光。
- 顺带确认：「来杯好茶」这段舞蹈的 両目/左目/右目 只有一帧静止关键帧，这段舞本身不动眼睛。

### 验证

文件级：`両目`（层级 0）→ `左目/右目`（付与 1.0、层级 1）、付与顺序违规 0；眼球材质自阴影关、单面、sphere 加算。
导回 Blender 转 `両目`：正视 / 左右 20° / 上下 15° 五张近景目检，两眼同步、虹膜不穿出眼眶；
改前改后近景对照。其余指标不变：两臂 37.3°、撕裂 0、乱接权重 0、胸部物理照旧。

## 2026-09-25 — Stellar Blade PMX：补上胸部物理，修掉脖子上的「肤色领子」

### 新增 / 变化

- `export_pmx_blender.py` 新增胸部物理：Eve 的胸部蒙皮骨 `Ab-L/R-Breast` 填进胸部槽位 → 改名 `左胸 / 右胸`，
  `add_breast_physics()` 每边一个球形刚体（蒙皮加权重心、半径按蒙皮实测约 5 cm、模式「物理+骨骼位置对齐」、
  第 15 组不碰撞）+ 一个带角度限制和回弹弹簧的关节（在骨头起点，胸廓内），拴到上半身刚体。参数在 `BUST`。
- 修掉转换时的权重乱分：脖子和领口 94 个顶点被分给了一个不跟头走的注视挂点骨，跳舞转头时拉成一圈肤色的扁「领子」。

### 用户如何操作

同上一条，重跑 `export_pmx_blender.py` 即可；`D:\stellarblade_exports\pmx\Eve_Mod_VindictusFiona\` 已更新。

### 实现原理与坑

- **为什么原来没有胸部物理**：Eve 的胸部骨挂在 UE AnimDynamics 的四节短链末端，名字 ROE 解析器不认；更根本的是
  整条工具链里没有建胸部物理的环节——Convert_to_MMD5 只把胸部槽位改名，原版的物理部分没搬过来。
- **「领子」的成因**：Convert_to_MMD5 退役辅助骨时，把权重交给「起点最近、且是变形骨」的骨，而 PSK 导进来的骨全是
  变形骨。`Ab-NeckSub` 的权重（23.6，一分不差）落到了挂在 Root 下的 `Sc_LookAtTarget` 上。ROE 那道
  「原来没权重的骨接了权重」检查没拦住，因为这些顶点原来的骨已被退役。
- 修法三层：① 不带自身蒙皮的非 Biped 骨一律标成非变形（111 根，只影响「能不能接权重」）；② 用 Convert_to_MMD5
  自己的分类器预判会被退役的脊柱辅助骨（`Ab-NeckSub`、`Ab-*-Shoulder0`、`Ab-*-Trape0`），转换前把权重并进父骨——
  没有 UE 驱动时它们本来就跟父骨僵硬地动，这是静止等价；否则还有一部分会落到受物理驱动的侧发骨上；
  ③ 转换后审计 `stray_recipients`（原来没权重、现在有了的骨），必须为空。
- 第一版只排除「整棵子树都没权重」的骨，胸部短链里零权重的 `Ab-L-Breast-Link`（子骨有蒙皮）就接走了胸大肌辅助骨的
  权重——它不受物理驱动，那片皮肤会在胸部甩动时停在原地。所以规则收紧到「自身没蒙皮」。

### 验证

导回 Blender（带物理并 build）套「来杯好茶」570 帧：`胸.L / 胸.R` 都由刚体驱动，相对上半身偏转平均 5.6° / 3.7°、
最大 19° / 12°（关节限制内）、约 80% 的帧在动；摆幅最大一帧的正面、侧面、四分之三侧面近景目检：胸部与上胸交界无折痕，
脖子与领口干净。审计：退役辅助骨 0、乱接权重的骨 0；两臂 37.3°、撕裂 0、付与顺序违规 0。

## 2026-09-25 — Stellar Blade：Eve（Vindictus Fiona）导出 MMD PMX

### 新增 / 变化

- 新增 `scripts/stellarblade/export_pmx_blender.py`：任何一个组装好的 Eve `.blend` → MMD 用的 PMX
  （`.pmx` + 相对路径的 `textures\` + 三张预览 + `_converted.blend`）。骨架转换**按函数复用** Rise of Eros
  的 PMX worker（槽位、辅助骨付与、37° A-pose、Convert_to_MMD5、碰撞体、`mmd_cloth_physics`、撕裂检查、
  12.5 倍导出、付与顺序检查），只加 Eve 专属的准备和材质、表情两步。
- 首个产物：`D:\stellarblade_exports\pmx\Eve_Mod_VindictusFiona\`（模型名 `Eve Vindictus Fiona`，说明里写明
  mod 作者 zdimwit 与出处）。

### 用户如何操作

见 `scripts/stellarblade/README.md`「导出 MMD（PMX）」一节，一条 Blender 命令。

### 实现原理与坑

- **骨名连字符**：Eve 的 Biped 骨叫 `Bip001-L-Clavicle`，ROE 解析器和 Convert_to_MMD5 只认空格写法 → 改名。
- **朝向**：PSK 导进来人面朝 ±X，A-pose 绕世界 Y 轴放手臂 → 绕错轴把手臂拧成 57°/49°，MMD 里人也是侧着的。
  按两只脚的脚尖方向转成面朝 -Y（只看一只脚有约 10° 外八偏差）。
- **整个人被缩小 10 倍**：UE 挂点骨离身体几米到几十米（无人机起点 6 m、`FX_GunFire_Rail_End` 在地下 22 m），
  Convert_to_MMD5「骨架高于 10 m 当厘米模型处理」的保护误触发。转换前删掉无权重、伸出身体包围盒的骨（22 根）。
- **材质**：mmd_tools 每个材质只留一张贴图，节点算颜色的材质全拿错了（头发拿到灰度遮罩成了灰白色、程序虹膜全黑、
  口腔灰色）；半透明辅助壳写成不透明，眼周一圈白、嘴里一片白。转换**前**用 blender2xps 烘焙节点颜色
  （转换后材质多了 MMD 着色器组，blender2xps 会跳过），辅助壳 alpha 0，漫反射 1 / 环境 0.5 / 低高光。
- **表情**：脸是 ARKit 52 形态键、没有脸骨，由 ARKit 形态按配方混出 26 个 MMD 标准顶点表情，ARKit 原形态一并导出，
  标准表情排在表情面板最前。

### 验证

文件级：高 21.7 单位、310 骨、22 材质、15 张贴图全部是相对路径且都在、79 表情、54 刚体 / 38 关节；两臂 37.3°、
权重空洞 0、撕裂 0、付与顺序违规 0。导回 Blender（mmd_tools，带物理并 build）套「来杯好茶」VMD：正面朝向、
五个舞蹈帧的四肢和胯部、后颈马尾根部、12 个表情（左右眼方向）逐张目检。

## 2026-09-24 — HoneySelect 2 (Libido DX)：模型列表 + 导出（单件 / 底模 / 角色卡，直接读 bundle）

### 新增

- `scripts/honeyselect2/list_models.py`：列出男女底模、31 类共 812 件带网格的物品（脸型 / 衣服 / 头发 /
  饰品）和 `UserData\chara` 的 15 张角色卡（每张穿戴了什么）；`--category/--group/--search/--sex` 筛选，
  `--json/--csv` 导出清单，`--html` 生成带 812 张游戏缩略图、可搜索的列表页，`--exported` 标出已导出的。
- `scripts/honeyselect2/export_model.py`：`--item fo_top:28`（单件，自带骨骼；`--with-body` 穿在底模上）、
  `--body female|male`、`--card <卡>`（`--nude` 去掉衣服和饰品）、`--all-cards`、`--all-items --group/--category`；
  产物 `D:\hs2_exports\{cards,bodies,items}\…\<名>.blend` + 正面 / 3/4 / 脸部预览（`--fbx` 另出 FBX）。
- `build_blend.py`（Blender 3.6 无头）、`hs2_data.py`（清单 / 依赖 / 角色卡）、`hs2_bundle.py`（prefab 拼装与
  蒙皮烘焙）、`hs2_msgpack.py`（免装 msgpack）。
- 画廊 `scripts/honeyselect2/html/make_gallery.py` → `html/index.html`：按角色卡·穿好 / 角色卡·裸 / 底模 / 单件
  分类、可搜索，每张卡片有正面 / 3/4 / 脸部预览、组成物品、规格、`.blend` 链接；缩略图写在
  `D:\hs2_exports\_gallery\thumbs`，页面只用 `file://`，游戏素材不进仓库。

### 用户操作

```bash
cd scripts\honeyselect2
python list_models.py                 # 看有什么
python list_models.py --html          # 缩略图列表 D:\hs2_exports\_list\index.html
python export_model.py --card HS2_ill_F_000 [--nude]
python export_model.py --item so_hair_b:9 --item ao_glasses:0
```

### 实现原理

物品清单是 `list\characustom` 里 MessagePack 编码的 `ChaListData`（`MainAB` + `MainData` = 包 + prefab）；
角色卡是 PNG 后的 `【AIS_Chara】` 块。按游戏的拼法：骨架 `p_cf_anim`（男女共用，身体挂点都在它上面），身体网格、
脸、衣服的骨骼拷贝按名字并上去，头骨挂 `cf_J_Head_s`、头发挂 `N_hair_Root`、饰品挂 `N_*`；每个蒙皮顶点按
`Σ w·(World×BindPose)·v` 烘到静止姿势。材质按贴图通道重建：衣服分色遮罩在清单 `ColorMaskTex` 里（黑 = 颜色 1、
R/G/B = 颜色 2/3/4），头发主贴图不带颜色（颜色全来自卡），眉毛 / 乳晕 / 阴毛走脸与身体的 UV1 / UV2，颜色一律
sRGB→线性。详见 [HoneySelect 2 提取](honey-select-2-extraction.md)。

### 验证

15 张角色卡穿好 + 裸、男女底模、31 类各第一件单独导出（外加 `--with-body` 抽测）全部 PASS、无警告，每份
约 3–7 秒；逐张看了预览。修过的问题：颜色没转线性（整体发白）、只读 R 的眉毛遮罩在脸上盖出暗色矩形、
眼睑影子壳被当成白色眼影、prefab 根存成 inactive 导致整件为空、内置 Sphere 网格、饰品挂点缺失（改用
`p_cf_anim`）、卡里饰品位移单位是 0.1（F_007 的鞭子原先飘在 60 cm 外）。体型滑块、衣服图案、脸部妆、衣服下的身体遮罩未做。

---

## 2026-09-24 — Stellar Blade：Nexus Mod「Vindictus Fiona」装进游戏并导出 Blender

### 新增 / 变化

- 新增 `scripts/stellarblade/build_standalone.py`：按 UE Viewer 的 `.mat` 精确重建一个网格的材质
  （Diffuse / Normal / ARM；镂空按 alpha 实际数值判断；纯黑代理槽拆成隐藏对象）。两种用法：
  `--psk` 单独出一个自带整颗头的 Mod 网格；`--blend ... --object Eve_Body_Mesh_01` 给
  `validate_eve.py` 组装好的场景只重做服装网格的材质。
- 装了 [mods/1145](https://www.nexusmods.com/stellarblade/mods/1145)（zdimwit）到 `~mods`：它顶替
  **CH_P_EVE_09（Planet Diving Suit 7th）**，外加 16 / 21 的几个材质实例。以后导原版 09 前要先挪开。

### 用户如何操作

见 `scripts/stellarblade/README.md`「Nexus 服装 Mod」一节（六步）。

### 实现原理与坑

- Mod 的 `face` 槽只是脖子过渡、`head` 槽是发冠——游戏里仍是 Eve 的脸和马尾，所以按普通服装组装；
  第一次把它当整人单独出，得到的是一个没头的人。
- `validate_eve.py` 按材质名猜贴图，碰到 `body` / `amt` 这种通用名会猜错（腿上黄粉花纹、裙子全黑）；
  改由 `.mat` 精确接图。
- Biped 骨名带连字符（`Bip001-L-Toe0`），按 `endswith("L Toe0")` 找不到脚趾，前方判错，渲出来是侧身。

### 验证

正身与脸部预览目检：Eve 的脸、马尾与 Mod 的发冠、耳坠、项链、白色仙女裙、蕾丝手套、臂环、粉色高跟
对位正确；`package_outfits.py` 打包 377 MB，30 张贴图全部在包内。

## 2026-09-19 — The First Descendant：睫毛和眉毛（一圈白睫毛的三个成因）

### 新增 / 变化

Nell 的脸上是一圈放射状的白睫毛。查下来是三件独立的事叠在一起，都修了，14 个模型重跑：

- `resolve_textures.py`：眉/睫的材质实例把 `texture` 参数显式置为 **None**，发丝图是从母材质继承的，
  所以它的 zen 名字表里**一张贴图都没有**。现在按材质名给这类槽补上母材质共享的
  `T_eyelash2_D` / `T_eyebrow_d`（`PARENT_ATLAS`）。
- `build_blend.py`：**`fresnel_col` 不是发丝颜色**，是掠射角的边缘染色。多数角色它恰好是深棕
  （看不出问题），但 Gley/Nell 的睫毛是 `(1.0, 0.783, 0.568)`、Bunny/Hailey 的眉毛是
  `(1.0, 0.672, 0.672)` —— 当底色用就是一圈亮桃色的毛。发丝底色写死在母材质里读不到，
  改成：**睫毛恒为近黑**，**眉毛取本角色的 `Hair_RootColor`**（一个模型有两套头发时取最暗的那套）。
- `build_blend.py`：这两张发丝图的**形状在 alpha 通道里**，RGB 是一张几乎均匀的灰卡
  （`T_eyebrow_d` 的 RGB 均值 180、alpha 均值 6）。原来接的是 Color → Alpha，
  整块面片就有了七成不透明度，眉毛变成一坨实心楔子。现在接 **Alpha → Alpha**。

### 用户如何操作

```
.\export_model.ps1 <模型> -Force
```

或者只重跑贴图和 Blender：删掉该模型目录下的 `materials.json` 和 `<id>.blend` 再跑一次。

### 实现原理与坑

三件事都只有**看渲染结果**才发现得了：材质实例的参数表是「对的」（`Lash Opacity`、`OpacityPower`
都在），贴图也「没缺」——但一个是继承来的贴图根本没进名字表，一个是参数名望文生义用错了，
一个是通道用错了。`missing_textures` 全空不代表材质就对。

### 验证

14 个模型重跑，逐张看脸部预览：Nell 的白睫毛没了，眉毛跟头发一样黑、是细发丝不是黑块；
Viessa / Serena 的浅色眉毛仍然是浅的（取自各自的发根色），Harris 是暗红眉，Ines 是铂金眉；
Bunny 和 Hailey 原来的亮粉色眉毛也一起修好了（Bunny 的被头盔挡着，之前没看出来）。

## 2026-09-19 — The First Descendant：12 个女性后裔批量导出 + 一页 HTML 画廊

### 新增 / 变化

- **批量导完 12 个女性后裔**（Viessa、Bunny、Freyna、Gley、Sharen、Valby、Luna、Hailey、Ines、
  Serena、Nell、Harris），加上之前的皮肤 Bunny_CMN_001 和怪 MOB_CMN_1001_A001，共 14 个模型
  落在 `D:\tfd_exports\blend\<id>\`。
- `scripts/firstdescendant/html/`（新）：`collect_manifest.py` 读每个模型的 `build.log`
  （`TFD_REPORT=` 那行）汇总成 manifest，`make_gallery.py` 出自包含的 `index.html` ——
  每个模型一张卡片（正身预览 + 圆形脸部小图、骨骼/顶点/材质/贴图统计、说明、blend 路径一键复制），
  顶部按 kind / 体型筛选 + 全文搜索 + 只看告警，末尾附完整的手工导出教程。和其它游戏的画廊同一套式样。
- 顺手修了几个让材质 / 预览出错的问题：预览分辨率、槽名识别、假的「贴图没解析到」、
  镜片的抖动噪点、日志编码（见下）。

### 用户如何操作

```
foreach ($id in 'Viessa','Bunny','Freyna','Gley','Sharen','Valby','Luna','Hailey','Ines','Serena','Nell','Harris') {
    .\export_model.ps1 $id
}
cd .\html
python .\collect_manifest.py
python .\make_gallery.py
```

只想重跑贴图和 Blender、不重导网格：删掉模型目录下的 `materials.json` 和 `<id>.blend` 再跑一次。

### 实现原理与坑

- **预览图分辨率一直没设过**：`build_blend.py` 的 `render()` 收了个 `size` 参数却只拿它算
  `clip_end`，结果每张预览都是场景默认的 1920×1080，竖着的人像被塞进宽幅中间一条，
  两侧全是空白。现在 `size` 真的写进 `resolution_x/y`（正身 900×1400、脸 900×900），
  `clip_end` 改用相机距离算。
- **游戏方的命名不统一，按名字判类型会漏**，三处都是实打实的错，不是洁癖：
  1. `_Ml`（小写 L）是 `_MI` 的笔误，Gley、Harris 整套都这么写；
  2. 贴图后缀可以多一位数字——Gley 的脸部颜色图叫 `PC_007_A0101_Face_C1`，
     `TEXTURE_RE` 和 `pick()` 都只认严格后缀，于是**她和 Nell 的脸整张没有颜色**（渲出来是白的）；
  3. 槽名里可以夹序号：`PC_018_A_EYE_000_MI`（Ines）、`PC_021_A0101_Eye_Ml`（Harris）
     按 `_eye_mi$` 判不出是眼球，被当成布料 → 现在另加「有 `Sclera` 贴图就是眼球」这条数据判据。
  顺带：`Fur` 也是眉毛（贴 `T_eyebrow_d`），`Eyeleash` 是睫毛的另一种拼法。
- **「没解析到的贴图」以前有一半是假警报**：材质名字表里那些看着像贴图名的参数
  （`Face_Dyed_Mask` 之类），容器里根本没有同名包。现在凡是找不到包的一律当参数名丢掉，
  只有「包在、PNG 没解出来」才算 missing——刷新后 14 个模型的 missing 全为空。
- 蕾丝类材质（Serena 的 `PC_019_A_Body_000_Lace_Ml`）没有颜色图，只有 `_Alpha` + `_N`，
  颜色来自参数 `Col_A`；单独走一条半透明分支，不再按「没有颜色图」当灰布处理。
- **面罩/镜片改用 `BLEND` 而不是 `HASHED`**：EEVEE 的 HASHED 是随机抖动，采样数再高，
  眼睛前面那层镜片也糊成一片磨砂噪点（Gley 的眼镜）。没有镂空遮罩的纯 alpha 材质就该用真混合。
- **`Tee-Object` 写出来的 `build.log` 是 UTF-16**：PowerShell 的 `Select-String` 能认，
  Python 按 UTF-8 读就是一堆乱码，`TFD_REPORT=` 那行永远匹配不上（画廊里一半模型统计全是 0）。
  `export_model.ps1` 改成自己用 UTF-8 写日志，`collect_manifest.py` 也按 BOM 兼容 UTF-16 旧日志。

### 验证

14 个模型全部重跑（贴图 + Blender），14 张正身预览逐张目检：Gley / Nell 的脸恢复肤色和妆容、
Gley 的镜片干净了，Ines / Harris 的眼球是眼球而不是灰片，Serena 的胸口蕾丝透了，Valby 隔着
透明头盔能看见脸，Bunny_CMN_001 的角盔仍在头上，预览构图正常（900×1400 / 脸 900×900）。
画廊页在浏览器里打开过；HTML 标签闭合、70 条 `file://` 链接全部指向存在的文件（脚本校验）。

## 2026-09-19 — The First Descendant：带贴图的导出线（CUE4Parse + 自读 zen 包头）

### 新增 / 变化

上一条只出白模（umodel 解不了 UE5 虚拟贴图）。现在 `scripts/firstdescendant/` 换成 CUE4Parse 路线，
后裔 / 皮肤 / 怪都出**带贴图、带 111 个表情 morph、材质槽名真实**的 `.blend`：

- `export_model.ps1`：网格改由 **CUE4Parse CLI**（`-g GAME_TheFirstDescendant` + 社区 usmap）导 ActorX
  pskx；新增第 3 步 `resolve_textures.py`；Blender 步接收 `materials.json`。
- `resolve_textures.py`（新）：pskx 槽名 → 材质实例包 → 用 **`iostore.py`（新，纯 Python 读容器 +
  zen 包头名字表，不需要 usmap）** 拿到它引用的贴图名 → CUE4Parse 一次解码全部虚拟贴图成 PNG →
  UE Viewer 读材质参数（根/梢发色、自发光色、虹膜参数）。
- `build_blend.py`：按槽名建材质（`_C/_N/_P/_FX`、皮肤、头发根梢渐变、眼睛程序化虹膜、眉睫、
  面罩玻璃、透明壳）；**socket 配件规则**（皮肤 HEAD 的头盔自带三根骨、画在原点 → 骨父级到
  `Bn_Socket_Head`，否则掉在脚边）；贴图拷进 `textures\` 用相对路径。
- `list_models.py`：`find_psk` 优先认 `cue4_exports\M1\Content\<包>.pskx`。

### 用户如何操作

```
.\export_model.ps1 Viessa            # 或 Bunny / Bunny_CMN_001 / MOB_CMN_1001_A001 ...
```

前提多两样：`E:\tools\cue4parse_cli\cue4parse.exe`（joric/CUE4Parse.CLI 0.2.0）和
`E:\tools\tfd\Mappings_2024-07-16_gildor.usmap`。

### 实现原理与坑

- **usmap 来源**：Nexus 的两个映射 mod 已下架（板块只剩壁纸）；现用 Gildor 论坛 TFD 帖第 7 页
  （2024-07-16）网友的 MediaFire `Mappings.usmap`。它能解 Texture2D / 虚拟贴图 / SkeletalMesh，
  **解不了 MaterialInstanceConstant**（`Invalid bool value`）——材质→贴图的链接因此改由自己读
  zen 名字表完成，参数由 UE Viewer 补。用通用 `GAME_UE5_2` 会把贴图解坏，必须用 TFD 专用枚举。
- CUE4Parse 首次运行会自动下载 `oodle-data-shared.dll`（这台机器之前找不到任何 oo2core），
  `iostore.py` 就用它做 Oodle 解压。
- 贴图约定：`_P` = R AO / G 粗糙 / B 金属（皮肤例外，B 恒 255 → 金属度置 0）；`_N` 是 DirectX
  法线要翻绿；打包图 alpha≈0，Blender 里必须 Channel Packed 否则预乘抹黑；`_ID` 是六色染色遮罩，
  默认外观不用；头发共享 `HairTex_*_P`：A 透明度、G 根→梢。
- PowerShell 5.1：CUE4Parse 往 stderr 写日志，`$ErrorActionPreference='Stop'` + `2>&1` 会把第一行
  当成终止错误，调用处临时切 `Continue`。
- Blender：跨 edit-mode 切换后不能再读骨引用（`UnicodeDecodeError`），先拉成普通值。

### 验证

Viessa（622 骨 / 13 槽 / 26 张贴图 / 111 morph）、Bunny、皮肤 Bunny_CMN_001（Body+Head 配件+Face →
504 骨，头盔在头上）、怪 MOB_CMN_1001_A001 全部一条命令跑通，渲图逐个目检：金属/布料/皮肤/头发/
眼睛/眉睫/面罩都对。已知限制：虹膜颜色近似、染色系统未接、usmap 为 2024 版。

## 2026-09-19 — The First Descendant（第一后裔）：查看列表 + 导出脚本

### 新增

`scripts/firstdescendant/`（新目录）：Nexon UE5 扫射游戏 The First Descendant（内部代号 M1）的
模型查看 + 导出。游戏是单个 IoStore 容器（utoc v5 / pak v11 / Oodle / 目录索引 AES 加密）。

- `list_models.py`：解密并读 `*.utoc` 目录索引（复用 scripts/vindictus 的解密器，同为 Nexon UE5），
  编目 **2067 个模型**：33 个后裔（含 Ultimate）、1075 套皮肤、201 怪、54 Boss、99 NPC、250 武器、
  248 配饰、宠物/载具。`--kind` / `--char` / `--resolve` / `--json` / `--raw` 筛选。
- `export_model.ps1` + `build_blend.py`：解析 → UE Viewer(`-game=first`) 导 PSK/PSKX → Blender 合骨架、
  渲预览、存 `.blend`，产物在 `D:\tfd_exports\blend\<id>\`。
- `find_aes_key.py`：从 shipping exe 重建 AES key（Nexon 用8 条 `mov imm32` 运行时拼出，非明文）。

### 用户如何操作

```
cd scripts\firstdescendant
python .\find_aes_key.py --out D:\tfd_exports\_keys\aes_key.txt   # 一次性，~60s
python .\list_models.py --kind descendant
.\export_model.ps1 Bunny
```

### 实现原理与坑

- **贴图是 UE5 虚拟贴图（Virtual Texture），UE Viewer 解不了**（报 `it's a virtual texture` 跳过），
  所以 umodel 这条线只出几何 + 骨架的白模。完整贴图需 FModel + usmap（同 FF7 Rebirth 那条线，未接）。
- 后裔代号 → 名字来自 `PC/MESH/PRESET/<名字>` 文件夹；默认装是一整块合并网格（身体+头+头发+脸），
  导出最干净；皮肤 = `SKIN/<类别>/<序号>/..._(BODY|HEAD)` + 该后裔的 Face。
- 怪/Boss/武器按主网格逐个编目（A001/B001 算不同模型），`Parts/` 归为 extras（`-IncludeExtras` 才带）。
- Blender 坑：跨 edit-mode 切换后不能再读骨引用（会 `UnicodeDecodeError`），合骨前先把骨名/坐标拉成普通值。
- 已知局限：白模；个别皮肤的头部配件（只挂 socket 的小件）会掉在脚边（身体+脸正确）。

### 验证

后裔 Bunny（270 骨 / 111438 顶点，单块合并网格）、皮肤 Bunny_CMN_001（Body+Head+Face → 348 骨）、
怪 MOB_CMN_1001_A001（101 骨）均一条命令跑通，渲图目检。key 已由 find_aes_key.py 重建（只存
`D:\tfd_exports\_keys\aes_key.txt`，不入仓）。

## 2026-09-19 — Rise of Eros：67 套「套装」(suit) 全部拼成独立 .blend（直接读 bundle）

### 新增

- `scripts/riseoferos/suit_bundle.py`：用 UnityPy 直接从存根 `accessory_components_pc_<id>_suit_<suit>.ab`
  + `chara_components_pc_<id>.ab`（+ `chara_components_common.ab`、该套的 `chara_tex_components_*`）读出每个
  部件的网格 / 蒙皮骨名权重 / 放置矩阵 / 渲染器材质真正引用的贴图（`_BaseMap`、`_BumpMap`），贴图从
  bundle 解码，算「穿好」状态；不再经过 AssetStudio 的逐对象 FBX（同名部件互相覆盖、09-12 新套装没提取、
  贴图靠猜名字三个坑）。
- `assemble_suit_blender.py --suit suit.json`：bundle 模式，npz 建网格 + 顶点组绑到底模骨架；静态件烘进世界
  坐标并骨骼父子到最近的 `Bip001` 骨；材质 = 基色 + 法线，无贴图槽用 `_BaseColor`，镜片做玻璃。
- `export_suits.py`：批量驱动（`--list/--only/--exclude/--force/--lanes/--sheet`），产物
  `D:\roe_exports\<id>\blend\pc_<id>_<suit>.blend` + 预览，清单 `_suits\manifest.json`。
- `suit_overrides.json`：「穿好」规则的人工覆盖（7 条，看预览定）。
- 画廊 `html/make_gallery.py` 读 `_suits/manifest.json`：67 张「套装」卡片插在各自角色的卡片后面（底模 + 存根、
  部件数/穿好数、去掉的部件和原因、blend 路径），工具栏加「角色模型 / 套装」筛选，附录加 `export_suits.py` 用法；
  `index.html` 重生成（124 模型 + 67 套装）。

### 实现原理与坑

部件在哪个坐标系里建，数据不说，看了 752 个部件归纳出五种：Z-up 模型空间的蒙皮件（`BoneWorld×BindPose`
转回模型系是单位阵）、Y-up 世界空间的蒙皮件（c01 泳装胸衣，同一公式再乘 `R_x(+90°)`）、带放置变换的静态件
（眼镜/猫耳/翅膀）、按**厘米**建模的配件池道具（魔化的角/光环，`_R` 根是镜像）、只有自带物理骨的配件
（圣诞帽/耳坠/牛尾：bundle 里没挂点，按 `Area` 挂到身体骨，骨的静止矩阵取身体网格 BindPose 的逆——bare 包
里的 Transform 是动作姿势）。每个部件把说得通的读法都算一遍，取质心离该部位骨骼最近的。Unity→Blender 只是
镜像 X（j01 底模逐顶点核对），绕序要反。详见 [ROE 套装拼装](roe-suit-assembly.md)。

### 验证

66 套批量 0 失败（4 路并行，每套 7–17 秒）+ 已有 ProUniform = 67 套；逐角色预览拼图看了五轮、每轮修一类放置
问题；18 条 WARN 全是无基色贴图的槽（fm 的 `FMRear` 1 mm 占位、镜片、乳胶第二层）。XPS/PMX 未接。

## 2026-09-19 — Vindictus: Defying Fate：剩下的 12 个模型（男装、怪物、NPC）全部导出，共 30 个

### 新增

- `scripts/vindictus/build_blend.py` 认得怪物和 NPC 的材质家族（之前只按 Fiona/Lethita 的 `M_PC_*` 写）：
  1. **分层材质 `M_Outfit`**（`Character/public/`，NPC 套装 Swordwind / RoyalArmy，`PCM_001/002/004_Temp`
     男装就是它们）没有基色贴图，颜色是纯色板：`Sub Mat Map` 的 R 选子材质 A（黑）/B（白）、G 选 C，各取
     实例的 `A/B/C L1 Color`；`GDO Map` R 是灰度细节（0.5 中性，×2）、B 是不透明度；有 `Layer Color Map`
     时直接当基色。`T_White_MK` 作 Sub Mat Map 表示整件是 B（手套、头盔）。
  2. **`M_Mob_Base` / `M_Mob_Outfit` / `M_NPC_Outfit`**：参数名 `BaseColor / Opacity`、`ARM / E`；基色乘
     `Basecolor Brightness`（怪物 D 图故意很暗，2–3.5 倍）、按 `Basecolor Saturation` 去饱和、乘 `Basecolor Tint`；
     粗糙度重映射到 `[Roughness Min, Roughness Max]`，金属度乘 `Metallic Intensity`。
  3. **`MA_HairStyle` 毛发卡片**：`Fur_A` R 作 alpha，`Fur_root` 反相驱动 `RootColor → TipColor`，乘
     `Brightness` 但最大通道压到 0.8 以内。
  4. **`M_EyeRefractive` 怪物眼球**直接走 `build_eye()`（同一套 MetaHuman 参数），`M_EyeOcclusion` 走遮蔽壳。
- 单骨部件的挂点规则：那根骨在底骨架里存在就挂那根、带完整 rest 变换（Carminegust 的锤子
  `Anim_Attachment_RH` → 右手，之前躺在脚下）；只有 `root` 的仍挂 `head`（Lethita 头发）。
- `list_models.py` 跳过套装里的整体副本网格（`PCM_001_Temp` 的 `SK_PCM_001_Temp` 把脸、发、五件都合在一起）。
- 画廊 `collect_manifest.py` 补了 12 个模型的说明；`html/index.html` 重生成，30 张卡。

### 验证

- 先 `-NoBlend` 顺序导 26 个包，再 3 路并行 Blender，12 个全部 rc=0，0 贴图未解析。逐张看过预览：
  三套男装（面甲 + 锁子甲、全罩盔板甲、羽饰盔 + 红披风）颜色对；四只豺狼人毛/皮/甲/眼都有色，
  狗头人首领重甲 + 钩爪正常。
- 已知：两只哥布林（同一个 25 万顶点网格）和 `Male_Knight` 在包里**没有材质**（`material_0/1`、顶点色全白），
  是白模；`NPCM_RoyalArmy_sword` 只有一把剑；`Gnoll_Type2_Named_Boss_03` 的弓有自己的 16 根骨，留在原点；
  毛发 `Brightness` 语义没有对照，Carminegust 红毛偏粉。狗头人另外 6 条只有武器，没导。

## 2026-09-19 — Rise of Eros：把「套装」(suit) 拼装成一个模型（林恩·冷艳主管）

### 新增

`suit_parts.py` + `assemble_suit_blender.py`：把一套服装变体（suit）拼成一个带材质、
绑到底模骨架的 `.blend`。ROE 的 suit 不是一个整体 FBX，而是裸体底模 + 头发 +
一堆分开的部件网格（外套/领饰/手套/长袜/高跟/桂冠…），全部蒙皮到同一副骨架。
第一个实例是林恩（`j01`）的 **ProUniform**（冷艳主管职业制服，2026-09-12 更新加入）。

### 用户如何操作

```
.\extract_character.ps1 j01 -ExportTextures
python suit_parts.py --game "<AssetBundles>" --id j01 --suit prouniform
blender --background --factory-startup --python assemble_suit_blender.py --     --root <提取目录> --tex <贴图目录>     --out D:\roe_exports\j01\blend\pc_j01_prouniform.blend     --base pc_j01_nk --parts <逗号分隔部件名> --glb 1
```

产物：`D:\roe_exports\j01\blend\pc_j01_prouniform.blend`（内嵌贴图）+ 三视图预览 + `glb\`。

### 实现原理与坑

- **部件组成**写在存根 `accessory_components_pc_<id>_suit_<suit>.ab`（根 GameObject 用 PPtr
  指向 `chara_components_pc_<id>.ab` 里的真网格）；`suit_parts.py` 解析它列出部件名。
- **部件 FBX 不带材质**，需按部件名去 suit 贴图目录找 `Lynn_<部件>_rgbx_Albedo`。
- **蒙皮部件的顶点在正确模型空间，但物体 `matrix_world` 是错的**（AssetStudio 把四肢
  部件的导出根设成一根肢骨，烘了个多余变换），导入后会飘到离骨头约 1.5 m（手套
  飘到身体正前方）。修法：蒙皮部件丢掉物体变换、重新绑到底模骨架（顶点组名与骨名
  一致）；静态部件（如桂冠，`MeshFilter` 无骨架）相反——保留自己的变换，只挂到骨架下。
- ProUniform 存根列 17 个部件，“穿好”用 13 个，去掉 `EggVibrator`（道具）、`OpenVest`
  （`CloseVest` 的敷开替代态）、`LLaceBra`/`RLaceBra`（乳贴）。完整说明见
  [ROE 套装拼装](roe-suit-assembly.md)。

### 验证

仓库脚本重跑一致复现，`missing=[]`，15 个网格 / 14 张贴图全部打包，三视图逐件目检：
外套/领饰/手套/长袜/高跟/桂冠/吊袜带位置与贴图均正确。目前只出 blend/preview/glb（XPS/PMX 未接），
且只在 j01 ProUniform 上验证过。

## 2026-09-13 — Vindictus: Defying Fate（2024-03 Pre-Alpha）：客户端、AES key、UE Viewer → Blender 流水线

### 客户端从哪来

- 游戏未发售（Steam 商店页写 2027）。2025-06 的 Alpha Demo（Steam `3576170`）测试结束两天后被
  换成 348 MB 空壳，商店页下架、没有 free-on-demand 授权，拿不到；2026-04 的 FGT 只对韩国线下
  和媒体开放。**唯一能下的是 archive.org 的 2024-03-14 Pre-Alpha 客户端**（项目
  `vindictus-defying-fate.-7z`，14.1 GB 7z，md5 `801374e1…`），先用 HTTP Range 只读 7z 头确认是
  完整客户端（478 项 15.8 GB，`Vindictus-Windows.ucas` 15.04 GB），再下。archive.org 直连被墙、
  配置的远程代理只有 33 KB/s，改走本机 Veee 系统代理（`127.0.0.1:15236`）8 连接 ≈ 14 MB/s，
  19.5 分钟下完；解压到 `E:\tools\vindictus`（`Vindictus.exe` 为根），按 7z 头逐项核对大小全部一致。
  下载/校验/安装脚本留在 `E:\tools\vindictus\_download\`，不入库。
- 引擎 UE **5.3**，IoStore（utoc v5）+ Oodle，pak v11，**索引 AES 加密**（key GUID 全 0）。
  没有反作弊，只有 Steamworks dll。

### AES key 怎么来的

- cs.rin.ru 的 key 帖要登录；`Vindictus.exe` 和 `libnative.dll` 里也**没有连续的 32 字节 key**
  （对齐/逐字节全扫 88M 候选都没有）——Nexon 用 8 条 `mov dword [..], imm32` 在运行时拼
  （`.text` 文件偏移 `0x47745EB`）。
- 新脚本 `scripts/vindictus/find_aes_key.py`：先扫连续窗口，再收集 `.text` 里成串的
  imm64×4 / imm32×8 / imm8×32 和成对的 rip 相对 xmm 常量，按顺序（含倒序）拼成候选，用
  `Vindictus-Windows.pak` 加密索引的前 16 字节 AES-256-ECB 试解密，解出挂载点 `../../../` 即命中。
  80 秒找到。key **只放** `E:\tools\vindictus\_download\aes_key.txt`，脚本通过 `VINDICTUS_AES_KEY`
  或 `-AesKeyFile` 读取、经临时文件交给 UE Viewer，仓库/CHANGELOG/画廊里不出现。

### UE Viewer

- spiritovod 的 UE5 specific build（Gildor topic 7906 的 Google Drive `umodel_materials.zip`，
  取其中 `umodel_materials_ue5.exe`，build 1579 based fix282，2026-09-05）放在
  `E:\tools\umodel_specific\materials\`；`-game=ue5.3`，Oodle 内置无需额外 dll，`-png` 直接出 PNG。
  包名用 Content 相对路径（`VindictusRoot/Character/.../SK_xxx`），避开容器里 178 个重名 stem。
- 已知限制（Gildor 8886/8190）：静态网格贴图是 virtual texture 导不出；Nanite 只有基础几何；
  不导 morph target（脸包里的 MetaHuman `DNAAsset` 同样不导）。

### 新增 `scripts/vindictus/`

- `list_models.py`：解密并解析 utoc 目录索引（16,703 条路径），把 SK 网格按游戏拼装方式分成
  36 个模型：player（Fiona、Lethita）、outfit（PCF_001…067 共 13 套女装 + `Player/Outfit/Shiningwill/Mesh`
  下的旧版 Shiningwill 一套（`Shiningwill_legacy`），都配 Fiona 脸/发；PCM_00x_Temp 3 套男装 +
  Lethita 脸/发；PCF→Fiona、PCM→Lethita 由 UE Viewer 加载的
  `SK_PCF/PCM_BaseBody01_Skeleton` 核实）、base（PCM 四件 / `SK_female_base`）、monster（Gnoll /
  Kobold / Goblin 13 个）、npc（2 个）；`--resolve <id> --json` 给出包路径和 PSK 状态。
- `export_model.ps1 <id>`：list → 逐包 umodel → `build_blend.py`，解析 `VINDICTUS_REPORT=`
  打印骨骼/顶点/材质/贴图/警告；`-List/-Force/-NoBlend/-NoPreview/-Smooth/-IncludeWeapons`。
- `build_blend.py`（Blender 3.6 无头，`io_scene_psk_psa` 5.0.6）：
  1. UE Viewer 给每个网格导的是自己的骨架子集（Fiona 脸 658、发 274、上身 531、脚 30……），
     取最多的一副为底按名字补缺、rest 变换照抄，所有网格重绑到一副骨架；共享骨骼 rest 偏差
     写进报告（Fiona 0，Lethita 脸骨架 0.25 cm）。只有一根 `root` 的部件（Lethita 头发）按游戏的
     做法挂到 `head` 骨（bone parent），否则会躺在脚下。
  2. 材质从 `.mat` + `.props.txt` 重建：服装 D/N/ORM|ARM（Opacity 用 alpha 按 UE Masked 1/3
     裁切）、皮肤 D×Basecolor Tint、头发 ODI.R 透明 + FR.B 驱动 Root/Mid/Tip 渐变、眉睫 ODI.R、
     眼球 = 巩膜 + 虹膜遮罩（`T_PC_Iris_A_M`：1-B 虹膜环、R 瞳孔，UV 以中心 ×2 采样）+ 在
     `T_PC_Iris_color_picker` 上按实例 `IrisColor1/2 U,V` 采样的虹膜色、眼部遮蔽壳/泪线/假反射片
     半透明。
  3. 贴图复制到 `textures\`、相对路径保存；预览相机不写死 +X——UE 骨骼网格资源朝 -Y，
     用 `foot→ball`（Biped 用 `Bip001_*_Foot→Toe0`）骨方向判断朝向。
  4. 部件绑在另一版骨架上的（8 套服装的 Head 脊柱链差 6.9 cm，Shiningwill 旧版差 6 cm）先把自己的
     骨架摆到底骨架的 rest 姿势再烘焙（等价于运行时蒙皮），再并入；只有一根 `root` 的部件（Lethita
     头发）挂到 `head` 骨。默认头发只在 Head 部件带头发材质或 `HEAD_REPLACES_HAIR`（PCF_067）时
     隐藏——项链/耳机/帽子/发带/发冠都不隐藏；几何启发式分不开耳机和发型，所以用表。
  5. `Shiningwill_legacy`（用户反馈「没有面部」）：旧装的 Biped 骨架（`Root → Bip001_*`）合并进
     Fiona 脸骨架后是第二棵根子树，而且它的朝向和 UE 骨架差 90°——身体侧着、脸朝前。加
     `align_secondary_hierarchies()`：第二棵根子树连同绑在上面的网格按脚趾方向转到 UE 朝向、按
     `Bip001_Head`→`head` 平移对齐；旧装自带的旧发型盖住新脸的眼睛，改成隐藏旧发型、保留默认头发。
     ——第一版用 `Vector.angle_signed`（顺时针为正）配 `Matrix.Rotation`（逆时针为正），转反了，
     Shiningwill 旧版看着「正面」其实是背面；改用 `atan2` 差值，并在日志里打印转正后的朝向核对。
  6. 基础身体（用户要求导出 `Fiona_BaseBody` / `PCM_BaseBody`）：Fiona 的素体是名字带 `SM_` 的
     SkeletalMesh `SM_pc_fiona_basebody`（`SK_female_base` 是 Skeleton），旧版 Biped 骨架、自带旧头，
     转正后把 `Bip001_Head/Neck` 权重的旧头切掉换成现在的脸；Lethita 的 `MI_EyeShell01`（无贴图的
     眼影壳）原来落到默认白色 PBR 变成白眼球，归入遮蔽壳。顺带发现 `"rma"` 子串匹配到 `Normal Map`
     把法线当 ORM 接进去（金属度 1）：PCF_012「银裙」、素体的古铜皮肤都是这个 bug，改整词匹配后重建。
  7. 眼睛重做（用户反馈「眼睛暗淡」）：原来把 `T_Iris_A_M` 的 B 通道当虹膜遮罩，其实 B 是径向渐变、
     G 是纤维、alpha 才是瞳孔，而且从色板采到的 `IrisColor` 是 sRGB 值直接塞进了线性颜色口——虹膜
     成了一团发白的雾。现在 `build_eye()`：UV 中心半径 0.2 的程序化虹膜盘，两色沿半径渐变
     （色板采样转线性 × `IrisBrightness` × 1.35）× 纤维 × limbus 变暗，瞳孔半径 0.32×`PupilScale`，
     巩膜 × 血丝，粗糙度 0.12；`M_PC_Skin_Eye`（Lethita，`Iris Color Inner/Outer` + `T_EyeMap01`）
     走同一套。遮蔽壳 0.25→0.12。半径 0.17/0.2/0.22、亮度 3/4/5 用 `eye_lab.py` 渲染对比后定的。
- `README.md`：环境、key 规矩、三个脚本、材质映射表、限制、验证。
- `html/collect_manifest.py` + `html/make_gallery.py` → `html/index.html`：和其它游戏同一套画廊
  （`file://` 缩略图落在导出根的 `_gallery\thumbs`，manifest 只有路径和统计）。卡片带类型/身体/
  隐藏头发/重定位/告警徽章，可按类型、身体筛选和搜索；底部是完整手工导出教程（客户端来源、
  key 计算、脚本、批量、参数、坑）。16 张卡片，用无头 Edge 截图核过版式。

### 验证

- `Fiona`：6 部件 103,180 顶点 → 1415 根骨架（合并 757），19 材质 41 贴图，0 未解析贴图；
  `Lethita`：7 部件 476 根，19 材质。preview.png / preview_face.png 逐张看过：正面取景、Shiningwill
  银甲、头发/眉毛/皮肤/眼睛都对。
- **15 套女装全部导出**（Fiona 默认装 + `Shiningwill_legacy` + 13 套 `PCF_*`）：先顺序 `-NoBlend`
  导 61 个包（UE Viewer 并发会互相覆盖共享贴图，不能并行），再 3 路并行 Blender（每套 2–3 分钟）。
  15 张预览拼图逐一核对：8 套旧骨架服装重定位后帽子/耳机/颈圈位置正确，头发按表显示/隐藏，
  PCF_012 的 `.hdr` 基色生效；`PCF_001_Temp` 裤子的彩虹格是资源自带的占位贴图。

## 2026-09-12 — Rise of Eros：9-12 更新的新角色导出（b14 / k07 / m03）

### 怎么发现的

这次更新是 Steam 增量更新，运行时缓存（`LocalLow\Pinkcore\Rise of Eros\AssetBundles`）已被清到 29 个
文件，8-30 记的「缓存 vs 安装目录」差分法查不出东西。改用两条线索：安装目录里 `chara_(armor|bare)_pc_<id>`
的 ID 减去 `D:\roe_exports\<id>` 已有目录；以及安装目录的 mtime 直方图——增量更新只给改动的文件盖新
日期（2082 个文件是 2026-09-12，7841 个还是 2025-12-13），所以新日期这次是可信的，和 8-01 全量重下
那次不同。

### 结果

- **新角色**：`b14`（Kart 14，主装 + `outfit1` 两套网格、92 张贴图）、`k07`（Keleira 7）、`m03`（Amano 3，
  以前没有独立网格，这次补了 armor 包）。`extract_character.ps1 <id> -ExportTextures` →
  `export_character_models.ps1 -Only b14,k07,m03`，4 个模型全部 PASS，渲染逐张目视（脸 / 眼 / 发 / 服装齐全）。
- **占位**：`f13`、`h11` 只有 36–45 KB 的 `chara_bare` 包，提取出来只有武器，记为 NOMESH。
- **老角色被重写的 armor 包**（a11 c02 c09 c10 j10 k02 m02 m03 h09）：用 `-OutputRoot D:\roe_exports_probe`
  提到临时目录再和现有导出比对，**不直接重提**（重提会把 `blend\`、XPS、PMX 整个删掉）。FBX 只能按大小比
  （导出器写时间戳，哈希每次不同），PNG 按 SHA。只有 **c10** 真变了（身体 albedo / mgac 高低模各一套 +
  新增脸部法线）；a11 只是法线图的 pathID 后缀变了、c09 只是玩具 fbx 改名、h09 的 `_update_1` 贴图包解出来
  和原来一样。c10 把临时目录里的贴图 / FBX 拷回原目录（保留 `blend\`），`-Only c10 -Force -Format blend,xps,pmx`
  重做三种格式。
- 画廊重生成（142 条：PASS 124、NOMESH 18），`prune_exports.py --apply` 清掉 0.57 GB 重复贴图，临时目录已删。

### 坑

Git Bash 里调 robocopy 的 `/E` 会被 MSYS 当成 `E:\` 路径，什么都不拷且不报错——同步用 python 或 PowerShell。

---

## 2026-09-06 — VaM 导入线：把别的人物身上的网格搬到 VaM 的身体上

### 新增

`import_to_vam.ps1` / `blender_to_duf.py` 多了三个参数，处理“外面扒来的角色”这类输入：

- **`-Materials a,b`**：只导这些材质槽的面，并丢掉没用到的顶点。MMD / 游戏拆包出来的角色
  往往整只就是**一个网格**，身体和每件衣服只靠材质区分。
- **`-Align` + `-AlignUsing`**：把网格缩放平移到 VaM 基础人体上。只解**等比缩放 + 平移**（两具
  身体都站着、朝向相同，多给一个旋转自由度只会让错误对应把人放倒），先按身高和脚底对齐，
  再做几轮锁死旋转的 scaled ICP。拟合用**源角色自己的皮肤**解，不是用衣服解。
- **`-Lift <米>`**：把扎进身体的布料顶点沿法线推回表面外。VaM 穿衣服时身体照样画，而别人的体型
  到处差一两厘米，不推就会被顶穿。

`vam_duf.py` 相应多了 `blender_to_vam` / `vam_to_blender` / `nearest_points` / `fit_to_reference`。

### 实测（Fiona 18，Genesis 8 Female 转 MMD，227079 顶点 / 19 个材质的单一网格）

- 等比 **0.0866**（MMD 单位→米），躯干/腿/头对 G2F 残差中位 **17.3 mm**——G8F 与 G2F 的体型差，衣服吃得下。
- 裙子有 **15.1% 的顶点原本扎在身体里**（最深 40 mm），`-Lift 0.004` 后为 0。
- 手臂残差中位 **326 mm**：A-pose 对 T-pose。把手臂摆正后手套 232.6 → **9.4 mm**、臂环 33.4 → 14.1 mm；
  而裙子顶点只动了 0.3 mm（它没绑手臂骨）。姿势差异只影响**长在那根骨头上的件**。
- 顺带测出 **G2F 的默认姿势不是纯 T**：手臂水平但肘部前扫约 22–26°，照实测方向摆比摆成纯水平好三倍
  （9.1 mm vs 26.4 mm）。

### 搚不过来的（实测结论，别再试）

皮肤贴图搚不了（VaM 的 Person 是 Genesis 2，UV 完全不同）；**脸也搚不了**。把 G2F 顶点最近点投影到
外来角色表面做体型 morph，位移看着无害（中位 22.9 mm）但那是**纯剪切**：鼻子边长比 p99 到 24.8 倍、
嘴唇 16.2 倍，头部 4.68% 的面法线翻转，侧面渲出来鼻子没了。原因是**对应关系**不对而不是目标面不全
（把口腔、眼球补进目标只会更糟）。能救的只有躯干+腿：头（z 1.50–1.60）、手臂（|x| 0.145–0.21）、
脚（z 0.09–0.17）用 smoothstep 衰减冻住，剩 6570 个顶点、边长比 p99 1.465、只有 37 个面翻转，渲出来是个
正常身体。要真做脸得上带地标的 wrap 变形。

### 验证

`python tests\test_vam_duf.py` → `VAM_DUF_TEST=PASS`（新增 `fit_to_reference` 的已知解回收测试），
`test_vam_lib.py` 仍 PASS。Fiona 的 10 件穿戴件全部导出并逐件渲图目检：裙子/领/头发/头饰/项链/耳环/
内裤/手套/臂环位置均正确；**只有高跟鞋不行**（源模型的脚为高跟踮起，VaM 基础人体是平脚，光脚从鞋里穿出）。

## 2026-09-06 — VaM：反方向的导入线（Blender → DAZ `.duf` / Genesis 2 morph `.dsf`）

### 新增

- **`scripts/vam/import_to_vam.ps1`**（+ `vam_duf.py`、`blender_to_duf.py`、
  `tests/test_vam_duf.py`）：把 Blender 里的网格写成 VaM 1.22 游戏内创作器
  `DAZRuntimeCreator`（Clothing Creator / Hair Creator）能导入的 DAZ `.duf` 场景，
  以及 `Custom\Atom\Person\Morphs\` 下的 Genesis 2 morph `.dsf`。**不需要 DAZ Studio，
  也不需要 Unity**——贴身（`CreateDAZSkinWrap`）和布料模拟由 VaM 自己算。
- `-Reference` 生成建模参照：VaM 自己的基础 Genesis 2 人体（女 23008 顶点 / 男 22970，带 UV）
  存成 Blender 坐标、米制的 `.blend`。衣服必须照这具身体建模，因为创作器是对着**基础**身体
  算包裹的，不是对着某个角色的 morph 结果。

### 用户如何操作

```powershell
cd E:\code\othercode\ripper_tpose\scripts\vam
.\import_to_vam.ps1 -Reference                                   # 参照人体 -> D:\vam_imports\_reference\
.\import_to_vam.ps1 -Source D:\work\jacket.blend -Install clothing -Author me
.\import_to_vam.ps1 -Source D:\work\belly.blend -Morph "Belly Out" -Install morph
```

游戏内：Person 加 Clothing Creator → `dufFile` 选这个 `.duf` → Import →（可选
`CreateClothSim`）→ 填 `storeName` → Store。morph 则重启 VaM，它会把 `.dsf` 编译成
`.vmi/.vmb`。顶点数上限是创作器自己提示的：包裹 < 50000，布料模拟 < 25000，`check_duf` 会提前警告。

### 实现原理与兼容性

坐标换算不是猜的，是拿 VaM 吃过的文件标定的：`VL_13.Lashes_2.1` 这个包里创作者把源文件
`Lashes_Skin_subd.duf` 和它产出的 `.vab` 一起打包了，正好是一对输入输出（392 顶点 / 282 四边形）。
逐顶点比对得到 `VaM 顶点 = (-x, y, z) * 0.01`（DAZ 用厘米），最大误差 1.5e-07，即 float32 精度；
**顶点顺序、面顺序、绕序、四边形、UV 全部 1:1 保留**。换算到 Blender 就是干净的右手 Z-up → Y-up
旋转 `DAZ = (100·bx, 100·bz, -100·by)`，两次镜像相消，**面朝向直接沿用**（DAZ 与 Blender 同为
从外看逆时针；实测一个封闭 DAZ 网格 88.7% 的面右手法线朝外）。

写出的 DSON 是自包含的（全部 `#id` 本地引用），因为 VaM 的 `DAZImport` 会拿 `url` 去注册表
`HKCU\Software\DAZ\Studio` 的内容目录里找外部文件，找不到就报 "could not found libraries"。
`vam_duf.check_duf()` 在写文件前把所有引用、索引范围、UV 计数查一遍，把这类问题挡在游戏之外。
UV 接缝按 DSON 的办法编码：`uvs` 前 `vertex_count` 个是每顶点默认值，接缝复制追加在后面，
`polygon_vertex_indices` 只给偏离默认的角点写 `[面号, 顶点号, uv号]`。
morph 的 `.dsf` 与装好的包里那些逐字段同构（比对了 `MacGruber.Life.13` 的 `Breathing_Chest.dsf`）：
`vertex_count` 21556、`parent` 指向 `Genesis2Female.dsf#GenesisFemale-1`（男性
`Genesis2Male.dsf#Genesis2Male`）。21556 是身体顶点数，生殖器嫁接网格排在其后、morph 管不到，
落在那里的改动会被数出来警告。

道具 / 场景物件那条路（CustomUnityAsset `.assetbundle`）需要 Unity **2018.1.9f1**
（版本从 `VaM_Data\globalgamemanagers` 读出），本机没装，暂未实现。

### 已执行的验证

- `python tests\test_vam_duf.py` → `VAM_DUF_TEST=PASS`；除合成 fixture 外，还用上面那对真实
  DUF / VAB 复核坐标换算，并要求 `check_duf` 接受 VaM 自己接受过的文件。`test_vam_lib.py` 仍 PASS。
- 闭环：缓存里的基础人体 → Blender → `.duf` → 换算回 VaM 空间，23008 个顶点最大误差 5e-07 米，
  绕序在 DAZ 空间为外向，22448/22506 个面保持四边形。
- Blender 默认立方体、单四边形 OBJ、23008 顶点整具人体、577 顶点的测试 morph（3 cm 位移，
  DAZ 空间读数正好 3.0 cm 且落在 +Z）四种输入跑通，PowerShell 入口的 `.blend` / `.obj` /
  `-Morph` 三条分支均验证。

## 2026-09-06 — 六个画廊页面补「手工导出教程」附录

### 新增

原来每个 `html/index.html` 底部的附录只有几条命令，别人看了自己导不出来。现在 DOA6、DOA5LR、
FF7 Remake、FF7 Rebirth、Throne of Desire、Stellar Blade 六页的附录都换成完整教程（每页 1.8–2.3 万字符，
写在各自 `make_gallery.py` 的 `APPENDIX_HTML` 常量里，`PAGE_TEMPLATE` 用 `{appendix}` 占位）：

- **前提**：工具版本与本机默认路径（Blender 3.6.15、Noesis 32/64 位、UE Viewer 专用构建、FModel、
  Python 包），要在装了游戏的机器上跑，需要自己设的环境变量只写名字（AES key 一律不进页面）。
- **步骤**：从游戏文件到带贴图 `.blend`，每步写清作用、完整命令、产物落在哪；单个模型与批量两条路径；
  怎么列出模型 ID / 包名。
- **参数表、产物目录、坑、并行与耗时、重新生成本页、例外与已知限制**。破坏性命令（会删掉整个部件目录、
  覆盖已有产物、覆盖 FModel 全局设置的那些）都在命令旁边标了出来。

### 验证

每页起草后过两轮多代理对抗校验（命令 / 参数 / 默认路径逐条对照脚本的 `param()`、`argparse`，
外加安全与过期检查），共 72 条问题、68 条已改。抓到的实质错误例如：DOA6 的 `_objdb` 提取
`--filter "*.kidssingletondb"` 会写出 347 个文件（应为 `*Editor.kidssingletondb` 三个）、
DOA5LR 的自检命令查错了封包（霞的部件在 `chara_initial` 不在 `chara_common`）、
FF7 Remake 手套那节 `-save` 只存了 Model 包导致后面必然缺贴图、
Rebirth「24 个没有主模型包」的成分写错、Stellar Blade 打包体积与耗时是旧数字。

---

## 2026-09-05 — Stellar Blade：每个 Eve 模型打成可单独分发的文件夹（`package_outfits.py`）

### 新增

- **`scripts/stellarblade/package_outfits.py`**（Blender 3.6 headless）：`blender\Eve_*.blend` 的贴图是
  `//..\umodel_*_exports\` 相对外链，单拷 .blend 会整身丢图。脚本把每个模型打成自足的文件夹
  `D:\stellarblade_exports\packages\Eve_<包名>\`：`.blend`（贴图改成 `//textures/` 相对路径）+
  `textures\`（材质接着的 12–17 张）+ `textures\extra\`（服装自己目录里没接节点的 _N/_ORM/_Mask/换色图）+
  `preview.png` / `preview_face.png` + 中英 `README.txt` + `package.json`。参数
  `--only/--force/--lane/--lanes/--no-extra/--zip/--include-probe`，`--index`（纯 python）写 `packages\README.md`。
  实现：open → 拷贴图 → 图片路径指到新绝对位置 → `save_as_mainfile` → `make_paths_relative` → 再存 →
  重新打开校验每张图都在包内；对象/材质自定义属性里的源 PSK 绝对路径改成相对；`save_version=0`。
- 画廊 `scripts/stellarblade/html/`：manifest 记 `packageDir`，卡片多一行「独立包」指向该文件夹。

### 本批结果

148 个包（146 套服装 + 标准 Eve + 裸模；UEFormat 探针不打）29.8 GB（平均 201 MB，其中附带贴图 16.5 GB），
三路并行约 10 分钟。
校验：14 个样本包拷到 C 盘另一路径，用 `--factory-startup`（无插件）Blender 3.6.15 打开，
贴图 14/14 全部从包内加载、从副本渲染与预览一致；审查代理另外在 4.5.10 / 5.1.2 打开无误。

### 2026-09-06 按审查结果修正（全部 148 个包重打）

- `textures\extra\` 改成从已接贴图往上找 `CH_P_EVE_<服装>` 目录后整棵树递归收（01 系的 `Tex\Body`、
  `Tex\Boost` 和 49_TypeB 的 `Textures\TypeB` 原来漏掉）；同名贴图冲突时两边都加前缀，不再依赖枚举顺序。
- 相对路径统一成 `//textures/x.png` 正斜杠；打包命令加 `--factory-startup`（否则存进去的是本机启动文件
  的中文工作区名和文件浏览器路径），最终保存后再按字节把用户目录 / 导出根的残留填成 NUL；Scene 上的
  `faceit_*` 残留属性删掉。校验：148 个 .blend 二进制里 0 个含用户目录或 `stellarblade_exports`。
- `package.json` 做完才写（`.part` + `os.replace`），重做先删旧的；`--zip` 在 marker 之后打包（原来 fresh
  构建的 zip 里没有 package.json）；SKIP 判定要求 .blend 和清单里的贴图都在；统计直接从打开的文件数，
  验证 JSON 缺失或不一致记为 problem；`--lane/--lanes` 校验、目录参数取绝对路径。
- README.txt：头部对象是 `Eve_Head_Mesh_01`（表情 Shape Keys 在它上面），列出全部物体名；单位厘米说明；
  导出时先选骨架和网格（场景里还有验证相机和三盏灯）；头发只接了 alpha、颜色固定；版本"3.6 及更新
  （4.5、5.1 已实测）"；来源改成"UE Viewer + FModel 导出、Blender 3.6 组装"，注明非官方、勿再分发；
  带头套的服装提示隐藏身体看表情；extras 为 0 时不写那两行。
- `validate_eve._export_index` 同名文件只记第一个，`CH_P_EVE_60` 的 `CH_P_EVE_BB_A.png` 被 CH_P_EVE_55 的
  同名文件顶掉（全部 146 套里只有 60 / 60NH 中招）→ 索引保留全部路径，`.mat` 与贴图都优先取服装自己
  目录下的；60 / 60NH 已重导、重渲预览。
- `collect_manifest.NAMES`：加 `01 = Default Body`，`11_1` / `15_V02` 名字加区分，NH 名字去掉多余空格。

---

## 2026-09-05 — Virt-A-Mate：Look / 衣服导出脚本（`scripts/vam/`）

### 新增

- **`scripts/vam/export_vam_models.ps1`** + `export_vam_models.py` + `vam_lib.py` +
  `export_vam_model_blender.py`：与 ROE `export_character_models.ps1` 同款接口——`-List` 列出
  全部 Look（场景里的 Person 原子 + 外观预设 .vap）、衣服、头发；`-Only <key|唯一子串>` /
  `-Index <#>` / `-All` 导出为带材质 `.blend`（可选 `.glb`）+ 三视图预览。本机 119 个 `.var`：
  66 个 Look、328 件衣服、219 个头发条目。
- 一个 Look 由**游戏包 `a_per` 里的 Genesis 2 合并网格**（女 21556+1452、男 21556+1325+89 顶点，
  AssetStudioModCLI 带 `--assembly-folder` dump 后解析）+ `.vmb` morph 增量 + 内置 morph 库
  （`f_mb`/`m_mb`）+ 场景 `textures` 四区皮肤贴图（缺的回退默认皮肤包）+ 衣服 `.vab` 网格拼成；
  衣服用最近 4 顶点距离平方反比把 morph 位移搬到衣服上。贴皮肤的壳（口红层/眼影/眼膜/指甲）
  自动识别为 skin layer：BLEND 材质 + 法线外推 0.4 mm，否则 EEVEE 的 HASHED 深度预通道会在脸上
  渲出黑色蕾丝状 z-fight（实测 alpha 恒 0 也出现）。
- 逆向的格式：`.vab` DAZMesh DynamicStore（字符串头 → 顶点 → 材质名 → 基础面 → UV 面 → UV →
  UV 映射）、`.vmb`（`count + {int idx, float3}`）、创作者 Body morph 的越界索引（21556..26469，
  皆为 ~1e-5 噪声，丢弃）、内置 morph 用 displayName 引用且 `isPoseControl` 对 CTRL 系不可靠
  （改按分组名 `Pose Controls`）。全部写在 `scripts/vam/README.md` §5。
- `tests/test_vam_lib.py`：合成 `.var`/`.vab`/`.vmb`/AssetStudio dump fixture 的纯 Python 回归。
- **头发**（同日追加）：`RuntimeHairGeometryCreator` `.vab` 逆向——每个头皮顶点一条造型后的引导线
  （`int segments, float segLen, byte, int N, byte[N] 掩码, int N, {int idx, int count, Vector3[count]}[N]`，
  后接索引表与点的重复副本）。导成 Blender 曲线（引导线 + ≤7 条随机偏移子发丝，bevel 0.5–1.2 mm，
  颜色 = rootColor/tipColor 均值），加 `a_per` 里同名头皮帽（Soleil/Udane/Krayon/Leyton/Omri），
  随 morph 位移；从未造型的直线引导线（横伸出头的"铁丝"）按「≥15 cm、笔直、不向下垂」丢弃。
  Look 缺省带头发（`-NoHair` 关），头发也能单独导（`-Type hair`）。预览取景只按网格算包围盒
  （后台模式曲线包围盒不可靠）。
- **CustomUnityAsset 附件**（同日追加）：挂在人物骨骼上的 Unity 资源包原子（网格头发、耳环、王冠、
  腰链、手镯、大剑）用 AssetStudioModCLI `splitObjects` 拆成 FBX + 贴图，Blender `global_scale=100`
  导入并挂到按静止姿势重算的空物体上。姿势→静止的换算用场景里每个关节控制点的
  `localPosition/localRotation`（相对人物容器；46 个场景全有），静止关节位置来自 `a_per` 的 `DAZBone`；
  无控制点的骨骼退回正向运动学（存的骨骼旋转是相对静止朝向的增量）。`-NoAttachments` 关闭。
  xnpvv Tifa 的头发就是这种 CUA——之前"没有头发"的原因。
- **CUA 附件摆放修正**（同日）：之前把关节控制点当成骨骼位置，而控制点只是用户放的目标，只有 Off
  状态的控制点才跟着骨骼（xnpvv 头部控制点离头骨 10 cm / 5.6°，头发因此歪）。现在从链上最深的 Off
  控制点锚定（JSON 只写非默认状态；默认 On 的是 hip / chest / head / 手 / 脚），往下每段：控制点离上一帧
  正好一段骨长（±3 cm）就当物理追到了、采用控制点，否则用场景里存的骨骼旋转（Unity 欧拉表示的完整局部
  旋转，179 对 Off 父子控制点验证 0.2°）推一步——maiden_queen 全 On 的链存的骨骼角度是陈旧的预设值，
  只能信控制点。`linkTo` 指向控制点时仍跟控制点。之前"存的骨骼旋转是相对静止朝向的增量"的结论是错的，
  已改回。
- **衣服贴合改用 DAZSkinWrapStore**（同日）：Cloud 的上衣缩进胸里、裤子鼓成灯笼——`.vab` 里的顶点是
  创作者 morph 过的身体上的位置，不能按"基础体→morph 体位移"搬。解出了 DAZMesh 后面的
  `DAZSkinWrapStore`（每顶点：最近皮肤三角形 + 局部坐标 `v1 + N·(f0+surfaceOffset) + (质心−v1)·f1 +
  (N×(质心−v1))·f2`，328 件衣服验证，标准体上做的误差 0.2–0.3 mm），照 VaM 运行时那样在当前身体上
  重建，离皮肤 1–4 cm 以外的松散部位（裙摆、灯笼裤）保留制作时的形状、按贴身顶点的位移平移（逐三角形
  重建会碎成锯齿）；没有包裹数据、或切向系数中位数超过 3 个三角形宽且文件里存的位置本身合理（悬空配件：
  牛仔帽、飘带、戒指，那里包裹坐标系无意义、按存的位置摆更稳）才退回位移搬运——存的位置离身体 0.15 m 以上的
  （圈耳环 0.94 m、脐环 0.32 m、高跟鞋部件 0.28 m）仍必须靠包裹重建。顺带：DAZ 多边形从外看顺时针，之前皮肤层 / 头皮帽的"外推"其实
  是往里推，改为 `outward_normals`；衣服 `disableAnatomy` 时隐藏生殖器 graft、露出 `Hidden` 材质上的
  原生裆部面；陷进皮肤 1 mm 以内的衣服顶点沿皮肤法线推出（穿模保护）。
- **CUA 只导 `assetName` 指定的 prefab**（2026-09-06）：一个资源包常装着创作者的整套配件，之前把包里
  所有对象都导进来叠在一处（maiden_queen 的王冠、两只手镯各重复 4 份）。现在按 `assetName` 的 prefab 名筛选；
  场景没指定且包里不止一个对象就跳过该原子并在清单里注明。
- **画廊**（同日）：`vam\html\make_gallery.py`（`-Gallery` 开关）从清单生成 `vam\html\index.html`，
  缩略图写在 `D:\vam_exports\_gallery\thumbs\`，卡片列出衣服 / 头发 / morph / 附件、告警与备注，
  可按种类过滤与搜索。

### 用户如何操作

```powershell
cd E:\code\othercode\ripper_tpose\scripts\vam
.\export_vam_models.ps1 -List
.\export_vam_models.ps1 -Only VAMSOY.Angela.1~Angela~Person
.\export_vam_models.ps1 -Index 125,550 -Format blend,glb
```

产物在 `D:\vam_exports\looks\<key>\blend\` 与 `D:\vam_exports\clothings\<key>\blend\`，
清单 `D:\vam_exports\vam_models_manifest.json`，缓存 `D:\vam_exports\_cache`（首次自动建，~40 s，
默认贴图按需导出后 ~1.4 GB）。

### 实现原理与兼容性

- 坐标 `(x, y, z) → (-x, -z, y)`（镜像，面序反转）；+X 为角色右侧用脚尖朝向与脸部 UV 验证。
- 姿势 morph 缺省跳过（`-IncludePoseMorphs` 保留）；头发是引导线近似（无密度/物理）；无骨架；Decal 按 alpha 叠在漫反射上（有创作者把整套皮肤放 Decal 槽）；
  依赖包缺失的衣服/morph 记进 manifest 后继续。
- `.ps1` 字符串全 ASCII（PS 5.1 OEM 码页规则），中文包名通过参数传递没问题，`-List` 里正常显示。

### 已执行的验证

- `tests\test_vam_lib.py` PASS。
- 集成：Angela（Female Custom，4 件皮肤层）、Cloud（Male 4，6 件衣服）、Preset_Alivia（Kayla
  默认皮肤，148 morph）、瑶瑶（Lexi，女仆装 5 件 + 3 皮肤层，中文子串选择）、单件 Cheongsam set，
  全部 PASS，预览逐张看过；`-List`、`-ValidateOnly` 经 `.ps1` 走通。
- 21 个 Tifa Look（含头发重导）+ 上述 4 个 Look 带头发重导，全部 PASS，预览拼图核对。
- CUA 附件：xnpvv Tifa（网格头发落在头上）、JackyCracky Tifa/7thHeaven（耳环）、maiden_queen
  （头发/王冠/项链/腰链/手镯）、Cloud（大剑在右手）重导核对；摆放修正后这 5 个 Look 再次重导核对，
  xnpvv 头发正 / 侧 / 顶视贴合头皮，maiden_queen 原本偏 10 cm 的右手镯落回手腕。
- 目录里剩余的 40 个 Look 全部导出（同日晚），至此 66 个 Look + 1 件衣服全部 PASS，画廊 67 条；
  新导的 40 个只看了清单没有逐一目检。

---

---

## 2026-09-05 — Stellar Blade：Eve 全部 146 套服装批量导出 + 画廊

### 新增与修复

- **`scripts/stellarblade/export_outfit.ps1`**：找网格时 `.psk` 与 `.pskx` 都认（顶点多的服装
  UE Viewer 写 `.pskx`，原来 79 套直接失败）；排除 `\Temp\` 同名子包（20/26 的 Temp 版没有
  马尾锚点骨）；按名导不出网格时用 `list_models.py` 解析出完整包路径再按路径导（52 系）。
- **`scripts/stellarblade/validate_eve.py`**：`find_material_albedo` 先读材质的 UE Viewer `.mat`——
  `Diffuse=` 是真颜色图就用，是 `T_*`/引擎图标/`del` 占位就在其它槽位找 `_D/_A/_BaseColor/_ADIR`，
  在整个导出根（DLC 从 `DLC_N` 上一级算）找贴图；猜 `*_A.png` 只作兜底，并惩罚材质名里没有的
  TypeB/TypeC 换色标记。01–06 系用共享的 `ScanCloth_*_D` 且导在别的服装目录下，原来整身灰白；
  01_Body 原来拿到 TypeB 的换色贴图；11_1（Raven 变体）的自带头发原来贴成引擎图标。
- **新增 `scripts/stellarblade/html/{collect_manifest.py, make_gallery.py}`**：Stellar Blade 画廊，
  manifest 直接读 `validation\*.json`；卡片显示服装名（对照表烘进脚本）、包名徽标、表情数；
  按编号下拉，本体 / DLC / 裸模筛选。

### 本批结果

146 套（本体 136 + DLC 10）全部出 `.blend`（`39_TYPE-A/A1` 是 `MI_CH_Delete` 占位的废弃网格，
剔除），加标准 Eve、裸模、Face 探针共 149 个，
6.9 GB，在 `D:\stellarblade_exports\blender\`。三路并行每套 7–16 s。
预览逐一目视 + 两轮多代理对抗复核（第一轮抓出 01–06 灰白与 Nikke_01 未匹配，第二轮抓出 01_Body
换色错拿、11_1 头发贴成引擎图标、39_TYPE-A 占位网格）。已知局限：11_1 自带头发，管线又装了默认发型。

 + 71 个 Player 变体材质化 + 画廊

### 新增与修复

- **新增 `scripts/final/fmodel_export_player.py`**：pywinauto 驱动 FModel（备份/改写 AppSettings
  指向 Rebirth、经典浏览器、ActorX；启动、Load、展开树、`Shift+F10` 触发
  「Save Folder's Packages Models」、轮询到 3 分钟无新文件、还原设置）。以前 Rebirth 只能
  在 FModel 里逐个手点 Save Model，所以只导过 9 个 Tifa。
- **新增 `scripts/final/html/render_blend_preview.py`**：给不带预览的 .blend 补渲正面预览
  （UE/ActorX 人物正面朝 +X）。
- **新增 `scripts/final/html_rebirth/{collect_manifest.py, make_gallery.py}`**：Rebirth 画廊，
  manifest 由 `export_ff7rb_models.ps1` 的 manifest 转换，按角色下拉 + 主服装/过场/蛤蟆筛选。

### 本批结果

85 个 Player 主模型包 → FModel 写出 72 个 PSKX → 材质化 PASS 71 / FAIL 1；
13 个包 FModel 读 SkeletalMesh 失败且不可恢复（Cloud 血迹版 ×4、Aerith/Sonon 血迹版、
Toad_Standard、6 个 PC7xxx 过场版），清单见 `docs/ff7rebirth-player-export-inventory.md` §0。
产物 `D:\ff7rebirth_exports\materialized\`（7.3 GB）。

### 踩坑

FModel 全局 Mesh Format 被切成 UEFormat（另一款游戏的配置）时整目录导出写的是 `.uemodel`；
新浏览器模式没有目录右键菜单；高 DPI 下 pywinauto 鼠标坐标偏移——脚本已全部规避。



### 新增与修复

- **新增 `scripts/final/export_ff7remake_models.ps1`**：按 `docs/ff7remake-player-model-files.txt`
  的 36 个包循环「`ff7remake_export.ps1` umodel 提取 → `validate_ff7remake_model.py` 材质化」，
  支持 `-Only`、`-SkipExtract`、`-Force`、`-Lane/-Lanes`、`-List`；所有包共用
  `D:\ff7remake_exports\player\` 一个根。`enable_psk_addon.py` 负责在无头 Blender 里启用 PSK 导入器。
- **`validate_ff7remake_model.py` 两处修复**：同名 `_A` 遮罩只在材质 `.mat` 引用它时才接 Alpha
  （否则 Tifa 的衬衫/袖套/丝袜被 99% 全黑的 `BodyA_A` 透掉）；`.mat` 本包找不到时到整个导出根找
  （Yuffie 莫古利装引用 `PC0005_00` 基础包的材质，原来缺 24/34 张贴图）。预览灯光由面光改太阳光。
- **新增 `scripts/final/html/{collect_manifest.py, make_gallery.py}`**：FF7 Remake 画廊，
  manifest 直接从各包报告 JSON 汇总（不开 Blender），按角色下拉 + 主服装/贴片/蛤蟆筛选。

### 用户如何操作

见 `docs/final-fantasy-vii-remake-extraction.md`「批量导出全部 Player 主模型」。

### 本批结果

36/36 成功、缺贴图 0，每包材质化 2–8 s。完整人物 22 个；`_90/_91` 的 7 个是泪痕/血迹叠加贴片
（约 1000 顶点，不是完整人物）；Toad 7 个。产物在 `D:\ff7remake_exports\player\_blends\`。

### 验证

- Tifa 标准装修复前后对比：衬衫/丝袜回来，报告 `alpha` 只剩 Earring/Hair/Eyebrow 三个材质。
- Yuffie Moogle 修复后 `missing_preview_textures=[]`。
- 36 张预览拼图逐一目视。

（19 人 270 套 COS/DLC/DLCU）

### 新增与修复

- **`scripts/doa5lr/export_full.ps1`**：`-Archive` 缺省改为 `auto`——首次扫游戏目录全部
  36 个 `.bin` 建 `<OutRoot>\_archive_index.txt`（条目名 → 封包），之后每个部件各自查
  封包；以前一个 `-Archive` 管三个部件，服装在 `chara_common` 而脸/发型在 `chara_initial`
  的角色（霞、绫音）换装时会解不出脸。已提取过的部件目录（`<OutRoot>\<条目>\<条目>\*.fbx`）
  直接复用，不再每次 `-Force` 重解包——这也是三路并行不互相踩脸/发型目录的前提。
- **`scripts/doa5lr/build_blend.py` 就位判据放宽**：脸/头发「顶端够到身体顶端」的余量
  由身体高度 5% 放宽到 25%。兔女郎类 DLC（`AYANE_DLC_006/007` 等 11 套）的兔耳把身体
  包围盒顶端撑高约 15%，脸和头发被误判为未就位而整体上移 ~25 cm。真正未就位的头发
  （用自己原点、悬在腰腹，顶端只到 0.6）仍能判出。
- **`scripts/doa5lr/html/collect_manifest.py` / `make_gallery.py`**：从文件名解析服装条目
  （`<角色>_<名>_<COS|DLC|DLCU>_<NNN>`，无后缀即 `COS_001`），封包徽标按整个服装条目名查
  （原来只认 `_COS_001`），卡片加服装号徽标，工具栏加**按角色下拉筛选**，搜索框也搜服装号。

### 用户如何操作

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa5lr
.\export_full.ps1 KASUMI_COS_002 -Face auto -Hair 001 -Label KASUMI_Kasumi_COS_002   # 单套
# 批量：python extract_lnk.py <bin> --list 抓 <角色>_(COS|DLC)_NNN.TMC 做清单后循环上面这条
blender --background --factory-startup --python html\collect_manifest.py
python html\make_gallery.py --force
```

### 本批结果

19 名女性角色在 `chara_common` / `chara_initial` 里共 245 个 `COS/DLC` 条目：19 个 COS_001
早已导出，3 个是 10 KB 占位（`MILA_COS_008`、`SARAH_DLC_002`、`PAI_DLC_002`），其余
**223 套全部出 .blend**（三路并行，每套 5–16 s）；随后 `DLCU_NNN`（「Ultimate」系 DLC 位，
14 人 47 套，与同号 DLC 不是同一套衣服）也全部出 .blend。共 270 套 / 4.6 GB，在
`D:\doa5lr_exports\_blends\`，对照表见该目录 README §1。头发统一 `HAIR_001`
（官方每套服装的默认发型无法从条目名得知）。画廊 291 个模型。

### 验证

- `KASUMI_COS_002`：84 材质重建、135 贴图打包、脸/发型复用无重解包。
- 270 套预览拼图逐一目视：Alpha-152 通体白色仍是素材本身；兔耳装修复前后对比
  脸/头发回到颈部；无其它对齐或材质异常。

---

---

## 2026-09-05 — FF7 Rebirth：FModel 整目录自动导出 + 71 个 Player 变体材质化 + 画廊

### 新增与修复

- **新增 `scripts/final/fmodel_export_player.py`**：pywinauto 驱动 FModel（备份/改写 AppSettings
  指向 Rebirth、经典浏览器、ActorX；启动、Load、展开树、`Shift+F10` 触发
  「Save Folder's Packages Models」、轮询到 3 分钟无新文件、还原设置）。以前 Rebirth 只能
  在 FModel 里逐个手点 Save Model，所以只导过 9 个 Tifa。
- **新增 `scripts/final/html/render_blend_preview.py`**：给不带预览的 .blend 补渲正面预览
  （UE/ActorX 人物正面朝 +X）。
- **新增 `scripts/final/html_rebirth/{collect_manifest.py, make_gallery.py}`**：Rebirth 画廊，
  manifest 由 `export_ff7rb_models.ps1` 的 manifest 转换，按角色下拉 + 主服装/过场/蛤蟆筛选。

### 本批结果

85 个 Player 主模型包 → FModel 写出 72 个 PSKX → 材质化 PASS 71 / FAIL 1；
13 个包 FModel 读 SkeletalMesh 失败且不可恢复（Cloud 血迹版 ×4、Aerith/Sonon 血迹版、
Toad_Standard、6 个 PC7xxx 过场版），清单见 `docs/ff7rebirth-player-export-inventory.md` §0。
产物 `D:\ff7rebirth_exports\materialized\`（7.3 GB）。

### 踩坑

FModel 全局 Mesh Format 被切成 UEFormat（另一款游戏的配置）时整目录导出写的是 `.uemodel`；
新浏览器模式没有目录右键菜单；高 DPI 下 pywinauto 鼠标坐标偏移——脚本已全部规避。



### 新增与修复

- **新增 `scripts/final/export_ff7remake_models.ps1`**：按 `docs/ff7remake-player-model-files.txt`
  的 36 个包循环「`ff7remake_export.ps1` umodel 提取 → `validate_ff7remake_model.py` 材质化」，
  支持 `-Only`、`-SkipExtract`、`-Force`、`-Lane/-Lanes`、`-List`；所有包共用
  `D:\ff7remake_exports\player\` 一个根。`enable_psk_addon.py` 负责在无头 Blender 里启用 PSK 导入器。
- **`validate_ff7remake_model.py` 两处修复**：同名 `_A` 遮罩只在材质 `.mat` 引用它时才接 Alpha
  （否则 Tifa 的衬衫/袖套/丝袜被 99% 全黑的 `BodyA_A` 透掉）；`.mat` 本包找不到时到整个导出根找
  （Yuffie 莫古利装引用 `PC0005_00` 基础包的材质，原来缺 24/34 张贴图）。预览灯光由面光改太阳光。
- **新增 `scripts/final/html/{collect_manifest.py, make_gallery.py}`**：FF7 Remake 画廊，
  manifest 直接从各包报告 JSON 汇总（不开 Blender），按角色下拉 + 主服装/贴片/蛤蟆筛选。

### 用户如何操作

见 `docs/final-fantasy-vii-remake-extraction.md`「批量导出全部 Player 主模型」。

### 本批结果

36/36 成功、缺贴图 0，每包材质化 2–8 s。完整人物 22 个；`_90/_91` 的 7 个是泪痕/血迹叠加贴片
（约 1000 顶点，不是完整人物）；Toad 7 个。产物在 `D:\ff7remake_exports\player\_blends\`。

### 验证

- Tifa 标准装修复前后对比：衬衫/丝袜回来，报告 `alpha` 只剩 Earring/Hair/Eyebrow 三个材质。
- Yuffie Moogle 修复后 `missing_preview_textures=[]`。
- 36 张预览拼图逐一目视。

（19 人 270 套 COS/DLC/DLCU）

### 新增与修复

- **`scripts/doa5lr/export_full.ps1`**：`-Archive` 缺省改为 `auto`——首次扫游戏目录全部
  36 个 `.bin` 建 `<OutRoot>\_archive_index.txt`（条目名 → 封包），之后每个部件各自查
  封包；以前一个 `-Archive` 管三个部件，服装在 `chara_common` 而脸/发型在 `chara_initial`
  的角色（霞、绫音）换装时会解不出脸。已提取过的部件目录（`<OutRoot>\<条目>\<条目>\*.fbx`）
  直接复用，不再每次 `-Force` 重解包——这也是三路并行不互相踩脸/发型目录的前提。
- **`scripts/doa5lr/build_blend.py` 就位判据放宽**：脸/头发「顶端够到身体顶端」的余量
  由身体高度 5% 放宽到 25%。兔女郎类 DLC（`AYANE_DLC_006/007` 等 11 套）的兔耳把身体
  包围盒顶端撑高约 15%，脸和头发被误判为未就位而整体上移 ~25 cm。真正未就位的头发
  （用自己原点、悬在腰腹，顶端只到 0.6）仍能判出。
- **`scripts/doa5lr/html/collect_manifest.py` / `make_gallery.py`**：从文件名解析服装条目
  （`<角色>_<名>_<COS|DLC|DLCU>_<NNN>`，无后缀即 `COS_001`），封包徽标按整个服装条目名查
  （原来只认 `_COS_001`），卡片加服装号徽标，工具栏加**按角色下拉筛选**，搜索框也搜服装号。

### 用户如何操作

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa5lr
.\export_full.ps1 KASUMI_COS_002 -Face auto -Hair 001 -Label KASUMI_Kasumi_COS_002   # 单套
# 批量：python extract_lnk.py <bin> --list 抓 <角色>_(COS|DLC)_NNN.TMC 做清单后循环上面这条
blender --background --factory-startup --python html\collect_manifest.py
python html\make_gallery.py --force
```

### 本批结果

19 名女性角色在 `chara_common` / `chara_initial` 里共 245 个 `COS/DLC` 条目：19 个 COS_001
早已导出，3 个是 10 KB 占位（`MILA_COS_008`、`SARAH_DLC_002`、`PAI_DLC_002`），其余
**223 套全部出 .blend**（三路并行，每套 5–16 s）；随后 `DLCU_NNN`（「Ultimate」系 DLC 位，
14 人 47 套，与同号 DLC 不是同一套衣服）也全部出 .blend。共 270 套 / 4.6 GB，在
`D:\doa5lr_exports\_blends\`，对照表见该目录 README §1。头发统一 `HAIR_001`
（官方每套服装的默认发型无法从条目名得知）。画廊 291 个模型。

### 验证

- `KASUMI_COS_002`：84 材质重建、135 贴图打包、脸/发型复用无重解包。
- 270 套预览拼图逐一目视：Alpha-152 通体白色仍是素材本身；兔耳装修复前后对比
  脸/头发回到颈部；无其它对齐或材质异常。

---

---

## 2026-09-05 — FF7 Remake：36 个 Player 主模型批量导出 + 画廊

### 新增与修复

- **新增 `scripts/final/export_ff7remake_models.ps1`**：按 `docs/ff7remake-player-model-files.txt`
  的 36 个包循环「`ff7remake_export.ps1` umodel 提取 → `validate_ff7remake_model.py` 材质化」，
  支持 `-Only`、`-SkipExtract`、`-Force`、`-Lane/-Lanes`、`-List`；所有包共用
  `D:\ff7remake_exports\player\` 一个根。`enable_psk_addon.py` 负责在无头 Blender 里启用 PSK 导入器。
- **`validate_ff7remake_model.py` 两处修复**：同名 `_A` 遮罩只在材质 `.mat` 引用它时才接 Alpha
  （否则 Tifa 的衬衫/袖套/丝袜被 99% 全黑的 `BodyA_A` 透掉）；`.mat` 本包找不到时到整个导出根找
  （Yuffie 莫古利装引用 `PC0005_00` 基础包的材质，原来缺 24/34 张贴图）。预览灯光由面光改太阳光。
- **新增 `scripts/final/html/{collect_manifest.py, make_gallery.py}`**：FF7 Remake 画廊，
  manifest 直接从各包报告 JSON 汇总（不开 Blender），按角色下拉 + 主服装/贴片/蛤蟆筛选。

### 用户如何操作

见 `docs/final-fantasy-vii-remake-extraction.md`「批量导出全部 Player 主模型」。

### 本批结果

36/36 成功、缺贴图 0，每包材质化 2–8 s。完整人物 22 个；`_90/_91` 的 7 个是泪痕/血迹叠加贴片
（约 1000 顶点，不是完整人物）；Toad 7 个。产物在 `D:\ff7remake_exports\player\_blends\`。

### 验证

- Tifa 标准装修复前后对比：衬衫/丝袜回来，报告 `alpha` 只剩 Earring/Hair/Eyebrow 三个材质。
- Yuffie Moogle 修复后 `missing_preview_textures=[]`。
- 36 张预览拼图逐一目视。

（19 人 270 套 COS/DLC/DLCU）

### 新增与修复

- **`scripts/doa5lr/export_full.ps1`**：`-Archive` 缺省改为 `auto`——首次扫游戏目录全部
  36 个 `.bin` 建 `<OutRoot>\_archive_index.txt`（条目名 → 封包），之后每个部件各自查
  封包；以前一个 `-Archive` 管三个部件，服装在 `chara_common` 而脸/发型在 `chara_initial`
  的角色（霞、绫音）换装时会解不出脸。已提取过的部件目录（`<OutRoot>\<条目>\<条目>\*.fbx`）
  直接复用，不再每次 `-Force` 重解包——这也是三路并行不互相踩脸/发型目录的前提。
- **`scripts/doa5lr/build_blend.py` 就位判据放宽**：脸/头发「顶端够到身体顶端」的余量
  由身体高度 5% 放宽到 25%。兔女郎类 DLC（`AYANE_DLC_006/007` 等 11 套）的兔耳把身体
  包围盒顶端撑高约 15%，脸和头发被误判为未就位而整体上移 ~25 cm。真正未就位的头发
  （用自己原点、悬在腰腹，顶端只到 0.6）仍能判出。
- **`scripts/doa5lr/html/collect_manifest.py` / `make_gallery.py`**：从文件名解析服装条目
  （`<角色>_<名>_<COS|DLC|DLCU>_<NNN>`，无后缀即 `COS_001`），封包徽标按整个服装条目名查
  （原来只认 `_COS_001`），卡片加服装号徽标，工具栏加**按角色下拉筛选**，搜索框也搜服装号。

### 用户如何操作

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa5lr
.\export_full.ps1 KASUMI_COS_002 -Face auto -Hair 001 -Label KASUMI_Kasumi_COS_002   # 单套
# 批量：python extract_lnk.py <bin> --list 抓 <角色>_(COS|DLC)_NNN.TMC 做清单后循环上面这条
blender --background --factory-startup --python html\collect_manifest.py
python html\make_gallery.py --force
```

### 本批结果

19 名女性角色在 `chara_common` / `chara_initial` 里共 245 个 `COS/DLC` 条目：19 个 COS_001
早已导出，3 个是 10 KB 占位（`MILA_COS_008`、`SARAH_DLC_002`、`PAI_DLC_002`），其余
**223 套全部出 .blend**（三路并行，每套 5–16 s）；随后 `DLCU_NNN`（「Ultimate」系 DLC 位，
14 人 47 套，与同号 DLC 不是同一套衣服）也全部出 .blend。共 270 套 / 4.6 GB，在
`D:\doa5lr_exports\_blends\`，对照表见该目录 README §1。头发统一 `HAIR_001`
（官方每套服装的默认发型无法从条目名得知）。画廊 291 个模型。

### 验证

- `KASUMI_COS_002`：84 材质重建、135 贴图打包、脸/发型复用无重解包。
- 270 套预览拼图逐一目视：Alpha-152 通体白色仍是素材本身；兔耳装修复前后对比
  脸/头发回到颈部；无其它对齐或材质异常。

---

---

## 2026-09-05 — DOA5LR：换服装批量导出（19 人 270 套 COS/DLC/DLCU）

### 新增与修复

- **`scripts/doa5lr/export_full.ps1`**：`-Archive` 缺省改为 `auto`——首次扫游戏目录全部
  36 个 `.bin` 建 `<OutRoot>\_archive_index.txt`（条目名 → 封包），之后每个部件各自查
  封包；以前一个 `-Archive` 管三个部件，服装在 `chara_common` 而脸/发型在 `chara_initial`
  的角色（霞、绫音）换装时会解不出脸。已提取过的部件目录（`<OutRoot>\<条目>\<条目>\*.fbx`）
  直接复用，不再每次 `-Force` 重解包——这也是三路并行不互相踩脸/发型目录的前提。
- **`scripts/doa5lr/build_blend.py` 就位判据放宽**：脸/头发「顶端够到身体顶端」的余量
  由身体高度 5% 放宽到 25%。兔女郎类 DLC（`AYANE_DLC_006/007` 等 11 套）的兔耳把身体
  包围盒顶端撑高约 15%，脸和头发被误判为未就位而整体上移 ~25 cm。真正未就位的头发
  （用自己原点、悬在腰腹，顶端只到 0.6）仍能判出。
- **`scripts/doa5lr/html/collect_manifest.py` / `make_gallery.py`**：从文件名解析服装条目
  （`<角色>_<名>_<COS|DLC|DLCU>_<NNN>`，无后缀即 `COS_001`），封包徽标按整个服装条目名查
  （原来只认 `_COS_001`），卡片加服装号徽标，工具栏加**按角色下拉筛选**，搜索框也搜服装号。

### 用户如何操作

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa5lr
.\export_full.ps1 KASUMI_COS_002 -Face auto -Hair 001 -Label KASUMI_Kasumi_COS_002   # 单套
# 批量：python extract_lnk.py <bin> --list 抓 <角色>_(COS|DLC)_NNN.TMC 做清单后循环上面这条
blender --background --factory-startup --python html\collect_manifest.py
python html\make_gallery.py --force
```

### 本批结果

19 名女性角色在 `chara_common` / `chara_initial` 里共 245 个 `COS/DLC` 条目：19 个 COS_001
早已导出，3 个是 10 KB 占位（`MILA_COS_008`、`SARAH_DLC_002`、`PAI_DLC_002`），其余
**223 套全部出 .blend**（三路并行，每套 5–16 s）；随后 `DLCU_NNN`（「Ultimate」系 DLC 位，
14 人 47 套，与同号 DLC 不是同一套衣服）也全部出 .blend。共 270 套 / 4.6 GB，在
`D:\doa5lr_exports\_blends\`，对照表见该目录 README §1。头发统一 `HAIR_001`
（官方每套服装的默认发型无法从条目名得知）。画廊 291 个模型。

### 验证

- `KASUMI_COS_002`：84 材质重建、135 贴图打包、脸/发型复用无重解包。
- 270 套预览拼图逐一目视：Alpha-152 通体白色仍是素材本身；兔耳装修复前后对比
  脸/头发回到颈部；无其它对齐或材质异常。

---

---

## 2026-09-05 — DOA6：mod 导出支持发型/脸部件，批量转出 45 个社区 mod 变体

### 新增与修复

- **`scripts/doa6/export_nude_mod.ps1` 重写为按部件驱动**：以前只认 mod 里的服装 g1m，
  现在按 `<CHR>_<COS|HAIR|FACE>_<NNN>` 把 mod 的 g1m 分类，mod 给什么就换什么，
  缺的部件用官方 `COS_001 / FACE_001 / HAIR_001` 补齐（`-Cos/-Face/-Hair` 改编号）。
  `-Chr` 可省略（按 g1m 名推断），`-Label` 缺省由 zip 名生成，新增 `-NoPreview`。
  `-Cos/-Face/-Hair` 除编号外也接受完整部件名（`-Face AYA_FACE_001`，body-swap 类 mod
  用别的角色的脸），官方件本机没导出过时自动调 `export_character.ps1` 现场导。
- **mod 自带 `<id>.ktid` 优先于原版**：Yor Forger 的发型 mod 把贴图槽位从 6 个扩成
  13 个，用原版 ktid 解析时 44 个 submesh 全部无贴图（渲成白发）。现在先找 g1m 旁边
  的 ktid；另加兜底——路线 A 若留下有顶点却无 albedo 的 submesh，自动改走启发式。
- **mod 若带官方部件的贴图（如 `PHFFACE001_face_kidsalb`）**，把官方部件复制一份叠上
  mod 贴图再组装，不再丢弃这些贴图。
- **`mod_matmap.py --key <部件键>`**：多部件 mod 的 Material 目录混着几套贴图，
  启发式只看本部件的 g1t（无匹配时退回全部）。
- **`html/collect_manifest.py`**：mod 变体的判定从「服装目录是 `<Label>_cos`」放宽到
  `_cos/_face/_hair` 任一，贴图计数同样覆盖三个目录；否则发型 mod 会被标成官方。
- 两处老坑再次踩到并修掉：PowerShell 函数里 python 的 stdout 会混进返回值
  （`$partDirs` 变脏 → "blend 未生成"），全部改成 `| ForEach-Object { Write-Host }`；
  Blender 输出改写到 `_blends\<Label>.log`，失败时打印尾部而不是静默。

### 用户如何操作

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa6
.\export_nude_mod.ps1 D:\doa_mods\doa6\_zips\<mod>.zip -Label MOM_Momiji_LooseHair   # 发型 mod
.\export_nude_mod.ps1 <zip> -Label PHF_YorForger_Bikini                              # 服装+发型 mod
.\export_nude_mod.ps1 <已解压目录> -Chr AYA -Label AYA_Ayane_Fachan2 -Assign "5=body"  # 纠正启发式
```

产物 `D:\doa6_exports\_blends\<Label>.blend` + `_preview.png`，部件暂存目录
`<Label>_cos / _face / _hair`。全部 mod 的对照表与已知缺陷见 `D:\doa6_exports\README.md` §1.5。

### 本批结果

`D:\doa_mods\doa6\_zips\` 里 39 个 zip：2 个是重复文件；Rosario+Vampire Moka（108 MB）
首次下载被 GameBanana 截断到 18 MB，`curl -sL --retry 3` 重下后是 10 个子 mod 的合集包，
出了 7 个可用的（白发 Moka × Kokoro 服装 5 个、粉发 Honoka 校服 2 个）。其余 36 个 +
早先 5 个，共 **45 个 .blend 全部成功**（三路并行，每个 11–32 s）。人工看预览后处理了：

- `SKD_Tamaki_*`（5 个）：Tamaki 是未装 DLC，本机没有脸/发型，只出身体（脚本警告而非报错）。
- `SKD_Tamaki_NudeMicroBikini`、`AYA_Ayane_Fachan2` 原 mod 不带皮肤 albedo，
  从同角色其它 mod 借了 `*_body_kidsalb/nmh` 放进 `D:\doa_mods\doa6\_patched\` 副本重跑。
- `AYA_Ayane_TropicalTune2`：g1m 里身体的三角面被删光（顶点还在），是 mod 本身如此。

### 验证

- Yor Forger：修复前预览白发，修复后黑发+金饰，`matmap.json` 里 43 个有顶点 submesh 全部有 alb。
- 45 个预览拼图逐一目视：无皮肤/衣物互换；黑色「Buckle Up」紧身衣与 NSFW1 湿衬衫经
  贴图均值/alpha 统计确认是 mod 设计。
- `mod_matmap.py --key` 对 Yor（27 个 g1t 混三部件）只取 `PHFCOS037` 的 3 个部位。

---

---

## 2026-08-30 — Rise of Eros：只打包用到的贴图，清理导出目录冗余

### 新增与修复

- **`export_character_model_blender.py` 与 `export_nude_model_blender.py`**：
  `pack_images()` 由"遍历 `bpy.data.images` 全打包"改为只打包**模型材质实际引用**
  的图片（沿材质节点树收集 `TEX_IMAGE`）。

### 根因

FBX 导入时 Blender 会**按 FBX 同级目录**为文件里提到的每张贴图创建图片数据块，
而插件随后是用 `_textures`（或暂存目录）里的副本重建材质的——两套数据块并存，
后者才被材质引用。旧的 `pack_images()` 不加区分地全打包，于是：

1. **.blend 里嵌入了大量没有任何材质使用的重复贴图**。修复后 g11 的 blend
   从 66.8 MB 降到 31.8 MB（−52%），b01 裸模从 15.8 MB 降到 13.4 MB。
2. 一旦把 `FBX_GameObjects` 子目录里的冗余贴图副本清掉，打包就会硬失败
   （`无法打包文件,找不到资源路径`）——**两条管线都会失败**，不只是穿衣那条。

### 清理脚本入库

- 新增 `scripts/riseoferos/prune_exports.py`（缺省空跑，`--apply` 才删）与纯 Python
  回归 `tests/test_prune_exports.py`。重复副本每次重新提取都会再长出来，所以这是
  常备维护脚本而不是一次性操作。
- 三道安全机制：贴图副本必须与本角色 `_textures` 的同名文件**哈希一致**才删；
  `.blend1` 必须对应 `.blend` 仍在才删（孤儿备份是唯一副本）；`_textures\` 与
  `blend\` 不进入遍历。测试用合成目录覆盖同名不同内容、无 `_textures` 的角色、
  受保护目录里的同名文件、孤儿 `.blend1`，并验证幂等；逐条破坏上述机制均能让
  测试失败（其中去掉受保护目录过滤会导致连 `_textures` 原件一起删）。

### 导出目录清理

`D:\roe_exports` 从 **46.6 GB 降到 28.1 GB**，删除的两类都逐文件校验过：

- **5378 个 PNG / 18.00 GB**：`extract_character.ps1` 每次运行都会把每张贴图
  在 `_textures\` 存一份、又在**每个对象子目录**各复制一份。删除前对每个文件
  与其 `_textures` 孪生文件做了完整 MD5 比对，一致才删。
- **21 个 `.blend1` / 0.53 GB**：Blender 备份，且仅在对应 `.blend` 仍存在时删除。

保留：`blend\`（120 个成品 + 120 张预览图）、`_textures\`（128 个角色目录全部
都有）、全部 FBX、以及子目录里 `_textures` 没有的 164 个独有 PNG（含 XPS 流程
烘焙的 `roe_eye_baked.png`）。

> **教训**：清理前我判断"两条管线都不受影响"，理由是材质读的是 `_textures`。
> 这个判断漏了 Blender 导入器自己创建的那批数据块——**材质用不到，打包却会碰**。
> 结论是对的（那些副本确实是冗余），但必须先修 `pack_images()` 再删。

---

---

## 2026-08-30 — Rise of Eros：修复 a00 眼球（头身合一、无 Eyeball 骨骼组）

### 新增与修复

- **`export_character_model_blender.py`**：`find_head()` 返回 `None`（头身合一）时，
  按几何特征认出眼球组件（250–800 面 + UV 基本铺满 0–1）并追加
  `module.eye_mat()` 程序化眼球材质；manifest 新增 `fusedHeadEyes` 字段。
  详见[避坑手册 #16](roe-material-pitfalls.md)。

### 问题与根因

a00 通用素体双眼渲染成白褐色碎块。它的网格叫 `pc_a00_nk`（不是 `*_nk_body`），顶点组
只有 `Bip000 *` 骨骼、**没有 `Eyeball` 组**，名字里也没有 `head` 词元——`find_head()`
两条判据全落空返回 `None`，眼/睫/眉分类整个被跳过；裸模 worker 的
`split_combined_nude_body` 又因为名字不匹配 `(?:^|_)nk_body$` 直接返回 `None`。
**两条既有路径都没接住它**（README §4 那句"a00 两网格/两材质"正是这个状态）。

但 a00 的眼球本身完全标准：两个 432 面、UV 铺满 0–1（0.0004–0.9995）的组件，签名与
g06 等角色一致。它们拿到了身体图集，满 0–1 的 UV 去采样身体图就渲成了碎块。

修法是在没有独立 head 网格时按几何特征直接认眼球，而**不是**放宽 `find_head()`——
把整块身体当 head 交给 `classify_head` 会把大半个躯干判成脸，那正是
`split_combined_nude_body` 当初要解决的问题。

### 验证

- a00 命中 864 面（2×432）挂上 `eye_mat`，材质槽 2→3，虹膜贴图
  `pc_a_nk_eye_iris_rgbx_Albedo.png` 进入 textures；特写渲染确认蓝色虹膜、瞳孔、
  眼白都正常。
- 守卫只在完全找不到独立 head 网格时触发，120 个模型里只有 a00 属于这种情况。

---

---

## 2026-08-30 — Rise of Eros：修复 g05 "没有眼球"（显式 face 槽抢走眼球）

### 新增与修复

- **`roe_xps_addon.py` / `classify_head`**：为 F10 加的"显式 face 槽 → 强制 slot 0"
  逐面覆盖增加 `and slot != 1` 例外，组件级判定为眼球的面不再被拉回脸。
  详见[避坑手册 #15](roe-material-pitfalls.md)。
- **`export_character_models.ps1`**：硬告警从只看 `face` 扩展到 `face` + `eye`
  两个槽（其余槽为 0 可能是正常的，判读表见避坑手册）。

### 问题与根因

用户报告 `pc_g05_hd.fbx` 眼睛没有眼球。`headSlots` 一眼定位：g05 的 eye 槽 **0 个面**，
而同体型 g01/g04/g06 都是 864；那 864 个面并进了 face（14,633 = 13,769 + 864），
所以眼球被刷上了脸部贴图。

眼球的连通块识别其实完全正常——428 面、Eyeball 权重 0.998、UV 铺满 0–1，
`w['eyeball'] > 0.9` 直接命中。问题在最后那轮逐面覆盖：g05 的原始槽是
`['pc_g_nk_face', 'pc_g_nk_eyebrow', 'pc_g_nk_tears']`，**没有 `pc_g_nk_eyes`**，
眼球面挂在 face 材质索引上，于是那条为 F10 加的覆盖把判对的眼球又拽回了脸。
g01/g04/g06 都有独立 eyes 槽，所以不受影响。

### 验证

- g05 恢复 `face/eye/lash/brow/overlay = 13769/864/660/228/548`，与同体型一致；
  渲染确认虹膜正常。
- 十个敏感角色（含 F10）改前改后**逐槽面数完全一致**，5 个合成回归测试全过。
- 全量重跑无 `face`/`eye` 为 0 的告警。

### 顺带澄清：槽为 0 不一定是缺陷

新增的 `headSlots` 扫描还查出 f11 `lash=0`、k06 与 i01–i04 `brow=0`。逐个看渲染确认
**都是正常的**：f11 眼部整个被金色面罩盖住、k06 戴眼罩且刘海遮眉、i 体型的眉毛本来
就烘进 face 图（坑 #13 已有记载）。因此硬告警只覆盖 `face` 与 `eye` 两个"为 0 必错"
的槽，其余留在 `headSlots` 供人工判读，避免噪音淹没真问题。

---

---

## 2026-08-30 — Rise of Eros：修复 f05 "没有脸"（残缺原始材质表）

### 新增与修复

- **`roe_xps_addon.py` / `classify_head`**：原始材质槽里有 eye/brow/lash/tear 这类
  特征槽、却**没有任何 face 槽**时，判定这份表不可信，清空 names 与 indices 走几何
  回退。详见[避坑手册 #14](roe-material-pitfalls.md)。
- **`export_character_model_blender.py`**：统计 head 每个材质槽的面数，新增
  `headSlots` 与 `headFacePolygons` 两个 manifest 字段；`export_character_models.ps1`
  在 `headFacePolygons` 为 0 时红字报警。

### 问题与根因

用户报告 `pc_f05_hd.fbx` 与 `pc_f05_outfit1_hd.fbx` 导出后没有脸——一对眼球悬在头发
里，下半张脸空白。**所有既有检查都是绿的**：插件自检 `缺贴图 0`，manifest 的
`untexturedSlots`、`familyMismatches` 全空，face 槽还正确挂着
`pc_f_nk_face_rgbx_Albedo.png`。贴图没问题，**是那个槽一个面都没有**。

这两份 FBX 的 head 只保留了 `pc_f_nk_eyebrow` 和 `pc_f_nk_tears` 两个原始材质槽，
face 和 eyes 槽在打包时就丢了，整张脸的多边形挂在这两个残存索引上。`classify_head`
见到有原始槽名就信任：`source_is_tear` 把 11,172 个面判给透明罩层，
`source_is_brow_or_lash` 把另外 8,376 个面判给睫毛眉毛，face 槽剩 0 个面。

同角色的 `pc_f05_hd (1)` 压根没有原始槽名，走几何回退反而分对了（face 18,322 面）
——**一份残缺的表比完全没有表更有害**，所以正确做法是识别并丢弃它，而不是换 FBX：
`(2)` 才有正确的三槽身体分区，`(1)` 只有一个身体槽且会按通配符错挂成 outfit1 贴图。

### 验证

- f05 两个模型 face 槽由 0 恢复到 18,322 面，渲染确认脸、角、精灵耳与红披风配色正确。
- a06/a07/a08/b02/f06/f10/g09/i03/j01/m02 十个角色改前改后**逐槽面数完全一致**
  （0/10 变化），5 个合成回归测试全过。
- 全量重跑 123 个条目，无 `headFacePolygons=0` 告警。

### 顺带修的一个脚本坑

给 ps1 加中文告警字符串导致整个脚本解析失败（`Unexpected token`、`missing
terminator`），六个分片全部空跑，还把 manifest 覆盖成空的。**PowerShell 5.1 会用 OEM
代码页读取无 BOM 的 .ps1**，多字节中文在 `#` 注释里无害，在**字符串字面量里会拆出引号
破坏解析**。仓库既有 ps1 的中文一律只在注释里，字符串全 ASCII——这条现在写进了文件
注释。教训：改完 ps1 先跑
`[System.Management.Automation.Language.Parser]::ParseFile()` 验证再批量执行。

---

---

## 2026-08-30 — Rise of Eros：穿衣角色批量材质化 + 预览图，新内容盘点

### 新增与修复

- 新增 `scripts/riseoferos/export_character_models.ps1` 与其 Blender worker
  `export_character_model_blender.py`：把每个已提取角色目录里最合适的模型 FBX
  重建材质、把贴图打包进 `.blend`，并在**同一目录**渲染一张三视图预览 PNG
  （3/4 + 正面 + 头部特写，横向拼接）。这是 §4 裸模批量脚本的穿衣角色对应物。
- 全量执行结果：**120 个模型 PASS、0 FAIL、17 NOMESH**，共 7.0 GB。
  产物在 `D:\roe_exports\<id>\blend\<stem>.blend` + `<stem>_preview.png`，
  全量清单 `D:\roe_exports\character_models_manifest.json`。
- **候选回退与 NOMESH**：worker 的第一个参数改为 `;` 分隔的候选列表，按
  `hd → ld → nk → Prefab_nk_model → nk_bs` 顺序逐个导入，**先检查是否真有网格
  再挂材质**。d10 / e11 / i06 只有 0.3MB 的 `*_nk_bs.fbx`（纯骨架壳，本体复用
  同字母基础体），连同另外 14 个只有 `chara_bare_pc_<id>_nk.ab` 的活动 NPC 一起
  记为 `NOMESH`——这是资源本身的性质，不再算作失败。
- **二次贴图解析**（worker 内，未改动共享插件）：插件挂完材质后，仍无 Base Color
  的槽再查一次 Albedo 索引，**只在唯一命中时**才补挂。规则是逐级放宽的探针——
  原名 → 去尾部 `hd/ld` → 去尾部数字 → 武器再试角色自己的 `wp_<id>` 图集。
  修好 12 个模型的武器/护甲槽（`wp_a_R` ← `wp_a_12`、`pc_h08_hd_armor01` ←
  `pc_h08_hd_armor`、`pc_h07_hd_body2` ← `pc_h07_hd_body` 等）。**能匹配到两张
  图的一律不补**：挂错贴图比留灰更糟，e10 的第三个身体槽（只出 body1/body2）
  就按这条留灰。
- 预览渲染用 **Standard** 视图变换而不是 Blender 默认的 Filmic——Filmic 会把
  Albedo 图集去饱和，导致预览图没法用来判断有没有挂错贴图。补白色取自渲染背景
  的角像素，不再是黑边。
- 新增 `-ManifestPath`：默认那一个 manifest 不支持并发写，多进程分片跑时必须
  给每个分片单独一个，跑完再合并。本次即用 6 分片并行（24 核机器约 25 分钟）。
- README 新增 §5 说明本脚本；原 §5–§10 顺延为 §6–§11，正文交叉引用同步更新。
- 新增 `scripts/riseoferos/html/make_gallery.py` 与它生成的 `html/index.html`：
  按 manifest 出一页可搜索/按体型筛选的模型总览，每卡含预览图、模型名、blend
  完整路径（可复制）、网格与材质槽统计、缺图/补挂角标，附录是导出脚本用法。
  179 MB 预览图缩成 2.9 MB 缩略图（平均 25 KB），**写到
  `D:\roe_exports\_gallery\thumbs\` 而非仓库**——仓库不收游戏素材这条规矩不破。
  页面靠 `file://` 引用本机文件，换机器重跑一次即可。
  踩坑记录：`.card` 上的 `display:flex` 会盖掉浏览器对 `[hidden]` 的
  `display:none`，筛选看着失效，必须显式补 `.card[hidden]{display:none!important}`。

### 顺带处理的资源盘点

- **如何判断游戏有没有新内容**：不要看 Steam 安装目录的时间戳——2026-08-01 的
  整包重下把全部 14046 个 `.ab` 刷成了同一个 mtime，按时间比会误报几十个"过期"。
  正确做法是拿运行时缓存（`%USERPROFILE%\AppData\LocalLow\Pinkcore\...`，约 807
  个文件）和安装目录**按文件名 + 大小做差集**：只在缓存里的 = 全新，大小不同的
  = 更新过。
- 据此发现并处理：新角色 **m02**（已导出 FBX + 45 贴图，并材质化为
  `m02\blend\pc_m02_hd.blend`）、j10 / k02 的新装、m01 的女仆装
  （`suit_maid`，产出 `pc_m01_outfit1_hd.fbx`）、3 件 26AUG 新配饰、新敌人
  `en_flesh_horror_001`。
- **配饰的正确导法**：104 个配饰网格全在 `chara_components_common.ab` 一个包里，
  逐件的 `accessory_<hash>_*.ab` 只有几 KB、是索引存根，贴图在配对的
  `chara_tex_<hash>_*_obj001.ab`。按件建目录会得到 104 份完全相同的 FBX；正确做法
  是把 components_common + 全部 `chara_tex_*_obj001` 一次性提取到
  `D:\roe_exports\components_accessories\`（104 FBX / 285 PNG）。
- 删除假目录 `D:\roe_exports\g16`：18 个文件全是 g/f 家族公共贴图加一把
  `wp_g01`，没有任何 g16 文件；游戏里也不存在 `chara_*_pc_g16` 包（"g16" 只出现在
  `mainstageavg16`、`env_tex_painting16` 这类无关包名里）。

### 用户如何操作

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
.\export_character_models.ps1 -List            # 看可转清单和各自用的 FBX
.\export_character_models.ps1                  # 全部转换，已有产物跳过
.\export_character_models.ps1 -Only m02 -Force # 重做单个角色
```

`.blend` 内嵌贴图、脱离 `_textures` 也能打开；预览图就在 `.blend` 旁边。缺共享
头部贴图而失败时（b01/g04/g05/l01 本次即如此），先补一次
`.\extract_character.ps1 <id> -ExportTextures` 再重跑。

### 验证

- 123 个候选条目全部跑完：120 PASS / 0 FAIL / 17 NOMESH，磁盘上 120 个 `.blend`
  与 120 张 `_preview.png` 数量一致。
- manifest 审计：`familyMismatches` **全部为空**（没有任何模型挂上别的字母体型的
  公共脸/发贴图）；`untexturedSlots` 从 15 个模型降到 3 个，且都确认为资源本身
  没出对应图（a00 的 `liquid` 特效网格、e10 的第三身体槽、j06 的武器）。
- 目检渲染：a01、j01、h08、g04、m02 的预览图逐张确认脸/眼/睫毛/头发/服装/武器
  贴图正确。

---

---

## 2026-08-30 — Venus Vacation PRISM：素体排查结论与完整裸模组装

### 新增与修复

- 71 个角色候选全部转换目检（export_model.ps1 -Sheet 拼图 + Noesis 兜底）：
  官方素体仅 `0x8baaa1ce.fdata` 内一组模块化展示套件——836 带头假人体
  （皮肤贴图躯干为灰）、**840 无头全裸素体（完整皮肤贴图）**、843 配套头、
  844 配套发、852 手臂；另有 114/118/849 三个内衣体；其余全为服装体。
- 无名模型贴图解析走通：`character_assets.py --component` 的 g1m_id 路径 +
  `_infer_bundle` 包内相邻推断（836 全 21 槽、840 全 10 槽零缺失）；843 有
  6 张贴图缺失，新增 `profiles/nude840.json` 按 Tamaki 模式豁免
  （prune_if_unreferenced）。
- `character_assets.py`：face_v1 虹膜烘焙槽位对参数化
  （`postprocess.face_v1_iris_pairs`，默认 (2,25,26)/(3,35,36) 不变）——
  展示头 843 的眼贴图在 27/28、37/38。
- `blender_assemble_character.py`：`--face` 改为可选（自带头的身体可只配
  发型），无 FACE 时 head_fit 以 BODY 为基准、neck_fit 记为 null；其余
  验证门与产物不变。
- 组装成品：`nude840\complete_nnmhair\Nude840_NNMHair_Aligned.blend`
  （840+843+Nanami 发；face-alpha 1,4,5,7,8,9 修复眼周透明卡片、虹膜烘焙
  正确）。对位勘误：展示件彼此不共位——843 头比标准脸高 ~6.7，840 身体
  领口（zmax 134.7）又低于标准脖口（Nanami 参照 150.6），最初"抬发 +6.92"
  方向错误；正确做法是头 −16.5、发 −9.58（保持发-头相对 +6.92），颈胸
  接缝经 A/B 渲染目检确认消失。native 844 发型版与 836 版一并保留；
  FBX/GLB 为对位前导出，需要时从 Aligned.blend 重导。

### 操作与验证

- `export_model.ps1 -Sheet` 全量 36 候选拼图（Noesis FBX 兜底覆盖 glTF
  关节越界导入失败项）；840 组件三件套 FBX 回读六项验证全过；脸部近景
  目检：虹膜/睫毛/眼影正常，发型对位无露皮。

---

## 2026-08-30 — Venus Vacation PRISM：export_model.ps1 按需浏览候选模型

### 新增与修复

- 新增 `venusvacationprism\export_model.ps1` + `gltf_to_blend_preview.py`：
  `-List` 列出 71 个角色候选（索引/KTID/骨骼数/大小/已命名标注/已转换标记，
  `-AllModels` 看全部 1,527 个）；按索引/0xKTID/内部名称逐个转换
  （FDATA→G1M→gust basic glTF→`.blend`+前后视图 PNG+统计 marker），
  输出 `models\model_<idx>_<ktid>\`。首次运行自动构建 probe 清单与角色名
  对应表。定位是"按需识别原生模型"，带材质完整人物仍走 export_character。
- 排查记录：36 个未命名角色候选中最大的 idx_830（34.4 MiB / 53 网格 /
  317,086 顶点 / 364 骨）实测为**便服套装体**（T恤短裤凉鞋），非素体；
  BODY 类模型无头/由 FACE+HAIR 补全是游戏拆件设计，并非导出缺失。
  素体是否存在的结论待逐个转换其余候选后更新。

### 操作与验证

```powershell
.\scripts\venusvacationprism\export_model.ps1 -List
.\scripts\venusvacationprism\export_model.ps1 830
```

- 实测 `-List`（71 行，命名/转换标注正确）与 idx_830 全链路
  （glTF 720KB、blend 98MB、前后预览渲染成功，高度 148cm 完整）。

---

---

## 2026-08-30 — DOA6 / Throne of Desire：补齐导出总览画廊

三个游戏现在都有和 `riseoferos/html/` 同款的画廊（manifest → 缩略图 → 自包含单页），
结构一致，只是各自的分组维度和附录内容不同。

### 新增

- `scripts\doa6\html\`：DOA6 画廊。网格名在组装时已被重命名为
  `<部件目录>_sm<N>`，据此归类部件；服装部件来自 `<Label>_cos` 暂存目录的即判定为
  **mod 变体**（紫色徽标），facet 是 官方 / mod 变体。附录含三部件表、
  `export_full.ps1` 与 `export_nude_mod.ps1` 用法、A/B 两条材质路线、
  以及"别用 Cethleann 解 DOA6"等坑。24 个模型（含 5 个 mod 变体）。
- `scripts\throneofdesire\html\`：ToD 画廊。递归扫导出根下全部 blend，
  `female_all\` 下归为**批量裸模**、其余归为**单独导出**（facet），并入
  `female_export_manifest.json` 的批量状态；统计含面数与贴图打包数。
  附录说明 NFS+NIF/KFM 格式、`build_codecs.py` 前置、以及"静态网格+未绑定骨架"
  这一当前限制。17 个模型（13 批量 + 4 单独）。
  缩略图按 `<组>_<模型>.jpg` 命名——同名模型可能既在批量里又有单独导出。

### 验证

- DOA6：24 卡片 / 24 缩略图 / 页面 37.0KB，官方与 mod 变体分类正确。
- ToD：17 卡片 / 17 缩略图 / 页面 30.3KB，批量与单独导出分组正确。

---

## 2026-08-30 — DOA5LR：新增导出总览画廊（对齐 riseoferos/html）

### 新增

- `scripts\doa5lr\html\collect_manifest.py`：Blender 无头逐个打开 `_blends\*.blend`，
  按网格名前缀（`WGT_body*`/`WGT_face*`/`WGT_hair*`/`MOT01_Head*`）归类部件，统计
  网格/材质/透明材质/贴图数，写出 `doa5lr_models_manifest.json`；缺脸、缺发、贴图
  过少会记为告警。
- `scripts\doa5lr\html\make_gallery.py`：读 manifest 生成自包含单页
  `html\index.html`（缩略图网格、搜索、按封包筛选、只看告警、点图看原图、
  一键复制 blend 路径）。沿用 ROE 画廊的视觉与交互；缩略图写到
  `D:\doa5lr_exports\_gallery\thumbs\`，**不进仓库**。
- 封包徽标现扫 `chara_common`/`chara_initial` 索引得出，直接对应 `-Archive` 参数。
  踩坑：匹配必须精确到 `<角色>_COS_001.TMC`，用子串会被 `KASUMI_BOSS_COS_001.TMC`
  命中，把霞误标成 `chara_common`。

### 验证

- 21 张卡片、21 张缩略图（共 0.9MB）、页面 35.5KB；霞/绫音正确标注
  `chara_initial`，其余 `chara_common`；两条告警均属实（Alpha-152 素材本身仅 5 张
  贴图、`KASUMI_DLC_011` 是未加 `-Hair` 的光头对照件）。

---

## 2026-08-30 — DOA5LR：修正部件对齐与 Alpha 判据（用户反馈的 4 个缺陷）

### 修复

用户反馈四处问题，逐个定位：

- **红叶/穗香「头发和头没对齐」、女天狗「没有脸」** —— 根因是我加的"对齐"本身。
  实测**绝大多数角色的脸/头发本来就和服装同处一个坐标系**（脸 Z 已接在颈口上方、
  头发顶端已到头顶），直接叠加即正确；早期版本无条件按包围盒对齐，把对的挪歪了：
  马尾的包围盒顶端是发梢而非头顶 → 头发被压到脸前面；女天狗的翅膀把身体包围盒
  撑大 → 脸被误判"不在位"而整个挪走。现在默认不动，判定改用部件**顶端**是否够到
  身体顶端（用底端会被马尾误导），只搬真正不在身体坐标系的部件（霞的头发）。
- **皮肤/衣服半透明起噪点** —— Alpha 判据不够严。仅要求">2% 全透明像素"会被两类
  冒充者骗过：穗香 `Tex_01`（62% 全透明但 alpha 最大只有 0.34）、穗香脸部贴图
  （3% 全透明、max 0.99，但均值仅 0.12 → 几乎没有实心区域）。改为**同时**要求
  **>2% 全透明 且 >4% 全不透明**（镂空遮罩必然"该实的全实、该空的全空"）。
  Honoka 的 alpha 材质数 95→65，Helena 40→21，Rachel 48→19。
- **Alpha-152 材质全白** —— 不是 bug。她三个部件加起来只有 8 张贴图
  （服装 2 张：一张 256×256 带绿调 + 一张 64×64 纯白），游戏里靠特殊半透明
  shader 表现，原始素材本身就没有颜色贴图。已在文档中说明。

### 验证

- 19 个 blend 全部用修正后的逻辑重建，红叶/女天狗/穗香的头部特写渲染确认正常
  （脸可见、头发在头后、皮肤实心），Marie/霞等原本正常的未被改坏。

---

## 2026-08-30 — DOA5LR：19 名女性角色批量导出 + 三部件对齐 + Alpha 语义修正

### 新增与修复

- **发现 DOA5LR 也是三部件**：`COS_NNN` 服装**不含头部**，脸是独立的
  `<角色>_FACE`（无编号），头发是 `<角色>_HAIR_NNN`。此前只导服装+头发会得到无头
  模型。`export_full.ps1` 新增 `-Face` / `-FaceTmc`。
- **三部件对齐逻辑**（`build_blend.py`）：三者坐标系互不相同。服装作基准；脸的 Z
  已在身体坐标系里但 X 有存储偏置（霞实测 +0.0037）→ 只居中 X；头发用自己的局部
  原点 → 整体搬到头部锚点顶部。锚点优先级 `*Head*` 网格 > 已就位的脸 > 身体包围盒
  顶部，故部件顺序强制为 服装 → 脸 → 头发。
- **修正 Alpha 语义**：DOA5LR 部分贴图把高光遮罩塞在 diffuse 的 alpha 里
  （实测 `Tex_27` 取值 0.00~0.91 连续、全透明/全不透明像素占比均为 0%）。无差别
  接到 Principled.Alpha 会让皮肤变成半透明抖动噪点。新增 `has_real_transparency()`
  用 numpy 采样判定（要求 >2% 全透明像素；头发实测 30~39%，身体 0%），只有真透明
  贴图才接 Alpha + HASHED，其余 OPAQUE。19 个成品已用修复后逻辑重建。

### 操作与验证

- 19 名女性角色批量（workflow 并行 19 agent，129 秒）：**19/19 成功**，
  全部 `COS_001 + FACE + HAIR_001` 三部件，4.7~21.4MB。霞/绫音在 `chara_initial`，
  其余 17 人在 `chara_common`。Alpha-152 仅 4.7MB 属正常（无服装半透明克隆体，
  ALPHA_MATERIALS=0）。
- 产物索引见 `D:\doa5lr_exports\README.md`，操作见 `scripts\doa5lr\EXPORT_GUIDE.md`。

---

## 2026-08-30 — DOA5LR：export_full.ps1 支持外部 mod TMC（-TmcFile / -HairTmc）

### 新增与修复

- `export_full.ps1` 新增 `-TmcFile` / `-HairTmc`：直接吃外部 `.TMC`（+同目录同名
  `.TMCL`）出带材质 .blend，用于社区 nude/服装 mod；可与官方部件混用
  （mod 身体 + 官方发型）。`-TmcFile` 也接受目录（取其中第一个 `.TMC`）。
  中转目录 `D:\doa5lr_exports\_mods\<TMC名>\`。
- 修复 PowerShell 函数把内部脚本 stdout 当作返回值的坑：`New-PartFromArchive` 里
  `export_character.ps1` 的输出会混进 `$partDirs`，导致后续路径参数报
  "A parameter cannot be found that matches parameter name 'File'"。内部调用
  统一 `| ForEach-Object { Write-Host $_ }` 消费掉。
- 确认 DOA5LR **无官方 nude**：全部 36 个封包、12,625 个条目名搜
  `nude/naked/bare/skin/under/lingerie` 零命中（此前只查过名称库）。

### 验证

- 外部 TMC（拷官方 TMC/TMCL 到独立目录模拟 mod）+ 官方 `KASUMI_HAIR_001` 混用：
  产物统计与直接从封包导出完全一致（59 材质 / 82 贴图 / 13.7MB），路径正确。

---

## 2026-08-30 — DOA5LR：补齐 .blend 组装链路 + 全封包可解析

### 新增与修复

- `scripts\doa5lr\build_blend.py` + `export_full.ps1`：DOA5LR 现在也能一键出带材质
  `.blend` + 预览图（此前只到 FBX+DDS）。要点：DOA5LR 的 FBX **自带**材质→贴图
  连接（Noesis 的 doa5pc 插件写入 Diffuse/Normal/Specular），因此**不需要** DOA6
  那套材质映射解析；脚本只按统一接法重建（法线 Non-Color + Normal Map、Alpha
  HASHED）。
- 修复 `extract_lnk.py` 把数据体魔数写死为 `CHCM` 的 bug——魔数其实是各封包自己的
  4 字节标签（`CHIN`/`STCM`/`P25C`…），结构一致。改为只做结构校验后，**36 个封包
  全部可解析**（此前只有 chara_common）。据此点清模型总数：TMC 1099 个，
  其中角色模型 678 个 / 34 名角色。
- `build_blend.py` 处理两个 DOA5LR 特有问题：① Noesis 以 scale 0.01 导出，角色仅
  ~1.6cm 高会整个落在相机近裁剪面内（渲染全空）→ 归一到 ~1.7 单位；② 头发是独立
  TMC 且用自己的局部原点、FBX 无骨架 → 按几何对齐到身体 `*Head*` 网格的包围盒
  （X/Y 中心 + 顶部），`export_full.ps1 -Hair` 一并处理。

### 验证

- `KASUMI_DLC_011` + `KASUMI_HAIR_001` → 13.7MB .blend（59 材质、82 贴图打包、
  头发对齐 dz=0.005），渲染正常。

---

## 2026-08-30 — DOA6：19 名女性角色批量导出 + nude/mod 变体管线

### 新增与修复

- `scripts\doa6\export_full.ps1`：官方角色一键出带材质 .blend（三部件提取 →
  matmap → PNG → 组装 + 渲预览）。
- `scripts\doa6\export_nude_mod.ps1` + `mod_matmap.py`：REDELBE layer2 mod
  （zip/目录）→ nude 变体 .blend，自动接官方发型/脸。双路线：mod 替换的服装编号
  本机存在时走原版 ktid 链（精确）；替换未安装 DLC 位时走启发式（按网格顶点数
  分配部位），猜错用 `-Assign "3=f01,5=body"` 纠正。
- `scripts\doa6\EXPORT_GUIDE.md`：官方与 nude 两条路线的完整操作指南（与脚本同目录）。
- `D:\doa6_exports\README.md`：产物索引（19 官方 + 4 变体）、角色花名册、目录结构。

### 操作与验证

- 19 名女性角色批量（workflow 并行 19 agent，4 分钟）：**19/19 成功**，35~60MB/个。
  自动处理特例：NIC/MAI/SNK 的 `COS_000~003` 是无 ktid 占位体，回退 `COS_004`；
  PHF 的 HAIR_001 官方无贴图（白模头发）。
- nude/mod 变体 4 个已验证渲染正确：HEL_Helena_Nude（路线 A）、
  MOM_Momiji_Malf / LIS_Lisa_Malf（路线 B 一次到位）、
  AYA_Ayane_Malf（路线 B + `-Assign` 纠正皮肤/衣物互换）。

---

## 2026-08-30 — DOA6：材质链解析 + 一键组装带贴图 Blend（Momiji 验证）

### 新增与修复

- `scripts\doa6\g1m_matmap.py`：解 g1m G1MG 材质段 + 部件 .ktid + kidssingletondb
  的 TexContext 对象（属性 0x6c7321d2），产出 submesh→g1t 贴图名的精确映射 JSON。
  发现并绕开 Cethleann OBJDB 解析器读不了 DOA6 `_DOK` 容器的问题
  （Nyotengu.KTID 因此只会产出空 g1t）。
- `scripts\doa6\build_blend.py`（Blender 3.6 无头）：导入 COS/HAIR/FACE 三部件
  FBX、按 matmap 挂 albedo+normal（HASHED 透明）、打包贴图、存 .blend 并渲染预览。
  规避 FBX 占位 Image 使 pack_all 失败的问题（逐图 pack）。
- `scripts\doa6\import_mod.ps1`：任意 DOA5LR/DOA6 mod（zip/目录）批量转 FBX+DDS。

### 操作与验证

- Momiji 完整角色：`MOM_COS_001`+`MOM_HAIR_001`+`MOM_FACE_001` 三部件导出、
  30 张 alb/nmh PNG、组装为 `D:\doa6_exports\MOMIJI_COS001.blend`（54.8MB，贴图内嵌）
  并渲出正确预览（脸/马尾/服装纹样/alpha 均正常）。流程见 doa6/README §3.5。

---

## 2026-08-30 — 新增 DOA5LR 与 DOA6 提取管线（自研解包器 + Noesis 转换）

### 新增与修复

- 新目录 `scripts\doa5lr\`：`extract_lnk.py`（.bin/.lnk 解包，Python 移植 Archive
  Tool 1.2.1 的 C# 算法：LFMO 混淆名索引 + file5lr.dat 名称库 + doaKey/动态 key XOR
  解密 + 分块 zlib 解压）与 `export_character.ps1`（按名称前缀批量 TMC/TMCL→FBX+DDS，
  经 32 位 Noesis + doa5pc_custom.py 插件）。
- 新目录 `scripts\doa6\`：`extract_rdb.py`（KTGL v2 RDB 解包：48 字节条目 +
  `offset@size#bin&sub` 地址串 + 内层 IDRK 头 + 分块 zlib/lz4）与
  `export_character.ps1`（CharacterEditor 模型 + MaterialEditor 贴图按服装一键导出，
  经 Noesis64 + ProjectG1M）。
- **修复 Cethleann.DataExporter 的截断 bug**：其 zlib 每块只读一次导致 1536 个 g1m
  中 1300 个在 ~80% 处截断，坏文件令 ProjectG1M 崩掉 Noesis（"打开就 crash"的根因）；
  自研解压后全部大小与 G1M/G1T 头部声明一致。
- 工具落地：`E:\tools\doa5lr\`（doaKey、file5lr.dat、Archive/Texture/DLC Tool、
  Blender TMC importer）、`E:\tools\doa6\`（Cethleann 1.2.1 套件 + filelist CSV、
  ProjectG1M 1.8.1/1.7.4.2）、Noesis 插件就位（32 位 `plugins\`、64 位 `plugins\x64\`）、
  便携 `E:\tools\7zr.exe`。

### 用户如何操作

- DOA5LR：`scripts\doa5lr\export_character.ps1 HONOKA`（或 `-List`）。
- DOA6：`scripts\doa6\export_character.ps1 HON_COS_002`（或 `-List`）。
- 产物分别在 `D:\doa5lr_exports\`、`D:\doa6_exports\`。

### 实现原理与兼容性

- 两游戏格式细节见 `scripts\doa5lr\README.md`、`scripts\doa6\README.md` §3。
- .ps1 带 UTF-8 BOM（PowerShell 5.1 中文脚本必需）；Python 端零第三方依赖
  （lz4 条目才需 `pip install lz4`，DOA6 实测全 zlib）。

### 已执行的验证

- DOA5LR：HONOKA_COS_001 TMC 魔数校验、FBX+30 DDS；HONOKA_HAIR_001 全链路 exit 0。
- DOA6：HON_COS_001.g1m 尺寸==头部声明；HON_COS_002 全链路 FBX 2.6MB + 154/154 DDS；
  `*HONCOS001_*` 定向抽 MaterialEditor 83 个 g1t 零失败（含 22MB 4K 图）。

---

## 2026-08-30 — Venus Vacation PRISM：export_character.ps1 对齐 ROE 操作方式

### 新增与修复

- `venusvacationprism\export_character.ps1` 从单行透传升级为 ROE
  `extract_character.ps1` 风格入口：位置参数直接给名字（中/英/内部代码，
  逗号分隔多名）、`-List`（角色与支持状态）、`-ListModels [-Probe]`
  （生成 models.csv/json/md 清单）、`-Format blend,fbx,glb`、`-Plan`、
  `-Resume`、`-AssetsOnly`、`-GameRoot`/`-OutputRoot` 覆盖默认。
- 旧 GNU 风格调用（`--name 穗香 --formats ...`）检测到 `--` 开头即原样
  透传给 `export_character.py`，完全向后兼容。
- `scripts/README.md` 推荐入口更新为 `export_character.ps1`；目录 README
  增加"快速上手"一节。

### 操作与验证

- 实测四种模式：`-List`（6 名角色状态正确）、`Fiona -Plan`（默认游戏目录/
  输出/工具链解析正确）、`-ListModels`（1,527 个 G1M 清单写出）、
  `--list-characters` 透传（exit 0）。

---

## 2026-08-30 — Stellar Blade：合并为单一主骨骼（可整体 pose）

### 新增与修复

- `validate_eve.py` 新增 `--merge-armatures`：把脸/发型/马尾/短发束骨架合并进
  身体骨架成单一 `Eve_Armature`。要点：①合并后重名骨（`.001`）去重，子骨转挂
  原骨，顶点组权重自然落到身体同名骨；②发型/马尾自己的 `Root` 位于挂点而非
  角色原点，不能与身体 `Root` 去重——改名为 `Hair_Root`/`HairTail_Root` 携带骨
  （连同网格顶点组同步改名）并挂到 `SC_Hair`（无 socket 的 UE Viewer 身体回退
  `Bip001-Head`）/`Ab-TL-HairB01`；③头部小骨挂 `Bip001-Head`；④网格父级与
  Armature modifier 全部改指主骨架。
- 首版曾把发型 Root 直接去重进身体 Root，转头测试暴露头皮不跟随；携带骨方案
  修复后转头渲染确认整个发型（发冠/刘海/侧发/马尾根）随头运动。
- `export_eve.ps1` / `export_outfit.ps1` 默认启用合并，加
  `-KeepSeparateArmatures` 恢复旧的每组件独立骨架结构。

### 操作与验证

- 三个 blend 均已重建为单骨架：标准装 329 骨、裸模 189 骨、Nikke_06 204 骨
  （各去重 17 根）；Nikke_06 上 `Bip001-Head` 旋转 25° 的姿势渲染目检通过。
- 补充（同日）：PSK/UEFormat 导入的骨显示长度固定 1cm，厘米级角色在视口里
  是一团小点。`validate_eve.py` 新增 `resize_bone_display`：有子骨的取到最近
  子骨的距离、末端骨继承父骨 60%（限 1–25cm），只沿现有 Y 轴改长度，不动
  骨头位置/朝向/roll，蒙皮与局部轴不受影响。三个 blend 重建后骨长中位数
  1.0cm → 约 4.35cm，报告新增 `bone_display` 字段记录前后值。

---

## 2026-08-30 — Stellar Blade：眼部预览材质优化

### 新增与修复

- 诊断出旧眼部预览发死的两个原因：`M_MikeEyeBlend_Inst` 与
  `MI_EVE_Eyeshadow_Occlusion` 两层壳的几何覆盖整个眼眶，近黑不透明/半透明
  设置把眼球整体压暗成"重烟熏+黑洞"；虹膜源贴图是为 UE 光照折射栈制作的
  暗色图，平铺进 Eevee 预览时读作全瞳孔。
- `validate_eve.py` 眼部调整：MikeEyeBlend 改为浅暖色 HASHED 半透明
  （alpha 0.10）、eyeshadow occlusion 减淡（alpha 0.55→0.12）、虹膜贴图后
  插入 HSV 提亮（Value 1.8 / Saturation 1.15，标定半径 0.055 不变）、
  EyeLight 眼神光增强（emission 0.15→0.5）。
- 排错记录：一度怀疑半径/粗糙度，经"隐藏全部壳层"的排除性渲染确认暗盘
  来自壳层而非眼球材质本身。

### 操作与验证

- 标准装、裸模、Nikke_06 三个 blend 均已重建；脸部近景目检：眼白透亮、
  虹膜有层次并带眼神光，眼周恢复为柔和红棕妆感。几何/骨骼统计不变。
- 二次微调（同日）：反馈眼仁偏小，可视虹膜半径 0.055→0.07（约放大 27%），
  HSV 提亮 1.8→2.6、饱和度 0.95 让虹膜纹理透出；A/B 渲染对比后定稿，
  三个 blend 再次重建，正面近景虹膜大小与游戏内观感一致。

---

## 2026-08-29 — Stellar Blade：export_outfit.ps1 任意服装一键出 Blender

### 新增与修复

- 新增 `scripts/stellarblade/export_outfit.ps1`：按包名（含 DLC）一条命令产出
  组装好的 `.blend`——PSK 缺失时自动用专用 UE Viewer 导出，随后无头运行
  `validate_eve.py` 把服装身体与共享的 Face_003/发型/马尾/短发束组装、渲染
  并出 JSON 报告；输出 `blender\Eve_<包名>.blend`。依赖 `export_eve.ps1`
  已跑过一次（共享组件、UEFormat 快照与对齐参考 JSON）。
- `validate_eve.py` 的 `--body-diffuse` 现在也接受**贴图目录**：按材质名
  自动匹配各材质槽的 `*_A` albedo（去掉 `MI_/MA_` 前缀精确匹配，退化为
  token 重合度 + 文件大小排序），多材质服装不再整体套一张贴图；报告新增
  `preview_materials.body_assignments` 记录逐材质匹配结果。

### 操作与验证

```powershell
.\scripts\stellarblade\export_outfit.ps1 CH_P_EVE_Nikke_06
```

- 实测 NIKKE Alice（DLC_2，UV1/UV2/Decal 三材质）：5 网格 / 122,988 顶点 /
  221 骨，三个材质分别匹配到 UV1_A/UV2_A/Decal_A，渲染目检粉色连体衣、
  外套、SUPER 贴片、球鞋与共享脸/发型全部正确。

---

## 2026-08-29 — Stellar Blade：Eve 服装清单与粉色判定文档

### 新增与修复

- 新增 [`docs/stellar-blade-eve-outfits.md`](stellar-blade-eve-outfits.md)：
  Eve 全部服装的编号→名称对照（59 个编号装 + 7 个特殊装 + NieR/NIKKE 联动
  DLC 各 4/6 套；名称取自 Modding Guide ID's Library，存在性用 `.utoc` 索引
  核对），以及基于 299 张 albedo 贴图色相统计 + 目检的粉色判定：真正粉色仅
  Pink Bear（45 TypeB）与 NIKKE Alice Cooling Suit（DLC_2 Nikke_06）两套。
- 勘误：本机安装包含 `SB/Content/DLC_1/`（NieR）与 `DLC_2/`（NIKKE）两个联动
  DLC；`list_models.py` 默认过滤 `SB/Content/Art/Character/` 不含 DLC 挂载，
  统计 DLC 需另用 `--path-filter`。

---

## 2026-08-29 — Stellar Blade：修正主发型 180° 朝向（刘海朝后）

### 新增与修复

- 发现主发型 `EVE_HR_01` 自首次验证以来一直反戴：独立 UE Viewer PSK 与马尾
  一样带 180° 局部轴翻转，而旧对齐只把发型 Root **平移**到 `SC_Hair` 插槽位置，
  未恢复旋转，导致刘海在后脑、颈后露出发型底面（即上一条记录里误判为
  "发型紧贴侧区"的裸露带）。
- `validate_eve.py` 主发型对齐改为 `SC_Hair` 完整静置矩阵（位置+旋转），与
  马尾/短发束的共有骨方法一致；`--alignment-reference` 回退路径自动继承修正
  后的完整矩阵。

### 操作与验证

- 标准装与裸模均已用修正后的对齐重建。渲染目检：正面平齐刘海位于额前、
  编发冠与侧发正确环绕面部；后脑马尾高扎、发量完整覆盖，无裸露带。
  组件数量与顶点/骨骼统计不变（5 网格 / 346 骨）。

---

## 2026-08-29 — Stellar Blade：补齐缺失的后颈短发束 EVE_HR_Tail_Short

### 新增与修复

- 确认此前组装的 Eve（标准装与裸模）后脑左侧有一块裸露区域：默认发型实际由
  4 个网格组成，除主发型和长马尾外还有挂在 `Bip001-Head` 下的后颈短发束
  `EVE_HR_Tail_Short`（7,466 顶点 / 7,210 面 / 8 骨），此前未导出。同目录的
  `EVE_HR_01_ShortTail` 则是长马尾的"短马尾"替换选项（仅 Root 锚），不叠加。
- 专用 UE Viewer 补导 `EVE_HR_Tail_Short.psk` 与 `EVE_HR_01_ShortTail.psk` 到
  `umodel_exports`；`validate_eve.py` 新增可选 `--tail-short`，按双方共有的
  `Bip001-Head` 完整静置骨矩阵对齐（误差 0），并入发型验证材质；
  `export_eve.ps1` 组件清单加入 `tail-short`（缺失时自动补导并传参）。

### 操作与验证

- 标准装与裸模均已重建：5 网格；标准装 114,589 顶点 / 141,084 面 / 346 骨。
  后脑视角渲染目检：短发束正确垂落在脑后与背部，原空缺被覆盖（余下发际
  边缘为发型本身的紧贴侧区，位于编发之下）。

---

## 2026-08-29 — Stellar Blade：EveOriginalProportions 裸模导出与组装

### 新增与修复

- 用重新下载并校验的专用 UE Viewer（`umodel_stellar_blade_v6.zip`，SHA256 与
  文档记录一致 `61A641D3…F550`，现存放 `E:\tools\umodel_stellarblade\`）从本机
  `_probe_stash` 中的 EveOriginalProportions Mod 导出全部 4 个变体
  （barefoot / barefoot_pubic / highheels / highheels_pubic）的
  `CH_P_EVE_InnerSuit.psk` 网格与 custombody/heels 贴图，各 12 对象，输出到
  `D:\stellarblade_exports\umodel_mod_exports\<variant>\`。Mod 是独立 IoStore
  三件套，UE Viewer 需要同目录有游戏的 `global.utoc/ucas`，脚本流程用临时
  staging 目录解决。
- `validate_eve.py` 新增 `--alignment-reference`：UE Viewer PSK 不含 socket，
  裸模骨架缺 `SC_Hair`（马尾锚 `Ab-TL-HairB01` 仍在）；该参数从既有验证报告
  JSON 复用记录的发型根变换（两副骨架静置姿态相同），马尾仍按共有骨原生对齐。
  默认行为不变。

### 操作与验证

- 组装产物：`D:\stellarblade_exports\blender\Eve_Nude_Barefoot.blend` 及
  `validation\Eve_Nude_Barefoot.png/_face.png/.json`。
- 实测：4 网格 / 113,229 顶点 / 179,668 面 / 198 骨（裸体 53,742 顶点、
  107,424 面、159 骨、材质 `SkinEve`），马尾锚点误差 ≈1.1e-6，渲染目检
  脸/发型/马尾对位正确、赤足贴地。游戏与 Mod 资产仍不入仓库。

---

## 2026-08-29 — Stellar Blade：list_models.py 模型清单与未导出差集

### 新增与修复

- 新增 `scripts/stellarblade/list_models.py`：纯 Python 只读解析 Paks 下所有
  `.utoc` 的 IoStore 目录索引（FIoStoreTocHeader 144 字节 + FIoDirectoryIndexResource
  目录/文件/字符串表；Stellar Blade 索引未加密，无需 AES、FModel 或 UE Viewer），
  列出全部包路径并与导出根目录里的 `.psk/.uemodel/.fbx/.glb/.gltf/.blend`
  按文件名差集，回答"还有哪些模型没导出"。
- 支持 `--path-filter`/`--glob`/`--include-exported`/`--all-files`/`--csv`；
  "模型包"为命名启发式（排除贴图/材质/动画/物理/碰撞/CameraBone/Facial 等），
  脚本输出中明确标注该局限。

### 操作与验证

```powershell
python scripts\stellarblade\list_models.py                     # 未导出模型包
python scripts\stellarblade\list_models.py --include-exported  # 全表带状态
```

- 本机 1.4.1 实测：7 个 `.utoc` 共索引 224,322 个文件（主容器 221,592，与专用
  UE Viewer 报告的 228,867 同量级，后者含 .pak 内文件）；角色树筛出 1,957 个
  模型包候选，已导出 6 个（与实际状态一致：身体、Face_001/003、Teeth_001、
  主发型、马尾，且逐个列出对应本地文件路径），未导出 1,951 个。

---

## 2026-08-29 — Stellar Blade：一键封装脚本 export_eve.ps1

### 新增与修复

- 新增 `scripts/stellarblade/export_eve.ps1`：把已验证的 Eve 手动流程包成一条命令，
  接口风格与 `riseoferos/extract_character.ps1`、`export_nude_models.ps1` 一致
  （`-List`/`-Check`/`-Force`/`-RefreshHair`，参数化 `-GameRoot`/`-ExportRoot`/
  `-BlenderExe`/`-UmodelExe`/`-UEFormatSource`/`-OutputName`）。
- 流程：①校验 FModel 手动导出（身体 PSK、Face_003 `.uemodel`、身体漫反射，含
  `ACTRHEAD`/`UEFORMAT` 文件头检查；FModel 无法无头运行，缺失时打印配置指引）；
  ②头发/马尾/贴图缺失时用专用 UE Viewer CLI 自动补导，校验 `Found N game files`
  识别错误构建，`~mods` 有 Mod 时告警；③自动解析/下载并补丁 UEFormat 源码；
  ④无头运行 `validate_eve.py` 并解析 `STELLARBLADE_EVE_REPORT=` 结果。
- 重要修正：UEFormat 上游 main 已重构 `importer/logic.py`，
  `ueformat-blender36.patch` 不再适用于 main。自动下载现在钉住补丁基线 commit
  `58d1abf52d6b2e5ad8d00e7c31bc98495231e642`（`importer/logic.py` blob `5020309`
  与补丁前像一致）。另外该补丁是零上下文 diff，`git apply` 必须带
  `--unidiff-zero`，脚本已内置。

### 操作与验证

```powershell
.\scripts\stellarblade\export_eve.ps1 -Check   # 只检查输入
.\scripts\stellarblade\export_eve.ps1          # 组装 + 验证（输出存在则跳过）
```

- 本机全流程实测（独立 OutputName，未覆盖既有验证输出）：自动下载钉版快照、
  `git apply --unidiff-zero` 干净应用、Blender 3.6.15 组装通过，结果与
  2026-08-02 手动验证完全一致：4 网格 / 107,123 顶点 / 133,874 面 / 338 骨、
  53 源 Morph → 54 Shape Keys、发型插槽误差 0、马尾锚点误差 ≈2.1e-6，
  渲染图目检正常。

---

## 2026-08-29 — Operation LOVECRAFT: Fallen Doll 提取调研与脚本骨架

### 新增与修复

- 新增 `scripts/fallendoll/`：`probe_pak.py`（只读探测 pak 版本/加密/索引，不接触
  key）、`prepare_fmodel.ps1`（验证安装、建隔离工作区、打印 FModel 配置指引）、
  `export_models.ps1`（扫描 FModel 已导出的 SkeletalMesh，批量材质化为 Blend/FBX/GLB，
  接口/manifest 与 ROE/FF7RB/ToD 一致）。下游材质直接复用已验证的 FF7 Rebirth
  worker `export_ff7rb_model_blender.py`（两者同为 UE4.26 FModel 导出）。
- 调研结论（`docs/fallen-doll-extraction.md`）：引擎 UE4.26（ChaosCloth 存在、apex
  缺失、pak v9 印证），项目名 Paralogue，Desktop/VR 各一个约 5.4 GiB 的 pak，pak
  version 9 且**索引 AES 加密**。提取被 AES key 阻塞。
- 实测排除本机取 key 途径：零 key、exe 内 64 位 hex 候选、shipping exe 全量滑窗爆破
  （高熵 4 对齐 55 万窗口 0 命中；step-1 全覆盖 11 个候选经严格 mount-point 校验全为
  误报，实为 x86 指令/字符串常量如 `ragePakList`）。**key 不以明文连续 32 字节存在于
  exe 中**；合法获取途径（社区 UE key 库、运行时取 key）记入文档，key 不入仓库。

### 操作与验证

```powershell
python scripts\fallendoll\probe_pak.py         # 探测（不需要 key）
.\scripts\fallendoll\prepare_fmodel.ps1        # 工作区 + FModel 指引
.\scripts\fallendoll\export_models.ps1 -List   # 拿到 key、FModel 导出后使用
```

- `probe_pak.py` 对 Desktop/VR 两个 pak 均正确报告 pak v9 + 索引加密。
- `prepare_fmodel.ps1` 端到端跑通（探测 + 建工作区 + 打印三项 FModel 配置）。
- `export_models.ps1` 两个 ps1 语法解析通过；`-List` 空树与非空（伪造 FModel 布局）
  均正确；委派链用伪造模型端到端跑到真实 Blender worker，如实在「缺 Base Color 贴图」
  处 FAIL 并写 validate 快照 manifest——证明扫描/委派/错误传播/manifest 全部工作，真实
  带贴图导出时即 PASS。
- 待办：AES key 到位后进行真实导出与裸模结构判定。

---

---

## 2026-08-29 — Throne of Desire 裸模批量导出统一入口

### 新增与修复

- 新增 `scripts/throneofdesire/export_nude_models.ps1`：与 ROE 同名脚本约定一致的
  PowerShell 入口（`-List` / `-Only` / `-Format` / `-ValidateOnly` / `-Force`，本机
  默认路径零参数即跑），包装既有 `batch_export_female.py`。模型清单从 Python 模块的
  `FEMALE_MODEL_IDS` 动态读取，保持单一事实源。ToD 女性 h 系模型本体即裸模（衣服为
  默认隐藏的附件网格，FBX 只含基础身体+骨架），无需 mod。
- `-ValidateOnly` 调用既有 `validate_female_exports36.py` 在 Blender 中重开已导出的
  Blend/FBX 复检，报告写独立 `female_export_validation.json`，不触碰导出 manifest。
- 修复 `batch_export_female.py` 的 manifest 覆盖问题（与 ROE `-Only` 同型）：
  `--models` 子集运行改为合并更新 `female_export_manifest.json`，按 13 套规范顺序保
  留未重导出的记录；损坏的旧 manifest 安全忽略。真实导出前预检两个贴图解码器并给出
  `build_codecs.py` 构建提示。

### 操作与验证

```powershell
cd E:\code\othercode\ripper_tpose\scripts\throneofdesire
.\export_nude_models.ps1 -List
.\export_nude_models.ps1 -Only h005,h020 -Force
.\export_nude_models.ps1 -ValidateOnly
```

- 真机 `-List` 正确显示 13 套全部 COMPLETE；`-Only h005` 断点续跑秒级 skip，且
  manifest 保持 13 条完整记录（修复前会被覆盖成 1 条），`requested_models` 如实记录
  本次子集。
- `-ValidateOnly -Only h005,h020` 重开验证 2/2 ok 并写入独立报告。
- 缺解码器时预检报错并给出构建指引；`build_codecs.py` 经 WSL g++ 重建两个解码器后
  恢复正常。纯 Python 单测
  `tests/test_batch_export_female_manifest.py` 5/5 通过（合并、幂等、规范排序、损坏
  manifest 容错）。
- 沿用限制不变：产物为静态网格 + 未蒙皮静止骨架（蒙皮/动画尚未恢复），XPS 不支持。

---

---

## 2026-08-29 — FF7 Rebirth 已导出变体批量材质化

### 新增与修复

- 新增 `scripts/final/export_ff7rb_models.ps1` 与 Blender worker
  `export_ff7rb_model_blender.py`：扫描 FModel 已保存的 Player 变体
  （`PC????_*`），无头导入 ActorX、修 PSK 三角反光、按 FModel 材质 JSON 匹配贴图
  （复用 `ff7rebirth_tools.py` 的模块函数），输出内嵌贴图 `.blend`，可选 FBX/GLB。
  默认输出 `D:\ff7rebirth_exports\materialized`。
- 上游保持手动：FModel 无 CLI，未保存的变体不做自动补提取；无 `Model` 目录的材质
  包（湿身/眼泪、`PC7002_00` 转换失败件）记为 `NO_MODEL` 并跳过，不算失败。
- `.blend` 保留完整节点；FBX/GLB 前做便携简化：分层眼球按 ColorRamp 参数烘成单张
  PNG（smoothstep 近似 EASE），DirectX 法线预翻转 G 通道生成 `*_gl.png` 直连
  Normal Map，`simplified` 字段记录改动。XPS/PMX 未在 FF7RB 骨架上验证，暂不提供。
- 修复跨目录贴图引用：材质 JSON 的引用是精确 Unreal 包路径，常指向本变体之外
  （PC0002_11 换衣模型复用 PC0002_00 的皮肤/头发/服装 atlas；眼白/口腔在
  `Character\Common`）。旧版只扫本变体目录，PC0002_11 的十个材质全部被按名兜底连到
  唯一本地贴图 `Skin_O` 遮罩，整模呈灰白色。现在语义解析在整个已导出 `Character` 树
  上按包路径精确匹配（`texture_reference_score` 按 `End/Content/<相对路径>` 后缀计
  分），按名兜底仍限本变体 + Common；manifest 增记 `indexedTextures`。
- manifest 机制对齐 ROE：`-ValidateOnly` 写独立快照、`-Only` 按扫描顺序合并、失败
  记录 ASCII 转义的 traceback；worker 结果行同样规避 PowerShell 5.1 OEM 解码问题。

### 操作与验证

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
.\export_ff7rb_models.ps1 -List
.\export_ff7rb_models.ps1                 # 全部有模型变体 -> .blend
.\export_ff7rb_models.ps1 -Only PC0002_00 -Format blend,fbx,glb -Force
```

- 真机全量：9/9 个已保存变体 PASS（8 个 Tifa `.pskx` + Toad Tifa `.psk`），5 个
  `NO_MODEL` 正确跳过；产物 13–141 MB `.blend` 落盘并生成 manifest。
- PC0002_00 三格式导出 PASS：536 骨、188,921 顶点、226,086 面、12 材质，11 张法线
  预翻转，`Common_Mouth_Light` 无 Base Color 如实记入 `missing_base`。
- `-ValidateOnly -Only PC0099_03` 覆盖 `.psk` 旧格式分支并写入
  `ff7rb_models_manifest.validate.json`，不触碰正式 manifest。
- 纯 Python 单测 `tests/test_export_ff7rb_worker.py` 7/7 通过（眼球烘焙数学、最近邻
  重采样、格式白名单与 marker 契约），mock bpy，无需 Blender。
- 跨目录引用修复后全量 `-Force` 重导 9/9 PASS：PC0002_11 的 10/11 材质按 JSON 引用
  连上 `PC0002_00_*_C` 共享 atlas（EEVEE 渲染确认服装/皮肤/头发正确），九个变体的眼
  睛全部转为 sclera+iris 分层混合（此前仅 PC0002_00），`missingBase` 仅剩 PC0002_05
  的发光材质（本就无 Base Color）。语义索引覆盖 179 张已导出贴图。

---

---

## 2026-08-09 — Rise of Eros 基础裸模带材质批量导出

### 新增与修复

- 新增 `scripts/riseoferos/export_nude_models.ps1` 与 Blender worker
  `export_nude_model_blender.py`，批量处理 `a00`、A–M 十三套 `01` 基础体和 E/F/G
  三套 `fm` 变体，默认集中输出到 `D:\roe_exports\nude_materials`。
- 每个 `.blend` 打包实际引用的图片，并生成 `nude_models_manifest.json`；支持
  `-ValidateOnly`、`-Only`、`-Force`、自定义源目录和输出目录。
- `extract_character.ps1 -List` 新增 17 个 `nude:<id>` 独立条目，并可直接执行例如
  `nude:b01 -Format blend,fbx,xps,pmx,glb`。`export_nude_models.ps1 -List` 提供相同清单；
  原有普通角色 ID 与默认 FBX 提取行为不变。
- 材质化裸模新增 Blend/FBX/XPS/PMX/GLB 多格式输出。非 Blender 格式先把程序化眼球
  烘焙成便携虹膜贴图；FBX/GLB 内嵌纹理，XPS/PMX 输出配套 PNG。六槽 nude XPS 会按
  `body / face / eye / lash / brow` 拆成正确 render group，透明 overlay 不导出。
- `-Only` 现在合并更新已有 manifest，并按 17 套规范顺序保留未重导出的记录，不再因
  单独补导一个格式而把完整清单覆盖成一条；manifest 同时记录每种格式的实际路径。
  `-ValidateOnly` 的结果改写入独立快照 `nude_models_manifest.validate.json`：验证运行
  没有输出路径，合并进正式 manifest 会把已记录的导出路径清成空记录。
- `extract_character.ps1 nude:<id>` 在缺少该角色常规提取产物（FBX 或 Albedo 贴图）时，
  先自动执行一次带 `-ExportTextures` 的常规提取再进入裸模流程；普通角色 ID 与
  `blend` 格式混用的错误改为执行前报告；`-Force` 仅作用于 nude 导出（帮助里注明）。
- 加固批量导出链路：裸模六槽在对象上打 `roe_nude_slots` 自定义属性标记，XPS 导出改
  按标记识别（材质名嗅探不稳定——便携眼球烘焙会把 eye 槽换成 `eye_portable`，仅存
  旧 .blend 兜底）；PMX 因 mmd_tools 原地改建骨架而固定最后导出；便携眼球烘焙状态
  记入 manifest（a00 无组合裸模网格时记录 `skipped` 及原因，槽丢失则直接判失败）；
  worker 失败时把 Python traceback 一并写入 manifest；XPS 导出算子已注册时不再要求
  特定插件模块名。
- 修复直接复用 HD 材质流程时的裸模错误：`*_nk_body` 同时含躯干和头部，旧逻辑会把
  所有默认区域都指向 face Albedo。worker 保留既有眼球/睫毛/眉毛分类，再按连通块与
  面部骨权重建立 `body / face / eye / lash / brow / overlay` 六槽。
- 修复 B01 眼球材质槽存在但没有实际面的错误。B01 眼球约按 80% `Eyeball`、20% `Head`
  混合权重，旧版 90% 门槛会把左右眼共 864 面留在 face；现在只有同时符合多数眼球权重、
  250–800 面紧凑拓扑及完整 0–1 虹膜 UV 的连通块才按眼球处理。裸模 worker 也新增
  `eye > 0` 硬校验，避免空眼球槽再次被当作成功。
- Blender worker 的结果行改为 ASCII 转义 JSON，避免 Windows PowerShell 5.1 用 OEM 代码页
  错误解码中文诊断并吞掉字符串结尾，从而生成无法被标准 JSON 解析器读取的 manifest。
- 贴图临时目录只归集同字母体型资源；缺失公共头部贴图时直接读取游戏的
  `chara_tex_bare_pc_<字母>_common*`，并拒绝把其他体型的脸当兜底。

### 操作与验证

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
.\export_nude_models.ps1                 # 实际导出
.\export_nude_models.ps1 -ValidateOnly   # 只检查
.\extract_character.ps1 -List
.\extract_character.ps1 nude:b01 -Format blend,fbx,xps,pmx,glb -Force
```

- Blender 3.6 无头验证 17/17 通过：标准裸模各为 2 网格、1 骨架和 7 个材质槽；I/J
  体型眉线已烘进 face，使用 4 张 diffuse，其余使用 5 张；`a00` 是独立的两网格/两材质
  通用体。
- A01 六槽面数为 `36142 / 15042 / 864 / 804 / 228 / 294`；身体和脸分别命中
  `pc_a01_nk_body` 与 `pc_a_nk_face`，没有再把躯干错误映射到脸图。
- B01 修复后六槽面数为 `35414 / 15078 / 864 / 884 / 228 / 0`，眼球使用同体型的
  `pc_b_nk_eye_iris_rgbx_Albedo.png`；合成回归同时覆盖插件与独立脚本的 80/20 权重眼球。
- B01 五格式真实导出并重导入通过：FBX/GLB 均为 2 网格、1 骨架、61,624 面；XPS 为
  body `35414`、face `15078`、eye `864`、lash `884`、brow `228`、hair `9156` 六个分件；
  PMX 合并为 1 网格、1 骨架、6 材质、61,624 面，五张配套纹理均可重新加载。
- 实际保存并重开 A01 `.blend`，确认图片均为 packed；EEVEE 正面渲染确认身体、脸、
  眼睛和头发贴图连续。材质仍是 Blender PBR/程序化近似，不声称复刻 Unity Toon/NPR、
  MGAC 与 Normal 的完整游戏内效果。
- 2026-08-29 加固后复验：`-ValidateOnly` 全 17 套重新 PASS 并写入独立
  `nude_models_manifest.validate.json`，对已有正式 manifest 的目录重复验证后其内容逐
  字节不变；B01 五格式重新导出 PASS，manifest 含 `portableEye`（status/path）与
  `nudeSplit.eye_slot`，XPS 内部分件为 `5_body / 5_face / 5_eye / 7_lash / 7_brow`；
  保存的 `.blend` 重开后 `roe_nude_slots=1` 与 6 槽仍在；空 `-OutputRoot` 下
  `extract_character.ps1 nude:b01` 自动先完成常规提取（34 个角色 FBX、165 张贴图）再
  产出 blend；两个 PowerShell 脚本通过语法解析，对现有 17 套素材的缺源检测全部命中
  「无需补提取」；4 个合成 fixture Blender 回归（head 语义、贴图别名、body 变体、XPS
  alpha 槽）与 FBX bind 兼容测试共 5 项 PASS（3 个需真实 HD 素材参数的矩阵测试未随
  本次运行）。

---

## 2026-08-09 — Venus Vacation PRISM 角色名称对应表

### 新增

- 新增 `scripts/venusvacationprism/map_characters.py`，输出 JSON、CSV、Markdown 三种
  “角色—模型”对应表；支持用中文名、英文名或内部代码筛选角色。
- 在 `prism_rdb.py` 实现 KTGL RDB 名称哈希，并确认六名角色的内部代码为
  `MIS/FON/ELS/TAM/NNM/HON`。只有 G1M 与至少两个 MTL/GRP/OID 同名伴随资源均实际存在时，
  才接受该名称，避免把单个 32 位哈希碰撞误报为角色模型。
- `export_model.py` 新增 `--name`，可直接使用对应表中的 `FACE_FON_000` 等内部基名导出，
  原有 `--index` 和 `--id` 行为不变。

### 结果与验证

- 本机 Steam 安装确认 35 个具备完整哈希证据链的角色 G1M：海咲 8、菲欧娜 6、
  伊莉丝 6、环 5、七海 5、穗香 5。它们包含脸部、头发，以及海咲/七海的
  `COS_*_001` 服装/身体分件；未命名的共用基础身体不作无证据归属。
- 纠正仅凭轮廓作出的候选推测：索引 837 / `0xbcea6c57` 是海咲
  `COS_MIS_001`，索引 839 / `0x16a61601` 是七海 `COS_NNM_001`。
- 实际按 `--name FACE_FON_000` 成功导出索引 860 / `0xa359e61c`，并通过 9 项单元测试；
  名称哈希测试同时覆盖公开的 `HON_HAIR_033.GRP` 向量和 PRISM 的 `COS_MIS_001.G1M`。

---

## 2026-08-08 — Venus Vacation PRISM 原始 RDB/FDATA 解包

### 新增

- 新增 `scripts/venusvacationprism/prism_rdb.py`，只读扫描 KTGL FDATA，并解码该游戏
  `0x00400000` 标志对应的 16 KiB 分块 Zlib 数据；块边界、Zlib 流和最终尺寸均严格校验。
- 新增 `list_models.py`，输出 JSON、CSV、Markdown 三种清单；`--probe` 会补充 G1M
  版本、区块、骨骼数以及角色候选分类。
- 新增 `export_model.py`，可按清单一基索引或十六进制 KTID 导出原生 G1M 和来源
  manifest；可选调用 `eArmada8/gust_stuff` 输出 glTF/BIN。第三方转换失败不会删除已还原 G1M。

### 使用与验证

- Steam 安装实扫 1,527 个 G1M/1,527 个唯一 ID，分布在 69 个 FDATA 包；全部深度探测
  成功，零解包错误。压缩内容共 1,247,942,069 字节，解压后共 2,242,373,324 字节。
- 按骨骼数筛出 71 个角色组件候选；该数字包含身体、脸、服装和共用件，不代表角色人数。
- 实际导出索引 836、KTID `0x7ce546e8`：G1M 5,252,712 字节、924 个骨骼节点、
  17 个网格。glTF 转换及 Blender 3.6.15 后台导入/渲染通过，几何为完整女性基础身体。
- 新增 6 项单元测试，覆盖多块解压、尾部/尺寸损坏、G1M 元数据和 FDATA 实际读取。

---

## 2026-08-02 — ROE XPS Tools v1.1.12 / i03、i04 脸部贴图兼容

### 修复与兼容性

- 修复 i03/i04 点击材质准备或“修复脸部”后仍没有脸部贴图的问题。i 体型资源没有
  `pc_i_nk_eye_iris_rgbx_Albedo.png` 和 `pc_i_nk_eyebrow_rgbx_Albedo.png`；旧逻辑把三张
  head 贴图全部视为必需项，因此在真正设置 face 材质之前取消整个操作。
- i 体型现在只在独立虹膜图缺失时回退到实际存在的
  `pc_i_ld_eyes_rgbx_Albedo.png`。该回退排在标准 `eye_iris` 之后，f/g 等已有高清虹膜
  资源的旧角色不会改变。
- face 与 hair 增加角色专属前缀优先级：i04 使用 `pc_i04_hd_face/hair`，i03 因没有
  角色专属 face/hair 而继续使用 `pc_i_nk_face/hair`。共享图仍是精确角色图未命中后的
  兼容回退。
- i03/i04 的眉毛与眼线已经烘进 face Albedo，而独立 `pc_i_nk_eyebrow` 几何没有对应
  Albedo。仅 i 体型允许该贴图缺失，相关 stroke 材质保持透明；XPS 导出同时跳过任何
  纯透明 head 槽，不再生成 `lash_diffuse.png` 占位片。其他体型缺 eyebrow 时仍报错。

### 使用与验证

1. 覆盖安装插件并彻底重启 Blender 3.6，确认版本为 `1.1.12`。
2. 已打开的 i03/i04 场景无需重新导入；确认对应 HD FBX 和 `_textures` 后点击
   **“修复脸部”**。首次导入仍可使用完整的“检查并准备材质”。
3. Blender 3.6.15 实测 i03 face `11616` 面，使用
   `pc_i_nk_face_rgbx_Albedo.png`；i04 face `12172` 面，使用角色专属
   `pc_i04_hd_face_rgbx_Albedo.png`；两者 eye 均为 `864` 面并烘焙为
   `roe_eye_baked.png`。
4. 两个角色均通过“单独修脸不改身体”、旧的一键流程、XPS 导出和全新场景重导入。
   新增 `test_i_family_materials_blender.py`；F10、G09、e06、b02、g07、g02 既有回归
   同时通过。

---

## 2026-08-02 — ROE XPS Tools v1.1.11 / F10 脸部材质与分区修复按钮

### 修复与新增

- 修复 F10 的脸部材质消失。F10 的 head 在同一连通块内跨越 `pc_f_nk_face` 与
  `pc_f_nk_tears` 原始材质边界；旧版按连通块判断时把 11,596 个脸部面误归为透明
  `eye_overlay`。现在只要 FBX 同时提供明确的 face 与眼部附属槽，就优先按每个面的
  原始材质索引保留 face/tears 语义，再对没有明确语义的面使用既有骨骼、UV 和几何兜底。
- 在“检查并准备材质”下新增 **修复脸部 / 修复身体 / 修复翅膀** 三个按钮：脸部只重建
  head 五槽；身体只处理非 head、非 wing 的身体/衣装/头发槽；翅膀只处理原始槽名或
  对象名含独立 `wing/wings[数字]` 词元的槽。F10 没有翅膀时按钮提示未识别并零修改。
- 原有 **“2. 检查并准备材质”** 完整保留，默认仍一次处理全部材质；“修复眼睛”也保留，
  用于只重建眼球的更窄场景。分区按钮共用相同贴图匹配和原始槽缓存，不另造角色特例。
- 新增 [ROE Blender 材质兼容避坑手册](roe-material-pitfalls.md)，集中记录 F10、G09、
  e06、b02、g07、g02、插件重启、重复 FBX、输出目录清理、原始槽缓存和 XPS 重导验证
  等已确认问题，并固定以后修改材质逻辑时必须执行的最低回归矩阵。

### 兼容性与验证

- Blender 3.6.15 实测 F10：face/eye/lash/brow/overlay 从错误的
  `4148/864/900/228/11596` 恢复为 `15354/864/900/228/390`；face 使用
  `pc_f_nk_face_rgbx_Albedo.png`。单独修脸时身体材质和面索引不变，单独修身体时头部
  不变，单独修翅膀为零修改。
- F10 通过旧的一键流程导出并重新导入 XPS：`5_face` 为 15,354 面并加载正确脸贴图，
  `5_eye` 为 864 面并加载 `roe_eye_baked.png`。
- G09 实机回归通过：脸部分槽仍为 `13626/864/660/228/548`，身体按钮不改两组翅膀，
  翅膀按钮不改 body/skin，最终 XPS render group 仍为 `5/5/7/7`。
- e06 缺失绑定集成测试、g07 多图集、g02 Albedo/Abedo、b02 眼部语义和全部现有 Blender
  回归测试通过；v1.1.10 的临时 FBX bind 修复未改动。

### 使用

1. 覆盖安装插件并彻底重启 Blender 3.6，确认版本为 `1.1.11`。
2. F10 已导入场景只需确认原 FBX 与 `f10\_textures` 路径，点击 **“修复脸部”**；无需
   重新修身体。新导入角色仍可继续使用原来的“一键准备材质”。
3. 以后只有单一区域异常时优先点对应按钮；不确定或首次导入时仍点完整准备按钮。

---

## 2026-08-02 — ROE XPS Tools v1.1.10 / e06 FBX 缺失绑定兼容

### 修复与兼容性

- 修复 e06 HD FBX 在 Blender 3.6 导入时因 `wp_e_06` 缺少骨架绑定矩阵而触发
  `KeyError: Root` 的问题。旧流程会在异常后留下 4 个无材质网格和 1 个未完成骨架；
  这些对象只是导入半成品，不能继续准备材质或导出。
- 插件仅在 Blender FBX 导入器已把网格归入骨架、但该网格没有 `armature_setup` 时，
  使用网格世界矩阵和骨架 bind matrix 补齐缺项。已有绑定绝不覆盖；补丁只在本次
  `bpy.ops.import_scene.fbx` 调用期间生效，完成或异常后都会恢复 Blender 原方法。
- 主“1. 导入 FBX”和旧场景从源 FBX 恢复材质分区两条路径共用同一兼容入口；不依赖
  修改 Blender 安装目录。若新版 Blender 不暴露 3.6 的内部辅助类，插件会退回其原生
  FBX 操作，不施加版本相关补丁。

### 使用与验证

1. 覆盖安装插件并彻底重启 Blender 3.6，确认版本为 `1.1.10`；删除异常导入留下的
   e06 半成品。
2. e06 选择带 `(1)` 的完整文件
   `pc_e06_hd (1)\FBX_GameObjects\pc_e06_hd\pc_e06_hd.fbx`，贴图目录选择
   `e06\_textures`，再按正常三步流程操作。无 `(1)` 的同名副本本身缺少材质分区。
3. Blender 3.6.15 实机验证得到 169 根骨骼；body 2 个原始槽、head 4 个原始槽、
   hair/weapon 各 1 槽，武器保留 `ball_scale` 权重和 Armature 修改器；材质准备后 head
   正常重建为 5 槽。
4. 新增 `test_fbx_missing_bind_compat_blender.py`，覆盖缺项补齐、正常绑定不覆盖、重复
   调用幂等、临时补丁恢复和 e06 完整导入/材质准备。既有 G07、B02、G02、G09 四组
   Blender 回归测试同时通过。

---

## 2026-08-02 — ROE XPS Tools v1.1.9 / g09 Blender 3.6 翅膀视口修复

### 修复与兼容性

- 根据 Blender 3.6 实际截图补充修复：g09 的两组翅膀材质在准备阶段改用 Alpha Clip，
  避免 Alpha Hashed 在重叠羽毛片上显示黑色散点和卡片状噪声；XPS 导出仍使用 RG7。
- 复用严格的 g09 槽识别函数，同时限定 `pc_g09_hd/ld_body` 对象名与
  `pc_g09_hd/ld_wing(s)[数字]` 原始槽名。非 g09 角色、普通 body/skin、头发和手工
  覆盖的历史分支不改变。
- 回归测试额外固定 Blender 材质模式：g09 `body/skin=HASHED`、
  `wings/wings2=CLIP`，并继续验证非 g09 wing 不进入特例；测试还会模拟旧场景中主翼
  错挂 `wings2 + HASHED`，确认再次准备材质能够原地修复。

### 使用

1. 覆盖安装插件并彻底重启 Blender 3.6，确认版本为 `1.1.9`。
2. 对已经打开的旧 g09 场景重新执行“2. 检查并准备材质”；旧材质数据不会仅靠导入
   插件文件自动刷新。之后再执行“3. 导出 XPS(.mesh)”。

---

## 2026-08-02 — ROE XPS Tools v1.1.8 / g09 翅膀透明材质

### 修复

- 修复 g09 的 `pc_g09_hd_wings` 与 `pc_g09_hd_wings2` 在 XPS 导出后出现黑底、
  硬边或实心羽毛片的问题。两槽与 body/skin 共用 `pc_g09_hd_body` 网格，旧逻辑把
  所有 ROE body 槽统一导为不透明 RG5，因而丢失翅膀 Albedo 的 alpha。
- 修复贴图前缀歧义：`pc_g09_hd_wings*Albedo*.png` 会同时命中 `wings` 与
  `wings2`，且旧排序优先选择 `wings2`。现在先按完整的 `_rgbx_Albedo` 文件干精确
  查找，主翼和独立羽毛片分别使用自己的图集。
- 新增按原始材质槽名选择 XPS render group：普通 body/skin 保持 RG5；仅 g09 HD/LD
  的 `wing`、`wings`、`wings2` 等槽在材质确实使用 alpha 时导为 RG7；头发仍为 RG7。
  角色 ID 与 body 对象名采用双重限定，其他旧角色即使有同名 wing 槽也维持原来的 RG5。
- 新增 Blender 回归测试 `test_xps_alpha_slots_blender.py`，固定 g09 的四槽期望为
  `body=5`、`skin=5`、`wings2=7`、`wings=7`，并验证非 g09 的 alpha wing 槽仍为
  RG5、没有 alpha 的 g09 wing 也不改变。

### 使用

1. 覆盖安装 `scripts/riseoferos/roe_xps_addon.py` 并重启 Blender，版本应为 `1.1.8`。
2. 现有 g09 场景无需重新导入；重新执行“2. 检查并准备材质”，再执行
   “3. 导出 XPS(.mesh)”。

---

## 2026-08-02 — Throne of Desire X-Legend NFS/Gamebryo 调研与样本验证

### 新增与修正

- 确认 Steam App `4496710` 不使用 Unreal/Unity，而是 HyenaPC 包装层、X-Legend NFS
  封包和 Gamebryo NIF/KFM 模型动画格式。
- 新增 [`scripts/throneofdesire`](../scripts/throneofdesire/) 独立流程和
  [提取调研文档](throne-of-desire-extraction.md)，不复用 FFVII/Stellar Blade 的
  FModel、mapping 或 Unreal profile。
- `extract_nfs.py` 支持 `0x20190503` packageindex、低 32 位 XOR 偏移/大小、
  `FileListPC.txt` 映射、zlib 解压、格式扫描、按哈希提取和按编号模型组提取。

### 用户如何操作

1. 用 `scan` 建立完整 JSON 清单；
2. 用 `extract-model --model h001` 一次提取匹配 KFM 和紧随其后的基础 NIF；
3. 先在 X-Legend/Aura Kingdom 专用 NIF 查看器中验证，再尝试 Noesis 转 FBX/DAE 后
   导入 Blender 3.6；解析失败时才退回 Ninja Ripper。

### 原理与兼容性

- 当前模型/KFM 均为带 16 字节容器头的 zlib 流；部分非模型资源为自定义 LZMA 或未知
  纹理编码，脚本会分类但不会错误地套用标准 LZMA 解码。
- NIF 版本为 `20.3.3.2`。通用 NifTools/Noesis 对 X-Legend 自定义块的兼容性尚未在
  当前机器验证，因此本次不声明已生成 Blender 文件。

### 验证

- 全量扫描 32,780 条当前索引：5,957 个 NIF、323 个 KFM、295 个 XML；其中
  15,377 条为 zlib、1,877 条为 X-Legend LZMA、15,526 条压缩/编码尚未识别。
- 成功提取 `m001` 基础样本和 `h001` 角色候选组；`h001.nif` 906,860 字节、
  `h001.kfm` 62,650 字节，输出大小与 FileList 清单一致，SHA-256 已写入 manifest。
- Python 语法检查、完整索引扫描和两个 `extract-model` 回归命令均通过；游戏目录保持
  只读，未改动原始 NFS 或索引。

---

## 2026-08-01 — Stellar Blade PC 导出分析与 Eve Blender 3.6 验证

### 新增与修正

- 新增独立的 [`scripts/stellarblade`](../scripts/stellarblade/) 流程和
  [Stellar Blade 导出文档](stellar-blade-extraction.md)，不复用 FFVII 的 profile、
  mapping 或包路径。
- 确认 Steam build `19963153` 为 UE4 IoStore、无 AES，FModel 精确 profile 为
  `GAME_StellarBlade`；社区 `StellarBlade_1.1.0.usmap` 已能解析并导出当前身体和脸。
- FModel 成功导出 Eve 标准身体 PSK 和完整 Face_003 UEFormat；其 4.4.4 版本在头发/牙齿 Extract 发生
  `NullReferenceException`，改用社区指南链接的 Stellar Blade 专用 UE Viewer v6
  补导默认主发型与长马尾。
- 新增 `import_uemodel36.py`、UEFormat Blender 3.6 兼容补丁和 `validate_eve.py`：检查
  ActorX/UEFormat 文件头，用 `SC_Hair` 和 `Ab-TL-HairB01` 静置骨矩阵组合模块，保留
  Face_003 全部 53 个 Morph，再生成 Blender 3.6 `.blend`、全身/脸部 PNG 和 JSON。
- 新增 [Eve 验证资产路径清单](stellar-blade-eve-assets.txt)。游戏资产、mapping 和
  第三方程序仍只保存在本机，不提交仓库。

### 用户如何操作

1. 按文档配置 FModel 的 `GAME_StellarBlade` 和 local mapping，临时禁用 `~mods`。
2. FModel 导出身体 PSK 和 Face_003 UEFormat；单个组件复现异常时，使用专用 UE Viewer v6 补导。
3. Blender 3.6 安装 `io_scene_psk_psa 5.0.6`，并给官方 UEFormat 源码应用本仓库兼容补丁，按
   [`scripts/stellarblade/README.md`](../scripts/stellarblade/README.md) 运行验证命令。
4. 输出位于 `D:\stellarblade_exports`；完成导出后恢复 Mod，保持游戏包原始名称。

### 原理与兼容性

- Eve 是模块化角色。主发型以局部原点导出，按身体 `SC_Hair` 插槽移动；长马尾以双方
  共有的 `Ab-TL-HairB01` 完整静置骨矩阵对齐，不能把所有 PSK 直接堆在世界原点。
- PSK 导入器将 Mesh parent 到 Armature；脚本只变换对象层级根，避免父子都移动造成
  双倍位移。组件骨架、权重和对象层级保持不变。
- 手动重导 PSK 时应选 **Don't Export Bone Sockets**。完整角色生产仍优先统一使用
  FModel `.uemodel`，避免不同提取器之间潜在的颈缝。

### 验证

- 专用 UE Viewer 扫描到 `228,867` 个游戏文件，并实际输出两个头发 PSK；三个验证
  PSK 都非空且以 `ACTRHEAD` 开始，Face_003 以 `UEFORMAT` 开始。
- Blender `3.6.15` 实际生成 4 个网格、4 套原始 Armature、107,123 顶点、133,874 个面；
  Face_003 为 24,350 顶点、35,992 个面、11 个材质槽，并保留 54 个 Shape Keys（含 Basis）；
  主发型插槽误差为 `0`，马尾骨锚点误差约 `0.000002`。
- 输出 `Eve_Standard_validation.blend`、全身/脸部 PNG 和 JSON 均已生成并视觉检查；游戏
  `.pak/.utoc/.ucas` 名称未改动。已安装 Eve Mod 当前仍在隔离目录，启动游戏前恢复。

---

## 2026-08-01 — FF7 Remake / Rebirth Player 主模型清单复核

### 新增与修正

- 新增 Remake 与 Rebirth 两份一行一个 Unreal 包路径的 Player 主模型清单。
- Remake 原版 pak 的主模型包总数保持为 `36`；安装到 `~mods`、覆盖已有包路径的
  Mod 不重复计数。
- Rebirth 的统计口径由 `109` 个一级资源目录细分为 `85` 个主模型包和 `24` 个
  纯材质、贴图等资源变体，避免把效果目录误算成模型。

### 用户如何操作

- 按 [Remake 主模型文件列表](ff7remake-player-model-files.txt) 或
  [Rebirth 主模型文件列表](ff7rebirth-player-model-files.txt) 中的完整路径，在
  UModel/FModel 中定位对应的 `SkeletalMesh` 主资产并导出。

### 原理与兼容性

- 主模型采用 `Player/<变体>/Model/PC????_??.uasset` 路径约定识别；Skeleton、
  PhysicsAsset、BNM、Condition、材质和贴图不计入主模型数。
- Rebirth 使用本机安装目录下全部 `51` 个 `.utoc` 的目录索引只读枚举，不修改、
  解包或回写游戏文件。

### 验证

- Remake 清单 `36` 行、`36` 个唯一值，与现有详细清单逐项一致。
- Rebirth 清单 `85` 行、`85` 个唯一值，与全部 IoStore 目录索引逐项比较差异为 `0`。
- 两份清单均通过完整路径格式检查，`git diff --check` 无错误。

---

## 2026-07-26 — ROE XPS Tools v1.1.7 / g07 身体贴图与手动材质修复

### 新增与修复

- 修复 g07 身体三个材质槽找不到颜色贴图的问题。原始槽名为
  `pc_g07_hd_skin`、`pc_g07_hd_body1`、`pc_g07_hd_body2`，实际 PNG 却命名为
  `pc_g07_body1_rgbx_Albedo.png` 和 `pc_g07_body2_rgbx_Albedo.png`，省略了
  `_hd_`；旧版只按完整前缀查找，因此三个身体槽都生成了无图片材质。
- 插件和独立材质脚本新增 `_hd_/_ld_` 省略命名兼容。仍先尝试原始槽名精确匹配，
  只有未命中时才去掉一次 LOD 标记重试。
- “当前槽用途”新增 **透明罩/隐藏**。人工指定后生成纯 `Transparent BSDF`，
  ROE XPS 导出也会跳过该槽，便于手工处理 tear、泪膜或眼镜状透明卡片。
- 新增 [ROE 材质手动修复指南](roe-manual-material-repair.md)，统一记录身体槽贴图
  覆盖、透明罩隐藏、头部逐面分类、撤销与保存方法。

### 用户如何操作

1. 安装或覆盖 `scripts\riseoferos\roe_xps_addon.py`，重启 Blender，版本应为
   `1.1.7`。本次当前 Blender 已热加载新版本。
2. g07 已打开的场景无需重新导入；保持模型来源与
   `D:\roe_exports\g07\_textures\`，点击一次“检查并准备材质”。
3. 自动结果仍有局部偏差时，按
   [手动修复指南](roe-manual-material-repair.md) 使用高级材质调整：
   当前槽保存用途/贴图覆盖，或在 Edit Mode 标记头部所选面。
4. 检查无误后保存 `.blend`。

### 原理与兼容性

- g07 正确映射为：`skin → body1`、`body1 → body1`、`body2 → body2`。修复只扩展
  文件名解析，不修改 UV、顶点、面、骨架、权重或原始材质槽。
- 精确文件名前缀的优先级不变，因此 a06/a07/a08、g08 和标准命名角色不会被宽松
  回退抢走贴图；g02 的 `Abedo` 拼写兼容也继续保留。
- 透明槽采用持久化槽覆盖，不需要删除几何；清除当前槽覆盖即可恢复自动判断。
  头部逐面人工分类仍存储在网格属性中，二者都会随 `.blend` 保存。

### 验证

- 当前 g07 Blender 3.6 场景应用返回 `FINISHED`：3 个网格，缺贴图 `0`。
- 身体三个槽保持原面数 `14312 / 7034 / 24219`；前两个连接
  `pc_g07_body1_rgbx_Albedo.png`，第三个连接
  `pc_g07_body2_rgbx_Albedo.png`。
- Blender 合成回归同时覆盖插件与独立脚本的 g07 LOD 省略命名；b02 头部语义和
  非 head tear 透明槽、g02 `Albedo/Abedo` 回归继续通过。

---

## 2026-07-26 — ROE XPS Tools v1.1.6 / b02 下睫毛与左眼透明片

### 新增与修复

- 修复 b02 下睫毛被分到脸材质的问题。两侧下睫毛共 `300` 面，原始材质属于
  `pc_b_nk_eyebrow`，但 Eyelid 权重低于 other，旧规则把它们留在 face 槽。
- 修复左眼附近像“眼镜片”的错误几何。它不是独立眼镜模型，而是
  `pc_b_nk_tears` 的透明眼部罩层。head 内旧规则把其中 `60` 面当成脸、`56` 面
  当成睫毛；此外身体网格 `pc_b02_hd.002` 还有一个同名 `32` 面材质槽。
- v1.1.5 已修复 head 内的分区，但没有处理身体网格里的同名 tear 槽；v1.1.6 将
  所有非 head 网格的 `tear/tears` 原始槽也改为纯透明材质，完成左眼“眼镜片”修复。
- 插件和独立脚本现在都保留骨骼权重的优先判定，并增加原始材质名兜底：
  `tear/tears` 直接进入透明罩层；`brow/eyebrow/lash` 只在权重无法判定时，按相对
  眼球高度拆分眉毛和睫毛。

### 用户如何操作

1. 安装或覆盖 `scripts\riseoferos\roe_xps_addon.py`，版本应为 `1.1.6`。
2. 已经打开的 b02 场景不需要重新导入；确认模型来源与贴图目录仍指向 b02 后，
   点击一次“检查并准备材质”。
3. 本次当前 Blender 已热加载并执行完成；以后重启 Blender 会直接使用磁盘上的
   v1.1.6。
4. 检查无误后保存 `.blend`，否则本次场景内的逐面材质索引不会持久化。

### 原理与兼容性

- b02 的 `pc_b_nk_eyebrow` 同时装有眉毛、上睫毛和下睫毛，不能把整个原始材质槽
  直接映射为单一目标槽；新规则仍优先使用历史 Eyebrow/Eyelid 骨骼权重，仅处理
  权重不明确的连通块。
- `pc_b_nk_tears` 是运行时眼部效果使用的透明卡片，Blender 基础预览应统一映射到
  `Transparent BSDF` 的 `eye_overlay`，而不是赋予脸色或眉睫贴图。该规则同时应用
  于 head 的逐面分类和其他网格的原始材质槽。
- 没有修改贴图、UV、顶点、骨架或权重。g02 的 `Abedo` 回退、a08 眼球材质名兜底
  以及 a06/a07 的历史骨骼权重分类继续保留。

### 验证

- b02 当前 Blender 3.6 场景应用返回 `FINISHED`，3 个网格，缺贴图 `0`。
- b02 头部分槽：face `13920`、eye `864`、lash `804`、brow `228`、
  eye_overlay `116`。
- b02 身体网格 `pc_b02_hd.002` 的 `pc_b_nk_tears` 槽共 `32` 面，已连接到只含
  `Transparent BSDF` 与 Material Output 的透明材质。
- 真实 FBX 回归覆盖 a06、a07、a08、g02、g03：眼球均保持 `864` 面，各角色既有
  骨骼优先分类继续生效。
- 新增 Blender 合成网格测试，同时验证插件与独立脚本的脸、眼球、上下睫毛、眉毛、
  tear 罩层语义；与 g02 `Albedo/Abedo` 回归测试均通过。

---

## 2026-07-26 — ROE g03 白脸 / 旧导出贴图补全

### 问题与修复

- `D:\roe_exports\g03\_textures\` 是早期的不完整导出，只包含 g03 的 HD/LD
  身体 Albedo、MGAC、Normal，没有 g 体型共用的
  `pc_g_nk_face`、`pc_g_nk_eye_iris`、`pc_g_nk_eyebrow`、`pc_g_nk_hair`
  贴图。
- Blender 中身体的 Albedo 已正确连接，但头部没有材质槽；插件因缺少
  face、eye_iris、eyebrow 三项必需贴图而中止头部材质准备，所以脸显示为白色。
- 使用当前 `extract_character.ps1` 在隔离目录重新提取 g03，确认能够导出
  31 张贴图；将其中缺失的 6 张 g 体型共用贴图补入原 `_textures` 后，重新执行
  “检查并准备材质”，当前 Blender 场景已恢复。

### 用户如何操作

若旧角色出现身体有贴图、脸或头发为白色，推荐重新提取：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
.\extract_character.ps1 g03 -ExportTextures
```

重提取会清空并重建 `D:\roe_exports\g03\`，请先把自己生成的 `.blend`、`.mesh`
或烘焙贴图移到该目录之外。随后在 Blender 的 ROE 面板重新选择：

1. 模型来源：完整的 g03 HD FBX；
2. ROE 贴图目录：`D:\roe_exports\g03\_textures\`；
3. 点击“检查模型”以及“检查并准备材质”。

### 原理与兼容性

- g02、g03、g08 的 `pc_g_nk_*` 文件 SHA256 完全一致，证明它们是 g 体型公共资源，
  不是角色专属贴图。
- 当前提取脚本会合并角色包、`chara_armor_common*` 和
  `chara_*_pc_<体型>_common*`，因此新提取能补齐公共头部贴图。
- 本次没有修改 FBX、UV、骨架、权重或 Blender 材质分类算法，也没有改变 g02
  的 `Abedo` 兼容及 g08 的标准 `Albedo` 优先级。

### 验证

- 隔离重提取 g03：`28` 个 AssetBundle、`10` 个 FBX、`31` 张 PNG。
- 共用脸、虹膜、眉毛、头发及脸部 MGAC/Normal 与 g02、g08 对应文件哈希一致。
- Blender 3.6 当前场景材质准备返回 `FINISHED`：3 个网格，恢复 1 个头部原始分区，
  未恢复 0，缺贴图 0；头部恢复为 face、eye、lash、brow、eye_overlay 五个材质槽。

---

## 2026-07-26 — `scripts` 根目录清理与开发工具归档

### 整理内容

- 删除 `scripts` 根目录下 `19` 个未跟踪、未被仓库引用的一次性 Blender 诊断文件，
  包括 a07/a08 热重载、临时渲染、会话保存、材质对比和依赖本机旧路径的手工测试。
- 保留可复用的 Blender MCP TCP 客户端，并从
  `scripts\_blender_mcp_client.ps1` 移到
  `scripts\dev\blender_mcp\execute_code.ps1`。
- 新增 `scripts\dev\blender_mcp\README.md`，记录启动条件、命令、端口参数和任意代码
  执行的安全边界。
- 正式目录 `scripts\riseoferos`、`scripts\final`、两者的测试目录，以及旧命令兼容
  入口 `scripts\extract_character.ps1` 均保留。

### 用户如何操作

- ROE 与 FF7 Rebirth 的正常操作不变，继续从 `scripts\riseoferos` 和
  `scripts\final` 进入。
- 只有开发诊断时才使用：

  ```powershell
  .\scripts\dev\blender_mcp\execute_code.ps1 -CodeFile .\path\to\probe.py
  ```

### 原理与兼容性

- 删除项全部未被 Git 跟踪且全仓库无引用；其中多个测试仍硬编码已经迁移前的
  `scripts\roe_xps_addon.py`，继续保留会造成误用。
- 通用 MCP 客户端本身不含角色或版本逻辑，因此归档到 `dev/blender_mcp`；正式用户
  入口路径没有改变。

### 验证

- 清理后 `scripts` 根目录只剩 `README.md` 和兼容入口 `extract_character.ps1`。
- 重新检查仓库引用与 Markdown 相对链接，确认没有指向已删除的一次性脚本。
- ROE `Abedo` 回归测试与 FF7 Rebirth helper 测试仍位于各自游戏目录。

---

## 2026-07-26 — ROE XPS Tools v1.1.4 / g02 `Abedo` 材质兼容

### 新增与修正

- 修复 `D:\roe_exports\g02` 导入后身体材质缺失。g02 原始 HD/LD 身体颜色贴图把
  `Albedo` 拼成了 `Abedo`，而旧版只搜索 `*Albedo*.png`，导致身体网格生成无图片
  节点的平面材质。
- `roe_xps_addon.py` 与独立的 `blender_face_materials.py` 现在都先匹配标准
  `Albedo`，未命中时再匹配 g02 的 `Abedo`；若两个文件同时存在，标准拼写优先。

### 用户如何操作

1. 在 Blender 3.6 中覆盖安装 `scripts\riseoferos\roe_xps_addon.py`，然后重启
   Blender，确认插件版本为 `1.1.4`。
2. “模型来源”选择 g02 的有效 HD FBX，“ROE 贴图目录”选择
   `D:\roe_exports\g02\_textures\`。
3. 点击“导入 FBX”→“检查模型”→“检查并准备材质”。旧场景也可重新指定上述路径后，
   直接再次点击“检查并准备材质”。
4. 身体材质的 Image Texture 应连接
   `pc_g02_hd_body_rgbx_Abedo.png`，脸、眼睛、眉毛和头发继续使用共享的标准
   `Albedo` 贴图。

### 原理与兼容性

- 修复只扩展颜色贴图的文件名解析，不重命名或改写 PNG，不改变 g08 等标准
  `Albedo` 角色的优先匹配结果。
- MGAC、Normal、UV、骨架、权重、材质槽恢复和眼睛分类逻辑均未改动。

### 验证

- 对比本机 `g02` 与正确的 `g08`：g02 的 HD/LD 身体贴图均为 `Abedo`，g08 为标准
  `Albedo`，其他共享脸/眼/眉/发贴图命名一致。
- Blender 3.6 回归脚本覆盖插件和独立材质脚本：只有 `Abedo` 时能够回退命中；同时
  存在 `Albedo` 与 `Abedo` 时仍选择标准 `Albedo`。

---

## 2026-07-26 — FF7 Rebirth Player 待导出清单与手动流程

### 新增内容

- 新增
  [`ff7rebirth-player-export-inventory.md`](ff7rebirth-player-export-inventory.md)，
  记录 FModel 虚拟 `Player` 目录 `109` 项、本机已经写入的 `14` 项和待核查/待导出的
  `95` 项完整差集。
- 已有 14 项进一步区分为：`9` 个有效 ActorX 模型、`2` 个 Tifa 纯材质效果、
  `1` 个尚未转换的 PC7002 原始模型资源，以及 `2` 个仅含共享贴图的 Cloud 依赖目录。
- 95 项按角色建立可维护的 Markdown 复选框；`Wet/Tear/Hologram/Dirty/Blood`
  等疑似效果变体标记为先核查，避免把资源目录数误写成独立模型数。

### 用户如何操作

1. 在 FModel 中进入 `End > Content > Character > Player`，搜索清单中的完整变体名。
2. 先判断是否存在 `Model`，并打开资产确认 3D Viewer/Outliner 中是否为
   `SkeletalMesh`。
3. 模型使用 **Save Model**；整目录可使用
   **Save Folder's Packages Models**。
4. `Material` 使用 **Save Folder's Packages Properties (.json)**，
   `Texture` 使用 **Save Folder's Packages Textures**。
5. 导出后检查日志、PNG/JSON 和 PSK/PSKX；ActorX 文件头必须为 `ACTRHEAD`，再更新
   清单复选框和输出文件名。

### 原理与兼容性

- FModel 输出目录设为 `D:\ff7rebirth_exports\fmodel_exports` 并启用
  `Keep Directory Structure` 后，会把 Unreal 虚拟包路径映射为磁盘上的
  `End\Content\...` 层级；因此该目录是 FModel 导出结果，不是 Blender 创建的。
- 一级资源变体可能只有材质/贴图。只有存在 `Model` 且确认是 `SkeletalMesh` 时才执行
  Save Model；没有 Model 的效果项导出 JSON/PNG 后记录为“无独立网格”。
- 当前 FF7 Rebirth 的 glTF tangent 路径仍可能失败，骨骼模型继续使用 ActorX 和
  `First Level Only`。PC7002 当前只保留原始 UASSET，不标记为 Blender 可用。

### 验证

- 直接读取当前 FModel Folders 视图，确认 `Player` 为 `109 folders`，并取得全部一级
  目录名。
- 递归盘点本机 Player 输出：`14` 个一级目录、`266` 个文件；其中 `.pskx 8`、
  `.psk 1`、`.uasset 5`、`.json 99`、`.png 152`、`.hdr 1`。
- 对 109 项与磁盘 14 项取差集得到 95 项，分组复算
  `20+8+17+7+8+3+3+4+4+3+3+9+6=95`。
- 9 个 PSK/PSKX 均验证以 `ACTRHEAD` 开始。

---

## 2026-07-26 — FF7 Rebirth Tools v0.3.0 / 材质、法线与同骨架配件

### 新增与修正

#### 1. 材质改为优先读取 FModel JSON

- 插件会同时扫描“FModel 导出目录”和“贴图目录”中的 MaterialInstance JSON 与图片，
  读取 JSON 顶层 `Textures` 表中的 Unreal 参数名和资源引用。
- `Color/BaseColor/PM_Diffuse`、`Normal`、`Roughness`、`Metallic`、
  `ORM`、`Coverage/Opacity` 等参数先按语义解析，再按 `/Game/...` 包路径在保留层级的
  FModel 输出中定位同名 PNG；只有没有可用 JSON 时才退回文件名启发式匹配。
- `/Game/Renderer/Texture/...` 下的白色、黑色等渲染器占位贴图不会替代真正的角色贴图。
  Base Color 以 `sRGB` 读取，Normal、Roughness、Metallic、ORM、Opacity 以
  `Non-Color` 读取。
- 旧版把 `PC0002_00_Arms_O` 误判为 ORM，是因为在 `Arms` 中做子串匹配时命中了
  三字母通道标记 `ARM`，随后错误地把该图的 G/B 通道接到 Roughness/Metallic。
  现在 `ARM/RMA/MRA/ORM` 只有作为完整尾部词元时才算打包通道图；`Arms_O` 不再命中。
  无 JSON 的兼容回退仍识别 FF7 的 `Mg` 为 Roughness、`Mr` 为 Metallic。
- 勾选“覆盖已有基础贴图”再点击“重新匹配基础贴图”，会清理本插件旧版本生成的
  `FF7RB_` 节点后重新建立连接；不会以同名弱匹配在多个 Unreal 包之间随意选图。

#### 2. DirectX 法线转换与分级强度

- Unreal 的切线空间法线采用 DirectX `Y-`，Blender 的 Normal Map 节点按 OpenGL
  `Y+` 解释。插件现在把 Normal 图设为 `Non-Color`，保留 R/B，只对绿色通道执行
  `G' = 1 - G`，再组合后送入 Normal Map；不再把凹凸方向反着显示。
- 皮肤与眼睛需要比衣物更柔和的微表面：材质名含
  `skin/head/arms/eye/mouth` 时 Normal Strength 为 `0.35`，其他材质默认 `0.7`。
  这些值只控制 Blender 预览节点，不修改原始 PNG。

#### 3. Tifa 眼睛改为共享巩膜与角色虹膜分层

- `Eye` 材质不再把 `PC0002_00_Eye_C` 当作整颗眼球的 Base Color。该图只包含
  Tifa 的虹膜颜色，直接铺满会把眼白染暗或染红。
- JSON 的 `Color` 解析为共享巩膜 `Common_Eye_Player_C`，`IrisColor` 解析为
  `PC0002_00_Eye_C`；眼睛法线继续按 JSON 的 `Normal` 引用解析。
- Blender 节点使用 `VTXW0000` UV，以 `(0.5, 0.5)` 为虹膜中心计算二维距离：
  半径 `0.18` 内使用虹膜，`0.22` 外使用巩膜，中间用 `EASE` 色带平滑过渡。
  这能恢复可用的眼白与虹膜预览，但仍不是 Unreal 的角膜折射、湿润层和运行时眼球
  Shader 的完整复刻。

#### 4. PSK/PSKX 有效性、事务导入与三角反光修复

- 扫描时先检查 `.psk/.pskx` 至少 `32` bytes 且文件头以 `ACTRHEAD` 开始；
  结构可识别的 PSKX/PSK 优先于 FFVII Rebirth 当前可能含非法 tangent 的 glTF。
  手动指定的“模型文件”仍按用户选择导入，不会被扫描器擅自改写。
- “替换上次导入”不再在调用导入器前删除旧批次。导入器返回成功且创建对象后，还会
  先完成法线、缩放、材质等后处理；全部成功才删除旧批次并提交新批次。异常、取消、
  零对象或后处理失败都会清理本次残留对象，原模型保留。
- Blender 3.6 使用官方
  [DarklightGames/io_scene_psk_psa 5.0.6](https://github.com/DarklightGames/io_scene_psk_psa/releases/tag/5.0.6)。
  操作符检测兼容 Blender 动态 `bpy.ops` 命名空间在未注册时抛出的 `KeyError`，并支持
  `import_scene.psk`；其他版本若提供新版 `psk.import_file` 也可使用。
- `io_scene_psk_psa 5.0.6` 会把 FF7 PSK 的自定义分裂法线与 `30° Auto Smooth`
  一起带入 Blender；在这些高密度网格上几乎每个三角形都会形成可见明暗边界，因此
  即使贴图连接正确，皮肤和衣物仍会像皱纸或金属三角片。
- v0.3.0 默认勾选“PSK 导入后修复三角反光”：仅对 PSK/PSKX 新建网格把所有面设为
  Smooth，并关闭不兼容的 Auto Smooth，让 Blender 使用连续的平滑顶点法线；不改
  顶点、面、UV、骨架或权重。旧场景可在“基础材质”区点击“修复 PSK 三角反光”。

#### 5. 一键导入并绑定 Tifa 标准服装默认手套

- `PC0002_00` 主体只保留与手套衔接的手指段；掌部和手套不是权重丢失，而是独立的
  Weapon SkeletalMesh。默认皮手套的精确 FModel 虚拟路径是：

  ```text
  End/Content/Character/Weapon/WE0002_00_Tifa_LeatherGlove/Model/WE0002_00.uasset
  ```

- 在 FModel 精确搜索 `WE0002_00_Tifa_LeatherGlove`，打开 `Model/WE0002_00`，
  在 3D Viewer Outliner 右键 **Save Model**。本次实际输出为：

  ```text
  D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk
  ```

- 同时保留 `WE0002_00_Body`、`WE0002_00_Alpha`、`WE0002_00_Materia`
  Material JSON，以及 `WE0002_00_Body_A/C/Mg/Mr/N/O` 图片和原目录层级。
- v0.3.0 的 **“导入并绑定同骨架配件”** 会导入所选 PSK/PSKX，并逐个检查配件网格：
  每个实际带权 vertex group 必须在当前主体骨架中有同名骨骼，公共骨骼的
  `matrix_local` 最大元素差必须不超过 `0.01`。
- 验证通过后，按钮保留配件原权重与相对变换，把 Armature modifier 和 Parent 改为
  当前主体骨架，删除配件导入产生的重复骨架，将配件加入主体当前批次，并按当前选项
  自动修复三角反光、准备材质。任一网格不兼容时会回滚本次全部配件对象，主体不变。

### 如何操作

1. 主体按既有流程导出 `PC0002_00.pskx`。在 FF7RB 导入区保持默认勾选
   “PSK 导入后修复三角反光”，再点击“导入选中模型”。
2. 如果是 v0.3.0 以前保存的旧场景，点击“修复 PSK 三角反光”；该按钮只处理当前
   FF7RB 批次网格，无需重新导入。
3. 在材质目录层级完整的前提下，勾选“覆盖已有基础贴图”，点击一次
   “重新匹配基础贴图”；确认腿部不再使用 `Arms_O` 的 G/B 通道，眼睛同时出现眼白和
   居中的棕色虹膜、法线凹凸方向正确后，关闭该勾选项。
4. 按上述 Weapon 路径从 FModel 保存 `WE0002_00` 及其 Material/Texture。
5. 在 **“4. 独立配件/武器”** 的“配件/武器模型”选择 `WE0002_00.psk`，点击
   **“导入并绑定同骨架配件”**。无需修改“模型文件”，也无需关闭“替换上次导入”。
6. 成功提示应说明配件网格已绑定到主体骨架；在 Pose Mode 轻微旋转腕/手指骨确认
   手套随主体变形并立即撤销，然后另存 `.blend`。

### 实现原理与兼容性

- JSON 是材质实例对实际纹理包的显式引用，优先级高于相似文件名；保留 FModel
  目录层级可以消除不同 Unreal 包中同名贴图的歧义。
- 眼球分层使用 FF7 Player Eye 的两个颜色来源和 UV 径向蒙版，是 Blender 基础预览
  的确定性近似，不承诺还原游戏全部 Shader 参数。
- DirectX 绿色通道翻转解决法线方向，PSK 平滑修复解决几何分裂法线/Auto Smooth；
  两者原因不同，不能互相替代。
- PSK 主体事务导入保护 FF7RB 当前批次，不会删除 ROE 或未标记对象。配件按钮不会
  开启新的当前批次：验证成功的配件网格直接加入主体批次；失败则删除本次新建对象。
- 配件重绑只复用 PSK 已有权重，不计算自动权重。材质修复与骨架重绑仍是两条独立
  链路：材质正确不能证明骨骼兼容，骨骼兼容也不能代替材质 JSON。

### 验证

- Tifa 主体 `188,921` 顶点、`226,086` 三角面、`12` 材质、`536` 骨骼和
  `480,494` 权重记录的 PSKX 已在 Blender 3.6 导入。
- JSON 引导的无界面验证覆盖全部 `12` 个主体材质：腿部解析为
  `Legs_C/Mg/Mr/N`，眼睛解析为 `Common_Eye_Player_C` +
  `PC0002_00_Eye_C`，嘴部、头发和透明贴图也按各自 JSON 引用定位。
- 材质、扫描、法线强度、平滑修复与事务导入辅助测试共 `11` 项通过；其中覆盖
  导入器成功但材质后处理失败时回滚新对象并保留旧批次。强制重匹配
  可重复执行，不会不断叠加旧 `FF7RB_` 节点。
- 已验证新法线节点对 DirectX Normal 执行 `G' = 1 - G`，并分别写入皮肤/眼睛
  `0.35`、其他材质 `0.7` 的 Strength；主体和手套 PSK 导入后均执行平滑修复。
- FModel 已确认保存 `WE0002_00.psk`（`1,380,580` bytes）；预览为 `229`
  骨骼、`17` sockets、`3` 材质。v0.3.0 的“导入并绑定同骨架配件”已用该文件实测
  通过：自动完成骨骼/静止姿势验证、重绑主体骨架、删除重复骨架、材质准备与三角
  反光修复。

---

---

## 2026-07-26 — FF7 Rebirth Tifa 导出验证 / ActorX workaround

### 新增与修正

#### 1. 固化 UE4SS mapping 生成流程

- 已验证 UE4SS `v3.0.1 Beta #0`（Git SHA `c838a8ac`）可通过内置
  Keybinds 的 `DumpUSMAP()` 生成 FFVII Rebirth mapping。
- 稳定配置是将 `UE4SS-settings.ini` 中所有 `Hook...` 项设为 `0`，
  `Mods\mods.txt` 中关闭其他 Mod，只保留 `Keybinds : 1`。
- 游戏进入可响应键盘的界面后按 `Ctrl+Numpad6`；日志确认：
  `Mappings Generation Completed Successfully!`。
- UE4SS 临时输出 `--c838a8ac.usmap` 已复制为：

  ```text
  D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap
  ```

- 文件大小为 `2,205,102` bytes，源文件与稳定副本的 SHA256 均为：

  ```text
  5675ABC2024CA3ABC98F078B000FEE1C48EC65C015D02EB1D6CC8D107FA4BFD0
  ```

启动游戏只用于让 UE4SS 从运行时 Unreal 反射数据生成 mapping。生成并核对哈希后，
FModel 离线读取 `.pak/.utoc/.ucas`，不需要游戏继续运行；后续游戏 Fatal Error
不会使已经完整写出的 mapping 失效。

#### 2. 确认 FModel 必须使用 FFVII Rebirth 专用 profile

- 本次使用 FModel `4.4.4.0`
  (`b2708293f64ffc858b4901ff785a9078b99c67f4`)。
- Directory Selector 选择游戏根目录，不选 `End\Content\Paks`。
- 手动 profile 使用
  `GAME_FinalFantasy7Rebirth = 68812805`，不能以通用
  `GAME_UE4_26` 或 `GAME_UE4_LATEST` 代替。
- FModel 加载上述稳定 mapping 后，日志同时确认
  `GAME_FinalFantasy7Rebirth` 与
  `Mappings pulled from 'FF7Rebirth-4.26-20260726-c838a8ac.usmap'`。

#### 3. 核对 Player/Tifa 目录和标准版模型

- FModel 虚拟 IoStore 索引的 `End/Content/Character/Player` 下确认有 `109`
  个角色/服装变体目录；这些数字不是物理导出目录数。
- 其中有 `12` 个名称含 Tifa 的直接变体目录：`10` 个 PC0002 变体，另有
  `PC0099_03_Toad_Tifa` 和 `PC7002_00_Tifa_StandardCFEnd2`。
- 标准版是 `PC0002_00_Tifa_Standard`，共 `65` 个 packages：
  Material `13`、Model `7`、Texture `45`。
- Model 子目录的 `7` 项中，`Model/PC0002_00` 和
  `Model/PC0002_00_Condition` 是两个 SkeletalMesh。
- 标准主体应打开 `PC0002_00.uasset`，而不是优先选择 Condition 变体。

#### 4. 记录 glTF `Invalid Tangent` 根因并改用 ActorX

- reader 的
  `Read incorrect amount of tangent bytes ... behind: -217552`
  来自 FFVII Rebirth tangent bulk 的 stride 与精度标志不一致。
  `217,552 = 27,194 × 8`：`27,194` 个顶点的 header 声明每顶点 `8` 字节，
  解析器却按高精度每顶点 `16` 字节读取。
- glTF 保存阶段的
  `Accessor[2] TANGENT[18]: Invalid Tangent`
  是另一个独立问题：CUE4Parse 对整个 tangent `Vector4` 做归一化，破坏了 glTF
  要求的 XYZ 单位长度和手性 `W = ±1`，随后被 SharpGLTF 1.0.6 Strict 校验拒绝。
- 当前 UI workaround：
  **Settings > Models > Mesh Format > ActorX (psk / pskx)**，
  **Level Of Detail Format > First Level Only**；再打开 `PC0002_00.uasset`，
  在 3D Viewer 的 Outliner 中右键模型并选择 **Save Model**。
- ActorX 写位置、法线、UV、骨架和权重，不经过 glTF 的 `VEC4 TANGENT`
  校验。`First Level Only` 控制输出 LOD 数量，但不是 reader 修复；日志仍可能出现
  tangent bytes 错误。
- 长期修复方向是：FFVII Rebirth reader 按 tangent `itemSize` 选择 8/16 字节精度；
  glTF 只归一化 XYZ、单独保持 W 为 `±1`，或使用 SharpGLTF
  `ValidationMode.TryFix`。不建议只用 `ValidationMode.Skip`。

### 实际操作

1. UE4SS 关闭全部 Hook，只启用 Keybinds。
2. 启动游戏，按 `Ctrl+Numpad6`，等待 mapping 成功日志后关闭游戏。
3. 固定 mapping 文件名并核对 SHA256。
4. 在 FModel 为游戏根目录选择专用 `Final Fantasy VII Rebirth` profile，
   加载稳定 mapping。
5. **Settings > Models** 选择 ActorX、First Level Only、PNG，并保持目录层级。
6. 进入
   `End/Content/Character/Player/PC0002_00_Tifa_Standard/Model`，
   双击 `PC0002_00.uasset`。
7. 在 3D Viewer Outliner 右键模型，点击 **Save Model**。
8. Blender 3.6 使用 `io_scene_psk_psa 5.0.6` 导入生成的 `.pskx`；
   FF7RB 插件扫描结果不正确时手动指定该文件。

### 验证

- FModel 日志于 `2026-07-26 14:54:37` 确认成功保存：

  ```text
  D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Player\PC0002_00_Tifa_Standard\Model\PC0002_00.pskx
  ```

- 文件大小 `20,480,844` bytes，SHA256：
  `568B7280E0CB556BB7280CE18E67786257E19E0471E1221CF124C6D625DA1980`。
- PSKX chunk 边界完整，统计为 `188,921` 顶点、`226,086` 三角面、`12`
  材质、`536` 骨骼、`480,494` 权重记录和 `2` 组额外 UV。
- ActorX 导出过程不再出现 SharpGLTF `Invalid Tangent`；reader 的 tangent bytes
  日志仍存在，但没有阻止本次完整 PSKX 写出。

---

---

## 2026-07-25 — FF7 Rebirth Tools v0.1.0 / 脚本按游戏分目录

### 新增与调整

#### 1. 新增独立的 FFVII Rebirth 流程

- 新建 `scripts\final\prepare_fmodel.ps1`。
- 已按本机安装验证游戏资源位于 `End\Content\Paks`，包含成对的
  `.utoc/.ucas`，属于 Unreal IoStore，不能使用 ROE 的 AssetStudioModCLI。
- 脚本检查 archive 配对，建立
  `D:\ff7rebirth_exports\fmodel_exports/blender/xps`，并可启动用户已有的 FModel。
- 提取阶段不内置 AES key、mapping 或猜测的固定 UE 版本；这些内容与用户合法拥有的
  游戏构建相关。

#### 2. 新增 FF7 Rebirth Blender 插件

- 新建 `scripts\final\ff7rebirth_tools.py`，与 ROE 插件完全分离。
- Blender 侧边栏新增 **FF7RB** 页签，第一步就是选择 FModel 导出目录。
- 可递归扫描 `.glb/.gltf/.fbx/.pskx/.psk/.obj`，优先 glTF/FBX 与 LOD0。
- PSK 同时兼容新版 `psk.import_file` 和旧版 `import_scene.psk` 操作符。
- 根据材质名/贴图名匹配 Base Color、Normal、Roughness、ORM、Opacity；默认不覆盖
  已有 Base Color 连接。
- “替换上次导入”只处理本插件标记的上一个导入批次，不删除 ROE 或用户其他对象。

#### 3. ROE 脚本迁入专属目录并保留旧入口

- ROE 正式源码迁到 `scripts\riseoferos\`：
  `extract_character.ps1`、`convert_fbx.py`、`roe_xps_addon.py`、
  `blender_face_materials.py`。
- `scripts\extract_character.ps1` 保留为兼容转发入口，原命令继续可用。
- 文档链接已更新；现有 Blender 用户插件目录中的 ROE 插件不受仓库整理影响。

### 如何操作

#### FFVII Rebirth

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
.\prepare_fmodel.ps1
```

1. 在 FModel 的 Directory Selector 选择 FFVII Rebirth 游戏根目录。
2. 将 Model Export Directory 设为
   `D:\ff7rebirth_exports\fmodel_exports`，优先导出 glTF/LOD0/PNG。
3. Blender 3.6 安装 `scripts\final\ff7rebirth_tools.py`。
4. `N` → **FF7RB** → 选择 FModel 导出目录 → 扫描 → 导入。
5. PSK/PSKX 需要兼容 Blender 3.6 的 `io_scene_psk_psa 5.0.6`；glTF 不需要。

#### Rise of Eros

新路径：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
.\extract_character.ps1 a08 -ExportTextures
```

原来的 `scripts\extract_character.ps1 ...` 仍可使用。

### 实现原理与兼容性

- 两套流程只共享文档入口，不共享引擎提取核心或 Blender Scene 属性。
- FFVII 插件只处理 FModel 的导出物，不直接访问 `.utoc/.ucas`。
- glTF/FBX 使用 Blender 内置导入器；PSK/PSKX 调用已安装的第三方导入器。
- 基础材质匹配使用规范化文件名词段、字符串相似度和贴图角色后缀评分；复杂 Unreal
  皮肤、眼球、头发 Shader 不会伪装成已经完整还原，仍需人工校正。
- ROE 的材质槽缓存、a07 腿部与 a08 眼睛修复代码没有改变，只调整了仓库路径。

### 验证

- 本机 FFVII Rebirth 安装目录检查到 `global.utoc/global.ucas` 及多组
  `pakchunk*.utoc/.ucas`。
- `prepare_fmodel.ps1` 通过 PowerShell 语法检查及隔离临时目录运行测试。
- `ff7rebirth_tools.py` 通过 Python 语法编译与 Blender 3.6 注册/注销测试。
- FF7RB 的贴图角色识别、LOD0 选择评分与 Principled Base Color 节点连接测试通过。
- 已安装到本机 Blender 3.6 用户插件目录并保存启用状态；当时 MCP 端口未监听，因此
  已打开的旧 Blender 窗口需要重启后显示 **FF7RB** 页签。
- ROE 正式脚本内容迁移后进行哈希/语法检查；旧 PowerShell 入口转发参数测试通过。

---

---

## 2026-07-25 — ROE XPS Tools v1.1.3

### 新增与修复

#### 1. 新增 Universal / ROE 双工作流

- “自动识别”根据对象名判断是否为 Rise of Eros 模型。
- “通用模型”保留任意 FBX/OBJ/glTF 的现有材质和关联骨架，可直接转 XPS。
- “ROE 增强”继续处理脸、眼睛、睫毛、眉毛、皮肤和多图集身体材质。
- 处理范围支持“最新导入”“所选网格”“所有可见”，并可采用其他插件导入的所选模型。
- 新增模型诊断、当前材质槽用途/贴图覆盖、头部选中面人工分类及高级眼睛/睫毛参数。

#### 2. 恢复原始材质分区，修复 a07 腿部贴图

- 导入时缓存原始材质槽名称和每个面的材质索引。
- 旧场景已经被压成单一材质槽时，可从“模型来源”指定的原始 FBX 临时恢复分区。
- a07 的身体恢复为四槽分区：
  `pc_a07_hd_body 2 / skin / body 1 / skin2`，分别使用 `body1/body2` Albedo。
- a07 应使用：
  `D:\roe_exports\a07\pc_a07_hd (1)\FBX_GameObjects\pc_a07_hd\pc_a07_hd.fbx`。
  无后缀的 `pc_a07_hd` 本身只有一个身体材质槽，不能用于恢复。

#### 3. 新增“修复眼睛”按钮，修复 a08 眼球误判

- a08 虽然存在 `Eyeball` 顶点组，但 864 个眼球面的 Eyeball 权重不足。
- 旧算法发现语义骨骼组后会关闭几何兜底，因而把眼球全部判成脸，表现为纯白或脸色眼球。
- v1.1.3 新增原始 `eye/eyes/iris` 材质名兜底，并在 ROE 面板增加独立
  **“修复眼睛”** 按钮。
- 按钮只重建眼球材质，并修正眼球槽及误入眼球槽的面；已有有效缓存时不会恢复或扰动
  整个头部材质分区。

#### 4. 提取脚本合并 Steam 安装资源与 LocalLow 缓存

- `extract_character.ps1` 新增 `-CacheRoot`。
- 同时扫描游戏安装目录和
  `%USERPROFILE%\AppData\LocalLow\Pinkcore\Rise of Eros\AssetBundles`。
- 同名 AssetBundle 优先选择更新时间较新的文件；时间相同时优先运行时缓存，并从安装目录
  补齐公共包。
- `-List` 同时识别 `chara_armor` 与 `chara_bare` 模型包，可列出新角色、活动角色和
  只有裸模的 NPC。

### 如何操作

#### 更新插件

1. Blender 3.6 → `Edit > Preferences > Add-ons > Install...`。
2. 选择 `scripts\riseoferos\roe_xps_addon.py` 并覆盖安装。
3. 重启 Blender；仅覆盖磁盘文件不会替换当前内存中的旧代码。

#### 新提取并导入角色

```powershell
.\extract_character.ps1 a08 -ExportTextures
```

1. 在 Blender 3D 视口按 `N`，打开 **ROE** 页签。
2. 工作流选“自动识别”或“ROE 增强”，处理范围选“最新导入”。
3. “模型来源”选择包含完整材质槽的 HD FBX。若有同名 `(1)` 目录，应检查并优先选择
   带完整材质槽和贴图引用的那一份。
4. “ROE 贴图目录”选择 `D:\roe_exports\<角色>\_textures\`。
5. 点击“导入 FBX”→“检查模型”→“检查并准备材质”。
6. 若眼球仍为纯白或脸色，点击 **“修复眼睛”**。
7. 设置 XPS 输出路径后导出。

#### 修复已有场景

1. 在“模型来源”重新指定该角色的原始 FBX，在“ROE 贴图目录”指定 `_textures`。
2. 点击“检查并准备材质”，恢复丢失的身体/头部原始分区。
3. 仅眼球不对时直接点击“修复眼睛”，无需重新导入整个角色。
4. 确认效果后另存 `.blend`；按钮修改的是当前场景内存，未保存不会持久化。

### 实现原理

#### 原始材质布局缓存与恢复

- 对象属性 `roe_source_materials` 保存 FBX 原始材质槽名。
- 面属性 `roe_source_material_index` 保存每个面的原始槽索引。
- `roe_source_fbx` 保存来源 FBX。
- 旧场景缺缓存时，插件临时导入来源 FBX，按对象规范名、顶点数、面数及逐面拓扑匹配，
  复制材质布局后立即删除临时对象。
- 多图集身体根据原始 `body/skin/body1/body2` 槽名寻找对应 Albedo，不再把所有面压到
  第一个贴图。

#### 眼部识别

head 网格先按顶点连通块拆解，再组合以下信号分类：

- `Eyeball / Eyebrow / Eyelid` 骨骼权重；
- 连通块面数、中心高度和尺寸；
- UV 是否位于 `[0,1]`、UV 跨度及是否收缩到小区域；
- 原始材质名中的 `eye/eyes/iris`、`eyebrow/lash`、`tear` 等语义。

a06 没有语义骨骼组时继续使用几何兜底；a07 优先使用有效骨骼权重；a08 在权重不足时
由“眼睛材质名 + 眼球几何”兜底，因此兼容旧角色且不会把整块脸材质误认成眼球。

#### 资源目录合并

提取脚本先建立两个 AssetBundle 根目录的统一清单，再按文件名分组。每组选出更新时间
最新的候选，时间相同时用来源优先级打破平局，最后复制到角色临时 staging 目录交给
AssetStudioModCLI。

### 验证

- a06：眼球 864 面；修复按钮前后脸、睫毛、眉毛、罩层分配不变。
- a07：眼球 864 面；身体四槽面数为 `10017 / 10319 / 22679 / 2948`。
- a08 与 `a08_outfit1`：眼球从脸槽恢复为 864 面，使用
  `pc_a_nk_eye_iris_rgbx_Albedo.png`。
- a08 原始 FBX 可不先准备材质，直接点击“修复眼睛”生成完整五槽头部材质。
- 通用模型材质保留、旧场景缓存恢复、损坏缓存恢复和手工头部区域覆盖测试通过。

