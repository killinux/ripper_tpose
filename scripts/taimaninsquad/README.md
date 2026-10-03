# Taimanin Squad（対魔忍スクワッド）：模型列表与导出

Steam 版（GREMORY Games，`E:\SteamLibrary\steamapps\common\Taimanin Squad`）。**Unity 2022.3.62f3 + IL2CPP + URP**，
资源全部在 `TaimaninSquad_Data\StreamingAssets\aa\`：一份 Addressables 目录 `catalog.json`（6 万条）和 999 个普通
UnityFS bundle（LZ4HC，**没加密**，3.7 GB）。角色是 3D 蒙皮模型（3ds Max Biped 骨架 + 表情 blend shape），
用游戏自己的卡通着色器 `Squad/SquadToon` 渲染。

这套脚本做三件事：

| 脚本 | 做什么 |
|---|---|
| `list_models.py` | 列出全部 252 个 3D 单位（角色 117、其他造型 19、怪物 88、特殊 3、Boss 22、序章杂兵 3），标出哪些已导出；`--html` 出画廊页 |
| `export_model.py` | 导出 **卡通着色的 .blend**（游戏着色器逐项还原 + 描边），`--xps` 出 XPS，`--pmx` 出 MMD PMX（骨架、物理、表情） |
| `dance_video.py` | 给导出的 PMX 套一段 MMD 动作（`.vmd`）渲成带配乐的视频，并存一份能直接打开播放的 `.blend` |
| `export_backgrounds.py` | 把游戏里的背景图（剧情背景、过场画、天空全景 ……）挑好的 128 张导到一个文件夹，带总览图 |
| `html/make_gallery.py` | 画廊页 `html/index.html`：导出过的显示预览图和文件位置，没导出的显示预览渲染（或游戏头像）和导出命令；页首是「手动操作说明」 |

辅助脚本：`rig_lint.py`（检查骨架：肢体的皮是否跟着 Biped 骨、有没有哪段肢体根本没有皮）、`dump_shader.py`（着色器反汇编）、
`preview_xps_blender.py` / `preview_pmx_morphs.py` / `render_turntable.py`（导出后的读回检查图和转台视频，
`export_model.py` 会自动调用）。

## 需要的东西

| 需要 | 在哪 | 说明 |
|---|---|---|
| Python 3 + `UnityPy` `lz4` `numpy` `Pillow` | `pip install UnityPy lz4 numpy pillow` | 读 bundle、解贴图；不需要 AssetStudio / AssetRipper |
| Blender 3.6 | `D:\Program Files\blender-3.6.15-windows-x64\blender.exe` | 出 `.blend` 只用它本身（`--factory-startup`，不依赖任何插件） |
| Blender2XPS | 隔壁仓库 `..\blender2xps` | `--xps` 用；读回检查用 XNALaraMesh 插件 |
| mmd_tools、Convert_to_MMD5、mmd_cloth_physics | Blender 插件（后者在 `scripts\blender_addons`） | `--pmx` 用，和 Rise of Eros / FF7 / Stellar Blade 的 PMX 是同一条转换链 |

路径都可以用环境变量改：`TSQUAD_GAME_DIR`（游戏目录）、`TSQUAD_EXPORT_ROOT`（默认 `E:\game_export\TaimaninSquad`）、
`TSQUAD_BLENDER`、`BLENDER2XPS`。**不需要 key、不需要启动游戏、不需要联网。**

## 用法

```powershell
cd scripts\taimaninsquad
python list_models.py                       # 全部 252 个单位，按类别分组，标出已导出的格式
python list_models.py --category character  # 只看一类（character / costume / monster / special / boss / mob）
python list_models.py --find asagi 24 kira* # 按 id / 单位编号 / 名字找，支持通配符
python list_models.py --details             # 另外读出部件数、顶点、三角面、蒙皮骨、表情数、身高、是否女性体型（约 20 秒，有缓存）
python list_models.py --female              # 只列女性体型（148 个：140 个有胸部骨 F + 8 个看预览认的 f，见下）
python list_models.py --exported            # 只列已导出的
python list_models.py --html                # 生成画廊页 html\index.html（预览图 + 导出命令 + 手动操作说明）

python export_model.py 24_kirara            # 导出一个：.blend + 全身 / 脸部预览 + 表情总览图
python export_model.py asagi                # 一个角色的全部造型（1_asagi、253_asagi、271_asagi）
python export_model.py 24_kirara --xps --pmx        # 另出 XPS 和 MMD PMX（已有 .blend 就直接转换）
python export_model.py 24_kirara --turntable        # 另渲一段转台视频（转一圈 + 脸部特写扫光）
python export_model.py --female --xps --pmx --turntable --jobs 4   # 全部女性体型，4 个同时跑（见「批量导出」）
python export_model.py 24_kirara --views            # 另渲 5 个全身角度 + 4 个脸部角度到 _work\views\24_kirara
python export_model.py --category character --preview-only   # 只渲预览图到 _work\previews（不存 .blend），快速看一批
python export_model.py 212_dullahan --xps --pmx --weapons   # 连武器 prefab 一起导（刀、枪、肩甲、头饰；见「武器 prefab」）
python export_model.py 20_natsume --weapon-grade 1  # 武器的升级外观（0 初始 / 1 / 2）
python export_model.py 130_orc1 --xps --pmx --keep-weapon   # XPS / PMX 里带上停在原点的武器（见「已知限制」）
python export_model.py 24_kirara --force            # 已有产物时重做（.blend、转台视频、XPS、PMX 全部）
python export_model.py 24_kirara --xps --pmx --reconvert   # 只从现有 .blend 重做 XPS / PMX（转换脚本改过之后用）
python export_model.py 24_kirara --xps --pmx --repreview   # 只重渲 XPS / PMX 的检查图（预览脚本改过之后用）

python dance_video.py 1_asagi --vmd "E:\Downloads\mmd\<动作文件夹>"   # 给 PMX 套 MMD 动作渲视频（见「舞蹈视频」）

python export_backgrounds.py                        # 游戏里的背景图：挑好的 128 张 → E:\game_export\TaimaninSquad\_backgrounds
python export_backgrounds.py --list                 # 只列出这 128 张各自来自 catalog 的哪个地址
python export_backgrounds.py --all                  # 另把背景相关文件夹里的全部图片也导出来（_backgrounds\全部\，523 张）

python rig_lint.py                                  # 检查每个单位的肢体：皮是否跟着 Biped 骨、有没有缺胳膊少腿（约 5 分钟）
python rig_lint.py --weapons none                   # 只看单位 prefab 本身：列出肢体放在武器 prefab 里的单位
python dump_shader.py Squad/SquadToon --asm         # 把游戏着色器反汇编成文本（还原材质时用的）
python -m unittest discover -s tests                # 离线测试（不需要游戏 / Blender）
```

一个模型从游戏到 `.blend` 约 5–10 秒；XPS 约 15 秒；PMX（含舞蹈物理预览）约 1 分钟；转台视频约 40 秒。
全套（`--xps --pmx --turntable`）单独跑约 1.5–2 分钟。

### 批量导出

- `--category <类>`、`--female`、`--all` 选一批；可以和具体的 id 混着写。
- `--jobs N`：同一条命令起 N 个进程，各拿名单里每隔 N 个的那一份（输出行前面的 `3|` 是进程号）。
  实测 6 个并行时每分钟出约 2 个全套模型（瓶颈是几个 Blender 抢同一块显卡渲预览）。
  想分开在几个终端里跑就用 `--shard 1/4`、`--shard 2/4` ……（`--jobs` 给子进程的就是它）。
- **可以随时停、随时续**：已经存在的 `.blend` / `.xps` / `.pmx` / 转台视频会跳过，`_meta\exports.json` 每导完
  一个模型就写一次。所以批量被打断后，把同一条命令再跑一遍即可；要重做某个加 `--force`。
- **女性名单**（`--female`）：游戏的配置表解不开（见下），没有性别字段可读。判断依据是**胸部骨** ——
  Magica Cloth 里名字带 Breast 的那一组的根骨，140 个单位有（清单里标 `F`）。另有 8 个女性体型没有胸部骨，
  是把其余 112 个单位的预览图逐个看过后手工列进 `tsquad_common.FEMALE_BY_LOOK` 的（清单里标 `f`）：
  `87_torajiro`、`95_shizuku`、`113_nao`（三个女孩）、`81_library` / `b_33_library`（女性外形的全身机甲）、
  `158_paladin` / `159_paladin2`（戴面具的女剑士杂兵）、`80_shikanosuke`（鹿之助：设定上是男孩子，模型是女孩外形）。

## 输出

```
E:\game_export\TaimaninSquad\
  <角色>\blend\<id>\<id>.blend             贴图全部打包进去，目录可以单独拷走（E:\game_export 的归档约定）
  <角色>\blend\<id>\<id>_preview.png       全身正面（EEVEE，游戏卡通着色 + 描边）
  <角色>\blend\<id>\<id>_face.png          脸部特写
  <角色>\blend\<id>\<id>_expressions.png   表情总览：每个 blend shape 一格
  <角色>\blend\<id>\<id>_turntable.mp4     --turntable：转一圈 + 脸部扫光
  <角色>\xps\<id>\<id>.xps                 XPS + 贴图 + .report.txt + <id>_xps_preview.png（读回 Blender 摆姿势渲的）
  <角色>\pmx\<id>\<id>.pmx                 MMD + textures\（底色图、toon 渐变、sphere 高光）+ <id>_converted.blend
                                           + preview.png（静止）/ preview_dance.png（套舞蹈跑物理的 4 帧）
                                           + preview_morphs.png（**每个 MMD 表情一格，带名字**，从 PMX 读回渲的）
  <角色>\video\<id>\<id>_<动作>.mp4        dance_video.py：套 MMD 动作渲的视频（H.264 + AAC）
                                           + 同名 .blend（模型、动作、烘好的物理、贴图和配乐都在里面）+ .json（记录）
  _backgrounds\                            export_backgrounds.py：游戏里的背景图 128 张 + _总览_<类别>_<n>.jpg（见「游戏里的背景图」）
  _meta\backgrounds.json                   每张背景图来自 catalog 的哪个地址、哪个 bundle
  _meta\model_list.md / .json              list_models.py 写的清单
  _meta\model_details.json                 --details 的缓存（按美术包文件名，游戏更新后自动失效）
  _meta\exports.json                       每次导出的记录（时间、面数、材质、警告、带上的武器 prefab、PMX 报告）
  _meta\rig_lint.json                      rig_lint.py 的结果（每个单位每段肢体的蒙皮归属、没有皮的肢体）
  _meta\gallery\icons\ thumbs\             画廊用的游戏头像和缩略图
  _meta\catalog_assets.json cab_index.json 目录和 bundle 索引的缓存
  _work\logs\                              每个模型的 Blender 日志
  _work\previews\ views\ shader\           --preview-only / --views / dump_shader.py 的产物
