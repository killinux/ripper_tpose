# -*- coding: utf-8 -*-
"""Blender side of hq_materials: where each PMX material's game (PBR) inputs come from in its source .blend.

    blender -b <source.blend> --python extract_pbr_blender.py -- --request <request.json> --out <result.json>
            --bake-dir <folder> [--bake-size 0] [--bake-cap 2048] [--no-bake]

request.json is written by make_hq_materials.py:
    {"materials": [{"index": 0, "name": "<PMX material name>", "texture": "<PMX texture file name>"}, ...],
     "strip_prefixes": ["HQ_"]}

For every PMX material the script finds the Blender material it came from (same name; the name with a prefix such as
ROE's "HQ_" removed; or the material whose image is the PMX texture) and reads the Principled BSDF of that material -
also when mmd_tools has put its own MMD shader in front of it (the *_converted.blend files keep the game node tree):

  * Normal, Roughness, Metallic, Specular, Emission (colour x strength) and a few hints (Subsurface, Sheen,
    Clearcoat, Transmission, Alpha);
  * each input is a constant, or "file": an image read straight through the PMX's UV map (one channel of it, maybe
    inverted with 1 - x, a normal map with its green channel flipped by a Separate / 1 - G / Combine chain);
  * anything else (math on several images, a mapping node, another UV map, a node group, a bump node) is baked by
    Cycles on the material's UV layout into --bake-dir: EMIT for scalars and colours, NORMAL (tangent space, OpenGL
    green = the convention ray-mmd and Blender share) for the normal.

result.json: {"blend": ..., "uv": ..., "materials": [{"index", "name", "blend_material", "match", "channels", "hints"}]}
Prints HQ_EXTRACT=<summary json> at the end.
"""
import json
import os
import re
import sys

import bpy

SCALARS = ("Roughness", "Metallic", "Specular")
HINTS = ("Subsurface", "Sheen", "Clearcoat", "Transmission", "Alpha", "IOR")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"bake_size": 0, "bake_cap": 2048, "no_bake": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--request":
            out["request"] = argv[i + 1]; i += 2
        elif a == "--out":
            out["out"] = argv[i + 1]; i += 2
        elif a == "--bake-dir":
            out["bake_dir"] = argv[i + 1]; i += 2
        elif a == "--bake-size":
            out["bake_size"] = int(argv[i + 1]); i += 2
        elif a == "--bake-cap":
            out["bake_cap"] = int(argv[i + 1]); i += 2
        elif a == "--no-bake":
            out["no_bake"] = True; i += 1
        else:
            raise SystemExit("unknown argument %s" % a)
    return out


# ---------------------------------------------------------------- matching

def norm(name):
    return re.sub(r"\.\d{3}$", "", name).strip().lower()


def material_images(mat):
    if not mat or not mat.use_nodes or not mat.node_tree:
        return set()
    return {os.path.basename(bpy.path.abspath(n.image.filepath)).lower() for n in mat.node_tree.nodes
            if n.type == "TEX_IMAGE" and n.image and n.image.filepath} | \
           {n.image.name.lower() for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image}


def match_materials(request):
    used = {}
    for o in bpy.data.objects:
        if o.type == "MESH":
            for s in o.material_slots:
                if s.material:
                    used.setdefault(s.material.name, s.material)
    by_norm = {}
    for name, m in used.items():
        by_norm.setdefault(norm(name), m)
    prefixes = request.get("strip_prefixes", [])
    out = {}
    for item in request["materials"]:
        name, tex = item["name"], (item.get("texture") or "").lower()
        m, how = by_norm.get(norm(name)), "name"
        if m is None:
            for p in prefixes:
                m = by_norm.get(norm(p + name))
                if m is not None:
                    how = "prefix " + p
                    break
        if m is None and tex:
            hits = [mm for mm in used.values() if tex in material_images(mm)]
            if len(hits) == 1:
                m, how = hits[0], "texture"
        if m is None and tex:
            # the PMX texture is "<game material>_baked.png" (Vindictus' build_blend bakes one per material; a
            # material shared by two meshes was split into "<name>_<part>"): strip the suffix, then trailing words
            base = re.sub(r"_?baked$", "", os.path.splitext(tex)[0], flags=re.I)
            while base and m is None:
                m = by_norm.get(norm(base)) or by_norm.get(norm(base + "_"))
                if m is None:
                    if not re.search(r"_[A-Za-z0-9]+$", base):
                        break
                    base = base.rsplit("_", 1)[0]
            if m is not None:
                how = "texture name"
        out[item["index"]] = (m, how if m is not None else "none")
    return out


