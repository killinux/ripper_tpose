# Marvel Rivals（UE 5.3）mod → 高清 .blend + PMX + XPS

Nexus 上的 Marvel Rivals 皮肤 mod 一般是 `<名字>_9999999_P.pak / .utoc / .ucas` 三个文件（IoStore 容器），有的压缩包里按变体分了很多文件夹
（披风有 / 无、体型 L–XXXL……）。`export_mod.py` 一个变体出一套。

```powershell
python -I scripts\marvelrivals\export_mod.py "<mod 的 .zip / .rar 或文件夹>" --list          # 每个变体里有哪些资源
python -I scripts\marvelrivals\export_mod.py "<mod>"                                          # 全部变体，blend + pmx + xps
python -I scripts\marvelrivals\export_mod.py "<mod>" --variant "Cape off" --formats blend
```

| 参数 | 默认 | 作用 |
|---|---|---|
| `--name` | 从 Nexus 文件名取 | 名字前缀，后面接 mod 编号和变体文件夹名 |
| `--out-root` | `E:\game_export\MarvelRivals` | 输出到 `<out-root>\<英雄>\{blend,pmx,xps}\<名字>\`，英雄按角色编号（1035 Venom、1015 Storm……） |
| `--mesh` | `lobby` | 用大厅模型 `SK_*_Lobby`（英雄展示用，细节更多）；`game` 用局内模型 |
| `--variant` | 全部 | 只导路径匹配这个正则的变体 |
| `--formats` | `blend,pmx,xps` | |
| `--usmap <文件>` | `_mappings` 里最新的 | 映射文件。默认按顺序找 `SkinStudio_1.0.6-Marvel.usmap`、`S1_1_release-Marvel.usmap`（见坑 2） |
| `--extra-textures <目录>` | 无 | 游戏给不出的贴图（映射文件过期，见坑 2）按名字到这个目录里找，可以写多个。例如别的 mod 里带着的游戏原版贴图：HS2 的 Venom 移植带着 `T_1035001_Head_D / N / ORM`。文件名后面带数字编号（`T_1035001_Head_D_3133077305.png`）也认 |
| `--colour "<正则>=r,g,b[,粗糙度]"` | 无 | 还是没有颜色贴图的材质用这个颜色（sRGB 0–1）代替灰色，可以写多个。节点上标「替身颜色」 |

## 需要什么

- CUE4Parse 命令行 `E:\tools\cue4parse_cli_ff7\cue4parse.exe`。
- 游戏的映射文件（.usmap）和 AES 密钥，都是公开的，放在仓库外的 `E:\tools\marvelrivals\`，来源见那里的 `README.txt`：
  - `_mappings\SkinStudio_1.0.6-Marvel.usmap`：默认用这个。从 Nexus #13477 Variant Skin Studio 的 SkinStudio App 1.0.6 里
    只取出 `app\blender\Marvel.usmap`（2026-09-24），SHA256 和它自带的 `SHA256SUMS.txt` 对得上，包里别的东西不运行；
  - `_mappings\S1_1_release-Marvel.usmap`：github.com/picarica/Marvel-modding-guide 的第 1 赛季版，只读得出 mod 自己的资源。
- 游戏的 `global.utoc / .ucas`：IoStore 包没有它里面的脚本对象表，一个都读不出来。
  脚本先找已装好的游戏（各 Steam 库），没装完时从 Steam 的下载目录只读取这两个文件。
- mod 没带的东西都要从**装好的游戏**里拿，比如基础材质、它改的那套皮肤的贴图。
  游戏的容器用硬链接放进工作目录（`E:\marvelrivals_work`，要和游戏在同一个盘），游戏目录不动。

## 每一步

1. 解压 mod（zip 用 zipfile，rar 用 7z）到新的工作目录。
2. 每个变体：
   - 建一个舞台目录：游戏容器的硬链接，加上 mod 的三个文件，mod 文件改名加 `zzmod_` 前缀，`_P` 结尾优先级最高；
   - 列出 mod 自己的包，找出骨骼模型。
3. 模型 → PSK（UE 坐标，左右按 UE Viewer 的方式镜像），再导一份 JSON 拿到材质槽。
4. 每个材质槽：
   - 材质实例连同它的父材质一代一代导 JSON，参数子级覆盖父级；
   - 父材质每一代用一次命令行调用，因为每次调用都要挂载整个游戏，一代代批量调；
   - 参数里提到的贴图全部导成 PNG。
5. `build_blend.py`（Blender 3.6）建材质：
   - `BaseColor` → 颜色；
   - `Normal` → 法线，UE 法线要把绿通道翻转；
   - `ORM`：R 是 AO（乘进颜色），G 是粗糙度，B 是金属度；
   - `SpecularTexture` → 高光；
   - 名字里有 Emissive 的 → 自发光。

   UE 厘米换成米。按两只脚尖的方向转到面朝 -Y，并应用变换。最后渲预览图。
6. `scripts\pmx_tools\biped_pmx`（骨骼映射 `ue_mannequin`）→ PMX 和 XPS。

## 坑

1. **容器头说「加密」，目录索引却是明文**。Nexus #10647 黑寡妇是这样：数据块确实加密，但索引没加密，长度也不是 16 的倍数。
   CUE4Parse 照着标志去解密索引，报 `AES-ECB input length must be a multiple of 16 bytes`；把标志去掉能列出文件，可数据块又被当明文读，
   报 `Could not load standard asset`。`fix_utoc.py` 在**副本**上把索引补零到 16 的倍数，用游戏密钥按引擎的方式加密回去，
   再改 `DirectoryIndexSize`。容器本来正常就原样不动。
2. **映射文件过期**。公开的 usmap 是第 1 赛季的：
   - mod 的资源是作者当时打包的，用它读得出来；
   - 游戏本体的资源是后来的版本编译的，材质实例只读出 `Parent` 等两三个属性，贴图参数全丢，贴图也报 `Failed to decode texture mip -1`。

   **2026-11-21 解决**：换成 SkinStudio App 1.0.6 带的 `Marvel.usmap`（见「需要什么」），游戏 11-15 装的版本：
   - 材质实例的参数、父材质的混合模式都读得出来，游戏原版贴图也能解码；
   - She-Venom #6188 去掉替身参数重导，身体、头、装饰全是游戏原版贴图。
     前后对比图：`E:\game_export\MarvelRivals\Venom\blend\She-Venom_6188\材质对比_替身版vs游戏原版.jpg`。

   游戏以后大更新，映射文件又可能过期，症状同上。到时候找新的 usmap 放进 `_mappings`，用 `--usmap` 指定，或者加进
   `export_mod.py` 的 `USMAPS` 列表最前面。

   材质实例读不出贴图参数时，脚本还会按名字到同一套皮肤的目录里找贴图：`MI_1035001_Body` 对应 `T_1035001_Body_D / _N / _ORM / _S`。
   映射文件过期时这一步只能**找到**贴图，解码还是要新的映射文件。

   **以前等新映射文件时的替身做法**（2026-11-15，She-Venom #6188，用户说「没有材质」；11-21 已经用游戏原版重导，
   替身版备份在 `E:\game_export\MarvelRivals\_meta\backup_替身版_20261121\`）：

   - 这个 mod 只带了短上衣和丁字裤（`MI_Mommy`），头、身体、腿用的是游戏原版 Venom 的材质 `MI_1035001_Head / Body / Equip`，都是灰的；
   - **头**：HS2 那个 Venom 移植版（`E:\game_export\HoneySelect2\Venom`）的头和 She-Venom 的头面数完全一样（46,462），
     是同一个游戏网格，它带的 `T_1035001_Head_*` 就是游戏原版贴图，用 `--extra-textures` 直接套上；
   - **身体和腿**：移植版的身体是另做的网格，贴图对不上，用 `--colour` 给深藏青黑色加光泽。颜色对照的是 mod 作者在 Nexus 的预览图；
   - 先给每个材质刷一种纯色渲一张图，看清楚哪个材质盖哪里，再决定用什么补。

   ```powershell
   python -I scripts\marvelrivals\export_mod.py "<She-Venom 的 .rar>" `
       --extra-textures "E:\game_export\HoneySelect2\Venom\blend\Venom_MarvelRivals_Fouetty\textures" `
       --colour "^MI_1035001_(Body|Equip)$=0.07,0.075,0.10,0.3"
   ```

   报告里每个材质记着 `from_extra`（哪张贴图是从别处来的）和 `flat`（替身颜色）。拿到新映射文件后，去掉这两个参数重新导出，就是游戏原版。
3. 没有自发光贴图的轮廓光、特效外壳，比如 `*_Rim_HeroDetails`、父材质 `M_RimOnly`，在游戏里由专门的着色器画在身体外面。
   当普通表面会把身体整个盖住，所以留在文件里，设成全透明。
4. Marvel Rivals 每个材质实例都覆盖了 `OpacityMaskClipValue`，这不代表材质是镂空的。只有混合模式写明 Masked，
   或者头发类材质的颜色贴图里确实有透明像素时，才按 alpha 裁剪。否则不透明身体的贴图 alpha 会裁出洞。
5. 只有贴图、没有模型的变体会跳过，并写进报告。比如 #6269 Stormy、#4249 的 `_Anti-Venom` 文件夹，它们换的是游戏原版模型的贴图。
6. **贴图分错角色**（2026-11-21，新映射文件第一次把参数全读出来时）。Venom 的材质实例里，
   `FX - ChangeColor - NoiseTex`（`T_1035103_Noise_26_001_D`，一张绿黄噪声）、`FlowMapNormal`、`NormalMask_Tex`
   排在 `BaseColor / Normal / ORM` 前面。`build_blend.py` 原来按「先到先得」，还拿贴图名的后缀 `_D / _N / _M` 判断，
   结果整个身体刷成绿黄噪声。现在分两轮：
   - 先看参数名（`BaseColor`、`Normal`、`ORM`……）；
   - 还空着的角色才看贴图名后缀，而且特效 / 细节参数（名字里有 FX、Noise、Flow、Growth、Mask_Tex，或者以数字编号开头）不参与。
7. **混合模式读出来以后，所有身体材质都是 Masked**（`M_Common_Body`、`M_1035001_Skin_1035`，给溶解特效用）。
   颜色贴图的 alpha 其实全是 255。现在只有混合模式是 Masked、**并且** alpha 里真有透明像素时才按 alpha 裁剪。
