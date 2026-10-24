# MMD Cloth Physics —— 给 mmd_tools 模型的布料刚体/关节（Blender 插件）

给已经转成 mmd_tools 结构的模型（PMX 导入的、或 Convert_to_MMD5 转出来的）自动加
MMD 标准的布料物理：**认形状找衣服骨 → 按类型套预设 → 纵向关节 + 横向格子关节 →
刚体尺寸按蒙皮量 → 掉落测试**。设计对标 PMXEditor 圈子里的做法（そぼろ
曲面自動設定プラグイン、極北P 标准剛体/ジョイント生成 + 横ジョイント、PmxTailor 预设），
参数来自社区经验与两份手调参考 PMX。

```
scripts/blender_addons/mmd_cloth_physics/
  __init__.py   Blender 插件入口：侧栏 MMD 页签 → Cloth Physics 面板
  analyze.py    找衣服：候选骨 → 连通链 → 按锚骨+名字词干归组 → ring / sheet / strand → 横向配对（按网格）
  presets.py    预设：skirt / coat / ribbon / sleeve / tassel / hair / ornament
  build.py      建刚体 + 关节（mmd_tools Model.createRigidBody / createJoint），身体碰撞胶囊，链尾粘连
  collide.py    碰撞组：身体按部位分组，每个布刚体只关掉它出生就陷进去的那个部位
  geom.py       刚体形状与穿插深度（numpy），collide / build / analyze 共用
  validate.py   掉落测试：静置 N 帧看拉断 / 未停
  api.py        脚本入口 setup(obj, ...)，批处理用
```

## 0. 2026-10-18 修了什么（0.2.0；10-24 的 0.2.1 见本节「另外」之后）

ROE Inase a08 的裙子穿腿，查下来是插件自己的四个问题。198 个带物理的 ROE 模型全部有，
其他游戏（对魔忍、FF7、剑星、洛奇英雄传）也有：

| 问题 | 以前 | 现在 |
|---|---|---|
| 箱形刚体的坐标系 | `box_frame` 造的是 (x, y, y×x)，**左手系（镜像）**；`to_euler('YXZ')` 还原出来长轴还在骨上，但绕骨乱转了最多 90°：ROE 44% 的箱子薄面朝侧面，像鱼鳍插在裙子上，大腿从鳍旁边滑进布里 | 右手系；厚度方向 = 这根骨驱动的那片布的法线（PCA 最小主轴），量不到才退回「离锚骨水平向外」，并且朝离身体最近碰撞体的反方向 |
| 箱子的大小和位置 | 以骨为中心、按骨长；宽/厚沿错的轴量 | 按布本身：横跨布的 5–95% 分位 + 预设厚度，宽同样，**链的最后一节一直盖到裙摆**（裙摆在骨尾下面还有 4–6 cm，腿撞的就是那里）；再挪到布上，但不比在骨上时更深地陷进身体 |
| 横向格子关节 | 链按**根骨**绕锚骨的方位角排序、相邻两条逐行连：a08 侧/前/后片同挂在一块胯部护片下，前片被连到后片（穿过大腿），共用开头几节的分叉链连到了**自己** | 按网格：两条链在布接触的地方连（同时有两根骨权重的顶点 + 跨两根骨的网格边），每根骨连它接触最多的那根；网格上本来不相连的两片（分开的布条）才按「布在身体周围的位置」相邻逐行连，且连线不能穿过身体碰撞体；同一块网格中间剪开的（开衩）不连 |
| 碰撞组 | 贴身段（第 0 行或包围球挨着碰撞体）放组 10，**什么都不撞**；裙子上半部几乎全是：81 个裙子贴腿的 ROE 模型，贴腿的布一半以上不撞腿 | 身体碰撞体按部位（头 / 颈 / 躯干 / 手臂 / 腿）各一组；每个布刚体测它出生时陷进各部位多深，陷进去的先削薄（盒子一个轴、胶囊半径，最少到 35%），还不行才只关掉那一个部位；每种部位组合一个组。挂在物理刚体上的布（挂在胸上的饰带）一律不撞——手碰到会扯动胸 |

