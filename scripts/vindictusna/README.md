# Vindictus（洛奇英雄传 / Mabinogi Heroes）北美服 模型导出

NEXON 的 Vindictus，Source 引擎改版。北美客户端（Nexon 启动器）装在 `D:\vindictus\appdata\en-US`，约 45 GB。
这套脚本把女性角色导出成三种格式：

- `.blend`：游戏原始材质，贴图全分辨率；
- XPS（XNALara）；
- MMD PMX：带物理。

国服客户端（世纪天成，`E:\TCGameApps\cmh\zh-CN`）用的是同一种包格式、同一份读包 DLL，设置 `VINDICTUS_DIR` 后也能用。
这里的 `scripts/vindictus/` 是另一个游戏：《Vindictus: Defying Fate》，UE5 版，和本目录无关。

## 快速开始

```powershell
cd E:\code\othercode\ripper_tpose\scripts\vindictusna
python hfs.py --catalog                       # 第一次：扫描 4,369 个包的目录（10 个进程约 11 分钟）
python list_models.py                         # 19 位女角色：脸、发型、内衬模型，以及缺哪些贴图
python list_models.py --outfits --complete    # 贴图齐全的女性服装
python export_model.py lynn                   # 琳的默认外观（looks.py）-> .blend
python export_model.py lynn --xps --pmx       # 再出 XPS 和 PMX
python export_model.py lynn --outfit valkyrie # 换一套服装（models/armor/ 下的文件夹名）
python export_model.py lynn --nude            # 只要完整身体
python export_model.py --all --xps --pmx      # 全部 19 位
```

其他参数：
- `--hair <发型模型>`：换发型；
- `--head`：带上服装的帽子或头盔；
- `--variant create`：用服装的另一个版本，例如创建角色界面那版；
- `--no-figure`：不套角色体型；
- `--redo`：重新构建；
- `--prepare-only`：只解包、转贴图、写配置。并行导出前先单进程跑一次。

## 输出

