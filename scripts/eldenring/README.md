# ELDEN RING 角色 mod → 高清材质 Blender / XPS / PMX

把 Nexus 上的 Elden Ring 角色 mod（Mod Engine 2 格式的 zip）转成：

- `.blend`：游戏原尺寸贴图的 PBR 材质（颜色、金属度、粗糙度、法线、自发光），骨骼、权重、法线都是游戏原样；
- `.xps`：骨骼改成 Biped 名，XPS 的标准姿势能直接用；
- `.pmx`：MMD 标准骨骼 + IK、身体碰撞体、胸部物理、眼睛骨骼（両目）、头发物理链。

本机不用装 Elden Ring：mod 自带模型和贴图；解压要的 Oodle 用 CUE4Parse 下载的 `E:\tools\cue4parse_cli\oodle-data-shared.dll`，
BC6H 贴图用 DirectXTex 的 `E:\tools\directxtex\texconv.exe`（2026-11-01 从 GitHub 下载）。

## 一条命令

```powershell
cd scripts\eldenring
python export_mod.py "E:\Downloads\Reika 11065 1.0 2026-09-20T14-20Z yxOchH6Z3.zip"
python ..\archive\archive_exports.py eldenring        # 拷到 E:\game_export\EldenRing\<角色>\<格式>\<造型>\
```

产物先落在 `D:\eldenring_exports\`：

| 目录 | 内容 |
|---|---|
| `work\<名字>\` | 中间文件：`model.json`、`model.npz`、`textures\`（可删，能重新生成） |
| `blend\<名字>\` | `.blend` + `textures\` + `preview.png`（正面 / 侧面 / 背面） |
| `xps\<名字>[_<变体>]\` | `.xps` + 贴图 |
| `pmx\<名字>[_<变体>]\` | `.pmx` + `textures\` + `_converted.blend` + 四张回读预览（静止、表情、眼睛转动、跳舞） |
| `logs\` | 每一步的完整输出、`<名字>_summary.json` |
| `mods\` | mod 原文件（zip） |

选项：`--name` / `--character`、`--tint 材质=#RRGGBB`（可多个）、`--variant 标签=正则`（可多个，正则匹配的网格不要，
网格名 = FLVER 材质名）、`--no-xps`、`--no-pmx`、`--no-preview`、`--out-root`、`--blender`、`--vmd`（预览用的舞）。
认识的 mod 写在 `export_mod.py` 的 `PRESETS` 里（按 zip 名里的 Nexus mod 编号），名字、角色、改色、变体自动带上。

每一步也能单独跑：

```powershell
python unpack_mod.py <mod.zip | 解开的文件夹> --out <work> [--parts hd_m_1810,...] [--tint Hair=#a95e37]
                     [--weapon-hand R|L|none] [--gloss-from normal-blue|none] [--no-glow]
blender -b --factory-startup --python build_blend.py -- --work <work> --out <x.blend> [--preview <png 前缀>] [--glow-strength 6]
blender -b <x.blend> --factory-startup --python export_xps_blender.py -- --out <目录> [--name N] [--leave-out 正则]
blender -b <x.blend> --factory-startup --python export_pmx_blender.py -- --out <目录> [--name N] [--model-name M]
        [--comment C] [--leave-out 正则] [--hair-chains auto|off]
python fromsoft.py <任意 .dcx / .bnd / .flver / .tpf>            # 看里面有什么
```

## 已经转过的

