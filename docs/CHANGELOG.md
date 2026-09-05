# 更新日志

本文件记录会改变提取结果、Blender 操作或导出行为的更新，最新内容放在最前面。

今后每次功能更新必须同时补充一条记录，并至少写明：

1. 日期与版本；
2. 新增或修复内容；
3. 用户如何操作；
4. 实现原理与兼容性；
5. 已执行的验证。

日期按项目当前使用时区 `Asia/Shanghai` 记录。

---

## 2026-09-05 — DOA5LR：换服装批量导出（19 人 223 套 COS/DLC）

### 新增与修复

- **`scripts/doa5lr/export_full.ps1`**：`-Archive` 缺省改为 `auto`——首次扫游戏目录全部
  36 个 `.bin` 建 `<OutRoot>\_archive_index.txt`（条目名 → 封包），之后每个部件各自查
  封包；以前一个 `-Archive` 管三个部件，服装在 `chara_common` 而脸/发型在 `chara_initial`
  的角色（霞、绫音）换装时会解不出脸。已提取过的部件目录（`<OutRoot>\<条目>\<条目>\*.fbx`）
  直接复用，不再每次 `-Force` 重解包——这也是三路并行不互相踩脸/发型目录的前提。
- **`scripts/doa5lr/build_blend.py` 就位判据放宽**：脸/头发「顶端够到身体顶端」的余量
  由身体高度 5% 放宽到 25%。兔女郎类 DLC（`AYANE_DLC_006/007` 等 11 套）的兔耳把身体
  包围盒顶端撑高约 15%，脸和头发被误判为未就位而整体上移 ~25 cm。真正未就位的头发
  （用自己原点、悬在腰腹，顶端只到 0.6）仍能判出。
- **`scripts/doa5lr/html/collect_manifest.py` / `make_gallery.py`**：从文件名解析服装条目
  （`<角色>_<名>_<COS|DLC>_<NNN>`，无后缀即 `COS_001`），封包徽标按整个服装条目名查
  （原来只认 `_COS_001`），卡片加服装号徽标，工具栏加**按角色下拉筛选**，搜索框也搜服装号。

### 用户如何操作

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa5lr
.\export_full.ps1 KASUMI_COS_002 -Face auto -Hair 001 -Label KASUMI_Kasumi_COS_002   # 单套
# 批量：python extract_lnk.py <bin> --list 抓 <角色>_(COS|DLC)_NNN.TMC 做清单后循环上面这条
blender --background --factory-startup --python html\collect_manifest.py
python html\make_gallery.py --force
```

### 本批结果

19 名女性角色在 `chara_common` / `chara_initial` 里共 245 个 `COS/DLC` 条目：19 个 COS_001
早已导出，3 个是 10 KB 占位（`MILA_COS_008`、`SARAH_DLC_002`、`PAI_DLC_002`），其余
**223 套全部出 .blend**（三路并行，每套 5–16 s），在 `D:\doa5lr_exports\_blends\`，
对照表见该目录 README §1。头发统一 `HAIR_001`（官方每套服装的默认发型无法从条目名得知）。
`DLCU_NNN`（47 套）未导。

### 验证

- `KASUMI_COS_002`：84 材质重建、135 贴图打包、脸/发型复用无重解包。
- 223 套预览拼图逐一目视：Alpha-152 通体白色仍是素材本身；兔耳装修复前后对比
  脸/头发回到颈部；无其它对齐或材质异常。

---

## 2026-09-05 — DOA6：mod 导出支持发型/脸部件，批量转出 45 个社区 mod 变体

### 新增与修复

- **`scripts/doa6/export_nude_mod.ps1` 重写为按部件驱动**：以前只认 mod 里的服装 g1m，
  现在按 `<CHR>_<COS|HAIR|FACE>_<NNN>` 把 mod 的 g1m 分类，mod 给什么就换什么，
  缺的部件用官方 `COS_001 / FACE_001 / HAIR_001` 补齐（`-Cos/-Face/-Hair` 改编号）。
  `-Chr` 可省略（按 g1m 名推断），`-Label` 缺省由 zip 名生成，新增 `-NoPreview`。
  `-Cos/-Face/-Hair` 除编号外也接受完整部件名（`-Face AYA_FACE_001`，body-swap 类 mod
  用别的角色的脸），官方件本机没导出过时自动调 `export_character.ps1` 现场导。
- **mod 自带 `<id>.ktid` 优先于原版**：Yor Forger 的发型 mod 把贴图槽位从 6 个扩成
  13 个，用原版 ktid 解析时 44 个 submesh 全部无贴图（渲成白发）。现在先找 g1m 旁边
  的 ktid；另加兜底——路线 A 若留下有顶点却无 albedo 的 submesh，自动改走启发式。
- **mod 若带官方部件的贴图（如 `PHFFACE001_face_kidsalb`）**，把官方部件复制一份叠上
  mod 贴图再组装，不再丢弃这些贴图。
- **`mod_matmap.py --key <部件键>`**：多部件 mod 的 Material 目录混着几套贴图，
  启发式只看本部件的 g1t（无匹配时退回全部）。
- **`html/collect_manifest.py`**：mod 变体的判定从「服装目录是 `<Label>_cos`」放宽到
  `_cos/_face/_hair` 任一，贴图计数同样覆盖三个目录；否则发型 mod 会被标成官方。
- 两处老坑再次踩到并修掉：PowerShell 函数里 python 的 stdout 会混进返回值
  （`$partDirs` 变脏 → "blend 未生成"），全部改成 `| ForEach-Object { Write-Host }`；
  Blender 输出改写到 `_blends\<Label>.log`，失败时打印尾部而不是静默。

### 用户如何操作

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa6
.\export_nude_mod.ps1 D:\doa_mods\doa6\_zips\<mod>.zip -Label MOM_Momiji_LooseHair   # 发型 mod
.\export_nude_mod.ps1 <zip> -Label PHF_YorForger_Bikini                              # 服装+发型 mod
.\export_nude_mod.ps1 <已解压目录> -Chr AYA -Label AYA_Ayane_Fachan2 -Assign "5=body"  # 纠正启发式
```

产物 `D:\doa6_exports\_blends\<Label>.blend` + `_preview.png`，部件暂存目录
`<Label>_cos / _face / _hair`。全部 mod 的对照表与已知缺陷见 `D:\doa6_exports\README.md` §1.5。

### 本批结果

`D:\doa_mods\doa6\_zips\` 里 39 个 zip：2 个是重复文件；Rosario+Vampire Moka（108 MB）
首次下载被 GameBanana 截断到 18 MB，`curl -sL --retry 3` 重下后是 10 个子 mod 的合集包，
出了 7 个可用的（白发 Moka × Kokoro 服装 5 个、粉发 Honoka 校服 2 个）。其余 36 个 +
早先 5 个，共 **45 个 .blend 全部成功**（三路并行，每个 11–32 s）。人工看预览后处理了：

- `SKD_Tamaki_*`（5 个）：Tamaki 是未装 DLC，本机没有脸/发型，只出身体（脚本警告而非报错）。
- `SKD_Tamaki_NudeMicroBikini`、`AYA_Ayane_Fachan2` 原 mod 不带皮肤 albedo，
  从同角色其它 mod 借了 `*_body_kidsalb/nmh` 放进 `D:\doa_mods\doa6\_patched\` 副本重跑。
- `AYA_Ayane_TropicalTune2`：g1m 里身体的三角面被删光（顶点还在），是 mod 本身如此。

### 验证

- Yor Forger：修复前预览白发，修复后黑发+金饰，`matmap.json` 里 43 个有顶点 submesh 全部有 alb。
- 45 个预览拼图逐一目视：无皮肤/衣物互换；黑色「Buckle Up」紧身衣与 NSFW1 湿衬衫经
  贴图均值/alpha 统计确认是 mod 设计。
- `mod_matmap.py --key` 对 Yor（27 个 g1t 混三部件）只取 `PHFCOS037` 的 3 个部位。

---

## 2026-08-30 — Rise of Eros：只打包用到的贴图，清理导出目录冗余

### 新增与修复

- **`export_character_model_blender.py` 与 `export_nude_model_blender.py`**：
  `pack_images()` 由"遍历 `bpy.data.images` 全打包"改为只打包**模型材质实际引用**
  的图片（沿材质节点树收集 `TEX_IMAGE`）。

### 根因

FBX 导入时 Blender 会**按 FBX 同级目录**为文件里提到的每张贴图创建图片数据块，
而插件随后是用 `_textures`（或暂存目录）里的副本重建材质的——两套数据块并存，
后者才被材质引用。旧的 `pack_images()` 不加区分地全打包，于是：

1. **.blend 里嵌入了大量没有任何材质使用的重复贴图**。修复后 g11 的 blend
   从 66.8 MB 降到 31.8 MB（−52%），b01 裸模从 15.8 MB 降到 13.4 MB。
2. 一旦把 `FBX_GameObjects` 子目录里的冗余贴图副本清掉，打包就会硬失败
   （`无法打包文件,找不到资源路径`）——**两条管线都会失败**，不只是穿衣那条。

### 清理脚本入库

- 新增 `scripts/riseoferos/prune_exports.py`（缺省空跑，`--apply` 才删）与纯 Python
  回归 `tests/test_prune_exports.py`。重复副本每次重新提取都会再长出来，所以这是
  常备维护脚本而不是一次性操作。
- 三道安全机制：贴图副本必须与本角色 `_textures` 的同名文件**哈希一致**才删；
  `.blend1` 必须对应 `.blend` 仍在才删（孤儿备份是唯一副本）；`_textures\` 与
  `blend\` 不进入遍历。测试用合成目录覆盖同名不同内容、无 `_textures` 的角色、
  受保护目录里的同名文件、孤儿 `.blend1`，并验证幂等；逐条破坏上述机制均能让
  测试失败（其中去掉受保护目录过滤会导致连 `_textures` 原件一起删）。

### 导出目录清理

`D:\roe_exports` 从 **46.6 GB 降到 28.1 GB**，删除的两类都逐文件校验过：

- **5378 个 PNG / 18.00 GB**：`extract_character.ps1` 每次运行都会把每张贴图
  在 `_textures\` 存一份、又在**每个对象子目录**各复制一份。删除前对每个文件
  与其 `_textures` 孪生文件做了完整 MD5 比对，一致才删。
- **21 个 `.blend1` / 0.53 GB**：Blender 备份，且仅在对应 `.blend` 仍存在时删除。

保留：`blend\`（120 个成品 + 120 张预览图）、`_textures\`（128 个角色目录全部
都有）、全部 FBX、以及子目录里 `_textures` 没有的 164 个独有 PNG（含 XPS 流程
烘焙的 `roe_eye_baked.png`）。

> **教训**：清理前我判断"两条管线都不受影响"，理由是材质读的是 `_textures`。
> 这个判断漏了 Blender 导入器自己创建的那批数据块——**材质用不到，打包却会碰**。
> 结论是对的（那些副本确实是冗余），但必须先修 `pack_images()` 再删。

---

## 2026-08-30 — Rise of Eros：修复 a00 眼球（头身合一、无 Eyeball 骨骼组）

### 新增与修复

- **`export_character_model_blender.py`**：`find_head()` 返回 `None`（头身合一）时，
  按几何特征认出眼球组件（250–800 面 + UV 基本铺满 0–1）并追加
  `module.eye_mat()` 程序化眼球材质；manifest 新增 `fusedHeadEyes` 字段。
  详见[避坑手册 #16](roe-material-pitfalls.md)。

### 问题与根因

a00 通用素体双眼渲染成白褐色碎块。它的网格叫 `pc_a00_nk`（不是 `*_nk_body`），顶点组
只有 `Bip000 *` 骨骼、**没有 `Eyeball` 组**，名字里也没有 `head` 词元——`find_head()`
两条判据全落空返回 `None`，眼/睫/眉分类整个被跳过；裸模 worker 的
`split_combined_nude_body` 又因为名字不匹配 `(?:^|_)nk_body$` 直接返回 `None`。
**两条既有路径都没接住它**（README §4 那句"a00 两网格/两材质"正是这个状态）。

但 a00 的眼球本身完全标准：两个 432 面、UV 铺满 0–1（0.0004–0.9995）的组件，签名与
g06 等角色一致。它们拿到了身体图集，满 0–1 的 UV 去采样身体图就渲成了碎块。

修法是在没有独立 head 网格时按几何特征直接认眼球，而**不是**放宽 `find_head()`——
把整块身体当 head 交给 `classify_head` 会把大半个躯干判成脸，那正是
`split_combined_nude_body` 当初要解决的问题。

### 验证

- a00 命中 864 面（2×432）挂上 `eye_mat`，材质槽 2→3，虹膜贴图
  `pc_a_nk_eye_iris_rgbx_Albedo.png` 进入 textures；特写渲染确认蓝色虹膜、瞳孔、
  眼白都正常。
- 守卫只在完全找不到独立 head 网格时触发，120 个模型里只有 a00 属于这种情况。

---

## 2026-08-30 — Rise of Eros：修复 g05 "没有眼球"（显式 face 槽抢走眼球）

### 新增与修复

- **`roe_xps_addon.py` / `classify_head`**：为 F10 加的"显式 face 槽 → 强制 slot 0"
  逐面覆盖增加 `and slot != 1` 例外，组件级判定为眼球的面不再被拉回脸。
  详见[避坑手册 #15](roe-material-pitfalls.md)。
- **`export_character_models.ps1`**：硬告警从只看 `face` 扩展到 `face` + `eye`
  两个槽（其余槽为 0 可能是正常的，判读表见避坑手册）。

### 问题与根因

用户报告 `pc_g05_hd.fbx` 眼睛没有眼球。`headSlots` 一眼定位：g05 的 eye 槽 **0 个面**，
而同体型 g01/g04/g06 都是 864；那 864 个面并进了 face（14,633 = 13,769 + 864），
所以眼球被刷上了脸部贴图。

眼球的连通块识别其实完全正常——428 面、Eyeball 权重 0.998、UV 铺满 0–1，
`w['eyeball'] > 0.9` 直接命中。问题在最后那轮逐面覆盖：g05 的原始槽是
`['pc_g_nk_face', 'pc_g_nk_eyebrow', 'pc_g_nk_tears']`，**没有 `pc_g_nk_eyes`**，
眼球面挂在 face 材质索引上，于是那条为 F10 加的覆盖把判对的眼球又拽回了脸。
g01/g04/g06 都有独立 eyes 槽，所以不受影响。

### 验证

- g05 恢复 `face/eye/lash/brow/overlay = 13769/864/660/228/548`，与同体型一致；
  渲染确认虹膜正常。
- 十个敏感角色（含 F10）改前改后**逐槽面数完全一致**，5 个合成回归测试全过。
- 全量重跑无 `face`/`eye` 为 0 的告警。

### 顺带澄清：槽为 0 不一定是缺陷

新增的 `headSlots` 扫描还查出 f11 `lash=0`、k06 与 i01–i04 `brow=0`。逐个看渲染确认
**都是正常的**：f11 眼部整个被金色面罩盖住、k06 戴眼罩且刘海遮眉、i 体型的眉毛本来
就烘进 face 图（坑 #13 已有记载）。因此硬告警只覆盖 `face` 与 `eye` 两个"为 0 必错"
的槽，其余留在 `headSlots` 供人工判读，避免噪音淹没真问题。

---

## 2026-08-30 — Rise of Eros：修复 f05 "没有脸"（残缺原始材质表）

### 新增与修复

- **`roe_xps_addon.py` / `classify_head`**：原始材质槽里有 eye/brow/lash/tear 这类
  特征槽、却**没有任何 face 槽**时，判定这份表不可信，清空 names 与 indices 走几何
  回退。详见[避坑手册 #14](roe-material-pitfalls.md)。
- **`export_character_model_blender.py`**：统计 head 每个材质槽的面数，新增
  `headSlots` 与 `headFacePolygons` 两个 manifest 字段；`export_character_models.ps1`
  在 `headFacePolygons` 为 0 时红字报警。

### 问题与根因

用户报告 `pc_f05_hd.fbx` 与 `pc_f05_outfit1_hd.fbx` 导出后没有脸——一对眼球悬在头发
里，下半张脸空白。**所有既有检查都是绿的**：插件自检 `缺贴图 0`，manifest 的
`untexturedSlots`、`familyMismatches` 全空，face 槽还正确挂着
`pc_f_nk_face_rgbx_Albedo.png`。贴图没问题，**是那个槽一个面都没有**。

这两份 FBX 的 head 只保留了 `pc_f_nk_eyebrow` 和 `pc_f_nk_tears` 两个原始材质槽，
face 和 eyes 槽在打包时就丢了，整张脸的多边形挂在这两个残存索引上。`classify_head`
见到有原始槽名就信任：`source_is_tear` 把 11,172 个面判给透明罩层，
`source_is_brow_or_lash` 把另外 8,376 个面判给睫毛眉毛，face 槽剩 0 个面。

同角色的 `pc_f05_hd (1)` 压根没有原始槽名，走几何回退反而分对了（face 18,322 面）
——**一份残缺的表比完全没有表更有害**，所以正确做法是识别并丢弃它，而不是换 FBX：
`(2)` 才有正确的三槽身体分区，`(1)` 只有一个身体槽且会按通配符错挂成 outfit1 贴图。

### 验证

- f05 两个模型 face 槽由 0 恢复到 18,322 面，渲染确认脸、角、精灵耳与红披风配色正确。
- a06/a07/a08/b02/f06/f10/g09/i03/j01/m02 十个角色改前改后**逐槽面数完全一致**
  （0/10 变化），5 个合成回归测试全过。
- 全量重跑 123 个条目，无 `headFacePolygons=0` 告警。

### 顺带修的一个脚本坑

给 ps1 加中文告警字符串导致整个脚本解析失败（`Unexpected token`、`missing
terminator`），六个分片全部空跑，还把 manifest 覆盖成空的。**PowerShell 5.1 会用 OEM
代码页读取无 BOM 的 .ps1**，多字节中文在 `#` 注释里无害，在**字符串字面量里会拆出引号
破坏解析**。仓库既有 ps1 的中文一律只在注释里，字符串全 ASCII——这条现在写进了文件
注释。教训：改完 ps1 先跑
`[System.Management.Automation.Language.Parser]::ParseFile()` 验证再批量执行。

