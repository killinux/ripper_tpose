# 游戏脚本入口

不同游戏使用不同引擎、封包和提取 profile，源码按流程隔离：

| 游戏 | 引擎 / 资源 | 目录 | 推荐入口 |
|---|---|---|---|
| Rise of Eros | Unity AssetBundle | [`riseoferos/`](riseoferos/) | `riseoferos\extract_character.ps1` |
| FINAL FANTASY VII REBIRTH | Unreal IoStore (`.utoc/.ucas`) | [`final/`](final/) | `final\prepare_fmodel.ps1` |
| Stellar Blade | Unreal IoStore (`.utoc/.ucas`) | [`stellarblade/`](stellarblade/) | `stellarblade\export_eve.ps1` |
| Throne of Desire | X-Legend NFS + Gamebryo NIF/KFM | [`throneofdesire/`](throneofdesire/) | `throneofdesire\export_nude_models.ps1` |
| Venus Vacation PRISM | KTGL RDB/FDATA + G1M | [`venusvacationprism/`](venusvacationprism/) | `venusvacationprism\export_character.ps1` |
| Operation LOVECRAFT: Fallen Doll | Unreal (UE4.26, AES 加密 pak) | [`fallendoll/`](fallendoll/) | `fallendoll\prepare_fmodel.ps1` |
| Dead or Alive 5 Last Round | Team Ninja .bin/.lnk + TMC/TMCL | [`doa5lr/`](doa5lr/) | `doa5lr\export_full.ps1` |
| Dead or Alive 6 | KTGL v2 RDB + G1M/G1T | [`doa6/`](doa6/) | `doa6\export_full.ps1` |
| Virt-A-Mate 1.22 | Unity 资源包 + `.var`（DAZ Genesis 2 人体 / 自定义网格） | [`vam/`](vam/) | `vam\export_vam_models.ps1` |

旧命令 `scripts\extract_character.ps1` 仍然可用，它只转发到
`scripts\riseoferos\extract_character.ps1`，因此原有 ROE 自动提取逻辑不变。

Blender 插件也彼此独立：

- ROE：`scripts\riseoferos\roe_xps_addon.py`，侧边栏 **ROE**；
- FFVII Rebirth：`scripts\final\ff7rebirth_tools.py`，侧边栏 **FF7RB**；
- Stellar Blade：`scripts\stellarblade\validate_eve.py`，Blender 3.6 后台组合验证。

