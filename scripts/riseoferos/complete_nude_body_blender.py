"""Give a dressed ROE model the whole body: the skin under its outfit, taken from the family nude base.

A dressed model (pc_a08_hd) ships only the skin its outfit leaves visible - the game deletes what the clothes
cover (a08 keeps 16,325 of the nude body's 36,142 body faces: shins, feet, crotch, nipples, forearms and neck are
holes).  The family nude base (pc_a01_nk_bs) is the same surface in full - a08's skin lies on the nude body within
0.1 mm (median; p99 2.9 mm, only the breasts differ, by up to 5 mm) - but it is rigged on a skeleton whose joints
sit up to 2 cm elsewhere (a08's ankle 19 mm higher; g04's hips 2 cm) and that has bones the dressed rig lacks
(genitals, toes, butt, nipples, muscle helpers).  This puts the nude body on the dressed model's rig:
  * the nude bones the body is weighted to: a model bone of the same name, else the model's own version under
    another name (bone_resolver: spelt with other spaces / case - d08's Bip001 LThigh; ALIASES - g04 calls the
    breasts chest_L / chest_L02, the nude base Breast_L / Breast_L02; or the parent of the model bone the nude bone's
    child maps to - d08's LUpArm, d09's calf LCalfTwist - the outfit follows those, so the body must too), else
    added to the armature at its nude rest pose under the same-named (or aliased) parent
  * a model rigged in another rest pose (c10: arms 44 degrees down; POSE_MIN) gets the nude base's limbs turned to
    it first (repose_nude), body and rig, so the completed body stands like the model
  * the nude mesh's body slot is the new body, plus the part of its face slot the model's head mesh does not
    cover: g04's head stops at the jaw and its neck was a face-material piece on the body mesh that did not meet
    the nude body (a 2.5 cm overlap, a ridge at the collarbones); the nude neck replaces such pieces.  Covered:
    on the head within 1 mm, or with the head's skin along the normal within 8 mm (c02's face is 1-5 mm off the
    nude one); bits of the face slot not joined to the body (seen through the head's eye / nose holes) go too
  * the body keeps the nude base's weights (one consistent design); vertices on the seam with the head move onto
    the head's vertices and copy their weights and normals, so it stays closed and shades without a line.  Where
    the head's neck opening and the nude neck do not share vertices (c02: 44 against 48), stitch() moves the neck's
    edge onto the opening by arc length (between head vertices, blended) and fills the corners with slivers.
    The old skin's weights are NOT carried over: they lean on helpers the game drives by animation keys (a08's
    calf twist bones hang under the THIGH); blending them in tore the shins as soon as a knee bent (939
    overstretched vertices in a kick pose vs 518 with the nude weights alone, 410 on the nude base itself)
  * every material slot of the other meshes is skin (>= 60 % of its vertices within 1.5 mm of the nude body: deleted),
    keep (the face material: g04's neck piece on the body mesh) or outfit; whole meshes named wp_* or marked
    roe_added_weapon (add_weapon_blender.py) are weapons and stay in both variants.  Skin slots are checked by
    colour against the nude body's (painted_skin): one far off on the whole is clothing lying on the skin (l01's
    leotard) and becomes outfit; in the full variant, patches far off are paint on the skin (m02's vines) and stay
    over the body as an outfit slot
  * variant "nude" deletes the outfit; variant "full" keeps it - split into outfit-only objects, marked roe_outfit
    (export_suit_pmx_blender.py gives the PMX a 衣服非表示 morph over their materials) and roe_xps_optional "+outfit"
    (XNALara / XPS optional item) - and pushes the body CLEAR (1.5 mm) under it where the two touch or cross, only
    on the parts the dressed model did not have
  * a kept slot whose game material (roe_source_materials) has an HQ material in the file but wears another one
    gets it back (a08's braid ring: outfit atlas, it came out grey); in the full variant a kept slot that shares a
    material with the outfit gets its own copy (the PMX morph hides materials)
The head is the mesh with the most eyeball-weighted vertices (Bip001 eyeball_L, or eye_L as on b01; else the mesh
with the HQ "eye" slot), hair any mesh named *hair*.  A model with no slot mostly skin (f06: skin and outfit share
one material) has that slot as outfit (report skin_note).

  blender -b --factory-startup <model.blend> --python complete_nude_body_blender.py --
      --nude <nude base .blend> --variant nude|full --out <out.blend> [--report <json>]
"""
import argparse
import json
import math
import os
import re
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, kdtree
from mathutils.bvhtree import BVHTree

ALIGN_MIN = 0.01         # the nude base is moved onto the model when the bones both have are this far off (median):
                         # d03 stands 13.3 cm to the side, c01 / c03-c05 33 mm higher on heels; a08 2.8 mm, g04 0.1
SKIN_DIST = 0.0015       # a model vertex this close to the nude body surface is skin
SKIN_SHARE = 0.6         # share of a slot's vertices that must be skin
SAME = 0.001             # nude vertex this close to the old skin: the part the dressed model already had
SEAM = 0.001             # nude vertex this close to a kept head / face vertex: moved onto it, takes its weights
COVER = 0.001            # a nude face-slot face whose vertices all lie this close to the head mesh is the head's
RAY_COVER = 0.008        # ... and one with a vertex that has the head's skin this close along its normal (either way)
RAY_FACING = 0.5         # ... facing the same way (|cos| of the two normals): c02's face is 1-5 mm off the c01 one
STITCH_REACH = 0.015     # an open body edge this close to an open edge of the head's skin is joined to it by a strip
JOINED = 0.0001          # ... where their vertices are this close (or seam-matched) they already meet
STITCH_FALLOFF = 0.02    # ... the body this close to the edge follows its move by a fading share
HEAD_EXTRAS = ("eye", "lash", "brow", "eye_overlay")    # head slots off the skin (the HQ add-on's names)
SLOT_PAINTED = 0.08      # a skin slot whose colour differs from the nude body's this much (median per face) is
                         # clothing lying on the skin: l01's leotard + stockings (0.144); real skin 0.004-0.007
FACE_PAINTED = 0.12      # full variant: faces of a skin slot this far off are paint on the skin (m02's vines, 25 %)
PAINT_MIN = 12           # ... in patches of at least this many such faces (b01 / d01: 0.3 % scattered specks)
TONE_MIN = 1.5           # CIELAB distance at the neck seam between the model's face colour and the colour the nude
                         # base's own face would have there, over which the body is tinted to the model's skin
                         # (b08_outfit1 tanned 20.6, k07 / k03 pale 14.0 / 12.2, b14 4.4; every other model 0 - 0.5)
TONE_REACH = 0.008       # ... the colour on either side of a seam vertex: faces whose centre is this close to it
TONE_TOUCH = 0.0005      # ... a body vertex this close to a vertex in the face material is on the seam
TONE_SEAM_MIN = 20       # ... seam vertices with colour on both sides needed for a measurement
TONE_SPREAD = 0.1        # ... and no tint when the gain of the front half of the neck and of the back half differ more
                         # (b14: its face's AO is 18 % lighter than the family's under the jaw, the same at the nape)
EYE_GROUP = re.compile(r"\beye(ball)?_[lr]$", re.IGNORECASE)     # Bip001 eyeball_L (most), Bip001 eye_L (b01)
TAIL = re.compile(r"(^|[\W_])tail(\d|_|$)", re.IGNORECASE)        # e05: pc_e05_hd_tail / tail2, bones tail_01-04
TAIL_SHARE = 0.5         # ... or a slot with this share of its vertices on tail bones: part of the body, kept
TAIL_MIN = 20            # ... or this many faces on tail bones inside an outfit slot (b08 / f02 / f08: a thin devil
                         # tail in the outfit's material) - split off as their own slot
MAX_INFLUENCES = 4       # the game's and PMX's limit
CLEAR = 0.0015           # full variant: the body stays this far under the outfit
PROBE = 0.012            # ... looking this far out for outfit over the skin
PROBE_IN = 0.02          # ... and this far in for outfit the skin pokes through (a08's boots, g04's pointed shoes)
FACING = 0.0             # an outfit face is over a skin vertex when its normal looks the same way (not a lining)
FIT_ROUNDS = 8           # project under the outfit, smooth the displacement, project again
HIDE_STEP = 0.0005       # full variant, last: a vertex that still shows through the outfit moves in by this ...
HIDE_MAX = 0.003         # ... up to this far (fingertips past a glove's tips, nails)
HIDE_MARGIN = 0.0006     # ... also when the outfit covers it by less than this (it flickers through)
NUDE_SHAPE = "裸体形状"   # full variant: shape key holding the body's own shape (the basis is fitted under the outfit)
ALIAS_DIST = 0.03        # an aliased model bone must sit this close to the nude bone
POSE_MIN = 10.0          # degrees: a limb of the model's rest pose this far off the nude base's is turned to match first
                         # (c10, the kimono, is rigged with the arms 44 degrees down; every other rest pose is a T within 5)
LIMBS = (("Bip001 %s UpperArm", "Bip001 %s Forearm", "Bip001 %s Hand", "Bip001 %s Finger2"),
         ("Bip001 %s Thigh", "Bip001 %s Calf", "Bip001 %s Foot", "Bip001 %s Toe0"))    # nude names; the last only aims
ALIASES = [(re.compile(r"^Bip001 Breast_([LR])(\d*)$"), r"Bip001 chest_\1\2")]   # nude name -> model name
DEBUG_ATTR = bool(os.environ.get("ROE_COMPLETE_DEBUG"))   # keep cn_old_skin / cn_push point attributes


def args_after_dashes():
    p = argparse.ArgumentParser()
    p.add_argument("--nude", required=True)
    p.add_argument("--variant", choices=("nude", "full"), default="nude")
    p.add_argument("--out", required=True)
    p.add_argument("--report", default="")
    p.add_argument("--name", default="", help="name of the new body object (default <model>_body)")
    return p.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def world_co(obj):
    me = obj.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    m = np.array(obj.matrix_world)
    return co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]


def world_normals(obj):
    me = obj.data
    n = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("normal", n)
    n = n.reshape(-1, 3) @ np.array(obj.matrix_world.to_3x3().inverted().transposed()).T
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def triangles(obj, slots=None):
    me = obj.data
    me.calc_loop_triangles()
    tris = [tuple(t.vertices) for t in me.loop_triangles if slots is None or t.material_index in slots]
    return np.array(tris, dtype=np.int64).reshape(-1, 3)


def bvh(points, tris):
    return BVHTree.FromPolygons([Vector(p) for p in points], tris.tolist())


def armature_of(obj):
    return next((m.object for m in obj.modifiers if m.type == "ARMATURE" and m.object), None)


def dense_weights(obj, columns, verts=None):
    """(verts x bones) weights over the column names; groups not in columns are dropped."""
    col = {name: i for i, name in enumerate(columns)}
    gmap = {g.index: col.get(g.name) for g in obj.vertex_groups}
    w = np.zeros((len(obj.data.vertices), len(columns)), dtype=np.float32)
    for v in obj.data.vertices if verts is None else (obj.data.vertices[i] for i in verts):
        for g in v.groups:
            c = gmap.get(g.group)
            if c is not None and g.weight > 0:
                w[v.index, c] = g.weight
    return w


