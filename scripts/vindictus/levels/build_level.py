"""Blender 3.6: a region of a Vindictus level as a .blend, from level_extract.py's placements and UE Viewer's export
(PSKX meshes, .mat / .props.txt materials, PNG textures, landscape height / weight maps).

  blender -b --python build_level.py -- --placements placements.json --assets <umodel out dir>
      --center X,Y --radius R [--far R2] [--foliage-radius R3] [--no-foliage] [--no-landscape]
      --out scene.blend [--views dir]

Units: UE cm, left-handed -> Blender m, right-handed.  UE Viewer writes PSK meshes mirrored in Y already, so a UE
placement M (row vectors, v' = v * M) becomes F M^T F (F = diag(1, -1, 1)) with the translation / 100 and an extra
uniform 1/100 on the object (the mesh data stays in cm).
- radius: everything whose bounds reach into the circle; far: also anything bigger than 20 m within this distance
  (cliffs / mountains on the horizon); foliage-radius: grass / bushes / small stones (instanced, geometry nodes);
- materials: base colour / normal (DirectX, green flipped) / ORM (R AO, G roughness, B metallic) from the material
  instance's texture parameters, else UE Viewer's .mat; Megascans plants clip on the base colour alpha;
- landscape: every component as a 127 x 127 grid from its heightmap (R * 256 + G, (h - 32768) / 128 * scale z),
  layer weights from the weightmaps -> one image per layer over the whole landscape (1 px per quad)."""
import argparse
import collections
import json
import math
import os
import re
import struct
import sys
import time

import bpy
import addon_utils
import numpy as np
from mathutils import Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--placements", required=True)
ap.add_argument("--assets", required=True)
ap.add_argument("--center", required=True)
ap.add_argument("--radius", type=float, default=15000.0)
ap.add_argument("--far", type=float, default=0.0)
ap.add_argument("--foliage-radius", type=float, default=6000.0)
ap.add_argument("--no-foliage", action="store_true")
ap.add_argument("--no-landscape", action="store_true")
ap.add_argument("--out", required=True)
ap.add_argument("--views", default="")
ap.add_argument("--sun-elev", type=float, default=38.0)
ap.add_argument("--sun-rot", type=float, default=150.0)
ap.add_argument("--grass", default="", help="x,y,dir,r_full,r_max[,clear] - landscape grass around a spot (UE cm)")
ap.add_argument("--grass-types", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "grass_types.json"))
ap.add_argument("--grass-density", type=float, default=1.0)
ap.add_argument("--sky-hdr", default="kloofendal_48d_partly_cloudy_puresky_4k",
                help="texture stem of the sky panorama ('' = Nishita sky); --sun-elev < 0 takes the panorama's sun")
ap.add_argument("--sky-strength", type=float, default=1.0)
ap.add_argument("--sun-energy", type=float, default=4.0)
ap.add_argument("--haze", type=float, default=0.0, help="aerial perspective distance (m); 0 = off")
ap.add_argument("--haze-cap", type=float, default=0.8)
ap.add_argument("--haze-color", default="0.44,0.47,0.57", help="the sky panorama at the horizon")
args = ap.parse_args(argv)
CX, CY = (float(v) for v in args.center.split(","))
T0 = time.time()


def log(msg):
    print("[level %6.1fs] %s" % (time.time() - T0, msg), flush=True)


bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("io_scene_psk_psa", default_set=False)
from io_scene_psk_psa.psk.reader import read_psk          # noqa: E402
from io_scene_psk_psa.psk.importer import import_psk, PskImportOptions   # noqa: E402

scene = bpy.context.scene
D = json.load(open(args.placements, encoding="utf-8"))

# ------------------------------------------------------------------ asset index
FILES = collections.defaultdict(dict)        # ext -> stem(lower) -> path
for dp, _dirs, files in os.walk(args.assets):
    for f in files:
        low = f.lower()
        for ext in (".pskx", ".psk", ".png", ".tga", ".hdr", ".mat", ".props.txt"):
            if low.endswith(ext):
                FILES[ext].setdefault(low[:-len(ext)], os.path.join(dp, f))
                break
MESH_FILE = {}
for dp, _dirs, files in os.walk(args.assets):
    for f in files:
        if f.lower().endswith((".pskx", ".psk")):
            rel = os.path.relpath(os.path.join(dp, f), args.assets).replace(os.sep, "/")
            MESH_FILE["/game/" + rel.rsplit(".", 1)[0].lower()] = os.path.join(dp, f)
log("index: %d meshes, %d png, %d props" % (len(MESH_FILE), len(FILES[".png"]), len(FILES[".props.txt"])))


def psk_bounds(path, cache={}):
    """(min xyz, max xyz) of the PNTS chunk, cm, PSK (Y-mirrored) space."""
    if path not in cache:
        data = open(path, "rb").read()
        o = 0
        while o < len(data):
            cid = data[o:o + 20].split(b"\0")[0]
            size, count = struct.unpack_from("<ii", data, o + 24)
            if cid == b"PNTS0000":
                pts = np.frombuffer(data, dtype="<f4", count=count * 3, offset=o + 32).reshape(-1, 3)
                cache[path] = (pts.min(0), pts.max(0))
                break
            o += 32 + size * count
        else:
            cache[path] = (np.zeros(3), np.zeros(3))
    return cache[path]


# ------------------------------------------------------------------ select
F = Matrix(((1, 0, 0), (0, -1, 0), (0, 0, 1)))


def to_blender(m):
    """UE row-major 16 (row vectors) -> Blender 4x4 (m, mesh data in cm)."""
    r = Matrix(((m[0], m[4], m[8]), (m[1], m[5], m[9]), (m[2], m[6], m[10])))     # transpose: column vectors
    r = F @ r @ F
    out = (r * 0.01).to_4x4()
    out.translation = (m[12] * 0.01, -m[13] * 0.01, m[14] * 0.01)
    return out


def max_scale(m):
    return max(math.sqrt(m[r * 4] ** 2 + m[r * 4 + 1] ** 2 + m[r * 4 + 2] ** 2) for r in range(3))


