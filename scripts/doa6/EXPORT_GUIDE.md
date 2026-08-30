# DOA6 导出指南：官方模型 与 nude/mod 变体

两条路线共用同一套底层（RDB 解包 → G1M/G1T → Noesis → Blender 组装），
区别只在服装网格从哪来。本文件与脚本同目录，命令可直接复制运行。

```
                    ┌─ 官方服装 ──→ export_full.ps1      ─┐
CharacterEditor.rdb ┤                                      ├→ 带材质 .blend + 预览
MaterialEditor.rdb  └─ mod 服装 ──→ export_nude_mod.ps1   ─┘   (D:\doa6_exports\_blends\)
                         (REDELBE layer2 zip/目录)
```

角色 = **服装(COS) + 发型(HAIR) + 脸(FACE)** 三部件，骨架同源自动对齐。
nude 变体只换 COS，发型/脸复用官方导出结果。

---

## 一、非 nude（官方模型）

```powershell
cd E:\code\othercode\ripper_tpose\scripts\doa6

.\export_full.ps1 KAS -Label KAS_Kasumi            # 默认 COS_001/HAIR_001/FACE_001
.\export_full.ps1 MOM -Cos 102 -Label MOM_泳装      # 换服装编号
.\export_full.ps1 AYA -Force                       # 覆盖重导
```

查角色有哪些编号：

```powershell
python extract_rdb.py "D:\Program Files (x86)\Steam\steamapps\common\Dead or Alive 6\CharacterEditor.rdb" `
  --list --types g1m --filter "KAS_*"
```

编号规律：`COS_000~0xx` 本体服装，`COS_10x` 起多为 DLC（泳装集中在此）。
客串角色（MAI/SNK/NIC）的 `COS_000~003` 是无 ktid 的占位调试体，**正装从 004 起**。

---

## 二、nude / mod 变体

需要先有该角色的官方发型和脸（即先跑过 `export_full.ps1 <CHR>`）。

```powershell
# zip 直接喂，或已解压目录也行
.\export_nude_mod.ps1 D:\doa_mods\doa6\_zips\xxx_nude_helena.zip -Chr HEL -Label HEL_Helena_Nude

# 启发式路线猜错时（预览里皮肤和衣服贴图互换），按提示的材质号纠正后重跑
.\export_nude_mod.ps1 D:\mods\ayane_malf.zip -Chr AYA -Label AYA_Malf -Assign "3=f01,5=body"
```

脚本会自动选路线并在输出里标明：

| 路线 | 触发条件 | 材质映射 | 可靠性 |
|---|---|---|---|
| **A 精确** | mod 替换的服装编号本机有（如 `HEL_COS_001`） | 原版 ktid 链（`g1m_matmap.py`） | 一次到位 |
| **B 启发式** | 替换未安装的 DLC 位（如 `MOM_COS_105`） | 按网格大小猜部位（`mod_matmap.py`） | 多数一次对，偶尔需 `-Assign` |

**路线 B 怎么纠正**：看生成的预览图。若躯干皮肤上出现衣服花纹（或反之），
把脚本打印的 `assign: {3: 'body', 5: 'f01'}` 里两个部位对调，作为
`-Assign "3=f01,5=body"` 重跑即可。零顶点材质（Malf 删掉的衣物）无需理会。

### mod 从哪来

- **GameBanana**（可直连脚本化下载）：`gamebanana.com` DOA6 game id = **6966**。
  列表 `https://gamebanana.com/apiv11/Util/Search/Results?_sModelName=Mod&_sSearchString=nude&_idGameRow=6966&_nPage=1`，
  下载直链 `https://gamebanana.com/apiv11/Mod/<id>/DownloadPage` 里的 `_sDownloadUrl`。
  在售内容多为「裸微比基尼 / 走光(Malf)」类。
- **LoversLab / DeviantArt**：全裸整合包（如 SaafRats 全角色）在这里，但**需登录**，
  无法脚本化；手动下好后 zip 路径直接喂给 `export_nude_mod.ps1` 即可。
- DOA5LR 的 mod 同样能转（`import_mod.ps1`，出 FBX+DDS，不组装 blend）。

---

## 三、脚本清单

| 脚本 | 作用 |
|---|---|
| `export_full.ps1` | **官方角色一键**：三部件 → 材质映射 → PNG → .blend + 预览 |
| `export_nude_mod.ps1` | **mod 变体一键**：mod 服装 + 官方发型/脸 → .blend + 预览 |
| `export_character.ps1` | 单部件提取（模型+贴图+FBX），上面两个的底层 |
| `extract_rdb.py` | RDB 解包器（自研，修复了 Cethleann 的 zlib 截断 bug） |
| `g1m_matmap.py` | 精确材质映射（g1m → ktid → kidssingletondb → g1t） |
| `mod_matmap.py` | 启发式材质映射（mod 无原版 ktid 时） |
| `build_blend.py` | Blender 无头组装：导入部件、挂材质、打包贴图、渲预览 |
| `import_mod.ps1` | 任意 DOA5LR/DOA6 mod 批量转 FBX+DDS（不组装） |

格式细节、坑与依赖路径见同目录 `README.md`；产物索引见 `D:\doa6_exports\README.md`。

---

## 四、常见问题

- **缺部件报错**：先 `export_full.ps1 <CHR>` 把该角色的 HAIR/FACE 导出来。
- **Blender 打开贴图全白**：确认用的是 `_blends\` 里的 .blend（贴图已打包），
  不是部件目录里的裸 FBX。
- **发型是白模**：个别角色（如 Phase 4）的 HAIR 在 MaterialEditor 里确实没有贴图。
- **.ps1 报 "missing terminator"**：脚本被存成无 BOM 的 UTF-8 了。PowerShell 5.1
  会按 GBK 解析中文注释吞掉引号——用 UTF-8 with BOM 重存。
- **不要用 Cethleann.DataExporter 解 DOA6**：它会截断文件，坏 g1m 让 Noesis 静默崩溃。
