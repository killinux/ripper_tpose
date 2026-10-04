# Action Taimanin（アクション対魔忍）：模型列表与导出

游戏目录默认 `E:\SteamLibrary\steamapps\common\Action Taimanin`（Steam，GREMORY，Unity 2022.3.62f2 / IL2CPP）。
这里的脚本列出游戏里全部 3D 模型（1384 个 prefab），并把选中的模型导成带卡通材质和骨架的 `.blend`，
再转 XPS 和 MMD 的 PMX。Blender 端和格式转换**复用 Taimanin Squad 的代码**（`..\taimaninsquad`），
本目录只写这款游戏不一样的部分：大包的按块读取、模型清单、Dynamic Bone、两套卡通着色器。

| 脚本 | 作用 |
|---|---|
| `list_models.py` | 列出模型（按类别 / 角色），`--details` 读面数 / 骨骼 / 着色器，`--html` 出画廊页 |
| `export_model.py` | 导出：`.blend` + 预览图，`--xps` / `--pmx` / `--turntable` 再转格式 |
| `ataimanin_common.py` | 路径、UnityFS 大包的按块读取（`Bundle`）、UnityPy 环境（`Game`）、模型清单 |
| `ataimanin_scene.py` | 读一个 prefab 写成场景文件夹（继承 `tsquad_scene.Scene`）：部件、材质提示、Dynamic Bone、胸部骨识别 |
| `atm_materials.py` | Blender 端的材质：Toony Colors Pro 2 和 Unity-Chan Toon Shader 2（给 `build_blend.py --materials` 用） |
| `html/make_gallery.py` | 画廊页 `html/index.html`（页首有脚本用法和手工操作说明） |
| `tests/test_ataimanin.py` | 离线测试（不需要游戏和 Blender） |

## 需要的东西

| 需要 | 在哪 | 说明 |
|---|---|---|
| Python 3 + `UnityPy` `lz4` `numpy` `Pillow` | `pip install UnityPy lz4 numpy pillow` | 读 bundle、解贴图；不需要 AssetStudio |
| Blender 3.6 | `D:\Program Files\blender-3.6.15-windows-x64\blender.exe` | 出 `.blend` 只用它本身 |
| `..\taimaninsquad` | 本仓库 | `build_blend.py`、XPS / PMX 转换、预览脚本都用它的 |
| Blender2XPS、mmd_tools、Convert_to_MMD5、mmd_cloth_physics | 同 Taimanin Squad | `--xps` / `--pmx` 用 |

路径用环境变量改：`ATAIMANIN_GAME_DIR`（游戏目录）、`ATAIMANIN_EXPORT_ROOT`（默认 `E:\game_export\ActionTaimanin`）、
`TSQUAD_BLENDER`、`BLENDER2XPS`。**不需要 key、不需要启动游戏、不需要联网。**

## 用法

```powershell
cd scripts\actiontaimanin
python list_models.py                         # 全部 1384 个，按类别
python list_models.py --find asagi            # 一个角色的全部模型
python list_models.py --category figure --details   # 面数 / 骨骼 / 材质 / 着色器（全部读一遍约 5 分钟，有缓存）
python list_models.py --html                  # 画廊页 html\index.html

python export_model.py asagi_costume_1_f                 # .blend + 预览图
python export_model.py asagi_costume_1_f --xps --pmx     # + XPS + PMX（带检查图）
python export_model.py asagi_costume_1_f --turntable --views   # + 转台视频、9 个角度的图
python export_model.py asagi --xps --pmx --jobs 4        # 一个角色的全部模型，4 个并行
python export_model.py asagi_costume_1_f --pmx --reconvert --bust amount=1.3   # 只重做 PMX，胸部幅度 1.3 倍
```

模型 id 就是 prefab 的名字：

| 类别 | id 的样子 | 数量 | 是什么 |
|---|---|---:|---|
| `figure` | `<角色>_costume_<n>_f` | 918 | 某个角色穿第 n 套服装的展示用模型，身体 + 头发 + 脸已经拼好 —— **要导就导这个** |
| `character` | `<角色>_g` / `<角色>_l` | 90 | 战斗（g）/ 大厅（l）用的同一角色（45 个角色） |
| `monster` | `<名字>`、`monster_<角色>_<n>` | 317 | 敌人；后一种是玩家角色当 Boss |
| `npc` | `<名字>` | 11 | NPC 和物件 |
| `weapon` | `<名字>` | 48 | 武器 prefab（游戏挂在 `Bip001 Prop1` 上） |

