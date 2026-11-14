# -*- coding: utf-8 -*-
"""MMD materials for our game PMX files, in two layers (docs/pmx-hq-materials.md):

1. MMD's own material settings by what each material is - skin, hair, eyes, cloth, metal, glossy (latex / leather
   / plastic), glass, glowing parts: a toon texture, a sphere map, specular / shininess and an edge line, written to
   ``<stem>_材质.pmx`` next to the original (shared toon / sphere images in ``<pmx folder>/mmd_materials/``).
   Every MMD shows it, no plug-in needed.
2. A ray-mmd (MME) version made from the game's own maps - normal, roughness, metallic, specular, emission - read
   from the PMX's source .blend (Blender, ``extract_pbr_blender.py``), in an ASCII-only folder (MME garbles Chinese
   paths): ``E:\\game_export\\_raymmd\\<Game>\\<character>_<model>_<hash>\\`` with ``model.pmx`` + ``textures\\``
   (hard links), ``fx\\`` (one ray-mmd .fx per material) and ``scene.emm`` (MME's per-material assignment; a
   per-model .emd cannot carry it).  ``mmd_drive.py scene`` adds a one-click ``scene.pmm``.

What a material is comes from its name and texture name (skin / hair / eye / ... keywords in English, Chinese and
Japanese) and, when the source .blend is found, from the game maps measured inside the material's own UV triangles
(metallic share, mean roughness, emission, subsurface).  The values per kind live in DEFAULT_VALUES and can be
overridden with --values <json> ({"skin": {"specular": 0.1}, ...}).

    python make_hq_materials.py <pmx file or folder> ... [--blend <source.blend>] [--suffix _材质]
           [--steps 1,2] [--force] [--dry-run] [--report out.json] [--values values.json]
           [--blender <blender.exe>] [--ray-mmd <ray-mmd folder>] [--raymmd-root <ASCII folder>]

The source .blend is looked up as ``<pmx folder>/<stem>_converted.blend`` (written by our PMX exporters) or, in the
E:\\game_export layout, ``<Game>/<Character>/blend/<model>/*.blend`` (Rise of Eros).  Without one, step 2 still
writes a pack from the per-kind presets (no game maps).  Originals are never changed.
"""
import argparse
import glob
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
RAY_MMD = r"E:\tools\MikuMikuDanceE_v932x64\ray-mmd-1.5.2"
TEXCONV = r"E:\tools\directxtex\texconv.exe"
SUFFIX = "_材质"
RAY_SUFFIX = "_raymmd"
SHARED = "mmd_materials"
PACK = "ray_mmd"
D3DX_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".tga", ".dds")
MARK = "MMD materials by kind + ray-mmd pack (pmx_tools/hq_materials)"

# ------------------------------------------------------------------ per-kind values
# specular / shininess: MMD's Phong highlight (colour added on top); toon: shadow colour of the generated toon ramp
# (top white -> this colour below the terminator, soft = width of the step); sphere: generated map + mode;
# edge: edge size (0 = off), the colour is the material's average texture colour darkened.
DEFAULT_VALUES = {
    "skin": {"specular": 0.15, "shininess": 4.0, "toon": [0.88, 0.76, 0.73], "soft": 0.24,
             "sphere": ["skin", "add"], "edge": 0.4},
    "hair": {"specular": 0.25, "shininess": 20.0, "toon": [0.78, 0.76, 0.80], "soft": 0.18,
             "sphere": ["hair", "add"], "edge": 0.4},
    "cloth": {"specular": 0.15, "shininess": 4.0, "toon": [0.80, 0.80, 0.82], "soft": 0.18,
              "sphere": None, "edge": 0.4},
    # metal / mixed / glossy / glass: no sphere by default.  With the environment spheres the ELDEN RING Gantz suit
    # got flat grey patches exactly where an outer layer (bikini / thigh covers) lies on the suit - opaque textures,
    # so not the cut-out problem below; without spheres it was clean and the toon alone already shaded it (11-14).
    # The maps are still written ("metal", "metal_soft", "gloss"): {"metal": {"sphere": ["metal", "add"]}} turns
    # them on through --values.
    "mixed": {"specular": 0.5, "shininess": 8.0, "toon": [0.78, 0.78, 0.80], "soft": 0.16,
              "sphere": None, "edge": 0.4},
    "metal": {"specular": 0.8, "shininess": 30.0, "toon": [0.66, 0.66, 0.70], "soft": 0.14,
              "sphere": None, "edge": 0.4},
    "glossy": {"specular": 0.6, "shininess": 40.0, "toon": [0.70, 0.70, 0.74], "soft": 0.14,
               "sphere": None, "edge": 0.4},
    "glass": {"specular": 0.9, "shininess": 60.0, "toon": None, "soft": 0.0, "sphere": None, "edge": 0.0},
    "eye": {"specular": 0.5, "shininess": 60.0, "toon": [1.0, 1.0, 1.0], "soft": 0.0, "sphere": ["eye", "add"],
            "edge": 0.0},
    "eye_overlay": {"keep": True, "edge": 0.0},
    "lash_brow": {"specular": 0.0, "shininess": 5.0, "toon": [1.0, 1.0, 1.0], "soft": 0.0, "sphere": None,
                  "edge": 0.0},
    "mouth": {"specular": 0.3, "shininess": 20.0, "toon": [0.86, 0.76, 0.76], "soft": 0.2, "sphere": None,
              "edge": 0.0},
    "emissive": {"specular": 0.0, "shininess": 5.0, "toon": [1.0, 1.0, 1.0], "soft": 0.0, "sphere": None,
                 "edge": 0.0, "ambient": 1.0},
}
# ray-mmd presets per kind when the game gives no map / value: smoothness, metalness, specular (0.5 = F0 0.04),
# custom shading model (1 skin, 5 cloth, 0 default)
RAY_PRESETS = {
    "skin": {"smoothness": 0.45, "metalness": 0.0, "specular": 0.35, "custom": 1},
    "hair": {"smoothness": 0.45, "metalness": 0.0, "specular": 0.5, "custom": 0},
    "cloth": {"smoothness": 0.25, "metalness": 0.0, "specular": 0.5, "custom": 0},
    "mixed": {"smoothness": 0.5, "metalness": 0.5, "specular": 0.5, "custom": 0},
    "metal": {"smoothness": 0.65, "metalness": 1.0, "specular": 0.5, "custom": 0},
    "glossy": {"smoothness": 0.8, "metalness": 0.0, "specular": 0.5, "custom": 0},
    "glass": {"smoothness": 0.95, "metalness": 0.0, "specular": 0.5, "custom": 0},
    "eye": {"smoothness": 0.9, "metalness": 0.0, "specular": 0.5, "custom": 0},
    "eye_overlay": {"smoothness": 0.9, "metalness": 0.0, "specular": 0.5, "custom": 0},
    "lash_brow": {"smoothness": 0.2, "metalness": 0.0, "specular": 0.3, "custom": 0},
    "mouth": {"smoothness": 0.6, "metalness": 0.0, "specular": 0.5, "custom": 0},
    "emissive": {"smoothness": 0.5, "metalness": 0.0, "specular": 0.5, "custom": 0},
}

