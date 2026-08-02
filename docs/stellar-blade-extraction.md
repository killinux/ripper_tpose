# Stellar Blade PC 模型导出与 Eve 验证

本文记录 2026-08-01 至 2026-08-02 在本机 Steam 版 Stellar Blade 上实际完成的文件级导出。目标是
保留 SkeletalMesh、骨架和蒙皮权重，并用 Blender 3.6 组合一个 Eve 标准模型验证；
不使用 Ninja Ripper，也不修改或重新封装游戏资产。

## 1. 结论

| 项目 | 已验证值 |
|---|---|
| 游戏版本 | `1.4.1`，Steam build `19963153` |
| 安装目录 | `D:\Program Files (x86)\Steam\steamapps\common\StellarBlade` |
| 引擎/封包 | UE4 IoStore，`.utoc/.ucas/.pak` |
| AES | 不需要 |
| 首选提取器 | FModel 4.4.4 b270829，`GAME_StellarBlade` |
| mapping | `StellarBlade_1.1.0.usmap` |
| mapping SHA256 | `40A8D85B0159AAA73B79E335F7D2E243B9EED028489FED274A5E624242DA9122` |
| Blender | `3.6.15` + `io_scene_psk_psa 5.0.6` + UEFormat 3.6 兼容桥 |
| 独立输出根目录 | `D:\stellarblade_exports` |

社区指南建议优先使用 FModel 的 `.uemodel`，因为 UE Viewer 的 PSK 在部分模块之间可能
产生骨骼位置差异或颈缝。最终验证使用 FModel ActorX 身体、FModel UEFormat Face_003，
以及专用 UE Viewer 导出的主发型和马尾。Face_003 保留了全部 53 个源 Morph；第一次
PSK Face_001 仅是定位探针，不再作为最终头部。不要把普通官方 UE Viewer 当成这个专用构建：普通
版本在当前 IoStore 中只能看到约 7,275 个文件，专用构建能看到 228,867 个。

参考：