另外：链尾的布缝在别的刚体上（a08 胯侧挂链的后端粘在胯部护片上，只从前端挂着）时补一个
`A.` 关节，限位同这条链最后一节。

**0.2.1（2026-10-24）改正上面这一条的判断。** 0.2.0 数「缝在上面」的顶点时，把最后一节和上一节共用的顶点也算了进去。
那只是链自己的平滑蒙皮：一个顶点同时挂在上下两三节上。结果隔一节的祖父骨、旁边那条链的上一节都像「粘着」，被补上
零位移的 `A.` 关节，和已有关节围成三角形。三个刚体只剩绕一根轴转，而那根轴顺着链，扭转限位只有几度，所以发梢、
披肩、丝带、袖口、裙摆最下面那节基本摆不起来。

现在的规则：
- 只数**上一节不带**的共用顶点（`SkinIndex.driven()`，`shared_points` / `shared_counts` 的 `without=`）；
- 只隔两个关节的刚体一律不连，免得围成三角形。四边以上的环照样连，比如卷发的发梢缝回本链往上 3–4 节，或 a08 的链尾
  缝回链根的胯甲。

重建过的 18 个模型（ROE 13 个 + Aerith / Tifa / Anemone / Fiona / Eve）：

| | ROE 13 个 | 其他游戏 5 个 | 合计 |
|---|---|---|---|
| 0.2.0 的 `A.` 关节 | 95 | 103 | 198 |
| 0.2.1 的 `A.` 关节 | 8 | 26 | 34 |

保留的都是真缝着的，比如几层裙片的下摆、整片缝在一起的发束、大腿丝带缝在下半身上。a08 的重建结果和 0.2.0 逐字节
相同（它那两个 `A.` 关节的 12 个共用顶点，上一节一个都不带）。其余关节和刚体都没变，掉落测试全部稳定。

a08 穿衣版（手势舞，裙子顶点进腿部皮肤，每帧，不算胯部护片）：插件旧版 695 → 新版 78（护腿 45 → 2.2）；
新版 + `cloth_collision_pmx.py --colliders-from`（按 full 版裸体贴合的大腿/小腿碰撞体）20.8，
比 10-18 手工修的 27 还低。插件自己做不到碰撞体贴合裸体（要 full 版的裸体），这一步仍在后处理。

测试时又修的三处：游戏骨骼的骨尾是 1–2 cm 的短桩（CCFF7R Aerith 的裙链骨间隔 15–20 cm）——链上只有一个子骨时
一律量到子骨，最后一节骨尾太短就沿上一节的方向；位置写在名字前面的裙子（`CB_skirtA`、`LF_skA`）每条链被当成一件
衣服——同一锚骨下、布在网格里相连、名字提示的预设不冲突的合成一件（名字记成「最大那件+N」）；碰撞阈值 2 mm，和
ROE / 剑星导出脚本之后跑的 `release_rest_overlaps` 一致，它不会再把插件判为可碰的刚体关掉。

`api.setup(..., collision="near")` 回到旧碰撞组规则（对比用）；`analyze.find_garments(..., mode="legacy")`
回到旧的横向配对。已有 PMX 用 `scripts/mmd_physics/cloth_rebuild_blender.py` 按新插件重建物理（其余数据不动），
`cloth_check_pmx.py` 只读检查上面这几类问题。

## 1. 安装与使用

**插件方式**：Blender → Preferences → Add-ons → Install，选这个目录打成的 zip（或把目录
放进 `scripts/addons/`），启用「MMD Cloth Physics」。要求 mmd_tools 已启用。

面板在 3D 视图侧栏（N）的 **MMD** 页签：

1. 选中模型任意对象，**Analyze garments** —— 列出找到的衣服：名字@锚骨、类型、预设，
   每件可改预设 / 取消勾选。
2. 没有身体碰撞刚体的模型先点 **Body colliders**（有就跳过）。
3. **Build physics** —— 建刚体 + 关节。**Clear** 删掉本插件建的（身体胶囊保留）。面板上
   「By body part / Old: near = none」选碰撞组规则（默认按部位），「Boxes on the cloth」把盒子挪到布上（默认开）。
