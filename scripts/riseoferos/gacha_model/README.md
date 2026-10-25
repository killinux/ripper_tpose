# ROE 抽奖开场的女孩（pc_gacha01）—— 导出 .blend + PMX

游戏里抽奖的开场动画（要你点、拖、划她屁股的那段）用的模型，内部名 `pc_gacha01`。它不是哪个角色本人，是用几个角色的零件拼的，
所以 ROE 的批量导出（按角色编号找包、按编号首字母找家族贴图）导不出它。这里的脚本把它按 ROE 其他模型的同一套流程导出来。

2026-10-25 第一次导出，成品在 `E:\game_export\RiseOfEros\_抽奖模型\`（.blend、预览图、PMX、跳舞视频、说明.md）。

```
scripts/riseoferos/gacha_model/
  export_gacha_model.py        入口（系统 Python，要 UnityPy + Pillow）：提取 → 游戏材质 → .blend → PMX（→ 视频）→ 复制到成品目录
  build_gacha_blender.py       Blender 那一段：导入、拼泳衣、挂材质、游戏材质、预览、存 .blend
  inspect_bundle_renderers.py  看一个包（场景 / 预制体）里每个渲染器画的是哪个网格、哪个材质、哪张贴图，各在哪个包
```

## 用法

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos\gacha_model
python export_gacha_model.py                  # 全部步骤，结果复制到 E:\game_export\RiseOfEros\_抽奖模型（同名覆盖）
python export_gacha_model.py --video          # 再渲一段 PMX 跳手势舞的预览
python export_gacha_model.py --out D:\x --steps blend,pmx   # 用工作目录里已有的 FBX / 材质缓存重做后两步
python export_gacha_model.py --dry-run        # 只打印命令
```

工作目录缺省是 `%TEMP%\roe_gacha01`（`--work` 可改），里面是复制来的包、AssetStudio 导出的 FBX 和贴图、游戏材质缓存、每一步的日志。
从头到尾 6 分钟左右（不含视频，视频再加 4 分钟左右）。最后一行打印 `ROE_GACHA_EXPORT={json}`。

## 它由谁的零件拼成

游戏抽奖场景 `scene_meta3d_gachaintro.ab` 里实际画的（用 `inspect_bundle_renderers.py` 读出来的）：

| 部位 | 网格 | 材质 / 贴图 |
|---|---|---|
| 身体和头 | `pc_e01_nk_body`：**Miri（e01）的裸体**，29011 个顶点全部和 Miri 原版重合（0.1 mm 以内），少了头顶狐狸耳朵的 468 个顶点 | **Lynn（j）**：`pc_j_nk_body` 皮肤、`pc_j_nk_face` 脸、`pc_j_nk_eyebrow` 眉毛 / 睫毛、`pc_j_nk_eyes` 眼睛、`pc_j_nk_tears` 泪膜；牙齿 `pc_common_tooth` |
| 头发 | `pc_k01_nk_hair`：**Keleira（k01）的发型**（顶点数、UV 一样，形状调过） | `pc_gacha01_nk_hair`：Keleira 的发色贴图，颜色乘 0.49（比 Keleira 本人深） |
| 泳衣 | `Miriam_*`：Miri 那套泳衣的上下两件 | `pc_gacha01_Swimbra_obj001` / `pc_gacha01_SwimUnderwear_obj001`：抽奖专用的蓝白条纹 |
| 项链 | `Common_Upper_NeckArea_GemNecklace_obj001` | `GemNecklace_*` |

Lynn 的眉毛和虹膜贴图文件属于 Erin（d）家族（`pc_d_nk_eyebrow`、`pc_d_nk_eye_iris`）。Lynn 本人在游戏里也是借用这两张，
虹膜再乘 `_IrisColor`（偏红）。所以这张脸就是 Lynn 的眉眼和妆面，形状是 Miri 的。

用到的包（`export_gacha_model.py` 里的 `MODEL` / `MATS` / `TEXS`）：
- `chara_bare_pc_gacha01_nk_tutorial.ab`（模型）、`gacha_video_prefab_pc_gacha01.ab`（同一套网格，渲染器上挂着游戏的材质）；
- 材质包：gacha01 自己、j01 裸体、j 的头、公共；
- 贴图包：再加 d 的头、k 的头。

## 每一步

1. **extract**：把上面的包从安装目录 / 下载缓存（取新的）复制到工作目录，用 AssetStudioModCLI 导 FBX（参数同 `extract_character.ps1`：
   绑定姿势、不带动画、x100、按场景层级）和全部贴图。
2. **hq**：`hq_material_data.py` 读这 12 个游戏材质，解码贴图，生成 XPS / PMX 用的贴图，写进工作目录的材质缓存（id `j_gacha01`）。
   它本来按角色编号挑包，这个模型的材质散在四个角色的包里挑不到，所以把挑包的函数换成上面这张固定清单，其余照旧。
