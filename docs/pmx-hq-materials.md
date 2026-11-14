# PMX 的 MMD 材质和 ray-mmd 高清材质

pmx-todo 第 2 项「MMD 里的材质」。2026-11-14 用户选了「两步都做」。工具在 `scripts/pmx_tools/hq_materials/`，
用法见那里的 README。这一篇讲为什么这么做、怎么做的，以及踩过的坑。

## 问题

我们各游戏导出的 PMX，材质只设了贴图。普通 MMD 里这样看是平的：

- MMD 的明暗主要靠 **toon 贴图**。每个材质按「法线和光的夹角」到一张竖条图里取色，再乘到颜色上。
  没有 toon 时用默认的白条，模型几乎没有明暗；只有自身阴影能打出一点影子。
- 高光一刀切：Convert to MMD 和我们的导出给所有材质 specular (1, 1, 1)、shininess 11.9。
  在 MMD 里，这就是皮肤、头发、衣服、金属同样亮的一层大白光。
- 没有 sphere 贴图（MMD 用它做头发光泽、金属反光），也没有描边。
- 游戏原版的法线、粗糙度、金属度、自发光贴图只用在 Blender 插件里，MMD 一张都用不上。

## 第一步：普通 MMD 也能看到的材质（`<名字>_材质.pmx`）

按「这个材质是什么」配 MMD 自己的四样东西：

| 类别 | 高光 / shininess | toon 阴影色 | sphere（加算） | 描边 |
|---|---|---|---|---|
| skin 皮肤 | 0.15 / 4 | 偏暖 (0.88, 0.76, 0.73)，过渡最软 | 边缘微光 | 0.4 |
| hair 头发 | 0.25 / 20 | 偏冷灰 | 上方一条柔光带 | 0.4 |
| cloth 布 | 0.15 / 4 | 中性灰 | 无 | 0.4 |
| mixed 半金属 | 0.5 / 8 | 中性灰 | 无（见下面的坑） | 0.4 |
| metal 金属 | 0.8 / 30 | 深一点 | 无 | 0.4 |
| glossy 乳胶 / 皮革 / 塑料 | 0.6 / 40 | 深一点 | 无 | 0.4 |
| glass 玻璃 / 透明件 | 0.9 / 60 | 不改 | 无 | 无 |
| eye 眼睛 | 0.5 / 60 | 白（不打阴影） | 眼神光点 | 无 |
| lash_brow 睫毛 / 眉毛 / 眼影 | 0 | 白 | 无 | 无 |
| mouth 牙齿 / 舌头 | 0.3 / 20 | 偏暖 | 无 | 无 |
| emissive 发光件 | 0 | 白，环境色 1、关自身阴影（不受光照影响） | 无 | 无 |
| eye_overlay 泪光 / 眼部遮罩 | 整个不改 | | | |