# name / texture keywords, checked in this order on "<material name> <texture file name>" (lower case)
KEYWORDS = [
    ("eye_overlay", r"namida|tear|overlay|occlusion|catch_?light|hi_?light|涙|泪|eye_?wet"),
    ("lash_brow", r"lash|brow|eyekage|eye_?shadow|eye_?line|まつ|睫|眉"),
    ("eye", r"eye|iris|pupil|cornea|sclera|瞳|眼球|眼睛|虹膜|目玉|hitomi"),
    ("mouth", r"teeth|tooth|tongue|(^|[^a-z])tang([^a-z]|$)|mouth|oral|口腔|牙|舌|歯|口内"),
    ("hair", r"hair|髪|发|髮|ponytail|twintail|(^|[^a-z])bangs?([^a-z]|$)"),
    ("emissive", r"emiss|glow|(^|[^a-z])light([^a-z]|$)|neon|(^|[^a-z])led([^a-z]|$)|发光|ライト"),
    ("glass", r"transparent|(^|[^a-z])lens|crystal|(^|[^a-z])glass([^a-z]|$)|玻璃|ガラス|透明"),
    ("glossy", r"latex|rubber|leather|vinyl|pvc|enamel|patent|gantz|plastic|glasses|bodysuit|ラテックス|エナメル|"
               r"紧身衣|胶衣|皮革|乳胶|比基尼"),
    ("skin", r"skin|(^|[^a-z])body(?!suit)|face|(^|[^a-z])head(?!phone|set|band|gear|dress|piece)|(^|[^a-z])hands?"
             r"([^a-z]|$)|foot|feet|(^|[^a-z])legs?([^a-z]|$)|(^|[^a-z])arms?([^a-z]|$)|nk_body|nk_face|肌|皮肤|身体|"
             r"胴体|躯干|脸|颜|nude|naked"),
    ("metal", r"metal|steel|iron|gold|silver|chrome|chain|buckle|zipper|armou?r|金属|铁|鉄|钢|(^|[^a-z])ring"
              r"([^a-z]|$)|earring|necklace|jewel|bracelet|watch|按钮|纽扣"),
]
# "<mesh file>.fbx_<material>" (Chinese mod packs name materials after the mesh file): only the part after it counts
MESH_PREFIX = re.compile(r"^.*\.(fbx|obj|dae|pmx|xps|mesh)[_ ]", re.I)
NAME_ONLY = ("eye_overlay", "lash_brow", "eye", "mouth", "hair", "glass")    # the maps do not overrule these


# ------------------------------------------------------------------ PMX module

def find_pmx_module():
    root = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender")
    for pattern in ("3.6/scripts/addons/mmd_tools/core/pmx/__init__.py", "*/scripts/addons/mmd_tools/core/pmx/__init__.py",
                    "*/extensions/*/mmd_tools/core/pmx/__init__.py"):
        hits = sorted(glob.glob(os.path.join(root, pattern)))
        if hits:
            spec = importlib.util.spec_from_file_location("mmd_pmx", hits[0])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise SystemExit("mmd_tools' core/pmx/__init__.py not found")


pmx = find_pmx_module()


# ------------------------------------------------------------------ helpers

def ascii_slug(name):
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_.")[:48] or "m"
    return "%s_%s" % (slug, hashlib.md5(name.encode("utf-8")).hexdigest()[:6])


def tex_path(model, index):
    if index is None or index < 0 or index >= len(model.textures):
        return None
    return model.textures[index].path


def read_image(path):
    """A PIL image, or None.  DDS formats Pillow cannot open go through texconv."""
    if not path or not os.path.isfile(path):
        return None
    try:
        im = Image.open(path)
        im.load()
        return im
    except Exception:  # noqa: BLE001
        pass
    if path.lower().endswith(".dds") and os.path.isfile(TEXCONV):
        tmp = tempfile.mkdtemp(prefix="hqmat_")
        try:
            subprocess.run([TEXCONV, "-nologo", "-y", "-ft", "png", "-f", "R8G8B8A8_UNORM", "-o", tmp, path],
                           capture_output=True, timeout=300)
            out = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0] + ".png")
            if os.path.isfile(out):
                im = Image.open(out)
                im.load()
                return im
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return None


def srgb_to_linear(v):
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def channel_array(desc, size):
    """A channel descriptor from extract_pbr_blender -> float array (size[1], size[0]) as Blender reads it."""
    im = read_image(desc.get("path"))
    if im is None:
        return None
    a = np.asarray(im.convert("RGBA").resize(size, Image.BILINEAR), dtype=np.float32) / 255.0
    ch = desc.get("channel")
    if ch == "lum":
        v = a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722
    elif ch is None:
        v = a[..., 0]
    else:
        v = a[..., int(ch)]
    if desc.get("colorspace") == "sRGB" and ch != 3:
        v = srgb_to_linear(v)
    if desc.get("invert"):
        v = 1.0 - v
    return v


def coverage(model, start, count, size):
    """Mask of the material's UV triangles (the PMX's own UVs, D3D convention: v down = image rows)."""
    img = Image.new("L", size, 0)
    draw = ImageDraw.Draw(img)
    w, h = size
    for f in model.faces[start:start + count]:
        pts = []
        for i in f:
            u, v = model.vertices[i].uv
            pts.append(((u % 1.0) * w, (v % 1.0) * h))
        draw.polygon(pts, fill=255)
    return np.asarray(img) > 0


