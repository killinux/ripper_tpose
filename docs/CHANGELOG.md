# 更新日志

本文件记录会改变提取结果、Blender 操作或导出行为的更新，最新内容放在最前面。

今后每次功能更新必须同时补充一条记录，并至少写明：

1. 日期与版本；
2. 新增或修复内容；
3. 用户如何操作；
4. 实现原理与兼容性；
5. 已执行的验证。

日期按项目当前使用时区 `Asia/Shanghai` 记录。

---

## 2026-07-26 — FF7 Rebirth Tools v0.3.0 / 材质、法线与同骨架配件

### 新增与修正

#### 1. 材质改为优先读取 FModel JSON

- 插件会同时扫描“FModel 导出目录”和“贴图目录”中的 MaterialInstance JSON 与图片，
  读取 JSON 顶层 `Textures` 表中的 Unreal 参数名和资源引用。
- `Color/BaseColor/PM_Diffuse`、`Normal`、`Roughness`、`Metallic`、
  `ORM`、`Coverage/Opacity` 等参数先按语义解析，再按 `/Game/...` 包路径在保留层级的
  FModel 输出中定位同名 PNG；只有没有可用 JSON 时才退回文件名启发式匹配。
- `/Game/Renderer/Texture/...` 下的白色、黑色等渲染器占位贴图不会替代真正的角色贴图。
  Base Color 以 `sRGB` 读取，Normal、Roughness、Metallic、ORM、Opacity 以
  `Non-Color` 读取。
- 旧版把 `PC0002_00_Arms_O` 误判为 ORM，是因为在 `Arms` 中做子串匹配时命中了
  三字母通道标记 `ARM`，随后错误地把该图的 G/B 通道接到 Roughness/Metallic。
  现在 `ARM/RMA/MRA/ORM` 只有作为完整尾部词元时才算打包通道图；`Arms_O` 不再命中。
  无 JSON 的兼容回退仍识别 FF7 的 `Mg` 为 Roughness、`Mr` 为 Metallic。
- 勾选“覆盖已有基础贴图”再点击“重新匹配基础贴图”，会清理本插件旧版本生成的
  `FF7RB_` 节点后重新建立连接；不会以同名弱匹配在多个 Unreal 包之间随意选图。

#### 2. DirectX 法线转换与分级强度

- Unreal 的切线空间法线采用 DirectX `Y-`，Blender 的 Normal Map 节点按 OpenGL
  `Y+` 解释。插件现在把 Normal 图设为 `Non-Color`，保留 R/B，只对绿色通道执行
  `G' = 1 - G`，再组合后送入 Normal Map；不再把凹凸方向反着显示。
- 皮肤与眼睛需要比衣物更柔和的微表面：材质名含
  `skin/head/arms/eye/mouth` 时 Normal Strength 为 `0.35`，其他材质默认 `0.7`。
  这些值只控制 Blender 预览节点，不修改原始 PNG。

#### 3. Tifa 眼睛改为共享巩膜与角色虹膜分层

- `Eye` 材质不再把 `PC0002_00_Eye_C` 当作整颗眼球的 Base Color。该图只包含
  Tifa 的虹膜颜色，直接铺满会把眼白染暗或染红。
- JSON 的 `Color` 解析为共享巩膜 `Common_Eye_Player_C`，`IrisColor` 解析为
  `PC0002_00_Eye_C`；眼睛法线继续按 JSON 的 `Normal` 引用解析。
- Blender 节点使用 `VTXW0000` UV，以 `(0.5, 0.5)` 为虹膜中心计算二维距离：
  半径 `0.18` 内使用虹膜，`0.22` 外使用巩膜，中间用 `EASE` 色带平滑过渡。
  这能恢复可用的眼白与虹膜预览，但仍不是 Unreal 的角膜折射、湿润层和运行时眼球
  Shader 的完整复刻。

#### 4. PSK/PSKX 有效性、事务导入与三角反光修复

