# Vindictus 关卡还原：北方遗迹 → Blender 场景

把游戏里的关卡 `S1_Northruin_01`（北方遗迹）还原成 Blender 场景：地形、岩石、遗迹、树、草和游戏自己的天空都按关卡数据摆好，
再裁成渲染视频用的轻量版本。变身视频（mmd_disperse）的北方遗迹背景就是这样做出来的（2026-10-05/06）。

游戏是 2024-03 的 Pre-Alpha（UE 5.3），装在 `E:\tools\vindictus\`。AES key 只在 `E:\tools\vindictus\_download\aes_key.txt`，
不进仓库、不进文档，命令里都是从这个文件读。

## 成品在哪

| 文件 | 是什么 |
|---|---|
| `E:\game_export\Vindictus\_disperse\场景和材质\北方遗迹场景\northruin_v3v.blend` + `textures\`（277 张，1.2 GB） | 视频版场景：只留镜头看得到的部分，贴图缩到 1K；图片都是绝对路径，整个文件夹可以直接用 |
| `E:\game_export\Vindictus\_disperse\场景和材质\北方遗迹_静帧测试.jpg` | 第 1 对变身在场景里的 4 张静帧 |
| `E:\game_export\Vindictus\_disperse\场景和材质\北方遗迹_还原对比_测试.jpg` | 游戏加载画面和还原结果并排对比 |
| `E:\game_export\Vindictus\_disperse\0n_*_北方遗迹.mp4` | 用这个场景渲染的变身视频 |

完整场景（`northruin_v3.blend`，带全部 4K/8K 贴图）和中间数据（关卡 JSON、7.1 GB 的导出素材）在 2026-10-06 清理磁盘时删掉了。
要换角度或换地点，就从第 1 步重新做一遍，大约 1 小时，其中大部分时间花在第 4 步。

## 流程一览

| 步骤 | 脚本 | 输入 → 输出 | 耗时 |
|---|---|---|---|
| 1 修补类型映射 | `patch_usmap.py` | TFD 的 UE 5.2 usmap → `vdf53_patched.usmap` | 几秒 |
| 2 关卡转 JSON | CUE4Parse CLI | 66 个关卡分块 `.umap` → `nr_json\`（98 MB） | 3 分钟 |
| 2b 蓝图模板 | `list_templates.py` + CUE4Parse | 分块里引用的 50 个蓝图包 → `tpl_json\` | 很快 |
| 3 摆放清单 | `level_extract.py` | JSON + 原始字节 → `placements_nr.json`（50721 件） | 6 秒 |
| 4 导出素材 | `export_level_assets.py` | UE Viewer：308 个模型包 + 16 个地形分块 → `assets\`（7.1 GB） | 约 40 分钟 |
| 5 缩贴图 | `shrink_textures.py` | `assets\` → `assets_lo\`（1K，地形层 2K） | 1 分钟 |
| 6 搭场景 | `build_level.py`（Blender 3.6） | → `blend\northruin_v3.blend` | 2 分钟 |
| 7 裁成视频版 | `cull_set.py`（Blender） | → `blend\northruin_v3v.blend` | 几分钟 |
| 8 检查 + 搬家 | `verify_append.py`、`relocate_scene.py` | → E 盘的 `北方遗迹场景\` | 几分钟 |
| 静帧 | `render_views.py` | 任意机位的 EEVEE 静帧 | |

探索用的脚本：`zen53.py`（UE 5.3 包读取）、`usmap.py`（查一个类的属性顺序）、`survey_cells.py`（统计每个分块的组件类型）、
`find_overhangs.py`（找悬空的大岩石，用来定位加载画面的机位）、`grass_types.py`（解景观草类型，结果已在 `grass_types.json`）。

## 前提

- CUE4Parse 命令行版：`E:\tools\cue4parse_cli\cue4parse.exe`（Oodle 用同目录的 `oodle-data-shared.dll`）。
- UE Viewer 的 UE5 版：`E:\tools\umodel_specific\materials\umodel_materials_ue5.exe`。
- 《第一后裔》的 UE 5.2 类型映射：`E:\tools\tfd\Mappings_2024-07-16_gildor.usmap`（第 1 步在它上面打补丁）。
- 容器文件清单：`E:\tools\vindictus\_download\utoc_files.txt`。
- Blender 3.6.15，命令一律带 `--factory-startup`，要装好 PSK 导入插件 `io_scene_psk_psa`（`build_level.py` 用它读
  UE Viewer 导出的 PSKX）；Python 要有 numpy 和 Pillow。
- **短路径联接点**：UE Viewer 和 CUE4Parse 的输出路径很长，放在深目录下会超过 Windows 的 MAX_PATH（报 `Error creating file`）。
  `build_level.py` 和 `cull_set.py` 写死了联接点 `C:\Users\haoni\AppData\Local\Temp\vdfs`，所有工作文件都放在它下面。
  它应指向一个有 10 GB 空间的目录，例如 `E:\vdf_level_work`。用 PowerShell 建（Git Bash 的 `mklink` 会把参数弄坏）：

  ```powershell
  cmd /c rmdir C:\Users\haoni\AppData\Local\Temp\vdfs      # 只删联接点本身，不删目标里的文件
  New-Item -ItemType Directory -Force E:\vdf_level_work
  New-Item -ItemType Junction -Path C:\Users\haoni\AppData\Local\Temp\vdfs -Target E:\vdf_level_work
  ```

## 每一步的命令（Git Bash）

```bash
R=/e/code/othercode/ripper_tpose/scripts/vindictus/levels
W=C:/Users/haoni/AppData/Local/Temp/vdfs          # 联接点
B="/d/Program Files/blender-3.6.15-windows-x64/blender.exe"
PAKS="E:/tools/vindictus/Vindictus/Content/Paks"
K="$(tr -d '\r\n' < /e/tools/vindictus/_download/aes_key.txt)"   # 只放在变量里，不要打印
cd "$W"

