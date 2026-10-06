"""Vindictus World Partition level -> what is where, from the CUE4Parse JSON of every cell (exported with
vdf53_patched.usmap), the JSON of the blueprint packages the cells use as component templates, and the cells' raw
bytes (instance matrices of HISM / foliage components are native data CUE4Parse leaves out).

  python level_extract.py <cells json root> <templates json root> <out.json>

Output (UE world space: cm, left-handed, Z up; 4x4 row-major for row vectors v' = v * M, translation m[12:15]):
  items:      [{"mesh": "/Game/.../SM_x", "m": [16], "kind": "smc|ism|foliage|spline", "actor": class, "cell": id}]
              spline items also carry "spline": [start, start tangent, end, end tangent] (component local) and
              "axis" (ForwardAxis 0/1/2)
  landscape:  one entry per LandscapeComponent (proxy root matrix, section base, sizes, height / weight maps)
  skipped:    counts of components without a mesh or a resolvable template, per class"""
import collections
import glob
import json
import math
import os
import re
import struct
import sys

import zen53

CELLS_ROOT, TPL_ROOT, OUT = sys.argv[1:4]
INSTANCED = ("InstancedStaticMeshComponent", "HierarchicalInstancedStaticMeshComponent",
             "FoliageInstancedStaticMeshComponent")
MESHY = ("StaticMeshComponent", "SplineMeshComponent") + INSTANCED


def load(path):
    return json.load(open(path, encoding="utf-8-sig"))


def game_path(json_path, root):
    """.../Vindictus/Content/X/Y.json -> /Game/X/Y"""
    rel = os.path.relpath(json_path, root).replace(os.sep, "/")
    rel = re.sub(r"^Vindictus/Content/", "", rel)
    return "/Game/" + rel[:-len(".json")]


# ------------------------------------------------------------------ all objects, keyed by (package, export index)
objs = {}
cells = {}
for f in sorted(glob.glob(os.path.join(CELLS_ROOT, "**", "*.json"), recursive=True)):
    pkg = game_path(f, CELLS_ROOT)
    cells[pkg] = load(f)
    for i, x in enumerate(cells[pkg]):
        objs[(pkg.lower(), i)] = x
templates = {}
for f in sorted(glob.glob(os.path.join(TPL_ROOT, "**", "*.json"), recursive=True)):
    pkg = game_path(f, TPL_ROOT)
    for i, x in enumerate(load(f)):
        objs[(pkg.lower(), i)] = x
        templates[pkg] = True


def ref(r):
    """{"ObjectName", "ObjectPath": "/Game/a/b.N"} -> (package lower-cased - paths differ in case, N)"""
    if not r or not isinstance(r, dict) or "ObjectPath" not in r:
        return None
    pkg, _, idx = r["ObjectPath"].rpartition(".")
    return (pkg.lower(), int(idx)) if idx.isdigit() else None


def mesh_path(r):
    if not r or not isinstance(r, dict) or "ObjectPath" not in r:
        return None
    return r["ObjectPath"].rpartition(".")[0]


MISSING = object()


def prop(x, name, depth=0):
    """A property of an export, or its template's (= its archetype) when the export does not carry it."""
    p = x.get("Properties") or {}
    if name in p:
        return p[name]
    t = ref(x.get("Template"))
    if t and depth < 8:
        if t in objs:
            return prop(objs[t], name, depth + 1)
        return MISSING
    return None


# ------------------------------------------------------------------ transforms (UE conventions)
def rot_matrix(pitch, yaw, roll):
    p, y, r = (math.radians(v) for v in (pitch, yaw, roll))
    sp, cp, sy, cy, sr, cr = math.sin(p), math.cos(p), math.sin(y), math.cos(y), math.sin(r), math.cos(r)
    return [[cp * cy, cp * sy, sp],
            [sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp],
            [-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp]]