```

`<角色>` 是单位文件夹名里的名字：`1_Asagi`、`253_Asagi`、`271_Asagi` 都放在 `Asagi\` 下。

## 游戏里的资源结构

每个单位 `<编号>_<名字>` 有两个 bundle：

| bundle | 内容 |
|---|---|
| `localunit_aos_assets_<n>_<name>_<hash>.bundle` | **美术包**：`<n>_<Name>/Art/fbx_<n>.fbx`（网格）、`Art/Materials/`（材质 + 贴图）、`Unit/prf_<n>.prefab`（游戏实例化的单位 prefab）和它的低模孪生 `prf_<n>_LOD1.prefab` |
| `localunit_assets_<n>_<name>_<hash>.bundle` | 动作、Anievent、技能过场 Timeline、特效、武器 prefab（`Weapon/`） |

- bundle 里的容器表用 **GUID** 当键；可读地址（`24_Kirara/Unit/prf_24.prefab`）→ GUID → 所在 bundle 的对应关系在
  `catalog.json` 里（Addressables 1.x：`m_KeyDataString` / `m_BucketDataString` / `m_EntryDataString` 三段 base64）。
  `tsquad_common.parse_catalog()` 直接解析它，不需要加载任何 bundle。
- 材质引用别的包里的着色器和公共贴图（`squadtoonshader_*`、`localbundle_assets_unitcommon_*` 的 MatCap）。
  bundle 之间靠 CAB 名互相引用，`tsquad_common.cab_index()` 只读每个 bundle 的文件头就建好「CAB 名 → bundle」索引
  （999 个包不到 1 秒），用到哪个包才加载哪个包。
- **prefab 结构**（以 `prf_24` 为例）：根下并排放着渲染器 `costume_24`（身体 + 衣服）、`hair_24`、`face_24`、
  `face_24_out`（头的外轮廓）、`face_24_mouth_in`（牙和舌头），以及骨架 `Root/Bip001/...`。
- **骨架**：3ds Max Biped（`Bip001 L UpperArm`、`Bip001 L Finger01` ……）+ 扭转 / 关节辅助骨（`Bip001_B_L Elbow`
  或 `Bone_L_elbow`，两套命名都有）+ `Bone_*` 链（头发、裙子、丝带、胸）。游戏里这些链由 **Magica Cloth 2**
  的 Bone Cloth 模拟；每组的根骨、重力、阻尼脚本都读出来了，存在 `.blend` 骨架物体的自定义属性 `tsq_cloth` 里。
- **早期角色的腿不蒙在 Biped 上**：阿莎姬、不知火、飞鸟（含黑色剪影版）、胧这 5 个单位，大腿和小腿的皮
  蒙在另一条链 `Bone_L_Thigh > Bone_L_Knee_end > Bone_L_Calf` 上（挂在 `Bip001 L Thigh` 下面），游戏里每个
  动画都给这条链打了关键帧，让它和 Biped 的腿重合。离开游戏就没人驱动它了，所以导出时**把这条链的权重交给
  重合的 Biped 骨**（原骨保留为空骨；记在骨架的自定义属性 `tsq_limb_aliases` 里）。同理，不知火大腿的皮主要在
  Biped 的扭转骨 `Bip001 LThighTwist` 上，它在 3ds Max 里是大腿的**兄弟**而不是子骨，导出的骨架把它改挂到
  大腿下面。
- **特效叠加网格**：7 个单位（10_jubei、81_library、283_rin、b_8、b_13、b_16、b_33）有名字带 `EffectRender`
  的渲染器，是把身体用加算发光着色器再画一遍。`.blend` 里放在「Effects (hidden)」集合，默认隐藏，XPS / PMX 不带。
- **材质槽之外的子网格游戏不画**：Unity 用渲染器的第 i 个材质槽画网格的第 i 个子网格，子网格比材质槽多时，
  多出来的根本不画。美术用这个办法「关掉」部件：`257_shizuru` 眼镜上的白色反光镜片、`125_sokushitsuki` 的一部分脸饰、
  备用的嘴型片等，共 11 个单位。提取时把这些子网格连同只属于它们的顶点去掉（去掉了什么记在骨架的自定义属性
  `tsq_undrawn_submeshes` 里）。
- **prefab 自带的默认表情**：`SkinnedMeshRenderer.m_BlendShapeWeights` 是单位一出场时各形态键的权重。全游戏只有
  `125_sokushitsuki` 用到：角 `face_125_horn` 的 `face_125_hornsmall` = 100（戴着斗笠，角是缩小的）。`.blend` 里这个
  形态键默认值就是 1；XPS / PMX 没法让表情默认不为 0，转换时把它烘进静止形状，PMX 里留一个反向的表情
  `face_125_hornsmall_off`（拉满 = 角长回原来的大小）。
- **胸部骨的名字不统一**：`Bone_L_Bust`、`Bone_LBreast`，还有 Biped 的备用骨 `Bip001 Xtra01` / `Bip001 Xtra01Opp`
  （不知火、飞鸟）。统一从 Magica Cloth 里名字带 Breast 的那一组的根骨认（`tsq_breast_bones`），它们也是
  `list_models.py --female` 的主要依据（140 个单位；另外 8 个没有胸部骨的女性体型是看图列的，见「批量导出」）。
- **表情**：脸是 blend shape，没有脸部骨。标准的一套是 `up_eyes` `down_eyes` `left_eyes` `right_eyes` `closed_eyes`
  + 整脸表情 `smile_face` `shouted_face` `sad_face` `dissatisfied_face` `debuff_face` `signature_face` ……
  （各角色略有不同，全游戏 180 个不同的名字），少数角色有口型 `mouth_talk_A / E / O`。嘴里（`*_mouth_in`）
  有一套同名的配套形态，`.blend` 里已经改成和脸同名并用驱动器跟着脸走，拉一个滑块就行。
  **注意 `up_eyes` / `down_eyes` 拉满是翻白眼**（虹膜整个移出眼眶），游戏里只用一小部分权重。
- 泪珠、汗滴、怒气符号这些是**藏在头里面的小贴片**，由某个整脸表情把它们「飞」出来；反过来，闭嘴时的
  嘴缝线、唇下的小阴影是**平时贴在脸上、张嘴时缩进头里**的小贴片。
- 另有一套挂在头骨下的独立贴片 `em_*`（MeshRenderer，prefab 里是关着的，游戏按状态打开），`.blend` 里放在
  「Emotes (hidden)」集合里，默认隐藏，要用就取消隐藏。
- **单位 prefab 里自带的武器是刚体网格**（MeshRenderer），挂在 `Bone_RH_Weapon` 之类的骨头上。有的 prefab 里武器骨
  就在手上（死亡骑士的剑、四臂鬼的斧）；有的武器骨停在原点甚至地面以下，要等动画把它放到手里（兽人的棍子）。
  角色（和一部分怪物）的武器不在单位 prefab 里，是另一个包里的独立 prefab —— **其中有的其实是手臂和腿**，
  见下一节。
- 贴图原生就是 1024×1024（脸和身体各一套），没有更高分辨率的版本；网格用的是 LOD0。
- 怪物的网格大多开了 Unity 的 Mesh Compression（顶点流是空的，数据在 `m_CompressedMesh`），脚本两种都读。
- 配置表（`LocalLow\GREMORYGames\TaimaninSquad\Tables\*.etlb`，含角色的正式名字）是 AES 加密的，**密钥由服务器在
  登录时下发**（`EtlbSecurity` 的报错文本写的是「收到的 key 长度」），离线解不了，所以名字用的是文件夹里的英文名。

## 武器 prefab：放在武器栏里的手臂和腿

单位 prefab **不一定是完整的角色**。游戏把「武器」做成独立的 prefab，放在单位的另一个包（动作包）里：

```
<n>_<Name>/Weapon/Prefab/prf_weapon_<n>_<档>_<槽>.prefab      （各有一个 _LOD1 低模孪生）
    档：0 / 1 / 2 = 武器升级后的三种外观（不是每个槽都有 1、2）
    槽：L、R、O、R2、L2、O2、B …… 一个单位可以同时带几件
