# 用 blender-mcp 的 socket 直接驱动正在运行的 Blender

2026-09-13。目的：不碰鼠标，把 b14 的布料物理在用户**已经打开的** Blender 3.6 里建出来、
播起来，让人当场看效果。做法不是走 MCP 客户端，而是直接跟 blender-mcp 插件开在
Blender 里的 TCP 服务说话。脚本在 `scripts/blender_mcp/`。

## 1. 它是什么

[ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) 分两半：Blender 端一个插件
（装在 `%APPDATA%\Blender Foundation\Blender\3.6\scripts\addons\addon.py`，侧栏 **BlenderMCP**
页签，点「Connect to MCP server」），和一个给 Claude Desktop / Cursor 用的 MCP 服务端
（`uvx blender-mcp`）。插件那一半自己就是个 **JSON over TCP** 服务，默认 `127.0.0.1:9876`，
MCP 服务端只是把它包成工具。所以在 Claude Code 里即使没配 MCP，也能用 20 行 Python
直接连上去——这次就是这么干的。

确认它在听：`netstat -ano | findstr 9876`，PID 应该是 blender.exe。

## 2. 协议

一次连接一个请求，请求和应答都是一整段 JSON（插件那边 `recv` 到能 `json.loads` 为止；
它不关连接，读到能解析就停）：

```json
{"type": "execute_code", "params": {"code": "import bpy\nprint(len(bpy.data.objects))"}}
{"status": "success", "result": {"executed": true, "result": "22\n"}}
```

出错是 `{"status": "error", "message": "..."}`。用到的命令：

| type | params | 说明 |
|---|---|---|
| `get_scene_info` | — | 场景名、对象数、前若干对象 |
| `get_object_info` | `name` | 单个对象的位置/旋转/材质等 |
| `execute_code` | `code` | 在 Blender **主线程**里 `exec`，`print` 的内容原样带回 |
| `get_viewport_screenshot` | `max_size`, `filepath` | 3D 视图截图存到 `filepath`（必填），返回宽高 |

`execute_code` 的实现是把代码交给 `bpy.app.timers` 排队、下一次 UI 刷新时执行，执行期间
Blender 界面会卡住直到返回——开文件、建 100 个刚体这种几秒的事没问题，长任务别往里塞。

`scripts/blender_mcp/mcp_exec.py` 发一个 .py 文件（或 stdin），`mcp_cmd.py` 发任意命令：

```powershell
python scripts\blender_mcp\mcp_cmd.py get_scene_info
python scripts\blender_mcp\mcp_exec.py scripts\blender_mcp\cloth_demo.py 600
python scripts\blender_mcp\mcp_cmd.py get_viewport_screenshot '{"max_size": 1100, "filepath": "C:/tmp/view.png"}'
```

## 3. 这次做了什么（`cloth_demo.py`）

1. `bpy.ops.preferences.addon_enable(module=...)` 启用 mmd_tools 和 mmd_cloth_physics——
   对正在运行的实例直接生效，不用去 Preferences 里 Refresh（插件目录是联接到仓库的，见
   `scripts/blender_addons/mmd_cloth_physics/README.md`）。
2. `bpy.ops.wm.open_mainfile(filepath=..., load_ui=False)` 打开准备好的
   `pc_b14_outfit1_hd_clothlab.blend`（PMX + VMD 已导入、自带物理已剥掉、Rigid Body World 开着），
   `load_ui=False` 保住用户自己的窗口布局。
3. 选中骨架，依次调面板的算子 `mmd_cloth.analyze` → `mmd_cloth.build` → `mmd_cloth.preview`
   （= mmd_tools Build + 打开 Rigid Body World + cache 铺满帧范围）。
4. 视口整理：`mmd_root.show_rigid_bodies / show_joints / show_armature = False` 把辅助物件藏掉，
   实体着色 + 贴图色，`view3d.view_axis(FRONT)` + `view3d.view_selected` 框住网格。
5. `scene.sync_mode = "NONE"`（播放每一帧），跳到首帧，`screen.animation_play()`。
6. 另开一个请求 `get_viewport_screenshot` 截图核对；再用 `execute_code` 读
   `scene.frame_current`、裙摆末端在骨盆坐标系里的位置，确认帧在走、布在动。

收尾用 `cloth_demo_stop.py`：停播放、`mmd_cloth.stop_preview`（= mmd_tools Clean，刚体回
绑定位）、把辅助物件显示回来。**导出 PMX 前必须停预览**。

## 4. 坑

- **timer 里没有窗口上下文。** 需要窗口/区域的算子——`wm.open_mainfile`、`view3d.*`、
  `screen.animation_play`、以及 mmd_cloth_physics 自己的算子（它们读 `context.active_object`）
  ——不包 `temp_override` 就报「context is incorrect」。统一用：

  ```python
  w = bpy.context.window_manager.windows[0]
  area = next(a for a in w.screen.areas if a.type == "VIEW_3D")
  region = next(r for r in area.regions if r.type == "WINDOW")
  with bpy.context.temp_override(window=w, screen=w.screen, area=area, region=region, scene=bpy.context.scene):
      ...
  ```

  打开文件之后 `window`/`area` 对象要重新取一遍（`load_ui=False` 时屏幕还是原来的，但稳妥）。
- **刚体 cache 只在帧连续推进时计算。** 播放同步模式若是「丢帧」或「同步到音频」，跳过的帧
  不算物理，布就冻在原地、身体照跳——看起来就是「衣服没跟着动」。所以脚本强制
  `sync_mode = "NONE"`；正常时视口左上角显示帧率 ≈30。
- **mmd_tools 的 Build 不碰 Rigid Body World 开关。** 场景里 World 关着时 Build 完骨骼绑上了、
  刚体不算，同样是布定在空中。`mmd_cloth.preview` 会强制打开；手点 mmd_tools Build 的话去
  Scene → Rigid Body World 勾上。
- 截图命令必须给 `filepath`，路径用正斜杠；返回只有宽高和路径，图要自己去读。
- 每次请求都是新连接，Blender 那边的 `exec` 用的是同一个 namespace（`globals()` 级），跨请求
  留变量不可靠，每段脚本自己找一遍 root / armature。
- 出错信息只有 `message` 一行，没有 traceback：脚本里自己 `try/except` + `traceback.print_exc()`
  再 print 出来。

## 5. 复现

```powershell
# Blender 3.6 里：侧栏 BlenderMCP → Connect to MCP server
python scripts\blender_mcp\mcp_cmd.py get_scene_info                      # 通了就有 Scene 信息
python scripts\blender_mcp\mcp_exec.py scripts\blender_mcp\cloth_demo.py 600
python scripts\blender_mcp\mcp_cmd.py get_viewport_screenshot '{"max_size": 1100, "filepath": "C:/tmp/view.png"}'
python scripts\blender_mcp\mcp_exec.py scripts\blender_mcp\cloth_demo_stop.py
```

换模型：改 `cloth_demo.py` 顶上的 `BLEND`；准备场景的办法是 PMX 用 mmd_tools 导入（带
PHYSICS 也无妨）、VMD 导入、然后面板上 **Strip dynamic physics**、存盘。