# ------------------------------------------------------------------ classification

def classify(name, texture, stats, hints):
    """(kind, reasons).  Names first for the parts the maps cannot tell (eyes, lashes, mouth, hair, glass); then the
    game maps measured inside the material's UV triangles - a map (file / baked) is strong evidence, a constant in
    the node tree is weak (several converters leave Metallic 0 everywhere) and only breaks ties."""
    name = MESH_PREFIX.sub("", name)
    tex = MESH_PREFIX.sub("", os.path.splitext(os.path.basename(texture or ""))[0])
    by_name = None
    for text in (name.lower(), tex.lower()):
        for cls, rx in KEYWORDS:
            if re.search(rx, text):
                by_name = cls
                break
        if by_name:
            break
    reasons = ["name: %s" % by_name] if by_name else []
    if by_name in NAME_ONLY:
        return by_name, reasons
    st = stats or {}
    src = st.get("source", {})
    if st.get("emission_share", 0) >= 0.5:
        return "emissive", reasons + ["emission over %.0f%% of it" % (100 * st["emission_share"])]
    m, r = st.get("metallic"), st.get("roughness")
    m_map, r_map = src.get("metallic") == "map", src.get("roughness") == "map"
    if m is not None and m >= 0.5 and (m_map or by_name in (None, "metal")):
        return "metal", reasons + ["metallic %.2f (%s)" % (m, src.get("metallic"))]
    if m is not None and m >= 0.2 and m_map and by_name != "skin":
        return "mixed", reasons + ["metallic %.2f (map)" % m]
    if by_name == "metal" and m is not None and m < 0.2 and m_map:
        by_name = None                                 # the game says it is not metal
        reasons.append("metallic map %.2f: not metal" % m)
    sss = hints.get("Subsurface")
    if isinstance(sss, float) and sss > 0.05 and by_name in (None, "skin"):
        return "skin", reasons + ["subsurface %.2f" % sss]
    if r is not None and r <= 0.3 and by_name not in ("skin", "emissive") and (r_map or by_name is None):
        return "glossy", reasons + ["roughness %.2f (%s)" % (r, src.get("roughness"))]
    if by_name:
        return by_name, reasons
    return "cloth", reasons + ["default"]


# ------------------------------------------------------------------ toon / sphere images