```

全游戏 142 个单位有武器 prefab，不算低模共 572 个。运行时由根节点上的 `AttachObject` 组件装到角色身上：

| 字段 | 含义 |
|---|---|
| `kBoneName` | 挂到角色骨架里叫这个名字的节点下面（`Bone_RH_Weapon`、`Bip001 L Clavicle`、`Bip001 Pelvis` ……） |
| `kInitTrans` | 1 = 挂上去后把自己的位置 / 旋转 / 缩放清零（带这个组件的 547 个里 541 个是 1） |
| `kWeaponName` | 实例改成这个名字 —— 升级外观写的也是第 0 档的名字，因为动画是按**路径**找节点的 |

（另有 25 个 `_B` 槽的 prefab 没有这个组件，只在第 1、2 档出现，脚本不处理。）

**武器栏里放的不只是刀枪。** `20_natsume` 的整条左臂、`82_tsuru` 的右前臂（一支枪）、`71_snakelady` 的双臂、
`47_saika` / `282_saika` 的双腿都是「武器」：单位 prefab 里那一段是空的，只有骨头没有皮。只导单位 prefab，
Natsume 就少一只胳膊。

这类 prefab 认得出来：它是蒙皮网格，而且**每一根蒙皮骨都叫 `Ref_<角色骨名>`**（`Ref_Bip001 L UpperArm`、
`Ref_Bip001 L Finger01` ……），是角色那根骨头在武器里的替身。证据在动画里 —— Animator 的绑定存的是节点路径的
CRC32，把候选路径算一遍去对：Natsume 的片段里 `…/Bip001 L Clavicle/Bip001 L UpperArm` 和
`…/Bip001 L Clavicle/prf_weapon_20_0_L/Ref_Bip001 L UpperArm` 两条路径都有曲线（手臂的 22 个节点都是这样），
prefab 里这两套骨头也是重合的。

导出时的做法（`tsquad_scene.Scene.add_weapons`）：

- 读完单位 prefab 后，把选中档位的武器 prefab 挂到 `kBoneName` 上；
- `Ref_<骨名>` 节点**不另建骨头**，蒙在它上面的皮直接蒙到角色自己的那根骨头上（bind pose 用武器网格自带的），
  它的子节点改挂到角色的那根骨头下面；名字和角色的骨头相同、位置也重合的节点同样处理；
- 所有蒙皮骨都落在角色骨架上的 prefab 算**身体的一部分**（`kind: limb`），**默认就带上**，在 `.blend` / XPS / PMX 里
  和身体别的部分一样跟着骨架动。全游戏 13 个单位、21 个 prefab：

  | 单位 | 武器栏里放的是 |
  |---|---|
  | `20_natsume` | 整条左臂 |
  | `82_tsuru` | 右前臂（枪） |
  | `71_snakelady` | 双臂 |
  | `47_saika`、`282_saika` | 双腿 |
  | `6_amane`、`110_denji` | 一只手 |
  | `17_yuzuriha`、`87_torajiro`（虎爪）、`129_crackle` | 双手 |
  | `102_yeager` | 双前臂和爪 |
  | `51_mari` | 双臂上的臂甲 |
  | `44_koro` | 斜挎的背带和刀鞘（蒙在脊柱上） |

  其中 10 个单位武器里的替身骨和角色的骨头在 prefab 里完全重合，另外 3 个差 3 mm – 20 cm（Yeager）；
  因为皮是蒙到角色的骨头上的，这不影响结果。`91_sensyu` 也有一对这样的手臂，但渲染器在 prefab 里是关着的
  （她本来的双臂在单位 prefab 里；这一对游戏里什么时候打开不清楚），不带。
- 其余的才是真正的武器（`kind: weapon`：自己带骨头的蒙皮网格，或刚体网格），**默认不带，加 `--weapons` 才带**。
  位置用 prefab 里的：握在手里的刀、背上的刀鞘、小臂上的刃、头饰、肩甲大多是对的；但有些靠动画摆位，prefab 里的
  姿势没法看（`59_sayaneo` 背后的爪链横着伸向一侧，`84_anje` 的触手左右伸出 4 米）；挂点停在原点的
  （Sakuya 的两件武器等，第 0 档里有 68 个 prefab）照旧放进隐藏集合「Weapons (parked)」，XPS / PMX 不带。
  `--weapon-grade 1` / `2` 换成升级后的外观（某个槽没有那一档就用它有的最高一档）。
- 带了哪些、没带哪些（和原因）记在 `.blend` 骨架物体的自定义属性 `tsq_weapon_prefabs` /
  `tsq_weapon_prefabs_left_out` 里，每个网格物体的 `tsq_weapon` 是它出自哪个 prefab；`_meta\exports.json` 和画廊卡片
  的「武器」一行也有。

怎么保证没有别的单位缺肢体：`rig_lint.py` 对每个单位的上臂 / 前臂 / 手 / 大腿 / 小腿 / 脚逐段检查「这根骨头连同它下面
所有的骨头身上有没有皮」—— 一点没有，或只剩一截断肢（不到另一侧同一段的 15%，且不到全身顶点的 1%；实测 Natsume
肩头的断口是 156 个顶点，她的右臂是 1881 个）；手再看手指骨上有没有皮，因为袖口蒙在手骨上会把缺手盖住。
`python rig_lint.py --weapons none` 只看单位 prefab，252 个单位报出 18 个：上表里除 Mari、Koro（它们缺的不是肢体）
之外的 11 个，加 7 个怪物。默认（带上身体部件）再跑，那 11 个全部消失，剩下 8 个都是本来就没有那一段的：
7 个怪物（两个穿长袍的法师没有腿和手、两只双头犬是爪子、一个左手是长刃的僵尸、机甲 Earthquake、
岩石巨人 `b_15_saturday`）和 Tsuru —— 她的右前臂是枪，没有手指。这 8 个都看过预览图。

## 着色器还原

游戏不带着色器源码，只有编译后的 D3D11 字节码。`dump_shader.py` 用系统自带的 `d3dcompiler_47.dll`
（`D3DDisassemble`）把它反汇编成文本，`Squad/SquadToon` 的 ForwardLit 片元程序读下来是这样（`.blend` 里的节点组
`TSQ Toon` 就是逐项照搬）：

```
albedo   = _BaseMap(tex_d) × _BaseColor
mask     = _MaskMap(tex_m)        R = 自发光遮罩   G = 高光遮罩   B = MatCap 遮罩
lit      = sat((N·L×0.5+0.5 − _Shadow1Step + _Shadow1Feather) / _Shadow1Feather)      ← 半兰伯特卡一刀
diffuse  = lerp(_InShadowMap(tex_s), albedo, lit)                                     ← 暗部不是「变暗」，是换成另一张画好的阴影色图
           关键字 _SHADOWCOLOR 时暗部 = albedo × lerp(_Shadow2Color, _Shadow1Color, 第二刀)
specular = _BaseMap × _SpecColor × mask.G² × lit × 卡通化的 GGX（URP 的 DirectBRDFSpecular，再用 _SpecularStep/_Feather 卡一刀）
           关键字 _HAIRSPECULARVIEWNORMAL 时改成「法线水平朝向相机」的一条竖带（紧身衣的反光）
rim      = _RimColor × sat((1−N·V − _RimStep + _RimFeather)/_RimFeather)，再按 _RimBlendLdotV 乘逆光、按 _RimBlendShadow 乘 lit（_RimFlip 时乘 1−lit）
matcap   = _MatCapMap((N_view.xy×0.5+0.5 − s)/(1−2s)) × _MatCapColor × mask.B × lit    s = _MatCapUVScale；_IgnoreShadowMatCap 时不乘 lit
color    = (diffuse + specular + rim + matcap) × 主光颜色 + albedo × 环境光(SH) + mask.R × albedo × _EmissionColor
脸（关键字 _SDFSHADOWMAP）：lit 不看法线，看 SDF 阈值图 tex_on 的 R 通道：
           K   = sat(头的前方·光 × 0.5 + 0.5)（在头的水平面里算）
           lit = 1 − sat(((1−sdf) − K − (2×_Shadow1Step−1)) / _Shadow1Feather + 1)，光在另一侧时把 U 镜像再采样