# 1  usmap 补丁
python $R/patch_usmap.py E:/tools/tfd/Mappings_2024-07-16_gildor.usmap vdf53_patched.usmap

# 2  66 个关卡分块 -> JSON（输出里可能带 key，用 grep 滤掉）
/e/tools/cue4parse_cli/cue4parse.exe -i "$PAKS" -g GAME_UE5_3 -k "$K" -m "$W/vdf53_patched.usmap" -f json -y \
    -o "$W/nr_json" -p "Vindictus/Content/VindictusRoot/Environment/Levels/Season1/S1_Northruin_01/*.umap" 2>&1 \
    | grep -v -i "$K" | tail -2

# 2b 分块里的蓝图组件只存了和模板不同的属性，模板也要转
python $R/list_templates.py nr_json > tpl_container.txt
ARGS=(); while read -r p; do ARGS+=(-p "$p"); done < tpl_container.txt
/e/tools/cue4parse_cli/cue4parse.exe -i "$PAKS" -g GAME_UE5_3 -k "$K" -m "$W/vdf53_patched.usmap" -f json -y \
    -o "$W/tpl_json" "${ARGS[@]}" 2>&1 | grep -v -i "$K" | tail -2

# 3  摆放清单
python $R/level_extract.py nr_json tpl_json placements_nr.json

# 4  素材：先模型（3 路并行），再地形分块（单路）；中断了重跑会接着做
PYTHONIOENCODING=utf-8 python $R/export_level_assets.py placements_nr.json "$W/assets" --lanes 3 --meshes-only
PYTHONIOENCODING=utf-8 python $R/export_level_assets.py placements_nr.json "$W/assets" --lanes 1 --cells-only

# 5  视频版用的小贴图
python $R/shrink_textures.py assets assets_lo \
    --landscape-mi "assets/VindictusRoot/Environment/Levels/Season1/S1_Northruin_01/MI_Northruin_Landscape_01.props.txt"

