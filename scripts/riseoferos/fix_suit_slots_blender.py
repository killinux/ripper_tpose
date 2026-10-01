"""Catch-up fixes for suit / nude-base .blends built before 2026-10-01, run in front of
hq_materials_blender.py in the same Blender session (the HQ step then upgrades what this filled in,
packs the images and saves):

  * i / j lash and brow cards: the add-on before v1.1.16 left them transparent - their texture is in
    another family's bundle (i -> pc_h_nk_eyebrow, j -> pc_d_nk_eyebrow); rebuilt with the add-on's own
    stroke_mat from a sibling family export (D:/roe_exports/d01/_textures ...)
  * fm ears (FMRear_L / FMRear_R): the suit stub points their renderer at pc_f01_fm_nk_face in
    chara_mat_bare_pc_f01_fm_nk.ab, a bundle the suit build does not read, so they came out flat grey;
    they get the suit's own face material (every family's face atlas has the same layout, pointed-ear
    paint included).  Their vertices are modelled in f01's space (its head is 15 cm lower than most), so
    on any other character they hung at the collar bones: moved by the head-bone offset and parented to
    Bip001 Head, as on f01
  * a piece slot whose game material is the character's hair (j01 idol LDoubleBun / RDoubleBun slot 1
    -> pc_j_nk_hair in chara_mat_bare_pc_j_common_head.ab, also unread): the hair mesh's material
  * skinned pieces left with no vertex group (their own bones never reached the skeleton: a01 marry Veil,
    j01 2025_newyear earrings, j01 defeatgod veil): weighted to their area bone from suit.json

A borrowed HQ material is copied with its UV Map / Normal Map nodes pointed at the piece's own first UV
layer (suit pieces call it UVMap, the FBX body / hair UV0).

  blender -b --factory-startup <x.blend> --python fix_suit_slots_blender.py \
          --python hq_materials_blender.py -- <x.blend> [--preview]

Prints ROE_SUIT_FIX={json}.
"""
import importlib.util
import json
import os
import re

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
# f01's Bip001 Head rest position (D:/roe_exports/f01/blend/pc_f01_fm.blend), the space the fm ears are
# modelled in
F01_HEAD = Vector((0.0, -0.03079, 1.39281))
EXPORT_ROOT = os.environ.get("ROE_EXPORTS", r"D:\roe_exports")
# pieces whose slot borrows the character's face / hair material (game material resolved by hand from
# the renderer's PPtr, see the docstring): object-name prefix -> (slot index, role)
BORROWED = {"FMRear_": (0, "face"), "LDoubleBun": (1, "hair"), "RDoubleBun": (1, "hair")}


