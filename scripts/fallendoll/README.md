# Operation LOVECRAFT: Fallen Doll 导出工具

UE4.26 游戏（项目名 **Paralogue**），单个 AES 加密 pak（pak v9，索引加密）。
完整调研与流程见 [Fallen Doll 提取调研](../../docs/fallen-doll-extraction.md)。

| 脚本 | 作用 | 需要 key |
|---|---|---|
| `probe_pak.py` | 只读探测 pak 版本/加密/索引（不接触 key） | 否 |
| `prepare_fmodel.ps1` | 验证安装、建工作区、打印 FModel 配置指引 | 否 |
| `export_models.ps1` | 扫描 FModel 已导出的 SkeletalMesh，批量材质化为 Blend/FBX/GLB | 是（上游导出时） |

## 当前状态

**唯一阻塞项是 pak 的 AES-256 key**：本机 FModel 未配置，且经实测该 key 不以明文
形式存在于游戏 exe 中（详见调研文档 §3）。key 只在拥有游戏的本机 FModel 中配置，
**不提交到仓库**。

## 快速开始

```powershell
# 1. 探测（不需要 key）
python scripts\fallendoll\probe_pak.py

# 2. 建工作区 + 查看 FModel 配置指引（不需要 key）
.\scripts\fallendoll\prepare_fmodel.ps1

# 3. 在 FModel 中配置 UE4.26 + AES key，导出 SkeletalMesh 到 fmodel_exports\
#    然后批量材质化（下游复用 FF7 Rebirth 的 UE4.26 管线）：
.\scripts\fallendoll\export_models.ps1 -List
.\scripts\fallendoll\export_models.ps1
```

材质流程（材质 JSON 匹配、DirectX→OpenGL 法线、ORM、分层眼球、便携眼球烘焙）与
FF7 Rebirth 完全一致，直接复用已验证的
[`scripts/final/export_ff7rb_model_blender.py`](../final/export_ff7rb_model_blender.py)。
