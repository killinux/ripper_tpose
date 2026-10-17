# Vindictus: Defying Fate（2024-03 Pre-Alpha）模型导出

Nexon 的《洛奇英雄传：反抗命运》还没发售（Steam 商店页写 2027）。能拿到的只有 2024-03-14
那次 Pre-Alpha 的客户端（archive.org 项目 `vindictus-defying-fate.-7z`，14.1 GB 7z）；2025-06 的
Alpha Demo（Steam `3576170`）测试结束后被替换成 348 MB 空壳，已经拿不到了。本目录针对
Pre-Alpha 客户端：**UE 5.3、IoStore（utoc/ucas）、Oodle 压缩、索引 AES 加密**。

## 快速开始

所有命令都在本目录里跑（PowerShell 先 `cd 〈仓库〉\scripts\vindictus`）。

### 看有哪些模型

```powershell
python .\list_models.py                             # 全表：id / kind / body / 部件数 / umodel 已导 / blend 已建
python .\list_models.py --kind outfit               # 只看一类：player / outfit / base / monster / npc
python .\list_models.py --resolve PCF_003 --json    # 某一个模型：每个部件的包路径、PSK 是否已导
python .\list_models.py --raw --path-filter /Character/AI/   # 容器里的原始路径（找没归类到的东西）
.\export_model.ps1 -List                            # 同一张表
```

直接解密并读游戏 `Paks\*.utoc` 的目录索引，不开任何工具。当前 36 个模型：`Fiona`、`Lethita`、
女装 `PCF_001`…`PCF_067` + `Shiningwill_legacy`、男装 `PCM_00x_Temp`、`Fiona_BaseBody` /
`PCM_BaseBody`、13 只怪（如 `Gnoll_type3_Tribe_Boss_01`）、2 个 NPC。

### 导出一个模型

```powershell
.\export_model.ps1 Fiona                 # 主角默认装
.\export_model.ps1 PCF_003               # 一套服装（自动配 Fiona 的脸和头发）
.\export_model.ps1 PCF_067 -Force        # 已导过想重做：重导包 + 重建 blend
.\export_model.ps1 Gnoll_type3_Tribe_Boss_01 -NoPreview
```

一条命令做完三步：`list_models.py` 解析包 → UE Viewer 逐包导出 PSK + PNG + 材质参数到
`D:\vindictus_exports\umodel_exports\` → Blender 无头跑 `build_blend.py` 合骨架、建材质、渲预览。
结束时打印骨骼数、各部件顶点、材质/贴图数、告警。产物：

```text
D:\vindictus_exports\blend\<id>\<id>.blend       一副骨架 + 全部部件 + 材质
D:\vindictus_exports\blend\<id>\textures\        贴图
D:\vindictus_exports\blend\<id>\preview.png / preview_face.png
```

整个 `blend\<id>\` 目录可以直接拷给别人。常用参数：`-Force`（重做）、`-NoBlend`（只到 UE Viewer）、
`-NoPreview`、`-Smooth`（平滑法线）、`-IncludeWeapons`（把武器并进来）；路径都有默认值
（`-GameRoot E:\tools\vindictus`、`-ExportRoot D:\vindictus_exports`、`-UmodelExe`、`-BlenderExe`）。

### 批量

```powershell
# 先顺序把包导完（UE Viewer 并发会互相覆盖共享贴图，这一步不能并行）
python .\list_models.py --kind outfit --json | ConvertFrom-Json | Where-Object body -eq PCF | ForEach-Object { .\export_model.ps1 $_.id -NoBlend }
# 再分几路并行跑 Blender，每套 2–3 分钟
foreach ($id in 'PCF_001','PCF_002','PCF_003') { .\export_model.ps1 $id }
```

### 更新画廊

```powershell
cd html
python .\collect_manifest.py     # 汇总 blend\*\build.log
python .\make_gallery.py         # -> html\index.html
```

### 前提（只做一次）

- 客户端在 `E:\tools\vindictus`，UE Viewer 用 `E:\tools\umodel_specific\materials\umodel_materials_ue5.exe`，
  Blender 3.6 装了 `io_scene_psk_psa`——本机都已就位，细节见下面「已验证环境」。
- AES key：脚本从 `VINDICTUS_AES_KEY` 环境变量或 `E:\tools\vindictus\_download\aes_key.txt` 读。
  换机器或丢了就 `python .\find_aes_key.py --out <路径>` 重新算（80 秒）。key 别放进仓库。

### 全手工做一遍（不跑脚本）

[`docs/vindictus-fiona-manual-export.md`](../../docs/vindictus-fiona-manual-export.md) 以 `Fiona_BaseBody` 为例，
从 UE Viewer 解包，到 Blender 里手工组装（转正、合骨架、切旧头、建材质、修脖子、并成一副骨架），
再到手工导出 XPS 和 PMX。每一步都给了菜单路径和数值，并写明对应的自动脚本。

### 导出 PMX（带表情、胸部物理、头发物理）

```powershell
python .\metahuman_dna.py extract --out <目录>\SK_Fiona_Face01.dna      # 从游戏容器里取脸的 DNA（几秒）
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' -b --python .\export_pmx.py -- `
    --xps E:\game_export\Vindictus\Fiona\xps\Fiona_BaseBody\Fiona_BaseBody.xps `
    --dna <目录>\SK_Fiona_Face01.dna --out <输出目录> --model-name Fiona
```

**高清版**：直接从 `export_model.ps1` 建好的 `.blend` 出，贴图按原尺寸：

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' -b --python .\export_pmx.py -- `
    --blend D:\vindictus_exports\blend\PCF_005\PCF_005.blend `
    --dna E:\game_export\Vindictus\_meta\face\SK_Fiona_Face01.dna `
    --out D:\vindictus_exports\pmx --model-name 'Fiona PCF_005'
