# 游戏脚本入口

两套游戏使用不同引擎和不同提取工具，源码按游戏隔离：

| 游戏 | 引擎 / 资源 | 目录 | 推荐入口 |
|---|---|---|---|
| Rise of Eros | Unity AssetBundle | [`riseoferos/`](riseoferos/) | `riseoferos\extract_character.ps1` |
| FINAL FANTASY VII REBIRTH | Unreal IoStore (`.utoc/.ucas`) | [`final/`](final/) | `final\prepare_fmodel.ps1` |

旧命令 `scripts\extract_character.ps1` 仍然可用，它只转发到
`scripts\riseoferos\extract_character.ps1`，因此原有 ROE 自动提取逻辑不变。

Blender 插件也彼此独立：

- ROE：`scripts\riseoferos\roe_xps_addon.py`，侧边栏 **ROE**；
- FFVII Rebirth：`scripts\final\ff7rebirth_tools.py`，侧边栏 **FF7RB**。

FFVII Rebirth 不能调用 AssetStudio：它的模型先由 FModel 从 Unreal IoStore 导出，再由
Blender 插件从导出目录导入。完整步骤见
[`docs/final-fantasy-vii-rebirth-extraction.md`](../docs/final-fantasy-vii-rebirth-extraction.md)。