---

## 2026-08-30 — Rise of Eros：穿衣角色批量材质化 + 预览图，新内容盘点

### 新增与修复

- 新增 `scripts/riseoferos/export_character_models.ps1` 与其 Blender worker
  `export_character_model_blender.py`：把每个已提取角色目录里最合适的模型 FBX
  重建材质、把贴图打包进 `.blend`，并在**同一目录**渲染一张三视图预览 PNG
  （3/4 + 正面 + 头部特写，横向拼接）。这是 §4 裸模批量脚本的穿衣角色对应物。
- 全量执行结果：**120 个模型 PASS、0 FAIL、17 NOMESH**，共 7.0 GB。
  产物在 `D:\roe_exports\<id>\blend\<stem>.blend` + `<stem>_preview.png`，
  全量清单 `D:\roe_exports\character_models_manifest.json`。
- **候选回退与 NOMESH**：worker 的第一个参数改为 `;` 分隔的候选列表，按
  `hd → ld → nk → Prefab_nk_model → nk_bs` 顺序逐个导入，**先检查是否真有网格
  再挂材质**。d10 / e11 / i06 只有 0.3MB 的 `*_nk_bs.fbx`（纯骨架壳，本体复用
  同字母基础体），连同另外 14 个只有 `chara_bare_pc_<id>_nk.ab` 的活动 NPC 一起
  记为 `NOMESH`——这是资源本身的性质，不再算作失败。
- **二次贴图解析**（worker 内，未改动共享插件）：插件挂完材质后，仍无 Base Color
  的槽再查一次 Albedo 索引，**只在唯一命中时**才补挂。规则是逐级放宽的探针——
  原名 → 去尾部 `hd/ld` → 去尾部数字 → 武器再试角色自己的 `wp_<id>` 图集。
  修好 12 个模型的武器/护甲槽（`wp_a_R` ← `wp_a_12`、`pc_h08_hd_armor01` ←
  `pc_h08_hd_armor`、`pc_h07_hd_body2` ← `pc_h07_hd_body` 等）。**能匹配到两张
  图的一律不补**：挂错贴图比留灰更糟，e10 的第三个身体槽（只出 body1/body2）
  就按这条留灰。
- 预览渲染用 **Standard** 视图变换而不是 Blender 默认的 Filmic——Filmic 会把
  Albedo 图集去饱和，导致预览图没法用来判断有没有挂错贴图。补白色取自渲染背景
  的角像素，不再是黑边。
- 新增 `-ManifestPath`：默认那一个 manifest 不支持并发写，多进程分片跑时必须
  给每个分片单独一个，跑完再合并。本次即用 6 分片并行（24 核机器约 25 分钟）。
- README 新增 §5 说明本脚本；原 §5–§10 顺延为 §6–§11，正文交叉引用同步更新。
- 新增 `scripts/riseoferos/html/make_gallery.py` 与它生成的 `html/index.html`：
  按 manifest 出一页可搜索/按体型筛选的模型总览，每卡含预览图、模型名、blend
  完整路径（可复制）、网格与材质槽统计、缺图/补挂角标，附录是导出脚本用法。
  179 MB 预览图缩成 2.9 MB 缩略图（平均 25 KB），**写到
  `D:\roe_exports\_gallery\thumbs\` 而非仓库**——仓库不收游戏素材这条规矩不破。
  页面靠 `file://` 引用本机文件，换机器重跑一次即可。
  踩坑记录：`.card` 上的 `display:flex` 会盖掉浏览器对 `[hidden]` 的
  `display:none`，筛选看着失效，必须显式补 `.card[hidden]{display:none!important}`。

### 顺带处理的资源盘点

- **如何判断游戏有没有新内容**：不要看 Steam 安装目录的时间戳——2026-08-01 的
  整包重下把全部 14046 个 `.ab` 刷成了同一个 mtime，按时间比会误报几十个"过期"。
  正确做法是拿运行时缓存（`%USERPROFILE%\AppData\LocalLow\Pinkcore\...`，约 807
  个文件）和安装目录**按文件名 + 大小做差集**：只在缓存里的 = 全新，大小不同的
  = 更新过。
- 据此发现并处理：新角色 **m02**（已导出 FBX + 45 贴图，并材质化为
  `m02\blend\pc_m02_hd.blend`）、j10 / k02 的新装、m01 的女仆装
  （`suit_maid`，产出 `pc_m01_outfit1_hd.fbx`）、3 件 26AUG 新配饰、新敌人
  `en_flesh_horror_001`。
- **配饰的正确导法**：104 个配饰网格全在 `chara_components_common.ab` 一个包里，
  逐件的 `accessory_<hash>_*.ab` 只有几 KB、是索引存根，贴图在配对的
  `chara_tex_<hash>_*_obj001.ab`。按件建目录会得到 104 份完全相同的 FBX；正确做法
  是把 components_common + 全部 `chara_tex_*_obj001` 一次性提取到
  `D:\roe_exports\components_accessories\`（104 FBX / 285 PNG）。
- 删除假目录 `D:\roe_exports\g16`：18 个文件全是 g/f 家族公共贴图加一把
  `wp_g01`，没有任何 g16 文件；游戏里也不存在 `chara_*_pc_g16` 包（"g16" 只出现在
  `mainstageavg16`、`env_tex_painting16` 这类无关包名里）。

### 用户如何操作

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
.\export_character_models.ps1 -List            # 看可转清单和各自用的 FBX
.\export_character_models.ps1                  # 全部转换，已有产物跳过
.\export_character_models.ps1 -Only m02 -Force # 重做单个角色
```

`.blend` 内嵌贴图、脱离 `_textures` 也能打开；预览图就在 `.blend` 旁边。缺共享
头部贴图而失败时（b01/g04/g05/l01 本次即如此），先补一次
`.\extract_character.ps1 <id> -ExportTextures` 再重跑。

### 验证

- 123 个候选条目全部跑完：120 PASS / 0 FAIL / 17 NOMESH，磁盘上 120 个 `.blend`
  与 120 张 `_preview.png` 数量一致。
- manifest 审计：`familyMismatches` **全部为空**（没有任何模型挂上别的字母体型的
  公共脸/发贴图）；`untexturedSlots` 从 15 个模型降到 3 个，且都确认为资源本身
  没出对应图（a00 的 `liquid` 特效网格、e10 的第三身体槽、j06 的武器）。
- 目检渲染：a01、j01、h08、g04、m02 的预览图逐张确认脸/眼/睫毛/头发/服装/武器
  贴图正确。

---

## 2026-08-30 — Venus Vacation PRISM：素体排查结论与完整裸模组装

### 新增与修复

- 71 个角色候选全部转换目检（export_model.ps1 -Sheet 拼图 + Noesis 兜底）：
  官方素体仅 `0x8baaa1ce.fdata` 内一组模块化展示套件——836 带头假人体
  （皮肤贴图躯干为灰）、**840 无头全裸素体（完整皮肤贴图）**、843 配套头、
  844 配套发、852 手臂；另有 114/118/849 三个内衣体；其余全为服装体。
- 无名模型贴图解析走通：`character_assets.py --component` 的 g1m_id 路径 +
  `_infer_bundle` 包内相邻推断（836 全 21 槽、840 全 10 槽零缺失）；843 有
  6 张贴图缺失，新增 `profiles/nude840.json` 按 Tamaki 模式豁免
  （prune_if_unreferenced）。
- `character_assets.py`：face_v1 虹膜烘焙槽位对参数化
  （`postprocess.face_v1_iris_pairs`，默认 (2,25,26)/(3,35,36) 不变）——
  展示头 843 的眼贴图在 27/28、37/38。
- `blender_assemble_character.py`：`--face` 改为可选（自带头的身体可只配
  发型），无 FACE 时 head_fit 以 BODY 为基准、neck_fit 记为 null；其余
  验证门与产物不变。
- 组装成品：`nude840\complete_nnmhair\Nude840_NNMHair_Aligned.blend`
  （840+843+Nanami 发；face-alpha 1,4,5,7,8,9 修复眼周透明卡片、虹膜烘焙
  正确）。对位勘误：展示件彼此不共位——843 头比标准脸高 ~6.7，840 身体
  领口（zmax 134.7）又低于标准脖口（Nanami 参照 150.6），最初"抬发 +6.92"
  方向错误；正确做法是头 −16.5、发 −9.58（保持发-头相对 +6.92），颈胸
  接缝经 A/B 渲染目检确认消失。native 844 发型版与 836 版一并保留；
  FBX/GLB 为对位前导出，需要时从 Aligned.blend 重导。

### 操作与验证

- `export_model.ps1 -Sheet` 全量 36 候选拼图（Noesis FBX 兜底覆盖 glTF
  关节越界导入失败项）；840 组件三件套 FBX 回读六项验证全过；脸部近景
  目检：虹膜/睫毛/眼影正常，发型对位无露皮。

## 2026-08-30 — Venus Vacation PRISM：export_model.ps1 按需浏览候选模型

### 新增与修复

