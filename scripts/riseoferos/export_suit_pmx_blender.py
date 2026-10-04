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
Marks other scripts leave in the .blend:
  * roe_added_weapon (add_weapon_blender.py: a battle weapon the HD model lacks) - those meshes and bones are left
    out; pmx_add_weapon.py appends the weapon to the PMX afterwards with its 武器非表示 morph, like the main model's.
    The PMX's index fields are sized with the weapon counted in (it cannot widen them: reserve_indices)
  * roe_outfit (complete_nude_body_blender.py --variant full: the outfit over a completed body) - the PMX gets a
    material morph 衣服非表示 over those meshes' materials (pmx_hide_morph.py): 1 = the body underneath.  The body's
    shape key 裸体形状 (its own shape; the basis is fitted under the outfit) becomes a vertex morph, and 衣服非表示
    a group morph of it and the material morph 衣服非表示_材質, so the body is whole again when the outfit goes

  blender -b --factory-startup <suit.blend> --python export_suit_pmx_blender.py -- <out.pmx> [--pmx-morphs bone]
The expressions come out as vertex morphs (default) or, with --pmx-morphs bone / ROE_PMX_MORPHS=bone, bone morphs.
The .blend is not saved.  Prints ROE_SUIT_PMX={json} and writes <out>.report.json like the batch.
"""
import json
import os
import re
import sys
import tempfile

import bpy
import numpy as np

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


OUTFIT_MORPH = "衣服非表示"
NUDE_SHAPE = "裸体形状"      # the full version's body: its own shape, the basis is fitted under the outfit


def drop_added_weapons(arm, meshes):
    """Meshes and bones add_weapon_blender.py added (roe_added_weapon): pmx_add_weapon.py appends the weapon to the
    PMX instead, with its hide morph and the bones the battle motions key."""
    gone = [o for o in meshes if o.get("roe_added_weapon")]
    names = [o.name for o in gone]
    bones = [b.name for b in arm.data.bones if b.get("roe_added_weapon")]
    size = {"verts": sum(len(o.data.vertices) for o in gone), "materials": sum(len(o.material_slots) for o in gone),
            "bones": len(bones)}
    for obj in gone:
        bpy.data.objects.remove(obj, do_unlink=True)
    if bones:
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        arm.hide_set(False)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        for name in bones:
            eb = arm.data.edit_bones.get(name)
            if eb is not None:
                arm.data.edit_bones.remove(eb)
        bpy.ops.object.mode_set(mode="OBJECT")
    return {"meshes": names, "bones": bones, "size": size}


def keep_shape_keys_in_rest_bakes():
    """Convert_to_MMD5's _bake_pose_delta_to_rest (the worker's A-pose: the arms swung down and baked as rest)
    leaves out meshes with shape keys - the full version's body (裸体形状) kept T-pose arms on an A-pose skeleton,
    the gloves hung below the hands.  Wrapped: such a mesh is baked as plain geometry, each shape key through a
    copy of the mesh in that key's shape, and the keys are put back from the copies."""
    worker.enable_addon("Convert_to_MMD5")
    from Convert_to_MMD5.convert import align
    original = getattr(align._bake_pose_delta_to_rest, "roe_original", align._bake_pose_delta_to_rest)

    def bake(context, obj, plans, log_tag):
        stash = []
        for mesh in [m for m in bpy.data.objects if m.type == "MESH" and m.data.shape_keys and
                     any(mod.type == "ARMATURE" and mod.object == obj for mod in m.modifiers)]:
            twins = []
            for kb in list(mesh.data.shape_keys.key_blocks)[1:]:
                twin = mesh.copy()
                twin.data = mesh.data.copy()
                for coll in mesh.users_collection:
                    coll.objects.link(twin)
                co = np.empty(len(kb.data) * 3, dtype=np.float32)
                kb.data.foreach_get("co", co)
                for key in reversed(list(twin.data.shape_keys.key_blocks)):
                    twin.shape_key_remove(key)
                twin.data.vertices.foreach_set("co", co)
                twins.append((kb.name, kb.value, twin))
            for key in reversed(list(mesh.data.shape_keys.key_blocks)):
                mesh.shape_key_remove(key)
            stash.append((mesh, twins))
        try:
            return original(context, obj, plans, log_tag)
        finally:
            for mesh, twins in stash:
                mesh.shape_key_add(name="Basis", from_mix=False)
                for name, value, twin in twins:
                    kb = mesh.shape_key_add(name=name, from_mix=False)
                    co = np.empty(len(twin.data.vertices) * 3, dtype=np.float32)
                    twin.data.vertices.foreach_get("co", co)
                    kb.data.foreach_set("co", co)
                    kb.value = value
                    data = twin.data
                    bpy.data.objects.remove(twin, do_unlink=True)
                    bpy.data.meshes.remove(data)
    bake.roe_original = original
    align._bake_pose_delta_to_rest = bake