def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / max(1e-6, e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def write_toon(path, shadow, soft):
    """MMD looks the toon up at v = 0.5 - N.L / 2: top = lit, 0.5 = terminator, bottom (and self-shadow) = shadow."""
    v = (np.arange(256, dtype=np.float32) + 0.5) / 256.0
    t = smoothstep(0.5 - soft / 2, 0.5 + soft / 2 + 0.06, v) if soft > 0 else (v > 0.55).astype(np.float32)
    col = (1.0 - t)[:, None] * np.ones(3)[None, :] + t[:, None] * np.asarray(shadow, dtype=np.float32)[None, :]
    img = np.repeat((np.clip(col, 0, 1) * 255 + 0.5).astype(np.uint8)[:, None, :], 32, axis=1)
    Image.fromarray(img, "RGB").save(path, format="PNG")


def write_sphere(path, kind):
    """Additive sphere maps, indexed by the view-space normal: centre = facing the camera, edge = grazing, top = up."""
    n = 256
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    u, v = (x + 0.5) / n * 2 - 1, (y + 0.5) / n * 2 - 1          # v down
    r = np.sqrt(u * u + v * v)
    inside = (r <= 1.0).astype(np.float32)
    rim = smoothstep(0.55, 1.0, r) ** 2

    def blob(cx, cy, s):
        return np.exp(-((u - cx) ** 2 + (v - cy) ** 2) / (2 * s * s))
    if kind == "skin":
        val = 0.10 * rim + 0.05 * blob(-0.3, -0.45, 0.35)
        col = np.array([1.0, 0.92, 0.88])
    elif kind == "hair":
        val = 0.22 * np.exp(-((v + 0.38) / 0.16) ** 2) * np.clip(1 - np.abs(u) * 0.9, 0, 1) + 0.06 * rim
        col = np.array([1.0, 0.98, 0.95])
    elif kind == "metal_soft":
        val = 0.12 * smoothstep(0.2, -0.9, v) + 0.06 * rim + 0.18 * blob(-0.35, -0.45, 0.12)
        col = np.array([1.0, 1.0, 1.0])
    elif kind == "metal":
        val = 0.20 * smoothstep(0.25, -0.9, v) + 0.04 * smoothstep(0.1, 0.0, np.abs(v - 0.05)) + 0.08 * rim + \
            0.35 * blob(-0.35, -0.45, 0.10)
        col = np.array([1.0, 1.0, 1.0])
    elif kind == "gloss":
        val = 0.50 * blob(-0.32, -0.42, 0.07) + 0.12 * blob(-0.32, -0.42, 0.25) + 0.10 * rim
        col = np.array([1.0, 1.0, 1.0])
    elif kind == "eye":
        val = 0.85 * blob(-0.32, -0.38, 0.05)
        col = np.array([1.0, 1.0, 1.0])
    else:
        raise ValueError(kind)
    rgb = np.clip(val * inside, 0, 1)[..., None] * col[None, None, :]
    # Opaque on purpose.  MMD's own renderer lets an additive sphere map's alpha into the material's alpha: with
    # an opaque map the cut-out parts of the texture (alpha 0) turn into grey ghosts, with an alpha-0 map the
    # whole material disappears (both tried in MMD 9.32, 11-14).  So materials with cut-outs get no sphere at all
    # (step1 measures the texture's alpha inside the material's UV triangles).
    Image.fromarray((rgb * 255 + 0.5).astype(np.uint8), "RGB").save(path, format="PNG")


def shared_images(folder, values):
    os.makedirs(folder, exist_ok=True)
    files = {}
    for kind in ("skin", "hair", "metal_soft", "metal", "gloss", "eye"):
        p = os.path.join(folder, "sphere_%s.spa" % kind)
        write_sphere(p, kind)
        files[("sphere", kind)] = p
    for cls, v in values.items():
        if v.get("keep"):
            continue
        if v.get("toon") is not None:
            p = os.path.join(folder, "toon_%s.png" % cls)
            write_toon(p, v["toon"], v.get("soft", 0.18))
            files[("toon", cls)] = p
        if v.get("sphere"):
            kind, mode = v["sphere"]
            if ("sphere", kind) not in files:
                p = os.path.join(folder, "sphere_%s.%s" % (kind, "spa" if mode == "add" else "sph"))
                write_sphere(p, kind)
                files[("sphere", kind)] = p
    return files


# ------------------------------------------------------------------ source .blend

def find_source_blend(path, explicit=None):
    if explicit:
        return explicit
    folder, stem = os.path.dirname(path), os.path.splitext(os.path.basename(path))[0]
    s = stem
    while True:
        cand = os.path.join(folder, s + "_converted.blend")
        if os.path.isfile(cand):
            return cand
        if "_" not in s:
            break
        s = s.rsplit("_", 1)[0]
    hits = sorted(glob.glob(os.path.join(folder, "*_converted.blend")))
    if len(hits) == 1:
        return hits[0]
    parts = os.path.normpath(folder).split(os.sep)
    if len(parts) >= 3 and parts[-2].lower() == "pmx":
        blend_dir = os.path.join(os.sep.join(parts[:-2]), "blend", parts[-1])
        hits = sorted(glob.glob(os.path.join(blend_dir, "*.blend")))
        if hits:
            exact = [h for h in hits if os.path.splitext(os.path.basename(h))[0] == parts[-1]]
            return (exact or hits)[0]
    return None


def run_extract(blend, model, work, bake_dir, blender, log):
    request = {"materials": [{"index": i, "name": m.name,
                              "texture": os.path.basename(tex_path(model, m.texture) or "")}
                             for i, m in enumerate(model.materials)],
               "strip_prefixes": ["HQ_"]}
    req = os.path.join(work, "request.json")
    out = os.path.join(work, "extract.json")
    with open(req, "w", encoding="utf-8") as f:
        json.dump(request, f, ensure_ascii=False)
    cmd = [blender, "-b", "--factory-startup", blend, "--python", os.path.join(HERE, "extract_pbr_blender.py"), "--",
           "--request", req, "--out", out, "--bake-dir", bake_dir]
    p = subprocess.run(cmd, capture_output=True, timeout=7200)
    text = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
    with open(log, "w", encoding="utf-8") as f:
        f.write(text)
    if not os.path.isfile(out):
        raise RuntimeError("extract_pbr_blender failed (see %s)" % log)
    return json.load(open(out, encoding="utf-8"))


# ------------------------------------------------------------------ measuring the game maps

def measure(model, extract, size=512):
    """Per PMX material index: metallic / roughness means and emission share inside its UV triangles."""
    out = {}
    if not extract:
        return out
    rows = {r["index"]: r for r in extract["materials"]}
    start = 0
    for i, mat in enumerate(model.materials):
        n = mat.vertex_count // 3
        row = rows.get(i)
        st = {}
        if row and row.get("blend_material"):
            mask = coverage(model, start, n, (size, size))
            if mask.any():
                st["source"] = {}
                for key in ("metallic", "roughness"):
                    d = row["channels"].get(key) or {}
                    if d.get("kind") == "const":
                        st[key] = float(d["value"])
                        st["source"][key] = "const"
                    elif d.get("kind") in ("file", "baked"):
                        a = channel_array(d, (size, size))
                        if a is not None:
                            st[key] = float(a[mask].mean())
                            st["source"][key] = "map"
                e = row["channels"].get("emission") or {}
                if e.get("kind") == "const":
                    st["emission_share"] = 1.0 if max(e["value"]) * e.get("strength", 1) > 0.05 else 0.0
                elif e.get("kind") in ("file", "baked"):
                    im = read_image(e["path"])
                    if im is not None:
                        a = np.asarray(im.convert("RGB").resize((size, size)), dtype=np.float32) / 255.0
                        lum = a.max(axis=2) * float(e.get("strength", 1.0))
                        st["emission_share"] = float((lum[mask] > 0.05).mean())
        out[i] = st
        start += n
    return out


def cutout_share(model, mat, start, n, size=256):
    """Share of the material's UV area where its texture is (partly) transparent; also counts a diffuse alpha < 1."""
    if mat.diffuse[3] < 0.999:
        return 1.0
    im = read_image(tex_path(model, mat.texture))
    if im is None or im.mode not in ("RGBA", "LA", "P", "PA"):
        return 0.0
    a = np.asarray(im.convert("RGBA").resize((size, size)), dtype=np.float32)[..., 3] / 255.0
    mask = coverage(model, start, n, (size, size))
    return float((a[mask] < 0.95).mean()) if mask.any() else 0.0


def edge_colour(model, mat, start, n):
    im = read_image(tex_path(model, mat.texture))
    if im is None:
        c = [float(x) for x in mat.diffuse[:3]]
    else:
        a = np.asarray(im.convert("RGB").resize((256, 256)), dtype=np.float32) / 255.0
        mask = coverage(model, start, n, (256, 256))
        c = a[mask].mean(axis=0).tolist() if mask.any() else a.reshape(-1, 3).mean(axis=0).tolist()
    return [max(0.0, min(1.0, x * 0.35)) for x in c] + [1.0]


# ------------------------------------------------------------------ step 1: MMD's own materials

def step1(model, classes, values, shared, force):
    """Change the material fields in place; returns per-material notes."""
    def tex_index(path):
        for k, t in enumerate(model.textures):
            if os.path.normcase(os.path.abspath(t.path)) == os.path.normcase(os.path.abspath(path)):
                return k
        t = pmx.Texture()
        t.path = path
        model.textures.append(t)
        return len(model.textures) - 1

    notes = []
    start = 0
    for i, mat in enumerate(model.materials):
        n = mat.vertex_count // 3
        cls = classes[i]["class"]
        v = values[cls]
        note = {"index": i, "class": cls}
        game_toon = not mat.is_shared_toon_texture and mat.toon_texture is not None and mat.toon_texture >= 0
        game_sphere = mat.sphere_texture is not None and mat.sphere_texture >= 0 and mat.sphere_texture_mode > 0
        if v.get("keep") or ((game_toon or game_sphere) and not force):
            note["kept"] = "kept as it is" if v.get("keep") else "has its own toon / sphere"
            notes.append(note)
            start += n
            continue
        mat.specular = [v["specular"]] * 3
        mat.shininess = float(v["shininess"])
        if v.get("toon") is not None:
            mat.is_shared_toon_texture = False
            mat.toon_texture = tex_index(shared[("toon", cls)])
        if v.get("sphere") and not game_sphere:
            cut = cutout_share(model, mat, start, n)
            if cut > 0.005:                    # MMD adds the sphere's alpha: cut-outs would turn into grey ghosts
                note["no_sphere"] = "texture has cut-outs over %.1f%% of it" % (100 * cut)
            else:
                kind, mode = v["sphere"]
                mat.sphere_texture = tex_index(shared[("sphere", kind)])
                mat.sphere_texture_mode = 2 if mode == "add" else 1
        if v.get("ambient") is not None:
            mat.ambient = [float(v["ambient"])] * 3
            mat.enabled_self_shadow = False
        if v.get("edge", 0) > 0:
            mat.enabled_toon_edge = True
            mat.edge_size = float(v["edge"])
            mat.edge_color = edge_colour(model, mat, start, n)
        else:
            mat.enabled_toon_edge = False
        notes.append(note)
        start += n
    if MARK not in (model.comment or ""):
        model.comment = ((model.comment or "").rstrip() + "\r\n" + MARK).strip()
    return notes


# ------------------------------------------------------------------ step 2: ray-mmd pack

def set_define(text, name, value):
    new, k = re.subn(r"(?m)^#define %s .*$" % re.escape(name), "#define %s %s" % (name, value), text)
    if not k:
        raise KeyError(name)
    return new


def set_const(text, name, value):
    new, k = re.subn(r"(?m)^(const\s+\w+\s+%s\s*=\s*).*?;" % re.escape(name), r"\g<1>%s;" % value, text)
    if not k:
        raise KeyError(name)
    return new


class Pack:
    """The ray_mmd folder: maps hard-linked / converted under ASCII names, one .fx per material."""

    def __init__(self, folder, ray_mmd):
        self.folder = folder
        self.maps = os.path.join(folder, "maps")
        self.ray = ray_mmd
        self.linked = {}
        os.makedirs(self.maps, exist_ok=True)
        for old in glob.glob(os.path.join(folder, "*.fx")):      # ours: rewritten every run
            os.remove(old)
        self.template = open(os.path.join(ray_mmd, "Materials", "material_2.0.fx"), encoding="utf-8",
                             errors="replace").read()
        shutil.copyfile(os.path.join(ray_mmd, "Materials", "material_common_2.0.fxsub"),
                        os.path.join(folder, "material_common_2.0.fxsub"))
        lic = os.path.join(ray_mmd, "LICENSE.txt")
        if os.path.isfile(lic):
            shutil.copyfile(lic, os.path.join(folder, "ray-mmd_LICENSE.txt"))

    def rel(self, path):
        return os.path.relpath(path, self.folder).replace("\\", "/")

    def link(self, src):
        """A file the .fx can name: the source itself if it sits inside the pack, else a hard link (or copy)
        under an ASCII name in maps/."""
        src = os.path.abspath(src)
        if src in self.linked:
            return self.linked[src]
        try:
            inside = os.path.commonpath([src, self.folder]) == self.folder
        except ValueError:                                  # another drive
            inside = False
        if inside and self.rel(src).isascii():
            self.linked[src] = self.rel(src)
            return self.linked[src]
        base, ext = os.path.splitext(os.path.basename(src))
        dst = os.path.join(self.maps, ascii_slug(base) + ext.lower())
        if not os.path.exists(dst):
            try:
                os.link(src, dst)
            except OSError:
                shutil.copyfile(src, dst)
        self.linked[src] = self.rel(dst)
        return self.linked[src]

    def derived(self, key, make):
        """A converted map (written once): make() -> PIL image."""
        dst = os.path.join(self.maps, key + ".png")
        if not os.path.isfile(dst):
            im = make()
            if im is None:
                return None
            im.save(dst)
        return self.rel(dst)

    # -- channels

    def scalar_map(self, d, kind):
        """(file, swizzle, inverted) for roughness / metallic / specular descriptors, or None."""
        if d.get("kind") == "baked":
            return self.link(d["path"]), 0, False
        if d.get("kind") != "file":
            return None
        path, ch = d["path"], d.get("channel")
        ok_format = path.lower().endswith(D3DX_EXT)
        if ch == "lum":
            im = read_image(path)
            if im is None:
                return None
            a = np.asarray(im.convert("RGB"), dtype=np.int16)
            grey = np.abs(a[..., 0] - a[..., 1]).max() <= 2 and np.abs(a[..., 0] - a[..., 2]).max() <= 2
            ch = 0 if grey else None
        if ch is not None and ok_format and d.get("colorspace") != "sRGB":
            return self.link(path), int(ch), bool(d.get("invert"))
        key = "%s_%s_%s" % (ascii_slug(os.path.splitext(os.path.basename(path))[0]), kind,
                            hashlib.md5(json.dumps(d, sort_keys=True).encode()).hexdigest()[:6])

        def make():
            im = read_image(path)
            if im is None:
                return None
            v = channel_array(dict(d, invert=False), im.size)
            return Image.fromarray((np.clip(v, 0, 1) * 255 + 0.5).astype(np.uint8), "L")
        rel = self.derived(key, make)
        return (rel, 0, bool(d.get("invert"))) if rel else None

    def normal_map(self, d):
        if d.get("kind") == "baked":
            return self.link(d["path"]), 1.0
        if d.get("kind") != "file":
            return None
        path = d["path"]
        if not d.get("flip_g") and path.lower().endswith(D3DX_EXT):
            return self.link(path), float(d.get("strength", 1.0))
        key = ascii_slug(os.path.splitext(os.path.basename(path))[0]) + ("_flipg" if d.get("flip_g") else "_n")

        def make():
            im = read_image(path)
            if im is None:
                return None
            a = np.asarray(im.convert("RGB"), dtype=np.uint8).copy()
            if d.get("flip_g"):
                a[..., 1] = 255 - a[..., 1]
            return Image.fromarray(a, "RGB")
        rel = self.derived(key, make)
        return (rel, float(d.get("strength", 1.0))) if rel else None

    # -- one material

    def write_fx(self, index, mat, model, cls, row):
        t = self.template
        tex = tex_path(model, mat.texture)
        diffuse = [float(x) for x in mat.diffuse]
        notes = []
        if tex and os.path.isfile(tex):
            t = set_define(t, "ALBEDO_MAP_FROM", 3)
            tinted = max(diffuse[:3]) - min(diffuse[:3]) > 0.02 or min(diffuse[:3]) < 0.75
            t = set_define(t, "ALBEDO_MAP_APPLY_DIFFUSE", 1 if tinted else 0)
            t = set_define(t, "ALPHA_MAP_FROM", 3)
        else:
            lin = [x ** 2.2 for x in diffuse[:3]]
            t = set_define(t, "ALBEDO_MAP_FROM", 0)
            t = set_const(t, "albedo", "float3(%.4f, %.4f, %.4f)" % tuple(lin))
            t = set_define(t, "ALPHA_MAP_FROM", 0)
            t = set_const(t, "alpha", "%.4f" % diffuse[3])
        preset = RAY_PRESETS[cls]
        ch = (row or {}).get("channels") or {}
        # normal
        nm = self.normal_map(ch.get("normal") or {})
        if nm:
            t = set_define(t, "NORMAL_MAP_FROM", 1)
            t = set_define(t, "NORMAL_MAP_FILE", '"%s"' % nm[0])
            t = set_const(t, "normalMapScale", "%.3f" % nm[1])
            notes.append("normal")
        # smoothness from roughness
        r = ch.get("roughness") or {}
        sm = self.scalar_map(r, "rough") if r.get("kind") in ("file", "baked") else None
        if sm:
            t = set_define(t, "SMOOTHNESS_MAP_FROM", 1)
            t = set_define(t, "SMOOTHNESS_MAP_FILE", '"%s"' % sm[0])
            t = set_define(t, "SMOOTHNESS_MAP_SWIZZLE", sm[1])
            # the map holds Blender roughness r (GGX alpha = r^2); ray-mmd: alpha = (1 - smoothness)^2 -> 1 - r.
            # A 1 - x in front of it means the file holds smoothness (gloss) already.
            t = set_define(t, "SMOOTHNESS_MAP_TYPE", 0 if sm[2] else 2)
            notes.append("roughness map")
        else:
            value = 1.0 - float(r["value"]) if r.get("kind") == "const" else preset["smoothness"]
            t = set_define(t, "SMOOTHNESS_MAP_FROM", 0)
            t = set_const(t, "smoothness", "%.3f" % value)
        # metalness
        m = ch.get("metallic") or {}
        mm = self.scalar_map(m, "metal") if m.get("kind") in ("file", "baked") else None
        if mm and mm[2]:
            key = "%s_metal_inv" % ascii_slug(os.path.splitext(os.path.basename(m["path"]))[0])
            rel = self.derived(key, lambda: Image.fromarray(
                (np.clip(channel_array(m, read_image(m["path"]).size), 0, 1) * 255 + 0.5).astype(np.uint8), "L"))
            mm = (rel, 0, False) if rel else None
        if mm:
            t = set_define(t, "METALNESS_MAP_FROM", 1)
            t = set_define(t, "METALNESS_MAP_FILE", '"%s"' % mm[0])
            t = set_define(t, "METALNESS_MAP_SWIZZLE", mm[1])
            notes.append("metallic map")
        else:
            value = float(m["value"]) if m.get("kind") == "const" else preset["metalness"]
            t = set_define(t, "METALNESS_MAP_FROM", 0)
            t = set_const(t, "metalness", "%.3f" % value)
        # specular (Blender's Principled Specular is UE4's: F0 = 0.08 x)
        s = ch.get("specular") or {}
        sp = self.scalar_map(s, "spec") if s.get("kind") in ("file", "baked") else None
        if sp and not sp[2]:
            t = set_define(t, "SPECULAR_MAP_FROM", 1)
            t = set_define(t, "SPECULAR_MAP_TYPE", 2)
            t = set_define(t, "SPECULAR_MAP_FILE", '"%s"' % sp[0])
            t = set_define(t, "SPECULAR_MAP_SWIZZLE", sp[1])
            notes.append("specular map")
        else:
            value = float(s["value"]) if s.get("kind") == "const" else preset["specular"]
            t = set_const(t, "specular", "%.3f" % value)
        # emission
        e = ch.get("emission") or {}
        if e.get("kind") in ("file", "baked", "const"):
            t = set_define(t, "EMISSIVE_ENABLE", 1)
            if e["kind"] == "const":
                t = set_define(t, "EMISSIVE_MAP_FROM", 0)
                t = set_const(t, "emissive", "float3(%.4f, %.4f, %.4f)" % tuple(e["value"][:3]))
            else:
                t = set_define(t, "EMISSIVE_MAP_FROM", 1)
                t = set_define(t, "EMISSIVE_MAP_FILE", '"%s"' % self.link(e["path"]))
            strength = float(e.get("strength", 1.0)) if e["kind"] != "baked" else 1.0
            t = set_const(t, "emissiveIntensity", "%.3f" % strength)
            notes.append("emission")
        elif cls == "emissive":
            t = set_define(t, "EMISSIVE_ENABLE", 1)
            t = set_define(t, "EMISSIVE_MAP_FROM", 3)
            t = set_const(t, "emissiveIntensity", "1.0")
            notes.append("emission = texture")
        # shading model
        if preset["custom"] == 1:
            t = set_define(t, "CUSTOM_ENABLE", 1)
            t = set_const(t, "customA", "0.6")
            t = t.replace("const float3 customB = ",
                          "#define SSS_SKIN_TRANSMITTANCE(x) exp((1 - saturate(x)) * float3(-8, -40, -64))\n"
                          "const float3 customB = ", 1)
            t = set_const(t, "customB", "SSS_SKIN_TRANSMITTANCE(0.85)")
        head = "// PMX material %d (%s), kind %s - written by ripper_tpose scripts/pmx_tools/hq_materials\n" % (
            index, ascii_slug(mat.name), cls)
        name = "%02d_%s_%s.fx" % (index, cls, ascii_slug(mat.name)[-6:])
        with open(os.path.join(self.folder, name), "w", encoding="ascii", errors="replace", newline="\r\n") as f:
            f.write(head + t)
        return name, notes


def raymmd_dir(path, root=None):
    """Where a PMX's ray-mmd version goes: an ASCII-only folder.  MME looks files up through Japanese (CP932)
    conversions: on this Chinese Windows a model loaded from a folder named in Chinese shows up as mojibake in MME
    ("黑_全覆盖" -> "麷_慡暍岢") and its effect mapping fails ("Failed to load effect mapping for the following
    objects"), 11-14.  Archive PMX (E:\\game_export\\<Game>\\<Character>\\pmx\\<model>\\) go to
    <archive>\\_raymmd\\<Game>\\<ascii slug of character + model>\\, anything else to --raymmd-root or, when its own
    folder is ASCII, <pmx folder>\\ray_mmd\\."""
    folder = os.path.dirname(os.path.abspath(path))
    stem = os.path.splitext(os.path.basename(path))[0]
    parts = os.path.normpath(folder).split(os.sep)
    if root is None and len(parts) >= 5 and parts[-2].lower() == "pmx":
        root = os.path.join(os.sep.join(parts[:-4]), "_raymmd", parts[-4])
        return os.path.join(root, ascii_slug("%s_%s" % (parts[-3], stem)))
    if root:
        return os.path.join(root, ascii_slug(stem))
    if folder.isascii():
        return os.path.join(folder, PACK, ascii_slug(stem))
    raise RuntimeError("the PMX's folder is not ASCII: pass --raymmd-root <ASCII folder>")


def link_or_copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def stage_model(path, model, mirror):
    """model.pmx in the mirror folder: a hard link of the PMX plus hard links of its textures at the same relative
    paths (texture names may stay Chinese - MMD reads them, MME gets them from MMD); a rewritten copy with ASCII
    texture paths when a texture lies outside the PMX's folder."""
    folder = os.path.dirname(os.path.abspath(path))
    dst = os.path.join(mirror, "model.pmx")
    rels = []
    for t in model.textures:
        p = os.path.abspath(t.path)
        try:
            rel = os.path.relpath(p, folder)
        except ValueError:
            rel = None
        rels.append(rel if rel and not rel.startswith("..") else None)
    if all(r is not None for r in rels):
        for t, rel in zip(model.textures, rels):
            if os.path.isfile(t.path):
                link_or_copy(t.path, os.path.join(mirror, rel))
        if os.path.exists(dst):
            os.remove(dst)
        link_or_copy(os.path.abspath(path), dst)
        return dst, "hard link"
    m2 = pmx.load(path)
    for t in m2.textures:
        if os.path.isfile(t.path):
            base, ext = os.path.splitext(os.path.basename(t.path))
            new = os.path.join(mirror, "tex", ascii_slug(base) + ext.lower())
            link_or_copy(t.path, new)
            t.path = new
    pmx.save(dst, m2, add_uv_count=m2.header.additional_uvs)
    return dst, "copy with ASCII texture paths"


def write_emm(path, ray_x, model_pmx, pack_dir, fx_names):
    """MME's effect mapping file for one model: only the ray-mmd MaterialMap tab, per material (MME's "subset").
    The section syntax ([Effect@<offscreen>], Owner, Pmd<n>[<subset>]) is what MME 0.37 itself writes (File > Save
    in the Map Effect File dialog, 11-14); objects are matched by path, so the load order does not matter.  A per-model
    .emd cannot do this: MME reads only [Effect] (the Main tab) from it and stops at any other section."""
    # the skybox the README recommends is listed too: MME names every object of the scene that the .emm does not
    # describe in a "Failed to load effect mapping for the following objects" box
    ray = os.path.dirname(ray_x)
    sky = os.path.join(ray, "Skybox", "Helipad GoldenHour", "Sky with box.pmx")
    lines = ["[Info]", "Version = 3", "", "[Object]", "Acs1 = " + ray_x, "Pmd2 = " + sky, "Pmd3 = " + model_pmx, "",
             "[Effect]", "Default = none", "Pmd2 = " + os.path.splitext(sky)[0] + ".fx", "Pmd3 = none", "",
             "[Effect@MaterialMap]", "Owner = Acs1", "Acs1.show = false",
             "Pmd2 = " + os.path.join(ray, "Materials", "material_skybox.fx"),
             "Pmd3 = " + os.path.join(pack_dir, "_default.fx")]
    lines += ["Pmd3[%d] = %s" % (i, os.path.join(pack_dir, n)) for i, n in enumerate(fx_names)]
    text = "\n".join(lines) + "\n"
    if not text.isascii():
        raise RuntimeError("non-ASCII path in the .emm: %r" % [l for l in lines if not l.isascii()][:2])
    with open(path, "w", encoding="ascii", newline="\r\n") as f:
        f.write(text)


README_TXT = """ray-mmd version of {source}
made by ripper_tpose scripts/pmx_tools/hq_materials (docs/pmx-hq-materials.md)

model.pmx    the model ({how})
fx\\          one ray-mmd material per PMX material, from the game's own maps
scene.emm    MME effect mapping: every material -> its fx file
scene.pmm    (if present) an MMD scene with ray.x + skybox + model; open it and everything is set

In MMD (MME + ray-mmd installed):
  1. load ray-mmd's ray.x (accessory), a skybox (e.g. Skybox\\Helipad GoldenHour\\Sky with box.pmx), then model.pmx
  2. MMEffect > Effect Mapping > File > Open > scene.emm, then OK
  or just open scene.pmm.
"""


# ------------------------------------------------------------------ main

def process(path, args, values):
    folder = os.path.dirname(os.path.abspath(path))
    stem = os.path.splitext(os.path.basename(path))[0]
    res = {"file": path}
    model = pmx.load(path)
    blend = find_source_blend(path, args.blend)
    res["blend"] = blend
    work = tempfile.mkdtemp(prefix="hqmat_")
    mirror = raymmd_dir(path, args.raymmd_root) if "2" in args.steps else None
    pack_dir = os.path.join(mirror, "fx") if mirror else os.path.join(work, "fx")
    extract = None
    if blend and "2" in args.steps or (blend and not args.no_measure):
        if args.dry_run:
            res["extract"] = "dry run"
        else:
            os.makedirs(os.path.join(pack_dir, "baked"), exist_ok=True)
            extract = run_extract(blend, model, work, os.path.join(pack_dir, "baked"), args.blender,
                                  os.path.join(work, "extract.log"))
            res["extract"] = {"matched": sum(1 for r in extract["materials"] if r.get("blend_material")),
                              "materials": len(extract["materials"])}
    stats = measure(model, extract)
    rows = {r["index"]: r for r in (extract or {}).get("materials", [])}
    classes = []
    for i, mat in enumerate(model.materials):
        row = rows.get(i) or {}
        cls, why = classify(mat.name, tex_path(model, mat.texture), stats.get(i), row.get("hints") or {})
        classes.append({"index": i, "name": mat.name, "class": cls, "why": why, "stats": stats.get(i),
                        "blend_material": row.get("blend_material"), "match": row.get("match")})
    res["materials"] = classes
    if args.dry_run:
        return res
    if "1" in args.steps:
        shared = shared_images(os.path.join(folder, SHARED), values)
        model1 = pmx.load(path)
        res["step1"] = step1(model1, classes, values, shared, args.force)
        out = os.path.join(folder, stem + args.suffix + ".pmx")
        tmp = out + ".tmp"
        pmx.save(tmp, model1, add_uv_count=model1.header.additional_uvs)
        pmx.load(tmp)
        os.replace(tmp, out)
        res["pmx"] = out
    if "2" in args.steps:
        pack = Pack(pack_dir, args.ray_mmd)
        fx_names, notes = [], {}
        for i, mat in enumerate(model.materials):
            name, n = pack.write_fx(i, mat, model, classes[i]["class"], rows.get(i))
            fx_names.append(name)
            notes[i] = n
        with open(os.path.join(pack_dir, "_default.fx"), "w", encoding="ascii", errors="replace",
                  newline="\r\n") as f:
            f.write(pack.template)
        model_pmx, how = stage_model(path, model, mirror)
        emm = os.path.join(mirror, "scene.emm")
        write_emm(emm, os.path.join(args.ray_mmd, "ray.x"), model_pmx, pack_dir, fx_names)
        with open(os.path.join(mirror, "README.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
            f.write(README_TXT.format(source=os.path.abspath(path), how=how))
        with open(os.path.join(pack_dir, "pack.json"), "w", encoding="utf-8") as f:
            json.dump({"source": os.path.abspath(path), "materials": [m.name for m in model.materials],
                       "classes": [c["class"] for c in classes], "blend": blend, "fx": fx_names, "notes": notes,
                       "ray_mmd": args.ray_mmd, "model": how}, f, ensure_ascii=False, indent=1)
        res["raymmd_dir"] = mirror
        res["raymmd_pmx"] = model_pmx
        res["emm"] = emm
        res["ray_notes"] = notes
    if extract:
        shutil.copyfile(os.path.join(work, "extract.json"), os.path.join(pack_dir, "extract.json"))
        shutil.copyfile(os.path.join(work, "extract.log"), os.path.join(pack_dir, "extract.log"))
    shutil.rmtree(work, ignore_errors=True)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--blend", help="the PMX's source .blend (default: found next to it)")
    ap.add_argument("--suffix", default=SUFFIX)
    ap.add_argument("--steps", default="1,2", help="1 = MMD toon / sphere / specular / edge, 2 = ray-mmd pack")
    ap.add_argument("--force", action="store_true", help="also re-do materials that have their own toon / sphere")
    ap.add_argument("--no-measure", action="store_true", help="step 1 by names only (no Blender run)")
    ap.add_argument("--dry-run", action="store_true", help="classify and print, write nothing")
    ap.add_argument("--values", help="JSON overriding DEFAULT_VALUES per kind")
    ap.add_argument("--blender", default=BLENDER)
    ap.add_argument("--ray-mmd", default=RAY_MMD)
    ap.add_argument("--raymmd-root", help="ASCII folder for the ray-mmd versions (default: <archive>\\_raymmd\\<Game>)")
    ap.add_argument("--report")
    args = ap.parse_args()
    values = json.loads(json.dumps(DEFAULT_VALUES))
    if args.values:
        for cls, over in json.load(open(args.values, encoding="utf-8")).items():
            values.setdefault(cls, {}).update(over)
    files = []
    for p in args.inputs:
        if os.path.isdir(p):
            files += [f for f in sorted(glob.glob(os.path.join(p, "**", "*.pmx"), recursive=True))
                      if not os.path.splitext(f)[0].endswith((args.suffix, RAY_SUFFIX))]
        else:
            files.append(p)
    results = []
    for f in files:
        try:
            r = process(f, args, values)
        except Exception as exc:  # noqa: BLE001 - one broken model must not stop a batch
            r = {"file": f, "error": repr(exc)}
        results.append(r)
        if "error" in r:
            print("ERROR %s: %s" % (f, r["error"]), flush=True)
            continue
        kinds = {}
        for m in r["materials"]:
            kinds[m["class"]] = kinds.get(m["class"], 0) + 1
        print("%s | blend %s | %s" % (os.path.basename(f), os.path.basename(r.get("blend") or "-"),
                                      ", ".join("%s %d" % kv for kv in sorted(kinds.items()))), flush=True)
        for m in r["materials"]:
            st = {k: v for k, v in (m.get("stats") or {}).items() if isinstance(v, float)}
            print("   %2d %-40s %-10s %s | %s" % (m["index"], m["name"][:40], m["class"], "; ".join(m["why"]),
                                              " ".join("%s=%.2f" % kv for kv in st.items())), flush=True)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
    print("HQ_MATERIALS=" + json.dumps({"files": len(files), "errors": sum(1 for r in results if "error" in r)}))


if __name__ == "__main__":
    main()
