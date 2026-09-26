# Vindictus Fiona 全手工导出：游戏文件 → Blender → XPS / PMX

2026-09-26。例子是《洛奇英雄传：反抗命运》Pre-Alpha 客户端里的 **Fiona_BaseBody**（Fiona 素体）。
从解包到 XPS、PMX，每一步都在图形界面里手工完成，不跑仓库脚本。每一节末尾写了对应的自动脚本，
方便对照结果。

Fiona_BaseBody 由三块拼成，是这个游戏里最麻烦的一个：

- **旧版素体** `SM_pc_fiona_basebody`：裸体身体（贴图是裸体），外面套一层白 T 恤 + 短裤（材质 `inner`）。
  它用 3ds Max Biped 骨架，还自带一个没贴图的旧头。
- **现在的脸** `SK_Fiona_Face01`：MetaHuman 式的头，UE 骨架，620 根 `FACIAL_*` 面部骨。
- **头发** `SK_Fiona_Hair01`。

所以它比普通服装多三件事：身体要转向对齐（2.3），切掉旧头并修脖子接缝（2.5、第 3 节），
把两副骨架并成一副（第 4 节）。

> **普通服装**（Fiona 默认装、`PCF_0xx`）跳过 2.3、2.5、第 3 节、第 4 节，其余照做，因为它们的部件都在同一副 UE 骨架上。
> 例外是 `Shiningwill_legacy`：它和素体一样是 Biped 身体配 UE 脸，要做 2.3 和第 4 节。
> 另外两点：
>
> - 每个部件的 PSK 都自带一份共用骨骼，合并后会出现一批 `.001` 副本。处理方法和 2.4 第 3 步一样：
>   把部件独有骨骼的根挂回原名骨，再删掉 `.001`。
> - 有 8 套服装的部件绑在另一版骨架上（比如女巫帽离头 7 cm）。这种手工很难对齐，
>   直接用 `export_model.ps1` 自动构建，脚本里的 `repose_part()` 会处理。

> **key 和资产**：AES key 只放在本机 `E:\tools\vindictus\_download\aes_key.txt`，
> 是用 `scripts\vindictus\find_aes_key.py` 从 exe 里算出来的。下面这些地方都不能出现 key：
> 文档、截图、提交记录、聊天。游戏资产和导出的贴图也不要提交到 Git。

---

## 0. 准备

### 工具（本机都已装好）

| 用途 | 程序 | 路径 / 版本 |
|---|---|---|
| 解包 | UE Viewer（spiritovod 的 UE5 版） | `E:\tools\umodel_specific\materials\umodel_materials_ue5.exe`，build 1579（fix282，2026-09-05），自带 Oodle |
| 组装 | Blender | `D:\Program Files\blender-3.6.15-windows-x64\blender.exe`（3.6.15） |
| 导入 PSK | PSK/PSA Importer/Exporter（`io_scene_psk_psa`） | 5.0.6 |
| 导出 XPS | Blender2XPS（`blender2xps`） | 1.0.0，目录联接到 `E:\code\othercode\blender2xps` |
| 回读 XPS | XNALara/XPS Import/Export（`XNALaraMesh-master`） | 2.0.2 |
| MMD 数据结构 | mmd_tools（UuuNyaa 分支） | bl_info 1.0.2 |
| 转 MMD 骨架 | Convert to MMD 5 | 3.0（面板顶部显示 `build 2026-07-05 left-align`） |
| 头发 / 布料物理 | MMD Cloth Physics | 0.1.0（`scripts\blender_addons\mmd_cloth_physics`） |
| 看 XPS | XNALara XPS 11.8 | `E:\tools\XPS 11.8\XNALara XPS.exe` |
| 看 / 改 PMX | PmxEditor 0257 汉化版 | `E:\tools\PmxEditor_0257_CHS（…）\PmxEditor_x64.exe` |
| 让 PMX 动起来 | MikuMikuDance 9.32 x64（英文版） | `E:\tools\MikuMikuDanceE_v932x64\MikuMikuDance.exe` |

在 Blender 的 Edit → Preferences → Add-ons 里确认下面这些插件都已启用（本机都开着）：
PSK/PSA、Blender2XPS、XNALara/XPS、mmd_tools、Convert to MMD 5、MMD Cloth Physics。
原版 Convert to MMD 和 Convert to MMD 5 的操作符同名，两个不能同时启用。

### 工作目录

```text
D:\vindictus_manual\
├─ umodel_exports\                  UE Viewer 导出的 PSK / PNG / .mat / .props.txt
├─ blend\Fiona_BaseBody\            Fiona_BaseBody.blend + textures\
├─ xps\Fiona_BaseBody\
└─ pmx\Fiona_BaseBody\
```

不要直接改 `E:\game_export` 里的归档文件。

### 单位和朝向

- **单位**：PSK 按 UE 的单位导入，Blender 里 1 个单位 = 1 cm，人物约 175 个单位高。
  N 面板上显示的 "m" 实际是厘米，场景单位不用改。
- **朝向**：
  - UE 的角色网格朝 −Y，所以 Blender 前视图（小键盘 1）正对她的脸。
  - 旧素体（Biped）朝 +X，要转过来，见 2.3。
- **导出缩放**：
  - XPS：缩放 0.01，得到约 1.75 个单位高。
  - PMX：先把整个模型缩到米（×0.01），mmd_tools 再按 12.5 导出，约 21.9 个 MMD 单位
    （1 MMD 单位 = 8 cm，折合 175 cm）。

### 总流程

```text
UE Viewer（加密 IoStore）─→ 3 个 PSK + PNG + .mat/.props.txt
   └─ Blender：导入 → 素体转正 → 合并骨架 → 切旧头 → 建材质 → 修脖子 → 并成一副骨架
         ├─ Blender2XPS ─→ .xps（XNALara XPS 11.8 检查）
         └─ 缩到米 → Convert to MMD 5 → 物理 / 表情 / 材质 → mmd_tools ×12.5 ─→ .pmx（PMXEditor / MMD 检查）
```

---

## 1. 从游戏文件取出原始资源（UE Viewer）

客户端在 `E:\tools\vindictus`：UE 5.3，IoStore（utoc/ucas），Oodle 压缩，目录索引用 AES 加密。

仓库一直用 UE Viewer 解这个游戏。FModel（`E:\tools\fmodel`）不推荐，两个原因：

- 没在这个游戏上验证过；
- 它把材质导成 JSON，2.6 节照 `.mat` / `.props.txt` 建材质的步骤就对不上了。

### 1.1 启动

1. 双击 `umodel_materials_ue5.exe`，出现 **UE Viewer Startup Options**，按下表填，然后点 OK：

   | 项 | 填 |
   |---|---|
   | Path to game files | `E:\tools\vindictus\Vindictus\Content\Paks` |
   | Override game detection | 勾上，选 `Unreal engine 5` → `Unreal engine 5.3` |
   | View / export object types | 默认（Skeletal mesh、Static mesh 勾着） |
   | Platform | Auto |

2. 接着弹出 "UE Viewer has found an encrypted UE5 package…"，下面有 **Please enter AES encryption key** 输入框。
   打开 `aes_key.txt`，把那一行（`0x` 开头）粘进去，点 OK。
   - **不想每次粘贴**：建一个快捷方式，目标写成下面这样。`-aes=@文件` 表示从文件读 key，
     自动脚本也是这么传的，key 不会出现在命令行里。

     ```text
     "E:\tools\umodel_specific\materials\umodel_materials_ue5.exe" -gui -game=ue5.3 -path=E:\tools\vindictus\Vindictus\Content\Paks -aes=@E:\tools\vindictus\_download\aes_key.txt
     ```

   - **弹出 "unversioned UE5 package"**：如果看到 "…found an unversioned UE5 package… please specify which Unreal engine 5
     version"，说明上一步没选 5.3，回去选上。

### 1.2 导出选项

菜单里的 Options 打开导出设置，按下表改，其余保持默认。
（菜单位置未实测：选项名取自程序内的界面字符串，命令行导出已验证。）

| 项 | 设置 |
|---|---|
| Export to this folder | `D:\vindictus_manual\umodel_exports` |
| Texture format | PNG |
| Skeletal Mesh | ActorX (psk) |
| Static Mesh | ActorX (pskx) |
| Export LODs | 不勾（只要 LOD0） |

### 1.3 找到三个包

按 O（File → Open package…），打开 **Choose a package to open**：

- 左边是目录树，右边是包列表。列表的 Skel / Stat 两列标出这个包里有没有骨骼网格、静态网格。
- 上方 Filter 可以按名字过滤，勾 Flat view 平铺显示。

| 部件 | 包路径 | 导出成 |
|---|---|---|
| 脸 | `VindictusRoot/Character/Player/Fiona/Face/Model/SK_Fiona_Face01` | `SK_Fiona_Face01.pskx` |
| 头发 | `VindictusRoot/Character/Player/Fiona/Face/Model/SK_Fiona_Hair01` | `SK_Fiona_Hair01.psk` |
| 素体 | `VindictusRoot/Character/Player/Fiona/Model/Mesh/SM_pc_fiona_basebody` | `SM_pc_fiona_basebody.pskx` |

- 素体名字以 SM_ 开头，但它其实是 SkeletalMesh。旁边的 `SK_female_base` 是 Skeleton 资源，导不出网格。
- 容器里有 178 个同名资源，一定按上表的完整目录去找，别用按名字搜到的第一个。

### 1.4 导出

选中包 → Open (replace loaded set) → 视窗里出现模型 → 菜单里的 **Export current object**（Ctrl+X）。三个包各做一遍。

同一时间只开一个 UE Viewer：同时导多个模型会互相覆盖共用的贴图（自动流程因此也不并行）。

导出结果（下面是命令行 `-export` 实测的目录结构）：

```text
umodel_exports\
├─ VindictusRoot\Character\Player\Fiona\Face\Model\
│    SK_Fiona_Face01.pskx   SK_Fiona_Hair01.psk
│    MI_Fiona_Face01_*.mat / *.props.txt、MI_Fiona_Hair01.*、MI_Fona_Face01_Eyebrow.* / _EyeLash.*
│    T_Fiona_Face01_D.png / _N.png / _Mask.png
├─ VindictusRoot\Character\Player\Fiona\Model\Mesh\SM_pc_fiona_basebody.pskx
├─ VindictusRoot\Character\public\Hair\T_Hair02_ODI.png、T_Hair02_FR.png
├─ VindictusRoot\Common\Materials\Textures\Character\    眉毛、睫毛、牙齿、眼睛的贴图
└─ _Prework\Characters\Player\Fiona\fiona2\              素体材质 MI_pc_female_body05.* 与 T_pc_fiona_basebody02_D/N.png 等
```

- `.mat` 列出材质用到的贴图（`Diffuse=`、`Normal=`、`Other[n]=`）。
- `.props.txt` 是材质实例的父材质，以及贴图、颜色、数值参数。2.6 节建材质照的就是它。

**命令行版**：和 GUI 等价，一个包一条命令，是 `export_model.ps1` 第 2 步的原样命令，已验证：

