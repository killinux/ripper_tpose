"""XPS for an assembled suit / nude-base .blend (export_suits.py, then hq_materials_blender.py), through the
batch's own XPS export: export_character_model_blender.export_xps -> the ROE add-on's 3. 导出 XPS operator
(eye baked to a PNG, the head split by slot, render groups, every texture copied beside the .mesh), so a suit's
XPS matches a dressed character's: game-material slots get render group 24 (25 with alpha) with diffuse x
colour, AO lightmap, bump and specular (the maps hq_materials_blender.py recorded as roe_hq_xps).

What a suit needs on top of the batch:
  * pieces parented to a bone (rings, horns, ears, glasses ...) are skinned 100 % to that bone first (XPS
    stores vertex weights, not object parents) - the same helper as export_suit_pmx_blender.py
  * see-through pieces keep their alpha: the add-on writes every non-hair slot of a ROE model opaque
    (render group 5, body atlases carry junk alpha); here a piece whose material is not opaque AND whose
    diffuse really is see-through where its UVs land (>= 2 % of the surface below alpha 0.9: veils,
    sheer stockings, fishnet, lace) gets render group 7 -> 25.  Body, face and hair keep the add-on's rule.
  * the procedural eye is baked from the iris image; a packed iris whose file is gone is written to a temp
    file first (the bake reads a file)

  blender -b --factory-startup <suit.blend> --python export_suit_xps_blender.py -- <out.mesh>
The .blend is not saved.  Prints ROE_SUIT_XPS={json} (read back with XNALaraMesh: mesh names = render group,
textures) and writes <out>.report.json.
"""
import importlib
import json
import os
import re
import sys
import tempfile

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import export_character_model_blender as worker  # noqa: E402
from export_suit_pmx_blender import skin_bone_parented  # noqa: E402
from fix_suit_slots_blender import fix_nude_marker  # noqa: E402

ADDON = os.path.join(HERE, "roe_xps_addon.py")
ALPHA_SHARE = 0.02          # share of the piece's surface that must be see-through (alpha < 0.9)
SAMPLES = 20000


def texture_dir(blend):
    """The character's extracted textures (<exports>\\<cid>\\_textures): where the add-on looks for the iris.
    Left empty, its search would glob the working directory recursively."""
    cid = re.match(r"pc_([a-z]\d+)", os.path.basename(blend))
    if not cid:
        return ""
    up = os.path.dirname(os.path.dirname(os.path.abspath(blend)))   # <exports>\<cid> (suit) / <exports> (nude base)
    for path in (os.path.join(up, "_textures"), os.path.join(up, cid.group(1), "_textures")):
        if os.path.isdir(path) and os.path.basename(os.path.dirname(path)).lower() == cid.group(1):
            return path
    return ""


def readable_iris(head):
    """The eye slot's iris image must exist as a file for the bake; write a packed one out if its file is gone.
    Returns the temp path to remove afterwards (or None)."""
    eye = next((s.material for s in (head.material_slots if head else [])
                if s.material and re.sub(r"\.\d{3}$", "", s.material.name) == "eye"), None)
    if eye is None or not eye.use_nodes:
        return None
    image = next((n.image for n in eye.node_tree.nodes if n.type == "TEX_IMAGE" and n.image), None)
    if image is None or os.path.isfile(bpy.path.abspath(image.filepath)) or not image.packed_file:
        return None
    temp = os.path.join(tempfile.gettempdir(), "roe_suit_xps_iris_%d.png" % os.getpid())
    with open(temp, "wb") as handle:
        handle.write(image.packed_file.data)
    image.filepath = temp
    return temp