`E:\game_export\VindictusNA\<角色>\`（`scripts/archive` 的布局）：

| 位置 | 内容 |
|---|---|
| `blend\<外观>\<外观>.blend` | 一副骨架（游戏的 ValveBiped 骨骼名）+ 身体、脸、眼睛、头发、服装，材质按游戏着色器还原，贴图在 `textures\`（相对路径），文件里有「说明」文本 |
| `blend\<外观>\<外观>_front/_34/_side/_back/_face.png` | 预览 |
| `xps\<外观>\<外观>.xps` | XPS，骨骼改成 XPS 标准名（XPS 姿势能套），染色材质烘成贴图，附 blender2xps 报告 |
| `pmx\<外观>\<外观>.pmx` | MMD 模型，骨架、IK、身体刚体、胸部和衣摆物理，`textures\`，`<外观>_converted.blend` |

外观名 = `<角色>_<服装>`，例如 `Lynn_OrientalOdyssey`。中间文件在 `E:\tools\vindictusna`（`VINDICTUSNA_WORK`）：

- `root\`：解出来的游戏文件；
- `png\`：转好的贴图；
- `cfg\`：构建配置；
- `build\<外观>\`：日志。

## 19 位女角色的默认外观（`looks.py`）

| 角色 | 服装 | 说明 |
|---|---|---|
| fiona 菲欧娜 | valkyrie 女武神 | 脸、头发用 NPC「Ceara」的贴图（菲欧娜同款脸，她自己的脸部贴图对不上网格） |
| evy 伊菲 | dorothy 多萝西 | 脸部贴图游戏里没有，借用 Ceara 的脸 |
| vella 维拉 | dancingblade 舞刃（创建角色版） | 脸、眼睛贴图都没有，借用琳的 |
| lynn 琳 | oriental_odyssey 东方奥德赛（带斗笠） | |
| arisha 艾莉莎 | silverfox 银狐（创建角色版） | 发型也是银狐创建版 |
| delia 黛莉娅 | yukata_delia 浴衣 | 头皮贴图缺，用发色 |
| miri 芈璃 | dragon_rises 龙腾 | 脸部贴图没有，借用蕾希的脸；头发用琳的 centipede 发型 |
| miul 缪儿 | devilhunter 恶魔猎人 | 发型用过场动画里她的头发 |
| bel 蓓尔 | white_shark 白鲨（创建角色版） | |
| lethor 蕾希 | kitsunemiko 狐巫女 | |
| tessa 泰莎 | venetian 威尼斯 | |
| danah 丹雅 | rurosakura 流浪樱 | |
| letty 蕾媞 | maid 女仆 | |
| latiya 拉缇雅 | ninja 忍者 | |
| czern 萨恩 | western 西部 | |
| sanyaa 纱妮娅 | darknight 暗夜骑士 | |
| neamhain 内文 | shiningwill 闪耀意志 | |
| calia 卡莉亚 | calia_armor2 专属第二套 | 一块金属件贴图缺，做成纯金属 |
| lumielle 露米艾尔 | highelf 高等精灵 | 她自己的头发贴图没有，用艾莉莎的银狐发型 |

服装的中文名是内部文件名的意译。官方名和默认配色都在加密的道具库（`sqlite/heroes.db3`）里，没有读取。
所以颜色是按角色立绘配的，每个材质的 `VindDye` 节点组可以改。

## 怎么做到的

### 1. 包（`hfs.py`、`hfs_emu.py`）

资源在 `hfs\<sha1>_<NNNNN>.hfs`：每个 sha1 是一个逻辑包，`_00000` 放包头和目录，后面的分卷接着放数据。
当前格式（v4）加密并压缩。脚本没有重新实现这个格式，而是把游戏自己的 `bin\FileSystem_Stdio.dll` 装进 Unicorn x86 模拟器，
直接调用它的打开、读取函数：
- 目录取自 DLL 打开包时解出的索引；
- 文件内容由 DLL 自己解密、解压后交出来。

北美服和国服的这个 DLL 完全相同（SHA1 `8c84dca5…a7`），四千多个包里大部分逐字节相同。北美服共 205,934 个文件。
和国服的差别主要是语音（`sound/voice`）和少量活动模型。

### 2. 模型（`source_mdl.py`）

模型是标准的 Source `.mdl` v44/45 + `.vvd` + `.dx90.vtx`，读取器是自己写的：骨骼、身体部件、网格、权重（每顶点最多 3 根骨）、眼球。
- 女性服装和角色共用一副 77 根骨的 ValveBiped 骨架，绑定姿势完全相同，所以各部件可以直接拼。
- 单位：1 游戏单位 = 1 英寸（0.0254 m）。默认身材高 1.84 m，模型面朝 -Y。

### 3. 完整的身体（`export_model.body_spec`）

游戏的身体在内衬下面是挖空的；45 个内衬模型里，只有 `miri_inner_2020_chn.mdl` 衣服下面的皮肤是完整的。
所有外观都站在这副身体上，它那件小内衣藏起来。另外修了三处：
- **手**：手脚贴图游戏里没有，借玩家身体 `fiona.mdl` 的贴图坐标；
- **脚**：换成玩家身体自己的脚，脚踝一圈 16 个顶点重合；
- **右大腿**：有一圈吊袜带凸起，换成 `lynn_inner_oriental_odyssey.mdl` 的干净右腿。

### 4. 材质（`build_blend.py`）

| 游戏 | Blender |
|---|---|
| 服装、头发、眉毛贴图是**染色遮罩**：R / G / B 是三个染色槽，亮度是明暗 | 节点组 `VindDye`：底色 = Σ (强度 × 通道)^2.2 × 染色。判断方法：亮像素（最大通道 > 0.2）里，第二强通道低于最强的 0.3 倍的占比 > 0.3 就是遮罩；19 位角色的 282 张贴图里，真彩色是 0–0.07，遮罩是 0.42–1（`textures.stat`） |
| `Heroes_Faceskin`（皮肤、脸） | 底色 + 法线 + 次表面散射（半径按真实皮肤：红 3.6 / 绿 1.35 / 蓝 0.75 mm）；`$phongexponentmap` → 粗糙度（嘴唇有光泽） |
| `$surface metal` | 金属度 1，粗糙度 = √(2 / (phongexponent + 2)) |
| `$surface cloth` / `$envmap` | 布料：sheen + 缎面高光 |
| `Refract` | 透射玻璃 |
| 头发（`$hairmask`） | 各向异性高光，顺着发丝；`hairmask` 的 G 通道 → 高光强度；Alpha 用 HASHED |
| 眼睛（`Eyes` 着色器） | 巩膜用网格 UV；虹膜按 studiorender 的方式投影（`IrisUV`）；透明角膜用清漆层。游戏的眼球贴图只有眼皮露出的杏仁形是白的，其余全黑，等于把眼皮的阴影烘了进去；游戏里眼球不转，只移动投影的虹膜，所以看不出来。材质里另放了一张完整眼白（`textures.fill_sclera`：黑色部分用这张贴图自己的眼白色补满，往外稍微压暗），由节点 `FullSclera` 切换：0 = 游戏原样（`.blend` 默认），1 = 完整眼白。XPS / PMX 导出时自动切到 1，因为 PMX 的眼骨会转动整个眼球 |
| 法线贴图 | DirectX 规范（逐张做旋度测试确认），接入时翻转绿通道 |
| 捏脸图层（`materials/models/player/face_layer/<角色>/`） | 眉毛预先叠进脸部贴图，按发色着色（`textures.composite`） |

### 5. 体型（`.fig`）

游戏给每位角色一个默认体型 `csf/bodyshape_<角色>_default.fig`（KeyValues）。
- 内容：逐骨骼的缩放矩阵，有时带位移；`isIndependentFromChild` 表示子骨跟着移动、但不继承缩放。
- 例子：蓓尔的大腿长 0.95 倍、小腿长 0.90 倍、粗 0.85 倍，骨盆下移 3.3 单位，让脚刚好落地，身高从 1.84 m 降到 1.745 m。
- 实现：`build_blend.apply_figure` 用姿势缩放加上子骨「继承缩放 = 无」，在 Blender 里实测和这个语义一致。
  套完烘进网格，再设为静止姿势，所以 `.blend`、XPS、PMX 都带体型。
- 没有体型文件的角色保持默认身材。

### 6. 游戏数据里本来就没有的贴图

北美服和国服缺的完全一样，所以这些是游戏运行时才合成，或者根本没随客户端发布：
- 老角色的玩家脸部贴图：菲欧娜、伊菲、维拉、芈璃；
- 手脚贴图；
- 若干发型和服装的头皮、半透明、金属部件；
- 新角色专属初始服装（`calia_armor1`、`lumielle_armor*`、`sanyaa_armor*`、`neamhain_armor*`）的大部分贴图。

替代方法见 `looks.py`，每个 `.blend` 的「说明」里逐条列出。

借脸部贴图时，脸型保留她自己的网格，贴图来自另一张脸，分两步：
1. 每个角点取对方脸面上最近点的贴图坐标。按法线匹配，避免嘴唇取到口腔里面。
2. 对每块 UV 岛，用稳健最小二乘拟合一个 4 次多项式：自己的 UV → 对方的 UV。

只做第 1 步的话，两张脸五官位置的差异会把嘴唇撕开（`build_blend.uv_from` 的 `warp`）。

### 7. XPS（`export_xps_blender.py`）

`.blend` 进 Blender 后：
1. 先把骨骼改成 3ds Max Biped 名（`rig.py`）。ValveBiped 本来就是 Max 的 Biped，层级一样：`Bip01 → Pelvis → Spine`，大腿挂在 Spine 下。
2. 去掉不带蒙皮的挂点骨 `Anim_Attachment_*`。
3. 交给隔壁仓库的 [blender2xps](../../../blender2xps)：
   - Biped 名映射成 XPS 标准名；
   - 染色材质烘成 `*_baked.png`；
   - 法线贴图原样带上（XPS 也用 DirectX 规范）。

### 8. 表情（Source flex）

脸部模型带 Source 的 flex：顶点动画，按名字分在脸、睫毛、牙齿等网格上。
- 名字包括 `blink`、`smile`、`happy`、`wink`、`sad`、`sorry`、`angry`、`hurt`、`surprised`、`chew_down`、`ah`、`woo`、`oh` 等，各角色 18–39 个。
- `source_mdl.py` 读出位移（半精度浮点，按网格顶点编号）。
- `build_blend.py` 在每个带这个名字的网格上建同名形态键，所以 `.blend` 里可以直接拧。
- 体型烘焙会逐个形态键算形变，因为带形态键的网格不能直接应用修改器。
- PMX 时由 `export_pmx_blender.add_morphs` 做成 MMD 顶点表情：每个标准名取第一个存在的 flex，原始 flex 也全部保留在「その他」里。

| MMD | 取自 |
|---|---|
| まばたき / 笑い / じと目 / びっくり | blink / blink_smile / blink_half / surprised |
| ウィンク / ウィンク右 | wink_L / wink_R；只有一个 `wink` 时按位移所在的一侧判断左右，另一侧按 X 镜像生成 |
| 真面目 / 困る / にこり / 怒り / 上 | hostile / sorry / mild / angry / brow_up |
| あ / い / う / え / お | ah（没有时用 chew_down）/ mouth_e_half / woo / mouth_e / oh |
| にっこり / にやり / ∧ | smile / sneer / frown |
| 喜び / 悲しい / 痛い | happy / sad / hurt |

游戏的 flex 是整张脸的表情，不是分区的；眉毛类的 morph 也会带动嘴。
检查用的特写：`morph_sheet_blender.py`，在 `<外观>_converted.blend` 上逐个表情渲染。

### 9. PMX（`export_pmx_blender.py`）

走 Stellar Blade / Rise of Eros 那条 Biped 链：
- mmd_tools 写 PMX；
- Convert_to_MMD5 建 MMD 骨架、IK 和身体刚体；
- mmd_cloth_physics 处理衣摆和头发骨。

这里补的部分：
- 骨骼改名（同 XPS）；
- 两眼骨：游戏在着色器里转眼球，没有眼骨。眼球网格只是**前半个球壳**（琳：半径 18 mm、深 17 mm），共用脚本按整球估转轴（最后面的点 + 半径），结果落在角膜上，一转眼眼球就从眼皮里甩出来；`fix_eye_pivots` 改用球面拟合的球心，多数角色的眼骨因此往后挪 17–21 mm（菲欧娜、伊菲、维拉的老式眼球网格半径约 14 mm，挪 8–9 mm）。
  共用脚本（`stellarblade/export_pmx_blender.add_eye_bones`）按「在头骨哪一侧」分左右眼，以前在循环里读头骨位置，而第一只眼建骨时切过一次编辑模式，Blender 重建了骨骼，之前拿到的头骨引用就指向已释放的内存。Vindictus 每只眼球是单独的网格，第二只眼读到的是乱值，19 位里有 4 位（艾莉莎、萨恩、纱妮娅、泰莎）两只眼挂在同一根眼骨上。现在头骨位置在切模式之前读一次。`fix_eye_pivots` 也加了检查：必须正好找到两只眼，拟合半径必须在 5–30 mm，否则报错，不会悄悄导出坏眼睛；
- 检查：`blender -b --python ..\stellarblade\preview_pmx_blender.py -- --pmx <pmx>` 在 PMX 旁边生成 `preview_gaze.png`（两眼向左、右、上、下转）、`preview_morphs.png`（表情）和 `preview_dance.png`（带物理跳舞），画廊会显示后两张；
- 胸部：皮肤挂在 Source 摆动骨 `jiggle_L/Rbust_2` 上，映射成 左胸 / 右胸，各加一个球形刚体和一个弹簧关节；
- 手臂扭转辅助骨（`ForeTwist`、`Shoulder01`）接成 腕捩 / 手捩，不当布料。

## 依赖

- Python：`unicorn`、`pefile`、`numpy`、`Pillow`；
- Blender 3.6.15（`BLENDER`），装好 mmd_tools 和 Convert_to_MMD5；
- Noesis（`NOESIS`），用来把 VTF 转 PNG。少数它不认的未压缩 VTF 由 `textures.raw_vtf_to_png` 处理；
- blender2xps（`BLENDER2XPS`，默认 `E:\code\othercode\blender2xps`）。

## 已知限制

- 颜色是自己配的，不是游戏的默认配色（道具库加密，没有读取）。
- 身体皮肤贴图是游戏原样：胸部和私处没有细节。
- 贴图都是游戏里的最大尺寸，没有缩小：瞳孔多为 64 px，眼球 128，脸 512×256（7 位是 1024），头发 512–1024，服装多为 512–1024（4 套 2048），身体 1024。所以近距离特写会糊，尤其是瞳孔和眉毛。
- 不带武器。
- XPS 没有表情（格式不支持形态键）；表情在 `.blend` 和 PMX 里。
