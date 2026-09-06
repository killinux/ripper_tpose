"""Blender side of the import-into-VaM path: meshes -> a DAZ ``.duf`` scene.

VaM 1.22's in-game Clothing Creator / Hair Creator (``DAZRuntimeCreator``)
imports one file type, a DAZ ``.duf`` scene, and does the body fitting itself.
This script writes that file straight out of Blender -- no DAZ Studio, no
Unity -- using the coordinate map calibrated in ``vam_duf.py``.

It also builds the modelling reference: VaM wraps clothing onto the *base*
Genesis 2 body, so a garment has to be modelled around that exact mesh.
``--base-body`` drops it into the scene from the export cache.

Usage (headless, driven by import_to_vam.ps1):

  blender --background garment.blend --python blender_to_duf.py -- \
      --out D:\vam_imports\jacket.duf --name jacket

  blender --background --python blender_to_duf.py -- \
      --load garment.obj --out D:\vam_imports\jacket.duf

  blender --background --python blender_to_duf.py -- \
      --base-body female --save-blend D:\vam_imports\_reference\Genesis2Female.blend

Result marker (ASCII JSON on stdout):  VAM_DUF={...}
"""

import argparse
import json
import os
import sys

import numpy as np

import bmesh
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import vam_duf as vd  # noqa: E402
import vam_lib as vl  # noqa: E402

RESULT_PREFIX = "VAM_DUF="
DEFAULT_CACHE = r"D:\vam_exports\_cache"


def sanitize(name, fallback="mesh"):
    """DSON ids end up in ``#id`` urls, so keep them url-safe."""
    kept = "".join(c if (c.isalnum() or c in "_- ") else "_" for c in str(name)).strip()
    return kept or fallback


# --------------------------------------------------------------------------
# reading meshes out of Blender
# --------------------------------------------------------------------------

def evaluated_mesh(obj, use_modifiers=True):
    """A triangulated-where-necessary copy of ``obj`` in world space."""
    if use_modifiers:
        source = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    else:
        source = obj
    temp = source.to_mesh()

    bm = bmesh.new()
    bm.from_mesh(temp)
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons)
    out = bpy.data.meshes.new("%s_duf" % obj.name)
    bm.to_mesh(out)
    bm.free()
    source.to_mesh_clear()
    return out, len(ngons)