- 皮肤和布的 0.15 / 4 沿用 10-05 用户在 Vindictus 上从渲染对比里挑定的值（`scripts/vindictus/pmx_materials.py`）。
- toon 是生成的 32×256 竖条图：上半白（受光），过了中线（明暗交界）渐变到阴影色；自身阴影里也取最下面的颜色。
  sphere 是 256×256 的图，按视角空间的法线取色：中间 = 正对镜头，边缘 = 掠射。都放在 PMX 旁边的 `mmd_materials\`。
- 描边颜色 = 这个材质贴图在自己 UV 范围里的平均色 × 0.35。
- 漫反射色和环境色保持原样，导出脚本已经调好亮度；只有发光件把环境色调到 1。
- 自带 toon / sphere 的材质（对魔忍 Squad 用的是游戏自己的 toon）默认保留，`--force` 才重做。

### 怎么判断类别

1. 先看名字：材质名和贴图名，英文、中文、日文关键词都认（`KEYWORDS`）。
   - 眼睛、睫毛、嘴、头发、玻璃只看名字，游戏贴图不推翻这几类。
   - 「`<网格文件>.fbx_<材质>`」这种名字（ELDEN RING / 只狼的 mod 包）只看 `.fbx_` 后面那段。
     第一版没去掉前缀，「头手腿.fbx_…」里的「腿」把比基尼、紧身衣、鞋都判成了皮肤。
2. 再用游戏贴图（找得到源 .blend 时）。在这个材质自己的 UV 三角形里取平均：
   - 发光的面积 ≥ 50% → emissive；
   - 金属度贴图平均 ≥ 0.5 → metal，0.2–0.5 → mixed；
   - 名字说是金属、金属度贴图却 < 0.2 → 不当金属（HS2 的战斗服材质叫 `cf_m_bra_meka`，「meka」不是金属）；
   - 有次表面散射 → skin；
   - 粗糙度贴图平均 ≤ 0.3 → glossy。
   - **贴图算强证据，节点树里的常数只算弱证据**：好几个转换流程把所有材质的 Metallic 都留成 0，
     那不代表「不是金属」。

### 坑：sphere 会在 MMD 里出灰斑

ELDEN RING Tifa Gantz 黑色全覆盖加了金属 sphere 之后，手臂内侧、腰两边、大腿出现灰色半透明的斑块。
这件衣服是好几层叠起来的，外层贴图有大片透明（alpha 0）的地方。

在 MMD 9.32 里对同一个模型试了三种（`samples` 对比图，11-14）：

| sphere 图 | 结果 |
|---|---|
| 不透明 RGB | 透明处变成灰斑 |
| RGBA，alpha 255 | 一样有灰斑 |
| RGBA，alpha 0 | 整个材质消失 |
| 不加 sphere | 干净 |

所以 MMD 自带的渲染会把加算 sphere 的 alpha 带进材质的 alpha（MME 的说明里也提到旧版 full.fx 有同样的问题）。
处理一：先量这个材质贴图在自己 UV 范围里透明（alpha < 0.95）的面积，超过 0.5% 就不加 sphere，报告里记一条 `no_sphere`。
sphere 图本身保持不透明 RGB。

后来发现这件衣服的灰斑贴图根本不透明（RGB，没有 alpha），灰斑正好在外层（比基尼、大腿套）贴着内层战斗服的地方。
推测是外层网格的法线朝向不同，sphere 按法线取色时取到了图上最亮的那块。
处理二：金属、半金属、乳胶、玻璃默认都不加 sphere。只靠 toon 和高光，这件衣服已经是干净的黑亮质感（样品对比图第二栏）。
皮肤（很淡的边缘光）、头发（有镂空的不加）、眼睛（眼神光点）的 sphere 保留。
金属类的 sphere 图照样生成在 `mmd_materials\` 里，想用就 `--values` 打开，例如 `{"metal": {"sphere": ["metal", "add"]}}`。

## 第二步：ray-mmd 高清材质（`E:\game_export\_raymmd\<游戏>\<模型>\`）

[ray-mmd](https://github.com/ray-cast/ray-mmd) 是 MME 的一套基于物理的渲染（PBR）效果。每个材质用一个 `.fx` 文件，
写明 albedo、法线、光滑度、金属度、高光、自发光、着色模型。我们从游戏材质里把这些读出来，一个材质写一个 `.fx`。

### 读游戏材质（`extract_pbr_blender.py`）

PMX 的源 .blend 里保留着游戏的节点树。我们的 PMX 导出脚本会在 PMX 旁边留下 `*_converted.blend`：mmd_tools 把输出接到
自己的 MMD shader 上，但原来的 Principled BSDF 还在节点树里。Rise of Eros 的归档 .blend 用的是高清游戏材质。

对每个 PMX 材质：

1. 找到它来自哪个 Blender 材质：先比同名；再去掉前缀比（ROE 的 `HQ_`）；最后看哪个材质用了这个 PMX 贴图。
2. 读 Principled BSDF 的 Normal、Roughness、Metallic、Specular、Emission（颜色 × 强度），
   顺带记下 Subsurface、Sheen、Clearcoat、Transmission、Alpha 这几个提示。每个输入分三种情况：
   - 常数 → 直接写数；
   - 一张图通过 PMX 自己的 UV 直接读出来 → 直接引用原图。这张图可以只取一个通道（Separate RGB），
     可以是 1 − x，法线图可以经过「拆通道 → 1 − G → 合通道」把绿通道反过来；
   - 别的（几张图做运算、Mapping 节点、另一套 UV、节点组、Bump）→ 用 Cycles 在这个材质的 UV 上烘焙一张：
     标量和颜色接到 Emission 上烘 EMIT，法线烘 NORMAL（切线空间）。
3. 打包在 .blend 里的图先写出来（`baked\packed_*`）。

### 换算

- **法线**：ray-mmd 的切线空间 `tbn[1] = -B`，B 是 UV 的 v 增大方向（D3D 里 v 往下），所以它要的是绿通道朝上的
  OpenGL 法线图，和 Blender 一样。Blender 里经过「1 − G」的图（原来是 DirectX 的）另存一张反过绿通道的。
- **粗糙度 → 光滑度**：ray-mmd 的 GGX alpha = (1 − smoothness)²；Blender（和 UE4）的 GGX alpha = roughness²。
  所以 smoothness = 1 − roughness，对应 `SMOOTHNESS_MAP_TYPE 2`。
  `TYPE 1` 是 1 − √roughness，给存 alpha 的图用，不要选。
  前面有 1 − x 的（图里存的本来就是光滑度）用 `TYPE 0`。
- **高光**：Principled 的 Specular 和 UE4 一样，F0 = 0.08 × 值，正是 ray-mmd 的 `specular` 常数（默认 0.5 = F0 0.04），
  贴图用 `SPECULAR_MAP_TYPE 2`。
- **金属度**：直接用，`METALNESS_MAP_SWIZZLE` 选通道；1 − x 的另存一张。
- **自发光**：贴图 + `emissiveIntensity` = Blender 的 Emission Strength。
- **albedo**：PMX 自己的贴图（`ALBEDO_MAP_FROM 3`）。PMX 的漫反射色只在它带色调或明显偏暗时才乘上去。
  导出脚本给的 0.8 灰是为了普通 MMD 的亮度，ray-mmd 里不要。没有贴图的材质用漫反射色（转成线性）。
- **着色模型**：皮肤用 ray-mmd 的 Skin（`CUSTOM_ENABLE 1`，曲率 0.6，透射色照它自带的 material_skin.fx）。
  其他用默认。
- 没有源 .blend 的材质按类别给预设（`RAY_PRESETS`）。

### 文件放在哪：纯英文路径

每个模型的 ray-mmd 版放在一个**只有英文字符的文件夹**里：`E:\game_export\_raymmd\<游戏>\<角色>_<模型>_<哈希>\`。

```
model.pmx     原 PMX 的硬链接（同一份数据，不占空间）
textures\     PMX 用到的贴图的硬链接，相对路径和原文件夹一样（贴图名可以是中文：MMD 能读，MME 从 MMD 拿）
fx\           每个材质一个 NN_<类别>_<哈希>.fx、_default.fx、material_common_2.0.fxsub、ray-mmd_LICENSE.txt、
              maps\（游戏贴图的硬链接，英文名）、baked\（烘焙出来的图）、pack.json、extract.json / .log
