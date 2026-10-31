# PMX 换头插件怎么用（pmx_head_swap）

给一个 PMX 模型换上另一个 PMX 模型的头：脸、眼睛、睫毛、眉毛、头发，连同头的骨骼、头发物理、贴图和表情一起过去，
脖子那一圈顶点对顶点焊上，法线、权重、肤色在接缝处做成连续的，写出一个新的 PMX。两个原文件不动。

原理和数字见 [pmx-head-swap.md](pmx-head-swap.md)，插件目录：`scripts/blender_addons/pmx_head_swap/`。
换衣服用另一个插件：[pmx-outfit-transfer-usage.md](pmx-outfit-transfer-usage.md)。

## 一、安装

本机已经装好（目录联接），Blender 3.6 里也已经勾上了（2026-10-31），直接看第二节。
别的机器这样装（两个插件都要，换头插件借用换衣插件的底层代码）：

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\3.6\scripts\addons\pmx_outfit_transfer" `
         -Target "E:\code\othercode\ripper_tpose\scripts\blender_addons\pmx_outfit_transfer"
New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\3.6\scripts\addons\pmx_head_swap" `
         -Target "E:\code\othercode\ripper_tpose\scripts\blender_addons\pmx_head_swap"
```

1. 打开 Blender 3.6（已经开着的要重启，或 F3 搜「Reload Scripts」）。
2. 编辑 → 偏好设置 → 插件，搜 `PMX Head Swap`，勾上（`PMX Outfit Transfer` 不必勾，装着就行）。
3. 同时要开着 **mmd_tools**。

## 二、面板在哪

3D 视图按 `N` 拉出侧栏 → **MMD** 页签 → 「**换头**」面板：

```
┌ 换头 ───────────────────────────────────────────┐
│ 头来自     [ E:\...\pc_a08_hd_full_裙子碰撞修正.pmx ]              │
│ 换到       [ E:\...\pc_g05_hd_full_裙子碰撞修正_瞳孔修正.pmx ]     │
│ 输出 PMX   [                                   ]  ← 留空自动     │
│ [ 读取源模型的材质 ]                                            │
│ ☐ pc_a01_nk_body   ☐ pc_a08_hd_body1   ☑ pc_a_nk_hair           │
│ ☑ pc_a_nk_face     ☑ eye_portable      ☑ lash  ☑ brow           │
│ ☑ eye_overlay      ☐ wp_a08_l  …                                │
│ 目标去掉的材质 [ pc_g_nk_face, pc_g_nk_face_nude, eye_portable, lash, brow, eye_overlay, pc_g_nk_hair ] │
│ ┌ 选项 ─────────────────────────┐                               │
│ │ 脖子过渡 cm [4.0]              │                               │
│ │ 肤色 [匹配 + 接缝渐变 ▾]       │                               │
│ │ 头的缩放 [1.000]               │                               │
│ │ 前缀 [a08]                     │                               │
│ │ ☑ 做完导入场景                 │                               │
│ └───────────────────────────────┘                               │
│ [ 换头 ]                                                        │
│ 写出 pc_g05_hd_full_换a08头.pmx：接缝 1:1，14 根新骨，10 刚体，61 表情 │
└─────────────────────────────────────────────────┘
```

## 三、一步一步（例子：g05 换上 a08 的头）

1. **头来自**：提供头的 PMX。例子：`E:\game_export\RiseOfEros\Inase\pmx\pc_a08_hd_full\pc_a08_hd_full_裙子碰撞修正.pmx`。
   有修正版就用修正版（和头没关系的修正也无妨，只取头）。
2. **换到**：要换头的 PMX，身体留下。例子：`E:\game_export\RiseOfEros\Luf\pmx\pc_g05_hd_full\pc_g05_hd_full_裙子碰撞修正_瞳孔修正.pmx`。
   用 full 版最好：有裸体副本，「衣服非表示」换完头照常能用。
3. **输出 PMX**：留空就在目标旁边新建 `<目标文件名>_换<前缀>头\`，PMX 和 `textures\` 都在里面；不覆盖已有文件。
4. 点「**读取源模型的材质**」：
   - 列表里脸、眼睛、睫毛、眉毛、头发默认**勾上**（按名字认：`_nk_face`、`eye_`、`lash`、`brow`、`eye_overlay`、`_nk_hair`），
     身体、衣服、武器不勾。头饰（发簪、耳环）如果是单独材质，想要就勾；
   - 「目标去掉的材质」自动填目标自己的同类材质（含 `_nude` 副本）。目标的头饰在衣服材质里的话不会被去掉，之后自己删。
5. 选项（默认就是例子用的）：
   - **脖子过渡 cm**：头的脖子在接缝以上这段里逐渐变成身体那一圈的形状，默认 4。两家脖子粗细差得多就加大（6–8），差得少可以减到 2–3；
   - **肤色**：「匹配 + 接缝渐变」（默认）；两家肤色明显不同又想保留头原来的肤色时选「不动」（接缝会有色差）；
   - **头的缩放**：以脖子那一圈为中心缩放整个头，默认 1。换到明显更高大 / 娇小的身体上时调；
   - **前缀**：新骨骼的显示枠、重名材质用，留空从源文件名取（`pc_a08_…` → `a08`）。
6. 点「**换头**」。几秒钟。面板下面显示接缝配对方式（`1:1` = 两圈顶点数一样、一一对应；`projected` = 顶点数不同、投影加切边）和数量。
7. 默认导入场景。把衣服和头发暂时隐藏，转到脖子看一圈：正面、侧面、后面、仰视。

成品里有什么：
- 目标的身体、衣服、物理、非脸部表情都原样；
- 源的脸、眼睛、睫毛、眉毛、头发（材质名不变；和目标重名的加前缀），源的 58 个脸部表情，头发物理（换到目标没用的碰撞组，只碰身体）；
- 目标 `頭` 下面同名的骨头（両目、左目、右目、脸骨）挪到了源的位置，源独有的头发骨在显示枠「`<前缀>头`」里；
- `textures\` 里是两边贴图的实拷贝，脸贴图是调过肤色的 `*_toned.png`。

## 四、换完还要做的

- **头饰 / 旧头的零件**：目标头上原来戴的东西如果在衣服材质里（g05 的光环在 `pc_g05_hd_body 2` 里），会留在新头上。
  不要就在 PMXEditor 或 Blender 里按材质 / 按连通块删。
- **胸部表情、眼睛跟踪**照常；源模型有 `両目` 之类标准骨的话 MMD 的眼睛跟踪能用。
- **头发碰到衣领**：头发只碰身体碰撞体，不碰衣服刚体。想让它碰衣服就在 PMXEditor 里把头发刚体的非碰撞组改一下。

## 五、命令行（不开 Blender 界面）

```powershell
& "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" -b --factory-startup `
    --python E:\code\othercode\ripper_tpose\scripts\blender_addons\pmx_head_swap\cli.py -- `
    头.pmx 身体.pmx 输出.pmx `
    [--head "pc_a_nk_face,eye_portable,lash,brow,eye_overlay,pc_a_nk_hair"] [--remove "pc_g_nk_face,pc_g_nk_face_nude,..."] `
    [--blend 4] [--tone seam|whole|none] [--scale 1.0] [--prefix a08]
