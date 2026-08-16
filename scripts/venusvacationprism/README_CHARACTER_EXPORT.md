# PRISM 按角色名查看与导出

这套命令从游戏原始 `fdata_package` 中选择经过验证的 BODY、FACE、HAIR 默认组合，解析
G1M 和全部纹理，再通过 Blender 生成绑定的 Blend、FBX 与 GLB。脚本只读游戏安装目录，
不会注入或修改游戏。

## 1. 查看可以使用的角色名

在仓库根目录运行：

```powershell
.\scripts\venusvacationprism\list_character_names.ps1
```

只显示当前支持一键导出的角色：

```powershell
.\scripts\venusvacationprism\list_character_names.ps1 --exportable-only
```

显示默认 BODY、FACE、HAIR 的模型索引和 G1M ID：

```powershell
.\scripts\venusvacationprism\list_character_names.ps1 --details
```

输出机器可读 JSON：

```powershell
.\scripts\venusvacationprism\list_character_names.ps1 --json
```

当前支持情况：

| 可用名字 | 默认身体 | 状态 |
|---|---:|---|
| `Honoka` / `穗香` / `HON` | index 1479 | 可自动导出 |
| `Nanami` / `七海` / `NNM` | index 722 | 可自动导出 |
| `Misaki` / `海咲` / `MIS` | index 837 | 已登记，暂未开放 |
| `Elise` / `伊莉丝` / `ELS` | index 834 | 需要兼容处理，暂未开放 |

## 2. 按角色名导出

导出七海：

```powershell
.\scripts\venusvacationprism\export_character.ps1 `
  --name 七海 `
  --output "D:\venusvacationprism_exports\nanami\complete_auto" `
  --formats blend,fbx,glb
```

导出穗香：

```powershell
.\scripts\venusvacationprism\export_character.ps1 `
  --name 穗香 `
  --output "D:\venusvacationprism_exports\honoka\complete_auto" `
  --formats blend,fbx,glb
```

同一角色的英文名、中文名和内部代码等价。例如 `--name Nanami`、`--name 七海`、
`--name NNM` 都会选择同一套已验证默认组合。

当前电脑的 Steam 游戏路径、Blender 3.6 LTS 和转换依赖可以自动发现。其他安装位置可显式指定：

```powershell
.\scripts\venusvacationprism\export_character.ps1 `
  --name Nanami `
  --game "D:\Games\Venus Vacation PRISM - DEAD OR ALIVE Xtreme -" `
  --blender "D:\Tools\blender-3.6.15\blender.exe" `
  --gust-dir "D:\Tools\gust_stuff" `
  --output "D:\venusvacationprism_exports\nanami\complete_auto" `
  --formats blend,fbx,glb
```

## 3. 常用选项

先查看将选择的资源，不写入文件：

```powershell
.\scripts\venusvacationprism\export_character.ps1 --name 七海 --plan
```

中断后继续；已完成的三组件会先校验再复用：

```powershell
.\scripts\venusvacationprism\export_character.ps1 `
  --name 七海 `
  --output "D:\venusvacationprism_exports\nanami\complete_auto" `
  --formats blend,fbx,glb `
  --resume
```

只解包原始组件、纹理和 glTF，不启动 Blender：

```powershell
.\scripts\venusvacationprism\export_character.ps1 `
  --name 七海 `
  --output "D:\venusvacationprism_exports\nanami\assets" `
  --assets-only
```

`--formats` 可指定 `blend`、`fbx`、`glb` 中的一种或多种，例如
`--formats blend,glb`。非空输出目录默认拒绝写入；只有同一角色、同一组件规则和同一格式集合
才能使用 `--resume`，避免把两个角色的文件混在一起。

## 4. 输出内容

完整导出目录包含：

- `{Character}_Complete_Rigged.blend`：推荐文件，使用中的图片已打包。
- `{Character}_Complete_Rigged.fbx`：附 `textures/fbx/`、材质映射和 Blender 重连脚本。
- `{Character}_Complete_Rigged.glb`：单文件便携模型。
- `components/body`、`components/face`、`components/hair`：原始五件套、逐槽
  G1T/DDS/PNG、glTF、材质映射和静态验证。
- `previews/`：成品及 FBX 回读的正面、背面、右侧和头部预览。
- `character_profile_regression.json`：几何、颈部、贴图及格式回读检查。
- `SHA256SUMS.txt`、`SHA256_MANIFEST.json`：完整交付校验值。

FBX 导入 Blender 后若透明或法线表现不正确，运行同目录的
`{Character}_Relink_FBX_Materials.py` 恢复材质连接。

## 5. 依赖与验证

Python 依赖：

```powershell
python -m pip install -r scripts\venusvacationprism\requirements-character-export.txt
```

另需 Blender 3.6 LTS 与 `eArmada8/gust_stuff`。导出完成前脚本会检查：

- BODY、FACE、HAIR 均保持原始 identity 对齐；
- POSITION 为 glTF 合法的 VEC3，且所有使用中图片存在；
- 头发与脸部包围盒相交，颈部距离符合角色基线；
- Blend 图片全部打包；
- FBX 回读几何、骨架、边界、材质和纹理完整；
- GLB 回读网格、面数、骨架、材质和边界完整；
- 最终目录中每个交付文件的 SHA-256 可复验。

Nanami BODY722 使用已经验证的 dry/static 便携材质近似；原始湿润/DT2 条件 pass 仍保留在
原始资源和 `FULL_SOURCE` glTF 中。Misaki 与 Elise 当前不会由一键入口输出不完整成品。