```powershell
& 'E:\tools\umodel_specific\materials\umodel_materials_ue5.exe' -game=ue5.3 -path=E:\tools\vindictus\Vindictus\Content\Paks -aes=@E:\tools\vindictus\_download\aes_key.txt -export -png -out=D:\vindictus_manual\umodel_exports VindictusRoot/Character/Player/Fiona/Face/Model/SK_Fiona_Face01
```

自动流程：`scripts\vindictus\export_model.ps1 Fiona_BaseBody -NoBlend`（`list_models.py` 解析包路径，再调 UE Viewer 命令行）。

---

## 2. 在 Blender 里组装

### 2.1 导入三个 PSK

1. File → New → General，删掉默认的 Cube、Camera、Light。
2. File → Import → **Unreal PSK (.psk/.pskx)**，依次导入脸、头发、素体，选项如下：

   | 选项 | 设置 | 说明 |
   |---|---|---|
   | Import Materials | 勾 | 按 PSK 的材质槽建空材质，名字就是 `MI_xxx` |
   | Import Mesh | 勾 | |
   | Vertex Normals | 勾 | 保留游戏的拆分法线（自定义法线） |
   | Extra UVs | 勾 | |
   | Vertex Colors | **不勾** | 和自动脚本一致；第 3 节要自己建一层顶点色 |
   | Shape Keys | 勾 | 这三块都没有形态键，勾不勾一样 |
   | Import Skeleton | 勾，Bone Length 1.0 | |

   每个文件会生成一个骨架（以文件命名，如 `SK_Fiona_Face01`）和一个网格（`SK_Fiona_Face01.001`）。实测：

   | 部件 | 骨骼 | 顶点 |
   |---|---:|---:|
   | 脸 | 658 | 32,481 |
   | 头发 | 274 | 28,492 |
   | 素体 | 105 | 82,028 |

3. 在大纲里双击改名。和自动脚本同名方便对照，第 3 节也能直接对这个文件跑脚本：

   | 原名 | 改成 |
   |---|---|
   | `SK_Fiona_Face01.001` | `Fiona_BaseBody_Face` |
   | `SK_Fiona_Hair01.001` | `Fiona_BaseBody_Hair` |
   | `SM_pc_fiona_basebody.001` | `Fiona_BaseBody_BaseBody` |

   骨架先不改名，2.4 合并成一个以后再改。

**三块的关系：**

- 脸和头发：
  - 都是 UE 骨架（`root → pelvis → spine_01…05 → neck_01 → neck_02 → head`），朝 −Y。
  - 头发骨架和脸骨架共用 10 根骨（root 到 head），位置完全一样。
- 素体：
  - 是 3ds Max Biped 骨架（`Root → Bip001 → Bip001_Pelvis → …`），朝 **+X**，要在右视图（小键盘 3）才看到正面。
  - 它的 `Bip001_Head` 比脸的 `head` 高 1 cm；转正以后在 `head` 前方 6.9 cm，要往后挪（2.3）。

### 2.2 小心自定义法线

三块网格都带游戏的**自定义拆分法线**（Object Data → Normals 里 Auto Smooth 是勾着的）。

- 移动顶点**不会**更新这些法线。第 3 节挪完脖子顶点后，要把法线一起换掉，不然素模下都看得见一道弧线。
- 删掉相邻的面也会让它变：自定义法线是相对周围的面存的。第 3 节删完旧皮要把旧身体的法线还回去。
- 不要随手点 Clear Custom Split Normals：脸和身体会变成另一种光照，接缝反而更明显。

### 2.3 素体转正、对齐

1. 对象模式下选中**素体的骨架** `SM_pc_fiona_basebody`。网格是它的子物体，会跟着动。
2. N 面板 Item 页：Rotation Z 填 **-90**，Location Y 填 **6.9**，Z 不动。
   这时 `Bip001_Head` 正好在 `head` 正上方 1 cm。两套头骨本来就差 1 cm 高，不用管。
3. 把骨架和它的网格一起选中（点骨架，再 Shift 点网格），Ctrl+A → **All Transforms**。
   实测网格位置不变，静止姿势也没有偏移。

**为什么：**

- Biped 的正前方是 +X，UE 是 −Y。不转的话，合并后身体侧着、脸朝前。
- 自动脚本 `align_secondary_hierarchies()` 按脚到脚趾的方向算，结果同样是 −90°、6.9 cm。

### 2.4 合并骨架

1. **合并**：依次点头发骨架、素体骨架，最后 Shift 点**脸的骨架**（最后点的是活动物体），
   然后 Ctrl+J（Object → Join）。合并后的骨架改名为 `Fiona_BaseBody_rig`。
2. **修 Armature 修改器**：合并后，头发和素体网格的 Armature 修改器 Object 一栏是空的
   （Blender 3.6 合并骨架只改了父级，没改修改器），网格不跟骨架动。
   到这两个网格的 Modifier Properties 里，把 Object 重新选成 `Fiona_BaseBody_rig`。
3. **把头发骨链挂回去**：
   - 问题：头发 PSK 自带的那 10 根共用骨，合并后变成了 `root.001 … head.001`，
     头发骨 `hair_root` 挂在 `head.001` 下面，摆头时头发不跟着动。
   - 做法：进骨架编辑模式（Tab），然后：
     1. 选 `hair_root`，再 Shift 选 `head`，Ctrl+P → **Keep Offset**；
     2. Select → Select Pattern… 输入 `*.001`，选中那 10 根，按 X → 删除骨骼。
   - 结果：共 1027 根骨，和自动构建的数量一样。头发的顶点组本来就按名字绑在 `Fiona_hair_*` 上，不受影响。

检查（姿态模式）：

- 转 `head`：脸和头发一起动。
- 转 `Bip001_Spine2`：只有身体动，脸不动。这是对的，两副骨架要到第 4 节才合成一副。

自动流程：`build_blend.py` 的合并循环（以骨数最多的骨架为底，缺的骨按父子关系补进去）。

### 2.5 切掉旧头（保留 T 恤）

旧素体自带一个没贴图的旧头，会从新脸里穿出来。规则和自动脚本一样：

- 主权重在 `Bip001_Head` / `Bip001_Neck` 上的顶点全部删掉；
- 但 `inner`（T 恤、短裤）的顶点一个都不能动。T 恤领口的顶点也带脖子权重，删了领口会缺口。

Blender 没有"按主权重选顶点"的按钮，用两个权重修改器凑出来。选中素体网格 `Fiona_BaseBody_BaseBody`：

1. Object Data Properties → Vertex Groups → **+**，新建一个空组，命名为 `oldhead`。
2. Add Modifier → Edit → **Vertex Weight Mix**，按下表设置；然后在修改器下拉 ∨ 里点 Move to First，再点 Apply：

   | 项 | 设置 |
   |---|---|
   | Vertex Group A | `oldhead` |
   | Vertex Group B | `Bip001_Head` |
   | Vertex Set | **Vertex Group A or B**（默认的 A and B 一个顶点也不会选中） |
   | Mix Mode | **Add**（默认是 Replace） |

3. 再加一个同样的 Vertex Weight Mix，B 换成 `Bip001_Neck`，Move to First，Apply。
   现在 `oldhead` = 头 + 脖子的权重之和。
4. Add Modifier → **Vertex Weight Edit**：Vertex Group 选 `oldhead`，勾 **Group Remove**，
   Remove Threshold 填 **0.5**（把和小于 0.5 的顶点移出组）。Move to First，Apply。
5. 删顶点：
   1. Tab 进编辑模式，切到顶点选择，Alt+A 全不选；
   2. Vertex Groups 里选 `oldhead` → **Select**；
   3. Material 里选 `inner` 槽 → **Deselect**；
   4. X → Vertices。

   实测删掉 58,483 个顶点，剩 23,545 个（自动脚本删 58,484）。
6. 旧头还留下一些零碎的材质面：在材质槽里依次选 `MI_pc_fiona_face05`、`MI_fiona04_hair`、`MI_pc_fiona_face02_*`，
   每个都 Select → X → Faces。
7. 收尾：删掉顶点组 `oldhead`（点 −）；材质槽下拉 ∨ → Remove Unused Slots。

自动流程：`build_blend.py` 的 `cut_legacy_head()`。

### 2.6 手工建材质

以下在 EEVEE 下，用 Material Properties 和 Shader Editor 操作。数值都来自 `.props.txt`，用 `build_blend.py` 的规则换算。

**法线贴图（通用接法）**：UE 的法线是 DirectX 格式（绿通道朝下），Blender 要 OpenGL 格式，不翻的话凹凸是反的。

1. Image Texture，色彩空间选 Non-Color；
2. 接 Separate RGB；
3. G 通道接 Math → Subtract（1 − G）；
4. 接 Combine RGB（R、B 直接连）；
5. 接 Normal Map（Strength 见下表），输出到 Principled 的 Normal。

