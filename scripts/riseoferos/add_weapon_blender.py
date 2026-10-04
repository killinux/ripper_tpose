"""Put an outfit's battle weapon into a Rise of Eros .blend (Blender side of weapon_dump.py).

Some outfits show their weapon only in battle: the HD prefab the .blend is built from has none (a08's greatsword,
two mirrored halves that part in the skills).  weapon_dump.py reads the battle prefab's skinned meshes at the HD rest;
this builds them into the open .blend:
  * game -> Blender: the similarity (or mirror + similarity) fitted on the bones the game skeleton and the
    armature share, outliers dropped
  * the weapon's bones and the ancestors linking them (Point007_L > chain_ALL > chain02 ...) are added to the
    armature where missing, parented to the first ancestor it has (none: top level, their game parent is Root)
  * one mesh per renderer, skinned with the game weights, custom normals from the game, winding to match
  * material: the game's (hq_materials_blender: albedo, normal, metal / smoothness / AO from the HQ cache)
  * marked: roe_added_weapon = <id> (export_suit_pmx_blender.py leaves them out - pmx_add_weapon.py adds the
    weapon to the PMX with its 武器非表示 morph, as for the main model) and roe_xps_optional = "+weapon" (an XPS
    optional item: XNALara / XPS can hide it)

  blender -b --factory-startup <model.blend> --python add_weapon_blender.py -- --dump <weapon.json> [--out X.blend]
Saves in place unless --out.  A .blend whose armature already has meshes marked for this id is left alone.
"""
import argparse
import json
import os
import re
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
CACHE = os.environ.get("ROE_HQ_CACHE") or r"D:\roe_exports\_hq_materials"


def armature_of(obj):
    return next((m.object for m in obj.modifiers if m.type == "ARMATURE" and m.object), None)


def fit_similarity(P, Q):
    """s, R, t with Q ~ s R P + t (rows are points), R a proper rotation (Umeyama)."""
    mp, mq = P.mean(0), Q.mean(0)
    A, B = P - mp, Q - mq
    U, S, Vt = np.linalg.svd(B.T @ A)
    D = np.diag([1.0, 1.0, np.sign(np.linalg.det(U @ Vt)) or 1.0])
    R = U @ D @ Vt
    return float((S * np.diag(D)).sum() / (A ** 2).sum()), R, mq - (S * np.diag(D)).sum() / (A ** 2).sum() * R @ mp


def game_to_blender(dump, arm, log):
    """4x4 taking Unity world to Blender world: best of a plain and an X-mirrored similarity on shared bones."""
    heads = {b.name: arm.matrix_world @ b.head_local for b in arm.data.bones}
    P = np.array([s["world"][0][3:4] + s["world"][1][3:4] + s["world"][2][3:4] for s in dump["skeleton"]
                  if s["name"] in heads], dtype=float).reshape(-1, 3)
    Q = np.array([tuple(heads[s["name"]]) for s in dump["skeleton"] if s["name"] in heads], dtype=float)
    if len(P) < 6:
        raise SystemExit("only %d bones shared by the game skeleton and the armature" % len(P))
    best = None
    for mirror in (np.diag([1.0, 1.0, 1.0]), np.diag([-1.0, 1.0, 1.0])):
        Pm = P @ mirror.T
        keep = np.ones(len(P), bool)
        for _ in range(3):
            s, R, t = fit_similarity(Pm[keep], Q[keep])
            res = np.linalg.norm(Pm @ (s * R).T + t - Q, axis=1)
            keep = res < max(0.02, 4 * np.median(res[keep]))
        s, R, t = fit_similarity(Pm[keep], Q[keep])
        res = np.linalg.norm(Pm @ (s * R).T + t - Q, axis=1)
        score = res[keep].mean()
        if best is None or score < best[0]:
            best = (score, s, R, t, mirror, keep.sum(), res[keep].max())
    score, s, R, t, mirror, used, worst = best
    M = np.eye(4)
    M[:3, :3] = s * R @ mirror
    M[:3, 3] = t
    log("game -> Blender: scale %.4f, %s, %d of %d shared bones, residual mean %.2f max %.2f mm"
        % (s, "mirrored X" if mirror[0, 0] < 0 else "no mirror", used, len(P), score * 1000, worst * 1000))
    return M


