# -*- coding: utf-8 -*-
"""HoneySelect 2 card .blend (export_card.py / the archive) -> MMD .pmx, inside Blender 3.6 (headless).

The Stellar Blade chain (scripts/stellarblade/export_pmx_blender.py -> the Rise of Eros worker: Convert_to_MMD5
builds the MMD skeleton, body colliders and twist bones, mmd_cloth_physics the hair / skirt chains, blender2xps
bakes node colours into one texture per material, mmd_tools writes the PMX at 12.5).  The Illusion rig is not a
3ds Max Biped, so this file does what the Biped resolver did and a little more:

  * slots: cf_J_Hips = 全ての親's source (Biped's Bip001 sits at the hips too), cf_J_Kosi01 = 下半身,
    cf_J_Spine01..03 = 上半身 / 上半身2 / 上半身3, cf_J_Neck, cf_J_Head, cf_J_Shoulder / ArmUp00 / ArmLow01 / Hand,
    cf_J_LegUp00 / LegLow01 / Foot01 / Toes01, the fingers Thumb / Index / Middle / Ring / Little 01..03,
    cf_J_eye_rs = the eyes (they carry the eyeballs), cf_J_Mune00 = the breasts.  _L is the character's left;
  * the joints carry no skin: Illusion skins the body on scale / damping helpers that a game script drives
    (cf_J_ArmUp01_s, cf_J_LegUp02_s, cf_J_Spine02_s, cf_J_Mune02_s, cf_J_Siri_s ...).  Each helper's weight goes to
    the slot bone above it - for the arms Convert_to_MMD5's own twist split then spreads 腕 / ひじ over 腕捩 / 手捩 -
    except the knee and elbow pads (cf_J_LegKnee_*, cf_J_ArmElbo*), which the ROE helper planner measures and
    grants a share of the joint.  Face bones go to 頭 (the expressions are the game's blend shapes), the breast's
    sub-bones to cf_J_Mune00, accessories to the bone above them; bones left without skin are removed (a slot's
    children then hang on the slot above: the foot on the calf, the thigh on 下半身);
  * hair: the scalp bones (c_J_hair*_top) go to 頭, the strands (c_J_hair_*) and skirt chains (cf_J_sk_*) stay
    for mmd_cloth_physics; no other cf_J_ bone may become cloth;
  * expressions: the game's blend shapes - e* eyes, g* brows, k* mouth, on the head, the lashes and the tear film
    alike - are mixed into the standard MMD set by RECIPES on every mesh that has them, so one PMX morph moves all
    of them; the teeth and the tongue have only open levels (k01_open0 / k02_open1 / k03_open2), and the game pairs
    open1 with open1, so each mouth morph opens them as far as its own jaw drop (TEETH_RATIO); the raw shapes are
    exported too (panel その他);
  * hair strands hang on ONE bone each (c_J_hair_FRa_01 ...; the game's DynamicBone swings it) and
    mmd_cloth_physics needs two at least, so each strand is split into a chain along the skin it carries
    (STRAND_SEGMENT per bone, the weights spread between neighbours);
  * baking: hair cards and accessories use tiled UVs (-2.99 .. 1.07) and a bake only fills 0..1, so they came out
    empty and were hidden as "fully transparent"; each face of the first UV layer is moved by whole tiles into 0..1
    (the textures repeat, so every texel stays the same) - the PMX keeps these UVs.  The lashes' alpha is
    min(R, G, B) x A in the card .blend, but their mask has only a red channel (G = B = 0, the lashes vanished):
    such a mask's MINIMUM nodes become MAXIMUM.  blender2xps bakes a material with the FIRST object that uses it,
    so a material shared by several objects baked only that object's UV islands - the front hair's four card meshes
    share one material and the bangs came out nearly empty; objects sharing a material are joined first (meshes
    with shape keys stay apart: the face meshes share no material);
  * texture alpha after the write (scripts/pmx_tools/texture_alpha_blender.py): MMD multiplies it in, so the
    textures only OPAQUE materials use get alpha 1 (a bake leaves the space between UV islands at 0).

blender -b --factory-startup <card>.blend --python export_pmx_blender.py -- --out <dir> [--name N]
    [--model-name M] [--comment C]
Prints HS2_PMX={json}; writes <out>/<name>/<name>.pmx + textures/ + <name>_converted.blend + <name>_report.json.
"""
import argparse
import importlib.util
import json
import os
import re
import sys

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SB_SCRIPT = os.path.join(REPO, "scripts", "stellarblade", "export_pmx_blender.py")
sys.path.insert(0, os.path.join(REPO, "scripts", "pmx_tools"))
from texture_alpha_blender import fix_texture_alpha, source_alpha_modes  # noqa: E402
SUIT_SCRIPT = os.path.join(REPO, "scripts", "riseoferos", "export_suit_pmx_blender.py")

