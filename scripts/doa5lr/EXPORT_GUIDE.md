# DOA5LR 导出指南：官方模型 与 nude/mod 变体

与 `scripts\doa6\EXPORT_GUIDE.md` 对应的 DOA5LR 版本。本文件与脚本同目录，
命令可直接复制运行。

```
                 ┌─ 官方 TMC ──→ 按名字从封包提取  ─┐
.bin/.lnk 封包 ──┤                                   ├→ export_full.ps1 → 带材质 .blend + 预览
                 └─ mod  TMC ──→ -TmcFile 直接喂    ─┘   (D:\doa5lr_exports\_blends\)
```

角色 = **服装 + 脸 + 头发** 三个独立 TMC（和 DOA6 一样）：

| 部件 | 条目名 | 不加会怎样 |
|---|---|---|
| 服装 + 身体 | `<角色>_COS_NNN` | — |
| 脸 | `<角色>_FACE`（**无编号**） | 不加 `-Face` → 无头 |
| 头发 | `<角色>_HAIR_NNN` | 不加 `-Hair` → 光头 |

少数 DLC 服装（如 `KASUMI_DLC_011`）自带头部，但 `COS_` 系一律不带。

---

## 一、非 nude（官方模型）

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa5lr

# 标准三部件（推荐写法）：-Face auto 会自动用 <角色>_FACE；
# -Archive 缺省 auto，自动查条目在哪个封包（首次扫全部 .bin 建索引 _archive_index.txt）
.\export_full.ps1 KASUMI_COS_001 -Face auto -Hair 001 -Label KASUMI_Kasumi
.\export_full.ps1 MARIE_COS_001 -Face auto -Hair 001 -Label MARIE_MarieRose

# 换服装编号：脸和发型已经提取过就直接复用，只解包新服装
.\export_full.ps1 KASUMI_COS_002 -Face auto -Hair 001 -Label KASUMI_Kasumi_COS_002
.\export_full.ps1 KASUMI_DLC_011 -Face auto -Hair 001 -Label KASUMI_Kasumi_DLC_011
```

> 19 名女性角色的默认服装 + **全部 223 套换装（COS/DLC）** 已批量导出在
> `D:\doa5lr_exports\_blends\`（见该目录 README §1）。换装批量就是上面那条命令
> 按清单循环：`python extract_lnk.py <bin> --list` 抓 `<角色>_(COS|DLC)_NNN.TMC`，
> 三路并行，每套 5–16 s。

**查名字**（DOA5LR 模型分散在 36 个封包里；`-Archive auto` 会自己找，手动指定时要选对）：

```powershell
python extract_lnk.py "D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 5 Last Round\chara_initial.bin" `
  --list --filter "KASUMI*"
```

| 封包 | 内容 |
|---|---|
| `chara_initial` | **常规服装/发型的主场**（`KASUMI_DLC_011`、`KASUMI_HAIR_001`…） |
| `chara_common` | BOSS 变体（`*_BOSS_*`）与公共件 |
| `rtm_common` | 过场动画版角色（265 个） |
| `patch_XX_catalog` | 后期 DLC |
| `stage_*` | 场景 |

服装命名是**纯编号**（`COS_001` / `DLC_011`），名字看不出款式，只能导出后看预览挑——
画廊页（`html\index.html`）可按角色下拉筛选、搜服装号。`DLCU_NNN`（47 套）是 DLC 的
变体位，本批未导；`MILA_COS_008 / SARAH_DLC_002 / PAI_DLC_002` 是 10KB 占位条目，跳过。
头发一律用 `HAIR_001`；官方每套服装的默认发型无法从条目名得知，需要别的发型用
`-Hair 003` 重导。

---

## 二、nude / mod 变体

> **DOA5LR 没有官方 nude**：全部 36 个封包、12,625 个条目名搜
> `nude/naked/bare/skin/under/lingerie`，零命中。衣服底下的皮肤网格被裁掉了。

nude 只能用社区 mod。DOA5LR 的 mod 就是替换用的 `.TMC` + 同名 `.TMCL`（贴图库），
与官方格式完全一致，所以拿到就能直接用：

