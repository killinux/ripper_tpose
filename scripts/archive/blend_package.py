"""把引用了目录外文件的 .blend 做成独立的：外部贴图 / 声音拷进造型目录，路径改成相对，另存到 E 盘。

  blender -b --factory-startup --python blend_package.py -- <jobs.json> <result.json>

jobs.json: [{"src": 源 .blend, "dest": 目标 .blend, "product_src": 源造型目录, "product_dest": 目标造型目录}]
result.json: {dest: {"copied": [[源文件, 目标文件], ...], "missing": [源文件里本来就找不到的路径],
                     "problems": [...]}}

规则：源造型目录里的文件按原相对位置放；目录外的文件放进 ``textures\\``（重名且内容不同就加 _2、_3）。
打开时 load_ui=True，存出来的界面布局和原文件一样。存完 make_paths_relative 再存一次，然后重新打开核对。
"""
import hashlib
import json
import os
import shutil
import sys

import bpy

lst, out = sys.argv[sys.argv.index("--") + 1:][:2]
with open(lst, encoding="utf-8") as f:
    jobs = json.load(f)
bpy.context.preferences.filepaths.save_version = 0      # 存两次，不要留 .blend1


def nc(p):
    return os.path.normcase(os.path.normpath(p))


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def same_file(a, b):
    return os.path.getsize(a) == os.path.getsize(b) and md5(a) == md5(b)


def datablocks():
    for coll in (bpy.data.images, bpy.data.sounds, bpy.data.movieclips, bpy.data.fonts):
        for db in coll:
            if getattr(db, "library", None) is not None:
                continue
            fp = getattr(db, "filepath", "")
            if not fp or fp == "<builtin>":
                continue
            if getattr(db, "packed_file", None) is not None:
                continue
            if coll is bpy.data.images and db.source not in {"FILE", "MOVIE", "SEQUENCE"}:
                continue
            yield db


def rebuild_sound_strips():
    """声音轨除了引用 Sound 数据块，自己还存着一份旧的目录 + 文件名（blend_paths 报的就是它，播放用的是数据块）。
    改完数据块路径后按新路径重建声音轨，保留名字、通道、起止帧、音量等。"""
    for sc in bpy.data.scenes:
        se = sc.sequence_editor
        if not se:
            continue
        for st in [s for s in se.sequences if s.type == "SOUND" and s.sound is not None]:
            target = bpy.path.abspath(st.sound.filepath)
            if not os.path.isfile(target):
                continue
            keep = {k: getattr(st, k) for k in ("frame_offset_start", "frame_offset_end", "volume", "pan", "mute",
                                                  "lock", "show_waveform", "speed_factor") if hasattr(st, k)}
            name, channel, start = st.name, st.channel, int(round(st.frame_start))
            se.sequences.remove(st)
            new = se.sequences.new_sound(name, target, channel, start)
            for k, v in keep.items():
                try:
                    setattr(new, k, v)
                except (AttributeError, TypeError, ValueError):
                    pass
            new.name = name


result = {}
if os.path.exists(out):
    with open(out, encoding="utf-8") as f:
        result = json.load(f)
for job in jobs:
    dest = job["dest"]
    if dest in result and not result[dest].get("problems"):
        continue
    entry = {"copied": [], "missing": [], "problems": []}
    result[dest] = entry
    try:
        bpy.ops.wm.open_mainfile(filepath=job["src"])
    except Exception as exc:  # noqa: BLE001
        entry["problems"].append("打不开: %s" % exc)
        continue
    psrc, pdst = os.path.normpath(job["product_src"]), os.path.normpath(job["product_dest"])
    taken = {}
    for db in list(datablocks()):
        absp = os.path.normpath(bpy.path.abspath(db.filepath, library=db.library))
        if "<UDIM>" in absp or not os.path.isfile(absp):
            entry["missing"].append(db.filepath)
            continue
        if nc(absp).startswith(nc(psrc) + os.sep):
            target = os.path.join(pdst, os.path.relpath(absp, psrc))
        else:
            base, ext = os.path.splitext(os.path.basename(absp))
            target = os.path.join(pdst, "textures", base + ext)
            n = 2
            while (nc(target) in taken and taken[nc(target)] != nc(absp)) or \
                    (nc(target) not in taken and os.path.exists(target) and not same_file(target, absp)):
                target = os.path.join(pdst, "textures", "%s_%d%s" % (base, n, ext))
                n += 1
        taken[nc(target)] = nc(absp)
        if not os.path.exists(target) or not same_file(target, absp):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(absp, target)
        entry["copied"].append([absp, target])
        db.filepath = target
    rebuild_sound_strips()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=dest, copy=False)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile()
    # 重新打开核对：和自检一样看 blend_paths（它还包括声音轨自己记的路径）
    bpy.ops.wm.open_mainfile(filepath=dest, load_ui=False)
    for p in bpy.utils.blend_paths(absolute=True, packed=False, local=False):
        p = os.path.normpath(p)          # 找不到的留给 archive_exports 的自检判断（源文件本来就缺 vs 漏拷）
        if os.path.exists(p) and not nc(p).startswith(nc(pdst) + os.sep):
            entry["problems"].append("另存后仍在目录外: %s" % p)
    for lib in bpy.data.libraries:
        entry["problems"].append("链接了别的 .blend（没处理）: %s" % lib.filepath)
    print("PACKAGED %s copied=%d missing=%d problems=%d" % (dest, len(entry["copied"]), len(entry["missing"]),
                                                           len(entry["problems"])), flush=True)
    with open(out + ".part", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    os.replace(out + ".part", out)
with open(out + ".part", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
os.replace(out + ".part", out)
