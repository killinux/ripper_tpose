# Taimanin Collection（対魔忍コレクション）：3D 模型的列表与导出

Steam 版（eTOYLab，`E:\SteamLibrary\steamapps\common\Taimanin Collection`）。**Unity 2018.4.36f1 + IL2CPP，内置渲染管线，
Gamma 色彩空间。** 这是一个 **2D 卡牌游戏**：843 张卡是 `Data\Res` 下加密的图片，没有模型。它的 3D 内容只有摩托小游戏那一块，
全部在玩家数据 `TaimaninCollection_Data\data.unity3d` 这一个文件里（360 MB，普通 UnityFS，**没加密**）：

- **阿莎姬**一个角色 —— 和 Action Taimanin 的 `asagi_costume_1` 是同一套做法（同一家工作室的引擎代码）：3ds Max Biped 骨架，
  脸是挂在头上的单独 prefab、蒙在约 28 根脸部骨上，头发和胸是 Dynamic Bone，材质是 Toony Colors Pro 2；
- 摩托小游戏用的：带骨架的**摩托车**、**运输机**，**桥面赛道**、路障、金币、加速瓶、磁铁、卡车、夜空穹顶，以及拼出关卡的 22 个**赛道段**；
- Action Taimanin 的**残留**，这个游戏并不显示：两套城市布景（材质在构建时被剥掉了着色器和全部参数）、221 个原始模型导入件（其中 218 个只挂着 Unity 默认材质）。

这里的脚本列出这些对象，把选中的导成带游戏材质和骨架的 `.blend`，再转 XPS 和 MMD 的 PMX。Blender 端和格式转换用
Taimanin Squad 的代码（`..\taimaninsquad`），读角色和卡通材质用 Action Taimanin 的（`..\actiontaimanin`），本目录只写这个游戏不一样的部分。

| 脚本 | 作用 |
|---|---|
| `list_models.py` | 列出带网格的对象（按类别），`--details` 读面数 / 骨骼 / 材质，`--html` 出画廊页 |
| `export_model.py` | 导出：`.blend` + 预览图，`--xps` / `--pmx` / `--turntable` 再转格式 |
| `tcollection_common.py` | 路径、读 `data.unity3d`（`Game`）、没有类型树时怎么认脚本组件、模型清单 |
| `tcollection_scene.py` | 读一个 prefab 或一个场景写成场景文件夹（继承 `ataimanin_scene.Scene`）：材质的补救、场景的多个根 |
| `tco_materials.py` | Blender 端的材质：Action Taimanin 的卡通材质 + 这个游戏的场景着色器（给 `build_blend.py --materials` 用） |
| `dynamic_bone_types.json` | Dynamic Bone 两个脚本类的字段表（见「没有类型树」） |
| `html/make_gallery.py` | 画廊页 `html/index.html`：页首是「怎么导出模型」，然后是已导出的卡片和全部清单 |
| `tests/test_tcollection.py` | 离线测试（不需要游戏和 Blender） |

## 需要的东西

| 需要 | 在哪 | 说明 |
|---|---|---|
| Python 3 + `UnityPy` `lz4` `numpy` `Pillow` | `pip install UnityPy lz4 numpy pillow` | 读数据文件、解贴图 |
| Blender 3.6 | `D:\Program Files\blender-3.6.15-windows-x64\blender.exe` | 出 `.blend` 只用它本身 |
| `..\taimaninsquad`、`..\actiontaimanin` | 本仓库 | Blender 端、格式转换、角色读取都用它们的 |
| Blender2XPS、mmd_tools、Convert_to_MMD5、mmd_cloth_physics | 同 Taimanin Squad | `--xps` / `--pmx` 用 |

路径用环境变量改：`TCOLLECTION_GAME_DIR`（游戏目录）、`TCOLLECTION_EXPORT_ROOT`（默认 `E:\game_export\TaimaninCollection`）、
`TSQUAD_BLENDER`、`BLENDER2XPS`。**不需要 key、不需要启动游戏、不需要联网。**

## 用法

