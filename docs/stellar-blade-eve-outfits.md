# Stellar Blade Eve 服装清单与粉色判定

记录 2026-08-29 在本机 Steam 版 Stellar Blade `1.4.1`（build `19963153`）上核对的
Eve 服装资产清单。编号→名称映射来自
[Stellar Blade Modding Guide 的 ID's Library](https://github.com/Stellar-Blade-Modding-Team/Stellar-Blade-Modding-Guide/wiki/ID's-Library)，
资产存在性用 `scripts/stellarblade/list_models.py` 直接解析 `.utoc` 目录索引核对；
颜色判定基于全部服装 albedo 贴图的色相统计（方法见文末）。

包路径规律：本体 `SB/Content/Art/Character/PC/CH_P_EVE_XX/CH_P_EVE_XX[_Body].uasset`，
换色变体 `_TypeB/_TypeC`（部分带 `NH` 无高跟变体）；联动 DLC 挂载在
`SB/Content/DLC_1/`（NieR）与 `SB/Content/DLC_2/`（NIKKE）下，用
`SB/Content/Art/` 过滤会漏掉它们。

## 1. 编号服装（CH_P_EVE_02 – 63）

编号不连续：12、13、38、44 不存在。TypeB/TypeC 为同目录换色变体。

| ID | 名称 | 变体 |
|---|---|---|
| 02 | Daily Biker | TypeB: Four Seconds Biker |
| 03 | Daily Rider | — |
| 04 | Daily Denim | TypeB: Four Seconds Denim |
| 05 | Daily Sailor | TypeB: Comfort Sailor（另有 NH） |
| 06 | Black Wave | TypeB: Wild Wave（另有 NH） |
| 07 | Punk Top | TypeB: Punk Style |
| 08 | Prototype Planet Diving Suit V2 | TypeB: 6th V2 (OrangeRed)、TypeC: 6th V3 |
| 09 | Planet Diving Suit (7th) | TypeB/TypeC: V2/V3；09_V02: Protection Suit (7th)（+TypeB） |
| 10 | Planet Diving Suit (Captain) / Tachy Suit | — |
| 11 | Raven Suit | — |
| 14 | Planet Diving Suit (3rd) | TypeB: V2；14_1: Prototype（+TypeB） |
| 15 | Orca Engineer (15_V02) | TypeB: Orca Techie |
| 16 | Black Kunoichi | TypeB: White Kunoichi |
| 17 | Sporty Yellow | TypeB: Sporty Energy |
| 18 | Daily Mascot | TypeB: Comfort Mascot |
| 19 | Cybernetic Bondage | TypeB: Autonetic Bondage |
| 20 | Black Rose | TypeB: La Vie en Rose、TypeC: Angelic Rose |
| 21 | Sky Ace | TypeB: Air Ace |
| 22 | White full dress | — |
| 23 | Black full dress | — |
| 24 | Wasteland Adventurer | TypeB: Wasteland Explorer |
| 25 | Motivation | TypeB: Resonance |
| 26 | Red Passion | TypeB: Emerald Passion |
| 27 | Ocean Maid | TypeB: Tidal Maid |
| 28 | Holliday Rabbit | TypeB: Holliday Bunny |
| 29 | Keyhole Suit | TypeB: Stargazer Suit、TypeC: Keyhole Dress |
| 30 | Planet Diving Suit (2nd) | TypeB: V2 |
| 31 | Cybernetic Dress | TypeB: Cybernetic Suit |
| 32 | Daily Knit Dress | TypeB: Comfort Knit Dress |
| 33 | Peony | Body_02: Hydrangea |
| 34 | Moutan Peony | body_02: Black Lotus |
| 35 | Black Pearl | TypeB: Red Pearl |
| 36 | Junk Mechanic | TypeB: Junk Engineer |
| 37 | Office Style | TypeB: Crew Style |
| 39 | Daily Force | TypeB: Comfort Force |
| 40 | Cyber Magician | TypeB: Cyber Trickster、TypeC: Cyber Illusionist |
| 41 | Racers High | TypeB: Speeders High |
| 42 | Orca Exploration Suit | TypeB: Orca Pathfinder |
| 43 | Blue Monsoon | TypeB: White Monsoon |
| 45 | Fluffy Bear | TypeB: **Pink Bear** |
| 46 | Silver Kunoichi | TypeB: Shadow Kunoichi |
| 47 | Cyber Bunny | — |
| 48 | Ocean String | — |
| 49 | White Pearl | TypeB: Aqua Pearl |
| 50 | Four Seconds Everyday Wear | TypeB: Essential Wear |
| 51 | Four Seconds Destroyed Denim | — |
| 52 | Four Seconds Black Denim | TypeB: Classic Denim |
| 53 | Ultimate Bunny | TypeB: Extreme Bunny |
| 54 | Neurocircuit Bondage | — |
| 55 | Prototype Neurolink Suit | TypeB: Prototype Sensate Suit |
| 56 | Neurolink Suit | — |
| 57 | Neurolink Skin | TypeB: Sensate Skin |
| 58 | War Aegis | — |
| 59 | War Dress | TypeB: War Suit |
| 60 | Midsummer Red Hood | — |
| 61 | Midsummer Alice | — |
| 62 | Wave Oblique Monokini | — |
| 63 | Wave Diver Bikini | — |

## 2. 特殊目录