SIDES = (("left", "L"), ("right", "R"))
FINGERS = (("thumb", "Thumb", ("0", "1", "2")), ("index", "Index", ("1", "2", "3")),
           ("middle", "Middle", ("1", "2", "3")), ("ring", "Ring", ("1", "2", "3")),
           ("pinky", "Little", ("1", "2", "3")))
JOINT_PADS = re.compile(r"^cf_J_(?:LegKnee|ArmElbo)")
CLOTH_BONE = re.compile(r"^(?:c_J_hair|cf_J_sk_)", re.IGNORECASE)
SCALP = re.compile(r"^c_J_hair[A-Z]?_top$", re.IGNORECASE)
NOT_CLOTH = r"|^cf_J_(?!sk_)"                     # for mmd_cloth_physics' limb-helper pattern
EYE_MATERIAL = r"|^c_m_eye_\d"

# name, English name, panel, {shape: weight}; a shape counts on every mesh that has it
RECIPES = [
    ("まばたき", "blink", "EYE", {"e01_close": 1.0}),
    ("笑い", "smile", "EYE", {"e04_warai_cl": 1.0}),
    ("ウィンク", "wink", "EYE", {"e10_wink_L": 1.0}),
    ("ウィンク右", "wink_R", "EYE", {"e09_wink_R": 1.0}),
    ("ウィンク２", "wink2", "EYE", {"e03_close_L": 1.0}),
    ("ｳｨﾝｸ２右", "wink2_R", "EYE", {"e02_close_R": 1.0}),
    ("びっくり", "surprised", "EYE", {"e08_odoroki": 1.0}),
    ("じと目", "jito-eye", "EYE", {"e01_close": 0.4}),
    ("はぅ", "close><", "EYE", {"e05_damage": 1.0}),
    ("なごみ", "calm", "EYE", {"e04_warai": 1.0}),
    ("真面目", "serious", "EYEBROW", {"g03_ikari1": 0.5}),
    ("困る", "trouble", "EYEBROW", {"g05_kanasimi1": 1.0}),
    ("にこり", "cheerful", "EYEBROW", {"g01_warai1": 1.0}),
    ("怒り", "anger", "EYEBROW", {"g03_ikari1": 1.0}),
    ("上", "brow_up", "EYEBROW", {"g08_up": 1.0}),
    ("下", "brow_down", "EYEBROW", {"g03_ikari1": 0.7}),
    ("あ", "a", "MOUTH", {"k18_a": 1.0}),
    ("い", "i", "MOUTH", {"k19_i": 1.0}),
    ("う", "u", "MOUTH", {"k20_u": 1.0}),
    ("え", "e", "MOUTH", {"k21_e": 1.0}),
    ("お", "o", "MOUTH", {"k22_o": 1.0}),
    ("にっこり", "smile_mouth", "MOUTH", {"k01_warai1": 1.0}),
    ("にやり", "grin", "MOUTH", {"k02_warai2": 1.0}),
    ("∧", "mouth_∧", "MOUTH", {"k03_kanasimi": 1.0}),
    ("口角上げ", "mouth_corner_up", "MOUTH", {"k01_warai1": 0.6}),
    ("口角下げ", "mouth_corner_down", "MOUTH", {"k03_kanasimi": 0.7}),
    ("口横広げ", "mouth_wide", "MOUTH", {"k19_i": 0.7}),
    ("ワ", "wa", "MOUTH", {"k01_warai1_op": 1.0}),
    ("ぺろっ", "tongue_out", "MOUTH", {"k23_tehepero": 1.0, "k10_tehepero": 1.0}),
]
STRAND_SEGMENT = 0.06       # m of hair per bone when a strand is split into a chain
STRAND_MAX_BONES = 6
OPEN_LEVELS = ("k01_open0", "k02_open1", "k03_open2")
TEETH_RATIO = 1.12          # the head's jaw drop / the teeth's at the same open level (k09_open1 / k02_open1 ...)
TEETH_MESHES = re.compile(r"^o_(tooth|tang)")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sb = load(SB_SCRIPT, "sb_pmx")
sb.BUST["bones"] = (("左胸", "cf_J_Mune00_L"), ("右胸", "cf_J_Mune00_R"))
sb.EYE_MAT_RE = re.compile(sb.EYE_MAT_RE.pattern + EYE_MATERIAL, re.IGNORECASE)