描边（Outline pass）：背面外扩的反向外壳，宽度 = _Outline_Width × 0.001 m（近处），颜色 _Outline_Color
```

几个从字节码里才能看出来的事实：阴影色图**直接替换**底色（材质上的 `_Shadow1Color` 在没有 `_SHADOWCOLOR` 关键字时
根本没被用到）；头发上一缕缕的高光其实是「自发光」（`tex_m` 的 R 通道 × `_EmissionColor`=1）；不透明材质
（`_SrcBlend=1`）完全不看贴图 alpha。

`.blend` 里对应的东西：

| 物件 | 说明 |
|---|---|
| 节点组 `TSQ Toon` | 上面整套公式；每个材质的参数都在组节点的输入上，可以直接改 |
| 节点组 `TSQ Light` | 光的方向、颜色、环境光。方向 = 场景里 **`TSQ_Sun` 物体的朝向**（转它就是重新打光），用变换驱动器读取，不含 Python 表达式，打开文件不会弹「自动执行脚本」的警告 |
| 节点组 `TSQ MatCap UV`、`TSQ Face SDF UV`、`TSQ Face Lit` | MatCap 取样坐标；脸部 SDF 阴影（头的朝向用驱动器跟着 `Bip001 Head` 骨，摆头后阴影方向仍然正确） |
| 修改器 `TSQ Outline`（Solidify，法线翻转）+ 材质 `TSQ Outline 000000` | 描边。不想要就关掉修改器；宽度按材质的 `_Outline_Width` 存在顶点组 `tsq_outline` 里 |
| 材质的自定义属性 `tsq_spec` | 游戏材质的原始记录（全部 float / color / 关键字 / 贴图名），XPS / PMX 转换就靠它 |

所有着色都是「法线、视线、一个光方向」上的数学，输出走 Emission，所以 **EEVEE 和 Cycles 看起来一样，和灯的强度
无关**；色彩管理设成了 Standard（贴图就是最终颜色，Filmic 会让它发灰）。

## XPS

`export_xps_blender.py` 调 Blender2XPS：去掉描边外壳，每个材质退回它的底色图（`tex_d`，游戏里受光面的颜色）。
`_BaseColor` 有染色的材质（41 个单位有，如 Emily 发绿光的装甲、Reiko 的蓝色薄纱）会另生成一张乘好颜色的贴图副本，
名字带染色的十六进制值（`tex_d_face_18_ffeded.png`）；没有贴图的材质（`16_asuka_black` 的纯黑）出一张纯色小图。
Biped 骨名直接映射成 XPS 标准骨名（XPS 姿势能套），单位是米。
`--xps-unlit` 改用无光照渲染组（10 / 21），XPS 里看到的就是贴图原色。XPS 没有 morph，导出的是默认表情。
导完用 XNALaraMesh 插件读回 Blender、摆一个测试姿势（放下手臂、抬腿屈膝、转头）渲一张 `<id>_xps_preview.png`。

## PMX

`export_pmx_blender.py` 复用 Rise of Eros 的 PMX worker（同样是 Biped 骨架）：槽位解析、肢体辅助骨的付与、
37° A-pose、Convert_to_MMD5 一键转换、身体碰撞体、胸部物理、mmd_cloth_physics（头发 / 裙子 / 丝带链按形状识别）、
mmd_tools 以 12.5 倍导出、付与顺序校验、骨名截到 15 字节以内。Taimanin Squad 专有的部分：

- **胸部**：胸骨（见上）放进 chest 槽位 → `左胸` / `右胸`，worker 建刚体，关节再改成**平移弹簧**
  （照游戏的 Bone Spring）—— 见下一节「胸部物理（乳摇）是怎么做的」。
- **表情是顶点 morph**。游戏只有整脸表情、没有口型，所以标准 MMD 表情是从整脸表情里**按区域切出来**的：
  用 `closed_eyes` 量出眼睛的上下沿、用张嘴最大的形态量出嘴的高度，把脸分成 眉 / 眼 / 嘴 三段，再按中线分左右：

  | MMD 表情 | 来源 |
  |---|---|
  | まばたき | `closed_eyes` |
  | ウィンク２ / ｳｨﾝｸ２右 | `closed_eyes` 的左半 / 右半（左 = 角色自己的左眼） |
  | 笑い、ウィンク / ウィンク右 | 角色的 smile 确实闭上双眼（"^ ^"，如阿莎姬的 `smile_01_face`）时取它的眼部；否则（Kirara 的 smile 是单眼眨眼）退回 `closed_eyes` |
  | あ | `mouth_talk_A`，没有就取 `shouted_face` 的嘴部 |
  | い う え お | `mouth_talk_E / O` 和 smile / shout 的嘴部按比例混出来（标注为 approximated） |
  | にっこり | smile 的嘴部 |
  | 口角下げ | sad 的嘴部；没有 sad（47 个单位）就用 dissatisfied 的嘴部 |
  | 困る | sad 的眉部；没有 sad 就用 debuff 的眉部 |
  | 怒り | dissatisfied 的眉部；没有（30 个单位，如 Kirara）就用 shouted 的眉部 |
  | 目上 目下 目左 目右 | 视线形态**按眼睛高度缩放**：虹膜上下移动眼高的 0.2、左右 0.25（原形态拉满是翻白眼：虹膜走 24–28 mm，而眼睛只有 17–23 mm 高）。左右按游戏的叫法 = 画面上的左右 |

  切区域时不带那些「从头里飞出来的小贴片」。判断办法：整块一起位移超过 8 mm、**起点藏在皮肤后面 8 mm 以上、
  终点落在皮肤表面**的网格孤岛才算贴片；眉毛、嘴缝线、牙和舌头也是整块移动的，但它们起点在表面或者始终在
  嘴里，属于脸本身，要跟着走（否则张嘴后下排牙留在原地、嘴缝线悬在张开的嘴上）。
  还有反方向的：有的贴片平时就藏在嘴唇后面，整脸表情张嘴时会把它**再往头里收**（Hebiko 喊叫时把「ε」嘴形贴片
  往里送 30 mm），不带上这个动作，张开的嘴里就露出那块贴片。所以「被这个表情移动、但移动后仍在皮肤后面
  8 mm 以上」的贴片，按它所在的区域整块跟着走。
  游戏原有的每个形态也都原名导出（面板「その他」）。`mouth_talk_*` 是游戏对话用的口型，幅度本来就小。
- **材质**：底色图（`_BaseColor` 有染色的用乘好颜色的副本，同 XPS）+ 每个材质一张 toon 渐变（阴影色 = 该材质
  `tex_s` / `tex_d` 的平均比值，底色有染色时再除以染色）+ MatCap 当加算 sphere（`.spa` 的效果）+ 描边颜色 / 宽度
  写成 PMX 的 edge（`_Outline_Width` 2 → edge 1.0）。没有贴图的材质把颜色写进 PMX 的 diffuse。
  sphere 图 = MatCap × `_MatCapColor` × **遮罩覆盖率**：游戏里 MatCap 还要乘 `tex_m` 的 B 通道，MMD 的 sphere 没法
  逐像素遮罩，就在这个材质自己的 UV 上取 B 的平均值（Yukiha 的皮肤 0.42、紧身衣 0.62），整张图按它调暗。
- **不是人形的单位**（6 个里的 4 个）：标准 MMD 骨架要两条腿、两只手臂才能对上。蛇身的 `300_kaliya` / `b_26_kaliya`、
  人鱼 `b_12_wednesday`、翅膀代替手臂的 `b_16_harbinger` 走 mmd_tools 自带的转换：**骨头保持游戏原名，没有 IK、
  没有物理**，表情和材质照常（报告里记为 `plain_rig`）。MMD 的舞蹈动作套不上，只能自己摆骨头。
  巨型 Boss `b_10_monday`、`b_13_thursday` 是人形，照常转换。
- 导完用 `scripts\stellarblade\preview_pmx_blender.py` 把 PMX 读回 Blender、套一段舞蹈逐帧跑物理，渲
  `preview_dance.png`；再用 `preview_pmx_morphs.py` 把每个表情拉满渲一格，拼成带名字的 `preview_morphs.png`
  （不开 MMD 就能看每个表情长什么样）。静止图和舞蹈图用预览脚本的 `--look mmd`：环境光是强度 0.8 的白光、
  一盏弱主光、Standard 色彩管理 —— MMD 里受光的材质显示的就是贴图本色，这样渲出来的颜色才对得上。
  预览脚本默认的「三盏强光 + Filmic」会把颜色提亮近一倍、暗部再抬一截，黑色紧身衣渲成浅灰（别的写实游戏用它没问题）。
  和 `.blend` 比仍然会亮一些：卡通着色里大片暗部用的是另一张更深的阴影色图，PMX 只有一张底色图加 toon 渐变。

## 胸部物理（乳摇）是怎么做的

**现象**：`1_asagi` 套舞蹈渲出来，胸部几乎不动。**骨骼没有问题** —— `左胸` / `右胸` 有骨头、有刚体、有关节，
胸部的顶点也确实蒙在上面（每侧 377 个顶点，其中 145 个权重 ≥ 0.9）。问题出在物理的**做法**上。

**量出来的原因**（舞蹈「爆了」400 帧，胸部刚体相对上半身的运动）：

| | 关节怎么做的 | 结果 |
|---|---|---|
| 游戏（Magica Cloth 2 的 **Bone Spring**，`clothType 10`） | 骨头在原位附近**平移**，弹簧拉回，最远 `limitDistance`（Asagi 是 5 cm）；`gravity = 0` | —— |
| 改之前的 PMX（Rise of Eros worker 的模板） | 绕骨头根部**转动** ±10°，没有弹簧，不能平移 | 被重力压在下限位上（合成约 16°，刚体中心下垂 2.4 cm），整段舞蹈里中位速度 **0.06 cm/帧** |
| 现在的 PMX | 三个方向的**平移弹簧**，不转动 | 行程左右 7.4 cm、前后 4.4 cm、上下 1.9 cm，中位速度 **0.37 cm/帧** |

第一版视频里还叠了两个 **Blender 预览自己的问题**（和 PMX 无关，但预览因此更显不出来）：

1. mmd_tools 把每个关节建成 SPRING2 约束，每个轴自带 0.5 的阻尼。MMD 没有这一项，它会把软弹簧按得几乎不动。
2. Blender 里所有刚体都在碰撞层 0，mmd_tools 只给**静止时靠得近**的刚体对建「互不碰撞」的约束。所以 PMX 里写着
   「和谁都不碰」的胸部刚体，在 Blender 里仍会被舞蹈中经过胸前的手臂碰撞体撞到（实测右胸被撞出 5 cm、关节被掰到
   33°）—— MMD 里不会有这种事。

**做法**（`tsquad_blender.spring_bust`，导出 PMX 时自动做）：

- worker 照旧建刚体（球，位于胸部蒙皮的加权中心，质量 1，和谁都不碰撞）和关节；然后把关节改掉：
- **关节移到刚体中心**：没有力臂，重力只会往下拉、不会拧它；
- **转动锁死，三个平移轴放开，各带弹簧**，刚度 `k = 质量 × (2π × 频率)²`：
  - 左右 2.2 Hz、前后 2.6 Hz —— 这两个方向没有重力，可以软；
  - 上下 3.6 Hz —— **MMD 关不掉重力**，而弹簧对弹跳让多少、对重力就让多少：静止下垂量 = g / (2πf)²
    （g = 98 PMX 单位/s² = 7.84 m/s²）。3.6 Hz 垂 1.5 cm，2.8 Hz 垂 2.5 cm，2.2 Hz 垂 4.1 cm。所以上下只能硬一些；
- **行程限位**：左右 ±5 cm、前后 ±4 cm、上下 ±4 cm（游戏是 5 cm）；
- **阻尼**：用刚体的「移動減衰」。Bullet 的阻尼是每秒 `v ×= (1 − d)`，相当于 `x″ + c·x′ + ω²x = 0` 里
  `c = −ln(1 − d)`。想要阻尼比 ζ（默认 0.25：晃两下停住）就取 `d = 1 − e^(−2ζω)`，ω 用最软的那个轴 → d = 0.999。
  （MMD 模型里常见的 0.5 只相当于 ζ = 0.025，会晃个没完。）
- 写进 Asagi 的 PMX 的值：关节 移動制限 ±0.625 / ±0.5 / ±0.5，ばね（移動）191 / 512 / 267（x / y 竖直 / z），
  回転制限 0；刚体 移動減衰 0.999、回転減衰 0.99。

**怎么调**：设置都在 `tsquad_common.BUST` 里，每一项是默认值，命令行用 `--bust 名=值,名=值` 覆盖：

| 设置 | 默认 | 含义 |
|---|---|---|
| `sway_hz` / `depth_hz` / `bounce_hz` | 2.2 / 2.6 / 3.6 | 左右 / 前后 / 上下 的弹簧频率，越小越软、晃得越大 |
| `sway_cm` / `depth_cm` / `bounce_cm` | 5 / 4 / 4 | 各方向最多能走多远（上下的下垂量算在里面） |
| `ratio` | 0.25 | 阻尼比：0.1 晃很久，0.25 晃两下，0.7 只是让一下就回来 |
| `tilt_deg` / `tilt_hz` | 0 / 3 | 允许胸部同时转动多少度（0 = 只平移，和游戏一样） |
| `mass` / `ang_damp` | 1 / 0.99 | 刚体质量 / 回転減衰 |
| `amount` | 1 | **整体幅度**：0.5 = 行程减半（弹簧相应变硬），1.3 = 多三成。想让某个角色晃得多一点 / 少一点，改这一个就够 |
| `size_cm` | 10.9 | 上面那些值是照多大的胸部调的（Asagi：胸部蒙皮的中心离胸部骨 10.9 cm）。别的角色按自己的大小成比例缩放；`0` = 不看大小 |
| `game` | 1 | `1` = 行程不超过游戏给这个角色的上限（见下），`0` = 不管游戏 |
| `cap_cm` | （从游戏读） | 那个上限，厘米。脚本自己从游戏里读；写在 `--bust` 里就以你写的为准 |
| `style` | `spring` | `swing` = 回到原来的转动模板 |

```powershell
python dance_video.py 1_asagi --vmd <动作> --view chest --bust bounce_hz=3,ratio=0.15   # 只在这段视频里试（PMX 不变），约 2 分钟
python export_model.py 1_asagi --pmx --reconvert --bust bounce_hz=3,ratio=0.15         # 满意了，写进 PMX
python export_model.py 11_rinko --pmx --reconvert --bust game=0                        # 这个角色不要游戏的行程上限
python export_model.py 7_yukikaze --pmx --reconvert --bust amount=0.5                  # 这个角色再减半
python export_model.py --female --pmx --reconvert --jobs 6 --bust size_cm=0,game=0     # 所有人都用 Asagi 那一套
python export_model.py 1_asagi --pmx --reconvert --bust style=swing                    # 回到原来的转动模板
```

**每个角色不一样**（`tsquad_common.bust_fitted`，导出 PMX 时自动做）。上面的值是在 Asagi 身上调的，别的角色按两件事缩放：

1. **胸部大小**。量的是「胸部蒙皮的加权中心离胸部骨有多远」（就是胸部刚体到骨头根部的距离，导出日志里的
   `size`）：平胸 4–7 cm，Asagi 10.9 cm，最大的 15 cm 上下。系数 = 这个距离 ÷ 10.9，限制在 0.4–1.2 之间。
   平胸的 Yukikaze（7.1 cm）得到 0.66，Sakuya（4.0 cm）0.4。
2. **游戏给的行程上限**。游戏里每个角色的 Bone Spring 有一个 `limitDistance`（骨头最远能离开原位多远），再乘
   `blendWeight`（模拟结果只显示几成）：Asagi 是 5 cm；有胸部物理的 135 个单位里，65 个是 5 cm 以上，26 个是 4 cm，
   44 个不到 4 cm（其中 25 个不到 2 cm：Rinko 5 cm × 0.3 = 1.5 cm，Asuka 1 cm）。PMX 里左右方向的行程不超过它。

   两者取小的那个，再限制在 0.25–1.6 之间，得到这个角色的**系数**。行程（三个 `*_cm`）乘系数；弹簧同时调硬
   `1 / √系数`（一次推动引起的摆幅和频率的平方成反比），这样摆幅也跟着系数走 —— 不然行程小了弹簧还那么软，
   胸部就会一直撞在限位上。上下方向只调硬、不调软（调软了静止时会垂得更低）。阻尼比不变。

全部 148 个女性单位重导之后（2026-10-02）：135 个有平移弹簧的胸部物理 —— 系数 1.0 的 23 个，0.8–0.99 的 46 个，
0.5–0.79 的 28 个，不到 0.5 的 36 个，另有 2 个 1.2；87 个的系数是被游戏上限定的，48 个是按大小定的。其余 13 个没有
胸部物理：8 个没有胸部骨，4 个不是人形，`23_oboro` 的胸部骨上没有蒙皮。每个角色得到的数值写在 `_meta\exports.json`
（`pmx_report.bust_springs`）和画廊卡片的 pmx 一行里。

实测（同一段舞蹈，`dance_video.py --stills 1 --no-video --bust ""` 量出来的行程，左右 / 前后 / 上下，cm）：

| 角色 | 大小 cm | 游戏上限 cm | 系数 | 行程设置 cm | 舞蹈里实际走了 |
|---|---|---|---|---|---|
| `1_asagi` | 10.9 | 5 | 1.0 | ±5 / 4 / 4 | 7.4 / 4.4 / 1.9 |
| `13_shiranui` | 12.2 | 5 | 1.0 | ±5 / 4 / 4 | 7.0 / 4.8 / 1.9 |
| `14_azusa` | 12.5 | 4 | 0.8 | ±4 / 3.2 / 3.2 | 5.4 / 4.2 / 1.4 |
| `7_yukikaze` | 7.1 | 10 | 0.66 | ±3.3 / 2.6 / 2.6 | 3.2 / 4.4 / 1.1 |
| `2_sakuya` | 4.0 | 3 | 0.4 | ±2 / 1.6 / 1.6 | 1.9 / 2.1 / 0.5 |
| `11_rinko` | 15.4 | 1.5 | 0.3 | ±1.5 / 1.2 / 1.2 | 2.3 / 1.7 / 0.5 |
| `16_asuka` | 9.5 | 1 | 0.25 | ±1.25 / 1 / 1 | 1.7 / 1.4 / 0.4 |

**没有照搬的游戏参数**：游戏里每个角色的弹簧软硬（`springPower` 0.01–0.2）和阻尼（`damping` 0.06–0.9）也各不相同。
试过按它们缩放（频率 × √(springPower ÷ 0.1)、阻尼比按游戏的比例），量出来不行，所以没用：

- 软弹簧配小行程的角色（最常见的一组是 `springPower 0.03`、4 cm、`damping 0.65`，22 个）在舞蹈里一直撞在限位上：
  量到的行程 7.9 / 6.4 cm，正好是限位 ±4 / ±3.2 的两倍。
- MMD 的阻尼只有刚体的「移動減衰」一种，它减的是刚体**相对世界**的速度，不是相对胸口的。阻尼一大，身体一移动
  胸部就被「拖」在后面贴着限位。
- 硬弹簧配重阻尼（`13_shiranui`：0.2 / 0.9）算出来的移動減衰在 PMX 的 32 位浮点里四舍五入成 1.0，刚体每一步都被
  刹死，整段舞蹈挂在限位上（量到 ±5 cm 全程顶满）。现在给衰减率设了上限（`BUST_MAX_RATE`）防这种情况。
- Magica Cloth 2 内部怎么用 `springPower` 和 `damping` 没有公开的公式（官方文档只说「弹簧强度」「空气阻力」），
  上面的换算是按「每秒 90 步，每步拉回一定比例」推的，不是对照游戏画面验证过的。

每段视频的 `.json` 和命令行最后一行都会报出胸部的行程和每帧速度（`bust_motion`），有没有乳摇不用靠眼睛猜。

**预览怎么才像 MMD**（`--physics mmd`，舞蹈视频和 PMX 检查图现在的默认）：关节改成 SPRING1、阻尼 0（Blender 把
SPRING1 的阻尼**取反**后才交给 Bullet，0 才是 MMD 的实际值）；回転ばね乘导入缩放的平方（mmd_tools 原样拷贝，硬了
156 倍）；重力 98 × 0.08；mask 全屏蔽的刚体各放进一个单独的碰撞层。前三条来自 `scripts/mmd_physics` 的标定。

**还没做的 / 要注意的**：

- 「胸部大小」是从蒙皮量的近似值：同一个角色的不同造型会差一些（Asagi 三个造型是 10.9 / 10.5 / 9.3 cm），
  骨头放得深浅也会影响。觉得某个角色不对，用 `amount` 单独调。
- 游戏上限很小的角色（Rinko 1.5 cm、Asuka 1 cm ……）在 PMX 里也晃得很小 —— 这是照游戏来的。想要大一些：
  `--bust game=0`（不管游戏的上限），或者直接给 `cap_cm=4`。
- 静止时胸部比游戏里低一点（重力下垂）：Asagi 1.5 cm，系数小的角色按系数更少（旧模板是 2.4 cm）。
- 在 MMD 本体里还没验证过：MMD 的物理步长和关节限位的软硬都和 Blender 不同。

## 舞蹈视频（给 PMX 套 MMD 动作）

```powershell
python dance_video.py 1_asagi --vmd "E:\Downloads\mmd\爆了2026.1.18by小王动画"   # 给文件夹：里面的 .vmd 和配乐
python dance_video.py 1_asagi --vmd dance.vmd --bgm song.wav --name mydance      # 或者分别指定
python dance_video.py asagi kirara --vmd <文件夹> --jobs 2                       # 几个单位，两个同时渲
python dance_video.py 1_asagi --vmd <文件夹> --stills 6 --no-video               # 只渲 6 张检查帧（不到 1 分钟）
python dance_video.py 1_asagi --vmd <文件夹> --view chest                        # 胸部特写：相机跟着上半身走
python dance_video.py 1_asagi --vmd <文件夹> --view chest --bust bounce_hz=3     # 试别的胸部物理（只影响这段视频）
python dance_video.py 14_azusa --vmd <文件夹> --view chest --bust ""             # 把现在的默认胸部物理套到一个旧 PMX 上看
python dance_video.py 1_asagi --vmd <文件夹> --backdrop 夜店舞台                 # 换背景：游戏背景图名字里的一段（见「游戏里的背景图」）
python dance_video.py 1_asagi --vmd <文件夹> --backdrop 全景_drt --backdrop-turn 40   # 全景图：往右转 40° 取景
python dance_video.py 1_asagi --vmd <文件夹> --backdrop "D:\图\我的背景.jpg"     # 或者任意一张图
```

前提是这个单位已经导出过 PMX（`export_model.py <id> --pmx`）。脚本把 PMX 用 mmd_tools 读回 Blender 3.6，套上动作，
烘物理，渲出来（`render_dance_blender.py`）：

```
E:\game_export\TaimaninSquad\<角色>\video\<id>\
  <id>_<动作>.mp4      竖屏 1080×1920、30 fps、H.264 + AAC（配乐从动作第 0 帧开始）
  <id>_<动作>.blend    同一个场景：模型、动作、烘好的物理，贴图和配乐都打包在里面 —— 打开按空格就能播，
                       想换角度、换灯光、重渲都在这里改（「渲染动画」会重新出同一个 mp4）
  <id>_<动作>.json     这段视频是用什么渲的（PMX、VMD、帧数、物理刚体数、胸部的行程和速度 ……）
  <id>_<动作>_stills\  --stills N：均匀取 N 帧的 PNG
  <id>_<动作>_chest.mp4            --view chest：胸部特写
  <id>_<动作>_bust-<设置>.mp4      --bust ...：临时改了胸部物理的版本（文件名带上设置，和正常的并排放）
  <id>_<动作>_bg-<背景图名>.mp4    --backdrop ...：换了背景的版本
