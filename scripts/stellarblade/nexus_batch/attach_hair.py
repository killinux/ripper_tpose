"""Put a mod's hairstyle on a package .blend in place of Eve's own hair (2026-11-22: Demon Maiden's horned
EVE_HR_Nikke_03 replacer, Laniakea's CNS hair).  Edits the .blend in place.

    blender -b <package.blend> --factory-startup --python attach_hair.py -- --psk <hair .psk(x)> [--root Root]
            [--anchor Hair_Root] [--remove Eve_Hair_Mesh_01,Eve_HairTail_Mesh_01,Eve_HairTailShort_Mesh_01]
            [--name Eve_Hair_Mesh_01]

The game attaches a hairstyle's skeletal mesh COMPONENT to the body socket SC_Hair - its root bone's own rest rotation
plays no part.  validate_eve.py built the archived packages by putting the default hair PSK's Root rest matrix onto
that socket (merged as ``Hair_Root``), which is right only for a root oriented like that one: Demon Maiden's
EVE_HR_Nikke_03 put that way came out turned 180 degrees about its up axis (front bones behind the head, left ones
right).  The socket frame is Hair_Root's bone matrix with the PSK importer's bone-axis convention taken off -
SOCKET_FROM_HAIR_ROOT, a cyclic axis permutation (11-22: exactly what that 180-degree fix gives).  So:
  * the old hair objects are removed, then the bones only they used (their whole subtrees);
  * the hair PSK is imported (armature object at the identity = its component frame) and its object put on the
    socket frame, Hair_Root x SOCKET_FROM_HAIR_ROOT; transforms applied;
  * a hair bone whose name the package armature already has (``Root``; Laniakea's ``root`` = the face's) gets the
    prefix ``Hair2_``, one whose name does not say hair the prefix ``Hair_`` (vertex groups too): the PMX export's
    mmd_cloth_physics gives physics to a bone under the head only when it is named like hair;
  * the hair armature is joined into the package armature, its root parented where Hair_Root was (the head);
  * the mesh is bound to the package armature and named --name (the PMX / XPS steps and the add-on know it).
The materials keep the hair's instance names, empty - run_look.py's hair step fills them (fill_materials.py).
An accessory on the same socket (--keep-hair --rigid Bip001-Head: Evil maid's horns, which replace the Christmas
DLC's one-bone sleigh earcuff ACC_EAR_Christmas_02) is added the same way, nothing removed, every vertex on that bone.
SC_Hair sits on Bip001-Head with no offset (CH_P_EVE_01_Skeleton's socket list); the frame used is stored on the
armature ("sc_hair_frame") for an accessory put on after a hairstyle has replaced Hair_Root.
Prints SB_HAIR={json}."""
import argparse
import json
import re
import sys

import addon_utils
import bpy
from mathutils import Matrix