```

不写 `--head` / `--remove` 就是面板里默认的那些。装了 numpy 和 Pillow 的普通 Python 也能 `python cli.py …`（几秒钟）。最后一行 `REPORT {...}` 是 JSON 报告。

## 六、常见问题

- **「both models need the bones 首 and 頭」**：不是 MMD 标准骨名的模型先改骨名（首、頭 至少要有）。
- **「no neck ring found」**：脸网格在脖子根没有开放边（脸只到下巴、脖子长在身体上的模型）。这种还没处理，接缝在下巴那一圈。
- **「no body material (*_nk_body) in the target」**：目标的身体材质不叫 `*_nk_body`。目前按 ROE 的命名找身体，别的游戏的模型先把身体材质改成这个名字。
- **脖子根有一圈颜色不一样**：看面板有没有「skin tone … texture left alone」的警告——身体材质没有贴图文件时肤色匹配会跳过。
  或者选了「不动」。
- **脖子根形状有棱**：加大「脖子过渡 cm」。
- **头看着大 / 小**：调「头的缩放」。
- **头发穿过肩膀**：头发不参与脖子过渡，位置按脖子那一圈刚性摆的；长发碰肩膀处自己挪一下，或者在 PMXEditor 里把头发刚体改碰衣服。
- **源的材质表情（换眼睛贴图之类）没了**：不搬，只搬顶点表情、UV 表情、骨骼表情和它们的组。

## 七、它怎么做的（一句话版）

头按脖子那一圈刚性摆好 → 接缝顶点直接挪到身体对应顶点上 → 位移在脖子上 4 cm 里衰减、在脸上平滑 → 接缝处用身体的法线和权重 →
脸贴图按接缝两侧肤色乘增益、剩余差别烘成渐变 → 旧头删掉、新头的骨骼 / 物理 / 表情接上。细节见 [pmx-head-swap.md](pmx-head-swap.md)。
