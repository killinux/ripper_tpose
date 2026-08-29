# FF7 Rebirth Player 待导出资源与手动导出流程

> 初次盘点：2026-07-26（Asia/Shanghai）
> 主模型包复核：2026-08-01（本机 51 个 `.utoc` 目录索引，只读枚举）
> FModel：`4.4.4.0`，commit `b2708293f64ffc858b4901ff785a9078b99c67f4`
> 游戏虚拟目录：`End/Content/Character/Player`
> 本机输出目录：`D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Player`

## 1. 统计口径

这里的“导出”是指 **FModel 从 FF7 Rebirth 的 IoStore 包读取资源并写到磁盘**，
不是 Blender 把内容导入该目录。

FModel 的 `Player` 虚拟目录当前有 `109` 个一级资源变体；本机输出目录已有 `14`
个一级目录，因此还有 `95` 个一级资源变体尚未写入磁盘。

复核全部 IoStore 目录索引后，其中 `85` 个一级资源变体包含符合
`Model/PC????_??.uasset` 约定的 Player 主模型包，另外 `24` 个是没有该主模型包的
材质/贴图等资源变体。完整的一行一路径清单见
[`ff7rebirth-player-model-files.txt`](ff7rebirth-player-model-files.txt)。

需要注意：

- 一级资源变体目录不等于独立网格模型；
- 只有存在 `Model` 子目录，并且打开资产后在 3D Viewer/Outliner 中确认是
  `SkeletalMesh`，才算可执行 **Save Model** 的模型；
- 只有 `Material`、`Texture` 的目录通常是湿身、眼泪、血迹、脏污或全息等材质效果；
- 本文的 `95` 项应理解为“待核查/待导出的资源变体”，不能直接理解为 `95` 个模型。

| 项目 | 当前数量 |
|---|---:|
| FModel 虚拟 `Player` 一级目录 | `109` |
| Player 主模型包 | `85` |
| 无主模型包的材质/贴图等变体 | `24` |
| 已写入本机输出目录 | `14` |
| 尚未写入本机输出目录 | `95` |
| 已验证可供 Blender 导入的 ActorX 模型 | `9` |
| 尚未形成已验证 ActorX 的主模型包 | `76` |
| Tifa 一级目录 | `12 / 12` 已写入 |

## 2. 当前已经导出的内容

> 已写入磁盘且带主模型的变体，可用
> [`scripts/final/export_ff7rb_models.ps1`](../scripts/final/export_ff7rb_models.ps1)
> 批量材质化为 Blend/FBX/GLB（`-List` 会显示磁盘上每个变体的 MODEL/NO_MODEL 状态）。

### 2.1 Blender 可直接导入的 9 个 ActorX 模型

以下文件均已验证以 `ACTRHEAD` 开始：

| 资源变体 | 模型输出 |
|---|---|
| `PC0002_00_Tifa_Standard` | `Model\PC0002_00.pskx` |
| `PC0002_04_Tifa_NoGlove` | `Model\PC0002_04.pskx` |
| `PC0002_05_Tifa_Soldier` | `Model\PC0002_05.pskx` |
| `PC0002_06_Tifa_SoldierNoHelmet` | `Model\PC0002_06.pskx` |
| `PC0002_08_Tifa_CostaClothing` | `Model\PC0002_08.pskx` |
| `PC0002_09_Tifa_CostaClothing2` | `Model\PC0002_09.pskx` |
| `PC0002_10_Tifa_Loveless` | `Model\PC0002_10.pskx` |
| `PC0002_11_Tifa_ChangingClothes` | `Model\PC0002_11.pskx` |
| `PC0099_03_Toad_Tifa` | `Model\PC0099_03.psk` |

### 2.2 已写入，但不是可直接导入的独立模型