```powershell
cd scripts\taimanincollection
python list_models.py                            # 全部 276 个对象，按类别
python list_models.py --category prop level      # 只看某几类
python list_models.py --find asagi "*truck*"     # 按 id / 角色名找，支持通配符
python list_models.py --details                  # 顶点 / 三角面 / 骨骼 / 材质（几个是默认 / 被剥掉的）/ 着色器
python list_models.py --html                     # 画廊页 html\index.html

python export_model.py prf_asagi_costume_1                           # 阿莎姬：.blend + 预览图（约 30 秒）
python export_model.py prf_asagi_costume_1 --xps --pmx --turntable   # 全套（约 3 分钟）
python export_model.py fbx_motorcycle_rig fbx_dropship_rig --xps --pmx    # 载具
python export_model.py --category vehicle prop scene --xps --pmx     # 按类别
python export_model.py --game                    # 游戏实际显示的全部：角色、载具、道具、赛道段、场景（残留不算）
python export_model.py prf_asagi_costume_1 --pmx --reconvert --bust amount=1.3   # 只重做 PMX，胸部幅度 1.3 倍
python export_model.py scene_race_bridge --preview-view 1,0,0.3      # 道具 / 场景的预览换个方向
python -m unittest discover -s tests             # 离线测试
```

**id 就是 prefab 自己的名字**；场景是 `scene_<场景名>`，场景里单独一个根物体是 `scene_<场景名>_<根物体名>`。

| 类别 | 在数据里的位置 | 数量 | 是什么 |
|---|---|---:|---|
| `character` | `unit_art/model/<角色>/prf_*` | 1 | 拼好的角色（身体 + 头发 + 脸）—— `prf_asagi_costume_1` |
| `vehicle` | `background/art/movie/*_rig` | 4 | 带骨架的载具：摩托车车身、前后轮（各一个 rig）、运输机 |
| `prop` | `bike/background/prf_*`、`bike/skybox/prf_*` | 8 | 摩托小游戏的道具和场景件：桥面赛道、路障、金币、加速瓶、红心、磁铁、卡车、夜空穹顶 |
| `level` | `bike/level/prf_race_trackobject_*` | 22 | 拼出关卡的赛道段：路障、金币、卡车按位置摆好（另带粒子特效，不导） |
| `scene` | 构建里的场景 | 3 | `scene_race_bridge`（整个赛车场景）和它的两个根：`…_bikeobj`（装好轮子的整辆摩托）、`…_background` |
| `set` | `background/art/movie/…/prf_*` | 3 | Action Taimanin 的城市布景，残留：材质被剥掉 |
| `unit` | `unit/<名>` | 1 | 游戏实际生成的单位 `asagi_g`：同一个角色模型 + 一台相机 |
| `part` | `unit_art/model/<角色>/<服装>/` | 4 | 角色的零件（身体、脸、备用脸、脸红贴片） |
| `effect` / `director` | `effect/`、`director/` | 5 / 4 | 特效网格；过场演出的摆位（Timeline） |
| `raw` | 其余 | 221 | 原始模型导入件（残留）；218 个只有 Unity 默认材质 |

`--game` 导出前五类；残留和零件要点名或用 `--category` 才导。

## 输出

```
E:\game_export\TaimaninCollection\
  <组>\blend\<id>\<id>.blend            贴图已打包；<id>_preview.png，角色另有 _face.png / _expressions.png / _turntable.mp4
  <组>\xps\<id>\<id>.xps + 贴图         <id>_xps_preview.png = 读回并摆姿势的检查图
  <组>\pmx\<id>\<id>.pmx + textures\    角色另有 preview.png / preview_dance.png / preview_gaze.png / preview_morphs.png
  _meta\models.json、model_list.md、model_details.json、exports.json
  _work\logs\、_work\views\<id>\        日志、--views 的 9 张图
```

`<组>` 是角色名（`Asagi`）或类别（`Vehicles`、`Props`、`Levels`、`Scenes`、`Sets` ……）。

## 导出结果（2026-10-04）