def limit_normalize(w, k=MAX_INFLUENCES):
    if w.shape[1] > k:
        cut = np.partition(w, -k, axis=1)[:, -k][:, None]
        w = np.where(w >= cut, w, 0.0)
        for i in np.nonzero((w > 0).sum(1) > k)[0]:          # ties can leave more than k
            nz = np.nonzero(w[i])[0]
            w[i, nz[np.argsort(w[i, nz])[:-k]]] = 0.0
    s = w.sum(1, keepdims=True)
    return np.where(s > 0, w / np.maximum(s, 1e-12), w)


def base(name):
    return re.sub(r"\.\d{3}$", "", name or "")


def slot_sources(obj):
    """{slot index: game material name stored from the FBX (roe_source_materials, by face majority)}."""
    names = str(obj.get("roe_source_materials", "")).split("\n")
    attr = obj.data.attributes.get("roe_source_material_index")
    if not any(names) or attr is None or not len(obj.data.polygons):
        return {}
    n = len(obj.data.polygons)
    src = np.empty(n, dtype=np.int64)
    attr.data.foreach_get("value", src)
    slot = np.empty(n, dtype=np.int64)
    obj.data.polygons.foreach_get("material_index", slot)
    out = {}
    for index in range(len(obj.material_slots)):
        picked = src[slot == index]
        if len(picked):
            k = int(np.bincount(picked).argmax())
            if k < len(names) and names[k]:
                out[index] = names[k]
    return out


def append_nude(path):
    """The nude base's *_nk_body mesh and its armature; returns (body, armature, body slot index)."""
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if re.search(r"_nk_body$", n)]
    if not dst.objects:
        raise SystemExit("no *_nk_body mesh in %s" % path)
    body = dst.objects[0]
    bpy.context.scene.collection.objects.link(body)
    arm = armature_of(body)
    if arm is None:
        raise SystemExit("%s has no armature" % body.name)
    if arm.name not in bpy.context.scene.objects:
        bpy.context.scene.collection.objects.link(arm)
    slot = next((i for i, s in enumerate(body.material_slots) if s.material and "nk_body" in s.material.name), 0)
    return body, arm, slot


def align_nude(model_arm, nude_arm, nude_body):
    """Put the nude base where the dressed model stands: moved by the median offset of the bones both armatures have,
    when that is ALIGN_MIN or more.  d03's armature object sits 13.3 cm to the side, c01 / c03-c05 stand 33 mm higher
    (their heels): their skin, head and neck matched nothing - no skin slot, a second body beside d03, a second head.
    The armature object moves (bone positions are read in world space); the body object stays and its vertices move
    (it may be the armature's child; at rest the armature modifier changes nothing).  Returns the offset in mm."""
    common = [b.name for b in model_arm.data.bones if nude_arm.data.bones.get(b.name)]
    if not common:
        return [0.0, 0.0, 0.0]
    d = np.array([np.array(model_arm.matrix_world @ model_arm.data.bones[n].head_local)
                  - np.array(nude_arm.matrix_world @ nude_arm.data.bones[n].head_local) for n in common])
    t = np.median(d, axis=0)
    if np.linalg.norm(t) < ALIGN_MIN:
        return [0.0, 0.0, 0.0]
    body_world = nude_body.matrix_world.copy()
    nude_arm.matrix_world = Matrix.Translation(Vector(t.tolist())) @ nude_arm.matrix_world
    bpy.context.view_layer.update()
    nude_body.matrix_world = body_world
    bpy.context.view_layer.update()
    nude_body.data.transform(Matrix.Translation(body_world.inverted().to_3x3() @ Vector(t.tolist())), shape_keys=True)
    nude_body.data.update()
    return [round(float(x) * 1000.0, 1) for x in t]


def turn(cur, tgt, cur2=None, tgt2=None):
    """4x4 rotation taking the direction cur onto tgt and then, about tgt, cur2's part across it onto tgt2's."""
    q = cur.rotation_difference(tgt)
    if cur2 is not None and tgt2 is not None:
        a = tgt.normalized()
        c2 = q @ cur2
        p, r = c2 - a * c2.dot(a), tgt2 - a * tgt2.dot(a)
        if p.length > 1e-6 and r.length > 1e-6:
            q = p.rotation_difference(r) @ q
    return q.to_matrix().to_4x4()


def repose_nude(model_arm, nude_arm, nude_body):
    """Turn the nude base's limbs to the dressed model's rest pose where they are POSE_MIN or more apart.  c10 (the
    kimono) is rigged with its arms hanging 44 degrees down, the nude base in a T: unturned, the body's arms stuck
    straight out through the sleeves and the elbows the skin bent at sat 15 cm above the model's.  Per limb each bone
    (upper arm, forearm, hand; thigh, calf, foot) turns about its head to point at the model's next joint, parents
    first; the hand also turns its palm (index to little finger root) like the model's.  Helpers hanging off one bone
    but sitting at the next joint (Biped's ForeTwist under the upper arm, at the elbow) follow the next bone meanwhile.
    The body takes the pose through its armature modifier and keeps it as its shape, and the pose becomes the nude
    rig's rest: the rest of the completion sees a nude base standing like the model.
    Returns {first bone of each turned limb: [degrees off per segment]}."""
    resolve, _mapping = bone_resolver(model_arm, nude_arm, lambda line: None)
    nb = nude_arm.data.bones

    def head(arm, name):
        return arm.matrix_world @ arm.data.bones[name].head_local

    limbs, turned = [], {}
    for side in "LR":
        for limb in LIMBS:
            names = [n % side for n in limb]
            models = [resolve(n) if n in nb else None for n in names]
            k = next((i for i, m in enumerate(models) if not m), len(names))   # joints both rigs have, from the top
            names, models = names[:k], models[:k]
            if len(names) < 2:
                continue
            off = [math.degrees((head(nude_arm, names[i + 1]) - head(nude_arm, names[i])).angle(
                head(model_arm, models[i + 1]) - head(model_arm, models[i]))) for i in range(len(names) - 1)]
            if max(off) >= POSE_MIN:
                limbs.append((names, models))
                turned[names[0]] = [round(x, 1) for x in off]
    if not limbs:
        return {}
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    nude_arm.hide_set(False)
    nude_arm.select_set(True)
    bpy.context.view_layer.objects.active = nude_arm
    bpy.ops.object.mode_set(mode="EDIT")
    edit = nude_arm.data.edit_bones
    moved = {}
    for names, _models in limbs:
        for i in range(len(names) - 2):
            near, far = edit[names[i]], edit[names[i + 1]]
            seg = far.head - near.head
            for child in list(near.children):
                if child.name not in names and (child.head - near.head).dot(seg) >= 0.98 * seg.length_squared:
                    moved[child.name] = near.name
                    keep = child.head.copy(), child.tail.copy(), child.roll
                    child.use_connect = False
                    child.parent = far
                    child.head, child.tail, child.roll = keep
    bpy.ops.object.mode_set(mode="POSE")
    pose, world = nude_arm.pose.bones, nude_arm.matrix_world
    for names, models in limbs:
        for i in range(len(names) - 1):
            bpy.context.view_layer.update()
            pb = pose[names[i]]
            m = world @ pb.matrix
            h = m.translation.copy()
            cur = (world @ pose[names[i + 1]].matrix).translation - h
            tgt = head(model_arm, models[i + 1]) - head(model_arm, models[i])
            cur2 = tgt2 = None
            if names[i].endswith(" Hand"):
                ends = [names[i + 1].replace("Finger2", f) for f in ("Finger1", "Finger4")]
                mine = [resolve(n) if n in nb else None for n in ends]
                if all(mine):
                    cur2 = (world @ pose[ends[1]].matrix).translation - (world @ pose[ends[0]].matrix).translation
                    tgt2 = head(model_arm, mine[1]) - head(model_arm, mine[0])
            pb.matrix = world.inverted() @ (Matrix.Translation(h) @ turn(cur, tgt, cur2, tgt2)
                                             @ Matrix.Translation(-h) @ m)
    bpy.context.view_layer.update()
    me = nude_body.data
    n = len(me.vertices)
    rest = np.empty(n * 3)
    me.vertices.foreach_get("co", rest)
    evaluated = nude_body.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    if len(evaluated.vertices) != n:
        raise SystemExit("the nude body's modifiers change its vertex count: cannot keep the pose")
    posed = np.empty(n * 3)
    evaluated.vertices.foreach_get("co", posed)
    if me.shape_keys:
        for kb in me.shape_keys.key_blocks:
            co = np.empty(n * 3)
            kb.data.foreach_get("co", co)
            kb.data.foreach_set("co", co + posed - rest)
    me.vertices.foreach_set("co", posed)
    me.update()
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode="EDIT")
    edit = nude_arm.data.edit_bones
    for name, parent in moved.items():              # back where the nude rig had them (rest-neutral)
        child = edit[name]
        keep = child.head.copy(), child.tail.copy(), child.roll
        child.parent = edit[parent]
        child.head, child.tail, child.roll = keep
    bpy.ops.object.mode_set(mode="OBJECT")
    return turned


def tail_patch(obj, index, tail_groups):
    """Faces of a slot that are a tail: every vertex mainly on a tail bone, plus the faces joined to those that have
    at least one such vertex (the tail's root ring)."""
    me = obj.data
    top = [bool(v.groups) and max(v.groups, key=lambda g: g.weight).group in tail_groups for v in me.vertices]
    faces = [p for p in me.polygons if p.material_index == index]
    seeds = {p.index for p in faces if all(top[v] for v in p.vertices)}
    if len(seeds) < TAIL_MIN:
        return []
    touch = sorted(p.index for p in faces if any(top[v] for v in p.vertices))
    key = np.arange(len(me.vertices))
    for group in coincident(world_co(obj)):
        key[group] = group.min()
    root = islands(touch, key, lambda f: me.polygons[f].vertices)
    good = {root[f] for f in seeds}
    return [f for f in touch if root[f] in good]


def classify(model_arm, nude_tree):
    """{head, hair, weapons, slots: {obj: {slot: skin|keep|part|outfit}}, shares} of the model, by name and shape;
    part = a tail (material or most vertices' bones named tail), kept in both variants like the hair."""
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and armature_of(o) is model_arm]

    def eyeball_weighted(o):
        groups = {g.index for g in o.vertex_groups if EYE_GROUP.search(g.name)}
        return sum(1 for v in o.data.vertices if any(g.group in groups and g.weight > 0 for g in v.groups)) \
            if groups else 0
    eyed = [(eyeball_weighted(o), o) for o in meshes]
    eyed = [e for e in eyed if e[0]]
    head = max(eyed, key=lambda e: e[0])[1] if eyed else None
    if head is None:            # no eye bones by those names: the mesh with the ROE add-on's eye slot
        head = next((o for o in meshes if any(s.material and base(s.material.name) == "eye" for s in o.material_slots)),
                    None)
    hair = [o for o in meshes if "hair" in o.name.lower() and o is not head]
    weapons = [o for o in meshes if o.get("roe_added_weapon") or o.name.lower().startswith("wp_")]
    head_mats = {base(s.material.name) for s in head.material_slots if s.material} if head else set()
    slots, shares = {}, {}
    for obj in meshes:
        if obj is head or obj in hair or obj in weapons:
            continue
        co = world_co(obj)
        me = obj.data
        sources = slot_sources(obj)
        tail_groups = {g.index for g in obj.vertex_groups if TAIL.search(g.name)}
        kinds = {}
        for index in sorted({p.material_index for p in me.polygons}):
            verts = sorted({i for p in me.polygons if p.material_index == index for i in p.vertices})
            near = sum(1 for i in verts if nude_tree.find_nearest(Vector(co[i]), SKIN_DIST)[0] is not None)
            share = near / len(verts)
            shares["%s[%d]" % (obj.name, index)] = round(share, 3)
            mat = obj.material_slots[index].material if index < len(obj.material_slots) else None
            on_tail = sum(1 for i in verts if me.vertices[i].groups and max(
                me.vertices[i].groups, key=lambda g: g.weight).group in tail_groups) if tail_groups else 0
            if (mat is not None and TAIL.search(base(mat.name))) or on_tail >= TAIL_SHARE * len(verts):
                kinds[index] = "part"           # a tail: the body's, kept in both variants (user, 10-04)
            elif share >= SKIN_SHARE:
                kinds[index] = "skin"
            elif (mat is not None and base(mat.name) in head_mats) or re.search(r"_face$", sources.get(index, "")):
                kinds[index] = "keep"
            else:
                kinds[index] = "outfit"
        for index, kind in sorted(kinds.items()):     # a tail drawn with the outfit's material: its own slot
            faces = tail_patch(obj, index, tail_groups) if kind == "outfit" and tail_groups else []
            if faces:
                me.materials.append(obj.material_slots[index].material)
                new = len(me.materials) - 1
                for f in faces:
                    me.polygons[f].material_index = new
                kinds[new] = "part"
        slots[obj] = kinds
    return {"meshes": meshes, "head": head, "hair": hair, "weapons": weapons, "slots": slots, "shares": shares}