| 资源变体 | 当前内容 | 说明 |
|---|---|---|
| `PC0002_12_Tifa_CutTearBothEyes` | JSON `2` / PNG `1` | 眼泪材质效果，无独立网格 |
| `PC0002_13_Tifa_StandardWet` | JSON `11` / PNG `7` | 湿身材质效果，无独立网格 |
| `PC7002_00_Tifa_StandardCFEnd2` | UASSET `5` / JSON `1` / PNG `5` | 有 UE 原始模型资源，但 FModel ActorX 转换失败 |
| `PC0000_00_Cloud_Standard` | PNG `1` | 引用依赖贴图，不代表 Cloud 模型已经导出 |
| `PC0000_06_Cloud_Soldier` | PNG `5` | Soldier 服装引用贴图，不代表 Cloud 模型已经导出 |

`PC7002_00` 当前不要反复执行 Save Model。其 LOD0 section/index 数据会在当前
FModel ActorX 导出阶段触发越界；原始 `.uasset` 已保留，后续应使用兼容 FF7
Rebirth 的专用 UModel/UE Viewer 构建转换。

## 3. 手动导出前的 FModel 设置

### 3.1 启动与游戏解析设置

可从仓库启动准备脚本：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
.\prepare_fmodel.ps1 -LaunchFModel
```

然后在 FModel 中确认：

1. **Directory Selector** 选择游戏根目录：
   `D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH`。
   不要选择 `End\Content\Paks`。
2. 游戏 profile 选择 **Final Fantasy VII Rebirth**，内部值应为
   `GAME_FinalFantasy7Rebirth = 68812805`，不要改为通用 `UE4.26` 或 `Latest`。
3. mapping 使用
   `D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap`。
4. 更换 profile 或 mapping 后重启一次 FModel。模型格式或输出格式的普通调整不要求
   重启。
5. 日志中应同时出现：

   ```text
   GAME_FinalFantasy7Rebirth
   Mappings pulled from 'FF7Rebirth-4.26-20260726-c838a8ac.usmap'
   ```

mapping 已经生成后，FModel 可以离线读取游戏包，不需要继续运行游戏。

### 3.2 模型与输出设置

打开 **Settings > Models**，确认：

| FModel 项目 | 值 |
|---|---|
| Model Export Directory | `D:\ff7rebirth_exports\fmodel_exports` |
| Mesh Format | `ActorX (psk / pskx)` |
| Level Of Detail Format | `First Level Only` |
| Texture Format | `PNG` |
| Keep Directory Structure | 开启 |

同时在 Settings 的对应输出项中确认 **Save Properties Directory** 和
**Save Texture Directory** 也指向 `D:\ff7rebirth_exports\fmodel_exports`。本机当前
`OutputDirectory`、`RawDataDirectory`、`PropertiesDirectory`、`TextureDirectory`
和 `ModelDirectory` 均使用这个根目录。

当前 Tifa 的 FModel glTF 路径可能因非法 tangent 失败，所以 Player 骨骼模型优先使用
ActorX。开启 `Keep Directory Structure` 后，FModel 会把游戏内 `/Game/...` 资源路径
原样映射到 `D:\ff7rebirth_exports\fmodel_exports\End\Content\...`，这也是
`Player` 目录自动出现的原因。

## 4. 手动导出一个 Player 资源变体

以下流程每次只处理一个一级目录，便于检查失败项和维护清单。

### 4.1 定位资源变体

1. 打开 FModel 的 **Folders** 页签。
2. 进入 `End > Content > Character > Player`。
3. 在搜索框输入清单中的完整目录名，例如
   `PC0003_00_Aerith_Standard`。
4. 双击搜索结果进入目录。
5. 先观察其子目录：
   - 有 `Model`：继续核查网格；
   - 有 `Material`：导出 MaterialInstance JSON；
   - 有 `Texture`：导出 PNG；
   - 没有 `Model`：记录为材质/效果变体，不要把它当成模型导出失败。

### 4.2 导出模型

推荐使用“选择主模型”的方式：

1. 进入该变体的 `Model` 子目录。
2. 优先寻找与变体编号相同的资产，例如：
   - `PC0003_00_Aerith_Standard` 优先打开 `PC0003_00.uasset`；
   - `PC0004_00_RedXIII_Standard` 优先打开 `PC0004_00.uasset`。
3. 双击 `.uasset`，等待 3D Viewer 打开。
4. 确认 Outliner 中显示的是 `SkeletalMesh`，而不是 Skeleton、BNM、Condition、
   VFX 或其他辅助数据。
5. 在 3D Viewer 的 **Outliner** 中右键目标网格，选择 **Save Model**。
6. 等待日志出现成功信息，再检查对应输出目录中的 `.psk` 或 `.pskx`。

如果要尝试导出 `Model` 子目录中的全部可转换模型，可在 Folders 视图右键
`Model` 文件夹，选择 **Save Folder's Packages Models**。批量命令可能同时输出
Condition 或其他网格，因此仍需检查最终文件，不应看到多个文件就默认全部都要导入
Blender。若旧版 FModel 没有文件夹批量菜单，则逐个打开确认后的 SkeletalMesh，并使用
**Save Model**。

### 4.3 导出材质 JSON

1. 返回资源变体根目录。
2. 右键 `Material` 文件夹。
3. 选择 **Save Folder's Packages Properties (.json)**。
4. 如果只保存一个 MaterialInstance，则打开或右键该资产，选择
   **Save Properties (.json)**。
5. 日志应显示类似：

   ```text
   Successfully exported N json files from End/Content/Character/Player/.../Material
   ```

JSON 中的 Unreal 贴图参数与包路径是 Blender 插件准确匹配 Base Color、Normal、
Roughness、Metallic、Opacity 和眼睛分层贴图的重要依据，不应只保存 PNG 而丢弃
JSON。若旧版 FModel 没有文件夹批量菜单，则逐个 MaterialInstance 使用
**Save Properties (.json)**。

### 4.4 导出贴图

1. 右键 `Texture` 文件夹。
2. 选择 **Save Folder's Packages Textures**。
3. 如果只保存一个贴图，则打开或右键该资产，选择 **Save Texture**。
4. 等待日志显示成功导出的纹理数量。
5. 检查输出目录中是否生成 PNG，并保留完整的原目录层级。

不要把不同角色的同名 PNG 全部移动到一个平面文件夹；Material JSON 使用 Unreal
包路径区分同名贴图，打平目录会降低自动匹配的准确性。

### 4.5 完成一个变体后的验收

1. 模型目录应至少出现一个非空 `.psk/.pskx`。
2. ActorX 文件前 8 bytes 应为 `ACTRHEAD`。
3. 材质目录应有 `.json`，贴图目录应有 `.png`；某些模型会引用
   `Character/Common`、其他 Player 变体或 Renderer 下的共享贴图，这是正常依赖。
4. 若没有 `Model` 子目录，只需确认 JSON/PNG 导出成功，并在清单标记
   “材质效果，无独立网格”。
5. 若 Save Model 报错，不要把仅有 `.uasset` 的结果标成 Blender 可用模型。

可在 PowerShell 中检查单个变体：

```powershell
$variant = 'PC0003_00_Aerith_Standard'
$root = 'D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Player'