4. **Drop test** —— 静置 60 帧，报告每个关节拉伸了几倍（>1.5× 记拉断）、末尾还在不在动。
   先存盘：它会 `Model.build()` 再 `clean()`，位置会还原，但仍属于会动场景的操作。
5. **Preview (build + play)** —— 相当于 mmd_tools 的 Build 再把 Scene 的 Rigid Body World
   打开、cache 铺满帧范围、跳到首帧；空格播放就能看布飘。**看完按 Stop preview**（= mmd_tools
   Clean，刚体回绑定位）再导出。直接点 mmd_tools 自己的 Build 也行，但它会保留 Rigid Body
   World 原来的开关状态——场景里若是关着的，骨骼绑上了刚体、刚体却不算，衣服就整段定在
   空中不跟身体走。
6. 之后用 mmd_tools 正常导出 PMX。

不想自己点：Blender 里开着 blender-mcp 的服务时，`scripts/blender_mcp/cloth_demo.py` 会把
1–5 步在那个 Blender 里全做完并开始播放，见 `docs/blender-mcp-driving.md`。

**脚本方式**（批处理、ROE 导出流程就是这样调）：

```python
import sys; sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\blender_addons")
from mmd_cloth_physics import api
report = api.setup(root_or_any_object,
                   presets={"Skirt": "skirt", "Decoration": "ornament"},   # 可选，按词干或全名覆盖
                   body_regex=r"^Bip0\d\d\b", prop_regex=r"\bProp\d*$",
                   lattice=True, reverse_joints=False, log=print)
```

`report` 里有每件衣服的类型/预设/刚体数/关节数，可直接写进 manifest。

## 2. 它怎么找衣服（analyze.py）

候选骨 = 驱动真实蒙皮（权重和 ≥ 2.0）、还没有刚体、且不是：MMD 标准骨（日文名）、
身体骨架（`body_regex`，Biped 是 `^Bip0\d\d\b`）、四肢辅助骨（twist/elbow/knee…）、
脸（頭/首 之下，头发词表命中的除外）、手持道具（`prop_regex` 祖先之下）。

候选骨按父子连成分量；只有一根的是护甲片、臀骨之类，扔掉。分量按 **(锚骨, 名字词干)**
归为一件衣服——词干是去掉尾部 `_B1_01` / `_R1_010` 这类侧向+序号后的部分，b14 的
`Skirt_B1..B4/F1/L1..L4/R1..R2` 11 条链就归成一件 `Skirt@下半身`。

类型：≥4 条链、链上的布绕锚骨一圈、相邻方位角最大缺口 <120° → **ring**（裙）；否则多条链
→ **sheet**（披风片、并排流苏）；单链 → **strand**（袖、飘带）。ring/sheet 的横向配对见第 0 节：
布接触的地方按接触量配对；分开的布条才按高度配对（不是按序号：b14 的裙链有 4 节的也有 6 节的），
配对距离 ≤2.5×典型段长，所以相隔半个身子的左右流苏不会被连起来。

预设按名字猜：hair / sleeve / tassel|pendant|rope / ribbon|streamer|sash / coat|cloak|cape /
skirt|dress|frill / decoration|feather|wing|rib|armor → ornament；猜不到按类型：ring→skirt，
sheet→coat，strand→ribbon。UI 里可改。

## 3. 建了什么（build.py）

- **刚体**：BOX（布）或 CAPSULE（发、流苏）。BOX 本地 Y 沿骨、X 横跨布面（厚，朝外）、Z 沿布面（宽），
  右手系；X 是布的法线。大小**按蒙皮量**——该骨权重 ≥0.3 的顶点在 X/Z 上的 5–95% 分位（最后一节沿骨
  量到裙摆），盒子挪到布上；量不到退回段长比例。第 0 行用预设的 `root_mode`（裙/袖/外套是 2 =
  物理+ボーン位置合わせ，根不漂）。质量、移动/回转减衰 按行从 root 到 tip 插值。
- **纵向关节**：放在子骨头部，位移锁死，回转限制 (swing, side, twist) 按行插值，弹簧按预设
  且按段长² 缩放（短段满刚度会超出求解稳定域，参考实现踩过）。关节朝向 X=切向 / Y=径向 /
  Z=沿骨：MMD 老 Bullet 对 6DOF 限位做欧拉分解时 Y 是奇异轴，小角度的扭转轴必须落在
  PMX Y（= Blender Z）上，否则快速转身全裙爆炸；Blender 的新 Bullet 测不出这一类。纵向关节的
  Y 取盒子的 X（布的法线），所以摆动是「离开布面」而不是沿布面横摆。