```powershell
# 纯 mod（身体+头发都来自 mod）
.\export_full.ps1 -TmcFile D:\mods\KasumiNude.TMC -Label KAS_Nude
.\export_full.ps1 -TmcFile D:\mods\body.TMC -HairTmc D:\mods\hair.TMC -Label X

# 混用：mod 身体 + 官方发型（最常见）
.\export_full.ps1 KASUMI_DLC_011 -TmcFile D:\mods\nude.TMC -Archive chara_initial -Hair 001 -Label KAS_Nude

# 只要 FBX+DDS 不要 blend（也支持整包 zip/目录批量）
.\import_mod.ps1 D:\mods\some_mod_folder
```

- `-TmcFile` 也接受**目录**，会取其中第一个 `.TMC`（省得从 mod 包里翻文件）。
- 找不到同名 `.TMCL` 会警告并出白模，不会静默出错。
- 中转目录：`D:\doa5lr_exports\_mods\<TMC名>\`。

### mod 从哪来

| 来源 | DOA5LR 库存 | 能否脚本化下载 |
|---|---|---|
| LoversLab | 大量（主力站） | ❌ 需注册登录，手动下 |
| GameBanana | **0 个**（game id 6968 页面是空的） | — |
| 日本社区（2ch / 个人站） | 大量 | ❌ 分散、多数链接已死 |

对比：DOA6 在 GameBanana（game id 6966）能直连脚本化下载，DOA5LR 不行。

---

## 三、脚本清单

| 脚本 | 作用 |
|---|---|
| `export_full.ps1` | **一键**：官方名或外部 mod TMC → 带材质 .blend + 预览 |
| `export_character.ps1` | 按名字从封包提取 → FBX + DDS（上面那个的底层） |
| `extract_lnk.py` | `.bin/.lnk` 解包器（自研：解混淆名 + XOR 解密 + 分块 zlib） |
| `build_blend.py` | Blender 无头组装：材质重建、部件对齐、打包贴图、渲预览 |
| `import_mod.ps1` | 任意 mod（zip/目录）批量转 FBX+DDS，不组装 blend |
| `html/collect_manifest.py` | Blender 无头扫全部 blend，收集统计写 manifest |
| `html/make_gallery.py` | 读 manifest 生成可浏览的单页画廊 `html/index.html` |

### 浏览已导出的模型

```powershell
blender --background --factory-startup --python html\collect_manifest.py
python html\make_gallery.py
```

生成 `scripts\doa5lr\html\index.html`：缩略图网格、搜索、按封包筛选、告警标记，
卡片直接链到本机的 blend 与原图。缩略图写在 `D:\doa5lr_exports\_gallery\thumbs\`，
**不进仓库**（同 ROE 的规矩，仓库不收任何游戏素材）。

格式细节与实现要点见同目录 `README.md`；产物索引见 `D:\doa5lr_exports\README.md`。

---

## 四、常见问题

- **光头 / 无头**：没加 `-Hair` / `-Face`。服装 TMC 既不含头发也不含脸。
- **皮肤/衣服半透明、像撒了噪点**：已修复。DOA5LR 很多贴图把高光遮罩塞在 alpha
  通道里，早期版本无差别接到 Principled 的 Alpha 上就会这样。现在按数据判定：
  要求 **>2% 全透明 且 >4% 全不透明** 像素才认定为镂空遮罩。
- **头发压在脸上 / 没有脸**：已修复。早期版本无条件按包围盒"对齐"部件，但实测
  多数角色三部件本来就同处一个坐标系——强行对齐反而挪歪（马尾的包围盒顶端是发梢
  不是头顶；女天狗的翅膀撑大身体包围盒，导致脸被判定为不在位而整个挪走）。
  现在默认不动，只搬真正不在身体坐标系的部件（如霞的头发）。
- **头发位置偏一点**：头发 TMC 用自己的局部原点，FBX 又无骨架，脚本按几何对齐
  （头发包围盒的 X/Y 中心 + 顶部 → 身体 `*Head*` 网格）。马尾类后垂发型可能需要
  在 Blender 里前后微调几毫米。
- **找不到条目**：换封包（见 §1 表），或先用 `extract_lnk.py --list --filter` 查。
- **渲染是空白**：已修复（Noesis 以 scale 0.01 导出，角色仅 ~1.6cm 高会落在相机
  近裁剪面内）；`build_blend.py` 现在会归一到约 1.7 单位。
- **mod 出白模**：mod 目录里缺同名 `.TMCL` 贴图库。
- **.ps1 报 "missing terminator"**：脚本被存成无 BOM 的 UTF-8。PowerShell 5.1 会按
  GBK 解析中文注释吞掉引号——用 UTF-8 with BOM 重存。