3. **blend**（`build_gacha_blender.py`）：
   - ROE 插件导入预制体的 FBX；
   - 删掉游戏运行时的辅助物（打码球的锚点、MagicaCloth 的屁股物理配置）；
   - 两件泳衣按骨骼名挂到本体骨架上；
   - 插件挂材质，裸模拆身体槽，牙齿单独一个槽；
   - 套游戏原始材质，渲预览，存 .blend（贴图打包，打开是材质预览）。
4. **pmx**：`export_suit_pmx_blender.py` 转 PMX，和套装、裸模的 PMX 同一套转换：
   - Convert_to_MMD5 骨骼、A-pose；
   - 58 个顶点表情；
   - 胸部、头发物理。

   泳衣标了 `roe_outfit`，所以 PMX 多一个「衣服非表示」（其他栏，1 = 泳衣隐藏）。
5. **video**（`--video`）：`render_pmx_dance.py` 跳默认的手势舞。

## 踩过的坑（都已在脚本里处理）

- **包里的模型没有真材质**：`chara_bare_pc_gacha01` 自己的渲染器挂的是占位材质 `default_material_bare`，游戏运行时才换。
  真的材质挂在抽奖场景和 `gacha_video_prefab_pc_gacha01.ab` 的渲染器上。所以本体用预制体导出的 FBX
  （`Prefab_pc_gacha01.fbx`，同一套网格），材质名就是游戏的（`pc_j_nk_body`……）。
- **泳衣是单独的根物体**：上衣、下装在包里各是一个根，各带一小段 `Root_G` 骨架（23 / 15 根骨）。导进来以后：
  - 换成本体的骨架（骨骼名都对得上，静止位置差 0.0005 mm）；
  - 删掉它们自己的骨架。
- **小零件被插件放大 100 倍**：ROE 插件的「导入 FBX」看到网格小于 0.5 m 就当成旧的厘米单位导出，整体放大 100 倍。
  单独一件泳衣就这么小，上衣导成了 26 m 宽。泳衣改走插件同一个导入函数（`import_fbx_compat`），跳过这一步。
- **上衣躺在地上**：上衣 FBX 的骨架根是 `Bip001` 节点，`Root_G` 成了空物体，Blender 的坐标轴转换没作用到网格上，
  网格还是 Y 轴朝上（胸的高度在 y 上）。
  - 脚本对每件泳衣试三种摆法：不转、绕 X 转 +90°、转 −90°，取离身体表面最近的（离最近身体顶点的中位距离）。
  - 实测上衣转 +90° 是 3.2 mm（其余两种 1.2–1.3 m）；下装不转是 4.3 mm。
- **下装那份 FBX 没有材质**：包里每件泳衣有两份，第二份的材质指向游戏没发的包。AssetStudio 导第一份下装时写贴图路径报错，
  导出来的是第二份。网格是同一个，材质按游戏的 `pc_gacha01_SwimUnderwear_obj001` 补上。
- **裸模拆身体槽按网格名找身体贴图**：`split_combined_nude_body` 拿网格名 `pc_e01_nk_body` 去找 `pc_e01_nk_body*Albedo*`，
  这个模型用的是 Lynn 的 `pc_j_nk_body`。调用时网格临时改名 `pc_j_nk_body`，完了改成 `pc_gacha01_nk_body`。
- **牙齿套着脸的贴图**：插件处理头部时，眼、睫毛、眉毛、泪膜以外的面都归脸。这次构建报告里 2870 个牙齿面原来全在 `face` 槽；
  之前导出的 ROE 模型也都没有单独的牙齿材质（Miri、Lynn 的裸模和 Luf 的 g05 都查过）。这里按 FBX 记下的原材质，
  把牙齿面分出来，单独一个 `tooth` 槽，用 `pc_common_tooth`。其他模型没改。
- **PMX 那步要一个活动物体**：从空场景建出来存的 .blend 没有活动物体，`export_suit_pmx_blender.py` 第一个 `mode_set`
  会报 `Context missing active object`。存之前选中骨架设为活动物体。

## 限制

- 游戏抽奖时屁股的 MagicaCloth 物理（戳了会晃）没做；PMX 只有导出流程自带的胸部、头发物理。
- 只认 `pc_gacha01`。以后游戏出了别的抽奖模型：
  1. 先用 `inspect_bundle_renderers.py` 读它的场景或预制体，看网格、材质、贴图各在哪个包；
  2. 改 `export_gacha_model.py` 的包清单；
  3. 再改 `build_gacha_blender.py` 的文件名、泳衣材质。
- 材质是 Blender 对游戏着色器的近似，和 ROE 其他模型一样（见 [docs/roe-hq-materials.md](../../../docs/roe-hq-materials.md)）。