# editor helpers, fog cards (translucent sheets), sky domes (the world shader is the sky here), water planes
EXCLUDE = re.compile(r"SkyDome|FogCard|FogSheet|/Cube$|/Sphere$|SM_Cylinder$|SM_Sphere$|WaterPlane|Dummy", re.I)
picked = []
missing = collections.Counter()
for it in D["items"]:
    if EXCLUDE.search(it["mesh"]):
        continue
    path = MESH_FILE.get(it["mesh"].lower())
    if path is None:
        missing[it["mesh"]] += 1
        continue
    x, y = it["m"][12], it["m"][13]
    dist = math.hypot(x - CX, y - CY)
    if it["kind"] == "foliage":
        lo, hi = psk_bounds(path)
        size = float(np.linalg.norm(hi - lo)) * 0.5 * max_scale(it["m"])
        if args.no_foliage or dist > args.foliage_radius + (size if size > 500 else 0):
            continue
        picked.append((it, path))
        continue
    lo, hi = psk_bounds(path)
    size = float(np.linalg.norm(hi - lo)) * 0.5 * max_scale(it["m"])
    if dist - size <= args.radius or (args.far and size > 2000 and dist - size <= args.far):
        picked.append((it, path))
log("picked %d of %d items (%s); meshes missing from the export: %d" % (
    len(picked), len(D["items"]), dict(collections.Counter(it["kind"] for it, _p in picked)), len(missing)))
for name, n in missing.most_common(8):
    log("  missing %s x%d" % (name, n))


# ------------------------------------------------------------------ materials
def read_props(name):
    out = {"parent": "", "textures": {}, "scalars": {}, "vectors": {}, "blend": ""}
    path = FILES[".props.txt"].get(name.lower())
    if not path:
        return out
    text = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"^Parent = (.*)$", text, re.M)
    out["parent"] = m.group(1).strip() if m else ""
    for m in re.finditer(r"ParameterInfo = \{ Name=(?P<n>[^}]*?) \}\s*ParameterValue = (?P<v>[^\n]*)", text):
        n, v = m.group("n").strip(), m.group("v").strip()
        if v.startswith("Texture2D"):
            out["textures"][n] = v.rsplit(".", 1)[-1].rstrip("'")
        elif v.startswith("{"):
            out["vectors"][n] = tuple(float(x) for x in re.findall(r"[RGBA]=([-\d.eE+]+)", v))
        else:
            try:
                out["scalars"][n] = float(v)
            except ValueError:
                pass
    m = re.search(r"BlendMode = (\w+)", text)
    out["blend"] = m.group(1) if m else ""
    return out


def read_mat(name):
    out = {"others": []}
    path = FILES[".mat"].get(name.lower())
    if path:
        for line in open(path, encoding="utf-8", errors="replace"):
            if "=" in line:
                k, v = line.strip().split("=", 1)
                if k.startswith("Other["):
                    out["others"].append(v)
                else:
                    out[k] = v
    return out


def tex(stem):
    """PNG / TGA, or HDR (UE Viewer writes BC6H textures as float .hdr - linear already)"""
    key = (stem or "").lower()
    return FILES[".png"].get(key) or FILES[".tga"].get(key) or FILES[".hdr"].get(key)


ROLE_PARAM = {
    "base": re.compile(r"albedo|base ?colou?r|diffuse|^colou?r$|basemap|^bc$|^d$", re.I),
    "normal": re.compile(r"normal", re.I),
    "orm": re.compile(r"^orm|^arm|^rma|^mra|packed|^mask$|occlusion.?roughness", re.I),
    "rough": re.compile(r"rough", re.I),
    "opacity": re.compile(r"opacity|alpha", re.I),
}
ROLE_SUFFIX = {
    "base": re.compile(r"_(d|bc|basecolor|albedo|diffuse|col|color)$", re.I),
    "normal": re.compile(r"_(n|normal|nrm)$", re.I),
    "orm": re.compile(r"_(orm|arm|rma|mra|dpr|ordp|ord|mask|m)$", re.I),
}
_images = {}


def image(path, non_color):
    key = (path, non_color)
    if key not in _images:
        img = bpy.data.images.load(path, check_existing=True)
        if non_color:
            img.colorspace_settings.name = "Non-Color"
        _images[key] = img
    return _images[key]


def material_roles(name):
    props, mat = read_props(name), read_mat(name)
    roles = {}
    for pname, stem in props["textures"].items():
        for role, rx in ROLE_PARAM.items():
            if role not in roles and rx.search(pname) and tex(stem):
                roles[role] = tex(stem)
                break
    # foliage packs: ORT / ART (R opacity, G roughness, B translucency); SpeedTree-style MAI_*: Mask (R opacity)
    for pname, stem in props["textures"].items():
        if pname in ("ORT", "Mask") and tex(stem):
            roles["opacity_tex"] = tex(stem)
            if pname == "ORT":
                roles["orm"] = tex(stem)
    # Megascans-preset cliffs without their own albedo: the tiling "BlendingBasecolor" is the colour
    blend_base = props["textures"].get("BlendingBasecolor")
    if "base" not in roles and blend_base and tex(blend_base):
        roles["base"] = tex(blend_base)
        roles["blending_base"] = True
    stems = [mat.get("Diffuse"), mat.get("Normal"), mat.get("Specular"), mat.get("Opacity")] + \
        list(props["textures"].values()) + mat["others"]
    for role, rx in ROLE_SUFFIX.items():
        if role not in roles:
            for stem in stems:
                if stem and rx.search(stem) and tex(stem) and "placeholder" not in stem.lower() \
                        and not stem.lower().startswith(("t_moss", "t_cliffmoss", "t_snow", "t_grunge", "t_water")):
                    roles[role] = tex(stem)
                    break
    if "base" not in roles and mat.get("Diffuse") and tex(mat["Diffuse"]) \
            and not mat["Diffuse"].lower().startswith(("t_cliffmoss", "t_moss")):
        roles["base"] = tex(mat["Diffuse"])
    if "normal" not in roles and mat.get("Normal") and tex(mat["Normal"]) and "placeholder" not in mat["Normal"].lower():
        roles["normal"] = tex(mat["Normal"])
    return roles, props


MOSS = {}


def moss_maps():
    """the Megascans-preset parent's own moss (T_Moss01A_D): game cliffs carry it on their up-facing sides"""
    if not MOSS and tex("T_Moss01A_D"):
        MOSS["T_Moss01A_D"] = tex("T_Moss01A_D")
    return MOSS


HAZE = tuple(float(v) for v in args.haze_color.split(","))