def add_bones(arm, dump, M, log):
    """The weapon's bones and their missing ancestors; returns {name: head (Blender world)}."""
    skel = dump["skeleton"]
    index = {s["name"]: i for i, s in enumerate(skel)}
    have = set(arm.data.bones.keys())
    want = []
    for r in dump["renderers"]:
        for name in r["bones"]:
            i = index[name]
            while i >= 0 and skel[i]["name"] not in have and skel[i]["parent"] >= 0 and skel[i]["name"] != "Root":
                if skel[i]["name"] not in want:
                    want.append(skel[i]["name"])
                i = skel[i]["parent"]

    def depth(name):
        d, i = 0, index[name]
        while skel[i]["parent"] >= 0:
            d, i = d + 1, skel[i]["parent"]
        return d
    want.sort(key=lambda n: (depth(n), index[n]))
    to_world = lambda name: M @ np.array(skel[index[name]]["world"])[:, 3]
    heads = {n: Vector(to_world(n)[:3]) for n in want}
    owned = {n: [] for n in want}
    for r in dump["renderers"]:
        V = np.array(r["v"])
        Vb = V @ M[:3, :3].T + M[:3, 3]
        for i, pairs in enumerate(r["skin"]):
            if pairs and pairs[0][0] in owned:
                owned[pairs[0][0]].append(Vb[i])
    inv = arm.matrix_world.inverted()
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    arm.hide_set(False)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    edit = arm.data.edit_bones
    for name in want:
        parent_i = skel[index[name]]["parent"]
        parent = skel[parent_i]["name"] if parent_i >= 0 else None
        kids = [k for k in want if skel[skel[index[k]]["parent"]]["name"] == name]
        head = heads[name]
        if len(kids) == 1:
            tail = heads[kids[0]]
        elif owned[name]:                                   # towards its farthest vertex: the blade
            pts = np.array(owned[name])
            far = pts[np.argmax(np.linalg.norm(pts - np.array(head), axis=1))]
            tail = head + (Vector(far) - head) * 0.9
        elif parent in heads:
            tail = head + (head - heads[parent])
        else:
            tail = head + Vector((0.0, 0.0, 0.1))
        if (tail - head).length < 1e-3:
            tail = head + Vector((0.0, 0.0, 0.05))
        eb = edit.new(name)
        eb.head, eb.tail = inv @ head, inv @ tail
        eb.parent = edit.get(parent) if parent else None
        eb.use_connect = False
        eb.use_deform = True
    bpy.ops.object.mode_set(mode="OBJECT")
    for name in want:                        # export_suit_pmx_blender.py drops them (pmx_add_weapon.py adds its own)
        arm.data.bones[name]["roe_added_weapon"] = dump["id"]
    log("bones added: %s" % ", ".join(want))
    return heads