def hs2_slots(arm):
    bones = arm.data.bones

    def have(name):
        return name if name in bones else ""

    slots = {"all_parents_bone": have("cf_J_Hips"), "center_bone": "", "lower_body_bone": have("cf_J_Kosi01"),
             "upper_body_bone": have("cf_J_Spine01"), "upper_body2_bone": have("cf_J_Spine02"),
             "upper_body3_bone": have("cf_J_Spine03"), "neck_bone": have("cf_J_Neck"), "head_bone": have("cf_J_Head")}
    for side, s in SIDES:
        slots.update({
            "%s_eye_bone" % side: have("cf_J_eye_rs_%s" % s),
            "%s_chest_bone" % side: have("cf_J_Mune00_%s" % s),
            "%s_shoulder_bone" % side: have("cf_J_Shoulder_%s" % s),
            "%s_upper_arm_bone" % side: have("cf_J_ArmUp00_%s" % s),
            "%s_lower_arm_bone" % side: have("cf_J_ArmLow01_%s" % s),
            "%s_hand_bone" % side: have("cf_J_Hand_%s" % s),
            "%s_thigh_bone" % side: have("cf_J_LegUp00_%s" % s),
            "%s_calf_bone" % side: have("cf_J_LegLow01_%s" % s),
            "%s_foot_bone" % side: have("cf_J_Foot01_%s" % s),
            "%s_toe_bone" % side: have("cf_J_Toes01_%s" % s),
        })
        for role, stem, segments in FINGERS:
            for i, segment in enumerate(segments):
                slots["%s_%s_%s" % (side, role, segment)] = have("cf_J_Hand_%s%02d_%s" % (stem, i + 1, s))
    missing = sorted(k for k, v in slots.items() if not v and k != "center_bone")
    return slots, missing


def character_meshes(arm):
    out = []
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and not obj.hide_render and \
                any(m.type == "ARMATURE" and m.object == arm for m in obj.modifiers):
            out.append(obj)
    return out


def join_shared_materials(meshes):
    """Join the objects (without shape keys) that share a material, so each material is baked with all its faces.
    Returns 'kept object <- joined objects' lines."""
    plain = [m for m in meshes if not m.data.shape_keys]
    parent = {m.name: m.name for m in plain}
    everyone = {}
    for m in meshes:
        for slot in m.material_slots:
            if slot.material is not None:
                everyone.setdefault(slot.material.name, set()).add(m)
    shared_keyed = sorted(n for n, objs in everyone.items() if len(objs) > 1 and any(o.data.shape_keys for o in objs))

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    users = {}
    for m in plain:
        for slot in m.material_slots:
            if slot.material is not None:
                users.setdefault(slot.material.name, []).append(m.name)
    for names in users.values():
        for other in names[1:]:
            parent[find(other)] = find(names[0])
    groups = {}
    for m in plain:
        groups.setdefault(find(m.name), []).append(m)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        keep = max(members, key=lambda o: len(o.data.vertices))
        others = [o for o in members if o is not keep]
        names = [o.name for o in others]
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        for o in members:
            o.select_set(True)
        bpy.context.view_layer.objects.active = keep
        bpy.ops.object.join()
        out.append("%s <- %s" % (keep.name, ", ".join(names)))
    if shared_keyed:
        out.append("not joined (shape keys): " + ", ".join(shared_keyed))
    return out


def wrap_tiled_uvs(meshes):
    """Move each face of the first UV layer by whole tiles so its centre lies in 0..1.  Returns mesh: faces."""
    done = {}
    for mesh in meshes:
        if not mesh.data.uv_layers:
            continue
        layer = mesh.data.uv_layers[0]
        uv = np.empty(len(layer.data) * 2, dtype=np.float64)
        layer.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        if uv.size == 0 or (uv.min() >= -1e-3 and uv.max() <= 1.0 + 1e-3):
            continue
        moved = 0
        for poly in mesh.data.polygons:
            loops = list(range(poly.loop_start, poly.loop_start + poly.loop_total))
            shift = np.floor(uv[loops].mean(axis=0))
            if shift.any():
                uv[loops] -= shift
                moved += 1
        layer.data.foreach_set("uv", uv.ravel())
        mesh.data.update()
        done[mesh.name] = moved
    return done


