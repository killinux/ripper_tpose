# CRISIS CORE –FINAL FANTASY VII– REUNION（CCFF7R）：模型列表与导出

Steam 版（App 1608070，build 10871899）。游戏是 **Unreal Engine 4.27.2**，资源在 IoStore 容器
（`.utoc/.ucas`）里，pak 索引 **AES 加密**，属性是**未版本化**（unversioned）序列化，所以三样东西缺一不可：

| 需要 | 在哪 | 说明 |
|---|---|---|
| CUE4Parse CLI | `E:\tools\cue4parse_cli_ff7\cue4parse.exe` | FF7 Rebirth 那套打过补丁的 CLI（`scripts/final/cue4parse_ff7_mod_tangents.patch`），`-g GAME_UE4_27` |
| AES key | `E:\tools\ccff7r\_keys\ccff7r_aes.txt`（或环境变量 `CCFF7R_AES_KEY`） | 仓库里**不存**；用 `scripts/firstdescendant/find_aes_key.py` 从 exe 找（见下） |
| usmap | `E:\tools\ccff7r\mappings\CCFF7R-4.27-20221217-Mappings.usmap` | 没有它 CUE4Parse 连包头都不读（`Could not load standard asset`） |
| Blender 3.6 | `D:\Program Files\blender-3.6.15-windows-x64\blender.exe` | 需装 `io_scene_psk_psa`（导 PSK） |

路径都可以用环境变量改：`CCFF7R_GAME_DIR`、`CCFF7R_CLI`、`CCFF7R_AES_KEY_FILE`、`CCFF7R_USMAP`、
`CCFF7R_EXPORT_ROOT`、`CCFF7R_BLENDER`（见 `ccff7r_common.py`）。

## 一次性准备

1. **AES key**（41 秒）：key 不是连续常量，是指令里拼出来的（和 TFD、Vindictus 一样），
   通用查找脚本能直接找到：

   ```powershell
   python scripts\firstdescendant\find_aes_key.py `
     --exe "E:\SteamLibrary\steamapps\common\CCFF7R\CCFF7R\Binaries\Win64\CCFF7R-Win64-Shipping.exe" `
     --pak "E:\SteamLibrary\steamapps\common\CCFF7R\CCFF7R\Content\Paks\pakchunk0-WindowsNoEditor.pak" `
     --out "E:\tools\ccff7r\_keys\ccff7r_aes.txt"
   ```

   输出里 `pak v11, encrypted index=1`，最后一行 `KEY 0x...`。不带 key 时 CLI 列出 **0** 个资源。
2. **usmap**：社区归档 [TheNaeem/Unreal-Mappings-Archive](https://github.com/TheNaeem/Unreal-Mappings-Archive)
   的 `CCFF7R/Mappings.usmap`（2022-12-17 上传，发售后第 4 天；803,588 字节，
   SHA256 `9bcc66952ddc6a494ae2bcffe9bcf299e0b20128c3e18d5ca0a70b41f67f469e`），另存为上表的文件名。
   它比当前 build 旧，但我们读的 SkeletalMesh / Texture2D / MaterialInstanceConstant 都是引擎类，
   布局没变，实测全部能解析。以后游戏大更新导致解析失败，再用 UE4SS 的 `DumpUSMAP()` 在游戏里现导一份
   （做法同 [FF7 Rebirth](../../docs/final-fantasy-vii-rebirth-extraction.md) 第 2 节）。

## 用法

```powershell
cd scripts\ccff7r
python list_models.py                    # 全部 266 个模型，按类别分组，标出已导出的
python list_models.py --category named   # 只看主要角色（34）
python list_models.py --find tifa zack*  # 按 id / 英文名 / 中文名 / 组名找，支持通配符
python list_models.py --details          # 另外读出顶点数、三角面、材质槽、身高（读全部网格约 7 秒）
python list_models.py --json

python export_model.py tifa              # 导出一个
python export_model.py tifa aerith zack_s12
python export_model.py Zack              # 一个组：zack_s11 / s12 / s13 / s21 / costa 全部
python export_model.py --category named  # 整个主要角色类
python export_model.py tifa --force      # 已有 .blend 时重做
python export_model.py tifa --views      # 额外渲 6 个角度 + 4 张脸部特写到 _work\views\tifa\
python export_model.py tifa --sw         # 导 "_SW" 版（同一网格，简化材质）
python export_model.py tifa --xps --pmx  # 另出 XPS 和 MMD PMX（已有 .blend 就直接转换）
python export_model.py --category npc --preview-only   # 只渲预览图到 _work\previews（不存 .blend），快速看一批

