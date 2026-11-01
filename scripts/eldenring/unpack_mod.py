# -*- coding: utf-8 -*-
"""Elden Ring character mod (Nexus zip or its unpacked folder) -> one work folder that build_blend.py turns into a
.blend: every part's model in Blender axes, one merged skeleton, materials and full-size textures.

    python unpack_mod.py <mod.zip | mod folder> --out <work dir> [--parts hd_m_1810,bd_m_1810,...]
           [--weapon-hand R|L|none] [--gloss-from normal-blue|none]

What a mod ships (Mod Engine 2 layout): parts/<kind>_<sex>_<id>.partsbnd.dcx - hd (head), bd (body), am (arms),
lg (legs), fc / hr (face / hair), wp (weapon) - each a BND4 holding <name>.flver + <name>.tpf (+ Havok cloth
_c.hkx / .clm2, which a .blend cannot use); material/allmaterial.matbinbnd.dcx when the mod adds materials.

Game -> Blender: Elden Ring is left-handed, Y up, a character faces -Z with her left side at +X; Blender wants Z up,
facing -Y, left at +X: (x, y, z) -> (x, z, y), a mirror, so every triangle's winding is turned (and checked against
the vertex normals).  Units are metres already.  UV v -> 1 - v (DirectX top-left origin).

Skeleton: the parts carry the same ~410-bone player skeleton (identical transforms, checked) plus helper rigs
(Ctrl_*, Rig_*, LinkNode_*, ...) and one node per mesh; kept are the bones some vertex is weighted to, their
parents, and the body skeleton (spine, limbs, fingers, twist bones).  Spine and Pelvis are roots in the FLVER (the
game joins them in its Havok skeleton): Spine is hung under Pelvis.  Weights are normalised per vertex (mods often
ship them summing to 0.5-1.9; the game normalises in its shader).

Textures (DDS in the TPF, decoded by Pillow, full size): <tex>.png as stored, and for Blender
  <normal>_nrm.png    OpenGL tangent normal: the game's maps are DirectX (green down) and keep the GLOSS in blue,
                      so blue is rebuilt from red / green
  <normal>_rough.png  roughness = 1 - the normal map's blue (gloss); --gloss-from none leaves roughness constant
  <metallic>_metal.png  metallic = the _m map's red
A weapon (wp_*) is put in the right hand (--weapon-hand): the blade along the line from the little finger to the
index finger, the grip in the palm - the game's own hold comes from its animation skeleton, which mods do not ship.

Writes <out>/model.json, <out>/model.npz, <out>/textures/.  Prints ER_UNPACK={json}.
"""
import argparse
import io
import json
import os
import re
import shutil
import struct
import sys
import time
import zipfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fromsoft as fs  # noqa: E402

PART_KIND = {"hd": "头部", "bd": "身体", "am": "手臂", "lg": "腿部", "fc": "脸", "hr": "头发", "wp": "武器"}
EYE_LIKE = re.compile(r"eye|iris|pupil|瞳|目", re.IGNORECASE)
BODY_BONE = re.compile(r"^(Master|Pelvis|Spine\d?|Neck|Head|[LR]_(Clavicle|UpperArm|UpArmTwist\d?|Forearm|"
                       r"ForeArmTwist\d?|Hand|Finger\d+|Pectoral|Thigh|ThighTwist\d?|Calf|CalfTwist\d?|Foot|"
                       r"FootTwist|Toe0))$")
P = np.array([[1, 0, 0], [0, 0, 1], [0, 1, 0]], dtype=np.float64)      # game -> Blender (a mirror)


def g2b(v):
    v = np.asarray(v, dtype=np.float64)
    return v[..., [0, 2, 1]]


# ------------------------------------------------------------------------------------------------- mod files
class ModSource:
    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if path.lower().endswith(".zip") else None

    def names(self):
        if self.zip:
            return [n for n in self.zip.namelist() if not n.endswith("/")]
        out = []
        for root, _d, files in os.walk(self.path):
            out += [os.path.relpath(os.path.join(root, f), self.path).replace("\\", "/") for f in files]
        return out

    def read(self, name):
        if self.zip:
            return self.zip.read(name)
        with open(os.path.join(self.path, name), "rb") as fh:
            return fh.read()


def part_files(src, only=None):
    out = []
    for n in sorted(src.names()):
        m = re.search(r"(?:^|/)parts/((hd|bd|am|lg|fc|hr|wp)_[a-z]_\d+)\.partsbnd\.dcx$", n, re.IGNORECASE)
        if m and (not only or m.group(1).lower() in only):
            out.append((m.group(1).lower(), m.group(2).lower(), n))
    return out