贴图路径都相对 `umodel_exports\`：

| 材质 | 贴图 | 接法 | Principled 与设置 |
|---|---|---|---|
| `MI_Fiona_Face01_`（脸皮肤，父材质 M_PC_Skin_Head） | `VindictusRoot\Character\Player\Fiona\Face\Model\T_Fiona_Face01_D.png`（sRGB）、`…_N.png` | D → Hue/Saturation/Value（Value **0.9297** = Basecolor Brightness）→ Mix（Multiply，Fac 1，Color2 = **(1, 0.9047, 0.9047)** = Basecolor Tint）→ Base Color；N 法线强度 0.6 | Roughness 0.55，Specular 0.35，Subsurface 0.02，Subsurface Color (0.8, 0.3, 0.2) |
| `MI_pc_female_body05`（身体，裸体贴图） | `_Prework\Characters\Player\Fiona\fiona2\T_pc_fiona_basebody02_D.png` / `_N.png` | D 直接连 Base Color；N 法线强度 0.6 | 同上 |
| `MI_pc_female_handfoot05`（手脚） | 同一目录 `T_pc_fiona_hand_foot02_D.png` / `_N.png` | 同上 | 同上 |
| `inner`（T 恤、短裤） | 无 | — | 默认浅灰 0.8，Roughness 0.6，Specular 0.35 |
| `MI_Fiona_Hair01`（父材质 M_PC_Hair） | `VindictusRoot\Character\public\Hair\T_Hair02_ODI.png`、`T_Hair02_FR.png`（都用 Non-Color） | ODI → Separate RGB → **R 连 Alpha**；FR → Separate RGB → **B 连 Color Ramp 的 Fac**（发根到发梢）→ Base Color。Color Ramp 三个色标：0 = Root (0.196, 0.145, 0.096)，0.5 = Mid (0.373, 0.272, 0.182)，1 = Tip (0.186, 0.129, 0.098) | Roughness 0.35，Specular 0.4；Settings 里 Blend Mode 和 Shadow Mode 都选 **Alpha Hashed**，Backface Culling 不勾 |
| `MI_Fona_Face01_Eyebrow` / `MI_Fona_Face01_EyeLash` | `VindictusRoot\Common\Materials\Textures\Character\T_Eyebrow01_ODI.png`（眉毛）/ `T_Eyebrow02_ODI.png`（睫毛），Non-Color | R 连 Alpha | Base Color：眉毛 (0.047, 0.020, 0.012)，睫毛 (0.004, 0.004, 0.004)；Roughness 0.6；Alpha Hashed |
| `MI_Fiona_Face01_Teeth` | 同一目录 `T_Teeth01_BC.png`、`T_Teeth01_NA.png` | BC 连 Base Color；NA 法线强度 0.6 | 按皮肤设：Roughness 0.55，Specular 0.35，Subsurface 0.02 |
| `MI_Fiona_Face01_EyeShdow`（眼周遮蔽壳） | 无 | — | Base Color 黑，Alpha 0.12，Specular 0，Roughness 1；Blend Mode 选 Alpha Blend，Shadow Mode 选 None，Show Backface 不勾，Backface Culling 勾 |
| `MI_Fiona_Face01_Lacrimal`（泪线） | 无 | — | Base Color (0.9, 0.9, 0.9)，Roughness 0.05，Specular 0.8，Alpha 0.15；Alpha Blend，Shadow Mode None |
| `MI_Fiona_Face01_EyeReflection_Fake`（假反光片） | `_Prework\Characters\MetaHumans\Common\Face\Textures\T_lacrimal_h.png` | 贴图的 Alpha 乘 0.4（Math Multiply）后连 Alpha | 同泪线 |
| `MI_Fiona_Face01_EyeBall` | 见下 | | |

身体材质的 `.props.txt` 里有个 `BaseColorBrightness = 1.5`，名字和脸上的 `Basecolor Brightness` 不一样。
自动脚本没用这个参数，这里也不用，保持两边一致。

**眼球（推荐从现成文件追加）**：自动构建的眼球有三十来个节点：程序化虹膜、取色器采样、瞳孔、外圈暗边。
Fiona 默认装和素体用的是同一张脸、同一个眼球材质，直接追加最省事：

1. File → Append → 选 `E:\game_export\Vindictus\Fiona\blend\Fiona\Fiona.blend` → Material → `MI_Fiona_Face01_EyeBall`。
   同名会自动变成 `.001`。
2. 在脸网格的 EyeBall 槽里换成追加进来的这个材质。

**眼球（简化手搭，和自动构建有差别，没有虹膜纤维）**：

- 巩膜：`_Prework\Characters\MetaHumans\Common\Face\Textures\T_Sclera_D.png` 作底色。
- 半径值：Texture Coordinate 的 UV → Vector Math Subtract (0.5, 0.5, 0) → Length → Math Multiply 5。
  得到虹膜中心为 0、虹膜边缘为 1 的半径值（虹膜盘半径是 UV 的 0.2）。
- 虹膜颜色：用 Color Ramp 按半径上色：
  - 0 到 0.33：黑色（瞳孔）；
  - 0.36 到 0.9：虹膜色约 (0.20, 0.23, 0.17)；
  - 0.97：虹膜色乘 0.3（外圈暗边）。
- 巩膜和虹膜混合：用 Map Range 把半径 0.90→0.98 映射成 1→0，作为 Mix 的 Fac。
- 法线：`VindictusRoot\Common\Materials\Textures\Character\T_PC_Eye_N.png`，强度 0.4。
- Principled：Roughness 0.12，Specular 0.5。

自动流程：`build_blend.py` 的 `setup_material()`、`build_eye()`。

### 2.7 保存，把贴图收进 textures\

1. File → Save As，存为 `D:\vindictus_manual\blend\Fiona_BaseBody\Fiona_BaseBody.blend`。
2. File → External Data → **Pack Resources**。
3. File → External Data → **Unpack Resources** → "Write files to current directory (overwrite existing files)"。
   贴图会写到 .blend 旁边的 `textures\`，并改成相对路径，和自动构建的产物一样，整个目录拷走就能打开。
4. 再保存一次。

---

## 3. 脖子接缝（与自动脚本同一思路，参数以 scripts/vindictus/fix_basebody_neck.py 为准）

**问题在哪：**

- 新脸自带一圈颈部和锁骨的"围兜"，顶点权重在 `spine_04`、`clavicle_*`、`upperarm_*` 上。
  这圈围兜在前面浮在旧身体外约 1 cm，在后背陷进旧身体约 1 cm。
- 旧身体的脖子根是照旧脖子做的，比新脖子粗，还往前倾；T 恤领口也比新脖子宽。

**素体的特殊要求**：素体要能脱掉 T 恤当裸体底模，所以不能靠衣服遮，身体本身必须是完整的一层皮。
"删掉被 T 恤盖住的皮"这种做法是错的：2026-09-26 前两轮修复就栽在这上面，一脱 T 恤锁骨和后背一圈是洞。

**做法**：

1. 围兜按权重贴到旧身体表面上，过渡带要宽、要平滑；
2. 外沿一圈压进旧皮下面；
3. 法线换成旧身体的；
4. 删掉被围兜盖住的那层旧皮，外沿那圈留着；
5. 旧身体的法线原样还回去；
6. 围兜改用身体的骨骼权重，T 恤在围兜上方放出余量（摆姿势、导 XPS / PMX 要用）；
7. 肤色往旧身体靠。

下面每一步都在一份没做脖子修复的自动构建上重放过，用的是 GUI 按钮调用的同一批操作符。和脚本的对比见本节末尾。

### (a) 两份身体副本

1. **`BodySkin`（纯皮肤）**：
   1. 选 `Fiona_BaseBody_BaseBody`，Shift+D 复制，右键取消移动（原地复制），改名为 `BodySkin`；
   2. 进编辑模式，材质槽选 `inner` → Select；
   3. 旧头残留的材质槽也 Select：`MI_pc_fiona_face05`、`MI_fiona04_hair`、`MI_pc_fiona_face02_*`（2.5 第 6 步删过就没有了）；
   4. X → Faces。副本里只剩裸皮肤。
2. **`BodyOrig`（原样备份）**：再原地复制一份 `Fiona_BaseBody_BaseBody`，改名为 `BodyOrig`，什么都不改。

**为什么**：

- `BodySkin`：围兜要贴到皮上，不能贴到 T 恤上。
- `BodyOrig`：(e) 删面会让切口一圈的自定义法线变样，(f) 要从它把原来的法线拷回去。
- 两份到 (g) 做完才删：(g) 要从 `BodySkin` 拷骨骼权重，从 `BodyOrig` 再拷一次法线。

### (b) 在脸上做三个权重组：`bib`、`band`、`edge`

以下都在 `Fiona_BaseBody_Face` 上操作。

1. **`bib`（身体骨骼权重占比）**：
   1. 新建一个空的顶点组 `bib`；
   2. 下面每个组各加一个 Vertex Weight Mix，都是 Move to First 后 Apply。设置：

      | 项 | 设置 |
      |---|---|
      | Vertex Group A | `bib` |
      | Vertex Group B | 该组 |
      | Vertex Set | Vertex Group A or B |
      | Mix Mode | Add |

      要加的组共 15 个（规则是名字以 spine / clavicle / upperarm / pectoral / breast 开头，实测脸上有权重的就是这些）：

      ```text
      spine_04  clavicle_l  clavicle_r  clavicle_out_l  clavicle_out_r  clavicle_scap_l  clavicle_scap_r
      clavicle_pec_l  clavicle_pec_r  upperarm_out_l  upperarm_out_r  upperarm_fwd_l  upperarm_fwd_r
      upperarm_bck_l  upperarm_bck_r
      ```

      配好一个修改器以后，用下拉里的 Duplicate（Shift+D）复制，只改 B 即可。

   结果：`bib` = 每个顶点的"身体骨骼权重占比" w，围兜外圈是 1，脖子是 0，中间过渡。实测 899 个顶点。
2. **把 `bib` 重映射成 S 曲线**：
   1. 加一个 Vertex Weight Edit，Vertex Group 选 `bib`，Falloff Type 选 **Custom Curve**；
   2. 曲线上放 4 个点：(0.05, 0)、(0.275, 0.156)、(0.725, 0.844)、(0.95, 1)。
      在曲线上点一下就加一个点；选中点后，可以在曲线下方直接输入 X / Y；
   3. Move to First，Apply。

   **为什么**：
   - w ≥ 0.95 的部分完全贴到旧身体上，w 0.05～0.95 是过渡带。
   - 过渡带要宽：旧身体的脖子根比新脖子粗、还往前倾。第一次试的 0.1～0.7 只有 2 cm 左右宽，脖子根一圈折出了一道棱。
   - 直接用 w（不重映射）更糟：后背那一圈只贴上去一部分，陷在旧皮下面 1～2 mm，旧皮从围兜里穿出来。
3. **`band`（过渡带：中间 1，两头 0）**：
   1. 新建空组 `band`；
   2. 加一个 Vertex Weight Mix（A = `band`，B = `bib`，A or B，Add），Apply。这时 `band` = `bib`；
   3. 再加一个 Vertex Weight Edit：`band`，Custom Curve，三个点 (0, 0)、(0.5, 1)、(1, 0)。Apply。
4. **`edge`（围兜外沿两圈）**：
   1. 新建空组 `edge`。
   2. Tab 进编辑模式，切到顶点选择，Alt+A 全不选。
   3. Vertex Groups 选 `bib` → Select，Ctrl+I 反选，H 隐藏。这样只剩围兜可见。
   4. Select → Select All by Trait → **Non Manifold**。在左下角的操作面板里只留 **Boundaries**，
      把 Wire、Multiple Faces、Non Contiguous、Vertices 都取消。选中的就是围兜外沿那一圈（实测 72 个顶点）。
   5. Ctrl+小键盘 + 按两次（Select More），多选两圈。Vertex Groups 选 `edge`，下方 Weight 填 **0.33** → Assign。
   6. Ctrl+小键盘 − 按一次（Select Less）→ Weight 填 **0.66** → Assign。
   7. 再 Select Less 一次 → Weight 填 **1.0** → Assign。
   8. Alt+H 显示全部，Tab 回对象模式。实测 `edge` 216 个顶点，三圈各 72 个。

### (c) 贴上去：先绑定 Corrective Smooth，再加两个 Shrinkwrap

顺序很重要：Corrective Smooth 要在挪顶点之前先 **Bind**，记住原来的形状。这样它只平滑"挪了多少"，脸本身的形状细节不会被抹平。

1. 加 **Corrective Smooth**，Move to First，按下表设置。然后点 **Bind**，先别 Apply。
   绑定前修改器会报 "Bind data required"，这是正常的。

   | 项 | 设置 |
   |---|---|
   | Factor | 0.5 |
   | Repeat | 20 |
   | Smooth Type | Simple |
   | Vertex Group | `band` |
   | Only Smooth | 不勾 |
   | Pin Boundaries | 不勾 |
   | Rest Source | **Bind Coords** |

2. 加 **Shrinkwrap**（把围兜贴上去），设置如下，然后 Move to First，Apply：

   | 项 | 设置 |
   |---|---|
   | Target | `BodySkin` |
   | Wrap Method | Nearest Surface Point |
   | Snap Mode | **Above Surface** |
   | Offset | **0.05**（场景单位是 cm，即 0.5 mm） |
   | Vertex Group | `bib` |

3. 再加一个 **Shrinkwrap**（把外沿压下去）：设置同上，只是 Offset 填 **-0.05**，Vertex Group 选 `edge`。Move to First，Apply。
4. 最后把 Corrective Smooth 也 Move to First，Apply。

实测：899 个顶点被挪动，外沿 72 个顶点都在旧皮下面 0.05 cm。

**为什么外沿要压下去**：

- 外沿浮在旧皮上面时，正面看不出来；但从侧面贴着肩膀顶看，视线会从外沿底下的缝钻进去，看到围兜的背面，
  素模和贴图下都是一道细黑线（09-26 踩过）。
- 压在旧皮下面，边就由旧皮盖住，两层在外沿里面交叉过去，看不出缝。

### (d) 把围兜的法线换成旧身体的

1. 给 Face 加 **Data Transfer**：

   | 项 | 设置 |
   |---|---|
   | Source | `BodySkin` |
   | Face Corner Data | 勾，选 **Custom Normals** |
   | Mapping | **Nearest Face Interpolated** |
   | Vertex Group | `bib` |

2. 脸网格 Object Data → Normals 里 Auto Smooth 要勾着（PSK 导入时已经勾了）。
3. Move to First，Apply。

**为什么**：见 2.2。09-26 挪完顶点没换法线，背面围兜和身体的法线夹角中位数从 7.7° 变成了 17.9°，
素模下看得见一道弧线。

### (e) 删掉被围兜盖住的旧皮（外沿那圈留着）

1. **`FaceCore`（去掉外沿两圈的围兜）**：选 Face，原地复制，改名 `FaceCore`；
   进编辑模式，Vertex Groups 选 `edge` → Select → X → Vertices。
2. **标记所有顶点**：选中 `Fiona_BaseBody_BaseBody`，新建顶点组 `near_face`；进编辑模式按 A 全选，
   Weight 填 1 → Assign，回对象模式。
3. **只留离 `FaceCore` 近的顶点**：加 **Vertex Weight Proximity**，设置如下，然后 Move to First，Apply：

   | 项 | 设置 |
   |---|---|
   | Vertex Group | `near_face` |
   | Target | **`FaceCore`** |
   | Proximity Mode | Geometry，勾 Face |
   | Lowest | 0 |
   | Highest | **0.5** |
   | Falloff | 打开旁边的 ⇆（Invert）：离得越近权重越大，0.5 cm 以外为 0 |

4. 加 **Vertex Weight Edit**：`near_face`，勾 Group Remove，Remove Threshold 填 0.01，把 0.5 cm 以外的顶点移出组。
   Move to First，Apply。
5. **删面**：
   1. 进编辑模式，切到顶点选择，Alt+A；
   2. `near_face` → Select；
   3. 材质槽 `inner` → **Deselect**；
   4. 旧头残留的材质槽如果还有，Select；
   5. X → **Faces**：只有四个角都选中的面才会被删。

   实测删掉 724 个面。脚本删 820 个，差别在外沿那圈留得更宽，渲染里看不出来。
6. 删掉顶点组 `near_face`，删掉物体 `FaceCore`。`BodySkin`、`BodyOrig` 后面还要用。

**为什么用 `FaceCore` 算距离**：外沿那圈围兜压在旧皮下面，旁边的旧皮必须留着把边盖住。
用整张脸算距离，会把这圈旧皮一起删掉，外沿就露出来了。

### (f) 把旧身体的法线原样还回去

1. 给 `Fiona_BaseBody_BaseBody` 加 **Data Transfer**，然后 Move to First，Apply：

   | 项 | 设置 |
   |---|---|
   | Source | **`BodyOrig`** |
   | Face Corner Data | 勾，选 **Custom Normals** |
   | Mapping | **Nearest Corner and Best Matching Face Normal** |

2. `BodyOrig` 先留着，(g) 最后还要用一次。

**为什么**：自定义法线是相对周围的面存的。删面以后切口一圈的法线会变（实测最多差 4°），
留下的旧皮和围兜交叉的地方明暗就对不上。

### (g) 骨骼权重和衣服余量（摆姿势、导 XPS / PMX 要用）

到 (f) 为止，静止姿势已经没问题，但一摆姿势就会露馅：弯腰、转头、抬手时，左肩和领口的皮会从 T 恤里穿出来。原因有两个：

- **两套骨头**：围兜只是形状贴到了身体上，权重还是脸自己的 UE 骨（`spine_04`、`clavicle_*`、上臂修正骨）。
  T 恤和身体则跟着 Biped 骨动，两边一动就错开了。
- **4 个权重的上限**：XPS 每个顶点只存 4 个骨骼权重。旧身体本来就最多 4 根骨，
  但从身体插值到围兜上的权重有 5～10 根，导出时被截断，某些姿势会比 T 恤多偏 2 mm 左右。
  所以还得让 T 恤在围兜上方多留一点空。

这一步只改权重和 T 恤，皮肤的形状不动，脱掉 T 恤看到的效果和做之前一样。

1. **`TeeOnly`（只剩 T 恤的副本）**：
   1. 选 `BodyOrig`，原地复制，改名 `TeeOnly`；
   2. 进编辑模式按 A 全选，材质槽 `inner` → **Deselect**，X → Faces。
2. **`collar`（离 T 恤近的程度）**：
   1. 在 `Fiona_BaseBody_Face` 上新建顶点组 `collar`；
   2. 进编辑模式按 A 全选，Weight 填 1 → Assign，回对象模式；
   3. 加 **Vertex Weight Proximity**，设置如下，然后 Move to First，Apply：

      | 项 | 设置 |
      |---|---|
      | Vertex Group | `collar` |
      | Target | `TeeOnly` |
      | Proximity Mode | Geometry，勾 Face |
      | Lowest / Highest | **0.3** / **1.5** |
      | Falloff | **Smooth**，并打开 ⇆（Invert） |

      结果是离 T 恤 0.3 cm 以内为 1，到 1.5 cm 慢慢降到 0。
3. **`wfac`（换权重的比例 = `bib` 和 `collar` 取大）**：
   1. 新建空组 `wfac`；
   2. 加 Vertex Weight Mix（A = `wfac`，B = `bib`，Vertex Group A or B，Add），Apply；
   3. 再加一个 Vertex Weight Mix（A = `wfac`，B = `collar`，Vertex Group A or B，Mix Mode **Maximum**），Apply。
4. **把身体的权重拷过来**：
   1. Vertex Groups 列表右边的 ∨ → **Lock All**，把脸上现有的组全锁住；
   2. 加 **Data Transfer**，设置如下：

      | 项 | 设置 |
      |---|---|
      | Source | `BodySkin` |
      | Vertex Data | 勾，选 **Vertex Groups** |
      | Mapping | **Nearest Face Interpolated** |
      | Layer Selection | 源 **All Layers** → 目标 **By Name** |
      | Mix Mode | **Replace**，Mix Factor 1 |
      | Vertex Group | `wfac` |

   3. 先点修改器顶上的 **Generate Data Layers**。它会在脸上新建身体的那些 Biped 组，实测 85 个。然后 Move to First，Apply。
5. **把脸自己的权重压到 1 − 比例**：
   1. ∨ → **Lock Invert All**：这样新拷来的身体组被锁住，脸自己的组解锁；
   2. 切到 Weight Paint 模式 → Weights → **Normalize All**。在左下角操作面板里，Subset 选 **Deform Pose Bones**，Lock Active 不勾；
   3. 回对象模式，∨ → **Unlock All**。

   效果：没锁的（脸自己的）权重被缩放到每个顶点总和为 1，也就是乘了 1 − `wfac`。贴好的围兜（`wfac` = 1）完全用身体的权重，过渡带按比例混合。
6. **T 恤放出余量**：
   1. 选中 `Fiona_BaseBody_BaseBody`，新建顶点组 `tee_room`；
   2. 进编辑模式 Alt+A，材质槽 `inner` → Select，Weight 填 1 → Assign，回对象模式；
   3. 加 **Vertex Weight Proximity**：Vertex Group `tee_room`，Target `Fiona_BaseBody_Face`，Geometry 勾 Face，
      Lowest 0，Highest **0.5**，打开 ⇆（Invert，Falloff 用默认的 Linear）。Move to First，Apply；
   4. 加 **Displace**：Vertex Group `tee_room`，Direction **Normal**，Strength **0.5**，Midlevel **0**。Move to First，Apply。

   效果：离脸不到 0.5 cm 的 T 恤顶点沿法线往外推 (0.5 − 距离)，也就是 T 恤离围兜至少 5 mm。
   推得最多的地方也不到 3 mm，穿着看不出来。
7. **T 恤的法线还回去**：给身体再做一次 (f) 的 Data Transfer（Source `BodyOrig`、Custom Normals、
   Nearest Corner and Best Matching Face Normal），Apply。
8. **收尾**：
   - 删掉顶点组 `collar`、`wfac`（脸上）和 `tee_room`（身体上）；
   - 删掉物体 `TeeOnly`、`BodySkin`、`BodyOrig`。

**和脚本的区别**：

- 脚本从 T 恤顶点往里、也从围兜顶点往外量间隙，再把衣服推到 4 mm。
  手工版的 Vertex Weight Proximity 只按 T 恤顶点量，照顾不到平面在两个顶点之间下垂的地方。
  余量取 4 mm 时，重放的 XPS 里锁骨上还剩一个小点，放到 5 mm 就没了。
- 脚本还把 V 领下面 8 个离衣服不到 2 mm 的围兜顶点往里收了一点。手工版不做这一步，T 恤放出的余量已经够了。

**实测**（和脚本在同一份输入上对比）：

- 在 Blender 里摆 30 个姿势（每只手臂三个轴各 ±45°、锁骨、头、脊柱），从 T 恤外往里打射线，数脸 / 围兜穿出衣服的次数：
  - 手工版不做这一步：927 处；
  - 做了这一步：0 处；
  - 脚本：2 处。
- 导出 XPS 读回，摆弯腰 + 转头 + 抬左臂的姿势，领口特写干净。
- 脱掉 T 恤的静止渲染和做这一步之前逐像素相同，最多差 1 个像素。

### (h) 肤色（手工版用一个整体倍数）

1. **建顶点色**：Face → Object Data → Color Attributes → **+**，新建 `bib_blend`（Face Corner、Byte Color），设为 active。
2. **把权重写成顶点色**：
   1. 在 Vertex Groups 里点选 `bib`，让它成为活动组；
   2. 切到 Vertex Paint 模式 → Paint → **Vertex Color from Weight**；
   3. 回到对象模式。
3. **接进脸皮肤材质** `MI_Fiona_Face01_`（在 Shader Editor 里）：
   1. Add → Input → **Color Attribute**，选 `bib_blend`；
   2. 新建一个 Mix（Multiply），把 Color Attribute 的 Color 接到它的 **Fac**；
   3. 原来接到 Base Color 的那根线改接到 Mix 的 Color1，Color2 填 **(1.138, 1.067, 0.944)**；
   4. Mix 的输出接 Base Color。

**这个倍数怎么来的**：

- 它是围兜外沿一圈上，旧身体贴图颜色和围兜颜色的比值。围兜颜色要把脸材质里 HSV 的 0.9297、乘色 (1, 0.9047, 0.9047) 算进去。
  脚本日志里 `match_bib_tone` 打印的 "outer bib … median" 就是这一组。
- 脚本逐顶点计算：前胸、后背各用各的比值，写进顶点色 `bib_tone`，Mix 的 Fac 填 1，Color2 接顶点色。
- 手工版只用一个整体倍数。重放时贴图下看不出差别，后背贴得很近看时可能略亮一点。

### 检查（一定要做）

09-26 前两轮修复都是因为看得不够近才返工，这些都要过一遍：

- **穿着、脱掉 T 恤各看一遍**。脱 T 恤的方法：
  1. 新建顶点组 `inner_v`，进编辑模式选 `inner` 槽 → Assign；
  2. 给身体加 **Mask** 修改器：Vertex Group 模式，选 `inner_v`，点 ⇆ 反选；
  3. 看完把 Mask 修改器的眼睛图标关掉。
- **近景**：约 45 cm 距离、70–85 mm 焦距；正面、3/4、侧面、背面、俯视都看。两个肩膀顶再从侧面贴近看一眼。
- **着色模式**：Material Preview 和 Solid 都看。Solid 模式里把 Color 设成 Material，就能看出哪片是旧身体、哪片是新脸。
  这种模式下外沿那圈红紫交错是正常的：两层几乎重合地交叉，贴图和白模下看不出来。
- **摆个姿势**：穿着 T 恤，姿态模式下转一下 `Bip001_Spine2`，再把 `Bip001_L_UpperArm` 抬起来。
  看领口和锁骨上有没有皮从 T 恤里穿出来，看完 Alt+R 复位。
  转头（`Bip001_Neck`、`Bip001_Head`）要等第 4 节把两副骨架并成一副以后再试：在那之前，头还挂在 UE 骨上，不跟着 Biped 骨转。
- **要求**：不能有洞、台阶、细线、颜色断层；不能靠衣服遮；摆姿势时不能从衣服里穿出来。

### 或者：直接跑脚本

不想手做的话，在 2.6 建好材质以后、第 4 节之前，对手工文件跑脚本：

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' -b D:\vindictus_manual\blend\Fiona_BaseBody\Fiona_BaseBody.blend --factory-startup --python E:\code\othercode\ripper_tpose\scripts\vindictus\fix_basebody_neck.py -- --out D:\vindictus_manual\blend\Fiona_BaseBody\Fiona_BaseBody_neck.blend
```

