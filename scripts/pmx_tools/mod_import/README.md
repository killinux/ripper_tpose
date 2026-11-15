# 把 Nexus 上的游戏 mod 转成 PMX / 高清材质 .blend（2026-11-01）

用户下了两个 mod 要「转成高清材质的 blender，然后衣服加入到木兰的改造中」：怪物猎人世界的
`HPN SkimpyER Velkhana Armor - Empress V3.1`（#3318，.mod3 / .mrl3 / .tex）和上古卷轴 SE 的 `COCO Mulan - CBBE 3BA`（#89916，.nif / .dds）。
这里是两条转换链，都是普通 Python + Blender 后台，不装 Blender 插件。

## 工具

| 脚本 | 跑在哪 | 做什么 |
|---|---|---|
| `mhw_tex2dds.py <tex dir> <png dir>` | 普通 Python | MHW `.tex`（版本 0x10）→ DX10 DDS → texconv → PNG。头：0x14 mip 数、0x18/0x1C 宽高、0x24 格式（0x16 BC1、0x17 BC1 sRGB、0x1A BC5、0x1F BC7 sRGB），0xB8 起的 u64 偏移表，数据从第一个偏移开始；BC5 法线要 `texconv -f R8G8B8A8_UNORM` |
| `mod3_to_pmx.py` | **Blender 的 Python**（`blender -b --factory-startup --python mod3_to_pmx.py -- --out X.pmx --tex PNG目录 a.mod3 b.mod3 …`，mod3 解析器要 mathutils） | 用 AsteriskAmpersand 的 Mod3-MHW-Importer 源码（`E:\tools\mod_importers\mod3_src`，只用它的 mod3 / mrl3 解析，插件本身是 2.79 的）读网格、权重、骨架、材质→贴图；按 MHW 的 bone function 搭标准 MMD 骨架（11-14 起：0 → 全ての親（放到地面）、新建无权重的センター、13 骨盆 → 下半身、1 → 上半身、2 → 上半身2（锁骨挂在它上面）、3 → 首、4 → 頭，5–8 左肩/腕/肘/手首 9–12 右，81/83 → 手捩，14–17/18–21 腿 31–46/48–63 手指；关节上的辅助骨把权重交给关节的 MMD 骨，控制骨上不挂权重；≥100 的是每件装备自己的布料骨，按文件分开；标准骨补尾端）；MHW 是 Y 上 Z 前 左 = +X、厘米、骨盆在原点：按肩（func 6）/脚踝（func 16）高度缩放到目标（a08：141.1 / 16 cm），Z 取反，面按法线重定绕向 |
| `mod3_probe.py` | Blender 的 Python | 打印一个 mod3 的骨架（function、位置）和网格分块 |
| `nif_to_pmx.py --out X.pmx --tex PNG目录 a.nif b.nif …` | 普通 Python | 用 PyNifly 的 `pyn` 库（`E:\tools\mod_importers\io_scene_nifly`，NiflyDLL.dll，不用进 Blender）读 Skyrim SE 的 NIF（BodySlide ShapeData 里的 nif 自带整套 NPC 骨骼的全局位置）；NPC 骨名 → MMD 名（Pelvis 下半身、Spine/1/2 上半身/2/3、Clavicle 肩、UpperArm 腕、Forearm ひじ、Hand 手首、Thigh 足、Calf ひざ、Foot 足首、Finger00–42 手指、Breast01 胸；其余蒙了皮的节点（扭转、胸、臀辅助骨、SMP 链）挂到编号链的上一节，或离它最近的标准骨段——11-14 前都挂在センター上；没蒙皮的形状节点不建骨；标准骨补尾端），Skyrim 是 Z 上 +Y 前 左 = −X、约 1.33 cm/单位：按髋（L Thigh）/ 脚踝（L Foot）高度缩放到目标（99.3 / 16 cm）；贴图取非 _n/_m/_e 的那张 |
| `pmx_to_hq_blend.py --pmx P --out X.blend --preview P.png` | Blender | mmd_tools 导入 PMX，材质换成 Principled：MHW `_NM`（BC5 只有 RG，蓝通道补 1）、`_RMT`（R 粗糙度、G 金属度）、`_EM` 发光；Skyrim `_n`（法线，alpha = 高光 → 粗糙度取反）、`_m`（金属 / 环境遮罩）；打包贴图、存 .blend、渲一张 900×1400 预览（mmd_tools 导入后输出格式会变成动画格式，渲染前要设回 PNG） |