## 输出

```
E:\game_export\ActionTaimanin\
  <角色>\blend\<id>\<id>.blend                贴图已打包；<id>_preview.png、<id>_face.png、<id>_turntable.mp4
  <角色>\xps\<id>\<id>.xps + 贴图             <id>_xps_preview.png = 读回并摆姿势的检查图
  <角色>\pmx\<id>\<id>.pmx + textures\        preview.png / preview_dance.png / preview_gaze.png 检查图
  _meta\models.json、model_list.md、exports.json、model_details.json
  _work\logs\、_work\views\<id>\              日志、--views 的 9 张图
```

## 游戏里的资源结构

- **39 个大包**，在 `ActionTaimanin_Data\StreamingAssets\AssetBundles\pc\`，没有扩展名，是老式 AssetBundle
  （不是 Addressables）：每个包一个序列化文件 + 一个 `.resS`。`model_char` 1 GB（解开 2 GB），`unit` 126 MB。
  `game` / `string` / `system` 三个是加密的数据表，模型用不到。
- **按块读**：包是 LZ4HC、每块 128 KB。`Bundle` 只读块表，要哪段数据就解哪几块；序列化文件整个读进 UnityPy
  （`model_char` 的 245 MB 不到 1 秒），网格和贴图所在的 `.resS` 由 UnityPy 通过同一个按块读取器按需取。
  没有这一层，UnityPy 得先把 2 GB 全解到内存里。
- **模型清单 = `unit` 包里的 prefab**（容器路径 `assets/resources.assetbundle/unit/<类别>/<名>/<名>.prefab`）。
- **零件分开放**：`model_char/<角色>/body_<角色>/` 放脸（`fbx_<角色>_face`）和各套服装的头发，
  `model_char/<角色>/costume_<角色>_<n>[_aos|_wos]/` 放那套服装的身体网格、材质、贴图；
  只有 `unit` 里的 prefab 把它们拼成一个角色，所以脚本从 prefab 读，跨包引用按 CAB 名找到对应的包。
- **一个展示用 prefab 的样子**（`asagi_costume_1_F`）：
  - 根上是 `FigureUnit`；下面 `prf_asagi_costume_1` 挂着 `Animator`、`CostumeBody`、4 个 `DynamicBone`；
  - `charbody`、`charhair` 两个蒙皮网格，骨架 `root/Bip001/...`（3ds Max Biped）；
  - 脸是单独的 prefab，挂在 `Bip001 Head/Socket_head` 下：`fbx_asagi_face` 里的 `charface` 蒙在 28 根**脸部骨**上；
    `fbx_asagi_face_none`（未激活）是不带骨骼的备用脸，`emotion_shy`（未激活）是脸红贴片 —— 前者不导，后者导出后隐藏；
  - `CostumeBody.kCostumeResMaterialList` 是这套服装的换色材质表，`TexPartsColor` 是换色遮罩。

## 着色器

游戏用**内置渲染管线、Gamma 色彩空间**（`PlayerSettings.m_ActiveColorSpace = 0`）：着色器直接对显示值做乘加。
`atm_materials.py` 的节点组也这样算 —— 贴图先转成显示值（x^(1/2.2)），材质颜色原样进，结果再转回线性给 Blender；
单独一张贴图进出不变。和 Squad 一样，结果是纯自发光，光的方向由 `TSQ_Sun` 物体决定。

角色材质 6518 个，用到的着色器：

| 着色器 | 材质数 | 说明 |
|---|---:|---|
| `eTOYLab/Toony Colors Pro 2/Variants/Mobile RimOutline ...` | 5501 | Toony Colors Pro 2（商业着色器），工作室改过；老服装都是它 |
| `UnityChanToonShader/Mobile/Toon_ShadingGradeMap ...` | 736 | Unity-Chan Toon Shader 2.0.8（开源），新服装 |
| `Shader Forge/eye_unlit_mask_togray` | 174 | 眼睛，不受光 |
| `Mobile/Particles/Alpha Blended` | 70 | 脸红贴片 |
| 其他（Standard、特效） | 37 | 当普通材质 |

**Toony Colors Pro 2**（公式是从编译后的 D3D11 程序反汇编读出来的，工具是 `..\taimaninsquad\dump_shader.py` 的函数）：

```
albedo = MainTex × _Color
albedo = lerp(albedo, mean(albedo) × _WhiteBalance × _PartsColorR|G|B, PartsColorMask.r|g|b)   ← 换色
albedo = lerp(albedo, _RimColor.rgb, smoothstep(_RimMin, _RimMax, 1 − N·V) × _RimColor.a)       ← 边缘光混进底色
ramp   = smoothstep(_RampThreshold ∓ _RampSmooth/2, N·L × 0.5 + 0.5)
亮部 = 1（换色区：sat(_PartsColor + 0.5)）；暗部 = lerp(亮部, _SColor.rgb, _SColor.a)（换色区：× 0.4）
颜色 = albedo × 光 × lerp(暗部, 亮部, ramp) + Emission × _Emission_color × _Emission_power
描边：顶点沿法线外推 _Outline × 0.01（_Outline 一般是 0.1，即 1 mm），颜色 _OutlineColor
```

材质里虽然存着 `_HColor`，这个版本的程序里亮部是常数 1，没有用它。

**Unity-Chan Toon Shader 2**（公开源码的 `UCTS_ShadingGradeMap`，和反汇编对过）：底色 / 一影 / 二影按两级带羽化的阈值切换，
高光（`_HighColor`，硬边或 Specular）、边缘光（含反向边缘光）、MatCap（加或乘，带遮罩）、自发光、
`_Outline_Width × 0.001` 的描边。工作室加的**换色在这里作用于最终颜色**（TCP2 是作用于底色）：
`最终色 = lerp(最终色, mean(最终色) × _WhiteBalance × _PartsColor, 遮罩)`。Asagi 的紫色战斗服就是这样上色的
（`_PartsColorR/G/B` 都是 (0.518, 0.31, 0.482)）。

没做的：UTS2 的 AngelRing（头发天使环，这些材质里 `_AngelRing` 都是 0）、法线贴图只用于底色明暗（MatCap 用几何法线）、
`_ColorShift` 动画。

## 骨架、脸、物理

- **骨架**：3ds Max Biped（`Bip001 ...`），手指每根 2 节，没有扭转辅助骨。额外的骨头很多没有名字
  （`Bone005` / `Bone006` 是 Asagi 的胸，`Bone136`–`Bone141` 是她的长发）；也有带名字的（Rinko 的 `bone_bo_l_00`、`bone_hair_*`）。
- **脸是骨骼驱动的**，没有 blend shape：眼球（`Bone_Eyeball_L/R`）、上眼睑（每侧 3 根）、眉（每侧 2 根）、
  嘴唇 8 根、上下牙、舌头，共约 28 根。表情是动画片段（在 `animation_char` 包里）。
- **物理是 Dynamic Bone**（Unity 插件）：每条链一个组件，参数是 `damping / elasticity / stiffness / inert`，
  碰撞体是球和胶囊（`DynamicBoneCollider`）。胸部是单根骨 + `m_EndOffset`（一个摆）。脚本把它们读进场景文件
  （`.blend` 骨架的 `tsq_cloth` 属性）。
- **哪两根是胸部骨**（`ataimanin_scene.breast_pair`）：名字带 bust / breast / mune 的优先；否则取 Dynamic Bone 的根里
  挂在脊柱骨上、位于脊柱前方、左右对称的那一对单骨链。
- **按名字找眼球骨 / 嘴唇骨**（`ataimanin_scene.by_side`，2026-10-04）：脸的骨架里可能有名字结尾相同的辅助点
  （Taimanin Collection 的 `Point_Eyeball_L` 挨着 `Bone_Eyeball_L`）。同一侧有几个候选时取**带蒙皮的那个**；
  原来是后找到的盖掉先找到的，转到了辅助点上，视线形状一个顶点都不动。这个游戏的模型没有这种辅助点，结果不变。
- 本目录的角色读取（`ataimanin_scene.Scene`）也被 `..\taimanincollection` 用着：那个游戏的阿莎姬是同一套做法。
- **导出的是 prefab 的姿势**（Unity 在播任何动画之前画出来的样子）。Asagi 两侧那两缕绕出去的细发
  （`Bone_hair00` / `Bone_hair06`）在 prefab 里比绑定姿势转了 26°，prefab 的姿势才是对的（见「踩过的坑」）。

## 表情（2026-10-03）

脸没有 blend shape，游戏的表情是 `animation_char` 包里的动画片段。脚本把它们解出来做成形状键，PMX 里再组成 MMD 的标准表情。
Asagi：`.blend` 里 28 个形状键，PMX 里 36 个顶点表情（22 个 MMD 标准名 + 14 个游戏原名）。

- **数据在哪**：`animation_char/<角色>/ani_story/ani_face_<角色>_story_<名>_01.anim` 是剧情对话用的整脸表情
  （idle、smile、angry、panic、serious、shy、surprise，约 45 个角色都有）；idle 片段第 1.00 秒有一次眨眼。
  `ani_mouth_<角色>_story_<名>_01.anim` 只有一个姿势：用这个表情说话时张开的嘴。没有元音口型，没有单独的眨眼 / 视线片段，
  也没有「闭着嘴笑」的嘴（smile 的嘴和平时一样，只有眼睛和眉毛在笑）。
- **片段解码**（`ataimanin_anim.py`）：曲线分三种存（streamed：带三次多项式系数的关键帧；dense：每帧一个采样；
  constant：一个值），绑定里的路径是「Animator 下面的骨骼路径」的 CRC32，属性 1 / 2 / 3 = 位置 / 旋转四元数 / 缩放。
- **做成形状键**（`ataimanin_scene.Scene.add_expressions`）：把姿势套到脸部骨上，按蒙皮权重算出每个顶点的位移，
  存成和游戏自带 blend shape 一样的数据，后面的流程（`.blend` 的形状键、PMX 的顶点表情）不用改：

  | 形状键 | 来源 | 是游戏数据吗 |
  |---|---|---|
  | `closed_eyes` | idle 片段里眼睑离静止位置最远的那一帧（眨眼），只取眼睑骨 | 是 |
  | `<名>_face`（`smile_face`、`angry_face`、`surprised_face` …） | 该表情片段开头的姿势 | 是 |
  | `mouth_talk_a` | idle 的说话口型（相对静止脸的位移） | 是 |
  | `<名>_talk` | 该表情的说话口型，存成**相对那个表情**的位移，所以「表情 + 说话」叠加 = 游戏里边说话边做表情的样子 | 是 |
  | `smile_eyes`、`surprise_eyes`、`smile_brows`、`angry_brows`、`serious_brows`、`panic_brows` | 整脸表情里只取一组骨头（眼睑 / 眉毛）的那部分（`CUTS`） | 是，按骨骼切出来的 |
  | `mouth_smile`、`mouth_frown`、`mouth_wide`、`mouth_narrow` | 8 根嘴唇骨按配方平移（`MOUTH_POSES`：嘴角 / 上下唇两侧 / 上下唇中间各移多少毫米，按嘴宽缩放） | **不是**，自己配的 |
  | `up_eyes`、`down_eyes`、`left_eyes`、`right_eyes` | 眼球骨绕自己的骨头转 5°（上下）/ 9°（左右）（`GAZE`；游戏自己的 panic 表情里眼睛斜看也是 9° 左右） | **不是**，自己转的 |

- **PMX 的表情**（`morph_recipes` → 场景的 `morph_sources` → Squad 的 `export_pmx_blender.build_morphs`）：

  | MMD 表情 | 用哪个形状 |
  |---|---|
  | `まばたき` | `closed_eyes` |
  | `笑い` | `smile_eyes`（笑的时候眼睛是闭上的才用它，否则和 `まばたき` 一样） |
  | `ウィンク` / `ウィンク右` | `smile_eyes` 的左半 / 右半 |
  | `ウィンク２` / `ｳｨﾝｸ２右` | `closed_eyes` 的左半 / 右半 |
  | `びっくり` | `surprise_eyes` |
  | `あ` | `mouth_talk_a` |
  | `い` / `え` | 0.3 × `あ` + `mouth_wide` / 0.55 × `あ` + 0.6 × `mouth_wide` |
  | `う` / `お` | 0.25 × `あ` + `mouth_narrow` / 0.8 × `あ` + 0.75 × `mouth_narrow` |
  | `にっこり` / `口角下げ` | `mouth_smile` / `mouth_frown` |
  | `困る` / `怒り` / `真面目` / `にこり` | `panic_brows` / `angry_brows` / `serious_brows` / `smile_brows` |
  | `目上` / `目下` / `目左` / `目右` | `up_eyes` … `right_eyes`（左右按从正面看的方向，和 Squad 游戏自带的 `left_eyes` 一致） |

  另外 7 个整脸表情和 7 个说话口型以游戏原名列在「其他」里。切出来的和自己配的辅助形状只留在 `.blend` 里，不以原名进 PMX。
- **「笑的时候眼睛闭不闭」怎么判断**（`eye_closure`）：直接量眼睑 —— 把眼睛沿宽度分 6 列，每列取「上眼睑下缘 − 下眼睑上缘」，
  平均开口比静止时少 70 % 以上算闭上。Asagi 和 Rinko 的 smile 都是 98 % – 100 %（「^ ^」）。
- **为什么不按高度切区域**：Squad 的转换脚本是按高度把整脸表情切成眼 / 眉 / 嘴的。这张脸的眉毛和上睫毛在同一高度，
  切不开；这里有骨骼，所以按骨骼组切（`CUTS`），再用「配方」告诉转换脚本每个 MMD 表情用哪个形状。
- **核对过的**（Asagi）：`.blend` 的嘴部正面 / 侧面特写（平时、にっこり、口角下げ、あいうえお、怒脸、怒吼、害羞、边笑边说）
  和去掉头发的眼部特写（眨眼、笑眼、惊讶、四个视线、四种眉毛、panic）；PMX 读回的 36 格表情表。
- **限制**：嘴唇配方和视线角度只在 Asagi 上调过，别的角色嘴形不同时可能要改 `MOUTH_POSES` / `GAZE`；
  没有「眉毛上 / 下」（游戏没有这样的表情）；脸红贴片 `emotion_shy` 没有做成表情；没有在 MMD 本体里打开过。
  用 `--no-expressions` 可以不带这些形状键。

## XPS / PMX

用的是 Taimanin Squad 的转换脚本（`export_xps_blender.py`、`export_pmx_blender.py`），在那边加了几处通用入口：

| 入口 | 作用 |
|---|---|
| `build_blend.py --materials <文件>` | 别的游戏的材质构建器（本目录的 `atm_materials.py`） |
| 骨架属性 `tsq_body_bones` | 「这些蒙皮骨是身体」的正则 —— 脸部骨不能被布料插件当成衣物 |
| 骨架属性 `tsq_cloth` 里的 Dynamic Bone 链 | 头上的无名骨链（`Bone136`…）算头发：布料插件默认不碰头下面的骨头，除非名字里有 hair |
| 材质记录里的 `hints` | 阴影色比例、球面贴图（MatCap）及其遮罩、描边 —— PMX 的 toon / sphere / edge 从这里取 |
| 眼球骨 | `Bone_Eyeball_L/R` → MMD 的 `左目` / `右目`（有 `両目`） |
| 场景里的 `morph_sources`（骨架属性 `tsq_morph_sources`） | 表情来源：`{角色: [形状名]}`、`recipes`（每个 MMD 表情用哪个形状，和 Squad 的 `RECIPES` 同格式）、`drop`（不以原名进 PMX 的辅助形状） |
| 材质属性 `tsq_overlay = 0` | 这个 unlit 材质是脸本身（眼睛材质里有眉毛、睫毛、牙齿），不是藏在头里的贴片 |

胸部物理和 Squad 相同：平移弹簧，按胸部大小缩放（`--bust`，设置在 `..\taimaninsquad\tsquad_common.BUST`）。
Dynamic Bone 没有「最大行程」这个参数，所以这里没有 Squad 那样的游戏上限。

## 和 Taimanin Squad 的不同

同一家公司（GREMORY / Lilith）、同一批角色、都是 Unity 2022.3 + IL2CPP、骨架都是 3ds Max Biped，但两个游戏差别很大：

| | Taimanin Squad | Action Taimanin |
|---|---|---|
| 渲染 | URP，**线性**色彩空间 | 内置管线，**Gamma** 色彩空间 |
| 打包 | Addressables：`catalog.json` + 999 个小包（每个单位一个） | 39 个大包（`model_char` 1 GB），按容器路径找；3 个数据表包加密 |
| 读取 | UnityPy 直接整包读 | 要按块读（否则先解 2 GB） |
| 模型数量 | 252 个单位 | 1384 个 prefab（918 个展示模型 = 45 个角色 × 服装） |
| 一个模型 | 一个 prefab 就是整个角色（少数肢体放在武器 prefab 里） | prefab 把身体、头发、脸三处的零件拼起来 |
| 服装 | 少数角色有另一个单位号（19 个） | 每个角色十几到三十套，另有换色（材质表 + 遮罩 × 颜色） |
| 卡通着色器 | 自研 `Squad/SquadToon`：阴影色贴图、遮罩图、MatCap、**脸部 SDF 阴影** | Toony Colors Pro 2（84 %）+ Unity-Chan Toon Shader 2（11 %）：阴影是颜色乘数，没有阴影贴图，没有 SDF |
| 脸 | **blend shape**（整脸表情约 24 个），没有眼球骨 | **骨骼**（约 28 根），表情是动画片段，有眼球骨 |
| 布料 / 胸部 | Magica Cloth 2；胸部 = Bone Spring（平移弹簧，有行程上限） | Dynamic Bone；胸部 = 单骨摆（转动），没有行程上限 |
| 骨头命名 | `Bone_L_Bust`、`Bone_*_Hair_*`，有扭转辅助骨 | 很多无名骨（`Bone005`、`Bone136`），没有扭转骨，手指 2 节 |
| 描边 | 反向外壳，`_Outline_Width` mm | 反向外壳，TCP2 `_Outline × 1 cm`、UTS2 `_Outline_Width` mm |

同一个角色（Asagi 默认服装）的数字：

| | Squad `1_asagi` | Action `asagi_costume_1_f` |
|---|---:|---:|
| 顶点（焊接后） | 23,397 | 9,210 |
| 三角面 | 33,415 | 13,714 |
| 骨骼（.blend） | 135 | 96 |
| 材质 | 9 | 7 |
| blend shape | 24 | 0（脸部骨 28） |
| 主贴图 | 1024（服装）/ 1024（脸） | 1024（服装）/ 512（脸） |
| 身高 | 1.70 m | 1.70 m |

Squad 的模型精度高一倍多，表情现成；Action Taimanin 的服装多得多，着色器是公开 / 通用的两种。

## 试导结果（2026-10-03）

`python export_model.py asagi_costume_1_f --xps --pmx --turntable --views` → `E:\game_export\ActionTaimanin\Asagi\`：

| 格式 | 结果 |
|---|---|
| `.blend` | 4 个部件（身体、头发、脸、隐藏的脸红贴片），约 9,200 顶点 / 13,714 三角面，96 根骨（80 根有蒙皮），7 个材质，脸上 28 个形状键（总览图 `<id>_expressions.png`）；读取 + 建模约 12 秒 |
| XPS | 96 根骨、6 个网格、13,714 面，每顶点最多 3 个权重，没有未加权的顶点；读回摆姿势的检查图正常 |
| PMX | 190 根骨、24 个刚体、9 个关节；撕裂 0、付与顺序违规 0；胸部 2 个刚体（大小 8.2 cm → 系数 0.76，最多晃 ±3.8 cm）；长发 5 节 + 刘海 2 节有物理；静止下落最大漂移 1.2 cm；顶点表情 36 个（见「表情」，表情表 `preview_morphs.png`） |

看过的图：`.blend` 的正面 / 侧面 / 背面 / 四分之三 / 脸、形状键总览；XPS 读回图；PMX 的表情表、`preview.png`、`preview_dance.png`（4 帧，身体姿势正常）、
`preview_gaze.png`（眼球骨能转；上下看时虹膜会转出眼眶，这张脸的眼睛转动量要比检查图里用的小）。
另外在临时目录建过 `asagi_costume_2_f`（浴巾，全是 TCP2 材质）和 `rinko_costume_1_f`（UTS2 + 换色遮罩，带名字的胸部 / 头发骨）
的 `.blend` 看材质，没有归档。

## 已知限制

- **表情**的限制见「表情」一节（嘴唇配方和视线是自己配的，只在 Asagi 上调过）。
- **没有在 MMD 本体和 XPS 本体里打开过**：检查图是 Blender 读回渲的。
- **只试导了少数几个模型**（见「试导结果」），1384 个里绝大多数没有跑过；怪物 / NPC / 武器类别没有试。
- **武器没有挂上**：展示用 prefab 不带武器，武器是 `unit/weapon/` 下单独的 prefab。
- **服装换色没有做成选项**：导出的是材质里存的默认颜色（`CostumeBody` 的换色材质表没有用）。
- **`--pmx` 用的是 ROE worker 的胸部刚体代码**（`scripts\riseoferos\export_character_model_blender.py`，2026-10-03 下午进了仓库）：
  和 Taimanin Squad 相同，见 `..\taimaninsquad\README.md` 的已知限制。
- 着色器没做的部分见「着色器」一节末尾。

## 踩过的坑

- **prefab 姿势和绑定姿势不一样时，哪个对**：Asagi 的头发网格里 `Bone_hair00` / `Bone_hair06`（两缕细长的侧发）
  在 prefab 里和绑定姿势差 26°，其余 8 根头发骨、43 根身体骨、28 根脸部骨都在绑定姿势上。一开始以为 prefab 里是
  过期的姿势，写了「把离群的骨头放回绑定姿势」的步骤 —— 渲出来对比，放回去之后两缕头发横着支出去，
  而 prefab 姿势下它们顺着长发垂在背后，Squad 里的同一角色也是这个形状。结论：**prefab 姿势是美术摆好的造型**，
  那一步删掉了。判断方法：两种都渲侧面图对比，不要只看正面。
- **布料插件不给头下面的无名骨链加物理**：`mmd_cloth_physics` 为了不碰脸部骨，头 / 脖子下面的骨头只有名字里带
  hair 才当头发。Asagi 的长发是 `Bone136`–`Bone141`，第一次导出的 PMX 里长发是硬的。现在用游戏自己的信息：
  Dynamic Bone 组件的根就是会摆的链。
- **脸部骨会被当成衣物**：同一个插件把身体正则（`^Bip001`）以外的所有蒙皮骨链当衣物。脸部骨的名字
  （`Bone_Face_*`、`Bone_Eyeball_*`、`Bone_Teeth_*`…）通过骨架属性 `tsq_body_bones` 加进身体正则。
- **压缩网格的第 4 个骨骼权重是错的（UnityPy 1.25.3）**：压缩网格的权重按 1/31 存，每个顶点最多存 3 个，第 4 个是
  「差多少到 1」。UnityPy 把它算成「1 − 前三个整数之和」，例如 25 + 2 + 2 → **−28** 而不是 2/31。脸是压缩网格，
  嘴角一圈顶点正好有 4 根骨：这里算表情位移时权重和成了负数，这些顶点没有位移 —— 嘴角被撕开、露出牙齿；
  Blender 里负权重被丢掉，第 4 根骨的份额没了。现在在 `tsquad_scene.packed_weights` 里按「1 − 前三个之和」重算。
  发现方法：同一个配方用「摆骨头」和「形状键」各渲一次，嘴不一样，逐顶点对比出 64 个顶点没有位移。
- **眼睛材质里画着眉毛、睫毛、牙齿**：Squad 把 unlit 材质当成藏在头里的贴片（脸红、汗），切表情时不带它们；
  这里的眼睛材质就是脸的一部分。材质属性 `tsq_overlay = 0` 告诉转换脚本「这不是贴片」，否则眉毛表情是空的。
- **眼睑骨既平移又转**：用骨头原点的位移判断「眼睛闭没闭」会算错（笑眼的上眼睑中段骨只下来 2 mm，眨眼是 7 mm），
  而且「^ ^」是下眼睑往上顶，和眨眼方向不一样。所以直接量眼睑顶点之间的开口。
- **1 GB 的包不能整个解**：见「按块读」。三个加密包的文件头不是 `UnityFS`，`Bundle` 直接拒绝。
- **`_PartsColorMask` 不是可有可无的**：UTS2 材质的默认颜色就是靠换色算出来的，不接遮罩衣服会是贴图的原色。

## 测试

```powershell
python -m unittest discover -s tests        # 32 项：按块读取（合成的 UnityFS 文件）、模型 id 解析、材质提示、胸部骨识别、同名骨取带蒙皮的、片段解码、姿势 → 顶点位移、嘴唇配方 / 视线 / 眼睑开口 / PMX 配方
```