```

`--blend` 比 `--xps` 多做的事（2026-10-02，PCF_005 第一个用它出）：
- **原尺寸**：每个材质的颜色按它自己贴图的尺寸烘：服装、头发、身体皮肤 4096，脸、眼睛 2048，睫毛、眉毛 1024；
  `--max-texture` 设上限。走 `--xps` 的话贴图是 XPS 里的，Blender2XPS 最多烘到 2048。
- **AO 乘进颜色**：PMX 的材质只有一张颜色贴图，没有法线、粗糙度、AO 的输入。所以把 ARM 贴图 R 通道的 AO 乘进去，
  和 ROE 的高清 PMX 一样（颜色 × 色调 × AO）。`--ao 0.5` 只乘一半。
- **每个材质都烘**：Blender2XPS 平时把「色相 / 饱和度 / 明度」节点和接近白色（差 0.1 以内）的色调当成轻微调整，直接用原图。
  这样脸和手丢掉了材质实例的 `Basecolor Brightness`（0.93、0.90）和偏粉的色调，身体皮肤的色调差得多一点被烘了，三处肤色不一样。
- **共用材质拆开**：一个材质用在两个网格上（PCF_005 的腿 `MI_PCF_Lower01` 在脚和连衣裙两个网格里），
  Blender2XPS 按网格分别烘、却按材质名存，后烘的盖掉先烘的，第一版 PMX 的腿只剩 4.7% 的像素，整条腿看不见。
  现在第二个网格起各用一份拷贝（`<材质>_<网格>`）。
- **裁切 alpha**：游戏和 `.blend` 里服装是 Masked 材质，alpha 只当遮罩：大于 1/3 就完全不透明。MMD 会把 alpha 当真透明度用。
  PCF_005 的裙子 74% 的像素 alpha 在 1/3 到 0.99 之间，第一版 PMX 的裙子成了透出背景的灰色。现在 Masked 材质的 alpha
  按材质自己的阈值烘成 0 / 1，不透明材质 alpha 全是 1；头发、睫毛、眼部的半透明壳保留原来的 alpha。
- **颜色不乘 alpha**：Cycles 的图像节点在它的 Alpha 输出没接到着色器里时，给出的颜色是乘过 alpha 的。`.blend` 里 Alpha 接着
  Principled，但烘焙只取 Base Color，于是颜色被乘了一次遮罩：裙子布料（alpha 0.4–0.6）烘出 0.49，原图是 0.87，PMX 里还是灰的。
  烘之前把带 alpha 的贴图设成 Channel Packed（RGB 和 alpha 各管各的，UE 就是这样把不透明度打包进颜色图的）。
  单独测过：同一张图只接颜色烘，普通模式 0.527，Channel Packed 0.870，和原图一样。ARM 这类非彩色贴图本来就不受影响，AO 一直是对的。
- 中间的 XPS 写在 `<out>\<名字>\_xps\`，导完删掉（`--keep-xps` 保留）。

归档里的高清 XPS（`E:\game_export\Vindictus\Fiona\xps\<id>\<id>.xps`）就是 `--blend` 留下的中间 XPS，换了导出设置要重导时
直接拿它走 `--xps`，不用重新烘：贴图和 `--blend` 出的逐字节相同，一套 1–2 分钟（2026-10-04 的 15 套重导就是这样做的）。
两种来源导完，转换后的 `<名字>_converted.blend` 都改指向 PMX 旁边 `textures\` 里的贴图。

`export_pmx.py` 做的事：
1. **转换**：XPS → Convert to MMD 5，和教程 6.10 的手工步骤一样。
   - 转换前：手指拉直、UE 辅助骨并回所属的一段、前臂拉直、手臂抬到 40°（见下面「手臂权重」「手臂角度」「手指」）；
   - 清骨架缩放；
   - 改 4 行槽位：センター 清空、下半身、頭、目；
   - 一键转换时关掉自动识别。
2. **両目**：沿用 ROE worker 的 `add_both_eyes_bone`。
3. **表情**：Vindictus 的玩家脸是 MetaHuman，没有形态键，表情靠 RigLogic 驱动约 630 根 `FACIAL_*` 骨。
   - 驱动数据在脸网格包里的 `DNAAsset` 中，UE Viewer 不导出。`metahuman_dna.py` 直接从 IoStore 容器里把它切出来，解析 DNA v2.1。
   - 求值和 RigLogic 一样：原始控制 → PSD（带权输入相乘，限制在 0～1）→ 关节增量（每组一个稠密矩阵，LOD 0）→ 正向运动学。
   - **默认做顶点表情**（2026-10-04 起，用户：「后续默认做出的pmx表情都是顶点的」）：走 Expression Kit
     （`scripts/blender_addons/expression_kit`，DNA 来源），PCF_005 / Fiona 出 56 个（ω、ω□、歯無し上 / 下 MetaHuman 没有对应控制）。
     烘焙时先从脸的原始网格包（DNA 旁边的 `SK_Fiona_Face01.uasset.bin`，`--face-package` 可指定）把游戏的完整蒙皮权重
     （每顶点最多 12 个，UE Viewer 只留 4 个）放回去，表情就是游戏里脸动起来的样子；烘完把 PMX 用的 4 权重蒙皮原样放回
     （约 1.5 万个顶点），所以和骨骼表情版只差表情本身。找不到网格包就用 4 权重烘，日志会提示。
   - `--morphs bone` 保留原来的做法：26 个标准 MMD 表情（まばたき、笑い、ウィンク、あいうえお、眉毛……）各按一组控制值求值，
     再把每根骨从静止到摆好的变化写成骨骼表情；求值前先把 DNA 的中性骨架拟合到模型骨架上（620 根骨，平均误差 0.38 mm）。
     骨骼表情只能通过 PMX 的 4 个权重带动皮肤，张嘴、单侧微笑时脸颊起包（あ２ 偏 7.8 mm、ぺろっ 5.2、あ 4.7）。
   - 顶点表情的 PMX 大一倍（PCF_005：8.5 → 17.7 MB），MMD、Blender 里都照常用表情滑块。
4. **物理**：
   - **身体碰撞体**：用 Convert to MMD 5 的。
   - **胸部**：刚体布局按你的 MMD 模板（`标准骨骼与刚体.pmx` 的 乳奶1/乳奶2）：
     - `Bip001_*_bust_1` 上放静态球，`bust_2` 上放动态球；
     - 关节 ±10°，碰撞组不和任何东西碰。
     - **关节加了角度弹簧 450**。模板不带弹簧，站着时重力把乳房一直压在 10° 限位上，看起来整体下坠，右侧上缘还折出一道凹痕。
       弹簧值按 MMD 单位算：1 单位约 8 cm，重力 9.8 单位/s²，球离转轴约 1.56 单位。450 时静止只下坠约 3°，晃动频率约 2 Hz。
       星刃 Fiona 用的 120 在按米制导入的 Blender 预览里看着没问题，按 MMD 单位导入（1.0）实测会下坠 10°。
     - **2026-10-04 起关节改由 `bust_physics.py` 按 MMD 的重力重新定**（见下面「胸部物理按 MMD 重力定」）。
       上面的 450 / ±10° 只用来先把模板搭起来，所有刚体建好以后整个关节重算。
     - **权重**：游戏里 `bust_2` 的皮肤权重最高只有 0.24，刚体晃起来皮肤只动几毫米。所以放大到最高 0.75，多出的从同一顶点的其它骨扣。
       放大倍数随权重平方增长：峰值放大 3.1 倍，边缘（峰值的 30%）只放大约 1.2 倍。整体按一个倍数放大时，边缘过渡变陡，晃起来上缘会折出凹痕。
       T 恤按同样规则处理，跟着皮肤走。
   - **头发**：用 mmd_cloth_physics 建发束。
     - `FACIAL_*` 算身体骨：MetaHuman 发际线的关节名字里带 Hair，但它们是脸皮。
     - 波波头改用 `ornament`（保形）预设。
     - 每条发束从根部起，只要骨尾还在耳线以上（双眼下方 3 cm）就跟着头骨走，从第一节低于耳线开始才参与物理。原因见下面「已验证」。
5. **导出**：按 12.5 倍导出 PMX 并复制贴图；写好的 PMX 里肘部一圈改成 SDEF（`pmx_sdef.py`，见下面「手臂权重」，
   `--no-sdef` 不改）；颜色贴图做扩边（`pad_textures.py`，见下面「贴图扩边」，`--no-pad` 不做）；用 `--blend` 导出时
   按游戏材质设各材质的高光（`pmx_materials.py`，见下面「材质高光」，`--no-tune-materials` 不设）；查付与的计算顺序，
   另存转换后的 `.blend` 和 `.pmx.report.json`。

上面写的骨名是 `Fiona_BaseBody` 的（旧的 3ds Max Biped 身体）。**服装（`PCF_*`）和默认装是 UE5 的身体骨架**，脚本按有没有
`Bip001_Pelvis` 自动判断，规则在 `RIGS` 里。和 Biped 版不同的地方：
- **下半身 = pelvis**（XPS 里叫 `root hips`），センター 清空让插件新建一根空的。自动识别会把 pelvis 当成 センター，
  转换时把它的蒙皮权重清掉：センター 和 下半身 都没有权重，胯部不跟 下半身 动（PCF_005：3235 个顶点、权重和 1207）。
- **胸部 = `breast_physics_01` / `_02`**：游戏的胸是 `breast_l → breast_physics_01 → 02 → 03 → …`，02、03 下面还挂着一圈软组织骨。
  皮肤挂在 02 和它下面所有骨上，按顶点加起来中心正好是 1.0，所以动态球放在 02 上，整个胸跟着摆，权重不用放大。
  模板和 Biped 版一样，关节同样最后由 `bust_physics.py` 重算。
- **裙子**：游戏把裙子根骨挂在 `spine_02`（上半身2）上，MMD 习惯挂在 下半身：弯腰时整条裙子会跟着上身翻起来，所以改挂到 下半身。
  mmd_cloth_physics 按名字分组时只认大写的左右标记（`Skirt_L_01`），`Outfit005_skirt_a_01_l` 这种每条链都成了单独一件，
  链与链之间没有横向关节，裙片会各摆各的、从中间分开。现在同一锚点下的 `*_skirt_<字母>_<序号>_<l|r>` 合成一圈
  （PCF_005：14 条链、54 个刚体、54 个横向关节）。
  - 同样合并的还有外套下摆 `*_coat_*`（PCF_067）、衬衫 / 帽衫下摆 `*_shirt_*`（PCF_008）、默认装的肩布 `*_fabric_*`
    和 PCF_009 的西装下摆 `Outfit009_upper_<字母>_*`（`GARMENT_MERGE`）。飘带、羽毛、项链之类的饰品仍是一条一条单独摆。
  - 有的裙子游戏是按腿拆开的：左半边根骨挂 `thigh_l`、右半边挂 `thigh_r`（默认装的盔甲裙、PCF_001_Temp 的风衣下摆、
    PCF_067）。锚点不同，所以每条腿各合成一片，两片之间不加关节，腿分开时不会互相拉扯；根骨也不改挂，照游戏跟着大腿走。
  - 默认装的盔甲裙片只蒙皮在每条链的 `_02` 上：`_01` 的权重只有 0.3–1.8 或者没有（mmd_cloth_physics 要求至少 2），`_03` 为 0，
    链就只剩一节，一节骨在 mmd_cloth_physics 里算「板子」不建物理，整圈盔甲裙原来不会动。现在单独剩下一节的布料骨
    把它的父骨加回来当链的第一节（`link_lone_garment_bones`，父骨是身体骨、扭转骨、辅助骨时不加，头发不加——发束按条处理），
    盔甲裙每条腿 9 条链、两节、16 对横向关节。同样救回来的还有 PCF_005 手臂上的两圈羽毛（只蒙皮在 `_01` 上，羽毛根骨没有权重）、
    PCF_008 手腕和胸前的丝带、PCF_003 手套的翻边。
- **辅助骨的权重**：UE5 身体有约 260 根扭转骨、矫正骨、肌肉骨，Blender2XPS 给它们加了 `unused_` 前缀。Convert to MMD 5
  转换时把它们的权重并进**离它最近的骨**，不管那根骨是什么：
  - `calf_twist_01` 在小腿下三分之一处，离脚踝比离膝盖近，小腿下半截跟着 足首 转，穿高跟鞋跳舞时小腿从中间折断；
  - 胸口的矫正骨并进了胸部的软组织骨，头颈的并进了头发骨和外套下摆：PCF_067 的钢制胸甲跟着胸部物理晃，头盔跟着
    五束头发摆（一根头发骨多出 1190 的权重），PCF_005 手腕的皮肤跟着手臂上的羽毛摆。
  - 现在转换前先把这些骨的权重并进各自的父骨（`merge_into_parent`，`RIGS["ue"]["into_parent"]`）：UE 里矫正骨只在游戏的
    姿态驱动下才动，静止时就跟着父骨。2026-10-04 起手臂扭转骨也一起并（原来留给插件，以为它会对应到 腕捩 / 手捩，其实
    不会，见下面「手臂权重」），另外加上 Blender2XPS 没加前缀的六根：`upperarm_bicep` / `upperarm_tricep`、
    `wrist_inner` / `wrist_outer`、`calf_knee` / `calf_kneeBack`（`UE_HELPERS`）。
  - Blender2XPS 按名字判断辅助骨，会误伤服装骨：PCF_005 背后中间那条羽毛叫 `Outfit005_spine05_feather_g_bck_01`，`_bck`
    像手臂的矫正骨，就被改成了 `unused_…`，再被上一步并进羽毛根骨，14 条羽毛被绑成一整块甩。现在转换前先把
    `unused_Outfit*` / `unused_Armor*` / `unused_Fiona_*` 改回原名（`unhide_outfit_bones`），它们照常当布料。15 套里只有 PCF_005 有。
  - 插件合并扭转骨和几根带权重的链根骨时，仍会把权重并进最近的非 MMD 骨（羽毛、盾牌挂点 `shield_l`、手腕辅助骨）。
    所以转换前记下每个顶点的权重，转换后非 MMD 骨（不是日文名的骨，脸部的 `FACIAL_*` 除外）多出来的那部分，逐个顶点
    挪到离顶点最近的 MMD 变形骨上，原有的权重不动（`return_conversion_gains`，报告里的 `conversion_gains_moved`）。
    PCF_005：3159 的权重回到 ひじ / 手捩 / 腕捩 / 腕；PCF_067：5099。修好后转换前后逐骨对比，非 MMD 骨一根也没多出权重。
- **不当布料的骨**：`breast_*`、脚趾（`bigtoe_01` 之类，原来被当成了飘带）。
- 头发：mmd_cloth_physics 只给名字像头发的骨建物理，其余挂在 頭 / 首 下面的骨都跟着头走：PCF_005 头冠上的羽毛和耳环、
  PCF_010 的帽檐、PCF_008 的熊耳朵。PCF_008 自带发型（`Outfit008_hair_*`）照头发处理；PCF_001_Temp、PCF_010 的发型和帽子是一个
  部件、只蒙皮在头骨上，没有头发物理；PCF_067 的全罩头盔把头发藏起来了。
- PCF_007 鞋子部件里的白色竖纹及膝长袜，10-03 第一次重出时看着像「袜筒比小腿细、躲在皮肤里，腿一动就从小腿外侧露出来」，
  当成了资源的问题；其实是合并骨架时鞋落在脚后 13 cm（见下面「已知限制」），修好以后长袜套在小腿上。
- 资源里缺布料骨的：Shiningwill_legacy 的白披风（左右两条长布条，从肩胛垂到膝盖）只蒙皮在 `Bip001_Spine2` 一根骨上，
  上身一扭就像木板一样甩出去。`build_blend.py` 给它补了布料骨（`CAPE_RIGS` / `rig_cape()`）：每条 2 列 × 6 节
  （`LegacyCape_<L|R>_coat_<a|b>_<nn>_<l|r>`，挂在 `Bip001_Spine2` 下，关节沿披风表面排），肩胛以下的蒙皮按位置分给
  左右相邻的两列、上下相邻的两节，往上 8 cm 渐变回原来的权重，肩上那段照旧跟着肩走。导 PMX 时每条的两列连成一片布
  （`GARMENT_MERGE`，名字带 cape 用 coat 预设）。这套旧装的 Upper 和 Onepiece 两个部件各带一份披风（几乎重合，都显示），
  两份按同样的规则绑，一起动。

#### 胸部物理按 MMD 重力定（`bust_physics.py`，2026-10-04）

上面模板的弹簧 450 是 09-26 按重力 9.8 单位/s² 定的。和 MMD 兼容的物理实现（three.js MMDPhysics、saba、MMDAgent-EX）
用的是 98（见 [`scripts/mmd_physics/README.md`](../mmd_physics/README.md)）。10-04 按这个重力把 15 套 PMX 都测了一遍
（`checks/bust_check.py`、`checks/bust_dance.py`）：
- 站着不动，每套的胸都下垂 7–12°，贴着 10° 的限位；
- 限位卡住了幅度：转到 10° 时胸前只移动 1.0–1.7 cm，跳舞时来回约 1 cm；衣服都跟着动，没有穿模；
- PCF_008 帽衫胸前的两片布料，每边 8 个刚体挂在胸部刚体上，重量是胸本身的 10 倍，胸一直被拽在下限，几乎不晃。

现在导出的最后一步（所有刚体建好以后）由 `bust_physics.py` 重算每个胸部关节：
- **弹簧按重力算**：静止下垂角 = 重力力矩 ÷（弹簧 − 重力刚度），所以弹簧 = 力矩 ÷ 下垂角 + 重力刚度。
  - 力矩算上挂在胸上的所有刚体。这些刚体的质量和它们自己关节的弹簧先一起乘 0.2：它们自己怎么摆不变，
    只是拖胸的力小了（和 ROE g05 的吊坠一样）。
  - 重力刚度来自骨骼的位置：UE 身体的 `breast_physics_02` 在乳房里偏下，刚体（它带动的那片皮肤的中心）在它上方
    1.5–7.6 cm，像一个倒立摆，往前倾得越多重力力矩越大。不算这一项的话，按 8° 算的弹簧实际停在 11°，
    按 15° 算的直接垂到 25° 的限位上。
- **限位** 俯仰 / 左右 / 扭转 ±25° / ±15° / ±5°。
- **阻尼** 0.5（移動減衰、回転減衰都是）。

限位和阻尼一开始定的是 ±18°、0.99（「C 方案」）：「来杯好茶摇一摇」30 秒里摆幅（10%–90%）从模板的 5.6–8.6° 变成 13–20°，
平均下垂差不多，PCF_005 静止下垂 7.9°（目标 8°），停下来约 1 秒静住。用户在 Blender 里实时试过几组值，要晃得更明显，
定了阻尼 0.5、±25°，看过 PCF_005 的视频后改成默认。手势舞（MMD 的重力）里 PCF_005 的摆幅（10%–90% / 最大）：

| | 模板 | C（0.99 / ±18°） | 现在（0.5 / ±25°） |
|---|---|---|---|
| 摆幅 | 8.1–8.9° / 16–17.5° | 11.4–13.1° / 23–24° | 14.2–15.9° / 29–30° |

代价：静止姿势里把胸骨直接转到 ±25°，5 套（默认装、PCF_003 / 005 / 006 / 008）领口附近的皮肤会从衣服里穿出来
（最多 57 个顶点、1.7 cm）；±18° 时最多 0.8 cm，PCF_005 只有 19 个顶点、0.55 cm（连衣裙两层布之间）。哪套跳舞时看得出来，
就单独用 `--bust "pitch_limit=18"` 导那一套；要回到 C 方案用 `--bust "lin_damp=0.99,ang_damp=0.99,pitch_limit=18"`。

所有数值都有默认值，都能改：

```powershell
# 导出时默认就用这套
... export_pmx.py -- --blend ... --bust "sag=10,pitch_limit=20"      # 改几个值
... export_pmx.py -- --blend ... --bust-template                      # 不重算，保留模板（450 / ±10° / 阻尼 0.5）