# the SC_Hair socket frame in Hair_Root's bone frame (see the docstring)
SOCKET_FROM_HAIR_ROOT = Matrix(((0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
# mmd_cloth_physics' HAIR_NAME (presets.NAME_HINTS[0]): under the head only bones named like this get physics
HAIR_WORD = re.compile(r"hair|ponytail|twintail|braid|bang|fringe", re.IGNORECASE)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--psk", required=True)
ap.add_argument("--root", default="")
ap.add_argument("--anchor", default="Hair_Root")
ap.add_argument("--remove", default="Eve_Hair_Mesh_01,Eve_HairTail_Mesh_01,Eve_HairTailShort_Mesh_01")
ap.add_argument("--name", default="Eve_Hair_Mesh_01")
ap.add_argument("--prefix", default="Hair2_")
ap.add_argument("--keep-hair", action="store_true",
                help="an accessory on the same socket (Evil maid's horns in place of the Christmas earcuff): add, remove nothing")
ap.add_argument("--rigid", default="",
                help="bind every vertex to this bone instead of merging the mesh's skeleton (a one-bone accessory)")
args = ap.parse_args(argv)
if args.keep_hair:
    args.remove = ""

scene = bpy.context.scene
arm = bpy.data.objects.get("Eve_Armature") or next(o for o in scene.objects if o.type == "ARMATURE")
anchor = arm.data.bones.get(args.anchor)
if anchor is not None:
    A = arm.matrix_world @ anchor.matrix_local
    F = A @ SOCKET_FROM_HAIR_ROOT
    anchor_parent = anchor.parent.name if anchor.parent else None
elif "sc_hair_frame" in arm:
    # a hairstyle was put on before (its Hair_Root is gone): the socket frame it stored
    v = list(arm["sc_hair_frame"])
    F = Matrix([v[i * 4:i * 4 + 4] for i in range(4)])
    anchor_parent = arm.get("sc_hair_bone", "Bip001-Head")
else:
    raise SystemExit("no %s bone and no stored socket frame" % args.anchor)
report = {"psk": args.psk, "anchor": args.anchor, "anchor_parent": anchor_parent}


def select_only(*objs, active=None):
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
    for o in scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]


# ------------------------------------------------------------------ the old hair and the bones only it used
old = [bpy.data.objects[n] for n in args.remove.split(",") if n and n in bpy.data.objects]
old_groups = {g.name for o in old for g in o.vertex_groups}
coll = (old[0] if old else bpy.data.objects.get("Eve_Body_Mesh_01") or arm).users_collection[0]
report["removed_objects"] = [o.name for o in old]
for o in old:
    bpy.data.objects.remove(o, do_unlink=True)
kept_groups = {g.name for o in scene.objects if o.type == "MESH" for g in o.vertex_groups}
doomed = {n for n in old_groups - kept_groups if n in arm.data.bones}
if old and args.anchor in arm.data.bones:
    doomed.add(args.anchor)
for n in list(doomed):                                  # whole subtrees (chain ends carry no group)
    for c in arm.data.bones[n].children_recursive:
        if c.name not in kept_groups:
            doomed.add(c.name)
# removed BEFORE the join: a new bone of the same name would otherwise come in as "<name>.001", off its group
select_only(arm)
bpy.ops.object.mode_set(mode="EDIT")
for n in sorted(doomed):
    if n in arm.data.edit_bones:
        arm.data.edit_bones.remove(arm.data.edit_bones[n])
bpy.ops.object.mode_set(mode="OBJECT")
report["removed_bones"] = len(doomed)

# ------------------------------------------------------------------ the new hair
addon_utils.enable("io_scene_psk_psa", default_set=True)
before = set(bpy.data.objects)
bpy.ops.import_scene.psk(filepath=args.psk)
new = [o for o in bpy.data.objects if o not in before]
ha = next(o for o in new if o.type == "ARMATURE")
hm = next(o for o in new if o.type == "MESH")
root_name = args.root or next(b.name for b in ha.data.bones if b.parent is None)
report["import_object_matrix_identity"] = ha.matrix_world == Matrix.Identity(4)
ha.matrix_world = F @ ha.matrix_world
bpy.context.view_layer.update()
mw = hm.matrix_world.copy()
hm.parent = None
hm.matrix_world = mw
for md in list(hm.modifiers):
    if md.type == "ARMATURE":
        hm.modifiers.remove(md)
select_only(hm)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
select_only(ha)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

if args.rigid:
    # a one-bone accessory: no skeleton to merge, every vertex on the bone the socket sits on
    bpy.data.objects.remove(ha, do_unlink=True)
    hm.vertex_groups.clear()
    g = hm.vertex_groups.new(name=args.rigid)
    g.add(list(range(len(hm.data.vertices))), 1.0, "REPLACE")
    report.update(root=root_name, rigid=args.rigid, hair_bones=0)
else:
    renamed = {}
    for b in ha.data.bones:
        if b.name in arm.data.bones:
            renamed[b.name] = args.prefix + b.name
        elif not HAIR_WORD.search(b.name):
            # mmd_cloth_physics (the PMX export's physics) takes a bone under the head for cloth only when its name
            # says hair - Laniakea's joint2..30 and Nikke_03's Ab-Front-* came out without any physics
            renamed[b.name] = "Hair_" + b.name
    for old_name, new_name in renamed.items():
        ha.data.bones[old_name].name = new_name
        g = hm.vertex_groups.get(old_name)
        if g is not None:
            g.name = new_name
    new_root = renamed.get(root_name, root_name)
    hair_bones = [b.name for b in ha.data.bones]
    report.update(root=root_name, new_root=new_root, renamed=renamed, hair_bones=len(hair_bones))

    # -------------------------------------------------------------- into the package armature
    select_only(arm, ha, active=arm)
    bpy.ops.object.join()
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    if anchor_parent and anchor_parent in eb:
        eb[new_root].parent = eb[anchor_parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    root_head = (arm.matrix_world @ arm.data.bones[new_root].head_local)
    report["root_offset_cm"] = round((root_head - F.translation).length, 4)
arm["sc_hair_frame"] = [F[i][j] for i in range(4) for j in range(4)]   # for an accessory put on after this
arm["sc_hair_bone"] = anchor_parent or "Bip001-Head"

for c in list(hm.users_collection):
    c.objects.unlink(hm)
coll.objects.link(hm)
hm.parent = arm
hm.matrix_parent_inverse = arm.matrix_world.inverted()
md = hm.modifiers.new("Armature", "ARMATURE")
md.object = arm
hm.name = args.name
hm.data.name = args.name
missing = sorted(g.name for g in hm.vertex_groups if g.name not in arm.data.bones)
report.update(name=hm.name, vertices=len(hm.data.vertices), materials=[m.name if m else None for m in hm.data.materials],
              groups_without_bone=missing, bones=len(arm.data.bones))
bpy.ops.wm.save_mainfile()
print("SB_HAIR=" + json.dumps(report, ensure_ascii=False))
