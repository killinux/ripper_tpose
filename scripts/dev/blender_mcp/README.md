# Blender MCP 开发辅助

本目录只放可复用的 Blender MCP 本地诊断工具，不属于 ROE 或 FF7 Rebirth 的用户导入
流程。

## `execute_code.ps1`

把一个本地 Python 文件发送到已经启动的 Blender MCP TCP 服务中执行。默认连接
`127.0.0.1:9876`。

使用前：

1. 启动 Blender；
2. 打开 Blender MCP 面板并启动服务；
3. 准备一个只包含本次诊断逻辑的 Python 文件；
4. 在仓库根目录执行：

   ```powershell
   .\scripts\dev\blender_mcp\execute_code.ps1 `
       -CodeFile .\path\to\probe.py
   ```

若 Blender MCP 使用其他端口：

```powershell
.\scripts\dev\blender_mcp\execute_code.ps1 `
    -CodeFile .\path\to\probe.py `
    -Port 9877
```

该工具会在当前 Blender 进程中执行任意 `bpy` 代码。只应运行自己检查过的本地脚本；
一次性 probe、热重载和渲染脚本执行完成后不要长期堆放在 `scripts` 根目录。