- **横向格子关节**（横ジョイント）：ring/sheet 相邻链的两个刚体之间（配对见第 0 节），位移 ±2 cm、
  回转 ±30/30/10°、无弹簧——这是 PMXEditor 圈子防「腿穿裙」的标准做法。可选
  **裏ジョイント**（同一对再反向建一条）。链尾粘在别的刚体上时补 `A.` 关节。
- **碰撞组**（collide.py，`collision="classes"`）：身体碰撞体按部位分组，布刚体撞它出生时没陷进去的
  所有部位（见第 0 节）；布与布不互撞（参考 PMX 同款）。旧规则 `collision="near"`：身体 0；贴身段 10
  不撞任何东西；自由段 11 只撞身体；头发 9。
- 所有刚体/关节 empty 是 `rotation_mode='YXZ'`，欧拉一律 `to_euler('YXZ')`；创建期间关掉
  `scene.rigidbody_world`，否则新刚体一评估就被步进、绑定位漂移。

## 4. 预设（presets.py）

| 预设 | 形状 | 质量 root→tip | swing / side / twist (root→tip, °) | 弹簧 | 格子 |
|---|---|---|---|---|---|
| skirt | BOX | 1.0→0.4 | 20→50 / 10→25 / 5 | 5→0 | ✓ ±2 cm |
| coat | BOX | 1.0→0.5 | 15→35 / 8→20 / 5 | 15→5 | ✓ ±1.5 cm |
| ribbon | BOX | 0.6→0.2 | 30→60 / 20→45 / 10→20 | 2→0 | — |
| sleeve | BOX | 0.8→0.3 | 25→50 / 15→35 / 8→15 | 5→0 | ✓ |
| tassel | CAPSULE | 0.8→0.3 | 20→40 / 20→40 / 10 | 0 | — |
| hair | CAPSULE | 1.0→0.6 | 10 / 10 / 10 | 0 | — |
| ornament | BOX | 1.0 | 5→8 / 5→8 / 3 | 30 | — |

弹簧就是「保形」旋钮：0 是垂下来的布，30 是只会抖的雕塑。Convert_to_MMD5 的 skirt.py
对所有布一律 30，所以 m03 那两条在 T-pose 里绕过肩膀的宽飘带整段舞都停在原造型。

## 5. 掉落测试（validate.py）

Blender 的 Bullet 比 MMD 的（2.75，软约束）新且硬，测不出 MMD 的动态手感和关节系爆炸，
但能回答「结构健不健康」：静置 60 帧后每个刚体到最近 kinematic 刚体的距离是静置前的几倍
（>1.6× 记为拉断）、末尾速度（>2 cm/帧 记为没停）。袖子从 A-pose 摆到竖直位移 0.7 m
是正常的，拉断倍数才是要看的。

## 6. 参考

- [PMXメモ：スカートの物理設定 - ジョイント編](http://black-yuzunyan.lolipop.jp/archives/3987) —— 关节轴要对齐裙面（绿轴向上、蓝轴向外）
- [スカート剛体について（備忘録）](https://site.nicovideo.jp/ch/userblomaga_thanks/archive/ar853593) —— 纵关节只限转、横关节要有位移余量、防穿腿
- [曲面自動設定プラグインのメモ](https://ameblo.jp/everymemo/entry-12825424626.html) / [VRoid→MMD 裙物理](https://mimisui-mmd.blog.jp/archives/10692230.html) —— 曲面格子生成
- [vrm→pmx スカート物理](https://note.com/krpooo/n/na548a28bf06c) —— PmxTailor 预设、碰撞组分层、穿模对策
- [MMD 剛体/ジョイント設定](https://site-builder.wiki/posts/21917) —— 三种刚体类型的用法
- Convert_to_MMD5 `docs/skirt_physics_design.md` —— 关节朝向 / YXZ 欧拉 / 弹簧按段长² 三个坑的来历