- 新增 `venusvacationprism\export_model.ps1` + `gltf_to_blend_preview.py`：
  `-List` 列出 71 个角色候选（索引/KTID/骨骼数/大小/已命名标注/已转换标记，
  `-AllModels` 看全部 1,527 个）；按索引/0xKTID/内部名称逐个转换
  （FDATA→G1M→gust basic glTF→`.blend`+前后视图 PNG+统计 marker），
  输出 `models\model_<idx>_<ktid>\`。首次运行自动构建 probe 清单与角色名
  对应表。定位是"按需识别原生模型"，带材质完整人物仍走 export_character。
- 排查记录：36 个未命名角色候选中最大的 idx_830（34.4 MiB / 53 网格 /
  317,086 顶点 / 364 骨）实测为**便服套装体**（T恤短裤凉鞋），非素体；
  BODY 类模型无头/由 FACE+HAIR 补全是游戏拆件设计，并非导出缺失。
  素体是否存在的结论待逐个转换其余候选后更新。

### 操作与验证

```powershell
.\scripts\venusvacationprism\export_model.ps1 -List
.\scripts\venusvacationprism\export_model.ps1 830
```

- 实测 `-List`（71 行，命名/转换标注正确）与 idx_830 全链路
  （glTF 720KB、blend 98MB、前后预览渲染成功，高度 148cm 完整）。

---

## 2026-08-30 — DOA6 / Throne of Desire：补齐导出总览画廊

三个游戏现在都有和 `riseoferos/html/` 同款的画廊（manifest → 缩略图 → 自包含单页），
结构一致，只是各自的分组维度和附录内容不同。

### 新增

- `scripts\doa6\html\`：DOA6 画廊。网格名在组装时已被重命名为
  `<部件目录>_sm<N>`，据此归类部件；服装部件来自 `<Label>_cos` 暂存目录的即判定为
  **mod 变体**（紫色徽标），facet 是 官方 / mod 变体。附录含三部件表、
  `export_full.ps1` 与 `export_nude_mod.ps1` 用法、A/B 两条材质路线、
  以及"别用 Cethleann 解 DOA6"等坑。24 个模型（含 5 个 mod 变体）。
- `scripts\throneofdesire\html\`：ToD 画廊。递归扫导出根下全部 blend，
  `female_all\` 下归为**批量裸模**、其余归为**单独导出**（facet），并入
  `female_export_manifest.json` 的批量状态；统计含面数与贴图打包数。
  附录说明 NFS+NIF/KFM 格式、`build_codecs.py` 前置、以及"静态网格+未绑定骨架"
  这一当前限制。17 个模型（13 批量 + 4 单独）。
  缩略图按 `<组>_<模型>.jpg` 命名——同名模型可能既在批量里又有单独导出。

### 验证

- DOA6：24 卡片 / 24 缩略图 / 页面 37.0KB，官方与 mod 变体分类正确。
- ToD：17 卡片 / 17 缩略图 / 页面 30.3KB，批量与单独导出分组正确。

## 2026-08-30 — DOA5LR：新增导出总览画廊（对齐 riseoferos/html）

### 新增

- `scripts\doa5lr\html\collect_manifest.py`：Blender 无头逐个打开 `_blends\*.blend`，
  按网格名前缀（`WGT_body*`/`WGT_face*`/`WGT_hair*`/`MOT01_Head*`）归类部件，统计
  网格/材质/透明材质/贴图数，写出 `doa5lr_models_manifest.json`；缺脸、缺发、贴图
  过少会记为告警。
- `scripts\doa5lr\html\make_gallery.py`：读 manifest 生成自包含单页
  `html\index.html`（缩略图网格、搜索、按封包筛选、只看告警、点图看原图、
  一键复制 blend 路径）。沿用 ROE 画廊的视觉与交互；缩略图写到
  `D:\doa5lr_exports\_gallery\thumbs\`，**不进仓库**。
- 封包徽标现扫 `chara_common`/`chara_initial` 索引得出，直接对应 `-Archive` 参数。
  踩坑：匹配必须精确到 `<角色>_COS_001.TMC`，用子串会被 `KASUMI_BOSS_COS_001.TMC`
  命中，把霞误标成 `chara_common`。

### 验证

- 21 张卡片、21 张缩略图（共 0.9MB）、页面 35.5KB；霞/绫音正确标注
  `chara_initial`，其余 `chara_common`；两条告警均属实（Alpha-152 素材本身仅 5 张
  贴图、`KASUMI_DLC_011` 是未加 `-Hair` 的光头对照件）。

## 2026-08-30 — DOA5LR：修正部件对齐与 Alpha 判据（用户反馈的 4 个缺陷）

### 修复

用户反馈四处问题，逐个定位：

- **红叶/穗香「头发和头没对齐」、女天狗「没有脸」** —— 根因是我加的"对齐"本身。
  实测**绝大多数角色的脸/头发本来就和服装同处一个坐标系**（脸 Z 已接在颈口上方、
  头发顶端已到头顶），直接叠加即正确；早期版本无条件按包围盒对齐，把对的挪歪了：
  马尾的包围盒顶端是发梢而非头顶 → 头发被压到脸前面；女天狗的翅膀把身体包围盒
  撑大 → 脸被误判"不在位"而整个挪走。现在默认不动，判定改用部件**顶端**是否够到
  身体顶端（用底端会被马尾误导），只搬真正不在身体坐标系的部件（霞的头发）。
- **皮肤/衣服半透明起噪点** —— Alpha 判据不够严。仅要求">2% 全透明像素"会被两类
  冒充者骗过：穗香 `Tex_01`（62% 全透明但 alpha 最大只有 0.34）、穗香脸部贴图
  （3% 全透明、max 0.99，但均值仅 0.12 → 几乎没有实心区域）。改为**同时**要求
  **>2% 全透明 且 >4% 全不透明**（镂空遮罩必然"该实的全实、该空的全空"）。
  Honoka 的 alpha 材质数 95→65，Helena 40→21，Rachel 48→19。
- **Alpha-152 材质全白** —— 不是 bug。她三个部件加起来只有 8 张贴图
  （服装 2 张：一张 256×256 带绿调 + 一张 64×64 纯白），游戏里靠特殊半透明
  shader 表现，原始素材本身就没有颜色贴图。已在文档中说明。

### 验证

- 19 个 blend 全部用修正后的逻辑重建，红叶/女天狗/穗香的头部特写渲染确认正常
  （脸可见、头发在头后、皮肤实心），Marie/霞等原本正常的未被改坏。

## 2026-08-30 — DOA5LR：19 名女性角色批量导出 + 三部件对齐 + Alpha 语义修正

### 新增与修复

- **发现 DOA5LR 也是三部件**：`COS_NNN` 服装**不含头部**，脸是独立的
  `<角色>_FACE`（无编号），头发是 `<角色>_HAIR_NNN`。此前只导服装+头发会得到无头
  模型。`export_full.ps1` 新增 `-Face` / `-FaceTmc`。
- **三部件对齐逻辑**（`build_blend.py`）：三者坐标系互不相同。服装作基准；脸的 Z
  已在身体坐标系里但 X 有存储偏置（霞实测 +0.0037）→ 只居中 X；头发用自己的局部
  原点 → 整体搬到头部锚点顶部。锚点优先级 `*Head*` 网格 > 已就位的脸 > 身体包围盒
  顶部，故部件顺序强制为 服装 → 脸 → 头发。
- **修正 Alpha 语义**：DOA5LR 部分贴图把高光遮罩塞在 diffuse 的 alpha 里
  （实测 `Tex_27` 取值 0.00~0.91 连续、全透明/全不透明像素占比均为 0%）。无差别
  接到 Principled.Alpha 会让皮肤变成半透明抖动噪点。新增 `has_real_transparency()`
  用 numpy 采样判定（要求 >2% 全透明像素；头发实测 30~39%，身体 0%），只有真透明
  贴图才接 Alpha + HASHED，其余 OPAQUE。19 个成品已用修复后逻辑重建。

### 操作与验证

- 19 名女性角色批量（workflow 并行 19 agent，129 秒）：**19/19 成功**，
  全部 `COS_001 + FACE + HAIR_001` 三部件，4.7~21.4MB。霞/绫音在 `chara_initial`，
  其余 17 人在 `chara_common`。Alpha-152 仅 4.7MB 属正常（无服装半透明克隆体，
  ALPHA_MATERIALS=0）。
- 产物索引见 `D:\doa5lr_exports\README.md`，操作见 `scripts\doa5lr\EXPORT_GUIDE.md`。

## 2026-08-30 — DOA5LR：export_full.ps1 支持外部 mod TMC（-TmcFile / -HairTmc）

### 新增与修复

- `export_full.ps1` 新增 `-TmcFile` / `-HairTmc`：直接吃外部 `.TMC`（+同目录同名
  `.TMCL`）出带材质 .blend，用于社区 nude/服装 mod；可与官方部件混用
  （mod 身体 + 官方发型）。`-TmcFile` 也接受目录（取其中第一个 `.TMC`）。
  中转目录 `D:\doa5lr_exports\_mods\<TMC名>\`。
- 修复 PowerShell 函数把内部脚本 stdout 当作返回值的坑：`New-PartFromArchive` 里
  `export_character.ps1` 的输出会混进 `$partDirs`，导致后续路径参数报
  "A parameter cannot be found that matches parameter name 'File'"。内部调用
  统一 `| ForEach-Object { Write-Host $_ }` 消费掉。
- 确认 DOA5LR **无官方 nude**：全部 36 个封包、12,625 个条目名搜
  `nude/naked/bare/skin/under/lingerie` 零命中（此前只查过名称库）。

### 验证

- 外部 TMC（拷官方 TMC/TMCL 到独立目录模拟 mod）+ 官方 `KASUMI_HAIR_001` 混用：
  产物统计与直接从封包导出完全一致（59 材质 / 82 贴图 / 13.7MB），路径正确。

## 2026-08-30 — DOA5LR：补齐 .blend 组装链路 + 全封包可解析

### 新增与修复

- `scripts\doa5lr\build_blend.py` + `export_full.ps1`：DOA5LR 现在也能一键出带材质
  `.blend` + 预览图（此前只到 FBX+DDS）。要点：DOA5LR 的 FBX **自带**材质→贴图
  连接（Noesis 的 doa5pc 插件写入 Diffuse/Normal/Specular），因此**不需要** DOA6
  那套材质映射解析；脚本只按统一接法重建（法线 Non-Color + Normal Map、Alpha
  HASHED）。
- 修复 `extract_lnk.py` 把数据体魔数写死为 `CHCM` 的 bug——魔数其实是各封包自己的
  4 字节标签（`CHIN`/`STCM`/`P25C`…），结构一致。改为只做结构校验后，**36 个封包
  全部可解析**（此前只有 chara_common）。据此点清模型总数：TMC 1099 个，
  其中角色模型 678 个 / 34 名角色。
- `build_blend.py` 处理两个 DOA5LR 特有问题：① Noesis 以 scale 0.01 导出，角色仅
  ~1.6cm 高会整个落在相机近裁剪面内（渲染全空）→ 归一到 ~1.7 单位；② 头发是独立
  TMC 且用自己的局部原点、FBX 无骨架 → 按几何对齐到身体 `*Head*` 网格的包围盒
  （X/Y 中心 + 顶部），`export_full.ps1 -Hair` 一并处理。

### 验证

- `KASUMI_DLC_011` + `KASUMI_HAIR_001` → 13.7MB .blend（59 材质、82 贴图打包、
  头发对齐 dz=0.005），渲染正常。

## 2026-08-30 — DOA6：19 名女性角色批量导出 + nude/mod 变体管线

### 新增与修复

- `scripts\doa6\export_full.ps1`：官方角色一键出带材质 .blend（三部件提取 →
  matmap → PNG → 组装 + 渲预览）。
- `scripts\doa6\export_nude_mod.ps1` + `mod_matmap.py`：REDELBE layer2 mod
  （zip/目录）→ nude 变体 .blend，自动接官方发型/脸。双路线：mod 替换的服装编号
  本机存在时走原版 ktid 链（精确）；替换未安装 DLC 位时走启发式（按网格顶点数
  分配部位），猜错用 `-Assign "3=f01,5=body"` 纠正。
- `scripts\doa6\EXPORT_GUIDE.md`：官方与 nude 两条路线的完整操作指南（与脚本同目录）。
- `D:\doa6_exports\README.md`：产物索引（19 官方 + 4 变体）、角色花名册、目录结构。

### 操作与验证

- 19 名女性角色批量（workflow 并行 19 agent，4 分钟）：**19/19 成功**，35~60MB/个。
  自动处理特例：NIC/MAI/SNK 的 `COS_000~003` 是无 ktid 占位体，回退 `COS_004`；
  PHF 的 HAIR_001 官方无贴图（白模头发）。
- nude/mod 变体 4 个已验证渲染正确：HEL_Helena_Nude（路线 A）、
  MOM_Momiji_Malf / LIS_Lisa_Malf（路线 B 一次到位）、
  AYA_Ayane_Malf（路线 B + `-Assign` 纠正皮肤/衣物互换）。

## 2026-08-30 — DOA6：材质链解析 + 一键组装带贴图 Blend（Momiji 验证）

### 新增与修复

- `scripts\doa6\g1m_matmap.py`：解 g1m G1MG 材质段 + 部件 .ktid + kidssingletondb
  的 TexContext 对象（属性 0x6c7321d2），产出 submesh→g1t 贴图名的精确映射 JSON。
  发现并绕开 Cethleann OBJDB 解析器读不了 DOA6 `_DOK` 容器的问题
  （Nyotengu.KTID 因此只会产出空 g1t）。
- `scripts\doa6\build_blend.py`（Blender 3.6 无头）：导入 COS/HAIR/FACE 三部件
  FBX、按 matmap 挂 albedo+normal（HASHED 透明）、打包贴图、存 .blend 并渲染预览。
  规避 FBX 占位 Image 使 pack_all 失败的问题（逐图 pack）。
- `scripts\doa6\import_mod.ps1`：任意 DOA5LR/DOA6 mod（zip/目录）批量转 FBX+DDS。

### 操作与验证

- Momiji 完整角色：`MOM_COS_001`+`MOM_HAIR_001`+`MOM_FACE_001` 三部件导出、
  30 张 alb/nmh PNG、组装为 `D:\doa6_exports\MOMIJI_COS001.blend`（54.8MB，贴图内嵌）
  并渲出正确预览（脸/马尾/服装纹样/alpha 均正常）。流程见 doa6/README §3.5。

## 2026-08-30 — 新增 DOA5LR 与 DOA6 提取管线（自研解包器 + Noesis 转换）

### 新增与修复

- 新目录 `scripts\doa5lr\`：`extract_lnk.py`（.bin/.lnk 解包，Python 移植 Archive
  Tool 1.2.1 的 C# 算法：LFMO 混淆名索引 + file5lr.dat 名称库 + doaKey/动态 key XOR
  解密 + 分块 zlib 解压）与 `export_character.ps1`（按名称前缀批量 TMC/TMCL→FBX+DDS，
  经 32 位 Noesis + doa5pc_custom.py 插件）。
- 新目录 `scripts\doa6\`：`extract_rdb.py`（KTGL v2 RDB 解包：48 字节条目 +
  `offset@size#bin&sub` 地址串 + 内层 IDRK 头 + 分块 zlib/lz4）与
  `export_character.ps1`（CharacterEditor 模型 + MaterialEditor 贴图按服装一键导出，
  经 Noesis64 + ProjectG1M）。
- **修复 Cethleann.DataExporter 的截断 bug**：其 zlib 每块只读一次导致 1536 个 g1m
  中 1300 个在 ~80% 处截断，坏文件令 ProjectG1M 崩掉 Noesis（"打开就 crash"的根因）；
  自研解压后全部大小与 G1M/G1T 头部声明一致。