- 为什么在第 4 节之前：脚本要用 `neck_01` 骨找脖子，第 4 节会把它删掉。
- 2.1 改过名的不用加参数；没改名就加 `--face SK_Fiona_Face01.001 --body SM_pc_fiona_basebody.001`。
- 在手工组装的文件上实测：899 个顶点贴上去，外沿 72 个压进去，删 822 个面，和自动构建一致。

**手工版和脚本的对比**：同一份输入上重放，结果如下。

- 各段偏移中位数相差不到 0.06 cm；
- 外沿都在旧皮下 0.05 cm；
- 贴好部分的法线和旧身体一致；
- 贴图、白模渲染看不出差别；
- 只有按材质上色时，手工版外沿交叉的那圈更宽；
- 摆姿势（(g)）：Blender 里 30 个姿势穿出衣服 0 处（脚本 2 处）；XPS 读回，弯腰 + 转头 + 抬左臂的姿势两边都干净。

自动流程：`fix_basebody_neck.py` 的 `fit_face_to_body()`、`match_bib_tone()`，由 `build_blend.py` 调用。

---

## 4. 并成一副骨架（导 XPS / PMX 之前必做）

**为什么必须做：**

- 身体绑在 `Bip001_*` 上，脸绑在 UE 的 `head` / `spine_04` / `clavicle_*` 上。
  到了 XPS 或 MMD 里，摆 Biped 骨只有身体动，脸和头发留在原地。