def read_mesh(obj, use_modifiers=True):
    """(verts, faces, loop uvs or None, face material slots, slot names)."""
    mesh, ngons = evaluated_mesh(obj, use_modifiers)
    try:
        count = len(mesh.vertices)
        co = np.empty(count * 3, dtype=np.float64)
        mesh.vertices.foreach_get("co", co)
        co = co.reshape(count, 3)
        matrix = np.array(obj.matrix_world, dtype=np.float64)
        verts = co @ matrix[:3, :3].T + matrix[:3, 3]

        polys = len(mesh.polygons)
        loop_total = np.empty(polys, dtype=np.int32)
        loop_start = np.empty(polys, dtype=np.int32)
        material_index = np.empty(polys, dtype=np.int32)
        mesh.polygons.foreach_get("loop_total", loop_total)
        mesh.polygons.foreach_get("loop_start", loop_start)
        mesh.polygons.foreach_get("material_index", material_index)

        loops = len(mesh.loops)
        loop_vert = np.empty(loops, dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", loop_vert)

        layer = mesh.uv_layers.active
        loop_uv = None
        if layer is not None:
            flat = np.empty(loops * 2, dtype=np.float64)
            layer.data.foreach_get("uv", flat)
            loop_uv = flat.reshape(loops, 2)

        # A negatively scaled object comes through inside out.
        flip = np.linalg.det(matrix[:3, :3]) < 0
        faces, uv_faces = [], []
        for start, total in zip(loop_start, loop_total):
            corner = list(range(start, start + total))
            if flip:
                corner.reverse()
            faces.append([int(loop_vert[c]) for c in corner])
            if loop_uv is not None:
                uv_faces.append(corner)

        names = [sanitize(slot.material.name if slot.material else "default", "default")
                 for slot in obj.material_slots] or ["default"]
        slots = [min(int(m), len(names) - 1) for m in material_index]
        return {"verts": verts, "faces": faces, "loop_uv": loop_uv,
                "uv_faces": uv_faces, "slots": slots, "names": names,
                "ngons": ngons}
    finally:
        bpy.data.meshes.remove(mesh)


def combine(objects, use_modifiers=True):
    """Merge several objects into the arrays :class:`vam_duf.DufMesh` wants.

    UVs are deduplicated by value first: without that every loop of a shared
    vertex would look like a seam and the writer would emit a duplicate UV
    plus a polygon_vertex_indices row for each of them.
    """
    verts, faces, slots, names = [], [], [], []
    uv_values, uv_faces, uv_lookup = [], [], {}
    have_uv = True
    ngons = 0
    offset = 0
    for obj in objects:
        part = read_mesh(obj, use_modifiers)
        ngons += part["ngons"]
        verts.append(part["verts"])
        remap = {}
        for index, name in enumerate(part["names"]):
            if name not in names:
                names.append(name)
            remap[index] = names.index(name)
        for face, slot in zip(part["faces"], part["slots"]):
            faces.append([v + offset for v in face])
            slots.append(remap[slot])
        if part["loop_uv"] is None:
            have_uv = False
        elif have_uv:
            for corner in part["uv_faces"]:
                row = []
                for loop in corner:
                    u, v = part["loop_uv"][loop]
                    key = (round(float(u), 6), round(float(v), 6))
                    index = uv_lookup.get(key)
                    if index is None:
                        index = len(uv_values)
                        uv_lookup[key] = index
                        uv_values.append(key)
                    row.append(index)
                uv_faces.append(row)
        offset += len(part["verts"])

    return {"verts": np.concatenate(verts) if verts else np.zeros((0, 3)),
            "faces": faces, "slots": slots, "names": names,
            "uvs": np.asarray(uv_values, dtype=np.float64) if have_uv and uv_values else None,
            "uv_faces": uv_faces if have_uv and uv_values else None,
            "ngons": ngons}


def to_duf_mesh(name, parts):
    return vd.DufMesh(name, parts["verts"], parts["faces"], uvs=parts["uvs"],
                      uv_faces=parts["uv_faces"], face_materials=parts["slots"],
                      material_names=parts["names"], space="blender")


# --------------------------------------------------------------------------
# the modelling reference
# --------------------------------------------------------------------------

def base_body_verts(gender, cache_dir=DEFAULT_CACHE):
    """The base body in Blender axes, straight from the export cache."""
    cache = vl.VamCache(cache_dir, None, log=lambda *a: None)
    mesh, _meta = cache.base(gender)
    return vl.to_blender(mesh.verts), mesh


def morph_deltas(obj, gender, cache_dir=DEFAULT_CACHE, threshold=1e-5,
                 use_modifiers=True):
    """What ``obj`` changed about the base body, as {vertex: (dx, dy, dz)}.

    A Genesis 2 morph is defined on the 21556 body vertices; the reference
    body carries the genital graft after those, so a sculpt of the whole
    reference works too -- graft vertices are simply not addressable.
    """
    part = read_mesh(obj, use_modifiers)
    verts = part["verts"]
    base, _mesh = base_body_verts(gender, cache_dir)
    if len(verts) not in (vd.GENESIS2_VERTS, len(base)):
        raise SystemExit(
            "%s has %d vertices; a morph needs the base body's %d (or the whole "
            "%d-vertex reference).  Sculpt a copy of the reference without adding "
            "or deleting vertices." % (obj.name, len(verts), vd.GENESIS2_VERTS, len(base)))
    count = vd.GENESIS2_VERTS
    whole = verts[:len(base)] - base[:len(verts)]
    ignored = int((np.abs(whole[count:]).max(axis=1) > threshold).sum()) if len(base) > count else 0
    offset = whole[:count]
    moved = np.where(np.abs(offset).max(axis=1) > threshold)[0]
    return {int(i): tuple(offset[i]) for i in moved}, len(verts), ignored


def add_base_body(gender, cache_dir=DEFAULT_CACHE):
    """Drop VaM's own Genesis 2 body into the scene, in Blender axes.

    Clothing has to be modelled around this exact mesh: the creator's wrap is
    computed against the base body, not against whatever character happens to
    be loaded.
    """
    cache = vl.VamCache(cache_dir, None, log=lambda *a: None)
    mesh, _meta = cache.base(gender)
    verts = vl.to_blender(mesh.verts)

    # Keep the stored corner order: VaM winds clockwise seen from outside, and
    # to_blender is a mirror, which already flips the handedness of the cross
    # product -- so the same indices come out counter-clockwise (outward
    # normals) in Blender.  Measured with the signed volume of this very mesh:
    # -0.0597 in VaM axes, +0.0597 in Blender axes.
    faces, loop_uv, cursor = [], [], 0
    for length in mesh.poly_len:
        span = slice(cursor, cursor + int(length))
        corner = [int(i) for i in mesh.poly_idx[span]]
        cursor += int(length)
        if len(set(corner)) != len(corner):
            continue        # degenerate, and validate() would drop it anyway
        faces.append(corner)
        loop_uv.extend(int(i) for i in mesh.uv_poly_idx[span])

    name = "Genesis2%s" % gender.capitalize()
    data = bpy.data.meshes.new(name)
    data.from_pydata([tuple(v) for v in verts], [], faces)
    if len(data.loops) == len(loop_uv):
        uvs = np.asarray(mesh.uvs, dtype=np.float32)[np.asarray(loop_uv, dtype=np.int32)]
        data.uv_layers.new(name="UVMap").data.foreach_set("uv", uvs.ravel().tolist())
    data.validate()
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    return obj, len(verts), len(faces)


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def parse_args(argv):
    parser = argparse.ArgumentParser(prog="blender_to_duf")
    parser.add_argument("--out", help="path of the .duf to write")
    parser.add_argument("--load", help="import this .obj/.fbx/.glb first")
    parser.add_argument("--objects", nargs="*",
                        help="object names (default: the selection, else every mesh)")
    parser.add_argument("--name", help="item name inside the DUF (default: the object)")
    parser.add_argument("--separate", action="store_true",
                        help="one .duf per object instead of one merged item")
    parser.add_argument("--no-modifiers", action="store_true")
    parser.add_argument("--plain", action="store_true", help="do not gzip the DUF")
    parser.add_argument("--author", default="ripper_tpose")
    parser.add_argument("--morph", metavar="NAME",
                        help="write a Genesis 2 morph .dsf instead: the deltas "
                             "between the chosen object and the base body")
    parser.add_argument("--gender", choices=("female", "male"), default="female")
    parser.add_argument("--morph-group", default="/Morphs/ripper_tpose",
                        help="where the morph shows up in VaM's morph list")
    parser.add_argument("--morph-min", type=float, default=0.0)
    parser.add_argument("--morph-max", type=float, default=1.0)
    parser.add_argument("--threshold", type=float, default=1e-5,
                        help="ignore vertices that moved less than this (metres)")
    parser.add_argument("--base-body", choices=("female", "male"),
                        help="add VaM's base Genesis 2 body to the scene instead")
    parser.add_argument("--clean", action="store_true",
                        help="empty the scene first (drops Blender's startup cube)")
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--save-blend", help="save the scene here when done")
    return parser.parse_args(argv)


def load_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".obj":
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=path, forward_axis="Y", up_axis="Z")
        else:
            bpy.ops.import_scene.obj(filepath=path, axis_forward="Y", axis_up="Z")
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path, global_scale=1.0)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".dae":
        bpy.ops.wm.collada_import(filepath=path)
    else:
        raise SystemExit("cannot import %s (use .obj/.fbx/.glb/.dae or a .blend)" % ext)


