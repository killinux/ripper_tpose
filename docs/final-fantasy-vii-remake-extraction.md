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

原验证渲染中手腕处的断口并不是 KineDriver/Bonamik 或主体权重错误。Remake 标准服装把
完整手掌、护腕和拳套放在独立 Weapon SkeletalMesh 中；`PC0002_00.pskx` 只是主体，单独
导入必然缺少这部分。

## Tifa 默认皮手套

已确认的原版资源目录是：

```text
End/Content/GameContents/Character/Weapon/WE0002_00_Tifa_LeatherGlove/
├── Model/WE0002_00.uasset
├── Material/
└── Texture/
```

### 从 FModel 原始包转成 ActorX

如果专用 UE Viewer 不能直接从加密 `.pak` 定位该网格，可以使用已经验证过的两步法：

1. 在 FModel 搜索 `WE0002_00_Tifa_LeatherGlove`；
2. 保持上述 Unreal 相对目录，保存 `Model`、`Material` 和 `Texture` 中目标包的原始
   `.uasset/.uexp`；
3. 把保存根目录作为 UE Viewer 的 loose-package `-path`，只导出主网格包。

PowerShell 示例（`$rawRoot` 改成 FModel 实际保存根目录）：

```powershell
$rawRoot = 'D:\ff7remake_exports\fmodel_raw'
$umodelArgs = @(
  '-export',
  '-png',
  '-game=ue4.18',
  '-noanim',
  "-path=$rawRoot",
  '-out=D:\ff7remake_exports\umodel_glove_raw',
  'End/Content/GameContents/Character/Weapon/WE0002_00_Tifa_LeatherGlove/Model/WE0002_00.uasset'
)
& 'E:\tools\umodel_ff7remake\umodel_FFVII_intergrade_v8.exe' @umodelArgs
```

不要把 `-game=ue4.18` 直接拼成未经数组保护的动态命令字符串；本机 PowerShell 验证中，
参数数组可避免版本值被错误拆分。成功结果包括：

```text
D:\ff7remake_exports\umodel_glove_raw\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk
D:\ff7remake_exports\umodel_glove_raw\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Texture\WE0002_00_Body_C.png
D:\ff7remake_exports\umodel_glove_raw\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Texture\WE0002_00_Body_N.png
```

### 在 Blender 3.6 中绑定主体

使用仓库中的 `scripts/final/fix_ff7remake_tifa_gloves.py`：

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background `
  'D:\ff7remake_exports\umodel_original\Tifa_Remake_validation.blend' `
  --python 'E:\code\othercode\ripper_tpose\scripts\final\fix_ff7remake_tifa_gloves.py' -- `
  --glove 'D:\ff7remake_exports\umodel_glove_raw\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk' `
  --textures 'D:\ff7remake_exports\umodel_glove_raw\GameContents\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Texture' `
  --output 'D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed.blend' `
  --render 'D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed.png' `
  --closeup 'D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed_gloves.png' `
  --report 'D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed.json'
```

脚本复用手套 PSK 自带权重，不会重新计算自动权重。它会检查所有权重骨名和 local
rest/bind 矩阵，改绑 `PC0002_00` 主体骨架，删除重复手套骨架，再临时旋转权重骨骼验证
Armature modifier 确实产生形变并复位。本机验证结果：

| 检查项 | 结果 |
|---|---:|
| 手套网格 | 1 |
| 顶点 | 13,110 |
| 多边形 | 19,634 |
| 实际权重骨骼 | 30 |
| 主体缺失权重骨骼 | 0 |
| 最坏 local rest 矩阵差 | `6.56e-7` |

最终文件：

```text
D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed.blend
D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed.png
D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed_gloves.png
D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed.json
```

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

服装变体也是同样规律，例如 Tifa 的 `PC0002_01_Tifa_PurpleDress`、
`PC0002_02_Tifa_ChinaDress` 和 `PC0002_03_Tifa_WutaiDress`。先在 FModel/UE Viewer
树中确认具体文件名，再把完整包路径传给脚本；不要对整个 `Player` 目录一次性导出。
本机原版 pak 实际枚举出的 `36` 个 Player 主模型见
[`ff7remake-player-model-inventory.md`](ff7remake-player-model-inventory.md)。

## Tifa PurpleDress 验证结果

已使用同一专用 UE Viewer 和 Blender 3.6 流程验证：

```text
End/Content/GameContents/Character/Player/
└── PC0002_01_Tifa_PurpleDress/Model/PC0002_01.uasset
```

导出目录和 Blender 产物：

```text
D:\ff7remake_exports\tifa_purple_dress\GameContents\Character\Player\PC0002_01_Tifa_PurpleDress\Model\PC0002_01.pskx
D:\ff7remake_exports\tifa_purple_dress\Tifa_PurpleDress.blend
D:\ff7remake_exports\tifa_purple_dress\Tifa_PurpleDress.png
D:\ff7remake_exports\tifa_purple_dress\Tifa_PurpleDress.json
```

| 检查项 | 结果 |
|---|---:|
| ActorX 文件头 | `ACTRHEAD` |
| 网格 | 1 |
| 顶点 | 82,509 |
| 多边形 | 108,907 |
| 骨架 / 骨骼 | 1 / 410 |
| 实际权重顶点组 | 276 |
| 材质槽 | 9 |
| UV 层 | 3 |
| 缺失基础预览贴图 | 0 |

PurpleDress 主网格包含完整手掌和手指，不需要绑定标准服装使用的独立皮手套。基础材质由
`validate_ff7remake_model.py` 根据 UE Viewer `.mat` 中的 Diffuse/Normal 引用连接；脚本会
把 DirectX 法线的绿色通道转换为 Blender/OpenGL 方向，但不会猜测 Renderer 专用打包
遮罩的完整 Shader 语义。

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