def bone_resolver(model_arm, nude_arm, log):
    """resolve(nude bone name) -> the model's bone for it, or None (a bone to add).  The same name; else the same
    bone spelt another way: case (Bip001 Chin / chin), spaces and underscores (d08's Bip001 LThigh / LCalf for the
    nude base's Bip001 L Thigh / L Calf), ALIASES (g04's chest_L for Breast_L); else the parent of the model bone the
    nude bone's child resolves to (d08's Bip001 LUpArm above Bip001 L Forearm, d09's calf Bip001 LCalfTwist above
    Bip001 L Foot) - always within ALIAS_DIST of the nude bone.  Unresolved, d08 got the nude base's whole thigh /
    calf / upper arm chain as second bones beside its own: the PMX took those for 足 / ひざ / 腕 and the outfit,
    riding d08's own, stayed put under motion.  Returns (resolve, {nude name: model name or None})."""
    have = set(model_arm.data.bones.keys())
    m_head = {b.name: model_arm.matrix_world @ b.head_local for b in model_arm.data.bones}
    n_head = {b.name: nude_arm.matrix_world @ b.head_local for b in nude_arm.data.bones}
    mapping = {}
    lower = {n.lower(): n for n in have}
    squeezed = {}
    for n in have:
        squeezed.setdefault(re.sub(r"[\s_]", "", n.lower()), []).append(n)

    def near(name, other):
        return name in n_head and (m_head[other] - n_head[name]).length <= ALIAS_DIST

    def alias(name, other, why=""):
        mapping[name] = other
        log("alias %s -> %s (%.1f mm%s)" % (name, other, (m_head[other] - n_head[name]).length * 1000, why))
        return other

    def resolve(name):
        if name in mapping:
            return mapping[name]
        if name in have:
            mapping[name] = name
            return name
        same = lower.get(name.lower())                # Bip001 Chin / Bip001 chin (the families spell face bones apart)
        if same and near(name, same):
            return alias(name, same)
        spelt = sorted((n for n in squeezed.get(re.sub(r"[\s_]", "", name.lower()), []) if near(name, n)),
                       key=lambda n: (m_head[n] - n_head[name]).length)
        if spelt:
            return alias(name, spelt[0])
        for pattern, repl in ALIASES:
            if pattern.match(name):
                other = pattern.sub(repl, name)
                if other in have and near(name, other):
                    return alias(name, other)
        mapping[name] = None                          # to add, unless a child tells (set first: no cycles)
        bone = nude_arm.data.bones.get(name)
        for child in (bone.children if bone is not None else ()):
            below = resolve(child.name)
            up = model_arm.data.bones[below].parent if below else None
            if up is not None and near(name, up.name):
                return alias(name, up.name, ", parent of %s" % below)
        return None
    return resolve, mapping


def map_bones(model_arm, nude_arm, names, log):
    """Model bone for every nude bone the body uses (bone_resolver), else a bone to add.
    Returns ({nude name: model name}, [names to add, parents first])."""
    resolve, mapping = bone_resolver(model_arm, nude_arm, log)
    add = set()
    for name in names:
        bone = nude_arm.data.bones.get(name)
        while bone is not None and resolve(bone.name) is None:
            add.add(bone.name)
            bone = bone.parent
    order = [b.name for b in nude_arm.data.bones if b.name in add]      # bones are stored parents first
    for name in order:
        mapping[name] = name
    return mapping, order


def add_bones(model_arm, nude_arm, order, mapping):
    """The nude bones to add, at their nude rest pose, under the mapped parent."""
    if not order:
        return
    to_model = model_arm.matrix_world.inverted() @ nude_arm.matrix_world
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    model_arm.hide_set(False)
    model_arm.select_set(True)
    bpy.context.view_layer.objects.active = model_arm
    bpy.ops.object.mode_set(mode="EDIT")
    edit = model_arm.data.edit_bones
    for name in order:
        src = nude_arm.data.bones[name]
        eb = edit.new(name)
        eb.head = (0.0, 0.0, 0.0)
        eb.tail = (0.0, max(src.length, 0.002), 0.0)
        eb.matrix = to_model @ src.matrix_local
        eb.use_deform = src.use_deform
        eb.use_connect = False
        eb.parent = edit.get(mapping.get(src.parent.name, src.parent.name)) if src.parent else None
    bpy.ops.object.mode_set(mode="OBJECT")


def rename_groups(obj, mapping):
    """Vertex groups named after nude bones -> the mapped model bones (two nude groups onto one model bone add up)."""
    for g in list(obj.vertex_groups):
        target = mapping.get(g.name)
        if not target or target == g.name:
            continue
        other = obj.vertex_groups.get(target)
        if other is None:
            g.name = target
            continue
        for v in obj.data.vertices:
            w = next((x.weight for x in v.groups if x.group == g.index), 0.0)
            if w > 0:
                cur = next((x.weight for x in v.groups if x.group == other.index), 0.0)
                other.add([v.index], cur + w, "REPLACE")
        obj.vertex_groups.remove(g)


def kd_of(points):
    kd = kdtree.KDTree(len(points))
    for k, p in enumerate(points):
        kd.insert(Vector(p), k)
    kd.balance()
    return kd


def open_edges(obj, slots=None):
    """Open edges of obj's faces (those in slots), vertices at the same place taken as one (the meshes are split
    along their UV seams): (world positions, key vertex per vertex, {key: {neighbour key, ...}})."""
    co = world_co(obj)
    key = np.arange(len(co))
    for group in coincident(co):
        key[group] = group.min()
    count = {}
    for p in obj.data.polygons:
        if slots is None or p.material_index in slots:
            vs = [int(key[v]) for v in p.vertices]
            for a, b in zip(vs, vs[1:] + vs[:1]):
                e = (a, b) if a < b else (b, a)
                count[e] = count.get(e, 0) + 1
    adj = {}
    for (a, b), c in count.items():
        if c == 1:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    return co, key, adj


def runs(adj, chosen):
    """The chosen vertices of an open-edge graph as ordered runs: [(vertices, closed), ...]."""
    left, out = set(chosen), []
    while left:
        ends = sorted(v for v in left if len(adj[v] & left) == 1)
        run = [ends[0] if ends else min(left)]
        left.discard(run[0])
        while True:
            nxt = sorted(adj[run[-1]] & left)
            if not nxt:
                break
            run.append(nxt[0])
            left.discard(nxt[0])
        out.append((run, len(run) > 2 and run[0] in adj[run[-1]]))
    return out


def follow(pa, pb, closed):
    """Order of run b's points that runs along run a: same direction, a closed run starting next to a's start."""
    m = len(pb)
    if not closed:
        fwd = np.linalg.norm(pa[0] - pb[0]) + np.linalg.norm(pa[-1] - pb[-1])
        rev = np.linalg.norm(pa[0] - pb[-1]) + np.linalg.norm(pa[-1] - pb[0])
        return list(range(m)) if fwd <= rev else list(range(m - 1, -1, -1))
    c = pb.mean(axis=0)
    n = np.linalg.svd(pb - c)[2][2]

    def turn(p):
        q = p - c
        return float(np.dot(np.cross(q, np.roll(q, -1, axis=0)).sum(axis=0), n))

    order = list(range(m)) if turn(pa) * turn(pb) > 0 else list(range(m - 1, -1, -1))
    start = int(np.argmin(np.linalg.norm(pb[order] - pa[0], axis=1)))
    return order[start:] + order[:start]


