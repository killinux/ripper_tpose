"""Blender side of export_gacha_model.py: the ROE gacha intro girl (pc_gacha01) as a .blend with the game's materials,
built the way the ROE pipeline builds a nude base (roe_xps_addon import + materials, the nude body split,
hq_materials_blender, the batch preview).

  blender -b --factory-startup --python build_gacha_blender.py -- inspect <work>
  blender -b --factory-startup --python build_gacha_blender.py -- build <work> <hq cache> <out.blend>

<work> is export_gacha_model.py's work folder (export\\ = AssetStudio's FBX + _textures\\), <hq cache> the folder its
hq step filled (j_gacha01.json).  Prints GACHA_BUILD={json}; writes <out>.build.json beside the .blend.

The model in the game (scene_meta3d_gachaintro.ab, checked 2026-10-25): Miri's e01 nude body mesh without the fox
ears, Lynn's skin / face / eye / brow materials (pc_j_nk_*), Keleira's k01 hair mesh with pc_gacha01_nk_hair, a gem
necklace, Miri's swimsuit meshes (Miriam_*) with pc_gacha01 textures.  The swimsuit pieces are roots of their own in
the bundle (each with a partial Root_G skeleton): they are moved onto the body's armature by bone name and marked
roe_outfit, so export_suit_pmx_blender.py gives the PMX a 衣服非表示 morph."""
import json
import math
import os
import re
import sys

import bpy

ROE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROE)
import export_character_model_blender as W  # noqa: E402
import hq_materials_blender as HQ  # noqa: E402
from export_nude_model_blender import split_combined_nude_body  # noqa: E402

ADDON = os.path.join(ROE, "roe_xps_addon.py")
CID = "j_gacha01"          # the HQ cache id export_gacha_model.py decodes the materials under (j = Lynn's family)
# the game's material per swimsuit piece: the second copy of each piece in the bundle points at a bundle the game
# does not ship, and the FBX AssetStudio writes for the pants is that copy (no material)
PART_ALBEDO = {"Miriam_Upper_BreastArea_Swimbra_obj001": "pc_gacha01_Swimbra_obj001_rgbx_Albedo.png",
               "Miriam_Lower_PantiesArea_SwimUnderwear_obj001": "pc_gacha01_SwimUnderwear_obj001_Albedo.png"}
REPORT = {}


def log(*a):
    print("[gacha]", *a)


def paths(work):
    export = os.path.join(work, "export")
    fbx = lambda root, name: os.path.join(export, root, "FBX_GameObjects", name, name + ".fbx")  # noqa: E731
    return {"tex": os.path.join(export, "_textures"),
            # the video prefab, not the bundle's own root: same meshes, but the renderers carry the game's materials
            # (the bundle's pc_gacha01_nk has default_material_bare placeholders the game swaps at run time)
            "main": fbx("Prefab_pc_gacha01", "Prefab_pc_gacha01"),
            "parts": [fbx("pc_gacha01_Swimbra_obj001", "pc_gacha01_Swimbra_obj001"),
                      fbx("pc_gacha01_SwimUnderwear_obj001", "pc_gacha01_SwimUnderwear_obj001")]}


def import_fbx(module, path, part=False):
    before = set(bpy.context.scene.objects)
    if part:
        # the add-on's operator scales an import up x100 when its meshes are under 0.5 m (old centimetre exports):
        # a swimsuit piece alone is that small (the bra came out 26 m wide), so the pieces skip the operator
        module.import_fbx_compat(filepath=path, automatic_bone_orientation=True, use_image_search=False)
        new = [o for o in bpy.context.scene.objects if o not in before]
        for o in new:
            if o.type == "MESH":
                module.store_source_layout(o, fbx_path=path)
        return new
    props = bpy.context.scene.roe
    props.fbx_path = path
    r = bpy.ops.roe.import_fbx()
    if r != {"FINISHED"}:
        raise RuntimeError("import failed %r: %s" % (r, path))
    return [o for o in bpy.context.scene.objects if o not in before]


def describe(objs, label):
    log("==", label)
    for o in sorted(objs, key=lambda o: (o.type, o.name)):
        if o.type == "EMPTY":
            continue
        extra = ""
        if o.type == "MESH":
            mats = [s.material.name if s.material else "-" for s in o.material_slots]
            arm = next((m.object.name for m in o.modifiers if m.type == "ARMATURE" and m.object), None)
            extra = "verts %d mats %s arm %s groups %d" % (len(o.data.vertices), mats, arm, len(o.vertex_groups))
        elif o.type == "ARMATURE":
            extra = "bones %d" % len(o.data.bones)
        log("  %-9s %-50s parent=%s %s" % (o.type, o.name, o.parent.name if o.parent else None, extra))
    log("  + %d empties" % sum(1 for o in objs if o.type == "EMPTY"))


