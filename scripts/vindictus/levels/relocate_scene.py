"""Move a level .blend and every image file it uses into one folder (absolute paths, saved as they are), so the
scratch copy of the level assets can go.  Packed images stay packed.

  blender -b <level.blend> --factory-startup --python relocate_scene.py -- <dest dir> [<name>.blend]"""
import os
import shutil
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
dest = os.path.abspath(argv[0])
name = argv[1] if len(argv) > 1 else os.path.basename(bpy.data.filepath)
tex_dir = os.path.join(dest, "textures")
os.makedirs(tex_dir, exist_ok=True)
taken = {}
copied = size = 0
for img in bpy.data.images:
    if img.packed_file or img.source != "FILE":
        continue
    src = os.path.normpath(bpy.path.abspath(img.filepath))
    if not os.path.isfile(src):
        print("[relocate] MISSING", img.name, src, flush=True)
        continue
    base = os.path.basename(src)
    stem, ext = os.path.splitext(base)
    out = base
    n = 1
    while out.lower() in taken and taken[out.lower()] != src.lower():
        n += 1
        out = "%s_%d%s" % (stem, n, ext)
    taken[out.lower()] = src.lower()
    dst = os.path.join(tex_dir, out)
    if not os.path.isfile(dst):
        shutil.copy2(src, dst)
        copied += 1
        size += os.path.getsize(dst)
    img.filepath = dst
missing = [img.name for img in bpy.data.images
           if img.source == "FILE" and not img.packed_file and not os.path.isfile(img.filepath)]
out_blend = os.path.join(dest, name)
bpy.ops.wm.save_as_mainfile(filepath=out_blend, compress=True, relative_remap=False)
print("[relocate] %d files copied (%.0f MB) -> %s; missing %d; saved %s" % (copied, size / 1e6, tex_dir, len(missing),
                                                                           out_blend), flush=True)