python -m unittest discover -s tests     # 离线测试（不需要游戏 / Blender）
```

一个模型从游戏到 `.blend` 约 6–10 秒。

## 输出

```
E:\game_export\CCFF7R\
  <组>\blend\<id>\<id>.blend           贴图全部打包进去，目录可以单独拷走（归档约定）
  <组>\blend\<id>\<id>_preview.png     全身正面（EEVEE）
  <组>\blend\<id>\<id>_face.png        脸部特写
  <组>\xps\<id>\<id>.xps               XPS（XNALara），+ 烘好的贴图、法线贴图、.report.txt
  <组>\pmx\<id>\<id>.pmx               MMD，+ textures\、<id>_converted.blend、preview.png / preview_dance.png /
                                       preview_gaze.png / preview_morphs.png（导回 Blender 套舞蹈跑物理渲的）
  _meta\packages.txt (+ .sig)          游戏全部 70,666 个包路径的缓存；容器大小 / 时间一变就重新列
  _meta\model_list.md / .json          list_models.py 写的清单
  _meta\exports.json                   每次导出的记录（时间、面数、材质、警告）
  _work\raw\    CLI 导出的 PSK + PNG（缓存，可删，需要时重导）
  _work\props\  材质实例 / 网格的 JSON（-f json）
  _work\specs\  每个模型交给 Blender 的规格文件 + Blender 日志
  _work\views\  --views 的多角度图
  _work\previews\  --preview-only 的预览图（全部 NPC / 召唤兽 / 敌人都渲过一遍）
  _meta\female_models.png              全部女性模型一张总览
