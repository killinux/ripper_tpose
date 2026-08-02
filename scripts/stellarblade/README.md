# Stellar Blade 模型导出与 Blender 3.6 验证

Stellar Blade PC 版使用 UE4 IoStore。它与 FFVII Rebirth/Remake 的 profile、mapping
和资源路径都不同，因此本目录单独维护验证脚本。完整的 FModel、专用 UE Viewer 和
手动 Blender 流程见
[`docs/stellar-blade-extraction.md`](../../docs/stellar-blade-extraction.md)。

## 已验证环境

```text
游戏：Stellar Blade 1.4.1 / Steam build 19963153
游戏目录：D:\Program Files (x86)\Steam\steamapps\common\StellarBlade
FModel：4.4.4 b270829，GAME_StellarBlade
Blender：3.6.15
PSK 导入器：io_scene_psk_psa 5.0.6
头部格式：FModel UEFormat v9（Face_003，53 个 Morph）
```

## `validate_eve.py`

脚本导入 Eve 的标准身体、完整 Face_003、默认发型和独立长马尾。身体/头发 PSK 会检查
`ACTRHEAD`，头部会检查 `UEFORMAT` 并核对 53 个源 Morph 与 Blender 的 54 个 Shape Keys
（含 Basis），再按原骨骼锚点组合组件、保存 `.blend`、渲染 PNG 并写出 JSON 报告。

- 主发型的本地原点对齐身体骨架的 `SC_Hair`；
- 长马尾按双方共有的 `Ab-TL-HairB01` 完整静置骨矩阵恢复位置和旋转；
- 每个组件保留自己的原始骨架、蒙皮权重和对象层级；
- 脸、眼、眉、牙齿、身体和头发连接验证用材质，不覆盖原始导出文件。

当前官方 UEFormat Blender 插件声明 Blender 4.x。Blender 3.6 使用方法：下载
[官方 UEFormat 源码](https://github.com/h4lfheart/UEFormat)，在源码根目录应用
[`ueformat-blender36.patch`](ueformat-blender36.patch)，然后把
`--ueformat-source` 指向 `plugins\blender\io_scene_ueformat`。补丁只跳过 Blender 4
专用骨骼调色 API；解析器、网格、骨架、权重和 Morph 数据不改写。

本机已验证命令：

```powershell
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background `
  --python 'E:\code\othercode\ripper_tpose\scripts\stellarblade\validate_eve.py' -- `
  --body 'D:\stellarblade_exports\fmodel_exports\SB\Content\Art\Character\PC\CH_P_EVE_01\CH_P_EVE_01_Body.psk' `
  --head-uemodel 'D:\stellarblade_exports\fmodel_exports\SB\Content\Art\Character\PC\CH_P_EVE_Head\CH_P_EVE_Face_003.uemodel' `
  --ueformat-source 'C:\Tools\UEFormat\plugins\blender\io_scene_ueformat' `
  --hair 'D:\stellarblade_exports\umodel_exports\Art\Character\PC\00_HR\EVE_HR_01\EVE_HR_01.psk' `
  --tail 'D:\stellarblade_exports\umodel_exports\Art\Character\PC\00_HR\EVE_HR_01\EVE_HR_01_Tail.psk' `
  --face-assets 'D:\stellarblade_exports\umodel_face_exports' `
  --body-diffuse 'D:\stellarblade_exports\fmodel_exports\SB\Content\Art\Character\PC\CH_P_EVE_01\Tex\Body\CH_P_EVE_01_Body_D.png' `
  --hair-alpha 'D:\stellarblade_exports\umodel_exports\Art\Character\PC\CH_P_EVE_Hair\Textures\PonyTail_Alpha.png' `
  --output 'D:\stellarblade_exports\blender\Eve_Standard_validation.blend' `
  --render 'D:\stellarblade_exports\validation\Eve_Standard_validation.png' `
  --report 'D:\stellarblade_exports\validation\Eve_Standard_validation.json'
```

已验证结果为 4 个网格、4 套原始骨架、107,123 顶点、133,874 个面和 338 根骨骼。
Face_003 单独包含 24,350 顶点、35,992 个面、11 个材质槽和 53 个 Morph；脸部近景
`D:\stellarblade_exports\validation\Eve_Standard_validation_face.png` 已视觉复核。

仓库只保存脚本和说明，不保存游戏 PSK、贴图、mapping 或第三方可执行文件。
