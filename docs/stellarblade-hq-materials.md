# 剑星高清材质：`_HQ.blend` 和「剑星游戏材质」插件的原理

一句话：PMX 只带一张颜色贴图，游戏里的完整材质另存成存档里每套衣服旁边的 `<名字>_HQ.blend`。
插件「剑星游戏材质」按**材质名**从这些文件里把节点搬进你导入的 PMX。

相关代码：

| 文件 | 作用 |
|---|---|
| `scripts/stellarblade/hq_materials.py` | 把游戏的材质参数翻译成 `materials.json` |
| `scripts/stellarblade/hq_materials_blender.py` | 在存档 .blend 的副本上接节点，存成 `_HQ.blend` |
| `scripts/stellarblade/hq_mod_outfits.py` | Nexus mod 服装的高清版，一条命令跑完整条线 |
| `scripts/stellarblade/game_materials_blender.py` | 插件的核心：找 `_HQ.blend`、搬节点、切换 |
| `scripts/blender_addons/stellarblade_game_materials/` | 插件的界面（侧栏面板、按钮） |

用法见插件的 README，各套衣服的记录见 `scripts/stellarblade/README.md`「高清材质」一节。

## 1. 为什么要单独一份 `_HQ.blend`

| | PMX（MMD） | 游戏里的材质 |
|---|---|---|
| 贴图 | 每个材质一张颜色贴图（另有 toon、sphere） | 底色、法线、ORM（R 遮蔽 / G 粗糙度 / B 金属度）、遮罩、自发光、花纹法线、皮肤的 ORSS…… |
| 参数 | 漫反射、高光、环境色 | 粗糙度范围、金属度、清漆、绒毛光泽、自发光强度、透明裁剪、次表面散射…… |

PMX 装不下这些，所以导出 PMX 时只把「底色 × AO」烘成一张 `_pmx.png`（会发光的材质再叠上自发光颜色）。
完整的节点网络存在 Blender 文件里，要用时由插件搬进来。

## 2. 存档里的样子

```
E:\game_export\StellarBlade\
├─ Eve\
│  ├─ blend\
│  │  ├─ CH_P_EVE_Nikke_06\
│  │  │  ├─ Eve_CH_P_EVE_Nikke_06.blend        打包时的 .blend，只接了底色
│  │  │  ├─ Eve_CH_P_EVE_Nikke_06_HQ.blend     高清版，脚本生成，和上面那个放在一起
│  │  │  └─ textures\  textures\extra\         两个 .blend 都用相对路径读这里的贴图
│  │  └─ Mod_VindictusDemonMaiden\ …           mod 服装另有 textures\mod\（mod 自带的贴图）
│  └─ pmx\CH_P_EVE_Nikke_06\Eve_CH_P_EVE_Nikke_06.pmx
├─ Fiona\blend\Mod_VindictusFiona\Eve_Mod_VindictusFiona_HQ.blend
├─ Reika\blend\Mod_GantzReika_A\ …
└─ _meta\hq_materials\<服装包>\                生成高清版时的中间数据，插件不读
```

`_meta\hq_materials\<服装包>\` 里放的是：材质实例的 JSON（`mi_json\`、`staged\`）、`materials.json`、`skin.json`、`normals.json`、`hq_log.txt`。
重做高清版时用得上，平时可以不管。

## 3. `_HQ.blend` 是怎么做出来的

```
游戏 / mod 的 .pak ──CUE4Parse──▶ 材质实例 JSON ──合并──▶ materials.json ──Blender──▶ <名字>_HQ.blend
                      （实例 → 父实例 → 母材质）      （hq_materials.py）     （hq_materials_blender.py）
