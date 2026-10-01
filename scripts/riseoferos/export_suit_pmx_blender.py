"""PMX for an assembled suit / nude-base .blend (export_suits.py, then hq_materials_blender.py), through the
batch's own conversion: export_character_model_blender.export_pmx (Convert_to_MMD5 rig, bust / cloth / hair
physics, face morphs, tear gate, grant-order check), so a suit's PMX matches a dressed character's.

Before the conversion it does what the batch does between a fresh model's .blend and its PMX, on a file that
only has the game (HQ) materials left:
  * every HQ material becomes a plain colour material on its baked PMX texture (albedo x _BaseColor x AO,
    hq_material_data.py export/<material>__pmx_diffuse.png, recorded on the material as roe_hq_pmx) - mmd_tools
    takes one colour texture per material; an alpha-tested / blended slot keeps alpha (the add-on's albedo_mat)
  * the procedural eye is baked to a texture (the suit's body mesh carries the head: the eye is the slot whose
    material is "eye", not slot 1 as on a dressed character)
plus one step only suits need:
  * pieces parented to a bone (wreath, rings, horns, ears, halo, glasses ...) are skinned 100 % to that bone:
    mmd_tools writes vertex weights, not object parents
  * packed images whose file is gone are written beside the PMX (the nude bases' lash / brow texture pointed
    into a deleted temp dir, so the PMX stored a dead C: path)
A mesh with no vertex groups at all is reported (unweighted_meshes): fix_suit_slots_blender.py weights the known
ones in the .blend (pieces whose own bones the suit build could not attach).

  blender -b --factory-startup <suit.blend> --python export_suit_pmx_blender.py -- <out.pmx>
The .blend is not saved.  Prints ROE_SUIT_PMX={json} and writes <out>.report.json like the batch.
"""
import json
import os
import re
import sys
import tempfile

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import export_character_model_blender as worker  # noqa: E402

ADDON = os.path.join(HERE, "roe_xps_addon.py")


def base_name(material):
    return re.sub(r"\.\d{3}$", "", material.name) if material else ""


def pmx_colour_materials(addon, meshes):
    """HQ materials -> albedo materials on the baked PMX textures (one per HQ material)."""
    made, swapped, fallback = {}, [], []
    for obj in meshes:
        for index, slot in enumerate(obj.material_slots):
            mat = slot.material
            if mat is None or not mat.get("roe_hq_role"):
                continue
            if mat.name not in made:
                path = mat.get("roe_hq_pmx")
                if not (path and os.path.isfile(path)):
                    # no baked texture (a material without export maps): its own albedo
                    node = next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image
                                 and n.name.endswith("albedo")), None)
                    path = bpy.path.abspath(node.image.filepath) if node else ""
                    fallback.append(mat.name)
                name = re.sub(r"^HQ_", "", mat.name)[:56]
                made[mat.name] = addon.albedo_mat(name, path if path and os.path.isfile(path) else None,
                                                  desat=False, hashed=mat.blend_method == "HASHED")
                if mat.blend_method == "OPAQUE":
                    made[mat.name].blend_method = "OPAQUE"
            slot.material = made[mat.name]
            swapped.append("%s[%d]" % (obj.name, index))
    return {"materials": len(made), "slots": len(swapped), "albedo_fallback": fallback}


def bake_suit_eye(addon, meshes, out_dir):
    head = addon.find_head(meshes)
    if head is None:
        return {"status": "skipped", "reason": "no head mesh"}
    index = next((i for i, s in enumerate(head.material_slots) if base_name(s.material) == "eye"), None)
    if index is None:
        return {"status": "skipped", "reason": "no eye slot on %s" % head.name}
    image = addon.diffuse_image(head.material_slots[index].material)
    if image is None:
        return {"status": "skipped", "reason": "eye slot has no iris image"}
    iris, temp = bpy.path.abspath(image.filepath), None
    if not os.path.isfile(iris):
        if not image.packed_file:
            return {"status": "skipped", "reason": "iris image missing: %s" % iris}
        # packed, its file gone: the bake reads a file (the add-on also re-reads the node's image path)
        temp = os.path.join(tempfile.gettempdir(), "roe_suit_iris_%d.png" % os.getpid())
        with open(temp, "wb") as handle:
            handle.write(image.packed_file.data)
        image.filepath, iris = temp, temp
    os.makedirs(out_dir, exist_ok=True)
    baked = os.path.join(out_dir, re.sub(r"[^A-Za-z0-9_.-]+", "_", head.name) + "_eye_baked.png")
    addon.bake_eye_texture(head, iris, baked, eye_slot=index)
    head.data.materials[index] = addon.albedo_mat("eye_portable", baked, desat=False)
    if temp:
        os.remove(temp)
    return {"status": "baked", "path": baked, "slot": index}


