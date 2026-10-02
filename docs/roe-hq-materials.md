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
  - 套装（2026-10-01 起）：再读 `accessory_components_pc_<id>_suit_*`（材质）+ `chara_tex_components_pc_<id>_suit_*`
    （贴图），魔化（fm）套的共用部件读 `accessory_components_common_*`。腿环、臂毛、腿毛这些老部件在
    `accessory_<8 位哈希>_common_<部件>.ab` 里，按颜色贴图名 `Common_<部件>_rgbx_Albedo` 找；
    fm 这一组整组读（8 个小包）：臂毛的贴图放在 `…_common_fmmleghair_obj001` 包里，按名字对不上。
    查过的部件记在 `<id>.json` 的 `pieces` 里，同一角色后面再跑别的套装也不会把它们丢掉。
  - **名字不能当身份**（schema 4，2026-10-01）：
    - 贴图：g01 HD 服装的 MGAC 也叫 `pc_g01_nk_body_rgbx_MGAC`，和裸体身体自己的那张同名。原来按名字只解码先遇到的那张，
      g01 的套装和裸模身上就套了服装的 MGAC，皮肤上一块块深色斑。秘书装的胸罩，不透明版和透明版也是两张同名贴图。
      现在每个槽记下它真正引用的对象（`source` = CAB + path_id）；一个名字下有内容不同的几张图时，
      材质用自己那张，存成 `<主干>__<md5 前 8 位>_rgbx_<类型>`，写进 `overrides`。内容相同的拷贝照旧用原名。
      全游戏跨包同名而内容不同的贴图有 35 个：HD / LD 两份、几个角色的套装部件、g01 这张，见 §6；
    - **只差大小写也算同名**（2026-10-02）：`textures\` 是 Windows 文件夹，不分大小写。
      k01 战斗装的 `Clara_Eyemask_…` 和圣诞装的 `Clara_EyeMask_…` 是同一个文件，战斗装的眼罩就成了圣诞装的黑眼罩。
      现在按不分大小写分组判断；全游戏只有 k01 的眼罩和袖子两组；
    - 材质：两个套装可以有同名部件（g01 睡衣和瑜伽服都有 `Rouffe_Underwear_obj001`，一件黑蕾丝、一件白色运动款），
      原来只留贴图大的那个，瑜伽服就用了睡衣的。现在每个套装自己的定义另存一份 `<材质>@<套装>`，
      `pick_material()` 在 `pc_g01_yoga.blend` 里优先选 `…@yoga`。
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
| 全部主模型（10-01，blend + XPS + PMX） | 124 PASS / 0 失败（另 18 个 NOMESH）；700 个槽换成游戏材质、保留 499、错误 0；归档 464/464 自检通过 |
| a / g / j 的套装 + 裸模（10-01，就地升级） | 22 套 + 5 个裸模逐槽检查：全部是游戏材质或该保留的槽，没有灰色占位、没有缺贴图的睫毛；预览逐张看过；归档 51 个文件，自检 150/150。对比图 `_hq_trial\suits_agj\`（魔化耳朵、偶像装双丸子和睫毛、g01 皮肤斑块、22 套总图） |
| a / g / j 的套装 + 裸模 PMX（10-01） | 26 个（22 套 + 4 个裸模）全部 PASS：撕裂 0、付与顺序错误 0、表情 58、胸部物理两侧、头发物理；26 个胸部 B 版；PMX 里引用的贴图全部存在（第一轮 3 个裸模的睫毛贴图是 C 盘死路径，已修）；衣服顶点被头发链拽住的扫描 0；26 个用 mmd_tools 读回渲染逐张看过；冷艳主管 PMX 和 .blend 预览对比无差异 |
| 同名贴图核对（schema 4） | a/g/j 36 个角色的数据重读：需要各用各贴图的只有 g01（身体 MGAC、3 套内衣 / 胸罩）、g10（HD / LD）、j07 / j10（`_DissolveMap`，Blender 材质不用）。a/g/j 主模型实际用到的贴图和应有的逐张比对一致 |

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

# 套装 / 裸模（就地升级，--preview 重出预览图）
& $blender -b --factory-startup D:\roe_exports\j01\blend\pc_j01_idol.blend `
    --python fix_suit_slots_blender.py --python hq_materials_blender.py -- D:\roe_exports\j01\blend\pc_j01_idol.blend --preview
# 已经升级过的文件：再跑一次只补还是颜色贴图的槽；数据修过以后加 --rebuild 全部重建

# 套装 / 裸模的 PMX（和主模型同一套转换）+ 胸部 B 版
& $blender -b --factory-startup D:\roe_exports\j01\blend\pc_j01_idol.blend `
    --python export_suit_pmx_blender.py -- D:\roe_exports\j01\blend\pmx\pc_j01_idol\pc_j01_idol.pmx
python ..\mmd_physics\tune_bust_pmx.py <.pmx> <同目录>\pc_j01_idol_bustB.pmx
```

`export_suit_pmx_blender.py` 调主模型的 `export_pmx()`：Convert_to_MMD5 骨架、胸 / 布料 / 头发物理、58 个表情、撕裂门禁、
付与顺序回读。转换前补三步，`.blend` 不保存：
- 高清材质换成烘好的 PMX 颜色贴图（`roe_hq_pmx`），和主模型导 PMX 时一样；
- 眼睛槽按材质名 `eye` 找，烘成贴图。套装的头在身体网格上，眼睛不在主模型的第 1 槽；
- 挂在骨头上的部件改成 100% 蒙皮到那根骨。mmd_tools 只写顶点权重，不认物体父级。