def build_meshes(arm, dump, M, log):
    R = M[:3, :3]
    mirrored = np.linalg.det(R) < 0
    Rn = np.linalg.inv(R).T
    made = []
    collection = arm.users_collection[0] if arm.users_collection else bpy.context.scene.collection
    for r in dump["renderers"]:
        V = np.array(r["v"]) @ R.T + M[:3, 3]
        N = np.array(r["n"]) @ Rn.T
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
        tris = np.array(r["tris"], dtype=np.int64)
        # winding: the face normal should point along its vertices' normals
        a, b, c = V[tris[:, 0]], V[tris[:, 1]], V[tris[:, 2]]
        geo = np.cross(b - a, c - a)
        along = np.einsum("ij,ij->i", geo, N[tris[:, 0]] + N[tris[:, 1]] + N[tris[:, 2]])
        if (along < 0).sum() > (along > 0).sum():
            tris = tris[:, [0, 2, 1]]
        me = bpy.data.meshes.new(r["name"])
        me.from_pydata([tuple(v) for v in V], [], [tuple(t) for t in tris.tolist()])
        uv = me.uv_layers.new(name="UV0")
        loops = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", loops)
        uvs = np.array(r["uv"], dtype=np.float32)[loops]
        uv.data.foreach_set("uv", uvs.ravel())
        for p in me.polygons:
            p.use_smooth = True
        me.update()
        me.use_auto_smooth = True
        me.normals_split_custom_set_from_vertices([tuple(n) for n in N])
        obj = bpy.data.objects.new(r["name"], me)
        collection.objects.link(obj)
        groups = {}
        for i, pairs in enumerate(r["skin"]):
            for bone, w in pairs:
                g = groups.get(bone) or obj.vertex_groups.new(name=bone)
                groups[bone] = g
                g.add([i], float(w), "REPLACE")
        obj.parent = arm
        obj.modifiers.new("Armature", "ARMATURE").object = arm
        obj["roe_added_weapon"] = dump["id"]
        obj["roe_xps_optional"] = "+weapon"
        obj["roe_source_materials"] = dump["material"]
        made.append(obj)
        log("   %s: %d vertices, %d triangles%s" % (r["name"], len(V), len(tris), " (mirrored)" if mirrored else ""))
    return made


def weapon_material(dump, objs, log):
    """A plain material on the weapon's albedo, then the game material from the HQ cache."""
    path = os.path.join(CACHE, "textures", dump["albedo"] + ".png")
    mat = bpy.data.materials.new(dump["material"])
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    if os.path.isfile(path):
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(path, check_existing=True)
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    for obj in objs:
        obj.data.materials.append(mat)
    try:
        import hq_materials_blender as hq
        _state, report = hq.apply(objs, stem="pc_%s_hd" % dump["id"], cache=CACHE,
                                  log=lambda line: log("   hq: " + line))
        return {"hq": {k: (len(v) if isinstance(v, list) else v) for k, v in (report or {}).items()
                       if k in ("upgraded", "kept", "errors")}}
    except Exception as exc:                                     # the albedo material stays
        log("   hq materials failed: %s" % exc)
        return {"hq": "failed: %s" % exc}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    dump = json.load(open(a.dump, encoding="utf-8"))
    lines = []

    def log(line):
        print("[weapon] " + line, flush=True)
        lines.append(line)
    counts = {}
    for o in bpy.context.scene.objects:
        if o.type == "MESH" and armature_of(o):
            counts[armature_of(o)] = counts.get(armature_of(o), 0) + 1
    arm = max(counts, key=counts.get)
    if any(o.get("roe_added_weapon") == dump["id"] for o in bpy.context.scene.objects if o.type == "MESH"):
        print("ROE_ADD_WEAPON=" + json.dumps({"skipped": "already has the weapon"}))
        return
    M = game_to_blender(dump, arm, log)
    add_bones(arm, dump, M, log)
    objs = build_meshes(arm, dump, M, log)
    info = weapon_material(dump, objs, log)
    for image in bpy.data.images:                    # the albedo / HQ textures go into the file
        if image.users and not image.packed_file and image.source == "FILE" and \
                os.path.isfile(bpy.path.abspath(image.filepath)):
            image.pack()
    out = os.path.abspath(a.out) if a.out else bpy.data.filepath
    bpy.ops.wm.save_as_mainfile(filepath=out, copy=bool(a.out))
    print("ROE_ADD_WEAPON=" + json.dumps({"out": out, "objects": [o.name for o in objs], **info}, default=str))


if __name__ == "__main__":
    main()
