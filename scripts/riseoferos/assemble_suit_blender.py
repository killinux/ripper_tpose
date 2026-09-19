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

Bundle mode (2026-09-19, used by ``export_suits.py`` for the whole catalogue):
    ... --root <extraction dir> --tex <texture dir> --out <out.blend> \
        --suit <suit.json written by suit_bundle.py> [--glb 1]

reads the parts straight from ``suit_bundle.py``'s dump instead of FBX: exact
mesh per stub root (same-named parts of other suits cannot collide), bone
weights re-mapped onto the base skeleton (accessory-only physics bones fall back
to their nearest ancestor that the base rig has), static parts placed from the
component prefab's transform and bone-parented to the closest bone, and every
material textured from the texture names the renderer's material really uses
(albedo + normal map) rather than a name guess.  The dressed selection comes from
the manifest (``excluded``), see ``suit_bundle.select_dressed``.
"""
import importlib.util
import json
import math
import os
import re
import sys

import bpy
import mathutils
import numpy as np

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

# --- bundle mode helpers -------------------------------------------------------
# Unity world (Y-up; the character prefab rotates its Z-up model -90 deg about X)
# -> the model frame -> Blender (X mirrored, exactly what the FBX route yields).
UNITY_TO_MODEL = mathutils.Matrix.Rotation(math.radians(90.0), 4, "X")
MIRROR_X = mathutils.Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
# rig helpers that should not win the "nearest bone" search for a static part
HELPER_BONE_RE = re.compile(r"muscle|geosphere|point_|nub|strand|helper|twist|prop|labia|anus|clitoris|vagina"
                            r"|nipple|breast|eye|mouth|tongue|teeth|jaw|hair", re.IGNORECASE)


def blender_matrix_from_unity(rows):
    unity = mathutils.Matrix([list(map(float, r)) for r in rows])
    return MIRROR_X @ (UNITY_TO_MODEL @ unity) @ MIRROR_X


def nearest_bone(armature, point):
    best, best_d = None, float("inf")
    for bone in armature.data.bones:
        d = ((armature.matrix_world @ bone.head_local) - point).length
        if HELPER_BONE_RE.search(bone.name):
            d += 0.15
        if not bone.name.startswith("Bip001"):
            d += 0.10                                     # prefer the Biped skeleton proper
        if d < best_d:
            best, best_d = bone, d
    return best


def suit_material(part, material, cache):
    """Principled material from the renderer's real albedo (+ normal map)."""
    files = material.get("files", {})
    key = material.get("name") or part["piece"]
    if key in cache:
        return cache[key]
    mat = addon.albedo_mat("%s_mat" % key[:40], files.get("albedo"), desat=False,
                           hashed=bool(part.get("transparent")))
    if not files.get("albedo") and mat.node_tree:
        # a slot without an albedo map: the lens of glasses / a visor is glass,
        # anything else (the "<piece>2" gloss layer of latex, a plain trim) takes
        # the material's own _BaseColor
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is not None:
            if re.search(r"glass|lens|visor|goggle", "%s %s" % (key, part["piece"]), re.IGNORECASE):
                bsdf.inputs["Base Color"].default_value = (0.85, 0.92, 1.0, 1.0)
                bsdf.inputs["Alpha"].default_value = 0.18
                bsdf.inputs["Roughness"].default_value = 0.08
                mat.blend_method = "BLEND"
                mat.shadow_method = "NONE"
            else:
                color = material.get("color") or [0.5, 0.5, 0.5, 1.0]
                bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
                bsdf.inputs["Roughness"].default_value = 0.35
                bsdf.inputs["Alpha"].default_value = min(1.0, max(0.0, color[3])) if len(color) > 3 else 1.0
                if bsdf.inputs["Alpha"].default_value < 0.999:
                    mat.blend_method = "BLEND"
    normal = files.get("normal")
    if normal and os.path.isfile(normal) and mat.node_tree:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is not None:
            img = nodes.new("ShaderNodeTexImage")
            img.image = bpy.data.images.load(normal, check_existing=True)
            img.image.colorspace_settings.name = "Non-Color"
            img.location = (-600, -400)
            nmap = nodes.new("ShaderNodeNormalMap")
            nmap.location = (-300, -400)
            links.new(img.outputs["Color"], nmap.inputs["Color"])
            links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    cache[key] = mat
    return mat


