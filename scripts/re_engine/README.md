# RE Engine（生化危机 2 / 3 重制版）角色 mod → 高清 .blend + PMX + XPS

不用游戏本体。mod 里的 `natives\stm\...\*.mesh.<版本>`、`.mdf2.13`、`.tex.<版本>` 直接转。第一个用例是 Nexus 上生化危机 3 的
She-Venom Jill：#1424，以及 #1561 的 Black 和 Black Damage 两个变体。

```powershell
python -I scripts\re_engine\export_mod.py "<mod 的 .zip 或文件夹>" --game ResidentEvil3 --character Jill --name SheVenom_Jill_1424
```

| 参数 | 作用 |
|---|---|
| `--game` / `--character` | 输出到 `<out-root>\<game>\<character>\{blend,pmx,xps}\<名字>\`，`--out-root` 默认 `E:\game_export` |
| `--name` | 名字；压缩包里有几个 mod 文件夹（各带一个 `natives`）时，后面接各自文件夹名多出来的部分，例如 `_Damage` |
| `--colour 材质或母材质=r,g,b` | mod 没带贴图的材质用的纯色（sRGB 0–1）；头发母材质默认深棕 `0.23,0.15,0.10` |
| `--formats` | 默认 `blend,pmx,xps` |

## 需要什么

- **RE Mesh Editor**（NSACloud，GPLv3，2026-04 起归档）。下载 GitHub 的 main.zip，解到仓库外的
  `E:\tools\re_mesh_editor\scripts\addons\RE-Mesh-Editor-main\`。它要 Blender 4.3.2 以上，本机用
  `D:\Program Files\Blender Foundation\Blender 4.5\blender.exe`。
- 脚本启动 Blender 时把 `BLENDER_USER_SCRIPTS` 指到 `E:\tools\re_mesh_editor\scripts`，插件只在这次后台会话里启用，
  不保存偏好设置，**不改用户 Blender 的配置**。
- texconv（`E:\tools\directxtex`）。PMX 和 XPS 用 Blender 3.6。

## 每一步

1. 解压 mod，每个带 `natives` 的文件夹算一个变体。
2. 只取 `natives\...\mesh\` 文件夹里的 `*.mesh.*`，同名的只取版本号最大的。作者留下的 `Nova pasta`、`исходники` 之类的源文件夹会跳过。
   名字和角色文件夹相同的那个排第一（`pl2000\mesh\pl2000.mesh`），由它提供骨架，其余的并进来。
3. `import_re_mesh.py`（Blender 4.5）用插件导入：
   - 去掉不足 10 个顶点的子网格。mod 把去掉的装备压成一个三角形藏起来，Jill 有 19 个这种；
   - 用插件自带的读取器读每个材质的贴图绑定（`.mdf2`）；
   - 插件转好的 `.dds` 在它的缓存里，`.tex` 不在 mod 里的就记成缺失；
   - 导出 FBX。
4. texconv 把 `.dds` 转成 PNG。
5. `build_blend.py`（Blender 3.6）导入 FBX，按脚尖方向转到面朝 -Y，重建材质：
   - `BaseMetalMap`（ALBM）：RGB 颜色，A 金属度；
   - `BaseAlphaMap` / `BaseMap`（ALBA / ALB）：颜色，ALBA 的 A 是透明度；
   - `NormalRoughnessMap`（NRMR）：RGB 法线（OpenGL 方向，不翻转），A 粗糙度；
   - `AlphaTranslucentOcclusionSSSMap`（ATOS）：R 透明度，G 透光，B AO（乘进颜色），A 凹缝；
   - 角膜、泪液、眼影这类母材质做成透明壳；`Hair` 母材质用 ATOS 的 R 做镂空；`Skin` 母材质加一点次表面散射。
6. `scripts\pmx_tools\biped_pmx`（骨骼映射 `re_engine`）→ PMX 和 XPS。

## 坑

1. 插件的「显示控制台」会调用 `bpy.ops.wm.console_toggle`，Blender 后台模式下没有窗口，直接崩溃（`GHOST_setConsoleWindowState`）。脚本把这个选项关掉。
2. 插件按**游戏内路径**缓存转好的贴图，同一个角色的 mod 路径全一样。不重新转的话，第二个 Jill mod 拿到的是第一个 mod 的蓝色身体贴图。
   所以导入时设 `reloadCachedTextures=True`。
3. **打包在 alpha 里的数据不是透明度**：ALBM 的 alpha 是金属度，NRMR 是粗糙度，ATOS 是凹缝。
   按默认的直通 alpha 读，Blender 会拿 alpha 去乘颜色。Jill 的脸部贴图 alpha 平均 0.28，烘焙出来的 PMX 脸是黑的。
   这类贴图设成 `CHANNEL_PACKED`；ALBA / ALB 的 alpha 才是透明度。
4. 材质名可能和内容对不上。这个 mod 里叫 `pl2001_Face_Mat` 的子网格用的是 `Hair` 母材质和头发贴图，其实是头发；
   叫 `pl2001_Eyelash_Mat` 的才是脸。所以重建材质看母材质和贴图绑定，不看名字。
5. 头发贴图（`pl2005_Hair_*`）、道具贴图都在游戏的 pak 里，mod 没带，头发只能是纯色的发帽。有游戏本体的话，可以把它们解出来放进 natives 再转。