Get-ChildItem -LiteralPath (Join-Path $root $variant) -Recurse -File |
    Select-Object FullName, Length
```

检查 ActorX 文件头：

```powershell
$model = Get-ChildItem -LiteralPath (Join-Path $root $variant) -Recurse -File |
    Where-Object { $_.Extension -in '.psk', '.pskx' } |
    Select-Object -First 1

if (-not $model) {
    throw "未找到 $variant 的 PSK/PSKX；先确认该变体确实包含 SkeletalMesh 并已成功 Save Model"
}

[Text.Encoding]::ASCII.GetString(
    [IO.File]::ReadAllBytes($model.FullName),
    0,
    8
)
```

正确结果应为：

```text
ACTRHEAD
```

## 5. 待核查/待导出的 95 个资源变体

清单约定：

- `[ ]`：该一级目录尚未写入本机 Player 输出目录；
- `⚠`：名称高度疑似材质或效果变体，必须先确认是否有 `Model/SkeletalMesh`；
- 导出后若得到有效 PSK/PSKX，改成 `[x]` 并记录模型文件名；
- 若没有独立网格，也改成 `[x]`，但注明“材质效果，无独立网格”；
- 若转换失败，保留 `[ ]` 并记录错误，不要把原始 UASSET 当作完成。

### 5.1 Cloud：20

- [ ] `PC0000_04_Cloud_ZackCostume`
- [ ] `PC0000_07_Cloud_SoldierSenior`
- [ ] `PC0000_08_Cloud_SoldierNoHelmet`
- [ ] `PC0000_09_Cloud_CostaClothing`
- [ ] `PC0000_10_Cloud_CostaClothing2`
- [ ] `PC0000_11_Cloud_Loveless`
- [ ] `PC0000_12_Cloud_ZackCostumeDirty` ⚠
- [ ] `PC0000_13_Cloud_CutBroodCheek` ⚠
- [ ] `PC0000_14_Cloud_CutBroodPalm` ⚠
- [ ] `PC0000_15_Cloud_CutBroodBackOfHand` ⚠
- [ ] `PC0000_16_Cloud_CutTearBothEyes` ⚠
- [ ] `PC0000_17_Cloud_LovelessNoMask`
- [ ] `PC0000_18_Cloud_ZackCostumeAge21`
- [ ] `PC0000_19_Cloud_ZackCostumeDirtyAge21` ⚠
- [ ] `PC0000_20_Cloud_LovelessHologram` ⚠
- [ ] `PC0000_21_Cloud_Hologram` ⚠
- [ ] `PC0000_22_Cloud_StandardWet` ⚠
- [ ] `PC0000_23_Cloud_ZackCostumeWet` ⚠
- [ ] `PC0000_24_Cloud_CutTearBothEyes2` ⚠
- [ ] `PC0000_25_Cloud_CutBroodCheek2` ⚠

### 5.2 Barret：8

- [ ] `PC0001_00_Barret_Standard`
- [ ] `PC0001_02_Barret_Corel`
- [ ] `PC0001_03_Barret_Sailor`
- [ ] `PC0001_04_Barret_Loveless`
- [ ] `PC0001_05_Barret_Bandage`
- [ ] `PC0001_06_Barret_CutTearBothEyes` ⚠
- [ ] `PC0001_09_Barret_StandardWet` ⚠
- [ ] `PC0001_10_Barret_StandardWetOnlyHead` ⚠

### 5.3 Aerith：17

- [ ] `PC0003_00_Aerith_Standard`
- [ ] `PC0003_04_Aerith_Dirty` ⚠
- [ ] `PC0003_05_Aerith_Soldier`
- [ ] `PC0003_06_Aerith_SoldierNoHelmet`
- [ ] `PC0003_07_Aerith_CostaClothing`
- [ ] `PC0003_08_Aerith_CostaClothing2`
- [ ] `PC0003_09_Aerith_Loveless`
- [ ] `PC0003_10_Aerith_NoRibbon`
- [ ] `PC0003_11_Aerith_CutNoJacket`
- [ ] `PC0003_12_Aerith_ChangingClothes`
- [ ] `PC0003_13_Aerith_DirtyNoRibbon` ⚠
- [ ] `PC0003_14_Aerith_NoJacketNoRibbon`
- [ ] `PC0003_15_Aerith_CutTearBothEyes` ⚠
- [ ] `PC0003_16_Aerith_LovelessTearBothEyes` ⚠
- [ ] `PC0003_18_Aerith_NoRibbonBlood` ⚠
- [ ] `PC0003_19_Aerith_LovelessSing` ⚠
- [ ] `PC0003_20_Aerith_LovelessSingHologram` ⚠

### 5.4 Red XIII：7

- [ ] `PC0004_00_RedXIII_Standard`
- [ ] `PC0004_02_RedXIII_Loveless`
- [ ] `PC0004_04_RedXIII_Once2`
- [ ] `PC0004_05_RedXIII_Soldier`
- [ ] `PC0004_06_RedXIII_OnceHologram` ⚠
- [ ] `PC0004_07_RedXIII_Once3`
- [ ] `PC0004_08_RedXIII_Dirty` ⚠

### 5.5 Yuffie：8

- [ ] `PC0005_00_Yuffie_Standard`
- [ ] `PC0005_01_Yuffie_Moogle`
- [ ] `PC0005_03_Yuffie_CostaClothing`
- [ ] `PC0005_04_Yuffie_WelcomeDance`
- [ ] `PC0005_05_Yuffie_BlackMantle`
- [ ] `PC0005_06_Yuffie_StandardAvatar` ⚠
- [ ] `PC0005_08_Yuffie_Loveless`
- [ ] `PC0005_09_Yuffie_StandardWet` ⚠

### 5.6 Sonon：3

- [ ] `PC0006_00_Sonon_Standard`
- [ ] `PC0006_01_Sonon_Ghost` ⚠
- [ ] `PC0006_91_Sonon_BloodPSBL00910` ⚠

### 5.7 Cait Sith：3

- [ ] `PC0007_00_CaitSith_Standard`
- [ ] `PC0007_01_CaitSith_Loveless`
- [ ] `PC0007_02_CaitSith_LovelessHologram` ⚠

### 5.8 Debumoogle：4

- [ ] `PC0008_00_Debumoogle_Standard`
- [ ] `PC0008_01_Debumoogle_CutL`
- [ ] `PC0008_02_Debumoogle_CutM`
- [ ] `PC0008_03_Debumoogle_CutS`

### 5.9 Zack：4

- [ ] `PC0009_00_Zack_Standard`
- [ ] `PC0009_01_Zack_AerithRibbon`
- [ ] `PC0009_02_Zack_Dirty` ⚠
- [ ] `PC0009_03_Zack_StandardWet` ⚠

### 5.10 Sephiroth：3

- [ ] `PC0010_00_Sephiroth_Standard`
- [ ] `PC0010_01_Sephiroth_StandardWet` ⚠
- [ ] `PC0010_10_Sephiroth_Transform`

### 5.11 Vincent 与 Cid：3

- [ ] `PC0011_00_Vincent_Standard`
- [ ] `PC0012_00_Cid_Standard`
- [ ] `PC0012_01_Cid_NoAmbientOcclusion` ⚠

### 5.12 青蛙变体：9

- [ ] `PC0099_00_Toad_Standard`
- [ ] `PC0099_01_Toad_Cloud`
- [ ] `PC0099_02_Toad_Barret`
- [ ] `PC0099_04_Toad_Aerith`
- [ ] `PC0099_05_Toad_Yuffie`
- [ ] `PC0099_07_Toad_RedXIII`
- [ ] `PC0099_08_Toad_CaitSith`
- [ ] `PC0099_90_Toad_Mob`
- [ ] `PC0099_91_Toad_Finn`

### 5.13 CFEnd2 变体：6

- [ ] `PC7000_00_Cloud_StandardCFEnd2`
- [ ] `PC7000_01_Cloud_StandardCFEnd2Hologram` ⚠
- [ ] `PC7001_00_Barret_StandardCFEnd2`
- [ ] `PC7005_00_Yuffie_StandardCFEnd2`
- [ ] `PC7008_00_Debumoogle_StandardCFEnd2`
- [ ] `PC7010_00_Sephiroth_StandardCFEnd2`

合计：

```text
20 + 8 + 17 + 7 + 8 + 3 + 3 + 4 + 4 + 3 + 3 + 9 + 6 = 95
```

## 6. 每次完成后的维护规则

每处理一个资源变体，都在本文件中同步：

1. 更新对应复选框；
2. 记录是“有效 ActorX 模型”“材质效果”还是“转换失败”；
3. 若有模型，记录 `.psk/.pskx` 文件名；
4. 若失败，记录 FModel 日志中的错误摘要；
5. 重新统计“已写入/待导出/Blender 可用模型”数量；
6. 在 `docs/CHANGELOG.md` 记录本次批次、操作方法、原理和验证结果。

不要仅根据一级目录已经出现就标记模型完成。必须以有效 PSK/PSKX，或明确确认该变体
没有独立网格为准。
