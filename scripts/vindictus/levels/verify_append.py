"""Append a level .blend the way disperse_pair.py does (by the given path, into an unsaved file) and list image files
that cannot be found.  blender -b --factory-startup --python verify_append.py -- <level.blend>"""
import os
import sys

import bpy

lib = sys.argv[sys.argv.index("--") + 1]
with bpy.data.libraries.load(lib, link=False) as (src, dst):
    dst.objects = list(src.objects)
    dst.worlds = list(src.worlds)
images = [i for i in bpy.data.images if i.source == "FILE" and not i.packed_file]
bad = [i.filepath for i in images if not os.path.exists(os.path.normpath(bpy.path.abspath(i.filepath)))]
print("[verify] objects %d, file images %d, missing %d" % (len(bpy.data.objects), len(images), len(bad)))
for b in bad[:10]:
    print("[verify] MISSING", b)
print("[verify] sample", images[0].filepath if images else None)