- 工具落地：`E:\tools\doa5lr\`（doaKey、file5lr.dat、Archive/Texture/DLC Tool、
  Blender TMC importer）、`E:\tools\doa6\`（Cethleann 1.2.1 套件 + filelist CSV、
  ProjectG1M 1.8.1/1.7.4.2）、Noesis 插件就位（32 位 `plugins\`、64 位 `plugins\x64\`）、
  便携 `E:\tools\7zr.exe`。

### 用户如何操作

- DOA5LR：`scripts\doa5lr\export_character.ps1 HONOKA`（或 `-List`）。
- DOA6：`scripts\doa6\export_character.ps1 HON_COS_002`（或 `-List`）。
- 产物分别在 `D:\doa5lr_exports\`、`D:\doa6_exports\`。

### 实现原理与兼容性

- 两游戏格式细节见 `scripts\doa5lr\README.md`、`scripts\doa6\README.md` §3。
- .ps1 带 UTF-8 BOM（PowerShell 5.1 中文脚本必需）；Python 端零第三方依赖
  （lz4 条目才需 `pip install lz4`，DOA6 实测全 zlib）。

### 已执行的验证

- DOA5LR：HONOKA_COS_001 TMC 魔数校验、FBX+30 DDS；HONOKA_HAIR_001 全链路 exit 0。
- DOA6：HON_COS_001.g1m 尺寸==头部声明；HON_COS_002 全链路 FBX 2.6MB + 154/154 DDS；
  `*HONCOS001_*` 定向抽 MaterialEditor 83 个 g1t 零失败（含 22MB 4K 图）。

## 2026-08-30 — Venus Vacation PRISM：export_character.ps1 对齐 ROE 操作方式

### 新增与修复

- `venusvacationprism\export_character.ps1` 从单行透传升级为 ROE
  `extract_character.ps1` 风格入口：位置参数直接给名字（中/英/内部代码，
  逗号分隔多名）、`-List`（角色与支持状态）、`-ListModels [-Probe]`
  （生成 models.csv/json/md 清单）、`-Format blend,fbx,glb`、`-Plan`、
  `-Resume`、`-AssetsOnly`、`-GameRoot`/`-OutputRoot` 覆盖默认。
- 旧 GNU 风格调用（`--name 穗香 --formats ...`）检测到 `--` 开头即原样
  透传给 `export_character.py`，完全向后兼容。
- `scripts/README.md` 推荐入口更新为 `export_character.ps1`；目录 README
  增加"快速上手"一节。

### 操作与验证

- 实测四种模式：`-List`（6 名角色状态正确）、`Fiona -Plan`（默认游戏目录/
  输出/工具链解析正确）、`-ListModels`（1,527 个 G1M 清单写出）、
  `--list-characters` 透传（exit 0）。

## 2026-08-30 — Stellar Blade：合并为单一主骨骼（可整体 pose）

### 新增与修复

- `validate_eve.py` 新增 `--merge-armatures`：把脸/发型/马尾/短发束骨架合并进
  身体骨架成单一 `Eve_Armature`。要点：①合并后重名骨（`.001`）去重，子骨转挂
  原骨，顶点组权重自然落到身体同名骨；②发型/马尾自己的 `Root` 位于挂点而非
  角色原点，不能与身体 `Root` 去重——改名为 `Hair_Root`/`HairTail_Root` 携带骨
  （连同网格顶点组同步改名）并挂到 `SC_Hair`（无 socket 的 UE Viewer 身体回退
  `Bip001-Head`）/`Ab-TL-HairB01`；③头部小骨挂 `Bip001-Head`；④网格父级与
  Armature modifier 全部改指主骨架。
- 首版曾把发型 Root 直接去重进身体 Root，转头测试暴露头皮不跟随；携带骨方案
  修复后转头渲染确认整个发型（发冠/刘海/侧发/马尾根）随头运动。
- `export_eve.ps1` / `export_outfit.ps1` 默认启用合并，加
  `-KeepSeparateArmatures` 恢复旧的每组件独立骨架结构。

### 操作与验证

- 三个 blend 均已重建为单骨架：标准装 329 骨、裸模 189 骨、Nikke_06 204 骨
  （各去重 17 根）；Nikke_06 上 `Bip001-Head` 旋转 25° 的姿势渲染目检通过。
- 补充（同日）：PSK/UEFormat 导入的骨显示长度固定 1cm，厘米级角色在视口里
  是一团小点。`validate_eve.py` 新增 `resize_bone_display`：有子骨的取到最近
  子骨的距离、末端骨继承父骨 60%（限 1–25cm），只沿现有 Y 轴改长度，不动
  骨头位置/朝向/roll，蒙皮与局部轴不受影响。三个 blend 重建后骨长中位数
  1.0cm → 约 4.35cm，报告新增 `bone_display` 字段记录前后值。

## 2026-08-30 — Stellar Blade：眼部预览材质优化

### 新增与修复

- 诊断出旧眼部预览发死的两个原因：`M_MikeEyeBlend_Inst` 与
  `MI_EVE_Eyeshadow_Occlusion` 两层壳的几何覆盖整个眼眶，近黑不透明/半透明
  设置把眼球整体压暗成"重烟熏+黑洞"；虹膜源贴图是为 UE 光照折射栈制作的
  暗色图，平铺进 Eevee 预览时读作全瞳孔。
- `validate_eve.py` 眼部调整：MikeEyeBlend 改为浅暖色 HASHED 半透明
  （alpha 0.10）、eyeshadow occlusion 减淡（alpha 0.55→0.12）、虹膜贴图后
  插入 HSV 提亮（Value 1.8 / Saturation 1.15，标定半径 0.055 不变）、
  EyeLight 眼神光增强（emission 0.15→0.5）。
- 排错记录：一度怀疑半径/粗糙度，经"隐藏全部壳层"的排除性渲染确认暗盘
  来自壳层而非眼球材质本身。

### 操作与验证

- 标准装、裸模、Nikke_06 三个 blend 均已重建；脸部近景目检：眼白透亮、
  虹膜有层次并带眼神光，眼周恢复为柔和红棕妆感。几何/骨骼统计不变。
- 二次微调（同日）：反馈眼仁偏小，可视虹膜半径 0.055→0.07（约放大 27%），
  HSV 提亮 1.8→2.6、饱和度 0.95 让虹膜纹理透出；A/B 渲染对比后定稿，
  三个 blend 再次重建，正面近景虹膜大小与游戏内观感一致。

## 2026-08-29 — Stellar Blade：export_outfit.ps1 任意服装一键出 Blender

### 新增与修复

- 新增 `scripts/stellarblade/export_outfit.ps1`：按包名（含 DLC）一条命令产出
  组装好的 `.blend`——PSK 缺失时自动用专用 UE Viewer 导出，随后无头运行
  `validate_eve.py` 把服装身体与共享的 Face_003/发型/马尾/短发束组装、渲染
  并出 JSON 报告；输出 `blender\Eve_<包名>.blend`。依赖 `export_eve.ps1`
  已跑过一次（共享组件、UEFormat 快照与对齐参考 JSON）。
- `validate_eve.py` 的 `--body-diffuse` 现在也接受**贴图目录**：按材质名
  自动匹配各材质槽的 `*_A` albedo（去掉 `MI_/MA_` 前缀精确匹配，退化为
  token 重合度 + 文件大小排序），多材质服装不再整体套一张贴图；报告新增
  `preview_materials.body_assignments` 记录逐材质匹配结果。

### 操作与验证

```powershell
.\scripts\stellarblade\export_outfit.ps1 CH_P_EVE_Nikke_06
```

- 实测 NIKKE Alice（DLC_2，UV1/UV2/Decal 三材质）：5 网格 / 122,988 顶点 /
  221 骨，三个材质分别匹配到 UV1_A/UV2_A/Decal_A，渲染目检粉色连体衣、
  外套、SUPER 贴片、球鞋与共享脸/发型全部正确。

## 2026-08-29 — Stellar Blade：Eve 服装清单与粉色判定文档

### 新增与修复

- 新增 [`docs/stellar-blade-eve-outfits.md`](stellar-blade-eve-outfits.md)：
  Eve 全部服装的编号→名称对照（59 个编号装 + 7 个特殊装 + NieR/NIKKE 联动
  DLC 各 4/6 套；名称取自 Modding Guide ID's Library，存在性用 `.utoc` 索引
  核对），以及基于 299 张 albedo 贴图色相统计 + 目检的粉色判定：真正粉色仅
  Pink Bear（45 TypeB）与 NIKKE Alice Cooling Suit（DLC_2 Nikke_06）两套。
- 勘误：本机安装包含 `SB/Content/DLC_1/`（NieR）与 `DLC_2/`（NIKKE）两个联动
  DLC；`list_models.py` 默认过滤 `SB/Content/Art/Character/` 不含 DLC 挂载，
  统计 DLC 需另用 `--path-filter`。

## 2026-08-29 — Stellar Blade：修正主发型 180° 朝向（刘海朝后）

### 新增与修复

- 发现主发型 `EVE_HR_01` 自首次验证以来一直反戴：独立 UE Viewer PSK 与马尾
  一样带 180° 局部轴翻转，而旧对齐只把发型 Root **平移**到 `SC_Hair` 插槽位置，
  未恢复旋转，导致刘海在后脑、颈后露出发型底面（即上一条记录里误判为
  "发型紧贴侧区"的裸露带）。
- `validate_eve.py` 主发型对齐改为 `SC_Hair` 完整静置矩阵（位置+旋转），与
  马尾/短发束的共有骨方法一致；`--alignment-reference` 回退路径自动继承修正
  后的完整矩阵。

### 操作与验证

- 标准装与裸模均已用修正后的对齐重建。渲染目检：正面平齐刘海位于额前、
  编发冠与侧发正确环绕面部；后脑马尾高扎、发量完整覆盖，无裸露带。
  组件数量与顶点/骨骼统计不变（5 网格 / 346 骨）。

## 2026-08-29 — Stellar Blade：补齐缺失的后颈短发束 EVE_HR_Tail_Short

### 新增与修复

- 确认此前组装的 Eve（标准装与裸模）后脑左侧有一块裸露区域：默认发型实际由
  4 个网格组成，除主发型和长马尾外还有挂在 `Bip001-Head` 下的后颈短发束
  `EVE_HR_Tail_Short`（7,466 顶点 / 7,210 面 / 8 骨），此前未导出。同目录的
  `EVE_HR_01_ShortTail` 则是长马尾的"短马尾"替换选项（仅 Root 锚），不叠加。
- 专用 UE Viewer 补导 `EVE_HR_Tail_Short.psk` 与 `EVE_HR_01_ShortTail.psk` 到
  `umodel_exports`；`validate_eve.py` 新增可选 `--tail-short`，按双方共有的
  `Bip001-Head` 完整静置骨矩阵对齐（误差 0），并入发型验证材质；
  `export_eve.ps1` 组件清单加入 `tail-short`（缺失时自动补导并传参）。

### 操作与验证

- 标准装与裸模均已重建：5 网格；标准装 114,589 顶点 / 141,084 面 / 346 骨。
  后脑视角渲染目检：短发束正确垂落在脑后与背部，原空缺被覆盖（余下发际
  边缘为发型本身的紧贴侧区，位于编发之下）。

## 2026-08-29 — Stellar Blade：EveOriginalProportions 裸模导出与组装

### 新增与修复

- 用重新下载并校验的专用 UE Viewer（`umodel_stellar_blade_v6.zip`，SHA256 与
  文档记录一致 `61A641D3…F550`，现存放 `E:\tools\umodel_stellarblade\`）从本机
  `_probe_stash` 中的 EveOriginalProportions Mod 导出全部 4 个变体
  （barefoot / barefoot_pubic / highheels / highheels_pubic）的
  `CH_P_EVE_InnerSuit.psk` 网格与 custombody/heels 贴图，各 12 对象，输出到
  `D:\stellarblade_exports\umodel_mod_exports\<variant>\`。Mod 是独立 IoStore
  三件套，UE Viewer 需要同目录有游戏的 `global.utoc/ucas`，脚本流程用临时
  staging 目录解决。
- `validate_eve.py` 新增 `--alignment-reference`：UE Viewer PSK 不含 socket，
  裸模骨架缺 `SC_Hair`（马尾锚 `Ab-TL-HairB01` 仍在）；该参数从既有验证报告
  JSON 复用记录的发型根变换（两副骨架静置姿态相同），马尾仍按共有骨原生对齐。
  默认行为不变。

### 操作与验证

- 组装产物：`D:\stellarblade_exports\blender\Eve_Nude_Barefoot.blend` 及
  `validation\Eve_Nude_Barefoot.png/_face.png/.json`。
- 实测：4 网格 / 113,229 顶点 / 179,668 面 / 198 骨（裸体 53,742 顶点、
  107,424 面、159 骨、材质 `SkinEve`），马尾锚点误差 ≈1.1e-6，渲染目检
  脸/发型/马尾对位正确、赤足贴地。游戏与 Mod 资产仍不入仓库。

## 2026-08-29 — Stellar Blade：list_models.py 模型清单与未导出差集

### 新增与修复

- 新增 `scripts/stellarblade/list_models.py`：纯 Python 只读解析 Paks 下所有
  `.utoc` 的 IoStore 目录索引（FIoStoreTocHeader 144 字节 + FIoDirectoryIndexResource
  目录/文件/字符串表；Stellar Blade 索引未加密，无需 AES、FModel 或 UE Viewer），
  列出全部包路径并与导出根目录里的 `.psk/.uemodel/.fbx/.glb/.gltf/.blend`
  按文件名差集，回答"还有哪些模型没导出"。
- 支持 `--path-filter`/`--glob`/`--include-exported`/`--all-files`/`--csv`；
  "模型包"为命名启发式（排除贴图/材质/动画/物理/碰撞/CameraBone/Facial 等），
  脚本输出中明确标注该局限。

### 操作与验证

```powershell
python scripts\stellarblade\list_models.py                     # 未导出模型包
python scripts\stellarblade\list_models.py --include-exported  # 全表带状态
```

- 本机 1.4.1 实测：7 个 `.utoc` 共索引 224,322 个文件（主容器 221,592，与专用
  UE Viewer 报告的 228,867 同量级，后者含 .pak 内文件）；角色树筛出 1,957 个
  模型包候选，已导出 6 个（与实际状态一致：身体、Face_001/003、Teeth_001、
  主发型、马尾，且逐个列出对应本地文件路径），未导出 1,951 个。

## 2026-08-29 — Stellar Blade：一键封装脚本 export_eve.ps1

### 新增与修复

- 新增 `scripts/stellarblade/export_eve.ps1`：把已验证的 Eve 手动流程包成一条命令，
  接口风格与 `riseoferos/extract_character.ps1`、`export_nude_models.ps1` 一致
  （`-List`/`-Check`/`-Force`/`-RefreshHair`，参数化 `-GameRoot`/`-ExportRoot`/
  `-BlenderExe`/`-UmodelExe`/`-UEFormatSource`/`-OutputName`）。
- 流程：①校验 FModel 手动导出（身体 PSK、Face_003 `.uemodel`、身体漫反射，含
  `ACTRHEAD`/`UEFORMAT` 文件头检查；FModel 无法无头运行，缺失时打印配置指引）；
  ②头发/马尾/贴图缺失时用专用 UE Viewer CLI 自动补导，校验 `Found N game files`
  识别错误构建，`~mods` 有 Mod 时告警；③自动解析/下载并补丁 UEFormat 源码；
  ④无头运行 `validate_eve.py` 并解析 `STELLARBLADE_EVE_REPORT=` 结果。
- 重要修正：UEFormat 上游 main 已重构 `importer/logic.py`，
  `ueformat-blender36.patch` 不再适用于 main。自动下载现在钉住补丁基线 commit
  `58d1abf52d6b2e5ad8d00e7c31bc98495231e642`（`importer/logic.py` blob `5020309`
  与补丁前像一致）。另外该补丁是零上下文 diff，`git apply` 必须带
  `--unidiff-zero`，脚本已内置。

### 操作与验证

```powershell
.\scripts\stellarblade\export_eve.ps1 -Check   # 只检查输入
.\scripts\stellarblade\export_eve.ps1          # 组装 + 验证（输出存在则跳过）
```

- 本机全流程实测（独立 OutputName，未覆盖既有验证输出）：自动下载钉版快照、
  `git apply --unidiff-zero` 干净应用、Blender 3.6.15 组装通过，结果与
  2026-08-02 手动验证完全一致：4 网格 / 107,123 顶点 / 133,874 面 / 338 骨、
  53 源 Morph → 54 Shape Keys、发型插槽误差 0、马尾锚点误差 ≈2.1e-6，
  渲染图目检正常。

## 2026-08-29 — Operation LOVECRAFT: Fallen Doll 提取调研与脚本骨架

### 新增与修复

- 新增 `scripts/fallendoll/`：`probe_pak.py`（只读探测 pak 版本/加密/索引，不接触
  key）、`prepare_fmodel.ps1`（验证安装、建隔离工作区、打印 FModel 配置指引）、
  `export_models.ps1`（扫描 FModel 已导出的 SkeletalMesh，批量材质化为 Blend/FBX/GLB，
  接口/manifest 与 ROE/FF7RB/ToD 一致）。下游材质直接复用已验证的 FF7 Rebirth
  worker `export_ff7rb_model_blender.py`（两者同为 UE4.26 FModel 导出）。
- 调研结论（`docs/fallen-doll-extraction.md`）：引擎 UE4.26（ChaosCloth 存在、apex
  缺失、pak v9 印证），项目名 Paralogue，Desktop/VR 各一个约 5.4 GiB 的 pak，pak
  version 9 且**索引 AES 加密**。提取被 AES key 阻塞。
- 实测排除本机取 key 途径：零 key、exe 内 64 位 hex 候选、shipping exe 全量滑窗爆破
  （高熵 4 对齐 55 万窗口 0 命中；step-1 全覆盖 11 个候选经严格 mount-point 校验全为
  误报，实为 x86 指令/字符串常量如 `ragePakList`）。**key 不以明文连续 32 字节存在于
  exe 中**；合法获取途径（社区 UE key 库、运行时取 key）记入文档，key 不入仓库。

### 操作与验证

```powershell
python scripts\fallendoll\probe_pak.py         # 探测（不需要 key）
.\scripts\fallendoll\prepare_fmodel.ps1        # 工作区 + FModel 指引
.\scripts\fallendoll\export_models.ps1 -List   # 拿到 key、FModel 导出后使用
```

- `probe_pak.py` 对 Desktop/VR 两个 pak 均正确报告 pak v9 + 索引加密。
- `prepare_fmodel.ps1` 端到端跑通（探测 + 建工作区 + 打印三项 FModel 配置）。
- `export_models.ps1` 两个 ps1 语法解析通过；`-List` 空树与非空（伪造 FModel 布局）
  均正确；委派链用伪造模型端到端跑到真实 Blender worker，如实在「缺 Base Color 贴图」
  处 FAIL 并写 validate 快照 manifest——证明扫描/委派/错误传播/manifest 全部工作，真实
  带贴图导出时即 PASS。
- 待办：AES key 到位后进行真实导出与裸模结构判定。

---

## 2026-08-29 — Throne of Desire 裸模批量导出统一入口

### 新增与修复

- 新增 `scripts/throneofdesire/export_nude_models.ps1`：与 ROE 同名脚本约定一致的
  PowerShell 入口（`-List` / `-Only` / `-Format` / `-ValidateOnly` / `-Force`，本机
  默认路径零参数即跑），包装既有 `batch_export_female.py`。模型清单从 Python 模块的
  `FEMALE_MODEL_IDS` 动态读取，保持单一事实源。ToD 女性 h 系模型本体即裸模（衣服为
  默认隐藏的附件网格，FBX 只含基础身体+骨架），无需 mod。
- `-ValidateOnly` 调用既有 `validate_female_exports36.py` 在 Blender 中重开已导出的
  Blend/FBX 复检，报告写独立 `female_export_validation.json`，不触碰导出 manifest。
- 修复 `batch_export_female.py` 的 manifest 覆盖问题（与 ROE `-Only` 同型）：
  `--models` 子集运行改为合并更新 `female_export_manifest.json`，按 13 套规范顺序保
  留未重导出的记录；损坏的旧 manifest 安全忽略。真实导出前预检两个贴图解码器并给出
  `build_codecs.py` 构建提示。

### 操作与验证

```powershell
cd E:\code\othercode\ripper_tpose\scripts\throneofdesire
.\export_nude_models.ps1 -List
.\export_nude_models.ps1 -Only h005,h020 -Force
.\export_nude_models.ps1 -ValidateOnly
```

- 真机 `-List` 正确显示 13 套全部 COMPLETE；`-Only h005` 断点续跑秒级 skip，且
  manifest 保持 13 条完整记录（修复前会被覆盖成 1 条），`requested_models` 如实记录
  本次子集。
- `-ValidateOnly -Only h005,h020` 重开验证 2/2 ok 并写入独立报告。
- 缺解码器时预检报错并给出构建指引；`build_codecs.py` 经 WSL g++ 重建两个解码器后
  恢复正常。纯 Python 单测
  `tests/test_batch_export_female_manifest.py` 5/5 通过（合并、幂等、规范排序、损坏
  manifest 容错）。
- 沿用限制不变：产物为静态网格 + 未蒙皮静止骨架（蒙皮/动画尚未恢复），XPS 不支持。

---

## 2026-08-29 — FF7 Rebirth 已导出变体批量材质化

### 新增与修复

- 新增 `scripts/final/export_ff7rb_models.ps1` 与 Blender worker
  `export_ff7rb_model_blender.py`：扫描 FModel 已保存的 Player 变体
  （`PC????_*`），无头导入 ActorX、修 PSK 三角反光、按 FModel 材质 JSON 匹配贴图
  （复用 `ff7rebirth_tools.py` 的模块函数），输出内嵌贴图 `.blend`，可选 FBX/GLB。
  默认输出 `D:\ff7rebirth_exports\materialized`。
- 上游保持手动：FModel 无 CLI，未保存的变体不做自动补提取；无 `Model` 目录的材质
  包（湿身/眼泪、`PC7002_00` 转换失败件）记为 `NO_MODEL` 并跳过，不算失败。
- `.blend` 保留完整节点；FBX/GLB 前做便携简化：分层眼球按 ColorRamp 参数烘成单张
  PNG（smoothstep 近似 EASE），DirectX 法线预翻转 G 通道生成 `*_gl.png` 直连
  Normal Map，`simplified` 字段记录改动。XPS/PMX 未在 FF7RB 骨架上验证，暂不提供。
- 修复跨目录贴图引用：材质 JSON 的引用是精确 Unreal 包路径，常指向本变体之外
  （PC0002_11 换衣模型复用 PC0002_00 的皮肤/头发/服装 atlas；眼白/口腔在
  `Character\Common`）。旧版只扫本变体目录，PC0002_11 的十个材质全部被按名兜底连到
  唯一本地贴图 `Skin_O` 遮罩，整模呈灰白色。现在语义解析在整个已导出 `Character` 树
  上按包路径精确匹配（`texture_reference_score` 按 `End/Content/<相对路径>` 后缀计
  分），按名兜底仍限本变体 + Common；manifest 增记 `indexedTextures`。
- manifest 机制对齐 ROE：`-ValidateOnly` 写独立快照、`-Only` 按扫描顺序合并、失败
  记录 ASCII 转义的 traceback；worker 结果行同样规避 PowerShell 5.1 OEM 解码问题。

### 操作与验证

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
.\export_ff7rb_models.ps1 -List
.\export_ff7rb_models.ps1                 # 全部有模型变体 -> .blend
.\export_ff7rb_models.ps1 -Only PC0002_00 -Format blend,fbx,glb -Force
```

- 真机全量：9/9 个已保存变体 PASS（8 个 Tifa `.pskx` + Toad Tifa `.psk`），5 个
  `NO_MODEL` 正确跳过；产物 13–141 MB `.blend` 落盘并生成 manifest。
- PC0002_00 三格式导出 PASS：536 骨、188,921 顶点、226,086 面、12 材质，11 张法线
  预翻转，`Common_Mouth_Light` 无 Base Color 如实记入 `missing_base`。
- `-ValidateOnly -Only PC0099_03` 覆盖 `.psk` 旧格式分支并写入
  `ff7rb_models_manifest.validate.json`，不触碰正式 manifest。
- 纯 Python 单测 `tests/test_export_ff7rb_worker.py` 7/7 通过（眼球烘焙数学、最近邻
  重采样、格式白名单与 marker 契约），mock bpy，无需 Blender。
- 跨目录引用修复后全量 `-Force` 重导 9/9 PASS：PC0002_11 的 10/11 材质按 JSON 引用
  连上 `PC0002_00_*_C` 共享 atlas（EEVEE 渲染确认服装/皮肤/头发正确），九个变体的眼
  睛全部转为 sclera+iris 分层混合（此前仅 PC0002_00），`missingBase` 仅剩 PC0002_05
  的发光材质（本就无 Base Color）。语义索引覆盖 179 张已导出贴图。

---

## 2026-08-09 — Rise of Eros 基础裸模带材质批量导出

### 新增与修复

- 新增 `scripts/riseoferos/export_nude_models.ps1` 与 Blender worker
  `export_nude_model_blender.py`，批量处理 `a00`、A–M 十三套 `01` 基础体和 E/F/G
  三套 `fm` 变体，默认集中输出到 `D:\roe_exports\nude_materials`。
- 每个 `.blend` 打包实际引用的图片，并生成 `nude_models_manifest.json`；支持
  `-ValidateOnly`、`-Only`、`-Force`、自定义源目录和输出目录。
- `extract_character.ps1 -List` 新增 17 个 `nude:<id>` 独立条目，并可直接执行例如
  `nude:b01 -Format blend,fbx,xps,pmx,glb`。`export_nude_models.ps1 -List` 提供相同清单；
  原有普通角色 ID 与默认 FBX 提取行为不变。
