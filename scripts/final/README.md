# FINAL FANTASY VII REBIRTH

本目录是独立的 Unreal 提取/导入入口，不会调用或修改 Rise of Eros 的 AssetStudio
流程。

## 文件

| 文件 | 作用 |
|---|---|
| `prepare_fmodel.ps1` | 检查游戏的 `.utoc/.ucas`，建立独立输出目录，可选启动 FModel |
| `ff7rebirth_tools.py` | Blender 插件：先选 FModel 导出目录，再扫描、导入并匹配基础贴图 |

## 2026-07-26 已验证配置

| 项目 | 值 |
|---|---|
| 游戏 profile | `GAME_FinalFantasy7Rebirth = 68812805` |
| mapping | `D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap` |
| mapping SHA256 | `5675ABC2024CA3ABC98F078B000FEE1C48EC65C015D02EB1D6CC8D107FA4BFD0` |
| Tifa 模型格式 | `ActorX (psk / pskx)` |
| LOD | `First Level Only` |

这里必须使用 FModel/CUE4Parse 的 FFVII Rebirth 专用 profile，不能用通用
`UE4.26` 或 `Latest` 替代。

## 2026-07-26 FF7 Rebirth Tools v0.3.0

- 材质现在优先读取 FModel MaterialInstance JSON 的 `Textures` 引用，再按完整
  `/Game/...` 包路径定位 PNG；只有无 JSON 时才退回文件名启发式。
- 旧版把 `PC0002_00_Arms_O` 中的 `Arms` 子串误识别为打包通道标记 `ARM`，
  错把 G/B 接到 Roughness/Metallic。现在 `ARM/RMA/MRA/ORM` 必须是完整尾部词元，
  `Arms_O` 不再被当作 ORM。
- Tifa 的 `Eye` 使用 `Common_Eye_Player_C` 作为共享巩膜、
  `PC0002_00_Eye_C` 作为虹膜，在 `VTXW0000` UV 中以中心 `(0.5, 0.5)` 做
  `0.18–0.22` 半径的平滑径向混合；这只是 Blender 预览近似，不包含完整角膜 Shader。
- Unreal 法线采用 DirectX `Y-`，插件会把绿色通道转换为 `1-G` 后再交给 Blender。
  皮肤/头脸/手臂/眼睛/口腔的 Normal Strength 为 `0.35`，其他材质默认 `0.7`。
- 扫描时优先选择文件头以 `ACTRHEAD` 开始的有效 PSKX/PSK。替换导入采用事务顺序：
  新模型的法线、缩放和材质后处理全部成功后才删除旧批次，任一步失败都回滚新对象
  并保留旧模型。
- `io_scene_psk_psa 5.0.6` 带入的 PSK 自定义分裂法线与 `30° Auto Smooth` 会让
  高密度表面呈现皱纸/金属三角反光。默认勾选“PSK 导入后修复三角反光”；旧场景可
  点击“修复 PSK 三角反光”。
- “导入并绑定同骨架配件”会先检查实际权重骨名与 local rest/bind 矩阵，再自动绑定
  主体骨架、删除重复配件骨架、准备材质；已用 Tifa `WE0002_00` 实测通过。