def _upstream_images(node, seen=None):
    seen = set() if seen is None else seen
    if node in seen:
        return []
    seen.add(node)
    if node.type == "TEX_IMAGE":
        return [node.image] if node.image is not None else []
    out = []
    for socket in node.inputs:
        for link in socket.links:
            out += _upstream_images(link.from_node, seen)
    return out


def fix_red_only_masks(meshes):
    """min(R, G, B) over a mask that has only a red channel is 0 everywhere -> MAXIMUM.  Returns material names."""
    checked = {}

    def red_only(image):
        if image.name not in checked:
            px = np.empty(len(image.pixels), dtype=np.float32)
            image.pixels.foreach_get(px)
            ch = image.channels
            checked[image.name] = (ch >= 3 and float(np.percentile(px[1::ch], 99)) < 0.05      # a few noisy texels
                                   and float(np.percentile(px[2::ch], 99)) < 0.05      # (c_t_eyelash_04: G, B
                                   and float(np.percentile(px[0::ch], 99)) > 0.3)      # max 0.13, mean 0.000)
        return checked[image.name]

    fixed = []
    for mat in {s.material for m in meshes for s in m.material_slots if s.material and s.material.use_nodes}:
        hit = [n for n in mat.node_tree.nodes if n.type == "MATH" and n.operation == "MINIMUM"
               and any(red_only(img) for img in _upstream_images(n))]
        for n in hit:
            n.operation = "MAXIMUM"
        if hit:
            fixed.append(mat.name)
    return sorted(fixed)


def split_hair_strands(arm, meshes):
    """Each hair bone that carries a strand alone -> a chain along that skin.  Returns 'bone: n bones' lines."""
    bones = arm.data.bones
    world = arm.matrix_world
    strands = [b.name for b in bones if CLOTH_BONE.match(b.name) and "hair" in b.name.lower()
               and not any(CLOTH_BONE.match(c.name) for c in b.children)]
    points = {n: [] for n in strands}
    for mesh in meshes:
        index = {g.index: g.name for g in mesh.vertex_groups}
        wanted = {i for i, n in index.items() if n in points}
        if not wanted:
            continue
        for v in mesh.data.vertices:
            for g in v.groups:
                if g.group in wanted and g.weight > 0.0:
                    points[index[g.group]].append((mesh, v.index, mesh.matrix_world @ v.co, g.weight))
    plans = []
    for name, pts in points.items():
        if len(pts) < 8:
            continue
        origin = world @ bones[name].head_local
        total = sum(p[3] for p in pts)
        direction = sum(((p[2] - origin) * p[3] for p in pts), Vector()) / total
        if direction.length < 1e-6:
            continue
        direction.normalize()
        along = sorted((p[2] - origin).dot(direction) for p in pts)
        length = along[int(0.97 * (len(along) - 1))]
        if length < STRAND_SEGMENT:
            continue
        count = max(2, min(STRAND_MAX_BONES, int(round(length / STRAND_SEGMENT))))
        plans.append((name, origin, direction, length, count, pts))
    if not plans:
        return []
    bpy.context.view_layer.objects.active = arm
    for o in bpy.context.scene.objects:
        o.select_set(o is arm)
    bpy.ops.object.mode_set(mode="EDIT")
    edit = arm.data.edit_bones
    inv = world.inverted()
    chains = {}
    for name, origin, direction, length, count, _pts in plans:
        step = length / count
        chain = [name]
        first = edit[name]
        first.use_connect = False
        first.head, first.tail = inv @ origin, inv @ (origin + direction * step)
        for j in range(1, count):
            e = edit.new("%s_%d" % (name, j + 1))
            e.head, e.tail = inv @ (origin + direction * step * j), inv @ (origin + direction * step * (j + 1))
            e.roll = first.roll
            e.parent = edit[chain[-1]]
            e.use_connect = True
            e.use_deform = True
            chain.append(e.name)
        chains[name] = chain
    bpy.ops.object.mode_set(mode="OBJECT")
    out = []
    for name, origin, direction, length, count, pts in plans:
        chain = chains[name]
        step = length / count
        for mesh, vi, co, w in pts:
            s = max(0.0, min(float(count), (co - origin).dot(direction) / step))
            if s <= 0.5:
                shares = [1.0] + [0.0] * (count - 1)
            elif s >= count - 0.5:
                shares = [0.0] * (count - 1) + [1.0]
            else:
                shares = [max(0.0, 1.0 - abs(s - (j + 0.5))) for j in range(count)]
            norm = sum(shares)
            mesh.vertex_groups[name].remove([vi])
            for j, share in enumerate(shares):
                if share > 0.0:
                    group = mesh.vertex_groups.get(chain[j]) or mesh.vertex_groups.new(name=chain[j])
                    group.add([vi], w * share / norm, "ADD")
        out.append("%s: %d bones over %.1f cm" % (name, count, length * 100))
    return out