# ------------------------------------------------------------------------------------------------- textures
def tex_key(path):
    return os.path.splitext(os.path.basename(path.replace("\\", "/")))[0].lower()


TEXCONV = os.environ.get("TEXCONV", r"E:\tools\directxtex\texconv.exe")
DXGI_BC6H = (94, 95, 96)
DXGI_SRGB = (29, 72, 75, 78, 91, 93, 99)


def dds_dxgi(body):
    return struct.unpack_from("<I", body, 128)[0] if body[84:88] == b"DX10" else None


def decode_float(body, name, scratch):
    """BC6H -> float32 HxWx4 through texconv (Pillow clamps BC6H to 8 bits and drops negative / HDR values)."""
    import subprocess
    os.makedirs(scratch, exist_ok=True)
    src = os.path.join(scratch, name + ".dds")
    with open(src, "wb") as fh:
        fh.write(body)
    out_dir = os.path.join(scratch, "f")
    os.makedirs(out_dir, exist_ok=True)
    subprocess.run([TEXCONV, "-nologo", "-y", "-f", "R32G32B32A32_FLOAT", "-m", "1", "-ft", "dds", "-o", out_dir, src],
                   capture_output=True, check=False)
    out = os.path.join(out_dir, name + ".dds")
    with open(out, "rb") as fh:
        b = fh.read()
    h, w = struct.unpack_from("<II", b, 12)
    off = 148 if b[84:88] == b"DX10" else 128
    arr = np.frombuffer(b, dtype="<f4", count=w * h * 4, offset=off).reshape(h, w, 4).copy()
    os.remove(src)
    os.remove(out)
    return arr


