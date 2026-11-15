# Marvel Heroes Omega（UE3）mod → Blender

不用游戏本体，把 Marvel Heroes Omega 的 mod（Nexus 上下载的 .zip，里面是 `.upk` 包）转成 Blender 文件，
同时出一份 PSK（UE Viewer 的格式）和 PNG 贴图。

第一个转的是 Nexus #369「Gwenom - Contest of Champions」：作者 MysticalBlock55，1.1 版，
把 Marvel Contest of Champions 的 Gwenom 移植进游戏，替换 Spider-Gwen 的服装。
成品在 `E:\game_export\MarvelHeroesOmega\Gwenom\`。

## 一条命令

```powershell
# 先看包里有什么：骨骼模型、材质、贴图（哪些贴图在包里，哪些只在游戏的 .tfc 缓存里）
python -I scripts\marvelheroes\export_upk.py "E:\Downloads\Venom\Gwenom Contest Of Champions 369 1.1 2026-09-10T17-12Z cFcgERS9L.zip" --list

# 导出
python -I scripts\marvelheroes\export_upk.py "<mod 的 .zip 或 .upk>" --out E:\game_export\MarvelHeroesOmega\Gwenom --name Gwenom
```

- 给 .zip 就行，不用先解压。脚本把里面的 `.upk / .json / .dds` 读到一个新的临时目录（文件名只留最后一段），用完就删；E:\Downloads 里的原文件不动。
- 包里有几个骨骼模型时取最大的；要别的用 `--mesh <名字>`（名字见 `--list`）。
- 名字默认取 mod 的 `manifest.json` 里 `Name` 的前半段（「Gwenom - Contest of Champions」→ `Gwenom`）。
- 约 30 秒：Blender 3.6 在后台建模型、渲 8 张预览图，不开窗口。

| 输出 | 内容 |
|---|---|
| `blend\<名字>\<名字>.blend` | 网格 + 骨架（109 根骨头）+ 4 个材质；`textures\` 在旁边，相对路径，整个目录拷走也能打开 |
| `blend\<名字>\preview.png` | 正面 / 3/4 / 侧面 / 背面 + 4 张头部特写；单张在 `preview\` |
| `psk\<名字>\<名字>.psk` | 同一个模型的 PSK（UE Viewer 的写法），`textures\` 是 PNG，`materials.json` 是包里每个材质实例的参数 |
| `_meta\` | `report_<名字>.json`（读到了什么、丢了什么、用的参数），mod 自带的 `manifest.json` / `eng.json`，图标转成的 PNG（商店图 `store_*.png` 可以拿来对照颜色） |

| 参数 | 默认 | 作用 |
|---|---|---|
| `--scale` | 0.018 | 游戏单位 → 米。Gwenom 高 93.4 单位，乘 0.018 = 1.685 m |
| `--spec-scale` | 0.025 | 彩色高光的强度 = 高光贴图 × 高光颜色 × 遮罩 × specmult × 这个数（见「材质」） |
| `--keep-dummy` | 关 | 保留只有一个三角形的占位分段（见「坑」4） |
| `--no-preview` | 关 | 不渲预览图 |
| `--blender` / `--texconv` | 本机路径 | Blender 3.6（要装 `io_scene_psk_psa`，本机装了）/ DirectXTex 的 texconv |

单独的步骤也能跑（都用 `python -I`，路径当参数传）：

```powershell
python -I scripts\marvelheroes\upk.py <包.upk>                         # 列出所有对象
python -I scripts\marvelheroes\upk.py <包.upk> props "Gwenom Body"     # 看一个对象的属性
python -I scripts\marvelheroes\skelmesh.py <包.upk> [模型名]            # 读骨骼模型，打印分段和尺寸
python -I scripts\marvelheroes\materials.py <包.upk> --json m.json     # 材质实例的参数
python -I scripts\marvelheroes\textures.py <包.upk> <输出目录>          # 包里的贴图 → DDS + PNG
python -I scripts\marvelheroes\write_psk.py <包.upk> <输出.psk>
```

## 为什么不用 UE Viewer

UE Viewer 的游戏列表里没有 Marvel Heroes。它能读包头（`Ver: 868/3 Engine: 10897`，按普通 UE3 处理），但每种对象都读不下去：

| 怎么导 | 报错 |
|---|---|
| 整包 `-export` | `AnimSet::Serialize(chain_lt_as): 621 unread bytes`（游戏改过动画集的格式） |
| 整包 `-export -noanim`（加 `-nomat` 也一样） | 父材质 `chbasematerial_v2-1`：`wrong export index 156927 … SerializeFMaterialResource` |
| 只导模型 `spidergwen SkeletalMesh` | `wrong export index 88670207 … USkeletalMesh3::Serialize` |
| 只导一张贴图 | `Serializing behind stopper … UTexture3::Serialize` |

拿十六进制对了一下：包的名字表、导入 / 导出表和属性标签都是标准 UE3。模型和贴图在属性后面的原生数据，也和 UE Viewer 源码里 ver 868 的普通 UE3 布局一致。
所以自己写了读取器（`upk.py`、`skelmesh.py`、`textures.py`）。父材质（编译好的着色器数据）和动画集不读：
材质只要实例上的参数就够了，动画见「没做的」。

## 每一步做了什么

1. **读包**（`upk.py`）：包头、名字表、导入 / 导出表、属性标签。压缩过的包（游戏原版的 .upk 多半是）会直接报错，mod 发出来的包是没压缩的。
2. **读模型**（`skelmesh.py`）：边界、材质槽、参考骨架（四元数 + 位置 + 父骨骼），LOD 0 的分段、索引缓冲（16 位）、
   chunk（每个 chunk 一张骨骼表，顶点的骨骼编号是表里的序号）、GPU 蒙皮顶点（2 个压缩法线、4 个骨骼 / 权重、位置、半精度 UV）。
   每一步都有检查：三角形数对得上索引数，索引不超过顶点数，每个顶点权重和 255，骨骼编号都在 chunk 的骨骼表里。对不上就报错停下，不会出一个坏模型。
3. **材质**（`materials.py`）：每个 MaterialInstanceConstant 的父材质和贴图 / 标量 / 颜色参数。
4. **贴图**（`textures.py`）：包里那一层最大的 mip → DDS → texconv 转 PNG。这个 mod 的 10 张都是 DXT5，2048² 或 1024² 或 512²。
5. **写 PSK**（`write_psk.py`）：写法和 UE Viewer 一模一样，所以 Blender 的 `io_scene_psk_psa` 导入后左右是对的：
   - Y 取反：位置、法线、骨骼；骨骼四元数是 Y 和 W 取反；
   - 三角形前两个角对调；
   - 位置、法线、权重都相同的顶点合成一个点，UV 缝两边仍然是平滑着色；
   - 法线写在 `VTXNORMS`，权重写在 `RAWWEIGHTS`。
6. **建 Blender 文件**（`build_blend.py`，Blender 3.6 后台）：
   - 导入 PSK，缩放 0.018，转到面朝 -Y（游戏里面朝 +X；Blender / MMD 的正面是 -Y），并应用变换；
   - 按游戏参数建材质；
   - 贴图拷到 .blend 旁边，用相对路径保存；
   - 渲预览图。

## 材质

游戏的角色材质都是 `chbasematerials_v2.chbasematerial_v2-1`：自定义光照，即漫反射 + 彩色 Blinn-Phong 高光 + 轮廓光；
混合模式是 masked，阈值 0.001，所以贴图 alpha（≥ 230）等于全不透明。实例参数对应到 Blender：

| 游戏参数 | Blender |
|---|---|
| `diffusetex` | 原理化 BSDF 的基础色 |
| `normaltex` | 法线贴图（UE 是 DirectX 法线，先把绿通道翻转），强度 = `normalstrength`（没设就是 1） |
| `specmult_specpow_skinmask_reflectivity` | 只用 R 通道当高光遮罩：这个 mod 的「Gloss」贴图只有 R 有值，G、B 都是 0 |
| `speccolortex` × `speccolorvalue` | 光泽 BSDF 的颜色：Gwenom 是淡蓝 (0.48, 0.78, 1.0)，共生体那种蓝色反光 |
| `specmult` | 光泽 BSDF 颜色再乘 `specmult × 0.025`（最少 0.03，最多 0.5） |
| `specularpower` n | 光泽 BSDF 的粗糙度 = √(√(2/(n+2)))：5 → 0.73，30 → 0.5 |
| `emissive` × `emissivemultiplier` | 自发光（只有眼睛）× 1.5 |

原理化 BSDF 只管漫反射（镜面 0.15、粗糙度 0.7），彩色高光走另一个光泽 BSDF，两者用「相加着色器」合起来。节点都带中文标签，材质上存了游戏原值（自定义属性 `mho_*`）。

Gwenom 的 4 个材质：

| 材质 | 用在哪 | 贴图 |
|---|---|---|
| `Gwenom_Body` | 紧身衣、上身 | Current_Diff / Norm / Gloss / Spec，specmult 1 |
| `Gwenom_Emissive` | 头（面罩）和眼睛 | 同上 + Emiss，specmult 20、specularpower 30 |
| `Gwenom_Hoodie` | 兜帽、粉色触手 | Hood_Diff / Hood_Norm / Hood_Gloss / Hood_Spec，specmult 2 |
| `Gwenom_Teeth` | 牙齿、触手上的尖刺 | Teeth_Diff + Hood 的另外三张 |

## 坑

1. **名字全是小写**：包里存的是 `structproperty`、`skeletalmesh`、`texture2d`。比较类型名和类名要不分大小写。
2. **BoolProperty**：标签里的大小是 0，值是标签后面的 1 个字节（版本 ≥ 673）。
3. **贴图在不在包里**：mod 自己带的贴图，最大一层 mip 直接存在包里。游戏自己的贴图（比如原版 `spidergwen_diff`）大图都在游戏的 `.tfc` 缓存
   （属性 `texturefilecachename = chartextures`），包里只剩 64×64 以下的小图。所以「不用游戏本体」只对自带贴图的 mod 成立。
   `--list` 会标出哪些贴图只在缓存里。
4. **一个三角形的占位分段**：mod 给原来的 Spider-Gwen 材质（`spidergwen_matv2`）留了 1 个三角形，藏在头里，
   这样游戏的 0 号材质槽还在。它不是模型的一部分，默认丢掉；`--keep-dummy` 保留。
5. **左半身的 UV 是 u + 1**：一半三角形的 u 在 1–2 之间，全在左半身和中线上。这是镜像 UV 的常见做法，贴图重复寻址，所以看到的是同一块贴图。
   Blender 默认就是重复，不要把 UV 截到 0–1。左右对比过：约 90% 的左半身顶点和镜像过来的右半身 UV 正好差 1。
   不一样的在左手指尖、脚踝和锁骨附近，是 mod 本来的 UV。
   两只手背上的白色贴片是贴图本身的图案（漫反射贴图上方那块白色），左右都有：两边手腕取到的颜色一样，各有 14 个顶点落在白色上。
6. **高光不能照搬数值**：游戏的 Blinn-Phong 没有能量归一化，Blender 的 GGX 有，同样的颜色在 Blender 里峰值亮约 5 倍。
   第一版照搬，面罩在柔光箱下整片发蓝白。商店图里面罩是黑的、眼睛是白的，去掉光泽层渲一张也是这样，所以高光颜色乘 `specmult × 0.025`。
   保留了各材质之间的比例：面罩 20 → 0.5，紧身衣 1 → 0.03。想更亮更暗就改 `--spec-scale`。
7. **烘焙包里留着 CPU 顶点**：每个 chunk 还存着一份 CPU 用的顶点数组，刚体顶点每个 61 字节，平滑顶点每个 68 字节。
   跳过时用后面紧跟的骨骼表核对长度，对不上会自动试 40–119 字节，还不行就报错。
8. **比例和朝向**：游戏单位不是厘米（人物约 93 单位高），0.018 是按身高 1.68 m 定的。导入后已经应用了缩放和旋转，骨架和网格的变换都是 1。
9. Windows 的 GBK 控制台打印模型路径会出编码错误，脚本里把输出改成了 UTF-8。

## 没做的

- **动作**：这个包里有 354 个 AnimSequence（`spidergwen_as`、`spidergirl_as` 等，是游戏里 Spider-Gwen 的全部动作）。
  UE Viewer 读这些 AnimSet 也报错。要转的话，得按 UE3 的压缩动画格式自己解，再转成 Blender 动作或 VMD。
- 只取 LOD 0（这个 mod 只有一个 LOD）。顶点色和 morph 没处理，这个 mod 也没有。
- 物理资产（`female_l_physics_v2`）和 63 个挂点（socket）没导。
- 转 PMX / XPS：用仓库里现有的 PMX 流程，需要的话再做。

## 验证（Gwenom）

- 网格：11,670 个 GPU 顶点合成 11,366 个点，17,947 个三角形，109 根骨头，所有检查通过。
- 后台独立打开归档里的 .blend：10 张贴图都是相对路径，没有缺失；网格有骨架修改器，72 个顶点组，4 个材质。
- 摆了几个姿势（手臂、肘、膝盖、头、腰）渲图，皮肤跟着骨骼走，没有撕裂。
- 和 mod 自带的商店图（`_meta\store_spiderman_gwenom3.png`）对照：黑紧身衣，黑面罩、白眼睛，粉色触手、兜帽边。
  游戏里的颜色更暗、偏红，因为游戏环境光偏棕。