FFVII **Remake** INTERGRADE 走 UE Viewer（umodel）专用构建：`final\export_ff7remake_models.ps1`
按清单批量「提取 + Blender 材质化」36 个 Player 包，画廊在 `final\html\`；
步骤见 [`docs/final-fantasy-vii-remake-extraction.md`](../docs/final-fantasy-vii-remake-extraction.md)。

FFVII Rebirth 不能调用 AssetStudio：它的模型先由 FModel 从 Unreal IoStore 导出，再由
Blender 插件从导出目录导入；`final\fmodel_export_player.py` 可用 pywinauto 驱动 FModel 把
`Player` 整目录一次导出，已保存的 Player 变体再用
`final\export_ff7rb_models.ps1` 无头批量材质化为 Blend/FBX/GLB，画廊在 `final\html_rebirth\`。完整步骤见
[`docs/final-fantasy-vii-rebirth-extraction.md`](../docs/final-fantasy-vii-rebirth-extraction.md)；
Player 的已导出/待导出差集与逐项手动操作见
[`docs/ff7rebirth-player-export-inventory.md`](../docs/ff7rebirth-player-export-inventory.md)。

Stellar Blade 使用精确的 `GAME_StellarBlade` profile 和独立 mapping；Eve 又由身体、脸、
主发型和马尾等 SkeletalMesh 组成，不能直接复用 FFVII 的资源路径。一键组装与验证用
`stellarblade\export_eve.ps1`（检查 FModel 手动导出、自动补导 UE Viewer 头发组件、
自动准备补丁版 UEFormat、无头运行 `validate_eve.py`）。FModel/专用 UE
Viewer 导出与 Blender 3.6 骨骼锚点组合方法见
[`docs/stellar-blade-extraction.md`](../docs/stellar-blade-extraction.md)。

Throne of Desire 不使用 Unreal/Unity。批量出带材质裸模用
`throneofdesire\export_nude_models.ps1`（女性 h 系模型本体即裸模，衣服是默认隐藏的
附件）；底层由 `extract_nfs.py` 读取 `packageindex` 和 `FileListPC.txt` 得到
Gamebryo NIF/KFM，再交给仓库的 Blender 导入器或兼容的 X-Legend 查看器。当前索引结构、资产统计和 Blender 3.6 限制见
[`docs/throne-of-desire-extraction.md`](../docs/throne-of-desire-extraction.md)。

Venus Vacation PRISM 使用 KTGL RDB/FDATA。`list_models.py` 会生成全量 G1M 清单，
`map_characters.py` 通过名称哈希生成六名角色的已确认分件对应表，`export_model.py` 可按
一基索引、KTID 或恢复的内部名称还原单个原生 G1M；格式说明与可选 glTF 转换见
[`venusvacationprism/README.md`](venusvacationprism/README.md)。

Operation LOVECRAFT: Fallen Doll 是 UE4.26 游戏，单个 AES 加密 pak（pak v9，索引加密）。
`fallendoll\probe_pak.py` 只读探测封包，`prepare_fmodel.ps1` 建工作区并打印 FModel
配置指引，`export_models.ps1` 在拿到 key、从 FModel 导出后批量材质化（复用 FF7 Rebirth
的 UE4.26 管线）。当前唯一阻塞是 pak 的 AES key（不在仓库保存）；详见
[Fallen Doll 提取调研](../docs/fallen-doll-extraction.md)。

Virt-A-Mate 没有传统意义的「角色模型文件」：一个 Look = 游戏自带的 Genesis 2 基础人体
（`VaM_Data\StreamingAssets_per`）+ 一串 morph 增量（`.vmb`）+ 皮肤贴图 + 若干件衣服网格
（`.vab`），全部散落在 `AddonPackages\*.var`（zip）和场景 JSON 里。`vam\export_vam_models.ps1`
把这些拼回一个带材质的 `.blend` + 预览图，`-List` 列出全部 Look / 衣服 / 头发，`-Only` /
`-Index` 按名字或序号转；发丝头发按造型引导线转成 Blender 曲线（近似），挂在骨骼上的
CustomUnityAsset（网格头发/首饰/武器）拆包后按静止姿势重摆。格式细节见
[`vam/README.md`](vam/README.md)。

DOA5LR 与 DOA6 都是 Koei Tecmo 系但封包完全不同：DOA5LR 用 `.bin/.lnk`（文件名混淆
+ XOR 加密 + 分块 zlib），`doa5lr\extract_lnk.py` 为自研 Python 解包器（算法移植自
Archive Tool 源码），TMC/TMCL 经 Noesis（32 位 + doa5pc 插件）转 FBX+DDS；DOA6 用
KTGL v2 RDB，`doa6\extract_rdb.py` 为自研解包器（修复了 Cethleann 的 zlib 截断
bug），G1M/G1T 经 Noesis64 + ProjectG1M 转 FBX+DDS。两游戏均可一键出**带材质 .blend + 预览图**（`export_full.ps1`），也都支持直接
喂社区 mod：DOA5LR 用 `-TmcFile <mod.TMC>`，DOA6 用 `export_nude_mod.ps1 <mod.zip>`
（两作官方内容都不含 nude，已逐条目核实）。角色组成不同——DOA5LR 是「服装 TMC
（含身体+脸）+ 头发 TMC」，DOA6 是「COS + HAIR + FACE」三部件。

操作指南（官方与 nude/mod 两条路线）见
[`doa5lr/EXPORT_GUIDE.md`](doa5lr/EXPORT_GUIDE.md)、[`doa6/EXPORT_GUIDE.md`](doa6/EXPORT_GUIDE.md)；
格式与实现细节见各自 [`doa5lr/README.md`](doa5lr/README.md)、[`doa6/README.md`](doa6/README.md)；
产物索引见导出目录下的 `README.md`（`D:\doa5lr_exports\`、`D:\doa6_exports\`）。

## 开发辅助

需要对已经打开且启动了 MCP 服务的 Blender 做本地诊断时，使用
[`dev/blender_mcp/execute_code.ps1`](dev/blender_mcp/execute_code.ps1)。其用途和安全
边界见 [`dev/blender_mcp/README.md`](dev/blender_mcp/README.md)。

`scripts` 根目录只保留本说明和兼容入口 `extract_character.ps1`；正式脚本按游戏放入
`riseoferos/`、`final/`、`stellarblade/`、`throneofdesire/`、`venusvacationprism/`、`fallendoll/`，可复用开发工具放入 `dev/`，一次性
probe/渲染/热重载脚本不提交到仓库。
