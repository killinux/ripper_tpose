# Rise of Eros：用游戏自己的材质数据导出高精度 .blend

> 2026-09-27。起因：用户问 riseoferos 现在导出的模型是不是精度最高的，Blender 里能不能更高。
> 先拿 Inase（a01）做了试验，用户确认后改了批量导出脚本，再用新脚本导出了 g05（Luf）。
> 仓库里只有脚本和说明；材质数据、贴图、导出物都不进仓库。

## 0. 结论

- **几何已经是最高的**：用的是 HD 模型；游戏里的网格没有压缩；每个顶点最多 4 根骨骼权重，游戏数据本来就是 4 根；
  游戏本身没有形态键。导出的 .blend 顶点数、自定义法线和游戏完全一致。
- **贴图分辨率也已经是最高的**：身体 2048，服装部件最高 4096，解码无损。
- **差在材质**。游戏每个部件都有颜色、法线、MGAC 三张图，脸上还有细节法线，头发有自己的法线、发丝遮蔽和发色，
  原来的 .blend 只接了颜色贴图。现在这些都用上了：
  - `.blend` 和预览图用完整材质；
  - XPS 带上颜色、AO、法线、高光四张图（XNALara render group 24 / 25）；
  - PMX 的颜色贴图里烘进发色和 AO；
  - GLB 不变。
- **顺带修正了发色**：头发颜色是 `_BaseColor` 乘上一张灰色贴图。原来没乘，Luf（g 家族）的头发一直是浅灰，
  游戏里是深棕。Inase 的发色系数接近白色，所以看不出区别。

## 1. 精度检查（a01_hd，UnityPy 读游戏包，对比已导出的 .blend）

| 项目 | 游戏数据 | 原来的 .blend |
|---|---|---|
| 网格 | HD：身体 18,585 / 头 8,708 / 头发 12,594 个顶点（LD 约三分之一），`m_MeshCompression = 0` | 用的 HD，顶点数完全相同，自定义法线保留 |
| 骨骼权重 | 每顶点最多 4 根，没有 `m_VariableBoneCountWeights` | 最多 4 根（头发 3 根） |
| 形态键 | 0 | 0 |
| UV / 顶点色 | 头部另有 UV1、UV2 和顶点色 | 顶点色在，UV1 / UV2 在 FBX 转换里丢了（材质用不到） |
| 贴图 | DXT1 / DXT5，2048–4096 | PNG 无损解码，分辨率相同 |
| 材质 | 颜色 + 法线 + MGAC，皮肤、头发、眼睛另有专用贴图 | **只有颜色贴图** |

## 2. 游戏的材质数据

- **真正的材质不在模型预制体上**。预制体的渲染器挂的是占位材质 `default_material_armor`
  （`chara_mat_armor__system_share_prelude.ab`），运行时才换成真正的材质。真正的材质在：
  - `chara_mat_armor_pc_<id>_hd & ld_hd.ab`：身体、皮肤；
  - `chara_mat_bare_pc_<家族>_common_head*.ab`：脸、眼睛、眉毛、头发、泪膜；
  - `chara_mat_bare_common_prelude.ab`：牙齿。
- 各家族的包名不一样（a 家族叫 `…_head_tutorial`，g 家族叫 `…_head_prelude`），所以按规则找包，不写死名字。
- 发丝遮蔽、头发法线、皮肤细节法线、皮肤 LUT、眼白、眼睛遮蔽、虹膜遮罩这 9 张公共贴图都在
  `chara_tex_bare_common_prelude.ab`。这个包名里没有角色 ID，原来的提取脚本不会去读它。
- 通道含义都在渲染图上核对过：
  - **法线**：Unity DXT5nm，R 恒为 1，G = B = Y，A = X。要重建 Z，转成标准 RGB 法线；
  - **MGAC**：R 金属度（只有金饰是白的）、G 光滑度、B 环境光遮蔽，A 和 G 几乎一样（相关系数 0.98–0.997）；
  - **头发**：`_BaseMap` 是 512 的灰色贴图（alpha 做裁切），颜色来自 `_BaseColor`；
    公共 `hair_rgbx_MGA` 的 R（= B）是发丝遮蔽，和颜色贴图的裁切区域一一对应；
  - **皮肤**：有 `_SkinLutMap` 和 `_TranslucentColor`（透光）；
    脸的 `_DetailNormalMap` 是 256 的毛孔法线，平铺 70 倍（裸体身体 120 倍），强度 0.4；
  - **眼睛**：程序化着色器，用虹膜、眼白、遮罩、视差等参数。