def flatten_helpers(arm, meshes, slots):
    """Helpers' skin -> the kept bone above them; then the bones without skin go.  Returns a report."""
    bones = arm.data.bones
    weighted = sb.weighted_bones(meshes)
    keep = {v for v in slots.values() if v}
    for name in weighted:
        if name in bones and (JOINT_PADS.match(name) or (CLOTH_BONE.match(name) and not SCALP.match(name))):
            keep.add(name)

    def owner(bone):
        cur = bone.parent
        while cur is not None and cur.name not in keep:
            cur = cur.parent
        return cur.name if cur is not None else None

    moved, orphans = {}, []
    for mesh in meshes:
        index = {g.index: g.name for g in mesh.vertex_groups}
        target_of = {}
        for g in mesh.vertex_groups:
            bone = bones.get(g.name)
            if bone is None or g.name in keep:
                continue
            target = owner(bone)
            if target is None:
                orphans.append(g.name)
                continue
            target_of[g.index] = target
        if not target_of:
            continue
        adds = {}
        for v in mesh.data.vertices:
            for g in v.groups:
                target = target_of.get(g.group)
                if target is not None and g.weight > 0.0:
                    adds.setdefault(target, {}).setdefault(v.index, 0.0)
                    adds[target][v.index] += g.weight
        for target, per_vertex in adds.items():
            group = mesh.vertex_groups.get(target) or mesh.vertex_groups.new(name=target)
            for vi, w in per_vertex.items():
                group.add([vi], w, "ADD")
        for gi in sorted(target_of, reverse=True):
            name = index[gi]
            moved.setdefault(name, target_of[gi])
            mesh.vertex_groups.remove(mesh.vertex_groups[name])
    bpy.context.view_layer.objects.active = arm
    for o in bpy.context.scene.objects:
        o.select_set(o is arm)
    bpy.ops.object.mode_set(mode="EDIT")
    edit = arm.data.edit_bones
    removed = 0
    for eb in list(edit):
        if eb.name not in keep:
            edit.remove(eb)                          # children move up to its parent
            removed += 1
    bpy.ops.object.mode_set(mode="OBJECT")
    by_target = {}
    for name, target in moved.items():
        by_target.setdefault(target, []).append(name)
    return {"kept_bones": len(arm.data.bones), "removed_bones": removed,
            "merged_into": {t: len(n) for t, n in sorted(by_target.items())},
            "joint_pads": sorted(n for n in keep if JOINT_PADS.match(n)),
            "cloth_bones": sorted(n for n in keep if CLOTH_BONE.match(n)),
            "orphan_groups": sorted(set(orphans))}


def _z(key):
    co = np.empty(len(key.data) * 3, dtype=np.float64)
    key.data.foreach_get("co", co)
    return co[2::3]


def mix_drop(mesh, mix):
    """Largest downward move of a mix of shapes {name: weight} (the chin / lower lip / lower teeth)."""
    keys = mesh.data.shape_keys.key_blocks
    base = _z(keys[0])
    dz = np.zeros_like(base)
    for name, weight in mix.items():
        if name in keys:
            dz += weight * (_z(keys[name]) - base)
    return float(max(0.0, -dz.min())) if dz.size else 0.0


def jaw_drop(mesh, key):
    return mix_drop(mesh, {key.name: 1.0})