# 6  搭场景：以她站的位置为中心（UE 坐标，厘米；负数要写成 --center=X,Y）
mkdir -p blend
"$B" -b --factory-startup --python $R/build_level.py -- --placements placements_nr.json --assets "$W/assets" \
    --center=84200,35500 --radius 20000 --far 150000 --foliage-radius 9000 \
    --grass "84200,35500,180,4000,9000,600" --sun-rot 130 --sun-elev -1 --haze 1500 --out blend/northruin_v3.blend

# 7  视频版：spot 是 Blender 坐标（米），z 是地面高度
"$B" -b blend/northruin_v3.blend --factory-startup --python $R/cull_set.py -- \
    --spot=842.0,-355.0,-64.82 --lo assets_lo --out blend/northruin_v3v.blend

# 8  按变身脚本的方式追加一遍，应当 missing 0；再连同贴图搬到 E 盘，再查一遍
"$B" -b --factory-startup --python $R/verify_append.py -- "$W/blend/northruin_v3v.blend"
"$B" -b blend/northruin_v3v.blend --factory-startup --python $R/relocate_scene.py -- \
    "E:/game_export/Vindictus/_disperse/场景和材质/北方遗迹场景" northruin_v3v.blend
"$B" -b --factory-startup --python $R/verify_append.py -- \
    "E:/game_export/Vindictus/_disperse/场景和材质/北方遗迹场景/northruin_v3v.blend"
```

静帧（机位 `名字:相机 x,y,z:目标 x,y,z:焦距[:宽x高]`，UE 坐标，厘米；`--disperse` = 变身视频的色调和竖幅）。
下面两个是当时用的：加载画面的视角，和视频相机转到 100° 时的位置：

```bash
"$B" -b blend/northruin_v3.blend --factory-startup --python $R/render_views.py -- --out "$W/views" \
    --cam "ls_view:86000,37500,-6428:72000,41000,-6238:18"
"$B" -b blend/northruin_v3v.blend --factory-startup --python $R/render_views.py -- --out "$W/views" \
    --cam "t100:84633,35424,-6307:84200,35500,-6312:50" --disperse