```

动作文件夹只读，不往里写任何东西。已有的视频不重做，要重做加 `--force`。

**每一步为什么这样做**（顺序不能乱，都是别的游戏上踩出来的）：

1. 导入 PMX 时**带物理**，然后 `Model.build()`：不 build 的话刚体在模拟、骨头却不读它，头发和裙子像木板一样跟着父骨。
2. 绑定表情滑块（`morph_slider`）：否则 VMD 里的眨眼、口型键什么都驱动不了。
3. 描边用 mmd_tools 自带的「边缘预览」（反向外壳，颜色和粗细取 PMX 的 edge 设置，也就是游戏的描边色和宽度）。
4. 导入 VMD 时留 30 帧引子（`--margin`）：静止姿势用 30 帧过渡到动作第一帧。没有引子的话模型一帧之内从 T 字跳进舞姿，
   物理链被甩飞（刘海翻到头顶），后面整段都不对。引子只参与模拟，**不渲进视频**。
5. **物理按 MMD 的方式跑**（`--physics mmd`，默认）：去掉 Blender 给每个关节轴加的 0.5 阻尼、回転ばね换算单位、
   重力 98，「和谁都不碰」的刚体真的不碰 —— 见上一节。`--physics blender` 是 mmd_tools 原样（更硬、更稳，胸部几乎不动）。
6. **先烘焙刚体模拟再渲**：在「活的」缓存上直接渲动画，渲到的不是逐帧步进出来的那个模拟。
7. 灯光用 PMX 检查图的「MMD 观感」：白色环境光让材质呈现贴图本色、一盏弱主光给形体和地面影子、Standard 色彩管理。
   地面是一块只显示影子的平面（受光处和背景同色，所以没有地平线）。
8. 相机固定不动，取景按**整段动作**里模型到过的范围算（烘完物理后每 3 帧量一次包围盒），所以手举到最高时也不出画。
   `--view chest` 换成胸部特写：相机挂在上半身的骨头上，躯干在画面里不动，动的就只有物理（`chest:60` 是从侧面 60° 看）。
   相机挂到骨头上时要把父级逆矩阵写出来 —— 设完父级立刻赋 `matrix_world` 用的是旧的父级矩阵，相机会跑到别处。
9. **换背景**（`--backdrop`）：给一张图，或者 `_backgrounds` 里某张图名字的一段（`夜店舞台`、`S018_B`；匹配到不止
   一张会列出来让你写得更具体）。图贴在一块跟着相机走、正好铺满画面的平面上，放在模型后面 60 米处：
   - 图保持比例、**铺满画面**，多出来的两边（或上下）均匀裁掉。4:3 的图放进竖屏只显示中间 42%，横屏（`--size 1920x1080`）
     能显示大部分。
   - **全景图**（宽正好是高的两倍，`全景_` 开头的那些）先取一个「视角」：`--backdrop-fov`（上下看多少度，默认 70）、
     `--backdrop-turn`（往右转多少度）、`--backdrop-tilt`（往上仰多少度）。不直接当世界背景用的原因：相机是 70 mm 的
     长焦，上下只看 29°，4096 px 的全景在它眼里只有 330 px 高，放大后是一片马赛克（`--backdrop-as world` 可以看到
     这个效果；它的好处是背景会跟着相机转）。
   - 有背景时地面改成透明的，只在影子落下的地方把背景压暗（`--shadow 0.45`，0 = 不要影子）。
   - 模型的打光不变（还是白色环境光 + 一盏弱主光），所以夜景背景前的角色仍然是亮的。

可调的：`--size 1920x1080`（横屏）、`--frames 150`（只渲前 150 帧）、`--samples`、`--no-edge`（不要描边）、
`--no-bgm`、`--no-blend`、`--view`、`--physics`、`--bust`、`--backdrop`、`--out-dir`（视频写到别的文件夹）。

**限制**：

- 相机是固定的全身机位，不读相机 VMD。要运镜就打开那份 `.blend` 自己加相机动画。
- 动作是给别的模型做的（这份的原模型是 Furina）：体型差得多时手会穿胸、穿胯，脚的间距也可能不合适 —— 这是
  MMD 动作通病，要在 MMD / Blender 里按模型修。
- 物理是在 Blender 里按 MMD 的方式跑的近似（见上一节），没有在 MMD 本体里对照过：MMD 的物理步长、关节限位的
  软硬和 Blender 不完全一样。头发、裙子的物理预设是在旧的（更硬的）预览下调的，现在看起来会软一些。
- 非人形的 4 个单位（蛇身、人鱼、翅膀代替手臂）的 PMX 没有标准 MMD 骨架，套不了舞蹈。

## 游戏里的背景图

```powershell
python export_backgrounds.py            # 挑好的 128 张 → E:\game_export\TaimaninSquad\_backgrounds\（约 1 分钟，141 MB）
python export_backgrounds.py --list     # 每张图的文件名 ← catalog 地址，不写文件
python export_backgrounds.py --all      # 另把下面这些文件夹里的全部图片导到 _backgrounds\全部\<类别>\（523 张）
python export_backgrounds.py --force    # 已有的文件重写一遍
```

**游戏里有什么**（把 catalog 里 10 445 张贴图按文件夹过了一遍，凡是名字像背景的都解出来看了缩略图）：

| 类别 | catalog 位置 | 有多少 | 是什么 | 入选 |
|---|---|---|---|---|
| 剧情 | `Story/BG/` | 55 | 视觉小说剧情的背景画：教室、海滩、街道、和室、霓虹街、夜店舞台、竞技场 ……（`E001`–`E006` 是 2048×1536，`S002`–`S027` 是 1024×768） | 全部 55 |
| 过场 | `Prologue_Epilogue/ep_xx/` | 335 | 每章开头 / 结尾那段漫画式演出的分层素材。大部分是人物、车辆、火焰、遮罩这类图层 | 整幅、不透明、画面里没有人物的 50 张 |
| 界面 | `UI/BackGround/` | 66 | 菜单的底图。多数是故意压暗、模糊过的 | 清晰的 2 张（基地休息室、指挥室） |
| 抽卡 | `Icon/Portal/`、`Director/GachaIntro/` | 12 | 招募界面的底图（另一半是叠在上面的角色立绘） | 5 |
| 天空 | `Effect/EP1_FX_Resources/Textures/Background/` | 42 | 技能演出里用的手绘天空、云、远山（512–1024 px，偏小） | 6 张天空 |
| 全景 | 各关卡的天空盒（`BackGround/.../*.png`，类型是 Cubemap） | 12 | 六个面各 1024 px 的立方体贴图 | 9 个，各拼成一张 4096×2048 的全景图；另有一张本来就是全景的 `sky_school_rooftop_Day` |

不是背景、没有导的：`Temp/`（408 张商店横幅）、`Icon/Loading/`（57 张角色立绘条）、关卡里的反射探针（16–64 px 的小立方体贴图）。

**输出**：一个文件夹，平铺，文件名是 `<类别>_<游戏里的名字>_<画的是什么>.png`，例如 `剧情_S018_B_夜店舞台.png`、
`过场_2-2_ep_01_0_DSO总部大厅.png`、`全景_drt_quest_pv_2D_asagi_Sky_1_霓虹都市_夜.png`。同一个文件夹里的
`_总览_<类别>_<n>.jpg` 是带名字的缩略图总览（8 张），先看它。每张图的来源记在 `_meta\backgrounds.json`。
图片是游戏素材，只放在导出目录，不进仓库。

**几个做法**：

- **界面底图要拉回 16:9**：`UI/BackGround/` 的图存成 2048×2048 的正方形，游戏里是拉成 16:9 显示的（正方形里椅子、
  屏幕都是瘦的）。导出时缩成 2048×1152。抽卡底图不是这样 —— 叠在上面的立绘在正方形里比例是对的，所以原样导出。
- **立方体贴图拼全景**：Cubemap 的图像数据是六个面依次排列（+X −X +Y −Y +Z −Z）。每个面是**从上往下**存的
  （普通 Texture2D 是从下往上，UnityPy 的 `.image` 会替它翻转；立方体的面不能翻）。全景图的每个像素算出它看的方向，
  按立方体贴图的标准规则找到面和面内坐标，双线性取样。经度的摆法照 Unity 的全景天空盒
  （`u = 0.5 − atan2(z, x) / 2π`）。判断对不对的办法：面翻错了的话，拼出来的全景在面的交界处是一圈扇贝形的接缝，
  一眼就看得出；对的版本云和楼是连续的。离线测试里用「把每个面涂成它所看方向的函数」验证了没有接缝。
- **怎么挑的**：先按「不透明、宽 ≥ 1000 px」筛掉图层和遮罩，剩下的做成带编号的缩略图逐张看。入选的标准是
  「整幅的场景、里面没有人物或怪物」；过场里几张特写（怪物的脸、俯拍的井盖、纯色渐变）没要。

**怎么用**：

- 平面的图（剧情 / 过场 / 界面 / 抽卡 / 天空）：在 Blender 里当相机背景，或者放在角色身后的一块平面上。
- 全景图：Blender 的「世界」里接一个「环境纹理」节点，相机转到哪都有背景；`全景_..._霓虹都市_夜` 是一整圈的夜景。
- 给舞蹈视频换背景：见「舞蹈视频」一节的 `--backdrop`。

**限制**：

- `S` 系列剧情背景只有 1024×768，放到 1080×1920 的竖屏视频里要放大 2.5 倍，会糊（可以当作景深虚化）。
- 过场画大多是夜景和战场，偏暗。
- **3D 关卡没有导**：游戏的战斗场景是 25 个 Unity 场景（`background_scenes_all_*.bundle`，82 MB：东京王国街区、
  五车学园、时代广场、机场、森林 ……），每个场景 100–800 个网格、一张烘焙光照图（Bakery）、天空盒、粒子特效，
  另有 14 个大厅主题（`LobbyTheme_*`）。它们不是图片，要在 Blender 里重建场景（网格 + 材质 + 光照图）才能当背景用，
  还没做。上面「全景」那几张就是这些关卡的天空。

## 画廊页和「手动操作说明」

`python list_models.py --html` 生成 `html\index.html`（只含指向本机文件的 `file://` 链接，游戏素材不进仓库）：

- 每个单位一张卡片：导出过的显示全身预览，链接到 `.blend`、XPS、PMX 的文件夹和各张检查图（脸部、表情总览、
  转台视频、XPS 读回、PMX 舞蹈、PMX 表情）；没导出的显示 `--preview-only` 渲过的预览（`_work\previews`，
  左上角标着「未导出」），再没有就用游戏头像；每张卡片带一条可复制的导出命令。
- 顶部可以搜索、按类别筛、「只看女性」「只看已导出」。
- 页首的**手动操作说明**把「自己怎么看有哪些模型、怎么导出」写在页面上：A 用脚本（准备、列清单、导出、
  产物在哪和怎么打开），B 不用脚本的手工路线。命令都带复制按钮，路径是生成时本机的真实路径。

## 不用脚本的手工路线（AssetStudio + Blender）

脚本之外也能把模型拿出来，只是拿到的是「带骨架和形态键的原始模型」。下面每一步都实测过
（对象是 Kirara `prf_24`；导出用 AssetStudioMod v0.19.0 的命令行版，和图形界面是同一个内核，菜单名取自
图形界面程序里的字符串；FBX 导进 Blender 3.6.15）：

1. **看有哪些模型**：资源管理器打开 `TaimaninSquad_Data\StreamingAssets\aa\StandaloneWindows64`，搜
   `localunit_aos_assets_`。每个文件是一个单位的美术包，名字就是 `localunit_aos_assets_<编号>_<名字>_<hash>.bundle`。
2. **取出模型**：AssetStudioModGUI → `File > Load file` 选美术包 → `Asset List` 页用 `Filter Type` 只留 Animator →
   右键 `prf_<编号>`（`_LOD1` 是低模）→ `Export Animator + selected AnimationClips`，得到 `prf_<编号>.fbx` 和同目录的
   PNG 贴图。（或者 `Scene Hierarchy` 页勾上 `prf_<编号>` → `Model > Export selected objects (merge)`。）
   命令行版的等价写法：`AssetStudioModCLI <美术包> -m animator --fbx-animation skip --fbx-scale-factor 100 -o <输出目录>`。
3. **大小**：默认导出的 FBX 进 Blender 只有 1.9 厘米高。导出前把 `Options > Export options` 的 `ScaleFactor` 改成 100，
   或者 Blender 导入 FBX 时把「缩放」填 100 —— 两种都得到 1.88 米的 Kirara。
4. **进 Blender**：`文件 > 导入 > FBX`。骨架（Kirara 104 根）、蒙皮、表情形态键（脸 12 个、嘴里 7 个）都在。
5. **贴图要自己接**：游戏着色器的贴图槽叫 `_BaseMap`，AssetStudio 只认 `_MainTex`，导入后 10 个材质里只有
   `mat_face_add_24` 带着贴图。按名字接底色图：`mat_face*` → `tex_d_face`，`mat_hair*` → `tex_d_hair`，
   `mat_skin / span / metal` → `tex_d_costume`，`mat_cloth` → `tex_d_cloth`。
6. **手工路线没有的**：卡通着色和描边（`tex_s` 阴影色、`tex_m` 遮罩、`tex_on_face` 脸部阴影都得自己搭节点）；
   UV 接缝处拆开的顶点没焊；嘴里的形态键不跟脸联动；`em_*` 表情贴片没隐藏；Magica Cloth 的组只是空物体；
   5 个早期单位的腿权重没修（见上）；XPS / PMX。
7. 从 Blender 再手工导 XPS / PMX 的步骤和别的游戏相同，见 `docs/vindictus-fiona-manual-export.md` 第 5、6 节。

## 已知限制

- **`--pmx` 依赖 ROE worker 里还没进仓库的胸部刚体代码**：胸部刚体和碰撞体修正是
  `scripts\riseoferos\export_character_model_blender.py` 的 `convert_rig_to_mmd(bust=True, collider_fixes=True)` 做的
  （本目录只把它建出的关节改成平移弹簧）。这段代码是 Rise of Eros 那条线的工作，2026-10-03 推送本目录时还在工作区里、
  没有提交。从仓库干净检出：`.blend` 和 XPS 正常，`--pmx` 会停下并提示 worker 缺胸部物理；那段代码进仓库后即可。
  （验证方法：把提交解到空目录跑 `1_asagi`，再把工作区的 worker 文件放进去重跑。）
- **眉毛 / 睫毛透过刘海**：游戏用模板缓冲（材质 `*_st`）让眉眼画在刘海上面。Blender 的 EEVEE 没有模板测试，
  `.blend` 里刘海会挡住眉毛；PMX 同理（MMD 里常见做法是把刘海材质调成半透明，可以自己在 PMXEditor 里改）。
- **没有眼球骨**：眼睛是脸网格的一部分，视线靠 blend shape。PMX 没有 `両目`，视线用 `目上/目下/目左/目右` 四个表情。
- **武器**：单位 prefab 里自带的武器（31 个单位，基本是怪物和 Boss）会导出，分两种：
  - **在身上的**（prefab 姿势下武器的包围盒够得着手，或够得着它挂的那根骨头：手里的剑、腰间的刀鞘、
    小臂上的刃）—— 正常显示，XPS / PMX 也带，跟着挂点骨动；
  - **停在原点的**（武器骨在原点、有的还在地面以下，或者根本不在骨架下面；13 个单位，如兽人的棍子）——
    放进「Weapons (parked)」集合并默认隐藏（要看就取消隐藏），预览图和转台不渲，XPS / PMX 默认不带，
    加 `--keep-weapon` 才带。
    把它们放回手里需要读动画里武器骨的位置，目前没做。

  角色的武器是另外的 prefab（见「武器 prefab」一节）。其中算作身体一部分的（手臂、腿）默认就带；真正的武器
  **默认不带**，`--weapons` 才带，而且位置只是 prefab 里的样子：
  - 靠动画摆位的不对（`59_sayaneo` 的爪链、`84_anje` 的触手）；`16_asuka` 的臂刃、脚刃在 prefab 里是伸出来的，
    游戏里平时是不是收着的不知道；
  - 挂点停在原点的（如 Sakuya 的双刀）和单位 prefab 里那 13 个一样进隐藏集合，XPS / PMX 不带；
  - `16_asuka_black`（纯黑剪影）带上武器会是彩色的刃配黑色的人，别给它加 `--weapons`。

  要把这些都摆对，得把待机动画里武器骨的位置读出来（动画片段的曲线解码还没做）。
- **没有闭眼形态的单位切不出标准 MMD 表情**：分区要靠 `closed_eyes` 量出眼睛的位置。4_Kuro、14_Azusa、
  78_Maskedtaimanin、283_Rin 没有这个形态，PMX 里只有游戏原名的整脸表情。兽人的 `closed_face` 不能当眨眼用
  （它连嘴一起闭上）；138_Orcboss 和 16_asuka_black 把眼睛 / 嘴拆成了 `closed_eyes_L` / `_R`、`smile_mouth`
  这样的分片形态，脚本把分片加起来当整脸形态用。
- **几个看着奇怪、其实是游戏数据本身的单位**：`16_asuka_black` 是技能演出用的纯黑剪影（材质全是 `FX_Black`），
  导出来就是黑的；`b_7_basilisk` 是一段两头开口的蛇身；997–999 是序章里发光的人形杂兵。
  （这里原来还写着「`282_saika` 只有大腿以上的半身」，那是错的 —— 她的腿在武器 prefab 里，见「踩过的坑」。）
- **布料链在绑定姿势下是直的**：头发、丝带、裙摆的 `Bone_*` 链在游戏里由 Magica Cloth 实时模拟，静止姿势里
  它们是建模时的样子（比如翡翠的丝带像棍子一样伸着）。PMX 里这些链有物理，一动就垂下来。
- **贴身短裙扭胯时会穿腿**（PMX 物理）：`248_mari` 的百褶裙紧贴着很宽的大腿，裙片的刚体一开始就和腿的碰撞体
  重叠，按规则这种刚体不参与碰撞（否则一开始就被弹飞），舞蹈里胯一扭，侧面的裙片就进了大腿。游戏里每片裙子只有
  两节骨，各片之间也没有横向连接。要好看得在 PMXEditor 里手调这条裙子的刚体和碰撞组。
- **宽袖子不会像真布那样垂**：袖子在游戏里只有两节骨（`Bone_L_Sleeve_01 / 02`），PMX 里用 `mmd_cloth_physics` 的
  sleeve 预设，摆幅上限 25–50°。手举过肩时袖子跟着前臂走，不会垂直挂下来（37_Mitsuki 的舞蹈预览能看到）。
- **几个单位的造型本身就特别**：`14_azusa` 一直闭着眼（所以没有闭眼形态）；`8_yukiha` 蒙着眼罩；
  `58_yuphiesophie` 是两个角色站在一起的一个单位（另有各自单独的 `_yuphie` / `_sophie`）；`82_tsuru` 的右前臂
  是一支枪，没有右手。
- **双人单位 `58_yuphiesophie` 的 PMX 里只有一个人会动**：MMD 的标准骨架只能套在一副骨架上（第一个 Biped，Yuphie），
  Sophie 的骨架保持游戏原名、不带 IK，舞蹈里她以静止姿势站在旁边（头发的物理还在）。要让两人各跳各的，用单独的
  `58_yuphiesophie_yuphie` 和 `58_yuphiesophie_sophie`。
- **个别细链饰在舞蹈里甩得很开**（`257_shizuru` 腰上的细链坠子能甩出一米）：它在游戏里是一条只在一头固定的骨链，
  PMX 里按「丝带」预设做的物理，现在检查图按 MMD 的方式跑（关节没有额外阻尼），所以比以前的检查图里活泼。
- 角色的正式名字（日文 / 中文）拿不到（表格的密钥在服务器），用的是文件夹里的英文名。
- 后处理（Bloom、色调映射）、头发投在脸上的假阴影（`HairShadowMask` pass）、溶解特效没有还原。
- 静止姿势是游戏 prefab 的姿势（手臂约 45° 下垂的 A-pose）。

## 踩过的坑

- **嘴唇不能按位置焊接**：Unity 在 UV 接缝处把顶点拆开，导入 Blender 前要焊回去；但闭着的上下唇在静止时
  坐标完全相同，按位置焊会把嘴缝死。焊接键 = 位置 + 法线 + 蒙皮 + **所有 blend shape 的位移**，只有真正的
  UV 接缝重复点才合并。
- **双面重复面**：有的网格把同一个三角面正反各画一遍（配合背面剔除显示两面）。Blender 的 `validate()` 会删掉
  第二份，脚本检测到后把该部件的材质改成双面。
- **Solidify 做反向外壳的正确参数**：`offset=+1`、`use_flip_normals=True`、厚度为正。实测其它组合要么把外壳长到
  里面，要么把原网格的法线翻了。
- **`smile_face` 不等于「笑い」**：Kirara 的 smile 是单眼眨眼，直接映射成 `笑い` 会让她跳舞时一直单眼闭着。
  所以先量 smile 在每只眼上的位移占 `closed_eyes` 的比例，两边都过半才用它。
- **「在 A-pose 里看着对」不等于骨架能用**：阿莎姬的 `.blend` 静止时毫无问题，一摆腿（XPS 测试姿势、MMD 舞蹈）
  小腿就留在原地、脚和腿分家 —— 小腿的皮在 `Bone_L_Calf` 上，它是大腿那条辅助链的子骨，根本不跟
  `Bip001 L Calf` 走。所以每个格式都要**摆个姿势再看**：XPS 读回后抬腿屈膝，PMX 套舞蹈跑几百帧。
  全游戏哪些单位有这类问题，是用 `rig_lint.py` 逐个量出来的：取每段肢体（大腿 / 小腿 / 上臂 / 前臂）中部的
  顶点，看它们的权重有多少落在该段 Biped 骨的子树里。比例低只是线索 —— 裙子、披风、肩甲盖在肢体上本来就
  跟自己的骨头走；要看的是「小腿的皮归了另一根像腿的骨头」这种。`--no-fixes` 看游戏原始骨架的结果。
- **单位 prefab 不等于完整的角色**：批量导出后 `20_natsume` 少一只左臂，三种格式都少。原因是她的左臂在游戏里
  是「武器」，放在另一个包的 `prf_weapon_20_0_L` 里，运行时才装上（见「武器 prefab」一节）。同样的还有 12 个单位。
  更糟的是此前已经看到 `71_snakelady` 没有手臂、`282_saika` 只有半身，却当成「造型本来如此」写进了已知限制，
  而每张检查图也都「看过」了。两条教训：一是觉得「造型就是这样」之前先对照游戏头像
  （`_meta\gallery\icons\<id>.png`：Snake Lady 的头像里明明有手臂）；二是「少了一块」这种事不该靠眼睛，
  现在 `rig_lint.py` 会逐段检查肢体上有没有皮，批量导出前后各跑一遍。
- **刚体网格要乘自己节点的世界矩阵**：蒙皮网格的每个顶点是 Σ 权重 ×（骨的世界矩阵 × bind pose），而武器、
  `em_*` 贴片这类 MeshRenderer 没有骨索引，顶点在网格自己的坐标系里。一开始把它们当成「单位矩阵」处理，
  结果所有武器都躺在原点 —— 死亡骑士的剑其实在手里。
- **Cycles 里眼睛花掉，原因有两个**：一是 Cycles 没有背面剔除，而眼睛是几层叠在一起的贴片，靠剔除背面才正确
  —— 节点组 `TSQ Toon` 有个 `Cull Back` 输入，把背面变成透明；二是描边外壳：没有描边的材质（睫毛、虹膜、眉毛）
  外壳厚度是 0，外壳和原来的面**完全重合**，Cycles 的光线穿过透明外壳后会把重合的那层也跳过去，整只眼睛就
  透到头的另一侧去了。给这些材质留 0.1 mm 的（不可见）外壳厚度就好了。修完后 EEVEE 和 Cycles 的画面逐像素
  平均差不到 1/255。
- **视线形态不能直接当 MMD 表情**：`up_eyes` 拉满是翻白眼。固定乘 0.4 也不行（阿莎姬的眼睛细，0.4 已经
  看不见虹膜），要按每个角色的眼睛高度算权重。
- **染色别交给导出器去烘**：一开始给 `_BaseColor` 不是白色的材质接了个「正片叠底」节点，Blender2XPS 见到节点
  运算就按**网格**烘贴图，但烘出来的图按**材质名**只存一份。脸和 `face_out` 共用 `mat_face` 时，第二个网格
  拿到的是第一个网格的烘焙结果，自己那片是黑的 —— Jinglei、Aki 眼睛周围一圈黑，像戴了面具（8 个单位中招）。
  PMX 这边则根本没乘这个颜色。现在直接生成乘好颜色的贴图副本，谁都不用烘。
- **Blender2XPS 给无贴图材质出纯色图时先看 mmd_tools 的颜色**：只要 Blender 里启用了 mmd_tools，每个材质都有
  `mmd_material.diffuse_color`（默认 0.8 灰），纯黑的 `FX_Black` 导出来成了浅灰。导出前把这个值也设成材质颜色。
- **切表情时不能把贴片一律留在原地**：见「PMX」—— 游戏会在张嘴的表情里把藏在嘴后面的贴片再往里收。
  这类问题只有逐个看 `preview_morphs.png` 才发现得了（Hebiko 的「あ」嘴里多出一个小卷）。
- **`Image.pixels` 给的是显示值，不是线性值**：8 位的 sRGB 贴图读出来就是文件里的数（已经过 sRGB 编码）。
  做 sphere 图时把它当线性值又编码了一次，中间调亮了 2–3 倍（0.2 → 0.33），加算上去黑色紧身衣成了银灰色、
  整个 PMX 发白 —— 一开始还以为是预览渲染器的灯光。toon 阴影色同理偏浅。MMD 自己是在显示值上直接乘、直接加的，
  所以交给它的颜色都按显示值算；需要在线性空间相乘的（MatCap × 颜色 × 遮罩）先解码、乘完再编码。
- **没有材质的面在 Blender 里是白的，不是不存在**：257_Shizuru 的眼镜片导出来一直是不透明的白色，以为是
  「反光眼镜」的造型，直到对照**游戏自带的头像**才发现游戏里镜片是透明的 —— 那是个没有材质槽的子网格，游戏
  根本不画（见「游戏里的资源结构」）。同一轮查出 Sokushitsuki 的角穿出斗笠（prefab 的默认形态键权重没读）。
  教训：拿不准一个造型对不对时，`_meta\gallery\icons\<id>.png` 就是现成的对照图。
- **第二副骨架被当成了布料**：`58_yuphiesophie` 一个单位里有两副 3ds Max Biped（`Bip001` 是 Yuphie，`Bip002` 是
  Sophie）。复用的 worker 告诉 `mmd_cloth_physics`「身体 = `^Bip001`」，插件就把其余所有带蒙皮的骨链当成衣物 ——
  Sophie 整个人成了一串物理刚体，静止测试里漂移 5 米，舞蹈里飞出去 93 米，检查图里干脆没有她（而我看图时没发现
  少了一个人）。同时胸部的左右是按世界坐标的正负判的，两人并排站、Yuphie 偏在一侧，结果她的左胸被认成「右胸」、
  另一边没有物理。修法：转换时把所有 `Bip\d+` 都算作身体；胸部的左右按主骨架的脊柱量，且优先取挂在主骨架上的胸部骨。
  教训：PMX 的报告里有**静止下落测试**（`rest_drop_test`）和「刚体离胯部最远多少米」，批量之后要把这两个数排个序看
  最大的几个 —— 这次就是这样查出来的，光看缩略图看不出来。
- **裙子的骨头名拼错了**：`24_kirara`、`86_robel`、`248_mari` 的裙子骨叫 `Bone_*_Skrit_*`。`mmd_cloth_physics` 按名字选
  预设，认不出来就当成软的「丝带」。转换时把 `skrit` 也算作 skirt（只在本次运行里改插件的名字表，不动插件文件），
  裙片硬了一些；但 Mari 的短裙仍会穿腿，见「已知限制」。
- **「骨架是不是竖着的」不能用高度和进深比**：复用的 worker 在烘完变换后检查「骨头的 Z 跨度 ≥ Y 跨度」，
  用来发现 FBX 导入的 Y-up 骨架。穿着 6 米触手裙的 Boss（`b_10_monday`、`b_13_thursday`）进深比身高大，被误判。
  我们的 `.blend` 构建时就是 Z-up，这条检查在这里跳过。
- 有的网格位置 / 法线是 float4（第四个分量是填充），取前三个。
- headless Blender 里 `bpy.data.objects.remove()` 之后要 `view_layer.update()`，否则 `view_layer.objects` 里还留着
  已删除的物体（Blender2XPS 在这上面崩过）。