scene.emm     MME 的效果分配：每个材质 → 它的 .fx
scene.pmm     （生成了的话）MMD 场景：ray.x + 天空盒 + model.pmx，打开就全部设好
README.txt
```

为什么不放在 PMX 旁边：**MME 处理路径时按日文编码（CP932）转换**。在中文 Windows 上，中文文件夹里的模型在 MME 里
变成乱码（「黑_全覆盖」→「麷_慡暍岢」）。这时 .emm 会报「Failed to load effect mapping for the following objects」，
同名 .emd 根本找不到（不报错，也不生效）。MMD 本身读中文路径没问题，只有 MME 有这个问题。

### 怎么让每个材质用上自己的 .fx：.emm，不是 .emd

- **`.emd` 不行**。MME 确实会读模型同名的 .emd（MME 0.33 起），但只读 `[Effect]` 一段，也就是 Main 分页。
  ray-mmd 的材质在 `MaterialMap` 分页。`[MaterialMap]`、`[Effect@MaterialMap]` 写进 .emd 都会报
  「Error: failed to load file … (line 7)」。在 MME 的「Map Effect File」窗口里用「Save by Model」存，
  也只存当前分页，并且写成 `[Effect]`（11-14 实测）。
- **`.emm` 可以**。这是整个场景的分配文件，由 MME 窗口的 File → Open / Save 读写，按路径对应物体。
  格式是照 MME 0.37 自己存出来的文件写的：

  ```
  [Info]
  Version = 3

  [Object]
  Acs1 = E:\tools\MikuMikuDanceE_v932x64\ray-mmd-1.5.2\ray.x
  Pmd2 = E:\tools\MikuMikuDanceE_v932x64\ray-mmd-1.5.2\Skybox\Helipad GoldenHour\Sky with box.pmx
  Pmd3 = E:\game_export\_raymmd\EldenRing\Tifa_mod4684_Tifa_Gantz_32b3ef\model.pmx

  [Effect]
  Default = none
  Pmd2 = …\Sky with box.fx
  Pmd3 = none

  [Effect@MaterialMap]
  Owner = Acs1
  Acs1.show = false
  Pmd2 = …\Materials\material_skybox.fx
  Pmd3 = …\fx\_default.fx
  Pmd3[0] = …\fx\00_hair_e51f31.fx
  Pmd3[1] = …\fx\01_mouth_6a90d7.fx
  ...
  ```

  - 离屏分页的段名是 `[Effect@<分页名>]`，`Owner` 指向带这个分页的物体（ray.x）；
  - `Pmd3[n]` 是第 n 个材质（MME 叫「サブセット」）；
  - 没有 `[Effect]` 段时 MME 报「section 'Effect' was not found」；
  - 场景里有、但 .emm 没写的物体，MME 会弹框列出来，所以推荐的天空盒也写进去了。
- `.fx` 和贴图用绝对路径，全是英文；.fx 里引用 `maps\…` 用相对路径。

### 在 MMD 里用

- 有 `scene.pmm` 的：MMD「文件 → 打开」选它（MME 会自动读同名的 scene.emm）。
- 自己搭场景：
  1. 载入 ray-mmd 的 `ray.x`（配件 / accessory）；
  2. 载入天空盒，例如 `Skybox\Helipad GoldenHour\Sky with box.pmx`；
  3. 载入 `model.pmx`；
  4. 菜单 MMEffect → Effect Mapping，窗口里 File → Open，选 `scene.emm`，再按 OK。
- 用别的天空盒或加了别的模型也没关系，MME 只会弹框提示那几个物体没写在 .emm 里，我们的模型照样生效。

## 安装（这台电脑，11-14）

- MME：MikuMikuEffect x64 ver0.37。下载自 BowlRoll `bowlroll.net/file/35013`（`MMEffect_x64_v037.zip`），
  SHA-1 `c9304108d61517e9ba47e05118dda1df6063c14c`，和页面上公布的一致。
  `d3d9.dll`、`MMHack.dll`、`MMEffect.dll` 拷到 `MikuMikuDance.exe` 旁边，说明书在 `MMEffect_doc\`。
  需要 `d3dx9_43.dll`，系统里已经有。
- ray-mmd 1.5.2（tag 1.5.2 = commit a425ab6d），装在 `E:\tools\MikuMikuDanceE_v932x64\ray-mmd-1.5.2\`。
  GitHub 走 HTTP 代理只有 20 KB/s，改用 SSH `git clone --depth 1 --branch 1.5.2`，速度 5 MB/s。
- MMD 菜单栏右边出现「MMEffect」就是装好了。

## 用脚本驱动 MMD 出图（`mmd_drive.py`）

验证要在 MMD 本体里看：.fx 写错了只有 MME 会报；sphere 的坑也只在 MMD 里出现。做法和坑见 `mmd_drive.py` 开头的说明。

- 按钮靠控件 ID，用 post 的 BM_CLICK 点；send 会卡在 MMD 的模态文件对话框里。
- 文件对话框的路径必须用反斜杠，用正斜杠时对话框说文件不存在。
- 出图走菜单「file → render to picture file」，尺寸看「view → screen size」。
- 相机面板的数字框收不到 post 过去的值，所以近景从大图里裁。
- 载入模型时 MMD 会弹「model infomation」（PMX 的注释），删模型会弹确认框；这两种是正常的，其余的都记为问题。
- MME 的「Map Effect File」窗口（菜单命令 40005）：File → Open 40009（.emm）、Save 40010、Open / Save by Model
  40016 / 40017（.emd）。分页用 pywinauto 按名字选（`select("MaterialMap")`，`texts()` 的第一项是控件自己的空标题，
  按下标数会差一位）。列表里展开的材质行写作 `  |-- n: subsetn`。
- `compare` 在 ray-mmd 那一栏出图之前，先读回 MaterialMap 分页，数有几个材质指向我们的 fx 文件夹，
  对比图标题里写「n/m 个材质用游戏贴图」。第一轮 .emd 的错就是这样查出来的：标题是 0/0，图却「好好的」，
  其实是 ray-mmd 的默认材质。

## 限制

- 没有源 .blend 的 PMX（下载的 MMD 模型，例如「18」系列）：第一步只能按名字分类，第二步只有按类别的预设，
  没有游戏贴图。
- 头发的各向异性高光、眼睛的折射、布料的 sheen 用的都是 ray-mmd 默认着色模型，没有专门做。
- ray-mmd 的整体观感很受天空盒和曝光影响。对比图统一用 `Helipad GoldenHour\Sky with box.pmx`、默认设置。
  皮肤在这个天空盒下偏白，曝光可以用 ray-mmd 的 `ray_controller.pmx` 调。
- 每个 ray-mmd 文件夹都是独立的：同一个文件夹里的几个 PMX 变体（ROE 的 `_bustB`、`_裙子碰撞修正`）各算各的，
  要烘焙的会各烘焙一次。
- `scene.pmm` 要让 MMD 自己存，每个模型开一次 MMD（约 40 秒，窗口会弹出来）。整批时要不要生成，等用户定。
