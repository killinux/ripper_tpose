# -*- coding: utf-8 -*-
"""Assemble a Rise of Eros 'suit' into one materialized, rigged .blend.

A suit (outfit variant) is the character's nude base body + hair plus a set of
clothing component meshes that all skin to the same skeleton; the game overlays
them at runtime, so there is no single dressed FBX.  This worker imports the
base body (six-slot nude materialize) and each component FBX, textures every
piece from the suit's ``Lynn_<piece>_rgbx_Albedo`` maps, re-binds the pieces to
the base skeleton and writes a packed .blend + a 3-view preview (+ optional glb).

Two non-obvious facts about the component FBX (extracted per-object from
``chara_components_pc_<id>.ab`` by AssetStudio splitObjects):

* They carry NO materials, so each slot is textured from the suit texture
  bundle by piece name (see ``resolve_albedo``).
* A SKINNED component stores its vertices in correct model space but with a
  spurious object ``matrix_world`` (baked from being parented to a limb bone's
  armature object), so it renders ~1.5 m off its bones.  Discarding the object
  transform and re-binding to the base skeleton places it correctly.  A STATIC
  component (a MeshFilter such as a head wreath) is the opposite: its verts are
  local and it relies on its object transform, so that transform is kept.

Usage (invoked by a caller that has already extracted the bundles):
    blender --background --factory-startup --python assemble_suit_blender.py -- \
        --root <extraction dir> --tex <texture dir> --out <out.blend> \
        --base pc_<id>_nk --parts a,b,c[,...] [--glb 1]

The extraction dir must hold, per component, ``<name>/FBX_GameObjects/<name>/
<name>.fbx`` (AssetStudio splitObjects layout); ``--parts`` are those <name>s
(from suit_parts.py, minus pieces you do not want).  Prints ``ASSEMBLE_DONE``.
"""
import importlib.util
import json
import os
import re
import sys

import bpy
import mathutils

RIS = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.join(RIS, "roe_xps_addon.py")


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


addon = load_mod("roe_suit_addon", ADDON)
addon.register()
sys.path.insert(0, RIS)
sys.path.insert(0, os.path.join(RIS, "..", "blender_addons"))
nude = load_mod("roe_suit_nude", os.path.join(RIS, "export_nude_model_blender.py"))
char = load_mod("roe_suit_char", os.path.join(RIS, "export_character_model_blender.py"))

# Pieces whose Blender material wants alpha (the game gives them a
# ``*_transparency`` material): lace panties, stockings, fishnets.
HASHED_RE = re.compile(r"panties|stocking|fishnet", re.IGNORECASE)
# Pieces that reuse another piece's atlas rather than one named after them.
SPECIAL_TEX = {"garter": "eggvibrator"}


def argval(flag, default=None):
    argv = sys.argv[sys.argv.index("--") + 1:]
    return argv[argv.index(flag) + 1] if flag in argv else default


def resolve_albedo(albedo_index, piece):
    """Find the Lynn_<piece>_rgbx_Albedo texture for a component."""
    for candidate in (piece, re.sub(r"^[LR](?=[A-Z])", "", piece),
                      SPECIAL_TEX.get(piece.lower(), "")):
        if not candidate:
            continue
        key = char._texture_key("Lynn_%s_obj001" % candidate)
        if key in albedo_index:
            return albedo_index[key]
    return None


