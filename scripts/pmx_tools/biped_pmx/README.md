# 任意游戏的 .blend → PMX / XPS（Biped 骨骼映射）

仓库里的 PMX 流程（Stellar Blade 的 `export_pmx_blender.py` 加 Rise of Eros 的转换器：Convert_to_MMD5 建 MMD 骨骼、IK 和身体碰撞体，
mmd_cloth_physics 做头发 / 布料链，blender2xps 把节点算出的颜色烘成贴图，mmd_tools 按 12.5 倍写 PMX）和 blender2xps 的 XPS 导出，
都只认 3ds Max Biped 的骨骼名（`Bip001 Pelvis`、`Bip001 L UpperArm` ……）。这里把「游戏骨骼 → Biped」做成一个个**骨骼映射**，
新游戏只要写一个映射文件，就能用同一条流程出 PMX 和 XPS。

```powershell
# PMX（要用户的 Blender 3.6 插件：mmd_tools、Convert_to_MMD5、mmd_cloth_physics，所以不加 --factory-startup）
& "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" -b <模型>.blend --python scripts\pmx_tools\biped_pmx\export_pmx_blender.py -- `
    --rig mho --out <输出目录> --name <名字> [--model-name <MMD 里的名字>] [--comment <说明>] `
    [--leave-out <正则>] [--hair-chains auto|off] [--straighten-fingers auto|on|off]
# XPS
& "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" -b <模型>.blend --factory-startup --python scripts\pmx_tools\biped_pmx\export_xps_blender.py -- `
    --rig mho --out <输出目录> --name <名字> [--leave-out <正则>]
```

输入的 .blend 要是米制、Z 朝上、角色面朝 -Y（`scripts/marvelheroes`、`scripts/marvelrivals`、`scripts/re_engine` 的建模脚本都是这样存的）。
PMX 打印 `BIPED_PMX={json}`，写 `<out>\<名字>.pmx`、`textures\`、`<名字>_converted.blend`；XPS 打印 `BIPED_XPS={json}`。
**注意**：PMX 导出开始时会把 `<out>` 整个清空（避免旧贴图残留），检查视频之类的别放在里面，或者导完再生成。

## 骨骼映射（`rigs\`）

| 映射 | 用于 | 要点 |
|---|---|---|
| `mho` | Marvel Heroes Omega（`g_*`） | 腿挂在根骨上、脊椎之间夹着 `*_offset` 空骨：骨盆改成枢纽（脊椎和两条腿都挂上去），空骨去掉；一根 `g_breast` 带两边胸部，按左右拆成 `L / R Pectoral` |
| `ue_mannequin` | Marvel Rivals 等 UE4 / UE5 小白人命名 | `spine_01..05` 取头、中、尾三根做 Spine / Spine1 / Spine2；`*_Fix_*_Jnt` 修正骨、`twist`、掌骨、武器 / 挂点都当肢体辅助骨（不做布料）；分开的脚趾骨（`bigtoe / index / middle / ring / pinky _phalange_l/r`）并进 `ball_l/r`；胸骨跳过 `*_end` 标记骨 |
| `re_engine` | 生化危机 2 / 3 重制版（RE Engine，经 RE Mesh Editor） | `hips` 改成枢纽，`COG`、`Null_Offset` 去掉；头下面 100 多根表情骨并进头（不保留表情）；没有胸骨，用胸肌辅助骨 `pecA_muscle` 做胸部物理；无名指 / 小指的 `_0` 是掌骨 |
| `rigify_twk` | Rigify 风格、变形链由 `.twk` 骨组成（HS2 的 Venom 移植） | 扭转骨夹在链中间（上臂 → 扭转 → 前臂），按 Biped 扭转辅助骨命名；舌头、身体器官的骨链标成辅助骨 |

一个映射文件要提供：

- `to_biped(arm, meshes)`：改名（顶点组跟着改）并整理骨骼树，返回报告；常用操作在 `rigtools.py`：
  - `rename_bones`：改名；
  - `reparent`：换父骨，骨骼位置不动；
  - `collapse`：去掉中间的空骨，子骨挂到它的父骨；
  - `drop_unweighted`：删掉没有皮肤、子孙也没有皮肤的骨，比如 IK、挂点；
  - `merge_into`：把一组骨的权重合进另一根骨再删掉，比如表情骨；
  - `split_bone_by_side`：一根骨带两边胸部时，按左右拆成两根，中间 2 cm 过渡。
- `BUST`：两根胸骨的名字，各配一个胸部物理球。
- `LIMB_HELPER`：跟着肢体走、绝不当布料的骨，写成正则片段。
- `EYE_MATERIAL`：眼球材质的正则，用来生成眼睛骨 左目 / 右目；`None` 表示不生成。
- `HAIR_MATERIAL`：头发材质的正则。没有自己骨骼的头发会生成发链。
- `COMMENT`：PMX 的默认说明。

## 流程里另外做的事（和坑）

1. **UV 不在 0–1 的面先挪回 0–1**（`wrap_uv_tiles`，PMX 和 XPS 都做）：烘焙只填 0–1 这一格，
   HS2 Venom 的身体、手臂、腿用 1–5 号 UV 格（UDIM 式），烘出来全透明，材质被当成透明外壳藏掉，跳舞视频里只剩头。
   贴图本来就是重复的，挪整数格颜色不变。NARAKA 遇到过一次（`scripts/naraka`），这里是通用流程漏了。
2. **手指拉直**（`--straighten-fingers`，默认 `auto`）：MMD 动作默认手指伸直。绑定时手指是弯的，一握拳就会握进掌心。
   `auto` 在关节平均弯曲超过 15° 时拉直，逐节转，皮肤按权重份额跟着转（`scripts/vindictus/limbs.py`，和 Vindictus 的 UE 身体同一套做法）。
3. 和 Elden Ring 的版本一样：
   - 只给不透明材质用的贴图，在 PMX 里把 alpha 填满（MMD 会乘贴图 alpha）；
   - 眼睛骨的枢轴挪到眼球球心；
   - 胸部物理用 Stellar Blade 的设置（`BUST`）。
4. 每次导出都会打印 `distortion`：拉伸和撕裂的边数。只看这个数不够，**一定要跑一遍舞蹈**看手和脸（见下）。

## 验证

```powershell
& "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" --background --python scripts\riseoferos\render_pmx_dance.py -- `
    <模型>.pmx "E:\Downloads\mmd\0.meeynara手势舞2025.2.14by小王动画\适配瓦雷莎.vmd" "<同目录的 WAV>" <输出>.mp4 0 full mmd
```