- [Stellar Blade Modding Team：Extracting game files](https://github.com/Stellar-Blade-Modding-Team/Stellar-Blade-Modding-Guide/wiki/Extracting-game-files)
- [Stellar Blade Modding Team：Models](https://github.com/Stellar-Blade-Modding-Team/Stellar-Blade-Modding-Guide/wiki/Models)
- [官方 UE Viewer 项目页](https://www.gildor.org/en/projects/umodel)
- [官方 UE Viewer 源码](https://github.com/gildor2/UEViewer)

## 2. 操作前准备

1. 关闭游戏、FModel 和 UE Viewer。
2. 输出目录放在游戏安装目录之外，例如 `D:\stellarblade_exports`。
3. 临时把 `SB\Content\Paks\~mods` 中的 Mod 移到安全目录，避免 Mod 的同路径包覆盖
   原版资产。完成后必须原样放回。
4. 不要改动 `.pak/.utoc/.ucas` 的基本文件名；IoStore 工具依赖同名文件配对。
5. mapping 使用社区仓库中的
   [`StellarBlade_1.1.0.usmap`](https://github.com/Stellar-Blade-Modding-Team/Stellar-Blade-Modding-Guide/blob/main/StellarBlade_1.1.0.usmap)。
   文件名虽然是 1.1.0，但本机 1.4.1 的身体和脸已经实际解析、预览和导出成功。版本
   更新后仍应重新验证，不要仅凭文件名假定永久兼容。

本机安装了 `EveOriginalProportions-30-2-1-1750283806`，包含 Barefoot、Barefoot with
Pubic、High Heels、High Heels with Pubic 四套选项。它覆盖的是
`CH_P_EVE_InnerSuit`，不是本次验证的 `CH_P_EVE_01_Body`。验证期间已临时隔离到
`D:\stellarblade_exports\_probe_stash`；启动游戏前应恢复到原 `~mods` 目录。

## 3. FModel 手动导出

### 3.1 配置

1. 启动 `E:\tools\FModel\FModel.exe`。
2. 添加游戏存档目录：

   ```text
   D:\Program Files (x86)\Steam\steamapps\common\StellarBlade\SB\Content\Paks
   ```

3. 游戏 profile 选择精确的 `Stellar Blade / GAME_StellarBlade`，不要只用通用 Latest。
4. 开启 local mapping，选择下载的 `StellarBlade_1.1.0.usmap`。
5. Models 设置：

   | 设置 | 值 |
   |---|---|
   | Mesh Format | `ActorX (psk / pskx)`，或优先 `.uemodel` |
   | LOD | `First Level Only` |
   | Texture | PNG |
   | Morph targets | 需要时开启 |
   | Bone sockets | PSK 选择 **Don't Export Bone Sockets** |

6. 输出设为 `D:\stellarblade_exports\fmodel_exports`。
7. 加载 `pakchunk0-WindowsNoEditor.utoc`。无 AES key。

PSK 若把 sockets 作为 bones 导出，会在 Blender 中出现大量并非变形骨的节点。当前首次
验证文件已经成功导入，但手动重导时应使用 **Don't Export Bone Sockets**，骨架更干净。

### 3.2 Eve 标准组件

完整路径另见 [Eve 资产清单](stellar-blade-eve-assets.txt)。FModel 搜索并右键
`Save Model`：

| 组件 | Unreal 包路径 |
|---|---|
| 身体/标准服装 | `SB/Content/Art/Character/PC/CH_P_EVE_01/CH_P_EVE_01_Body.uasset` |
| 身体 Skeleton | `SB/Content/Art/Character/PC/CH_P_EVE_01/CH_P_EVE_01_Skeleton.uasset` |
| 完整脸（最终验证） | `SB/Content/Art/Character/PC/CH_P_EVE_Head/CH_P_EVE_Face_003.uasset` |
| 牙齿 | `SB/Content/Art/Character/PC/CH_P_EVE_Head/CH_P_EVE_Teeth_001.uasset` |
| 默认主发型 | `SB/Content/Art/Character/PC/00_HR/EVE_HR_01/EVE_HR_01.uasset` |
| 默认长马尾 | `SB/Content/Art/Character/PC/00_HR/EVE_HR_01/EVE_HR_01_Tail.uasset` |
| 默认短马尾 | `SB/Content/Art/Character/PC/00_HR/EVE_HR_01/EVE_HR_01_ShortTail.uasset` |

本次 FModel 已成功导出身体 PSK 和 Face_003 UEFormat；对牙齿、头发执行 Extract 时，FModel 4.4.4 的
`CUE4ParseViewModel.Extract` 抛出 `System.NullReferenceException`。这不是 mapping 全面
失效：同一配置已解析出身体 203 个原始骨，并写出有效 PSK。遇到这一错误时先单独重启
FModel；若仍复现，只对失败组件使用下一节的专用 UE Viewer。

## 4. 专用 UE Viewer 补导头发

社区提取指南链接的文件为 `umodel_stellar_blade_v6.zip`；本次下载文件 SHA256：

```text
61A641D3EC214C2DBA9805364D31A64837866F34298B5CD7A58CAA229B1FD550
```

解压出的程序报告 `UE Viewer build 1579 based fix2 / 2025-07-01`。导出前保持 Mod 临时
禁用，并确认 `pakchunk0-WindowsNoEditor.pak/.utoc/.ucas` 三个基本名称完全一致。

PowerShell 示例：

```powershell
$umodel = 'C:\Tools\umodel_stellar_blade_v6.exe'
$game = 'D:\Program Files (x86)\Steam\steamapps\common\StellarBlade'
$out = 'D:\stellarblade_exports\umodel_exports'

& $umodel -export ('-path=' + $game) '-game=ue4.26' -noanim -psk -png `
  ('-out=' + $out) `
  'SB/Content/Art/Character/PC/00_HR/EVE_HR_01/EVE_HR_01'

& $umodel -export ('-path=' + $game) '-game=ue4.26' -noanim -psk -png `
  ('-out=' + $out) `
  'SB/Content/Art/Character/PC/00_HR/EVE_HR_01/EVE_HR_01_Tail'
```

扫描游戏根目录时出现 CEF locales `.pak has an unknown format` 可以忽略；它们是嵌入式
浏览器资源，不是 UE 游戏资产。成功标志是日志出现 `Found 228867 game files`，并为两个
包分别输出 `EVE_HR_01.psk` 和 `EVE_HR_01_Tail.psk`。

## 5. Blender 3.6 组合验证

Blender 3.6 安装并启用
[`io_scene_psk_psa 5.0.6`](https://github.com/DarklightGames/io_scene_psk_psa/releases/tag/5.0.6)。
Face_003 使用[官方 UEFormat](https://github.com/h4lfheart/UEFormat)源码读取器；由于当前插件
声明 Blender 4.x，需要先在 UEFormat 源码根目录应用
[`ueformat-blender36.patch`](../scripts/stellarblade/ueformat-blender36.patch)。补丁只给 Blender 4
骨骼调色 API 加版本判断，不修改模型解析、骨架、蒙皮或 Morph 数据。然后执行
[`scripts/stellarblade/validate_eve.py`](../scripts/stellarblade/validate_eve.py)；完整命令见该目录的
[README](../scripts/stellarblade/README.md)。

Eve 是模块化角色，四个组件并非都使用相同局部原点：

- 身体 PSK 和 Face_003 UEFormat 来自 FModel，按相同厘米尺度进入角色空间；
- 主发型从局部原点移动到身体 `SC_Hair` 插槽；
- 长马尾用身体和马尾骨架共有的 `Ab-TL-HairB01` 静置骨矩阵恢复位置与轴向；
- 只移动组件对象层级根节点，不烘焙顶点、不重算权重；每个原始骨架仍然保留。

不要仅把头发的网格物体和 Armature 同时平移：PSK 导入器会把网格 parent 到 Armature，
同时移动父子对象会把位移应用两次。本仓库脚本只变换层级根对象，并检查锚点误差。

## 6. 实际验证结果

| 组件 | 文件 | bytes | SHA256 |
|---|---:|---:|---|
| 身体 | `CH_P_EVE_01_Body.psk` | 4,323,400 | `01DB1B4569205B71B4178F6A59F8D811009625794962A19D29F5FC7BA0C51F3E` |
| 完整脸 | `CH_P_EVE_Face_003.uemodel` | 6,490,725 | `8D02453C142C7F9061BA5B9CB686838BA2B8F23B9C77C33056CD528E6E2390D8` |
| 主发型 | `EVE_HR_01.psk` | 1,978,140 | `66468E9FC39B54089A8B1600F9FA601EB6C1636994F9115838C8281E1E34DC20` |
| 长马尾 | `EVE_HR_01_Tail.psk` | 833,588 | `6E08591D60D82EA6BE9ED2D050A5480E58F6DEA471D97B3C40E8D1EDC2EF066B` |

身体、主发型和马尾以 `ACTRHEAD` 开始，Face_003 以 `UEFORMAT` 开始。Blender 3.6.15 实际结果：

| 指标 | 值 |
|---|---:|
| 组件/网格 | 4 / 4 |
| 原始 Armature | 4 |
| 顶点 | 107,123 |
| 面 | 133,874 |
| 骨数（各骨架合计） | 338 |
| Face_003 Shape Keys | 54（Basis + 53 个源 Morph） |
| 主发型插槽误差 | `0.0` |
| 马尾骨锚点误差 | 约 `0.000002` |

PSK 导入器对一个头发组件丢弃了 66 个退化/无效面，其余组件和 Face_003 共 133,874 个面正常进入场景。
这通常是游戏实时发片中的退化三角形，不影响本次视觉验证，但正式制作应在导出格式或
插件升级后复核。

输出：

```text
D:\stellarblade_exports\blender\Eve_Standard_validation.blend
D:\stellarblade_exports\validation\Eve_Standard_validation.png
D:\stellarblade_exports\validation\Eve_Standard_validation_face.png
D:\stellarblade_exports\validation\Eve_Standard_validation.json
```

预览连接了标准身体颜色图、头发透明图，以及完整脸、眼睛、眉毛和牙齿贴图。Eevee 不会
复现 Unreal 的角膜视差/折射，因此虹膜使用按正面 UV 校准的预览混合；原始 Face_003 几何和
53 个 Morph 不被改写。正面近景已确认脸部和双眼完整可见。

## 7. 常见问题

| 问题 | 原因与处理 |
|---|---|
| FModel `NullReferenceException` | 单独重启并只导目标包；仍失败时用专用 UE Viewer 补导该组件 |
| UE Viewer 只找到约 7,275 文件 | 使用了普通构建，或破坏了 `.pak/.utoc/.ucas` 同名配对 |
| 头发出现在脚下/世界原点 | 头发 PSK 是局部组件，必须按 `SC_Hair`/共有尾发骨对齐 |
| 头发移动了两倍 | 同时变换了 Armature 父对象和 Mesh 子对象，只移动层级根 |
| PSK 骨架多出大量节点 | FModel 将 sockets 导成 bones；重导时选择 Don't Export Bone Sockets |
| 颈部出现缝 | 不混用不同工具的身体与脸；优先 FModel `.uemodel`，或统一同一工具/格式 |
| 导出内容像 Mod 而非原版 | 临时禁用 `~mods` 后重新扫描，结束后再原样恢复 |

游戏资产版权归原权利人所有。本仓库只提交操作文档和验证脚本，不分发游戏模型、贴图、
mapping、AES key 或第三方工具。