def lin_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def srgb_to_lin(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def to8(x):
    return (np.clip(x, 0, 1) * 255 + 0.5).astype(np.uint8)


def save_textures(tpf, tex_dir, gloss, log):
    """Every texture as PNG + the maps Blender needs.  BC6H (half float) textures are read as floats: the game samples
    them without an sRGB decode, so a colour map's values ARE linear colour - written sRGB-encoded here, so the PNG
    shows what the game shows; a BC6H normal map is signed (0 = flat, not 0.5)."""
    done = {}
    scratch = os.path.join(tex_dir, "_dds")
    for name, _fmt, body in tpf.textures:
        key = name.lower()
        png = os.path.join(tex_dir, name + ".png")
        dxgi = dds_dxgi(body)
        is_float = dxgi in DXGI_BC6H and os.path.isfile(TEXCONV)
        if is_float:
            arr = decode_float(body, name, scratch)                    # HxWx4 float, raw values
        else:
            im = Image.open(io.BytesIO(body))
            im.load()
            arr = np.asarray(im.convert("RGBA"), dtype=np.float32) / 255.0
            if im.mode != "RGBA":
                arr[:, :, 3] = 1.0
        info = {"file": name + ".png", "size": [arr.shape[1], arr.shape[0]], "dxgi": dxgi,
                "encoding": "bc6h-linear" if is_float else ("srgb" if dxgi in DXGI_SRGB else "unorm")}
        info["alpha"] = bool(arr[:, :, 3].min() < 0.98)
        colour = key.endswith("_a")
        if colour and is_float:
            rgb = lin_to_srgb(arr[:, :, :3])
        else:
            rgb = np.clip(arr[:, :, :3], 0, 1)
        if info["alpha"]:
            Image.fromarray(to8(np.dstack([rgb, arr[:, :, 3]])), "RGBA").save(png)
        else:
            Image.fromarray(to8(rgb), "RGB").save(png)
        if key.endswith("_n"):
            if is_float:                                           # signed: the value is the component
                x, y = arr[:, :, 0], arr[:, :, 1]
            else:
                x, y = arr[:, :, 0] * 2 - 1, arr[:, :, 1] * 2 - 1
            y = -y                                                 # DirectX (green down) -> OpenGL
            z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
            Image.fromarray(to8(np.stack([x, y, z], -1) * 0.5 + 0.5), "RGB").save(os.path.join(tex_dir, name + "_nrm.png"))
            info["nrm"] = name + "_nrm.png"
            # the same with green down (DirectX), for XPS - its shaders read normal maps the DirectX way
            Image.fromarray(to8(np.stack([x, -y, z], -1) * 0.5 + 0.5), "RGB").save(os.path.join(tex_dir, name + "_nrm_dx.png"))
            info["nrm_dx"] = name + "_nrm_dx.png"
            if gloss == "normal-blue":
                g = np.clip(arr[:, :, 2], 0, 1)
                Image.fromarray(to8(1.0 - g), "L").save(os.path.join(tex_dir, name + "_rough.png"))
                info["rough"] = name + "_rough.png"
                info["gloss_mean"] = round(float(g.mean()), 3)
        if key.endswith("_m"):
            r = np.clip(arr[:, :, 0], 0, 1)
            Image.fromarray(to8(r), "L").save(os.path.join(tex_dir, name + "_metal.png"))
            info["metal"] = name + "_metal.png"
            info["metal_mean"] = round(float(r.mean()), 3)
        done[key] = info
        log.append("texture %s dxgi %s %dx%d" % (name, dxgi, arr.shape[1], arr.shape[0]))
    if os.path.isdir(scratch):
        shutil.rmtree(scratch, ignore_errors=True)
    return done


def tint_texture(tex_dir, info, hex_colour, out_name):
    """Re-colour a colour map to one measured colour, keeping its own light / dark pattern (relative luminance in
    linear light; the alpha stays).  For shaders that colour a near-black map in the game (Elden Ring's fur / hair
    'Beast' shader), whose formula a .blend cannot copy."""
    im = Image.open(os.path.join(tex_dir, info["file"])).convert("RGBA")
    a = np.asarray(im, dtype=np.float32) / 255.0
    lin = srgb_to_lin(a[:, :, :3])
    lum = lin @ np.array([0.2126, 0.7152, 0.0722])
    sel = a[:, :, 3] > 0.5 if info.get("alpha") else np.ones(lum.shape, bool)
    mean = float(lum[sel].mean()) if sel.any() else float(lum.mean())
    target = srgb_to_lin(np.array([int(hex_colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]))
    rel = np.clip(lum / max(mean, 1e-6), 0.25, 2.5)[:, :, None]
    rgb = lin_to_srgb(target[None, None, :] * rel)
    Image.fromarray(to8(np.dstack([rgb, a[:, :, 3]])), "RGBA").save(os.path.join(tex_dir, out_name))
    return out_name


def glow_texture(tex_dir, info, out_name):
    """Emission map for the lit cyan / blue lamps of a colour map (saturated blue that outshines red): the game's
    glow comes from its shader, the colour map only shows where the lamps are.  None when there are none."""
    a = np.asarray(Image.open(os.path.join(tex_dir, info["file"])).convert("RGB"), dtype=np.float32) / 255.0
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    m = np.clip((b - r - 0.12) / 0.2, 0, 1) * np.clip((b - 0.25) / 0.2, 0, 1)
    frac = float((m > 0.5).mean())
    if frac < 1e-5 or frac > 0.08:
        return None, frac
    Image.fromarray(to8(a * m[:, :, None]), "RGB").save(os.path.join(tex_dir, out_name))
    return out_name, frac


ROLE = [("albedo", re.compile(r"AlbedoMap", re.I)), ("normal", re.compile(r"NormalMap", re.I)),
        ("metallic", re.compile(r"MetallicMap", re.I)), ("emissive", re.compile(r"EmissiveMap", re.I))]


def material_slots(mat, matbins):
    """{role: texture key}: the FLVER's own paths first, the MATBIN's samplers for the empty ones."""
    slots = {}
    pairs = [(t["type"], t["path"]) for t in mat.textures]
    mb = matbins.get(os.path.basename(mat.mtd.replace("\\", "/")).lower().replace(".matxml", ".matbin")
                     .replace(".mtd", ".matbin"))
    if mb is not None:
        pairs += [(s, p) for s, p, _u in mb.samplers]
    for typ, path in pairs:
        if not path:
            continue
        for role, rx in ROLE:
            if role not in slots and rx.search(typ):
                slots[role] = tex_key(path)
    return slots


# ------------------------------------------------------------------------------------------------- skeleton
def merged_skeleton(flvers, weighted):
    """-> list of dicts (name, parent index, world 4x4 in game axes) for the kept bones, and a name -> index map."""
    first = {}
    for f in flvers:
        _loc, world = f.bone_matrices()
        for i, b in enumerate(f.bones):
            if b.name not in first:
                first[b.name] = (b, world[i], f)
    keep = set(weighted) | {n for n in first if BODY_BONE.match(n)}
    parent_of = {}
    for n, (b, _w, f) in first.items():
        parent_of[n] = f.bones[b.parent].name if b.parent >= 0 else None
    parent_of["Spine"] = "Pelvis" if "Pelvis" in first else parent_of.get("Spine")
    parent_of["Pelvis"] = "Master" if "Master" in first else None
    changed = True
    while changed:
        changed = False
        for n in list(keep):
            p = parent_of.get(n)
            if p and p not in keep:
                keep.add(p)
                changed = True
    order, seen = [], set()

    def visit(n):
        if n in seen:
            return
        p = parent_of.get(n)
        if p in keep:
            visit(p)
        seen.add(n)
        order.append(n)
    for n in [b.name for f in flvers for b in f.bones]:
        if n in keep:
            visit(n)
    index = {n: i for i, n in enumerate(order)}
    bones = []
    for n in order:
        b, w, _f = first[n]
        p = parent_of.get(n)
        bones.append({"name": n, "parent": index[p] if p in index else -1, "world_game": w})
    return bones, index


def to_blender_bone(world):
    head = g2b(world[:3, 3])
    axes = [P @ world[:3, k] for k in range(3)]
    return head, axes


# ------------------------------------------------------------------------------------------------- weapon
def weapon_matrix(skel_world, hand="R"):
    """Game-space 4x4 placing a weapon's model space in the hand: blade (-Y) along little -> index finger."""
    def pos(n):
        return skel_world[n][:3, 3]
    hand_m = skel_world[hand + "_Hand"]
    index, little = pos(hand + "_Finger1"), pos(hand + "_Finger4")
    blade = index - little
    blade /= np.linalg.norm(blade)
    fingers = (pos(hand + "_Finger2") - pos(hand + "_Hand"))
    fingers -= blade * fingers.dot(blade)
    fingers /= np.linalg.norm(fingers)
    palm = np.cross(blade, fingers)
    # the palm side: the hand's Z axis points out of the palm in the rest A-pose (checked on c0000)
    if palm.dot(hand_m[:3, 2]) < 0:
        palm = -palm
    y_w = -blade                                   # weapon +Y = pommel side
    x_w = fingers
    z_w = np.cross(x_w, y_w)
    R = np.stack([x_w, y_w, z_w], 1)
    grip = (pos(hand + "_Hand") * 0.35 + (index + little) * 0.5 * 0.65) + palm * 0.025
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = grip - R @ np.array([0.0, 0.10, 0.0])   # hold 10 cm above the guard
    return M


# ------------------------------------------------------------------------------------------------- main work
def unpack(src_path, out, parts_only=None, weapon_hand="R", gloss="normal-blue", tints=None, glow=True):
    t0 = time.time()
    src = ModSource(src_path)
    tex_dir = os.path.join(out, "textures")
    os.makedirs(tex_dir, exist_ok=True)
    log = []
    matbins = {}
    for n in src.names():
        if n.lower().endswith(".matbinbnd.dcx"):
            for _i, name, body, _f in fs.BND4(fs.dcx_decompress(src.read(n))[0]).entries:
                if body:
                    matbins[os.path.basename(name.replace("\\", "/")).lower()] = fs.MATBIN(body)
    files = part_files(src, parts_only)
    if not files:
        raise SystemExit("no parts/*.partsbnd.dcx in %s" % src_path)
    parts, textures = [], {}
    for pid, kind, n in files:
        bnd = fs.BND4(fs.dcx_decompress(src.read(n))[0])
        flv = [b for _i, nm, b, _f in bnd.entries if nm and nm.lower().endswith(".flver")]
        tpf = [b for _i, nm, b, _f in bnd.entries if nm and nm.lower().endswith(".tpf")]
        if not flv:
            log.append("%s: no flver, skipped" % pid)
            continue
        f = fs.FLVER(flv[0])
        if tpf:
            textures.update(save_textures(fs.TPF(tpf[0]), tex_dir, gloss, log))
        parts.append({"id": pid, "kind": kind, "file": n, "flver": f,
                      "extras": [nm for _i, nm, _b, _f in bnd.entries if nm and not nm.lower().endswith((".flver", ".tpf"))]})
    body_parts = [p for p in parts if p["kind"] != "wp"]
    weighted = set()
    for p in body_parts:
        f = p["flver"]
        for m in f.meshes:
            W, B = m.attrs.get("weights"), m.attrs.get("bones")
            if W is None:
                continue
            used = np.unique(B[W > 0])
            weighted |= {f.bones[i].name for i in used if 0 <= i < len(f.bones)}
    skel, sindex = merged_skeleton([p["flver"] for p in body_parts], weighted)
    skel_world = {b["name"]: b["world_game"] for b in skel}
    # check: same-name bones agree between parts
    worst = 0.0
    for p in body_parts:
        _l, w = p["flver"].bone_matrices()
        for i, b in enumerate(p["flver"].bones):
            if b.name in skel_world:
                worst = max(worst, float(np.abs(w[i] - skel_world[b.name]).max()))
    meshes, arrays, materials = [], {}, {}
    weapon_bones = []
    glow_done = {}
    for p in parts:
        f = p["flver"]
        is_weapon = p["kind"] == "wp"
        wmat = None
        if is_weapon:
            if weapon_hand == "none" or "R_Hand" not in skel_world:
                wmat = np.eye(4)
            else:
                wmat = weapon_matrix(skel_world, weapon_hand)
            wname = p["id"].upper()
            weapon_bones.append({"name": wname, "parent_name": (weapon_hand + "_Hand") if weapon_hand != "none" else None,
                                 "world_game": wmat})
        seen_geo = {}
        for mi, m in enumerate(f.meshes):
            a = m.attrs
            pos = a["position"].astype(np.float64)
            if is_weapon:
                pos = (wmat[:3, :3] @ pos.T).T + wmat[:3, 3]
            sig = (m.material, m.vertex_count, round(float(pos.sum()), 4), len(m.faces))
            if sig in seen_geo:
                log.append("%s mesh %d = mesh %d (same material, same vertices): left out" % (p["id"], mi, seen_geo[sig]))
                continue
            seen_geo[sig] = mi
            mat = f.materials[m.material]
            mkey = "%s|%s" % (p["id"], mat.name)
            if mkey not in materials:
                slots = material_slots(mat, matbins)
                cull = any(fs_["cull"] for fs_ in m.face_sets if fs_["flags"] == 0)
                tx = {r: dict(textures[k]) for r, k in slots.items() if k in textures}
                alb = tx.get("albedo")
                tint = next((c for n_, c in (tints or {}).items() if n_.lower() == mat.name.lower()), None)
                if alb and tint:
                    alb["file"] = tint_texture(tex_dir, alb, tint, os.path.splitext(alb["file"])[0] + "_tint.png")
                    alb["tinted"] = tint
                    log.append("%s: colour map re-coloured to %s (--tint)" % (mat.name, tint))
                if alb and glow and not EYE_LIKE.search(mat.name):
                    gkey = os.path.splitext(textures[slots["albedo"]]["file"])[0] + "_glow.png"
                    if gkey not in glow_done:
                        glow_done[gkey] = glow_texture(tex_dir, textures[slots["albedo"]], gkey)
                    gfile, frac = glow_done[gkey]
                    if gfile:
                        tx["emission"] = {"file": gfile, "lamp_fraction": round(frac, 5)}
                materials[mkey] = {"name": mat.name, "part": p["id"], "shader": os.path.basename(mat.mtd.replace("\\", "/")),
                                   "slots": slots, "textures": tx, "backface_culling": bool(cull)}
            nrm = a["normal"].astype(np.float64)
            if is_weapon:
                nrm = (wmat[:3, :3] @ nrm.T).T
            V = g2b(pos)
            N = g2b(nrm)
            N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
            tri = m.faces[:, [0, 2, 1]].astype(np.int32)              # mirror -> turn the winding
            # check against the vertex normals; turn back if most faces disagree
            fn = np.cross(V[tri[:, 1]] - V[tri[:, 0]], V[tri[:, 2]] - V[tri[:, 0]])
            agree = float(((fn * (N[tri[:, 0]] + N[tri[:, 1]] + N[tri[:, 2]])).sum(1) > 0).mean()) if len(tri) else 1.0
            if agree < 0.5:
                tri = tri[:, [0, 2, 1]]
                agree = 1 - agree
            if is_weapon:
                bix = np.zeros((len(V), 4), dtype=np.int32)
                wgt = np.zeros((len(V), 4), dtype=np.float32)
                wgt[:, 0] = 1.0
                bnames = [weapon_bones[-1]["name"]]
            else:
                W = a["weights"].astype(np.float64)
                Bi = a["bones"]
                if m.bone_indices:
                    Bi = np.asarray(m.bone_indices)[Bi]
                s = W.sum(1, keepdims=True)
                W = np.where(s > 0, W / np.maximum(s, 1e-9), 0)
                names = [b.name for b in f.bones]
                # merge duplicate bone slots, map to merged skeleton
                bnames = sorted({names[i] for i in np.unique(Bi[W > 0])})
                local = {n: k for k, n in enumerate(bnames)}
                bix = np.vectorize(lambda i: local.get(names[i], 0))(Bi).astype(np.int32)
                wgt = W.astype(np.float32)
            uvs = [np.stack([u[:, 0], 1.0 - u[:, 1]], 1).astype(np.float32) for u in a["uv"][:2]]
            mid = "m%03d" % len(meshes)
            arrays[mid + "_pos"] = V.astype(np.float32)
            arrays[mid + "_nrm"] = N.astype(np.float32)
            arrays[mid + "_tri"] = tri
            arrays[mid + "_bix"] = bix
            arrays[mid + "_wgt"] = wgt
            for k, u in enumerate(uvs):
                arrays[mid + "_uv%d" % k] = u
            if a["color"]:
                arrays[mid + "_col"] = a["color"][0].astype(np.float32)
            meshes.append({"id": mid, "name": mat.name, "part": p["id"], "kind": p["kind"], "material": mkey,
                           "vertices": int(len(V)), "triangles": int(len(tri)), "uv_sets": len(uvs),
                           "bone_names": bnames, "winding_agrees": round(agree, 3), "dynamic": int(m.dynamic)})
    bones_out = []
    for b in skel:
        head, axes = to_blender_bone(b["world_game"])
        bones_out.append({"name": b["name"], "parent": skel[b["parent"]]["name"] if b["parent"] >= 0 else None,
                          "head": head.tolist(), "x": axes[0].tolist(), "y": axes[1].tolist(), "z": axes[2].tolist()})
    for wb in weapon_bones:
        head, axes = to_blender_bone(wb["world_game"])
        bones_out.append({"name": wb["name"], "parent": wb["parent_name"], "head": head.tolist(),
                          "x": axes[0].tolist(), "y": axes[1].tolist(), "z": axes[2].tolist(), "weapon": True})
    model = {"source": os.path.abspath(src_path), "parts": [{"id": p["id"], "kind": p["kind"],
             "label": PART_KIND.get(p["kind"], p["kind"]), "file": p["file"], "extras": p["extras"],
             "flver_version": hex(p["flver"].version), "bones_in_file": len(p["flver"].bones)} for p in parts],
             "bones": bones_out, "materials": materials, "meshes": meshes, "textures": textures,
             "gloss_from": gloss, "weapon_hand": weapon_hand, "bone_transform_mismatch": worst,
             "tints": tints or {}, "glow": glow}
    with open(os.path.join(out, "model.json"), "w", encoding="utf-8") as fh:
        json.dump(model, fh, ensure_ascii=False, indent=1)
    np.savez_compressed(os.path.join(out, "model.npz"), **arrays)
    summary = {"out": out, "parts": [p["id"] for p in parts], "bones": len(bones_out), "meshes": len(meshes),
               "materials": len(materials), "textures": len(textures), "vertices": sum(m["vertices"] for m in meshes),
               "triangles": sum(m["triangles"] for m in meshes), "bone_transform_mismatch": worst,
               "seconds": round(time.time() - t0, 1), "log": [x for x in log if not x.startswith("texture")]}
    return summary


def main(argv):
    ap = argparse.ArgumentParser(description="Elden Ring mod -> work folder for build_blend.py")
    ap.add_argument("mod", help="the mod's zip or unpacked folder (holding parts/ and material/)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--parts", default="", help="comma list of part ids (hd_m_1810,...); default all")
    ap.add_argument("--weapon-hand", default="R", choices=("R", "L", "none"))
    ap.add_argument("--gloss-from", default="normal-blue", choices=("normal-blue", "none"))
    ap.add_argument("--tint", action="append", default=[], metavar="MATERIAL=#RRGGBB",
                    help="re-colour one material's colour map (keeps its light / dark pattern); repeatable")
    ap.add_argument("--no-glow", action="store_true", help="no emission maps for the cyan / blue lamps")
    args = ap.parse_args(argv)
    only = {s.strip().lower() for s in args.parts.split(",") if s.strip()} or None
    tints = dict(t.split("=", 1) for t in args.tint)
    summary = unpack(args.mod, args.out, only, args.weapon_hand, args.gloss_from, tints, not args.no_glow)
    print("ER_UNPACK=" + json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
