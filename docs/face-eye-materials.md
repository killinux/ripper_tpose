# 面部材质修复：眼球 / 睫毛 / 眉毛（Rise of Eros）

以 g11（SWEETIE FOX 服装）为例，记录从 FBX 导入后"眼球全白、睫毛/眉毛是肤色色块"
到与游戏内效果基本一致的完整修复过程。可复用脚本: `scripts/blender_face_materials.py`。

---

## 一、问题现象

FBX 导入 Blender 后给 head 网格整体挂脸部贴图，结果：

| 部位 | 现象 | 根因 |
|---|---|---|
| 眼球 | 纯白无虹膜 | 眼球子网格 UV 采样到脸部贴图的白色皮肤区 |
| 睫毛 | 棕色皮肤色块 | 睫毛卡片 UV 采样到脸部贴图错误区域 |
| 眉毛 | 深色块状 | 同上 |

## 二、根因：AssetStudio 合并了子网格

游戏里 head 是一个 SkinnedMeshRenderer + 多个子网格（脸/眼球/睫毛/眉毛/罩层各挂
不同材质）。AssetStudioModCLI `splitObjects` 导出时**把子网格合并成单个 mesh 且不带
任何材质槽**（`slots: []`），子网格信息丢失。

但两条信息保留了下来，足以还原结构：

1. **骨骼权重**：眼球 100% 绑 `Bip001 Eyeball_L/R`，眉毛绑 `Bip001 Eyebrow_*`，
   眼睑/睫毛绑 `Bip001 Eyelid_*` / `AC eyelid_bone_*`。
2. **UV 分区约定**：脸部皮肤的 UV 被平移到 u∈[1,2]（tile 1），眼球/睫毛/眉毛留在
   u∈[0,1]（tile 0）。贴图默认 REPEAT，所以渲染上看不出差别，但可以用它区分子网格。

### head 连通块解码结果（g11，9267 顶点 / 17341 面）

用"顶点连通块 + 每块的骨骼权重分类"可以无歧义地识别每个子网格：

| 连通块 | 面数 | 权重特征 | UV | 判定 |
|---|---|---|---|---|
| 1 大块 | 11129 | other 为主 | tile 1 | 脸部皮肤 |
| 2 块 | 各 432 | 100% Eyeball | [0,1]² 满铺 | 眼球 ×2 |
| 4 块 | 180×2 + 150×2 | lid > other | tile 0 | 上/下睫毛卡 ×4 |
| 2 块 | 各 114 | brow 最大 | tile 0 | 眉毛卡 ×2 |
| 1 块 | 272 | lid≈other，UV 收缩成一个点 | tile 1 | 眼部罩层（半透明壳） |
| 其余 | ~2200 | mouth 类 | 混合 | 牙齿/舌头/口腔（闭嘴不可见，留脸部材质） |

## 三、贴图通道约定（关键！）

`-ExportTextures` 导出的相关贴图：

| 贴图 | 内容 | 注意 |
|---|---|---|
| `pc_g_nk_face_rgbx_Albedo.png` | 脸部皮肤 | 直接用，降饱和 0.85 防偏粉 |
| `pc_g_nk_eye_iris_rgbx_Albedo.png` | 虹膜+瞳孔 | **外圈也是棕色**——整张直接贴会"整眼棕色"没有眼白 |
| `pc_g_nk_eyebrow_rgbx_Albedo.png` | 眉毛+睫毛合一 | **RGB 是大块填充色（供色层，透明区底色是黑的），真正的毛发笔触形状在 alpha 通道里** |

两个由此而来的坑：

- 用"亮度反推 alpha"（白底→透明）会把黑底当不透明 → 渲染成黑色块。
  **必须直接用贴图的 alpha 通道**（此前误以为 alpha 全 0，实际有 33865 个非零像素）。
- 虹膜贴图不能整张贴眼球：要"程序化眼白 + 中心圆盘露虹膜"（见下）。

## 四、5 材质槽配方（EEVEE / Blender 3.6）

不切割几何——给 head 追加 4 个材质槽，按连通块分类逐面设置 `material_index`：

| 槽 | 材质 | 节点要点 |
|---|---|---|
| 0 脸 | face | Albedo → HueSat(Sat 0.85) → Base Color；贴图 Alpha → Alpha；CLIP |
| 1 眼球 | eye | UVMap → VectorMath(DISTANCE, 中心 (0.5,0.49)) → MapRange(SMOOTHSTEP, 0.235→0.285, 1→0) 作为 Fac，MixRGB(眼白 0.90/0.88/0.87, 虹膜贴图)；Roughness 0.15；OPAQUE |
| 2 睫毛 | lash | 眉毛贴图 Color → HueSat(Value 0.55 加深)；Alpha ×1.5(clamp)；BLEND + shadow NONE |
| 3 眉毛 | brow | 眉毛贴图 Color / Alpha 直连；BLEND + shadow NONE |
| 4 罩层 | overlay | **纯 Transparent BSDF**；BLEND + shadow NONE |

调参入口（`scripts/blender_face_materials.py` 顶部常量）：

- `IRIS_R_IN/OUT`：虹膜大小（0.235/0.285 与游戏截图对齐；改小→眼白更多）
- `LASH_ALPHA_GAIN / LASH_DARKEN`：睫毛浓密度/深浅
- `SKIN_DESAT`：肤色饱和度

## 五、踩坑记录

1. **Principled alpha=0 ≠ 隐形**：EEVEE 的 BLEND 模式下镜面高光不受 alpha 控制，
   罩层会在眼周留下灰白色月牙块。必须换 **Transparent BSDF**。
2. **EEVEE shader 编译延迟**：改完节点立刻截图会拍到灰白占位色（像"坏了"），
   等几秒再看。远程 MCP 操作时尤其容易误判。
3. 眼球/睫毛**不要做几何分离**（select_linked / separate）：会误选、产生黑洞，
   且不可逆。改 `material_index` 是无损方案，设回 0 即可还原。
4. 罩层带 lid 权重且面数不小（272），别当成睫毛——判据是"UV 收缩成一点 + 在 tile 1"。

## 六、复用

```powershell
# 无头一键（导入 FBX + 挂全部材质 + 存 .blend）
& 'D:\Program Files\blender-3.6.15-windows-x64\blender.exe' --background --python `
  scripts\blender_face_materials.py -- `
  'D:\roe_exports\g11\pc_g11_hd (1)\FBX_GameObjects\pc_g11_hd\pc_g11_hd.fbx' `
  'D:\roe_exports\g11\xps' `
  'D:\roe_exports\g11\g11.blend'
```

GUI 里用：先手动导入 FBX，Text Editor 打开脚本、改 `TEX_DIR`、Run Script。

脚本自动：按 `Eyeball` 顶点组找 head 网格；body/hair 按名字匹配 Albedo；
body1（带裸露皮肤）自动降饱和；head 做连通块分类 + 5 槽材质。

> 分类规则依赖的骨骼命名（`Bip001 Eyeball_* / Eyebrow_* / Eyelid_*`）是全角色共享
> 骨架的一部分，其他角色（k06 等）同样适用；贴图名前缀按体型变化（pc_g_ / pc_k_ …），
> 脚本用通配符匹配，不受影响。

## 七、已知无法还原的部分

游戏运行时的眼部效果还有 shader 层（视差虹膜、高光点、罩层的动态阴影着色），
静态提取无法完全复刻。当前方案达到的效果：棕色虹膜+黑瞳孔+白眼白、羽状深色睫毛、
自然眉毛——与游戏截图并排对比基本一致（差异主要在引擎光照）。