# 已经导出的 PMX 直接改，不用重新导出（普通 Python，几秒）
python .\bust_physics.py <原.pmx> <新.pmx>                    # 默认值
python .\bust_physics.py <原.pmx> <新.pmx> --pitch-limit 20   # 改值
python .\bust_physics.py <原.pmx> <新.pmx> --hanging-only     # 只给挂在胸上的布料减重，关节不动
python .\bust_physics.py <原.pmx> - --dry-run                 # 只打印
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `sag` | 8 | 静止时胸往下垂的角度（俯仰），俯仰弹簧由它反推 |
| `twist_sag` | 4 | 绕前后轴的静止侧倾，扭转弹簧由它反推 |
| `yaw_scale` | 1 | 左右弹簧 = 俯仰弹簧 × 这个倍数 |
| `pitch_limit` / `yaw_limit` / `twist_limit` | 25 / 15 / 5 | 转动限位（±度）；C 方案俯仰 18 |
| `lin_damp` / `ang_damp` | 0.5 / 0.5 | 胸部刚体的移動減衰 / 回転減衰；C 方案 0.99 |
| `hanging_scale` | 0.2 | 挂在胸上的刚体的质量和它们关节的弹簧乘这个倍数 |
| `gravity` | 98 | MMD 的重力（单位/s²） |
| `bones` | `胸\|乳\|chest\|breast\|bust\|oppai` | 按骨名找胸部刚体；只认挂在静态刚体上的那一个，所以 PCF_008 名字里带 breast 的布料不会被当成胸 |

- 改过的 PMX 注释里有一行 `bust physics sized for gravity 98 ...`。命令行看到这一行就不再改第二遍（不然挂件会被减重两次），
  要重来加 `--force`。