def add_haze(nt, bsdf):
    """aerial perspective without a volume (the game has exponential height fog): with the view distance d the base
    colour fades by f = cap * (1 - exp(-d / haze)) and the horizon colour comes in as emission - alpha untouched, so
    clipped plants keep their cut-outs"""
    if args.haze <= 0:
        return
    L = nt.links.new
    base_in = bsdf.inputs["Base Color"]
    src = base_in.links[0].from_socket if base_in.is_linked else None
    cam = nt.nodes.new("ShaderNodeCameraData")
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = -1.0 / args.haze
    L(cam.outputs["View Distance"], k.inputs[0])
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    L(k.outputs[0], ex.inputs[0])
    f = nt.nodes.new("ShaderNodeMath")
    f.operation = "MULTIPLY_ADD"                      # cap * (1 - e) = e * -cap + cap
    f.inputs[1].default_value = -args.haze_cap
    f.inputs[2].default_value = args.haze_cap
    L(ex.outputs[0], f.inputs[0])
    keep = nt.nodes.new("ShaderNodeMixRGB")
    L(f.outputs[0], keep.inputs[0])
    if src is not None:
        L(src, keep.inputs[1])
    else:
        keep.inputs[1].default_value = tuple(base_in.default_value)
    keep.inputs[2].default_value = (0.0, 0.0, 0.0, 1.0)
    L(keep.outputs[0], base_in)
    em = nt.nodes.new("ShaderNodeMixRGB")
    L(f.outputs[0], em.inputs[0])
    em.inputs[1].default_value = (0.0, 0.0, 0.0, 1.0)
    em.inputs[2].default_value = HAZE + (1.0,)
    L(em.outputs[0], bsdf.inputs["Emission"])
    bsdf.inputs["Emission Strength"].default_value = 1.0


def color_controls(props):
    """(tint RGBA, controls) of a material instance; two-sided tree presets carry their own *Leaves pair (their
    plain Albedo Tint is a trunk value like (1, 0, 0.78) that would turn the leaves magenta)"""
    vec = props["vectors"]
    if "Albedo Tint Leaves" in vec or "Albedo Controls Leaves" in vec:
        return vec.get("Albedo Tint Leaves"), vec.get("Albedo Controls Leaves")
    tint = vec.get("Albedo Tint") or vec.get("Tint") or vec.get("Color_Tint")
    return tint, vec.get("Albedo Controls") or vec.get("Color_Control")


