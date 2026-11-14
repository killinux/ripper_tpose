# ELDEN RING / SEKIRO 角色 mod → 高清材质 Blender / XPS / PMX

把 Nexus 上的 ELDEN RING 和 SEKIRO（只狼）角色 mod 转成：

- `.blend`：游戏原尺寸贴图的 PBR 材质（颜色、金属度、粗糙度、法线、自发光），骨骼、权重、法线都是游戏原样；
- `.xps`：骨骼改成 Biped 名，XPS 的标准姿势能直接用；
- `.pmx`：MMD 标准骨骼 + IK、身体碰撞体、胸部物理、眼睛骨骼（両目）、头发物理链。

两个游戏是同一家的格式（DCX / BND4 / FLVER2 / TPF），只狼的材质是 MTD（贴图由 FLVER 自己列出），ELDEN RING 是 MATBIN，脚本两种都认。
本机不用装游戏：mod 自带模型和贴图；解压要的 Oodle 用 CUE4Parse 下载的 `E:\tools\cue4parse_cli\oodle-data-shared.dll`，
BC6H 和 Pillow 读不了的贴图用 DirectXTex 的 `E:\tools\directxtex\texconv.exe`，`.rar` / `.7z` 用 `E:\tools\7zip\7z.exe`（`SEVEN_ZIP` 可改）。

## 一条命令

```powershell
cd scripts\eldenring
python export_mod.py "D:\eldenring_exports\mods\Tifa Gantz Black-4684-1-0-1709897552.rar"
python export_mod.py "D:\sekiro_exports\mods\Black-1838-1-0-1711241742.rar"     # 只狼：预设里写了输出到 D:\sekiro_exports
python ..\archive\archive_exports.py eldenring        # 拷到 E:\game_export\EldenRing\<角色>\<格式>\<造型>\
python ..\archive\archive_exports.py sekiro           # 拷到 E:\game_export\Sekiro\...
```

下载的文件可以是 `.zip`、`.rar`、`.7z` 或解开的文件夹；压缩包第一次用时解到 `<输出根>\work\_extracted\<包名>\`，以后直接用。
产物先落在 `D:\eldenring_exports\`（只狼 `D:\sekiro_exports\`）：

| 目录 | 内容 |
|---|---|
| `work\<名字>\` | 中间文件：`model.json`、`model.npz`、`textures\`（可删，能重新生成） |
| `blend\<名字>\` | `.blend` + `textures\` + `preview.png`（正面 / 侧面 / 背面） |
| `xps\<名字>[_<变体>]\` | `.xps` + 贴图 |
| `pmx\<名字>[_<变体>]\` | `.pmx` + `textures\` + `_converted.blend` + 四张回读预览（静止、表情、眼睛转动、跳舞） |
| `logs\` | 每一步的完整输出、`<名字>_summary.json` |
| `mods\` | mod 原文件 |

选项：
- `--name` / `--character`、`--tint 材质=#RRGGBB`（可多个）；
- `--variant 标签=正则`（可多个，正则匹配的网格不要，网格名 = FLVER 材质名）；
- `--set 标签=部件`（可多个；一个压缩包里有几套衣服、每套是一个盔甲编号时，每套出一个模型。部件写编号或通配符，如 `*_1500` 或 `*_9000,wp_*`）、`--only-set 标签1,标签2`；
- `--label`（这个下载在名字里的那一段，默认按预设的 `file_labels` 从文件名里认，比如 Black → 黑）；
- `--skip-done`（`logs\<名字>_summary.json` 已经完整的跳过，批量中断后续跑用）；
- `--from-step xps|pmx`（不重新解包、不重建 .blend，只从这一步重做；改了 PMX 那一步以后用）；
- `--no-xps`、`--no-pmx`、`--no-preview`、`--out-root`、`--blender`、`--vmd`（预览用的舞）。

认识的 mod 写在 `export_mod.py` 的 `PRESETS` 里（按文件名里的 Nexus mod 编号；新式文件名 `<名字> <编号> <版本> <时间> <随机>.zip`，
旧式 `<名字>-<编号>-<版本>-<时间>.rar` 都认），名字、角色、改色、变体、分套、输出目录自动带上。

每一步也能单独跑：

```powershell
python unpack_mod.py <mod 压缩包 | 文件夹> --out <work> [--parts hd_m_1810,*_1500,wp_*] [--tint Hair=#a95e37]
                     [--weapon-hand R|L|none] [--gloss-from normal-blue|none] [--no-glow] [--keep-untextured]
                     [--hang-chains '^hair\d+$' | none]
blender -b --factory-startup --python build_blend.py -- --work <work> --out <x.blend> [--preview <png 前缀>] [--glow-strength 6]
blender -b <x.blend> --factory-startup --python export_xps_blender.py -- --out <目录> [--name N] [--leave-out 正则]
blender -b <x.blend> --factory-startup --python export_pmx_blender.py -- --out <目录> [--name N] [--model-name M]
        [--comment C] [--leave-out 正则] [--hair-chains auto|off]
python fromsoft.py <任意 .dcx / .bnd / .flver / .tpf>            # 看里面有什么
```