```

### 放进变身视频

`disperse_pair.py --bg "set|<场景.blend>|x,y,z|turn"`：x、y 是 Blender 坐标（米，= UE x / 100、−UE y / 100）；
z 是向下打射线找地面的起点高度，打不到地面时就把 z 当作地面；turn 是人物和机位绕 Z 轴转的角度。北方遗迹用的是：

```
set|E:\game_export\Vindictus\_disperse\场景和材质\北方遗迹场景\northruin_v3v.blend|842.0,-355.0,-40|100
```

她站在 UE (84200, 35500)，地面 −6482 cm 处的平沙地上；turn 100 = 朝 UE 170°，身后是挂满藤蔓的悬空巨石和哥特遗迹。
这一带地面起伏 0.5–1 m，视频相机的高度跟着她的脚走，所以选了这块平地。

## 原理和坑

### 1. 为什么要补 usmap

Vindictus 没有公开的 usmap（属性类型映射）。用 UE4SS 从游戏里导也不行：这个 Pre-Alpha 启动约 2 秒就以 255 退出（它自己的启动检查，
不去绕过）。UE 5.2 的 TFD 映射能解地形，但 `StaticMeshComponent` 只解出 StaticMesh，位置旋转全丢了，因为 5.3 多了几个属性，
后面的序号全部错位。补丁的偏移是对着关卡数据本身一个个核出来的：

- `StaticMeshComponent` 多 2 个属性：OverrideMaterials 31 → 33，补两个假 bool 在末尾；
- `PrimitiveComponent` 多 3 个，在 IndirectLightingCacheQuality 之前：BodyInstance 122 → 127，补在开头；
- `HierarchicalInstancedStaticMeshComponent` 多 1 个（12 → 13），补在本地序号 6；
- `CacheMeshExtendedBounds` 带着自己的 unversioned 头写入，CUE4Parse 却按原生 BoxSphereBounds 读，差 2 字节，
  导致 StaticMesh 变成 null。把它改成一个结构相同的 usmap 结构体 `Vdf53BoxSphereBounds` 来读。

UE 5.3 zen 包的两个细节：导出数据按 CookedSerialOffset（也就是导出序号）顺序排，不按 export bundle 的顺序，按后者读组件会错开
18 字节；unversioned 属性的顺序是子类属性在前，父类的排在后面。`zen53.py` 和 `usmap.py` 是验证这些用的。

### 2. 摆放：UE 坐标 → Blender

- 普通模型组件（11007 个）：世界矩阵 = 本地矩阵 × AttachParent 链；蓝图组件缺的属性从模板（`tpl_json`）里取。
- 植被实例（34800 个）不在 JSON 里，是 HISM / 植被组件的原生数据：`int32 128, int32 n, n × FMatrix`
  （16 个 double，行主序，平移在 [12:15]），所以从包的原始字节里扫出来。实例矩阵相对于组件，组件又挂在
  InstancedFoliageActor 下面，这个 Actor 的位置在所属 25600 网格的中心。
- 打包关卡 Actor（BPP_*）的 ISM 实例（4284 个）在 JSON 的 PerInstanceSMData 里，模型从蓝图模板里取。
- 样条模型（630 个）先用直的替代。
- 地形：8 × 8 个组件，每个 126 格，每格 1 m，从 (0, 0, −1750) 开始，Z 缩放 30；组件位置就是 SectionBase × 100。
  高度 = (R × 256 + G − 32768) / 128 × 30。各层权重图的分块布局和高度图一样（采样加 0.5 texel 偏移）。
  层：1 沙、2 泥、3 草、4 焦土、5 雪（山顶）、6 坡上的岩石。
- UE 是厘米、左手系，UE Viewer 导出的 PSK 已经做过 Y 镜像，所以一个 UE 矩阵 M（行向量）在 Blender 里是 F Mᵀ F，
  F = diag(1, −1, 1)，平移除以 100。模型数据保持厘米，物体缩放 1/100。

### 3. 材质

- 贴图：Albedo、Normal（DirectX 格式，G 通道翻转）、ORM（G = 粗糙度；这个游戏的 DpR、ORDp 等打包里 B 都不是金属度）。
  植物按 ORT / Mask 的 R 通道裁剪，它们的 albedo 没有 alpha。
- 颜色参数：`Color_Tint` 的 A 是混合量（0 / 0.2 / 0.3），不是乘满。第一版把藤蔓帘子的 (1,1,0) 全乘上去，结果是黄的。
  `Albedo Controls` / `Color_Control` = (亮度, 饱和度, 对比度)，用 HueSat 节点取前两项，饱和度上限 1.5：River Saltbush
  要求 3，那样会变成荧光色。双面树的预设要用 `*Leaves` 那一对参数，不能用普通的 Albedo Tint (1, 0, 0.78)，否则是品红。
- Megascans 预设的悬崖（1044 处）没有 Albedo，用的是平铺的地衣图 BlendingBasecolor。这里把它压灰（饱和度 0.3、明度 0.75），
  MossBlend > 0 时朝上的面盖苔藓 `T_Moss01A_D`。第一版没做这一步，悬崖是亮黄色。
- 地形各层：`<n>BaseColor / Normal / ORMH`，加上该层的 `<n>AlbedoTint`、`<n>AlbedoControls` 和 AO^(AO_Intensity/2)。

### 4. 草：游戏运行时才长出来的

关卡里没有地形上的草，UE 是运行时按 LandscapeGrassType 撒出来的。`grass_types.py` 不靠 usmap 直接解了这些包：草层 3
（LGT_3）是 Kikuyu 草，每 100 m² 500 棵，缩放 1.5–1.8，还有花、滨藜、棉草和小石头；层 1（LGT_1）是石头；剔除距离 100 m。
`--grass x,y,dir,r_full,r_max,clear` 用几何节点只在镜头方向（dir ±100°）撒，r_full 以外密度降到 1/3，并在她脚下清出半径 clear
的空地（6 m，免得草挡在 3.9 m 外的镜头前）。

### 5. 天空：用游戏自己的

关卡里有两个 `SM_SkyDome`，材质 `MI_EmissiveAdditiveSky_01` 的发光贴图是 Poly Haven 的 HDRI
`kloofendal_48d_partly_cloudy_puresky_4k`，乘 1.5（另有 SkyAtmosphere、体积云、高度雾和 SkyLight 立方体贴图）。
`build_level.py` 默认把这张 HDRI 用作世界环境（`--sky-hdr`，传空串就改回 Nishita 天空）。`--sun-elev -1` 时，太阳取全景图最亮的
那个像素（高度角 43.8°），再转动全景图，让图里的太阳和灯光方向对上。几个在 Blender 里实测过的事实：

- 等距柱状投影：u = 0.5 − atan2(y, x) / 2π（u 0.5 = +X，0.25 = +Y，0 = −X），图像行从下往上存；
- Mapping 节点 POINT 类型的旋转作用在查询方向上，所以角度 = 图里的方位 − 想要的方位；
- 强度 S 的日光照在白色漫反射平面上，亮度是 S/π。

`--haze 1500` 是空气透视：越远越往地平线颜色 (0.44, 0.47, 0.57) 靠，最多 0.8（`--haze-cap`）。

### 6. 视频版为什么要裁

完整场景每帧 50–120 秒：EEVEE 把所有贴图不压缩地放进显存，几百张 4K/8K 加上两个角色和别的程序，16 GB 显存溢出；而且 3367 个物体
每帧都要重新同步。

- `shrink_textures.py`：缩成 1K，地形层 2K，415 张，用时 1 分钟；
- `cull_set.py`：只留变身视频的镜头看得到的部分，覆盖 turn 90–110 的环绕和推近到 0.55 倍距离，再加她周围 35 m 一圈投影物；
  草的载体面裁到视野里（14914 → 4299）；不用的源模型删掉（26 个）。结果是物体 1734 留、1463 删，实例 6020 → 1896，
  贴图 282 张里换了 217 张。

之后每帧 8–13 秒（第一帧 33 秒，含着色器编译）。换机位要用新的 `--turn` 重新裁。

### 7. 路径的坑：联接点和真实路径

Blender 打开 .blend 用的是真实路径（长路径），变身脚本追加场景时用的却是联接点路径。保存时写的相对路径 `//..\..\..` 一换基准就指错了，
草、藤蔓和天空全部变成品红。现在 `build_level.py` 和 `cull_set.py` 保存前把每张图都改成联接点下的绝对路径，并用
`save_as_mainfile(relative_remap=False)` 保存。`verify_append.py` 按变身脚本的方式追加，列出找不到的图（应为 0 / 277）。
`relocate_scene.py` 把场景和它用到的所有图片搬进一个文件夹，同样写绝对路径，所以搬家后工作目录可以删。

## 没做的和已知限制

- 样条模型是直的（没按样条弯曲）；水面（`S_WaterPlane_256`）没放。
- 关卡实例 LevelInstance（304 个）没有展开。
- 由 Chaos 几何集合做的蓝图道具（橡树 BG_Oak、罐子）跳过了。
- 天空球（改用世界环境的 HDRI）、雾片、水面、方块占位体和碰撞体积（BlockingVolume）不导入；游戏里的高度雾和体积云用
  `--haze` 近似。
- 冰谷 `S1_Icevalley_01`（34 个分块）没做。这套脚本应该能用，地形层和材质预设要另外核对。
- 主城 Colhen 没有关卡数据，只有素材。