- **颜色是 sRGB**：Unity 把材质颜色按 sRGB 存，在线性色彩空间里转成线性再交给着色器。
  Blender 的颜色插口吃线性值，所以要先转换。g 家族的发色系数 (0.54, 0.41, 0.41) 转成线性是 (0.25, 0.14, 0.14)，
  高光色 (0.88, 0.62, 0.43) 也是暖色，和棕发对得上（Inase 的高光是白色，银发）。
- **a01 自己的脸部颜色贴图**：运行时的头部包 `chara_tex_bare_pc_a_common_head.ab` 里只有 `pc_a01_hd_face`，
  和公共的 `pc_a_nk_face` 只差头皮颜色：前者是浅色，配她的银发；后者是深灰带发际线。给 a01 用它自己的这张。

## 3. 做法

```
游戏包 ──hq_material_data.py（系统 Python + UnityPy）──> <缓存>\<id>.json + textures\*.png（+ __nrm.png）
                                                              │
FBX ──插件挂颜色贴图材质──> 场景 ──hq_materials_blender.apply()──> 游戏完整材质 ──> 预览图、.blend
                                                   └──revert()──> 颜色贴图材质 ──> XPS / GLB / PMX（和以前一样）
```

- `hq_material_data.py`：
  - 选包：名字含 `pc_<id>`、`pc_<家族>_common`，以及公共 bare / armor / system 包，加上配对的 `chara_tex_*` 包；
  - 选材质：按名字（插件从 FBX 存下来的材质名），或者按它用的颜色贴图；同名材质出现两次（HD 和 LD 头部）时，
    取贴图更大的那个；
  - 只解码选中材质用到的贴图，法线另存一份标准 RGB 版 `<名字>__nrm.png`；
  - 缓存：每个角色一个 `<id>.json`，`textures\` 所有角色共用，原子写入，并行跑也安全。
- `hq_materials_blender.py`：
  - **槽对应游戏材质**：以槽的颜色贴图为主键，去找 `_BaseMap` 是这张图的游戏材质。插件存的材质名
    （`roe_source_materials` 加每个面的 `roe_source_material_index`）只用来决胜负：身体和皮肤用的是同一张颜色贴图。
    g05 的头发就没有存名字，只能靠颜色贴图找到；
  - **材质构建**：
    - pbr：颜色 × `_BaseColor` × AO，法线，金属度 = R × `_Metallic`，粗糙度 = 1 − G × `_Smoothness`，
      高光 = 0.5 × AO；
    - 皮肤：pbr 加次表面散射，脸再加细节法线，和主法线在切线空间用 UDN 方式合成；
    - 头发：颜色 × 发色 × 发丝遮蔽，alpha 按 `_Cutoff` 裁切，加头发法线；
    - alpha 测试、透明、自发光按游戏的开关处理。插件原来设成透明的槽，保留它的混合设置；
  - 眼睛、眉毛 / 睫毛、泪膜保留插件原来的材质。
- **高光也要压 AO**：领口内衬的光滑度是 0.9、AO 是 0.55。只压底色的话，它会把整片灰色天空反射出来，
  深红皮革变成灰色。游戏也会压间接高光，所以高光也乘上 AO。
- **worker 接入**（`export_character_model_blender.py` 里几处小改动）：
  1. 挂完插件材质后调 `apply()`；
  2. 预览图和 `.blend` 用新材质；
  3. 写完 `.blend` 调 `revert()` 换回插件材质再导 XPS / GLB；
  4. PMX 之前调 `use_pmx_textures()`，把颜色贴图换成烘好的那张；
  5. 结果里多一个 `hq_materials`，批量脚本写进 manifest 的 `hqMaterials`，控制台打印一行。
- **XPS / PMX 的贴图**：它们跑不了节点，由 `hq_material_data.py` 预先算好，放在 `<缓存>\export\`：
  - XPS 颜色 = 颜色贴图 × `_BaseColor`（在线性空间里乘，再转回 sRGB；头发的 alpha 保留）；
  - XPS lightmap = 和 .blend 一样强度的 AO；
  - XPS bump = 法线，绿通道翻转。XPS 文件头默认的切线空间标志就是反 Y（XPS Tools `flagsDefault`）；
  - XPS specular = √（光滑度 × `_Smoothness`）。XPS Tools 读回时按 粗糙度 = 1 − spec² 解释，正好对上；头发给 0.35；
  - PMX 颜色 = 颜色 × `_BaseColor` × AO。
  - `apply()` 把这些路径记在材质的 `roe_hq_xps` / `roe_hq_pmx` 属性上。插件导 XPS 时读到 `roe_hq_xps`，
    就把这四张图接到 XPS Shader 的 Diffuse / Lightmap / Bump Map / Specular 插口，渲染组改成 24（透明的 25），
    高光强度 0.4；没有这个属性的槽（眼睛、睫毛、眉毛）照旧。
- **插件按钮**：`roe_xps_addon.py` 新加「**2.5 游戏原始材质（高精度）**」，调的是同一个 `apply()`，
  手动和批量结果一样。
  - v1.1.15 起导入的 PMX 也能点。mmd_tools 把 `pc_a08_hd.pmx` 的模型叫成 `Pc A08 Hd`（网格 `Pc A08 Hd_mesh`），
    按钮依次从网格名、父物体（MMD 根）、FBX 路径、.blend 文件名认角色，都没有再看贴图名。
  - 遇到 MMD 模型就原地加（`in_place=True`，和 ROE Game Materials 插件一样），刚体 / 关节网格跳过。
  - v1.1.14 只认以 `pc_<字母><数字>` 开头的 FBX 网格名，导入 PMX 后点会报「认不出角色代号」。
- **失败处理**：这一步出错不会让模型失败，该模型保留颜色贴图材质。

## 4. 验证

| 模型 | 结果 |
|---|---|
| a01（试验，`E:\game_export\RiseOfEros\_hq_trial\pc_a01_hd\`） | 5 个槽换成游戏材质（身体、皮肤、脸 ×2、头发），眼睛 / 睫毛 / 眉毛 / 泪膜保留；顶点数不变；12 张贴图全部打包 |
| g05（批量脚本 `-Only g05 -Format blend -Force`，42 秒） | `hq materials: 6 slots, kept 4, errors 0`；.blend 31.9 → 77.6 MB，15 张贴图全部打包 |
| g05 全流程第一版（blend + XPS + PMX，写到临时目录） | PASS，32 秒；那时 XPS / PMX 还用颜色贴图材质，贴图和原产物完全相同（各 6 张），PMX 撕裂 0、付与顺序错误 0 |
| g05 XPS / PMX 带游戏材质（`_hq_trial\pc_g05_hd\export\`，24 秒） | XPS Tools 读回：身体 / 皮肤 / 脸 = render group 24，头发 = 25，每个都有 Diffuse / Lightmap / Bump / Specular；眼睛 5、睫毛眉毛 7 不变。mmd_tools 读回：6 个槽用的都是烘好的颜色贴图，眼睛 / 睫毛 / 眉毛不变；撕裂 0、付与顺序错误 0 |
| 手动流程（插件按钮 1 → 2 → 2.5 → 清理 + 打包 → 保存 → 3，无头跑） | 全部 FINISHED；2.5 换了 6 个槽；导出的 XPS 带齐四张图 |
| a08 全格式（`_hq_trial\pc_a08_hd\export\`，blend + XPS + PMX，91 秒） | PASS；7 个槽换成游戏材质（身体 ×2、皮肤、脸、头发 ×3），保留 4，错误 0；PMX 烘了 5 张颜色贴图，mmd_tools 读回无误。和 09-06 的旧 PMX 比：顶点同为 53,213；表情 9 → 58（面部表情插件）；关节 75 → 103（裙子格子物理）。胸部仍是模板 A，旁边另有 `pc_a08_hd_bustB.pmx`（`tune_bust_pmx.py` 默认值：下垂 15°、±25°）。对比图 `_hq_trial\pc_a08_hd\pmx_old_vs_hq.png` |
| 2.5 按钮点在导入的 a08 PMX 上（v1.1.15） | 认出 a08，原地换 7 个材质，激活游戏材质输出，`mmd_base_tex` 不变；a08 的 FBX 手动流程照旧全部 FINISHED |

对比图（同一套灯光：预览用的灰色世界 + 两盏太阳光，Eevee）：`_hq_trial\pc_a01_hd\compare_old_vs_hq.png`、
`_hq_trial\pc_g05_hd\compare_old_vs_hq.png`。看得出的区别：
- 衣服的皮革纹理、缝线、褶皱出来了，金饰有金属感；
- 皮肤有毛孔和透光，嘴唇有光泽；
- 头发的发丝有层次；
- Luf 的发色从浅灰变成深棕。

g05 原来的 .blend 和预览图备份在 `D:\roe_exports\_hq_materials\_old\g05\`。

## 5. 用法

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
.\export_character_models.ps1 -Only g05 -Format blend -Force     # 只重做 .blend + 预览，XPS / PMX 不动
.\export_character_models.ps1 -Format blend -Force               # 全部重做 .blend（XPS / PMX 不受影响）

# 单独升级一个已有的 .blend
& $blender -b --factory-startup <旧.blend> --python hq_materials_blender.py -- <新.blend>

# 只看材质数据
python hq_material_data.py g05 --out D:\roe_exports\_hq_materials --all
```

