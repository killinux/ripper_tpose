# Virt-A-Mate (VaM) 脚本说明

把 VaM 1.22 里的 **Look（人物外观，含头发）**、**衣服** 和 **头发** 转成带材质的 `.blend`
（可选 `.glb`）+ 一张三视图预览 PNG。用法与 ROE 的 `export_character_models.ps1` 对齐：`-List` 看有什么，
`-Only <名字>` / `-Index <#>` 转指定的，`-All` 全转。

```
VaM 安装目录
   ├─ AddonPackages\**\*.var      （zip：场景 json、外观预设 .vap、衣服 .vam/.vaj/.vab、morph .vmi/.vmb、贴图）
   ├─ Custom\ / Saves\             （散装的同类内容，当作 local 包）
   └─ VaM_Data\StreamingAssets\    （游戏自带：a_per 基础人体网格、f_mb/m_mb 内置 morph、f_*/m_* 默认皮肤贴图）
        │
        │  ① export_vam_models.py prepare    （AssetStudioModCLI dump → D:\vam_exports\_cache，一次性 ~40s）
        │  ② export_vam_models.py export     （拼装：基础网格 + morph + 皮肤贴图 + 衣服 → model.json/npz/_textures）
        ▼
   D:\vam_exports\looks\<key>\ 或 clothings\<key>\
        │
        │  ③ export_vam_model_blender.py     （Blender 3.6 无头：建网格 → Principled 材质 → 打包贴图 → 渲预览）
        ▼
   blend\<key>.blend + blend\<key>_preview.png
```

`export_vam_models.ps1` 是上面 ①②③ 的一键包装。**不是**从游戏运行时抓模型：全部来自磁盘上的
`.var` 与游戏资源包，VaM 不需要运行。