def by_length(pa, pb, closed, anchors=()):
    """For each point of run a, the point of run b at the same share of the way (both runs go the same way), as
    (segment S, share u): segment S runs from b[S % m] to b[(S + 1) % m].  Anchors (i, j) - point i of a already
    on vertex j of b (d01: 19 of 54) - split the runs into stretches matched each on its own; without any, a closed
    pair is one stretch from point 0 / vertex 0 and an open pair runs end to end.  S never decreases from point 0
    on (a closed run's may pass m: once round)."""
    n, m = len(pa), len(pb)

    def lengths(p, start, stop):
        q = p[[k % len(p) for k in range(start, stop + 1)]]
        return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])

    if closed:
        marks = sorted(set(anchors)) or [(0, 0)]
        i0, j0 = marks[0]
        keep = [(i0, j0)]
        for i, j in marks[1:]:                      # anchors going round the head the other way are left out
            jj = j0 + (j - j0) % m
            if jj > keep[-1][1]:
                keep.append((i, jj))
        keep.append((i0 + n, j0 + m))
    else:
        keep = [(0, 0)]
        for i, j in sorted(set(anchors)):
            if 0 < i < n - 1 and keep[-1][1] < j < m - 1:
                keep.append((i, j))
        keep.append((n - 1, m - 1))
    spot = {}
    for (ia, ja), (ib, jb) in zip(keep, keep[1:]):
        ta, tb = lengths(pa, ia, ib), lengths(pb, ja, jb)
        ta, tb = ta / max(ta[-1], 1e-12), tb / max(tb[-1], 1e-12)
        for k, t in enumerate(ta[:-1]):             # a stretch's end is the next one's start
            if jb == ja:
                spot[ia + k] = (ja, 0.0)
                continue
            s = int(np.clip(np.searchsorted(tb, t, side="right") - 1, 0, jb - ja - 1))
            spot[ia + k] = (ja + s, float(np.clip((t - tb[s]) / max(tb[s + 1] - tb[s], 1e-12), 0.0, 1.0)))
    def exact(s, u):                                # on a vertex: say so (no zero-area sliver next to it)
        return (s + 1, 0.0) if u > 1.0 - 1e-6 else (s, 0.0 if u < 1e-6 else u)

    if not closed:
        spot[n - 1] = (m - 1, 0.0)
        return [exact(*spot[i]) for i in range(n)]
    first = keep[0][0]
    out = [(spot[i][0], spot[i][1]) if i >= first else (spot[i + n][0] - m, spot[i + n][1]) for i in range(n)]
    shift = -(out[0][0] // m) * m                   # point 0 on the head's first round
    return [exact(s + shift, u) for s, u in out]


def edge_loops(vref, members, a, b):
    """The body face along the open edge between the places a and b (vertex keys): (its loop at a, its loop at b,
    True when the face runs a -> b), or None."""
    mb = set(members[b])
    for i in members[a]:
        for loop in vref[i].link_loops:
            if loop.link_loop_next.vert.index in mb:
                return loop, loop.link_loop_next, True
            if loop.link_loop_prev.vert.index in mb:
                return loop, loop.link_loop_prev, False
    return None


def stitch(body, head, seam, report):
    """Close what the seam snap leaves open where the head's neck opening and the body's open edge next to it do not
    share vertices (c02: 44 head vertices against 48 nude ones, 6-12 mm apart; b01 / g04 / a08 meet vertex for
    vertex - nothing to do).  Along each pair of edge runs, matched by their share of the run's length, every body
    edge vertex goes onto the head's edge at that point, between two of its vertices (a seam entry: place, weights
    and normal blended from the two - snapped to vertices, 48 onto 44 put two on one in four places and the
    collapsed faces caught the light); each head vertex gets a new body vertex in a sliver triangle between the two
    body vertices around it; the body within STITCH_FALLOFF of the edge follows by a fading share of the move, so
    the stretch spreads over a few rings and the texture stays the body's own (a strip of new faces between the two
    edges showed streaks: no UVs fit there).  Returns the new seam entries."""
    if head is None:
        return []
    skin = {i for i, s in enumerate(head.material_slots) if not (s.material and base(s.material.name) in HEAD_EXTRAS)}
    hco, hkey, hadj = open_edges(head, skin)
    bco, bkey, badj = open_edges(body)
    if not hadj or not badj:
        return []
    hk, bk = sorted(hadj), sorted(badj)
    to_head = kd_of(hco[hk])
    near_b = sorted(v for v in bk if to_head.find(Vector(bco[v]))[2] <= STITCH_REACH)
    if not near_b:
        return []
    to_body = kd_of(bco[near_b])
    dist_h = {v: to_body.find(Vector(hco[v])) for v in hk}
    near_h = sorted(v for v in hk if dist_h[v][2] <= STITCH_REACH)
    joined = {}                                     # body key -> head key it already sits on
    for i, obj, j in seam:
        if obj is head and int(bkey[i]) in near_b and int(hkey[j]) in near_h:
            joined[int(bkey[i])] = int(hkey[j])
    for v in near_h:
        if dist_h[v][2] <= JOINED:
            joined.setdefault(near_b[dist_h[v][1]], v)
    report["stitch"] = {"head_edge": len(near_h), "body_edge": len(near_b), "joined": len(joined),
                        "unreached": int(sum(1 for v in hk if STITCH_REACH < dist_h[v][2] <= 2 * STITCH_REACH))}
    if set(near_b) <= set(joined) and set(near_h) <= set(joined.values()):
        return []
    members = {}                                    # key -> the vertices at that place (UV seam copies)
    for i, k in enumerate(bkey):
        members.setdefault(int(k), []).append(i)
    # an edge vertex the seam snap put on a head vertex off the head's edge (d01, j02, k01: it pulled the vertex
    # back 7-10 mm after the stitch had moved it): the stitch's point wins (seam is changed in place)
    edge_members = {i for v in near_b for i in members[v]}
    off_edge = {e[0] for e in seam if e[0] in edge_members and int(bkey[e[0]]) not in joined}
    if off_edge:
        seam[:] = [e for e in seam if e[0] not in off_edge]
    report["stitch"]["reseamed"] = len(off_edge)
    have = {i for i, _o, _j in seam}
    inv = np.array(body.matrix_world.inverted())
    to_local = inv[:3, :3]
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    uv_layers = list(bm.loops.layers.uv.values())
    shape_layers = list(bm.verts.layers.shape.values())
    vref = {i: bm.verts[i] for v in near_b for i in members[v]}     # before new vertices age the lookup table
    entries, moves, made, slivers = [], {}, {}, 0
    head_runs = runs(hadj, near_h)
    for brun, bclosed in runs(badj, near_b):
        pa = bco[brun]
        kd_a = kd_of(pa)
        hrun, hclosed = min(head_runs, key=lambda r: float(np.mean([kd_a.find(Vector(hco[v]))[2] for v in r[0]])))
        closed = bclosed and hclosed
        if hclosed and not closed:                  # an open body run along a closed head loop: cut the loop there
            k = int(np.argmin(np.linalg.norm(hco[hrun] - pa[0], axis=1)))
            hrun = hrun[k:] + hrun[:k]
        hrun = [hrun[k] for k in follow(pa, hco[hrun], closed)]
        m = len(hrun)
        pos = {h: k for k, h in enumerate(hrun)}
        anchors = [(i, pos[joined[v]]) for i, v in enumerate(brun) if v in joined and joined[v] in pos]
        spot = by_length(pa, hco[hrun], closed, anchors)    # per body vertex: (segment, share) on the head run
        for v, (s, u) in zip(brun, spot):
            j, k = hrun[s % m], hrun[(s + 1) % m]
            moves[v] = (1.0 - u) * hco[j] + u * hco[k] - bco[v]
            # between two head vertices: no two body vertices share one
            target = j if u == 0.0 else (k if u == 1.0 else (j, k, u))
            entries += [(i, head, target) for i in members[v] if i not in have]
        for a in range(len(brun) if closed else len(brun) - 1):
            b = (a + 1) % len(brun)
            s0, s1 = spot[a][0], spot[b][0] + (m if closed and b == 0 else 0)
            # the head vertices passed between the two (not one the next body vertex sits on)
            between = [hrun[t % m] for t in range(s0 + 1, s1 + 1) if not (t == s1 and spot[b][1] == 0.0)]
            if not between or len(between) > m // 2:
                continue
            hit = edge_loops(vref, members, brun[a], brun[b])
            if hit is None:
                continue
            la, lb, forward = hit                   # the body face along the edge: the sliver runs it the other way
            ua = [tuple(la[layer].uv) for layer in uv_layers]
            ub = [tuple(lb[layer].uv) for layer in uv_layers]
            chain = []
            for n, h in enumerate(between):         # the head's own corner between the two: a sliver triangle
                if h not in made:
                    local = Vector(to_local @ hco[h] + inv[:3, 3])
                    nv = bm.verts.new(local)
                    for layer in shape_layers:
                        nv[layer] = local
                    bm.verts.index_update()
                    made[h] = nv
                    entries.append((nv.index, head, h))
                f = (n + 1) / (len(between) + 1)
                chain.append((made[h], [tuple(np.add(np.multiply(x, 1 - f), np.multiply(y, f))) for x, y in zip(ua, ub)]))
            poly = [(la.vert, ua)] + chain + [(lb.vert, ub)]
            if not forward:
                poly = poly[::-1]
            for k in range(1, len(poly) - 1):
                tri = [poly[0], poly[k], poly[k + 1]]
                verts = [x[0] for x in tri]
                if len({x.index for x in verts}) < 3 or bm.faces.get(verts) is not None:
                    continue
                face = bm.faces.new(verts)
                face.material_index = la.face.material_index
                for loop, (_v, uv) in zip(face.loops, tri):
                    for layer, value in zip(uv_layers, uv):
                        loop[layer].uv = value
                slivers += 1
    # the edge onto the head, the body near it after it by a fading share (inverse-distance mean of the nearest moves)
    keys = sorted(moves)
    start = bco[keys]
    disp = np.array([moves[v] for v in keys])
    near = kd_of(start)
    moved = 0
    for vert in bm.verts:
        i = vert.index
        if i >= len(bco):
            continue
        k = int(bkey[i])
        if k in moves:
            d = moves[k]
        elif i in have:                             # pinned to the head by the seam anyway
            continue
        else:
            found = near.find_n(Vector(bco[i]), 4)
            dmin = found[0][2] if found else STITCH_FALLOFF
            if dmin >= STITCH_FALLOFF:
                continue
            w = np.array([1.0 / (dd + 1e-4) for _c, _j, dd in found])
            d = (w[:, None] * disp[[j for _c, j, _dd in found]]).sum(axis=0) / w.sum()
            d = d * (1.0 - dmin / STITCH_FALLOFF) ** 2
        vert.co = Vector(to_local @ (bco[i] + d) + inv[:3, 3])
        for layer in shape_layers:
            vert[layer] = vert.co.copy()
        moved += 1
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    report["stitch"].update(moved_edge=len(moves), max_move_mm=round(float(np.linalg.norm(disp, axis=1).max()) * 1000, 2),
                            followed=moved - sum(len(members[v]) for v in moves), slivers=slivers, new_verts=len(made))
    return entries


def seam_match(body, seam_parts):
    """[(body vertex, part object, part vertex)]: body vertices within SEAM of a kept head / face vertex."""
    refs, pts = [], []
    for obj, verts in seam_parts:
        co = world_co(obj)
        refs += [(obj, j) for j in verts]
        pts += [co[j] for j in verts]
    if not pts:
        return []
    kd = kdtree.KDTree(len(pts))
    for k, p in enumerate(pts):
        kd.insert(Vector(p), k)
    kd.balance()
    out = []
    for i, p in enumerate(world_co(body)):
        _co, k, d = kd.find(Vector(p))
        if d <= SEAM:
            out.append((i,) + refs[k])
    return out


def body_weights(body, columns, skin_parts, seam, report):
    """The nude base's weights over the model's bones; seam vertices copy the weights of their head / face vertex.
    Also measures how much of the body the dressed model already had: vertices on its old skin, and how far each
    lies from it (snap, world space; the full variant puts them there - g04's fingers in the gloves are 1 mm out)."""
    P = world_co(body)
    w = dense_weights(body, columns)
    n = len(P)
    old = np.zeros(n, dtype=bool)
    snap = np.zeros((n, 3))
    for obj, slots in skin_parts.items():
        tree = bvh(world_co(obj), triangles(obj, set(slots)))
        for i in range(n):
            if not old[i]:
                loc = tree.find_nearest(Vector(P[i]), SAME)[0]
                if loc is not None:
                    old[i] = True
                    snap[i] = np.array(loc) - P[i]
    copied = 0
    part_w = {}
    for i, obj, j in seam:
        if obj not in part_w:
            part_w[obj] = dense_weights(obj, columns, sorted({x for _i, o, jj in seam if o is obj
                                                              for x in seam_point(jj)[:2]}))
        a, b, t = seam_point(j)
        wj = (1.0 - t) * part_w[obj][a] + t * part_w[obj][b]
        if wj.sum() > 0:
            w[i] = wj
            copied += 1
    w = limit_normalize(w)
    if DEBUG_ATTR:
        attr = body.data.attributes.new("cn_old_skin", "FLOAT", "POINT")
        attr.data.foreach_set("value", old.astype(np.float32))
    report["weights"] = {"verts": n, "on_old_skin": int(old.sum()), "new": int(n - old.sum()), "seam": copied,
                         "unweighted": int((w.sum(1) < 0.99).sum())}
    return w, old, snap


def loop_vertex_normals(obj):
    """Per-vertex normal of obj in world space: the mean of its (custom) split normals."""
    me = obj.data
    me.calc_normals_split()
    ln = np.empty(len(me.loops) * 3, dtype=np.float64)
    me.loops.foreach_get("normal", ln)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    vn = np.zeros((len(me.vertices), 3))
    np.add.at(vn, lv, ln.reshape(-1, 3))
    vn = vn @ np.array(obj.matrix_world.to_3x3().inverted().transposed()).T
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)