## 已经转过的

| mod | 产物 |
|---|---|
| [ELDEN RING 11065 Reika Hardsuit - Gantz](https://www.nexusmods.com/eldenring/mods/11065)（zlohort） | `E:\game_export\EldenRing\Reika\`：完整版和 `_无外骨骼` |
| [ELDEN RING 4684 Tifa Gantz (nude jiggle physics 9 sets)](https://www.nexusmods.com/eldenring/mods/4684)（shintheweapon / 兵器君） | `E:\game_export\EldenRing\Tifa\`：黑 / 金属 / 白 × 比基尼（1500）/ 全覆盖（1810）/ 裸体（2110），9 个 |
| [ELDEN RING 1196 DOA Naotora Gantz set](https://www.nexusmods.com/eldenring/mods/1196)（az3163693） | `E:\game_export\EldenRing\Naotora\` |
| [SEKIRO 1838 Tifa Gantz](https://www.nexusmods.com/sekiro/mods/1838)（shintheweapon / 兵器君） | `E:\game_export\Sekiro\Tifa\`：黑 / 金属 / 白 × 全覆盖（9000）/ 比基尼（9120）/ 裸体（9130），9 个，都带楔丸 |

## 文件

| 文件 | 做什么 |
|---|---|
| `fromsoft.py` | 读 FromSoftware 格式：DCX（DFLT / KRAK）、BND4、TPF、FLVER2（0x20014 只狼 / 0x2001A）、MATBIN，纯 Python + numpy |
| `unpack_mod.py` | mod → 工作目录：合并骨架、换到 Blender 坐标、权重归一、贴图解码和派生贴图、武器放到手里 |
| `build_blend.py` | 工作目录 → `.blend`（Blender 3.6） |
| `rig.py` | FromSoft 骨骼名 → 3ds Max Biped 名；`--leave-out`；物理代理骨拆成左右胸 |
| `export_xps_blender.py` | `.blend` → XPS（blender2xps） |
| `export_pmx_blender.py` | `.blend` → PMX（星刃 / Rise of Eros 那条转换链） |
| `export_mod.py` | 上面全部串起来 + 回读预览；`PRESETS` |

## mod 里有什么

`parts\<种类>_<性别>_<编号>.partsbnd.dcx`：hd 头、bd 身体、am 手臂、lg 腿、fc 脸、hr 头发、wp 武器；每个是一个 BND4，
里面是 `.flver`（模型）+ `.tpf`（DDS 贴图）+ `_c.hkx` / `.clm2`（Havok 布料，转不过来）。`material\allmaterial.matbinbnd.dcx`
（ELDEN RING）/ `mtd\allmaterialbnd.mtdbnd.dcx`（只狼）是整套材质定义（mod 改了材质时才带）。`_l` 结尾的是远处用的低模，不读。

## 踩过的坑（都已在脚本里处理）

**坐标、格式**
- **坐标**：左手系，Y 向上，人物面朝 -Z、左手在 +X。换到 Blender（Z 向上、面朝 -Y）= `(x, y, z) → (x, z, y)`，
  这是一次镜像，每个三角形的绕向要翻转（脚本拿顶点法线核对）。UV 的 v → 1 - v。单位本来就是米。
- **BND4 的格式字节**：SoulsFormats 的标志位是高位在前（IDs 0x40、Names 0x30、长偏移 0x08、压缩 0x04），只有 BitBigEndian 不置位时才按位反转。
- **MATBIN 参数类型**：0 bool、4 int、5 int2、8 float、9 float2、10 float3、11 float4、12 float5。

**拿游戏原件当模板的 mod（Tifa Gantz、Naotora）**
- **原版残留网格**：作者拿别的盔甲文件当模板，原版的网格（`BD_metal`、`#24#fabric`、`#64#Hair` ……）还在文件里，
  三角面全收成一个点（游戏里就看不见了），贴图也不在 mod 里。三角面全是退化面的、贴图一张都不在 mod 里的网格都不要（`--keep-untextured` 保留后者）。
  个别网格只有一部分三角面是退化的，也去掉，不然 Blender 设自定义法线时直接崩溃（`lnor_space_for_single_fan`）。
- **断开的骨架**：原版盔甲文件里的骨架很多父子关系是断的（`Head` 没有父骨、整棵树停在 `Spine2`），局部变换被当成了世界变换，
  算出来的位置差一米多。一根骨只从「沿父链能走到 Master / Pelvis / Spine」的部件里取；断开的那一截按它顶端那根骨在完整骨架里的位置接回去。
- **骨架从哪个部件取**：从保留了网格的部件里取，保留顶点最多的部件优先。只狼 Tifa 的 `am_m_9000` 网格全藏了，骨架却是一个 NPC 的（脖子差 25 cm）。
- **别的骨架上做的部件**：只狼 Tifa 的后发放在 `am` 里，绑在那个 NPC 的骨架上。游戏按每个 FLVER 自己的绑定姿势蒙皮，会把它挪回真实头部；
  这里同样做一遍：部件自己的完整骨架和合并骨架对不上的骨，顶点按权重做一次线性混合蒙皮挪过去。这个 NPC 骨架独有的骨（`Hair01..05`）
  挂到合并骨架上同名父骨的位置，带着部件自己的局部偏移。断开的那种骨架不挪（顶点本来就在对的位置，Tifa 在 ELDEN RING 里的头发就是）。
- **横着的头发**：只狼 Tifa 的后发在文件里往后伸着（游戏靠物理把它吊下来）。`Hair\d+` 骨链上的头发如果离竖直下垂超过 25°，
  就绕链根转到「向下、略往后」，离链根 3–15 cm 之间逐渐转满（头皮那段不动），骨链一起转（`--hang-chains`）。
- **贴图槽**：较老的 mod 在材质里先列一张原版贴图（mod 里没有），真正的颜色图排在后面（Naotora：`LG_M_8200_a` 然后 `suita_base`）。
  同一用途有几张时，取 mod 里有的那张。只狼的金属度槽叫 `ReflectanceMap`。

**贴图**
- **BC6H 贴图（半精度浮点）**：颜色值本身就是线性颜色，按线性转 sRGB PNG；用 texconv 解成浮点（Pillow 会截到 8 位）。
  BC6H 的法线贴图是带符号的：0 就是平的。Pillow 打不开的其他格式（Naotora 的 BC1_UNORM_SRGB = 72）用 texconv 解成 8 位，色彩空间不变。
- **法线贴图和光滑度**：游戏的 `_n` 是 DirectX 方向（绿色朝下），**蓝通道存光滑度**（粗糙度 = 1 - 蓝）。派生三张：`_nrm.png`（OpenGL，
  Z 由红绿重算）、`_nrm_dx.png`（DirectX，XPS 用）、`_rough.png`。别的名字的法线贴图（Naotora 的 `*_nrm`）是普通法线图，蓝通道就是 Z，
  只有蓝通道和 Z 差得多（平均差 > 0.25）时才当光滑度。
- **金属度**：金属度槽那张图的红通道（原版叫 `_m`，Tifa Gantz 叫 `_s`）。
- **自发光**：材质有自发光贴图（`EmissiveMap`，Tifa Gantz 的 `_em`）就用它；没有的才从颜色图里找饱和青蓝色做灯光遮罩（Reika Hardsuit）。
- **着色器做出来的颜色**：Reika Hardsuit 的头发贴图几乎是黑的，游戏的毛发着色器把它染成铜色，按作者展示图测色重新上色（`--tint`）。

**PMX**
- **中文材质名**：头发（`毛发`、`头发`）、眼睛（`眼球`、`眼睛`）也认，用来加头发物理链和眼睛骨骼。
- **胸部挂在物理代理骨上**：Tifa Gantz 两边胸部都挂在一根布料代理骨上（ELDEN RING `[cloth]BD_M_2140_Board_001`，只狼 `BD_M_[Bone]RopeA_02`），
  游戏靠 Havok 让它晃。PMX 里按顶点在身体左右，把它的权重分给 `Bip001 L / R Pectoral`（中线 2 cm 内渐变），每边一个物理球。
- **头发物理链**：头发挂在 Biped 骨、布料代理骨（`[cloth]HR_A_0109_00x`）或 `Hair\d+` 骨链上时，在下垂的部分生成 7 束物理链
  （`scripts/aion2/hair_chains.py`，Reika Hardsuit 的长发在胸前，生成时把骨架临时转 180°、放大 100 倍）。
- **骨骼名**：FromSoft 的骨架就是去掉前缀的 3ds Max Biped（`Master` → `Bip001`，`L_Forearm` → `Bip001 L Forearm`），改回 Biped 名后
  XPS 和 PMX 那两条链直接认。

**武器**：mod 不带游戏的动画骨架，没有握持位置。刀放进右手：刀身沿小指根 → 食指根，刀柄在掌心，离护手 10 cm。

## 没做的 / 限制

- 游戏的 Havok 布料（`_c.hkx`）带不过来，头发、胸部的物理是 PMX 里重新加的；臀部的摇晃没有做。
- 脸没有骨骼也没有表情，PMX 没有表情（可以用表情移植插件 `pmx_expression_transfer` 从别的模型搬）。
- Naotora 的眼睛画在脸的贴图上（没有眼球网格），PMX 没有眼睛骨骼；原模型没有胸骨，没有胸部物理。
- Reika Hardsuit 的头发颜色、蓝灯发光是按截图补的，不是游戏着色器的结果。
- 只读 PC 版文件（小端）。DCX 只认 DFLT 和 KRAK。