- 两副骨架都在的时候，Blender2XPS 会把 UE 骨映射成 XPS 标准名（root hips、arm left shoulder 2 …），
  而真正带着身体的 Biped 骨反倒没有标准名。XPS 姿势全乱。
  归档里的 `Shiningwill_legacy.xps` 也是 Biped 身体 + UE 脸，从它的导出报告看，
  `root hips`、`arm left shoulder 2` 等标准名确实落在了 UE 骨上。

**第 3 节要先做完**，下面会改脸上的组名。

### 4.1 把脸上 4 个组并到 Biped 名字上

UE 主链上带权重的就是下面 4 个组。头发和身体不用 UE 主链。

| 原名 | 并到 |
|---|---|
| `head` | `Bip001_Head` |
| `spine_04` | `Bip001_Spine2` |
| `clavicle_l` | `Bip001_L_Clavicle` |
| `clavicle_r` | `Bip001_R_Clavicle` |

在 `Fiona_BaseBody_Face` 的 Vertex Groups 列表里先搜一下右边那个名字，按有没有分两种情况：

- **脸上还没有这个组**：双击左边的组，直接改名。
- **脸上已经有这个组**：不能改名，要合并。
  - 什么时候会有：跑过脚本 `fix_basebody_neck.py`（2026-09-26 之后的自动构建都跑过），围兜会带上身体的 Biped 权重，这 4 个名字多半已经存在。
  - 为什么不能改名：改成重名，Blender 会悄悄变成 `Bip001_Spine2.001`，这部分权重就没有骨骼带了。
  - 合并步骤：
    1. 加 **Vertex Weight Mix**：A = 右边的组（如 `Bip001_Spine2`），B = 左边的组（如 `spine_04`），
       Vertex Set 选 **Vertex Group A or B**，Mix Mode 选 **Add**；
    2. Move to First，Apply；
    3. 在列表里选中左边那个旧组，点 **−** 删掉。

### 4.2 把 UE 主链下面的子骨挂到 Biped 上

进骨架编辑模式。操作方法：先选子骨（可以多选），最后 Shift 选目标骨，Ctrl+P → **Keep Offset**。

| 子骨（原来的父骨） | 挂到 |
|---|---|
| `clavicle_pec_l/r`、`spine_04_latissimus_l/r`（原父骨 spine_05） | `Bip001_Spine3` |
| `clavicle_out_l`、`clavicle_scap_l`（原父骨 clavicle_l） | `Bip001_L_Clavicle` |
| `clavicle_out_r`、`clavicle_scap_r`（原父骨 clavicle_r） | `Bip001_R_Clavicle` |
| `upperarm_correctiveRoot_l`（原父骨 upperarm_l） | `Bip001_L_UpperArm` |
| `upperarm_correctiveRoot_r`（原父骨 upperarm_r） | `Bip001_R_UpperArm` |
| `FACIAL_C_Neck1Root`（原父骨 neck_01）、`FACIAL_C_Neck2Root`（原父骨 neck_02） | `Bip001_Neck` |
| `FACIAL_C_FacialRoot`、`hair_root`（原父骨 head） | `Bip001_Head` |
| `breast_l`、`breast_r`（原父骨 spine_04） | `Bip001_Spine2`（没有权重，也可以直接删） |

**为什么要先挂再删**：Blender 删骨时，会把它的子骨交给它的父骨。整条链都删掉以后，子骨就变成没有父骨的根骨，
脖子皮和整张脸都不跟任何骨动了。

### 4.3 删掉 UE 主链

选中下面 14 根，按 X 删除：

```text
root  pelvis  spine_01  spine_02  spine_03  spine_04  spine_05  neck_01  neck_02  head
clavicle_l  clavicle_r  upperarm_l  upperarm_r
```

### 4.4 检查

- 大纲里骨架顶层只剩一根 `Root`，共 1013 根骨。
- 姿态模式下依次转 `Bip001_Spine2`、`Bip001_Neck`、`Bip001_Head`、`Bip001_L_Clavicle`，
  脸和头发都要跟着动。实测转 `Bip001_Spine2` 20°：身体移动 22.5 cm，脸 4.7 cm，头发 5.0 cm。
- 顶点组如果对应的骨已经删了，Blender 不会报错，这些顶点只是不动。所以一定要摆一下姿势看看。

自动流程：目前没有，自动构建产出的 Fiona_BaseBody 仍是两副骨架。

---

## 5. 导出 XPS

### 5.1 用 Blender2XPS 导出

1. **导出前清理**：
   - 确认辅助物体 `BodySkin`、`BodyOrig`、`FaceCore`、`TeeOnly` 都已删掉；
   - 删掉辅助顶点组 `bib`、`band`、`edge`、`oldhead`、`near_face`、`inner_v`，以及 Mask 修改器（`bib_blend` 顶点色已经写好，不再需要 `bib` 组）。
2. N 面板 → **XPS** 页 → 「Blender2XPS 导出」，按下表设置：

   | 项 | 设置 |
   |---|---|
   | 骨架 | `Fiona_BaseBody_rig` |
   | 输出文件 | `D:\vindictus_manual\xps\Fiona_BaseBody\Fiona_BaseBody.xps` |
   | 缩放 | **0.01**（厘米场景 → 约 1.75 单位高） |
   | 导出顶点色 | **不勾**：第 3 节 (h) 的 `bib_blend`（跑脚本时是 `bib_tone`）会被当成顶点色写进去 |
   | 其余 | 保持默认，见下面 |

   其余默认项：
   - 文件格式：自动（v2.15，每顶点 4 权重，XPS 11.x 都能读）；
   - 骨骼命名：映射为 XPS 标准骨名；
   - 隐藏辅助骨：勾；
   - 材质烘焙：自动；
   - 跳过半透明辅助壳：勾；
   - 复制贴图到输出目录：勾。

3. 先点 **检查模型**，结果写在文本块 `blender2xps_report` 里；没问题再点 **导出…**。
4. 看结果。报告 `.xps.report.txt` 里应当是：
   - 1013 根骨，高约 1.75；
   - 改名清单：`Root → root ground`、`Bip001 → root hips`、`Bip001_Spine → spine lower`、`Bip001_Head → head neck upper`、
     `FACIAL_L_Eye → head eyeball left`、`FACIAL_C_Jaw → head jaw`、`Bip001_L_UpperArm → arm left shoulder 2` 等；
   - 校验 OK。
5. **烘焙贴图留着**：头发、眉毛、睫毛、眼球这些颜色由节点算出来的材质，会用 Cycles 烘焙成 `*_baked.png`，
   要一两分钟。PMX 那一步还要用这些图。

### 5.2 检查

- **在 XPS 里看**：XNALara XPS 11.8 → Modify → Load Generic Item → 选 `.xps`。逐项看：
  - 贴图都在（没有白模或粉色）；
  - 头发透明正常；
  - 转 `arm left shoulder 2`、`spine upper`、`head neck upper`，脸要跟着身体走，脖子接缝不开；
  - 在模型的部件列表里取消勾选 `inner` 那一件就是裸体（具体菜单未实测）。
- **在 Blender 里回读**：File → Import → XNALara / XPS → XNALara/XPS Model (.ascii/.mesh/.xps)。
  回读后骨架显示成躺倒 90°，只是 XPS 用 Y-up 坐标造成的显示问题，见 [xps-addon.md](xps-addon.md)。

