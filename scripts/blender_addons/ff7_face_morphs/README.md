# FF7 Face Morphs（Blender 3.6 插件）

给 FINAL FANTASY VII REMAKE 的角色模型加 MMD 表情。表情形状全部来自游戏自己的数据，没有手调：

- 眼、眉和整脸表情取自角色的表情姿势动画（`Motion/Player/<角色>/Facial00/F_*`）；
- あいうえお 取自游戏说话用的口型数据（`LipSync/LipMap/Player/<角色>/<名字>_Default`）。

生成的是形态键，导出 PMX 后就是标准 MMD 顶点表情（まばたき、笑い、ウィンク、あいうえお、ん、真面目、困る、怒り……
共 29 个标准表情 + 14 个游戏整脸表情），MMD 和舞蹈 VMD 都按名字直接驱动。原理和验证见
[`docs/ff7-face-morphs.md`](../../../docs/ff7-face-morphs.md)；完整的使用说明（MMD 里怎么用、表情一览、面板每个按钮、
常见问题）见 [`docs/ff7-face-morphs-usage.md`](../../../docs/ff7-face-morphs-usage.md)。

## 安装

仓库里的插件以目录联接装进 Blender（和 mmd_face_morphs、mmd_cloth_physics 一样）：

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\3.6\scripts\addons\ff7_face_morphs" `
         -Target "E:\code\othercode\ripper_tpose\scripts\blender_addons\ff7_face_morphs"
```

然后在 Blender 的 编辑 > 偏好设置 > 插件 里搜 `FF7 Face Morphs` 勾选。面板在 3D 视图侧栏（N）的 **MMD** 标签页。
需要 mmd_tools（登记表情、导出 PMX）；"导出带表情的 PMX"还需要 Convert_to_MMD5 和 mmd_cloth_physics（和批量导出一样）。

## 准备表情数据（每个角色一次）

表情数据是游戏数据，不进仓库，默认放在 `E:\game_export\FF7Remake\_meta\face\`：

```powershell
python scripts\final\ff7_face_data.py --out E:\game_export\FF7Remake\_meta\face\PC0002_Tifa.json
```

Tifa 的已经生成好了（`PC0002_Tifa.json`）。插件按模型名里的 `PC0002` 自动找对应文件；别的目录可以设环境变量
`FF7_FACE_DATA_DIR`，或者在面板里直接选文件。

## 用法

打开 FF7 Remake 模型的 **.blend**（带脸部骨骼 `C_FaceBase_a` 的原始 blend，例如
`E:\game_export\FF7Remake\Tifa\blend\<模型>\<模型>.blend`；已经转好的 PMX 里脸部骨骼被并掉了，不能用），
选中骨架或网格：

1. **分析模型**：显示脸部骨骼数、蒙皮网格、表情数据里有几个姿势和口型、能生成多少表情。
2. **生成表情**：按 目 / 眉 / 口 / 其他 选择要生成的类别，每类有强度（1.0 = 游戏原始幅度；游戏的眉毛动得比较轻，
   觉得不明显可以调到 1.3–1.5）。同名形态键会重新生成；场景里原来的姿势和其它形态键数值不受影响。
3. **预览**：选一个表情、拖权重看效果；"归零"把全部表情放回 0。**清除**只删本插件生成的形态键。
4. **导出带表情的 PMX**：在后台另开一个 Blender，用和批量导出完全相同的脚本
   （`scripts/final/export_ff7_pmx_blender.py --face-data …`）转换，当前打开的文件不会被改动；文件有未保存的修改时
   会先存一个临时副本。面板里的类别和强度会原样带过去：文件里之前生成过的表情会先清掉再重新生成，
   所以 PMX 里只有面板上勾选的类别。输出到 `<输出文件夹>\<文件名>\`（该文件夹会被整个替换，
   默认输出文件夹 `E:\game_export\FF7Remake\_face_trial`），完成后面板显示表情数、撕裂数和"打开文件夹"按钮。
   TheWolfster 的 GANTZ 紧身衣（Remake #1707、Rebirth #817）要勾"裙骨皮肤跟大腿"，和批量导出一致。

### 手动用 Convert_to_MMD5 转换时

Convert_to_MMD5 烘焙 A 字姿势、对齐手臂和手指时会**跳过带形态键的网格**；FF7 模型全身是一个网格，带着形态键转换
手臂就会出错。所以顺序是：

生成表情 → **转换前暂存**（形态键移到 .blend 里一个隐藏的网格副本，保存重开也不丢）→ Convert_to_MMD5 转换 →
**恢复并登记**（放回形态键；模型被转了方向或缩放成米也会跟着换算；同时登记到 mmd_tools 模型的 目/眉/口/その他 面板
并重建"表情"显示框）→ 用 mmd_tools 导出 PMX（Scale 12.5）。

## 脚本调用

```python
import sys; sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\blender_addons")
from ff7_face_morphs import api
made = api.build(bpy.context.object, r"E:\game_export\FF7Remake\_meta\face\PC0002_Tifa.json",
                 strengths={"EYEBROW": 1.5})
api.stash(bpy.context.object)      # 转换前
api.restore(bpy.context.object)    # 转换后
```

只看效果（渲染每个表情的脸部特写，不改文件）：

```powershell
blender -b <模型>.blend --python scripts\final\ff7_face_morph_sheet.py -- --face-data <json> --out <文件夹>
```

## 限制

- 只支持 FF7 Remake 的脸部骨架（`C_FaceBase_a` 下的约 104 根骨骼）；目前只有 Tifa 的表情数据。其他角色要用各自的
  `Facial00` 和 `LipMap` 生成数据；Rebirth 还没看。
- 没有 瞳小、ハイライト消し、照れ 这类要改贴图或加网格的表情，也没有 あ２、ω、左右单侧的眉/口角变体。