- 材质化裸模新增 Blend/FBX/XPS/PMX/GLB 多格式输出。非 Blender 格式先把程序化眼球
  烘焙成便携虹膜贴图；FBX/GLB 内嵌纹理，XPS/PMX 输出配套 PNG。六槽 nude XPS 会按
  `body / face / eye / lash / brow` 拆成正确 render group，透明 overlay 不导出。
- `-Only` 现在合并更新已有 manifest，并按 17 套规范顺序保留未重导出的记录，不再因
  单独补导一个格式而把完整清单覆盖成一条；manifest 同时记录每种格式的实际路径。
  `-ValidateOnly` 的结果改写入独立快照 `nude_models_manifest.validate.json`：验证运行
  没有输出路径，合并进正式 manifest 会把已记录的导出路径清成空记录。
- `extract_character.ps1 nude:<id>` 在缺少该角色常规提取产物（FBX 或 Albedo 贴图）时，
  先自动执行一次带 `-ExportTextures` 的常规提取再进入裸模流程；普通角色 ID 与
  `blend` 格式混用的错误改为执行前报告；`-Force` 仅作用于 nude 导出（帮助里注明）。
- 加固批量导出链路：裸模六槽在对象上打 `roe_nude_slots` 自定义属性标记，XPS 导出改
  按标记识别（材质名嗅探不稳定——便携眼球烘焙会把 eye 槽换成 `eye_portable`，仅存
  旧 .blend 兜底）；PMX 因 mmd_tools 原地改建骨架而固定最后导出；便携眼球烘焙状态
  记入 manifest（a00 无组合裸模网格时记录 `skipped` 及原因，槽丢失则直接判失败）；
  worker 失败时把 Python traceback 一并写入 manifest；XPS 导出算子已注册时不再要求
  特定插件模块名。
- 修复直接复用 HD 材质流程时的裸模错误：`*_nk_body` 同时含躯干和头部，旧逻辑会把
  所有默认区域都指向 face Albedo。worker 保留既有眼球/睫毛/眉毛分类，再按连通块与
  面部骨权重建立 `body / face / eye / lash / brow / overlay` 六槽。
- 修复 B01 眼球材质槽存在但没有实际面的错误。B01 眼球约按 80% `Eyeball`、20% `Head`
  混合权重，旧版 90% 门槛会把左右眼共 864 面留在 face；现在只有同时符合多数眼球权重、
  250–800 面紧凑拓扑及完整 0–1 虹膜 UV 的连通块才按眼球处理。裸模 worker 也新增
  `eye > 0` 硬校验，避免空眼球槽再次被当作成功。
- Blender worker 的结果行改为 ASCII 转义 JSON，避免 Windows PowerShell 5.1 用 OEM 代码页
  错误解码中文诊断并吞掉字符串结尾，从而生成无法被标准 JSON 解析器读取的 manifest。
- 贴图临时目录只归集同字母体型资源；缺失公共头部贴图时直接读取游戏的
  `chara_tex_bare_pc_<字母>_common*`，并拒绝把其他体型的脸当兜底。