`E:\game_export\TaimaninCollection\` 里一共 41 个模型：

| 类别 | 数量 | 格式 | 说明 |
|---|---:|---|---|
| 角色 | 1 | blend + XPS + PMX + 转台视频 | `prf_asagi_costume_1`：9,323 顶点 / 13,773 三角面，102 根骨，7 个材质，脸上 29 个形状键；PMX 196 根骨、24 个刚体、37 个表情（22 个 MMD 标准名），撕裂 0、付与顺序违规 0，胸部最多晃 ±3.8 cm |
| 载具 | 4 | blend + XPS + PMX | 摩托车车身（2,347 顶点，10 根骨）、前后轮、运输机（47,398 顶点，18 个部件，材质是借来的，见下） |
| 道具 | 8 | blend + XPS + PMX | 桥面赛道一段长 1,022 m；夜空穹顶的材质被剥掉且没有同名贴图，是纯白的 |
| 场景 | 3 | blend + XPS + PMX | 整个赛车场景（199,006 顶点：13 段桥 + 远山 + 城市远景 + 海面 + 摩托）；整辆摩托；背景 |
| 赛道段 | 22 | blend | 需要别的格式时加 `--xps --pmx` |
| 残留布景 | 3 | blend | 贴图是按名字猜的（见「材质的三种补救」） |

非人形的 PMX 都是「保持游戏原骨、没有 IK 和物理」的那条路。全部没有失败的。

和 Action Taimanin 的 `asagi_costume_1_f` 对比：那边 9,210 顶点 / 13,714 三角面、96 根骨、28 个形状键、PMX 36 个表情；
这里多 6 根骨（脸里多了 `Point_Eyeball_*` 之类的辅助点）、多一个说话口型 `angry_02_talk`。外观、贴图、骨架命名都一样，
是同一个模型的另一个版本。这里**只有这一套服装**（另有 `tex_asagi_body_02 / 03` 两张贴图，没有材质在用）。

## 游戏里的资源结构

- **`data.unity3d`** 是把整个玩家数据打成的一个 UnityFS 包，里面是：`globalgamemanagers`、`level0`–`level2`（三个场景：
  Title、Lobby、race_bridge）、`sharedassets*.assets`、`resources.assets`（24,762 个对象，模型都在这里）。UnityPy 整个读进来约 15 秒。
- **模型清单 = `Resources` 文件夹的路径表**：`globalgamemanagers` 里的 `ResourceManager.m_Container` 把 4,373 条路径
  （`unit_art/model/asagi/prf_asagi_costume_1` 这样的）对到对象上，其中 348 个是 prefab。脚本取「里面有会被画出来的网格」的那些
  （渲染器开着、物体是激活的、有网格），按路径分到上表的类别里；再加上三个场景里有网格的。
- **卡牌**（没有导，这里只记格式）：`Data\Res\C#####.dat` 843 个 + `CardFlip.dat`（868 MB）+ `Scenario.dat` 是加密的
  （每个 `.dat` 开头 16 字节都相同）。`Resources.map` / `CardFlip.map` 是明文索引：`u32 长度 + 组名`、`u32 条目数`，
  每条 `u32 长度 + 名字`、`u32 类型`、`u32 偏移`、`u32 大小`；9,268 个条目叫 `C00001a/b`（卡面）、`SR001a–f`、`R-ev001a–c`、`black`。
  按名字和大小看全是图片。`Data\Voice` 下 1,509 个是没加密的 UnityFS（语音）。

## 没有类型树：脚本组件怎么读

AssetBundle（Squad、Action Taimanin 用的）里每个对象都带着自己的**类型树**（字段表），什么脚本都读得出来。
**玩家构建不带类型树**：引擎自己的类（Mesh、Material、Transform、AnimationClip ……）UnityPy 自带字段表，能读；
脚本组件（MonoBehaviour）就只是一段不知道怎么切的字节。模型需要其中两个类 —— `DynamicBone`（哪些骨链会摆、参数）和
`DynamicBoneCollider`。做法：

1. **认出是哪个脚本**：任何 MonoBehaviour 的数据都以同样的四个字段开头 —— `m_GameObject`（int32 + int64）、`m_Enabled`
   （1 字节，对齐到 4）、`m_Script`（int32 文件号 + int64 路径号）。从第 16 字节读出 `m_Script`，到
   `globalgamemanagers.assets` 的 836 个 `MonoScript` 里查类名（`tcollection_common.script_reference` / `Game.script_class`）。
2. **借字段表**：Dynamic Bone 是同一个 Unity 插件，Action Taimanin 的包里有它的类型树。把那两棵树存成
   `dynamic_bone_types.json`（每个节点 `[层级, 类型, 名字, 字节数, meta flag, 版本, type flags]`，只是字段的排列，不是游戏素材），
   用 `TypeTreeNode.from_list` 还原后交给 `reader.read_typetree(node)`。
3. **核对**：UnityPy 读完会检查「读掉的字节数 = 对象的字节数」。这个游戏里 8 个 `DynamicBone`（236 / 248 / 280 字节，
   差别来自碰撞体列表的长短）和 4 个 `DynamicBoneCollider`（60 字节）全部正好读完。

读出来的结果：胸部 `Bone005` / `Bone006`（单骨 + `m_EndOffset`），长发 `Bone136` 起的链，刘海 `Bone_Fr_hair00`。

## 阿莎姬

读法和 Action Taimanin 完全一样（`ataimanin_scene.Scene`），这里多处理的三件事：

