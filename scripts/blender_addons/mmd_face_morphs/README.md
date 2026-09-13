# MMD Face Morphs —— 给骨骼脸的模型补 MMD 标准表情（Blender 插件）

给已经转成 mmd_tools 结构的模型，把 MMD 标准表情集做成 PMX **骨骼 morph**：
**认脸骨 → 按配方摆骨 → 写成 bone morph → 登记到 表情 枠 → 渲染对照图核对**。

适用对象是**没有 shape key、靠骨骼驱动脸**的模型。Rise of Eros 就是这样：
每个女性角色 `Bip001 Head` 下固定挂 32 根带蒙皮权重的脸骨（眼皮 4、眼球 2、眉毛
2+6 段、脸颊 2、鼻翼 2、下巴 1、嘴唇 8、舌头 3、牙齿 2），一根 shape key 都没有。
PMX 的骨骼 morph 正好能表达这种脸，VMD 里的表情键也就能驱动它。

```
scripts/blender_addons/mmd_face_morphs/
  __init__.py     插件入口：侧栏 MMD 页签 → Face Morphs 面板
  faces.py        认脸骨：三套命名风格 → 角色（role）；顺带算出坐标系（中线/眼距/朝向）
  expressions.py  配方：36 个标准表情，用 pitch/roll/yaw/move 四种动作描述
  build.py        配方 → mmd_tools bone morph；预览摆骨 / 复位
  api.py          脚本入口 setup(obj, ...)，批处理用
  tools/
    render_morph_sheet.py   在 Blender 里逐个表情渲染正脸特写（核对用）
    make_sheet.py           给特写贴标签、拼图、可选导出视频
```

## 1. 安装与使用

**插件方式**：Blender → Preferences → Add-ons → Install，选这个目录打成的 zip（或把目录
放进 `scripts/addons/`，本机是目录联接），启用「MMD Face Morphs」。要求 mmd_tools 已启用。

面板在 3D 视图侧栏（N）的 **MMD** 页签 → **Face Morphs**：

1. 选中模型任意对象，**Analyze face** —— 报告认出的命名风格、找到几根脸骨、36 个表情
   里有几个能建。控制台还会打出每个 role 对应哪根骨。
2. 勾选要建的类别（眉 / 目 / 口），需要的话调四个幅度倍率（Eyes / Brows / Mouth / Tongue，
   1.0 是标定值）。**Replace same-named morphs** 打开时会重建同名旧 morph
   （ROE 老流程那 9 个就是这么被换掉的）。
3. **Build morphs** —— 建 bone morph，并把全部 morph 登记进 `表情` 显示枠。
   **Clear** 只删本插件建的（记在根对象的 `mmd_face_morphs` 属性里）。
4. 下拉选一个 morph、拖 **Weight**、按 **Preview** 就地摆出来看；**Reset** 复位。
   **导出前一定要 Reset**——预览是真的在摆姿势，留着会被带进导出。
5. 之后用 mmd_tools 正常导出 PMX。

不想自己点，或者要核对效果：

```powershell
# 逐个表情渲染正脸特写（--setup 表示先跑一遍插件）
blender --background --python tools\render_morph_sheet.py -- `
    D:\...\pc_b14_outfit1_hd.pmx  out_dir  --setup
# 刘海挡住眉毛时把头发那几个材质遮掉，只渲眉毛那几个
blender --background --python tools\render_morph_sheet.py -- `
    model.pmx out_dir --setup --hide hair --only "真面目,困る,にこり,怒り,上,下"
# 贴标签拼图（另可 --video sheet.mp4 每个表情停 1 秒）
python tools\make_sheet.py out_dir sheet.png --cols 7
```

**脚本方式**（批处理）：

```python
import sys; sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\blender_addons")
from mmd_face_morphs import api
report = api.setup(root_or_any_object,
                   categories=("EYEBROW", "EYE", "MOUTH"),
                   scales={"eyes": 1.0, "brows": 1.0, "mouth": 1.0, "tongue": 1.0},
                   replace=True, log=print)
# report["morphs"] 建了哪些，report["skipped"] 为什么没建，report["face"] role→骨名
```

`import mmd_face_morphs` 不需要装插件（`register()` 只在 Blender 加载插件时调用），
所以批处理 worker 用 `sys.path` 插一下就能用。

## 2. 它怎么认脸骨（faces.py）

按 **role** 找，不按名字找。同一个游戏里并存三套拼法，`ROLE_NAMES` 每个 role 列出
见过的所有拼法，去掉 `Bip001 ` / `Bip000 ` 前缀、忽略大小写后精确匹配：

| role | 小写风格（a/c/d/e/f/g/h，38 个） | 大写风格（b14、i/j/k/l/m，75 个） | b01 风格（6 个） |
|---|---|---|---|
| upper_lid_L/R | `eyelid_UL` `eyelid_UR` | `Eyelid_LT` `Eyelid_RT` | `eyelid_UP_L/R` |
| lower_lid_L/R | `eyelid_BL` `eyelid_BR` | `Eyelid_LB` `Eyelid_RB` | `eyelid_DN_L/R` |
| brow_L/R | `eyebrow_L/R` + `_LC/_LL/_LR` 三段 | `Eyebrow_L/R` + 三段 | `Eyebrow_L/R`（无分段） |
| chin | `chin` | `Chin` | `Jaw` |
| corner_L/R | `lip_L` `lip_R` | `Lips_L` `Lips_R` | `Lips_L/R` |
| upper_lip_C/L/R | `lip_UC` `lip_UCL` `lip_UCR` | `Lips_TC` `Lips_TL` `Lips_TR` | `Lips_UP(_L/_R)` |
| lower_lip_C/L/R | `lip_BC` `lip_BCL` `lip_BCR` | `Lips_BC` `Lips_BL` `Lips_BR` | `Lips_DN(_L/_R)` |
| tongue_0/1/2 | `tongue` `tongue02` `tongue03` | `Tongue` … | 同 |
| teeth_up/dw | `teeth_up` `teeth_dw` | `Teeth_up` `Teeth_dw` | `teeth_UP/DW` |
| eye_L/R | mmd_tools 转过的 `目.L/.R`（按 `mmd_bone.name_j` 认 左目/右目） | | |