def seam_point(j):
    """A seam target as (vertex, vertex, share of the way to the second): a head / face vertex, or a point on the
    head's edge between two of its vertices (stitch)."""
    return (j, j, 0.0) if isinstance(j, (int, np.integer)) else j


def close_seam(body, seam):
    """Seam vertices move onto their head / face vertex (g04's head and the nude face differ by up to 0.62 mm)
    and take its normal: the head's custom normals were made to continue into the game's own neck / skin, while
    the cut nude mesh's are re-derived from the faces left at the edge - a shading line along the jaw."""
    if not seam:
        return {"verts": 0}
    me = body.data
    inv = body.matrix_world.inverted()
    to_local = np.array(body.matrix_world.to_3x3())        # normals: row @ M = M^T n, the inverse of the world map
    normals = {}
    moved = []
    keys = me.shape_keys.key_blocks if me.shape_keys else []       # full variant: basis + NUDE_SHAPE
    for i, obj, j in seam:
        if obj not in normals:
            normals[obj] = loop_vertex_normals(obj)
        a, b, t = seam_point(j)
        target = inv @ (obj.matrix_world @ obj.data.vertices[a].co.lerp(obj.data.vertices[b].co, t))
        moved.append((target - me.vertices[i].co).length)
        me.vertices[i].co = target
        for kb in keys:
            kb.data[i].co = target
    me.update()
    me.calc_normals_split()
    ln = np.empty(len(me.loops) * 3, dtype=np.float64)
    me.loops.foreach_get("normal", ln)
    ln = ln.reshape(-1, 3)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    want = {}
    for i, obj, j in seam:
        a, b, t = seam_point(j)
        want[i] = ((1.0 - t) * normals[obj][a] + t * normals[obj][b]) @ to_local
    for k in np.nonzero(np.isin(lv, list(want)))[0]:
        n = want[int(lv[k])]
        ln[k] = n / max(np.linalg.norm(n), 1e-12)
    me.use_auto_smooth = True
    me.normals_split_custom_set([tuple(x) for x in ln])
    return {"verts": len(want), "max_move_mm": round(max(moved) * 1000.0, 3)}


def write_groups(obj, columns, w):
    obj.vertex_groups.clear()
    used = np.nonzero(w.sum(0) > 0)[0]
    for c in used:
        g = obj.vertex_groups.new(name=columns[c])
        for i in np.nonzero(w[:, c] > 0)[0]:
            g.add([int(i)], float(w[i, c]), "REPLACE")
    return len(used)


def delete_faces(obj, slots):
    """Delete the faces of these material slots (and loose vertices), then the emptied slots."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in slots], context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    for index in sorted(slots, reverse=True):
        if index < len(obj.data.materials):
            obj.data.materials.pop(index=index)       # shifts the higher face indices down
    return len(obj.data.polygons)


def split_off(obj, slots, suffix):
    """A copy of obj holding only these slots' faces (the slots are deleted from obj); returns the copy."""
    part = obj.copy()
    part.data = obj.data.copy()
    for coll in obj.users_collection:
        coll.objects.link(part)
    part.name = part.data.name = base(obj.name) + suffix
    delete_faces(part, set(range(len(part.material_slots))) - set(slots))
    delete_faces(obj, set(slots))
    return part


def neighbours_mean(values, edges, n):
    """Mean of each vertex's neighbours (values: one number or one vector per vertex)."""
    total = np.zeros((n,) + values.shape[1:])
    count = np.zeros(n)
    np.add.at(total, edges[:, 0], values[edges[:, 1]])
    np.add.at(total, edges[:, 1], values[edges[:, 0]])
    np.add.at(count, edges[:, 0], 1)
    np.add.at(count, edges[:, 1], 1)
    return total / np.maximum(count, 1).reshape((n,) + (1,) * (values.ndim - 1))


def outfit_tree(outfit):
    """The outfit's triangles in one BVH (None without any)."""
    pts, tris, offset = [], [], 0
    for obj in outfit:
        t = triangles(obj)
        if len(t):
            co = world_co(obj)
            pts.append(co)
            tris.append(t + offset)
            offset += len(co)
    return bvh(np.concatenate(pts), np.concatenate(tris)) if pts else None


def outfit_hit(tree, origin, direction, limit, nv):
    """The first outfit face along the ray whose normal looks the way the skin normal nv does - the outside of the
    outfit over this skin, not a lining, an insole or the far side of the garment: (location, normal, distance)
    or None."""
    start, gone = origin, 0.0
    for _ in range(8):
        loc, nor, _index, d = tree.ray_cast(start, direction, limit - gone)
        if loc is None:
            return None
        gone += d
        if nor.dot(nv) > FACING:
            return loc, nor, gone
        start, gone = loc + direction * 1e-5, gone + 1e-5
        if gone >= limit:
            return None
    return None


def sphere_directions(count):
    """`count` directions spread evenly over the sphere (Fibonacci)."""
    k = np.arange(count) + 0.5
    z = 1.0 - 2.0 * k / count
    r = np.sqrt(1.0 - z * z)
    a = np.pi * (1.0 + 5 ** 0.5) * k
    return [Vector((float(x), float(y), float(w))) for x, y, w in zip(r * np.cos(a), r * np.sin(a), z)]


EXPOSE_DIRS = sphere_directions(64)
EXPOSE_CONE = 0.2        # ... looking out within about 78 degrees of the vertex normal
EXPOSE_NEAR = 0.005      # ... for vertices this close to the outfit


def hide_exposed(body, P, N, axis, disp, verts, otree, weld):
    """Last pass of the fit, judged by what can be seen: a vertex close under the outfit that a ray from it
    (EXPOSE_DIRS within EXPOSE_CONE of the body's own normal there - the squeezed surface may face anywhere) leaves
    past the outfit and the body is still showing through: a fingertip past the tip of a glove, a nail.  So is one
    the outfit covers by less than HIDE_MARGIN that way (it flickers through in a render).  It moves toward its
    skeleton point by HIDE_STEP until hidden, at most HIDE_MAX.  Returns how many still show."""
    tris = triangles(body)
    inward = np.zeros(len(P))
    shown = [i for i in verts if otree.find_nearest(Vector(P[i] + disp[i]), EXPOSE_NEAR)[0] is not None]
    for _ in range(int(round(HIDE_MAX / HIDE_STEP)) + 1):
        Q = P + disp
        btree = bvh(Q, tris)
        exposed = []
        for i in shown:
            q, nv = Vector(Q[i]), Vector(N[i])
            for d in EXPOSE_DIRS:
                if d.dot(nv) < EXPOSE_CONE:
                    continue
                hit = otree.ray_cast(q + d * 1e-5, d, 1.0)
                if (hit[0] is not None and hit[3] < HIDE_MARGIN or
                        hit[0] is None and btree.ray_cast(q + d * 3e-4, d, 1.0)[0] is None):
                    exposed.append(i)
                    break
        shown = [i for i in exposed if inward[i] < HIDE_MAX - 1e-9]
        if not shown:
            break
        for i in shown:
            way = axis[i] - Q[i]
            length = np.linalg.norm(way)
            disp[i] += (way / length if length > 1e-6 else -N[i]) * min(HIDE_STEP, 0.5 * length)
            inward[i] += HIDE_STEP
        weld()
    return len(shown)


def skeleton_points(P, w, columns, arm):
    """For every vertex the point inside the body it shrinks toward when the outfit squeezes it: the closest
    points on its bones (head..tail at rest), blended by its weights - a toe or a finger in a pointed shoe or a
    tight glove gets thinner and shorter instead of folding."""
    mw = arm.matrix_world
    out = np.zeros_like(P)
    total = np.zeros(len(P))
    for c, name in enumerate(columns):
        idx = np.nonzero(w[:, c] > 0)[0]
        bone = arm.data.bones.get(name)
        if not len(idx) or bone is None:
            continue
        h, t = np.array(mw @ bone.head_local), np.array(mw @ bone.tail_local)
        seg = t - h
        k = np.clip(((P[idx] - h) @ seg) / max(seg @ seg, 1e-12), 0.0, 1.0)
        out[idx] += w[idx, c][:, None] * (h + k[:, None] * seg)
        total[idx] += w[idx, c]
    return np.where(total[:, None] > 0, out / np.maximum(total, 1e-12)[:, None], P)


def coincident(P, tol=1e-5):
    """Groups of vertices at the same place (the body is split along its UV seams): [index array, ...]."""
    kd = kdtree.KDTree(len(P))
    for i, p in enumerate(P):
        kd.insert(Vector(p), i)
    kd.balance()
    seen, groups = set(), []
    for i, p in enumerate(P):
        if i in seen:
            continue
        group = [j for _co, j, _d in kd.find_range(Vector(p), tol)]
        if len(group) > 1:
            seen.update(group)
            groups.append(np.array(group))
    return groups


def outfit_move(q, nv, axis, otree, btree):
    """How far body vertex q (normal nv) must move to sit CLEAR under the outfit (None: it does not): toward its
    skeleton point `axis` (skeleton_points), so a toe in a pointed shoe is squeezed thinner instead of being pushed
    through its other side or folded over; along the outfit's normal where that way does not lead inside."""
    hits = []
    hit = outfit_hit(otree, q - nv * 1e-4, nv, PROBE, nv)                 # outfit over the skin
    if hit:
        hits.append(hit)
    hit = outfit_hit(otree, q + nv * 1e-4, -nv, PROBE_IN, nv)            # outfit inside: the skin pokes through
    if hit:
        exit_loc, _n, _i, exit_d = btree.ray_cast(q - nv * 6e-4, -nv, PROBE_IN)
        if exit_loc is None or exit_d + 4e-4 > hit[2]:        # ... unless the ray left the body first (the far
            hits.append(hit)                                   # side of a toe, then the sole of its shoe)
    best, most = None, 0.0
    for loc, nor, _d in hits:
        depth = (q - loc).dot(nor) + CLEAR                     # > 0: not CLEAR inside the outfit yet
        if depth > most:
            best, most = -nor * depth, depth
            inward = axis - q
            room = inward.length
            if room > 1e-6:
                along = -(inward / room).dot(nor)              # how much of a step toward the axis goes inside
                if along > 0.3 and depth / along < 0.8 * room:
                    best = inward / room * (depth / along)
    return best


