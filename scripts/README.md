# 游戏脚本入口

不同游戏使用不同引擎、封包和提取 profile，源码按流程隔离：

| 游戏 | 引擎 / 资源 | 目录 | 推荐入口 |
|---|---|---|---|
| Rise of Eros | Unity AssetBundle | [`riseoferos/`](riseoferos/) | `riseoferos\extract_character.ps1` |
| FINAL FANTASY VII REBIRTH | Unreal IoStore (`.utoc/.ucas`) | [`final/`](final/) | `final\prepare_fmodel.ps1` |
| Stellar Blade | Unreal IoStore (`.utoc/.ucas`) | [`stellarblade/`](stellarblade/) | `stellarblade\validate_eve.py` |
| Throne of Desire | X-Legend NFS + Gamebryo NIF/KFM | [`throneofdesire/`](throneofdesire/) | `throneofdesire\extract_nfs.py` |

旧命令 `scripts\extract_character.ps1` 仍然可用，它只转发到
`scripts\riseoferos\extract_character.ps1`，因此原有 ROE 自动提取逻辑不变。

Blender 插件也彼此独立：

- ROE：`scripts\riseoferos\roe_xps_addon.py`，侧边栏 **ROE**；
- FFVII Rebirth：`scripts\final\ff7rebirth_tools.py`，侧边栏 **FF7RB**；
- Stellar Blade：`scripts\stellarblade\validate_eve.py`，Blender 3.6 后台组合验证。

FFVII Rebirth 不能调用 AssetStudio：它的模型先由 FModel 从 Unreal IoStore 导出，再由
Blender 插件从导出目录导入。完整步骤见
[`docs/final-fantasy-vii-rebirth-extraction.md`](../docs/final-fantasy-vii-rebirth-extraction.md)；
Player 的已导出/待导出差集与逐项手动操作见
[`docs/ff7rebirth-player-export-inventory.md`](../docs/ff7rebirth-player-export-inventory.md)。

Stellar Blade 使用精确的 `GAME_StellarBlade` profile 和独立 mapping；Eve 又由身体、脸、
主发型和马尾等 SkeletalMesh 组成，不能直接复用 FFVII 的资源路径。FModel/专用 UE
Viewer 导出与 Blender 3.6 骨骼锚点组合方法见
[`docs/stellar-blade-extraction.md`](../docs/stellar-blade-extraction.md)。

Throne of Desire 不使用 Unreal/Unity。先用 `extract_nfs.py` 读取
`packageindex` 和 `FileListPC.txt`，得到 Gamebryo NIF/KFM，再交给兼容的
X-Legend 查看器或 NIF 转换器。当前索引结构、资产统计和 Blender 3.6 限制见
[`docs/throne-of-desire-extraction.md`](../docs/throne-of-desire-extraction.md)。

## 开发辅助

需要对已经打开且启动了 MCP 服务的 Blender 做本地诊断时，使用
[`dev/blender_mcp/execute_code.ps1`](dev/blender_mcp/execute_code.ps1)。其用途和安全
边界见 [`dev/blender_mcp/README.md`](dev/blender_mcp/README.md)。

`scripts` 根目录只保留本说明和兼容入口 `extract_character.ps1`；正式脚本按游戏放入
`riseoferos/`、`final/`、`stellarblade/`、`throneofdesire/`，可复用开发工具放入 `dev/`，一次性
probe/渲染/热重载脚本不提交到仓库。