def seat_on_body(mesh, body):
    """The swim bra's FBX comes in with its geometry still Y-up (the bra at y 1.16-1.46 m, z ~0: on the floor) - its
    skeleton root is the Bip001 node and the importer's axis conversion does not reach the mesh; the pants are fine.
    Try no turn / +90 / -90 degrees about X and keep the one whose vertices lie closest to the body's surface (median
    distance to the nearest body vertex: 3.2 mm for the bra turned +90, 4.3 mm for the pants as they are)."""
    from mathutils import Matrix
    from mathutils.kdtree import KDTree
    bw = body.matrix_world
    kd = KDTree(len(body.data.vertices))
    for i, v in enumerate(body.data.vertices):
        kd.insert(bw @ v.co, i)
    kd.balance()
    pts = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
    step = max(1, len(pts) // 600)
    cands = {"none": Matrix.Identity(4), "x+90": Matrix.Rotation(math.radians(90), 4, "X"),
             "x-90": Matrix.Rotation(math.radians(-90), 4, "X")}
    med = {}
    for name, rot in cands.items():
        d = sorted(kd.find(rot @ p)[2] for p in pts[::step])
        med[name] = d[len(d) // 2]
    best = min(med, key=med.get)
    if best != "none":
        mw = mesh.matrix_world
        mesh.data.transform(mw.inverted() @ cands[best] @ mw)
        mesh.data.update()
    return {"turn": best, "median_mm": {k: round(1000 * v, 2) for k, v in med.items()}}


def merge_part(main_arm, objs, body):
    """Move a swimsuit root's meshes onto the body's armature (same bone names), drop its own skeleton."""
    arms = [o for o in objs if o.type == "ARMATURE"]
    meshes = [o for o in objs if o.type == "MESH"]
    info = {"meshes": [m.name for m in meshes], "rest_diff_mm": 0.0, "missing_bones": [],
            "seat": {m.name: seat_on_body(m, body) for m in meshes}}
    for arm in arms:
        diffs = []
        for b in arm.data.bones:
            if b.name in main_arm.data.bones:
                h0 = main_arm.matrix_world @ main_arm.data.bones[b.name].head_local
                h1 = arm.matrix_world @ b.head_local
                diffs.append((h0 - h1).length)
        info["rest_diff_mm"] = max(info["rest_diff_mm"], 1000 * max(diffs, default=0.0))
        info["shared_bones"] = len(diffs)
    for m in meshes:
        world = m.matrix_world.copy()
        m.parent = main_arm
        m.matrix_parent_inverse = main_arm.matrix_world.inverted()
        m.matrix_world = world
        for mod in m.modifiers:
            if mod.type == "ARMATURE":
                mod.object = main_arm
        if not any(mod.type == "ARMATURE" for mod in m.modifiers):
            m.modifiers.new("Armature", "ARMATURE").object = main_arm
        info["missing_bones"] += [g.name for g in m.vertex_groups if g.name not in main_arm.data.bones]
        m["roe_outfit"] = 1           # export_suit_pmx_blender.py: the PMX's 衣服非表示 morph hides these
    for o in objs:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    return info


def tooth_slot(module, body, tex):
    """The teeth: the game draws them with pc_common_tooth; the add-on's head pass puts every polygon that is not eye
    / lash / brow / tear on the face atlas, the teeth included (no ROE export so far has a tooth material).  Their
    own slot from the FBX's material layout."""
    names = module.source_material_names(body)
    indices = module.cached_source_indices(body)
    if not names or not indices or "pc_common_tooth" not in names:
        return {"status": "skipped", "names": names, "indices": bool(indices)}
    src = names.index("pc_common_tooth")
    polys = [i for i, k in enumerate(indices) if k == src]
    if not polys or len(indices) != len(body.data.polygons):
        return {"status": "skipped", "polys": len(polys), "layout": len(indices), "mesh": len(body.data.polygons)}
    before = {}
    for i in polys:
        slot = body.material_slots[body.data.polygons[i].material_index]
        key = slot.material.name if slot.material else "-"
        before[key] = before.get(key, 0) + 1
    mat = module.albedo_mat("tooth", os.path.join(tex, "pc_common_tooth_rgbx_Albedo.png"))
    body.data.materials.append(mat)
    slot = len(body.data.materials) - 1
    for i in polys:
        body.data.polygons[i].material_index = slot
    return {"status": "done", "polygons": len(polys), "slot": slot, "were_on": before}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv or argv[0] not in ("inspect", "build") or (argv[0] == "build" and len(argv) != 4):
        raise SystemExit("usage: -- inspect <work> | build <work> <hq cache> <out.blend>")
    mode, work = argv[0], os.path.abspath(argv[1])
    p = paths(work)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    module = W.load_addon(ADDON)
    props = bpy.context.scene.roe
    props.workflow_mode = "ROE"
    props.apply_scope = "LATEST"
    props.replace_previous = False
    props.tex_dir = p["tex"]

    main_objs = import_fbx(module, p["main"])
    part_objs = [import_fbx(module, f, part=True) for f in p["parts"]]
    if mode == "inspect":
        describe(main_objs, "main")
        for f, objs in zip(p["parts"], part_objs):
            describe(objs, os.path.basename(f))
        return
    cache, out_blend = os.path.abspath(argv[2]), os.path.abspath(argv[3])

    main_arms = [o for o in main_objs if o.type == "ARMATURE"]
    if len(main_arms) != 1:
        raise RuntimeError("main import: expected one armature, got %s" % [a.name for a in main_arms])
    main_arm = main_arms[0]
    # the prefab's run-time helpers, not part of the model: the censor sphere's anchor (MosaicBoundingSphere_e01) and
    # the MagicaCloth butt-poke setup (MagicaUnitRoot > Config_* > Cloth_*).  The other empties (muscle strand ends,
    # props, footsteps, Miri's unweighted ear bones) are the ones every ROE nude import has.
    dropped = []
    doomed = [o for o in main_objs if o.name.startswith(("MosaicBoundingSphere", "MagicaUnitRoot"))]
    while doomed:
        o = doomed.pop()
        doomed.extend(o.children)
        dropped.append(o.name)
        bpy.data.objects.remove(o, do_unlink=True)
    REPORT["dropped"] = dropped
    body = next(o for o in bpy.context.scene.objects if o.type == "MESH" and o.name.startswith("pc_e01_nk_body"))
    bpy.context.view_layer.update()
    REPORT["parts"] = [merge_part(main_arm, objs, body) for objs in part_objs]
    log("parts", json.dumps(REPORT["parts"]))

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    props.apply_scope = "VISIBLE"
    r = bpy.ops.roe.apply_materials(repair_scope="ALL")
    if r != {"FINISHED"}:
        raise RuntimeError("material pass failed: %r" % (r,))
    REPORT["material_pass"] = props.diagnostic_report

    fixed = []
    for o in meshes:
        alb = PART_ALBEDO.get(re.sub(r"\.\d{3}$", "", o.name))
        if not alb:
            continue
        mat = o.material_slots[0].material if o.material_slots else None
        img = module.diffuse_image(mat) if mat else None
        if img is None or os.path.basename(bpy.path.abspath(img.filepath)) != alb:
            name = re.sub(r"(_rgbx)?_Albedo$", "", os.path.splitext(alb)[0])
            o.data.materials.clear()
            o.data.materials.append(module.albedo_mat(name, os.path.join(p["tex"], alb)))
            fixed.append(o.name)
    REPORT["swimsuit_material_fixed"] = fixed

    # the nude body split (export_nude_model_blender): the torso back to its own atlas.  It finds the body texture by
    # the mesh name - Lynn's pc_j_nk_body here, the material the game gives this body - so the mesh carries that name
    # for the call
    head = module.find_head(meshes)
    if head is None:
        raise RuntimeError("no head (Eyeball vertex groups) found")
    head.name = "pc_j_nk_body"
    REPORT["nude_split"] = split_combined_nude_body(module, p["tex"])
    head.name = "pc_gacha01_nk_body"
    REPORT["tooth"] = tooth_slot(module, head, p["tex"])
    log("nude split", REPORT["nude_split"], "tooth", REPORT["tooth"])

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    untextured = []
    for o in meshes:
        for i, s in enumerate(o.material_slots):
            m = s.material
            if m is None:
                untextured.append("%s[%d] <empty>" % (o.name, i))
            elif module.diffuse_image(m) is None and not module.material_is_transparent_only(m):
                untextured.append("%s[%d] %s" % (o.name, i, m.name))
    REPORT["untextured"] = untextured
    REPORT["slots"] = {o.name: [s.material.name if s.material else None for s in o.material_slots] for o in meshes}

    _state, hq = HQ.apply(meshes, stem="pc_gacha01_nk", cid=CID, cache=cache, log=log)
    REPORT["hq"] = hq
    os.makedirs(os.path.dirname(out_blend), exist_ok=True)
    stem = os.path.splitext(os.path.basename(out_blend))[0]
    REPORT["preview"] = W.render_preview(meshes, os.path.join(os.path.dirname(out_blend), stem + "_preview.png"),
                                         os.path.join(os.path.dirname(out_blend), "." + stem))
    packed, failures = W.pack_images(meshes)
    if failures:
        raise RuntimeError("image packing failed: %s" % failures)
    # an active object: export_suit_pmx_blender.py's first mode_set needs one (a file built from an empty scene has
    # none: "Context missing active object"), and the file opens with the rig selected, in Material Preview
    bpy.ops.object.select_all(action="DESELECT")
    main_arm.select_set(True)
    bpy.context.view_layer.objects.active = main_arm
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = "MATERIAL"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=out_blend, check_existing=False)
    REPORT.update(blend=out_blend, packed=len(packed))
    with open(os.path.splitext(out_blend)[0] + ".build.json", "w", encoding="utf-8") as fh:
        json.dump(REPORT, fh, ensure_ascii=False, indent=1, default=str)
    print("GACHA_BUILD=" + json.dumps({"blend": out_blend, "preview": REPORT["preview"], "untextured": untextured,
                                       "hq_errors": hq.get("errors"), "hq_kept": hq.get("kept"),
                                       "tooth": REPORT["tooth"], "parts": REPORT["parts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