### 操作与验证

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
.\export_nude_models.ps1                 # 实际导出
.\export_nude_models.ps1 -ValidateOnly   # 只检查
.\extract_character.ps1 -List
.\extract_character.ps1 nude:b01 -Format blend,fbx,xps,pmx,glb -Force
```

- Blender 3.6 无头验证 17/17 通过：标准裸模各为 2 网格、1 骨架和 7 个材质槽；I/J
  体型眉线已烘进 face，使用 4 张 diffuse，其余使用 5 张；`a00` 是独立的两网格/两材质
  通用体。
- A01 六槽面数为 `36142 / 15042 / 864 / 804 / 228 / 294`；身体和脸分别命中
  `pc_a01_nk_body` 与 `pc_a_nk_face`，没有再把躯干错误映射到脸图。
- B01 修复后六槽面数为 `35414 / 15078 / 864 / 884 / 228 / 0`，眼球使用同体型的
  `pc_b_nk_eye_iris_rgbx_Albedo.png`；合成回归同时覆盖插件与独立脚本的 80/20 权重眼球。
- B01 五格式真实导出并重导入通过：FBX/GLB 均为 2 网格、1 骨架、61,624 面；XPS 为
  body `35414`、face `15078`、eye `864`、lash `884`、brow `228`、hair `9156` 六个分件；
  PMX 合并为 1 网格、1 骨架、6 材质、61,624 面，五张配套纹理均可重新加载。
- 实际保存并重开 A01 `.blend`，确认图片均为 packed；EEVEE 正面渲染确认身体、脸、
  眼睛和头发贴图连续。材质仍是 Blender PBR/程序化近似，不声称复刻 Unity Toon/NPR、
  MGAC 与 Normal 的完整游戏内效果。
- 2026-08-29 加固后复验：`-ValidateOnly` 全 17 套重新 PASS 并写入独立
  `nude_models_manifest.validate.json`，对已有正式 manifest 的目录重复验证后其内容逐
  字节不变；B01 五格式重新导出 PASS，manifest 含 `portableEye`（status/path）与
  `nudeSplit.eye_slot`，XPS 内部分件为 `5_body / 5_face / 5_eye / 7_lash / 7_brow`；
  保存的 `.blend` 重开后 `roe_nude_slots=1` 与 6 槽仍在；空 `-OutputRoot` 下
  `extract_character.ps1 nude:b01` 自动先完成常规提取（34 个角色 FBX、165 张贴图）再
  产出 blend；两个 PowerShell 脚本通过语法解析，对现有 17 套素材的缺源检测全部命中
  「无需补提取」；4 个合成 fixture Blender 回归（head 语义、贴图别名、body 变体、XPS
  alpha 槽）与 FBX bind 兼容测试共 5 项 PASS（3 个需真实 HD 素材参数的矩阵测试未随
  本次运行）。

## 2026-08-09 — Venus Vacation PRISM 角色名称对应表

### 新增

- 新增 `scripts/venusvacationprism/map_characters.py`，输出 JSON、CSV、Markdown 三种
  “角色—模型”对应表；支持用中文名、英文名或内部代码筛选角色。
- 在 `prism_rdb.py` 实现 KTGL RDB 名称哈希，并确认六名角色的内部代码为
  `MIS/FON/ELS/TAM/NNM/HON`。只有 G1M 与至少两个 MTL/GRP/OID 同名伴随资源均实际存在时，
  才接受该名称，避免把单个 32 位哈希碰撞误报为角色模型。
- `export_model.py` 新增 `--name`，可直接使用对应表中的 `FACE_FON_000` 等内部基名导出，
  原有 `--index` 和 `--id` 行为不变。

### 结果与验证

- 本机 Steam 安装确认 35 个具备完整哈希证据链的角色 G1M：海咲 8、菲欧娜 6、
  伊莉丝 6、环 5、七海 5、穗香 5。它们包含脸部、头发，以及海咲/七海的
  `COS_*_001` 服装/身体分件；未命名的共用基础身体不作无证据归属。
- 纠正仅凭轮廓作出的候选推测：索引 837 / `0xbcea6c57` 是海咲
  `COS_MIS_001`，索引 839 / `0x16a61601` 是七海 `COS_NNM_001`。
- 实际按 `--name FACE_FON_000` 成功导出索引 860 / `0xa359e61c`，并通过 9 项单元测试；
  名称哈希测试同时覆盖公开的 `HON_HAIR_033.GRP` 向量和 PRISM 的 `COS_MIS_001.G1M`。

## 2026-08-08 — Venus Vacation PRISM 原始 RDB/FDATA 解包

### 新增

- 新增 `scripts/venusvacationprism/prism_rdb.py`，只读扫描 KTGL FDATA，并解码该游戏
  `0x00400000` 标志对应的 16 KiB 分块 Zlib 数据；块边界、Zlib 流和最终尺寸均严格校验。
- 新增 `list_models.py`，输出 JSON、CSV、Markdown 三种清单；`--probe` 会补充 G1M
  版本、区块、骨骼数以及角色候选分类。
- 新增 `export_model.py`，可按清单一基索引或十六进制 KTID 导出原生 G1M 和来源
  manifest；可选调用 `eArmada8/gust_stuff` 输出 glTF/BIN。第三方转换失败不会删除已还原 G1M。

### 使用与验证

- Steam 安装实扫 1,527 个 G1M/1,527 个唯一 ID，分布在 69 个 FDATA 包；全部深度探测
  成功，零解包错误。压缩内容共 1,247,942,069 字节，解压后共 2,242,373,324 字节。
- 按骨骼数筛出 71 个角色组件候选；该数字包含身体、脸、服装和共用件，不代表角色人数。
- 实际导出索引 836、KTID `0x7ce546e8`：G1M 5,252,712 字节、924 个骨骼节点、
  17 个网格。glTF 转换及 Blender 3.6.15 后台导入/渲染通过，几何为完整女性基础身体。
- 新增 6 项单元测试，覆盖多块解压、尾部/尺寸损坏、G1M 元数据和 FDATA 实际读取。

## 2026-08-02 — ROE XPS Tools v1.1.12 / i03、i04 脸部贴图兼容

### 修复与兼容性

- 修复 i03/i04 点击材质准备或“修复脸部”后仍没有脸部贴图的问题。i 体型资源没有
  `pc_i_nk_eye_iris_rgbx_Albedo.png` 和 `pc_i_nk_eyebrow_rgbx_Albedo.png`；旧逻辑把三张
  head 贴图全部视为必需项，因此在真正设置 face 材质之前取消整个操作。
- i 体型现在只在独立虹膜图缺失时回退到实际存在的
  `pc_i_ld_eyes_rgbx_Albedo.png`。该回退排在标准 `eye_iris` 之后，f/g 等已有高清虹膜
  资源的旧角色不会改变。
- face 与 hair 增加角色专属前缀优先级：i04 使用 `pc_i04_hd_face/hair`，i03 因没有
  角色专属 face/hair 而继续使用 `pc_i_nk_face/hair`。共享图仍是精确角色图未命中后的
  兼容回退。
- i03/i04 的眉毛与眼线已经烘进 face Albedo，而独立 `pc_i_nk_eyebrow` 几何没有对应
  Albedo。仅 i 体型允许该贴图缺失，相关 stroke 材质保持透明；XPS 导出同时跳过任何
  纯透明 head 槽，不再生成 `lash_diffuse.png` 占位片。其他体型缺 eyebrow 时仍报错。

### 使用与验证

1. 覆盖安装插件并彻底重启 Blender 3.6，确认版本为 `1.1.12`。
2. 已打开的 i03/i04 场景无需重新导入；确认对应 HD FBX 和 `_textures` 后点击
   **“修复脸部”**。首次导入仍可使用完整的“检查并准备材质”。
3. Blender 3.6.15 实测 i03 face `11616` 面，使用
   `pc_i_nk_face_rgbx_Albedo.png`；i04 face `12172` 面，使用角色专属
   `pc_i04_hd_face_rgbx_Albedo.png`；两者 eye 均为 `864` 面并烘焙为
   `roe_eye_baked.png`。
4. 两个角色均通过“单独修脸不改身体”、旧的一键流程、XPS 导出和全新场景重导入。
   新增 `test_i_family_materials_blender.py`；F10、G09、e06、b02、g07、g02 既有回归
   同时通过。

## 2026-08-02 — ROE XPS Tools v1.1.11 / F10 脸部材质与分区修复按钮

### 修复与新增

- 修复 F10 的脸部材质消失。F10 的 head 在同一连通块内跨越 `pc_f_nk_face` 与
  `pc_f_nk_tears` 原始材质边界；旧版按连通块判断时把 11,596 个脸部面误归为透明
  `eye_overlay`。现在只要 FBX 同时提供明确的 face 与眼部附属槽，就优先按每个面的
  原始材质索引保留 face/tears 语义，再对没有明确语义的面使用既有骨骼、UV 和几何兜底。
- 在“检查并准备材质”下新增 **修复脸部 / 修复身体 / 修复翅膀** 三个按钮：脸部只重建
  head 五槽；身体只处理非 head、非 wing 的身体/衣装/头发槽；翅膀只处理原始槽名或
  对象名含独立 `wing/wings[数字]` 词元的槽。F10 没有翅膀时按钮提示未识别并零修改。
- 原有 **“2. 检查并准备材质”** 完整保留，默认仍一次处理全部材质；“修复眼睛”也保留，
  用于只重建眼球的更窄场景。分区按钮共用相同贴图匹配和原始槽缓存，不另造角色特例。
- 新增 [ROE Blender 材质兼容避坑手册](roe-material-pitfalls.md)，集中记录 F10、G09、
  e06、b02、g07、g02、插件重启、重复 FBX、输出目录清理、原始槽缓存和 XPS 重导验证
  等已确认问题，并固定以后修改材质逻辑时必须执行的最低回归矩阵。

### 兼容性与验证

- Blender 3.6.15 实测 F10：face/eye/lash/brow/overlay 从错误的
  `4148/864/900/228/11596` 恢复为 `15354/864/900/228/390`；face 使用
  `pc_f_nk_face_rgbx_Albedo.png`。单独修脸时身体材质和面索引不变，单独修身体时头部
  不变，单独修翅膀为零修改。
- F10 通过旧的一键流程导出并重新导入 XPS：`5_face` 为 15,354 面并加载正确脸贴图，
  `5_eye` 为 864 面并加载 `roe_eye_baked.png`。
- G09 实机回归通过：脸部分槽仍为 `13626/864/660/228/548`，身体按钮不改两组翅膀，
  翅膀按钮不改 body/skin，最终 XPS render group 仍为 `5/5/7/7`。
- e06 缺失绑定集成测试、g07 多图集、g02 Albedo/Abedo、b02 眼部语义和全部现有 Blender
  回归测试通过；v1.1.10 的临时 FBX bind 修复未改动。

### 使用

1. 覆盖安装插件并彻底重启 Blender 3.6，确认版本为 `1.1.11`。
2. F10 已导入场景只需确认原 FBX 与 `f10\_textures` 路径，点击 **“修复脸部”**；无需
   重新修身体。新导入角色仍可继续使用原来的“一键准备材质”。
3. 以后只有单一区域异常时优先点对应按钮；不确定或首次导入时仍点完整准备按钮。

## 2026-08-02 — ROE XPS Tools v1.1.10 / e06 FBX 缺失绑定兼容

### 修复与兼容性

- 修复 e06 HD FBX 在 Blender 3.6 导入时因 `wp_e_06` 缺少骨架绑定矩阵而触发
  `KeyError: Root` 的问题。旧流程会在异常后留下 4 个无材质网格和 1 个未完成骨架；
  这些对象只是导入半成品，不能继续准备材质或导出。
- 插件仅在 Blender FBX 导入器已把网格归入骨架、但该网格没有 `armature_setup` 时，
  使用网格世界矩阵和骨架 bind matrix 补齐缺项。已有绑定绝不覆盖；补丁只在本次
  `bpy.ops.import_scene.fbx` 调用期间生效，完成或异常后都会恢复 Blender 原方法。
- 主“1. 导入 FBX”和旧场景从源 FBX 恢复材质分区两条路径共用同一兼容入口；不依赖
  修改 Blender 安装目录。若新版 Blender 不暴露 3.6 的内部辅助类，插件会退回其原生
  FBX 操作，不施加版本相关补丁。

### 使用与验证

1. 覆盖安装插件并彻底重启 Blender 3.6，确认版本为 `1.1.10`；删除异常导入留下的
   e06 半成品。
2. e06 选择带 `(1)` 的完整文件
   `pc_e06_hd (1)\FBX_GameObjects\pc_e06_hd\pc_e06_hd.fbx`，贴图目录选择
   `e06\_textures`，再按正常三步流程操作。无 `(1)` 的同名副本本身缺少材质分区。
3. Blender 3.6.15 实机验证得到 169 根骨骼；body 2 个原始槽、head 4 个原始槽、
   hair/weapon 各 1 槽，武器保留 `ball_scale` 权重和 Armature 修改器；材质准备后 head
   正常重建为 5 槽。
4. 新增 `test_fbx_missing_bind_compat_blender.py`，覆盖缺项补齐、正常绑定不覆盖、重复
   调用幂等、临时补丁恢复和 e06 完整导入/材质准备。既有 G07、B02、G02、G09 四组
   Blender 回归测试同时通过。

## 2026-08-02 — ROE XPS Tools v1.1.9 / g09 Blender 3.6 翅膀视口修复

### 修复与兼容性

- 根据 Blender 3.6 实际截图补充修复：g09 的两组翅膀材质在准备阶段改用 Alpha Clip，
  避免 Alpha Hashed 在重叠羽毛片上显示黑色散点和卡片状噪声；XPS 导出仍使用 RG7。
- 复用严格的 g09 槽识别函数，同时限定 `pc_g09_hd/ld_body` 对象名与
  `pc_g09_hd/ld_wing(s)[数字]` 原始槽名。非 g09 角色、普通 body/skin、头发和手工
  覆盖的历史分支不改变。
- 回归测试额外固定 Blender 材质模式：g09 `body/skin=HASHED`、
  `wings/wings2=CLIP`，并继续验证非 g09 wing 不进入特例；测试还会模拟旧场景中主翼
  错挂 `wings2 + HASHED`，确认再次准备材质能够原地修复。

### 使用

1. 覆盖安装插件并彻底重启 Blender 3.6，确认版本为 `1.1.9`。
2. 对已经打开的旧 g09 场景重新执行“2. 检查并准备材质”；旧材质数据不会仅靠导入
   插件文件自动刷新。之后再执行“3. 导出 XPS(.mesh)”。

## 2026-08-02 — ROE XPS Tools v1.1.8 / g09 翅膀透明材质

### 修复

- 修复 g09 的 `pc_g09_hd_wings` 与 `pc_g09_hd_wings2` 在 XPS 导出后出现黑底、
  硬边或实心羽毛片的问题。两槽与 body/skin 共用 `pc_g09_hd_body` 网格，旧逻辑把
  所有 ROE body 槽统一导为不透明 RG5，因而丢失翅膀 Albedo 的 alpha。
- 修复贴图前缀歧义：`pc_g09_hd_wings*Albedo*.png` 会同时命中 `wings` 与
  `wings2`，且旧排序优先选择 `wings2`。现在先按完整的 `_rgbx_Albedo` 文件干精确
  查找，主翼和独立羽毛片分别使用自己的图集。
- 新增按原始材质槽名选择 XPS render group：普通 body/skin 保持 RG5；仅 g09 HD/LD
  的 `wing`、`wings`、`wings2` 等槽在材质确实使用 alpha 时导为 RG7；头发仍为 RG7。
  角色 ID 与 body 对象名采用双重限定，其他旧角色即使有同名 wing 槽也维持原来的 RG5。
- 新增 Blender 回归测试 `test_xps_alpha_slots_blender.py`，固定 g09 的四槽期望为
  `body=5`、`skin=5`、`wings2=7`、`wings=7`，并验证非 g09 的 alpha wing 槽仍为
  RG5、没有 alpha 的 g09 wing 也不改变。

### 使用

1. 覆盖安装 `scripts/riseoferos/roe_xps_addon.py` 并重启 Blender，版本应为 `1.1.8`。
2. 现有 g09 场景无需重新导入；重新执行“2. 检查并准备材质”，再执行
   “3. 导出 XPS(.mesh)”。

## 2026-08-02 — Throne of Desire X-Legend NFS/Gamebryo 调研与样本验证

### 新增与修正

- 确认 Steam App `4496710` 不使用 Unreal/Unity，而是 HyenaPC 包装层、X-Legend NFS
  封包和 Gamebryo NIF/KFM 模型动画格式。
- 新增 [`scripts/throneofdesire`](../scripts/throneofdesire/) 独立流程和
  [提取调研文档](throne-of-desire-extraction.md)，不复用 FFVII/Stellar Blade 的
  FModel、mapping 或 Unreal profile。
- `extract_nfs.py` 支持 `0x20190503` packageindex、低 32 位 XOR 偏移/大小、
  `FileListPC.txt` 映射、zlib 解压、格式扫描、按哈希提取和按编号模型组提取。

### 用户如何操作

1. 用 `scan` 建立完整 JSON 清单；
2. 用 `extract-model --model h001` 一次提取匹配 KFM 和紧随其后的基础 NIF；
3. 先在 X-Legend/Aura Kingdom 专用 NIF 查看器中验证，再尝试 Noesis 转 FBX/DAE 后
   导入 Blender 3.6；解析失败时才退回 Ninja Ripper。

### 原理与兼容性

- 当前模型/KFM 均为带 16 字节容器头的 zlib 流；部分非模型资源为自定义 LZMA 或未知
  纹理编码，脚本会分类但不会错误地套用标准 LZMA 解码。
- NIF 版本为 `20.3.3.2`。通用 NifTools/Noesis 对 X-Legend 自定义块的兼容性尚未在
  当前机器验证，因此本次不声明已生成 Blender 文件。

### 验证

- 全量扫描 32,780 条当前索引：5,957 个 NIF、323 个 KFM、295 个 XML；其中
  15,377 条为 zlib、1,877 条为 X-Legend LZMA、15,526 条压缩/编码尚未识别。
- 成功提取 `m001` 基础样本和 `h001` 角色候选组；`h001.nif` 906,860 字节、
  `h001.kfm` 62,650 字节，输出大小与 FileList 清单一致，SHA-256 已写入 manifest。
- Python 语法检查、完整索引扫描和两个 `extract-model` 回归命令均通过；游戏目录保持
  只读，未改动原始 NFS 或索引。

## 2026-08-01 — Stellar Blade PC 导出分析与 Eve Blender 3.6 验证

### 新增与修正

- 新增独立的 [`scripts/stellarblade`](../scripts/stellarblade/) 流程和
  [Stellar Blade 导出文档](stellar-blade-extraction.md)，不复用 FFVII 的 profile、
  mapping 或包路径。
- 确认 Steam build `19963153` 为 UE4 IoStore、无 AES，FModel 精确 profile 为
  `GAME_StellarBlade`；社区 `StellarBlade_1.1.0.usmap` 已能解析并导出当前身体和脸。
- FModel 成功导出 Eve 标准身体 PSK 和完整 Face_003 UEFormat；其 4.4.4 版本在头发/牙齿 Extract 发生
  `NullReferenceException`，改用社区指南链接的 Stellar Blade 专用 UE Viewer v6
  补导默认主发型与长马尾。
- 新增 `import_uemodel36.py`、UEFormat Blender 3.6 兼容补丁和 `validate_eve.py`：检查
  ActorX/UEFormat 文件头，用 `SC_Hair` 和 `Ab-TL-HairB01` 静置骨矩阵组合模块，保留
  Face_003 全部 53 个 Morph，再生成 Blender 3.6 `.blend`、全身/脸部 PNG 和 JSON。
- 新增 [Eve 验证资产路径清单](stellar-blade-eve-assets.txt)。游戏资产、mapping 和
  第三方程序仍只保存在本机，不提交仓库。

### 用户如何操作

1. 按文档配置 FModel 的 `GAME_StellarBlade` 和 local mapping，临时禁用 `~mods`。
2. FModel 导出身体 PSK 和 Face_003 UEFormat；单个组件复现异常时，使用专用 UE Viewer v6 补导。
3. Blender 3.6 安装 `io_scene_psk_psa 5.0.6`，并给官方 UEFormat 源码应用本仓库兼容补丁，按
   [`scripts/stellarblade/README.md`](../scripts/stellarblade/README.md) 运行验证命令。
4. 输出位于 `D:\stellarblade_exports`；完成导出后恢复 Mod，保持游戏包原始名称。

### 原理与兼容性

- Eve 是模块化角色。主发型以局部原点导出，按身体 `SC_Hair` 插槽移动；长马尾以双方
  共有的 `Ab-TL-HairB01` 完整静置骨矩阵对齐，不能把所有 PSK 直接堆在世界原点。
- PSK 导入器将 Mesh parent 到 Armature；脚本只变换对象层级根，避免父子都移动造成
  双倍位移。组件骨架、权重和对象层级保持不变。
- 手动重导 PSK 时应选 **Don't Export Bone Sockets**。完整角色生产仍优先统一使用
  FModel `.uemodel`，避免不同提取器之间潜在的颈缝。

### 验证

- 专用 UE Viewer 扫描到 `228,867` 个游戏文件，并实际输出两个头发 PSK；三个验证
  PSK 都非空且以 `ACTRHEAD` 开始，Face_003 以 `UEFORMAT` 开始。
- Blender `3.6.15` 实际生成 4 个网格、4 套原始 Armature、107,123 顶点、133,874 个面；
  Face_003 为 24,350 顶点、35,992 个面、11 个材质槽，并保留 54 个 Shape Keys（含 Basis）；
  主发型插槽误差为 `0`，马尾骨锚点误差约 `0.000002`。
- 输出 `Eve_Standard_validation.blend`、全身/脸部 PNG 和 JSON 均已生成并视觉检查；游戏
  `.pak/.utoc/.ucas` 名称未改动。已安装 Eve Mod 当前仍在隔离目录，启动游戏前恢复。

## 2026-08-01 — FF7 Remake / Rebirth Player 主模型清单复核

### 新增与修正

- 新增 Remake 与 Rebirth 两份一行一个 Unreal 包路径的 Player 主模型清单。
- Remake 原版 pak 的主模型包总数保持为 `36`；安装到 `~mods`、覆盖已有包路径的
  Mod 不重复计数。
- Rebirth 的统计口径由 `109` 个一级资源目录细分为 `85` 个主模型包和 `24` 个
  纯材质、贴图等资源变体，避免把效果目录误算成模型。

### 用户如何操作

- 按 [Remake 主模型文件列表](ff7remake-player-model-files.txt) 或
  [Rebirth 主模型文件列表](ff7rebirth-player-model-files.txt) 中的完整路径，在
  UModel/FModel 中定位对应的 `SkeletalMesh` 主资产并导出。

### 原理与兼容性

- 主模型采用 `Player/<变体>/Model/PC????_??.uasset` 路径约定识别；Skeleton、
  PhysicsAsset、BNM、Condition、材质和贴图不计入主模型数。
- Rebirth 使用本机安装目录下全部 `51` 个 `.utoc` 的目录索引只读枚举，不修改、
  解包或回写游戏文件。

### 验证

- Remake 清单 `36` 行、`36` 个唯一值，与现有详细清单逐项一致。
- Rebirth 清单 `85` 行、`85` 个唯一值，与全部 IoStore 目录索引逐项比较差异为 `0`。
- 两份清单均通过完整路径格式检查，`git diff --check` 无错误。

## 2026-07-26 — ROE XPS Tools v1.1.7 / g07 身体贴图与手动材质修复

### 新增与修复

- 修复 g07 身体三个材质槽找不到颜色贴图的问题。原始槽名为
  `pc_g07_hd_skin`、`pc_g07_hd_body1`、`pc_g07_hd_body2`，实际 PNG 却命名为
  `pc_g07_body1_rgbx_Albedo.png` 和 `pc_g07_body2_rgbx_Albedo.png`，省略了
  `_hd_`；旧版只按完整前缀查找，因此三个身体槽都生成了无图片材质。
- 插件和独立材质脚本新增 `_hd_/_ld_` 省略命名兼容。仍先尝试原始槽名精确匹配，
  只有未命中时才去掉一次 LOD 标记重试。
- “当前槽用途”新增 **透明罩/隐藏**。人工指定后生成纯 `Transparent BSDF`，
  ROE XPS 导出也会跳过该槽，便于手工处理 tear、泪膜或眼镜状透明卡片。
- 新增 [ROE 材质手动修复指南](roe-manual-material-repair.md)，统一记录身体槽贴图
  覆盖、透明罩隐藏、头部逐面分类、撤销与保存方法。

### 用户如何操作

1. 安装或覆盖 `scripts\riseoferos\roe_xps_addon.py`，重启 Blender，版本应为
   `1.1.7`。本次当前 Blender 已热加载新版本。
2. g07 已打开的场景无需重新导入；保持模型来源与
   `D:\roe_exports\g07\_textures\`，点击一次“检查并准备材质”。
3. 自动结果仍有局部偏差时，按
   [手动修复指南](roe-manual-material-repair.md) 使用高级材质调整：
   当前槽保存用途/贴图覆盖，或在 Edit Mode 标记头部所选面。
4. 检查无误后保存 `.blend`。

### 原理与兼容性

- g07 正确映射为：`skin → body1`、`body1 → body1`、`body2 → body2`。修复只扩展
  文件名解析，不修改 UV、顶点、面、骨架、权重或原始材质槽。
- 精确文件名前缀的优先级不变，因此 a06/a07/a08、g08 和标准命名角色不会被宽松
  回退抢走贴图；g02 的 `Abedo` 拼写兼容也继续保留。
- 透明槽采用持久化槽覆盖，不需要删除几何；清除当前槽覆盖即可恢复自动判断。
  头部逐面人工分类仍存储在网格属性中，二者都会随 `.blend` 保存。

### 验证

- 当前 g07 Blender 3.6 场景应用返回 `FINISHED`：3 个网格，缺贴图 `0`。
- 身体三个槽保持原面数 `14312 / 7034 / 24219`；前两个连接
  `pc_g07_body1_rgbx_Albedo.png`，第三个连接
  `pc_g07_body2_rgbx_Albedo.png`。
- Blender 合成回归同时覆盖插件与独立脚本的 g07 LOD 省略命名；b02 头部语义和
  非 head tear 透明槽、g02 `Albedo/Abedo` 回归继续通过。

## 2026-07-26 — ROE XPS Tools v1.1.6 / b02 下睫毛与左眼透明片

### 新增与修复

- 修复 b02 下睫毛被分到脸材质的问题。两侧下睫毛共 `300` 面，原始材质属于
  `pc_b_nk_eyebrow`，但 Eyelid 权重低于 other，旧规则把它们留在 face 槽。
- 修复左眼附近像“眼镜片”的错误几何。它不是独立眼镜模型，而是
  `pc_b_nk_tears` 的透明眼部罩层。head 内旧规则把其中 `60` 面当成脸、`56` 面
  当成睫毛；此外身体网格 `pc_b02_hd.002` 还有一个同名 `32` 面材质槽。
- v1.1.5 已修复 head 内的分区，但没有处理身体网格里的同名 tear 槽；v1.1.6 将
  所有非 head 网格的 `tear/tears` 原始槽也改为纯透明材质，完成左眼“眼镜片”修复。
- 插件和独立脚本现在都保留骨骼权重的优先判定，并增加原始材质名兜底：
  `tear/tears` 直接进入透明罩层；`brow/eyebrow/lash` 只在权重无法判定时，按相对
  眼球高度拆分眉毛和睫毛。

### 用户如何操作

1. 安装或覆盖 `scripts\riseoferos\roe_xps_addon.py`，版本应为 `1.1.6`。
2. 已经打开的 b02 场景不需要重新导入；确认模型来源与贴图目录仍指向 b02 后，
   点击一次“检查并准备材质”。
3. 本次当前 Blender 已热加载并执行完成；以后重启 Blender 会直接使用磁盘上的
   v1.1.6。
4. 检查无误后保存 `.blend`，否则本次场景内的逐面材质索引不会持久化。

### 原理与兼容性

- b02 的 `pc_b_nk_eyebrow` 同时装有眉毛、上睫毛和下睫毛，不能把整个原始材质槽
  直接映射为单一目标槽；新规则仍优先使用历史 Eyebrow/Eyelid 骨骼权重，仅处理
  权重不明确的连通块。
- `pc_b_nk_tears` 是运行时眼部效果使用的透明卡片，Blender 基础预览应统一映射到
  `Transparent BSDF` 的 `eye_overlay`，而不是赋予脸色或眉睫贴图。该规则同时应用
  于 head 的逐面分类和其他网格的原始材质槽。
- 没有修改贴图、UV、顶点、骨架或权重。g02 的 `Abedo` 回退、a08 眼球材质名兜底
  以及 a06/a07 的历史骨骼权重分类继续保留。

### 验证

- b02 当前 Blender 3.6 场景应用返回 `FINISHED`，3 个网格，缺贴图 `0`。
- b02 头部分槽：face `13920`、eye `864`、lash `804`、brow `228`、
  eye_overlay `116`。
- b02 身体网格 `pc_b02_hd.002` 的 `pc_b_nk_tears` 槽共 `32` 面，已连接到只含
  `Transparent BSDF` 与 Material Output 的透明材质。
- 真实 FBX 回归覆盖 a06、a07、a08、g02、g03：眼球均保持 `864` 面，各角色既有
  骨骼优先分类继续生效。
- 新增 Blender 合成网格测试，同时验证插件与独立脚本的脸、眼球、上下睫毛、眉毛、
  tear 罩层语义；与 g02 `Albedo/Abedo` 回归测试均通过。

## 2026-07-26 — ROE g03 白脸 / 旧导出贴图补全

### 问题与修复

- `D:\roe_exports\g03\_textures\` 是早期的不完整导出，只包含 g03 的 HD/LD
  身体 Albedo、MGAC、Normal，没有 g 体型共用的
  `pc_g_nk_face`、`pc_g_nk_eye_iris`、`pc_g_nk_eyebrow`、`pc_g_nk_hair`
  贴图。
- Blender 中身体的 Albedo 已正确连接，但头部没有材质槽；插件因缺少
  face、eye_iris、eyebrow 三项必需贴图而中止头部材质准备，所以脸显示为白色。
- 使用当前 `extract_character.ps1` 在隔离目录重新提取 g03，确认能够导出
  31 张贴图；将其中缺失的 6 张 g 体型共用贴图补入原 `_textures` 后，重新执行
  “检查并准备材质”，当前 Blender 场景已恢复。

### 用户如何操作

若旧角色出现身体有贴图、脸或头发为白色，推荐重新提取：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
.\extract_character.ps1 g03 -ExportTextures
```

