# 女毒液模型：哪里有（调研页）

`html\venom_female_models.html`：女性毒液（She-Venom / Gwenom / 共生体）模型能从哪里拿到，每一项标出本机的情况：
游戏装没装、有没有转换流程、是不是已经导出。2026-11-15 整理。

```powershell
python -I scripts\venom\make_venom_page.py        # 用 data\ 里的数据重新生成页面（会重新检查 E:\game_export 里导出了哪些）
python -I scripts\venom\nexus_venom.py            # 可选：重新抓 Nexus（公开的 v2 GraphQL，不用密钥），写 data\nexus_venom.json
python -I scripts\venom\br_crawl_venom.py         # 可选：重新扫 BetterRepack 的 HS2 / AI 少女 zipmod 公开库
```

| 数据（`data\`） | 来源 |
|---|---|
| `nexus_venom.json` | Nexus 全站按名字搜 venom / symbiote / gwenom / carnage 等，2026-11-15 共 1,891 个 mod；仓库里只留页面列出的 64 个女性角色的 |
| `sketchfab_venom.json` | Sketchfab 公开搜索里能免费下载的 29 个 |
| `br_venom_hits.json` | BetterRepack 公开库 20,982 个 zipmod，只有 1 个：Fouetty 的 Marvel Rivals 毒液（男性，Studio 道具） |

付费 / 别的格式（itch.io、Gumroad、RenderHub、CGTrader、ModDB）是手工搜的，写在脚本里。

**已经转好的**不在这页，在毒液合集画廊 `E:\game_export\_毒液合集\index.html`
（`python scripts\archive\make_collection.py collections\venom.json` 生成）。
页面上「已导出 Blender」的标记：blend、PMX、XPS 三样都在归档里才算，只有测试 .blend 的不标。