def import_suit_part(part, base_arm, cache):
    """Build one part from suit_bundle.py's npz dump, bound to the base rig."""
    data = np.load(part["npz"])
    name = re.sub(r"_obj\d+$", "", part["root"])[:60]
    # Unity -> Blender is an X mirror.  A skinned part is already in the model
    # frame.  A static part is baked into world space here: its placement matrix
    # (the same-named object of the component prefab) carries the -90 deg X
    # rotation of the character root AND the unit scale -- the accessory-pool
    # props are authored in centimetres.  A pool prop the stub instances twice as
    # <name>_L / <name>_R shares one one-sided mesh: the _R root is the
    # model-space mirror of the _L one, i.e. it simply skips the X flip.
    flip = np.diag([1.0, 1.0, 1.0]) if part.get("mirrored") else np.diag([-1.0, 1.0, 1.0])
    linear, offset = flip, np.zeros(3)
    info_reading = "model-frame"
    if part.get("world_matrix") and part.get("placement_from") in ("components", "bindpose", "stub"):
        # Unity-world placement of the mesh (static: the prefab's transform chain;
        # skinned: BoneWorld * BindPose, i.e. where the mesh sits at bind time --
        # identity for a mesh authored Y-up, a -90 deg X turn for the usual Z-up
        # ones) brought back into the Z-up model frame
        raw = np.array(part["world_matrix"], dtype=np.float64)
        rx90 = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
        linear = flip @ rx90 @ raw[:3, :3]
        offset = flip @ rx90 @ raw[:3, 3]
        # The data does not say in which frame a part was authored: most sit in
        # the Z-up model frame (the placement above is then the identity), some
        # Y-up in Unity world, a static prop may carry no rotation at all, and an
        # accessory rigged only to its own physics bones (hat, earrings) is only
        # placed once the game hangs it on a body bone.  The body decides: of the
        # readings available keep the one whose centroid lands closest to a bone.
        raw_verts = data["vertices"].astype(np.float64)
        c0 = raw_verts.mean(axis=0)
        # what the raw coordinates look like decides which readings make sense:
        # a mesh sitting inside the body volume is authored in place (Z-up model
        # frame, or Y-up Unity world), one hugging the origin is local to the bone
        # it gets hung on
        in_body_zup = abs(c0[0]) < 0.7 and abs(c0[1]) < 0.7 and 0.0 <= c0[2] < 2.0
        in_body_yup = abs(c0[0]) < 0.7 and abs(c0[2]) < 0.7 and 0.0 <= c0[1] < 2.0
        local = float(np.linalg.norm(c0)) < 0.35
        candidates = [("placement", linear, offset)]
        if in_body_zup:
            candidates.append(("model-frame", flip, np.zeros(3)))
        if in_body_yup:
            candidates.append(("unity-world", flip @ raw[:3, :3], flip @ raw[:3, 3]))
        if part.get("attach_matrix") and local:
            # already in the model frame (body bind pose x mesh-in-root-bone space)
            att = np.array(part["attach_matrix"], dtype=np.float64)
            candidates.append(("attach:" + part.get("attach_bone", "?"), flip @ att[:3, :3], flip @ att[:3, 3]))

        area_bone = base_arm.data.bones.get(part.get("area_bone") or "")

        def bone_distance(lin, off):
            centre = mathutils.Vector((raw_verts @ lin.T + off).mean(axis=0).tolist())
            # measure against the bone the part's Area names (a hat belongs at the
            # head, not at whichever of the many toe bones happens to be closest)
            bone = area_bone or nearest_bone(base_arm, centre)
            return ((base_arm.matrix_world @ bone.head_local) - centre).length if bone else 1e9

        scored = [(bone_distance(lin, off) + (0.0 if i == 0 else 0.05), name, lin, off)
                  for i, (name, lin, off) in enumerate(candidates)]
        scored.sort(key=lambda s: s[0])
        _, chosen, linear, offset = scored[0]
        info_reading = chosen
    verts = data["vertices"].astype(np.float64) @ linear.T + offset
    if part["kind"] == "static" and len(verts) and float((verts.max(axis=0) - verts.min(axis=0)).max()) < 5e-3:
        return {"piece": part["piece"], "verts": 0, "kind": part["kind"], "tex": [], "skipped": "degenerate placeholder mesh"}
    tris = data["indices"].reshape(-1, 3)
    if np.linalg.det(linear) < 0:
        tris = tris[:, [0, 2, 1]]                          # mirrored -> reverse winding
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts.tolist(), [], tris.tolist())
    if len(mesh.polygons) == len(tris) and len(part.get("submeshes", [])) > 1:
        poly_mat = np.zeros(len(tris), dtype=np.int32)
        for first, count, index in part["submeshes"]:
            poly_mat[first // 3:(first + count) // 3] = index
        mesh.polygons.foreach_set("material_index", poly_mat.tolist())
    if "uv0" in data.files:
        uv = data["uv0"].astype(np.float32)
        loop_verts = np.zeros(len(mesh.loops), dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", loop_verts)
        layer = mesh.uv_layers.new(name="UVMap")
        layer.data.foreach_set("uv", uv[loop_verts].ravel().tolist())
    if "normals" in data.files and len(data["normals"]) == len(verts):
        normals = data["normals"].astype(np.float64) @ np.linalg.inv(linear)   # n' = inv(M)^T n
        length = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = np.where(length > 1e-6, normals / np.maximum(length, 1e-6), (0.0, 0.0, 1.0))
        mesh.use_auto_smooth = True
        mesh.normals_split_custom_set_from_vertices([tuple(v) for v in normals])
    mesh.validate(clean_customdata=False)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    for material in part.get("materials", []):
        obj.data.materials.append(suit_material(part, material, cache))
    info = {"piece": part["piece"], "verts": len(verts), "kind": part["kind"], "reading": info_reading,
            "tex": [os.path.basename(m.get("files", {}).get("albedo", "")) or "MISSING"
                    for m in part.get("materials", [])]}
    base_bones = base_arm.data.bones
    if part["kind"] == "skinned":
        ancestors = part.get("bone_ancestors", {})

        def remap(bone_name):
            if bone_name in base_bones:
                return bone_name
            for ancestor in ancestors.get(bone_name, []):
                if ancestor in base_bones:
                    return ancestor
            return None

        mapped = [remap(b) if b else None for b in part["bones"]]
        info["remapped"] = sorted({b for b, m in zip(part["bones"], mapped) if b and m != b})
        info["unbound_bones"] = sorted({b for b, m in zip(part["bones"], mapped) if b and m is None})
        indices, weights = data["bone_indices"], data["bone_weights"]
        groups = {}
        for vi in range(len(verts)):
            for k in range(indices.shape[1]):
                w = float(weights[vi, k])
                if w <= 0.0:
                    continue
                target = mapped[int(indices[vi, k])]
                if target is None:
                    continue
                groups.setdefault(target, {}).setdefault(vi, 0.0)
                groups[target][vi] += w
        for target, items in groups.items():
            group = obj.vertex_groups.new(name=target)
            for vi, w in items.items():
                group.add([vi], w, "REPLACE")
        obj.parent = base_arm
        obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
        obj.matrix_world = mathutils.Matrix.Identity(4)
        obj.modifiers.new("Armature", "ARMATURE").object = base_arm
    else:
        # baked into world space above: hang it on the bone closest to its centroid
        anchor = mathutils.Vector(verts.mean(axis=0).tolist())
        bone = nearest_bone(base_arm, anchor)
        bpy.context.view_layer.update()
        obj.parent = base_arm
        obj.parent_type = "BONE"
        obj.parent_bone = bone.name
        obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
        obj.matrix_world = mathutils.Matrix.Identity(4)
        info["bone"] = bone.name
        info["at"] = [round(c, 3) for c in anchor]
    return info


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
    suit = None
    if argval("--suit"):
        with open(argval("--suit"), encoding="utf-8") as fh:
            suit = json.load(fh)
        basefbx = basefbx or suit.get("base")

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
    if suit is not None:
        cache = {}
        excluded = suit.get("excluded", {})
        for part in suit["parts"]:
            if "error" in part:
                report.append((part["root"], "MISSING", None))
            elif part["root"] in excluded:
                print("SKIP %-46s %s" % (part["root"][:46], excluded[part["root"]]))
            else:
                report.append((part["root"], "ok", import_suit_part(part, base_arm, cache)))
        parts = []
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
               or (i and "MISSING" in (i.get("tex") if isinstance(i.get("tex"), list) else [i.get("tex")]))]
    print("SAVED %s meshes=%d packed=%d missing=%s"
          % (out, len(meshes), len(packed), missing))
    print("ASSEMBLE_DONE")


if __name__ == "__main__":
    main()
