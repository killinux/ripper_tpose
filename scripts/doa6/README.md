# Dead or Alive 6 脚本说明

DOA6（KTGL v2 / "NewSoftEngine"，RDB 封包）角色提取与转换。链路：

```
游戏 .rdb 索引 + .rdb.binXX 数据体（约 60GB）
   │  ① extract_rdb.py        （索引解析 + 名称映射 + 分块 zlib/lz4 解压）
   ▼
G1M（模型+骨架） + G1T（贴图） + ktid/mtl/oid 配套
   │  ② Noesis64 + ProjectG1M.dll（export_character.ps1 自动调用）
   ▼
FBX + DDS 贴图  （D:\doa6_exports\<服装>\）
```

> **为什么自研 extract_rdb.py**：社区的 Cethleann.DataExporter（已停更）zlib 解压
> 每块只调一次 `DeflateStream.Read`，读不满即丢弃，**几乎所有角色 g1m/g1t 在 ~80%
> 处截断**（1536 个 g1m 里 1300 个坏），坏文件会让 ProjectG1M 插件直接崩掉 Noesis。
> 本实现按块完整解压，产物大小与 G1M/G1T 头部声明一致。文件名映射复用 Cethleann
> 发行包里的 filelist CSV。

## 1. 环境准备（一次性，已部署）

| 依赖 | 路径 | 说明 |
|---|---|---|
| 游戏本体 | `D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 6` | `CharacterEditor.rdb`（模型）、`MaterialEditor.rdb`（贴图，45GB） |
| 文件名清单 | `E:\tools\doa6\cethleann\filelist-DeadOrAlive6-rdb.csv` | KTID→名称（约 5.5 万条） |
| 扩展名映射 | `E:\tools\doa6\cethleann\filelist-RDBExt-rdb.csv` | TypeInfoKTID→g1m/g1t/ktid/... |
| Noesis 64 位 | `E:\tools\noesisv\Noesis64.exe` | 插件 `plugins\x64\ProjectG1M.dll`（v1.7.4.2；32 位同名 dll 在 `plugins\`） |
| Python 3 | `D:\openclaw\python\python.exe` | zlib 标准库；lz4 条目需 `pip install lz4`（DOA6 实测全 zlib） |
| 输出 | `D:\doa6_exports\` | |

备用工具：`E:\tools\doa6\cethleann\`（完整 Cethleann 套件，含 Nyotengu.* DOA6 工具，
注意其 DataExporter 有上述截断 bug）；eterniti 的 rdbtool/g1mtools 源码在 GitHub
（modsfire 预编译包被 Cloudflare 拦，未落地）。

## 2. 快速开始

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa6

# 列出全部模型（1536 个 g1m：角色/服装/发型/道具）
.\export_character.ps1 -List

# 一套服装：g1m+配套 + MaterialEditor 贴图 + FBX + DDS
.\export_character.ps1 HON_COS_002

# 多套；发型通常没有独立 MaterialEditor 贴图
.\export_character.ps1 KAS_COS_001,HON_HAIR_011 -NoTextures
```

角色代号：HON=Honoka、KAS=Kasumi、AYA=Ayane、MAI、MAR=Marie、HTM=Hitomi、
LEI=Leifang、TIN=Tina、...（`-List` 全看得到）。

`extract_rdb.py` 单独用：

```powershell
python extract_rdb.py "<游戏>\CharacterEditor.rdb" --list --types g1m --filter "KAS_*"
python extract_rdb.py "<游戏>\MaterialEditor.rdb" -o D:\out --filter "*KASCOS001_*" --types g1t
```

## 3. 格式与实现要点

- `.rdb` 索引：头 24 字节（magic/ver/headerSize/system/count/nameDbKTID）+ 数据目录
  字符串；每条目 48 字节结构（magic `_DRK`… 实为 4 字节 + ver + entrySize/contentSize/
  size(i64×3) + type + fileKTID + typeKTID + flags）+ 地址串
  `offset@size[#binId][&binSub][?path]`（十六进制），条目按 4 字节对齐前进。
- 数据体 `<名>.rdb.bin[<binId>][_<binSub>]`：offset 处再包一层同结构 `IDRK` 头，
  content 段才是载荷；**解压与否看外层条目 flags**（0x100000=zlib 分块，0x200000=lz4，
  0x10000=external 散装 `0x<ktid>.file`，在数据目录/游戏根的十六进制目录里）。
- zlib 分块：`[u32 块长][zlib 流]` 重复到块长 0 或尾部。
- 名称：CSV 无则回落 `<ktid 十六进制>.<扩展名>`。
- 贴图归属：服装 `HON_COS_001` 的贴图在 MaterialEditor 里叫
  `MPR_Muscle_Character_HONCOS001_<部位>_<通道>.g1t`（去下划线拼接）；通道后缀
  kidsalb=Albedo、kidsnmh=Normal、kidsocc=AO、kidsrfr=Roughness/反射、kidsmm1/2=
  高清混合图、kidsemi=自发光。精确到面的贴图分配在 `.ktid`/`.mtl`（哈希引用），
  当前脚本按名称模式整套拉取，未做逐材质绑定。
