"""Blender 里逐个打开 .blend，列出它引用的全部外部文件（贴图、链接库、字体、声音、缓存……）。

  blender -b --factory-startup --python blend_selfcheck.py -- <blends.json> <result.json>

blends.json 是 .blend 路径列表；result.json = {blend: [[绝对路径, 存在?, 已打包?], ...]}。
打包进 .blend 的数据不算外部文件：blend_paths(packed=False) 跳过已打包的数据（Blender 3.6 实测；
它的文档写反了，packed=True 反而会把已打包贴图的原路径也列出来）。每查完一个就写一次结果，
Blender 在某个文件上崩掉时，那个文件记成 "<open failed: crashed>"，其余的不丢。
"""
import glob
import json
import os
import sys

import bpy

lst, out = sys.argv[sys.argv.index("--") + 1:][:2]
with open(lst, encoding="utf-8") as f:
    blends = json.load(f)
result = {}
if os.path.exists(out):
    with open(out, encoding="utf-8") as f:
        result = json.load(f)


def flush():
    with open(out + ".part", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    os.replace(out + ".part", out)


for path in blends:
    if path in result:
        continue
    result[path] = [["<open failed: crashed>", False, False]]
    flush()
    try:
        bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    except RuntimeError as exc:
        result[path] = [["<open failed: %s>" % exc, False, False]]
        flush()
        continue
    refs = []
    for p in bpy.utils.blend_paths(absolute=True, packed=False, local=False):
        p = os.path.normpath(p)
        if "<UDIM>" in p or "<UVTILE>" in p:
            exists = bool(glob.glob(p.replace("<UDIM>", "*").replace("<UVTILE>", "*")))
        else:
            exists = os.path.exists(p)
        refs.append([p, exists, False])
    result[path] = refs
    flush()
    print("SELFCHECK %s refs=%d missing=%d" % (path, len(refs), sum(not r[1] for r in refs)), flush=True)
flush()