def quat_matrix(x, y, z, w):
    x2, y2, z2 = x + x, y + y, z + z
    xx, xy, xz, yy, yz, zz = x * x2, x * y2, x * z2, y * y2, y * z2, z * z2
    wx, wy, wz = w * x2, w * y2, w * z2
    return [[1 - (yy + zz), xy + wz, xz - wy],
            [xy - wz, 1 - (xx + zz), yz + wx],
            [xz + wy, yz - wx, 1 - (xx + yy)]]


def compose(r3, s, t):
    return [r3[0][0] * s[0], r3[0][1] * s[0], r3[0][2] * s[0], 0.0,
            r3[1][0] * s[1], r3[1][1] * s[1], r3[1][2] * s[1], 0.0,
            r3[2][0] * s[2], r3[2][1] * s[2], r3[2][2] * s[2], 0.0,
            t[0], t[1], t[2], 1.0]


def mul(a, b):
    """a * b (row vectors: first a, then b)"""
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]


IDENT = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def vec(v, default):
    if not isinstance(v, dict):
        return default
    return (v.get("X", 0.0), v.get("Y", 0.0), v.get("Z", 0.0))


def local_matrix(x):
    loc = vec(prop(x, "RelativeLocation"), (0.0, 0.0, 0.0))
    rot = prop(x, "RelativeRotation")
    rot = (rot.get("Pitch", 0.0), rot.get("Yaw", 0.0), rot.get("Roll", 0.0)) if isinstance(rot, dict) else (0, 0, 0)
    scale = vec(prop(x, "RelativeScale3D"), (1.0, 1.0, 1.0))
    return compose(rot_matrix(*rot), scale, loc)


_world = {}


def world_matrix(key, depth=0):
    if key in _world:
        return _world[key]
    x = objs[key]
    m = local_matrix(x)
    parent = ref(prop(x, "AttachParent"))
    if parent and parent in objs and depth < 32:
        m = mul(m, world_matrix(parent, depth + 1))
    _world[key] = m
    return m


# ------------------------------------------------------------------ native instance matrices
_raw = {}


def raw_export(pkg, idx):
    if pkg not in _raw:
        container = "Vindictus/Content/" + pkg[len("/Game/"):] + ".umap"
        buf = zen53.read_package(container)
        _raw[pkg] = (buf, zen53.parse(buf))
    buf, parsed = _raw[pkg]
    e = parsed["exports"][idx]
    return buf[e["data_offset"]:e["data_offset"] + e["size"]]


def native_instances(data):
    """The first int32 128 + int32 n + n row-major FMatrix (doubles) with a (0,0,0,1) last column."""
    hdr, p = zen53.unversioned_header(data)
    while True:
        p = data.find(b"\x80\x00\x00\x00", p)
        if p < 0 or p + 8 > len(data):
            return []
        n, = struct.unpack_from("<i", data, p + 4)
        if 0 < n and p + 8 + n * 128 <= len(data):
            mats = [list(struct.unpack_from("<16d", data, p + 8 + k * 128)) for k in range(n)]
            if all(abs(m[3]) < 1e-6 and abs(m[7]) < 1e-6 and abs(m[11]) < 1e-6 and abs(m[15] - 1) < 1e-6
                   for m in mats[:8]):
                return mats
        p += 1


def json_instances(x):
    out = []
    for d in x.get("PerInstanceSMData") or []:
        t = d.get("TransformData", d)
        q = t["Rotation"]
        out.append(compose(quat_matrix(q["X"], q["Y"], q["Z"], q["W"]), vec(t.get("Scale3D"), (1, 1, 1)),
                           vec(t.get("Translation"), (0, 0, 0))))
    return out


# ------------------------------------------------------------------ walk
items, landscape = [], []
skipped = collections.Counter()
roots_of = {}       # actor (pkg, idx) -> root SceneComponent key
for pkg, exports in cells.items():
    for i, x in enumerate(exports):
        if x["Type"] == "SceneComponent" or x["Name"] in ("RootComponent0", "DefaultSceneRoot", "Root"):
            o = ref(x.get("Outer"))
            if o and not prop(x, "AttachParent"):
                roots_of.setdefault(o, (pkg.lower(), i))