重提取会清空并重建 `D:\roe_exports\g03\`，请先把自己生成的 `.blend`、`.mesh`
或烘焙贴图移到该目录之外。随后在 Blender 的 ROE 面板重新选择：

1. 模型来源：完整的 g03 HD FBX；
2. ROE 贴图目录：`D:\roe_exports\g03\_textures\`；
3. 点击“检查模型”以及“检查并准备材质”。

### 原理与兼容性

- g02、g03、g08 的 `pc_g_nk_*` 文件 SHA256 完全一致，证明它们是 g 体型公共资源，
  不是角色专属贴图。
- 当前提取脚本会合并角色包、`chara_armor_common*` 和
  `chara_*_pc_<体型>_common*`，因此新提取能补齐公共头部贴图。
- 本次没有修改 FBX、UV、骨架、权重或 Blender 材质分类算法，也没有改变 g02
  的 `Abedo` 兼容及 g08 的标准 `Albedo` 优先级。

### 验证

- 隔离重提取 g03：`28` 个 AssetBundle、`10` 个 FBX、`31` 张 PNG。
- 共用脸、虹膜、眉毛、头发及脸部 MGAC/Normal 与 g02、g08 对应文件哈希一致。
- Blender 3.6 当前场景材质准备返回 `FINISHED`：3 个网格，恢复 1 个头部原始分区，
  未恢复 0，缺贴图 0；头部恢复为 face、eye、lash、brow、eye_overlay 五个材质槽。

## 2026-07-26 — `scripts` 根目录清理与开发工具归档

### 整理内容

- 删除 `scripts` 根目录下 `19` 个未跟踪、未被仓库引用的一次性 Blender 诊断文件，
  包括 a07/a08 热重载、临时渲染、会话保存、材质对比和依赖本机旧路径的手工测试。
- 保留可复用的 Blender MCP TCP 客户端，并从
  `scripts\_blender_mcp_client.ps1` 移到
  `scripts\dev\blender_mcp\execute_code.ps1`。
- 新增 `scripts\dev\blender_mcp\README.md`，记录启动条件、命令、端口参数和任意代码
  执行的安全边界。
- 正式目录 `scripts\riseoferos`、`scripts\final`、两者的测试目录，以及旧命令兼容
  入口 `scripts\extract_character.ps1` 均保留。

### 用户如何操作

- ROE 与 FF7 Rebirth 的正常操作不变，继续从 `scripts\riseoferos` 和
  `scripts\final` 进入。
- 只有开发诊断时才使用：

  ```powershell
  .\scripts\dev\blender_mcp\execute_code.ps1 -CodeFile .\path\to\probe.py
  ```

### 原理与兼容性

- 删除项全部未被 Git 跟踪且全仓库无引用；其中多个测试仍硬编码已经迁移前的
  `scripts\roe_xps_addon.py`，继续保留会造成误用。
- 通用 MCP 客户端本身不含角色或版本逻辑，因此归档到 `dev/blender_mcp`；正式用户
  入口路径没有改变。

### 验证

- 清理后 `scripts` 根目录只剩 `README.md` 和兼容入口 `extract_character.ps1`。
- 重新检查仓库引用与 Markdown 相对链接，确认没有指向已删除的一次性脚本。
- ROE `Abedo` 回归测试与 FF7 Rebirth helper 测试仍位于各自游戏目录。

## 2026-07-26 — ROE XPS Tools v1.1.4 / g02 `Abedo` 材质兼容

### 新增与修正

- 修复 `D:\roe_exports\g02` 导入后身体材质缺失。g02 原始 HD/LD 身体颜色贴图把
  `Albedo` 拼成了 `Abedo`，而旧版只搜索 `*Albedo*.png`，导致身体网格生成无图片
  节点的平面材质。
- `roe_xps_addon.py` 与独立的 `blender_face_materials.py` 现在都先匹配标准
  `Albedo`，未命中时再匹配 g02 的 `Abedo`；若两个文件同时存在，标准拼写优先。

### 用户如何操作

1. 在 Blender 3.6 中覆盖安装 `scripts\riseoferos\roe_xps_addon.py`，然后重启
   Blender，确认插件版本为 `1.1.4`。
2. “模型来源”选择 g02 的有效 HD FBX，“ROE 贴图目录”选择
   `D:\roe_exports\g02\_textures\`。
3. 点击“导入 FBX”→“检查模型”→“检查并准备材质”。旧场景也可重新指定上述路径后，
   直接再次点击“检查并准备材质”。
4. 身体材质的 Image Texture 应连接
   `pc_g02_hd_body_rgbx_Abedo.png`，脸、眼睛、眉毛和头发继续使用共享的标准
   `Albedo` 贴图。

### 原理与兼容性

- 修复只扩展颜色贴图的文件名解析，不重命名或改写 PNG，不改变 g08 等标准
  `Albedo` 角色的优先匹配结果。
- MGAC、Normal、UV、骨架、权重、材质槽恢复和眼睛分类逻辑均未改动。

### 验证

- 对比本机 `g02` 与正确的 `g08`：g02 的 HD/LD 身体贴图均为 `Abedo`，g08 为标准
  `Albedo`，其他共享脸/眼/眉/发贴图命名一致。
- Blender 3.6 回归脚本覆盖插件和独立材质脚本：只有 `Abedo` 时能够回退命中；同时
  存在 `Albedo` 与 `Abedo` 时仍选择标准 `Albedo`。

## 2026-07-26 — FF7 Rebirth Player 待导出清单与手动流程

### 新增内容

- 新增
  [`ff7rebirth-player-export-inventory.md`](ff7rebirth-player-export-inventory.md)，
  记录 FModel 虚拟 `Player` 目录 `109` 项、本机已经写入的 `14` 项和待核查/待导出的
  `95` 项完整差集。
- 已有 14 项进一步区分为：`9` 个有效 ActorX 模型、`2` 个 Tifa 纯材质效果、
  `1` 个尚未转换的 PC7002 原始模型资源，以及 `2` 个仅含共享贴图的 Cloud 依赖目录。
- 95 项按角色建立可维护的 Markdown 复选框；`Wet/Tear/Hologram/Dirty/Blood`
  等疑似效果变体标记为先核查，避免把资源目录数误写成独立模型数。

### 用户如何操作

1. 在 FModel 中进入 `End > Content > Character > Player`，搜索清单中的完整变体名。
2. 先判断是否存在 `Model`，并打开资产确认 3D Viewer/Outliner 中是否为
   `SkeletalMesh`。
3. 模型使用 **Save Model**；整目录可使用
   **Save Folder's Packages Models**。
4. `Material` 使用 **Save Folder's Packages Properties (.json)**，
   `Texture` 使用 **Save Folder's Packages Textures**。
5. 导出后检查日志、PNG/JSON 和 PSK/PSKX；ActorX 文件头必须为 `ACTRHEAD`，再更新
   清单复选框和输出文件名。

### 原理与兼容性

- FModel 输出目录设为 `D:\ff7rebirth_exports\fmodel_exports` 并启用
  `Keep Directory Structure` 后，会把 Unreal 虚拟包路径映射为磁盘上的
  `End\Content\...` 层级；因此该目录是 FModel 导出结果，不是 Blender 创建的。
- 一级资源变体可能只有材质/贴图。只有存在 `Model` 且确认是 `SkeletalMesh` 时才执行
  Save Model；没有 Model 的效果项导出 JSON/PNG 后记录为“无独立网格”。
- 当前 FF7 Rebirth 的 glTF tangent 路径仍可能失败，骨骼模型继续使用 ActorX 和
  `First Level Only`。PC7002 当前只保留原始 UASSET，不标记为 Blender 可用。

### 验证

- 直接读取当前 FModel Folders 视图，确认 `Player` 为 `109 folders`，并取得全部一级
  目录名。
- 递归盘点本机 Player 输出：`14` 个一级目录、`266` 个文件；其中 `.pskx 8`、
  `.psk 1`、`.uasset 5`、`.json 99`、`.png 152`、`.hdr 1`。
- 对 109 项与磁盘 14 项取差集得到 95 项，分组复算
  `20+8+17+7+8+3+3+4+4+3+3+9+6=95`。
- 9 个 PSK/PSKX 均验证以 `ACTRHEAD` 开始。

## 2026-07-26 — FF7 Rebirth Tools v0.3.0 / 材质、法线与同骨架配件

### 新增与修正

#### 1. 材质改为优先读取 FModel JSON

- 插件会同时扫描“FModel 导出目录”和“贴图目录”中的 MaterialInstance JSON 与图片，
  读取 JSON 顶层 `Textures` 表中的 Unreal 参数名和资源引用。
- `Color/BaseColor/PM_Diffuse`、`Normal`、`Roughness`、`Metallic`、
  `ORM`、`Coverage/Opacity` 等参数先按语义解析，再按 `/Game/...` 包路径在保留层级的
  FModel 输出中定位同名 PNG；只有没有可用 JSON 时才退回文件名启发式匹配。
- `/Game/Renderer/Texture/...` 下的白色、黑色等渲染器占位贴图不会替代真正的角色贴图。
  Base Color 以 `sRGB` 读取，Normal、Roughness、Metallic、ORM、Opacity 以
  `Non-Color` 读取。
- 旧版把 `PC0002_00_Arms_O` 误判为 ORM，是因为在 `Arms` 中做子串匹配时命中了
  三字母通道标记 `ARM`，随后错误地把该图的 G/B 通道接到 Roughness/Metallic。
  现在 `ARM/RMA/MRA/ORM` 只有作为完整尾部词元时才算打包通道图；`Arms_O` 不再命中。
  无 JSON 的兼容回退仍识别 FF7 的 `Mg` 为 Roughness、`Mr` 为 Metallic。
- 勾选“覆盖已有基础贴图”再点击“重新匹配基础贴图”，会清理本插件旧版本生成的
  `FF7RB_` 节点后重新建立连接；不会以同名弱匹配在多个 Unreal 包之间随意选图。

#### 2. DirectX 法线转换与分级强度

- Unreal 的切线空间法线采用 DirectX `Y-`，Blender 的 Normal Map 节点按 OpenGL
  `Y+` 解释。插件现在把 Normal 图设为 `Non-Color`，保留 R/B，只对绿色通道执行
  `G' = 1 - G`，再组合后送入 Normal Map；不再把凹凸方向反着显示。
- 皮肤与眼睛需要比衣物更柔和的微表面：材质名含
  `skin/head/arms/eye/mouth` 时 Normal Strength 为 `0.35`，其他材质默认 `0.7`。
  这些值只控制 Blender 预览节点，不修改原始 PNG。

#### 3. Tifa 眼睛改为共享巩膜与角色虹膜分层

- `Eye` 材质不再把 `PC0002_00_Eye_C` 当作整颗眼球的 Base Color。该图只包含
  Tifa 的虹膜颜色，直接铺满会把眼白染暗或染红。
- JSON 的 `Color` 解析为共享巩膜 `Common_Eye_Player_C`，`IrisColor` 解析为
  `PC0002_00_Eye_C`；眼睛法线继续按 JSON 的 `Normal` 引用解析。
- Blender 节点使用 `VTXW0000` UV，以 `(0.5, 0.5)` 为虹膜中心计算二维距离：
  半径 `0.18` 内使用虹膜，`0.22` 外使用巩膜，中间用 `EASE` 色带平滑过渡。
  这能恢复可用的眼白与虹膜预览，但仍不是 Unreal 的角膜折射、湿润层和运行时眼球
  Shader 的完整复刻。

#### 4. PSK/PSKX 有效性、事务导入与三角反光修复

- 扫描时先检查 `.psk/.pskx` 至少 `32` bytes 且文件头以 `ACTRHEAD` 开始；
  结构可识别的 PSKX/PSK 优先于 FFVII Rebirth 当前可能含非法 tangent 的 glTF。
  手动指定的“模型文件”仍按用户选择导入，不会被扫描器擅自改写。
- “替换上次导入”不再在调用导入器前删除旧批次。导入器返回成功且创建对象后，还会
  先完成法线、缩放、材质等后处理；全部成功才删除旧批次并提交新批次。异常、取消、
  零对象或后处理失败都会清理本次残留对象，原模型保留。
