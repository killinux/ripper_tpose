# -*- coding: utf-8 -*-
"""Front close-up of a character's eyes + a report of every eye material (Blender 3.6, headless).

  blender -b X.blend --factory-startup --python render_eye_closeup.py -- --out <dir> [--tag T]
          [--material-re REGEX] [--dump-textures]

Finds the polygons that use an eye material (default regex: "eye" not followed by brow / lash / lid;
Reika's mod uses "^ojos$", Vincent "_Eye[LR]$"), aims a 100 mm camera at them from the front (the
direction from the head bone C_Head_a towards the eyes), lights them with one sun and a grey world,
and renders <out>/<tag>_eyes.png with EEVEE.  The blend's own lights are hidden so every model is
lit the same - that is what makes Remake / Rebirth or before / after pictures comparable.
<out>/<tag>_eyes.json lists each eye material's nodes (images, UV maps, ramps, mapping nodes), its
links, the eye polygons' UV range and bounding box.  --dump-textures also writes the images the eye
materials use (packed or not) next to it.  Nothing is saved back into the blend.
"""
import argparse
import json
import math
import os
import re
import sys

import bpy
import mathutils


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="")
    ap.add_argument("--material-re", default=r"eye(?!brow|lash|lid)")
    ap.add_argument("--dump-textures", action="store_true")
    return ap.parse_args(argv)


def val(sock):
    v = getattr(sock, "default_value", None)
    try:
        return [round(x, 4) for x in v]
    except TypeError:
        return round(v, 4) if isinstance(v, float) else v


def describe(material, out, tag, dump):
    info = {"blend_method": material.blend_method, "nodes": [], "links": []}
    if not (material.use_nodes and material.node_tree):
        return info
    for n in material.node_tree.nodes:
        d = {"type": n.type, "name": n.name}
        if n.type == "TEX_IMAGE" and n.image:
            img = n.image
            d.update(image=img.name, size=list(img.size), packed=bool(img.packed_file),
                     colorspace=img.colorspace_settings.name, extension=n.extension)
            if dump:
                dst = os.path.join(out, "%s__%s" % (tag, re.sub(r"[^\w.-]", "_", img.name)))
                data = bytes(img.packed_file.data) if img.packed_file else open(bpy.path.abspath(img.filepath), "rb").read()
                open(dst if os.path.splitext(dst)[1] else dst + ".png", "wb").write(data)
        elif n.type == "VALTORGB":
            d["ramp"] = [(round(e.position, 4), [round(c, 3) for c in e.color]) for e in n.color_ramp.elements]
        elif n.type == "MAPPING":
            d["inputs"] = {s.name: val(s) for s in n.inputs if not s.is_linked}
        elif n.type == "UVMAP":
            d["uv"] = n.uv_map
        info["nodes"].append(d)
    info["links"] = ["%s.%s -> %s.%s" % (l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name)
                     for l in material.node_tree.links]
    return info


def main():
    a = args()
    os.makedirs(a.out, exist_ok=True)
    tag = a.tag or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    eye_re = re.compile(a.material_re, re.IGNORECASE)
    eye_mats = [m for m in bpy.data.materials if eye_re.search(m.name)]
    report = {"blend": bpy.data.filepath, "materials": {m.name: describe(m, a.out, tag, a.dump_textures) for m in eye_mats},
              "objects": []}
    pts = []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        idx = {i for i, s in enumerate(o.material_slots) if s.material in eye_mats}
        if not idx:
            continue
        me = o.data
        polys = [p for p in me.polygons if p.material_index in idx]
        verts = {v for p in polys for v in p.vertices}
        pts += [o.matrix_world @ me.vertices[v].co for v in verts]
        uv = me.uv_layers.active.data if me.uv_layers else None
        uvs = [uv[li].uv for p in polys for li in p.loop_indices] if uv else []
        report["objects"].append({"name": o.name, "eye_vertices": len(verts), "uv_layers": [l.name for l in me.uv_layers],
                                  "uv_min": [round(min(u[k] for u in uvs), 4) for k in (0, 1)] if uvs else None,
                                  "uv_max": [round(max(u[k] for u in uvs), 4) for k in (0, 1)] if uvs else None})
    if pts:
        lo = mathutils.Vector([min(p[k] for p in pts) for k in range(3)])
        hi = mathutils.Vector([max(p[k] for p in pts) for k in range(3)])
        c, size = (lo + hi) / 2, max(hi - lo)
        report["eye_bbox"] = [[round(x, 4) for x in lo], [round(x, 4) for x in hi]]
        head = None
        for arm in (o for o in bpy.data.objects if o.type == "ARMATURE"):
            bone = arm.data.bones.get("C_Head_a") or next((b for b in arm.data.bones if b.name.lower().startswith("c_head")), None)
            if bone:
                head = arm.matrix_world @ bone.head_local
                break
        fwd = c - (head if head is not None else c - mathutils.Vector((0, 1, 0)) * size)
        fwd.z = 0
        fwd.normalize()
        up = mathutils.Vector((0, 0, 1))
        side = fwd.cross(up)
        width = max(abs((hi - lo).dot(side)), size) * 1.45
        for o in bpy.data.objects:
            if o.type == "LIGHT":
                o.hide_render = True
        scn = bpy.context.scene
        cam = bpy.data.objects.new("eye_cam", bpy.data.cameras.new("eye_cam"))
        cam.data.lens, cam.data.sensor_width, cam.data.clip_start = 100, 36, size * 0.01
        scn.collection.objects.link(cam)
        cam.location = c + fwd * (width * cam.data.lens / cam.data.sensor_width)
        cam.rotation_euler = (-fwd).to_track_quat("-Z", "Y").to_euler()
        scn.camera = cam
        sun = bpy.data.objects.new("eye_key", bpy.data.lights.new("eye_key", "SUN"))
        sun.data.energy = 3.0
        scn.collection.objects.link(sun)
        key = (-fwd * math.cos(math.radians(35)) - up * math.sin(math.radians(35)) + side * 0.25).normalized()
        sun.rotation_euler = key.to_track_quat("-Z", "Y").to_euler()
        if scn.world is None:
            scn.world = bpy.data.worlds.new("eye_world")
        scn.world.use_nodes = True
        bg = next((n for n in scn.world.node_tree.nodes if n.type == "BACKGROUND"), None)   # node names may be Chinese
        if bg:
            for link in list(bg.inputs[0].links):
                scn.world.node_tree.links.remove(link)
            bg.inputs[0].default_value = (0.35, 0.35, 0.35, 1)
            bg.inputs[1].default_value = 1.0
        scn.render.engine = "BLENDER_EEVEE"
        scn.eevee.taa_render_samples = 32
        scn.eevee.use_ssr = scn.eevee.use_ssr_refraction = True
        scn.view_settings.view_transform = "Standard"
        scn.render.resolution_x, scn.render.resolution_y, scn.render.resolution_percentage = 1400, 520, 100
        scn.render.image_settings.file_format, scn.render.image_settings.color_mode = "PNG", "RGB"
        scn.render.filepath = os.path.join(a.out, "%s_eyes.png" % tag)
        bpy.ops.render.render(write_still=True)
        report["render"] = scn.render.filepath
    with open(os.path.join(a.out, "%s_eyes.json" % tag), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print("EYE_CLOSEUP=" + json.dumps({"tag": tag, "materials": len(eye_mats), "render": report.get("render")}))


main()