这次在舞蹈里查出了 4 个问题，都是静止图看不出来的：

- **Marvel Heroes 手指甩出尖刺**：骨骼旋转约定写错了，修在 `scripts/marvelheroes/write_psk.py`。
- **Jill 的脸是黑的**：RE 贴图的 alpha 是金属度，被当成了透明度。修在 `scripts/re_engine/build_blend.py`，改成 `CHANNEL_PACKED`。
- **HS2 Venom 只剩头**：UV 分在别的格里，见上面第 1 条。
- **HS2 Venom 的爪子**：张手时像一根根棍子，其实是爪子本来就长（指尖离手腕 45 cm），不是错误。

后来 Marvel Rivals 的 She-Venom（#6188，第一个走 `ue_mannequin` 的 PMX）从导出报告里又查出两个，舞蹈视频里不明显：

- **脚趾成了布料**：Venom 每只脚有 5 根脚趾、每根 2 节，挂在 `ball_*`（足先EX）下面。布料识别把这 5 条短链当成一片「外套」，
  加了 20 个物理刚体，MMD 里脚趾会甩。现在映射里把脚趾骨的权重并进 `ball_*`（MMD 只有一根脚尖骨）。
  看报告的 `physics.garments`：身体模型这里应该是空的，出现名字里带 `phalange`、`toe` 的就是这种情况。
- **右胸没有物理**：胸骨是 `L/R_Chest_Muscle_01_Jnt`，每根后面还挂着一个没有皮肤的 `*_end` 标记骨，两者都匹配胸骨正则。
  按集合的随机顺序挑，右边挑中了 `_end`（报告 `bust_physics` 写「no skin」）。现在按名字排序，并跳过 `_end`。