def fit_under_outfit(body, outfit, fixed, base, axis, report):
    """Full variant: the body under the outfit must not show through it.  Vertices that sit closer than CLEAR
    under the outfit, or poke out through it, move CLEAR inside it; the displacement is smoothed over the
    neighbours and the projection repeated (FIT_ROUNDS), so the body is squeezed in smoothly.  Fixed vertices
    only take `base`: where the dressed model had skin they go exactly onto it - skin and outfit already sit as
    the game shows them there (a08's bra cups and back panel dip under the kept skin near their edges; moving
    those dented the breasts 13 mm), and the nude body lies up to 1 mm off it (g04's fingertips poked out of the
    gloves) - and the seam with the head stays.
    A pointed shoe or a tight glove squeezes toes and fingers out of shape, so the body keeps its own shape as
    the shape key NUDE_SHAPE (the basis is the fitted one): the PMX's 衣服非表示 morph switches it on together with
    hiding the outfit, the XPS writes that part of the body twice (export_suit_xps_blender.py)."""
    P = world_co(body)
    N = world_normals(body)
    btree = bvh(P, triangles(body))
    otree = outfit_tree(outfit)
    if otree is None:
        return 0
    n = len(P)
    free = ~fixed
    near = [i for i in np.nonzero(free)[0] if otree.find_nearest(Vector(P[i]), PROBE_IN)[0] is not None]
    # the copies of a vertex on both sides of a UV seam share one normal and one displacement (else the seam opens)
    seams = coincident(P)
    for group in seams:
        N[group] = N[group].sum(0) / max(np.linalg.norm(N[group].sum(0)), 1e-12)
    edges = np.array([tuple(e.vertices) for e in body.data.edges] +
                     [(g[0], k) for g in seams for k in g[1:]], dtype=np.int64)
    disp = np.where(fixed[:, None], base, 0.0)

    def weld():
        for group in seams:
            disp[group] = disp[group].mean(0)

    def project():
        """Move every vertex that needs it; returns how many moved more than 0.05 mm."""
        count = 0
        for i in near:
            move = outfit_move(Vector(P[i] + disp[i]), Vector(N[i]), Vector(axis[i]), otree, btree)
            if move is not None:
                disp[i] += np.array(move)
                count += move.length > 5e-5
        weld()
        return count
    needed = project()
    for _ in range(FIT_ROUNDS):
        for _ in range(3):
            disp = np.where(free[:, None], 0.5 * disp + 0.5 * neighbours_mean(disp, edges, n), base)
            weld()
        project()
    for _ in range(6):                # without smoothing until nothing moves any more
        left = project()
        if not left:
            break
    shown = hide_exposed(body, P, N, axis, disp, near, otree, weld)
    push = np.linalg.norm(disp, axis=1)
    if DEBUG_ATTR:
        attr = body.data.attributes.new("cn_push", "FLOAT", "POINT")
        attr.data.foreach_set("value", (push * 1000.0).astype(np.float32))      # mm
    inv = np.array(body.matrix_world.inverted())
    fitted = ((P + disp) @ inv[:3, :3].T + inv[:3, 3]).astype(np.float32).ravel()
    if body.data.shape_keys is None:
        body.shape_key_add(name="Basis", from_mix=False)
    body.shape_key_add(name=NUDE_SHAPE, from_mix=False)        # a copy of the basis: the shape before the fit
    body.data.shape_keys.key_blocks[0].data.foreach_set("co", fitted)
    body.data.vertices.foreach_set("co", fitted)
    body.data.update()
    report["fit"] = {"needed": needed, "moved": int((push > 1e-5).sum()),
                     "max_push_mm": round(float(push.max() * 1e3), 2), "left_after_fit": left,
                     "onto_old_skin": int((fixed & (np.linalg.norm(base, axis=1) > 1e-6)).sum()),
                     "still_shown": shown,
                     "shape_key": NUDE_SHAPE}
    return int((push > 1e-5).sum())


def source_materials(meshes):
    """A kept slot whose game material (roe_source_materials) has an HQ material in the file but wears another
    HQ material gets it back: a08's braid ring is drawn with the outfit atlas (pc_a08_hd_body2) and the HQ pass
    had put the hair material on it (a grey band instead of gold; hq_materials_blender.py is fixed too)."""
    fixed = []
    for obj in meshes:
        for index, source in slot_sources(obj).items():
            slot = obj.material_slots[index]
            want = bpy.data.materials.get("HQ_" + source)
            if want is not None and slot.material is not None and slot.material != want \
                    and base(slot.material.name).startswith("HQ_"):
                fixed.append("%s[%d] %s -> %s" % (obj.name, index, slot.material.name, want.name))
                slot.material = want
    return fixed


def albedo_pixels(mat, size=1024):
    """An HQ material's colour texture (node hq_albedo) scaled to size x size as an (h, w, 3) array, and the UV map
    its texture coordinates come from ("" = the active one); (None, "") without one."""
    nodes = mat.node_tree.nodes if mat is not None and mat.use_nodes and mat.node_tree else None
    node = nodes.get("hq_albedo") if nodes else None
    if node is None or node.image is None:
        return None, ""
    img = node.image.copy()
    try:
        img.scale(size, size)
        px = np.empty(size * size * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
    except (RuntimeError, ValueError):
        return None, ""
    finally:
        bpy.data.images.remove(img)
    uv = nodes.get("hq_uv")
    return px.reshape(size, size, 4)[:, :, :3], (uv.uv_map if uv is not None else "")


def texel(tex, uv):
    h, w = tex.shape[:2]
    x = np.clip((np.mod(uv[:, 0], 1.0) * w).astype(int), 0, w - 1)
    y = np.clip((np.mod(uv[:, 1], 1.0) * h).astype(int), 0, h - 1)
    return tex[y, x]


def loop_uvs(obj, name):
    me = obj.data
    layer = (me.uv_layers.get(name) if name else None) or me.uv_layers.active
    if layer is None:
        return None
    uv = np.empty(len(me.loops) * 2)
    layer.data.foreach_get("uv", uv)
    return uv.reshape(-1, 2)


def nude_colour(nude_body, body_slot):
    """f(world points) -> the nude body's texture colour at the nearest point of its body slot, or None."""
    tex, name = albedo_pixels(nude_body.material_slots[body_slot].material)
    uv = loop_uvs(nude_body, name)
    if tex is None or uv is None:
        return None
    me = nude_body.data
    me.calc_loop_triangles()
    tris = [t for t in me.loop_triangles if t.material_index == body_slot]
    tv = np.array([t.vertices[:] for t in tris], dtype=np.int64)
    tl = np.array([t.loops[:] for t in tris], dtype=np.int64)
    co = world_co(nude_body)
    tree = bvh(co, tv)

    def colour(points):
        hits = [tree.find_nearest(Vector(p)) for p in points]
        idx = np.array([h[2] for h in hits])
        loc = np.array([h[0] for h in hits])
        a, b, c = co[tv[idx, 0]], co[tv[idx, 1]], co[tv[idx, 2]]
        v0, v1, v2 = b - a, c - a, loc - a
        d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
        d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
        den = d00 * d11 - d01 * d01
        den[np.abs(den) < 1e-20] = 1e-20
        wv, ww = (d11 * d20 - d01 * d21) / den, (d00 * d21 - d01 * d20) / den
        wu = 1.0 - wv - ww
        at = wu[:, None] * uv[tl[idx, 0]] + wv[:, None] * uv[tl[idx, 1]] + ww[:, None] * uv[tl[idx, 2]]
        return texel(tex, at)
    return colour


def colour_difference(obj, index, colour):
    """{face: mean |RGB| difference} of a slot's faces between its own texture and the nude body's at the same
    place (the centre and three points halfway to the corners), or None without textures."""
    tex, name = albedo_pixels(obj.material_slots[index].material)
    uv = loop_uvs(obj, name)
    if tex is None or uv is None:
        return None
    me = obj.data
    co = world_co(obj)
    lv = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    pts_uv, pts_co, owner = [], [], []
    for p in me.polygons:
        if p.material_index != index:
            continue
        li = np.array(p.loop_indices)
        cu, cc = uv[li], co[lv[li]]
        mu, mc = cu.mean(0), cc.mean(0)
        pts_uv += [mu] + [(x + mu) / 2 for x in cu[:3]]
        pts_co += [mc] + [(x + mc) / 2 for x in cc[:3]]
        owner += [p.index] * 4
    if not owner:
        return None
    d = np.abs(texel(tex, np.array(pts_uv)) - colour(np.array(pts_co))).mean(1)
    out = {}
    for f, v in zip(owner, d):
        out.setdefault(f, []).append(v)
    return {f: float(np.mean(v)) for f, v in out.items()}


def paint_patches(obj, index, diff):
    """Faces of the slot that are paint on the skin: those off by FACE_PAINTED and their neighbours (a vine half
    across a face), in patches with at least PAINT_MIN such faces."""
    seeds = {f for f, v in diff.items() if v > FACE_PAINTED}
    if len(seeds) < PAINT_MIN:
        return []
    me = obj.data
    at = {}
    for p in me.polygons:
        if p.material_index == index:
            for v in p.vertices:
                at.setdefault(v, []).append(p.index)
    grown = set(seeds)
    for f in seeds:
        for v in me.polygons[f].vertices:
            grown.update(at[v])
    key = np.arange(len(me.vertices))
    for group in coincident(world_co(obj)):
        key[group] = group.min()
    root = islands(sorted(grown), key, lambda f: me.polygons[f].vertices)
    count = {}
    for f in seeds:
        count[root[f]] = count.get(root[f], 0) + 1
    return sorted(f for f in grown if count.get(root[f], 0) >= PAINT_MIN)


def painted_skin(kinds, nude_body, body_slot, variant):
    """Skin slots by colour, against the nude body's colour at the same place.  A slot far off on the whole is
    clothing lying on the skin (l01's leotard and stockings, their own material on the skin's surface): outfit.  In
    the full variant, patches of a skin slot far off are paint on the skin (m02's vines and sleeves): they move to
    a new slot with the same material, an outfit slot that stays over the body (the rest of the slot is skin and
    goes as before).  Returns what it found."""
    colour = nude_colour(nude_body, body_slot)
    if colour is None:
        return {"error": "the nude body has no colour texture (hq_albedo)"}
    found = {}
    for obj, s in kinds.items():
        for index, kind in sorted(s.items()):
            if kind != "skin":
                continue
            diff = colour_difference(obj, index, colour)
            label = "%s[%d]" % (obj.name, index)
            if diff is None:
                found[label] = "no colour texture"
                continue
            median = round(float(np.median(list(diff.values()))), 3)
            if median > SLOT_PAINTED:
                s[index] = "outfit"
                found[label] = {"median": median, "as": "outfit: clothing on the skin"}
                continue
            faces = paint_patches(obj, index, diff) if variant == "full" else []
            found[label] = {"median": median, "painted_faces": len(faces)}
            if faces:
                obj.data.materials.append(obj.material_slots[index].material)
                new = len(obj.data.materials) - 1
                for f in faces:
                    obj.data.polygons[f].material_index = new
                s[new] = "outfit"
                found[label]["slot"] = new
    return found


def srgb_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((np.maximum(c, 0.0) + 0.055) / 1.055) ** 2.4)


def linear_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055)