def setup_material(material, foliage=False):
    name = re.sub(r"\.\d{3}$", "", material.name)
    roles, props = material_roles(name)
    material.use_nodes = True
    nt = material.node_tree
    nt.nodes.clear()
    L = nt.links.new
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (-300, 0)
    out.location = (100, 0)
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Specular"].default_value = 0.3
    bsdf.inputs["Roughness"].default_value = 0.85
    parent = props["parent"].lower()
    plant = foliage or "foliage" in parent or "/mai_" in parent or "opacity_tex" in roles
    col = None
    if "base" in roles:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = image(roles["base"], False)
        t.location = (-1100, 300)
        col = t.outputs["Color"]
        if roles.get("blending_base"):
            # a lichen-rock tiling map that the game turns into grey rock with the preset's albedo controls
            hsv = nt.nodes.new("ShaderNodeHueSaturation")
            hsv.inputs["Saturation"].default_value = 0.3
            hsv.inputs["Value"].default_value = 0.75
            L(col, hsv.inputs["Color"])
            col = hsv.outputs["Color"]
        tint, ctrl = color_controls(props)
        # tint: Color_Tint's A is the amount (0.2 / 0.3 / 0 in the foliage presets); Albedo Tint has A = 1
        amount = tint[3] if tint and len(tint) > 3 and 0.0 <= tint[3] < 0.999 else 1.0
        if tint and amount > 0.001 and any(abs(c - 1) > 0.01 for c in tint[:3]):
            mix = nt.nodes.new("ShaderNodeMixRGB")
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = amount
            mix.inputs[2].default_value = tuple(tint[:3]) + (1.0,)
            L(col, mix.inputs[1])
            col = mix.outputs[0]
        # Albedo Controls / Color_Control = (brightness, saturation, contrast): the game darkens most rocks with it
        # (the overhanging slab 0.4, castle walls 0.55); the preset cliffs keep their own grey (saturation 3 there
        # works on a map we do not have)
        if ctrl and (abs(ctrl[0] - 1) > 0.01 or abs(ctrl[1] - 1) > 0.01):
            hsv = nt.nodes.new("ShaderNodeHueSaturation")
            hsv.inputs["Value"].default_value = max(0.05, ctrl[0])
            hsv.inputs["Saturation"].default_value = 1.0 if roles.get("blending_base") else max(0.0, min(1.5, ctrl[1]))
            # (capped at 1.5: River Saltbush asks for 3 - neon lime under the Standard view; UE's filmic tonemapper
            # tames such colours, ours does not)
            L(col, hsv.inputs["Color"])
            col = hsv.outputs["Color"]
        if plant and "opacity_tex" not in roles:
            L(t.outputs["Alpha"], bsdf.inputs["Alpha"])
    else:
        bsdf.inputs["Base Color"].default_value = (0.35, 0.33, 0.3, 1)
    if plant:
        if "opacity_tex" in roles:
            o = nt.nodes.new("ShaderNodeTexImage")
            o.image = image(roles["opacity_tex"], True)
            o.location = (-1100, -650)
            sep = nt.nodes.new("ShaderNodeSeparateRGB")
            L(o.outputs["Color"], sep.inputs[0])
            L(sep.outputs["R"], bsdf.inputs["Alpha"])
        material.blend_method = "CLIP"
        material.shadow_method = "CLIP"
        material.alpha_threshold = 0.4
        material.use_backface_culling = False
        bsdf.inputs["Specular"].default_value = 0.2
    # moss on the up-facing sides of the preset rocks (MossBlend > 0)
    moss = props["scalars"].get("MossBlend", 0.0)
    if col is not None and moss > 0 and moss_maps().get("T_Moss01A_D"):
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sxyz = nt.nodes.new("ShaderNodeSeparateXYZ")
        L(geo.outputs["Normal"], sxyz.inputs[0])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = 0.55
        mr.inputs["From Max"].default_value = 0.85
        mr.inputs["To Max"].default_value = min(1.0, moss / 2.6)
        L(sxyz.outputs["Z"], mr.inputs["Value"])
        mt = nt.nodes.new("ShaderNodeTexImage")
        mt.image = image(moss_maps()["T_Moss01A_D"], False)
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sc = nt.nodes.new("ShaderNodeVectorMath")
        sc.operation = "SCALE"
        sc.inputs["Scale"].default_value = 1.0 / 250.0         # object space is cm: one tile per 2.5 m
        L(tc.outputs["Object"], sc.inputs[0])
        L(sc.outputs[0], mt.inputs["Vector"])
        mix = nt.nodes.new("ShaderNodeMixRGB")
        L(mr.outputs["Result"], mix.inputs[0])
        L(col, mix.inputs[1])
        L(mt.outputs["Color"], mix.inputs[2])
        col = mix.outputs[0]
    if col is not None:
        L(col, bsdf.inputs["Base Color"])
    if "normal" in roles:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = image(roles["normal"], True)
        t.location = (-1100, -300)
        sep = nt.nodes.new("ShaderNodeSeparateRGB")
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        comb = nt.nodes.new("ShaderNodeCombineRGB")
        nm = nt.nodes.new("ShaderNodeNormalMap")
        for n, x in ((sep, -800), (inv, -650), (comb, -500), (nm, -400)):
            n.location = (x, -300)
        L(t.outputs["Color"], sep.inputs[0])
        L(sep.outputs["R"], comb.inputs["R"])
        L(sep.outputs["G"], inv.inputs[1])
        L(inv.outputs[0], comb.inputs["G"])
        L(sep.outputs["B"], comb.inputs["B"])
        L(comb.outputs[0], nm.inputs["Color"])
        L(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if "orm" in roles:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = image(roles["orm"], True)
        t.location = (-900, 0)
        sep = nt.nodes.new("ShaderNodeSeparateRGB")
        sep.location = (-600, 0)
        L(t.outputs["Color"], sep.inputs[0])
        L(sep.outputs["G"], bsdf.inputs["Roughness"])
    elif "rough" in roles:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = image(roles["rough"], True)
        t.location = (-900, 0)
        L(t.outputs["Color"], bsdf.inputs["Roughness"])
    add_haze(nt, bsdf)
    return roles


# ------------------------------------------------------------------ meshes
src_coll = bpy.data.collections.new("VDF_sources")
scene.collection.children.link(src_coll)
src_coll.hide_render = True
src_coll.hide_viewport = True
sources = {}          # psk path -> object (mesh data in cm)
_mat_done = set()


def source(path, foliage):
    if path in sources:
        return sources[path]
    psk = read_psk(path)
    opt = PskImportOptions()
    opt.name = os.path.splitext(os.path.basename(path))[0]
    opt.should_import_skeleton = False
    opt.should_import_vertex_colors = False
    opt.should_import_shape_keys = False
    before = set(bpy.data.objects)
    import_psk(psk, bpy.context, opt)
    obj = next(o for o in bpy.data.objects if o not in before and o.type == "MESH")
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    src_coll.objects.link(obj)
    obj.hide_render = True              # the mesh data is in cm at the origin: only its instances / copies show
    obj.hide_viewport = True
    for mat in obj.data.materials:
        if mat and mat.name not in _mat_done:
            _mat_done.add(mat.name)
            setup_material(mat, foliage)
    sources[path] = obj
    return obj


scene_coll = bpy.data.collections.new("VDF_level")
scene.collection.children.link(scene_coll)
coll = {}


def sub(name):
    if name not in coll:
        coll[name] = bpy.data.collections.new(name)
        scene_coll.children.link(coll[name])
    return coll[name]


def spline_local(it, path):
    """Straight stand-in for a spline mesh: the mesh's forward extent stretched from StartPos to EndPos."""
    (sx, sy, sz), _st, (ex, ey, ez), _et = it["spline"]
    lo, hi = psk_bounds(path)
    axis = it.get("axis", 0)
    length0 = max(float(hi[axis] - lo[axis]), 1e-3)
    d = np.array([ex - sx, ey - sy, ez - sz])
    L = float(np.linalg.norm(d))
    if L < 1e-3:
        return None
    d /= L
    up = np.array([0.0, 0.0, 1.0]) if abs(d[2]) < 0.95 else np.array([1.0, 0.0, 0.0])
    yv = np.cross(up, d)
    yv /= np.linalg.norm(yv)
    zv = np.cross(d, yv)
    rows = [None, None, None]
    rows[axis] = d * (L / length0)
    rows[(axis + 1) % 3] = yv
    rows[(axis + 2) % 3] = zv
    m = [rows[0][0], rows[0][1], rows[0][2], 0, rows[1][0], rows[1][1], rows[1][2], 0,
         rows[2][0], rows[2][1], rows[2][2], 0, 0, 0, 0, 1]
    # PSK bounds are Y-mirrored: UE min along the axis = psk lo except for Y (= -hi)
    start_off = float(lo[axis]) if axis != 1 else -float(hi[axis])
    shift = [0.0, 0.0, 0.0]
    shift[axis] = -start_off
    t = np.array(shift) @ np.array([m[0:3], m[4:7], m[8:11]]) + np.array([sx, sy, sz])
    m[12], m[13], m[14] = float(t[0]), float(t[1]), float(t[2])
    return m


def mul(a, b):
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]


instanced = collections.defaultdict(list)
n_obj = 0
for it, path in picked:
    if it["kind"] in ("foliage", "ism"):
        instanced[(path, it["kind"])].append(it["m"])
        continue
    src = source(path, False)
    m = it["m"]
    if it["kind"] == "spline":
        loc = spline_local(it, path)
        if loc is None:
            continue
        m = mul(loc, m)
    o = bpy.data.objects.new(src.name, src.data)
    o.matrix_world = to_blender(m)
    sub("smc" if it["kind"] == "smc" else "spline").objects.link(o)
    n_obj += 1
log("%d single objects, %d sources so far" % (n_obj, len(sources)))


def instancer_group():
    g = bpy.data.node_groups.get("VDF_Instancer")
    if g:
        return g
    g = bpy.data.node_groups.new("VDF_Instancer", "GeometryNodeTree")
    g.inputs.new("NodeSocketGeometry", "Geometry")
    g.inputs.new("NodeSocketObject", "Source")
    g.outputs.new("NodeSocketGeometry", "Geometry")
    n = g.nodes
    gi, go = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    info = n.new("GeometryNodeObjectInfo")
    info.transform_space = "ORIGINAL"
    iop = n.new("GeometryNodeInstanceOnPoints")
    rot, scl = n.new("GeometryNodeInputNamedAttribute"), n.new("GeometryNodeInputNamedAttribute")
    for a, nm in ((rot, "rot"), (scl, "scl")):
        a.data_type = "FLOAT_VECTOR"
        a.inputs["Name"].default_value = nm
    g.links.new(gi.outputs["Geometry"], iop.inputs["Points"])
    g.links.new(gi.outputs["Source"], info.inputs["Object"])
    g.links.new(info.outputs["Geometry"], iop.inputs["Instance"])
    g.links.new(rot.outputs["Attribute"], iop.inputs["Rotation"])
    g.links.new(scl.outputs["Attribute"], iop.inputs["Scale"])
    g.links.new(iop.outputs["Instances"], go.inputs["Geometry"])
    return g