def portable_images(meshes, out_dir):
    """An image whose file is gone but which is packed (the nude bases' lash / brow texture points into a
    deleted temp dir of export_nude_models.ps1) is written next to the PMX: otherwise mmd_tools cannot copy it
    and stores the dead absolute path."""
    written = []
    images = {node.image for obj in meshes for slot in obj.material_slots
              if slot.material is not None and slot.material.use_nodes
              for node in slot.material.node_tree.nodes if node.type == "TEX_IMAGE" and node.image}
    for image in images:
        path = bpy.path.abspath(image.filepath)
        if os.path.isfile(path) or not image.packed_file:
            continue
        os.makedirs(out_dir, exist_ok=True)
        target = os.path.join(out_dir, os.path.basename(path) or re.sub(r"[^A-Za-z0-9_.-]+", "_", image.name))
        with open(target, "wb") as handle:
            handle.write(image.packed_file.data)
        image.filepath = target
        written.append(os.path.basename(target))
    return written


def skin_bone_parented(arm, meshes):
    """A mesh parented to a bone -> parented to the armature object, all vertices weighted to that bone."""
    done = []
    for obj in meshes:
        if obj.parent is not arm or obj.parent_type != "BONE" or not obj.parent_bone:
            continue
        bone = obj.parent_bone
        world = obj.matrix_world.copy()
        group = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
        group.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
        obj.parent_type = "OBJECT"
        obj.parent_bone = ""
        bpy.context.view_layer.update()
        obj.matrix_world = world
        if not any(m.type == "ARMATURE" for m in obj.modifiers):
            obj.modifiers.new("Armature", "ARMATURE").object = arm
        done.append("%s -> %s" % (obj.name, bone))
    return done


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv or not argv[0].lower().endswith(".pmx"):
        raise SystemExit("usage: -- <out.pmx>")
    path = os.path.abspath(argv[0])
    addon = worker.load_addon(ADDON)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = addon.related_armatures(meshes)
    if len(armatures) != 1:
        raise SystemExit("expected one armature, found %s" % [a.name for a in armatures])
    arm = armatures[0]
    prep = {"materials": pmx_colour_materials(addon, meshes),
            "skinned_pieces": skin_bone_parented(arm, meshes)}
    unweighted = [o.name for o in meshes if not o.vertex_groups]
    if unweighted:
        prep["unweighted_meshes"] = unweighted          # would follow the root only: reported, not guessed
    textures = os.path.join(os.path.dirname(path), "textures")
    prep["portable_eye"] = bake_suit_eye(addon, meshes, textures)
    prep["unpacked_images"] = portable_images(meshes, textures)
    out, stats = worker.export_pmx(path, meshes, armatures)
    stats.update(prep, source=bpy.data.filepath, pmx=out)
    with open(os.path.splitext(out)[0] + ".report.json", "w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=1, default=str)
    summary = {"pmx": out, "bytes": os.path.getsize(out), "prep": prep,
               "torn": (stats.get("distortion") or {}).get("torn"),
               "grant_order_violations": len(stats.get("grant_order_violations") or []),
               "face_morphs": len(stats.get("face_morphs") or []), "bones": stats.get("bones"),
               "physics": {k: (v if isinstance(v, (str, int, float)) else len(v))
                           for k, v in (stats.get("physics") or {}).items()}}
    print("ROE_SUIT_PMX=" + json.dumps(summary, ensure_ascii=True, default=str))


main()