def chosen_objects(names):
    if names:
        picked = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj is None or obj.type != "MESH":
                raise SystemExit("no mesh object named %r" % name)
            picked.append(obj)
        return picked
    selected = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if selected:
        return selected
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parse_args(argv)
    result = {"written": [], "warnings": []}

    if args.clean:
        bpy.ops.wm.read_factory_settings(use_empty=True)

    if args.base_body:
        obj, verts, faces = add_base_body(args.base_body, args.cache)
        result["baseBody"] = {"object": obj.name, "vertices": verts, "polygons": faces}
    elif args.load:
        load_file(args.load)

    if args.out and args.morph:
        objects = chosen_objects(args.objects)
        if len(objects) != 1:
            raise SystemExit("a morph is one sculpted copy of the base body, got %d objects"
                             % len(objects))
        deltas, total, ignored = morph_deltas(objects[0], args.gender, args.cache,
                                              args.threshold, not args.no_modifiers)
        if ignored:
            result["warnings"].append(
                "%d moved vertices are on the genital graft, which a Genesis 2 morph "
                "cannot address; they were dropped" % ignored)
        if not deltas:
            raise SystemExit("%s is identical to the base body (nothing moved more "
                             "than %g m)" % (objects[0].name, args.threshold))
        doc = vd.build_morph_dsf(args.morph, deltas, gender=args.gender,
                                 group=args.morph_group, label=args.morph,
                                 minimum=args.morph_min, maximum=args.morph_max,
                                 author=args.author, space="blender")
        vd.write_dson(args.out, doc, compress=not args.plain)
        biggest = max(float(np.linalg.norm(d)) for d in deltas.values())
        result["written"].append({"path": args.out, "name": args.morph,
                                  "objects": [objects[0].name], "kind": "morph",
                                  "deltas": len(deltas), "vertices": total,
                                  "largestMove": round(biggest, 5),
                                  "gender": args.gender, "group": args.morph_group})
    elif args.out:
        objects = chosen_objects(args.objects)
        if not objects:
            raise SystemExit("no mesh objects to export")
        groups = ([([obj], sanitize(args.name or obj.name)) for obj in objects]
                  if args.separate else
                  [(objects, sanitize(args.name or objects[0].name))])
        root, ext = os.path.splitext(args.out)
        for index, (members, name) in enumerate(groups):
            parts = combine(members, use_modifiers=not args.no_modifiers)
            mesh = to_duf_mesh(name, parts)
            doc = vd.build_duf(mesh, asset_id="/%s.duf" % name, author=args.author)
            warnings = vd.check_duf(doc)
            if parts["ngons"]:
                warnings.append("%s: triangulated %d n-gons (DSON has quads at most)"
                                % (name, parts["ngons"]))
            path = args.out if len(groups) == 1 else "%s_%s%s" % (root, name, ext or ".duf")
            vd.write_dson(path, doc, compress=not args.plain)
            result["written"].append({
                "path": path, "name": name,
                "objects": [o.name for o in members],
                "vertices": len(mesh.verts), "polygons": len(mesh.faces),
                "materials": mesh.material_names,
                "uvs": mesh.uvs is not None and len(mesh.uvs) or 0,
                "seamUVs": len(mesh.uv_pairs),
            })
            result["warnings"].extend(warnings)
            del index

    if args.save_blend:
        directory = os.path.dirname(os.path.abspath(args.save_blend))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        bpy.ops.wm.save_as_mainfile(filepath=args.save_blend)
        result["blend"] = args.save_blend

    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