def cielab(lin):
    """Linear RGB (D65) -> CIELAB."""
    xyz = np.asarray(lin, dtype=np.float64) @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722],
                                                         [0.0193, 0.1192, 0.9505]]).T
    f = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(f > (6 / 29) ** 3, np.cbrt(f), f / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def recorded_map(mat, key):
    """A texture file hq_materials_blender.py recorded on an HQ material: roe_hq_xps[key], or roe_hq_pmx for "pmx"."""
    if mat is None:
        return None
    if key == "pmx":
        return mat.get("roe_hq_pmx")
    try:
        return json.loads(mat.get("roe_hq_xps", "")).get(key)
    except (TypeError, ValueError, AttributeError):
        return None


def file_pixels(path, size=None):
    """An image file as an (h, w, 4) array of its stored (sRGB-encoded) values, scaled to size x size if given."""
    img = bpy.data.images.load(path, check_existing=False)
    try:
        if size:
            img.scale(size, size)
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(h, w, 4)
        if img.is_float:                    # a float image holds linear values
            px[:, :, :3] = linear_srgb(px[:, :, :3])
        return px
    finally:
        bpy.data.images.remove(img)


def tinted_copy(src, dst, gain, rows=256):
    """src with every texel's linear RGB times gain (alpha kept), written as an 8-bit PNG at dst."""
    px = file_pixels(src)
    h, w = px.shape[:2]
    for y in range(0, h, rows):
        block = px[y:y + rows, :, :3]
        px[y:y + rows, :, :3] = linear_srgb(srgb_linear(block) * gain)
    out = bpy.data.images.new("roe_tone_tmp", w, h, alpha=True)
    try:
        out.pixels.foreach_set(px.ravel())
        out.filepath_raw = dst
        out.file_format = "PNG"
        out.save()
    finally:
        bpy.data.images.remove(out)


def uv_name(mat):
    """The UV map an HQ material reads (node hq_uv), "" for the active one."""
    node = mat.node_tree.nodes.get("hq_uv") if mat is not None and mat.use_nodes and mat.node_tree else None
    return node.uv_map if node is not None else ""


def material_faces(obj, mat):
    slots = {i for i, s in enumerate(obj.material_slots) if s.material == mat}
    return [p.index for p in obj.data.polygons if p.material_index in slots]


def face_samples(parts, tex):
    """[(obj, faces, uv map)] -> (face centres, linear colour of tex at each face's UV centre, the faces' vertices),
    world space; None without faces."""
    cen, col, verts = [], [], []
    for obj, faces, uvmap in parts:
        uv = loop_uvs(obj, uvmap)
        if not faces or uv is None:
            continue
        co = world_co(obj)
        lv = np.empty(len(obj.data.loops), dtype=np.int64)
        obj.data.loops.foreach_get("vertex_index", lv)
        polys = obj.data.polygons
        c, at, vs = [], [], set()
        for f in faces:
            li = np.array(polys[f].loop_indices)
            c.append(co[lv[li]].mean(0))
            at.append(uv[li].mean(0))
            vs.update(lv[li].tolist())
        cen.append(np.array(c))
        col.append(srgb_linear(texel(tex, np.array(at))))
        verts.append(co[sorted(vs)])
    if not cen:
        return None
    return np.concatenate(cen), np.concatenate(col), np.concatenate(verts)


def seam_ratio(face_parts, face_tex, body_parts, body_tex, extra=()):
    """Colour jump at the seam between a face-material side and a body side: per seam vertex (a body-side vertex
    within TONE_TOUCH of a face-side one, plus `extra` points), the mean colour of each side's faces within
    TONE_REACH; returns (median face / body ratio, median face colour, median body colour, seam vertices, their
    positions, their ratios) in linear RGB, or None."""
    fs, bs = face_samples(face_parts, face_tex), face_samples(body_parts, body_tex)
    if fs is None or bs is None:
        return None
    near = kd_of(fs[2])
    seam = [p for p in bs[2] if near.find(Vector(p))[2] <= TONE_TOUCH] + [p for p in extra]
    fkd, bkd = kd_of(fs[0]), kd_of(bs[0])
    fside, bside, at = [], [], []
    for p in seam:
        fi = [k for _co, k, _d in fkd.find_range(Vector(p), TONE_REACH)]
        bi = [k for _co, k, _d in bkd.find_range(Vector(p), TONE_REACH)]
        if fi and bi:
            fside.append(fs[1][fi].mean(0))
            bside.append(bs[1][bi].mean(0))
            at.append(p)
    if len(fside) < TONE_SEAM_MIN:
        return None
    fside, bside = np.array(fside), np.array(bside)
    ratio = fside / np.maximum(bside, 1e-4)
    return np.median(ratio, 0), np.median(fside, 0), np.median(bside, 0), len(fside), np.array(at), ratio


def front_of(head, centre):
    """Horizontal unit vector from the neck towards the face: the head's eye slot (else the whole head) seen from
    the seam's centre."""
    co = world_co(head)
    eye = {i for i, s in enumerate(head.material_slots) if s.material and base(s.material.name) == "eye"}
    verts = sorted({v for p in head.data.polygons if p.material_index in eye for v in p.vertices})
    d = (co[verts] if verts else co).mean(0) - centre
    d[2] = 0.0
    n = np.linalg.norm(d)
    return d / n if n > 1e-6 else np.array([0.0, -1.0, 0.0])


def tone_match(head, body, body_mat, seam, nude_body, nude_slot, face_slot, stem):
    """Tint the body to the model's skin when its face is coloured unlike the family's: the body is the family nude
    base's skin, the head the model's own, so a tanned (b08_outfit1) or pale (k03, k07) face met the nude body in a
    colour line at the neck.  Measured on the PMX diffuse textures (albedo x _BaseColor x AO, what all three formats
    show): the colour jump across the model's seam (face side / body side, median over the seam vertices) against
    the jump across the nude base's own face / body seam; their ratio, per channel in linear RGB, is the gain that
    makes head and body meet as they do on the nude base (b14's face differs from the family's only in its AO, 16 %
    lighter along the neck's lower edge).  Applied over TONE_MIN to: the HQ material's _BaseColor (node hq_tint,
    the .blend) and tinted copies of its XPS / PMX diffuse files (same names, in <cache>\\tone\\<stem>\\) recorded on
    the material, so XPS and PMX carry it too."""
    face = head.material_slots[0].material if head is not None and head.material_slots else None
    base_face = nude_body.material_slots[face_slot].material if face_slot is not None else None
    paths = [recorded_map(m, "pmx") for m in (face, base_face, body_mat)]
    if body_mat is None or not all(p and os.path.isfile(p) for p in paths):
        return {"skipped": "no PMX diffuse on the face / nude face / body material"}
    if os.path.normcase(os.path.abspath(paths[0])) == os.path.normcase(os.path.abspath(paths[1])):
        return {"skipped": "the family's own face"}
    face_tex, base_tex, body_tex = (file_pixels(p, 1024)[:, :, :3] for p in paths)
    body_faces = (body, material_faces(body, body_mat), uv_name(body_mat))
    model = seam_ratio([(head, material_faces(head, face), uv_name(face)),
                        (body, material_faces(body, face), uv_name(face))], face_tex, [body_faces], body_tex,
                       extra=world_co(body)[[i for i, _obj, _j in seam]] if seam else ())
    polys = nude_body.data.polygons
    base = seam_ratio([(nude_body, [p.index for p in polys if p.material_index == face_slot], uv_name(base_face))],
                      base_tex,
                      [(nude_body, [p.index for p in polys if p.material_index == nude_slot], uv_name(body_mat))],
                      body_tex)
    if model is None or base is None:
        return {"skipped": "no seam measured (model %s, nude base %s)" % (model is not None, base is not None)}
    gain = model[0] / base[0]
    dE = float(np.linalg.norm(cielab(model[1]) - cielab(model[1] / gain)))     # the face against what it would be
    front = front_of(head, model[4].mean(0))
    halves = []
    for res in (model, base):
        ahead = (res[4] - res[4].mean(0)) @ front > 0.0
        halves.append([np.median(res[5][ahead], 0), np.median(res[5][~ahead], 0)])
    by_half = [halves[0][k] / halves[1][k] for k in (0, 1)]             # front, back
    spread = float(np.max(np.abs(by_half[0] / by_half[1] - 1.0)))
    out = {"dE": round(dE, 2), "gain": [round(float(g), 4) for g in gain],
           "front_back": [[round(float(g), 3) for g in h] for h in by_half], "spread": round(spread, 3),
           "jump": [round(float(x), 3) for x in model[0]], "nude_base_jump": [round(float(x), 3) for x in base[0]],
           "seam_points": [model[3], base[3]], "tinted": False}
    if dE < TONE_MIN:
        return out
    if spread > TONE_SPREAD:
        out["skipped"] = "the difference changes around the neck: one tint cannot match the front and the back"
        return out
    users = [o for o in bpy.data.objects if o not in (body, nude_body) and o.type == "MESH"
             and any(s.material == body_mat for s in o.material_slots)]
    if users:                                   # never tint another mesh's material with it (the nude base goes)
        mine = body_mat.copy()
        for s in body.material_slots:
            if s.material == body_mat:
                s.material = mine
        body_mat = mine
    tint = body_mat.node_tree.nodes.get("hq_tint") if body_mat.use_nodes else None
    if tint is not None and tint.type == "MIX_RGB":
        c = tint.inputs["Color2"].default_value
        tint.inputs["Color2"].default_value = (c[0] * gain[0], c[1] * gain[1], c[2] * gain[2], c[3])
        out["base_color"] = "hq_tint x gain"
    files = {}
    for key in ("diffuse", "pmx"):
        src = recorded_map(body_mat, key)
        if not (src and os.path.isfile(src)):
            continue
        folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(src))), "tone", stem)
        os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, os.path.basename(src))   # same name: the XPS / PMX textures are replaced, not added
        tinted_copy(src, dst, gain)
        files[key] = dst
    if "diffuse" in files:
        maps = json.loads(body_mat["roe_hq_xps"])
        maps["diffuse"] = files["diffuse"]
        body_mat["roe_hq_xps"] = json.dumps(maps)
    if "pmx" in files:
        body_mat["roe_hq_pmx"] = files["pmx"]
    body_mat["roe_tone_gain"] = out["gain"]
    out.update(tinted=True, material=body_mat.name, files=files)
    return out


def own_materials(kept, outfit):
    """Full variant: a kept slot sharing a material with the outfit gets a copy (the PMX hide morph hides by
    material; a08's braid ring uses the outfit atlas)."""
    used = {s.material for o in outfit for s in o.material_slots if s.material}
    copies, done = {}, []
    for obj in kept:
        for slot in obj.material_slots:
            if slot.material in used:
                tag = "hair" if "hair" in obj.name.lower() else re.sub(r"\W+", "", base(obj.name).split("_")[-1])
                key = (slot.material.name, tag)
                if key not in copies:
                    copies[key] = slot.material.copy()
                    copies[key].name = "%s_%s" % (base(slot.material.name), tag)
                slot.material = copies[key]
                done.append("%s -> %s" % (obj.name, copies[key].name))
    return done


def head_surface(head):
    """BVH (world space) of the head's skin: its slots but the eyes, lashes and brows, which float off it."""
    skin = {i for i, s in enumerate(head.material_slots) if not (s.material and base(s.material.name) in HEAD_EXTRAS)}
    return bvh(world_co(head), triangles(head, skin))


def islands(faces, key, verts=lambda f: [v.index for v in f.verts]):
    """{face: island id} over faces joined by a vertex (vertices with the same key are one); verts(face) gives a
    face's vertex indices (default: a bmesh face)."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for f in faces:
        vs = [int(key[v]) for v in verts(f)]
        first = find(vs[0])
        for v in vs[1:]:
            other = find(v)
            if other != first:
                parent[other] = first
    return {f: find(int(key[verts(f)[0]])) for f in faces}


def under_head(tree, p, n):
    """The head's skin lies within RAY_COVER of point p along its normal n (either way), facing the same way."""
    for s in (1.0, -1.0):
        loc, normal, _i, _d = tree.ray_cast(Vector(p), Vector(n * s), RAY_COVER)
        if loc is not None and abs(Vector(n).dot(normal)) > RAY_FACING:
            return True
    return False


