# PMX 表情移植插件怎么用（pmx_expression_transfer）

把一个 PMX 模型的表情（眨眼、口型、眉毛……）移到另一个 PMX 模型的脸上，写出一个新的 PMX。两张脸的网格不用一样，
不同游戏、不同顶点数都行。表情写成目标的顶点表情，名字和面板跟来源一样，MMD 的舞蹈 VMD 按名字就能驱动。两个原文件不动。

原理和数字见 [pmx-expression-transfer.md](pmx-expression-transfer.md)，插件目录：`scripts/blender_addons/pmx_expression_transfer/`。
同一系列：换衣服 [pmx-outfit-transfer-usage.md](pmx-outfit-transfer-usage.md)、换头 [pmx-head-swap-usage.md](pmx-head-swap-usage.md)。

## 一、安装

本机已经装好（目录联接），别的机器这样装（表情移植借用换衣插件的底层代码，两个都要）：

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\3.6\scripts\addons\pmx_outfit_transfer" `
         -Target "E:\code\othercode\ripper_tpose\scripts\blender_addons\pmx_outfit_transfer"
New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\3.6\scripts\addons\pmx_expression_transfer" `
         -Target "E:\code\othercode\ripper_tpose\scripts\blender_addons\pmx_expression_transfer"
```

1. 打开 Blender 3.6（已经开着的要重启，或 F3 搜「Reload Scripts」）。
2. 编辑 → 偏好设置 → 插件，搜 `PMX Expression Transfer`，勾上（`PMX Outfit Transfer` 不必勾，装着就行）。
3. 同时要开着 **mmd_tools**。

## 二、面板在哪

3D 视图按 `N` 拉出侧栏 → **MMD** 页签 → 「**表情移植**」面板：

```
┌ 表情移植 ──────────────────────────────────────────┐
│ 表情来自   [ E:\...\mod1707_..._Tifa_..._Ma.pmx ]               │
│ 移到       [ E:\game_export\CCFF7R\Aerith\pmx\aerith\aerith.pmx ] │
│ 输出 PMX   [                                   ]  ← 留空自动     │
│ [ 读取表情 ]                                                     │
│ ☑ まばたき [目]                                                  │
│ ☑ 笑い [目]                                                      │
│ ☑ あ [口]                                                        │
│ ☐ F_Smile01 [其他]   不是 MMD 标准表情                           │
│ ☐ 瞳小 [目]          动的是眼球                                   │
│ [标准表情] [全选] [全不选]                                       │
│ ┌ 选项 ──────────────────────────────┐                          │
│ │ ☐ 同名的替换                        │                          │
│ │ ☑ 眨眼闭严修正                      │                          │
│ │ ☑ 牙齿舌头跟着下巴                  │                          │
│ │ 强度（按面板） 眉[1.0] 目[1.0] 口[1.0] 其他[1.0] │             │
│ │ ☑ 做完导入场景                      │                          │
│ └────────────────────────────────────┘                          │
│ [ 移植表情 ]                                                     │
│ 写出 aerith_表情移植.pmx：新加 29 个，替换 0 个，跳过 0 个        │
└──────────────────────────────────────────────────┘
```

## 三、一步一步（例子：给 CCFF7R 的 Aerith 加上 FF7R Tifa 的游戏表情）

1. **表情来自**：表情齐全的 PMX。例子：
   `E:\game_export\FF7Remake\_face_trial\mod1707_PC0002_00_Tifa_Gantz_Basic_Suit_Skimpy_Hair_and_Ma\mod1707_PC0002_00_Tifa_Gantz_Basic_Suit_Skimpy_Hair_and_Ma.pmx`
   （09-26 用游戏自己的表情数据做的 43 个表情）。
   来源和目标风格越像越好：写实的 FF7 脸用 FF7 的表情；ROE 的脸用 ROE 的表情。
2. **移到**：要加表情的 PMX。例子：`E:\game_export\CCFF7R\Aerith\pmx\aerith\aerith.pmx`。
3. **输出 PMX**：留空就在目标旁边新建 `<目标文件名>_表情移植\`，PMX 和 `textures\` 都在里面；不覆盖已有文件。
4. 点「**读取表情**」：
   - 默认勾上**目标没有的 MMD 标准表情**（まばたき、あ、い……）；
   - 来源的非标准表情（例子里 FF7 的 `F_Smile01` 这类整脸表情）不勾，想要就勾上或点「全选」；
   - 不勾的还有：目标已有的（写着「目标已有」）、动眼球 / 牙齿 / 伸舌头的（瞳小、歯無し、ぺろっ）、材质表情。
5. 选项：
   - **同名的替换**：默认关，目标已有的表情不动，只补缺的。想用来源的换掉目标自己的就打开。
   - **眨眼闭严修正**：默认开。两张脸眼睛张开的高度不一样时，按比例修正眼皮，来源闭上的地方目标也正好闭上。
   - **牙齿舌头跟着下巴**：默认开。张嘴时下牙和舌头随下巴转，上牙不动。
   - **强度**：按 MMD 的四个面板整体放大缩小，例如来源的口型太夸张就把「口」调到 0.7。
6. 点「**移植表情**」。一两分钟（模型越大越慢；Blender 里比命令行快）。
7. 默认导入场景。在 mmd_tools 的「表情」面板里拉每个表情的滑块看一遍；或者直接用 MMD 打开新的 PMX 放一段舞蹈。

成品里有什么：
- 目标的一切原样，只多了移植过来的顶点表情，都在显示枠「表情」里；
- 每个表情动的是：脸皮、睫毛眉毛这类小零件（跟着脸皮）、口腔（下牙和舌头随下巴转）。

## 四、看哪里

- **眨眼**（まばたき、ウィンク、笑い）：眼睛正好闭上，眼皮里没有眼球的颜色透出来；ウィンク 闭的是**模型自己的左眼**（MMD 的惯例）。
- **口型**（あ い う え お）：张嘴时能看到牙，嘴唇内侧没有拉扯出来的尖片。
- **睫毛**：闭眼时睫毛跟着眼皮一起转下来，不戳进眼睛。

## 五、命令行（不开 Blender 界面）

```powershell
& "D:\Program Files\blender-3.6.15-windows-x64\blender.exe" -b --factory-startup `
    --python E:\code\othercode\ripper_tpose\scripts\blender_addons\pmx_expression_transfer\cli.py -- `
    来源.pmx 目标.pmx 输出.pmx [--morphs "まばたき,あ,い"] [--replace] [--no-lid] [--no-jaw] `
    [--strength "brow=1,eye=1,mouth=0.8,other=1"]

python cli.py 来源.pmx 目标.pmx --list        # 只列出会搬哪些、为什么不搬
```

