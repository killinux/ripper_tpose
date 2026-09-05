# Virt-A-Mate (VaM) 脚本说明

把 VaM 1.22 里的 **Look（人物外观）** 和 **衣服** 转成带材质的 `.blend`（可选 `.glb`）+ 一张
三视图预览 PNG。用法与 ROE 的 `export_character_models.ps1` 对齐：`-List` 看有什么，
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
| `vam_lib.py` | 共享库：`.var` 索引与引用解析、`.vab`/`.vmb` 解析、AssetStudio dump 解析、缓存 |
| `export_vam_model_blender.py` | Blender 侧 worker（建网格、材质、打包、预览） |
| `tests/test_vam_lib.py` | 纯 Python 合成 fixture 回归，标记 `VAM_LIB_TEST=PASS` |

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
.\export_vam_models.ps1 -List -Type clothing -Filter gantz # 只看衣服，名字含 gantz
.\export_vam_models.ps1 -Only VAMSOY.Angela.1~Angela~Person
.\export_vam_models.ps1 -Only Angela~Person                # 唯一的子串也行
.\export_vam_models.ps1 -Index 125,550                     # 用 -List 里的 # 号
.\export_vam_models.ps1 -All -Type clothing                # 328 件衣服全转
.\export_vam_models.ps1 -Only 瑶瑶~Person -Format blend,glb -Force
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
| `-All` | 全部 Look + 全部有网格的衣服（配合 `-Type` 缩小范围） |
| `-Format` | `blend`、`glb` 或两者，缺省 `blend` |
| `-IncludePoseMorphs` | 保留姿势 morph（握拳、眨眼、耸肩…）；缺省跳过，导出的是静止 A-pose |
| `-NoClothing` | Look 只导人体，不带衣服 |
| `-NoPreview` | 不渲染预览图 |
| `-ValidateOnly` | 只拼装 + 在 Blender 里建网格/材质检查，不写产物 |
| `-Force` | 覆盖已有产物（缺省时 `.blend` 与预览图都在的条目 SKIP） |
| `-ManifestPath` | 自定义 manifest；多进程并行时每个进程各给一个 |
| `-Prepare` | 只建缓存 |

## 4. 产物

```text
D:\vam_exports\looks\<key>\model.json, model.npz     # 给 Blender 的中间产物（顶点/面/UV/材质表）
D:\vam_exports\looks\<key>\_textures\                # 该 Look 用到的全部贴图（从 .var 里解出）
D:\vam_exports\looks\<key>\blend\<key>.blend         # 贴图已打包
D:\vam_exports\looks\<key>\blend\<key>_preview.png   # 3/4 + 正面 + 头部
D:\vam_exports\looks\<key>\blend\glb\<key>.glb       # 仅 -Format glb
D:\vam_exports\clothings\<key>\...                   # 单件衣服同结构（预览只有 3/4 + 正面）
D:\vam_exports\vam_models_manifest.json              # 全量清单，-Only 时按条目合并
```

manifest 每条带 `notes`：角色/性别/皮肤包、morph 统计（`applied` / `skippedPose` / `missing`）、
用了哪些衣服、哪些衣服因依赖包缺失没找到（`clothingMissing`）、跳过的头发、哪些皮肤贴图槽回退到
默认皮肤（`defaultTexturesUsed`）、找不到的贴图（`missingTextures`）；Blender 侧再补
`objects` / `materials` / `packed_images` / `untextured_slots`。

`untextured_slots` 里出现衣服自己的纯色材质（VaM 里很多眼影/眼膜/内衬只给 `Diffuse Color`
不给贴图）是正常的；出现 `Face` / `Torso` / `Limbs` 这类人体槽才是问题。

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
  衣服文件里的顶点是**套在未 morph 的标准体**上的；VaM 运行时用 DAZSkinWrap 重新贴合，这里用
  「最近 4 个身体顶点的位移按距离平方反比加权」近似搬运，普通衣服足够，贴身的极端 morph 可能穿模。
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

头发的 `.vab` 是 `RuntimeHairGeometryCreator` 存储（发丝曲线，不是网格），`-List` 里列出但不转。
本机 119 个 `.var` 里 372 个衣服 `.vab` 全部按上面的布局解析通过（每一步都有一致性断言，不对就报错而不是出乱模）。

### 坐标

VaM/Unity：米，Y 向上，+Z 朝前，+X 是角色的**右**（用脚尖方向和脸部 UV 左右侧验证过）。
转 Blender：`(x, y, z) → (-x, -z, y)`，这是一次镜像，所以面的顶点顺序同时反转。

## 6. 已知限制

- **头发不转**：VaM 头发是发丝模拟数据，不是网格。
- **没有骨架**：只有静态网格（DAZSkinV2 里有权重，以后可加）。
- 姿势 morph 缺省跳过；表情/手势要 `-IncludePoseMorphs`。
- 场景依赖的包没装（`clothingMissing`）或 morph 缺失（`morphs.missing`）时照常导出，只是少那件/那点形变；
  `Breast Impact*` 这类物理驱动 morph 不在 morph 库里，值也很小，可忽略。
- 衣服贴合是近似。Decal 贴图按其 alpha 叠在漫反射之上（JPEG Decal 等于整张替换——mai.tifa8K 就是把 8K 皮肤放在 Decal 槽里）。
- 默认眼睛贴图按角色皮肤包挑第一张，可能和 VaM 里选的不同。

## 7. 测试

```powershell
cd E:\code\othercode\ripper_tpose\scripts\vam
python tests\test_vam_lib.py        # 纯 Python，合成 .var/.vab/.vmb/dump fixture，末行 VAM_LIB_TEST=PASS
```

集成验证（2026-09-05，本机 119 个包）：`Angela`（Female Custom + 4 件皮肤层）、
`Cloud`（Male 4 + 6 件衣服）、`Preset_Alivia`（Kayla 皮肤全默认贴图，148 个 morph）、
`瑶瑶`（Lexi 皮肤，中文包名，女仆装 5 件 + 3 层皮肤层）、单件 `Cheongsam set`，均 PASS，
单个 Look 8–55 s。