for (path, kind), mats in instanced.items():
    src = source(path, kind == "foliage")
    pts, rots, scls = [], [], []
    for m in mats:
        loc, q, s = to_blender(m).decompose()
        e = q.to_euler("XYZ")
        pts.append(tuple(loc))
        rots.append((e.x, e.y, e.z))
        scls.append(tuple(s))
    me = bpy.data.meshes.new("%s_points" % src.name)
    me.from_pydata(pts, [], [])
    for nm, vals in (("rot", rots), ("scl", scls)):
        a = me.attributes.new(nm, "FLOAT_VECTOR", "POINT")
        a.data.foreach_set("vector", [c for v in vals for c in v])
    o = bpy.data.objects.new("%s_%s" % (src.name, kind), me)
    mod = o.modifiers.new("instances", "NODES")
    mod.node_group = instancer_group()
    ident = mod.node_group.inputs["Source"].identifier
    mod[ident] = src
    sub(kind).objects.link(o)
log("%d instanced meshes (%d instances), %d sources" % (len(instanced), sum(len(v) for v in instanced.values()),
                                                        len(sources)))


# ------------------------------------------------------------------ landscape
CELL_PNG = {}
for dp, _dirs, files in os.walk(args.assets):
    low = dp.replace(os.sep, "/").lower()
    if "/_generated_/" in low:
        cell = low.split("/_generated_/", 1)[1].split("/", 1)[0]
        for f in files:
            if f.lower().endswith((".png", ".tga")):
                CELL_PNG.setdefault((cell, f.lower().rsplit(".", 1)[0]), os.path.join(dp, f))


def find_png(cell, texname):
    return CELL_PNG.get((cell.lower(), texname.lower()))


def layer_prefix(name):
    """landscape layer info name -> the material instance's parameter prefix: 3_LayerInfo -> 3, Layer5_LayerInfo -> 5"""
    return re.sub(r"_LayerInfo$", "", name).replace("Layer", "")