不写 `--morphs` 就是面板里默认勾的那些。装了 numpy 的普通 Python 也能 `python cli.py …`。最后一行 `REPORT {...}` 是 JSON 报告。

## 六、常见问题

- **「no eyeballs found」**：找不到眼球。眼球要挂在 `左目` / `右目` 骨上，或者材质名带 eye / iris / 瞳。
  眼睛画在贴图上、没有眼球网格的卡通脸做不了。
- **「eye L: the eyeball is nowhere visible from the front」**：从正面看不到眼球（被别的网格挡住，或者脸朝向判断反了）。
  模型要是标准 MMD 朝向（脸朝 -Z），有 `頭` 骨。
- **「no face skin found in front of the eyes / mouth」**：认不出脸皮。脸皮要挂在 `頭`（或它下面的脸骨）上。
- **某个表情被跳过「脸上没有变化」**：来源这个表情动的是眼球、牙齿或别的地方，脸皮几乎不动。
- **眨眼闭不严 / 闭过头**：确认「眨眼闭严修正」开着。来源本身的眨眼就是上下眼皮交叠闭合的（大多数写实模型都是），目标会照来源的比例交叠。
- **嘴张得太大 / 风格不像**：来源和目标风格差得远时会这样，用「口」的强度调小，或者换一个风格接近的来源。
- **睫毛、眉毛没跟着动**：它们要是单独的小零件（离脸皮 1 cm 以内、挂在头上、名字不像头发）。头发刘海不会跟着眉毛动，这是故意的。
- **想换掉目标自己的表情**：打开「同名的替换」。

## 七、它怎么做的（一句话版）

两张脸各自从正面找出眼睛开口、眼皮边缘、嘴唇缝、鼻尖 → 按这些特征把来源的脸弯到目标的脸上 → 每个目标顶点取来源脸上对应点的位移，
按局部脸型缩放 → 修正眼皮让眨眼正好闭上、不陷进眼球 → 睫毛眉毛跟着脸皮转、下牙舌头跟着下巴转。细节见 [pmx-expression-transfer.md](pmx-expression-transfer.md)。