# ---------------------------------------------------------------- node tracing

def find_principled(tree):
    ps = [n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"]
    if not ps:
        return None
    out = next((n for n in tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
    if out is not None and out.inputs["Surface"].is_linked and out.inputs["Surface"].links[0].from_node in ps:
        return out.inputs["Surface"].links[0].from_node
    return max(ps, key=lambda p: sum(1 for i in p.inputs if i.is_linked))


def default_uv(tex_node, uv_name):
    """True when an image node samples the PMX's UV map (no mapping).  ``uv_name`` is the set of UV map names that
    count as "the" UV of this material: the active UV of every object using it (objects of one model can name it
    differently - Rise of Eros hair vs body, 11-15) plus ""."""
    if isinstance(uv_name, str):
        uv_name = {uv_name, ""}
    v = tex_node.inputs.get("Vector")
    if v is None or not v.is_linked:
        return True
    link = v.links[0]
    src = link.from_node
    while src.type == "REROUTE":
        if not src.inputs[0].is_linked:
            return True
        link = src.inputs[0].links[0]
        src = link.from_node
    if src.type == "UVMAP":
        return src.uv_map in uv_name
    if src.type == "TEX_COORD":
        return link.from_socket.name == "UV"
    if src.type == "GROUP" and src.node_tree and "MMDTexUV" in src.node_tree.name:
        return link.from_socket.name == "Base UV"
    return False


def ascii_slug(name):
    """A file-name-safe ASCII version of a material / image name (MMD and MME open files through the ANSI API, so
    the pack keeps to ASCII names); a short hash keeps names that differ only in non-ASCII characters apart."""
    import hashlib
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_.")[:48] or "m"
    return "%s_%s" % (slug, hashlib.md5(name.encode("utf-8")).hexdigest()[:6])


def image_file(img, bake_dir):
    """Absolute path of an image's file (a packed image is written out to bake_dir)."""
    if img.packed_file is not None:
        ext = os.path.splitext(img.filepath or img.name)[1] or ".png"
        path = os.path.join(bake_dir, "packed_" + ascii_slug(os.path.splitext(img.name)[0]) + ext)
        if not os.path.isfile(path):
            os.makedirs(bake_dir, exist_ok=True)
            with open(path, "wb") as f:
                f.write(img.packed_file.data)
        return path
    path = os.path.normpath(bpy.path.abspath(img.filepath, library=img.library))
    return path if os.path.isfile(path) else None


def follow(sock):
    """(node, output socket name) feeding an input socket, through reroutes."""
    link = sock.links[0]
    n, out = link.from_node, link.from_socket.name
    while n.type == "REROUTE" and n.inputs[0].is_linked:
        link = n.inputs[0].links[0]
        n, out = link.from_node, link.from_socket.name
    return n, out


def is_one(sock):
    return not sock.is_linked and abs(float(sock.default_value) - 1.0) < 1e-6


MATH_OPS = {"ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "MULTIPLY_ADD", "POWER", "MINIMUM", "MAXIMUM"}


def _math_step(n):
    """One Math node with exactly one linked input among the ones its operation uses ->
    (op tuple, linked socket) or None.  The op is applied by make_hq_materials.apply_ops."""
    used = n.inputs[:3] if n.operation == "MULTIPLY_ADD" else n.inputs[:2]
    linked = [k for k, sock in enumerate(used) if sock.is_linked]
    if len(linked) != 1:
        return None
    consts = [0.0 if sock.is_linked else float(sock.default_value) for sock in used]
    return ("math", n.operation, linked[0], consts, bool(n.use_clamp)), used[linked[0]]


def trace_scalar(sock, uv_name, bake_dir):
    """A float input -> {"kind": "const"|"file", ...} or None (needs a bake).  Besides the image channel, a chain of
    simple per-pixel operations with constants is recorded (Math add / subtract / multiply / divide / multiply-add /
    power / min / max, Invert, Clamp, linear Map Range) - Rise of Eros writes roughness as 1 - 0.892 x G and
    metallic as R x 0.914, which needed no Cycles bake (11-15).  ops run from the image outward."""
    if not sock.is_linked:
        v = sock.default_value
        try:
            v = sum(v[:3]) / 3.0
        except TypeError:
            pass
        return {"kind": "const", "value": float(v)}
    n, out = follow(sock)
    ops = []
    for _ in range(12):
        if n.type == "MATH" and n.operation in MATH_OPS:
            step = _math_step(n)
            if step is None:
                return None
            ops.append(step[0])
            n, out = follow(step[1])
        elif n.type == "INVERT" and not n.inputs["Fac"].is_linked and n.inputs["Color"].is_linked:
            ops.append(("invert", float(n.inputs["Fac"].default_value)))
            n, out = follow(n.inputs["Color"])
        elif n.type == "CLAMP" and n.inputs["Value"].is_linked and not n.inputs["Min"].is_linked \
                and not n.inputs["Max"].is_linked:
            ops.append(("clamp", float(n.inputs["Min"].default_value), float(n.inputs["Max"].default_value)))
            n, out = follow(n.inputs["Value"])
        elif n.type == "MAP_RANGE" and getattr(n, "data_type", "FLOAT") == "FLOAT" \
                and n.interpolation_type == "LINEAR" and n.inputs["Value"].is_linked \
                and not any(n.inputs[k].is_linked for k in ("From Min", "From Max", "To Min", "To Max")):
            ops.append(("maprange", float(n.inputs["From Min"].default_value),
                        float(n.inputs["From Max"].default_value), float(n.inputs["To Min"].default_value),
                        float(n.inputs["To Max"].default_value), bool(n.clamp)))
            n, out = follow(n.inputs["Value"])
        else:
            break
    channel = None
    if n.bl_idname in ("ShaderNodeSeparateRGB", "ShaderNodeSeparateColor"):
        if n.bl_idname == "ShaderNodeSeparateColor" and getattr(n, "mode", "RGB") != "RGB":
            return None
        channel = {"R": 0, "G": 1, "B": 2, "Red": 0, "Green": 1, "Blue": 2}.get(out)
        src = n.inputs[0]
        if channel is None or not src.is_linked:
            return None
        n, out = follow(src)
        if out != "Color":
            return None
    if n.type != "TEX_IMAGE" or n.image is None or not default_uv(n, uv_name):
        return None
    if channel is None:
        channel = 3 if out == "Alpha" else "lum"
    path = image_file(n.image, bake_dir)
    if not path:
        return None
    ops.reverse()
    invert = False
    if ops in ([("math", "SUBTRACT", 1, [1.0, 0.0], False)], [("invert", 1.0)],
               [("math", "MULTIPLY_ADD", 0, [0.0, -1.0, 1.0], False)]):
        ops, invert = [], True                         # plain 1 - x: the map can still be used as it is
    elif all(o[0] == "math" and o[1] == "MULTIPLY" and o[3][1 - o[2]] == 1.0 for o in ops):
        ops = []                                       # x 1
    return {"kind": "file", "path": path, "channel": channel, "invert": invert, "ops": ops,
            "colorspace": n.image.colorspace_settings.name, "size": list(n.image.size)}


def trace_color(sock, uv_name, bake_dir):
    if not sock.is_linked:
        return {"kind": "const", "value": [float(x) for x in sock.default_value[:3]]}
    n, out = follow(sock)
    if n.type == "TEX_IMAGE" and n.image is not None and out == "Color" and default_uv(n, uv_name):
        path = image_file(n.image, bake_dir)
        if path:
            return {"kind": "file", "path": path, "colorspace": n.image.colorspace_settings.name,
                    "size": list(n.image.size)}
    return None


def trace_normal(sock, uv_name, bake_dir):
    if not sock.is_linked:
        return {"kind": "none"}
    n, out = follow(sock)
    uvs = {uv_name, ""} if isinstance(uv_name, str) else uv_name
    if n.type != "NORMAL_MAP" or n.space != "TANGENT" or n.uv_map not in uvs:
        return None
    strength = n.inputs["Strength"]
    if strength.is_linked or not n.inputs["Color"].is_linked:
        return None
    c, cout = follow(n.inputs["Color"])
    flip = False
    if c.bl_idname in ("ShaderNodeCombineRGB", "ShaderNodeCombineColor"):
        # Separate -> (R, 1 - G, B) -> Combine: a DirectX map turned into Blender's OpenGL one
        srcs = []
        for k, sock_in in enumerate(c.inputs[:3]):
            if not sock_in.is_linked:
                return None
            nn, oo = follow(sock_in)
            inv = False
            if nn.type == "MATH" and nn.operation == "SUBTRACT" and is_one(nn.inputs[0]) and nn.inputs[1].is_linked:
                inv = True
                nn, oo = follow(nn.inputs[1])
            if nn.bl_idname not in ("ShaderNodeSeparateRGB", "ShaderNodeSeparateColor"):
                return None
            srcs.append((nn, {"R": 0, "G": 1, "B": 2, "Red": 0, "Green": 1, "Blue": 2}.get(oo), inv))
        sep = srcs[0][0]
        if any(s[0] is not sep for s in srcs) or [s[1] for s in srcs] != [0, 1, 2] or srcs[0][2] or srcs[2][2]:
            return None
        flip = srcs[1][2]
        if not sep.inputs[0].is_linked:
            return None
        c, cout = follow(sep.inputs[0])
    if c.type in ("VECT_MATH", "MIX_RGB") or c.bl_idname == "ShaderNodeMix":
        return detail_blend(c, uv_name, bake_dir, float(strength.default_value))
    if c.type != "TEX_IMAGE" or c.image is None or cout != "Color" or not default_uv(c, uv_name):
        return None
    path = image_file(c.image, bake_dir)
    if not path:
        return None
    return {"kind": "file", "path": path, "flip_g": flip, "strength": float(strength.default_value),
            "size": list(c.image.size)}


def detail_blend(node, uv_name, bake_dir, strength):
    """A normal map blended with a tiling detail normal map through Vector Math / Mix nodes (Rise of Eros skin:
    the body map + a pore map).  Of the images upstream, the one read through the PMX's UV is the main normal map;
    one read through a Mapping node with a uniform scale becomes ray-mmd's sub normal (NORMAL_SUB_MAP, loop = scale).
    The blend formula itself is not reproduced - ray-mmd blends the two its own way (reoriented normal mapping)."""
    seen, queue, mains, details = set(), [node], [], []
    while queue:
        n = queue.pop(0)
        if n.as_pointer() in seen:
            continue
        seen.add(n.as_pointer())
        if n.type == "TEX_IMAGE":
            if n.image is not None:
                if default_uv(n, uv_name):
                    mains.append(n)
                else:
                    scale = _mapping_scale(n)
                    if scale:
                        details.append((n, scale))
            continue
        for sock in n.inputs:
            if sock.is_linked:
                queue.append(follow(sock)[0])
    if not mains:
        return None
    main = image_file(mains[0].image, bake_dir)
    if not main:
        return None
    out = {"kind": "file", "path": main, "flip_g": False, "strength": strength, "size": list(mains[0].image.size),
           "approx": "detail normal blend: main map%s" % (" + sub normal" if details else "")}
    if details:
        sub = image_file(details[0][0].image, bake_dir)
        if sub:
            out["sub"] = {"path": sub, "loop": details[0][1]}
    return out


def _mapping_scale(tex):
    """The uniform scale of a Mapping node feeding an image node's vector, else None."""
    v = tex.inputs.get("Vector")
    if v is None or not v.is_linked:
        return None
    n, _o = follow(v)
    if n.type != "MAPPING" or n.inputs["Scale"].is_linked:
        return None
    sx, sy = n.inputs["Scale"].default_value[0], n.inputs["Scale"].default_value[1]
    return float(sx) if abs(sx - sy) < 1e-4 and sx > 0 else None


def trace_emission(p, uv_name, bake_dir):
    col, st = p.inputs["Emission"], p.inputs.get("Emission Strength")
    strength = 1.0 if st is None else (None if st.is_linked else float(st.default_value))
    if not col.is_linked:
        c = [float(x) for x in col.default_value[:3]]
        if strength == 0 or max(c) <= 0:
            return {"kind": "none"}
        if strength is not None:
            return {"kind": "const", "value": c, "strength": strength}
        return None
    if strength == 0:
        return {"kind": "none"}
    t = trace_color(col, uv_name, bake_dir)
    if t is not None and strength is not None:
        t["strength"] = strength
        return t
    return None


def hints(p):
    out = {}
    for name in HINTS:
        s = p.inputs.get(name)
        if s is None:
            continue
        if s.is_linked:
            out[name] = "linked"
        else:
            out[name] = float(s.default_value) if not hasattr(s.default_value, "__len__") else \
                [float(x) for x in s.default_value[:3]]
    return out


# ---------------------------------------------------------------- baking

def bake_jobs(jobs, uv_name, bake_dir, size_for, report):
    """jobs: {(material name, channel): (material, principled)} -> {(mat, channel): file}.  channel in
    roughness / metallic / specular / emission / normal."""
    if not jobs:
        return {}
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    scene.render.bake.use_clear = True
    scene.render.bake.margin = 16
    scene.render.bake.use_selected_to_active = False
    scene.render.bake.target = "IMAGE_TEXTURES"
    try:
        scene.cycles.device = "CPU"
    except Exception:
        pass
    results = {}
    channels = sorted({ch for (_m, ch) in jobs})
    mats = {m: v[0] for (m, _c), v in jobs.items()}
    objs = [o for o in bpy.data.objects if o.type == "MESH" and o.data.uv_layers
            and any(s.material and s.material.name in mats for s in o.material_slots)]
    for o in objs:
        if o.name not in bpy.context.view_layer.objects:     # in an excluded collection: bake needs it selectable
            scene.collection.objects.link(o)
        o.hide_viewport = False
        o.hide_render = False
        o.hide_select = False
        try:
            o.hide_set(False)
        except Exception:
            pass
        uv = o.data.uv_layers.get(uv_name) or o.data.uv_layers.active
        for u in o.data.uv_layers:
            u.active_render = (u == uv)
    for ch in channels:
        want = {m for (m, c) in jobs if c == ch}
        temp_mats, images, originals = [], {}, []
        for o in objs:
            originals.append((o, [s.material for s in o.material_slots]))
        copies = {}
        try:
            for o in objs:
                for slot in o.material_slots:
                    mat = slot.material
                    if mat is None:
                        continue
                    if mat.name not in copies:
                        cp = mat.copy()
                        cp.name = "__hq_bake_%s" % mat.name
                        temp_mats.append(cp)
                        tree = cp.node_tree
                        node = tree.nodes.new("ShaderNodeTexImage")
                        if mat.name in want:
                            s = size_for(mat)
                            img = bpy.data.images.new("__hq_%s_%s" % (ch, mat.name), s, s, alpha=False)
                            img.colorspace_settings.name = "sRGB" if ch == "emission" else "Non-Color"
                            images[mat.name] = img
                            node.image = img
                            _wire(tree, find_principled(tree), ch)
                        else:
                            dummy = bpy.data.images.new("__hq_dummy", 8, 8)
                            node.image = dummy
                        tree.nodes.active = node
                        copies[mat.name] = cp
                    slot.material = copies[mat.name]
            bpy.ops.object.select_all(action="DESELECT")
            for o in objs:
                o.select_set(True)
            bpy.context.view_layer.objects.active = objs[0]
            bpy.ops.object.bake(type="NORMAL" if ch == "normal" else "EMIT", normal_space="TANGENT")
            for name, img in images.items():
                path = os.path.join(bake_dir, "%s_%s.png" % (ascii_slug(name), ch))
                img.filepath_raw = path
                img.file_format = "PNG"
                img.save()
                results[(name, ch)] = path
            report.append("baked %s for %d materials" % (ch, len(images)))
        finally:
            for o, mats_before in originals:
                for slot, m in zip(o.material_slots, mats_before):
                    slot.material = m
            for m in temp_mats:
                bpy.data.materials.remove(m)
            for img in list(bpy.data.images):
                if img.name.startswith("__hq_"):
                    bpy.data.images.remove(img)
    return results


def _wire(tree, p, ch):
    out = next((n for n in tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None) or \
        tree.nodes.new("ShaderNodeOutputMaterial")
    for l in list(out.inputs["Surface"].links):
        tree.links.remove(l)
    if ch == "normal":
        tree.links.new(p.outputs[0], out.inputs["Surface"])
        return
    emit = tree.nodes.new("ShaderNodeEmission")
    if ch == "emission":
        src, st = p.inputs["Emission"], p.inputs.get("Emission Strength")
        if src.is_linked:
            tree.links.new(src.links[0].from_socket, emit.inputs["Color"])
        else:
            emit.inputs["Color"].default_value = tuple(src.default_value)
        if st is not None:
            if st.is_linked:
                tree.links.new(st.links[0].from_socket, emit.inputs["Strength"])
            else:
                emit.inputs["Strength"].default_value = st.default_value
    else:
        src = p.inputs[{"roughness": "Roughness", "metallic": "Metallic", "specular": "Specular"}[ch]]
        if src.is_linked:
            tree.links.new(src.links[0].from_socket, emit.inputs["Color"])
        else:
            v = float(src.default_value)
            emit.inputs["Color"].default_value = (v, v, v, 1.0)
    tree.links.new(emit.outputs[0], out.inputs["Surface"])


# ---------------------------------------------------------------- main

def main():
    args = parse_args()
    request = json.load(open(args["request"], encoding="utf-8"))
    bake_dir = os.path.abspath(args["bake_dir"])
    os.makedirs(bake_dir, exist_ok=True)
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.data.uv_layers]
    uv_name = request.get("uv") or (meshes[0].data.uv_layers.active.name if meshes else "")
    matches = match_materials(request)
    rows, jobs, report = [], {}, []

    def size_for(mat):
        if args["bake_size"]:
            return args["bake_size"]
        sizes = [max(n.image.size) for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image
                 and n.image.size[0] > 0]
        return int(min(args["bake_cap"], max(512, max(sizes) if sizes else 1024)))

    for item in request["materials"]:
        mat, how = matches[item["index"]]
        row = {"index": item["index"], "name": item["name"], "blend_material": mat.name if mat else None,
               "match": how, "channels": {}, "hints": {}}
        rows.append(row)
        if mat is None or not mat.use_nodes or not mat.node_tree:
            continue
        p = find_principled(mat.node_tree)
        if p is None:
            row["match"] += " (no Principled BSDF)"
            continue
        row["hints"] = hints(p)
        ch = row["channels"]
        uvs = {"", uv_name} | {o.data.uv_layers.active.name for o in meshes
                               if any(sl.material == mat for sl in o.material_slots) and o.data.uv_layers.active}
        ch["normal"] = trace_normal(p.inputs["Normal"], uvs, bake_dir)
        for s in SCALARS:
            if s in p.inputs:
                ch[s.lower()] = trace_scalar(p.inputs[s], uvs, bake_dir)
        ch["emission"] = trace_emission(p, uvs, bake_dir)
        for k, v in list(ch.items()):
            if v is None:
                if args["no_bake"]:
                    ch[k] = {"kind": "skipped"}
                else:
                    jobs[(mat.name, k)] = (mat, p)
    baked = {}
    if jobs and not args["no_bake"]:
        baked = bake_jobs(jobs, uv_name, bake_dir, size_for, report)
    for row in rows:
        for k, v in row["channels"].items():
            if v is None:
                path = baked.get((row["blend_material"], k))
                row["channels"][k] = {"kind": "baked", "path": path} if path else {"kind": "failed"}
    result = {"blend": bpy.data.filepath, "uv": uv_name, "materials": rows, "report": report}
    with open(args["out"], "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    kinds = {}
    for row in rows:
        for k, v in row["channels"].items():
            kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    print("HQ_EXTRACT=" + json.dumps({"materials": len(rows), "matched": sum(1 for r in rows if r["blend_material"]),
                                      "channels": kinds, "baked_jobs": len(jobs), "report": report},
                                     ensure_ascii=False))


main()