### 5.3 另一个导出器

XNALaraMesh 自带的导出（File → Export → XNALara / XPS）也能用，但它有两个要求：

- 材质必须包在叫 `XPS Shader` 的节点组里，普通 Principled 材质会被写成 `missing.png`；
- 部件名要按 `<渲染组>_<名字>_<高光>` 命名。

详见 [xps-addon.md](xps-addon.md)。Blender2XPS 没有这些要求。

**自动流程**（`E:\game_export\Vindictus\Fiona\xps\` 里的 16 个 XPS 都是这样导出的；Fiona_BaseBody 还没有 XPS）：

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' -b --python E:\code\othercode\blender2xps\tools\batch_export_blends.py -- --out <目录> --scale 0.01 --bake AUTO <blend>
```

---

## 6. 导出 PMX

Vindictus 这条线没有自动导 PMX 的脚本。最接近的是星刃 Mod 版 Fiona 用的
`scripts\stellarblade\export_pmx_blender.py`，它复用 ROE 流程的函数。下面是手工版，坑都是那条脚本踩过的。

### 6.1 工作副本，厘米换算成米

1. File → Save As，另存为 `Fiona_BaseBody_pmx.blend`。后面的步骤会大改骨架，原文件留着。
2. 对象模式下操作：
   1. 按 A 全选；
   2. Shift+C（游标回到原点）；
   3. 3D 视图顶部的 Pivot Point 选 **3D Cursor**；
   4. 按 S，输入 0.01，回车；
   5. Ctrl+A → **All Transforms**。
3. 在 N 面板看 Dimensions Z，应约为 1.75 m。实测换算后摆姿势仍然正常。

**为什么**：Convert to MMD 5 的几何阈值按米设计。骨架超过 10 个单位高时，它会当成厘米骨架，把整个模型缩成 1/10。

### 6.2 删掉插槽骨

1. 进骨架编辑模式 → Select → Select Pattern… 输入 `Anim_Attachment*`，会选中 12 根。
2. 按 X 删除。

这些是游戏的挂点，没有蒙皮，有的离身体很远：`Anim_Attachment_EyeTarget` 在脸前 1.2 m。
星刃那次就是一根在地板下 22 m 的插槽骨，让整个模型被缩成了 1/10。

### 6.3 用 Convert to MMD 5 转骨架

在 N 面板 → **Convert to MMD** 页，模式选「主骨骼管理」，转换路线选「标准·重建权重」。

1. 选中骨架，点「自动识别骨架（填充下方槽位）」。
2. 有几个槽位识别错了，按下表改。可以在槽位的下拉框里搜骨名，
   也可以先在编辑 / 姿态模式里选中那根骨，再点该行的放大镜按钮（从选中骨填入）：

   | 槽位 | 自动识别结果 | 改成 |
   |---|---|---|
   | 全ての親 | `Root` | `Bip001` |
   | センター | `Bip001` | 留空（插件会自己建） |
   | 下半身 | 空 | `Bip001_Pelvis` |
   | 頭* | `FACIAL_C_FacialRoot` | `Bip001_Head` |
   | 目（左 / 右） | `FACIAL_L_EyesackUpper` / `FACIAL_R_EyesackUpper` | `FACIAL_L_Eye` / `FACIAL_R_Eye` |

   其余槽位自动识别是对的：上半身 `Bip001_Spine`、首 `Bip001_Neck`，
   肩 / 腕 / ひじ / 手首、足 / ひざ / 足首 / 足先EX 以及十根手指。

   **为什么这样改：**
   - 下半身：臀部的蒙皮在 `Bip001_Pelvis` 上。下半身留空的话，插件会另建一根空的下半身，
     `Bip001_Pelvis` 原样留着，MMD 里扭腰时屁股不动。ROE 的 Biped 也是这样对应的。
   - 目：眼球顶点绑在 `FACIAL_L_EyeParallel` / `FACIAL_L_Pupil` 上，这两根挂在 `FACIAL_L_Eye` 下面。

3. 点「**一键转换 XPS→MMD(标准)**」。注意这个按钮会先重新自动识别，把刚改好的槽位覆盖掉。
   所以点完马上打开 Edit → Adjust Last Operation（或左下角的操作面板），取消勾选「**自动识别骨架**」，
   它会用你改过的槽位重跑一遍。
   - 也可以先点「导出预设」把槽位存起来，下次用。
   - 手动分步按钮 1–15 也能走完全程，但一键流程里有两步顶点组清理（1.45 和转换后那次），分步按钮里没有，
     手腕可能撕开。
4. 看结果（实测）：
   - 15/15 步成功，共 1088 根骨；
   - 有センター、グルーブ、腰、上半身 / 2 / 3、首、頭、左目 / 右目，
     腕 / ひじ / 手首和对应的捩骨，足 / ひざ / 足首和对应的 D 骨、IK，肩P；
   - 腿由 IK 带动：直接转 `左足` / `左ひざ` 没反应，要移动 `左足ＩＫ`；
   - 顶层会多出一根没有子骨、没有权重的 `Root`，可以删，不删也没影响。

### 6.4 両目（未实测）

插件不建 両目。视线动作（VMD 里的 両目 关键帧）需要它，手工补：

1. 骨架编辑模式，Shift+A 加一根骨，命名为 `両目`，放在两眼上方，Ctrl+P（Keep Offset）挂到 `頭`。
2. 在 Bone Properties → **MMD Bone Tools** 里设 Name = 両目、Name(Eng) = eyes。
3. 在同一个面板里分别设置 `左目` 和 `右目`：
   - 打开 **Rotate +**，目标骨选 `両目`，Influence 1；
   - **Transform Order 设为 1**。
4. N 面板 MMD 页 → Operator → Bone Constraints: **Apply**。
5. 在 Display Panel 里把 `両目` 加进一个显示枠，否则 MMD 里选不到它。

**为什么 Transform Order 要设 1**：MMD 按变形阶层和骨序号的顺序计算骨骼，
付与（Rotate +）的来源骨必须先算。`両目` 加在骨架末尾，序号比 `左目` / `右目` 大。
不把两只眼设成阶层 1，MMD 里视线关键帧就不起作用；Blender 里却看不出来，因为 mmd_tools 用约束实现付与。
ROE 在 2026-09-06 之前导出的所有模型都有这个问题。

### 6.5 物理

- **身体碰撞刚体**：Convert to MMD 页 → 「衣服 / 刚体」→ **1. 身体碰撞刚体(自动)**。
  要先建身体刚体，再建头发，头发才不会穿进身体。
- **头发**：N 面板 MMD 页 → **Cloth Physics**：
  1. **Body bone regex** 从 `^Bip0\d\d\b` 改成 `^Bip0\d\d`。
     原因：Vindictus 的 Biped 骨名用下划线，`\b` 匹配不上。结果 `Bip001_L_Shoulder01 → Bip001_L_UpperArm01`
     这种带着上臂皮肤的两节辅助骨会被当成布料链，上臂皮肤会飘起来。
  2. 勾 Hair too → 点 Analyze garments。列表里应该只有头发（`Fiona_hair_*`），别的都取消勾选。
  3. 依次点 Build physics → Drop test → Preview (build + play) 看效果；看完点 **Stop preview** 再导出。
  4. 检查头发的"根"：`Fiona_hair_root` 和各个 `Fiona_hair_*_root` 要是 **Bone** 模式（跟骨走，不参与物理）。
     在 MMD 页 Rigid Bodies 里选中刚体看 Mode。星刃 Fiona 的头皮根骨当了物理刚体，站着不动就沉下去 12 cm，像秃了一块。
- **胸部（未实测）**：没有工具会自动建胸部物理，要手工做。数值取自 `scripts\stellarblade\export_pmx_blender.py` 的 `BUST`。
  左右各一个：
  1. **建刚体**：姿态模式选 `Bip001_L_bust_1` → MMD 页 Rigid Bodies 点 **+**。设置：
     - Shape：Sphere，半径约 0.05（单位 m）；
     - Mode：Physics + Bone；
     - Mass 1，Damping 0.5 / 0.5；
     - 碰撞组 14（PMXEditor 里显示为 15），不与任何组碰撞（碰撞遮罩全勾）；
     - 位置：把球移到 `Bip001_L_bust_2` 的头部（乳房中心）。
  2. **建关节**：选中 上半身2 的碰撞刚体和这个胸部刚体 → Joints 点 **+**。设置：
     - 位置：`Bip001_L_bust_1` 的头部；
     - 旋转限制：X ±15°、Y ±5°、Z ±12°；
     - 旋转弹簧：120；
     - 不允许平移。
- **膝盖辅助骨（可选，未实测）**：
  - 问题：`Bip001_L_knee` 带着 268 个膝盖顶点，却挂在大腿上（转换后在 `左足D` 下）。弯膝盖时膝盖骨留在大腿上。
  - 做法：在 MMD Bone Tools 里打开 Rotate +，目标骨选 `左ひざ`，Influence 约 0.5，Transform Order 设 1；右边同样处理；
    最后点 Bone Constraints: Apply。
  - 依据：ROE 批处理实测膝盖辅助骨约跟随 52%，自动版的做法见
    `scripts\riseoferos\export_character_model_blender.py` 的 `plan_joint_helper_moves()` / `apply_helper_grants()`。

### 6.6 表情（未实测）

- **为什么只能做骨骼表情**：PSK 不带形态键，UE Viewer 导出的这张脸一个形态键都没有。
  星刃 Mod 版 Fiona 的 52 个 ARKit 形态键来自 Mod 作者的网格，不是游戏里的这张脸。
  所以只能用 `FACIAL_*` 骨做**骨骼表情**：
  - あ：旋转 `FACIAL_C_Jaw`（下颌）；
  - まばたき：把 `FACIAL_L/R_EyelidUpperA*` 往下移。
- **做法**：
  1. N 面板 MMD 页 → Morph Tools → Bone 页 → **+**，填名字；
  2. 进姿态模式摆好这个表情；
  3. 点 **Apply**（把当前姿势存进表情），再 Clear 复位；
  4. 在 Display Panel 里把表情加到「表情」枠。
- `mmd_face_morphs` 插件是给 ROE 那 32 根脸骨写的，这张 MetaHuman 脸用不了。
- **更好的办法：用游戏自己的表情数据。**
  - 脸网格包 `SK_Fiona_Face01.uasset` 里嵌着 MetaHuman 的 DNA（`DNAAsset`，UE Viewer 不导出）。游戏运行时靠它，用 269 个表情控制驱动这些 `FACIAL_*` 骨。
  - `scripts\vindictus\metahuman_dna.py` 把它从游戏容器里取出来并按 RigLogic 的方式求值；`export_pmx.py` 再把每个 MMD 表情对应的控制组合算成骨骼表情。
  - 这一步手工做不了（每个表情要动 100～470 根骨），只能跑脚本。

### 6.7 材质

在 Material Properties 的 MMD Material 和 MMD Texture 两个面板里改。