def main():
    root = argval("--root")
    texdir = argval("--tex")
    out = argval("--out")
    basefbx = argval("--base")
    parts = argval("--parts", "").split(",") if argval("--parts") else []
    want_glb = argval("--glb", "0") != "0"

    def fbxpath(name):
        return os.path.join(root, name, "FBX_GameObjects", name, name + ".fbx")

    # --- base body: nude six-slot materialize via the existing workers ---
    bpy.ops.wm.read_factory_settings(use_empty=True)
    props = bpy.context.scene.roe
    props.workflow_mode = "ROE"
    props.apply_scope = "LATEST"
    props.replace_previous = False
    props.fbx_path = fbxpath(basefbx)
    props.tex_dir = texdir
    if bpy.ops.roe.import_fbx() != {"FINISHED"}:
        raise RuntimeError("base FBX import failed: %s" % basefbx)
    if bpy.ops.roe.apply_materials(repair_scope="ALL") != {"FINISHED"}:
        raise RuntimeError("base material pass failed")
    nude.split_combined_nude_body(addon, texdir)
    base_arm = next((o for o in bpy.context.scene.objects
                     if o.type == "ARMATURE"), None)
    if base_arm is None:
        raise RuntimeError("base body has no armature")

    albedo_index = char.build_albedo_index(texdir)
    report = []
    for name in parts:
        path = fbxpath(name)
        if not os.path.isfile(path):
            report.append((name, "MISSING", None))
            continue
        before = set(bpy.context.scene.objects)
        bpy.ops.import_scene.fbx(filepath=path, automatic_bone_orientation=True)
        new = [o for o in bpy.context.scene.objects if o not in before]
        meshes = [o for o in new if o.type == "MESH"]
        arms = [o for o in new if o.type == "ARMATURE"]
        match = re.search(r"Area_(.+?)_obj001", name)
        piece = match.group(1) if match else name
        tex = resolve_albedo(albedo_index, piece)
        hashed = bool(HASHED_RE.search(piece))
        for mesh in meshes:
            for modifier in list(mesh.modifiers):
                if modifier.type == "ARMATURE":
                    mesh.modifiers.remove(modifier)
            if arms:
                # skinned: verts are model-space; drop the spurious object
                # transform and re-bind to the base skeleton (names match).
                mesh.parent = base_arm
                mesh.matrix_parent_inverse = mathutils.Matrix.Identity(4)
                mesh.matrix_world = mathutils.Matrix.Identity(4)
                mesh.modifiers.new("Armature", "ARMATURE").object = base_arm
            else:
                # static mesh: keep its own transform, just travel with the char
                world = mesh.matrix_world.copy()
                mesh.parent = base_arm
                mesh.matrix_parent_inverse = base_arm.matrix_world.inverted()
                mesh.matrix_world = world
            mesh.data.materials.clear()
            mesh.data.materials.append(addon.albedo_mat(
                "%s_mat" % piece[:28], tex, desat=False, hashed=hashed))
            for polygon in mesh.data.polygons:
                polygon.material_index = 0
        for armature in arms:
            bpy.data.objects.remove(armature, do_unlink=True)
        report.append((name, "ok", dict(
            piece=piece, verts=sum(len(m.data.vertices) for m in meshes),
            tex=os.path.basename(tex) if tex else "MISSING")))

    for name, status, info in report:
        print("PART %-46s %s %s" % (
            name[:46], status, json.dumps(info, ensure_ascii=True) if info else ""))

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    stem = os.path.splitext(os.path.basename(out))[0]
    outdir = os.path.dirname(out)
    os.makedirs(outdir, exist_ok=True)
    char.render_preview(meshes, os.path.join(outdir, stem + "_preview.png"),
                        os.path.join(outdir, "." + stem))
    if want_glb:
        glb = os.path.join(outdir, "glb", stem + ".glb")
        os.makedirs(os.path.dirname(glb), exist_ok=True)
        char.select_character_objects(meshes, [base_arm])
        bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB",
                                  use_selection=True, export_apply=False)
    packed, failures = char.pack_images(meshes)
    if failures:
        raise RuntimeError("image packing failed: %s" % "; ".join(failures))
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=out, check_existing=False)
    missing = [n for n, s, i in report if s == "MISSING"
               or (i and i.get("tex") == "MISSING")]
    print("SAVED %s meshes=%d packed=%d missing=%s"
          % (out, len(meshes), len(packed), missing))
    print("ASSEMBLE_DONE")


if __name__ == "__main__":
    main()
