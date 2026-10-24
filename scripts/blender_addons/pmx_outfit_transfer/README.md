# PMX Outfit Transfer —— 把一个 PMX 的衣服贴身穿到另一个 PMX 上（Blender 插件）

给 PMX 模型之间**换衣服、拼衣服**用：选一个模型的衣服材质，连同它们的骨骼、刚体、关节、材质和贴图，搬到另一个模型上，
按目标的裸体形状贴身拟合，写出一个新的 PMX。两套衣服的刚体互不碰撞，原来的两个文件都不动。

```
scripts/blender_addons/pmx_outfit_transfer/
  __init__.py   Blender 插件入口：侧栏 MMD 页签 → 换装（服装移植）
  core.py       算法：骨骼重定向 + 身体形状场 + 按面坐标系贴合；骨骼/刚体/关节/材质/贴图搬运；碰撞组隔离
  cli.py        命令行：blender -b --factory-startup --python cli.py -- 源.pmx 目标.pmx 输出.pmx [选项]
```

2026-10-24 第一个用例：Luf g05（女神装）的整套衣服 → Inase a08 full 的裸体，成品在
`E:\game_export\RiseOfEros\_混搭\a08_full_穿g05衣服\`。
一步一步的用法（面板、挑零件、拼几套、常见问题）见 [docs/pmx-outfit-transfer-usage.md](../../../docs/pmx-outfit-transfer-usage.md)，
做法、数字和坑见 [docs/pmx-outfit-transfer.md](../../../docs/pmx-outfit-transfer.md)。

## 安装

和仓库里其他插件一样用目录联接装进 Blender 3.6，本机已装好：

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\3.6\scripts\addons\pmx_outfit_transfer" `
         -Target "E:\code\othercode\ripper_tpose\scripts\blender_addons\pmx_outfit_transfer"
```

「编辑 → 偏好设置 → 插件」里搜 `PMX Outfit Transfer` 勾选（已经开着的 Blender 要重启或 F3「Reload Scripts」）。
需要 mmd_tools（读写 PMX、把结果导入场景）。

## 用法

面板在 3D 视图侧栏（`N`）的 **MMD** 页签，「换装（服装移植）」：

1. **衣服来自**：提供衣服的 PMX；**穿到**：目标 PMX；**输出 PMX** 留空就在目标旁边新建「`<目标>_穿<前缀>衣服`」文件夹。不会覆盖已有文件。
2. 点「**读取源模型的材质**」：列出源的全部材质，身体 / 脸 / 头发 / 眼睛 / 武器默认不勾，其余默认勾上；勾选要搬的。
   同时认出两边的身体材质（ROE：源用 `*_nk_body`，目标用 `*_nk_body_nude`），认错了手改。
3. 选项（默认就是 g05 → a08 用的）：
   - **按身体形状贴身拟合**：关掉只按骨骼位置重定向；
   - **贴身距离 / 远离距离**：离源身体 2 cm 以内的衣服完全跟着身体形状走，12 cm 以外只跟骨骼（光环、法杖、长披帛的末端），中间渐变；
   - **按骨骼方向旋转**：两个模型休息姿势不同（T 形 / A 形）时需要，相同时没影响；
   - **拆分材质**：「按挂的骨头」一根骨头一个材质（`g05_body2_Leaf_L`、`g05_body1_Riband_M`……），挑零件方便；「按连通块」每块布一个；「不拆」原样；
   - **两套衣服的刚体互不碰撞**、**新衣服碰目标的身体**；
   - **加进「衣服非表示」**：full 版拉这个表情时新衣服也一起藏。默认不加：拉「衣服非表示」= 脱掉目标自己的衣服、留下新衣服，正好是「新衣服穿在裸体上」。
4. 点「**换装**」。十几秒后写出 PMX，默认再用 mmd_tools 导入场景。
5. 之后在 Blender 或 PMXEditor 里挑零件：不要的材质删掉；要调位置就改那块布的顶点。

命令行（批处理、不开 Blender 界面）：

```powershell
& "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" -b --factory-startup --python scripts\blender_addons\pmx_outfit_transfer\cli.py -- `
    源.pmx 目标.pmx 输出.pmx [--materials "a,b"] [--donor-body M] [--target-body M] [--no-fit] [--near 2] [--far 12] `
    [--no-rotation] [--split bone|island|none] [--prefix g05] [--no-isolate] [--no-body-collision] [--hide-morph 衣服非表示_材質]
```

普通 Python（装了 numpy）也能跑 `python cli.py ...`，最近点搜索用 numpy 暴力算，慢一些。

## 原理

1. **骨骼重定向**：衣服每个顶点按它的蒙皮权重，当作挂在目标同名骨头的休息位置上（线性混合蒙皮，每根骨头一个平移 + 可选的方向旋转）。
   目标没有的骨头：先在同一个父骨下找 5 cm 以内、没被占用的骨头按位置配（ROE 各家族胸骨名字不同：`chest_L02` / `Breast_L02` / `OPAI_L02`），
   配不上的连同到最近已配骨头之间的父链一起搬过来；两边都挂着物理、名字还一样的（两条都叫 `Skirt_L_01` 的裙链）改名搬。
2. **身体形状场**：源的身体（衣服是在它上面做的）同样重定向后，每个顶点找目标裸体上最近的点，位移场平滑 6 遍去掉拓扑噪声，再吸回目标表面。
   得到「源身体变成目标身材」的网格，拓扑不变。
3. **贴合**：在**源模型自己的空间**里，每个衣服顶点找源身体最近的面，记下在这个面坐标系里的偏移；面变到目标身材后，按同样的偏移放回去
   （和 Blender 的 Surface Deform 一个道理）。离身体远的部分按距离渐变回第 1 步的结果。
   偏移一定要在源的空间量：第 1 步之后衣服和皮肤可能已经错开（大腿环挂 `左足D`，皮肤挂 `ThighTwist`，两根骨头在两个模型里的相对位置不同）。
4. **物理**：衣服骨上的刚体、关节一起搬，位置按第 1–3 步同样移动；一头挂在源身体刚体上的关节改挂目标同名骨头的刚体（g05 胸前的吊坠挂到 a08 的胸部刚体上）。
   碰撞组：新衣服的动态刚体换到目标没用的组，目标的衣服刚体屏蔽这些组，新衣服只碰目标的身体碰撞体。
5. 材质、贴图真复制到输出文件夹的 `textures\`；新骨骼放进显示枠「`<前缀>衣服`」。

## 做不了 / 要自己来的

- 两边都要有裸体材质才能贴身拟合，没有就只按骨骼走（会提示）。
- 衣服的权重照搬源的骨头名，不会改成目标身体的权重。full 版胸带下面的身体和胸带摆动比例不一样的问题照旧，挑完零件后用
  `scripts/riseoferos/pmx_body_follows_cups.py` + `pmx_body_cover_cups.py` 处理。
- 源的表情（材质表情、顶点表情）不搬。
- IK 骨不搬 IK 设置。
- 远离身体的东西（法杖、光环）只按骨骼放，位置要自己看。