- **一个材质只带一张图**：mmd_tools 每个材质只保留一张贴图。头发、眉毛、睫毛可能拿到 ODI 遮罩（头发变灰），
  眼球可能拿不到图（虹膜全黑）。
  做法：在 MMD Texture → Texture 里先 Remove，再 Add，选 5.1 导出的 `*_baked.png`。
- **半透明壳**（EyeShdow、Lacrimal、EyeReflection_Fake）：MMD Material → **Alpha 设 0**。
  PMX 没有混合模式，不设的话会导成不透明，眼睛周围一圈发白、发灰。
- **光照值**（星刃那次调出来的）：
  - Diffuse (1, 1, 1)；
  - Ambient (0.5, 0.5, 0.5)；
  - Specular 低一些，约 0.12。

  默认值偏暗、偏油。
- **眼球**：关闭 Self Shadow，关闭 Double Sided。
- **脸皮肤**：第 3 节 (h) 的肤色过渡靠顶点色，单张贴图带不过去。
  如果 5.1 的报告里脸皮肤也烘成了 `_baked.png`，就换成那张。

### 6.8 导出

1. 在大纲里选中转换生成的**模型根物体**（骨架的父级，默认叫 New MMD Model 的空物体）。
   到 Object Properties → **MMD Model Information** 里填 Name / Name(Eng)，
   不填的话 MMD 里会显示 mmd_tools 的默认名 "New MMD Model"。
2. 模型根保持选中，N 面板 MMD 页 → Operator → Model 一栏点 **Export**，设置：

   | 项 | 设置 |
   |---|---|
   | Scale | **12.5**（默认是 1.0；场景已经是米，填 1.0 只有 1.75 单位高） |
   | Copy textures | 勾 |
   | 其余 | 默认 |

3. 保存到 `D:\vindictus_manual\pmx\Fiona_BaseBody\Fiona_BaseBody.pmx`。实测：1088 根骨，回读高度 21.9 个 MMD 单位。

### 6.9 检查

- **Blender**：
  1. 在 MMD 页用 Import 导入 PMX，勾上 Physics；
  2. 转 上半身 / 首 / 頭 / 左腕，移动 左足ＩＫ；
  3. 导入 VMD 时 **Margin 填 30**。Margin 为 0 的话第一帧会把头发整条甩飞，看着像模型坏了，其实不是。
- **PMXEditor**（汉化版菜单名可能不同，未实测）：
  1. 打开 `.pmx`；如果启动报错，先装软件目录里「！！如果出现报错…」文件夹中的运行库；
  2. 看骨骼、材质（有没有缺贴图）、表情、刚体、Joint 各页；
  3. 在 TransformView 里转骨骼、拉表情、打开物理。
- **MMD**（未实测具体菜单名）：
  1. 把 `.pmx` 拖进窗口；
  2. 选中模型后，把一个 `.vmd` 拖进去；
  3. 物理演算菜单选「常に演算」；
  4. 播放，重点看脖子接缝、肩膀、膝盖、头发、胸部，以及视线（VMD 里有 両目 关键帧时）。

### 6.10 另一条路线：直接从 XPS 转

