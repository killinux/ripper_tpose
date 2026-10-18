# ROE full 版胸部穿模：衣服下的身体从胸带里顶出来

工具：
- `scripts/riseoferos/pmx_body_follows_cups.py`（10-11 已有）
- `scripts/riseoferos/pmx_body_cover_cups.py`（10-18 新增）
- `scripts/mmd_physics/pmx_bust_chain_nocollide.py`（10-18 新增）
- 量具 `scripts/mmd_physics/chest_clip_blender.py`（10-18 新增）

## 现象

用户 10-18 反馈：`Luf\pmx\pc_g05_hd_full` 里的 PMX 跳手势舞时，胸部似乎穿模。胸部近景渲染（MMD 着色）证实：乳头从白色胸带边缘、甚至胸带中间顶出来。穿衣版（游戏自己的皮肤）在同样的帧上是干净的。

## 原因

full 版里有两份身体：一份贴着衣服内侧，平时穿着衣服时在里面；另一份是自然裸体，平时隐藏。贴着衣服的那份来自家族的裸体底模，用的是底模的权重；外面的衣服用的是游戏的权重。

1. **两层随胸摆动的比例不一样**。g05 的胸带随胸摆动骨（`chest_L02`）的权重是 0.44。胸带下面的身体，除了直接挂在 `chest_L02` 上的 0.35，还有约 0.5 挂在 `Nipple_L` 上，而 `Nipple_L` 也跟着 `chest_L02` 走，合起来将近 0.9。胸一晃，皮肤走的距离是胸带的两倍。乳头静止时只在胸带下 0.7–6 mm（中位数 3 mm），一晃就顶出来。
2. **只修比例还不够**。`pmx_body_follows_cups.py` 把胸带附近身体的摆动比例改成和胸带一样（周围 4 个胸带顶点的加权平均），之后平均已经接近 0。但其余骨头的分配仍然不同，第 144 帧还有一个乳头尖顶出 1.8 mm。
3. **（g05 特有，裙子修正带进来的）胸前挂件被手碰**。`cloth_collision_pmx.py` 给胸前两条宝石挂件（`Riband_L/R_01..03`，挂在会摆动的胸部刚体上）开了碰撞。手势舞里手从胸前划过时碰到挂件，挂件就把胸拽一下。

## 修法（三步，都只改 PMX，不用 Blender）

```powershell
python scripts\mmd_physics\pmx_bust_chain_nocollide.py full.pmx s1.pmx       # 挂在会摆动的胸部刚体上的链：不碰撞（归档原版就是这样）
python scripts\riseoferos\pmx_body_follows_cups.py s1.pmx s2.pmx              # 身体随胸摆动的比例 = 胸带的
python scripts\riseoferos\pmx_body_cover_cups.py s2.pmx 修好的.pmx            # 胸带正下方的身体：完全照抄胸带的权重
```

- `pmx_body_cover_cups.py` 只处理正好位于某个胸带三角形下面、深度不超过 1 cm 的身体顶点。判断条件：投影落在三角形内，偏移方向沿法线。这些顶点改用胸带上方那个点的权重，即三角形三个顶点权重按重心坐标的混合，所以两层永远一起动。
- 露在外面的皮肤不改。裸体那份、顶点位置、法线、表情、骨骼、刚体都不动。
- 穿衣版（皮肤是游戏自己的）只需要第三步，加参数 `--body <皮肤材质>`。
- 挂件只碰腿的方案试过，没有用：八方来才里大腿高抬时，bustB 那条轻挂件照样穿过去（归档原版也这样），其他布料反而变差。所以挂件保持原版的「不碰撞」。

## 量具

```powershell
blender -b --factory-startup --python scripts\mmd_physics\chest_clip_blender.py -- full.pmx 舞.vmd out.json
        [--body pc_g01_nk_body] [--outfit "pc_g05_hd_body 1,pc_g05_hd_body 2"]
```

- **配对**：把静止时位于胸带下面的每个身体顶点，和它正上方的胸带点（三角形加重心坐标）配成一对。胸带是衣服里有 ≥ 0.3 权重在胸部骨骼上的三角形，挂件链不算。
- **计数**：仿 MMD 物理逐帧重算，身体点跑到胸带前面超过 0.5 mm 就算顶出。
- **两个坑**：
  - 胸带三角形的朝向要用模型自带的法线定。用「背离胸部中心」来判断，会把约三成三角形判反。
  - 配对要用「偏移沿法线」判断。用「重心坐标都 > 0.02」会漏掉落在三角形内部边上的顶点。

## 结果（g05，手势舞，每帧顶出胸带的顶点数）

| | 修前 | 修后 |
|---|---|---|
| full | 165（最多 211，最深 9.3 mm） | 0（最深 0.2 mm） |
| full bustB | 122（最多 229） | 0 |
| 穿衣版 | 0.2 | 0 |
| 穿衣版 bustB | 1.6 | 0 |

对比视频：`E:\game_export\RiseOfEros\Luf\pmx\pc_g05_hd_full\pc_g05_hd_full_胸部_修正前后对比_手势舞.mp4`（0.55 m 近景，正面和右前侧）。

## 其他 full 版

10-11 已经对 14 套 OPAI/Xtra01 补全版跑过 `pmx_body_follows_cups.py`。其余补全版（a08 61–64%、g04、季节装等）还没跑，第三步更是都没做。a08 full 实测摆动比例平均差 0.34，和 g05 一样。