`pmxlib.py` 是写 PMX 的小封装（经 `pmx_head_swap/core.py` 用 mmd_tools 的 pmx 模块）。

## 两个 mod 的结果

- MHW Velkhana：`E:\game_export\MonsterHunterWorld\Velkhana_SkimpyER\pmx\Velkhana_SkimpyER\`（19 个盔甲材质，185 根骨，贴图目录里连 NM / RMT / EM 一起放）
  和 `blend\Velkhana_SkimpyER\Velkhana_SkimpyER.blend`（72 MB，贴图已打包）+ `preview.png`。身体（Empress，材质 Ch_Skin_Mt）没有贴图，归档版不带；
  工作目录里另有带身体的 `…_withskin.pmx` 给换装插件当供体身体（`--donor-body "f_body085_0000_Ch_Skin_Mt__7_10,f_leg085_0000_Ch_Skin_Mt__7_2"`）。
- Skyrim COCO Mulan：`E:\game_export\SkyrimSE\COCO_Mulan\pmx\COCO_Mulan\`（27 个材质：裙、披肩、金属肩甲 / 领、手套、袜、鞋、内裤，
  含 CBBE 3BA 身体 / 手 / 脚的参考网格（无贴图，材质名 `*_3BA` / `Shoes_Feet` / `Gloves_Hands`，贴合时当供体身体）；
  SMP 碰撞盒和私处网格已去掉）和 `blend\COCO_Mulan\COCO_Mulan.blend` + `preview.png`。

## 坑

- GitHub release 的 zip 用 curl 下三次都是截断的（中间坏块，7z 报 "Cannot open the file as archive"，python zipfile 能列目录但解不出）：
  换 `ghproxy.net` / `gh-proxy.com` 镜像或多试，下完一定 `zipfile.testzip()`。
- Blender 自带 Python 没有 PIL；Mod3 解析器要 mathutils（PyPI 的 mathutils 在 Python 3.13 装不上，所以在 Blender 里跑）。
- 第一次把 Velkhana 整套搬到 a08 上（11-01，`build10\v4_velk.pmx`）只对了一半：胸甲、腰部水晶裙全错位。原因全在转换出来的骨架（11-14 修）：
  1. MHW 的骨盆根骨（function 13）叫成了センター、腰甲 68 % 的权重挂在它上面——别的模型的センター不在骨盆（a08 在 43 cm），按骨名搬过去腰甲掉到小腿；
  2. 脊椎 / 头错了一节（上半身2 在胸口上沿、首在后脑），胸甲低 5–27 cm、头冠低 9 cm；
  3. 两个转换器写的骨都没有尾端（`displayConnection = -1`），换装插件比不了骨的方向，T 字姿势的护臂只被逐段平移、不转到 A 字；
     `pmxlib.connect_tails()` 补上（链的下一根骨，扭转骨沿臂段给一个偏移）；
  4. Skyrim 的辅助骨全挂在センター上（同 1），上臂扭转骨 `NPC L UpperarmTwist1` 在肩关节，名字却对上 a08 在上臂 80 % 的 `左腕捩`——
     换装插件 0.4.1 让扭转骨按它在臂段上的比例对位。
  修完后两个 mod 都先整套「按体形贴合」搬到 a08 的完整裸体，挑零件再原样移植进木兰（见 `scripts/pmx_tools/mulan_dragon_hunter/v2/README.md` 的 v10 节）。