- 新 PMX 写在别的文件夹时，旁边要有一份 `textures\`，不然贴图路径会指回原文件夹。读进来再原样写出去，文件逐字节相同。
- 导出流水线和命令行用的是同一套计算：PCF_005 从存档的 XPS 重新导一次，和「存档 PMX + 命令行」的结果逐项相同，
  和存档版只差两个胸部关节、两个胸部刚体的阻尼（当时的 C 方案）。
- 量胸部的脚本：`checks/bust_check.py`（姿势测试：胸骨转到限位，逐材质看移动和穿模；原地跳测试）、`checks/bust_dance.py`
  （跳舞时的摆幅）、`checks/bust_video.py` + `checks/bust_grid.py`（胸口特写视频、多段拼一起），物理设置都在 `checks/mmd_scene.py`。
  默认的测试动作是 `E:\Downloads\mmd\0.meeynara手势舞2025.2.14by小王动画\适配瓦雷莎.vmd`（10 秒，`bust_grid.py --audio test`
  配它的 WAV），在 `checks/test_motion.py` 里改；`--vmd` 换别的动作。
- 每套 PMX 旁边的 `<id>_dance.mp4`（2026-10-04 起）就是这几个脚本拼的三格：全身（`bust_video.py --fixed --yaw 25
  --distance 3.2 --lift -0.45 --sdef`，镜头不跟身体走）｜胸口特写｜左肘特写（`arm_video.py --sdef`），手势舞 + 配乐。
  胸口镜头瞄准胸部刚体；没有胸部物理的（PCF_067 的钢胸甲）瞄准胸骨。
- `bust_video.py --physics addon` 换成用户的 MMD Physics 插件（`E:\code\othercode\mmd_physics`）预览时的物理：重力
  9.8 单位/s²、SPRING2、临界阻尼的 10 %（`mmd_scene.addon_like`）。默认的 `mmd` 是重力 98（three.js MMDPhysics、saba、
  MMDAgent-EX 的值）。两种都把「和谁都不碰」的刚体放进单独的碰撞层：插件的预览没这么做，跳手势舞时手会撞到胸，
  摆角冲到 44–58°（限位 18°），MMD 里不会。
- 用插件调这批模型要注意：它按骨名认胸，`breast_physics_01`（静态锚点）和 `_02` 都算胸部刚体，面板读的是锚点的值；
  套预设会把锚点也改成物理演算，胸就塌了。只读参数、预览没问题。

#### 手臂权重：肘部和扭转（`limbs.py`，2026-10-04）

用户反馈导出的 PMX 肘部权重不对。查下来是两件事，都出在 Convert to MMD 5 转换这一步（UE 身体的 14 套都有，Biped 身体的
Fiona_BaseBody、Shiningwill_legacy 弯、扭都正常）：

- **扭转骨的权重被按「离哪个骨头起点最近」逐个顶点分走。** 游戏的手臂是 MetaHuman 身体：`upperarm_l` / `lowerarm_l` 本身
  不带皮肤，整条胳膊挂在扭转骨 `upperarm_twist_01/02`、`lowerarm_twist_01/02` 和它们下面的 `twistCor`、`bicep` / `tricep`、
  矫正骨上；肘关节那一圈约 60 % 在 `upperarm_twistCor_02`（上臂），35 % 在前臂的矫正骨。游戏里这些骨由
  `ABP_PCF_Corrective`、`Rig_proc_ControlRig`、`PA_female_base` 在运行时驱动，MMD 没有这套驱动。
  插件不接手 UE 的扭转骨：它自己建 腕捩 / 手捩 和 腕捩1–3 / 手捩1–3（付与 0.25 / 0.5 / 0.75），再把 腕 / ひじ 的权重
  按沿骨的位置切给它们（`convert/weights/twist.py`）；`unused_` 扭转骨则在 `transfer_unused_weights` 里逐个顶点给了
  **骨头起点离它最近的骨**。结果：
  - 上臂靠肘的最后约八分之一给了 ひじ（PCF_005 沿上臂 0.88 处的顶点：游戏里 93 % 上臂，转换后 98 % ひじ），弯肘时从上臂
    中下段开始折；插件再把 36.7° 弯着的前臂拉直烘进静止网格时，这段跟着转，直臂站着肘上方就有一个 S 形扭折（最多 2.6 cm）。
  - 前臂的皮肤先给了 手首 和手腕辅助骨，再被 `return_conversion_gains` 送回 ひじ：前臂 70 % 处一圈 100 % 在 ひじ 上，
    手捩 一扭两边的皮肤转、这一圈不转。`upperarm_bicep` / `tricep` 没前缀、留成了单独的骨，挂在被插件改挂到 腕捩 下面的
    扭转骨上，上臂中段整片跟着 腕捩 全扭。腕捩 转 80° 时肘部撕开一道缝，手捩 转 80° 时前臂起皱、手腕护臂撕裂。
- **拉直前臂用的是线性蒙皮。** 插件把前臂摆直后应用骨架修改器（`fix_forearm_bend`），上臂、前臂各占一部分权重的顶点
  会落在两边位置的连线上，肘部变细。

修法（`export_pmx.py` + `limbs.py`，转换前做，插件不用改）：
1. **辅助骨按骨架角色并回所属的那一段。** 扭转骨、`twistCor`、矫正骨、`bicep` / `tricep`、`wrist_inner` / `outer`、
   `calf_knee` / `kneeBack` 全部并进父骨，一路并到 上臂 / 前臂 / 手 / 小腿（`UE_HELPERS`）。插件看到的就是干净的
   腕 / ひじ / 手首，它的扭转切分（按位置平滑过渡，权重守恒）照常做；上臂、前臂、手之间的分界和游戏一模一样。
2. **前臂自己拉直，按球面混合。** `limbs.straighten_forearms()`：每个顶点按它在前臂（及以下）上的权重比例，绕肘关节转
   相应的角度，到关节的距离不变（MMD SDEF 的原理），形状键一起转；前臂、手、手指和挂在下面的骨跟着转。插件随后看到手臂
   已经是直的（< 2°）就跳过它自己的烘焙。骨链名是参数，别的骨架也能用。
3. **肘部 SDEF（导出默认做，`pmx_sdef.py`）**：PMX 写好以后，只挂在 腕捩 + ひじ 两根骨上的顶点（PCF_005 左 235、右 232 个）
   改成 SDEF，C = R0 = R1 = ひじ 的位置。BDEF2 的顶点弯肘时走两根骨各自位置的连线，外侧变平、内侧往里挤；SDEF 按两根骨
   旋转的混合绕肘关节转，弯到 130° 外侧还是圆的、内侧不挤。MMD、MMM 自己算 SDEF；Blender 里要手动绑定才看得到
   （侧栏「杂项」→「MMD SDEF驱动器」→「绑定」，偏好设置 > 文件路径里要勾「自动运行 Python 脚本」）。
   - 一开始没默认做：护臂的锯齿边和下面的皮肤，游戏里权重略有差别，SDEF 各按各的混合转，两层交叉的地方会露出几点。
     用户比过带和不带 SDEF 的视频（`checks/arm_video.py --sdef`），选了带的。
   - 只改写好的 PMX 文件，不动转换后的 `.blend`（那里没有 SDEF；把 PMX 导进 Blender 就有）。`--no-sdef` 不做；
     `--sdef-joints 左ひじ,右ひじ,左ひざ,右ひざ` 连膝盖一起做（每根配它在 PMX 里的父骨，膝盖没测过）。
   - 已经导出的 PMX 也能单独加，普通 Python：`python .\pmx_sdef.py <原.pmx> <新.pmx>`（`--dry-run` 只数顶点）。
     读进来原样写出去逐字节相同，所以输出和输入只差这些顶点和注释里的一行；别的游戏的 PMX 同样能用。
   - **还没解决（2026-10-06）**：用户看变身视频 1 说「胳膊肘的位置还是有缺陷」。弯到 110–145° 时，肘部外侧有一道折线。
     查到的原因：SDEF 只给了正好挂在 腕捩 + ひじ 两根骨上的顶点（PCF_005 每边 232 个）。紧挨着的一圈顶点还带着扭转骨
     手捩1 或 腕捩3，一共三根骨（PCF_005 每边 147 个，在肘下 4–6.6 cm 和肘上约 5.5 cm），只能线性混合，弯肘时往里瘪；
     旁边的 SDEF 顶点保持圆，交界处就折出一道线。所有 UE 身体的服装都这样。
     - 试过的修法是 `pmx_sdef.py --fold`（试验选项，默认不开）。横跨肘关节的顶点把扭转骨的权重并回同一段的主骨，也做成
       SDEF。扭转骨只管扭、不管弯，所以弯曲时完全一样。前臂的扭转从这圈下面开始，按 ひじ→手捩 距离的 0.3 倍逐渐恢复，
       扭的时候没有断层。
     - 在 Blender 里：手势舞第 326 / 334 帧的折线和肘尖缺口小了很多，弯 130° 更干净，扭 80° 和原来一样
       （`E:\game_export\Vindictus\_disperse\肘部检查\肘部折线_修前修后_*.jpg`）。
     - 用户自己测完说肘部还有问题，所以默认没开，存档也没改。试验文件 `PCF_005_肘部修正.pmx`、`Fiona_肘部修正.pmx`
       放在各自的 PMX 文件夹里。原因和新的修法见第 4 条。
4. **肘部换成游戏自己的矫正骨（`pmx_elbow.py`，2026-10-11，试验中，还没批量）**。用户是在 Blender 里（mmd_tools 默认导入）
   看到「弯曲时内侧塌陷 / 穿插」的。Blender 不跑 SDEF，肘部就是线性蒙皮：弯越深越捏成 V 形（PCF_005 弯 149° 离游戏的样子
   差 6.1 cm）；动作的 ひじ 关键帧还带着前臂扭转（手势舞最多 87°，动作是给手臂下垂约 42° 的模型做的，这套身体是 53°），
   线性蒙皮一扭就像拧糖纸，肘部一圈缩 29 %。MMD 里的 SDEF 是圆的，但蕾丝袖口和下面的皮肤错开，露出黑洞。
   - **游戏怎么做的**：MetaHuman 身体的肘部靠矫正骨，`ABP_PCF_Corrective` 的 PoseDriver 按姿势资源
     `BaseBody_PCF/Poses/pcf_lowerarm_l/r_pose`（9 个姿势，肘部弯 3.7°–148.7°）驱动：`lowerarm_correctiveRoot` 转弯曲的
     一半，`lowerarm_in / out / fwd / bck` 在上面平移（弯到 148.7° 时肘窝那根移 9 cm），`upperarm_bicep / tricep` 鼓起。
     MMD 没有这种驱动，导出时这些骨都并掉了。
   - **做法**：每条胳膊加两根 MMD 和 mmd_tools 都认的「回転付与」辅助骨，挂在 腕捩 下面、不显示：`左ひじ補1` 跟 ひじ 转
     100 %，支点在手臂轴线上往肩膀方向 32 cm（分到它的顶点弯肘时会滑开，和游戏的矫正骨推肉一样）；`左ひじ補2` 跟 ひじ
     转 50 %，支点在肘关节（弯和扭都多一个中间台阶，肘部不缩）。离肘 20 cm 以内的顶点（袖套等衣服层一起）重新算权重和
     静止位置：拿 XPS（游戏的绑定网格和权重）套上姿势资源里 9 个角度的矫正骨，作为目标去拟合；同时要求 ひじ 扭转时不缩、
     腕捩 扭转时和原来一样分配。原来的 腕捩1–3 / 手捩1–3 扭转比例保留，一共不超过 4 根骨。这些顶点的 SDEF 去掉，改成普通
     权重，MMD 和 Blender 里算法一样。
   - **为什么只用这两根**：远支点配小数比例（比如跟 65 %）弯 149° 能贴游戏到 0.7 cm（现在是 1.3 cm）。但 mmd_tools 实现
     付与是把欧拉角按比例缩放，不是 MMD 的四元数插值；又弯又扭的时候角度差几度，乘上 32 cm 的力臂，在 Blender 里鼓出 2 cm
     的包。跟 100 % 的骨原样复制旋转，没有这个问题；跟 50 % 的骨支点就在关节上，力臂小。手势舞最狠的几帧，Blender 和 MMD
     最多差 1.0 cm（平均 0.02 cm）。两根骨的支点都在手臂轴线上，ひじ 带的扭转不会把肉甩开。辅助骨在 PMX 里带
     「ローカル軸」，和 mmd_tools 给 ひじ 自动设的轴一样，这样 mmd_tools 会直接照搬 ひじ 的旋转，单纯弯曲时和 MMD 完全一致。
   - **权重往相邻顶点靠（`WEIGHT_SMOOTH = 3`，`--weight-smooth`，0 = 不靠）**：用户问「肘部的权重是否有一小块缺失了，
     所有的部分都能被控制么」。每个顶点单独拟合时，肘窝有一条细线的顶点几乎全挂在隐藏的辅助骨上（100 %，旁边只有 40 %），
     在 Blender 权重绘制里看 ひじ（或任何能操作的骨）就像缺了一块。其实没有缺权重、也没有不受控制的顶点：每个顶点合计 1，
     肘部 20 cm 内只用手臂骨和物理驱动的蕾丝骨，辅助骨靠付与跟着 ひじ 转。现在拟合时每个顶点的权重往相邻顶点拉：辅助骨
     最多约 0.7，每个顶点至少 0.3 在能操作的骨上，相邻顶点最多差 0.18（原来 0.47），和游戏自己矫正骨的权重一样是一条宽而
     柔和的带子（游戏最多 0.6）。贴游戏几乎不变（PCF_005 平均 0.114 → 0.117 cm；Fiona 默认装平均 0.135 → 0.146 cm，护肘
     甲片整块平均 0.5 挂在辅助骨上，从 0.16 平滑过渡到 0.95），Blender 和 MMD 的差距反而变小（手势舞最狠的帧 1.34 →
     1.00 cm）。强度 0 / 1 / 3 / 10：PCF_005 平均误差 0.114 / 0.115 / 0.117 / 0.120 cm，相邻顶点最大差 0.47 / 0.22 / 0.18 /
     0.15。对比图 `E:\game_export\Vindictus\_disperse\肘部检查\*_肘部权重_缺口原因和平滑.jpg`。
   - **用法**（普通 Python）：`python .\pmx_elbow.py <原.pmx> <新.pmx> --xps <导出这个 PMX 用的 XPS>`，`--report r.json`
     存数据。新文件写在原文件旁边（mmd_tools 写 PMX 时贴图路径按输出位置算）。注释里加一行标记，已经做过的会拒绝再做。
     游戏数据（姿势资源 + 骨架，CUE4Parse 导出的 JSON，约 1.4 MB）不放仓库，默认在 `E:\game_export\Vindictus\_meta\elbow`
     （`--game-data` 改）。重导：
     `cue4parse.exe -i <Paks> -g GAME_UE5_3 -k <key> -m vdf53_patched.usmap -f json -y -o <out>
     -p "Vindictus/Content/VindictusRoot/Character/Player/BaseBody_PCF/Poses/*"
     -p "Vindictus/Content/VindictusRoot/Character/Player/BaseBody_PCF/Model/SK_PCF_BaseBody01_Skeleton.uasset"`
     （usmap 照 `levels/README.md` 第 1 步打补丁），取 `pcf_lowerarm_l_pose.json`、`pcf_lowerarm_r_pose.json` 和骨架 JSON。
   - **实测**（PCF_005，按游戏的肘轴弯）：离游戏的样子弯 89° / 117° / 149° 最多 0.5 / 0.6 / 1.4 cm（原来线性 2.8 / 4.4 /
     6.1，SDEF 2.2 / 3.4 / 4.6）；ひじ 扭 90° 肘部一圈最多缩 13 %（原来 29 %）；腕捩 扭 80° 和原来平均差 0.07 cm、最多
     0.8 cm；手捩 扭 80° 最多 0.14 cm；静止位置最多动 0.6 cm（游戏自己伸直时的形状），改动先在网格上平滑过，相邻顶点
     高低差不到 0.6 mm，UV 接缝两边仍然重合。手势舞全部 ひじ 关键帧（最深 147°、带 84° 扭转）变形量不超过同样角度纯弯曲
     的 1.05 倍。Blender 实际摆姿势逐点对过：单纯弯、单纯扭和公式一致到 0.0001 cm。Fiona 默认装（板甲护肘）：离游戏
     6.7 → 1.4 cm，护肘甲片保持形状、不被压扁。
   - 试验文件 `PCF_005_肘部矫正骨.pmx`、`Fiona_肘部矫正骨.pmx` 在各自的 PMX 文件夹，存档原文件没动；对比图在
     `E:\game_export\Vindictus\_disperse\肘部检查\`（`肘部_游戏矫正骨_四方对比_*.jpg`、`*_手势舞_肘部_新旧对比_*.jpg`、
     `PCF_005_扭转加弯曲_放大_三方对比.jpg`）。用户确认以后再批量做 14 套 UE 身体的服装、考虑放进 `export_pmx.py` 默认步骤；
     Biped 身体的 Fiona_BaseBody、Shiningwill_legacy 不用。

结果（PCF_005，对照游戏原骨架同样弯法的线性蒙皮）：
- 沿手臂 0.4–1.7 每一格，上臂 / 前臂 / 手的权重占比和游戏完全相同（原来 0.9–1.0 处平均差 0.60）；转换后非 MMD 骨多出的
  权重从 3159 变成 0。
- 和只改了胸部的 `PCF_005_bustC.pmx` 逐顶点比：位置变的 1116 个全在手臂（肘部扭折拉平），权重变的在手臂和膝盖
  （护膝骨并进 ひざD，和原来跟着 ひざ 转等价）；骨骼、表情、刚体、关节都一样。
- 弯到 90° / 130°：肘部圆、折在肘上，和游戏一致；130° 内侧和游戏一样有线性蒙皮的挤压（游戏靠运行时的矫正骨补）。
  扭 80°：上臂、前臂都平滑，没有撕裂。

没改的：
- 插件的手腕回收照原样保留（`add_twist_bone` 把前臂末端的 手首 权重收回 手捩，沿前臂 0.9–1.1 渐变）。插件的腋窝平滑
  （`complete_missing_bones` 把 肩 的权重加一份给 腕）原来也保留，2026-10-11 起 UE 身体不做了，见下面「肩部」。

检查脚本：
- `checks/arm_shares.py`（转换前后每段权重占比，打印 `ARM_SHARES=`，正常 ≤ 0.02）：
  `blender -b <id>_converted.blend --factory-startup --python checks\arm_shares.py -- <id>.xps`
- `checks/arm_stills.py`（静止 / 弯 90° / 130° / 腕捩·手捩 扭 80°，灰模两个角度；`game` 模式拍 build_blend 的 .blend）+
  `checks/arm_sheet.py`（拼图）；`checks/arm_video.py`（跟着上臂拍肘部的跳舞视频，配 `bust_grid.py` 并排；`--sdef`
  用 mmd_tools 的 SDEF 驱动器带动 PMX 里的 SDEF 顶点，Blender 要加 `-y`）。

Convert to MMD 5 插件那边（另一个窗口）同时做了一套通用的做法：
- 骨架识别优先认 XPS 标准名；
- 新增胸部、头发物理按钮。

两边的逐项对比、实测数据和合并建议见 [`docs/vindictus-fiona-pmx-approaches.md`](../../docs/vindictus-fiona-pmx-approaches.md)。
重测用的脚本在 [`checks/`](checks/)。

#### 手臂角度：抬到 MMD 动作用的角度（`limbs.raise_arms`，导出默认做，2026-10-11，试验中）

VMD 记的是每根骨相对原模型的旋转。原模型的手臂垂多少度，动作就是按那个角度做的；手臂垂得更低的模型，所有手臂姿势都
跟着低一截，肘关节的转轴也和动作的对不上，弯肘的一部分会变成前臂的扭转。这套 UE 身体的上臂在水平线下 52.9°；
`E:\Downloads\mmd` 里 62 支动作的 腕捩 / 手捩 转轴算出来，原模型在 36.7°–42.3°（中位数约 40°）；Convert to MMD 5
的标准手臂（从真实 PMX 量的）是 37.2°。

- **做法**：`export_pmx.py` 在转换前（拉直前臂之后）把每条胳膊绕肩关节、在过手臂的竖直平面里抬到 40°（`--arm-angle`，
  给 0 保持游戏的 52.9°；只对 UE 身体）。顶点按各自在手臂上的权重比例转相应的角度，绕肩关节、距离不变，肩膀和腋下平滑
  过渡、不变细，和拉直前臂同一个函数（`limbs.turn_by_share`）。插件随后在抬好的手臂上建 腕捩 / 手捩 和 腕捩1–3 /
  手捩1–3：辅助骨照常竖直，扭转权重按最终的形状切分；肘部辅助骨（`pmx_elbow.py`）最后加，它会认出手臂抬过多少
  （拿 PMX 的上臂和游戏骨架比），对网格、目标形状和肘轴都按同样的抬法换算。
  - 先试过在做好的 PMX 上整条手臂转过去（先建骨、后抬臂）。几何上一样，但 腕捩1–3 / 手捩1–3 跟着歪了 12.9°。用户指出
    「应该先修正胳膊的角度，再加旋转骨」，所以改成在转换前抬。
- **实测**（PCF_005、Fiona 默认装，重新导出 → 布料碰撞（`--colliders-from Fiona_full`）→ `pmx_elbow.py`）：
  - 两边 52.9° → 40.00°。腕捩1–3 / 手捩1–3 离竖直 0.0°（先建骨后抬臂的那版是 12.9°）。
  - 不挂手臂的顶点和存档逐个相同（0.00000 cm）。表情偏移最多差 0.19 mm（重新烘焙的浮点误差）。胸部刚体差 0.008 mm。
    变的只有手臂上的刚体：PCF_005 手背羽毛、Fiona 肩下布、手臂碰撞体（碰撞工具让它们沿关节连线跟到新角度）。
  - 肘部：离游戏的样子和抬臂前一样（PCF_005 弯 149° 最多 1.5 cm）。Blender 里单纯弯 / 扭和公式一致到 0.0001 cm。
  - 手势舞 ひじ 关键帧带的前臂扭转（按这套身体的前臂轴量）：中位数从 51–57° 降到 38–39°，最大从 78–84° 降到 61°，
    剩下的是动作本身的扭转。
  - 静止姿势的肩膀、腋下、肩胛平滑。Fiona 的肩甲跟着抬，甲片不变形。手势舞里手的位置整体更高、更开，
    第 239 帧不再两手交叉挡在脖子前。
- 试验文件 `PCF_005_手臂修正.pmx`、`Fiona_手臂修正.pmx`（重新导出 + 碰撞 + 肘部）在各自 PMX 文件夹，贴图和存档的
  逐字节相同。对比图在 `E:\game_export\Vindictus\_disperse\肘部检查\`：
  - `PCF_005_捩骨方向_三版对比.jpg`
  - `*_手臂抬到40度_*.jpg`
  - `*_新版_手势舞_肘部_对比_*.jpg`

#### 手指：拉直（`limbs.straighten_fingers`，导出默认做，2026-10-11，试验中）

用户问「手指是否需要变直」。这套 UE 身体绑定时手指是弯的（游戏骨架的关节角）：
- 指根（掌指关节）：食指 19.7°、中指 24.4°、无名指 17.9°、小指 11.8°；
- 第二节：11.7° / 19.2° / 26.4° / 20.3°；
- 拇指第二节 21.1°；指尖那一节 0.1–4.6°，拇指 8.4°。

PMX 里量（和别的 MMD 模型一样，指１ 对「手首 → 指１」连线）是指１ 27–30°、指２ 12–26°、親指 21°。MMD 动作把静止
姿势当成手指伸直：张开的手只张到半握，握拳又多握 20–30°，指尖压进手心。用户 `E:\4090` 里几个 MMD 模型（Misaki、
Bunny / Reika / Lucy / Tifa 那一系列）静止时是指１ 2–19°、指２ 0–6°、親指 0–22°。

- **做法**：`export_pmx.py` 在转换前、UE 辅助骨并回父骨之前，一个关节一个关节从指根往外拉直：四指的 01 顺着掌骨，
  02 顺着 01；拇指的 02 顺着 01。顶点按各自在关节以外那几根骨上的权重比例转（和拉直前臂同一个函数）。游戏的半角骨
  （`index_01_half` 这类，挂在关节骨下面，游戏里只转关节的一半；绑定时和关节骨方向一致，差 0.0–0.6°）上的权重
  算一半，所以指根、第二节一圈的皮肤只转一半角度。这要用到半角骨自己的权重，所以放在并骨之前。
  - 最末一节后面没有骨，量不出方向（用网格估计会差 4–13°，比它本身的弯曲还大），保持原样（0.1–4.6°，拇指 8.4°）。
  - `--keep-fingers` 不拉直。`pmx_elbow.py` 从 左人指１–３ 是否在一条线上认出手指拉直过，匹配网格时同样拉直 XPS。
- **实测**（PCF_005，重新导出 → 布料碰撞 → `pmx_elbow.py`）：
  - PMX 的手指角度：指１ 食指 / 中指 / 无名指 / 小指 12° / 8° / 10° / 16°（就是掌骨相对手腕连线的角度），指２ 0°，
    親指 0°。和上面那几个 MMD 模型一个范围。
  - 只有挂在手上的顶点动了（5190 个，指尖最多 5.5 cm）；别的顶点、表情、刚体都不变；手上的权重最多差 0.008（插件按
    位置切 指０ 的权重带出来的）。肘部工具匹配仍然逐点对上（最大 0.00003），肘部结果和不拉直时相同。
  - 手势舞：第 252 帧张开的手张开了（原来半握）；第 150 帧握拳圆了（原来手指压进手心）；第 295 帧的摇滚手势
    食指、小指伸直。手背的花饰和中指上的环跟着皮肤走（离皮肤的距离几乎不变）。
  - Fiona 默认装（板甲护手）：角度相同；只有手上的顶点动了（6002 个，最多 6.1 cm），甲片保持形状。
  - 拉直这一步本身不到 1 秒（18 个关节）。
  - 对比图在 `E:\game_export\Vindictus\_disperse\肘部检查\`：`PCF_005_手指拉直_静止.jpg`、`PCF_005_手指拉直_手势舞.jpg`、
    `PCF_005_手指拉直_握拳灰模.jpg`、`Fiona_手指拉直_静止.jpg`、`Fiona_手指拉直_手势舞.jpg`。
- 试验文件 `PCF_005_手臂修正.pmx`、`Fiona_手臂修正.pmx` 现在是「抬臂 + 手指拉直 + 肘部（权重平滑）」的版本。

#### 肩部：不做转换插件的腋窝平滑（`export_pmx.skip_armpit_smoothing`，导出默认做，2026-10-11，试验中）

用户问「对于这个姿势（抬到 40° 的静止姿势），肩膀是正确的么」。拿游戏自己的肩部矫正数据对照：姿势资源
`BaseBody_PCF/Poses/pcf_upperarm_l/r_pose`（12 个姿势）和 `pcf_clavicle_l/r_pose`（5 个），用和肘部同一条 CUE4Parse 命令
导出（`Poses/*`）。
- **静止姿势是对的**：游戏的上臂姿势里正好有一个上臂在水平线下 39.7°（前 2.1°）。抬到 40° 的 PMX 和游戏在这个
  角度的形状逐顶点比，左肩一带（3478 个顶点）最多差 0.45 cm、平均 0.05 cm；旧版 52.9° 用线性蒙皮抬过去是 0.76 /
  0.12 cm。法线也跟着手臂转了。
- **游戏怎么做的**：上臂也有一组矫正骨，`upperarm_correctiveRoot` 转上臂角度的一半（和肘部的一样），
  `upperarm_in / out / fwd / bck` 在上面平移（举到水平线上 55° 时 out 移 6.5 cm）；锁骨另有 `clavicle_out / scap / pec`、
  `spine_04_latissimus`。MMD 没有这种驱动。
- **插件的腋窝平滑让它离得更远**：Convert to MMD 5 补全骨骼时（`complete.py`）沿 肩 → 腕 把 肩 的权重再加一份给 腕
  （肩 不减），肩头、上胸、后背被手臂带着走一部分；游戏里这些地方只跟锁骨走。PCF_005 每边约 2400 个顶点的手臂占比
  平均多了 0.08（最多 0.28）。Fiona 默认装手抬平、举高时，腋下后侧的盔甲层因此被撕开一个洞（两层衣服原来的 肩 权重
  不同，加出来的 腕 权重也不同）。
- **做法**：`export_pmx.py` 转换时把插件的这一次调用（`split_chain_weights(肩, 腕, …, src_keep_floor=1.0)`）换成空操作，
  转换完换回，插件文件不改。插件以后改了、找不到这次调用时照旧做，日志和报告里写明。只对 UE 身体
  （`RIGS["ue"]["armpit_smoothing"] = False`），`--armpit-smoothing` 保留插件的做法；报告的 `armpit_smoothing` 写跳过了
  哪几边。
- **实测**（重新导出 → 布料碰撞 → `pmx_elbow.py`，和上一版试验文件比）：
  - 只有离肩关节 18 cm 以内的权重变了（PCF_005 4807 个顶点、Fiona 5317 个）；顶点位置、骨骼、刚体、关节、贴图都相同，
    表情偏移只差重新烘焙的 0.08 mm。
  - 左肩一带离游戏形状（游戏带矫正骨，PMX 线性蒙皮，都从 40° 出发），最多 / 平均，cm：

    | 姿势 | PCF_005 原来 | PCF_005 去掉 | Fiona 原来 | Fiona 去掉 |
    |---|---|---|---|---|
    | 静止 40° | 0.45 / 0.05 | 0.44 / 0.04 | 0.59 / 0.13 | 0.58 / 0.13 |
    | 手臂水平 | 2.55 / 0.44 | 1.99 / 0.20 | 2.78 / 0.90 | 2.37 / 0.53 |
    | 举高 55° | 5.15 / 0.92 | 4.16 / 0.39 | 5.60 / 1.81 | 4.16 / 1.01 |
    | 往前上方举 | 6.88 / 1.10 | 7.08 / 0.55 | 7.05 / 2.20 | 7.29 / 1.26 |
    | 放低到 64.5° | 1.25 / 0.20 | 0.46 / 0.04 | 1.28 / 0.34 | 0.46 / 0.11 |
    | 耸肩（锁骨抬 44°） | 3.00 / 0.58 | 3.12 / 0.62 | 2.98 / 0.63 | 3.15 / 0.75 |

    去掉以后和「游戏自己的权重、不带矫正骨」几乎一样。只有耸肩、肩往后这两个锁骨姿势稍差一点（原来多给 腕 的权重
    碰巧让肩头多跟了一点锁骨）。
  - 《最佳男主角》跳舞（Blender，自动挑手臂举得最高、放得最低的 8 帧）：PCF_005 肉眼差别很小；Fiona 肩甲、腋下和
    原来一样跟着走，没有新的问题。
- **还差的**：手举高、往前举时，三角肌和后腋窝离游戏还差 3–7 cm，那是游戏矫正骨的作用，要像肘部那样加辅助骨才能补
  （2026-10-17 用辅助骨补了大部分，见下一节「肩部辅助骨」）。
- 试验文件 `PCF_005_手臂修正_去腋窝平滑.pmx`、`Fiona_手臂修正_去腋窝平滑.pmx` 在各自 PMX 文件夹，贴图和存档的逐字节
  相同。对比图在 `E:\game_export\Vindictus\_disperse\肘部检查\`：
  - `PCF_005_肩部_静止姿势_和游戏对比.jpg`
  - `*_肩部_去掉腋窝平滑_游戏姿势.jpg`
  - `*_肩部_去掉腋窝平滑_最佳男主角.jpg`
  - `Fiona_肩部_腋下破洞_去掉腋窝平滑前后.jpg`

#### 肩部辅助骨：游戏的肩部矫正骨（`pmx_shoulder.py`，2026-10-17，试验中，还没批量）

接着上一节（去掉腋窝平滑以后，手往前举、举高时三角肌和后腋窝离游戏还差 3–7 cm），像肘部那样用辅助骨把游戏的矫正骨补上。
- **游戏怎么做的**：姿势资源 `pcf_upperarm_l/r_pose`（11 个手臂方向）驱动 `upperarm_correctiveRoot`（转上臂角度的一半）和
  挂在它上面的 `upperarm_out / fwd / bck / in`（往前上方举时 fwd 平移 16 cm，权重最多 0.39）；`pcf_clavicle_l/r_pose`（肩往前 /
  往后 / 往下 / 往上）驱动 `clavicle_out / scap / pec` 和 `spine_04_latissimus`（肩往后拉时肩胛那根移 12 cm）。导出时这些骨
  都并进了 腕 / 肩 / 上半身5。
- **做法**：每边 3 根隐藏辅助骨，挂在 肩C（腕 的父骨）下，用「回転付与」跟 腕 转一定比例：`左腕補1` 跟 63 %，支点在手臂轴线上
  往外 150 cm；`左腕補2` 跟 70 %，支点往身体里 60 cm；`左腕補3` 跟 30 %，支点往外 12 cm。远处两个支点方向相反，角度小时
  两边几乎抵消，角度大时叠起来，分到它们的肉就跟着手臂的摆动方向「滑」一段，和游戏的矫正骨推肉一样。肩关节 17.6 cm 以内、
  游戏挂在锁骨 / 上臂上的顶点（衣服层一起）重新分权重：身体那部分（跟胸口走的）不动，剩下的在 肩、腕（各自原来的
  腕捩1–3、肘部辅助骨比例保留）和辅助骨之间重新分，一共不超过 4 根骨；目标是游戏 15 个矫正姿势的形状，按舞蹈里常见的
  程度加权（手臂下垂往前 / 往后、往前伸最重），另外要求 腕 绕自身轴扭转时和原来一样。顶点位置不动。
- **为什么这样选**（PCF_005 上试过的）：
  - 支点放在手臂轴线上：腕 绕自身轴扭转时辅助骨和手臂转得一样，肩膀不会被甩开。支点不在轴线上贴游戏稍好，但扭 90° 时
    肩膀被甩出 2–3 cm。
  - 不加锁骨辅助骨（`--helpers` 里加 `clav:比例:偏移` 可以加）：最好的一根（跟 肩 59 %，支点在肩前 24 cm）能把「肩往后拉」
    从 4.0 cm 降到 1.9 cm（这几支舞最常见的肩部动作），但肩往前时会在肩胛骨上折出一道，所以默认不加。
  - 拟合前把肩部小于 2 % 的零碎权重去掉：肘部工具在上臂高处留了 0.00x 的 ひじ補1/2 权重，占了 4 根骨的名额，旁边顶点全挂
    辅助骨、它一根都挂不上，手举高时在后腋窝挤出一道折痕。
  - 身体骨里没有动作会单独转的（上半身4、上半身5 跟 上半身3，首1 跟 首，脸部的颈部骨）算一根；需要腾位置时并到其中权重最大
    的一根上，动起来完全一样。查过用户的 535 个 VMD：没有一个转 上半身4/5、首1；244 个给 上半身3 打了关键帧，全是 0°。
  - 权重往相邻顶点靠一点（`WEIGHT_SMOOTH = 1`，区域外的邻居按原来的权重算，区域边上不断开）。在游戏姿势上比较「折痕」
    （摆好姿势后每个顶点相对邻居的局部弯曲，和游戏比），往前上方举 / 举高 55° / 往前平举最多 1.28 / 1.52 / 1.03 cm，
    不加辅助骨是 1.79 / 1.54 / 1.43；强度 3、10 都更差。在区域边上把权重硬拉回原样会把修正丢掉（游戏最大的位移有三分之一
    就在边上 4 cm 以内）。
- **Blender 和 MMD**：比例不是 1 的付与，mmd_tools 是把欧拉角按比例缩放，MMD 是四元数插值。游戏的这些姿势上两边差不到
  0.1 cm；《最佳男主角》244 个关键帧最多差 1.2 cm（手臂举到 110° 又带扭转的那几帧）、平均 0.004 cm（Fiona 0.013 cm）。Blender 里实际导入
  转动，和工具按 mmd_tools 方式算的结果一致到 0.0001 cm。
- **实测**（左肩一带，离游戏的形状，最多 / 平均 cm）：

  | 姿势 | PCF_005 现在 | PCF_005 辅助骨 | Fiona 现在 | Fiona 辅助骨 |
  |---|---|---|---|---|
  | 手臂水平 | 1.99 / 0.20 | 1.80 / 0.14 | 2.37 / 0.53 | 1.80 / 0.36 |
  | 举高 55° | 4.16 / 0.39 | 3.09 / 0.22 | 4.16 / 1.01 | 3.09 / 0.57 |
  | 往前上方举 | 7.08 / 0.55 | 2.68 / 0.22 | 7.29 / 1.26 | 2.91 / 0.53 |
  | 往前平举 | 5.80 / 0.46 | 2.38 / 0.19 | 5.92 / 1.03 | 2.53 / 0.43 |
  | 下垂往前（舞蹈最常见） | 1.85 / 0.12 | 1.36 / 0.11 | 1.87 / 0.31 | 1.54 / 0.22 |
  | 往后摆 | 1.87 / 0.15 | 1.88 / 0.16 | 1.93 / 0.40 | 2.00 / 0.37 |
  | 肩往后拉 | 3.97 / 0.23 | 3.98 / 0.26 | 4.00 / 0.50 | 4.00 / 0.54 |

  手臂放低的几个姿势和原来差不到 0.25 cm；腕 自转 90° 和原来差 2.0 cm（Fiona 2.6 cm），舞蹈里 腕 本身的扭转多在 30° 以内。
  超出游戏数据的姿势（手举过头、往前 150°）变形量随角度平滑增大（举到竖直 5 cm、170° 8 cm），不会失控。
  《最佳男主角》举得最高的几帧，后腋窝的折痕不比原来深（PCF_005 左肩局部弯曲最多 1.77 cm，原来 2.00；右肩 1.67，原来
  1.81）；Fiona 有盔甲，几帧里有几个顶点多弯 1 cm（原来就有 2.9 cm 的弯），渲染图上看不出新的折痕。
- **还差的**：举高时游戏后腋窝那个圆的大褶做不出来；肩往后拉、往上耸没改（锁骨辅助骨的取舍见上）；Fiona 的肩甲在游戏里
  会跟着矫正骨转到更外、更高，辅助骨只追回一部分。
- **用法**（普通 Python，在 `pmx_elbow.py` 之后跑，约 20 秒）：`python .\pmx_shoulder.py <原.pmx> <新.pmx> --xps <导出这个 PMX
  用的 XPS>`，`--report r.json` 存数据，`--helpers` 换辅助骨，`--weight-smooth` 改平滑。新文件写在原文件旁边；注释里加一行
  标记，做过的会拒绝再做。游戏数据和肘部的放在一起（`E:\game_export\Vindictus\_meta\elbow`，同一条 CUE4Parse 命令导出，
  多取 `pcf_upperarm_l/r_pose.json`、`pcf_clavicle_l/r_pose.json`）。
- 试验文件 `PCF_005_手臂修正_肩部辅助骨.pmx`、`Fiona_手臂修正_肩部辅助骨.pmx` 在各自 PMX 文件夹（= `*_手臂修正_去腋窝平滑.pmx`
  再加肩部辅助骨），对比图在 `E:\game_export\Vindictus\_disperse\肘部检查\`：
  - `*_肩部辅助骨_游戏姿势_手臂.jpg`、`*_肩部辅助骨_游戏姿势_常用和锁骨.jpg`
  - `*_肩部辅助骨_最佳男主角.jpg`

#### 贴图扩边：UV 接缝上的暗线（`pad_textures.py`，2026-10-05）

现象：抬手时，从肩膀到腋下有一条锯齿状的细暗线。PCF_005 举手时、盔甲 Fiona 露出腋下时都有，Blender 和 MMD 里都会出现。

原因：烘焙出来的颜色贴图（`*_baked.png`）在每个 UV 岛的边上，直接从皮肤色跳到透明黑 `(0,0,0,0)`，一个像素都没往外扩。
Blender2XPS 烘焙时设了 8 像素的 margin，但那一圈的透明度是 0，存出来就是黑的。贴图采样是在像素之间插值的，离得越远用的
mipmap 越小，岛外的透明黑就会沿着每条 UV 接缝混进来。UE 身体的 `MI_PCF_Upper01` 里，手臂岛的边正好绕肩一圈。
跟权重无关：接缝两边被拆开的顶点权重完全相同（`chunk_seam` / `split_seam` 查过）。

做法（导出时默认做，`--no-pad` 不做）：
- **判断透明度**：按 PMX 里用到这张贴图的三角形，画出它的 UV 覆盖范围。
  - 范围内（往里缩 2 像素）全都不透明的，算不透明贴图（皮肤、脸、布料），整张透明度改成 255。
  - 范围内有镂空的（头发、睫毛、眉毛、蕾丝），透明度不动。
- **填颜色**：有颜色（透明度 > 0）的像素一个都不改，其余的用金字塔填色，每一层先往外长 2 圈再缩小。这样紧挨着岛边的像素
  拿到的是这个岛自己的颜色。如果只按 2×2 对齐分块，紧挨着岛的像素会拿到远处小岛的平均色：PCF_005 躯干岛下面一开始就成了
  暗棕色。
- **写文件**：一张 4K 贴图大约 4–8 秒。只有像素真的变了才重写，先写临时文件再替换，文件名大小写保持不变。

已经导出的 PMX 可以单独做，用普通 Python：

```powershell
python .\pad_textures.py <id>.pmx --mirror <XPS 文件夹>   # --mirror：同名且逐字节相同的副本一起换；--dry-run 只统计
```

2026-10-05 已对存档的 16 套 PMX 和 XPS 里相同的副本做过。换装视频里 PCF_005 举手那几帧（第 211 帧）修前修后对比过：
肩上的线没了。同一批视频是在 Blender 里渲的，当时没绑 SDEF，肘部也折；绑上以后变圆了（见上面「手臂权重」第 3 条）。

#### 材质高光：皮肤、布料哑光，金属发亮（`pmx_materials.py`，2026-10-05）

Convert to MMD 5 给每个材质都是高光 (1, 1, 1)、光泽度 11.9，皮肤、布料、金属、头发一样亮。在 MMD 里是一大片白色高光；
Blender 的 mmd_tools 拿高光颜色当 2% 光泽反射的颜色，粗糙度 = 1 / 光泽度 = 0.08，接近镜面，皮肤像抹了油。

按每个材质烘焙前的游戏材质分类（build_blend 的 `build.log` 报告里有材质类型和贴图）。衣服材质再看 ARM / ORM 贴图的
金属度（B 通道），只统计这个材质自己的 UV 范围内金属像素占多少：

| 类别 | 怎么认 | 高光 | 光泽度 |
|---|---|---|---|
| 皮肤 | 游戏材质类型 skin（身体、脸、手） | 0.15 | 4 |
| 布料 | 衣服材质，金属占比 < 0.2，或没有金属度贴图 | 0.15 | 4 |
| 混合 | 金属占比 0.2–0.5（带金边的蕾丝、鞋） | 0.5 | 8 |
| 金属 | 金属占比 ≥ 0.5（盔甲、头饰） | 不动（1.0） | 不动（11.9） |
| 其他 | 眼睛、头发、眉毛睫毛、牙齿 | 不动 | 不动 |

- 皮肤的数值是渲染对比后用户选的（原样 / 0.35·6 / 0.15·4 三档）。
- export_pmx 把两个网格共用的材质拆成 `<名字>_<部件>` 两份，分类时去掉后缀再找游戏材质。
- Fiona_BaseBody 是另一套构建，没有报告，按贴图名认皮肤。

已经导出的 PMX 单独改（普通 Python，只改这两个字段，加一行注释）：

```powershell
python .\pmx_materials.py <id>.pmx --blend-dir <build_blend 的 <id> 文件夹> [--dry-run]
```

2026-10-05 已对存档的 16 套主 PMX 做过（不含 PCF_005 那几个试验文件）。

#### 头发和布料碰到身体（`../mmd_physics/cloth_collision_pmx.py`，2026-10-06）

问题：在 MMD 里头发、围巾、披风和裙子会穿进身体，因为它们的刚体根本不和身体碰撞。

原因：Convert_to_MMD5 和 mmd_cloth_physics 量身体碰撞体时，统计的是权重在这根骨上的所有顶点。穿着盔甲导出，盔甲也算进去了，
所以上臂的胶囊有手臂两倍粗，大腿是 1.6 倍。布料和头发的刚体一开始就在碰撞体里面，mmd_cloth_physics 就把它们放进“贴身”组 10。
这个组的掩码不含身体所在的组 0，身体碰撞体的掩码也排除了组 10，两边永远碰不到。存档的套装里，85–99 % 的动态刚体在组 10。

修法用的是另一个窗口写的工具（这里只调用）。`Fiona_full` 是同一副骨架，裸身，碰撞体按皮肤量过；把它的碰撞体按骨骼复制过来。
然后每个动态刚体（胸部除外）按碰撞体类别（头、脖子、躯干、手臂、腿）分组。开始就在某类碰撞体里的刚体先变细（盒子缩一个轴，
胶囊缩半径，最多缩到 35 %），还不够才不和那一类碰。刚体只追加，原有的不删不改，关节不动。

```bash
# 套装（UE 骨架）：碰撞体取自 Fiona_full
python scripts/mmd_physics/cloth_collision_pmx.py <id>.pmx <新>.pmx \
    --colliders-from "E:\game_export\Vindictus\_爆衣插件\Fiona_full\Fiona_full.pmx"
# Fiona_BaseBody 是旧的 Bip001 骨架，按自己的裸身量
python scripts/mmd_physics/cloth_collision_pmx.py Fiona_BaseBody.pmx <新>.pmx --skin \
    "4_BaseBody-MI-pc-female-body05_0.1_0_0,4_BaseBody-MI-pc-female-handfoot05_0.1_0_0,4_Face-MI-Fiona-Face01_0.1_0_0"
```

- 输出文件要和原 PMX 放在同一个文件夹。mmd_tools 的 pmx 模块保存时会按输出位置重写贴图的相对路径，放到别处贴图就断了。
- PCF_008 胸前的衬衫布片叫 `Outfit008_upper_breast_shirt_*`。当时工具默认的胸部正则会把这 16 个刚体当成胸部跳过，
  存档这套是加 `--bust "^breast_physics|bust|胸|乳|oppai"` 修的。工具 10-06 晚上起改了默认正则，“breast”只认名字开头
  或第一个词后面的，这种名字不会再被当成胸，不加参数也一样。
- PCF_010 只有两个胸部刚体是动态的，不用修。

2026-10-06 已对存档的 15 套做过，PCF_010 跳过。原文件备份在 `E:\game_export\Vindictus\_meta\backup_碰撞修复前_20261006\`，
里面还有每套的工具日志和 md5 清单 `manifest.json`。效果怎么量：`scripts/mmd_physics/clip_test_blender.py`，
用 MMD 式的物理播手势舞，统计每帧有多少物理顶点在身体里 5 mm 以上。修前修后都用修好的 PMX 的碰撞体当“身体”，
同一把尺子量。PCF_067：每帧 51.6 → 12.9 个，最深 7.4 → 2.8 cm；PCF_009：10.0 → 0.9 个，4.8 → 2.9 cm。

### 用游戏关卡做背景（北方遗迹，`levels/`）

关卡 `S1_Northruin_01` 按关卡数据还原成 Blender 场景，包括地形、岩石、遗迹、树、草和游戏自己的天空，再裁成渲染视频用的轻量版。
变身视频的北方遗迹背景就是这个场景。步骤、命令、原理和坑见 [`levels/README.md`](levels/README.md)。

### 用 iPhone Face Cap 驱动表情（Faceit）

`python .\extract_face_data.py --face Fiona` 把脸的 DNA 和原始网格包取到 `E:\game_export\Vindictus\_meta\face\`，
然后在 Blender 里用 `scripts\blender_addons\faceit_arkit` 插件：补全蒙皮权重 → 生成 52 个 ARKit 形态键 → 注册到 Faceit。
步骤见 [`docs/faceit-arkit-guide.md`](../../docs/faceit-arkit-guide.md)。

注意：UE Viewer 导出的脸每顶点只留 **4** 个骨骼权重，游戏里最多 **12** 个；插件的「恢复完整权重」
（`faceit_arkit/ue_weights.py`）能补回来。`export_pmx.py` 2026-10-04 起默认做顶点表情，烘焙时同样先补回完整权重；
`--morphs bone` 的骨骼表情建在截断的权重上，张嘴、单侧微笑、鼓腮时脸颊会起包。

`.dna` 是什么、里面各段存了什么、RigLogic 每帧怎么由它算出表情（PMX 表情和 Faceit 插件共用这套原理），
见 [`docs/metahuman-dna.md`](../../docs/metahuman-dna.md)。

## 已验证环境

```text
客户端：E:\tools\vindictus（Vindictus.exe 为游戏根；Paks 在 Vindictus\Content\Paks，ucas 15.04 GB）
UE Viewer：spiritovod 的 UE5 specific build，umodel_materials_ue5.exe（build 1579 based fix282，2026-09-05，自带 Oodle）
            E:\tools\umodel_specific\materials\umodel_materials_ue5.exe
Blender：3.6.15 + io_scene_psk_psa 5.0.6（PSK/PSKX 导入器）
Python：3.13 + cryptography（解 utoc 目录索引用）
输出：D:\vindictus_exports
```

## AES key（不在仓库里）

pak/utoc 的索引用主 key（GUID 全 0）加密。key **只放本地**，脚本按下面顺序取：

1. 环境变量 `VINDICTUS_AES_KEY`（`0x` + 64 位十六进制）；
2. `-AesKeyFile`（默认 `E:\tools\vindictus\_download\aes_key.txt`，一行）。

`export_model.ps1` 把 key 写进临时文件再以 `-aes=@file` 交给 UE Viewer，命令行里不出现 key。
仓库、CHANGELOG、画廊页面里都不能出现 key（和 FF7 Remake 的规矩一样）。

key 不是明文躺在 exe 里的：`Vindictus.exe` 用 8 条 `mov dword [..], imm32` 指令把 32 字节拼出来
（`.text` 文件偏移 `0x47745EB`），所以「找连续 32 字节」的扫描器找不到。`find_aes_key.py` 按指令
模式（imm64×4 / imm32×8 / imm8×32 / 成对 xmm 常量）重组候选，再拿 `Vindictus-Windows.pak`
的加密索引试解密，解出 `../../../` 挂载点即命中（先扫一遍连续窗口再扫指令模式，共约 80 秒）：

```powershell
python find_aes_key.py            # 默认扫 E:\tools\vindictus 的 exe + pak，命中后写 aes_key.txt 到 --out
python find_aes_key.py --exe <Game>.exe --pak <any>.pak --out D:\keys\game_aes.txt
```

## 三个脚本

### `export_model.ps1`（一键：UE Viewer → Blender）

```powershell
.\export_model.ps1 -List                 # 模型清单 + 导出状态（= list_models.py）
.\export_model.ps1 Fiona                 # 女主：脸 + 发 + Shiningwill 全套（Upper/Lower/Hand/Foot）
.\export_model.ps1 Lethita               # 男主：脸 + 发 + 盔甲（含 Head）
.\export_model.ps1 PCF_067 -Force        # 女服装 067 + Fiona 脸/发，重建
.\export_model.ps1 Gnoll_type3_Tribe_Boss_01 -NoPreview
```

步骤：

1. `list_models.py --resolve <id> --json` 解析出该模型的骨骼网格包（Content 相对路径，
   UE Viewer 接受 `VindictusRoot/Character/.../SK_xxx` 这种写法，避免 178 个重名 stem 的歧义）；
2. 对缺失的包逐个执行 `umodel -game=ue5.3 -path=<Paks> -aes=@tmp -export -png -out=<ExportRoot>\umodel_exports <package>`
   → PSK/PSKX + PNG 贴图 + `.mat`/`.props.txt`（材质实例的贴图、向量、标量参数）；
3. 写 `<ExportRoot>\blend\<id>\spec.json`，无头跑 `build_blend.py`；解析 `VINDICTUS_REPORT=` 行打印
   骨骼数、各部件顶点数、材质/贴图数、未解析贴图、警告。

参数：`-GameRoot`、`-ExportRoot`、`-UmodelExe`、`-BlenderExe`、`-AesKeyFile`、`-PythonExe`、
`-IncludeWeapons`（把武器也并进来）、`-Force`（重导 + 重建）、`-NoBlend`、`-NoPreview`、
`-Smooth`（丢掉 PSK 自带的拆分法线改平滑着色）。输出已存在且未 `-Force` 时跳过。

### `list_models.py`（清单）

直接解密并解析 Paks 下每个 `.utoc` 的 IoStore 目录索引（TOC v5：ChunkIds → OffsetLengths →
PerfectHashSeeds → ChunksWithoutPerfectHash → CompressionBlocks → 方法名 → 签名块 → 目录索引），
不需要 UE Viewer 在场。索引只有路径没有类型，所以「部件」= `Model/` 目录下名为 `SK_*` 且不是
`_Skeleton/_Physics/_PhysicsAsset` 的资源。按游戏的拼装方式分组：

| kind | 目录 | 组成 |
| --- | --- | --- |
| player | `Character/Player/<Name>/` | `Face/Model/SK_<Name>_Face01` + `SK_<Name>_Hair01` + `Armor/Model/SK_<Name>_*_master` |
| outfit | `Character/Outfit/PC{F,M}_Outfit/<Id>/Model/` | 服装部件 + 对应身体的脸/发（PCF→Fiona，PCM→Lethita；由 UE Viewer 加载的骨架 `SK_PCF/PCM_BaseBody01_Skeleton` 核实）；`Player/Outfit/<Name>/Mesh/` 下的旧版整套记作 `<Name>_legacy` |
| base | `BaseBody_PCM` 四件 / Fiona `SK_female_base` | 裸体基础身体 + 脸/发 |
| monster | `Character/AI/<Race>/<Type>/<Variant>/Model/` | 目录下全部 SK（武器标为 weapon） |
| npc | `Character/Npc/**` | 单个 SK |

```powershell
python list_models.py                         # 表：id / kind / body / 部件数 / umodel 已导 / blend 已建
python list_models.py --json --kind outfit
python list_models.py --resolve PCF_067 --json
python list_models.py --raw --path-filter /Character/AI/   # 原始路径
```

武器（`Weapon/` 下的 SK）默认放在 `extras`，`--include-weapons` 才并入部件。

### `build_blend.py`（Blender 3.6 无头组装）

```powershell
blender --background --factory-startup --python build_blend.py -- --spec spec.json [--no-preview] [--smooth]
```

1. 逐个导入 PSK（`io_scene_psk_psa`，材质按 PSK 的 MATT 槽命名，同名复用）；
2. **合并骨架**：UE Viewer 给每个网格导的是它自己的参考骨架子集（Fiona 脸 658 根、头发 274、
   上身 531、脚 30……），取最多的一副为底，其余按名字补缺（父子关系照抄，位置取该部件网格所在的
   位置：部件重摆过的取重摆后的姿势，见「已知限制」），所有网格重新绑定到这一副——Fiona 合成 1415 根
   一副可摆姿势的骨架，共享骨骼 rest 位置偏差 0；
3. **材质**从 `.mat`（Diffuse/Normal/Opacity/Other[n]）和 `.props.txt`（贴图参数名、向量、标量、Parent）重建：

| 母材质 | 处理 |
| --- | --- |
| `M_PC_Outfit` 服装 / 怪物 | `_D` 基色（有 Opacity 时 alpha 作 UE Masked 裁切，阈值 1/3）、`_N` 法线（翻 G 通道）、`_ORM`/`_ARM`：G 粗糙度、B 金属度 |
| `M_PC_Skin_Body` / `M_PC_Skin_Head` 皮肤 | `_D` × `Basecolor Tint`、`_N`（强度 0.6）、少量次表面；`_Mask` 未用 |
| `M_PC_Hair` 头发卡片 | `ODI` 的 R 作 alpha（HASHED），`FR` 的 B（发根→发梢）驱动 ColorRamp，颜色取实例的 `Color Root/Mid/Tip` |
| `M_PC_Skin_Eyebrow` 眉毛/睫毛 | `T_Eyebrow01_ODI` 的 R 作 alpha，深色 |
| `M_PC_Skin_EyeRefractive_Old`（Fiona）/ `M_PC_Skin_Eye`（Lethita）眼球 | `build_eye()`：巩膜贴图 × 血丝贴图（0.4）；虹膜是**程序化**的——以 UV 中心半径 0.2 为虹膜盘（MetaHuman 惯例），两种虹膜色沿半径渐变（Fiona：实例的 `IrisColor1/2 U,V` 在 `T_PC_Iris_color_picker` 上采样，**采样值是 sRGB 编码要先转线性**，再乘 `IrisBrightness`×1.35；Lethita：`Iris Color Inner/Outer` 向量），× 虹膜贴图 G 通道的纤维结构（`T_Iris_A_M` B 通道是径向渐变、G 是纤维；`T_EyeMap01` R 渐变、G 纤维），外缘 limbus 变暗（`LimbusDarkAmount`+0.1），瞳孔按半径 0.32×`PupilScale` 抠黑；粗糙度 0.12、高光 0.5、`T_PC_Eye_N` 法线 0.4 |
| 眼部遮蔽壳 / 泪线 / 假反射片 | 半透明黑 0.12（无高光）/ 透明高光 / 贴图 alpha × 0.4 |
| `M_Outfit`（`Character/public/`，NPC 套装，`PCM_00x_Temp` 男装复用）**分层材质** | 没有基色贴图：`Sub Mat Map` 的 R 选子材质 A（黑）/B（白）、G 选 C，每个子材质是一个纯色 `A/B/C L1 Color`；`GDO Map` 的 R 是灰度细节（0.5 为中性，×2 乘上去）、B 是不透明度（CLIP）；有 `Layer Color Map` 时直接当基色；`ARM Map`、`Normal Map` 同普通 PBR。`T_White_MK` 当 Sub Mat Map 表示整件都是 B |
| `M_Mob_Base` / `M_Mob_Outfit` / `M_NPC_Outfit`（怪物、NPC） | 参数名 `BaseColor / Opacity`、`ARM / E`、`Normal Map`；基色乘 `Basecolor Brightness`（怪物 D 图故意做得很暗，2–3.5 倍是常态）并按 `Basecolor Saturation` 去饱和、再乘 `Basecolor Tint`；粗糙度通道重映射到 `[Roughness Min, Roughness Max]`，金属度乘 `Metallic Intensity`。`Basecolor Contrast`、`Emissive` 没有用 |
| `M_Mob_Skin_Body_Old`（狗头人皮肤） | 走皮肤分支（母板名含 skin）：`BaseColor` × 亮度，`Mask`（DRCS）未用 |
| `MA_HairStyle` 怪物毛发卡片 | `Alpha`（`Fur_A`）R 作 alpha（HASHED），`Root`（`Fur_root`，发根处白）反相驱动 `RootColor → TipColor` 渐变，颜色乘 `Brightness` 但把最大通道压到 0.8 以内（Carminegust 红毛 ×3 会成粉色）；`Fur_Depth/Direction/ID/Gradient`、`DyeColor` 没有用 |
| `M_EyeRefractive`（怪物眼球） | 与 Fiona 的 MetaHuman 眼一样的参数集，直接走 `build_eye()`（`IrisColor1/2 U,V` 在 `T_PC_Iris_color_picker` 采样）；`M_EyeOcclusion` 走遮蔽壳 |

4. 用到的贴图复制到 `textures\`，`.blend` 存相对路径（整个 `<ExportRoot>\blend\<id>\` 目录可单独拷走）；
5. 渲 `preview.png`（全身 900×1400）与 `preview_face.png`（头骨 `head` 取景）。相机方向不是写死的
   +X：UE 骨骼网格资源朝 -Y，脚本用 `foot_l/r → ball_l/r` 的方向判断角色朝向再放相机。
6. 只有一根骨的部件不蒙皮，挂到插槽骨上：那根骨在底骨架里存在就挂那根（豺狼人的锤子
   `Anim_Attachment_RH` → 右手，带骨的完整 rest 变换）；只有 `root` 的（Lethita 头发）挂到 `head`（只平移）。

## 输出

```text
D:\vindictus_exports\umodel_exports\VindictusRoot\...   UE Viewer 原始导出（按游戏目录结构）
D:\vindictus_exports\blend\<id>\<id>.blend               一副骨架 + 全部部件 + 材质
D:\vindictus_exports\blend\<id>\textures\                贴图（PNG）
D:\vindictus_exports\blend\<id>\preview.png / preview_face.png / spec.json / build.log
D:\vindictus_exports\vindictus_models_manifest.json      画廊 manifest；_gallery\thumbs\ 缩略图
```

## 画廊（`html/`）

```powershell
cd html
python .\collect_manifest.py     # 读 blend\*\build.log 的 VINDICTUS_REPORT -> manifest（只有路径和统计）
python .\make_gallery.py         # 缩略图写到导出根下，页面 -> html\index.html（自包含，file:// 链接）
```

和其它游戏的画廊同一套：卡片 = 预览 + 说明 + 部件 + 规格（顶点/面/骨骼/材质/贴图/体积）+ blend 路径
+ 脸部预览；徽章标出类型、身体、隐藏的头发、重定位过的部件数、告警；顶部可按类型/身体筛选、搜索。
页面底部是完整的手工导出教程（客户端来源、key 计算、三个脚本、批量、参数表、产物目录、坑）。
`NAMES` 表里的中文说明是看着预览写的——Pre-Alpha 资源没有正式服装名。

## 已知限制

- 静态网格贴图是 virtual texture，UE Viewer 导不出（角色不受影响）；Nanite 只有基础几何；
  umodel 不导 morph target（脸包里的 MetaHuman `DNAAsset` 也不导），面部没有形态键。
  表情可以从 DNA 算出来做成 PMX 表情（默认顶点表情，也可以出骨骼表情），见上面「导出 PMX」。
- 服装的 `Head` 部件五花八门：项链/颈圈（001、007、009）、耳机（002、004）、帽子（003、012）、发带（006）、
  发冠 + 头皮片（005，头发照常显示）、自带发型（001_Temp、008、010 里打包了 Fiona 的头发）、全盔（067、Lethita）。
  规则：Head 部件里有头发材质，或 `list_models.py` 的 `HEAD_REPLACES_HAIR`（067）标了的，才隐藏默认
  头发（仍留在文件里，`<id>_Hair`）；其余保留。几何启发式（贴头皮比例、盖脸比例）试过，分不开耳机/帽子和发型。
- 部分服装的部件绑在**另一版骨架**上（Head 的脊柱链到 head 差 6.9 cm，Shiningwill 旧版差 6 cm）：
  `build_blend.py` 先把该部件自己的骨架摆到底骨架的 rest 姿势再烘焙网格（等价于游戏运行时的蒙皮），
  报告里记为 `reposed_parts`。
  - 旧版骨架的骨盆和 MetaHuman 脸骨架的骨盆位置相同、朝向差 7.6°。底骨架（脸）没有腿，腿骨由第一个带腿的
    部件（鞋 `Foot`）补进来。10-03 以前补骨是相对底骨架里的父骨摆的，旧版服装的整条腿就跟着骨盆向前甩了
    7.6°（脚尖处 13 cm）；鞋部件只和底骨架共享 root / pelvis，偏差不到重摆的门槛，网格留在原处。结果鞋和袜子
    落在脚后 13 cm，膝盖一弯就和小腿分开（PCF_002、003、004、006、007、008、009、010、012；新版骨架的默认装、
    PCF_001、001_Temp、005、067 和 Biped 的 Shiningwill_legacy 没有这个问题）。现在补进来的骨放在部件自己网格
    所在的位置：腿保持原样竖直，后面重摆的身体部件找到的腿也就在它们自己的位置上，只有臀部跟着转过的骨盆走。
  - 检查：`checks\part_alignment.py <id> ...`：每个部件里主要蒙皮在脚 / 手 / 头骨上的顶点，在骨的局部坐标里和
    它自己的 PSK 比，差 1 cm 以上的标出来。
- `Shiningwill_legacy` 整套和 Fiona 素体是 3ds Max Biped 骨架（`Root → Bip001_*`）。合并进 Fiona 的脸骨架
  （UE 命名，没有 Bip 骨）后它成了第二棵根子树，而且朝向和 UE 骨架差 90°（面朝 +X），直接合并会身体
  侧着、脸朝前。`align_secondary_hierarchies()` 把第二棵根子树连同绑在上面的网格按脚趾方向转到 UE
  朝向、再按 `Bip001_Head`→`head` 平移对齐（报告 `aligned_hierarchies`，日志里打印转正后的朝向）；旧装
  自带的旧发型是给旧头做的，会盖住新脸的眼睛，所以隐藏旧发型、保留默认头发。
- `SK_Fiona_Lower01_master` 里有一个 `PCF_005_Onepiece` 材质段，是 master 网格自带的，渲染上被裙甲盖住。
- 基础身体：`Fiona_BaseBody` 用的是 `Player/Fiona/Model/Mesh/SM_pc_fiona_basebody`（名字带 SM_ 其实是
  SkeletalMesh；旁边的 `SK_female_base` 反而是 Skeleton 资源，导不出网格）。它是旧版素体（白 T 恤 + 短裤，
  Biped 骨架，自带一个没贴图的旧头），脚本按上面的对齐规则转正后，把旧头/脖子（`Bip001_Head/Neck`
  权重的 5.8 万顶点）切掉换成现在的脸。`PCM_BaseBody` 是新骨架的四件，直接能用。
- 素体换脸后的脖子接缝（2026-09-26 修，改了好几轮）：原来的毛病——① 新脸（MetaHuman 式的头）自带一圈颈部 / 锁骨
  “围兜”，前面浮在旧身体外面 1 cm 左右（穿着 T 恤时胸口透出一块方形肤色），后背那片沉在旧身体里面 1 cm 左右；
  ② 按主权重删旧脖子时，T 恤（材质 `inner`）领口的 6 个顶点也被当成脖子删了；③ 旧身体残留的脖子皮和 100 个旧脸
  材质的碎面插在新脖子里；T 恤领口是照旧脖子做的，比新脖子宽。**这个素体要能脱掉 T 恤当裸体用**，身体本身必须是
  完整的一层皮，不能靠衣服遮。现在 `cut_legacy_head()` 不碰 `inner` 的顶点，然后 `fix_basebody_neck.py`：
  - `fit_face_to_body()`：围兜按“身体骨骼权重占比” w（spine / clavicle / upperarm）贴到旧身体表面上——w 从 0.05
    到 0.95 平滑过渡，过渡带里的位移量再在网格上平滑（旧身体的脖子根比新脖子粗，带子窄了会折出一道棱）；围兜外沿
    一圈压进旧皮下面 0.05 cm，由旧皮盖住边；挪过的顶点重写自定义法线（贴好的地方直接用旧身体在那一点的法线）；
    被围兜盖住的旧身体面和旧脸碎面删掉，删面前后旧身体的自定义法线原样写回。
  - `match_bib_tone()`（材质建好以后）：逐顶点把围兜的肤色往旧身体对应位置的肤色上靠——两张贴图各自模糊后取比值，
    在网格上平滑，写进顶点颜色 `bib_tone`，脸皮肤材质的 Base Color 后面串一个 Mix MULTIPLY；只动色调，细节不变。
  - 摆姿势（导 XPS 以后才看出来）：贴好的围兜改用旧身体在同一点的骨骼权重（Biped 骨），过渡带按 t 混合，领口边上
    离 T 恤近的也用身体权重；T 恤在盖住围兜的地方往外放到至少 4 mm。不这么做，抬手、弯腰、转头时左肩领口的皮会从
    T 恤里穿出来（围兜按脸的 UE 骨动、T 恤按 Biped 骨动；XPS 每顶点只存 4 个权重也会让围兜多偏 2 mm 左右）。
    检查方法：同一个姿势下从 T 恤外面往里打射线，看先碰到衣服还是皮肤。
  试错过程：第一轮按领口高度切掉整片围兜（领口比新脖子宽，两侧露出深色的旧皮，用户：“脖子还是不对”）；第二轮按
  遮挡删（穿着 T 恤没问题，脱掉以后锁骨和后背一圈缺皮，用户：“把白衣服去掉，只看身体，脖子缺了一部分”）；第三轮
  按 w 线性贴、没重写法线、肤色用全局一个比值（后背凹一块、围兜下沿一道弧）；围兜外沿浮在旧皮上面的那版从侧面
  贴着肩膀看有一道细黑线（视线从缝里看到了围兜的背面）。自定义法线是相对周围面存的：挪顶点、删相邻的面都会让它
  变，得自己算好写回。每一轮都在藏掉 T 恤和穿着两种状态下，用正 / 3/4 / 侧 / 后 / 俯视的材质效果、白模、按材质
  上色的近景核对。已经构建好的 .blend 也可以直接修（参数见脚本开头）：
  `blender -b <in.blend> --factory-startup --python fix_basebody_neck.py -- --out <out.blend>`。
- 材质参数名匹配用整词：`"rma"` 曾经作为子串匹配到 `Normal Map`，把法线贴图当 ORM 接了进去
  （B 通道≈1 → 金属度 1），没有 ARM 参数的服装（PCF_012、旧版 Shiningwill 上衣、素体）全成了金属；
  `find_role(..., whole_words=True)` 修掉。
- 睫毛（`MI_Fona_Face01_EyeLash`，父材质 `M_EyeLash_HigherLODs_Inst`）也有 `ODI Map` 参数，以前先命中了“有 ODI 就是头发”
  那条规则：接上头发的发根→发梢渐变，却没有 FR 贴图驱动，一直取中间的浅棕色，所有用 Fiona 脸的模型睫毛都发白。
  2026-09-26 起眉毛 / 睫毛的判断放在头发前面，Base Color 用材质实例的 `Color`（睫毛 0.0039，接近黑）。
  判断材质类型的规则有先后，特征重叠的（都有 ODI）要把更具体的放前面。
- `T_pc_fiona_basebody_01_D`（`M_female_skin_body_01` 的基色）是 virtual texture 导不出，这类皮肤材质用纯肤色代替；
  BC6H 贴图 UE Viewer 写成 `.hdr`（PCF_012 的 `_B` 基色），已按 `.hdr` 索引。
- 眼球是近似：没有折射（游戏用角膜折射 + 视差），虹膜半径 0.2 是按这批头的眼裂宽度定的
  （0.17 偏小、0.22 偏大），`IrisSaturation`（0.21）没有采用——按它做会灰掉；皮肤 `_Mask`、
  头发 `Specular Highlight Randomness` 等参数没有用上。
- 怪物/NPC 的材质母板（`M_Mob_*`、`M_NPC_Outfit`、`MA_HairStyle`、`M_EyeRefractive`、分层 `M_Outfit`）按上表
  近似，都是看参数名和贴图通道猜的，没有 UE 里的对照：毛发的 `Brightness` 语义不确定（"orange" 毛是 0.15、
  "black" 毛的发根色反而是浅的），Carminegust 的红毛偏粉。两只哥布林（`Goblin_Type2_FieldBoss02` 和
  `Goblin_type3_NamedBoss01` 是同一个 25 万顶点的网格）和 NPC `Male_Knight` 在包里**没有任何材质**，
  导出来是白模——不是导出问题，查过：`umodel -dump` 里两个 section 都是 `Material=None`，SK 包只
  import 骨架、PhysicsAsset 和 AnimBP（`umodel -save` 抠出原始包、扫 imported package names），角色蓝图
  `BP_Goblin_Type3_NamedBoss_01` 只引用 VFX、DataAsset、AIC、SK 和**豺狼人的** `ABP_Gnoll`，武器蓝图借的是
  `AS_Gnoll_Type1_NamedBoss01_weapon`，整个容器 `Character/AI/Goblin/` 下 180 条里没有一个 M_/MI_/T_，
  顶点色也全白——这版客户端里哥布林就是个占位高模。`NPCM_RoyalArmy_sword` 只有一把剑。多骨的武器
  （`Gnoll_Type2_Named_Boss_03` 的弓，16 根自己的骨）合并后留在原点。

## 已验证

- `Fiona`：6 部件 103,180 顶点，骨架 1415 根（合并 757），19 材质 41 贴图，0 未解析，rest 偏差 0。
- `Lethita`：7 部件，476 根（脸骨架 `SK_Lethita_Face01_Skeleton` 与 PCM 身体 rest 差 0.25 cm，可接受），19 材质 33 贴图。
- **全部 15 套女装**（Fiona 默认装、`Shiningwill_legacy`、`PCF_001`…`PCF_012`、`PCF_067`）一次批量导出：
  先 `-NoBlend` 顺序导 61 个包，再 3 路并行 Blender。逐张看过 `blend\*\preview.png`（拼图脚本在
  `_download` 之外的临时目录）：002/003/004/006/007/009/010/012 的部件都做了重定位烘焙（Head 6.9 cm、
  Upper/Lower 到脚趾 13 cm），帽子、耳机、颈圈位置正确；005/008/010/067 隐藏默认头发，其余保留；
  PCF_012 的 `.hdr` 基色生效；`PCF_001_Temp` 裤子是资源自带的彩虹占位贴图（WIP 服装），不是导出问题。
- **剩下的 12 个**（3 套男装 `PCM_001/002/004_Temp`、7 只怪、2 个 NPC）2026-09-19 一次导完，共 30 个 `.blend`：
  `PCM_001_Temp` 的整体网格 `SK_PCM_001_Temp`（把脸、发、五件都合在一起的副本）被 `list_models.py` 跳过；
  三套男装是 Swordwind / RoyalArmy 的 NPC 甲（分层材质，面甲、锁子甲、羽饰头盔、红披风都对）；四只豺狼人
  的毛、皮、甲、眼都有色，狗头人首领的重甲和钩爪正常；白模的三个见上一节。狗头人其余 6 条只有武器，没有导。
- **`export_pmx.py`（2026-09-26，Fiona_BaseBody）**：
  - 转换 15/15 步，1107 根骨，付与计算顺序 0 处违规，PMX 6.4 MB；26 个骨骼表情；264 个刚体、246 个关节。
  - **表情**：两遍检查。
    - 在转换后的 `.blend` 里逐个渲染：眨眼、单眼、笑眼、眉毛、あいうえお 都正确；「にやり」在 1.0 时脸颊鼓包，改成 0.8。
    - 把 PMX 重新导入，用 mmd_tools 的表情滑块驱动（VMD 走的就是这条路）：效果相同。
  - **头发**：
    - 用原来的 `hair` 预设，站着不动 1 秒，从分缝扫到侧面的长发束（`Fiona_hair_d_*`）就滑下来盖到脸上。
    - 关掉头发和身体的碰撞后照样滑，排除了碰撞的原因。头部碰撞体只是下巴高度一个 7 cm 的球，挡不住头顶的头发。
    - 改成贴头皮的部分跟随头骨（139 个刚体跟随、105 个晃动）后，站立时发梢最多 5 cm，四个方向看发型不变。
  - **胸部**：在 MMD 单位下跑「来杯好茶摇一摇」这支摇晃很大的舞（480 帧）。
    - 不管弹簧设 450 还是 1500，胸部大部分时间都被甩到限位，这是这支舞本身的效果。
    - 权重改成中心放大以后，第 80、360 帧的变形消失，其余帧和不加物理的版本几乎一样。
  - **注意**：mmd_tools 按 0.08 导回米制时不改重力，Blender 里的物理预览比 MMD 硬得多。要看接近 MMD 的效果，得按 1.0 导入 PMX 和 VMD。