| mod | 产物（`E:\game_export\EldenRing\Reika\`） |
|---|---|
| [11065 Reika Hardsuit - Gantz](https://www.nexusmods.com/eldenring/mods/11065)（zlohort，2026-10-04） | `blend\mod11065_Reika_Hardsuit\`；`xps\` 和 `pmx\` 各两版：完整（带外骨骼、管子、刀）和 `_无外骨骼`（只有战斗服的玲花） |

## 文件

| 文件 | 做什么 |
|---|---|
| `fromsoft.py` | 读 FromSoftware 格式：DCX（DFLT / KRAK）、BND4、TPF、FLVER2、MATBIN，纯 Python + numpy |
| `unpack_mod.py` | mod → 工作目录：合并骨架、换到 Blender 坐标、权重归一、贴图解码和派生贴图、武器放到手里 |
| `build_blend.py` | 工作目录 → `.blend`（Blender 3.6） |
| `rig.py` | FromSoft 骨骼名 → 3ds Max Biped 名；`--leave-out` |
| `export_xps_blender.py` | `.blend` → XPS（blender2xps） |
| `export_pmx_blender.py` | `.blend` → PMX（星刃 / Rise of Eros 那条转换链） |
| `export_mod.py` | 上面全部串起来 + 回读预览 |

## mod 里有什么

`parts\<种类>_<性别>_<编号>.partsbnd.dcx`：hd 头、bd 身体、am 手臂、lg 腿、fc 脸、hr 头发、wp 武器；每个是一个 BND4，
里面是 `.flver`（模型）+ `.tpf`（DDS 贴图）+ `_c.hkx` / `.clm2`（Havok 布料，转不过来）。`material\allmaterial.matbinbnd.dcx`
是整套材质定义（mod 加了自己的材质时才带）。部件的 FLVER 都带着同一副约 410 根骨的玩家骨架（同名骨变换一样，脚本会核对），
外加一堆绑定用的辅助骨（`Ctrl_*`、`Rig_*`、`LinkNode_*` ……）和每个网格一根同名节点：只留有权重的骨、它们的父骨、
身体骨（脊椎、四肢、手指、扭转骨）。

## 踩过的坑（都已在脚本里处理）

- **坐标**：Elden Ring 是左手系，Y 向上，人物面朝 -Z、左手在 +X。换到 Blender（Z 向上、面朝 -Y）= `(x, y, z) → (x, z, y)`，
  这是一次镜像，所以每个三角形的绕向要翻转（脚本拿顶点法线核对，Reika 全部 99.8% 以上一致）。UV 的 v → 1 - v。单位本来就是米。
- **BND4 的格式字节**：SoulsFormats 的标志位是高位在前（IDs 0x40、Names 0x30、长偏移 0x08、压缩 0x04），只有 BitBigEndian 不置位时才按位反转。
  按低位在前读，每个文件都是 0 字节。
- **骨架没连上**：FLVER 里 Spine 和 Pelvis 都是根骨（游戏在 Havok 骨架里才把它们连起来），脚本把 Spine 挂到 Pelvis 下、Pelvis 挂到 Master 下。
- **权重不归一**：mod 的权重和是 0.5 到 1.9（游戏在着色器里归一），转之前逐顶点除以和。
- **一个网格三份顶点流**：带布料的网格有两份位置 / 法线流（一份给 Havok 用），两份完全一样（脚本里核对过），取哪份都行。
  同一部件里材质和顶点都一样的重复网格只留一个（Reika 的 `Rings` 有两份）。
- **BC6H 贴图（半精度浮点）**：这个 mod 的颜色贴图大多是 BC6H_SF16。GPU 读它不做 sRGB 解码，游戏把里面的数直接当线性颜色用，
  所以要按线性颜色转成 sRGB PNG。按 sRGB 读的话，皮肤偏红偏暗，和游戏截图对不上。Pillow 会把 BC6H 截到 8 位（负数、大于 1 的值都没了），
  所以改用 texconv 解成浮点。BC6H 的法线贴图是带符号的：0 就是平的，不是 0.5。
- **法线贴图**：DirectX 方向（绿色朝下）：拿网格的「旋度」检验，Reika 7 张里 6 张是 DirectX，另一张分不出。
  **蓝通道不是法线 Z，是光滑度**：战斗服（亮面乳胶）的蓝通道 ≈ 1，头发 = 0，金属外骨骼 ≈ 0.19，和截图上的光泽一致。
  所以派生三张：`_nrm.png`（OpenGL 法线，Z 由红绿重算，Blender 用）、`_nrm_dx.png`（DirectX，XPS 用）、`_rough.png`（粗糙度 = 1 - 蓝）。
  金属度 = `_m` 的红通道（`_metal.png`）。不想用蓝通道当光滑度就加 `--gloss-from none`。
- **MATBIN 参数类型**：0 bool、4 int、5 int2、8 float、9 float2、10 float3、11 float4、12 float5（SoulsFormats），不是 0–7。
- **头发颜色**：Reika 的头发贴图几乎是黑的（发丝平均 sRGB 13 / 7 / 4），游戏里却是铜橘色，颜色来自游戏的毛发着色器（`c4720 Beast`），
  公式拿不到。所以按作者展示动图里头发的颜色（18 万个像素的中位数 `#a95e37`）重新上色，保留贴图本身的明暗（`--tint Hair=#a95e37`，已写进预设）。
- **发光的蓝灯**：游戏里外骨骼的青蓝色灯会发光，贴图里没有发光数据（BC6H 里没有大于 1 的值），也是着色器做的。
  所以从颜色贴图里找饱和的青蓝色像素，做一张自发光贴图（`_glow.png`），名字像眼睛的材质除外。`--no-glow` 关掉。
- **武器**：mod 不带游戏的动画骨架，没有握持位置。脚本把刀放进右手：刀身沿小指根 → 食指根的方向，刀柄在掌心，离护手 10 cm。
  Blender 里刀是一根挂在右手下的骨；PMX 里跟着右手动。
- **胸前的长发**：游戏用 Havok 布料让头发飘，PMX 带不过去，头发只蒙皮到头、脖子、胸、锁骨。仓库的 `scripts/aion2/hair_chains.py`
  只给垂在**背后**的头发生成骨骼链，而 Reika 的长发垂在**胸前**、背后是短发，所以生成时把骨架临时转 180°、放大 100 倍
  （那个脚本按厘米算），生成 7 束 16 节 `Hair_Front_*`，再转回来；mmd_cloth_physics 给它们套头发物理。
- **眼睛**：游戏没有眼睛骨骼（眼球蒙皮在 Head 上）。PMX 按眼球的球心加 左目 / 右目 + 両目（半径 14.8 mm）。
- **乳房**：皮肤一半挂 Spine2、一半挂 L_ / R_Pectoral；PMX 把 Pectoral 当 左胸 / 右胸，加星刃那套胸部物理。

## 没做的 / 限制

- 游戏的 Havok 布料（`_c.hkx`）带不过来。外骨骼的大手臂、管子在 PMX 里刚性地挂在上半身上（管子很长，跳舞会扫到地面），
  所以另出了 `_无外骨骼` 版。
- 脸没有骨骼也没有表情（mod 的脸是一块蒙皮在 Head 上的网格），PMX 没有表情。要表情可以用表情移植插件（`pmx_expression_transfer`）从别的模型搬。
- 头发颜色、蓝灯发光是按截图补的，不是游戏着色器的结果。
- 只读 PC 版文件（小端）。DCX 只认 DFLT 和 KRAK（Elden Ring 用的两种）。
