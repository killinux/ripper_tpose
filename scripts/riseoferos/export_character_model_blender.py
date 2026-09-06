"""Materialize a clothed Rise of Eros character and render a preview.

Blender-side worker for ``export_character_models.ps1``.  It drives the same
importer and material operators as the interactive ROE add-on, then writes a
packed .blend plus a single side-by-side preview PNG (3/4, front, head), and
optionally a GLB, a materialised XPS (.mesh with PNG sidecars) and/or an
MMD-ready PMX (Convert_to_MMD5 skeleton conversion + mmd_tools export, textures
copied beside the file).

Unlike ``export_nude_model_blender.py`` this worker makes no assumption that the
body is a single combined nude mesh: it neither splits the body into six slots
nor fails on a missing nude atlas, so it accepts any dressed HD/LD model.

Usage:
  blender --background --python export_character_model_blender.py -- \
      <fbx>[;<fallback fbx>...] <texture_dir> <out.blend> <roe_xps_addon.py> \
      <validate|export> [blend,glb,xps,pmx] [preview:0|1]

Candidates are tried in order and the first one that actually imports geometry
wins: several characters ship a ``*_nk_bs.fbx`` that holds only a rig, and an
event NPC may ship nothing but that.  When no candidate yields a mesh the worker
reports status NOMESH, which is a property of the bundles rather than a failure.
"""

import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
import traceback

import bpy
import numpy as np
from mathutils import Quaternion, Vector

RESULT_PREFIX = "ROE_CHAR_EXPORT="

# Views composited into the single preview image, left to right.
PREVIEW_VIEWS = ("hero", "front", "head")


def result(status, **details):
    # ASCII-only so PowerShell 5.1 cannot corrupt the marker by decoding
    # Blender's UTF-8 stdout with an OEM code page.
    print(RESULT_PREFIX + json.dumps({"status": status, **details},
                                     ensure_ascii=True, sort_keys=True))