- Blender 3.6 使用官方
  [DarklightGames/io_scene_psk_psa 5.0.6](https://github.com/DarklightGames/io_scene_psk_psa/releases/tag/5.0.6)。
  操作符检测兼容 Blender 动态 `bpy.ops` 命名空间在未注册时抛出的 `KeyError`，并支持
  `import_scene.psk`；其他版本若提供新版 `psk.import_file` 也可使用。
- `io_scene_psk_psa 5.0.6` 会把 FF7 PSK 的自定义分裂法线与 `30° Auto Smooth`
  一起带入 Blender；在这些高密度网格上几乎每个三角形都会形成可见明暗边界，因此
  即使贴图连接正确，皮肤和衣物仍会像皱纸或金属三角片。
- v0.3.0 默认勾选“PSK 导入后修复三角反光”：仅对 PSK/PSKX 新建网格把所有面设为
  Smooth，并关闭不兼容的 Auto Smooth，让 Blender 使用连续的平滑顶点法线；不改
  顶点、面、UV、骨架或权重。旧场景可在“基础材质”区点击“修复 PSK 三角反光”。

#### 5. 一键导入并绑定 Tifa 标准服装默认手套

- `PC0002_00` 主体只保留与手套衔接的手指段；掌部和手套不是权重丢失，而是独立的
  Weapon SkeletalMesh。默认皮手套的精确 FModel 虚拟路径是：

  ```text
  End/Content/Character/Weapon/WE0002_00_Tifa_LeatherGlove/Model/WE0002_00.uasset
  ```

- 在 FModel 精确搜索 `WE0002_00_Tifa_LeatherGlove`，打开 `Model/WE0002_00`，
  在 3D Viewer Outliner 右键 **Save Model**。本次实际输出为：

  ```text
  D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Weapon\WE0002_00_Tifa_LeatherGlove\Model\WE0002_00.psk
  ```

- 同时保留 `WE0002_00_Body`、`WE0002_00_Alpha`、`WE0002_00_Materia`
  Material JSON，以及 `WE0002_00_Body_A/C/Mg/Mr/N/O` 图片和原目录层级。
- v0.3.0 的 **“导入并绑定同骨架配件”** 会导入所选 PSK/PSKX，并逐个检查配件网格：
  每个实际带权 vertex group 必须在当前主体骨架中有同名骨骼，公共骨骼的
  `matrix_local` 最大元素差必须不超过 `0.01`。
- 验证通过后，按钮保留配件原权重与相对变换，把 Armature modifier 和 Parent 改为
  当前主体骨架，删除配件导入产生的重复骨架，将配件加入主体当前批次，并按当前选项
  自动修复三角反光、准备材质。任一网格不兼容时会回滚本次全部配件对象，主体不变。

### 如何操作

1. 主体按既有流程导出 `PC0002_00.pskx`。在 FF7RB 导入区保持默认勾选
   “PSK 导入后修复三角反光”，再点击“导入选中模型”。
2. 如果是 v0.3.0 以前保存的旧场景，点击“修复 PSK 三角反光”；该按钮只处理当前
   FF7RB 批次网格，无需重新导入。
3. 在材质目录层级完整的前提下，勾选“覆盖已有基础贴图”，点击一次
   “重新匹配基础贴图”；确认腿部不再使用 `Arms_O` 的 G/B 通道，眼睛同时出现眼白和
   居中的棕色虹膜、法线凹凸方向正确后，关闭该勾选项。
4. 按上述 Weapon 路径从 FModel 保存 `WE0002_00` 及其 Material/Texture。
5. 在 **“4. 独立配件/武器”** 的“配件/武器模型”选择 `WE0002_00.psk`，点击
   **“导入并绑定同骨架配件”**。无需修改“模型文件”，也无需关闭“替换上次导入”。
6. 成功提示应说明配件网格已绑定到主体骨架；在 Pose Mode 轻微旋转腕/手指骨确认
   手套随主体变形并立即撤销，然后另存 `.blend`。

### 实现原理与兼容性

- JSON 是材质实例对实际纹理包的显式引用，优先级高于相似文件名；保留 FModel
  目录层级可以消除不同 Unreal 包中同名贴图的歧义。
- 眼球分层使用 FF7 Player Eye 的两个颜色来源和 UV 径向蒙版，是 Blender 基础预览
  的确定性近似，不承诺还原游戏全部 Shader 参数。
- DirectX 绿色通道翻转解决法线方向，PSK 平滑修复解决几何分裂法线/Auto Smooth；
  两者原因不同，不能互相替代。
- PSK 主体事务导入保护 FF7RB 当前批次，不会删除 ROE 或未标记对象。配件按钮不会
  开启新的当前批次：验证成功的配件网格直接加入主体批次；失败则删除本次新建对象。
- 配件重绑只复用 PSK 已有权重，不计算自动权重。材质修复与骨架重绑仍是两条独立
  链路：材质正确不能证明骨骼兼容，骨骼兼容也不能代替材质 JSON。

### 验证

- Tifa 主体 `188,921` 顶点、`226,086` 三角面、`12` 材质、`536` 骨骼和
  `480,494` 权重记录的 PSKX 已在 Blender 3.6 导入。
- JSON 引导的无界面验证覆盖全部 `12` 个主体材质：腿部解析为
  `Legs_C/Mg/Mr/N`，眼睛解析为 `Common_Eye_Player_C` +
  `PC0002_00_Eye_C`，嘴部、头发和透明贴图也按各自 JSON 引用定位。
- 材质、扫描、法线强度、平滑修复与事务导入辅助测试共 `11` 项通过；其中覆盖
  导入器成功但材质后处理失败时回滚新对象并保留旧批次。强制重匹配
  可重复执行，不会不断叠加旧 `FF7RB_` 节点。
- 已验证新法线节点对 DirectX Normal 执行 `G' = 1 - G`，并分别写入皮肤/眼睛
  `0.35`、其他材质 `0.7` 的 Strength；主体和手套 PSK 导入后均执行平滑修复。
- FModel 已确认保存 `WE0002_00.psk`（`1,380,580` bytes）；预览为 `229`
  骨骼、`17` sockets、`3` 材质。v0.3.0 的“导入并绑定同骨架配件”已用该文件实测
  通过：自动完成骨骼/静止姿势验证、重绑主体骨架、删除重复骨架、材质准备与三角
  反光修复。

---

## 2026-07-26 — FF7 Rebirth Tifa 导出验证 / ActorX workaround

### 新增与修正

#### 1. 固化 UE4SS mapping 生成流程

- 已验证 UE4SS `v3.0.1 Beta #0`（Git SHA `c838a8ac`）可通过内置
  Keybinds 的 `DumpUSMAP()` 生成 FFVII Rebirth mapping。
- 稳定配置是将 `UE4SS-settings.ini` 中所有 `Hook...` 项设为 `0`，
  `Mods\mods.txt` 中关闭其他 Mod，只保留 `Keybinds : 1`。
- 游戏进入可响应键盘的界面后按 `Ctrl+Numpad6`；日志确认：
  `Mappings Generation Completed Successfully!`。
- UE4SS 临时输出 `--c838a8ac.usmap` 已复制为：

  ```text
  D:\ff7rebirth_exports\mappings\FF7Rebirth-4.26-20260726-c838a8ac.usmap
  ```

- 文件大小为 `2,205,102` bytes，源文件与稳定副本的 SHA256 均为：

  ```text
  5675ABC2024CA3ABC98F078B000FEE1C48EC65C015D02EB1D6CC8D107FA4BFD0
  ```

启动游戏只用于让 UE4SS 从运行时 Unreal 反射数据生成 mapping。生成并核对哈希后，
FModel 离线读取 `.pak/.utoc/.ucas`，不需要游戏继续运行；后续游戏 Fatal Error
不会使已经完整写出的 mapping 失效。

#### 2. 确认 FModel 必须使用 FFVII Rebirth 专用 profile

- 本次使用 FModel `4.4.4.0`
  (`b2708293f64ffc858b4901ff785a9078b99c67f4`)。
- Directory Selector 选择游戏根目录，不选 `End\Content\Paks`。
- 手动 profile 使用
  `GAME_FinalFantasy7Rebirth = 68812805`，不能以通用
  `GAME_UE4_26` 或 `GAME_UE4_LATEST` 代替。
- FModel 加载上述稳定 mapping 后，日志同时确认
  `GAME_FinalFantasy7Rebirth` 与
  `Mappings pulled from 'FF7Rebirth-4.26-20260726-c838a8ac.usmap'`。

#### 3. 核对 Player/Tifa 目录和标准版模型

- FModel 虚拟 IoStore 索引的 `End/Content/Character/Player` 下确认有 `109`
  个角色/服装变体目录；这些数字不是物理导出目录数。
- 其中有 `12` 个名称含 Tifa 的直接变体目录：`10` 个 PC0002 变体，另有
  `PC0099_03_Toad_Tifa` 和 `PC7002_00_Tifa_StandardCFEnd2`。
- 标准版是 `PC0002_00_Tifa_Standard`，共 `65` 个 packages：
  Material `13`、Model `7`、Texture `45`。
- Model 子目录的 `7` 项中，`Model/PC0002_00` 和
  `Model/PC0002_00_Condition` 是两个 SkeletalMesh。
- 标准主体应打开 `PC0002_00.uasset`，而不是优先选择 Condition 变体。

#### 4. 记录 glTF `Invalid Tangent` 根因并改用 ActorX

- reader 的
  `Read incorrect amount of tangent bytes ... behind: -217552`
  来自 FFVII Rebirth tangent bulk 的 stride 与精度标志不一致。
  `217,552 = 27,194 × 8`：`27,194` 个顶点的 header 声明每顶点 `8` 字节，
  解析器却按高精度每顶点 `16` 字节读取。
- glTF 保存阶段的
  `Accessor[2] TANGENT[18]: Invalid Tangent`
  是另一个独立问题：CUE4Parse 对整个 tangent `Vector4` 做归一化，破坏了 glTF
  要求的 XYZ 单位长度和手性 `W = ±1`，随后被 SharpGLTF 1.0.6 Strict 校验拒绝。
- 当前 UI workaround：
  **Settings > Models > Mesh Format > ActorX (psk / pskx)**，
  **Level Of Detail Format > First Level Only**；再打开 `PC0002_00.uasset`，
  在 3D Viewer 的 Outliner 中右键模型并选择 **Save Model**。
- ActorX 写位置、法线、UV、骨架和权重，不经过 glTF 的 `VEC4 TANGENT`
  校验。`First Level Only` 控制输出 LOD 数量，但不是 reader 修复；日志仍可能出现
  tangent bytes 错误。
- 长期修复方向是：FFVII Rebirth reader 按 tangent `itemSize` 选择 8/16 字节精度；
  glTF 只归一化 XYZ、单独保持 W 为 `±1`，或使用 SharpGLTF
  `ValidationMode.TryFix`。不建议只用 `ValidationMode.Skip`。

### 实际操作

1. UE4SS 关闭全部 Hook，只启用 Keybinds。
2. 启动游戏，按 `Ctrl+Numpad6`，等待 mapping 成功日志后关闭游戏。
3. 固定 mapping 文件名并核对 SHA256。
4. 在 FModel 为游戏根目录选择专用 `Final Fantasy VII Rebirth` profile，
   加载稳定 mapping。
5. **Settings > Models** 选择 ActorX、First Level Only、PNG，并保持目录层级。
6. 进入
   `End/Content/Character/Player/PC0002_00_Tifa_Standard/Model`，
   双击 `PC0002_00.uasset`。
7. 在 3D Viewer Outliner 右键模型，点击 **Save Model**。
8. Blender 3.6 使用 `io_scene_psk_psa 5.0.6` 导入生成的 `.pskx`；
   FF7RB 插件扫描结果不正确时手动指定该文件。

### 验证

- FModel 日志于 `2026-07-26 14:54:37` 确认成功保存：

  ```text
  D:\ff7rebirth_exports\fmodel_exports\End\Content\Character\Player\PC0002_00_Tifa_Standard\Model\PC0002_00.pskx
  ```

- 文件大小 `20,480,844` bytes，SHA256：
  `568B7280E0CB556BB7280CE18E67786257E19E0471E1221CF124C6D625DA1980`。
- PSKX chunk 边界完整，统计为 `188,921` 顶点、`226,086` 三角面、`12`
  材质、`536` 骨骼、`480,494` 权重记录和 `2` 组额外 UV。
- ActorX 导出过程不再出现 SharpGLTF `Invalid Tangent`；reader 的 tangent bytes
  日志仍存在，但没有阻止本次完整 PSKX 写出。

---

## 2026-07-25 — FF7 Rebirth Tools v0.1.0 / 脚本按游戏分目录

### 新增与调整

#### 1. 新增独立的 FFVII Rebirth 流程

- 新建 `scripts\final\prepare_fmodel.ps1`。
- 已按本机安装验证游戏资源位于 `End\Content\Paks`，包含成对的
  `.utoc/.ucas`，属于 Unreal IoStore，不能使用 ROE 的 AssetStudioModCLI。
- 脚本检查 archive 配对，建立
  `D:\ff7rebirth_exports\fmodel_exports/blender/xps`，并可启动用户已有的 FModel。
- 提取阶段不内置 AES key、mapping 或猜测的固定 UE 版本；这些内容与用户合法拥有的
  游戏构建相关。

#### 2. 新增 FF7 Rebirth Blender 插件

- 新建 `scripts\final\ff7rebirth_tools.py`，与 ROE 插件完全分离。
- Blender 侧边栏新增 **FF7RB** 页签，第一步就是选择 FModel 导出目录。
- 可递归扫描 `.glb/.gltf/.fbx/.pskx/.psk/.obj`，优先 glTF/FBX 与 LOD0。
- PSK 同时兼容新版 `psk.import_file` 和旧版 `import_scene.psk` 操作符。
- 根据材质名/贴图名匹配 Base Color、Normal、Roughness、ORM、Opacity；默认不覆盖
  已有 Base Color 连接。
- “替换上次导入”只处理本插件标记的上一个导入批次，不删除 ROE 或用户其他对象。

#### 3. ROE 脚本迁入专属目录并保留旧入口

- ROE 正式源码迁到 `scripts\riseoferos\`：
  `extract_character.ps1`、`convert_fbx.py`、`roe_xps_addon.py`、
  `blender_face_materials.py`。
- `scripts\extract_character.ps1` 保留为兼容转发入口，原命令继续可用。
- 文档链接已更新；现有 Blender 用户插件目录中的 ROE 插件不受仓库整理影响。

### 如何操作

#### FFVII Rebirth

```powershell
cd E:\code\othercode\ripper_tpose\scripts\final
.\prepare_fmodel.ps1
```

1. 在 FModel 的 Directory Selector 选择 FFVII Rebirth 游戏根目录。
2. 将 Model Export Directory 设为
   `D:\ff7rebirth_exports\fmodel_exports`，优先导出 glTF/LOD0/PNG。
3. Blender 3.6 安装 `scripts\final\ff7rebirth_tools.py`。
4. `N` → **FF7RB** → 选择 FModel 导出目录 → 扫描 → 导入。
5. PSK/PSKX 需要兼容 Blender 3.6 的 `io_scene_psk_psa 5.0.6`；glTF 不需要。

#### Rise of Eros

新路径：

```powershell
cd E:\code\othercode\ripper_tpose\scripts\riseoferos
.\extract_character.ps1 a08 -ExportTextures
```

原来的 `scripts\extract_character.ps1 ...` 仍可使用。

### 实现原理与兼容性

- 两套流程只共享文档入口，不共享引擎提取核心或 Blender Scene 属性。
- FFVII 插件只处理 FModel 的导出物，不直接访问 `.utoc/.ucas`。
- glTF/FBX 使用 Blender 内置导入器；PSK/PSKX 调用已安装的第三方导入器。
- 基础材质匹配使用规范化文件名词段、字符串相似度和贴图角色后缀评分；复杂 Unreal
  皮肤、眼球、头发 Shader 不会伪装成已经完整还原，仍需人工校正。
- ROE 的材质槽缓存、a07 腿部与 a08 眼睛修复代码没有改变，只调整了仓库路径。

### 验证

- 本机 FFVII Rebirth 安装目录检查到 `global.utoc/global.ucas` 及多组
  `pakchunk*.utoc/.ucas`。
- `prepare_fmodel.ps1` 通过 PowerShell 语法检查及隔离临时目录运行测试。
- `ff7rebirth_tools.py` 通过 Python 语法编译与 Blender 3.6 注册/注销测试。
- FF7RB 的贴图角色识别、LOD0 选择评分与 Principled Base Color 节点连接测试通过。
- 已安装到本机 Blender 3.6 用户插件目录并保存启用状态；当时 MCP 端口未监听，因此
  已打开的旧 Blender 窗口需要重启后显示 **FF7RB** 页签。
- ROE 正式脚本内容迁移后进行哈希/语法检查；旧 PowerShell 入口转发参数测试通过。

---

## 2026-07-25 — ROE XPS Tools v1.1.3

### 新增与修复

#### 1. 新增 Universal / ROE 双工作流

- “自动识别”根据对象名判断是否为 Rise of Eros 模型。
- “通用模型”保留任意 FBX/OBJ/glTF 的现有材质和关联骨架，可直接转 XPS。
- “ROE 增强”继续处理脸、眼睛、睫毛、眉毛、皮肤和多图集身体材质。
- 处理范围支持“最新导入”“所选网格”“所有可见”，并可采用其他插件导入的所选模型。
- 新增模型诊断、当前材质槽用途/贴图覆盖、头部选中面人工分类及高级眼睛/睫毛参数。

#### 2. 恢复原始材质分区，修复 a07 腿部贴图

- 导入时缓存原始材质槽名称和每个面的材质索引。
- 旧场景已经被压成单一材质槽时，可从“模型来源”指定的原始 FBX 临时恢复分区。
- a07 的身体恢复为四槽分区：
  `pc_a07_hd_body 2 / skin / body 1 / skin2`，分别使用 `body1/body2` Albedo。
- a07 应使用：
  `D:\roe_exports\a07\pc_a07_hd (1)\FBX_GameObjects\pc_a07_hd\pc_a07_hd.fbx`。
  无后缀的 `pc_a07_hd` 本身只有一个身体材质槽，不能用于恢复。

#### 3. 新增“修复眼睛”按钮，修复 a08 眼球误判

- a08 虽然存在 `Eyeball` 顶点组，但 864 个眼球面的 Eyeball 权重不足。
- 旧算法发现语义骨骼组后会关闭几何兜底，因而把眼球全部判成脸，表现为纯白或脸色眼球。
- v1.1.3 新增原始 `eye/eyes/iris` 材质名兜底，并在 ROE 面板增加独立
  **“修复眼睛”** 按钮。
- 按钮只重建眼球材质，并修正眼球槽及误入眼球槽的面；已有有效缓存时不会恢复或扰动
  整个头部材质分区。

#### 4. 提取脚本合并 Steam 安装资源与 LocalLow 缓存

- `extract_character.ps1` 新增 `-CacheRoot`。
- 同时扫描游戏安装目录和
  `%USERPROFILE%\AppData\LocalLow\Pinkcore\Rise of Eros\AssetBundles`。
- 同名 AssetBundle 优先选择更新时间较新的文件；时间相同时优先运行时缓存，并从安装目录
  补齐公共包。
- `-List` 同时识别 `chara_armor` 与 `chara_bare` 模型包，可列出新角色、活动角色和
  只有裸模的 NPC。

### 如何操作

#### 更新插件

1. Blender 3.6 → `Edit > Preferences > Add-ons > Install...`。
2. 选择 `scripts\riseoferos\roe_xps_addon.py` 并覆盖安装。
3. 重启 Blender；仅覆盖磁盘文件不会替换当前内存中的旧代码。

#### 新提取并导入角色

```powershell
.\extract_character.ps1 a08 -ExportTextures
```

1. 在 Blender 3D 视口按 `N`，打开 **ROE** 页签。
2. 工作流选“自动识别”或“ROE 增强”，处理范围选“最新导入”。
3. “模型来源”选择包含完整材质槽的 HD FBX。若有同名 `(1)` 目录，应检查并优先选择
   带完整材质槽和贴图引用的那一份。
4. “ROE 贴图目录”选择 `D:\roe_exports\<角色>\_textures\`。
5. 点击“导入 FBX”→“检查模型”→“检查并准备材质”。
6. 若眼球仍为纯白或脸色，点击 **“修复眼睛”**。
7. 设置 XPS 输出路径后导出。

#### 修复已有场景

1. 在“模型来源”重新指定该角色的原始 FBX，在“ROE 贴图目录”指定 `_textures`。
2. 点击“检查并准备材质”，恢复丢失的身体/头部原始分区。
3. 仅眼球不对时直接点击“修复眼睛”，无需重新导入整个角色。
4. 确认效果后另存 `.blend`；按钮修改的是当前场景内存，未保存不会持久化。

### 实现原理

#### 原始材质布局缓存与恢复

- 对象属性 `roe_source_materials` 保存 FBX 原始材质槽名。
- 面属性 `roe_source_material_index` 保存每个面的原始槽索引。
- `roe_source_fbx` 保存来源 FBX。
- 旧场景缺缓存时，插件临时导入来源 FBX，按对象规范名、顶点数、面数及逐面拓扑匹配，
  复制材质布局后立即删除临时对象。
- 多图集身体根据原始 `body/skin/body1/body2` 槽名寻找对应 Albedo，不再把所有面压到
  第一个贴图。

#### 眼部识别

head 网格先按顶点连通块拆解，再组合以下信号分类：

- `Eyeball / Eyebrow / Eyelid` 骨骼权重；
- 连通块面数、中心高度和尺寸；
- UV 是否位于 `[0,1]`、UV 跨度及是否收缩到小区域；
- 原始材质名中的 `eye/eyes/iris`、`eyebrow/lash`、`tear` 等语义。

a06 没有语义骨骼组时继续使用几何兜底；a07 优先使用有效骨骼权重；a08 在权重不足时
由“眼睛材质名 + 眼球几何”兜底，因此兼容旧角色且不会把整块脸材质误认成眼球。

#### 资源目录合并

提取脚本先建立两个 AssetBundle 根目录的统一清单，再按文件名分组。每组选出更新时间
最新的候选，时间相同时用来源优先级打破平局，最后复制到角色临时 staging 目录交给
AssetStudioModCLI。

### 验证

- a06：眼球 864 面；修复按钮前后脸、睫毛、眉毛、罩层分配不变。
- a07：眼球 864 面；身体四槽面数为 `10017 / 10319 / 22679 / 2948`。
- a08 与 `a08_outfit1`：眼球从脸槽恢复为 864 面，使用
  `pc_a_nk_eye_iris_rgbx_Albedo.png`。
- a08 原始 FBX 可不先准备材质，直接点击“修复眼睛”生成完整五槽头部材质。
- 通用模型材质保留、旧场景缓存恢复、损坏缓存恢复和手工头部区域覆盖测试通过。