- G1M→FBX 的骨骼名恢复需 `Oid.bin`（ProjectG1M 的 bLoadG1MOid 选项）；`oid/` 已随
  CharacterEditor 提取，如需带名骨架可在 Noesis GUI 里配合加载。
- **材质→贴图精确映射（g1m_matmap.py）**：g1m 的 G1MG 材质段（0x00010002，
  每材质头 16B + 12B/贴图槽）给出 submesh→材质→槽位；槽位查部件 `.ktid`
  （(index,ktid) 对表）得 TexContext 对象 KTID；对象存于
  `CharacterEditor/MaterialEditor.kidssingletondb`（KIDSSystemResource.rdb 内，
  IDOK 记录：hdr12+ktid+typeinfo+propCount+属性表+值区），其属性 `0x6c7321d2`
  (KTGLTexContextResourceHash) 的 UInt32 值即 g1t 文件 KTID，再查 CSV 得名。
  注意 Cethleann 的 OBJDB 解析器读不了 DOA6 这版 `_DOK` 容器（Count 字段布局不同），
  Nyotengu.KTID 会静默产出空 g1t——别用。

## 3.4 export_full.ps1 —— 一条命令出完整带材质 .blend（推荐入口）

```powershell
.\export_full.ps1 KAS -Label KAS_Kasumi          # 默认 COS_001/HAIR_001/FACE_001
.\export_full.ps1 MOM -Cos 102 -Label MOM_DLC    # 指定编号
```

内部串联：export_character（三部件+贴图+FBX）→ g1m_matmap（材质映射）→
alb/nmh DDS→PNG → build_blend（组装+打包+渲预览）。产物在
`D:\doa6_exports\_blends\<Label>.blend` + `_preview.png`。
角色代号花名册与产物索引见 `D:\doa6_exports\README.md`。

## 3.5 组装带材质 Blend（build_blend.py + g1m_matmap.py）

完整角色 = COS（身体+服装）+ HAIR + FACE 三个部件，骨架同源、原点对齐。流程：

```powershell
# ① 三个部件常规导出（模型+贴图+FBX）
.\export_character.ps1 MOM_COS_001,MOM_HAIR_001,MOM_FACE_001
# ② 每部件生成 submesh→贴图映射（需先解出 kidssingletondb，见 §3 注）
python g1m_matmap.py D:\doa6_exports\MOM_COS_001\MOM_COS_001.g1m D:\doa6_exports\MOM_COS_001\MOM_COS_001.ktid -o D:\doa6_exports\MOM_COS_001\matmap.json
# ③ 把映射用到的 alb/nmh DDS 转 PNG 到部件 _png\（Blender 读不了 BC7 DDS）
# ④ 组装 + 打包 + 渲预览
blender --background --factory-startup --python build_blend.py -- ^
  D:\doa6_exports\MOMIJI.blend D:\doa6_exports\MOMIJI_preview.png ^
  D:\doa6_exports\MOM_COS_001 D:\doa6_exports\MOM_HAIR_001 D:\doa6_exports\MOM_FACE_001
```

依赖的对象库（一次性解出到 `D:\doa6_exports\_objdb\`）：
`CharacterEditor.kidssingletondb`、`MaterialEditor.kidssingletondb`
（均在 KIDSSystemResource.rdb 里，用 extract_rdb.py --filter 提取）。

坑：FBX 导入会带进 `model_0_submesh_N` 占位 Image，`pack_all` 会炸——
build_blend.py 已按「存在才 pack、失效即删」处理。

## 4. 已验证

- HON_COS_001.g1m：1815492 字节 == 头部声明（Cethleann 版本只有 1516258，截断）。
- HON_COS_002：`export_character.ps1` 全链路 exit 0 —— FBX 2.6MB + 154/154 张 DDS。
- MaterialEditor 定向抽取 `*HONCOS001_*`：83 个 g1t 全部大小校验通过（含 22MB 4K 图）。
- g1t→DDS：ProjectG1M 按贴图索引输出 `0.dds`...，脚本自动改回 g1t 基名。

## 5. 坑

- **别用 Cethleann.DataExporter 解 DOA6**（截断 bug，见上）；它解出的坏 g1m 还会让
  Noesis 无提示崩溃，表现为"打开就 crash"。
- ProjectG1M 是原生插件：32 位 dll 放 `plugins\`、64 位放 `plugins\x64\`，配对使用
  `Noesis.exe`/`Noesis64.exe`；版本混放没问题（本机 32 位=1.8.1，64 位=1.7.4.2）。
- `.ps1` 必须带 UTF-8 BOM（PowerShell 5.1 中文脚本问题，同 DOA5LR）。
- `--filter` 是 fnmatch：`HON_*` 匹配不到贴图（它们叫 `MPR_Muscle_Character_HONCOS...`），
  贴图用 `*HONCOS001_*` 这类去下划线模式。