def landscape_material(layer_names, mi_name="MI_Northruin_Landscape_01"):
    """Weight-blended layers of the landscape material instance (<n>BaseColor / <n>Normal / <n>ORMH, world-aligned
    tiling), rock (6*) on slopes steeper than ~45 deg."""
    props = read_props(mi_name)
    mat = bpy.data.materials.new("VDF_Landscape")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    L = nt.links.new
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Specular"].default_value = 0.3
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    tc = nt.nodes.new("ShaderNodeTexCoord")

    def math_node(op, a, b=None, vector=False):
        n = nt.nodes.new("ShaderNodeVectorMath" if vector else "ShaderNodeMath")
        n.operation = op
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v if not vector else (v, v, v)
            else:
                L(v, n.inputs[i])
        return n.outputs[0] if not vector or op not in ("DOT_PRODUCT", "LENGTH") else n.outputs[1]

    def scale(vec, s):
        n = nt.nodes.new("ShaderNodeVectorMath")
        n.operation = "SCALE"
        L(vec, n.inputs[0])
        if isinstance(s, (int, float)):
            n.inputs["Scale"].default_value = s
        else:
            L(s, n.inputs["Scale"])
        return n.outputs[0]

    def layer_maps(prefix, tile_m):
        uv = scale(tc.outputs["Object"], 1.0 / tile_m)
        maps = {}
        for role, non_color in (("BaseColor", False), ("Normal", True), ("ORMH", True)):
            path = tex(props["textures"].get(prefix + role, ""))
            if not path:
                continue
            t = nt.nodes.new("ShaderNodeTexImage")
            t.image = image(path, non_color)
            L(uv, t.inputs["Vector"])
            maps[role] = t.outputs["Color"]
        if "Normal" in maps:                                   # DirectX -> flip green
            sep = nt.nodes.new("ShaderNodeSeparateRGB")
            comb = nt.nodes.new("ShaderNodeCombineRGB")
            L(maps["Normal"], sep.inputs[0])
            L(sep.outputs["R"], comb.inputs["R"])
            L(math_node("SUBTRACT", 1.0, sep.outputs["G"]), comb.inputs["G"])
            L(sep.outputs["B"], comb.inputs["B"])
            maps["Normal"] = comb.outputs[0]
        if "ORMH" in maps:
            sep = nt.nodes.new("ShaderNodeSeparateRGB")
            L(maps["ORMH"], sep.inputs[0])
            maps["Rough"] = sep.outputs["G"]
            maps["AO"] = sep.outputs["R"]
        return maps

    def layer_color(prefix, maps):
        """<n>AlbedoTint / <n>AlbedoControls (brightness, saturation) and the layer's AO, deepened by <n>AO_Intensity
        (sand + grass 3): base * AO ^ (intensity / 2)"""
        col = maps["BaseColor"]
        vec, sca = props["vectors"], props["scalars"]
        tint = vec.get(prefix + "AlbedoTint")
        if tint and any(abs(c - 1) > 0.01 for c in tint[:3]):
            mix = nt.nodes.new("ShaderNodeMixRGB")
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = 1.0
            mix.inputs[2].default_value = tuple(tint[:3]) + (1.0,)
            L(col, mix.inputs[1])
            col = mix.outputs[0]
        ctrl = vec.get(prefix + "AlbedoControls")
        if ctrl and (abs(ctrl[0] - 1) > 0.01 or abs(ctrl[1] - 1) > 0.01):
            hsv = nt.nodes.new("ShaderNodeHueSaturation")
            hsv.inputs["Value"].default_value = max(0.05, ctrl[0])
            hsv.inputs["Saturation"].default_value = max(0.0, min(2.0, ctrl[1]))
            L(col, hsv.inputs["Color"])
            col = hsv.outputs["Color"]
        if "AO" in maps:
            ao = math_node("POWER", maps["AO"], 0.5 * sca.get(prefix + "AO_Intensity", 1.0))
            mix = nt.nodes.new("ShaderNodeMixRGB")
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = 1.0
            L(col, mix.inputs[1])
            L(ao, mix.inputs[2])
            col = mix.outputs[0]
        return col

    acc = {"BaseColor": None, "Normal": None, "Rough": None}
    wsum = None
    for nm in layer_names:
        prefix = layer_prefix(nm)
        maps = layer_maps(prefix, 4.0 / max(props["scalars"].get(prefix + "Tiling", 0.5) / 0.5, 0.1))
        if "BaseColor" not in maps:
            continue
        wimg = nt.nodes.new("ShaderNodeTexImage")
        wimg.image = bpy.data.images["LW_" + nm]
        wimg.interpolation = "Linear"
        wimg.extension = "EXTEND"
        L(tc.outputs["UV"], wimg.inputs["Vector"])
        w = math_node("MULTIPLY", wimg.outputs["Color"], 1.0)
        wsum = w if wsum is None else math_node("ADD", wsum, w)
        maps["BaseColor"] = layer_color(prefix, maps)
        for role in acc:
            if role not in maps:
                continue
            v = scale(maps[role], w) if role != "Rough" else math_node("MULTIPLY", maps[role], w)
            if acc[role] is None:
                acc[role] = v
            else:
                acc[role] = math_node("ADD", acc[role], v, vector=(role != "Rough"))
    # slope rock
    rock = layer_maps("6", 6.0)
    if "BaseColor" in rock:
        rock["BaseColor"] = layer_color("6", rock)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    L(geo.outputs["Normal"], sep.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.78
    mr.inputs["From Max"].default_value = 0.6
    L(sep.outputs["Z"], mr.inputs["Value"])
    slope = mr.outputs["Result"]

    def finish(role, socket):
        if socket is None:
            return None
        if role in rock:
            mix = nt.nodes.new("ShaderNodeMixRGB")
            L(slope, mix.inputs[0])
            if role == "Rough":
                L(socket, mix.inputs[1])
            else:
                L(socket, mix.inputs[1])
            L(rock[role], mix.inputs[2])
            return mix.outputs[0]
        return socket

    col = finish("BaseColor", acc["BaseColor"])
    if col is not None:
        L(col, bsdf.inputs["Base Color"])
    nrm = finish("Normal", acc["Normal"])
    if nrm is not None:
        nm_node = nt.nodes.new("ShaderNodeNormalMap")
        L(nrm, nm_node.inputs["Color"])
        L(nm_node.outputs["Normal"], bsdf.inputs["Normal"])
    rough = finish("Rough", acc["Rough"])
    if rough is not None:
        L(rough, bsdf.inputs["Roughness"])
    add_haze(nt, bsdf)
    return mat


def load_rgba(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return np.flipud(px.reshape(h, w, 4))          # row 0 = top (texture v = 0)


if not args.no_landscape and D["landscape"]:
    verts, faces, uvs = [], [], []
    layer_names = sorted({a["layer"] for comp in D["landscape"] for a in comp["layers"] if a["layer"]})
    total = max(max(c["section"][0], c["section"][1]) + c["size"] for c in D["landscape"])
    weights = {n: np.zeros((total + 1, total + 1), dtype=np.float32) for n in layer_names}
    HEIGHT = np.full((total + 1, total + 1), np.nan)
    base_index = 0
    for comp in D["landscape"]:
        hp = find_png(comp["cell"], comp["heightmap"] or "")
        if not hp:
            log("no heightmap png for %s %s" % (comp["cell"], comp["heightmap"]))
            continue
        hm = load_rgba(hp)
        th, tw = hm.shape[:2]
        h16 = np.round(hm[..., 0] * 255) * 256 + np.round(hm[..., 1] * 255)
        n, sub_q, nsub = comp["size"], comp["sub"], comp["nsub"]
        bx, by = comp["hsb"][2] * tw, comp["hsb"][3] * th
        m = comp["m"]
        sxy, sz, ox, oy, oz = m[0], m[10], m[12], m[13], m[14]
        # the proxy root sits at the proxy's first section; components are offset by their section base
        root_sec = (round(ox / sxy), round(oy / sxy))
        idx = np.arange(n + 1)
        s_i = np.minimum(idx // sub_q, nsub - 1)
        tex_i = s_i * (sub_q + 1) + (idx - s_i * sub_q)
        hgrid = h16[(by + tex_i)[:, None].astype(int), (bx + tex_i)[None, :].astype(int)]   # [y, x]
        z = oz + (hgrid - 32768.0) / 128.0 * sz
        gx = (comp["section"][0] + idx) * sxy + (ox - root_sec[0] * sxy)
        gy = (comp["section"][1] + idx) * sxy + (oy - root_sec[1] * sxy)
        X, Y = np.meshgrid(gx, gy)
        V = np.stack([X * 0.01, -Y * 0.01, z * 0.01], -1).reshape(-1, 3)
        HEIGHT[comp["section"][1]:comp["section"][1] + n + 1, comp["section"][0]:comp["section"][0] + n + 1] = z
        verts.append(V)
        ii = np.arange(n)
        a = (ii[:, None] * (n + 1) + ii[None, :]).reshape(-1) + base_index
        faces.append(np.stack([a, a + n + 1, a + n + 2, a + 1], -1))   # Y flipped -> this winding is CCW from above
        U = np.stack([(comp["section"][0] + X * 0 + idx[None, :]) / total,
                      1.0 - (comp["section"][1] + idx[:, None] + Y * 0) / total], -1).reshape(-1, 2)
        uvs.append(U)
        base_index += (n + 1) ** 2
        # weights: weightmap texel for vertex (x, y) like the heightmap (scale-bias in texels)
        for wi, wname in enumerate(comp["weightmaps"]):
            wp = find_png(comp["cell"], wname)
            if not wp:
                continue
            wm = load_rgba(wp)
            wh, ww = wm.shape[:2]
            wbx, wby = comp["wsb"][2] * ww - 0.5, comp["wsb"][3] * wh - 0.5
            for alloc in comp["layers"]:
                if alloc["tex"] != wi or not alloc["layer"]:
                    continue
                ch = wm[..., alloc["ch"]]
                w = ch[(np.round(wby + tex_i)).astype(int)[:, None].clip(0, wh - 1),
                       (np.round(wbx + tex_i)).astype(int)[None, :].clip(0, ww - 1)]
                sx0, sy0 = comp["section"]
                weights[alloc["layer"]][sy0:sy0 + n + 1, sx0:sx0 + n + 1] = w
    if verts:
        V = np.concatenate(verts)
        Fc = np.concatenate(faces)
        me = bpy.data.meshes.new("Landscape")
        me.vertices.add(len(V))
        me.vertices.foreach_set("co", V.reshape(-1).astype(np.float32))
        me.loops.add(Fc.size)
        me.loops.foreach_set("vertex_index", Fc.reshape(-1).astype(np.int32))
        me.polygons.add(len(Fc))
        me.polygons.foreach_set("loop_start", (np.arange(len(Fc)) * 4).astype(np.int32))
        me.polygons.foreach_set("loop_total", np.full(len(Fc), 4, dtype=np.int32))
        me.update(calc_edges=True)
        uvl = me.uv_layers.new(name="UVMap")
        U = np.concatenate(uvs)
        uvl.data.foreach_set("uv", U[Fc.reshape(-1)].reshape(-1).astype(np.float32))
        me.polygons.foreach_set("use_smooth", np.ones(len(Fc), dtype=bool))
        lo = bpy.data.objects.new("Landscape", me)
        sub("landscape").objects.link(lo)
        for nm, w in weights.items():
            img = bpy.data.images.new("LW_" + nm, total + 1, total + 1, float_buffer=False, is_data=True)
            rgba = np.zeros((total + 1, total + 1, 4), dtype=np.float32)
            rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = w
            rgba[..., 3] = 1
            img.pixels.foreach_set(np.flipud(rgba).reshape(-1))
            img.pack()
        me.materials.append(landscape_material(layer_names))
        log("landscape: %d verts, %d faces, layers %s" % (len(V), len(Fc), layer_names))


# ------------------------------------------------------------------ landscape grass (LandscapeGrassType, runtime in UE)
def build_grass(spec, weights, total):
    """spec "x,y,dir,r_full,r_max[,clear]" (UE cm / deg): the game's landscape grass types scattered by their layer
    weights with geometry nodes; full density up to r_full, a third beyond, nothing past r_max; only in the half
    space the camera looks into (dir +-100 deg) plus a ring around the spot; a clearing of `clear` cm at the spot."""
    gx, gy, gdir, r_full, r_max = (float(v) for v in spec.split(",")[:5])
    clear = float(spec.split(",")[5]) if len(spec.split(",")) > 5 else 300.0
    types = json.load(open(args.grass_types, encoding="utf-8"))
    layer_of = {"LGT_1": "1_LayerInfo", "LGT_3": "3_LayerInfo"}
    # carrier: landscape quads within r_max (UE quads are 1 m)
    x0, x1 = int(max(0, (gx - r_max) // 100)), int(min(total, (gx + r_max) // 100 + 1))
    y0, y1 = int(max(0, (gy - r_max) // 100)), int(min(total, (gy + r_max) // 100 + 1))
    xs, ys = np.arange(x0, x1 + 1), np.arange(y0, y1 + 1)
    X, Y = np.meshgrid(xs, ys)
    Z = HEIGHT[y0:y1 + 1, x0:x1 + 1]
    V = np.stack([X * 1.0, -Y * 1.0, Z * 0.01], -1).reshape(-1, 3)        # 1 quad = 1 m, Blender metres
    dx, dy = X * 100.0 - gx, Y * 100.0 - gy
    dist = np.hypot(dx, dy)
    ang = np.degrees(np.arctan2(dy, dx)) - gdir
    ang = (ang + 180) % 360 - 180
    keep = (dist <= r_max) & ((np.abs(ang) <= 100) | (dist <= r_full * 0.5))
    fall = np.where(dist <= r_full, 1.0, 0.33) * keep
    fall *= np.clip((dist - clear) / 150.0, 0.0, 1.0)
    nx, ny = len(xs), len(ys)
    ii, jj = np.meshgrid(np.arange(ny - 1), np.arange(nx - 1), indexing="ij")
    a = (ii * nx + jj).reshape(-1)
    quads = np.stack([a, a + nx, a + nx + 1, a + 1], -1)
    qkeep = fall.reshape(-1)[quads].max(1) > 0
    quads = quads[qkeep]
    me = bpy.data.meshes.new("VDF_GrassGround")
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.reshape(-1).astype(np.float32))
    me.loops.add(quads.size)
    me.loops.foreach_set("vertex_index", quads.reshape(-1).astype(np.int32))
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", (np.arange(len(quads)) * 4).astype(np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(quads), 4, dtype=np.int32))
    me.update(calc_edges=True)
    for name, arr in (("fall", fall),) + tuple((ln, weights[ln][y0:y1 + 1, x0:x1 + 1]) for ln in set(layer_of.values())
                                               if ln in weights):
        at = me.attributes.new(name, "FLOAT", "POINT")
        at.data.foreach_set("value", np.asarray(arr, dtype=np.float32).reshape(-1))
    obj = bpy.data.objects.new("VDF_Grass", me)
    sub("grass").objects.link(obj)
    g = bpy.data.node_groups.new("VDF_GrassScatter", "GeometryNodeTree")
    g.inputs.new("NodeSocketGeometry", "Geometry")
    g.outputs.new("NodeSocketGeometry", "Geometry")
    n, L = g.nodes, g.links.new
    gi, go = n.new("NodeGroupInput"), n.new("NodeGroupOutput")
    join = n.new("GeometryNodeJoinGeometry")
    L(join.outputs[0], go.inputs[0])
    count = 0
    for tname, varieties in types.items():
        layer = layer_of.get(tname)
        if not layer or layer not in weights:
            continue
        for k, v in enumerate(varieties):
            mesh = v.get("GrassMesh")
            path = MESH_FILE.get((mesh or "").lower())
            if not path:
                log("grass mesh not exported: %s" % mesh)
                continue
            src = source(path, True)
            wl = n.new("GeometryNodeInputNamedAttribute")
            wl.data_type = "FLOAT"
            wl.inputs["Name"].default_value = layer
            fl = n.new("GeometryNodeInputNamedAttribute")
            fl.data_type = "FLOAT"
            fl.inputs["Name"].default_value = "fall"
            m1 = n.new("ShaderNodeMath")
            m1.operation = "MULTIPLY"
            L(wl.outputs["Attribute"], m1.inputs[0])
            L(fl.outputs["Attribute"], m1.inputs[1])
            m2 = n.new("ShaderNodeMath")
            m2.operation = "MULTIPLY"
            L(m1.outputs[0], m2.inputs[0])
            m2.inputs[1].default_value = v.get("GrassDensity", 10.0) / 100.0 * args.grass_density
            dist = n.new("GeometryNodeDistributePointsOnFaces")
            dist.distribute_method = "RANDOM"
            dist.inputs["Seed"].default_value = 17 + count * 31
            L(gi.outputs["Geometry"], dist.inputs["Mesh"])
            L(m2.outputs[0], dist.inputs["Density"])
            info = n.new("GeometryNodeObjectInfo")
            info.inputs["Object"].default_value = src
            rnd = n.new("FunctionNodeRandomValue")
            rnd.data_type = "FLOAT"
            rnd.inputs["Seed"].default_value = 3 + count
            rnd.inputs[2].default_value = 0.0
            rnd.inputs[3].default_value = 6.2832
            rotz = n.new("ShaderNodeCombineXYZ")
            L(rnd.outputs[1], rotz.inputs["Z"])
            rot = n.new("FunctionNodeRotateEuler")
            rot.space = "LOCAL"
            L(dist.outputs["Rotation"], rot.inputs["Rotation"])
            L(rotz.outputs[0], rot.inputs["Rotate By"])
            sx = v.get("ScaleX") or [1.0, 1.0]
            rs = n.new("FunctionNodeRandomValue")
            rs.data_type = "FLOAT"
            rs.inputs["Seed"].default_value = 7 + count
            rs.inputs[2].default_value = sx[0] * 0.01
            rs.inputs[3].default_value = sx[1] * 0.01
            iop = n.new("GeometryNodeInstanceOnPoints")
            L(dist.outputs["Points"], iop.inputs["Points"])
            L(info.outputs["Geometry"], iop.inputs["Instance"])
            L(rot.outputs[0] if v.get("AlignToSurface", 1) else rotz.outputs[0], iop.inputs["Rotation"])
            L(rs.outputs[1], iop.inputs["Scale"])
            L(iop.outputs["Instances"], join.inputs[0])
            count += 1
    mod = obj.modifiers.new("grass", "NODES")
    mod.node_group = g
    log("landscape grass: %d varieties on %d m2 around (%.0f, %.0f)" % (count, len(quads), gx, gy))


if args.grass and not args.no_landscape and D["landscape"]:
    build_grass(args.grass, weights, total)

# ------------------------------------------------------------------ sky + sun
world = bpy.data.worlds.new("VDF_Sky")
world.use_nodes = True
wt = world.node_tree
bg = next(n for n in wt.nodes if n.type == "BACKGROUND")
hdr = tex(args.sky_hdr) if args.sky_hdr else None
if hdr:
    # the level's own sky: SM_SkyDome with MI_EmissiveAdditiveSky_01 = this panorama (partly cloudy, Poly Haven's
    # kloofendal_48d) x 1.5 over the SkyAtmosphere; turned so that its sun sits where the sun lamp shines from
    env = wt.nodes.new("ShaderNodeTexEnvironment")
    env.image = image(hdr, False)
    w, h = env.image.size[0], env.image.size[1]
    px = np.empty(w * h * 4, dtype=np.float32)
    env.image.pixels.foreach_get(px)
    lum = px.reshape(-1, 4)[:, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    sy, sx = divmod(int(np.argmax(lum)), w)              # Blender images are stored bottom row first
    sun_u, sun_v = (sx + 0.5) / w, (sy + 0.5) / h
    hdr_az = (0.5 - sun_u) * 2 * math.pi                 # Blender equirect (probed): u = 0.5 - atan2(y, x) / 2pi
    hdr_el = (sun_v - 0.5) * math.pi
    rot = math.radians(args.sun_rot)
    want = math.atan2(math.cos(rot), math.sin(rot))      # the lamp's sun (x, y) = (sin rot, cos rot)
    coord = wt.nodes.new("ShaderNodeTexCoord")
    mapping = wt.nodes.new("ShaderNodeMapping")           # POINT: the lookup vector is rotated -> +(hdr - want)
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, hdr_az - want)
    wt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    wt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    wt.links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = args.sky_strength
    args.sun_elev = math.degrees(hdr_el) if args.sun_elev < 0 else args.sun_elev
    log("sky: %s, its sun at u %.3f v %.3f (elevation %.1f deg), turned %.1f deg; strength %.2f" % (
        os.path.basename(hdr), sun_u, sun_v, math.degrees(hdr_el), math.degrees(hdr_az - want), args.sky_strength))
else:
    sky = wt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(abs(args.sun_elev))
    sky.sun_rotation = math.radians(args.sun_rot)
    sky.altitude = 300.0
    sky.air_density = 1.0
    sky.dust_density = 2.0
    sky.sun_disc = False
    wt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.35
scene.world = world
sun_data = bpy.data.lights.new("VDF_Sun", "SUN")
sun_data.energy = args.sun_energy
sun_data.angle = math.radians(1.5)
sun_data.color = (1.0, 0.96, 0.9)
sun = bpy.data.objects.new("VDF_Sun", sun_data)
# Nishita: rotation 0 = sun towards -Y?; point the lamp along the sky's sun direction
el, rot = math.radians(args.sun_elev), math.radians(args.sun_rot)
to_sun = (math.sin(rot) * math.cos(el), math.cos(rot) * math.cos(el), math.sin(el))   # Nishita: rotation 0 = +Y, 90 = +X (probed)
from mathutils import Vector                                   # noqa: E402
sun.rotation_euler = Vector(to_sun).to_track_quat("Z", "Y").to_euler()
sub("lights").objects.link(sun)

# ------------------------------------------------------------------ save
# image paths absolute through the short junction, saved as they are: Blender opens a .blend by its real (long) path,
# disperse_pair.py appends it by the junction path - a relative path made against one breaks from the other
JUNCTION = r"C:\Users\haoni\AppData\Local\Temp\vdfs"
REAL = os.path.realpath(JUNCTION)
for img in bpy.data.images:
    if img.packed_file or img.source != "FILE":
        continue
    n = os.path.normpath(bpy.path.abspath(img.filepath))
    if n.lower().startswith(REAL.lower()):
        n = JUNCTION + n[len(REAL):]
    img.filepath = n
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out), compress=True, relative_remap=False)
log("saved %s" % args.out)