def reserve_indices(extra):
    """pmx_add_weapon.py appends the left-out weapon to the finished PMX and cannot widen its index fields: a08's
    full version has 63,912 vertices, the sword 2,692 more - past 65,535, the most 2-byte vertex indices hold.
    mmd_tools picks each index size from the counts at save time (Header.updateIndexSizes); this makes it count
    the weapon in (vertices, materials and their textures, bones, two more morphs: the hide morphs)."""
    worker.enable_addon("mmd_tools")
    from mmd_tools.core import pmx as pmx_core
    original = getattr(pmx_core.Header.updateIndexSizes, "roe_original", pmx_core.Header.updateIndexSizes)
    widened = []

    def update(self, model):
        original(self, model)
        if self.vertex_index_size < 4 and len(model.vertices) + extra["verts"] > (1 << (8 * self.vertex_index_size)) - 1:
            self.vertex_index_size = 2 if len(model.vertices) + extra["verts"] <= 0xFFFF else 4
            widened.append("vertex %d" % self.vertex_index_size)
        for attr, count, more in (("texture_index_size", len(model.textures), extra["materials"]),
                                  ("material_index_size", len(model.materials), extra["materials"]),
                                  ("bone_index_size", len(model.bones), extra["bones"]),
                                  ("morph_index_size", len(model.morphs), 2)):
            size = getattr(self, attr)
            if size < 4 and count + more >= 1 << (8 * size - 1):         # signed: 127 / 32767
                setattr(self, attr, 2 if size == 1 else 4)
                widened.append("%s %d" % (attr.split("_")[0], getattr(self, attr)))
    update.roe_original = original
    pmx_core.Header.updateIndexSizes = update
    return widened


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv or not argv[0].lower().endswith(".pmx"):
        raise SystemExit("usage: -- <out.pmx> [--pmx-morphs vertex|bone]")
    path = os.path.abspath(argv[0])
    if "--pmx-morphs" in argv:      # expressions as vertex (default) or bone morphs: worker.PMX_MORPHS_ENV
        os.environ[worker.PMX_MORPHS_ENV] = argv[argv.index("--pmx-morphs") + 1]
    worker.pmx_morph_kind()         # a bad value stops here, before the conversion
    addon = worker.load_addon(ADDON)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = addon.related_armatures(meshes)
    if len(armatures) != 1:
        raise SystemExit("expected one armature, found %s" % [a.name for a in armatures])
    arm = armatures[0]
    dropped = drop_added_weapons(arm, meshes)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    prep = {"materials": pmx_colour_materials(addon, meshes),
            "skinned_pieces": skin_bone_parented(arm, meshes)}
    if dropped["meshes"]:
        prep["left_out_weapon"] = dropped
        prep["index_sizes_widened"] = reserve_indices(dropped["size"])     # filled when the PMX is written
    outfit_materials = sorted({s.material.name for o in meshes if o.get("roe_outfit")
                               for s in o.material_slots if s.material})
    body_shapes = sorted({NUDE_SHAPE for o in meshes if o.data.shape_keys and o.data.shape_keys.key_blocks.get(NUDE_SHAPE)})
    if any(o.data.shape_keys for o in meshes):
        keep_shape_keys_in_rest_bakes()
    unweighted = [o.name for o in meshes if not o.vertex_groups]
    if unweighted:
        prep["unweighted_meshes"] = unweighted          # would follow the root only: reported, not guessed
    textures = os.path.join(os.path.dirname(path), "textures")
    prep["portable_eye"] = bake_suit_eye(addon, meshes, textures)
    prep["unpacked_images"] = portable_images(meshes, textures)
    out, stats = worker.export_pmx(path, meshes, armatures)
    if outfit_materials:
        import pmx_hide_morph
        prep["outfit_morph"] = pmx_hide_morph.add_hide_morph(out, out, OUTFIT_MORPH, outfit_materials,
                                                             with_morphs=body_shapes)
    stats.update(prep, source=bpy.data.filepath, pmx=out)
    with open(os.path.splitext(out)[0] + ".report.json", "w", encoding="utf-8") as handle:
        json.dump(stats, handle, ensure_ascii=False, indent=1, default=str)
    summary = {"pmx": out, "bytes": os.path.getsize(out), "prep": prep,
               "torn": (stats.get("distortion") or {}).get("torn"),
               "grant_order_violations": len(stats.get("grant_order_violations") or []),
               "face_morphs": len(stats.get("face_morphs") or []), "bones": stats.get("bones"),
               "morph_kind": stats.get("face_morph_kind"), "vertex_morph_bake": stats.get("vertex_morph_bake"),
               "physics": {k: (v if isinstance(v, (str, int, float)) else len(v))
                           for k, v in (stats.get("physics") or {}).items()}}
    print("ROE_SUIT_PMX=" + json.dumps(summary, ensure_ascii=True, default=str))


if __name__ == "__main__":      # export_suit_xps_blender.py imports the helpers above
    main()
