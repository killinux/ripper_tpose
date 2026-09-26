# -*- coding: utf-8 -*-
"""Blender half of ff7_face_data.py: game facial poses (umodel .psa) sampled on the character's
skeleton (umodel .psk / .pskx), per face bone, as armature-space deltas relative to C_FaceBase_a.

  blender -b --python ff7_face_poses_blender.py -- <skeleton.psk(x)> <psa_dir> <out.json>

The psk_psa add-on's PSA importer relies on the rest data its own PSK importer stores on the bones,
so the poses are sampled on a fresh PSK import - not on the model's armature (a glTF-imported mod
body orients its bones differently).  Each delta D maps a vertex at rest to its posed position:
D = FaceBase_rest * FaceBase_pose^-1 * Bone_pose * Bone_rest^-1, i.e. body and head motion of the
clip are taken out.  Clips longer than two frames (limit-break takes) are skipped: they are not poses.
Prints FF7_FACE_POSES={json summary}.
"""
import glob
import json
import os
import sys

import addon_utils
import bpy

FACE_ROOT = "C_FaceBase_a"


def main():
    psk_path, psa_dir, out_path = sys.argv[sys.argv.index("--") + 1:][:3]
    if addon_utils.enable("io_scene_psk_psa", default_set=False) is None:
        raise SystemExit("io_scene_psk_psa is not installed for this Blender")
    from io_scene_psk_psa.psa.importer import PsaImportOptions, import_psa
    from io_scene_psk_psa.psa.reader import PsaReader

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.psk(filepath=psk_path, should_import_mesh=False, should_import_skeleton=True,
                             bone_length=2.0)
    arm = next(o for o in bpy.data.objects if o not in before and o.type == "ARMATURE")
    bones = arm.data.bones
    face = []
    stack = [bones[FACE_ROOT]]
    while stack:
        b = stack.pop()
        face.append(b.name)
        stack.extend(b.children)

    clips = []
    for psa in sorted(glob.glob(os.path.join(psa_dir, "*.psa"))):
        reader = PsaReader(psa)
        options = PsaImportOptions()
        options.sequence_names = list(reader.sequences.keys())
        options.should_overwrite = True
        options.should_write_metadata = False
        options.bone_mapping_mode = "CASE_INSENSITIVE"
        import_psa(bpy.context, reader, arm, options)
        clips += [(n, reader.sequences[n].frame_count) for n in options.sequence_names]

    def flat(m):
        return [round(m[i][j], 7) for i in range(4) for j in range(4)]

    out = {"psk": psk_path, "rest": {n: list(arm.matrix_world @ bones[n].head_local) for n in face},
           "poses": {}, "skipped": []}
    arm.animation_data_create()
    for name, frames in clips:
        if frames > 2:
            out["skipped"].append(name)
            continue
        arm.animation_data.action = bpy.data.actions[name]
        bpy.context.scene.frame_set(0)
        pb = arm.pose.bones
        to_rest = bones[FACE_ROOT].matrix_local @ pb[FACE_ROOT].matrix.inverted()
        out["poses"][name] = {n: flat(to_rest @ pb[n].matrix @ bones[n].matrix_local.inverted())
                              for n in face if n != FACE_ROOT}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    print("FF7_FACE_POSES=" + json.dumps({"poses": len(out["poses"]), "skipped": out["skipped"],
                                          "face_bones": len(face)}), flush=True)


main()
