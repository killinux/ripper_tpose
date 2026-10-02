"""Catch-up fixes for suit / nude-base .blends built before 2026-10-01, run in front of
hq_materials_blender.py in the same Blender session (the HQ step then upgrades what this filled in,
packs the images and saves):

  * i / j lash and brow cards: the add-on before v1.1.16 left them transparent - their texture is in
    another family's bundle (i -> pc_h_nk_eyebrow, j -> pc_d_nk_eyebrow); rebuilt with the add-on's own
    stroke_mat from a sibling family export (D:/roe_exports/d01/_textures ...)
  * fm ears (FMRear_L / FMRear_R): the suit stub points their renderer at pc_f01_fm_nk_face in
    chara_mat_bare_pc_f01_fm_nk.ab, a bundle the suit build does not read, so they came out flat grey;
    they get the suit's own face material (every family's face atlas has the same layout, pointed-ear
    paint included)
  * every common fm piece (ears, both pairs of horns, halo, arm fur, cuff, leg rings, leg fur) sat where it
    sits on f01, whatever the character - the meshes are modelled on f01's body (its head is 15-20 cm lower
    than most): moved by its carrier bone's offset from f01 and parented to that bone (2026-10-02; the
    10-01 version moved only the ears, which hung at the collar bones)
  * a piece slot whose game material is the character's hair (j01 idol LDoubleBun / RDoubleBun slot 1
    -> pc_j_nk_hair in chara_mat_bare_pc_j_common_head.ab, also unread): the hair mesh's material
  * skinned pieces left with no vertex group (their own bones never reached the skeleton: a01 marry Veil,
    j01 2025_newyear earrings, j01 defeatgod veil): weighted to their area bone from suit.json
  * an fm body (e01 / f01 / g01 fm suits and fm nude bases) given the family's face / hair textures instead of
    its own pc_<id>_fm_nk_face / _hair (f01's fm horns, painted in the face atlas, came out black): swapped
  * a nude body without the roe_nude_slots marker the add-on's XPS export reads: marked

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
# f01's rest positions of the bones the common fm pieces hang from (D:/roe_exports/f01/blend/pc_f01_fm.blend):
# the pieces are modelled on f01's body
F01_BONES = {
    "Bip001 Head": (0.0, -0.03079, 1.39281),
    "Bip001 L UpperArm": (0.13002, 0.014, 1.26547), "Bip001 R UpperArm": (-0.13002, 0.014, 1.26547),
    "Bip001 L Forearm": (0.30812, 0.01328, 1.26112), "Bip001 R Forearm": (-0.30812, 0.01327, 1.26112),
    "Bip001 L Thigh": (0.08464, -0.033, 0.872), "Bip001 R Thigh": (-0.08464, -0.033, 0.872),
    "Bip001 L Calf": (0.08138, -0.01601, 0.50388), "Bip001 R Calf": (-0.08138, -0.01601, 0.50388),
    "Bip001 CalfSub_L": (0.09139, 0.00875, 0.3504), "Bip001 CalfSub_R": (-0.09139, 0.00875, 0.3504),
}
# fm piece (object-name prefix) -> the bone that carries it (%s = L / R, the side the piece is on)
FM_CARRIERS = {"FMRear": "Bip001 Head", "FMMhorn": "Bip001 Head", "FMRhorn": "Bip001 Head",
               "FMLhead": "Bip001 Head", "FMMarmhair": "Bip001 %s Forearm", "FMRcuff": "Bip001 %s UpperArm",
               "FMLlegring": "Bip001 %s Thigh", "FMRlegring": "Bip001 %s Thigh",
               "FMLcalfring": "Bip001 CalfSub_%s", "FMMleghair": "Bip001 CalfSub_%s"}
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


def fix_fm_placement(meshes):
    """Every common fm (魔化) piece sat where it sits on f01, whatever the character: the build reads these
    bone-parented props in a frame that does not follow the skeleton, and the meshes are modelled on f01's body.
    On a taller character (c01's head is 20 cm higher, her thighs 18 cm) the ram horns hung at the neck, the red
    horns at the temples, the halo round the face and the rings low on the limbs; 10-01 moved only the ears.
    Each piece now moves by its carrier bone's offset from f01 (head, upper arm, forearm, thigh, calf) and is
    parented to that bone - the horns no longer ride the cheek / lip bones the expressions move.  Marked
    roe_fm_moved; ears the 10-01 version already moved (parented to Bip001 Head) count as done."""
    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE" and "Bip001 Head" in o.data.bones), None)
    if arm is None:
        return []
    done = []
    for obj in meshes:
        prefix = next((p for p in FM_CARRIERS if obj.name.startswith(p)), None)
        if prefix is None or obj.parent is not arm or obj.parent_type != "BONE" or "roe_fm_moved" in obj:
            continue
        if prefix == "FMRear" and obj.parent_bone == "Bip001 Head":
            obj["roe_fm_moved"] = "10-01"
            continue
        world = obj.matrix_world.copy()
        verts = obj.data.vertices
        side = "L" if sum((world @ v.co).x for v in verts) > 0 else "R"
        bone = FM_CARRIERS[prefix] % side if "%s" in FM_CARRIERS[prefix] else FM_CARRIERS[prefix]
        if bone not in arm.data.bones:                       # no calf helper bone: the calf itself
            bone = bone.replace("CalfSub_%s" % side, "%s Calf" % side)
        if bone not in arm.data.bones or bone not in F01_BONES:
            continue
        delta = arm.matrix_world @ arm.data.bones[bone].head_local - Vector(F01_BONES[bone])
        world.translation += delta
        obj.parent_bone = bone
        bpy.context.view_layer.update()
        obj.matrix_world = world
        obj["roe_fm_moved"] = [round(x, 4) for x in delta]
        done.append("%s +%.3f m -> %s" % (obj.name, delta.length, bone))
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
    bone (suit.json area_bone, Bip001 Head for all four): it follows rigidly, without its own sway.
    Since 2026-10-02 the assembler binds such pieces itself (import_suit_part, "bound_to"); this is for files
    built before."""
    parts, done = suit_parts(), []
    for obj in meshes:
        arm = next((m.object for m in obj.modifiers if m.type == "ARMATURE" and m.object), None)
        bone = (parts.get(obj.name) or {}).get("area_bone")
        if obj.vertex_groups or arm is None or not bone or bone not in arm.data.bones:
            continue
        obj.vertex_groups.new(name=bone).add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
        done.append("%s -> %s" % (obj.name, bone))
    return done


def slot_albedo(addon, mat):
    """The colour texture's name without extension / .001: the game-material node or the add-on's Base Color."""
    node = mat.node_tree.nodes.get("hq_albedo") if mat and mat.use_nodes else None
    image = node.image if node is not None and node.image else (addon.diffuse_image(mat) if mat else None)
    return re.sub(r"(\.png)?(\.\d{3})?$", "", image.name, flags=re.IGNORECASE) if image else ""


def fix_fm_body_textures(addon, meshes):
    """An fm body (pc_e01_fm_nk / pc_f01_fm_nk / pc_g01_fm_nk: the base of those characters' fm suits and the fm
    nude bases) has its own face and hair atlases in the game (pc_<id>_fm_nk_face / _hair: redder skin, the fm
    body's own horns painted navy where they map, lighter hair), but the add-on gives every body of a family the
    family's shared head textures (pc_f_nk_face, pc_f_nk_hair): f01's fm horns came out grey-beige, black with
    the game materials.  A face / hair slot still on the family texture gets an albedo material on the fm one,
    which the game-material step that follows upgrades to pc_<id>_fm_nk_face / _hair."""
    body = next((re.match(r"pc_([a-z])(\d+)_fm_nk_body", o.name) for o in meshes
                 if re.match(r"pc_([a-z])(\d+)_fm_nk_body", o.name)), None)
    if body is None:
        return []
    family, cid = body.group(1), body.group(1) + body.group(2)
    done = []
    for obj in meshes:          # the fm body, its hair, and the fm ears that borrowed the face material
        if not re.match(r"pc_%s_fm_nk_(body|hair)|FMRear_" % cid, obj.name):
            continue
        for index, slot in enumerate(obj.material_slots):
            albedo = slot_albedo(addon, slot.material).lower()
            role = next((r for r in ("face", "hair") if albedo == "pc_%s_nk_%s_rgbx_albedo" % (family, r)), None)
            if role is None:
                continue
            tex = os.path.join(EXPORT_ROOT, cid, "_textures", "pc_%s_fm_nk_%s_rgbx_Albedo.png" % (cid, role))
            if not os.path.isfile(tex):
                continue                                   # g01's fm body has no face of its own
            old = slot.material
            slot.material = addon.albedo_mat(role, tex, desat=False)
            done.append("%s[%d] %s -> %s" % (obj.name, index, old.name, os.path.basename(tex)))
    return done


def fix_nude_marker(meshes):
    """The nude worker marks its split body (slot 0 body, 1 face, 2 eye, 3 lash, 4 brow) with roe_nude_slots,
    and the add-on's XPS export reads that marker to name and group the slots: without it slot 0 went out as
    the face, the face as the eye and the brows were dropped.  Eight nude bases were saved without it (c01 d01
    f01 f01_fm g01_fm k01 l01 m01) and once their slots carry the game materials the names the add-on sniffs
    instead (body / face / eye) are gone: a body mesh whose eye slot is 2 gets the marker."""
    done = []
    for obj in meshes:
        if obj.get("roe_nude_slots") or "_nk_body" not in obj.name:
            continue
        names = [re.sub(r"\.\d{3}$", "", s.material.name) if s.material else "" for s in obj.material_slots]
        if len(names) >= 5 and names[2] == "eye":
            obj["roe_nude_slots"] = 1
            done.append(obj.name)
    return done


def main():
    addon = load_addon()
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    log = []
    report = {"file": bpy.data.filepath, "lashes": fix_lashes(addon, meshes, log),
              "borrowed": fix_borrowed(meshes, log), "fm_pieces": fix_fm_placement(meshes),
              "unweighted": fix_unweighted_pieces(meshes), "nude_marker": fix_nude_marker(meshes),
              "fm_body": fix_fm_body_textures(addon, meshes), "problems": log}
    print("ROE_SUIT_FIX=" + json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":      # export_suit_xps_blender.py imports fix_nude_marker
    main()