手里只有 `.xps` 时用，例如 `E:\game_export\Vindictus\Fiona\xps\Fiona_BaseBody\`。

**比从 blend 转省事的地方**：
- 已经是米；
- 只有一副骨架；
- 主干骨是 XPS 标准名；
- 贴图已烘焙好。

**代价**：
- 每顶点只有 4 个权重；
- 材质是烘焙后的平面图；
- 没有形态键；
- 眼周半透明壳没导出。

1. **导入**：文件 → 导入 → XNALara/XPS Model (.ascii/.mesh/.xps)，选项全用默认。
   得到骨架 `Armature`（1013 根骨）和 9 个网格，高 1.75 m。
2. **确认骨架没有缩放**：选中 `Armature`，N 面板 Item 页的 Scale 应为 1。不是 1 就按 **Alt+S** 清掉。
   实测：骨架带 9.808 倍缩放时插件照样 15/15 成功，但 PMX 有 214.8 个单位高（正常 21.9）。
3. **自动识别**：
   1. 物体模式选中 `Armature`；
   2. N 面板 **Convert to MMD** 页 → 选「主骨骼管理」和「标准·重建权重」；
   3. 点「自动识别骨架（填充下方槽位）」。
4. **改 4 行槽位**：

   > 插件面板顶部的 build 号是 `2026-09-26 xps-names…` 或更新时，这一步和第 5 步取消勾选都可以跳过。
   > 新版识别会优先认 XPS 标准骨名，自动结果就是：
   > - 頭 = `head neck upper`；
   > - 目 = `head eyeball left / right`；
   > - センター = `root hips`（没有权重）；
   > - 下半身 由插件新建，`Bip001_Pelvis` 的臀部权重会转过去。
   >
   > 这个结果是 2026-09-26 在同一个 XPS 上实测的。直接点一键转换即可，下表只适用于旧版插件。

   | 槽位 | 自动识别结果 | 改成 | 原因 |
   |---|---|---|---|
   | センター | `Bip001_Pelvis` | 清空 | 它带着 3935 个臀部顶点；センター 是不变形骨，插件会自己建一根 |
   | 下半身 | 空 | `Bip001_Pelvis` | 臀部蒙皮归 下半身，扭腰时屁股才跟着动 |
   | 頭* | `FACIAL_C_FacialRoot` | `head neck upper` | 这是 `Bip001_Head` 改名来的，脸和头发都挂在它下面 |
   | 目（左 / 右） | `FACIAL_L_EyesackUpper` / `FACIAL_R_EyesackUpper` | `head eyeball left` / `head eyeball right` | EyesackUpper 是眼袋骨；眼球顶点在 eyeball 下面的 EyeParallel / Pupil 上 |

   - **怎么改**：点格子会弹出骨骼搜索框，输入名字的一部分再点选。
   - **怎么清空**：鼠标停在格子上按 Backspace，或右键 → 重置为默认值。
   - 左右两只眼都要手动改。右眼格子里已经有值，插件不会跟着左边自动填。
   - 其余不用动，都认对了：
     - 全ての親 `root ground`；
     - 上半身 `spine lower`；
     - 首 `head neck lower`；
     - 手臂、腿、手指（XPS 标准名）。
5. **一键转换**：
   1. 点「一键转换 XPS→MMD(标准)」。它会先重新自动识别，把第 4 步改的槽位盖掉，状态栏显示「16/16 步成功」。
   2. 马上展开 3D 视图左下角的「一键转换 XPS→MMD」面板（收起了就按 F9），取消勾选「**自动识别骨架**」。
      Blender 会撤销刚才那次，恢复你改的槽位，再重跑一遍。
   3. 状态栏应显示「**15/15 步成功**」。

   实测（在有界面的 Blender 里用撤销 + 重跑复现，面板做的就是这两步）：
   - 撤销后，4 行槽位原样恢复；
   - 重跑后 1099 根骨，`head neck upper` 已改名为 `頭`，`頭` 的父级是 `首`；
   - `左目` 挂在 `FACIAL_C_FacialRoot` 下。

   16/16 那次的结果是错的：
   - `頭` 成了 FacialRoot，旋转中心不对；
   - `左目` 成了眼袋骨，转眼睛时动的是眼皮。
6. **检查**：姿态模式下做三个测试：
   - 转 `頭`，脸、头发、睫毛一起动；
   - 转 `左目`，眼球动；
   - 移动 `左足ＩＫ`，腿会弯。
7. **材质不用改**：XNALaraMesh 建的材质已经接好贴图，mmd_tools 转换时自动取到。
   9 个材质都有图，头发、睫毛、眉毛、眼球、脸用的是烘焙图。这一点和 6.7 不同。
8. **导出**：同 6.8。选中 `New MMD Model` 填名字，Export 时 Scale 填 **12.5**，勾 Copy textures。
   实测：PMX 约 6.1 MB，`textures\` 里 9 张图；回读 1103 根骨，高 21.90。
9. **可选**：
   - 両目（6.4）、头发和胸部物理（6.5）、表情（6.6）手工做的话，做法和从 blend 转一样，这条路线上没手工实测。
   - **这三样也可以用脚本一次做完**：`scripts\vindictus\export_pmx.py`，用法见 `scripts/vindictus/README.md`「导出 PMX」。
     - 表情：从脸的 MetaHuman DNA 算出 26 个标准表情；
     - 胸部：按你的 乳奶 模板建刚体；
     - 头发：发束贴着头皮的部分跟随头骨，下垂的发尾参与物理。
   - 要裸体版：导出前删掉网格 `5_BaseBody-inner_0.1_0_0`（T 恤）。脖子已经修成去掉 T 恤也完整。

**摆姿势实测**：同一组姿势分别摆在原始 XPS 骨架和转换后的骨架上，统计"拉长到 3 倍以上、且伸长超过 1.6 cm"的边：

| 姿势 | 原始 XPS | 转换后 |
|---|---|---|
| 手臂上抬 60° | 9 | 9 |
| 手臂上抬 90° | 35 | 34 |
| 手臂前伸 60° + 屈肘 60° | 0 | 0 |
| 大腿前抬 45°（加屈膝 60° 也一样） | 7 | 7 |
| 大腿侧抬 30° | 5 | 5 |
| 上半身前弯 30° | 0 | 0 |

两边一样多，说明是 XPS 自带的权重，不是转换造成的：

- **腋下**：拉长的顶点挂在 `Bip001_L_deltoids`、`Shoulder01`、`infraspinous_02` 这些肌肉辅助骨上。
  游戏里由动画带动它们，XPS 和 MMD 里没有东西带。
- **胯部**：拉长的顶点主要挂在 `Bip001_Pelvis`（转换后的 `下半身`）上。

脖子接缝：静止时脸和身体对应顶点相距 0.3 cm，各姿势下不超过 0.4 cm，没有开缝。

---

## 7. 常见问题

| 现象 | 原因 | 办法 |
|---|---|---|
| UE Viewer 列表是空的，或提示 unversioned UE5 package | 没指定引擎版本 | Override game detection 选 Unreal engine 5.3 |
| 提示 encrypted UE5 package | 索引用 AES 加密 | 粘贴 `aes_key.txt` 那一行，或用 `-aes=@文件` 启动；key 丢了就用 `find_aes_key.py` 重新算（约 80 秒） |
| `SK_female_base` 导不出网格 | 它是 Skeleton 资源 | 素体用 `Model/Mesh/SM_pc_fiona_basebody` |
| 两个模型的贴图互相串了 | 同时开了多个 UE Viewer 导出，共用贴图被覆盖 | 一次只导一个 |
| 合并后身体侧着，脸朝前 | Biped 朝 +X | 2.3：骨架 Rotation Z −90，Location Y 6.9，Apply |
| 身体 / 头发不跟骨架动 | 合并骨架后 Armature 修改器的 Object 变空 | 2.4 第 2 步 |
| 摆头时头发不动 | `hair_root` 挂在 `head.001` 上 | 2.4 第 3 步 |
| 旧头从新脸里穿出来；T 恤领口缺口 | 没切旧头；或切的时候没保护 `inner` | 2.5 |
| 凹凸是反的 | UE 法线是 DirectX 格式 | 翻转 G 通道（2.6） |
| 衣服或皮肤发金属色 | ORM 接错了（曾经把 `Normal Map` 当成 "rma" 接进金属度） | 皮肤不接 ORM；服装的 ORM/ARM 是 G = 粗糙度、B = 金属度，参数名按整词匹配 |
| 眼睛发暗、虹膜发黑 | 取色器的采样值是 sRGB 编码 | 从 Fiona.blend 追加眼球材质；导 XPS / PMX 前先烘焙 |
| 睫毛发白、浅棕色 | 睫毛材质也有 ODI 贴图，被当成头发接了发根→发梢渐变，渐变没有输入，一直取中间的浅棕（2026-09-26 之前的自动构建都是这样） | 按 2.6 的表接：Base Color 用 `.props.txt` 里的 `Color`（接近黑，0.004），ODI 的 R 连 Alpha |
| 脖子一圈接缝，素模下背面有弧线 | 顶点挪了，自定义法线没跟着换 | 第 3 节 (d)、(f) |
| 从侧面看肩膀顶有一道细黑线 | 围兜外沿浮在旧皮上面，视线从缝里看到了围兜背面 | 第 3 节 (b)4 + (c)3：外沿压进旧皮下面，(e) 用 `FaceCore` 留住盖边的旧皮 |
| 脖子根一圈折出一道棱 | 过渡带太窄（旧脖子根比新脖子粗） | 第 3 节 (b)2 的 S 曲线（0.05～0.95）+ (c) 的 Corrective Smooth |
| 脱掉 T 恤后锁骨、后背有洞 | 按"被衣服盖住"删了皮 | 第 3 节：贴围兜，不删皮 |
| 摆姿势（弯腰、转头、抬手）时左肩、领口的皮从 T 恤里穿出来 | 围兜还用脸的 UE 骨权重，T 恤跟着 Biped 骨动 | 第 3 节 (g) 第 1～5 步：围兜改用身体的权重 |
| 换了权重以后，XPS 里某些姿势锁骨上还有一两个小点穿出来 | XPS 每顶点只存 4 个权重，截断后围兜比 T 恤多偏 2 mm 左右 | 第 3 节 (g) 第 6 步：T 恤在围兜上方放出 5 mm 余量 |
| 4.1 改名以后多出 `Bip001_Spine2.001` 这类组 | 脸上已经有同名的 Biped 组（跑过脚本或做过 (g)），改名撞名 | 4.1：已有同名组时用 Vertex Weight Mix（Add）合并，再删旧组 |
| XPS 里摆姿势，脸不跟身体 | 还是两副骨架 | 第 4 节 |
| XPS 里脸、脖子颜色不对（推测，没实测） | Blender2XPS 导出的是当前顶点色层，`bib_blend` / `bib_tone` 会被当成顶点色写进去 | Blender2XPS 里不勾「导出顶点色」 |
| PMX 整体缩成 1/10 | 场景是厘米，或有很远的插槽骨 | 6.1 缩到米，6.2 删 `Anim_Attachment*` |
| PMX 只有 1.75 高 | mmd_tools 导出时 Scale 用了默认的 1.0 | 填 12.5 |
| 从 XPS 转的 PMX 有 214 单位高（大了 10 倍） | 骨架物体带着缩放（导入后按过 S） | 转换前选中骨架按 Alt+S（6.10 第 2 步） |
| 一键转换后状态栏显示 16/16 步 | 自动识别又跑了一遍，改过的槽位被盖掉 | 左下角面板取消勾选「自动识别骨架」，应变成 15/15（6.3 / 6.10 第 5 步） |
| MMD 里扭腰屁股不动 | 下半身槽位空着，`Bip001_Pelvis` 没被接管 | 6.3：下半身 = `Bip001_Pelvis` |
| 頭 / 目 识别错了 | 自动识别按拓扑和几何判断，被 `FACIAL_*` 骨干扰 | 6.3 改槽位，并取消勾选「自动识别骨架」重跑 |
| 视线（両目）不动 | 付与来源骨的计算顺序不对 | 6.4：左目 / 右目的 Transform Order 设为 1 |
| 头发发灰、虹膜发黑、嘴里发灰 | mmd_tools 每个材质只保留一张贴图 | 6.7：换成 `*_baked.png` |
| 眼睛周围一圈白或灰 | 半透明壳导成了不透明 | 6.7：Alpha 设 0 |
| 头发像秃了一块，发根下沉 | 头发的根骨被当成物理刚体 | 6.5：根骨改成 Bone 模式 |
| 第一帧头发被甩飞 | 导入 VMD 时 Margin 为 0 | Margin 填 30 |
| 上臂皮肤乱飘 | 布料物理的正则认不出下划线形式的 Biped 骨 | 6.5：Body bone regex 改成 `^Bip0\d\d` |
| 弯膝盖时膝盖一圈有接缝 | 膝盖辅助骨挂在大腿上 | 6.5：给它加约 0.5 的付与 |

## 8. 自动流程对照

| 手工步骤 | 自动脚本 / 函数 |
|---|---|
| 1 解包 | `scripts\vindictus\export_model.ps1`（`list_models.py` 解析包路径 + UE Viewer 命令行）；key 用 `find_aes_key.py` |
| 2.1–2.4 导入、转正、合并 | `build_blend.py`：`import_psk()`、合并循环、`align_secondary_hierarchies()`；另一版骨架的部件由 `repose_part()` 处理 |
| 2.5 切旧头 | `build_blend.py`：`cut_legacy_head()`（保护 `inner`） |
| 2.6 材质 | `build_blend.py`：`setup_material()`、`build_eye()` |
| 2.7 收拢贴图 | `build_blend.py` 末尾：复制到 `textures\`，改相对路径 |
| 3 脖子 | `scripts\vindictus\fix_basebody_neck.py`：`fit_face_to_body()`、`match_bib_tone()` |
| 4 并骨架 | 无（自动构建的素体仍是两副骨架） |
| 5 XPS | `blender2xps\tools\batch_export_blends.py --scale 0.01 --bake AUTO` |
| 6.10 PMX（从 XPS） | `scripts\vindictus\export_pmx.py`：转换 + 両目 + DNA 表情 + 胸部 / 头发物理；脸的 DNA 用 `metahuman_dna.py extract` 取 |
| 6 PMX（从 blend） | Vindictus 没有；星刃 Eve 的 blend 用 `scripts\stellarblade\export_pmx_blender.py`（复用 ROE 的 worker：`resolve_roe_slots`、`plan_joint_helper_moves`、`apose_arms`、`add_both_eyes_bone`、`hide_transparent_materials`、`verify_grant_order` …，外加 `add_breast_physics()`、`anchor_hub_roots()`、`fix_pmx_materials()`） |
| 归档到 E 盘 | `scripts\archive\archive_exports.py vindictus` |

## 9. 本教程是怎么验证的

2026-09-26 用 Blender 3.6.15 在后台按 GUI 调用的同一批操作符，把第 2、4、5、6 节的关键步骤重放了一遍。
输入是命令行导出的三个 PSK。结果：

- **2.1 导入**：脸 658 骨 / 32,481 顶点，头发 274 / 28,492，素体 105 / 82,028。
- **2.3 素体转正**：素体朝 +X，转 −90°、平移 6.9 cm 后，`Bip001_Head` 在 `head` 正上方 1 cm。
- **2.4 合并**：合并后 1037 根骨，其中 10 根 `.001` 副本，清理后 1027 根，和自动构建一样。
  合并后头发、素体的 Armature 修改器 Object 确实变空。
- **2.5 切旧头**：删 58,483 个顶点（自动脚本删 58,484）。
- **第 3 节**：在一份没做脖子修复的自动构建（`VINDICTUS_NO_NECK_FIT=1`）上，按本节步骤用同样的操作符重放，
  再和脚本在同一份输入上的结果对比：
  - `bib` 899 个顶点、`edge` 216 个，外沿 72 个都压在旧皮下 0.05 cm；
  - 各段偏移中位数和脚本相差不到 0.06 cm，贴好部分的法线和旧身体一致；
  - 删掉 724 个旧身体的面（脚本 820）；
  - 正面、3/4、侧面、斜后、背面的贴图和白模渲染与脚本结果看不出差别。
  - 脚本直接跑在手工组装的文件上：899 个顶点、外沿 72 个、删 822 个面。
  - (g) 骨骼权重和衣服余量：`wfac` 899 个顶点（508 个为 1），Generate Data Layers 新建 85 个 Biped 组。
    然后在 Blender 里先按第 4 节把骨架并成一副，摆 30 个姿势（每只手臂三个轴各 ±45°、锁骨 ±25°、头、脊柱），
    从每块 T 恤面外 3 mm 往里打射线，数脸 / 围兜比 T 恤先被打到的次数：
    - 手工版不做 (g)：927；
    - 做了 (g)：0；
    - 脚本：2。

    再导出 XPS，用 XNALara 导入插件读回，摆弯腰 + 转头 + 抬左臂：
    - T 恤余量 4 mm：锁骨上剩一个约 25 像素的小点（这是隐藏脸以后就消失的皮肤像素，说明是脸 / 围兜穿出来的）；
    - T 恤余量 5 mm：干净，和脚本一样。

    脱掉 T 恤的静止渲染（正面、3/4、侧面、背面，贴图和白模）做 (g) 前后逐像素比较，每张最多 1 个像素超出阈值。
- **第 4 节**：挂好 16 根子骨、删掉 14 根主链骨以后，剩 1013 根骨，只有 `Root` 一个根。
  摆 Biped 的脊柱、脖子、头、锁骨，脸和头发都跟着动。
- **第 5 节**：Blender2XPS 导出校验 OK，高 1.752，XPS 标准骨名全部落在 Biped 骨上（UE 主链已删）。
- **第 6 节**：
  - 换算成米后摆姿势正常；
  - Convert to MMD 5 用改过的槽位，15/15 步成功；
  - 腿用 IK 驱动，移动 左足ＩＫ 25 cm，身体跟着动；
  - mmd_tools 按 12.5 导出，1088 根骨，回读高 21.9。
- **6.10（从 XPS 转）**：
  - 输入是 `E:\game_export\Vindictus\Fiona\xps\Fiona_BaseBody\Fiona_BaseBody.xps`，用 XNALaraMesh 默认选项导入；
  - 改 4 行槽位后 15/15 步，1099 根骨，0 个权重孔；
  - PMX 回读 1103 根骨，高 21.90，9 个材质的贴图都在；
  - 摆姿势统计见 6.10 末尾；
  - 撤销 + 重跑在有界面的 Blender 里验证过。

**没有实测的部分**（照着做时多留心）：

- UE Viewer 的 GUI 对话框：解包只实测了命令行，对话框名称取自程序内的界面字符串。
- 手工建材质：照 `build_blend.py` 的规则换算，没有逐个在 GUI 里搭过。
- 「Adjust Last Operation」取消勾选重跑：在有界面的 Blender 里用撤销 + 重跑验证过（面板做的就是这两步），没有用鼠标点过面板本身。
- 両目、胸部物理、膝盖付与、骨骼表情。
- PMX 的材质修正。
- 在 PMXEditor、MMD、XNALara XPS 里的查看。