def load_addon(path):
    spec = importlib.util.spec_from_file_location("roe_char_addon", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load ROE add-on: %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register()
    return module


def family_mismatches(images, expected_family):
    """Flag a shared head/hair texture borrowed from another body family."""
    mismatches = []
    common_role = re.compile(
        r"^pc_([a-z])_(?:nk|ld)_(?:face|eye|eyes|eye_iris|eyebrow|hair)",
        re.IGNORECASE)
    for image in images:
        filename = os.path.basename(bpy.path.abspath(
            image.filepath or image.name))
        match = common_role.match(filename)
        if match and match.group(1).lower() != expected_family:
            mismatches.append(filename)
    return sorted(set(mismatches))


ALBEDO_NAME = re.compile(r"_(?:albedo|abedo)", re.IGNORECASE)


def _normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _texture_key(stem):
    return _normalize(re.split(r"_rgbx", stem, flags=re.IGNORECASE)[0])


def build_albedo_index(texture_dir):
    """Map a normalized asset name to its best Albedo PNG (HD beats LD)."""
    index = {}
    for root, _dirs, files in os.walk(texture_dir):
        for name in files:
            if not name.lower().endswith(".png") or not ALBEDO_NAME.search(name):
                continue
            stem = os.path.splitext(name)[0]
            rank = 2 if re.search(r"_ld$", stem, re.IGNORECASE) else (
                0 if re.search(r"_hd$", stem, re.IGNORECASE) else 1)
            key = _texture_key(stem)
            current = index.get(key)
            if current is None or rank < current[0]:
                index[key] = (rank, os.path.join(root, name))
    return {key: value[1] for key, value in index.items()}


def resolve_leftover_texture(index, object_name, character_id):
    """Second-chance lookup for a slot the add-on left without a Base Color.

    Only an unambiguous hit is accepted.  Meshes are numbered more finely than
    the atlases they use (``..._armor01`` against ``..._armor``, ``wp_x_09_hd``
    against ``wp_x_09``), and a weapon mesh is usually named after its hand
    socket rather than its atlas, so the character's own ``wp_<id>`` atlas is
    tried last.  Anything that could match two atlases is left grey on purpose:
    a wrong texture is worse than an obviously missing one.
    """
    norm = _normalize(object_name)
    probes = []
    for candidate in (norm, re.sub(r"(?:hd|ld)$", "", norm)):
        probes.extend([candidate, re.sub(r"\d+$", "", candidate)])
    if norm.startswith("wp") and character_id:
        probes.append("wp" + _normalize(character_id))
    for probe in probes:
        if probe and probe in index:
            return index[probe]
    return None


def _mesh_components(mesh):
    """Group polygons into connected components (same union-find as the add-on)."""
    parent = list(range(len(mesh.vertices)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for edge in mesh.edges:
        first, second = edge.vertices
        root_a, root_b = find(first), find(second)
        if root_a != root_b:
            parent[root_a] = root_b

    components = {}
    for polygon in mesh.polygons:
        components.setdefault(find(polygon.vertices[0]), []).append(polygon)
    return components


def attach_fused_head_eyeballs(module, meshes, texture_dir, family):
    """Give eyeballs a real eye material when head and body share one mesh.

    a00's head is fused into the body mesh and carries no ``Eyeball`` vertex
    group, so ``find_head`` returns None and the add-on skips eye/lash/brow
    classification entirely.  Its two 432-polygon eyeballs then sample the body
    atlas through a full 0-1 iris UV, which renders as torn white/brown smears.

    Only components with the unmistakable ROE eyeball signature are touched:
    250-800 polygons whose UV island covers essentially the whole 0-1 square.
    """
    if not family:
        return []
    iris = (module.find_tex(texture_dir, "pc_%s_nk_eye_iris*Albedo*.png" % family)
            or module.find_tex(texture_dir, "pc_%s_nk_eyes*Albedo*.png" % family)
            or module.find_tex(texture_dir, "pc_%s_ld_eyes*Albedo*.png" % family))
    if not iris:
        return []

    attached = []
    for obj in meshes:
        mesh = obj.data
        if not mesh.uv_layers.active:
            continue
        uv_data = mesh.uv_layers.active.data
        targets = []
        for polygons in _mesh_components(mesh).values():
            if not 250 <= len(polygons) <= 800:
                continue
            u_min = v_min = 9.0
            u_max = v_max = -9.0
            for polygon in polygons:
                for loop in polygon.loop_indices:
                    u, v = uv_data[loop].uv
                    u_min, u_max = min(u_min, u), max(u_max, u)
                    v_min, v_max = min(v_min, v), max(v_max, v)
            if (u_min >= -0.01 and u_max <= 1.01 and v_min >= -0.01 and v_max <= 1.01
                    and u_max - u_min > 0.85 and v_max - v_min > 0.85):
                targets.extend(polygons)
        if not targets:
            continue
        mesh.materials.append(module.eye_mat("%s_eye" % obj.name, iris))
        eye_index = len(mesh.materials) - 1
        for polygon in targets:
            polygon.material_index = eye_index
        mesh.update()
        attached.append("%s[%d] <- %s (%d faces)"
                        % (obj.name, eye_index, os.path.basename(iris), len(targets)))
    return attached


def materials_images(meshes):
    """Every image reachable from the materials actually assigned to the model.

    The FBX importer creates an image datablock per texture named in the file,
    resolved beside the FBX.  Those datablocks stay in the scene even though the
    add-on rebuilds materials from the ``_textures`` copies, so packing all of
    ``bpy.data.images`` would embed unused duplicates — and hard-fail once the
    redundant per-object copies are pruned from disk.
    """
    images = set()
    for obj in meshes:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.use_nodes:
                continue
            for node in material.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image is not None:
                    images.add(node.image)
    return images


def pack_images(meshes):
    packed, failed = [], []
    for image in materials_images(meshes):
        if image.source != "FILE":
            continue
        try:
            image.pack()
            packed.append(image.name)
        except (OSError, RuntimeError) as exc:
            failed.append("%s: %s" % (image.name, exc))
    return packed, failed


def select_character_objects(meshes, armatures):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in list(meshes) + list(armatures):
        try:
            obj.hide_set(False)
            obj.hide_viewport = False
            obj.hide_render = False
            obj.select_set(True)
        except (ReferenceError, RuntimeError):
            pass
    if armatures:
        bpy.context.view_layer.objects.active = armatures[0]
    elif meshes:
        bpy.context.view_layer.objects.active = meshes[0]


def export_xps(module, path, meshes, armatures):
    """Write a materialised XPS model through the add-on's export operator.

    The operator bakes the eye texture, splits the head by material slot, sets
    the XPS render groups and copies every diffuse PNG beside the ``.mesh``
    (XPS resolves textures by file name in the same directory).  Each model gets
    its own directory so an outfit's sidecars never overwrite the base body's.
    """
    def operator_ready():
        try:
            bpy.ops.xps_tools.export_model.get_rna_type()
            return True
        except Exception:
            return False

    # An installed exporter may register the operator under any module name;
    # only walk the known add-on names when it is not available yet.
    if not operator_ready():
        for addon_name in ("XNALaraMesh-master", "XNALaraMesh", "b2xps_addon"):
            try:
                bpy.ops.preferences.addon_enable(module=addon_name)
            except Exception:
                continue
            if operator_ready():
                break
    if not operator_ready():
        raise RuntimeError("no XNALaraMesh/b2xps exporter add-on available")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        os.remove(path)
    select_character_objects(meshes, armatures)
    bpy.context.scene.roe.xps_out = path
    exported = bpy.ops.roe.export_xps()
    if exported != {"FINISHED"}:
        raise RuntimeError("XPS export failed: %r" % (exported,))
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("XPS not written: %s" % path)
    return path


def bake_portable_eye(module, head, out_dir):
    """Replace the procedural eye material with a baked PNG for PMX/GLB.

    The head's eye slot (index 1 on a dressed character) is a node graph
    (sclera + iris disc) that only Blender can evaluate.  Returns a status dict
    for the manifest; a model without a classified head keeps whatever the eye
    material resolves to, which is auditable rather than silently wrong.
    """
    if head is None or len(head.material_slots) < 2:
        return {"status": "skipped", "reason": "no classified head/eye slot"}
    eye_slot = 1
    eye_material = head.material_slots[eye_slot].material
    iris_image = module.diffuse_image(eye_material) if eye_material else None
    iris_path = (bpy.path.abspath(iris_image.filepath)
                 if iris_image is not None else "")
    if not iris_path or not os.path.isfile(iris_path):
        return {"status": "skipped", "reason": "eye slot has no iris image"}
    os.makedirs(out_dir, exist_ok=True)
    baked_path = os.path.join(
        out_dir, re.sub(r"[^A-Za-z0-9_.-]+", "_", head.name) + "_eye_baked.png")
    module.bake_eye_texture(head, iris_path, baked_path, eye_slot=eye_slot)
    head.data.materials[eye_slot] = module.albedo_mat(
        "eye_portable", baked_path, desat=False)
    head.data.update()
    return {"status": "baked", "path": baked_path}


# ---------------------------------------------------------------------------
# PMX through Convert_to_MMD5 (the user's XPS->MMD skeleton engine, a Blender
# add-on that sits on top of mmd_tools).  A plain mmd_tools export keeps the
# game's Biped bone names and has no IK / semi-standard bones, so MMD motion
# data cannot drive it; the add-on renames, completes, adds IK / D-bones /
# twist / shoulder-P, grants, bone groups and optional physics.
# ---------------------------------------------------------------------------

# MMD rest pose: upper arm this far below horizontal (measured from a reference
# PMX, see the add-on's presets/canonical_arm_dirs.json: atan2(0.605, 0.796)).
MMD_ARM_DOWN_DEG = 37.0

def _first_bone(bones, *names):
    """First of `names` present in `bones`, matched case-insensitively.

    ROE rigs disagree on capitalisation between characters (``Eyeball_L`` and
    ``eyeball_L``, ``Breast_L`` and ``chest_L``), so an exact lookup silently
    drops the eye and chest bones on most of the roster.
    """
    folded = {bone.name.lower(): bone.name for bone in bones}
    for name in names:
        if not name:
            continue
        hit = folded.get(name.lower())
        if hit:
            return hit
    return ""


def resolve_roe_slots(arm):
    """Map Convert_to_MMD5's bone slots onto this character's Biped rig.

    Every ROE character is a 3ds Max Biped, so a name table beats the add-on's
    topology auto-identify (tuned for XPS rigs), but the rigs are not uniform:
    the male base is ``Bip000``, some outfits drop the spaces (``LUpArm``,
    ``LThigh``, ``LCalf``), and one names the calf after its twist helper
    (thigh -> ``LCalfTwist`` -> foot).  So the prefix is detected, each joint
    tries its spellings, and a joint still missing is taken from the parent of
    the next joint down the chain.  The pelvis becomes 下半身 so its hip weights
    survive; センター is left empty and rebuilt by the add-on.

    Returns (slots, missing) where ``missing`` lists the optional roles that
    could not be resolved (eyes, chest, toes, finger segments).
    """
    bones = arm.data.bones
    prefix = ""
    for bone in bones:
        match = re.match(r"^(Bip\d+) Pelvis$", bone.name)
        if match:
            prefix = match.group(1)
            break
    if not prefix:
        raise RuntimeError("no Biped pelvis bone (Bip### Pelvis) in the rig")
    p = prefix

    def parent_of(name, grandparent=""):
        bone = bones.get(name)
        if bone is None or bone.parent is None:
            return ""
        if grandparent and (bone.parent.parent is None
                            or bone.parent.parent.name != grandparent):
            return ""
        return bone.parent.name

    slots = {
        "all_parents_bone": _first_bone(bones, p),
        "center_bone": "",
        "lower_body_bone": p + " Pelvis",
        "upper_body_bone": _first_bone(bones, p + " Spine"),
        "upper_body2_bone": _first_bone(bones, p + " Spine1"),
        "upper_body3_bone": _first_bone(bones, p + " Spine2"),
        "neck_bone": _first_bone(bones, p + " Neck"),
        "head_bone": _first_bone(bones, p + " Head"),
    }
    for side, s in (("left", "L"), ("right", "R")):
        slots["%s_eye_bone" % side] = _first_bone(
            bones, "%s eyeball_%s" % (p, s), "%s eye_%s" % (p, s),
            "%s %s Eye" % (p, s), "%s %sEye" % (p, s))
        slots["%s_chest_bone" % side] = _first_bone(
            bones, "%s chest_%s" % (p, s), "%s breast_%s" % (p, s),
            "%s %s Breast" % (p, s))
        clavicle = _first_bone(bones, "%s %s Clavicle" % (p, s), "%s %sClavicle" % (p, s))
        upper = _first_bone(bones, "%s %s UpperArm" % (p, s), "%s %sUpArm" % (p, s),
                            "%s %sUpperArm" % (p, s), "%s %s UpArm" % (p, s))
        fore = _first_bone(bones, "%s %s Forearm" % (p, s), "%s %sForearm" % (p, s),
                           "%s %s ForeArm" % (p, s))
        hand = _first_bone(bones, "%s %s Hand" % (p, s), "%s %sHand" % (p, s))
        thigh = _first_bone(bones, "%s %s Thigh" % (p, s), "%s %sThigh" % (p, s))
        calf = _first_bone(bones, "%s %s Calf" % (p, s), "%s %sCalf" % (p, s))
        foot = _first_bone(bones, "%s %s Foot" % (p, s), "%s %sFoot" % (p, s))
        toe = _first_bone(bones, "%s %s Toe0" % (p, s), "%s %sToe0" % (p, s))
        # Structural fallbacks, innermost joint first so each one can feed the next.
        fore = fore or parent_of(hand)
        upper = upper or parent_of(fore)
        clavicle = clavicle or parent_of(upper)
        calf = calf or parent_of(foot, grandparent=thigh)
        thigh = thigh or parent_of(calf)
        slots.update({
            "%s_shoulder_bone" % side: clavicle,
            "%s_upper_arm_bone" % side: upper,
            "%s_lower_arm_bone" % side: fore,
            "%s_hand_bone" % side: hand,
            "%s_thigh_bone" % side: thigh,
            "%s_calf_bone" % side: calf,
            "%s_foot_bone" % side: foot,
            "%s_toe_bone" % side: toe,
        })
        for digit, finger in (("0", "thumb"), ("1", "index"), ("2", "middle"),
                              ("3", "ring"), ("4", "pinky")):
            # Biped: Finger0 / Finger01 / Finger02; MMD thumb 0/1/2, others 1/2/3.
            segments = ("0", "1", "2") if digit == "0" else ("1", "2", "3")
            for index, segment in enumerate(segments):
                suffix = "Finger%s%s" % (digit, "" if index == 0 else index)
                slots["%s_%s_%s" % (side, finger, segment)] = _first_bone(
                    bones, "%s %s %s" % (p, s, suffix), "%s %s%s" % (p, s, suffix))
    missing = sorted(k for k, v in slots.items() if not v and k != "center_bone")
    return slots, missing


# Slots the add-on cannot do without (its complete/IK steps abort otherwise).
ROE_MMD_REQUIRED_SLOTS = (
    "upper_body_bone", "neck_bone", "head_bone",
    "left_shoulder_bone", "right_shoulder_bone", "left_upper_arm_bone",
    "right_upper_arm_bone", "left_lower_arm_bone", "right_lower_arm_bone",
    "left_hand_bone", "right_hand_bone", "left_thigh_bone", "right_thigh_bone",
    "left_calf_bone", "right_calf_bone", "left_foot_bone", "right_foot_bone",
)


def enable_addon(name):
    try:
        bpy.ops.preferences.addon_enable(module=name)
    except Exception as exc:
        raise RuntimeError("%s add-on is not available: %s" % (name, exc))


def bake_rig_transforms(arm, meshes):
    """Make armature space Z-up by baking the FBX importer's parent transform.

    The importer leaves the armature Y-up under an empty rotated 90 degrees
    about X.  Convert_to_MMD5 reads ``head_local`` (armature space) and assumes
    Z-up like an XPS import; on the raw rig its geometry heuristics read the
    legs as arms.  Clearing the parent with the transform kept and applying
    rotation/scale fixes that without moving anything in world space.
    """
    bpy.ops.object.mode_set(mode="OBJECT")
    objects = [arm] + list(meshes)
    bpy.ops.object.select_all(action="DESELECT")
    reparent = [obj for obj in objects
                if obj.parent is not None and obj.parent.type != "ARMATURE"]
    if reparent:
        for obj in reparent:
            obj.hide_set(False)
            obj.select_set(True)
        bpy.context.view_layer.objects.active = reparent[0]
        bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    for obj in list(bpy.data.objects):
        if obj.type == "EMPTY" and not obj.children:
            bpy.data.objects.remove(obj, do_unlink=True)
    heads = [bone.head_local for bone in arm.data.bones]
    span_z = max(h.z for h in heads) - min(h.z for h in heads)
    span_y = max(h.y for h in heads) - min(h.y for h in heads)
    if span_z < span_y:
        raise RuntimeError("armature is still not Z-up after applying transforms")


def edge_lengths(meshes):
    """Local-space edge lengths per mesh, for the geometry-integrity check."""
    snapshot = {}
    for mesh in meshes:
        data = mesh.data
        verts = data.vertices
        snapshot[mesh.name] = [
            (verts[e.vertices[0]].co - verts[e.vertices[1]].co).length
            for e in data.edges]
    return snapshot


def mesh_distortion(before, meshes, ratio_limit=3.0, growth_fraction=0.008):
    """Compare edge lengths against `before` and report torn geometry.

    Everything the conversion does to the rest pose is a rigid rotation of a
    bone sub-tree, so an edge only changes length when its two vertices are
    driven by bones that moved differently.  Some of that is honest skinning —
    the armpit fold opens when the arm comes down — so an edge counts as torn
    only when it both multiplies (>3x) and grows by a visible fraction of the
    model (>0.8% of the bounding-box diagonal).  Measured on the ROE male base:
    the wrist rip scored 7.0x / +33 mm, the armpit fold 2.4x / +8 mm.
    Ratios are normalised by their median so a uniform rescale reads as 1.0.
    """
    low = [1e9] * 3
    high = [-1e9] * 3
    for mesh in meshes:
        for corner in mesh.bound_box:
            for axis in range(3):
                low[axis] = min(low[axis], corner[axis])
                high[axis] = max(high[axis], corner[axis])
    size = max(math.dist(low, high), 1e-6)
    growth_limit = size * growth_fraction

    worst_ratio = 1.0
    worst_growth = 0.0
    worst_mesh = ""
    torn = 0
    stretched = 0
    compared = 0
    for mesh in meshes:
        old = before.get(mesh.name)
        if not old:
            continue
        new = edge_lengths([mesh])[mesh.name]
        if len(new) != len(old):
            continue
        pairs = [(n, o) for n, o in zip(new, old) if o > 1e-9]
        if not pairs:
            continue
        median = sorted(n / o for n, o in pairs)[len(pairs) // 2] or 1.0
        for new_len, old_len in pairs:
            scaled = old_len * median
            ratio = new_len / scaled
            growth = new_len - scaled
            compared += 1
            if abs(ratio - 1.0) > 0.25:
                stretched += 1
            if ratio > ratio_limit and growth > growth_limit:
                torn += 1
            if ratio > worst_ratio:
                worst_ratio = ratio
                worst_growth = growth
                worst_mesh = mesh.name
    return {"edges": compared, "stretched": stretched, "torn": torn,
            "worst_ratio": round(worst_ratio, 2),
            "worst_growth_mm": round(worst_growth * 1000, 1),
            "growth_limit_mm": round(growth_limit * 1000, 1),
            "worst_mesh": worst_mesh}


# 3ds Max Biped names its limb helpers by convention, and ROE follows it:
# ``ForeTwist`` / ``UpArmTwist`` / ``ThighTwist`` / ``CalfTwist`` for the twist
# correctives, ``Point_elbow`` / ``AC elbow`` / ``knee_`` / ``Point_ankle`` for
# the joint pads.  Matching the convention (then checking the geometry) is what
# keeps garment bones — buttocks, skirts, pauldrons — out of the limb chains.
LIMB_HELPER_NAME = re.compile(r"twist|elbow|knee|ankle|muscle\s*strand", re.IGNORECASE)


# How far past a joint the skin blend from one bone to the next reaches, in
# units of the distal bone's length.  Measured on the ROE rigs: ``knee_L``'s
# skin runs from t=-0.21 to t=+0.26 around the knee, ``LCalfTwist``'s from
# -0.07 to 0.62.  0.35 puts a pad straddling the joint at half the bend and a
# twist bone a quarter of the way down the shin at about three quarters.
GRANT_BLEND = 0.35


def weight_samples(meshes, names):
    """Every skinned vertex each named group drives: {name: [(world pos, weight)]}."""
    samples = {name: [] for name in names}
    for mesh in meshes:
        index_to_name = {}
        for name in names:
            group = mesh.vertex_groups.get(name)
            if group is not None:
                index_to_name[group.index] = name
        if not index_to_name:
            continue
        matrix = mesh.matrix_world
        for vertex in mesh.data.vertices:
            position = None
            for entry in vertex.groups:
                name = index_to_name.get(entry.group)
                if name is None or entry.weight <= 0.05:
                    continue
                if position is None:
                    position = matrix @ vertex.co
                samples[name].append((position, entry.weight))
    return samples


def snapshot_skin(arm, meshes):
    """Per-vertex bone weights, plus which bones exist and which drive skin.

    Taken once the arms are already in the A-pose, so anything that changes
    after this point changed because of the conversion; see
    :func:`restore_stray_weight_transfers`.
    """
    bones = {bone.name for bone in arm.data.bones}
    weights = {}
    driven = set()
    for mesh in meshes:
        names = {group.index: group.name for group in mesh.vertex_groups
                 if group.name in bones}
        rows = {}
        for vertex in mesh.data.vertices:
            entry = []
            for item in vertex.groups:
                name = names.get(item.group)
                if name is None or item.weight <= 0.0:
                    continue
                entry.append((name, item.weight))
                driven.add(name)
            if entry:
                rows[vertex.index] = entry
        weights[mesh.name] = rows
    return {"weights": weights, "bones": bones, "driven": driven}


def restore_stray_weight_transfers(arm, meshes, before):
    """Undo weight the conversion handed to a bone that never drove any skin.

    Convert_to_MMD5 redistributes a bone's weights when it retires one, and it
    picks the recipient geometrically.  On a10 that put eleven backpack vertices
    — weighted to ``backpack_D`` and ``backpack_all`` — onto ``Point_elbow_R``,
    an elbow pad carrying no skin at all, so a flap of the pack stretched into a
    spike reaching for the elbow whenever the arm moved.  The tear gate caught
    it as 4 edges at 10.8x.

    The test is narrow on purpose.  Bones the conversion *creates* are expected
    to take weight — that is what the ``足D`` chain, ``上半身2`` and ``足先EX``
    are for — and so is a bone that already drove skin.  Only a bone that came
    with the source rig, drove nothing there, and drives something now has been
    handed skin it was never meant to have; those vertices get their original
    weights back.  A vertex whose own bones the conversion retired is left
    where it was put — the transfer was the only option there, and that is how
    e07's holster ends up riding ``AC_holster_L`` after ``holster_L`` is gone,
    while the 381 body vertices swept onto the same bone go home.  Across the
    120 characters this fires on 7, and every recipient is an accessory or
    constraint bone.

    Only the weights are put back.  The stray weight was already live while the
    add-on baked its own re-poses, so those vertices also sit a couple of
    centimetres from where they belong in the rest mesh — that residue is what
    the gate still reports, and it is a small bump rather than the spike the
    animation used to draw.  Re-deriving their rest position from the bones'
    before/after matrices was tried and made it worse (30 torn edges instead of
    4), so the geometry is left alone.
    """
    live = {bone.name for bone in arm.data.bones}
    idle = (before["bones"] - before["driven"]) & live
    if not idle:
        return []

    restored = []
    for mesh in meshes:
        rows = before["weights"].get(mesh.name)
        if not rows:
            continue
        names = {group.index: group.name for group in mesh.vertex_groups}
        strays = {}
        for vertex in mesh.data.vertices:
            for item in vertex.groups:
                name = names.get(item.group)
                if name in idle and item.weight > 0.0:
                    strays.setdefault(name, []).append(vertex.index)
                    break
        for bone_name, indices in sorted(strays.items()):
            put_back = 0
            for index in indices:
                original = rows.get(index)
                if not original or any(name not in live for name, _w in original):
                    continue
                for group in mesh.vertex_groups:
                    if group.name in live:
                        group.remove([index])
                for name, weight in original:
                    group = mesh.vertex_groups.get(name) or mesh.vertex_groups.new(name=name)
                    group.add([index], weight, "REPLACE")
                put_back += 1
            if put_back:
                restored.append("%s: %d vertices off %s" % (mesh.name, put_back, bone_name))
        mesh.data.update()
    return restored


def skin_rotation_share(points, start, segment):
    """How much of the distal bone's rotation this helper's skin should take.

    A helper bone is a rigid island inside a smoothly weighted limb, so the
    question is not *which* bone it belongs to but *how much* of the joint it
    should follow.  Each of its vertices is projected onto the distal bone; a
    vertex sitting a full blend width past the joint follows that bone
    completely, one a blend width before it not at all, and the weighted mean
    over the island is the share the whole bone should take.  A pad straddling
    the joint lands near 0.5, a twist bone well down the limb near 1.0.
    """
    length_sq = segment.length_squared
    if length_sq <= 1e-12:
        return 1.0
    total = 0.0
    taken = 0.0
    for position, weight in points:
        t = (position - start).dot(segment) / length_sq
        taken += min(1.0, max(0.0, 0.5 + t / (2.0 * GRANT_BLEND))) * weight
        total += weight
    return taken / total if total > 0.0 else 1.0


def plan_joint_helper_moves(arm, meshes, slots):
    """Work out how much of its limb each helper bone should follow.

    Returns ``(plans, report)``.  ``plans`` is a list of
    ``(bone name, limb bone name, share)``: the helper is re-parented onto that
    limb bone and, once the conversion is done, given ``share`` of its rotation
    as an MMD rotation grant.  ``report`` holds one dict per candidate so a
    diagnostic tool can show the reasoning.

    ROE Biped rigs hang limb helpers off whatever was convenient — ``ForeTwist``
    under the UPPER ARM as a sibling of the forearm, ``ThighTwist`` under the
    SPINE as a sibling of the thigh — and correct them at runtime with
    constraints that no exporter can carry.  The helpers hold a lot of skin, so
    hanging them off the wrong bone leaves that skin behind: the wrist tore open
    during the rest-pose bake, the thigh stepped at the knee under animation.

    Simply re-parenting them onto the limb swaps one artefact for another.  A
    helper is a rigid island in an otherwise smoothly weighted limb, so if it
    takes *all* of the joint's rotation while the skin around it takes a blend,
    the island shears out of the surface — that is the lump that appeared on the
    knees.  ``knee_L`` is the clearest case: its 994 vertices straddle the knee
    from t=-0.21 to t=+0.26, so neither the thigh (0%) nor the shin (100%) is
    right and only half the bend looks like a knee.

    So each helper is measured, not classified.  Its NAME has to match Biped's
    limb-helper convention (which keeps ``butt_*``, ``skirt_*`` and
    ``Pauldrons_*`` — just as close to the thigh and shoulder heads — out of the
    limb chains), the SKIN it drives has to lie along one limb segment, and the
    share of that segment's rotation it takes comes from where the skin actually
    sits: see :func:`skin_rotation_share`.
    """
    mapped = {name for name in slots.values() if name}
    # A limb segment: (joint that must carry the skin, bone ending the segment).
    limbs = (("left_upper_arm_bone", "left_lower_arm_bone"),
             ("right_upper_arm_bone", "right_lower_arm_bone"),
             ("left_lower_arm_bone", "left_hand_bone"),
             ("right_lower_arm_bone", "right_hand_bone"),
             ("left_thigh_bone", "left_calf_bone"),
             ("right_thigh_bone", "right_calf_bone"),
             ("left_calf_bone", "left_foot_bone"),
             ("right_calf_bone", "right_foot_bone"))

    bones = arm.data.bones

    def descends_from(bone, ancestor_name):
        while bone is not None:
            if bone.name == ancestor_name:
                return True
            bone = bone.parent
        return False

    joints = []
    matrix = arm.matrix_world
    for role, end_role in limbs:
        joint = bones.get(slots.get(role) or "")
        end = bones.get(slots.get(end_role) or "")
        if joint is None or end is None:
            continue
        start = matrix @ joint.head_local
        segment = (matrix @ end.head_local) - start
        if segment.length_squared > 1e-9:
            joints.append((joint, start, segment))

    # Candidates: Biped's own limb helpers (their names are a convention, not a
    # per-model guess) plus anything sitting exactly on a joint.
    candidates = []
    for bone in bones:
        if bone.name in mapped:
            continue
        named = LIMB_HELPER_NAME.search(bone.name) is not None
        coincident = any((bone.head_local - joint.head_local).length < 1e-4
                         for joint, _s, _v in joints)
        if named or coincident:
            candidates.append(bone)
    samples = weight_samples(meshes, [b.name for b in candidates]) if candidates else {}

    plans = []
    report = []
    for bone in candidates:
        points = samples.get(bone.name) or []
        total = sum(weight for _p, weight in points)
        entry = {"bone": bone.name,
                 "parent": bone.parent.name if bone.parent else "",
                 "skin": bool(points),
                 "belongs_to": "", "t": None, "lateral_ratio": None, "share": None,
                 "verdict": "no skin"}
        report.append(entry)
        if total <= 0.0:              # drives no skin, so nothing can tear
            continue
        centroid = sum((p * w for p, w in points), Vector()) / total
        best = None
        for joint, start, segment in joints:
            length = segment.length
            t = (centroid - start).dot(segment) / (length * length)
            lateral = (centroid - (start + segment * max(0.0, min(1.0, t)))).length
            if lateral > 0.35 * length or not -0.25 <= t <= 1.25:
                continue
            # Prefer the limb the skin sits *within*: an elbow helper hangs off
            # the far end of the upper arm (t>1) but lives on the forearm (t~0.3),
            # and this keeps the other leg — the same distance away sideways —
            # from ever winning.  The last term breaks the tie for a pad sitting
            # right on a joint in favour of the distal bone, whose rotation the
            # grant can then hand back in the right proportion.
            score = (lateral + max(0.0, -t, t - 1.0) * length
                     + 0.15 * length * max(0.0, t - 0.5))
            if best is None or score < best[0]:
                best = (score, joint.name, t, lateral / length, start, segment)
        if best is None:
            entry["verdict"] = "skin not on any limb"
            continue
        limb, t, lateral_ratio, start, segment = best[1:]
        share = skin_rotation_share(points, start, segment)
        entry.update({"belongs_to": limb, "t": round(t, 3),
                      "lateral_ratio": round(lateral_ratio, 3),
                      "share": round(share, 2)})
        if share >= 0.97 and descends_from(bone, limb):
            # Already rides the limb it belongs to and should follow it fully.
            entry["verdict"] = "ok"
            continue
        entry["verdict"] = ("misparented" if not descends_from(bone, limb)
                            else "over-following")
        plans.append((bone.name, limb, share))
    return plans, report


def reparent_joint_helpers(arm, meshes, slots):
    """Apply :func:`plan_joint_helper_moves`.  Rest geometry is untouched
    (head/tail/roll are preserved), so re-parenting does not move the mesh.

    Every planned helper is hung directly off the limb bone, flattening the
    twist chains, so that all of them follow the conversion's own re-posing —
    the add-on straightens the forearm and this exporter drops the arms into the
    A-pose, and a helper left behind by either tears the skin in the rest pose,
    where it can never be corrected.  :func:`apply_helper_grants` hands the
    partial followers back afterwards.
    """
    plans, _report = plan_joint_helper_moves(arm, meshes, slots)
    return apply_joint_helper_moves(arm, plans)


def apply_joint_helper_moves(arm, plans):
    if not plans:
        return []
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = arm.data.edit_bones
    moved = []
    try:
        for plan in plans:
            child_name, joint_name = plan[0], plan[1]
            child = edit_bones.get(child_name)
            joint = edit_bones.get(joint_name)
            if child is None or joint is None or child is joint:
                continue
            head, tail, roll = child.head.copy(), child.tail.copy(), child.roll
            child.use_connect = False
            child.parent = joint
            child.head, child.tail, child.roll = head, tail, roll
            moved.append("%s -> %s" % (child_name, joint_name))
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    return moved


def apply_helper_grants(arm, plans):
    """Give each partially-following helper an MMD rotation grant.

    Run after the conversion, when the bones carry their MMD names and the rig
    has grown the bones the conversion adds.  A helper that should take only
    part of a joint's rotation is lifted one step up from wherever it now sits
    and given ``share`` of that bone's rotation as a 付与.  One step is the right
    step whichever bone the conversion moved it onto: a leg helper rides the
    deform twin (``ひざD``, whose parent is ``足D``) and an arm helper rides an
    inserted twist bone (``手捩``, whose parent is ``ひじ``), and in both cases
    the grandparent is the proximal bone of that joint.  Re-parenting is
    rest-neutral (head, tail and roll are kept), so nothing moves in the rest
    pose; only the animation changes, from "all of the joint" to "the part this
    island of skin actually sits in".

    The grant is taken from that bone's own source when it is itself a full-rate
    copy — the leg deform bones copy ``足``/``ひざ`` at 1.0 — so the chain stays
    one level deep and PMX never has to resolve a grant of a grant.
    """
    partial = [(name, share) for name, _limb, share in plans if share < 0.97]
    if not partial:
        return []

    sources = {}
    for name, share in partial:
        bone = arm.data.bones.get(name)
        if bone is None or bone.parent is None or bone.parent.parent is None:
            continue
        distal = bone.parent
        grandparent = distal.parent
        pose_bone = arm.pose.bones.get(distal.name)
        source = distal.name
        if pose_bone is not None:
            mmd_bone = pose_bone.mmd_bone
            if (mmd_bone.has_additional_rotation
                    and abs(mmd_bone.additional_transform_influence - 1.0) < 1e-3
                    and mmd_bone.additional_transform_bone in arm.data.bones):
                source = mmd_bone.additional_transform_bone
        sources[name] = (grandparent.name, source, share)

    if not sources:
        return []
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = arm.data.edit_bones
    try:
        for name, (parent_name, _source, _share) in sources.items():
            child = edit_bones.get(name)
            parent = edit_bones.get(parent_name)
            if child is None or parent is None:
                continue
            head, tail, roll = child.head.copy(), child.tail.copy(), child.roll
            child.use_connect = False
            child.parent = parent
            child.head, child.tail, child.roll = head, tail, roll
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")

    granted = []
    for name, (parent_name, source, share) in sources.items():
        pose_bone = arm.pose.bones.get(name)
        if pose_bone is None:
            continue
        mmd_bone = pose_bone.mmd_bone
        mmd_bone.has_additional_rotation = True
        mmd_bone.has_additional_location = False
        mmd_bone.additional_transform_bone = source
        mmd_bone.additional_transform_influence = share
        # MMD deforms by (transform layer, bone index) and a grant is only
        # honoured when its source came first.  These helpers are pure leaves —
        # nothing reads them back — so putting them one layer later makes the
        # order correct whatever index the exporter happens to give them.
        mmd_bone.transform_order = max(mmd_bone.transform_order, 1)
        granted.append("%s under %s, %.2f x %s" % (name, parent_name, share, source))
    try:
        bpy.ops.mmd_tools.apply_additional_transform()
    except Exception as exc:
        print("[roe pmx] apply_additional_transform after helper grants: %s" % exc)
    return granted


def arm_down_angle(arm, upper_name, lower_name):
    """Degrees the upper arm points below horizontal (world space)."""
    upper = arm.data.bones[upper_name]
    lower = arm.data.bones[lower_name]
    v = arm.matrix_world.to_3x3() @ (lower.head_local - upper.head_local)
    return math.degrees(math.atan2(-v.z, math.hypot(v.x, v.y)))


def relax_shoulder_weights(arm, slots):
    """Relax the shoulder/arm weight boundaries before the A-pose bake.

    Lowering the upper arm ~13-47 degrees shears the skin wherever the torso's
    weight meets the arm's abruptly — the armpit fold on a bare body, the seam
    between a stiff collar and the sleeve on a costume.  Relaxing the groups
    involved spreads the transition so the bake deforms smoothly; the add-on
    does the same before its own arm bakes.
    """
    from Convert_to_MMD5.convert.align import _smooth_group_weights

    names = []
    for side in ("left", "right"):
        for role in ("shoulder_bone", "upper_arm_bone", "lower_arm_bone"):
            name = slots.get("%s_%s" % (side, role))
            if name:
                names.append(name)
    if not names:
        return 0
    try:
        # Gentler than the add-on's own default (0.5 / 8): enough to take the
        # edge off the bake without turning a crisp shoulder into mush.
        return _smooth_group_weights(bpy.context, arm, names, factor=0.35, repeat=4)
    except Exception as exc:
        print("[roe pmx] shoulder weight relax skipped: %s" % exc)
        return 0


def apose_arms(arm, meshes, slots, target_deg=MMD_ARM_DOWN_DEG):
    """Lower the upper arms from the T-pose to the MMD A-pose and bake it as rest.

    VMD rotations are relative to the model's rest pose, so a T-pose rig would
    hold every arm ~37 degrees too high under MMD motion.  Each upper arm is
    rotated about the world front/back axis by exactly the missing amount; the
    add-on's ``_bake_pose_delta_to_rest`` then bakes the pose into the meshes
    (via a duplicated armature modifier) and applies it as the new rest pose.
    Returns the resulting (left, right) down angles.
    """
    from Convert_to_MMD5.convert.align import _bake_pose_delta_to_rest

    chains = tuple((slots["%s_upper_arm_bone" % side], slots["%s_lower_arm_bone" % side],
                    slots["%s_hand_bone" % side], sign)
                   for side, sign in (("left", 1.0), ("right", -1.0)))
    for chain in chains:
        for name in chain[:3]:
            if not name or name not in arm.data.bones:
                raise RuntimeError("arm bone missing for the A-pose: %r" % (chain[:3],))
    # Point the arm bones at their child joints: the FBX importer picks an
    # arbitrary tail for a bone with several children (UpperArm has the twist
    # helper too), and the add-on measures arm direction from the tails.
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = arm.data.edit_bones
    for upper, lower, hand, _sign in chains:
        edit_bones[upper].tail = edit_bones[lower].head
        edit_bones[lower].tail = edit_bones[hand].head
    bpy.ops.object.mode_set(mode="OBJECT")

    plans = []
    axis = Vector((0.0, 1.0, 0.0))
    for upper, lower, _hand, sign in chains:
        current = arm_down_angle(arm, upper, lower)
        delta = target_deg - current
        if abs(delta) < 0.5:
            continue
        pivot = arm.matrix_world @ arm.data.bones[upper].head_local
        plans.append((upper, pivot, axis, math.radians(delta) * sign))
    if plans:
        bpy.context.view_layer.objects.active = arm
        if _bake_pose_delta_to_rest(bpy.context, arm, plans, "roe apose") != "FINISHED":
            raise RuntimeError("A-pose bake failed")
    return tuple(round(arm_down_angle(arm, chain[0], chain[1]), 1) for chain in chains)


def add_both_eyes_bone(arm):
    """Create MMD's 両目 control bone and drive 左目/右目 from it.

    MMD motions steer the gaze through 両目.  The add-on renames the game's
    eyeball bones to 左目/右目 but never creates their parent control, so the
    eye keys in a VMD (the test dance has them) drive nothing.  両目 carries no
    skin; the eyes inherit its rotation through the standard 付与 at rate 1.0.
    """
    bones = arm.data.bones
    if "両目" in bones or "左目" not in bones or "右目" not in bones:
        return False
    left = bones["左目"].head_local.copy()
    right = bones["右目"].head_local.copy()
    spacing = max((left - right).length, 1e-3)
    middle = (left + right) * 0.5

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = arm.data.edit_bones
    eyes = edit_bones.new("両目")
    # Above the eyes, pointing the way the character faces (-Y once the rig is
    # Z-up); placement is display-only since the bone does not deform.
    eyes.head = middle + Vector((0.0, 0.0, spacing * 1.4))
    eyes.tail = eyes.head + Vector((0.0, -spacing * 1.2, 0.0))
    eyes.use_deform = False
    eyes.parent = edit_bones.get("頭")
    bpy.ops.object.mode_set(mode="OBJECT")

    for name in ("左目", "右目"):
        pose_bone = arm.pose.bones.get(name)
        if pose_bone is None:
            continue
        mmd_bone = pose_bone.mmd_bone
        mmd_bone.has_additional_rotation = True
        mmd_bone.has_additional_location = False
        mmd_bone.additional_transform_bone = "両目"
        mmd_bone.additional_transform_influence = 1.0
        # MMD deforms bones by (transform layer, bone index), and a grant only
        # works if its source was deformed first.  両目 is appended at the end of
        # the armature, well after the eyes it drives, so without a later layer
        # the eyes read a stale 両目 and the gaze keys do nothing.  Blender hides
        # this: mmd_tools drives the same relation with constraints, which
        # resolve in dependency order whatever the bone indices say.
        mmd_bone.transform_order = max(mmd_bone.transform_order, 1)
    try:
        bpy.ops.mmd_tools.apply_additional_transform()
    except Exception as exc:
        print("[roe pmx] apply_additional_transform after 両目: %s" % exc)
    return True


# --- facial expressions -----------------------------------------------------
# ROE characters have no shape keys; the face is driven by bones (eyelids, chin,
# lip corners).  PMX can express exactly that as *bone morphs*, so the standard
# MMD expressions a dance drives — a blink alone is 77 keys in the test motion —
# are authored here as small bone poses.  Angles were calibrated by rendering
# the eye and mouth through a sweep: the lid closes at ~33 degrees, the jaw
# reads as "a" at 18 and as "i" at 6.
BLINK_UPPER_DEG = 33.0
BLINK_LOWER_RATIO = -0.45
JAW_DEG = {"あ": 18.0, "い": 6.0, "う": 7.0, "え": 12.0, "お": 13.0}
# Lip-corner slide along the model's left-right axis, as a fraction of the eye
# spacing: positive spreads the mouth wide, negative purses it.
LIP_CORNER = {"い": 0.22, "う": -0.18, "え": 0.10, "お": -0.12}


def resolve_face_bones(arm, prefix):
    """Find the eyelid / chin / lip-corner bones across the ROE naming styles.

    Two conventions ship in the same game: ``eyelid_UL`` / ``lip_L`` / ``chin``
    on one set of characters, ``Eyelid_LT`` / ``Lips_L`` / ``Chin`` on another.
    ``AC``-prefixed duplicates carry no skin weight and are ignored.
    """
    bones = [b for b in arm.data.bones if not b.name.startswith("AC ")]
    p = prefix
    face = {
        "upper_left": _first_bone(bones, "%s eyelid_UL" % p, "%s Eyelid_LT" % p,
                                  "%s eyelid_UP_L" % p),
        "upper_right": _first_bone(bones, "%s eyelid_UR" % p, "%s Eyelid_RT" % p,
                                   "%s eyelid_UP_R" % p),
        "lower_left": _first_bone(bones, "%s eyelid_BL" % p, "%s Eyelid_LB" % p,
                                  "%s eyelid_DN_L" % p),
        "lower_right": _first_bone(bones, "%s eyelid_BR" % p, "%s Eyelid_RB" % p,
                                   "%s eyelid_DN_R" % p),
        "chin": _first_bone(bones, "%s chin" % p, "%s jaw" % p),
        "corner_left": _first_bone(bones, "%s lip_L" % p, "%s Lips_L" % p),
        "corner_right": _first_bone(bones, "%s lip_R" % p, "%s Lips_R" % p),
    }
    return {role: name for role, name in face.items() if name}


def _local_rotation(arm, bone_name, world_axis, degrees):
    """Quaternion in the bone's local space for a rotation about a world axis."""
    pose_bone = arm.pose.bones[bone_name]
    rest = arm.matrix_world @ pose_bone.bone.matrix_local
    axis = rest.to_3x3().inverted() @ world_axis
    if axis.length < 1e-9:
        return Quaternion((1.0, 0.0, 0.0, 0.0))
    return Quaternion(axis.normalized(), math.radians(degrees))


def _local_translation(arm, bone_name, world_vector):
    pose_bone = arm.pose.bones[bone_name]
    rest = arm.matrix_world @ pose_bone.bone.matrix_local
    return rest.to_3x3().inverted() @ world_vector


def add_face_morphs(root, arm):
    """Author the standard MMD expression set as PMX bone morphs.

    Returns the list of morph names created.
    """
    match = re.match(r"^(Bip\d+)", next((b.name for b in arm.data.bones
                                         if b.name.startswith("Bip")), ""))
    if not match:
        return []
    face = resolve_face_bones(arm, match.group(1))
    lids = [role for role in ("upper_left", "upper_right", "lower_left", "lower_right")
            if role in face]
    if not lids and "chin" not in face:
        return []

    # model-scale reference for the lip slide
    spacing = 0.03
    left_eye = arm.data.bones.get("左目")
    right_eye = arm.data.bones.get("右目")
    if left_eye and right_eye:
        spacing = max((left_eye.head_local - right_eye.head_local).length, 1e-3)

    x_axis = Vector((1.0, 0.0, 0.0))
    plans = []

    def lid_pose(sides):
        pose = []
        for side in sides:
            upper = face.get("upper_%s" % side)
            lower = face.get("lower_%s" % side)
            if upper:
                pose.append((upper, None,
                             _local_rotation(arm, upper, x_axis, BLINK_UPPER_DEG)))
            if lower:
                pose.append((lower, None,
                             _local_rotation(arm, lower, x_axis,
                                             BLINK_UPPER_DEG * BLINK_LOWER_RATIO)))
        return pose

    if lids:
        plans.append(("まばたき", "blink", "EYE", lid_pose(("left", "right"))))
        plans.append(("笑い", "smile", "EYE", lid_pose(("left", "right"))))
        plans.append(("ウィンク", "wink", "EYE", lid_pose(("left",))))
        plans.append(("ウィンク右", "wink_right", "EYE", lid_pose(("right",))))

    chin = face.get("chin")
    if chin:
        for vowel, degrees in JAW_DEG.items():
            pose = [(chin, None, _local_rotation(arm, chin, x_axis, degrees))]
            slide = LIP_CORNER.get(vowel)
            if slide:
                for role, sign in (("corner_left", 1.0), ("corner_right", -1.0)):
                    corner = face.get(role)
                    if corner:
                        offset = Vector((sign * slide * spacing, 0.0, 0.0))
                        pose.append((corner, _local_translation(arm, corner, offset), None))
            plans.append((vowel, vowel, "MOUTH", pose))

    mmd_root = root.mmd_root
    existing = {morph.name for morph in mmd_root.bone_morphs}
    created = []
    for name, name_e, category, pose in plans:
        if name in existing or not pose:
            continue
        morph = mmd_root.bone_morphs.add()
        morph.name = name
        morph.name_e = name_e
        morph.category = category
        for bone_name, location, rotation in pose:
            item = morph.data.add()
            item.bone = bone_name
            if location is not None:
                item.location = location
            if rotation is not None:
                item.rotation = rotation
        created.append(name)

    if created:
        # List them in the 表情 display frame, otherwise MMD's expression panel
        # stays empty even though the morphs are in the file.
        try:
            from mmd_tools.operators.display_item import DisplayItemQuickSetup

            DisplayItemQuickSetup.load_facial_items(mmd_root)
        except Exception as exc:
            print("[roe pmx] facial display frame: %s" % exc)
    return created


def convert_rig_to_mmd(arm, meshes, slots, missing_optional, helper_plans=(),
                       skin_before=None):
    """Run Convert_to_MMD5's one-click pipeline with the resolved slots; add physics.

    Returns (mmd_root_object, stats dict for the manifest).
    """
    from Convert_to_MMD5.presets import get_bones_list

    scene = bpy.context.scene
    for prop in get_bones_list():
        setattr(scene, prop, "")
    for prop, bone_name in slots.items():
        if bone_name:
            setattr(scene, prop, bone_name)

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    converted = bpy.ops.object.one_click_convert(auto_identify=False)
    if converted != {"FINISHED"}:
        raise RuntimeError("Convert_to_MMD5 one-click conversion failed: %r" % (converted,))
    # The add-on may have replaced the active object; find the live armature.
    arm = next(obj for obj in bpy.data.objects
               if obj.type == "ARMATURE" and "backup" not in obj.name.lower())
    root = arm
    while root.parent is not None:
        root = root.parent
    if getattr(root, "mmd_type", "") != "ROOT":
        raise RuntimeError("no mmd root object after conversion")

    # Now that the rig has its MMD names and the legs their deform chain, hand
    # the partially-following helpers back to the joint they share.
    helper_grants = apply_helper_grants(arm, helper_plans)
    stray_weights = (restore_stray_weight_transfers(arm, meshes, skin_before)
                     if skin_before else [])
    for line in stray_weights:
        print("[roe pmx] stray weight transfer undone - %s" % line)

    both_eyes = add_both_eyes_bone(arm)
    if both_eyes:
        # so 両目 lands in the "体(上)" display frame the add-on defines
        bpy.ops.object.select_all(action="DESELECT")
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        try:
            bpy.ops.object.create_bone_group()
        except Exception as exc:
            print("[roe pmx] regroup after 両目: %s" % exc)

    try:
        morphs = add_face_morphs(root, arm)
    except Exception as exc:
        print("[roe pmx] face morphs failed: %s" % exc)
        morphs = []

    bone_names = set(arm.data.bones.keys())
    holes = 0
    for mesh in meshes:
        deform = {vg.index for vg in mesh.vertex_groups if vg.name in bone_names}
        holes += sum(1 for v in mesh.data.vertices
                     if sum(g.weight for g in v.groups if g.group in deform) < 0.05)
    stats = {
        "bones": len(arm.data.bones),
        "relay_bones": sum(1 for b in arm.data.bones
                           if b.name.startswith(("_dummy_", "_shadow_"))),
        "weight_holes": holes,
        "both_eyes_bone": both_eyes,
        "helper_grants": helper_grants,
        "stray_weights": stray_weights,
        "face_morphs": morphs,
        "unmapped_slots": missing_optional,
    }

    # Physics: kinematic body capsules first (cloth needs something to collide
    # with), then rigid bodies + joints on skirt / cloak / hair bones.  Optional:
    # a failure here is recorded, not fatal.
    physics = {}
    for label, op in (("body", bpy.ops.object.add_body_rigids),
                      ("cloth", bpy.ops.object.add_skirt_physics)):
        bpy.ops.object.select_all(action="DESELECT")
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        restore = None
        if label == "cloth":
            # Teach the add-on this model's own garment names for one call, so
            # its calibrated rigid-body and joint parameters do the building.
            from Convert_to_MMD5.convert import skirt

            chains = cloth_chain_bones(arm, meshes,
                                       slots.get("lower_body_bone", "").split(" ")[0])
            # Only the ones its own vocabulary does not already reach.
            missed = [name for name in chains
                      if not skirt.CLOTH_RE.search(name)
                      and not skirt.HAIR_RE.search(name)]
            physics["cloth_chains"] = missed
            if missed:
                restore = skirt.CLOTH_RE
                skirt.CLOTH_RE = re.compile(
                    "(?:%s)|(?:%s)" % (restore.pattern,
                                       "|".join(re.escape(n) for n in missed)),
                    re.IGNORECASE)
        try:
            physics[label] = "ok" if op() == {"FINISHED"} else "cancelled"
        except Exception as exc:
            physics[label] = "failed: %s" % exc
        finally:
            if restore is not None:
                skirt.CLOTH_RE = restore
    physics["rigid_bodies"] = sum(1 for obj in bpy.data.objects
                                  if getattr(obj, "mmd_type", "") == "RIGID_BODY")
    physics["joints"] = sum(1 for obj in bpy.data.objects
                            if getattr(obj, "mmd_type", "") == "JOINT")
    stats["physics"] = physics
    return root, stats


def cloth_chain_bones(arm, meshes, biped_prefix=""):
    """Garment chains the add-on's cloth word list does not know about.

    Convert_to_MMD5 finds cloth by name — ``skirt|coat|cloak|cape|mantle|shawl|
    veil|scarf|hangings|drape|apron|robe|frill|sash|ribbon`` — which is a good
    generic list but not ROE's vocabulary.  g12's skirt is called ``Dress_F_*``
    and gets nothing while its ``Cape*`` chains get 165 rigid bodies; d09's is
    ``F_dress_*``, b13's sleeves ``Sleeve_L1_*``, e10's ``Streamer_*`` and
    ``Bowknot_*``, a12's ``Rope_*``.

    Rather than guess more words, find the shape.  A garment bone here is one
    that drives real skin, carries no rigid body yet, and is none of: an MMD
    standard bone (they are named in Japanese), a Biped bone (the body skeleton
    keeps its ``Bip001`` prefix, which is what keeps chin and lip bones out), a
    limb helper, or anything under the head — the face lives there, and hair
    already has its own word list.

    Those bones are then grouped into connected parent/child components and
    only components of two or more survive: a hanging strip of cloth is always a
    chain, while ``butt_L``, ``shoulder_R`` and a one-bone ``Armor_L1_01`` plate
    are single bones that should stay rigid.

    Held props are excluded, and Biped says which they are: it parks anything in
    the character's hands under ``Bip001 Prop1``/``Prop2``.  Everything down
    there is a chain that drives skin and would otherwise qualify — e05's parasol
    is 60 bones of ``ribs`` and ``stretcher``, j10 carries 66 bones of ``wp_*``
    weapon, i01 a pair of ``Bone_Wep*`` — and none of it should go floppy.  What
    is left hangs off the body, which is what cloth does.

    Returns the bone names to hand to the add-on.
    """
    if not meshes:
        return []
    names = {bone.name for bone in arm.data.bones}
    total = {}
    for mesh in meshes:
        index_to_name = {group.index: group.name for group in mesh.vertex_groups
                         if group.name in names}
        for vertex in mesh.data.vertices:
            for item in vertex.groups:
                name = index_to_name.get(item.group)
                if name and item.weight > 0.02:
                    total[name] = total.get(name, 0.0) + item.weight

    with_rigid = {obj.mmd_rigid.bone for obj in bpy.data.objects
                  if getattr(obj, "mmd_type", "") == "RIGID_BODY"}
    japanese = re.compile(r"[぀-ヿ一-鿿]")
    biped = re.compile(r"^%s\b" % re.escape(biped_prefix)) if biped_prefix else None

    prop = re.compile(r"^%s\s*Prop\d*$" % re.escape(biped_prefix), re.IGNORECASE) \
        if biped_prefix else None

    def carried_or_facial(bone):
        while bone is not None:
            if bone.name in ("頭", "首") or (prop and prop.match(bone.name)):
                return True
            bone = bone.parent
        return False

    free = set()
    for bone in arm.data.bones:
        if (bone.name not in with_rigid
                and not japanese.search(bone.name)
                and not (biped and biped.match(bone.name))
                and not LIMB_HELPER_NAME.search(bone.name)
                and total.get(bone.name, 0.0) >= 2.0
                and not carried_or_facial(bone)):
            free.add(bone.name)

    # Connected components over the parent link; a strip of cloth is a chain.
    parent_of = {bone.name: (bone.parent.name if bone.parent else None)
                 for bone in arm.data.bones}
    component = {}
    for name in free:
        root = name
        while parent_of.get(root) in free:
            root = parent_of[root]
        component.setdefault(root, []).append(name)
    return sorted(name for members in component.values() if len(members) > 1
                  for name in members)


def hide_transparent_materials(meshes):
    """Carry Blender's invisible slots into PMX as alpha 0.

    The head is split into face / eye / lash / brow / eye_overlay slots, and the
    ones with nothing to draw are given a bare Transparent BSDF: ``eye_overlay``
    always, plus lash and brow on the families whose face atlas already has the
    strokes painted in (i, j).  PMX has no blend modes and mmd_tools writes a
    material's ``mmd_material`` block, which defaults to opaque 0.8 grey — so
    j10's 10 590 eyelash vertices came out as a pale patch across the eyes.
    Setting the MMD alpha to 0 is how a PMX says "do not draw this".
    """
    hidden = []
    seen = set()
    for mesh in meshes:
        for slot in mesh.material_slots:
            material = slot.material
            if material is None or material.name in seen:
                continue
            if not material.use_nodes or not material.node_tree:
                continue
            nodes = material.node_tree.nodes
            if (any(node.type == "BSDF_TRANSPARENT" for node in nodes)
                    and not any(node.type == "BSDF_PRINCIPLED" for node in nodes)):
                seen.add(material.name)
                material.mmd_material.alpha = 0.0
                material.mmd_material.enabled_drop_shadow = False
                material.mmd_material.enabled_self_shadow = False
                material.mmd_material.enabled_self_shadow_map = False
                material.mmd_material.enabled_toon_edge = False
                hidden.append(material.name)
    return hidden


def verify_grant_order(path):
    """Read the written PMX back and check every rotation grant resolves.

    MMD deforms bones in order of (transform layer, bone index) and a grant is
    only honoured when its source bone was deformed first.  Blender hides a
    violation completely — mmd_tools drives the same relation with constraints,
    which resolve in dependency order whatever the indices say — so this is
    checked against the file rather than the scene.  It is how the 両目 control
    was caught: appended at the end of the armature, it was deformed long after
    the eyes it drives, and the VMD's gaze keys would have done nothing in MMD.
    """
    from mmd_tools.core import pmx as pmx_core

    model = pmx_core.load(path)
    names = [bone.name for bone in model.bones]
    violations = []
    for index, bone in enumerate(model.bones):
        if not getattr(bone, "hasAdditionalRotate", False):
            continue
        transform = getattr(bone, "additionalTransform", None)
        if not transform or transform[0] is None or transform[0] < 0:
            continue
        source = transform[0]
        source_key = (getattr(model.bones[source], "transform_order", 0), source)
        if source_key >= (getattr(bone, "transform_order", 0), index):
            violations.append("%s <- %s" % (bone.name, names[source]))
    return violations


def export_pmx(path, meshes, armatures):
    """Write an MMD-ready PMX: Convert_to_MMD5 skeleton conversion + mmd_tools.

    Rewrites the rig and bakes a new rest pose into the meshes, so this must be
    the last export of the scene.  Textures are copied beside the .pmx.
    Returns (path, stats).
    """
    enable_addon("mmd_tools")
    enable_addon("Convert_to_MMD5")
    if not hasattr(bpy.ops.object, "one_click_convert"):
        raise RuntimeError("Convert_to_MMD5 did not register one_click_convert")
    if not armatures:
        raise RuntimeError("no armature to convert")
    arm = armatures[0]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        os.remove(path)

    slots, missing_optional = resolve_roe_slots(arm)
    missing_required = [role for role in ROE_MMD_REQUIRED_SLOTS if not slots[role]]
    if missing_required:
        raise RuntimeError("rig lacks joints the MMD conversion needs: %s"
                           % ", ".join(missing_required))
    before = edge_lengths(meshes)
    bake_rig_transforms(arm, meshes)
    helper_plans, _helper_report = plan_joint_helper_moves(arm, meshes, slots)
    helpers = apply_joint_helper_moves(arm, helper_plans)
    relaxed = relax_shoulder_weights(arm, slots)
    apose = apose_arms(arm, meshes, slots)
    skin_before = snapshot_skin(arm, meshes)
    root, stats = convert_rig_to_mmd(arm, meshes, slots, missing_optional,
                                     helper_plans, skin_before)
    stats["arm_down_deg"] = apose
    stats["reparented_helpers"] = helpers
    stats["relaxed_groups"] = relaxed
    stats["distortion"] = mesh_distortion(before, meshes)
    stats["biped_prefix"] = slots["lower_body_bone"].split(" ")[0]
    stats["hidden_materials"] = hide_transparent_materials(meshes)

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
    # mmd_tools multiplies by ``scale`` on export (PMX = Blender units * scale),
    # so 12.5 turns a 1.7 m character into the usual ~21 PMX units; 0.08 would
    # produce a 0.14-unit model.
    bpy.ops.mmd_tools.export_pmx(filepath=path, scale=12.5, copy_textures=True,
                                 log_level="ERROR")
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("PMX not written: %s" % path)
    try:
        stats["grant_order_violations"] = verify_grant_order(path)
    except Exception as exc:
        print("[roe pmx] grant order check skipped: %s" % exc)
        stats["grant_order_violations"] = []
    return path, stats


def setup_preview_world():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    # Filmic (Blender's default) desaturates the albedo atlases, which makes a
    # preview useless for judging whether the right texture was bound.
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("preview_world")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.34, 0.34, 0.37, 1.0)
    background.inputs[1].default_value = 1.35
    scene.world = world

    # Key light slightly camera-left, fill from the opposite side so the far
    # cheek and the back of a dark costume do not read as a silhouette.
    for name, energy, rotation in (
        ("key", 3.2, (0.95, 0.0, 0.65)),
        ("fill", 1.1, (1.15, 0.0, -2.2)),
    ):
        data = bpy.data.lights.new(name, type="SUN")
        data.energy = energy
        lamp = bpy.data.objects.new(name, data)
        scene.collection.objects.link(lamp)
        lamp.rotation_euler = rotation


def mesh_bounds(meshes):
    points = [obj.matrix_world @ Vector(corner)
              for obj in meshes for corner in obj.bound_box]
    low = Vector((min(p.x for p in points), min(p.y for p in points),
                  min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points),
                   max(p.z for p in points)))
    return low, high


def render_view(camera, camera_data, target, ortho, direction, size, path):
    camera_data.ortho_scale = max(ortho, 0.01)
    camera.location = target + direction * size
    camera.rotation_euler = (
        (target - camera.location).to_track_quat("-Z", "Y").to_euler())
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def image_array(path):
    image = bpy.data.images.load(path)
    try:
        width, height = image.size
        pixels = np.array(image.pixels[:], dtype=np.float32)
        return pixels.reshape(height, width, image.channels)
    finally:
        bpy.data.images.remove(image)


def compose_preview(tiles, out_path):
    """Concatenate rendered tiles horizontally into one PNG."""
    height = max(tile.shape[0] for tile in tiles)
    # Pad short tiles with the rendered backdrop rather than black, sampled from
    # a corner pixel so it tracks the world colour and the view transform.
    backdrop = tiles[0][0, 0].copy()
    padded = []
    for tile in tiles:
        if tile.shape[0] != height:
            pad = np.empty((height, tile.shape[1], tile.shape[2]),
                           dtype=np.float32)
            pad[:, :] = backdrop
            offset = (height - tile.shape[0]) // 2
            pad[offset:offset + tile.shape[0]] = tile
            tile = pad
        padded.append(tile)
    combined = np.concatenate(padded, axis=1)
    out_height, out_width, channels = combined.shape
    image = bpy.data.images.new("preview", width=out_width, height=out_height,
                                alpha=channels > 3)
    try:
        image.pixels = combined.ravel().tolist()
        image.filepath_raw = out_path
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)
    return out_path


def render_preview(meshes, out_path, scratch_prefix):
    setup_preview_world()
    scene = bpy.context.scene
    low, high = mesh_bounds(meshes)
    center = (low + high) * 0.5
    extent = high - low
    distance = max(extent.length, 0.1) * 2.0

    camera_data = bpy.data.cameras.new("preview_cam")
    camera_data.type = "ORTHO"
    camera = bpy.data.objects.new("preview_cam", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    head_target = Vector((center.x, center.y, high.z - extent.z * 0.10))
    plans = {
        # 3/4 hero angle first: it shows silhouette and side detail at once.
        "hero": (center, extent.z * 1.12, Vector((-0.75, -0.95, 0.12)).normalized(),
                 620, 940),
        "front": (center, extent.z * 1.12, Vector((0.0, -1.0, 0.0)), 620, 940),
        "head": (head_target, extent.z * 0.26, Vector((0.0, -1.0, 0.05)).normalized(),
                 620, 620),
    }
    tiles = []
    temporaries = []
    for name in PREVIEW_VIEWS:
        target, ortho, direction, width, height = plans[name]
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        tile_path = "%s_%s.png" % (scratch_prefix, name)
        render_view(camera, camera_data, target, ortho, direction, distance,
                    tile_path)
        temporaries.append(tile_path)
        tiles.append(image_array(tile_path))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    compose_preview(tiles, out_path)
    for path in temporaries:
        try:
            os.remove(path)
        except OSError:
            pass
    return out_path


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) not in {5, 6, 7}:
        raise RuntimeError(
            "usage: <fbx> <texture_dir> <out.blend> <roe_xps_addon.py> "
            "<validate|export> [blend,glb,xps,pmx] [preview:0|1]")

    candidates = [os.path.abspath(item) for item in argv[0].split(";")
                  if item.strip()]
    texture_dir, output_path, addon_path = (
        os.path.abspath(argv[index]) for index in range(1, 4))
    mode = argv[4]
    formats = ({item.strip().lower() for item in argv[5].split(",")
                if item.strip()} if len(argv) >= 6 else {"blend"})
    want_preview = argv[6] != "0" if len(argv) == 7 else True

    unknown = formats - {"blend", "glb", "xps", "pmx"}
    if unknown:
        raise RuntimeError("unknown format(s): %s" % ", ".join(sorted(unknown)))
    if mode not in {"validate", "export"}:
        raise RuntimeError("unknown mode: %s" % mode)
    if not candidates:
        raise RuntimeError("no FBX candidate given")
    for label, path, predicate in (
        ("FBX", candidates[0], os.path.isfile),
        ("texture dir", texture_dir, os.path.isdir),
        ("ROE add-on", addon_path, os.path.isfile),
    ):
        if not predicate(path):
            raise RuntimeError("%s not found: %s" % (label, path))

    stem = Path(output_path).stem
    family_match = re.match(r"pc_([a-z])", stem.lower())
    expected_family = family_match.group(1) if family_match else ""

    bpy.ops.wm.read_factory_settings(use_empty=True)
    module = load_addon(addon_path)

    fbx_path = ""
    meshes = []
    empty_candidates = []
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        bpy.ops.wm.read_factory_settings(use_empty=True)
        props = bpy.context.scene.roe
        props.workflow_mode = "ROE"
        props.apply_scope = "LATEST"
        props.replace_previous = False
        props.fbx_path = candidate
        props.tex_dir = texture_dir

        imported = bpy.ops.roe.import_fbx()
        if imported != {"FINISHED"}:
            raise RuntimeError("FBX import failed: %r" % (imported,))
        found = [obj for obj in module.scene_meshes() if obj.type == "MESH"]
        if not found:
            # Rig-only prefab: the material pass would abort on it, so move on
            # to the next candidate before touching materials.
            empty_candidates.append(os.path.basename(candidate))
            continue
        applied = bpy.ops.roe.apply_materials(repair_scope="ALL")
        if applied != {"FINISHED"}:
            raise RuntimeError("material pass failed: %r" % (applied,))
        fbx_path = candidate
        meshes = [obj for obj in module.scene_meshes() if obj.type == "MESH"]
        break

    if not meshes:
        result("NOMESH", source=candidates[0],
               candidates=[os.path.basename(item) for item in candidates],
               empty_candidates=empty_candidates,
               error="no candidate FBX contains geometry (rig-only prefabs)")
        return
    armatures = module.related_armatures(meshes)

    id_match = re.match(r"pc_([a-z]\d+)", stem.lower())
    character_id = id_match.group(1) if id_match else ""
    albedo_index = build_albedo_index(texture_dir)
    recovered = []
    for obj in meshes:
        for index, slot in enumerate(obj.material_slots):
            material = slot.material
            if material is not None:
                if module.diffuse_image(material) is not None:
                    continue
                if module.material_is_transparent_only(material):
                    continue
            path = resolve_leftover_texture(albedo_index, obj.name, character_id)
            if not path:
                continue
            slot.material = module.albedo_mat(
                "%s_%02d_recovered" % (obj.name, index), path)
            recovered.append("%s[%d] <- %s"
                             % (obj.name, index, os.path.basename(path)))

    # Must run before the texture audit so the iris it binds is counted.
    head = module.find_head(meshes)
    fused_eyes = ([] if head is not None else attach_fused_head_eyeballs(
        module, meshes, texture_dir, character_id[:1] if character_id else ""))

    images = []
    untextured = []
    for obj in meshes:
        for index, slot in enumerate(obj.material_slots):
            material = slot.material
            if material is None:
                untextured.append("%s[%d] <empty>" % (obj.name, index))
                continue
            image = module.diffuse_image(material)
            if image is None:
                # A deliberately transparent slot (eye overlay, hidden helper)
                # has no Base Color image and is not a defect.
                if not module.material_is_transparent_only(material):
                    untextured.append("%s[%d] %s"
                                      % (obj.name, index, material.name))
                continue
            images.append(image)

    # A head can come back fully textured yet have every face polygon routed
    # into lash/brow/overlay, which renders as a faceless head while every other
    # check reports success.  Count the polygons per head slot so an empty face
    # slot is a hard signal instead of something only a human notices.
    head_slots = {}
    head_face_polygons = -1
    if head is not None:
        counts = {}
        for polygon in head.data.polygons:
            counts[polygon.material_index] = counts.get(polygon.material_index, 0) + 1
        for index, slot in enumerate(head.material_slots):
            name = slot.material.name if slot.material else "slot%d" % index
            head_slots[name] = counts.get(index, 0)
        head_face_polygons = head_slots.get("face", -1)

    textures = sorted({
        os.path.basename(bpy.path.abspath(image.filepath or image.name))
        for image in images})
    mismatches = family_mismatches(images, expected_family) if expected_family else []

    outputs = {}
    preview_path = ""
    packed = []
    portable_eye = None
    mmd_convert = None
    if mode == "export":
        output_root = os.path.dirname(output_path)
        os.makedirs(output_root, exist_ok=True)
        if want_preview:
            preview_path = render_preview(
                meshes, os.path.join(output_root, stem + "_preview.png"),
                os.path.join(output_root, "." + stem))
        if "blend" in formats:
            packed, failures = pack_images(meshes)
            if failures:
                raise RuntimeError("image packing failed: %s"
                                   % "; ".join(failures))
            bpy.context.preferences.filepaths.save_version = 0
            bpy.ops.wm.save_as_mainfile(filepath=output_path,
                                        check_existing=False)
            if not os.path.isfile(output_path):
                raise RuntimeError("blend not written: %s" % output_path)
            outputs["blend"] = output_path
        if "xps" in formats:
            # After the .blend: the operator bakes an eye PNG and copies the
            # sidecars from the images' file paths, which packing keeps intact.
            outputs["xps"] = export_xps(
                module, os.path.join(output_root, "xps", stem, stem + ".mesh"),
                meshes, armatures)
        if "glb" in formats:
            glb_path = os.path.join(output_root, "glb", stem + ".glb")
            os.makedirs(os.path.dirname(glb_path), exist_ok=True)
            select_character_objects(meshes, armatures)
            bpy.ops.export_scene.gltf(filepath=glb_path, export_format="GLB",
                                      use_selection=True, export_apply=False)
            if not os.path.isfile(glb_path) or os.path.getsize(glb_path) == 0:
                raise RuntimeError("GLB not written: %s" % glb_path)
            outputs["glb"] = glb_path
        if "pmx" in formats:
            # Last: mmd_tools rewrites the rig in place, and the eye bake
            # replaces the procedural eye material the earlier formats used.
            pmx_dir = os.path.join(output_root, "pmx", stem)
            # mmd_tools copies textures into <pmx dir>/textures; bake there
            # so the eye PNG is not duplicated at the root.
            portable_eye = bake_portable_eye(
                module, head, os.path.join(pmx_dir, "textures"))
            outputs["pmx"], mmd_convert = export_pmx(
                os.path.join(pmx_dir, stem + ".pmx"), meshes, armatures)

    result(
        "PASS",
        source=fbx_path,
        output=outputs.get("blend") or next(iter(outputs.values()), ""),
        outputs=outputs,
        preview=preview_path,
        formats=sorted(formats) if mode == "export" else [],
        meshes=len(meshes),
        armatures=len(armatures),
        materials=sum(len(obj.material_slots) for obj in meshes),
        textures=textures,
        packed_images=len(packed),
        untextured_slots=untextured,
        recovered_slots=recovered,
        family_mismatches=mismatches,
        head_slots=head_slots,
        head_face_polygons=head_face_polygons,
        fused_head_eyes=fused_eyes,
        portable_eye=portable_eye,
        mmd_convert=mmd_convert,
        diagnostic=bpy.context.scene.roe.diagnostic_report,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # Blender often exits 0 after a Python error.
        result("FAIL", error=str(exc), traceback=traceback.format_exc())
