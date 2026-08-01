# FINAL FANTASY VII REMAKE 模型导出

## 已验证结论

Steam 版 `FINAL FANTASY VII REMAKE` 使用传统 UE4 `.pak`，但 Intergrade 在 UE4.18 基础上混入了较新版本的未版本化属性和自定义 bulk data。FModel 可以解密和浏览目录，但没有匹配的 `.usmap` 时无法反序列化角色模型。实际导出应使用 Remake Intergrade 专用的 UE Viewer 构建。

本机已验证配置：

| 项目 | 值 |
|---|---|
| 游戏目录 | `D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REMAKE` |
| UE Viewer | `E:\tools\umodel_ff7remake\umodel_FFVII_intergrade_v8.exe` |
| 输出目录 | `D:\ff7remake_exports\umodel_original` |
| 引擎覆盖 | `ue4.18` |
| 网格格式 | ActorX `.pskx` |
| 贴图格式 | PNG（HDR 贴图保留为 `.hdr`） |

专用构建来自 UE Viewer 官方论坛的 [Remake 兼容帖](https://www.gildor.org/smf/index.php?topic=6925.120)。官方说明确认：Intergrade 总体仍是 UE4.18，但使用未版本化属性和修改过的 bulk data，必须使用专用构建；v8 构建可以处理网格、贴图和动画。UE Viewer 的通用命令行和导出格式见[官方项目页](https://www.gildor.org/en/projects/umodel)。

## Tifa 验证结果

验证使用的是原版资源，不是 `End\Content\Paks\~mods` 中的替换包：

```text
End/Content/GameContents/Character/Player/
└── PC0002_00_Tifa_Standard/
    ├── Model/PC0002_00.uasset
    ├── Material/
    └── Texture/
```

导出和 Blender 3.6.15 导入均成功：

| 检查项 | 结果 |
|---|---:|
| ActorX 主模型 | `PC0002_00.pskx`，9,251,828 bytes，`ACTRHEAD` 有效 |
| 网格 | 1 |
| 顶点 | 82,059 |
| 多边形 | 103,206 |
| 骨架 | 1 |
| 骨骼 | 481 |
| 材质槽 | 10 |
| UV 层 | 3 |
| 本次导出文件 | 96 个，约 52.97 MB |

验证产物：

```text
D:\ff7remake_exports\umodel_original\Tifa_Remake_validation.blend
D:\ff7remake_exports\umodel_original\Tifa_Remake_validation.png
D:\ff7remake_exports\umodel_original\Tifa_Remake_validation.json
```

Blender 导入器报告 384 个顶点的顶点色存在歧义；网格、骨架、权重、法线和 UV 均正常导入。模型是游戏 bind pose，接近 A-pose。Remake 的 Renderer 复杂材质不能由 UE Viewer 完整重建，因此验证 `.blend` 只按 `.mat` 中的 `Diffuse`、`Normal` 和可识别 Alpha 引用建立了基础材质。

验证渲染中手腕处仍有可见间隙。模型包同时带有 Square Enix 的 KineDriver/Bonamik 用户数据，而 ActorX 不会烘焙这类辅助变形；因此结构验证通过不等于最终美术资产已经完全清理。若目标是直接用于动画或发布，还需要在 Blender 中校正手腕/手部的 rest pose，或另行实现 KineDriver 数据处理。

## 导出 Tifa 或其他角色

使用包装脚本：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
$env:FF7REMAKE_AES_KEY = Read-Host 'FF7 Remake AES key'

.\ff7remake_export.ps1 -Package `
  'End/Content/GameContents/Character/Player/PC0002_00_Tifa_Standard/Model/PC0002_00.uasset'

Remove-Item Env:FF7REMAKE_AES_KEY
```

脚本默认执行以下保护：

- 关闭动画导出，避免主角动画集产生几十 GB 的 PSA；
- 临时将 `~mods` 顶层的 `.pak` 改为非 `.pak` 后缀，成功或失败都会在 `finally` 中恢复；
- 把 AES 写入临时文件并用 `-aes=@file` 传给 UE Viewer，退出后删除临时文件，避免密钥出现在进程命令行；
- 保留 Unreal 原目录结构，并导出引用到的 `.mat`、PNG 和 HDR 贴图。

常用选项：

| 选项 | 用途 |
|---|---|
| `-AllLods` | 导出全部 LOD |
| `-AllWeights` | 保留全部骨骼影响 |
| `-WithAnimations` | 允许导出动画；只对明确需要的包使用 |
| `-IncludeMods` | 不隔离 `~mods`，导出当前 mod 覆盖后的资源 |
| `-NoOverwrite` | 跳过已经存在的导出文件 |
| `-OutputRoot <路径>` | 指定独立输出目录 |

角色资源都在：

```text
End/Content/GameContents/Character/Player/<角色或服装>/Model/
```

主网格通常与文件夹开头的角色编号同名。例如：

```text
Cloud  : PC0000_00_Cloud_Standard/Model/PC0000_00.uasset
Barret : PC0001_00_Barret_Standard/Model/PC0001_00.uasset
Tifa   : PC0002_00_Tifa_Standard/Model/PC0002_00.uasset
```

服装变体也是同样规律，例如 Tifa 的 `PC0002_01_Tifa_PurpleDress`、`PC0002_02_Tifa_ChinaDress` 和 `PC0002_03_Tifa_WallMarketDress`。先在 FModel/UE Viewer 树中确认具体文件名，再把完整包路径传给脚本；不要对整个 `Player` 目录一次性导出。

多个包可以一次传入：

```powershell
.\ff7remake_export.ps1 -Package @(
  'End/Content/GameContents/Character/Player/PC0000_00_Cloud_Standard/Model/PC0000_00.uasset',
  'End/Content/GameContents/Character/Player/PC0001_00_Barret_Standard/Model/PC0001_00.uasset',
  'End/Content/GameContents/Character/Player/PC0002_00_Tifa_Standard/Model/PC0002_00.uasset'
)
```

## Blender 导入

本机 Blender 3.6 已安装 `io_scene_psk_psa` 5.0.6。导入步骤：

1. `File > Import > Unreal PSK (.psk/.pskx)`；
2. 选择角色的 `.pskx`；
3. 保持 Vertex Normals、Extra UVs、Vertex Colors、Skeleton 开启；
4. 按同目录的 `.mat` 文件连接贴图：`Diffuse` 接 Base Color，`Normal` 经过 Normal Map，`*_A` 用作 Alpha；
5. `_M`、`_B`、`_O` 是游戏专用的打包/遮罩贴图，通道语义需要按具体材质检查，不应统一猜测。

FModel 官方文档也说明，加密包必须配置 AES 才能启用归档，目录和包视图可用于定位资源；参见 [FModel Getting Started](https://github.com/4sval/FModel/wiki/Getting-Started)。