- **`AC ` 开头的骨跳过**：那是 3ds Max 的辅助副本，挂在真正的控制骨底下，动控制骨它们会跟着；
  mmd_tools 自己加的 `_dummy_` / `_shadow_` 代理骨同理。
- **眉毛分段按到中线的距离排**，不按名字：b14 的 `Eyebrow_LR` 其实是**内**侧（x=0.018），
  `Eyebrow_LL` 是**外**侧（x=0.050），照名字猜会左右颠倒。只有一根眉骨的（b01 风格）
  退化成 `brow_*_tilt`，用整根骨的 roll 表达喜怒。
- **舌头顺着最长的分支往下走**，有几节用几节。
- 同时算出这张脸的坐标系：**中线**（成对 role 的 x 均值）、**单位**（两眼间距，b14 是 59 mm）、
  **朝向**（脸骨相对头骨在 Y 上的符号）。所有幅度都以「眼距的几分之一」表示，所以换个
  身高或换个模型不用重调。

ROE 的 4 个男模（a03–a06）头下除了牙齿只有 `Xtra##`，认不出任何 role，一个 morph 也不会建——
这是对的，老流程在这几个模型上也是 0。

## 3. 表情是怎么描述的（expressions.py）

一条动作是 `(role, kind, amount)`，四种 kind：

| kind | 含义 | 正方向 |
|---|---|---|
| `pitch` 度 | 绕左右轴转 | 骨的**前端向下**（眼皮闭、下巴张、舌尖下垂） |
| `roll` 度 | 绕前后轴转 | **外侧端向上**（左右自动镜像） |
| `yaw` 度 | 绕上下轴转 | 前端**向外**摆（中线骨则朝角色左手边） |
| `move` (out, fwd, up) | 位移，单位是眼距 | out 离开中线（左右镜像）、fwd 朝脸前方 |

正方向不是靠猜骨的静止朝向，而是 `rotation_sign()` 实测：拿骨的前向/外向探针绕该轴转 1°，
看它往不往目标方向走，再决定符号。所以同一条配方在左右两侧、在朝向不同的骨上都对。

36 个表情：**眉 6**（真面目 / 困る / にこり / 怒り / 上 / 下）、**目 11**（まばたき / 笑い /
ウィンク / ウィンク右 / ウィンク２ / ｳｨﾝｸ２右 / なごみ / はぅ / びっくり / じと目 / キリッ）、
**口 19**（あいうえお / ▲ / ∧ / ω / ω□ / にやり / にやり２ / ぺろっ / てへぺろ / てへぺろ２ /
口角上げ / 口角下げ / 口横広げ / 歯無し上 / 歯無し下）。名字必须和 VMD 里的字节完全一致，
差一个字（半角 `ｳｨﾝｸ` vs 全角 `ウィンク`）在 MMD 里就是静默失效。

标定值：眼皮闭合 **33°**、下巴张到「あ」**18°**、眉毛行程 1–6 mm、嘴角 い 张 13 mm。
面板上的四个倍率就是乘在这些数上。

**舌头是量出来的，不是估的。** 第一版给 ぺろっ 用「下巴张 8° + 舌头前移 0.25 + 下俯 18°」，
渲出来舌尖从**下巴里穿出去**了：ROE 的舌尖静止时就在唇面**后方 4–8 mm**，只转不平移
只能让它扎进下巴。改成量评估后网格：取舌尖顶点组和上下唇顶点组，扫 216 组参数，
要求舌尖超出下唇 >8 mm 且位于上唇下缘以下，选出 **下巴 16° + 前移 0.45 + 下移 0.08 +
俯 6° + 卷 6°**，舌尖伸出下唇 14 mm。

## 4. 核对（tools/）

`render_morph_sheet.py` 在 Blender 里把模型正脸怼近（相机按眼距自动定位，前后朝向自适应），
逐个 morph 摆好渲一张 PNG，写 `index.json`；`make_sheet.py` 贴上表情名拼成一张大图或视频。
`--hide <正则>` 用来遮挡挡视线的部件：PMX 导入通常是**一整块合并网格**，所以匹配到的是
材质时走的是「按材质给面打 MASK 修改器」那条路，而不是把整个头藏掉。

b14_outfit1 上的验收结果：36 个全部建出、0 个跳过；导出 PMX 再用 `mmd_tools.core.pmx.load`
读回来，36 个骨骼 morph 分类正确（眉 6 / 目 11 / 口 19）、没有越界的骨引用、
`表情` 显示枠列了全部 36 个（MMD 的表情面板才有东西）。a01（小写风格）和 b01（b01 风格）
各建出 36 个，眨眼、单眼 wink 的左右、あいうえお、眉毛喜怒都正确。

## 5. 与 mmd_cloth_physics 的关系

同一套约定的姊妹插件，一个管布、一个管脸，都挂在侧栏 MMD 页签下，都能用
`api.setup()` 从批处理调用，都遵循「只动自己建的东西，Clear 只删自己建的」。