- **表情片段有两套**。脸没有 blend shape，表情是动画片段 `ani_face_asagi_story_<名>_01`（整脸）和
  `ani_mouth_asagi_story_<名>_01`（说话时张开的嘴），脚本把它们做成形状键。数据里 7 个整脸片段和 2 个口型片段**同名各有两个**：
  一套旧的（口型只有 angry / angry_02 / idle，而且是 2 秒的说话循环，开头嘴是闭着的），一套和 Action Taimanin 一致的
  （7 个整脸 + 7 个口型，口型是单帧姿势）。先遇到哪个用哪个的话会混着用：第一次导出 `mouth_talk_a` 只动了 0.1 mm。
  现在同名的取**后一个对象**（完整的那套排在后面），`mouth_talk_a` 是 7.3 mm。
- **`Point_Eyeball_L/R`**：脸的骨架里除了眼球骨 `Bone_Eyeball_L/R`，还有两个同样以 `Eyeball_L/R` 结尾的辅助点，不带蒙皮。
  原来的代码按名字找眼球骨，后找到的盖掉先找到的 —— 转的是辅助点，四个视线形状一个顶点都没动。现在同名的取**带蒙皮的那个**
  （`ataimanin_scene.by_side`，Action Taimanin 那边也一并改了，它的结果不变）。
- `unit/asagi_g`（游戏实际生成的单位）= `prf_asagi_costume_1` 外面套一层、加一台相机，模型相同，所以单列一类、默认不导。

## 材质

角色和载具的 **Toony Colors Pro 2**（`eTOYLab/Toony Colors Pro 2/Variants/Mobile RimOutline OutlineBlending`）、眼睛的
`Shader Forge/eye_unlit_mask_togray`、脸红贴片的粒子着色器，都直接用 `..\actiontaimanin\atm_materials.py` 的构建器
（公式见那边的 README）。摩托车和运输机还带一张发光图（`_Emission` × `_Emission_color` × `_Emission_power`）。

**场景的着色器**是这里加的（`tco_materials.build_background`），都当成「不受光 + 烘焙光照」：

```
颜色 = 底色图 × 染色 [× 光照图] [+ 发光图 × 发光颜色 × 强度]        （按显示值算：游戏是 Gamma 空间）
```

| 着色器 | 底色 | 光照图 | 发光 |
|---|---|---|---|
| `Curved/Curved_BG`（赛车场景） | `_diffuse_tex` × `_diffuse_color` | `_light_tex`，在第二套 UV 上 | `_glow_tex` × `_glow_color` × `_glow_velue` |
| `eTOYLab/bg_default` | `_MainTex` × `_Color` | — | `_Emission` × `_Emission_color` × `_Emission_power` |
| `Mobile/Unlit (Supports Lightmap)`、`Legacy Shaders/…`、`Standard` | `_MainTex` × `_Color` | — | — |
| 没有着色器（被剥掉的） | 按名字找到的 `tex_x` | `tex_x_lm` | `tex_x_e` |

- **只认着色器声明的属性**。Unity 的材质会留着它用过的每个着色器的参数，所以材质里有一堆不相干的值。着色器对象的
  `m_ParsedForm.m_PropInfo` 列着它真正声明的属性名，`background_hints` 只用这些：`Curved/Curved_BG` 声明的是 `_glow_velue`
  （拼错的那个才是真名），材质里另有一个没人用的 `_glow_value = 0`。
- 同一张图同时填在底色槽和光照 / 发光槽里时（卡车、金币），后者不算 —— 否则卡车会亮一倍。这是猜的（见「已知限制」）。
- 光照图用第二套 UV：一个材质的所有部件都有 `uv1` 时用它，否则退回第一套（`light_map_uv`）。

### 材质的三种补救

| 情况 | 哪些 | 怎么办 | 记录在 |
|---|---|---|---|
| **只有默认材质** | `fbx_dropship_rig` 的 18 个部件、穹顶的 2 个、`prf_movie_ch01_02` 的 1 个 | 找游戏在别处给**同一个网格**挂的材质（`Game.mesh_materials`）：运输机带贴图的那份在过场 `drt_race_start_asagi` 里 | `borrowed_materials` |
| **着色器和参数被剥掉**，有同名贴图 | 残留布景的 16 个材质 | `mat_x` → `tex_x`、`tex_x_lm`、`tex_x_e`（只认完全同名的） | `guessed_materials` |
| 同上，**没有同名贴图** | `mat_bg_nightsky01`、`mat_movie_ch01_build04 / road01 / road02` | 纯色 | `plain_materials` |

导出时这三种都会在终端里各打一行说明，画廊的卡片上也写着。