打包在 `.blend` 里、原文件已经不在的贴图，会先写到 PMX 旁边。裸模的睫毛贴图指向一个删掉的 C 盘临时目录，
不这样做 PMX 里会存一个死路径。游戏本身给服装做了胸部骨骼权重（马甲、胸罩、外套都有），所以服装会跟着胸部物理动。

`fix_suit_slots_blender.py` 补 10-01 之前拼好的套装 / 裸模的问题，放在升级前面跑，没问题的文件什么都不改：
- i / j 族的睫毛、眉毛卡片是透明的（插件 v1.1.16 之前），按 `EYEBROW_TEXTURE_FAMILY` 换上 h / d 族的贴图；
- 魔化耳朵 `FMRear_L/R`：存根里它的材质指向 `chara_mat_bare_pc_f01_fm_nk.ab` 的 `pc_f01_fm_nk_face`，拼装没读这个包，
  所以是灰色。各家族脸部贴图的布局相同，连尖耳朵那块都有，所以换成本套装自己的脸部材质。
  耳朵的顶点是按 f01 的身材建的（f01 头骨比别人低约 15 cm），别的角色身上它挂在锁骨处；
  按头骨位置差平移，再绑到 `Bip001 Head`，和 f01 一样；
- 偶像装双丸子的第 2 个材质槽，游戏里是角色头发 `pc_j_nk_hair`（在 `chara_mat_bare_pc_j_common_head.ab`，拼装也没读），
  原来是灰色，换成头发网格的材质；
- 一点权重都没有的蒙皮部件（a01 婚纱头纱、j01 新年装耳环、j01 降神装面纱）：游戏里它们只绑在自带的物理骨骼上，
  拼装没把这些骨骼接上骨架。现在按 suit.json 的部位骨整体绑定（这 4 个都是 `Bip001 Head`），能跟着头动，没有自己的摆动。
借来的 HQ 材质会复制一份，UV 节点改成部件自己的第一层 UV（部件叫 UVMap，身体 / 头发叫 UV0）。

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
- 124 个主模型 10-01 全部用新脚本重导（blend + XPS + PMX），已归档到 `E:\game_export\RiseOfEros`。
- 套装和裸模：`.blend` 就地升级（`hq_materials_blender.py`）。a / g / j 另外出了 PMX + 胸部 B 版（`export_suit_pmx_blender.py`），
  XPS 都还没有。
  - 用户 10-01 说只要 a / g / j：这三个角色的 22 套服装 + 5 个裸模逐槽查过、修过、归档了，
    22 套 + 4 个裸模有 PMX（a00 的裸模就是主模型 a00，本来就有）；
  - 拼装留下的两处 10-02 修好了，原因是同一个：自带物理骨的配件放错了位置。
    改的是 `suit_bundle.py` 的放置公式，见 [roe-suit-assembly.md](roe-suit-assembly.md)「2026-10-02：自带物理骨的配件」：
    - **j01 新年装耳环**：两只原来都藏在头的正中间，现在左右各挂在耳垂下；
    - **a01 婚纱头纱**：原来向后平伸（10-01 只修了「落在脚边」，用的还是错的放法），现在罩在头上垂到肩膀；
    - 这两套 10-02 重做了一遍：重拼 → 插槽修复 + 游戏材质 → PMX + 胸部 B 版 → 画廊 → 归档；
    - 用户随后要 a/g/j 以外的也修，渲染对比后实际坏的是 4 套：f01 2024 圣诞（帽子挂在后脑勺下）、f01 新年（右流苏叠在左边）、
      h01 护士（左耳环叠在右边）、k01 战斗（耳环在头里）。这 4 套走了同样的流程（重拼 → 插槽修复 + 游戏材质 → 画廊 → 归档），
      它们本来就没有 PMX，所以没出；
    - d01 魅魔、f01 牛重拼后和旧版一样，配件建在原位，本来就对。E 盘上的没换，D 盘上的是重拼后的游戏材质版；
    - k01 战斗装的眼罩、袖子贴图名和圣诞装 / 婚纱装只差大小写，缓存里串成了一个文件（眼罩变黑）。
      `hq_material_data.py` 已改成不分大小写判断同名，见 [roe-suit-assembly.md](roe-suit-assembly.md)「贴图名只差大小写」；
  - 其余角色的套装 / 裸模在 D 盘上也升级了（批量在收到「只要 a g j」之前就跑完了），但**没检查、没归档**，已知还有：
    - b / c / d / e / f / h / i / k / l / m 的魔化套：耳朵是灰色的（除 f01 外还挂在锁骨），腿环、臂毛、腿毛没换材质
      → 跑一遍 `fix_suit_slots_blender.py` + `hq_materials_blender.py`；
    - i01 的套装和裸模没有睫毛（拼装早于插件 v1.1.16），同上；
    - b01 police / wulin、c01 bohemia / student、d01 archer、k01 swim / weddingdress 有同名部件，
      要 `--rebuild` 才会用上各自的贴图；d01 succubus、k01 combat 10-02 已经用新数据重拼。
- 以后重新拼套装（`export_suits.py --force`）会丢掉 `fix_suit_slots_blender.py` 的修改：
  - 魔化耳朵、双丸子要再跑一次修复脚本，PMX 也要重出；
  - i/j 睫毛新拼出来就是对的（插件 v1.1.16）；
  - 头纱 / 耳环的权重拼装器自己会绑（10-02 起）。
  根治要在 `suit_bundle.py` 里解析指向别的包的材质引用（存根引用了 `pc_f01_fm_nk_face`、`pc_j_nk_hair`），还没做。
- 升级后的 `.blend` 里留着几张没人用的图片（被换掉的插件材质在保存那一刻还算它们的用户），指向原来的解包目录。
  不影响打开和渲染，归档时会自动打包补齐。
