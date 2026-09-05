#!/usr/bin/env python3
"""layer2 mod 无原版 ktid（未安装对应 DLC）时的合成 matmap。

- 解析 mod g1m 的材质/submesh（复用 g1m_matmap.parse_g1m）
- mod Material/*.g1t 按部位分组（body/a01/c01/f01...）
- 启发式分配：非零顶点 submesh 的材质按顶点数降序，最大者给 body（若有），
  其余按部位名序补位；零顶点网格（Malf 被删的衣物）随意。
- 启发式猜错时用 --assign 手动指定后重跑（看预览判断，皮肤/衣物弄反最常见）。

用法:
  python mod_matmap.py <mod.g1m> <Material目录> <输出matmap.json>
  python mod_matmap.py ... --assign "3=body,5=f01"   # 材质号=部位 手动覆盖
  python mod_matmap.py ... --key PHFCOS037            # 多部件 mod：只认这个部件的 g1t
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g1m_matmap import parse_g1m  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("g1m")
    ap.add_argument("mat_dir")
    ap.add_argument("out")
    ap.add_argument("--assign", default=None, help='手动 "材质号=部位,..." 覆盖启发式')
    ap.add_argument("--key", default=None, help="只用文件名含 _<KEY>_ 的 g1t（如 PHFCOS037）；没匹配则退回全部")
    args = ap.parse_args()

    mats, subs = parse_g1m(args.g1m)

    files = sorted(os.listdir(args.mat_dir))
    if args.key:
        keyed = [fn for fn in files if ("_%s_" % args.key.upper()) in fn.upper()]
        if keyed:
            files = keyed
    parts = {}
    for fn in files:
        m = re.match(r"MPR_Muscle_Character_[A-Z0-9]+_(\w+?)_kids(\w+)\.g1t$", fn)
        if m and os.path.getsize(os.path.join(args.mat_dir, fn)) > 200:
            parts.setdefault(m.group(1), {})[m.group(2)] = fn
    part_names = sorted(parts)
    if not part_names:
        raise SystemExit("Material 目录里没有可用 g1t")

    mat_verts = {}
    for s in subs:
        mat_verts[s["material"]] = max(mat_verts.get(s["material"], 0), s["vertexCount"])
    order = sorted(mat_verts, key=lambda m: -mat_verts[m])

    assign = {}
    if args.assign:
        for kv in args.assign.split(","):
            k, v = kv.split("=")
            assign[int(k)] = v.strip()
    remaining = [p for p in part_names if p not in assign.values()]
    if "body" in remaining and order and order[0] not in assign:
        assign[order[0]] = "body"
        remaining.remove("body")
    for m in order:
        if m not in assign:
            assign[m] = remaining.pop(0) if remaining else part_names[0]

    def texs(part):
        out = []
        for ch in ("alb", "nmh"):
            fn = parts.get(part, {}).get(ch)
            if fn:
                out.append({"slot": 0, "name": fn, "channel": ch, "layer": 0})
        return out

    result = {
        "g1m": os.path.basename(args.g1m),
        "heuristic": True,
        "assign": {str(k): v for k, v in assign.items()},
        "submeshes": [
            {"index": s["index"], "material": s["material"], "vertexCount": s["vertexCount"],
             "textures": texs(assign.get(s["material"], part_names[0]))}
            for s in subs
        ],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print("parts:", part_names, "| assign:", assign, "| verts:", mat_verts)


if __name__ == "__main__":
    main()
