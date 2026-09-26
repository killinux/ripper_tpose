# -*- coding: utf-8 -*-
"""Script entry points (the panel's buttons call these too).

    import sys; sys.path.insert(0, "E:/code/othercode/ripper_tpose/scripts/blender_addons")
    from ff7_face_morphs import api
    made = api.build(armature_or_mesh, "E:/game_export/FF7Remake/_meta/face/PC0002_Tifa.json")
    api.stash(armature)          # before a Convert_to_MMD5 conversion
    api.restore(armature)        # after it: keys back + filed under the mmd_tools model's panels
"""
import os

import bpy

from . import core


def analyze(obj, data_path=None):
    """What the model has and what the face data can build on it."""
    arm, meshes = core.model_parts(obj)
    bones = core.face_bones(arm)
    info = {"armature": arm.name, "face_bones": len(bones),
            "meshes": [m.name for m in core.skinned(meshes, bones)],
            "built": core.built_names(meshes), "stashed": core.stashed(meshes), "data": ""}
    if data_path:
        data = core.load_face_data(data_path)
        recipes = core.recipes_for(data)
        info.update(data=os.path.basename(data_path), poses=len(data["poses"]),
                    visemes=len(data["lipmap"]["shapes"]), possible=len(recipes),
                    by_panel={c: sum(1 for r in recipes if r[2] == c) for c in core.CATEGORIES})
    return info


def build(obj, data_path, categories=core.CATEGORIES, strengths=None, log=None):
    """Shape keys for every expression; returns [(name, name_e, panel, moved_vertices)]."""
    arm, meshes = core.model_parts(obj)
    data = core.load_face_data(data_path)
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    return core.build_shape_keys(arm, meshes, data, categories=categories, strengths=strengths, log=log)


def clear(obj):
    _arm, meshes = core.model_parts(obj)
    return core.clear(meshes)


def stash(obj):
    _arm, meshes = core.model_parts(obj)
    return core.stash(meshes)


def restore(obj):
    """Stashed keys back; when the model is an mmd_tools model by now, register them for the PMX."""
    arm, meshes = core.model_parts(obj)
    restored = core.restore(meshes)
    root = core.mmd_root_of(arm)
    registered = core.register_morphs(root, meshes) if root is not None else []
    return {"restored": restored, "registered": registered}
