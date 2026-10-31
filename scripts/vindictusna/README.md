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
python export_model.py lynn --upscale --xps --pmx   # 高清版：颜色贴图和染色遮罩 AI 放大 4 倍，另存为 <外观>_HD
python export_model.py --npcs --xps --pmx     # 剧情 NPC 和女性 Boss（looks.NPCS，7 个，见第 11 节）
python export_model.py dwyn --xps --pmx       # 其中一个
python html\make_gallery.py                   # 画廊 html\index.html
python html\make_hd_gallery.py                # 原版 / 高清版同机位对比 html\hd.html（缺的对比图先渲）
```

其他参数：
- `--hair <发型模型>`：换发型；
- `--head`：带上服装的帽子或头盔；
- `--variant create`：用服装的另一个版本，例如创建角色界面那版；
- `--no-figure`：不套角色体型；
- `--redo`：重新构建；
- `--prepare-only`：只解包、转贴图、写配置。并行导出前先单进程跑一次；
- `--upscale`：导出高清版（见下面第 10 节）。并行导出前先单进程跑一次 `--prepare-only --upscale`，GPU 放大都在这一步做完。

## 输出

`E:\game_export\VindictusNA\<角色>\`（`scripts/archive` 的布局）：

| 位置 | 内容 |
|---|---|
| `blend\<外观>\<外观>.blend` | 一副骨架（游戏的 ValveBiped 骨骼名）+ 身体、脸、眼睛、头发、服装，材质按游戏着色器还原，贴图在 `textures\`（相对路径），文件里有「说明」文本 |
| `blend\<外观>\<外观>_front/_34/_side/_back/_face.png` | 预览 |
| `xps\<外观>\<外观>.xps` | XPS，骨骼改成 XPS 标准名（XPS 姿势能套），染色材质烘成贴图，附 blender2xps 报告 |
| `pmx\<外观>\<外观>.pmx` | MMD 模型，骨架、IK、身体刚体、胸部和衣摆物理，`textures\`，`<外观>_converted.blend` |

外观名 = `<角色>_<服装>`，例如 `Lynn_OrientalOdyssey`；高清版是 `<外观>_HD`，三种格式各一个文件夹，和原版并排，
PMX 在 MMD 里的名字带「·高清」。中间文件在 `E:\tools\vindictusna`（`VINDICTUSNA_WORK`）：

- `root\`：解出来的游戏文件；
- `png\`：转好的贴图；`png_hd\`：放大 4 倍的副本（同名），`png_hd\_comp\` 是叠了眉毛的脸部贴图的放大版（按内容缓存）；
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
| 贴图的 Alpha | 只有材质本身透明（`$alphatest` / `$translucent` / 头发）时才是透明度；其余是游戏的高光 / 次表面遮罩，脸部贴图在脸上平均 0.7–0.9，Iset 的身体只有约 0.05。Straight 模式下 EEVEE 会把颜色贴图的 Alpha 乘进颜色：Alpha 为 0 的像素变黑（Dwyn 的眼球画在脸部贴图角上，Alpha 0，整只眼睛是黑的），脸上 Alpha 低的地方（眼周、唇线、鼻孔）被压暗。所以不透明材质用的贴图设成 Channel Packed，颜色原样。法线等非颜色数据的贴图不受影响（实测改不改渲染结果逐像素相同） |
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

Eire 不一样：她的 15 个 flex 是 HL2 式的面部动作单元（FACS），没有 `blink` 这类整脸表情。脸上没有 `blink`、有 `lid_droop` 时
改用 `FACS_MORPHS`（每个标准名一个来源，可乘系数、可只取一侧）：

| MMD | 取自 |
|---|---|
| まばたき / じと目 | lid_droop（上眼睑整个落下，能完全闭眼）/ lid_droop × 0.5 |
| ウィンク / ウィンク右 | lid_droop 只取 +X（模型左边）/ 只取 −X |
| びっくり / 困る / 怒り | lid_raiser / inner_raiser / lowerer |
| あ / い / う / お | mouth_drop / stretcher / lip_oo / lip_oh |
| にっこり / ∧ | corner_puller / conner_depres（游戏里就拼成 conner） |

她的 `upper_left` / `upper_right` 只让眼睑跟着视线动一点（最多 1.5 mm），不是眨眼；女主角们也有这两个，但她们有 `blink`，
仍走上面那张表，结果不变。

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
- 手臂扭转辅助骨（`ForeTwist`、`Shoulder01`）接成 腕捩 / 手捩，不当布料；
- 贴图的 Alpha：MMD 会把每张贴图的 Alpha 乘进材质，游戏放在 Alpha 里的遮罩就成了透明度——脸发虚、Dwyn 的眼睛消失、
  Iset 的身体几乎看不见。所以只被不透明材质用到的贴图，导出后 Alpha 填成 1（`fill_mask_alpha`，颜色逐像素不变；
  头发、睫毛、镂空布料照旧透明），报告里 `opaque_textures` 列出改了哪些。XPS 不受影响：blender2xps 给不透明材质选的是不带 Alpha 的渲染组。

### 10. 高清版（`--upscale`，AI 放大）

游戏贴图已经是游戏里的最大尺寸（瞳孔多为 64 px，脸 512×256），近距离特写会糊。`--upscale` 用 AI 把它们放大 4 倍（最大 4096），
另存一份 `<外观>_HD`，原版不动：
- 模型：4x-UltraSharp（`esrgan.py` 自带 ESRGAN 网络，PyTorch + CUDA 跑，不用装别的包；权重放在仓库外的 `E:\tools\upscale\models`）。
  在琳身上比过三种：Real-ESRGAN x4plus 会把布纹抹平成油画感，动漫版更平，还会在染色区域的边缘描黑边（染色后成黑缝）；
  UltraSharp 保留游戏原来的布纹和虹膜纹理，只是变锐利；
- 放大哪些：材质里 `$basetexture` / `$basetexture2` / `$iris` 指向的贴图（颜色图，以及服装和头发的染色遮罩——
  它们在 Blender 里是非颜色数据，但衣服的颜色和明暗就在里面），加上眼球的完整眼白图、叠了眉毛的脸部贴图，
  以及别名借来的贴图（比如借用的瞳孔）。法线、`$phongexponenttexture`、`$envmapmask`、`$hairmask` 等保持游戏原尺寸：
  AI 是拿照片训练的，放大法线和遮罩会出错；
- 透明通道用 Lanczos 普通放大，镂空和遮罩不会被 AI 补细节；
- 缓存：`png_hd\<同名>.png`，几位角色共用的贴图（比如身体）只放大一次；叠了眉毛的脸部贴图每次构建都会重新合成，按内容哈希缓存；
  构建时先找 `comp\`、再找 `png_hd\`、最后 `png\`，染色判断的统计数据按文件名查，和原版一致；
- 效果（琳）：瞳孔、眉毛提升最明显，衣服略锐利，全身远景看不出差别；皮肤会更光滑一点。新增的细节是 AI 补出来的，游戏里本来没有；
- 体积：每位约 190 MB（原版约 45 MB）；放大约 15 分钟（一次），之后每位构建 + XPS + PMX 约 12 分钟，XPS 占一大半
  （blender2xps 按 4096 的贴图逐材质烘焙）；高清 PMX 一步的 Blender 峰值约 4 GB 内存（芈璃实测 4.0 GB），
  别的窗口也在跑 Blender 时最多并行 2 组（10-31 下午 4 组加上别的窗口把内存用光，批量被中止过）；
- `html\make_hd_gallery.py` → `html\hd.html`：每位角色的原版和高清版用 `compare_views_blender.py` 同机位渲脸、眼睛、衣服、全身，
  页面上拖动分界线对比；对比图在 `E:\game_export\VindictusNA\_meta\hd_compare\`。渲染前两边都按第 4 节的贴图 Alpha 规则设置
  （之前做的原版 .blend 还是 Straight），差别只来自贴图。

### 11. 剧情 NPC 和女性 Boss（`looks.NPCS`，`--npcs`）

NPC 和 Boss 的游戏模型是一整个（身体、脸、头发、衣服都在里面），不用拼装，也不套体型；贴图是烘好的，不用叠图层。
`export_model.make_config_npc` 为它们写配置，`looks.note_npc` 写「说明」。现在 7 个（贴图齐全或只缺一张能借的）：

| 键 | 模型 | 说明 |
|---|---|---|
| `ceara` | `npc/ceara/npc_ceara.mdl` | 菲欧娜的脸和头发就是借她的；发色用游戏的外观预设 `csf/npc_ceara.csf`（暗红，和立绘一致） |
| `eire` | `npc/eire/npc_eire.mdl` | 第二季剧情 NPC（模型的事件表是 Crom Cruach、Elahan 两段结局过场）；棕发、长裙，眼睛是她自己的瞳孔 |
| `iset_npc` | `npc/iset/npc_iset.mdl` | 长袍、兜帽 |
| `dwyn` | `npc/female/dwyn_face.mdl` | 骑士板甲露脸版（第 8 章过场用）；缺牙齿贴图，借琳的；头盔和羽饰默认隐藏：整个挂在道具骨 `bone_helmet` 上，绑定姿势下飘在头左边约 60 cm（`hide`） |
| `dwyn_helmet` | `npc/female/dwyn.mdl` | 同一身板甲戴着头盔、不露脸，贴图齐全；颜色和 `dwyn` 一样是自己配的 |
| `lady` | `monster/lady/lady.mdl` | 人偶 Boss，面具；伙伴版 `lady_mate.mdl` 是同一个网格 |
| `iset_boss` | `monster/iset/iset.mdl` | Boss 战本体，高 2.17 m |

- 官方颜色：`csf\*.csf`（3,501 个外观预设，KeyValues，每个部位一块，`"color"` 是三个打包的 0xRRGGBB 整数，-1 = 不染）。
  `looks.csf_colours()` 读出来；NPC 写了 `csf=` 就按它给头发（`hair_mats`）和上衣染色。没有预设的（Dwyn）用 `dyes=`，说明里写明是自己配的；
- 眼睛：Ceara 和 Eire 有眼球网格和眼骨；其余眼睛画在脸上（Dwyn 的眼球是脸部材质的一部分），PMX 不建眼骨，
  `fix_eye_pivots` 允许一只眼骨都没有；
- 怎么算「贴图齐全」：只看网格实际用到的材质，以及这些材质的 vmt 写的贴图。MDL 的贴图表里还有眼球的虹膜材质（`*_pupil_l01`）
  和 `glint`（引擎的眼睛反光），但没有网格画它们：眼睛的虹膜来自眼球 vmt 的 `$iris`。只按贴图表数，Eire 就像是缺两只瞳孔，
  其实她的 `$iris`（`npc_eire_pupil_l` / `_r`）都在；
- 不算在内：Alice 用的是男主角 Lann 的脸和头发、男式胸甲（男性模型）；Morrighan / Ti / Sereuha 缺皮肤、脸等主要材质；
  女性 Boss 里只有 Lady 和 Iset 齐全，Macha 缺牙齿和翅膀，其余缺的更多（缺的材质连 vmt 都不在北美服的包里）。

## 依赖

- Python：`unicorn`、`pefile`、`numpy`、`Pillow`；`--upscale` 另需 PyTorch（CUDA）和放大模型权重（`UPSCALE_MODEL`，默认 `E:\tools\upscale\models\4x-UltraSharp.pth`；`esrgan.py` 单独用时找 `UPSCALE_MODELS` 文件夹）；
- Blender 3.6.15（`BLENDER`），装好 mmd_tools 和 Convert_to_MMD5；
- Noesis（`NOESIS`），用来把 VTF 转 PNG。少数它不认的未压缩 VTF 由 `textures.raw_vtf_to_png` 处理；
- blender2xps（`BLENDER2XPS`，默认 `E:\code\othercode\blender2xps`）。

## 已知限制

- 19 位女角色的颜色是自己配的。游戏的官方配色在 `csf\` 外观预设里（第 11 节），目前只有 NPC 用上了。
- 金属（`$surface metal`）在 `.blend` 里偏暗：金属度 1 时只剩环境反射，灰色钢板贴图（Ceara 的胸甲、Dwyn 的全身甲）看起来像黑铬；
  游戏是漫反射 + 环境贴图叠加，看着是银灰色。PMX / XPS 里是贴图本来的银灰色。
- 10-31 之前做的 19 位原版 `.blend`（连同它们旁边的效果图、画廊缩略图）贴图还是 Straight：脸部贴图 Alpha 里的遮罩把眼周、
  唇线、鼻孔压暗了一些（`_overview\旧版blend脸部Alpha_对比.png`，琳最明显，菲欧娜几乎看不出）。PMX、XPS 和之后做的 .blend
  （高清版、NPC）没有这个问题；`--redo` 重新构建就好。
- 身体皮肤贴图是游戏原样：胸部和私处没有细节。
- 贴图都是游戏里的最大尺寸，没有缩小：瞳孔多为 64 px，眼球 128，脸 512×256（7 位是 1024），头发 512–1024，服装多为 512–1024（4 套 2048），身体 1024。所以近距离特写会糊，尤其是瞳孔和眉毛；`--upscale` 的高清版用 AI 补了细节（第 10 节）。
- 不带武器。
- XPS 没有表情（格式不支持形态键）；表情在 `.blend` 和 PMX 里。