```

组（角色文件夹）：同一个人的几个造型放一起（`zack_s11` … `zack_costa` → `Zack`，`tian` / `tian_costa` → `Cissnei`），
NPC 放 `NPC`，敌人放 `Enemy_<种类>`（`behemoth1` → `Enemy_Behemoth`），道具放 `Objects`。

## 游戏里的资源结构

| 类别 | 路径 | 数量 |
|---|---|---:|
| named 主要角色 | `CCFF7R/Content/Fair/Character/01_named/<id>/` | 34 |
| limit 召唤兽（DMW） | `…/02_limit/<id>/`（凯特·西、陆行鸟、莫古利） | 3 |
| npc | `…/03_mob/<id>/` | 41 |
| enemy 敌人 | `…/04_enemy/<id>/` | 121 |
| object 道具 / 武器 | `CCFF7R/Content/Fair/Object/<id>/`（破坏剑、正宗、车、直升机……） | 67 |

每个角色文件夹：`Mesh\SK_CH_<id>`（骨骼网格）、`SK_CH_<id>_SW`、`SKL_CH_<id>`（骨架）、`PH_SK_CH_<id>`（物理）、
`Material\MI_CH_<id>_*`（`CutScene\*_CS` 是过场用的同名材质）、`Texture\T_CH_<id>_*_{BC,NM,MM1,MM2}`、`Animation\`。

- **`_SW` 版**：几何和主模型**完全一样**（Tifa 两个 LOD0 都是 30,086 顶点），只是材质换成父材质 `*_Lite` 的简化版，
  估计是 Switch 版资源。默认导主模型。
- 内部名：`tian` 是西丝妮（Cissnei），`zack_s1x` / `s2x` / `costa` 是扎克斯的几个造型，`*_worse` 是剧情后期的变化形态。
  游戏的 `Localization\Game\*.locres` 是空的，名字对照是脚本里手写的表（`ccff7r_common.NAMED`）。
- 骨架：Maya HumanIK 风格（`Hips`、`Spine`、`LeftUpLeg`…），带 `_chn` / `_eff` / `_skt` / `_string` 辅助骨，
  脸是 `hi_*` 骨骼（`hi_eye_L`、`hi_upperlip_R1`…）+ `AS_<id>_fcm_*` 表情动画，**没有** morph target。
- **武器是身体网格的一部分**：扎克斯的破坏剑、萨菲罗斯的正宗、西丝妮的手里剑挂在 `wpn` / `wpn_body` / `pivot`
  骨上，这几根骨在绑定姿势里都在原点，所以 T 姿势下武器平躺在脚边（游戏靠动画把它们带到手上或背上）。
  导出时把只跟随这些骨的面拆成单独的 `<id>_weapon` 物体（仍然蒙皮在同一副骨架上），预览图里不渲染它。

## 材质还原

CLI 按网格导出时，材质文件写的是空的 `{}`（和 FF7 Rebirth 一样），所以另用 `-f json` 把网格和每个材质实例
（沿 `Parent` 一路到公共父材质）导成 JSON，**子覆盖父**合并参数——实例没改的值（比如 `MI_ch_Human_Skin` 的毛孔贴图、
`MI_ch_Human_Mouth` 的牙齿贴图）也能拿到。1,945 个角色材质实例全部来自 8 类公共父材质，按父材质（`MI_ch_*` / `M_ch_*`，
小写 ch；角色自己的是大写 `MI_CH_<id>_*`，名字不可靠）定家族：

| 家族 | 父材质 | 还原（通道都在贴图上量过） |
|---|---|---|
| standard | `MI_ch_Standard` / `EMStandard`（`M_ch_StandardSS`） | `Tex_Color` 底色；`Tex_MultiMask` **R = 金属度**（破坏剑刃口、护肩包边、铆钉扣件是亮的），**G = 粗糙度**（`Roughness_Min..Max`），**B = AO**；`Tex_BakedNormal`（DirectX，翻 G）；`Tex_2ndMultiMask`（`_MM2`）**R = 自发光遮罩**（`Emi_ONOFF`，× `EmissiveColor` × `Emi_Int`）。`Masked` 且实例没设 `UseMaskDisable` 才用 BC 的 alpha 裁切（阈值 `OpacityMaskClipValue` 0.3333） |
| skin | `MI_ch_Human_Skin` / `Human_Mouth` | `AlbedMap` × `BaseColor_Tint`；`MultiMaskMap` **R = 次表面量**（皮肤约 0.58，头皮 0，口腔 1），G = 粗糙度，B = AO（头部 B 通道还烘着刘海的投影）；`BakedNormalMap`；毛孔：`PoreSpec` 平铺 `PoreTiling` 次做凹凸，`PoreMask`（`_MM2` 的 G）限定范围 |
| hair | `MI_ch_Hair`（`M_ch_Hair` / `HairSimple`） | `Tex_BaseColor` 的 alpha 是发丝遮罩（HASHED 半透明）；`Tex_Multi` B = 逐根 AO；`Roughness`；高光 × 0.6；颜色 × `Brightness^0.15`（见下） |
| eye | `MI_ch_Eye2_ad` | `Tex_Colormap` 是**完整眼球**贴图（眼白 + 虹膜 + 瞳孔，不像 Rebirth 只有虹膜），直接用，光滑 |
| eyelash | `MI_ch_Eyelash` | `Tex_Color` × `Color_Tint` × `Color_Int`，alpha 是睫毛形状 |
| glass | `MI_ch_Glass` | `Color_Tint`（× `Tex_Color`），25% 不透明 |
| gem | `MI_ch_GemStandard` | `Color_Main` + `Add to emissive`（巨型魔晶石敌人） |

**同一张贴图两种用法**：Tifa 的 `T_CH_tifa_body_MM1` 同时给衣服（standard）和露出的皮肤（skin，`MI_CH_tifa_skin`）用。
皮肤区域 R≈0.58 在 skin 里是次表面量；衣服的面基本不落在皮肤区域上。实测（每个面 UV 中心取 R）：Tifa 衣服 92% 的面
R<0.1、3.4% >0.65（银扣、铆钉）；扎克斯、爱丽丝、西丝妮、萨菲罗斯、NPC 女孩的衣服 80–100% R<0.1；西丝妮的手里剑
93% >0.65，正宗 40% >0.65（刃口）——和"R = 金属度"一致。

**头发亮度**：实例的 `Brightness`（Tifa 3.35）是给 UE 的 `MSM_Hair` 着色模型补亮的，那个模型的漫反射比 Lambert 暗得多；
原样乘到 Principled BSDF 上，黑发渲出来是中灰。对比渲染后改成 `Brightness^0.15`（3.35 → 1.2，默认 1 不变），高光取实例值的 0.6 倍。

## XPS / PMX

`--xps` / `--pmx` 从做好的 `.blend` 转（两边都会把 `<id>_weapon` 武器物体去掉，`--keep-weapon` 可保留）：

- **XPS**（`export_xps_blender.py`）：调隔壁仓库 [blender2xps](../../../blender2xps)，×0.01 转成米（Tifa 高 1.638）。
  CCFF7R 的骨骼是 HumanIK 命名（`Hips`、`Spine1`、`LeftForeArm`、`LeftHandThumb1`……），blender2xps 的别名表本来就认，
  直接改成 XPS 标准骨名，XPS 姿势能套。节点里的颜色（底色 × AO × 色调）烘成一张 `*_baked.png`。脸和皮肤的法线
  接在毛孔凹凸节点后面，blender2xps 只认直连的法线贴图，所以这两个材质的 XPS 不带法线贴图。
- **PMX**（`export_pmx_blender.py`）：沿用 FF7 / Stellar Blade 那条链（mmd_tools 写 PMX、Convert_to_MMD5 建 MMD
  骨架和身体刚体、mmd_cloth_physics 做头发和布料），这里只补 CCFF7R 骨架需要的：
  - HumanIK → MMD 槽位：`Hips` 下半身、`Spine` / `Spine1` 上半身 / 上半身2、`Neck`、`Head`、`hi_eye_L/R` 两眼、
    四肢和手指按名字对；
  - **镇民 / 村民 / 职员 / 女孩这些 NPC 骨架没有脖子**（头直接挂在 `Spine1` 上）、没有手指和脚趾：在肩膀上方到
    头部支点之间补一根不带权重的 `Neck`（MMD 必须有 首）；
  - 脸部骨（`hi_face` 下除两眼外的眼皮、眉、唇、下巴、舌头）并进 `Head`：还没做表情 morph，不并的话转换器会把
    这些皮肤分给眼球骨；
  - Tifa 的胸部链 `L_bustB → L_bustA` 合成一根（A 并进 B），挂 Eve 那套胸部物理（每侧一个球形刚体 + 弹簧关节）；
    其他模型没有胸部骨；
  - 转换器认不出的缩写先改名：`*_skt*` → `*_skirt*`、`ribon` → `ribbon`、`mant` → `mantle`、`Cloth` → `Cloak`；
    `Roll` / `Sub` 结尾的手臂腿部扭转辅助骨标成四肢辅助骨（不当布料），Convert_to_MMD5 会把它们接成
    腕捩 / 手捩 和按比例跟随的辅助骨。
  转换完 `preview_pmx_blender.py`（Stellar Blade 目录）把 PMX 导回 Blender、套一段舞蹈动作逐帧跑物理，渲
  `preview_dance.png` 等；报告里的 `torn`（撕裂的边）应为 0。

## 女性角色（21 个模型）

2026-09-26 逐个看过全部 266 个模型的预览（`--preview-only`）后确认：

| 类别 | id |
|---|---|
| 主要角色（5 人 6 个） | `tifa` 蒂法、`aerith` 爱丽丝、`tian` 西丝妮（塔克斯西装）、`tian_costa` 西丝妮（太阳海岸泳装）、`yuffie` 尤菲、`gillian` 吉莉安 |
| NPC 成年女性（10） | `npc_townb` `npc_townb2` `npc_townb3` `npc_townb_lw` `npc_townb_lw2` `npc_townb2_lw`（镇民）、`npc_vlgb` `npc_vlgd`（村民）、`suit_woman` `suit_woman2`（职员） |
| NPC 女孩（4） | `npc_girl` `npc_girl2` `npc_girl_lw` `npc_girl2_lw` |
| 敌人（1） | `minerva` 女神米涅瓦（全身甲，脸在头盔里） |

规律：NPC 名字里 `b` / `d`（`townb`、`vlgb`、`vlgd`）是女性，身高 168–170 cm；`a` / `c` 是男性，184–187 cm。
`npc_girl_lw2` 是没贴图的白色低模占位，不算。只有 Tifa 的骨架有胸部骨。

2026-09-26 全部导出：`.blend` 21、XPS 21、PMX 20（`python export_model.py <id...> --xps --pmx`，3 个进程并行约 25 分钟，
共 2.25 GB）。PMX 撕裂全为 0；总览 `E:\game_export\CCFF7R\_meta\female_pmx_check.png`（每行：`.blend` 预览、PMX 静止、4 帧舞蹈）。
- 米涅瓦没有 PMX：翅膀、旗帜、弓的骨骼前后伸得比身高还远，转换器判她"不是站立的"直接拒绝（她是一整座全身甲 Boss）。
- 尤菲的短发是单节骨、头上的丝带挂在头部下面，布料插件不给它们加物理，MMD 里是硬的。
- NPC 只有身体碰撞体（15–17 个刚体）；手是整块（游戏里就没有手指骨）。

## 已知限制

- 预览是近似：UE 的眼睛折射（`MSM_Eye`）、头发各向异性高光、次表面轮廓（SubsurfaceProfile）、眼睛的假高光
  （`FakeSpec*`）都没还原。
- `*_StackTranslucent` 头发材质（半透明叠层）在网格上没有对应的面，只列在材质槽里，不用。
- 过场材质 `*_CS` 不用；表情是骨骼动画，没导。
- 单位保持 UE 的厘米（Tifa 高 163.8），和 FF7 Rebirth / TFD 的 `.blend` 一致，以后可以直接套 XPS / PMX 转换。
- 静止姿势是 T 字。

## 踩过的坑

- **CLI 并行导出撞文件**：两个通配符匹配到同一个包（比如 `*/MI_*` 和 `00_Common/Materials/*` 都含 `MI_ch_Hair`），
  CLI 并行写同一个 JSON，`IOException` 后整批中止。`export_packages()` 先去重再用 `-c 列表文件` 导。
- CLI 写的 JSON 带 UTF-8 BOM，读的时候用 `utf-8-sig`。
- 在 Bash 里用 `sed` 改含反斜杠的 Windows 路径会把 `\r`、`\C` 这类吃掉；改文件用编辑工具。
