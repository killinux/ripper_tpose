# ROE 角色代号对照表

提取产物用的是 `a01`、`g11`、`m02` 这样的代号。规律是：

> **字母 = 角色身份，数字 = 服装/形态变体。**

所以 `g11` 是 Luf 的第 11 套，`a07` 是 Inase 的第 7 套。同字母共享基础裸体
（这也是 `export_nude_models.ps1` 按字母组织 17 套基础体的原因）。

## 对照表

| 字母 | 角色名 | 变体数 | 证据强度 |
|---|---|---|---|
| a | Inase | 14 | 128 |
| b | Kart | 13 | 140 |
| c | Misa | 11 | 110 |
| d | Erin | 11 | 118 |
| e | Miri | 11 | 100 |
| f | Rana | 11 | 120 |
| g | Luf | 13 | 118 |
| h | Fen | 10 | 90 |
| i | Sera | 5 | 40 |
| j | Lynn | 12 | 110 |
| k | Keleira | 8 | 60 |
| m | Amano | 4 | 20 |
| l | SFox？ | 1 | **5（存疑）** |

「证据强度」是下面那套推导里该名字被投到的票数。

## 两处存疑

- **`l` = SFox**：只有 5 票，且 `SFox` 更像资源命名而非角色名。这一格当作未确认。
- **Inase / ines**：`artifact_icon_ines_*.ab` 里的 `ines` 与推出的 `Inase` 可能是同一
  角色的不同拼写，也可能是两个不同角色。没有进一步证据前不合并。

## 怎么推出来的

游戏本体**没有**明文的 ID→名字表：主数据 `gameplayAsset.data`（LocalLow 缓存里，
80MB）是打包的 Lua 脚本 + 序列化数据，里面出现的 `a01`/`g11` 都是二进制巧合子串；
`HTTPCache` 是空的，名字很可能来自服务端接口。

可用的线索在 `StreamingAssets\AssetBundles\assetbundle_lookup_table.ab` 里——
解包后是一个 7.4MB 的单行 JSON（`assetbundleLookupTable.txt`），按资源类型分组，
每条记录形如：

```json
{"Key":[{"Key":"assetName","Value":"en_Inase_nk@eros03_p1"}],
 "Value":{"MainAsset":{"BundleName":["0","...pc_a03..."]}}}
```

关键在于**语音资源用真名命名**（`en_<Name>_nk@...` / `jp_<Name>_nk@...`），
而同一条记录的 bundle 名里带 `pc_<字母><数字>`。把两者配对、按字母聚合投票，
就得到上表。`artifact_icon_<名字>_*.ab` 这类按名字命名的资源族可作交叉验证：
erin / fen / kart / keleira / luf / lynn / miri / misa / rana / amano 十个都对得上。

复现步骤：

```powershell
# 1) 解出查找表
& "E:\tools\AssetStudioModCLI_net472\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe" `
  "D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros\RiseOfEros_Data\StreamingAssets\AssetBundles\assetbundle_lookup_table.ab" `
  -m export -o <输出目录> -g none
# 2) 解析 assetbundleLookupTable.txt：抓 assetName 里的 en_<Name>_nk 与
#    BundleName 里的 pc_<字母><数字>，按字母投票
```

出新角色后重跑即可更新；名字来自游戏资源命名，不是猜的。

## 别处的同类信息

- **DOA5LR**：条目名本身就是角色名（`KASUMI_COS_001`），无需对照。
- **DOA6**：三字母代号，花名册见 `D:\doa6_exports\README.md`。
- **Throne of Desire**：`h005` 这类代号尚未考证。
