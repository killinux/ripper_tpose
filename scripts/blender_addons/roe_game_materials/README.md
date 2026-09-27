# ROE Game Materials（Blender 3.6 插件）

导入 Rise of Eros 的 PMX（XPS、FBX 也行）以后，一键把材质换成**游戏原始的完整材质**，用来在 Blender 里做动画、出渲染：

- 法线：布料纹理、缝线、褶皱的凹凸；
- 金属度 / 光滑度 / AO：金饰的金属光泽、光滑面的反光、凹处的阴影；
- 皮肤：透光（次表面散射）和脸上的毛孔细节（游戏里平铺 70 倍）；
- 头发：游戏里的发色、发丝遮蔽、头发法线；
- 眼睛、睫毛、眉毛保持原样。

PMX 格式本身只装得下一张颜色贴图，这些效果只能在 Blender 里加回来。插件不删 mmd_tools 的任何节点：
随时能切回 MMD 着色，用 mmd_tools 再导出 PMX 也和原来一样。

## 安装

仓库里的插件用目录联接装进 Blender，和 mmd_cloth_physics、ff7_face_morphs 一样。本机已经装好：

```powershell
New-Item -ItemType Junction -Path "$env:APPDATA\Blender Foundation\Blender\3.6\scripts\addons\roe_game_materials" `
         -Target "E:\code\othercode\ripper_tpose\scripts\blender_addons\roe_game_materials"
```

然后在「编辑 → 偏好设置 → 插件」里搜 `ROE Game Materials` 勾选。
面板在 3D 视图侧栏（按 `N`）的 **MMD** 标签页，标题「ROE 游戏材质」。

需要：
- mmd_tools，用来导入 PMX；
- 某个角色**第一次**使用时，要从游戏包读材质数据，这需要装了 UnityPy 的系统 Python 和 Rise of Eros 的游戏文件，本机都有。
  读出来的数据缓存在 `D:\roe_exports\_hq_materials\`，之后再用就不读游戏了。

## 用法

1. 用 mmd_tools 导入 PMX，缩放 0.08。
2. 选中模型：点模型的根、骨架或网格都行。
3. 点「**换上游戏原始材质**」。某个角色第一次用要几十秒，之后几秒。
   面板下方会显示「角色 g05：换了 6 个材质，保留 4 个……」。
4. 「**游戏材质 / MMD 着色**」两个按钮来回切，方便对比。
5. 在「调整」里拖滑块，**实时生效**。1.0 是游戏原始值，「参数恢复默认」回到原始值。
6. 照常做动画、渲染。要再导出 PMX，就照常用 mmd_tools 导出，PMX 里还是原来那张颜色贴图。
7. 不想要了点「**去掉游戏材质**」，恢复原样。

| 参数 | 默认 | 作用 |
|---|---|---|
| 法线强度 | 1.0 | 游戏法线强度的倍数：布料纹理、缝线、褶皱的凹凸 |
| 毛孔细节 | 1.0 | 脸上细节法线（毛孔）的倍数 |
| AO 强度 | 1.0 | 凹处变暗的程度 |
| 光滑度 | 1.0 | 越大越亮、反光越清楚 |
| 金属度 | 1.0 | 金饰、扣子这类金属部分 |
| 皮肤透光 | 0.1 | 皮肤的次表面散射；0 = 关 |
| 头发粗糙度 | 0.45 | 越小头发越亮 |
| 凹处高光也压暗 | 开 | 和游戏一样让 AO 也压暗反光；关掉后凹处的光滑面会反射整片天空、发灰 |

「角色代号」一般留空：插件会从模型名或贴图名认出来，比如 g05、a01。认不出时再手动填。
「高级」里可以改数据缓存目录、Python 路径、游戏资源目录。

## 支持哪些模型

- 本仓库导出的 ROE PMX：
  - 新导出的，颜色贴图名是 `<材质>__pmx_diffuse.png`；
  - 2026-09-27 以前导出的，用的是游戏原来的颜色贴图名；
- ROE 的 XPS（`__xps_diffuse` 贴图），用 XPS Tools 导入；
- 用 ROE 插件导入 FBX、挂过材质的模型；
- 只有 Rise of Eros。别的游戏没有这套材质数据。

## 原理

- 按每个材质用的颜色贴图，找到对应的游戏材质。
  - 导出贴图的名字直接带着材质名；
  - 老的颜色贴图名就在游戏材质里查；
  - 身体和皮肤共用一张贴图，按材质名里有没有 `skin` 区分。
- 在**同一个材质里**加一套 `hq_` 开头的节点和一个自己的输出节点，切换靠「哪个输出节点是激活的」。
  - MMD 的节点一个不删，两边都一直连着。所以在 mmd_tools 里改 MMD 材质时，它不会把输出抢回去；
  - 导出 PMX 读的 `mmd_base_tex` 也原封不动。
- 节点和批量导出用的是同一份代码：`scripts/riseoferos/hq_materials_blender.py` 的 in_place 模式。
  游戏材质数据来自 `scripts/riseoferos/hq_material_data.py`。
- 详细做法和验证见 [`docs/roe-hq-materials.md`](../../../docs/roe-hq-materials.md)。

## 注意

- 只在 Blender 3.6 上测过。Blender 4.x 的 Principled BSDF 改了插口名，要另外适配。
- 用 Eevee 渲染时，打开「屏幕空间反射」金属会更好看。
- 这些效果只在 Blender 里有。PMX 放进 MMD 还是只显示颜色贴图，要法线效果得用 ray-mmd。