def body_and_neck(body, body_slot, face_slot, head, report=None):
    """Keep the nude mesh's body slot and the part of its face slot the model's head does not cover (g04's head
    stops at the jaw; its neck was a separate face-material piece on the body mesh that overlapped the nude body
    in a 2.5 cm band at the collarbones - the nude base's own neck meets its body exactly).  That part gets the
    head's face material.  Covered = every vertex within COVER of the head (g04: the same face, 0.6 mm), or one
    vertex with the head's skin over / under it along its normal within RAY_COVER: c02's face is 1-5 mm off the
    c01 nude face, and the 1 mm test alone laid the whole nude face over hers (blank eyes); her head is face + crown,
    the neck and the back of the head were a face-material piece on her body mesh.  A face partly under the head
    goes too, so what is kept stops short of the head's edge and stitch() closes the gap.  Returns the number of
    neck faces kept."""
    bm = bmesh.new()
    bm.from_mesh(body.data)
    covered = []
    if face_slot is not None and head is not None:
        hco = world_co(head)
        kd = kdtree.KDTree(len(hco))
        for j, p in enumerate(hco):
            kd.insert(Vector(p), j)
        kd.balance()
        P, N = world_co(body), world_normals(body)
        tree = head_surface(head)
        verts = {v.index for f in bm.faces if f.material_index == face_slot for v in f.verts}
        on = {i: kd.find(Vector(P[i]))[2] <= COVER for i in verts}
        under = {i: not on[i] and under_head(tree, P[i], N[i]) for i in verts}
        covered = [f for f in bm.faces if f.material_index == face_slot
                   and (all(on[v.index] for v in f.verts) or any(under[v.index] for v in f.verts))]
        # what is left of the face slot away from the body is the nude face showing through the head's holes
        # (c02: eyelids in her eye openings, nostrils, mouth corners) or round ears unlike hers: dropped
        key = np.arange(len(P))
        for group in coincident(P):                 # the mesh is split along its UV seams
            key[group] = group[0]
        gone = set(covered)
        kept = [f for f in bm.faces if f.material_index in (body_slot, face_slot) and f not in gone]
        root = islands(kept, key)
        with_body = {root[f] for f in kept if f.material_index == body_slot}
        loose = [f for f in kept if f.material_index == face_slot and root[f] not in with_body]
        covered += loose
        if report is not None:
            report["neck_under_head"] = sum(1 for f in covered if any(under[v.index] for v in f.verts))
            report["neck_loose_dropped"] = len(loose)
    drop = covered + [f for f in bm.faces if f.material_index not in (body_slot, face_slot)]
    if face_slot is not None and head is None:
        drop += [f for f in bm.faces if f.material_index == face_slot]
    bmesh.ops.delete(bm, geom=drop, context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    neck = sum(1 for p in body.data.polygons if p.material_index == face_slot) if face_slot is not None else 0
    if neck:
        body.material_slots[face_slot].material = head.material_slots[0].material
    keep = {body_slot} | ({face_slot} if neck else set())
    for index in sorted(set(range(len(body.data.materials))) - keep, reverse=True):
        body.data.materials.pop(index=index)
    return neck


def drop_weak_references():
    """Appended data keeps the path of the file it came from (ID.library_weak_reference, Blender 3.2+, read-only)
    and bpy.utils.blend_paths lists it, so the archive's self-check took the nude base .blend for an outside
    file.  A copy carries no such reference: swap every such ID for its copy (packed images stay packed)."""
    swapped = []
    for kind in ("images", "materials", "node_groups", "textures", "meshes", "armatures", "objects"):
        data = getattr(bpy.data, kind)
        for old in [i for i in data if getattr(i, "library_weak_reference", None) is not None]:
            name = old.name
            new = old.copy()
            old.user_remap(new)
            data.remove(old)
            new.name = name
            swapped.append(name)
    return swapped


def main():
    a = args_after_dashes()
    report = {"model": bpy.data.filepath, "nude": a.nude, "variant": a.variant}
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    counts = {}
    for o in bpy.context.scene.objects:
        if o.type == "MESH" and armature_of(o):
            counts[armature_of(o)] = counts.get(armature_of(o), 0) + 1
    model_arm = max(counts, key=counts.get)
    stem = re.sub(r"\.blend$", "", os.path.basename(bpy.data.filepath))
    nude_body, nude_arm, nude_slot = append_nude(os.path.abspath(a.nude))
    report["aligned_mm"] = align_nude(model_arm, nude_arm, nude_body)
    report["reposed"] = repose_nude(model_arm, nude_arm, nude_body)
    face_slot = next((i for i, s in enumerate(nude_body.material_slots)
                      if s.material and re.search(r"_nk_face", s.material.name)), None)

    c = classify(model_arm, bvh(world_co(nude_body), triangles(nude_body, {nude_slot})))
    head, hair, weapons, kinds = c["head"], c["hair"], c["weapons"], c["slots"]
    report["painted"] = painted_skin(kinds, nude_body, nude_slot, a.variant)
    skin = {o: [i for i, k in s.items() if k == "skin"] for o, s in kinds.items() if "skin" in s.values()}
    report.update(armature=model_arm.name, head=head.name if head else None, hair=[o.name for o in hair],
                  weapons=[o.name for o in weapons], slots={o.name: s for o, s in kinds.items()},
                  slot_skin_share=c["shares"])
    if not skin:
        # f06 / g08: one material for skin and outfit, no slot mostly on the nude surface - the whole slot is outfit
        # (the full variant keeps its own skin with the outfit, over the fitted body; the nude variant drops it)
        report["skin_note"] = "no slot is mostly skin: skin and outfit share a material, the slot goes with the outfit"
    report["source_materials"] = source_materials(hair)       # heads: their per-face source index is unreliable

    body = nude_body.copy()
    body.data = nude_body.data.copy()
    bpy.context.scene.collection.objects.link(body)
    report["neck_from_nude"] = body_and_neck(body, nude_slot, face_slot, head, report)
    if report["neck_from_nude"]:                 # it replaces the model's own face-material pieces (g04's neck)
        for obj, s in kinds.items():
            for i, k in s.items():
                if k == "keep":
                    s[i] = "skin"
                    skin.setdefault(obj, [])
    if "roe_nude_slots" in body:
        del body["roe_nude_slots"]          # that marker means "face slots on the body mesh": not any more
    if body.material_slots and body.material_slots[0].material:
        src = re.sub(r"^HQ_|\.\d{3}$", "", body.material_slots[0].material.name)
        body["roe_source_materials"] = src
        body["roe_source_texture_hints"] = json.dumps([src + "_rgbx_Normal.png"])
        if "roe_source_material_index" in body.data.attributes:
            body.data.attributes.remove(body.data.attributes["roe_source_material_index"])

    weighted = {body.vertex_groups[g.group].name for v in body.data.vertices for g in v.groups if g.weight > 0}
    lines = []
    mapping, order = map_bones(model_arm, nude_arm, sorted(weighted), lines.append)
    add_bones(model_arm, nude_arm, order, mapping)
    rename_groups(body, mapping)
    report["aliases"] = lines
    report["added_bones"] = order
    columns = [b.name for b in model_arm.data.bones]
    seam_parts = []
    if head is not None:
        seam_parts.append((head, list(range(len(head.data.vertices)))))
    for obj, s in kinds.items():
        keep = {i for i, k in s.items() if k == "keep"}
        if keep:
            seam_parts.append((obj, sorted({v for p in obj.data.polygons if p.material_index in keep
                                            for v in p.vertices})))
    seam = seam_match(body, seam_parts)
    seam += stitch(body, head, seam, report)
    weights, old, snap = body_weights(body, columns, skin, seam, report)
    report["groups"] = write_groups(body, columns, weights)
    for m in [m for m in body.modifiers if m.type == "ARMATURE"]:
        m.object = model_arm
    world = body.matrix_world.copy()
    body.parent = model_arm
    body.matrix_world = world

    outfit_objs, kept_objs = [], [o for o in [head] + hair + weapons if o is not None]
    for obj, s in kinds.items():
        gone = [i for i, k in s.items() if k == "skin" or (a.variant == "nude" and k == "outfit")]
        outfit = [i for i, k in s.items() if k == "outfit"]
        keep = [i for i, k in s.items() if k in ("keep", "part")]
        if a.variant == "full" and outfit and keep:          # g04's body mesh: neck piece + dress; e05: tail + dress
            delete_faces(obj, set(gone))
            remap = {i: n for n, i in enumerate(sorted(set(s) - set(gone)))}
            outfit_objs.append(split_off(obj, [remap[i] for i in outfit], "_outfit"))
            kept_objs.append(obj)
            continue
        if gone:
            delete_faces(obj, set(gone))
        if not len(obj.data.polygons):
            bpy.data.objects.remove(obj, do_unlink=True)
        elif outfit and a.variant == "full":
            outfit_objs.append(obj)
        else:
            kept_objs.append(obj)
    if a.variant == "full":
        for obj in outfit_objs:
            obj["roe_outfit"] = 1
            obj["roe_xps_optional"] = "+outfit"
        report["own_materials"] = own_materials(kept_objs, outfit_objs)
        fixed = old.copy()
        seam_verts = [i for i, _o, _j in seam]
        fixed[seam_verts] = True                              # the seam with the head stays where it is
        snap[seam_verts] = 0.0
        axis = skeleton_points(world_co(body), weights, columns, model_arm)
        fit_under_outfit(body, outfit_objs, fixed, snap, axis, report)
    report["seam"] = close_seam(body, seam)
    for obj in weapons:
        if not obj.get("roe_xps_optional"):
            obj["roe_xps_optional"] = "+weapon"

    report["tone"] = tone_match(head, body, nude_body.material_slots[nude_slot].material, seam, nude_body, nude_slot,
                                face_slot, stem)
    for obj in (nude_body, nude_arm):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            (bpy.data.meshes if isinstance(data, bpy.types.Mesh) else bpy.data.armatures).remove(data)
    target = a.name or (stem + "_body")
    clash = bpy.data.objects.get(target)
    if clash is not None and clash is not body:               # g04: its own body mesh, now the dress
        clash.name = target + ("_outfit" if clash.get("roe_outfit") else "_part")
    body.name = body.data.name = target
    report["outfit"] = [o.name for o in outfit_objs]
    body["roe_completed_from"] = os.path.basename(a.nude)
    body["roe_completed_variant"] = a.variant
    bpy.context.view_layer.update()

    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    packed, missing = 0, []      # pack what the file uses (HQ blends also hold orphan, pruned FBX-import images)
    for image in bpy.data.images:
        if not image.users or image.packed_file or image.source != "FILE":
            continue
        if os.path.isfile(bpy.path.abspath(image.filepath)):
            image.pack()
            packed += 1
        else:
            missing.append(image.name)
    report["pack"] = {"packed": packed, "missing": missing}
    report["weak_references_dropped"] = len(drop_weak_references())
    bpy.ops.wm.save_as_mainfile(filepath=out, copy=False)
    report["out"] = out
    report["body"] = {"name": body.name, "verts": len(body.data.vertices), "faces": len(body.data.polygons)}
    if a.report:
        with open(a.report, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=1, default=str)
    print("ROE_COMPLETE_NUDE=" + json.dumps({k: report.get(k) for k in ("variant", "body", "weights", "seam",
                                                                         "neck_from_nude", "fit", "outfit",
                                                                         "weapons", "aliases", "pack", "tone")},
                                            ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