- 扫描时先检查 `.psk/.pskx` 至少 `32` bytes 且文件头以 `ACTRHEAD` 开始；
  结构可识别的 PSKX/PSK 优先于 FFVII Rebirth 当前可能含非法 tangent 的 glTF。
  手动指定的“模型文件”仍按用户选择导入，不会被扫描器擅自改写。
- “替换上次导入”不再在调用导入器前删除旧批次。导入器返回成功且创建对象后，还会
  先完成法线、缩放、材质等后处理；全部成功才删除旧批次并提交新批次。异常、取消、
  零对象或后处理失败都会清理本次残留对象，原模型保留。
- Blender 3.6 使用官方
  [DarklightGames/io_scene_psk_psa 5.0.6](https://github.com/DarklightGames/io_scene_psk_psa/releases/tag/5.0.6)。
  操作符检测兼容 Blender 动态 `bpy.ops` 命名空间在未注册时抛出的 `KeyError`，并支持
  `import_scene.psk`；其他版本若提供新版 `psk.import_file` 也可使用。
- `io_scene_psk_psa 5.0.6` 会把 FF7 PSK 的自定义分裂法线与 `30° Auto Smooth`
  一起带入 Blender；在这些高密度网格上几乎每个三角形都会形成可见明暗边界，因此
  即使贴图连接正确，皮肤和衣物仍会像皱纸或金属三角片。
- v0.3.0 默认勾选“PSK 导入后修复三角反光”：仅对 PSK/PSKX 新建网格把所有面设为
  Smooth，并关闭不兼容的 Auto Smooth，让 Blender 使用连续的平滑顶点法线；不改
  顶点、面、UV、骨架或权重。旧场景可在“基础材质”区点击“修复 PSK 三角反光”。

#### 5. 一键导入并绑定 Tifa 标准服装默认手套

- `PC0002_00` 主体只保留与手套衔接的手指段；掌部和手套不是权重丢失，而是独立的
  Weapon SkeletalMesh。默认皮手套的精确 FModel 虚拟路径是：

  ```text
  End/Content/Character/Weapon/WE0002_00_Tifa_LeatherGlove/Model/WE0002_00.uasset
  ```

- 在 FModel 精确搜索 `WE0002_00_Tifa_LeatherGlove`，打开 `Model/WE0002_00`，
  在 3D Viewer Outliner 右键 **Save Model**。本次实际输出为：

  ```text
  D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk
  ```

- 同时保留 `WE0002_00_Body`、`WE0002_00_Alpha`、`WE0002_00_Materia`
  Material JSON，以及 `WE0002_00_Body_A/C/Mg/Mr/N/O` 图片和原目录层级。
- v0.3.0 的 **“导入并绑定同骨架配件”** 会导入所选 PSK/PSKX，并逐个检查配件网格：
  每个实际带权 vertex group 必须在当前主体骨架中有同名骨骼，公共骨骼的
  `matrix_local` 最大元素差必须不超过 `0.01`。
- 验证通过后，按钮保留配件原权重与相对变换，把 Armature modifier 和 Parent 改为
  当前主体骨架，删除配件导入产生的重复骨架，将配件加入主体当前批次，并按当前选项
  自动修复三角反光、准备材质。任一网格不兼容时会回滚本次全部配件对象，主体不变。

### 如何操作

1. 主体按既有流程导出 `PC0002_00.pskx`。在 FF7RB 导入区保持默认勾选
   “PSK 导入后修复三角反光”，再点击“导入选中模型”。
2. 如果是 v0.3.0 以前保存的旧场景，点击“修复 PSK 三角反光”；该按钮只处理当前
   FF7RB 批次网格，无需重新导入。
3. 在材质目录层级完整的前提下，勾选“覆盖已有基础贴图”，点击一次
   “重新匹配基础贴图”；确认腿部不再使用 `Arms_O` 的 G/B 通道，眼睛同时出现眼白和
   居中的棕色虹膜、法线凹凸方向正确后，关闭该勾选项。
4. 按上述 Weapon 路径从 FModel 保存 `WE0002_00` 及其 Material/Texture。
5. 在 **“4. 独立配件/武器”** 的“配件/武器模型”选择 `WE0002_00.psk`，点击
   **“导入并绑定同骨架配件”**。无需修改“模型文件”，也无需关闭“替换上次导入”。
6. 成功提示应说明配件网格已绑定到主体骨架；在 Pose Mode 轻微旋转腕/手指骨确认
   手套随主体变形并立即撤销，然后另存 `.blend`。

### 实现原理与兼容性

- JSON 是材质实例对实际纹理包的显式引用，优先级高于相似文件名；保留 FModel
  目录层级可以消除不同 Unreal 包中同名贴图的歧义。
- 眼球分层使用 FF7 Player Eye 的两个颜色来源和 UV 径向蒙版，是 Blender 基础预览
  的确定性近似，不承诺还原游戏全部 Shader 参数。
- DirectX 绿色通道翻转解决法线方向，PSK 平滑修复解决几何分裂法线/Auto Smooth；
  两者原因不同，不能互相替代。
- PSK 主体事务导入保护 FF7RB 当前批次，不会删除 ROE 或未标记对象。配件按钮不会
  开启新的当前批次：验证成功的配件网格直接加入主体批次；失败则删除本次新建对象。
- 配件重绑只复用 PSK 已有权重，不计算自动权重。材质修复与骨架重绑仍是两条独立
  链路：材质正确不能证明骨骼兼容，骨骼兼容也不能代替材质 JSON。

### 验证

- Tifa 主体 `188,921` 顶点、`226,086` 三角面、`12` 材质、`536` 骨骼和
  `480,494` 权重记录的 PSKX 已在 Blender 3.6 导入。
- JSON 引导的无界面验证覆盖全部 `12` 个主体材质：腿部解析为
  `Legs_C/Mg/Mr/N`，眼睛解析为 `Common_Eye_Player_C` +
  `PC0002_00_Eye_C`，嘴部、头发和透明贴图也按各自 JSON 引用定位。
- 材质、扫描、法线强度、平滑修复与事务导入辅助测试共 `11` 项通过；其中覆盖
  导入器成功但材质后处理失败时回滚新对象并保留旧批次。强制重匹配
  可重复执行，不会不断叠加旧 `FF7RB_` 节点。
- 已验证新法线节点对 DirectX Normal 执行 `G' = 1 - G`，并分别写入皮肤/眼睛
  `0.35`、其他材质 `0.7` 的 Strength；主体和手套 PSK 导入后均执行平滑修复。
- FModel 已确认保存 `WE0002_00.psk`（`1,380,580` bytes）；预览为 `229`
  骨骼、`17` sockets、`3` 材质。v0.3.0 的“导入并绑定同骨架配件”已用该文件实测
  通过：自动完成骨骼/静止姿势验证、重绑主体骨架、删除重复骨架、材质准备与三角
  反光修复。

---

## 2026-07-26 — FF7 Rebirth Tifa 导出验证 / ActorX workaround

### 新增与修正

#### 1. 固化 UE4SS mapping 生成流程

- 已验证 UE4SS `v3.0.1 Beta #0`（Git SHA `c838a8ac`）可通过内置
  Keybinds 的 `DumpUSMAP()` 生成 FFVII Rebirth mapping。
- 稳定配置是将 `UE4SS-settings.ini` 中所有 `Hook...` 项设为 `0`，
  `Mods\mods.txt` 中关闭其他 Mod，只保留 `Keybinds : 1`。
- 游戏进入可响应键盘的界面后按 `Ctrl+Numpad6`；日志确认：
  `Mappings Generation Completed Successfully!`。
- UE4SS 临时输出 `--c838a8ac.usmap` 已复制为：

  ```text
  D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap
  ```

- 文件大小为 `2,205,102` bytes，源文件与稳定副本的 SHA256 均为：

  ```text
  5675ABC2024CA3ABC98F078B000FEE1C48EC65C015D02EB1D6CC8D107FA4BFD0
  ```

启动游戏只用于让 UE4SS 从运行时 Unreal 反射数据生成 mapping。生成并核对哈希后，
FModel 离线读取 `.pak/.utoc/.ucas`，不需要游戏继续运行；后续游戏 Fatal Error
不会使已经完整写出的 mapping 失效。

#### 2. 确认 FModel 必须使用 FFVII Rebirth 专用 profile

- 本次使用 FModel `4.4.4.0`
  (`b2708293f64ffc858b4901ff785a9078b99c67f4`)。
- Directory Selector 选择游戏根目录，不选 `End\Content\Paks`。
- 手动 profile 使用
  `GAME_FinalFantasy7Rebirth = 68812805`，不能以通用
  `GAME_UE4_26` 或 `GAME_UE4_LATEST` 代替。
- FModel 加载上述稳定 mapping 后，日志同时确认
  `GAME_FinalFantasy7Rebirth` 与
  `Mappings pulled from 'FF7Rebirth-4.26-20260726-c838a8ac.usmap'`。

#### 3. 核对 Player/Tifa 目录和标准版模型

- FModel 虚拟 IoStore 索引的 `End/Content/Character/Player` 下确认有 `109`
  个角色/服装变体目录；这些数字不是物理导出目录数。
- 其中有 `12` 个名称含 Tifa 的直接变体目录：`10` 个 PC0002 变体，另有
  `PC0099_03_Toad_Tifa` 和 `PC7002_00_Tifa_StandardCFEnd2`。
- 标准版是 `PC0002_00_Tifa_Standard`，共 `65` 个 packages：
  Material `13`、Model `7`、Texture `45`。
- Model 子目录的 `7` 项中，`Model/PC0002_00` 和
  `Model/PC0002_00_Condition` 是两个 SkeletalMesh。
- 标准主体应打开 `PC0002_00.uasset`，而不是优先选择 Condition 变体。

#### 4. 记录 glTF `Invalid Tangent` 根因并改用 ActorX

- reader 的
  `Read incorrect amount of tangent bytes ... behind: -217552`
  来自 FFVII Rebirth tangent bulk 的 stride 与精度标志不一致。
  `217,552 = 27,194 × 8`：`27,194` 个顶点的 header 声明每顶点 `8` 字节，
  解析器却按高精度每顶点 `16` 字节读取。
- glTF 保存阶段的
  `Accessor[2] TANGENT[18]: Invalid Tangent`
  是另一个独立问题：CUE4Parse 对整个 tangent `Vector4` 做归一化，破坏了 glTF
  要求的 XYZ 单位长度和手性 `W = ±1`，随后被 SharpGLTF 1.0.6 Strict 校验拒绝。
- 当前 UI workaround：
  **Settings > Models > Mesh Format > ActorX (psk / pskx)**，
  **Level Of Detail Format > First Level Only**；再打开 `PC0002_00.uasset`，
  在 3D Viewer 的 Outliner 中右键模型并选择 **Save Model**。
- ActorX 写位置、法线、UV、骨架和权重，不经过 glTF 的 `VEC4 TANGENT`
  校验。`First Level Only` 控制输出 LOD 数量，但不是 reader 修复；日志仍可能出现
  tangent bytes 错误。
- 长期修复方向是：FFVII Rebirth reader 按 tangent `itemSize` 选择 8/16 字节精度；
  glTF 只归一化 XYZ、单独保持 W 为 `±1`，或使用 SharpGLTF
  `ValidationMode.TryFix`。不建议只用 `ValidationMode.Skip`。

### 实际操作

1. UE4SS 关闭全部 Hook，只启用 Keybinds。
2. 启动游戏，按 `Ctrl+Numpad6`，等待 mapping 成功日志后关闭游戏。
3. 固定 mapping 文件名并核对 SHA256。
4. 在 FModel 为游戏根目录选择专用 `Final Fantasy VII Rebirth` profile，
   加载稳定 mapping。
5. **Settings > Models** 选择 ActorX、First Level Only、PNG，并保持目录层级。
6. 进入
   `End/Content/Character/Player/PC0002_00_Tifa_Standard/Model`，
   双击 `PC0002_00.uasset`。
7. 在 3D Viewer Outliner 右键模型，点击 **Save Model**。
8. Blender 3.6 使用 `io_scene_psk_psa 5.0.6` 导入生成的 `.pskx`；
   FF7RB 插件扫描结果不正确时手动指定该文件。

### 验证

- FModel 日志于 `2026-07-26 14:54:37` 确认成功保存：

  ```text
  D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Player\PC0002_00_Tifa_Standard\Model\PC0002_00.pskx
  ```

- 文件大小 `20,480,844` bytes，SHA256：
  `568B7280E0CB556BB7280CE18E67786257E19E0471E1221CF124C6D625DA1980`。
- PSKX chunk 边界完整，统计为 `188,921` 顶点、`226,086` 三角面、`12`
  材质、`536` 骨骼、`480,494` 权重记录和 `2` 组额外 UV。
- ActorX 导出过程不再出现 SharpGLTF `Invalid Tangent`；reader 的 tangent bytes
  日志仍存在，但没有阻止本次完整 PSKX 写出。

---

## 2026-07-25 — FF7 Rebirth Tools v0.1.0 / 脚本按游戏分目录

### 新增与调整

#### 1. 新增独立的 FFVII Rebirth 流程

- 新建 `scripts\final\prepare_fmodel.ps1`。
- 已按本机安装验证游戏资源位于 `End\Content\Paks`，包含成对的
  `.utoc/.ucas`，属于 Unreal IoStore，不能使用 ROE 的 AssetStudioModCLI。
- 脚本检查 archive 配对，建立
  `D:\ff7rebirth_exports\fmodel_exports/blender/xps`，并可启动用户已有的 FModel。
- 提取阶段不内置 AES key、mapping 或猜测的固定 UE 版本；这些内容与用户合法拥有的
  游戏构建相关。

#### 2. 新增 FF7 Rebirth Blender 插件

- 新建 `scripts\final\ff7rebirth_tools.py`，与 ROE 插件完全分离。
- Blender 侧边栏新增 **FF7RB** 页签，第一步就是选择 FModel 导出目录。
- 可递归扫描 `.glb/.gltf/.fbx/.pskx/.psk/.obj`，优先 glTF/FBX 与 LOD0。
- PSK 同时兼容新版 `psk.import_file` 和旧版 `import_scene.psk` 操作符。
- 根据材质名/贴图名匹配 Base Color、Normal、Roughness、ORM、Opacity；默认不覆盖
  已有 Base Color 连接。
- “替换上次导入”只处理本插件标记的上一个导入批次，不删除 ROE 或用户其他对象。

#### 3. ROE 脚本迁入专属目录并保留旧入口

- ROE 正式源码迁到 `scripts\riseoferos\`：
  `extract_character.ps1`、`convert_fbx.py`、`roe_xps_addon.py`、
  `blender_face_materials.py`。
- `scripts\extract_character.ps1` 保留为兼容转发入口，原命令继续可用。
- 文档链接已更新；现有 Blender 用户插件目录中的 ROE 插件不受仓库整理影响。

### 如何操作

#### FFVII Rebirth

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
.\prepare_fmodel.ps1
```

1. 在 FModel 的 Directory Selector 选择 FFVII Rebirth 游戏根目录。
2. 将 Model Export Directory 设为
   `D:\ff7rebirth_exports\fmodel_exports`，优先导出 glTF/LOD0/PNG。
3. Blender 3.6 安装 `scripts\final\ff7rebirth_tools.py`。
4. `N` → **FF7RB** → 选择 FModel 导出目录 → 扫描 → 导入。
5. PSK/PSKX 需要兼容 Blender 3.6 的 `io_scene_psk_psa 5.0.6`；glTF 不需要。

#### Rise of Eros

新路径：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
.\extract_character.ps1 a08 -ExportTextures
```

原来的 `scripts\extract_character.ps1 ...` 仍可使用。

### 实现原理与兼容性

- 两套流程只共享文档入口，不共享引擎提取核心或 Blender Scene 属性。
- FFVII 插件只处理 FModel 的导出物，不直接访问 `.utoc/.ucas`。
- glTF/FBX 使用 Blender 内置导入器；PSK/PSKX 调用已安装的第三方导入器。
- 基础材质匹配使用规范化文件名词段、字符串相似度和贴图角色后缀评分；复杂 Unreal
  皮肤、眼球、头发 Shader 不会伪装成已经完整还原，仍需人工校正。
- ROE 的材质槽缓存、a07 腿部与 a08 眼睛修复代码没有改变，只调整了仓库路径。

### 验证

- 本机 FFVII Rebirth 安装目录检查到 `global.utoc/global.ucas` 及多组
  `pakchunk*.utoc/.ucas`。
- `prepare_fmodel.ps1` 通过 PowerShell 语法检查及隔离临时目录运行测试。
- `ff7rebirth_tools.py` 通过 Python 语法编译与 Blender 3.6 注册/注销测试。
- FF7RB 的贴图角色识别、LOD0 选择评分与 Principled Base Color 节点连接测试通过。
- 已安装到本机 Blender 3.6 用户插件目录并保存启用状态；当时 MCP 端口未监听，因此
  已打开的旧 Blender 窗口需要重启后显示 **FF7RB** 页签。
- ROE 正式脚本内容迁移后进行哈希/语法检查；旧 PowerShell 入口转发参数测试通过。

---

## 2026-07-25 — ROE XPS Tools v1.1.3

### 新增与修复

#### 1. 新增 Universal / ROE 双工作流

- “自动识别”根据对象名判断是否为 Rise of Eros 模型。
- “通用模型”保留任意 FBX/OBJ/glTF 的现有材质和关联骨架，可直接转 XPS。
- “ROE 增强”继续处理脸、眼睛、睫毛、眉毛、皮肤和多图集身体材质。
- 处理范围支持“最新导入”“所选网格”“所有可见”，并可采用其他插件导入的所选模型。
- 新增模型诊断、当前材质槽用途/贴图覆盖、头部选中面人工分类及高级眼睛/睫毛参数。

#### 2. 恢复原始材质分区，修复 a07 腿部贴图

- 导入时缓存原始材质槽名称和每个面的材质索引。
- 旧场景已经被压成单一材质槽时，可从“模型来源”指定的原始 FBX 临时恢复分区。
- a07 的身体恢复为四槽分区：
  `pc_a07_hd_body 2 / skin / body 1 / skin2`，分别使用 `body1/body2` Albedo。
- a07 应使用：
  `D:\roe_exports\a07\pc_a07_hd (1)\FBX_GameObjects\pc_a07_hd\pc_a07_hd.fbx`。
  无后缀的 `pc_a07_hd` 本身只有一个身体材质槽，不能用于恢复。

#### 3. 新增“修复眼睛”按钮，修复 a08 眼球误判

- a08 虽然存在 `Eyeball` 顶点组，但 864 个眼球面的 Eyeball 权重不足。
- 旧算法发现语义骨骼组后会关闭几何兜底，因而把眼球全部判成脸，表现为纯白或脸色眼球。
- v1.1.3 新增原始 `eye/eyes/iris` 材质名兜底，并在 ROE 面板增加独立
  **“修复眼睛”** 按钮。
- 按钮只重建眼球材质，并修正眼球槽及误入眼球槽的面；已有有效缓存时不会恢复或扰动
  整个头部材质分区。

#### 4. 提取脚本合并 Steam 安装资源与 LocalLow 缓存

- `extract_character.ps1` 新增 `-CacheRoot`。
- 同时扫描游戏安装目录和
  `%USERPROFILE%\AppData\LocalLow\Pinkcore\Rise of Eros\AssetBundles`。
- 同名 AssetBundle 优先选择更新时间较新的文件；时间相同时优先运行时缓存，并从安装目录
  补齐公共包。
- `-List` 同时识别 `chara_armor` 与 `chara_bare` 模型包，可列出新角色、活动角色和
  只有裸模的 NPC。

### 如何操作

#### 更新插件

1. Blender 3.6 → `Edit > Preferences > Add-ons > Install...`。
2. 选择 `scripts\riseoferos\roe_xps_addon.py` 并覆盖安装。
3. 重启 Blender；仅覆盖磁盘文件不会替换当前内存中的旧代码。

#### 新提取并导入角色

```powershell
.\extract_character.ps1 a08 -ExportTextures
```

1. 在 Blender 3D 视口按 `N`，打开 **ROE** 页签。
2. 工作流选“自动识别”或“ROE 增强”，处理范围选“最新导入”。
3. “模型来源”选择包含完整材质槽的 HD FBX。若有同名 `(1)` 目录，应检查并优先选择
   带完整材质槽和贴图引用的那一份。
4. “ROE 贴图目录”选择 `D:\roe_exports\<角色>\_textures\`。
5. 点击“导入 FBX”→“检查模型”→“检查并准备材质”。
6. 若眼球仍为纯白或脸色，点击 **“修复眼睛”**。
7. 设置 XPS 输出路径后导出。

#### 修复已有场景

1. 在“模型来源”重新指定该角色的原始 FBX，在“ROE 贴图目录”指定 `_textures`。
2. 点击“检查并准备材质”，恢复丢失的身体/头部原始分区。
3. 仅眼球不对时直接点击“修复眼睛”，无需重新导入整个角色。
4. 确认效果后另存 `.blend`；按钮修改的是当前场景内存，未保存不会持久化。

### 实现原理

#### 原始材质布局缓存与恢复

- 对象属性 `roe_source_materials` 保存 FBX 原始材质槽名。
- 面属性 `roe_source_material_index` 保存每个面的原始槽索引。
- `roe_source_fbx` 保存来源 FBX。
- 旧场景缺缓存时，插件临时导入来源 FBX，按对象规范名、顶点数、面数及逐面拓扑匹配，
  复制材质布局后立即删除临时对象。
- 多图集身体根据原始 `body/skin/body1/body2` 槽名寻找对应 Albedo，不再把所有面压到
  第一个贴图。

#### 眼部识别

head 网格先按顶点连通块拆解，再组合以下信号分类：

- `Eyeball / Eyebrow / Eyelid` 骨骼权重；
- 连通块面数、中心高度和尺寸；
- UV 是否位于 `[0,1]`、UV 跨度及是否收缩到小区域；
- 原始材质名中的 `eye/eyes/iris`、`eyebrow/lash`、`tear` 等语义。

a06 没有语义骨骼组时继续使用几何兜底；a07 优先使用有效骨骼权重；a08 在权重不足时
由“眼睛材质名 + 眼球几何”兜底，因此兼容旧角色且不会把整块脸材质误认成眼球。

#### 资源目录合并

提取脚本先建立两个 AssetBundle 根目录的统一清单，再按文件名分组。每组选出更新时间
最新的候选，时间相同时用来源优先级打破平局，最后复制到角色临时 staging 目录交给
AssetStudioModCLI。

### 验证

- a06：眼球 864 面；修复按钮前后脸、睫毛、眉毛、罩层分配不变。
- a07：眼球 864 面；身体四槽面数为 `10017 / 10319 / 22679 / 2948`。
- a08 与 `a08_outfit1`：眼球从脸槽恢复为 864 面，使用
  `pc_a_nk_eye_iris_rgbx_Albedo.png`。
- a08 原始 FBX 可不先准备材质，直接点击“修复眼睛”生成完整五槽头部材质。
- 通用模型材质保留、旧场景缓存恢复、损坏缓存恢复和手工头部区域覆盖测试通过。