for pkg, exports in cells.items():
    cell = pkg.rsplit("/", 1)[-1]
    for i, x in enumerate(exports):
        t = x["Type"]
        actor = objs.get(ref(x.get("Outer")), {}).get("Type", "?")
        if t == "LandscapeComponent":
            p = x["Properties"]
            proxy = ref(x.get("Outer"))
            root = roots_of.get(proxy)
            m = local_matrix(x)
            if root:
                m = mul(m, world_matrix(root))
            hm = p.get("HeightmapTexture")
            landscape.append({
                "cell": cell, "name": x["Name"], "m": m, "section": [p.get("SectionBaseX", 0), p.get("SectionBaseY", 0)],
                "size": p.get("ComponentSizeQuads", 126), "sub": p.get("SubsectionSizeQuads", 63),
                "nsub": p.get("NumSubsections", 2),
                "heightmap": hm and hm["ObjectName"].split(".")[-1].rstrip("'"),
                "hsb": [p["HeightmapScaleBias"][k] for k in "XYZW"],
                "wsb": [p.get("WeightmapScaleBias", {}).get(k, 0) for k in "XYZW"],
                "weightmaps": [w["ObjectName"].split(".")[-1].rstrip("'") for w in p.get("WeightmapTextures", [])],
                "layers": [{"layer": a["LayerInfo"]["ObjectPath"].rsplit("/", 1)[-1].split(".")[0] if a.get("LayerInfo") else None,
                            "tex": a.get("WeightmapTextureIndex", 0), "ch": a.get("WeightmapTextureChannel", 0)}
                           for a in p.get("WeightmapLayerAllocations", [])],
                "material": (p.get("MaterialInstances") or [{}])[0].get("ObjectName", "")})
            continue
        if t not in MESHY:
            continue
        mesh = prop(x, "StaticMesh")
        if mesh is MISSING:
            skipped[(t, "template not exported")] += 1
            continue
        mesh = mesh_path(mesh)
        if not mesh:
            skipped[(t, "no mesh")] += 1
            continue
        try:
            wm = world_matrix((pkg.lower(), i))
        except Exception as exc:                      # noqa: BLE001
            skipped[(t, "transform: %s" % exc)] += 1
            continue
        base = {"mesh": mesh, "actor": actor, "cell": cell}
        if t in INSTANCED:
            inst = json_instances(x) or native_instances(raw_export(pkg, i))
            if not inst:
                skipped[(t, "no instances")] += 1
            kind = "foliage" if t.startswith("Foliage") else "ism"
            for im in inst:
                items.append(dict(base, kind=kind, m=mul(im, wm)))
        elif t == "SplineMeshComponent":
            sp = prop(x, "SplineParams") or {}
            items.append(dict(base, kind="spline", m=wm, axis={"ESplineMeshAxis::X": 0, "ESplineMeshAxis::Y": 1,
                                                               "ESplineMeshAxis::Z": 2}.get(prop(x, "ForwardAxis"), 0),
                              spline=[vec(sp.get(k), (0, 0, 0)) for k in ("StartPos", "StartTangent", "EndPos",
                                                                           "EndTangent")]))
        else:
            items.append(dict(base, kind="smc", m=wm))

json.dump({"items": items, "landscape": landscape,
           "skipped": {"%s / %s" % k: v for k, v in skipped.items()}}, open(OUT, "w", encoding="utf-8"))
kinds = collections.Counter(it["kind"] for it in items)
print("%d items %s, %d landscape components, %d meshes" % (len(items), dict(kinds), len(landscape),
                                                          len({it["mesh"] for it in items})))
for k, v in sorted(skipped.items(), key=lambda kv: -kv[1]):
    print("  skipped %-60s %d" % ("%s / %s" % k, v))
