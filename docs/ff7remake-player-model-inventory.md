# FINAL FANTASY VII REMAKE Player 模型清单

本清单来自 2026-08-01 对本机 Steam 版 `FINAL FANTASY VII REMAKE INTERGRADE`
原版 pak 的只读枚举，不包含 `End\Content\Paks\~mods`。共确认 `36` 个符合
`PC????_??.uasset` 命名的 Player 主模型包。

完整的一行一路径清单见 [`ff7remake-player-model-files.txt`](ff7remake-player-model-files.txt)。
已安装 Mod 若覆盖既有包路径（例如 `PC0002_00`），不会额外增加主模型包数量。

统一根目录：

```text
End/Content/GameContents/Character/Player/
```

完整包路径由“统一根目录 + 模型目录 + `/Model/` + 主文件”组成。`90/91` 编号通常是
流泪、血污、汗液等剧情效果变体，可能依赖标准主体；`PC0099` 是青蛙状态模型。

## 常规角色和服装（22）

| 角色 | 模型目录 | 主文件 | 本机状态 |
|---|---|---|---|
| Cloud | `PC0000_00_Cloud_Standard` | `PC0000_00.uasset` | 待导出 |
| Cloud | `PC0000_01_Cloud_PoorDress` | `PC0000_01.uasset` | 待导出 |
| Cloud | `PC0000_02_Cloud_OrdinaryDress` | `PC0000_02.uasset` | 待导出 |
| Cloud | `PC0000_03_Cloud_GorgeousDress` | `PC0000_03.uasset` | 待导出 |
| Cloud | `PC0000_04_Cloud_ZackCostume` | `PC0000_04.uasset` | 待导出 |
| Cloud | `PC0000_05_Cloud_Naked` | `PC0000_05.uasset` | 待导出 |
| Barret | `PC0001_00_Barret_Standard` | `PC0001_00.uasset` | 待导出 |
| Tifa | `PC0002_00_Tifa_Standard` | `PC0002_00.uasset` | 已导出并完成默认手套修复 |
| Tifa | `PC0002_01_Tifa_PurpleDress` | `PC0002_01.uasset` | 已导出并通过 Blender 3.6 验证 |
| Tifa | `PC0002_02_Tifa_ChinaDress` | `PC0002_02.uasset` | 待导出 |
| Tifa | `PC0002_03_Tifa_WutaiDress` | `PC0002_03.uasset` | 待导出 |
| Tifa | `PC0002_04_Tifa_NoGlove` | `PC0002_04.uasset` | 待导出 |
| Aerith | `PC0003_00_Aerith_Standard` | `PC0003_00.uasset` | 待导出 |
| Aerith | `PC0003_01_Aerith_CheapDress` | `PC0003_01.uasset` | 待导出 |
| Aerith | `PC0003_02_Aerith_OrdinaryDress` | `PC0003_02.uasset` | 待导出 |
| Aerith | `PC0003_03_Aerith_SexyDress` | `PC0003_03.uasset` | 待导出 |
| Aerith | `PC0003_04_Aerith_Dirty` | `PC0003_04.uasset` | 待导出 |
| Red XIII | `PC0004_00_RedXIII_Standard` | `PC0004_00.uasset` | 待导出 |
| Yuffie | `PC0005_00_Yuffie_Standard` | `PC0005_00.uasset` | 待导出 |
| Yuffie | `PC0005_01_Yuffie_Moogle` | `PC0005_01.uasset` | 待导出 |
| Yuffie | `PC0005_02_Yuffie_MoogleHoodOff` | `PC0005_02.uasset` | 待导出 |
| Sonon | `PC0006_00_Sonon_Standard` | `PC0006_00.uasset` | 待导出 |

## 剧情效果变体（7）

| 角色 | 模型目录 | 主文件 | 本机状态 |
|---|---|---|---|
| Cloud | `PC0000_90_Cloud_TeaserTmpSweat` | `PC0000_90.uasset` | 待导出 |
| Cloud | `PC0000_91_Cloud_TearSLU5B1490` | `PC0000_91.uasset` | 待导出 |
| Tifa | `PC0002_90_Tifa_TearSLUM74582` | `PC0002_90.uasset` | 待导出 |
| Tifa | `PC0002_91_Tifa_TearSLU5B4550` | `PC0002_91.uasset` | 待导出 |
| Yuffie | `PC0005_90_Yuffie_TearPSBL00910` | `PC0005_90.uasset` | 待导出 |
| Sonon | `PC0006_90_Sonon_TearPSBL00910` | `PC0006_90.uasset` | 待导出 |
| Sonon | `PC0006_91_Sonon_BloodPSBL00910` | `PC0006_91.uasset` | 待导出 |

## 青蛙状态模型（7）

| 对应角色 | 模型目录 | 主文件 | 本机状态 |
|---|---|---|---|
| 通用 | `PC0099_00_Toad_Standard` | `PC0099_00.uasset` | 待导出 |
| Cloud | `PC0099_01_Toad_Cloud` | `PC0099_01.uasset` | 待导出 |
| Barret | `PC0099_02_Toad_Barret` | `PC0099_02.uasset` | 待导出 |
| Tifa | `PC0099_03_Toad_Tifa` | `PC0099_03.uasset` | 待导出 |
| Aerith | `PC0099_04_Toad_Aerith` | `PC0099_04.uasset` | 待导出 |
| Yuffie | `PC0099_05_Toad_Yuffie` | `PC0099_05.uasset` | 待导出 |
| Sonon | `PC0099_06_Toad_Sonon` | `PC0099_06.uasset` | 待导出 |

## 独立配件说明

Player 主模型不一定包含游戏画面中可见的全部部件。已确认 Tifa 标准皮手套位于独立
Weapon SkeletalMesh：

```text
End/Content/GameContents/Character/Weapon/
└── WE0002_00_Tifa_LeatherGlove/Model/WE0002_00.uasset
```

该手套不计入上面的 `36` 个 Player 主模型。

## 已验证产物

### Tifa 标准服装

```text
D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed.blend
D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed.png
D:\ff7remake_exports\umodel_original\Tifa_Remake_fixed_gloves.png
```

### Tifa PurpleDress

```text
D:\ff7remake_exports\tifa_purple_dress\GameContents\Character\Player\PC0002_01_Tifa_PurpleDress\Model\PC0002_01.pskx
D:\ff7remake_exports\tifa_purple_dress\Tifa_PurpleDress.blend
D:\ff7remake_exports\tifa_purple_dress\Tifa_PurpleDress.png
D:\ff7remake_exports\tifa_purple_dress\Tifa_PurpleDress.json
```

PurpleDress 验证数据：`82,509` 个顶点、`108,907` 个多边形、`410` 根骨骼、
`276` 个实际权重顶点组、`9` 个材质槽和 `3` 个 UV 层。主体包含完整手掌和手指，
不需要绑定标准服装的独立皮手套。