环境变量：
- `ROE_HQ_MATERIALS=0`：关掉；
- `ROE_HQ_CACHE`：缓存目录；
- `ROE_PYTHON`：装了 UnityPy 的 Python。

游戏更新后，删掉对应的 `<id>.json` 和用到的贴图，下次导出时会重新读取。

### 手动操作（Blender 界面）

一次性准备：
- Blender 3.6；
- ROE 插件 `scripts/riseoferos/roe_xps_addon.py`（安装见 `scripts/riseoferos/README.md` §1）；
- 导 XPS 还要 XNALaraMesh（XPS Tools）；
- 系统 Python 装了 UnityPy（本机已装），第 5 步要用。

以 g05 为例：

1. **提取**（没提取过的角色才要做）：
   ```powershell
   cd E:\code\othercode\ripper_tpose\scripts\riseoferos
   .\extract_character.ps1 g05 -ExportTextures
   ```
   结果在 `D:\roe_exports\g05\`。
2. 打开 Blender，删掉默认方块，按 `N` 打开侧栏，切到 **ROE** 页签，工作流选 **ROE**。
3. 填两个路径：
   - 「模型来源」FBX：`D:\roe_exports\g05\pc_g05_hd (1)\FBX_GameObjects\pc_g05_hd\pc_g05_hd.fbx`。
     要用带 `(1)` 的那份，不带的缺材质分区；
   - 「贴图目录」：`D:\roe_exports\g05\_textures`。
4. 点「**导入 FBX**」，再点「**2. 检查并准备材质**」。
5. 点「**2.5 游戏原始材质（高精度）**」。某个角色第一次点要几十秒（从游戏包读材质），之后走缓存。
   底部状态栏会显示「游戏原始材质：换了 N 个槽」。视口按 `Z` 选「材质预览」就能看到法线和金属效果。
6. **保存**：
   1. 文件 → 清理 → 清理未使用的数据（递归）；
   2. 文件 → 外部数据 → 打包资源；
   3. 文件 → 另存为。

   不先清理的话，打包会对 FBX 导入器留下、没人用的图片报「找不到文件」。结果不受影响，但错误一大串。
7. **要 XPS**：「XPS 输出」填一个不在 `D:\roe_exports\<角色>\` 里的路径（重新提取会清空那里），再点「**3. 导出 XPS(.mesh)**」。
   第 5 步点过的话，XPS 自动带上法线、AO、高光贴图。
8. **要 PMX**：用批量脚本最省事，发色和 AO 会烘进颜色贴图。
   ```powershell
   .\export_character_models.ps1 -Only g05 -Format pmx -Force
   ```
   会覆盖 `D:\roe_exports\g05\blend\pmx\` 里的 PMX。手动用 ROE PMX Tools 转的话，PMX 里没有烘好的发色和 AO。

### 导入 PMX 以后在 Blender 里用：ROE Game Materials 插件

用户的动画是在 Blender 里做的：把 PMX 导进来，用 MMD 骨架、物理和 VMD 动作。所以另做了一个独立插件
`scripts/blender_addons/roe_game_materials/`，已经用目录联接装好，勾选后在侧栏 MMD 标签页「ROE 游戏材质」。

- 用法：
  1. mmd_tools 导入 PMX；
  2. 选中模型，点「换上游戏原始材质」；
  3. 「游戏材质 / MMD 着色」可以来回切；
  4. 法线、毛孔、AO、光滑度、金属度、皮肤透光、头发粗糙度的滑块实时生效，1.0 = 游戏原始值。
- 做法：`hq_materials_blender.py` 的 in_place 模式。
  - 在每个 PMX 材质里另加一套 `hq_*` 节点和一个自己的输出节点，切换只改「哪个输出是激活的」；
  - mmd_tools 的节点一个不删。原因是 mmd_tools 改 MMD 材质时，只要发现自己的着色器输出没连着，就会把它连回输出。
    两边一直都连着，它就不会动；
  - 导出 PMX 读的 `mmd_base_tex` 也不变。
- 识别：
  - 贴图名 `<材质>__pmx_diffuse` / `__xps_diffuse` 直接对应游戏材质；
  - 老 PMX 的颜色贴图名在游戏材质的 `_BaseMap` 里查，身体和皮肤共用一张贴图，按材质名里的 skin 区分；
  - 角色代号从模型名或贴图名认。
- 踩到的坑：用 `is` 比较 Blender 的节点永远不成立（每次访问都是新的 Python 包装对象），
  结果两个输出都被设成非激活，Blender 退回第一个。要用 `==` 或按名字比较。
- 验证：
  - g05 bustB PMX：换了 6 个材质，保留 4 个（眼睛、睫毛、眉毛、泪膜）；
  - 切到 MMD 再切回、改 MMD 材质的漫反射色以后，激活的仍是游戏材质输出；
  - 法线滑块 1 → 2 实时生效；
  - 再导出 PMX，7 张贴图和原来一样；
  - 老的 Inase a01 PMX（原颜色贴图名）：换了 5 个材质，身体 / 皮肤分对，脸用了 a01 自己的脸部贴图；
  - 对比图 `_hq_trial\pc_g05_hd\pmx_mmd_vs_game.png`。

## 6. 限制和待办

- 没有逐项复刻的部分：
  - 眼睛着色器（虹膜视差、角膜缘）；
  - 头发的各向异性双高光（`_PrimaryShift` / `_SecondaryShift`）；
  - 皮肤 LUT；
  - AO 乘在底色上，游戏只压间接光，所以凹处会比游戏里略暗。
- XPS 没有带脸上的毛孔细节法线。XNALara 的 render group 22 / 23 有 microbump 可以放，还没做；
  XPS 的效果只在 Blender 里用 XPS Tools 读回看过，没在 XNALara / XPS 本体里打开过。
- PMX 格式本身没有法线和金属度，只能把发色和 AO 烘进颜色贴图；手动用 ROE PMX Tools 转的 PMX 不带这一步。
- 目前只有 g05 用新脚本重新导出了（.blend 在原位置；XPS / PMX 在 `_hq_trial\pc_g05_hd\export\`，没覆盖原来的），
  其余模型还是只有颜色贴图，要批量重跑 `-Format blend,xps,pmx -Force`。
- 套装（`assemble_suit_blender.py`）和裸模（`export_nude_model_blender.py`）走的是另外两条路，还没接这一步。
