# ROE XPS Tools 插件（一步步转 XPS）

`scripts/roe_xps_addon.py` —— Blender 插件，把"FBX 导入 → 修脸材质 → 导出 XPS"
做成侧边栏三个按钮。远程机器(haoni)的 Blender 3.6 已安装启用。

## 安装

Edit > Preferences > Add-ons > Install... 选 `roe_xps_addon.py`，勾选启用。
（依赖：第 3 步需要 XNALaraMesh 插件已启用）

## 使用

3D 视口按 `N` 打开侧边栏 → **ROE** 页签：

| 字段/按钮 | 说明 |
|---|---|
| FBX | extract_character.ps1 导出的角色 FBX |
| 贴图目录 | 含 `*_Albedo.png` 的目录（如 `D:\roe_exports\g11\xps`） |
| **1. 导入 FBX** | 自动骨骼朝向；旧版 cm 级模型自动 ×100 |
| **2. 挂材质(修眼睛)** | body/hair 挂 Albedo；head 分 5 槽修眼球/睫毛/眉毛（原理见 [face-eye-materials.md](face-eye-materials.md)）。EEVEE 编译 shader 需几秒 |
| XPS 输出 | 留空则自动输出到贴图目录 `<角色>_fixed.mesh` |
| **3. 导出 XPS(.mesh)** | 见下。场景本身不受影响 |

导出的 `.mesh` 和贴图在同一目录，XNALara / XPS 直接打开即可。

## 第 3 步做了什么

1. **烘焙眼球贴图**：XPS 不支持程序化节点，把"程序化眼白+虹膜圆盘"烘成
   `roe_eye_baked.png`（参数从场景里眼球材质节点读取，和视口所见一致）
2. **临时复制**所有网格（原场景不动），head 按材质槽拆成 face/eye/lash/brow，
   罩层丢弃
3. **XPS Shader 节点组包装**：XNALaraMesh 导出器只认名为 `XPS Shader` 的节点组
   （沿其 `Diffuse` 输入插槽找贴图），普通 Principled 材质会被写成 missing.png
4. **命名规则**：`<renderGroup>_<名字>_<高光>`；RG **5**=仅diffuse无alpha(脸/眼球)，
   RG **7**=仅diffuse带alpha(睫毛/眉毛/头发/身体)；名字本体不能含下划线
   （XPS 用 `_` 做分隔符，含下划线会被 XNALara 解析成多段并合并同名网格）
5. 调 `xps_tools.export_model` 导出，然后清理临时物体、恢复场景

## 已验证（g11）

导出 `pc_g11_hd_fixed.mesh`(3.0 MB) 重新导回 Blender：

| XPS mesh | 顶点 | 贴图 |
|---|---|---|
| 5_face | 8064 | pc_g_nk_face_rgbx_Albedo.png |
| 5_eye | 458 | roe_eye_baked.png |
| 7_lash / 7_brow | 416 / 154 | pc_g_nk_eyebrow_rgbx_Albedo.png |
| 7_pc-g11-hd-body1/2 | 13458 / 5750 | 各自 Albedo |
| 7_pc-g-hd-hair | 9937 | pc_g_nk_hair_rgbx_Albedo.png |
| 骨架 | 186 根 | — |

## 故障排查

| 现象 | 原因 | 解法 |
|---|---|---|
| 导入 .mesh 报 `KeyError: 'Alpha'` | 场景里有残缺的 'XPS Shader' 节点组（旧版插件导出时创建的），XNALaraMesh 导入按名字复用了它 | 升级到新版插件后**重启 Blender** 再导入即可；新版导出会自动把残缺组改名让位，且优先用 XNALaraMesh 自己的 `xps_shader_group()` 创建完整组 |
| 导回模型**全黑**（贴图都能加载） | 'XPS Shader' 组是半成品：内部 Principled 没连到组输出（建组函数中途异常），组输出为空 | 新版插件导出时自动校验并补上缺失的输出连接 |
| 导回模型全黑 + 贴图 missing | .mesh 旁边的贴图文件没了——**输出目录设在了 `D:\roe_exports\<角色>\` 里面**，重新提取该角色时会被脚本清空 | 输出放外面的目录（如 `D:\roe_exports\xps_export\`），插件会自动把贴图复制过去 |
| 导回后**夹克/大件衣服半透明**像消失 | body 网格用了 RG7（alpha 混合），EEVEE 对大网格透明排序错乱 | 新版已改：body 用 RG5（不透明），仅头发/睫毛/眉毛用 RG7 |
| 导回的**骨架和身体差 90 度**（骨骼摊在地上） | XPS 格式是 Y-up 坐标系，XNALaraMesh 导入只把网格转了 Z-up，骨架保留 Y-up 原样 | 点面板的 **「4. 修正XPS骨架方向」**（+90°X 烘进骨架数据，网格不动）；绑定/权重本来就正确，XPS 软件里显示也正常 |
| face 选到 LD 低清 / hair 选到别的体型贴图 | 贴图目录含多体型共享贴图，模糊匹配选错 | 新版按 `pc_<体型>_nk_*` 精确匹配 |

## 局限

- 皮肤降饱和、睫毛加深等 EEVEE 节点效果**带不进 XPS**（XPS 只认贴图文件），
  XPS 里显示原始贴图颜色，肤色会比 Blender 视口略粉
- 眼部罩层（游戏里的动态阴影壳）不导出
- 眉毛/睫毛依赖贴图 alpha 通道 + RG7 的 alpha 渲染