```

1. **读材质实例**：用 CUE4Parse 从游戏包里读出这套衣服用的材质实例，再顺着父实例一直读到母材质。
   mod 的话，读 mod 自己的实例，再连上它继承的游戏材质。
2. **按 UE 的规则合并参数**：
   - 子实例设了的值优先；
   - 谁都没设的，取母材质的默认值（`CachedExpressionData`）；
   - 参数名不分大小写（UE 的 FName），`BaseColor` 和 `Basecolor` 是同一个参数。
3. **翻译**（`hq_materials.py`）：认出每张贴图是底色、ORM、法线还是遮罩，写进 `materials.json`。
   同时写出 PMX 用的 `<底色>_pmx.png`（底色 × AO）。
4. **接节点**（`hq_materials_blender.py`）：打开存档里那份 .blend，按 `materials.json` 把每个材质重接成 Principled：
   - ORM：G → 粗糙度（落在实例的最小–最大值之间），B → 金属度；
   - 法线：UE 是 DirectX 格式，翻绿通道；
   - 清漆、绒毛光泽、自发光、针织花纹按各自的遮罩接；
   - 贴花按 1/3 透明裁剪；眼睛按游戏参数重做。

   **另存**为同一文件夹里的 `<名字>_HQ.blend`，原来那份不动，贴图用相对路径。
5. **mod 服装多一步**（`hq_mod_outfits.py --post`）：
   - 皮肤（母材质 `MA_Skin_EVE`）：ORSS 遮罩 → 粗糙度和高光，次表面散射照脸的设置。
     mod 皮肤没带自己的遮罩时，先比较 mod 的法线图和游戏原版身体的法线图：
     - 相关系数 ≥ 0.5：同一套 UV（例：Demon Maiden 0.92），直接用原版遮罩；
     - 否则（例：Fiona 约 0）：取遮罩的平均值当常数。
   - 每张法线图检测绿通道方向，mod 作者弄反的按反的读。
   - 母材质不透明的皮肤，断开底色的透明通道。

命令：

| 哪种衣服 | 命令 |
|---|---|
| 游戏原版服装 | `scripts/stellarblade/README.md`「高清材质」一节的 1–3 步 |
| Nexus mod 服装 | 在 `hq_mod_outfits.py` 的 `OUTFITS` 里加一条，然后 `python scripts/stellarblade/hq_mod_outfits.py --only <服装包>` |

## 4. 插件怎么用 `_HQ.blend`

Blender 3.6 里用 mmd_tools 导入 PMX。侧栏 **MMD** 页签有个「剑星游戏材质」面板，点 **换上游戏原始材质**，插件做四件事：

1. **扫描存档**：
   - 找 `<存档目录>\<任意角色>\blend\<任意服装包>\*_HQ.blend`，每个文件只读材质名，不加载内容。
   - 结果按文件大小和修改时间缓存在 `%APPDATA%\Blender Foundation\Blender\3.6\config\stellarblade_game_materials_index.json`。
     新增或改过的文件，下次点按钮时自动重读，不用重启 Blender。
   - 「重新扫描存档」会全部重读一遍。
2. **按名字配对**：
   - PMX 的材质名去掉 `_gloss`、`_burst`、`_nude` 后缀，再去和 `_HQ.blend` 里的材质名比。这几个后缀分别来自清漆拆分和爆衣插件。
   - 同名材质最多的那份是这个模型的「主 .blend」。头、头发、眼睛每套衣服都有，所以起决定作用的是衣服自己的材质。
   - 打平时，服装包文件夹名出现在模型名（或英文名）里的优先；再打平就取文件夹顺序靠前的（角色名字母序，Eve 在 Fiona 前）。
   - 几层衣服叠在一个 PMX 里的模型（`pmx_layers.py` 做的），每层各找各的主 .blend。
3. **搬节点**：
   - 从选中的 `_HQ.blend` 追加同名材质，把它的节点网络复制进 PMX 的材质。新节点名都以 `sbhq_` 开头，单独接一个输出节点。
   - mmd_tools 原来的节点和设置一个不动。
   - 次表面散射半径乘以「模型高度 ÷ 172」：存档是厘米，PMX 导入后大约是米。
   - 追加进来的临时材质和库条目随后删掉。
4. **切换**：
   - 「着色」在「游戏材质 / MMD 着色」之间切换。切的是哪个输出节点生效，以及各自的混合、阴影模式。
   - 法线、粗糙度、金属度、清漆、绒毛光泽、自发光都有滑块，是乘在游戏原值上的倍数。
   - 「去掉游戏材质」删掉所有 `sbhq_` 节点，回到导入时的样子。
   - 再导出 PMX 不受影响：mmd_tools 只读它自己的节点和材质属性。

## 5. 要不要放在指定目录

要。默认只认这个结构：

```
E:\game_export\StellarBlade\<角色>\blend\<服装包>\<任意名字>_HQ.blend
```

- 层级固定：`<角色>\blend\<服装包>\`，文件直接放在服装包文件夹里，多套一层就找不到。文件名必须以 `_HQ.blend` 结尾。
- 角色和服装包叫什么都行，配对靠材质名，不靠文件夹名。文件夹名只在打平时起作用。
- 我们的脚本直接把 `_HQ.blend` 写在这个位置，平时不用挪。
- 想放别处，面板展开「高级」：
  - **存档目录**：换一个根目录，下面的层级要保持一样。适合整个存档搬到别的盘或别的电脑。
  - **指定 .blend**：直接选一个 `_HQ.blend`，不扫描存档，放哪里都行。适合临时用、或者自动配错了的时候。

## 6. 注意事项

| 现象 / 情况 | 原因 | 办法 |
|---|---|---|
| 「存档里没找到这个模型的高清 .blend」 | 没有哪个 `_HQ.blend` 里有同名材质 | 看存档目录和层级对不对、文件名是不是 `_HQ.blend` 结尾；点「重新扫描存档」 |
| 只换上一部分（比如只有头和头发） | 这套衣服还没有自己的 `_HQ.blend`，配到了别的衣服（只共用头部材质） | 按第 3 节给这套衣服做高清版（例：Vindictus Fiona 做之前 13/22，做了以后 22/22） |
| 配到了别的衣服的 .blend | 打平了，按文件夹顺序取了靠前的 | 用「指定 .blend」 |
| 粉色、缺贴图 | `_HQ.blend` 用相对路径读旁边的 `textures\`，只拷了 .blend、没拷文件夹 | 整个服装包文件夹一起搬 |
| 场景拷到别的电脑缺贴图 | 换上以后，贴图仍然从存档里读，没有复制进你的场景 | 「文件 › 外部数据 › 打包资源」，或者那台电脑也放一份存档 |
| 有的材质没换上 | 在 PMXEditor 里改过材质名 | 用导出时的原名 |
| XPS 不行 | 导出 XPS 时材质名会改掉 | 用 PMX |
| 别的电脑上插件报「找不到 game_materials_blender.py」 | 插件的核心在仓库里 | 那台电脑也放一份仓库，或者设环境变量 `STELLARBLADE_SCRIPTS` 指到 `scripts\stellarblade` |
| 更新了插件，效果没变 | 核心代码每次启动 Blender 只读一次 | 重启 Blender，或者在偏好设置里关掉再打开插件 |

## 7. 新做一套的顺序

1. 照常导出这套衣服（Blender / XPS / PMX），归档到 `E:\game_export\StellarBlade\`。
2. 做高清版（第 3 节的命令），`_HQ.blend` 会出现在存档 .blend 旁边。
3. Blender 里导入 PMX，点「换上游戏原始材质」，面板报告里「没找到」应该是 0。
