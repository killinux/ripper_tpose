# GANTZ 相关 mod：待讨论

状态：**待讨论**（2026-11-01 整理）。每一项做不做、先做哪个，等用户挑。

## 怎么搜的

- **Nexus**：公开的 v2 GraphQL 接口，不用登录。
  - 按名字搜：gantz、reika、shimohira、kurono、kishimoto、hardsuit、x-gun、z-gun、ガンツ、杀戮都市；
  - 按简介搜：gantz、ガンツ；
  - 已知做过 GANTZ mod 的 23 个上传者，把他们的 mod 全部翻了一遍。
- **其他站点**：GameBanana 搜索接口、Steam 创意工坊接口、Patreon 公开帖子接口、gta5-mods.com、BOOTH，再加通用网页搜索。
- 2026-09-25、09-26 各搜过一次，这里把那两次的结果和这次新找到的合在一起。

## 一、已经有的（不重复做）

| mod | 游戏 | 在哪 |
|---|---|---|
| [#967 Tifa - Gantz Suit](https://www.nexusmods.com/finalfantasy7remake/mods/967) | FF7 重制版 | `E:\game_export\FF7Remake\Tifa\pmx\mod967_*` |
| [#1707 Tifa Gantz Basic Suit](https://www.nexusmods.com/finalfantasy7remake/mods/1707) | FF7 重制版 | `E:\game_export\FF7Remake\Tifa\pmx\mod1707_*` |
| [#817 GANTZ Basic Suit (Tifa)](https://www.nexusmods.com/finalfantasy7rebirth/mods/817) | FF7 重生 | `E:\game_export\FF7Rebirth\Tifa\pmx\mod817_*` |
| [#1613 Gantz - Reika (DRESSCODE)](https://www.nexusmods.com/finalfantasy7rebirth/mods/1613) | FF7 重生 | `E:\game_export\FF7Rebirth\Reika\pmx\mod1613_*`（5 个版本，另有表情移植版） |
| [#3561 Gantz Reika (CNS)](https://www.nexusmods.com/stellarblade/mods/3561) | 星刃 | `E:\game_export\StellarBlade\Reika\pmx\Mod_GantzReika_A` / `_B` / `_Layers` |
| [#11065 Reika Hardsuit - Gantz](https://www.nexusmods.com/eldenring/mods/11065) | Elden Ring | `E:\game_export\EldenRing\Reika\`（2026-11-01，完整版 + `_无外骨骼`） |
| 「18」系列 GANTZ 包（用户下载的 PMX） | MMD | `E:\game_export\_18系列_ウィンク修正\2026.6\2026gantz\`（34 个） |

## 二、用现有工具能转的（候选）

| # | mod | 游戏 | 作者 / 日期 / 下载量 | 怎么转 | 要什么 |
|---|---|---|---|---|---|
| A | [Tifa Gantz (nude jiggle physics 9 sets)](https://www.nexusmods.com/eldenring/mods/4684) | Elden Ring #4684 | shintheweapon，2024-03-08，1.68 万；成人向，3 种颜色 × 3 套 | `scripts\eldenring\export_mod.py`（今天写的） | 用户登录 Nexus 下载 zip |
| B | [DOA Naotora Gantz set](https://www.nexusmods.com/eldenring/mods/1196) | Elden Ring #1196 | az3163693，2022-05-18，589；DOA 井伊直虎穿 GANTZ 服，替换 ECCENTRIC 套 | 同上 | 同上 |
| C | [Gantz Sling suit](https://www.patreon.com/posts/134367203) | 星刃（不在 Nexus） | Patreon「m.tsqn」，2025-07-18，免费帖；4 个包：`gantz_sling_suit.zip`、`gantz_sling_suit_more_jiggle.zip`、`breaks_zss_suit_gantz_sling_suit_red_keyhole_suit.zip`、`breaks_zss_suit_gantz_sling_keyhole_dress.zip` | 星刃那条流程（`scripts\stellarblade`：解包 → 组装 Eve → 独立 .blend → XPS / PMX） | 不用登录就能下，但 Patreon 下载很慢（实测 25–40 KB/s，一张 3–6 MB 的预览图两三分钟），可以挂后台下 |
| D | [[AI/HS2] Outfit - Gantz Suit](https://www.patreon.com/posts/65578906) + [Gantz 场景和预设](https://www.patreon.com/posts/66057257) | HoneySelect 2 / AI 少女 | GGAdams，2022-04 / 05，免费帖 | `scripts\honeyselect2`（HS2 转 PMX 现在是另一个窗口在做，要先和它商量） | 接口里只看到预览图，没有附件；下载地址可能在正文的外链里（接口读不到），要人去页面上看 |
| E | [gantz suit (female)](https://www.patreon.com/posts/42572478)、[gantz suit (male)](https://www.patreon.com/posts/42572718)、[gantz room](https://www.patreon.com/posts/42593192)、[Gantz item (ver.1.1)](https://www.patreon.com/posts/41156825) | Honey Select（一代） | hankokoli，2020-09 / 10 | 本机没有 Honey Select 一代的流程 | 帖子里只有预览图；作者说下载 / 新闻在 pixiv（users/12346193）和 Discord |
| F | [Tifa Gantz (jiggle and hair physics, weapon included)](https://www.nexusmods.com/sekiro/mods/1838) | 只狼 #1838 | shintheweapon，2024-03-24，6062；成人向，全包 / 比基尼 / 裸体三种 | 和 Elden Ring 同一家的格式，`scripts\eldenring\fromsoft.py` 大概只要小改（只狼的材质是 MTD 不是 MATBIN，贴图槽名字不同），没试过 | 用户登录 Nexus 下载 |

## 三、别的游戏（本机没装、没有对应流程，或只是给游戏人物换衣服）

**2026-09-26 以后新出的、或上次漏掉的：**
- [RE3 重制版 #1166 Reika Outfit For Jill with Physics (RTX Update)](https://www.nexusmods.com/residentevil32020/mods/1166)：Gugabike，2026-02-15，2.45 万，成人向（老的 [#324 Reika](https://www.nexusmods.com/residentevil32020/mods/324) 有 21.9 万下载）。
- [NTE（异环）#94 Daffodil Gantz Suit](https://www.nexusmods.com/ntenevernesstoeverness/mods/94)：nemix94，2026-10-18。[GameBanana](https://gamebanana.com/mods/729279) 上也有。
- 辐射 4：[#99154 Fusion Girl 体型](https://www.nexusmods.com/fallout4/mods/99154)（2025-12）、[#100140 男款](https://www.nexusmods.com/fallout4/mods/100140)（2026-01）、[#100994 匈牙利语](https://www.nexusmods.com/fallout4/mods/100994)（2026-02）。
- GTA 5：[DOA5LR Naotora Ii - Gantz Outfits [Add-On Ped]](https://www.gta5-mods.com/player/doa5lr-naotora-ii-gantz-outfits-dl)，X-MAN，2018，1.58 万。它是从 DOA5LR 搬过去的，原版 DOA5LR mod 没找到；本机有 DOA5LR 的流程。
- FF15（Steam 创意工坊）：[Gantz Suit (Ignis)](https://steamcommunity.com/sharedfiles/filedetails/?id=1674808877)、[Gantz Suit (Prompto)](https://steamcommunity.com/sharedfiles/filedetails/?id=1674812349)，2019，男装，模型出自 lococr98。
- Half-Life 2（GameBanana）：[Korin GANTZ](https://gamebanana.com/mods/526132)，Wovikoff，2024-07。
- VRChat（BOOTH）：只有一把 GANTZ 剑的道具，¥500。

**以前就知道的：**
- 生化 4 重制版：[#1179 AG Gantz Suit](https://www.nexusmods.com/residentevil42023/mods/1179)（3.9 万）、[#3252 ada gantz tight suit](https://www.nexusmods.com/residentevil42023/mods/3252)、[#4739 Ada - Gantz Suit](https://www.nexusmods.com/residentevil42023/mods/4739)。
- 赛博朋克 2077：[#13282 Gantz Outfit and Sword](https://www.nexusmods.com/cyberpunk2077/mods/13282)（17.4 万）。
- 辐射 4：[#86781 KSKNP Gantz bodysuit](https://www.nexusmods.com/fallout4/mods/86781)（2.8 万）、[#49152 Reika](https://www.nexusmods.com/fallout4/mods/49152)、[#81626 3BBB 转制](https://www.nexusmods.com/fallout4/mods/81626)。
- 天际：[LE #67567 Gantz Suits 7B](https://www.nexusmods.com/skyrim/mods/67567)、[SE #121985 EVR REIKA](https://www.nexusmods.com/skyrimspecialedition/mods/121985)。
- 上古卷轴 4：[#39333 BBB for Neo Gantz Suits](https://www.nexusmods.com/oblivion/mods/39333)、[#18339 The Gantz Mod](https://www.nexusmods.com/oblivion/mods/18339)。
- 街霸 6：[#2326 Chun Li Gantz Suit](https://www.nexusmods.com/streetfighter6/mods/2326)、[#1126 GANTZ:O 怪物](https://www.nexusmods.com/streetfighter6/mods/1126)。
- 其他：[怪物猎人荒野 #2295](https://www.nexusmods.com/monsterhunterwilds/mods/2295)、[地狱潜者 2 #5597 Reika](https://www.nexusmods.com/helldivers2/mods/5597)（用的是 R2 Studio 的模型）、[Head Collector VR #14](https://www.nexusmods.com/headcollectorvr/mods/14)、[生化 Resistance #299](https://www.nexusmods.com/residentevilresistance/mods/299)、[辐射 NV #45183 Gantz Weapons](https://www.nexusmods.com/newvegas/mods/45183)。

## 四、没找到的、名字撞车的

- 2019 年 Steam 讨论帖里提过一个《怪物猎人：世界》的 GANTZ 女猎人 mod，Nexus 上已经找不到了（大概下架了）。
- GameBanana 上 P5R、P3R、暗喻幻想、火焰纹章 Engage、Sven Co-op 只有「求 GANTZ mod」的帖子，没有成品。
- 和 GANTZ 无关、只是名字撞了：
  - 天际「Reika Follower」、Kitami Reika（圣经黑）、Kurumu Kurono（吸血鬼新娘）、GTA 三部曲「Reika (DOAXVV)」；
  - KS Hairdos 里叫「Gantz」的发型、上传者 Gantz79 / Gabriel Gantz。

## 五、可以买的高精度模型（2026-11-01 查过）

- **R2 Studio「Reika - Gantz」**：$49.99，[ArtStation 商店](https://r2studio.artstation.com/store) / [CGTrader](https://www.cgtrader.com/3d-models/character/woman/reika-shimohira-gantz-2d21dadd-801b-4beb-9371-b4d1f40d42af)。
  - 65,876 三角面、4K 贴图，身体和脸都绑好骨骼；Blender 4（MustardUI）+ UE5；两套衣服。
  - 许可：禁止转卖、禁止做成 VRChat 形象。
  - 能找到的里面最精致、最像原作的玲花，可以走星刃 mod 那条路转 PMX / XPS。

## 六、要讨论的

1. **A、B（Elden Ring）**：要不要做？Tifa 那个 9 套是全转，还是挑几套？需要用户登录 Nexus 下载。
2. **C（星刃 Gantz Sling suit）**：要不要挂后台下载？4 个包全要，还是只要普通版？
3. **D（HS2）**：要不要做？HS2 转 PMX 现在归另一个窗口，要先跟它商量；下载地址得有人去帖子页面上看。
4. **E（Honey Select 一代）**：本机没有一代的流程，值不值得为它新写一条？
5. **F（只狼）**：要不要试着把 Elden Ring 的工具扩展到只狼？
6. **第三节里的别的游戏**：本机都没装，大多是给游戏人物换衣服（生化 4 / 生化 3 / 辐射 / 天际），要转得先有游戏文件和对应流程。要不要挑一两个做？
7. **R2 Studio 的付费玲花**：要不要买？