class AlphaRule:
    """Wraps the add-on's roe_xps_render_group: a non-opaque piece whose diffuse is really see-through on its
    own UVs gets render group 7 (alpha) instead of 5."""

    def __init__(self, addon):
        self.addon = addon
        self.original = addon.roe_xps_render_group
        self.alpha = {}
        self.decisions = {}
        addon.roe_xps_render_group = self

    def restore(self):
        self.addon.roe_xps_render_group = self.original

    def image_alpha(self, material):
        maps = self.addon.hq_export_maps(material)
        image = (bpy.data.images.load(maps["diffuse"], check_existing=True) if maps.get("diffuse")
                 else self.addon.diffuse_image(material))
        if image is None:
            return None, ""
        key = image.name
        if key not in self.alpha:
            width, height = image.size
            channels = image.channels
            if not width or not height or channels != 4:
                self.alpha[key] = None          # no alpha channel: opaque
            else:
                pixels = np.empty(width * height * channels, dtype=np.float32)
                image.pixels.foreach_get(pixels)
                self.alpha[key] = (pixels[3::4].reshape(height, width) * 255).astype(np.uint8)
        return self.alpha[key], os.path.basename(bpy.path.abspath(image.filepath)) or image.name

    @staticmethod
    def covered_share(obj, slot_index, alpha):
        """Share of the slot's UV area whose texel alpha is below 0.9 (area-weighted random samples)."""
        mesh = obj.data
        if not mesh.uv_layers:
            return None
        mesh.calc_loop_triangles()
        count = len(mesh.loop_triangles)
        loops = np.empty(count * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("loops", loops)
        mats = np.empty(count, dtype=np.int32)
        mesh.loop_triangles.foreach_get("material_index", mats)
        uv = np.empty(len(mesh.loops) * 2, dtype=np.float32)
        mesh.uv_layers[0].data.foreach_get("uv", uv)
        tri = uv.reshape(-1, 2)[loops.reshape(-1, 3)[mats == slot_index]]          # (n, 3, 2)
        if not len(tri):
            return None
        a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
        area = np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))
        if area.sum() <= 0:
            return None
        rng = np.random.default_rng(0)
        pick = rng.choice(len(tri), SAMPLES, p=area / area.sum())
        r1, r2 = np.sqrt(rng.random(SAMPLES)), rng.random(SAMPLES)
        p = (1 - r1)[:, None] * a[pick] + (r1 * (1 - r2))[:, None] * b[pick] + (r1 * r2)[:, None] * c[pick]
        height, width = alpha.shape
        x = (np.floor(np.mod(p[:, 0], 1.0) * width).astype(np.int64)) % width
        y = (np.floor(np.mod(p[:, 1], 1.0) * height).astype(np.int64)) % height
        return float(np.mean(alpha[y, x] < 230))

    def __call__(self, obj, slot_index, material):
        group = self.original(obj, slot_index, material)
        if group != "5" or material is None or material.blend_method == "OPAQUE":
            return group
        alpha, image = self.image_alpha(material)
        share = self.covered_share(obj, slot_index, alpha) if alpha is not None else None
        label = "%s[%d]" % (obj.name, slot_index)
        self.decisions[label] = {"material": material.name, "blend": material.blend_method, "image": image,
                                 "see_through": None if share is None else round(share, 4)}
        if share is not None and share >= ALPHA_SHARE:
            self.decisions[label]["group"] = "7"
            return "7"
        return group


def read_back(path):
    """Mesh names (render group_name_spec), vertex counts and textures as XNALaraMesh reads them."""
    for module in ("XNALaraMesh-master", "XNALaraMesh"):
        try:
            reader = importlib.import_module(module + ".read_bin_xps")
            break
        except ImportError:
            continue
    else:
        return {"error": "XNALaraMesh reader not found"}
    data = reader.readXpsModel(path)
    folder = os.path.dirname(path)
    meshes = [{"name": m.name, "verts": len(m.vertices), "textures": [t.file for t in m.textures]} for m in data.meshes]
    textures = sorted({t for m in meshes for t in m["textures"]})
    return {"bones": len(data.bones), "meshes": meshes,
            "missing_textures": [t for t in textures if not os.path.isfile(os.path.join(folder, os.path.basename(t)))],
            "unweighted_vertices": sum(1 for m in data.meshes for v in m.vertices
                                       if not any(w.weight > 0 for w in v.boneWeights))}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv or not argv[0].lower().endswith(".mesh"):
        raise SystemExit("usage: -- <out.mesh>")
    path = os.path.abspath(argv[0])
    addon = worker.load_addon(ADDON)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = addon.related_armatures(meshes)
    if len(armatures) != 1:
        raise SystemExit("expected one armature, found %s" % [a.name for a in armatures])
    arm = armatures[0]
    report = {"source": bpy.data.filepath, "skinned_pieces": skin_bone_parented(arm, meshes)}
    unweighted = [o.name for o in meshes if not o.vertex_groups]
    if unweighted:
        report["unweighted_meshes"] = unweighted        # would follow the root only: reported, not guessed
    props = bpy.context.scene.roe
    props.workflow_mode = "ROE"          # names like pc_b01_nk_body would read as a generic model
    props.apply_scope = "SELECTED"       # every mesh of the file (export_xps selects them), not an import batch
    props.tex_dir = texture_dir(bpy.data.filepath)
    head = addon.find_head(meshes)
    report["head"] = head.name if head else None
    report["nude_marker"] = fix_nude_marker(meshes)      # a file saved before fix_suit_slots_blender.py set it
    temp = readable_iris(head)
    rule = AlphaRule(addon)
    try:
        worker.export_xps(addon, path, meshes, armatures)
    finally:
        rule.restore()
        if temp and os.path.isfile(temp):
            os.remove(temp)
    report["alpha_pieces"] = sorted(k for k, v in rule.decisions.items() if v.get("group") == "7")
    report["alpha_checked"] = rule.decisions
    report["read_back"] = read_back(path)
    report["files"] = len(os.listdir(os.path.dirname(path)))
    with open(os.path.splitext(path)[0] + ".report.json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1, default=str)
    back = report["read_back"]
    summary = {"xps": path, "bytes": os.path.getsize(path), "skinned": len(report["skinned_pieces"]),
               "unweighted_meshes": unweighted, "alpha_pieces": report["alpha_pieces"],
               "meshes": len(back.get("meshes", [])), "bones": back.get("bones"),
               "missing_textures": back.get("missing_textures"), "unweighted_vertices": back.get("unweighted_vertices"),
               "groups": sorted({m["name"].split("_", 1)[0] for m in back.get("meshes", [])})}
    print("ROE_SUIT_XPS=" + json.dumps(summary, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
