# Operation LOVECRAFT: Fallen Doll 提取调研

> 初次调研：2026-08-29（Asia/Shanghai），本机只读枚举
> 游戏目录：`D:\Program Files (x86)\Steam\steamapps\common\Operation Lovecraft Fallen Doll Demo`
> UE 项目名：**Paralogue**

## 1. 结论速览

| 项目 | 结论 |
|---|---|
| 引擎 | **Unreal Engine 4.26**（`ChaosCloth` 存在、`apex` 缺失、pak v9 三重印证） |
| 封包 | 单个 `Paralogue-WindowsNoEditor.pak`，Desktop 与 VR 各一份（各约 5.4 GiB） |
| pak 版本 | **9**（相对/frozen 索引布局） |
| 索引加密 | **是**，需要 AES-256 key（footer 加密标志=1，索引头 56/64 高熵字节） |
| 提取工具 | FModel / CUE4Parse（通用 UE4.26 profile，无专用 GameName） |
| 模型格式 | ActorX `.psk/.pskx`（FModel Save Model） |
| 下游材质化 | 复用 FF7 Rebirth 的 UE4.26 管线（见 §4） |
| **当前阻塞** | **AES key 未知**：本机 FModel 未配置，且 key 不以明文形式存在于游戏 exe 中 |

一句话：工具链和脚本已就绪，**唯一缺的是 pak 的 AES-256 key**；拿到 key 在 FModel
里配置后，即可导出并材质化。

## 2. pak 与加密验证

只读探测脚本（不需要、不接触任何 key）：

```powershell
python scripts\fallendoll\probe_pak.py
```

输出（两个 pak 一致）：

```text
pak version:       9  (UE4.25-4.26 relative/frozen index)
index offset/size: 5865957844 / 8001488 bytes
index encrypted:   YES - AES key required
index head:        56/64 distinct bytes (high entropy, consistent with encryption)
```

`index encrypted: YES` 意味着**没有 key 时 FModel/CUE4Parse 连文件列表都读不出来**，
更谈不上导出。这与 ROE（Unity，文件级直取）、Throne of Desire（X-Legend 自定义封包）
不同：Fallen Doll 是标准 UE4 加密 pak，卡在 key 而非解析。

## 3. AES key 现状与获取途径

### 本机已排除的途径（2026-08-29 实测）

- **零 key**：解密索引头得到乱码，否。
- **exe 内 64 位 hex 字符串**（26 个候选）：无一能解出合法索引，否。
- **exe 全量滑窗爆破**：把 shipping exe 每个 32 字节窗口当 AES-256 key 试解索引头。
  - 第一轮：所有高熵、4 字节对齐窗口（552,027 个）——0 命中。
  - 第二轮：step-1 全覆盖（含非对齐偏移）——11 个「命中」经严格校验（mount point
    必须可打印且以 `../` 开头）**全部为误报**，解出的字节其实是 x86 指令或字符串
    常量（例如 `ragePakList`）。

**结论：AES key 不以明文连续 32 字节形式存在于 `Paralogue-Win64-Shipping.exe` 中**
（唯一的 shipping 二进制，无独立游戏 DLL）。这对加密发行的成人 UE4 游戏是常见做法。

### 合法获取途径（需游戏所有者在本机操作）

1. **社区 UE AES key 库**：FModel 用户维护的按游戏聚合的 key 列表常收录此类游戏的
   主 key；确认后手动填入 FModel。
2. **运行时取 key**：游戏自身在加载 pak 时会把 key 交给 `FAES::DecryptData`，因此 key
   存在于游戏进程内存中。对自己拥有的游戏，用相应工具在运行时读取是标准手段。

> 本仓库遵循与 FF7/Stellar Blade 文档一致的策略：**不在仓库中保存或分发 AES key、
> 游戏资产或其他受版权保护的数据**。key 只在拥有游戏的本机 FModel 中配置。

## 4. 拿到 key 之后的流程（已就绪）

### 4.1 准备工作区并查看 FModel 配置指引

```powershell
.\scripts\fallendoll\prepare_fmodel.ps1
# 或 -LaunchFModel 直接启动 FModel；-Variant VR 处理 VR 封包
```

脚本会跑一次 pak 探测，建立隔离工作区 `D:\fallendoll_exports\`，并打印 FModel 需要
的三项配置：

1. Add Undetected Game，目录指向 `...\Paralogue\Content\Paks`；
2. UE Versions 选 **GAME_UE4_26**；
3. AES 填入主 key（`0x...`）。

随后在 FModel 中 Load，把角色 **SkeletalMesh + Material + Texture** 保持 Unreal 目录
结构 Save 到 `D:\fallendoll_exports\fmodel_exports\`。

### 4.2 批量材质化（复用 FF7 Rebirth 管线）

Fallen Doll 与 FF7 Rebirth 同为 UE4.26 FModel 导出，材质流程完全一致（材质 JSON
匹配、DirectX→OpenGL 法线、ORM 拆分、分层眼球、便携眼球烘焙），因此下游直接复用
已验证的 `scripts/final/export_ff7rb_model_blender.py` worker：

```powershell
.\scripts\fallendoll\export_models.ps1 -List           # 扫描已导出的 SkeletalMesh
.\scripts\fallendoll\export_models.ps1                 # 全部 -> 内嵌贴图 .blend
.\scripts\fallendoll\export_models.ps1 -Only DollBody -Format blend,fbx,glb -Force
.\scripts\fallendoll\export_models.ps1 -ValidateOnly   # 只导入+校验
```

接口、manifest 机制（`-ValidateOnly` 独立快照、`-Only` 合并、失败记 traceback）与
ROE/FF7RB/ToD 的 `export_*` 脚本一致。产物进 `D:\fallendoll_exports\materialized\`。

> **裸模说明**：能否得到「裸模」取决于导出的 SkeletalMesh 本身——若身体与服装是
> 独立 mesh（如 ToD），选身体 mesh 即可；若一体，则与 ROE/FF7 同理需 mod 或组件筛选。
> 具体结构要等 key 到位、实际导出后才能判断，届时按 `-List` 结果确定。

## 5. 已就绪与待办

| 组件 | 状态 |
|---|---|
| `scripts/fallendoll/probe_pak.py` | ✅ 已验证（两个 pak 探测正确） |
| `scripts/fallendoll/prepare_fmodel.ps1` | ✅ 已验证（工作区+指引，端到端跑通） |
| `scripts/fallendoll/export_models.ps1` | ✅ 逻辑已验证（扫描/委派/manifest；用伪造布局端到端跑到真实 Blender worker） |
| 下游材质 worker | ✅ 复用已验证的 FF7RB `export_ff7rb_model_blender.py` |
| **AES key** | ❌ **待获取**（唯一阻塞项，见 §3） |
| 真实导出与裸模判定 | ⏳ 待 key 到位后进行 |