| ID | 名称 |
|---|---|
| CH_P_EVE_Christmas_01 | Santa Dress |
| CH_P_EVE_DX | Photogenic（TypeB: Telegenic） |
| CH_P_EVE_Fusion | Angelic Rose Nano Suit |
| CH_P_EVE_IberisCostume | Iberis' Costume |
| CH_P_EVE_InnerSuit | Skin Suit（InnerSuit1: Skin Suit Blue；EveOriginalProportions 裸模 Mod 覆盖对象） |
| CH_P_EVE_OneMillion_01 | Crimson Wings（百万纪念） |
| CH_P_EVE_RoyalGuard_01 | Royal Guard Suit（Rael 服装） |

## 3. 联动 DLC（本机已安装）

| ID | 名称 |
|---|---|
| DLC_1 CH_P_EVE_Nier_01 | YoRHa Uniform No. 2 Type B（2B） |
| DLC_1 CH_P_EVE_Nier_02 | YoRHa Uniform 1 |
| DLC_1 CH_P_EVE_Nier_03 | YoRHa Unofficial Ceremonial Attire |
| DLC_1 CH_P_EVE_Nier_04 | YoRHa Type A No. 2（A2） |
| DLC_2 CH_P_EVE_Nikke_01 | Scarlet Costume |
| DLC_2 CH_P_EVE_Nikke_02 | Elegant Dress（Dorothy） |
| DLC_2 CH_P_EVE_Nikke_03 | Elysion Combat Uniform（Rapi） |
| DLC_2 CH_P_EVE_Nikke_04 | Never Look Back（Anis） |
| DLC_2 CH_P_EVE_Nikke_05 | Missing Link（Modernia） |
| DLC_2 CH_P_EVE_Nikke_06 | **Cooling Suit（Alice）** |

## 4. 粉色判定

方法：专用 UE Viewer 按名批量导出全部服装 albedo（`*_A` 与换色变体
`*_A_Type_X` / `*_A_2`，共 299 张 PNG）到
`D:\stellarblade_exports\outfit_albedo\`，每张缩样后统计"强粉"像素占比
（HSV 色相 295–350°、饱和度 ≥ 0.28、明度 ≥ 0.35），完整排名见
`D:\stellarblade_exports\validation\outfit_pink_ranking.csv`，
头部候选已逐张目检。

**真正的粉色服装只有两套：**

| 服装 | 强粉占比 | 说明 |
|---|---:|---|
| CH_P_EVE_45_TypeB「Pink Bear」 | 82.8% | 亮粉色全身熊套装 |
| DLC_2 CH_P_EVE_Nikke_06「Cooling Suit (Alice)」 | 82.4% | NIKKE 联动 Alice 粉色紧身衣 |

易误判为粉色、实为红色系（已目检贴图）：

- La Vie en Rose（20 TypeB）：深玫瑰红礼裙；
- War Aegis（58）：绯红底 + 约 8.6% 品红点缀；
- Racers High（41）：红黑格纹；
- Peony（33）：正红韩服（Hydrangea 为青色）；
- Holliday Rabbit（28）：灰白/橙色（并非粉色兔装）。

局限：个别服装的最终颜色由材质实例的调色参数决定而非贴图本身
（灰度底图 + tint），此类贴图统计会偏低；目检未发现因此漏掉的粉色整装。

## 5. 怎么导出某套服装（简单示例）

最快的方式是专用 UE Viewer 命令行，**直接用包名**（不用写完整路径，
表中 ID 加变体后缀即包名）。以 Pink Bear 为例，本机已验证：

```powershell
$umodel = 'E:\tools\umodel_stellarblade\umodel_stellar_blade_v6.exe'
$game   = 'D:\Program Files (x86)\Steam\steamapps\common\StellarBlade'

& $umodel -export ('-path=' + $game) '-game=ue4.26' -noanim -psk -png `
  ('-out=D:\stellarblade_exports\umodel_outfit_exports') `
  CH_P_EVE_45_TypeB
```

输出 `...\umodel_outfit_exports\Art\Character\PC\CH_P_EVE_45\CH_P_EVE_45_TypeB.psk`
及引用到的全部贴图 PNG（一次 13 个对象，秒级）。要点：

- 包名规律：主装 `CH_P_EVE_XX`（或 `CH_P_EVE_XX_Body`），换色 `CH_P_EVE_XX_TypeB`，
  具体以第 1–3 节表格和 `list_models.py` 输出为准；DLC 服装同样直接用包名
  （如 `CH_P_EVE_Nikke_06`），不需要写 `DLC_2` 路径。
- 要直接得到组装好的 Blender 场景（服装 + 脸 + 发型 + 马尾），用一键脚本
  `scripts\stellarblade\export_outfit.ps1 <包名>`——它会自动补导 PSK、按材质名
  匹配贴图并输出 `blender\Eve_<包名>.blend`（详见
  `scripts/stellarblade/README.md`）。
- 需要 Morph（如脸）或想要 `.uemodel` 时用 FModel GUI 手动导出，
  完整流程见 [`stellar-blade-extraction.md`](stellar-blade-extraction.md) 第 3 节。
- 导出前确认 `~mods` 为空或已移走，避免 Mod 覆盖原版资产。

## 6. 相关文件

- 全模型清单差集工具：`scripts/stellarblade/list_models.py`（注意 DLC 路径
  以 `SB/Content/DLC_1/`、`SB/Content/DLC_2/` 开头，默认角色树过滤不含它们）
- 贴图导出目录：`D:\stellarblade_exports\outfit_albedo\`（约 1.5 GB，可删）
- 粉色排名 CSV：`D:\stellarblade_exports\validation\outfit_pink_ranking.csv`

游戏与 DLC 资产版权归原权利人所有；本仓库仅记录清单与方法，不提交贴图。