def load_addon():
    spec = importlib.util.spec_from_file_location("roe_fix_addon", os.path.join(HERE, "roe_xps_addon.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def has_image(mat):
    return bool(mat and mat.use_nodes and any(n.type == "TEX_IMAGE" and n.image for n in mat.node_tree.nodes))


def first_uv(obj):
    return obj.data.uv_layers[0].name if len(obj.data.uv_layers) else "UVMap"


def for_mesh(mat, obj):
    """`mat`, or a copy of it that samples `obj`'s own first UV layer."""
    uv = first_uv(obj)
    nodes = [n for n in mat.node_tree.nodes if n.type in {"UVMAP", "NORMAL_MAP"} and n.uv_map] \
        if mat.use_nodes else []
    if all(n.uv_map == uv for n in nodes):
        return mat
    name = "%s__%s" % (mat.name, uv)
    copy = bpy.data.materials.get(name)
    if copy is None:
        copy = mat.copy()
        copy.name = name
        for n in copy.node_tree.nodes:
            if n.type in {"UVMAP", "NORMAL_MAP"} and n.uv_map:
                n.uv_map = uv
    return copy


def body_mesh(meshes):
    return next((o for o in meshes if re.search(r"pc_[a-z]\d+(_fm)?_nk_body", o.name)), None)


def role_material(meshes, role):
    """The face material of the body mesh / the hair mesh's material (HQ or the add-on's)."""
    want = re.compile(r"(^|_)nk_%s$|^%s$" % (role, role))
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is not None and want.search(re.sub(r"\.\d{3}$", "", mat.name)) and has_image(mat):
                return mat
    return None


def fix_lashes(addon, meshes, log):
    body = body_mesh(meshes)
    m = re.search(r"pc_([a-z])(\d+)", body.name) if body else None
    if not m or m.group(1) not in addon.EYEBROW_TEXTURE_FAMILY:
        return []
    family = addon.EYEBROW_TEXTURE_FAMILY[m.group(1)]
    tex_dir = os.path.join(EXPORT_ROOT, m.group(1) + m.group(2), "_textures")
    done = []
    for name in ("lash", "brow"):
        old = next((s.material for s in body.material_slots
                    if s.material and re.sub(r"\.\d{3}$", "", s.material.name) == name), None)
        if old is None or has_image(old):
            continue
        tex = addon.find_family_tex(tex_dir, family, "pc_%s_nk_eyebrow*Albedo*.png" % family)
        if not tex:
            log.append("no pc_%s_nk_eyebrow texture next to %s" % (family, tex_dir))
            return done
        old.name = name + "__transparent_old"          # stroke_mat removes a material of its name
        if name == "lash":
            new = addon.stroke_mat(name, tex, addon.LASH_ALPHA_GAIN, addon.LASH_DARKEN)
        else:
            new = addon.stroke_mat(name, tex)
        old.user_remap(new)
        bpy.data.materials.remove(old)
        done.append("%s <- %s" % (name, os.path.basename(tex)))
    return done


def fix_borrowed(meshes, log):
    done = []
    for obj in meshes:
        hit = next(((index, role) for prefix, (index, role) in BORROWED.items() if obj.name.startswith(prefix)),
                   None)
        if hit is None or hit[0] >= len(obj.material_slots):
            continue
        index, role = hit
        slot = obj.material_slots[index]
        if has_image(slot.material):
            continue
        mat = role_material(meshes, role)
        if mat is None:
            log.append("%s[%d]: no %s material in the file" % (obj.name, index, role))
            continue
        old = slot.material
        slot.material = for_mesh(mat, obj)
        done.append("%s[%d] %s -> %s" % (obj.name, index, old.name if old else None, slot.material.name))
        if old is not None and old.users == 0:
            bpy.data.materials.remove(old)
    return done


def fix_ear_placement(meshes):
    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE" and "Bip001 Head" in o.data.bones), None)
    if arm is None:
        return []
    delta = arm.matrix_world @ arm.data.bones["Bip001 Head"].head_local - F01_HEAD
    done = []
    for obj in meshes:
        if not obj.name.startswith("FMRear_") or obj.parent is not arm or obj.parent_bone == "Bip001 Head":
            continue
        world = obj.matrix_world.copy()
        world.translation += delta
        obj.parent_bone = "Bip001 Head"
        bpy.context.view_layer.update()
        obj.matrix_world = world
        done.append("%s +%.3f m -> Bip001 Head" % (obj.name, delta.length))
    return done


def suit_parts():
    """{object name: part record} from the suit build's suit.json (export_suits.py); {} for other files."""
    m = re.match(r"pc_([a-z]\d+)_(.+)$", os.path.splitext(os.path.basename(bpy.data.filepath))[0])
    path = os.path.join(EXPORT_ROOT, "_suits", m.group(1), m.group(2), "suit.json") if m else ""
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return {re.sub(r"_obj001$", "", p["root"]): p for p in json.load(handle).get("parts", [])}


def fix_unweighted_pieces(meshes):
    """A skinned piece whose own bones the suit build could not hang on the skeleton (a01 marry Veil, j01
    2025_newyear NYearring_L / _R, j01 defeatgod veil: their bones' ancestors are the piece's own objects) has an
    armature modifier but no vertex group, so it stays put when the head turns.  Weighted 100 % to its area
    bone (suit.json area_bone, Bip001 Head for all four): it follows rigidly, without its own sway."""
    parts, done = suit_parts(), []
    for obj in meshes:
        arm = next((m.object for m in obj.modifiers if m.type == "ARMATURE" and m.object), None)
        bone = (parts.get(obj.name) or {}).get("area_bone")
        if obj.vertex_groups or arm is None or not bone or bone not in arm.data.bones:
            continue
        obj.vertex_groups.new(name=bone).add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
        done.append("%s -> %s" % (obj.name, bone))
    return done


def main():
    addon = load_addon()
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    log = []
    report = {"file": bpy.data.filepath, "lashes": fix_lashes(addon, meshes, log),
              "borrowed": fix_borrowed(meshes, log), "ears": fix_ear_placement(meshes),
              "unweighted": fix_unweighted_pieces(meshes), "problems": log}
    print("ROE_SUIT_FIX=" + json.dumps(report, ensure_ascii=True))


main()