def open_weights(mesh, drop):
    """{open level: weight} that lowers this mesh's teeth / tongue by ``drop``."""
    keys = mesh.data.shape_keys.key_blocks
    levels = [(name, jaw_drop(mesh, keys[name])) for name in OPEN_LEVELS if name in keys]
    levels = [(n, d) for n, d in levels if d > 1e-5]
    if not levels or drop <= 1e-4:
        return {}
    prev_name, prev_drop = None, 0.0
    for name, d in levels:
        if drop <= d:
            t = (drop - prev_drop) / (d - prev_drop)
            out = {name: t}
            if prev_name:
                out[prev_name] = 1.0 - t
            return out
        prev_name, prev_drop = name, d
    return {levels[-1][0]: drop / levels[-1][1]}


def add_hs2_morphs(root, meshes):
    """RECIPES -> shape keys of the same name on every mesh involved, registered as MMD vertex morphs."""
    keyed = [m for m in meshes if m.data.shape_keys]
    head = max(keyed, key=lambda m: len(m.data.shape_keys.key_blocks), default=None)
    made, skipped = [], []
    for m in keyed:
        for kb in m.data.shape_keys.key_blocks:
            kb.value = 0.0
    for name, name_e, category, mix in RECIPES:
        if head is None or not any(k in head.data.shape_keys.key_blocks for k in mix):
            skipped.append((name, "no shape"))
            continue
        drop = mix_drop(head, mix) if category == "MOUTH" else 0.0      # the lids drop too: no teeth for eyes
        touched = []
        for m in keyed:
            keys = m.data.shape_keys.key_blocks
            if name in keys:
                continue
            mix_here = {k: v for k, v in mix.items() if k in keys}
            if TEETH_MESHES.match(m.name) and category == "MOUTH":
                for level, w in open_weights(m, drop / TEETH_RATIO).items():
                    mix_here[level] = mix_here.get(level, 0.0) + w
            if not mix_here:
                continue
            for k, v in mix_here.items():
                keys[k].value = v
            new = m.shape_key_add(name=name, from_mix=True)
            new.value = 0.0
            for k in mix_here:
                keys[k].value = 0.0
            touched.append(m.name)
        if touched:
            made.append((name, name_e, category, round(drop * 100, 2), touched))
    mmd = root.mmd_root
    have = {m.name: m for m in mmd.vertex_morphs}
    for name, name_e, category, _drop, _meshes in made:
        item = have.get(name) or mmd.vertex_morphs.add()
        item.name, item.name_e, item.category = name, name_e, category
    have = {m.name for m in mmd.vertex_morphs}
    for m in keyed:                                  # the game's own shapes, under その他
        for kb in list(m.data.shape_keys.key_blocks)[1:]:
            if kb.name not in have:
                item = mmd.vertex_morphs.add()
                item.name, item.name_e, item.category = kb.name, kb.name, "OTHER"
                have.add(kb.name)
    for target, entry in enumerate(made):
        mmd.vertex_morphs.move(mmd.vertex_morphs.find(entry[0]), target)
    from mmd_tools.operators.display_item import DisplayItemQuickSetup
    if "表情" in mmd.display_item_frames:
        mmd.display_item_frames["表情"].data.clear()
    DisplayItemQuickSetup.load_facial_items(mmd)
    return ["%s (jaw %.2f cm: %s)" % (n, d, "+".join(t)) for n, _e, _c, d, t in made], skipped


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--model-name", default="", help="name shown in MMD (default: --name)")
    ap.add_argument("--comment", default="", help="model comment (credits / source)")
    args = ap.parse_args(argv)

    roe = sb.load_worker()
    suit = load(SUIT_SCRIPT, "roe_suit_pmx")
    scene = bpy.context.scene
    name = args.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    out_dir = os.path.join(os.path.abspath(args.out), name)
    path = os.path.join(out_dir, name + ".pmx")
    report = {"name": name, "pmx": path, "source": bpy.data.filepath}

    arm = next(o for o in scene.objects if o.type == "ARMATURE")
    meshes = character_meshes(arm)
    left_out = [o.name for o in scene.objects if o.type == "MESH" and o not in meshes]
    for obj_name in left_out:
        bpy.data.objects.remove(bpy.data.objects[obj_name], do_unlink=True)
    report["left_out"] = left_out
    os.makedirs(out_dir, exist_ok=True)
    for stale in (path, os.path.join(out_dir, name + "_converted.blend")):   # only this exporter's own files
        if os.path.isfile(stale):
            os.remove(stale)
    clip, opaque = source_alpha_modes()
    report["joined_meshes"] = join_shared_materials(meshes)
    meshes = character_meshes(arm)
    report["wrapped_uv_faces"] = wrap_tiled_uvs(meshes)
    report["red_only_masks"] = fix_red_only_masks(meshes)
    baked = sb.bake_node_colours(meshes, os.path.join(out_dir, "textures"))

    slots, missing_optional = hs2_slots(arm)
    missing_required = [r for r in roe.ROE_MMD_REQUIRED_SLOTS if not slots[r]]
    if missing_required:
        raise RuntimeError("rig lacks joints the MMD conversion needs: %s" % ", ".join(missing_required))
    report["missing_optional_slots"] = missing_optional
    report["flatten"] = flatten_helpers(arm, meshes, slots)
    report["hair_strands"] = split_hair_strands(arm, meshes)
    roe.enable_addon("mmd_tools")
    roe.enable_addon("Convert_to_MMD5")
    suit.keep_shape_keys_in_rest_bakes()             # the face meshes carry the game's blend shapes
    roe.LIMB_HELPER_NAME = re.compile(roe.LIMB_HELPER_NAME.pattern + r"|elbo", re.IGNORECASE)
    roe.bake_rig_transforms(arm, meshes)
    before = roe.edge_lengths(meshes)
    report["height_m"] = round(max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box), 3)
    helper_plans, _helper_report = roe.plan_joint_helper_moves(arm, meshes, slots)
    report["reparented_helpers"] = roe.apply_joint_helper_moves(arm, helper_plans)
    report["relaxed_groups"] = roe.relax_shoulder_weights(arm, slots)
    report["arm_down_deg"] = roe.apose_arms(arm, meshes, slots)
    skin_before = roe.snapshot_skin(arm, meshes)
    try:                                             # helpers are never cloth
        import mmd_cloth_physics.analyze as cloth_analyze
        if NOT_CLOTH not in cloth_analyze.LIMB_HELPER.pattern:
            cloth_analyze.LIMB_HELPER = re.compile(cloth_analyze.LIMB_HELPER.pattern + NOT_CLOTH, re.IGNORECASE)
    except ImportError:
        pass
    names_before, weighted_before = set(arm.data.bones.keys()), sb.weighted_bones(meshes)
    root, conv = roe.convert_rig_to_mmd(arm, meshes, slots, missing_optional, helper_plans, skin_before)
    report.update(conv)
    report["stray_recipients"] = sorted((sb.weighted_bones(meshes) - weighted_before) & names_before)
    report["anchored_hub_roots"] = sb.anchor_hub_roots(arm)
    report["released_rest_overlaps"] = sb.release_rest_overlaps()
    report["bust_physics"] = sb.add_breast_physics(root, arm, meshes)
    report["rigid_bodies"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY")
    report["joints"] = sum(1 for o in scene.objects if getattr(o, "mmd_type", "") == "JOINT")
    report["distortion"] = roe.mesh_distortion(before, meshes)
    report["hidden_materials"] = roe.hide_transparent_materials(meshes)
    report["materials"] = sb.fix_pmx_materials(meshes, baked, os.path.join(out_dir, "textures"))
    report["vertex_morphs"], report["morphs_skipped"] = add_hs2_morphs(root, meshes)

    root.mmd_root.name = root.mmd_root.name_e = args.model_name or name
    root.name = args.model_name or name
    comment = args.comment or "Converted from HoneySelect 2 by ripper_tpose (scripts/honeyselect2). Personal use only."
    text = bpy.data.texts.new(name + "_comment")
    text.from_string(comment.replace(chr(92) + "n", "\n"))
    root.mmd_root.comment_text = root.mmd_root.comment_e_text = text.name

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    stack = [root]
    while stack:
        obj = stack.pop()
        try:
            obj.hide_set(False)
            obj.select_set(True)
        except (ReferenceError, RuntimeError):
            pass
        stack.extend(obj.children)
    bpy.context.view_layer.objects.active = root
    bpy.ops.mmd_tools.export_pmx(filepath=path, scale=12.5, copy_textures=True, log_level="ERROR")
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("PMX not written: %s" % path)
    report["texture_alpha"] = fix_texture_alpha(path, clip, opaque)
    report["grant_order_violations"] = roe.verify_grant_order(path)
    report["bytes"] = os.path.getsize(path)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + "_converted.blend"))
    with open(os.path.join(out_dir, name + "_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, default=str)
    print("HS2_PMX=" + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