| 文件 | 作用 |
|---|---|
| `export_vam_models.ps1` | PowerShell 入口（`-List` / `-Only` / `-Index` / `-All` / `-Prepare`） |
| `export_vam_models.py` | 目录扫描、Look/衣服拼装、驱动 Blender、写 manifest |
| `vam_lib.py` | 共享库：`.var` 索引与引用解析、`.vab`（网格 / 发丝）与 `.vmb` 解析、AssetStudio dump 解析、缓存 |
| `export_vam_model_blender.py` | Blender 侧 worker（建网格、材质、打包、预览） |
| `tests/test_vam_lib.py` | 纯 Python 合成 fixture 回归，标记 `VAM_LIB_TEST=PASS` |
| `import_to_vam.ps1` + `vam_duf.py` + `blender_to_duf.py` | **反方向**：把 Blender 网格写成 VaM 能导入的 DAZ `.duf` / morph `.dsf`，见 [§8](#8-反向把-blender-模型导进-vam) |

---

## 1. 环境准备

| 依赖 | 默认路径 / 版本 | 覆盖参数 |
|---|---|---|
| VaM 安装目录 | `E:\tools\vam\vam1.22\vam1.22\1.22` | `-GameRoot` |
| 输出根目录 | `D:\vam_exports` | `-OutRoot` |
| Blender | `D:\Program Files\blender-3.6.15-windows-x64\blender.exe` | `-BlenderExe` |
| AssetStudioModCLI | `E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe` | `-AssetStudioExe` |
| Python 3 | 系统 `python`，需要 `numpy`（`Pillow` 可选，用来判断衣服贴图是否带 alpha） | `-PythonExe` |

第一次导出 Look 时会自动建缓存（`D:\vam_exports\_cache`），也可以先手动跑 `-Prepare`。
缓存内容：`characters.json`（角色名 → 皮肤资源包/性别）、`base_female/male.npz`（合并后的
Genesis 2 人体 + 生殖器网格、材质分组）、`morphs_female/male.npz`（内置 morph 增量）、
`textures\<bundle>\`（按需导出的默认皮肤贴图，是缓存里最占空间的部分，~1.4 GB）。删掉整个
`_cache` 重跑即可重建。

## 2. 快速开始

```powershell
cd E:\code\othercode\ripper_tpose\scripts\vam

.\export_vam_models.ps1 -List                              # 全部：Look / 衣服 / 头发
.\export_vam_models.ps1 -Only ddaamm.hair_long5.3~long5    # 单独导一个发型（引导线 + 头皮）
.\export_vam_models.ps1 -List -Type clothing -Filter gantz # 只看衣服，名字含 gantz
.\export_vam_models.ps1 -Only VAMSOY.Angela.1~Angela~Person
.\export_vam_models.ps1 -Only Angela~Person                # 唯一的子串也行
.\export_vam_models.ps1 -Index 125,550                     # 用 -List 里的 # 号
.\export_vam_models.ps1 -All -Type clothing                # 328 件衣服全转
.\export_vam_models.ps1 -Only 瑶瑶~Person -Format blend,glb -Force
.\export_vam_models.ps1 -Only Angela~Person -Gallery      # 导完顺手重建画廊
python html\make_gallery.py                                # 只重建画廊 html\index.html
```

`-List` 的 key 长这样：`<Creator>.<Package>.<版本>~<场景名>~<Person 原子 id>`（场景里的人）、
`<Creator>.<Package>.<版本>~<预设名>`（外观预设）、`<Creator>.<Package>.<版本>~<衣服名>`。
空格和路径非法字符统一换成 `_`，重名追加 `~2`。`-Only` 先精确匹配 key，不中再按**唯一**子串匹配
key 或显示名（大小写不敏感），多义会报错列出候选。

## 3. 参数

| 参数 | 说明 |
|---|---|
| `-List` | 列出可转条目；`-Type look|clothing|hair|all` 过滤种类，`-Filter <子串>` 过滤名字 |
| `-Only <key...>` | 按 key / 唯一子串选择，可逗号分隔多项 |
| `-Index <#...>` | 按 `-List` 的序号选择（序号跨三类连续编号） |
| `-All` | 全部 Look + 全部有数据的衣服和头发（配合 `-Type` 缩小范围） |
| `-Format` | `blend`、`glb` 或两者，缺省 `blend` |
| `-IncludePoseMorphs` | 保留姿势 morph（握拳、眨眼、耸肩…）；缺省跳过，导出的是静止 A-pose |
| `-NoClothing` | Look 只导人体，不带衣服 |
| `-NoHair` | Look 不带头发 |
| `-NoAttachments` | Look 不带挂在人物骨骼上的 CustomUnityAsset（网格头发、首饰、武器） |
| `-NoPreview` | 不渲染预览图 |
| `-ValidateOnly` | 只拼装 + 在 Blender 里建网格/材质检查，不写产物 |
| `-Force` | 覆盖已有产物（缺省时 `.blend` 与预览图都在的条目 SKIP） |
| `-ManifestPath` | 自定义 manifest；多进程并行时每个进程各给一个 |
| `-Prepare` | 只建缓存 |
| `-Gallery` | 导出后（或单独用）重建画廊 `html\index.html`：每个条目一张缩略图 + 用了哪些衣服 / 头发 / morph / 附件、告警、blend 路径，可按种类过滤、搜索 |

## 4. 产物

```text
D:\vam_exports\looks\<key>\model.json, model.npz     # 给 Blender 的中间产物（顶点/面/UV/材质表）
D:\vam_exports\looks\<key>\_textures\                # 该 Look 用到的全部贴图（从 .var 里解出）
D:\vam_exports\looks\<key>\_attachments\<名>\         # CustomUnityAsset 解出的 FBX + 贴图（AssetStudio splitObjects）
D:\vam_exports\looks\<key>\blend\<key>.blend         # 贴图已打包
D:\vam_exports\looks\<key>\blend\<key>_preview.png   # 3/4 + 正面 + 头部
D:\vam_exports\looks\<key>\blend\glb\<key>.glb       # 仅 -Format glb
D:\vam_exports\clothings\<key>\...                   # 单件衣服同结构（预览只有 3/4 + 正面）
D:\vam_exports\hairs\<key>\...                       # 单个发型同结构
D:\vam_exports\vam_models_manifest.json              # 全量清单，-Only 时按条目合并
D:\vam_exports\_gallery\thumbs\                       # 画廊缩略图（页面本身在 scripts\vam\html\index.html）
```

manifest 每条带 `notes`：角色/性别/皮肤包、morph 统计（`applied` / `skippedPose` / `missing`）、
用了哪些衣服、哪些衣服因依赖包缺失没找到（`clothingMissing`）、头发（`hair`，含引导线数与丢弃数）
与没找到的头发（`hairMissing`）、是否因衣服的 `disableAnatomy` 隐藏了生殖器（`anatomyHidden`）、
挂在骨骼上的 CustomUnityAsset（`attachments`，`名 -> 骨骼 (n fbx)`）与被跳过的
（`attachmentsSkipped`：碰撞体/粒子/灯光、包缺失、包里没网格）、哪些皮肤贴图槽回退到
默认皮肤（`defaultTexturesUsed`）、找不到的贴图（`missingTextures`）；Blender 侧再补
`objects` / `materials` / `packed_images` / `untextured_slots`。

`untextured_slots` 里出现衣服自己的纯色材质（VaM 里很多眼影/眼膜/内衬只给 `Diffuse Color`
不给贴图）是正常的；出现 `Face` / `Torso` / `Limbs` 这类人体槽才是问题。

### 画廊

`python html\make_gallery.py`（或导出时加 `-Gallery`）读清单，把每张预览缩成 720 px 的 JPEG 写到
`D:\vam_exports\_gallery\thumbs\`，生成 `scripts\vam\html\index.html`：按 Look / 衣服 / 头发过滤、
搜索名字 / 包名 / 衣服 / morph、告警（缺依赖、缺贴图、人体槽无贴图）与备注（回退默认皮肤、跳过的附件）
悬停可见、blend 路径一键复制。页面里只有 `file://` 链接和文字，仓库不进任何游戏图片。

## 5. 它是怎么做的（格式说明）

### `.var` 与引用

`.var` 就是 zip，文件名 `Creator.Package.版本.var`。场景里引用资源的写法有三种：
`SELF:/Custom/...`（本包）、`Creator.Package.latest:/Custom/...`（同名包里版本最高的）、
`Creator.Package.3:/...`（钉死版本）；裸的 `Custom/...` 先在本包找，再去游戏目录的散装
`Custom\` 找。`AddonPackages` 下的子目录（`Demo\`、`uug\`…）一并扫描，同一 id 的重复包只算一次。
VaM 的 JSON 带尾逗号，所有 JSON 都走 `lenient_json_loads`。

### Look = 基础人体 + morph + 皮肤贴图 + 衣服

- **基础人体**来自游戏包 `a_per` 里的 `DAZMergedMesh`（MonoBehaviour，用 AssetStudioModCLI
  `--assembly-folder` 带类型树 dump 成文本再解析）：女 = Genesis2Female 21556 顶点 +
  `Genitalia-default` 1452；男 = 21556 + 男生殖器 1325 + `AG_G2_Zeroed_F` 89。合并顺序就是
  「身体在前、graft 在后」，已用逐顶点比对确认。
- `geometry.character`（`Female Custom`、`Kayla`、`Male 4`…）通过 `DAZCharacter` 表决定性别和
  默认皮肤包（`f_c`、`f_rky`、`m_4`…）。
- **morph**：`.vmi` 是 JSON 元数据，`.vmb` 是二进制 `int32 count + {int32 顶点号, float xyz}[count]`；
  `female/` 目录的作用于身体 0..21555，`female_genitalia/` 的作用于 graft 段。创作者用插件
  保存的 Body morph 常带 21556..26469 的越界索引，全部是 ~1e-5 的噪声，直接丢弃。
  内置 morph（场景里只写名字，如 `Shoulders Shrug`）从 `f_mb`/`m_mb` 的 `DAZMorphSubBank`
  dump 出来，用 **displayName** 匹配（内部名是 `CTRLShouldersShrug`）。姿势 morph 按
  `isPoseControl` **或** 分组名以 `Pose Controls` 开头判定——VaM 自己的 flag 对 CTRL 系不可靠。
  `.vmi` 里的 `formulas`（改骨骼位置）忽略，导出的是静态网格。
- **皮肤贴图**：`textures` storable 的 `faceDiffuseUrl` / `torsoNormalUrl` … 四区（face / torso /
  limbs / genitals）× 五种（Diffuse / Specular / Gloss / Normal / Decal）。材质 → 区域的对应表来自
  `f_c` / `m_c` 里的 `DAZCharacterTextureControl`（女：face = Nostrils/Lips/Face；torso 含 Head、
  Ears、Neck、Hips、Torso、Nipples；limbs = Legs/Toenails/Fingernails/Hands/Shoulders/Forearms/Feet；
  genitals = defaultMat）。没给的槽回退到该角色默认皮肤包 `<bundle>_mat` 里的贴图，眼睛回退到
  `p_eye_mat`，嘴/眼再缺则回退到 `f_c_mat` / `m_c_mat`。默认贴图名各家一套
  （`V5BreeHeadM`、`Kayla FaceD (B)`、`Tina Face D Nude`、`M5PhillipFace01S`…），
  `classify_texture_name` 做容错分类，变体（Browless、MU01、(B)）排后。
- Decal 贴图（`*DecalUrl` / `customTexture_DecalTex`）按自身 alpha 叠在漫反射上再乘 `Skin Color`；`Skin Color` 按 HSV 转 RGB 乘在 Base Color 上；`Cornea` / `EyeReflection` / `Tear` 做成透明玻璃；
  `Hidden`（被 graft 遮住的面）直接删掉。
- **衣服**：`.vam`（元数据）+ `.vaj`（材质参数 JSON）+ `.vab`（网格二进制，见下）。贴图键
  `customTexture_MainTex/_BumpMap/_SpecTex/_GlossTex/_AlphaTex/_DecalTex`，值可能是
  `SELF:/…`、别的包、`./tex/x.png`、裸文件名、`NULL`。场景里同 id 的 storable（如
  `BooMoon:Lips LayerMaterialFace` 的 `Alpha Adjust`、`Diffuse Color`）覆盖 `.vaj` 默认值。
  衣服文件里的顶点是创作者**制作时那具身体**上的位置——很多人是在自己 morph 过的角色上包裹的
  （Cloud 的衣服套在基础男体上时上衣缩进胸里、裤子鼓成灯笼），所以不能拿「基础体→morph 体的位移」
  去搬。VaM 自己也不用这些顶点：`.vab` 里 DAZMesh 后面跟着 **DAZSkinWrapStore**（布局见下），把每个
  顶点记成「最近的皮肤三角形 + 该三角形局部坐标系里的偏移」，运行时按当前皮肤重建。这里照做：
  `顶点 = v1 + N·(f0 + surfaceOffset) + T1·f1 + T2·f2`，N 是三角形朝外的面法线，T1 = 质心 − v1，
  T2 = N × T1（都不归一化，系数按 |T|² 计）。328 件衣服在标准体上重建，做在标准体上的那些误差
  0.2–0.3 mm（常数 0.3 mm 是 VaM 默认 surfaceOffset 烤进去的）。`surfaceOffset` 取 `.vaj` 的
  `<uid>WrapControl`，场景同名 storable 覆盖。包裹坐标系只是一个几毫米宽的皮肤三角形，切向系数以它为单位：
  贴在皮肤上的衣服系数中位数都 ≤ 0.8，而**悬空**的配件（牛仔帽 12.6、圈耳环 10.9、飘带 15.8、离脚的鞋 5.3）
  要 4.7 以上——那里坐标系已无意义，三角形的一点点差别就把顶点甩出几厘米、整件搅碎。所以系数中位数超过 3
  的条目按文件里存的位置直接用（配合位移搬运），**除非**那个位置根本不在身体上：圈耳环存在离身体 0.94 m 处、
  脐环 0.32 m、AWG 高跟鞋的一个部件在脚下 0.28 m，只有包裹数据知道它们该在哪，这些仍用包裹重建（判据：
  离皮肤中位数 > 0.15 m；正常配件都在 0.09 m 以内）。没有包裹数据的条目也走位移搬运（清单里标
  `displacement fit`）。离皮肤超过 1–4 cm 的**松散部位**（裙摆、灯笼裤、袖口）
  逐三角形重建会碎成锯齿（相邻布料顶点各跟一条腿；VaM 靠布料模拟抹平），这里改为保留制作时的形状：
  松散顶点按最近的若干贴身顶点的位移加权平均移动，1–4 cm 之间线性过渡。贴合后再做一次**穿模保护**：离皮肤不足 1 mm
  或陷进皮肤的衣服顶点沿皮肤法线推到 1 mm（VaM 靠布料碰撞做这件事，这里没有物理）。
  衣服 `ItemControl` 里 `disableAnatomy` 为真（裤子、内裤常见）时，和 VaM 一样隐藏生殖器 graft、
  露出被它盖住的原生裆部面（合并网格里这些面停在 `Hidden` 材质上，挂回 `Hips` 材质）。
  注意 DAZ/VaM 的多边形是从外面看**顺时针**绕的，按右手定则算出的顶点法线朝内（`outward_normals`
  取反），皮肤层外推、头皮帽外推、包裹朝向都靠它。
- **头发**：`.vab` 是 `RuntimeHairGeometryCreator` 存储（布局见下）——每个头皮顶点一条**造型后的引导线**
  （20–50 个点，米制，未 morph 的标准体空间）。VaM 运行时按 `hairMultiplier × curveDensity` 在引导线
  周围随机生成发丝，这里退化成「每条引导线 + 最多 7 条随机偏移的子发丝」写成 Blender 曲线（POLY
  样条 + bevel 0.5–1.2 mm），颜色取 `.vaj`/场景 `<uid>Sim` 里 `rootColor` 与 `tipColor` 的均值。
  引导线先随身体 morph 位移（最近 4 个身体顶点的反距离平方位移搬运；引导线没有包裹数据）。从未造型的引导线仍是沿头皮法线的一条直线
  （会像铁丝一样横伸出头），检测「≥15 cm 且笔直 且不是向下垂」就丢弃——垂直向下的长直发保留。
  发丝下面加同名**头皮帽**（`SoleilScalp`/`UdaneScalp`/`KrayonScalp`/`LeytonScalp`/`OmriScalp` 对应
  `a_per` 里的 922/868/1948 顶点小网格，材质只有 `scalp`，缓存里 `scalp_*.npz`），颜色取
  `<uid>…ScalpMaterial…` 的 `Diffuse Color`。少数发型（眉毛、`xxx scalp` 类）本身就是 DAZMesh 网格，
  按衣服处理。`.glb` 导出前曲线先转网格。
- **CustomUnityAsset 附件**：不少 Look 的头发/首饰/武器不是 VaM 衣服，而是 Unity 资源包（`.assetbundle`）
  做成的 `CustomUnityAsset` 原子，用 `linkTo: "<Person>:<骨骼>"` 挂在人物骨骼上（xnpvv 的 Tifa 头发、
  JackyCracky 的 Tifa 耳环、maiden_queen 的头发/王冠/项链/腰链/手镯、Cloud 的大剑）。导出时用
  AssetStudioModCLI `-m splitObjects` 把资源包拆成 FBX + 贴图，在 Blender 里以 `global_scale=100`
  导入（AssetStudio 把米制数据写进 cm 单位的 FBX），去掉导入器生成的骨骼末端空物体和重复的
  无蒙皮副本，材质接上贴图 alpha 用 HASHED。一个资源包里常有创作者的**整套**东西（maiden_queen 的包里
  同时有王冠、两只手镯、臂环），原子的 `assetName` 指明用哪个 prefab，按文件名筛出来——不筛就会把整套叠在
  一个位置。`assetName` 指向 `.unity` 场景时整包导入（VaM 也是整场景加载）；干脆没写且包里不止一个对象则
  跳过该原子（无从判断该显示哪个，T.迦自 的 Fei 原子就是个 5 顶假发的库）。**摆放**：场景里存的是资产的世界变换，而人物有姿势，
  要换算成 `T_静止 = T_骨骼静止 · inv(T_骨骼姿势) · T_资产`。`T_骨骼静止` 来自 `a_per` 的 `DAZBone`
  （`_worldPosition` / `_worldOrientation`，morph 改过的关节用场景里存的局部位置）。`T_骨骼姿势`
  **不能直接用控制点**：VaM 给每个控制点都存了相对人物容器的 `localPosition/localRotation`，但控制点
  只是用户放的目标——只有 Off 状态的控制点跟着骨骼走（位置、旋转都精确），On / Comply / Hold /
  ParentLink 的控制点物理未必追得上（xnpvv 场景里头部控制点离真正的头骨 10 cm、5.6°，头发最初就是
  因此歪的）。JSON 只写与默认值不同的状态：默认 On 的是 hip / chest / head / 双手 / 双脚控制点，其余
  默认 Off。于是取链上**最深的 Off 控制点**当锚点（没有就用 hip 控制点，再没有才从人物根节点算），
  然后沿链往下：某骨骼的控制点若离上一帧正好一段骨长（±3 cm）就认为物理追到了、直接采用控制点，
  否则用场景里存的骨骼旋转（Unity ZXY 欧拉表示的**完整**局部旋转，含静止朝向；在 179 对 Off 父子
  控制点上验证，平均误差 0.2° / 0.1 mm）从上一帧推一步。两条规则缺一不可：xnpvv 的头部控制点离颈部
  0.16 m（骨长 0.09 m）、根本追不到，只能靠骨骼旋转推；maiden_queen 全部控制点都是 On 且链是刚性的，
  但存的骨骼角度是预设写进去的两位小数、与实际姿势差 40°，只能信控制点。`linkTo` 指向控制点本身
  （如 `rHandControl`）时资产跟的是控制点，直接用控制点的变换。名字或路径含
  collider / fluid / particle / light / focus 的原子跳过。
- **皮肤层**（口红层、眼影、眼膜、指甲等）是贴在皮肤上方零点几毫米的壳。检测到 ≥60% 顶点离身体
  < 2 mm 就标成 skin layer：材质用 `BLEND`（EEVEE 的 HASHED/CLIP 深度预通道会和皮肤 z-fight，
  在脸上渲出黑色蕾丝状噪点，实测即使 alpha 恒为 0 也会），并沿法线外推 0.4 mm。

### `.vab`（DAZMesh DynamicStore）布局

全部小端，字符串是 .NET `BinaryWriter` 的 7-bit 长度前缀 UTF-8：

```
"DynamicStore" "1.0" "DAZMesh" "1.0"
name, nodeId, sceneNodeId, geometryId              4 个字符串
int numVerts, Vector3[numVerts]
int numMaterials, string[numMaterials]
int numPolys, {int material, int count(3|4), int[count]}[numPolys]   基础面
{int material, int count, int[count]}[numPolys]                       UV 面（索引 UV 顶点）
int numUVVerts, Vector2[numUVVerts]
int numMapped (= numUVVerts - numVerts), {int uvVert, int baseVert}[numMapped]
... 之后是 skin-wrap / 布料模拟数据，静态导出不需要
```

本机 119 个 `.var` 里 372 个衣服 `.vab` 全部按上面的布局解析通过（每一步都有一致性断言，不对就报错而不是出乱模）。

### `.vab` 里的 DAZSkinWrapStore

DAZMesh 段之后（中间隔着一小段用途不明的整数三元组）依次是 `"DAZSkinWrap"`、`"Normal"`、然后：

```text
string "DAZSkinWrapStore", string "1.0"
int count                                   # = numUVVerts（按 UV 顶点存，前 numVerts 条对应基础顶点）
{ int closestTriangle,                       # 皮肤三角形序号（每个四边形拆成 (0,1,2)(0,2,3)）
  int v1, int v2, int v3,                    # 该三角形的三个皮肤顶点（合并人体网格的下标）
  float f0, float f1, float f2,              # 位置：N·f0 + T1·f1 + T2·f2（见上）
  float n0, float n1, float n2 }[count]      # 该顶点的法线在同一坐标系里的分量
string "MaterialOptions" ...                 # DAZSkinWrapMaterialOptions，之后是 Sim 数据
```

三个顶点的顺序不保证一致的绕向，N 的朝向要用皮肤顶点法线校正；`surfaceOffset = -1` 的几件
（BooMoon 的牙齿 / 穿孔）重建不出来，原因不明，导出时也只是它们不对。

### 头发 `.vab`（RuntimeHairGeometryCreator）布局

```
"DynamicStore" "1.0" byte 1 "RuntimeHairGeometryCreator" version("1.0"|"1.1") scalpName
int segments, float segmentLength, byte, int numScalpVerts, byte[numScalpVerts] 排除掩码
int numScalpVerts, {int vertexIndex, int numPoints(0|segments), Vector3[numPoints]}[numScalpVerts]
int n, int[n]                      （头皮三角索引之类，未用）
int numPoints, Vector3[numPoints]  （上面所有点的重复副本）
... 逐点权重 / 刚度绘制等（未用）
```

本机 197 个发丝文件全部解析通过，另有 23 个头发 `.vab` 是 DAZMesh（眉毛、头皮帽）。

### 坐标

VaM/Unity：米，Y 向上，+Z 朝前，+X 是角色的**右**（用脚尖方向和脸部 UV 左右侧验证过）。
转 Blender：`(x, y, z) → (-x, -z, y)`，这是一次镜像，所以面的顶点顺序同时反转。

## 6. 已知限制

- **头发是近似**：只有创作者造型的引导线是真实数据，发丝密度、随机卷曲、物理下垂都没有；预览里
  看起来比 VaM 稀疏、更"束状"。想要更密可以在 Blender 里把曲线转粒子毛发，或改 `HAIR_CHILDREN_MAX`。
- **CustomUnityAsset 附件是按静止姿势重摆的**：手上的武器、手镯会跟着手到 T-pose 的位置，方向按保存
  时相对关节的关系保留；控制点既没追到、存的骨骼角度又是陈旧预设值的骨骼（maiden_queen 的右前臂）
  只能按陈旧角度推，落点可能有几厘米偏差。
  资源包里的 Unity 材质只接了漫反射/法线/alpha，Shader 特效（金属度、发光）不还原。
- **没有骨架**：只有静态网格（DAZSkinV2 里有权重，以后可加）。
- 姿势 morph 缺省跳过；表情/手势要 `-IncludePoseMorphs`。
- 场景依赖的包没装（`clothingMissing`）或 morph 缺失（`morphs.missing`）时照常导出，只是少那件/那点形变；
  `Breast Impact*` 这类物理驱动 morph 不在 morph 库里，值也很小，可忽略。
- 衣服没有布料物理：VaM 里靠模拟 / 碰撞撑开的部位（裙摆、披风）保留的是制作时的形状，跟着髋部 / 四肢平移，1 mm 穿模保护
  之外偶尔还有几个皮肤小点透出来；`smoothIterations`、`additionalThicknessMultiplier` 没有实现。
- Decal 贴图按其 alpha 叠在漫反射之上（JPEG Decal 等于整张替换——mai.tifa8K 就是把 8K 皮肤放在 Decal 槽里）。
- 默认眼睛贴图按角色皮肤包挑第一张，可能和 VaM 里选的不同。

## 7. 测试

```powershell
cd E:\code\othercode\ripper_tpose\scripts\vam
python tests\test_vam_lib.py        # 纯 Python，合成 .var/.vab/.vmb/dump fixture，末行 VAM_LIB_TEST=PASS
python tests\test_vam_duf.py        # 反方向的 DSON 写入器，末行 VAM_DUF_TEST=PASS
python tests\test_vam_items.py      # 直接写物品（§9）：包裹 / 朝向 / morph / 脸部工具，末行 VAM_ITEMS_TEST=PASS
```

`test_vam_duf.py` 除了合成 fixture，还会在能找到 VaM 安装时拿 `VL_13.Lashes_2.1` 里那对
真实 DUF / VAB 复核坐标换算，并要求 `check_duf` 接受 VaM 自己接受过的文件。
`test_vam_items.py` 在能找到 VaM 安装时，会把前 60 个不带布料模拟的 `.vab` 用 `write_vab` 重写，
要求逐字节一致（全量 224 件是手动跑的）。

集成验证（2026-09-05，本机 119 个包）：`Angela`（Female Custom + 4 件皮肤层）、
`Cloud`（Male 4 + 6 件衣服）、`Preset_Alivia`（Kayla 皮肤全默认贴图，148 个 morph）、
`瑶瑶`（Lexi 皮肤，中文包名，女仆装 5 件 + 3 层皮肤层）、单件 `Cheongsam set`，以及 21 个
Tifa Look（JackyCracky 16 + mai 3 + xnpvv + Womb Fantussy；JackyCracky 的 4 段发丝头发 6.9k 根曲线）
均 PASS，单个 Look 8–160 s（头发多的最慢）。CustomUnityAsset 附件用 xnpvv Tifa（网格头发，人物根
节点转了 270° 且臀部控制点 Off）、JackyCracky Tifa（耳环）、maiden_queen（7 件首饰/头发）、
Cloud（右手大剑）核对过落点。xnpvv 的头发按头部控制点摆时偏了 4–10 cm，改成从 Off 控制点锚定的
骨骼正向运动学后，正 / 侧 / 顶视图都贴合头皮。衣服贴合改用 DAZSkinWrapStore 后 Cloud 的上衣 / 裤子 /
腰带贴身、生殖器按 `disableAnatomy` 隐藏，27 个条目全部重导并重建画廊。

---

## 8. 反向：把 Blender 模型导进 VaM

VaM 自己没有网格导入，但游戏内带一个创作器 `DAZRuntimeCreator`（以一件特殊"衣服"/"头发"的形式
挂到 Person 上，也就是 Clothing Creator / Hair Creator）。它**只吃 DAZ 的 `.duf` 场景文件**，导入后
自己算贴身（`CreateDAZSkinWrap`，算出来的正是 [§5](#vab-里的-dazskinwrapstore) 那个 DAZSkinWrapStore），
最后 Store 成 `.vam/.vaj/.vab`。所以从 Blender 进 VaM 的最短路径就是直接写 `.duf`——**不需要 DAZ
Studio，也不需要 Unity**。

### 三个入口

| 想导的东西 | 入口 | 代价 |
|---|---|---|
| 贴身衣服、网格头发、跟着身体走的配件 | 游戏内 Clothing / Hair Creator ← `.duf` | `import_to_vam.ps1`，无额外依赖 |
| 道具、场景物件、带自己动画或 shader 的东西 | CustomUnityAsset ← `.assetbundle` | 必须 Unity **2018.1.9f1**（从 `VaM_Data\globalgamemanagers` 读出的版本；本机未装） |
| 体型 / 表情 morph | `Custom\Atom\Person\Morphs\<性别>\` ← `.dsf` | `import_to_vam.ps1 -Morph` |

整个角色如果不是 Genesis 2 拓扑，VaM 里没有"换一具身体"这回事：要么整体当 CUA 摆件（需要 Unity），
要么拆成"衣服 + 体型 morph"两部分走上面两条路。

### 用法

```powershell
cd E:\code\othercode\ripper_tpose\scripts\vam

# ① 先要参照人体：VaM 的贴身是对着"基础"Genesis 2 身体算的，衣服必须照它建模
.\import_to_vam.ps1 -Reference
#    -> D:\vam_imports\_reference\Genesis2Female.blend （23008 顶点，带 UV）
#       D:\vam_imports\_reference\Genesis2Male.blend

# ② 建好模后导出 .duf（默认把选中的物体合成一件；-Separate 则一物体一件）
.\import_to_vam.ps1 -Source D:\work\jacket.blend -Name jacket
.\import_to_vam.ps1 -Source D:\work\jacket.obj -Install clothing -Author me
#    -Install 直接写进游戏目录 Custom\Clothing\Female\<Author>\，创作器的文件浏览器能看到

# ③ 体型 morph：复制参照人体，只改顶点位置（不能增删顶点），然后
.\import_to_vam.ps1 -Source D:\work\belly.blend -Morph "Belly Out" -Install morph
#    -> Custom\Atom\Person\Morphs\female\<Author>\Belly Out.dsf，重启 VaM 后编译成 .vmi/.vmb
```

游戏里：给 Person 加上 Clothing Creator（或 Hair Creator）→ `dufFile` 浏览到这个 `.duf` →
**Import** → 需要的话 `CreateClothSim` / `CreateHairSim` → 填 `storeFolderName` / `storeName` →
**Store**（"Create New Item"）。创作器自己会提醒顶点数：**包裹 < 50000，布料模拟 < 25000**，
`check_duf` 也会提前警告。

### 从别的游戏 / 别的 DAZ 世代搬东西过来

外面扒来的角色不会长在 VaM 的身体上：单位不同、身高不同、体型不同，而且经常整只角色就是**一个网格**，
身体和每件衣服只靠材质区分（MMD 转出来的尤其如此）。三个参数处理这三件事：

```powershell
.\import_to_vam.ps1 -Source "E:\Downloads\Fiona 18\Fiona 18 V1.blend" -Name FionaDress `
    -Objects "Fiona 18 V1_mesh" -Materials "+Dress.1" `
    -Align -AlignUsing Body,Legs,Face -Lift 0.004 -Install clothing -Author Fiona
```

- **`-Materials`**：只导这些材质槽的面，并把没用到的顶点丢掉。227079 顶点的整只角色里，裙子那 6519 个
  就这么挑出来。
- **`-Align`**：把网格缩放平移到 VaM 的基础人体上。只解**等比缩放 + 平移**，不解旋转——两具身体都站着、
  朝向相同，多给一个旋转自由度只会让错误的对应关系把人放倒。先按身高和脚底对齐，再做几轮最近点重拟合
  （锁死旋转的 scaled ICP）。
- **`-AlignUsing`**：拟合是拿**源角色自己的皮肤**去对 VaM 的身体解的，不是拿衣服解的——衣服要跟着穿它
  的人走。**姿势不一样的部位必须排除**：源模型多半是 A-pose，VaM 基础人体是 T-pose，把手臂算进去会把
  整个人拖歪。
- **`-Lift`**：VaM 穿衣服时身体照样画，而别人的体型到处差个一两厘米，所以贴身处会被身体顶穿。这一步把
  扎进身体的顶点沿法线推回表面外。

**实测（Fiona 18，Genesis 8 转 MMD）**：等比 0.0866（MMD 单位→米），躯干/腿/头对 G2F 的残差中位
**17.3 mm**——就是 G8F 和 G2F 的体型差，衣服完全吃得下。手臂则是中位 **326 mm**：A-pose 对 T-pose。
裙子有 **15.1% 的顶点原本扎在身体里**（最深 40 mm），`-Lift 0.004` 之后为 0。

姿势差异只影响**长在那根骨头上的东西**：把手臂摆成 T-pose 后，手套从 232.6 mm 降到 9.4 mm、臂环
33.4 → 14.1 mm，而裙子的顶点只动了 0.3 mm（它根本没绑手臂骨）。所以要么在 Blender 里把源模型摆成
T-pose 再导手臂上的件，要么就只导躯干/头/腿上的件。脚同理：为高跟鞋踮起的脚配的鞋，套在 VaM 的平脚上
一定露脚。

**搬不过来的**：皮肤贴图（VaM 的 Person 是 Genesis 2，UV 完全不同）、还有**脸**。把 G2F 顶点最近点投影
到外来角色表面听着像能做体型 morph，实测会把脸投烂——位移看着很小（中位 22.9 mm）但那是纯剪切，鼻子的
边长比 p99 到 24.8 倍、嘴唇 16.2 倍，8204 个头部面里 4.68% 法线翻转，侧面渲出来鼻子直接没了。原因是
**对应关系**不对而不是目标面不全（把口腔、眼球补进目标只会更糟）。只有躯干+腿那部分能用：头
（z 1.50–1.60）、手臂（|x| 0.145–0.21）、脚（z 0.09–0.17）用 smoothstep 衰减冻住，剩下 6570 个顶点，
边长比 p99 1.465、只有 37 个面翻转，渲出来是个正常身体。要真做脸得上带地标的 wrap 变形，最近点不够。（后来按地标做成了，见 [§9](#9-直接写-vam-物品把游戏角色整套搬进来bring_to_vampy)。）

### DSON 写了什么，怎么确定的

不是猜的，是拿 VaM 自己吃过的文件标定的。`VL_13.Lashes_2.1` 这个包里，创作者把源文件
`Lashes_Skin_subd.duf` 和它产出的 `.vab` 一起打包了，正好是一对输入输出（392 顶点 / 282 四边形）：

```
VaM 顶点 = ( -x, y, z ) * 0.01   ← DUF 里的顶点（DAZ 用厘米）
```

逐顶点比对最大误差 **1.5e-07**（float32 精度），**顶点顺序、面顺序、绕序、四边形、UV 全部 1:1 保留**。
换算到 Blender 就是干净的右手 Z-up → Y-up 旋转 `DAZ = (100·bx, 100·bz, -100·by)`，**没有镜像，
面朝向直接沿用**（DAZ 和 Blender 一样是从外看逆时针；VaM 自己的网格之所以是顺时针，就是上面那次
镜像造成的）。整条链路做过闭环：缓存里的基础人体 → Blender → `.duf` → 换算回来，23008 个顶点最大
误差 5e-07 米。

一个自包含的 `.duf` 长这样（VaM 的 `DAZImport` 用 SimpleJSON 读，只认这几段；任何解析不到的
`url` 都会变成运行时的 "Could not find ..." 报错，所以 `check_duf` 会先把引用全查一遍）：

| 段 | 内容 |
|---|---|
| `geometry_library[0].vertices` | `{count, values:[[x,y,z],…]}`，厘米 |
| `.polylist` | `{count, values:[[面组号, 材质组号, v0, v1, v2, (v3)],…]}`，5 项=三角形，6 项=四边形 |
| `.polygon_material_groups` | 材质名列表，polylist 第二列索引它 |
| `uv_set_library[0].uvs` | 前 `vertex_count` 个是每顶点默认 UV，接缝复制追加在后面 |
| `.polygon_vertex_indices` | `[面号, 顶点号, uv号]`，**只给偏离默认的角点写一条** |
| `node_library` / `scene.nodes` | 一个节点 + 它的实例，`#id` 本地引用 |
| `material_library` / `scene.materials` | 每个材质组一个槽（`groups: ["名字"]`），贴图在 VaM 里再挂 |

morph 的 `.dsf` 更简单，和装好的包里那些逐字段同构（比对过 `MacGruber.Life.13` 的
`Breathing_Chest.dsf`）：`modifier_library[0].morph = {vertex_count: 21556, deltas: {values: [[顶点号,
dx, dy, dz], …]}}`，`parent` 指向 `Genesis2Female.dsf#GenesisFemale-1`（男性是
`Genesis2Male.dsf#Genesis2Male`），`group` 决定它在 VaM 形态列表里的位置。**21556 是身体顶点数，
生殖器嫁接网格排在它后面、morph 管不到**，`-Morph` 会把落在嫁接区的改动数出来警告。

### 这条路还缺什么

- **贴图不写进 DUF**：`material_library` 只建材质槽，漫反射/法线在 VaM 的材质页里挂。多材质是支持的
  （按 Blender 的材质槽分组），创作器的 `combineMaterials` 关掉就能分开调。
- **布料模拟参数**要在游戏里设（`CreateClothSim`、`clothSimNearbyJointsDistance` 等），脚本不碰。
- **发丝头发**（strand hair）走 Hair Creator：DUF 里给一块头皮网格，进游戏后刷选头皮顶点再
  `CreateHairSim`，这一步是交互的，没法脚本化。
- **n-gon 会被三角化**（DSON 最多四边形），会在结果里报数量。
- CUA 那条路要 Unity 2018.1.9f1，本机没装，暂时没做。

## 9. 直接写 VaM 物品：把游戏角色整套搬进来（`bring_to_vam.py`）

§8 的 `.duf` 只是创作器的**输入**：游戏里还得 Import + Store，才会出现在衣服列表里。这一节换个做法：
直接写出 VaM 自己存的 `.vam / .vaj / .vab`，放进 `Custom\` 就能在衣服、头发列表和外观预设里看到，
完全不经过创作器。第一个例子是 Vindictus: Defying Fate 的 Fiona，素材是我们自己从游戏里导出的
`Fiona.blend`（UE5 / MetaHuman 骨架，四件盔甲 + 头发 + 脸）。

### 用法

```powershell
cd E:\code\othercode\ripper_tpose\scripts\vam
$blender = "D:\Program Files\blender-3.6.15-windows-x64\blender.exe"

# ① 从 .blend 导出蒙皮网格、骨骼、权重、材质；眼球是程序化材质，顺手把它的底色烘成一张图
& $blender -b E:\game_export\Vindictus\Fiona\blend\Fiona\Fiona.blend --factory-startup `
    -P blender_dump_skinned.py -- D:\vam_imports\FionaDF\_src --bake MI_Fiona_Face01_EyeBall

# ② 拟合、写物品 / morph / 贴图 / 预设，渲预览和缩略图；--install 同时拷进 VaM
python bring_to_vam.py --profile fiona_df --install
```

进游戏：选一个女性 Person → Appearance → Presets → `VindictusDF` → **`Preset_Fiona DF`**。每件东西也能在
Clothing / Hair 列表里单独找到（作者 `VindictusDF`）。

产物在 `D:\vam_imports\FionaDF\vam\Custom\` 下，`--install` 原样拷到 VaM 的 `Custom\`：

| 路径 | 内容 |
|---|---|
| `Clothing\Female\VindictusDF\Fiona DF Armor Top` / `Armor Bottom` / `Gauntlets` / `Boots` | `.vam/.vaj/.vab` + 贴图 + 缩略图 |
| `Hair\Female\VindictusDF\Fiona DF Hair` | 网格头发（HairFemale） |
| `Atom\Person\Morphs\female\VindictusDF\Fiona DF Body` / `Fiona DF Head` | `.vmi/.vmb` |
| `Atom\Person\Textures\VindictusDF\Fiona DF\` | 脸部漫反射 `Fiona DF Face D.png`、眼睛 `Fiona DF Eyes D.png` |
| `Atom\Person\Appearance\VindictusDF\Preset_Fiona DF.vap/.jpg` | 外观预设 |

`D:\vam_imports\FionaDF\_preview\` 是 Blender 按 VaM 的规则重建出来的样子（物品从 `.vab` 的包裹记录重建、
两个 morph 打开、贴上预设里的脸和眼睛）：全身正/侧/背、头、脸三个角度、脚/手/胸特写。

换角色：在 `PROFILES` 里加一项——每件衣服是哪个物体、要排除哪些皮肤材质、离皮肤留多少间隙，以及脸的
物体和材质名。骨架目前只认 UE5 / MetaHuman 的骨骼名（`rig: ue5`）。

### 物品格式（逐字节验证过）

- **`.vab`** = DAZMesh（顶点、UV、接缝映射表、多边形）+ `"DAZSkinWrap" "1.0" "Normal"` +
  `"DAZSkinWrapStore" "1.0"`（每个 UV 顶点一条 40 字节记录：三角形号、三个顶点号、6 个系数）+ `.vaj` 里每个
  `DAZSkinWrapMaterialOptions` 组一段 `MaterialOptions` 面索引 + 结尾一个字节（1 = 后面跟布料模拟数据）。接缝映射表
  是**三元组** `{基础顶点, UV 顶点, 首个多边形}`（§5 的解析按二元组读，碰巧不影响，因为它按标记找包裹段）。
  `vam_items.write_vab` 把本机装的 **224 件**不带布料模拟的物品全部重写得**逐字节一致**。
- **包裹记录**：位置 = v1 + N·f0 + T1·f1 + T2·f2（N 为朝外单位法线，T1 = 重心 − v1，T2 = N × T1，系数按 |T|² 归一），
  法线的三个系数用同一框架。三角形编号是 Unity 子网格的顺序：多边形按材质稳定排序，四边形拆成 (0,1,2)(0,2,3)。
  我们选的最近三角形总是不比 VaM 自己选的远，重建误差 1e-8 m。
- **`.vam`**：itemType、uid `<作者>:<名字>`、displayName、creatorName、tags、isRealItem；**`.vaj`**：storables
  （uid + Style / WrapControl / Sim / ItemControl / Material<材质名>）。头发物品（HairFemale）的 storable 前缀是
  uid + `CustomScalp`。预设里引用散装物品：`{"id": "Custom/Clothing/Female/<作者>/<件>/<件>.vam", "internalId": uid}`。
- **morph**：`.vmi` JSON + `.vmb`（int32 数量，再每条 {int32 顶点号, float3 位移}，VaM 空间、米）。女性身体 morph 只能动
  前 21556 个顶点。`formulas` 里 `BoneCenterX/Y/Z` 的值是**米、VaM 轴**——拿作者们的 morph 标定过：`lEye` 的值正好等于
  x < 0 那只眼球顶点的平均位移（`KSE-ZERO - Body` 完全相等，`KJL03` 差 0.2 mm 以内）。
- **预设里的皮肤和眼睛**：`textures.faceDiffuseUrl`、`irises.customTexture_MainTex`（整张眼睛贴图：上半眼白、
  下半两个虹膜）、`FemaleEyelashes."Diffuse Color"`（HSV）。散装文件写 `Custom/...` 相对路径，`.var` 包里才是
  `SELF:/Custom/...`；morph 的 uid 同理。

### 身体怎么对上

1. **骨架重定向**：UE5 的每根变形骨映射到 G2F 的关节（脊柱按弧长分配），每段骨一个仿射（旋转 + 沿骨缩放），用角色
   自己的权重做线性混合蒙皮——A-pose 摆成 VaM 的 T-pose，四肢长度也对上。**脊柱只平移**：UE 的 spine_05 → neck_01
   往后仰 37°，一旋转，围巾尾巴就甩到身后去了。前脚掌按「脚掌骨 → 鞋尖」映射到 G2F 的「脚趾 → 趾尖」，为高跟设计的
   靴子也能包住 VaM 的平脚。头部骨用脸拟合的相似变换（见下），头发就落在拟合后的头上。
2. **静止体 morph**（关键一步）：VaM 穿衣服时照样画身体，G2F 胸大臀宽，盔甲会被顶穿。把盔甲往外推会把硬甲片推瘪、
   裙甲外翻；反过来，把 G2F **往里收**到每件衣服的间隙以内，这个形状存成 morph `Fiona DF Body`，所有物品都对着它算
   包裹。预设把 morph 开到 1，VaM 重建出来的盔甲就是原样：不穿模，也不变形。
   - 收缩上限按**皮肤材质**分部位（躯干 10 cm、手指 3 mm……），并且不超过到该部位骨轴距离的一定比例——3 cm 粗的脚踝
     收 3 cm，三角形就翻过去了。
   - 每个衣服点固定在**起始身体**上离它最近的三角形上。在收缩中的身体上重新找的话，胸甲的点会从深收的乳尖跳到上方
     坡面，乳尖照样顶穿。
   - 大三角形内部也加采样点：一整块平板的顶点都在外面，中间照样会被顶穿。
   - **皮肤这一侧也要查**：衣服点只推它锚定的那个三角形，旁边的小凸起只分到平滑溢出来的量——乳头尖收了 65 mm，
     旁边的乳晕只收了 15 mm，还在胸甲前面 17 mm。所以躯干、臀、脖子、肩、腿、前臂的每个皮肤顶点还要落在离它最近的
     硬质衣服点后面至少一个间隙。手脚不做：它们上限只有几毫米，自己又多褶，这条规则让脚上翻面的三角形多了 4 倍。
     头发不算：它薄、透，发根本来就扎在头皮里；耳朵只许收 3 mm——头发穿过耳朵很正常，耳朵收 2 cm 会皱成一团。
   - 收缩方向用平滑过的法线场（约 5 cm），小凸起整体往后退，不会被各自朝侧面的法线扯开。
3. **包裹记录的朝向**（这个坑最隐蔽）：记录的法线 N 是三角形法线，按皮肤的顶点法线定朝向——VaM 是在**当时的**身体上
   定的。静止体收得很深，有的三角形在收缩后翻了面或者和顶点法线接近垂直，用基础身体的法线算出来的记录到了 VaM 里
   朝向就反了，顶点被甩到皮肤另一侧、偏出两倍的法向偏移。第一阶段装进去的五件都有：上衣 146、下装 135、护手 296、
   靴子 6、头发 369 个顶点偏出 5 mm 以上，最远 20 cm（耳边头发炸开就是它）。现在记录按静止体自己的法线算，并且只锚在
   「在基础 / 起始 / 静止三种形状里朝向都明确（|cos| ≥ 0.5）且一致」的三角形上（排除约 4% 的皮肤三角形）；流程最后
   用写出去的 `.vmb` 叠出身体、从 `.vab` 重建每一件做自检，五件都在 0.3 mm 表面偏移之外 ≤ 0.002 mm。
4. **最近三角形**用均匀网格加速：取 6 个最近顶点周围的三角形算精确距离，远于一个格子的点改走暴力搜索。身体用 3 cm
   格子，和暴力搜索比 25 mm 内完全一致；脸这种密网格用 1.5 倍中位边长（Fiona 的脸 7.5 mm），在 10 万个贴图像素上和
   64 候选的暴力搜索逐点一致（1 倍时有 341 个点选错）。查询分块，一块不超过约 2000 万个点-顶点对——2048 的贴图一次
   就是 290 万个点，不分块要 3.5 GB。

### 脸（`face_fit.py`）

§8 里说过，最近点投影会把脸投烂，所以这里按地标来：

1. **地标**：两边用同一套规则——眼内/外角、眼球中心、上下眼睑中点、嘴角、耳朵、鼻根、鼻尖、鼻翼、上下唇、下巴、
   额头、头顶、后脑、颧骨。G2F 这边从材质岛取（Lacrimals = 内眼角，Tear = 下眼睑，Lips、Ears、Sclera），Fiona 这边
   用 MetaHuman 的 `FACIAL_*` 骨头（EyeCornerInner/Outer、LipCorner、Ear、EyelidUpperA2/LowerA2）投到皮肤上；
   鼻翼、下巴这些纯几何的规则两边共用。
2. **相似变换**（Umeyama）把 Fiona 的脸搬到 G2F 的头上：**保留 VaM 的头的大小**，只借形状。Fiona 的头小一圈：
   s = 1.102，转 2.5°，地标残差中位 3.3 mm。
3. **薄板样条**（φ = r）：从 G2F 的地标到变换后的 Fiona 地标，作用于整个头，顺着脖子往下淡出。
4. **表面贴合**：脸、嘴唇、鼻孔、头皮的顶点拉向 Fiona 皮肤的最近点，位移先在 G2F 网格上平滑再施加，由粗到细 6 轮
   （平滑 30 → 1 次），最后中位 0.04 mm。有了样条，对应关系已经对了，鼻子不会再被剪切掉。三条护栏：
   - 两边表面朝向差超过 60° 的点对不拉（否则内唇被拉到外唇上，嘴唇翻折）；
   - **耳朵不拉**，跟着周围皮肤的位移走：耳朵的褶在别人的耳朵上找不到对应，投上去边长拉到 11.6 倍、21 个三角形翻面；
     睫毛、泪线、泪阜、口腔同样跟着附近皮肤走（不跟的话，睫毛会离开眼睑最多 4 mm）；
   - 最后在翻面的三角形及其两圈邻居里把位移做调和平均，直到没有翻面（头皮接耳朵处、嘴角共 33 个，2 轮清零）。
5. **眼球**整体平移到 Fiona 的眼球中心（约 1 mm），morph 里同时写 `lEye/rEye` 的 BoneCenter，VaM 转眼珠的支点跟着走。
6. 结果写成 morph `Fiona DF Head`。

**脸部贴图**：G2F 的脸部贴图（Face、Lips、Nostrils 三个材质；耳朵和头皮在躯干贴图上）按 UV 光栅化，每个像素在拟合后
的头上找 Fiona 皮肤的最近点，按她自己的 UV 采她的漫反射。2048² 共 290 万个像素，到 Fiona 皮肤的距离中位 0.14 mm。然后：

- **发底**：Fiona 的贴图在发际线以上画了一层深棕色的「发底」，金发底下露出来就是黑发根。眉毛以上、眼角外侧比皮肤暗的
  像素换成底模角色（Evey）的皮肤；替换区往外扩约 4 mm 再羽化，盖住发际线那圈发灰的过渡。
- **接缝**：脸在接缝处接的是 Evey 的躯干贴图（脖子、耳朵、头皮），所以沿外缘 5% 宽的一圈，把低频颜色比（线性光）
  过渡到 Evey 的；脸中间只带 30%，雀斑、疤、痣、嘴唇都保留。
- **眉毛**是贴在皮肤上的发片：每个发片顶点投到拟合后的头上取 G2F 的 UV，再在这个 UV 空间里按发片自己的 UV 光栅化，
  用 ODI 的 R 通道做覆盖率叠上去（透射率相乘，发片的先后顺序无关）。
- **虹膜**：Fiona 的眼球材质是程序化的（从调色板取色 + 纹理 + 节点画的瞳孔和角膜缘），所以在 dump 时用 Cycles 把它的
  Base Color 烘成一张图（`--bake`），再按半径映射进底模的眼睛贴图：两边都自动量出瞳孔边和虹膜外缘，这一圈对那一圈，
  瞳孔和眼白保留底模的。
- 睫毛用 VaM 自己的，在预设里调成棕色。

底模选 **Evey**：和 Fiona 的脸同色相，亮约 5%。它的皮肤是 "UV: Base Female"——我们烘的就是这套 UV，换底模时必须选
同一套 UV 的角色（Candy、Evey、Female 1、Janie、Kayla、Lexi、Tina……）。

### 实测（Fiona）

| 项 | 结果 |
|---|---|
| 头部相似变换 | s = 1.102，旋转 2.5°，地标残差中位 3.3 mm（最大 12.0 mm，在耳朵） |
| 表面贴合 | 6 轮后中位 0.04 mm、p95 0.59 mm；每轮 110–225 个点对因朝向不符被丢弃；翻面 33 → 0 |
| 头部 morph `Fiona DF Head` | 8836 个顶点；眼球平移约 1.1 mm，lEye / rEye 的 BoneCenter 一并写入 |
| 头部网格质量（对比基础 G2F） | 脸、嘴唇、鼻孔、耳朵、头皮、睫毛、脖子全部 0 翻面；耳朵边长比最大 2.4（改前 11.6） |
| 脸部贴图 | 2048²，2,894,074 个像素，到 Fiona 皮肤中位 0.15 mm / p95 0.63 mm；发底替换占 33.3%；眉毛 3592 片全部贴皮（高出皮肤中位 1.9 mm） |
| 虹膜映射 | G2F 瞳孔边 0.084–0.087 / 外缘 0.209–0.210（UV 半径）← Fiona 0.065 / 0.190 |
| 静止体 morph `Fiona DF Body` | 15,027 个顶点，收缩 p95 46.3 mm、最大 96.1 mm |
| 物品 | 上衣 17,063 顶点 / 28,842 面，下装 7,296 / 11,723，护手 7,676 / 15,092，靴子 6,450 / 12,068，头发 28,492 / 40,856 |
| 自检：`.vab` 在「基础 + 两个 morph」上重建 | 五件都在 0.3 mm 表面偏移之外 ≤ 0.002 mm（修前五件共 952 个顶点偏出 5 mm 以上，最远 20 cm） |
| 胸甲遮挡 | 正面看过去 194 个乳头顶点被胸甲挡住 194 个（修前 50 个露在外面，最远 17 mm） |
| 整条流程 | 约 6 分钟（其中脸部贴图 4 分钟），含 Blender 预览和缩略图 |

### 还没做的

- `Fiona DF Body` 是**只为穿盔甲准备的收缩体型**：盔甲下面约 500 个皮肤三角形被收得翻了面（手 184、躯干 131、胸 64、脚 58、指甲趾甲 58），
  穿着时看不见；**脱掉盔甲时把这个 morph 调回 0**。
- 靴子是为高跟设计的，VaM 的脚是平的：脚趾会从护脚甲前端下面露出来（第一阶段就这样）。可以在 VaM 里把脚尖往下压一点。
- 没有布料模拟（盔甲本来就是硬的）；头发是网格头发，不会飘。
- 脸的法线 / 高光贴图还是 Evey 的（G2F 的 UV 位置不变，嘴唇、鼻翼对得上；只是眉毛的凹凸留在 Evey 的眉毛位置）。
- 只做了女性，骨架只认 UE5 命名。
- 格式是逐字节验证的，拟合结果是在 Blender 里按 VaM 的规则重建出来检查的；**还没在 VaM 里亲眼看过**。