- 残留布景的光照图有 6 张是半浮点格式（RGBAHalf），UnityPy 1.25.3 解不了（`bytes must be in range(0, 256)`），
  这里自己解（`float_image`）：数值最大到 7.6，存 PNG 时在 1 处截断。

## 预览、XPS、PMX

- **预览图**：角色是正面平视（Squad 的做法）。别的东西正面看往往只是一条线（桥从桥头看过去），所以 `build_blend.py` 加了
  `--preview-view x,y,z`：从这个方向看，画面按物体实际占的范围取景；比其余部件大 6 倍以上的部件（天空、海面）不参与取景。
  默认方向是前、左、上方（`export_model.PREVIEW_VIEW`）。
- **XPS**：和 Squad 相同。只有一个网格、挂在根上的 prefab（赛道、金币）原本没有任何骨头，现在把根当作一根骨（`Scene.choose_bones`）。
- **PMX**：阿莎姬走标准的 MMD 骨架转换（和 Action Taimanin 的结果一样）。其余的不是人形 —— 原来的转换脚本在找不到 Biped
  骨盆时直接报错，现在走「保持原骨」的路（`export_pmx_blender.py`：蛇身单位用的那条）。**1 米 = 12.5 MMD 单位**，
  所以摩托车、赛道和阿莎姬的大小是配套的。
- 不是角色的模型不渲转台视频，也不渲 PMX 的舞蹈 / 表情检查图（那是让人物转圈、跳舞用的）；PMX 靠转换脚本自己的报告核对，
  XPS 有读回检查图。

## 已知限制

- **场景着色器的公式没有对着编译后的程序核过**，是按槽位和属性名定的；渲出来的结果没有游戏截图可以对照（我没有运行游戏）。
  角色和载具用的是 Action Taimanin 那边核对过的公式。
- **海面是一块纯蓝色**：`etoylab_effect/fx_sea02` 是带波纹、反射的水面着色器，没有还原，只取了它的颜色。
  赛车场景的预览里它占了大半个画面。
- **残留布景的贴图是按名字猜的**，有的材质没有同名贴图（纯色），整体只能算「大致的样子」。同样的布景在 Action Taimanin 里是完整的。
- **221 个原始模型没有导**：218 个只有默认材质（在别处也找不到同一网格的真材质），游戏也不显示。要的话 `python export_model.py --category raw`（没试过全部）。
- **动作没有导**：数据里有 114 段阿莎姬的动作（战斗 55、演出 32、大厅 17、剧情 9、T-pose 1）和 27 段摩托车动作，
  脚本只用了脸部的表情片段。所以没有「骑在摩托上」的姿势 —— 游戏里那是运行时把角色放上去再播动画。
- **粒子特效不导**（赛道段里有几十个）。
- 嘴唇配方和视线角度是 Action Taimanin 那边在阿莎姬上调的，这里沿用；没有在 MMD 本体和 XPS 本体里打开过，检查图是 Blender 读回渲的。
- 手工路线（AssetStudio）没有实测。

## 踩过的坑

- **`UnityPy` 的 `PPtr` 也有 `type` 和 `path_id` 属性**：想用「有这两个属性」判断拿到的是不是已经解开的对象，结果把指针当成了对象。
  改成看有没有 `get_raw_data`。
- **同名的东西不止一个**：表情片段两套、眼球骨和辅助点 —— 都是「按名字建字典，后者盖前者」出的错，而且不报错，
  只是形状键没动或者动得很小。发现办法是看每个形状键「动了多少顶点、最多几毫米」的那张表（`tcollection_scene.py <id> <目录>` 会打印）。
- **运输机渲出来是纯白的**：以为是发光贴图太亮，其实是这个 rig 根本没挂真材质。看 `materials_built` 里的材质名（`Default-Material`）一眼就知道。
- **根上就是网格的 prefab 没有骨头**：XPS 能出，PMX 在算骨架范围时对空列表取最大值而崩溃。
- **清单要带版本号**：分类规则改了以后，旧的 `models.json` 缓存还会被当成有效的（文件没变）。缓存的签名里加了 `LIST_VERSION`。

## 测试

```powershell
python -m unittest discover -s tests        # 18 项：路径 → 类别 / id / 组，场景拆成整体和各个根，脚本头解析，Dynamic Bone 字段表，
                                            # 表情片段的路径适配，着色器家族，只认声明的属性，按名字找回的材质，光照图的 UV，
                                            # 半浮点贴图，非角色不渲转台和舞蹈，画廊的说明和卡片
```