- Blender 3.6 使用官方
  [io_scene_psk_psa 5.0.6](https://github.com/DarklightGames/io_scene_psk_psa/releases/tag/5.0.6)。

## 最短流程

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
.\prepare_fmodel.ps1
```

脚本默认读取：

`D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH`

并建立：

```text
D:\ff7rebirth_exports\
├─ fmodel_exports\   # FModel 的 Model Export Directory
├─ blender\          # 自己保存的 .blend
└─ xps\              # 后续转换产物，避免与原始导出混放
```

如果还没有上表中的 mapping，只需生成一次：

1. UE4SS 的 `UE4SS-settings.ini` 中将全部 `Hook...` 设置为 `0`。
2. `Mods\mods.txt` 只启用 `Keybinds : 1`。
3. 从 Steam 启动游戏，进入可响应键盘的界面后按 `Ctrl+Numpad6`。
4. `UE4SS.log` 出现 `Mappings Generation Completed Successfully!` 后关闭游戏。
5. 将 `ue4ss\--c838a8ac.usmap` 复制到上表的稳定路径并核对 SHA256。

启动游戏是因为 `DumpUSMAP()` 要读取游戏进程中的 Unreal 反射信息；mapping 生成后，
FModel 离线读取 IoStore，游戏无需继续运行。

然后在 FModel 中：

1. Directory Selector 选择游戏根目录，不要选择 `End\Content\Paks`。
2. 选择专用 `Final Fantasy VII Rebirth` profile，并加载上表的 mapping。
3. **Settings > Models** 选择 `ActorX (psk / pskx)` 和
   `First Level Only`。
4. 进入
   `End/Content/Character/Player/PC0002_00_Tifa_Standard/Model`。
5. 双击 `PC0002_00.uasset`，在 3D Viewer 的 Outliner 中右键模型并
   **Save Model**。

本次 FModel 虚拟 IoStore 索引核对到 `109` 个 Player 变体目录、`12` 个名称含
Tifa 的直接变体目录。`PC0002_00_Tifa_Standard` 共 `65` 个 packages
（Material `13` / Model `7` / Texture `45`）；其中 Model 子目录的 `7` 项里，
`PC0002_00` 和 `PC0002_00_Condition` 是两个 SkeletalMesh。已成功生成：

```text
D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Player\PC0002_00_Tifa_Standard\Model\PC0002_00.pskx
```

文件大小 `20,480,844` bytes，结构包含 `188,921` 顶点、`226,086` 三角面、
`12` 材质、`536` 骨骼、`480,494` 权重记录和 `2` 组额外 UV。

当前 FModel/CUE4Parse 的 glTF 路径会把 tangent 的整个 `Vector4`（包括手性 W）一起
归一化，随后被 SharpGLTF 以 `Invalid Tangent` 拒绝。ActorX 不写 glTF 的
`VEC4 TANGENT`，因此是本次实测可用的 workaround。日志中仍可能出现 FFVII Rebirth
tangent bulk stride 与精度标志不一致的 reader 错误，但本次 FModel 保留了可用网格并
成功写出完整 PSKX。

Blender 3.6 安装 `ff7rebirth_tools.py` 和兼容版
`io_scene_psk_psa 5.0.6` 后，在 3D 视口按 `N`，打开 **FF7RB** 页签：

1. 先选择 `D:\ff7rebirth_exports\fmodel_exports\`；
2. 点击“扫描导出目录”；
3. 核对扫描结果为有效的 `PC0002_00.pskx`；
4. 保持默认勾选“PSK 导入后修复三角反光”，点击“导入选中模型”；
5. 首次修正旧材质时勾选“覆盖已有基础贴图”，点击一次“重新匹配基础贴图”，
   确认腿部、眼睛与法线方向正确后关闭该勾选项；
6. 旧场景仍有皱纸/金属三角反光时，点击“修复 PSK 三角反光”。

JSON 决定“哪张图属于哪个参数”：Base Color 使用 `sRGB`，Normal、Roughness、
Metallic、ORM 和 Opacity 使用 `Non-Color`。保留 FModel 的完整目录层级很重要；
多个 Unreal 包存在同名图片且完整路径无法区分时，插件会拒绝弱匹配。

Normal 节点会执行 DirectX 到 OpenGL 的绿通道转换：R/B 保持，G 改为 `1-G`。
`skin/head/arms/eye/mouth` 材质的 Strength 为 `0.35`，其他默认 `0.7`。三角反光
修复则把 PSK Mesh 的面设为 Smooth 并关闭 Auto Smooth；它解决的是分裂法线问题，
与 Normal 贴图绿通道转换是两件不同的事。

## Tifa 默认手套

主体 `PC0002_00` 没有完整掌部不是导入器丢顶点；标准皮手套是独立 Weapon
SkeletalMesh。FModel 精确搜索：

```text
WE0002_00_Tifa_LeatherGlove
```

模型虚拟路径：

```text
End/Content/Character/Weapon/WE0002_00_Tifa_LeatherGlove/Model/WE0002_00.uasset
```

打开后在 3D Viewer Outliner 右键 **Save Model**，本机已输出：

```text
D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk
```

同时保留 `WE0002_00_Body/Alpha/Materia` 的 Material JSON 与
`WE0002_00_Body_A/C/Mg/Mr/N/O` 图片。

在 Blender 中：

1. 先用 FF7RB 的“导入选中模型”导入 Tifa 主体。
2. 在 **“4. 独立配件/武器”** 的“配件/武器模型”选择 `WE0002_00.psk`。
3. 保持“导入后匹配基础贴图”和“PSK 导入后修复三角反光”开启，点击
   **“导入并绑定同骨架配件”**。
4. 插件会自动检查所有实际带权 vertex group 的同名主体骨骼，并比较同名骨骼的
   `matrix_local`（最大元素差容差 `0.01`）。通过后自动改绑主体骨架、删除重复骨架，
   并把手套加入主体当前批次；失败则回滚本次配件对象，主体不变。
5. 在主体骨架 Pose Mode 轻微旋转腕/手指测试并撤销，确认随动后另存 `.blend`。

无需修改主体“模型文件”或关闭“替换上次导入”。共骨架绑定复用 PSK 已有权重，不会
重新计算自动权重。`WE0002_00.psk` 已在 v0.3.0 实测完成自动验证、绑定、重复骨架
清理、材质准备与三角反光修复。

详细的 FModel 设置、PSK 依赖与限制见
[`docs/final-fantasy-vii-rebirth-extraction.md`](../../docs/final-fantasy-vii-rebirth-extraction.md)。
