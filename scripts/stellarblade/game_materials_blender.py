r"""Stellar Blade game materials for an imported Eve PMX (Blender 3.6) - the core of the stellarblade_game_materials
add-on.

A PMX holds one colour map per material (export_pmx_blender.py --hq-materials: the game colour x AO).  The archived
HQ .blend files (E:\game_export\StellarBlade\<character>\blend\<package>\*_HQ.blend, made by hq_materials_blender.py
from the game's own material instances) carry the full networks: normal map, ORM (roughness, metallic, specular
occlusion), clear coat, sheen, emission, the knit pattern, the decal's cut-out.  For every material of an imported
PMX this module finds the same-named material in an HQ .blend (a PMX ``<name>_gloss`` part - export_pmx_blender's
glossy split - takes ``<name>``'s), appends it and copies its network INTO the PMX material next to mmd_tools' own
nodes, with its own output node (all nodes ``sbhq_*``).  The MMD shader and everything the PMX export reads stay;
set_mode() switches between the two looks (as the Vindictus and ROE add-ons do).

The .blend holding most of the model's materials is its home: the head, hair and eye materials are in every outfit,
the outfit's own ones decide.

Several outfits in one PMX (scripts/clothes_burst/pmx_layers.py: Reika A over B over the nude body): every material
of such a model says in its PMX comment which layer it belongs to and what it was called in its own model
("layer=B; source=SuitA_Body"; mmd_tools keeps it in mmd_material.comment).  Each layer then has its own home (the
outer layer's also serves the head, hair and eyes), and a material its home lacks is looked up in the other .blend
files.  The layers are put on and taken off by material morphs (the step sliders): a material a morph can hide gets
the game alpha x the alpha mmd_tools' MMD shader draws with (its morph sliders included), and sync() - run by the
add-on whenever the scene changes or the frame moves - gives a hidden one EEVEE settings that keep it out of sight:
blend mode BLEND without the back-face pre-pass, no shadow, no subsurface.  Left alpha-hashed, a hidden layer lying
just under the visible skin drew thin dark lines where the two surfaces cross, and a hidden subsurface surface draws
black over what lies on it; shown again, it gets the game's own settings back.

Standalone check (imports the PMX with mmd_tools at 0.08):
    blender -b --factory-startup --python game_materials_blender.py -- <pmx> [--archive DIR] [--out x.blend]
"""
import json
import os
import re
import sys

import bpy
from mathutils import Vector

PREFIX = "sbhq_"
ARCHIVE = r"E:\game_export\StellarBlade"
ARCHIVE_HEIGHT = 172.0           # the archive .blend files are in centimetres (UE units): Eve stands ~172 tall
BASE_KEY = "sb_hq_base"
GLOSS_SUFFIX = "_gloss"
DEFAULT_PARAMS = {"normal": 1.0, "rough": 1.0, "metal": 1.0, "clearcoat": 1.0, "sheen": 1.0, "emission": 1.0}
GAINS = (("rough", "Roughness"), ("metal", "Metallic"), ("clearcoat", "Clearcoat"), ("sheen", "Sheen"))
SETTINGS = ("blend_method", "shadow_method", "alpha_threshold", "use_backface_culling", "show_transparent_back")
HIDE_KEY = "sbhq_hide"           # on a material a morph can hide: json {"sss": its subsurface weight, "state": ...}
LAYER_RE = re.compile(r"(\w+)\s*=\s*([^;\n]+)")
SKIP = {"rna_type", "name", "label", "location", "width", "width_hidden", "height", "dimensions", "parent", "select",
        "inputs", "outputs", "internal_links", "type", "bl_idname", "bl_label", "bl_description", "bl_icon",
        "bl_static_type", "bl_width_default", "bl_width_min", "bl_width_max", "bl_height_default", "bl_height_min",
        "bl_height_max", "show_options", "show_preview", "show_texture", "is_active_output", "hide", "mute", "color",
        "use_custom_color"}


def log(msg):
    print("[stellarblade_game_materials] " + msg, flush=True)


COPY_SUFFIXES = ("_burst", "_nude")   # the 爆衣 add-on's copies: fragments / the nude body copy of a material


def source_name(name):
    """the HQ material a PMX material comes from: its own name, or <name> for export_pmx's <name>_gloss part and for
    the 爆衣 add-on's <name>_burst / <name>_nude copies (so the burst can be made before or after the game look)"""
    for suffix in COPY_SUFFIXES:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name[:-len(GLOSS_SUFFIX)] if name.endswith(GLOSS_SUFFIX) else name


# --- the archive -------------------------------------------------------------------------------------------------
def hq_blends(root):
    r"""every <root>\<character>\blend\<package>\*_HQ.blend"""
    out = []
    if not os.path.isdir(root):
        return out
    for character in sorted(os.listdir(root)):
        folder = os.path.join(root, character, "blend")
        if not os.path.isdir(folder):
            continue
        for package in sorted(os.listdir(folder)):
            pdir = os.path.join(folder, package)
            if os.path.isdir(pdir):
                out += [os.path.join(pdir, f) for f in sorted(os.listdir(pdir)) if f.lower().endswith("_hq.blend")]
    return out


def index_path():
    return os.path.join(bpy.utils.user_resource("CONFIG"), "stellarblade_game_materials_index.json")


def archive_index(root=ARCHIVE, fresh=False):
    """{blend path: {"stamp", "materials"}} of the archive's HQ .blend files; cached by size + mtime, so only new or
    changed files are opened (names only, nothing is loaded)"""
    cache = index_path()
    old = {}
    if not fresh and os.path.isfile(cache):
        try:
            old = json.load(open(cache, encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
    out = {}
    for path in hq_blends(root):
        st = os.stat(path)
        stamp = "%d-%d" % (st.st_size, int(st.st_mtime))
        if old.get(path, {}).get("stamp") == stamp:
            out[path] = old[path]
            continue
        with bpy.data.libraries.load(path, link=False) as (data_from, _data_to):
            names = list(data_from.materials)
        out[path] = {"stamp": stamp, "materials": names}
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump(out, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    except OSError:
        pass
    return out


def match(names, index, hint=""):
    """(home .blend, {PMX material name: source name}) - the .blend holding most of the sources is home; a tie goes
    to the one whose folder the hint (model name / comment) names"""
    wanted = {n: source_name(n) for n in names}
    best, best_score = None, -1
    for path, entry in index.items():
        have = set(entry["materials"])
        score = sum(1 for s in set(wanted.values()) if s in have)
        package = os.path.basename(os.path.dirname(path))
        bonus = 0.5 if hint and package.lower() in hint.lower() else 0.0
        if score + bonus > best_score:
            best, best_score = path, score + bonus
    if best is None or best_score < 1:
        return None, {}
    have = set(index[best]["materials"])
    return best, {n: s for n, s in wanted.items() if s in have}


def layer_of(mat):
    """(layer, source name) of a material: pmx_layers.py writes "layer=B; source=SuitA_Body" into the PMX comment of
    every outfit material (source only when it was renamed); ("", source_name()) for any other"""
    text = getattr(getattr(mat, "mmd_material", None), "comment", "") or ""
    tags = {k.lower(): v.strip() for k, v in LAYER_RE.findall(text)}
    return tags.get("layer", ""), source_name(tags.get("source") or mat.name)


def plan(mats, index, hint=""):
    """({PMX material name: (.blend, source)}, {layer: home .blend}).  A model without layers has one home, the
    .blend holding most of its materials (match()).  A pmx_layers.py model: every layer its own home, the .blend
    holding most of that layer's sources - the outer (first) layer's also counts the materials no layer names (head,
    hair, eyes) and serves them; a source a home lacks comes from the next .blend that has it, the homes first."""
    groups = {}
    for m in mats:
        layer, src = layer_of(m)
        groups.setdefault(layer, []).append((m.name, src))
    tagged = [layer for layer in groups if layer]
    if not tagged:
        home, found = match([m.name for m in mats], index, hint)
        return {n: (home, s) for n, s in found.items()}, ({"": home} if home else {})
    have = {path: set(entry["materials"]) for path, entry in index.items()}
    homes = {}
    for k, layer in enumerate(tagged):
        sources = {s for _n, s in groups[layer]} | ({s for _n, s in groups.get("", [])} if k == 0 else set())
        best, best_score = None, 0.0
        for path in sorted(have):
            package = os.path.basename(os.path.dirname(path)).lower()
            score = len(sources & have[path]) + (0.5 if hint and package in hint.lower() else 0.0)
            if score > best_score:
                best, best_score = path, score
        if best is not None:
            homes[layer] = best
    if tagged[0] in homes:
        homes[""] = homes[tagged[0]]
    order = list(dict.fromkeys(homes.values()))
    picks = {}
    for layer, items in groups.items():
        for name, src in items:
            first = homes.get(layer)
            if first is not None and src in have[first]:
                picks[name] = (first, src)
                continue
            other = next((p for p in order if src in have[p]), None) or \
                next((p for p in sorted(have, key=lambda p: -len(have[p])) if src in have[p]), None)
            if other is not None:
                picks[name] = (other, src)
    return picks, homes


# --- copying a network ---------------------------------------------------------------------------------------------
def copy_ramp(src, dst):
    dst.color_mode, dst.interpolation = src.color_mode, src.interpolation
    while len(dst.elements) > len(src.elements):
        dst.elements.remove(dst.elements[-1])
    while len(dst.elements) < len(src.elements):
        dst.elements.new(0.5)
    for a, b in zip(src.elements, dst.elements):
        b.position, b.color = a.position, a.color


def copy_node(src, nodes, offset):
    dst = nodes.new(src.bl_idname)
    dst.name = PREFIX + src.name
    dst.label = src.label
    dst.location = src.location + offset
    dst.width = src.width
    for prop in src.bl_rna.properties:
        pid = prop.identifier
        if pid in SKIP or prop.is_readonly:
            continue
        try:
            setattr(dst, pid, getattr(src, pid))
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass
    if getattr(src, "color_ramp", None) is not None:
        copy_ramp(src.color_ramp, dst.color_ramp)
    for a, b in zip(src.inputs, dst.inputs):
        if hasattr(a, "default_value"):
            try:
                b.default_value = a.default_value
            except (AttributeError, TypeError, ValueError):
                pass
    return dst


def copy_network(src_mat, dst_mat):
    """src_mat's nodes and links into dst_mat (below its own nodes); returns {src name: new node}"""
    nodes = dst_mat.node_tree.nodes
    low = min((n.location.y for n in nodes), default=0.0)
    top = max((n.location.y for n in src_mat.node_tree.nodes), default=0.0)
    offset = Vector((0.0, low - 400.0 - top))
    made = {n.name: copy_node(n, nodes, offset) for n in src_mat.node_tree.nodes}
    links = dst_mat.node_tree.links
    for link in src_mat.node_tree.links:
        a, b = made[link.from_node.name], made[link.to_node.name]
        out = next((s for s in a.outputs if s.identifier == link.from_socket.identifier), None)
        inp = next((s for s in b.inputs if s.identifier == link.to_socket.identifier), None)
        if out is not None and inp is not None:
            links.new(out, inp)
    return made


def insert_gain(tree, bsdf, socket_name, tag):
    """a MULTIPLY node in front of a linked Principled input (value 1 = the game's), for live tuning"""
    sock = bsdf.inputs.get(socket_name)
    if sock is None or not sock.links:
        return None
    src = sock.links[0].from_socket
    g = tree.nodes.new("ShaderNodeMath")
    g.operation = "MULTIPLY"
    g.use_clamp = tag in ("rough", "metal", "clearcoat")
    g.name = g.label = PREFIX + "gain_" + tag
    g.location = bsdf.location + Vector((-220.0, -60.0 * (1 + [t for t, _s in GAINS].index(tag))))
    g.inputs[1].default_value = 1.0
    tree.links.new(src, g.inputs[0])
    tree.links.new(g.outputs[0], sock)
    return g


# --- per material ----------------------------------------------------------------------------------------------------
def settings_of(mat):
    return {k: getattr(mat, k) for k in SETTINGS}


def put_settings(mat, values):
    for k, v in values.items():
        try:
            setattr(mat, k, v)
        except (AttributeError, TypeError, ValueError):
            pass


def outputs(mat):
    """(mmd_tools' output, ours) of a material"""
    mine = [n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL" and n.name.startswith(PREFIX)]
    theirs = [n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL" and not n.name.startswith(PREFIX)]
    return (theirs[0] if theirs else None), (mine[0] if mine else None)


# --- layers a material morph puts on and takes off ---------------------------------------------------------------------
def root_of(obj):
    while obj is not None and getattr(obj, "mmd_type", "NONE") != "ROOT":
        obj = obj.parent
    return obj


def alpha_morphs(root):
    """({material_id: [(morph, "MULT"|"ADD", alpha)]}, {morph: [(group morph, factor)]}) of an mmd_tools model;
    material_id -1 = a morph on every material"""
    terms, groups = {}, {}
    mmd_root = getattr(root, "mmd_root", None)
    if mmd_root is None:
        return terms, groups
    for morph in mmd_root.material_morphs:
        for d in morph.data:
            a = d.diffuse_color[3]
            if (abs(a - 1.0) if d.offset_type == "MULT" else abs(a)) > 1e-4:
                terms.setdefault(d.material_id, []).append((morph.name, d.offset_type, a))
    for g in mmd_root.group_morphs:
        for d in g.data:
            groups.setdefault(d.name, []).append((g.name, d.factor))
    return terms, groups


def can_hide(mat, terms):
    """a material morph changes its alpha.  A morph on every material counts only for materials the PMX shows:
    the ones it keeps at alpha 0 (eye occlusion, tear film) are drawn by the game look whatever MMD does."""
    mid = getattr(getattr(mat, "mmd_material", None), "material_id", -1)
    if mid >= 0 and mid in terms:
        return True
    return -1 in terms and getattr(getattr(mat, "mmd_material", None), "alpha", 1.0) > 1e-3


def placeholder(root):
    return next((c for c in root.children if getattr(c, "mmd_type", "") == "PLACEHOLDER" and c.type == "MESH"), None)


def slider_values(root, frame=None):
    """{morph: slider value} of mmd_tools' morph sliders ({} until they are bound - till then no morph acts).  With
    a frame the animated sliders are read from their curves at that frame: before the frame is evaluated (the
    frame_change_pre handler) the keys still hold the last frame's values."""
    ph = placeholder(root)
    keys = getattr(getattr(ph, "data", None), "shape_keys", None)
    if keys is None or not len(keys.key_blocks) or keys.key_blocks[0].mute:
        return {}
    values = {kb.name: kb.value for kb in keys.key_blocks[1:]}
    action = getattr(keys.animation_data, "action", None) if keys.animation_data else None
    if frame is not None and action is not None:
        for fc in action.fcurves:
            m = re.match(r'key_blocks\["(.+)"\]\.value$', fc.data_path)
            if m and not fc.mute:
                values[m.group(1).replace('\\"', '"')] = fc.evaluate(frame)
    return values


def morph_alpha(mat, terms, groups, values):
    """the alpha MMD draws the material with: base x the multiplies + the adds, each morph weighted by its slider
    plus its group sliders x their factors (mmd_tools' own drivers do the same)"""
    mid = getattr(getattr(mat, "mmd_material", None), "material_id", -1)
    alpha = getattr(getattr(mat, "mmd_material", None), "alpha", 1.0)

    def weight(name):
        return values.get(name, 0.0) + sum(values.get(g, 0.0) * f for g, f in groups.get(name, ()))

    entries = terms.get(-1, []) + (terms.get(mid, []) if mid >= 0 else [])
    for name, op, a in entries:
        if op == "MULT":
            alpha *= 1.0 + weight(name) * (a - 1.0)
    for name, op, a in entries:
        if op == "ADD":
            alpha += weight(name) * a
    return min(max(alpha, 0.0), 1.0)


def mmd_alpha_source(mat):
    """(socket or None, value) the MMD shader takes its alpha from: once the morph sliders are bound, mmd_tools'
    morph nodes (mmd_bind*) feed its Alpha input"""
    node = mat.node_tree.nodes.get("mmd_shader")
    sock = node.inputs.get("Alpha") if node is not None else None
    if sock is not None:
        return (sock.links[0].from_socket if sock.is_linked else None), sock.default_value
    return None, getattr(getattr(mat, "mmd_material", None), "alpha", 1.0)


def add_mmd_alpha(mat, bsdf):
    """sbhq_mmd_alpha in front of the game network's Alpha: the game alpha x the MMD alpha"""
    tree = mat.node_tree
    sock = bsdf.inputs.get("Alpha")
    if sock is None:
        return None
    node = tree.nodes.new("ShaderNodeMath")
    node.name = node.label = PREFIX + "mmd_alpha"
    node.operation = "MULTIPLY"
    node.use_clamp = True
    node.location = bsdf.location + Vector((-220.0, -420.0))
    if sock.is_linked:
        tree.links.new(sock.links[0].from_socket, node.inputs[0])
    else:
        node.inputs[0].default_value = sock.default_value
    tree.links.new(node.outputs[0], sock)
    relink_alpha(mat)
    return node


def relink_alpha(mat):
    """point sbhq_mmd_alpha at wherever the MMD shader's alpha comes from now (binding the sliders later replaces
    mmd_tools' morph nodes)"""
    node = mat.node_tree.nodes.get(PREFIX + "mmd_alpha")
    if node is None:
        return False
    src, value = mmd_alpha_source(mat)
    inp = node.inputs[1]
    if src is not None:
        if inp.is_linked and inp.links[0].from_node.name == src.node.name and \
                inp.links[0].from_socket.identifier == src.identifier:
            return False
        mat.node_tree.links.new(src, inp)
        return True
    changed = inp.is_linked or abs(inp.default_value - value) > 1e-6
    for link in list(inp.links):
        mat.node_tree.links.remove(link)
    inp.default_value = value
    return changed


def _state_settings(mat, mode, state):
    """the EEVEE settings for a material that can hide, in one look, shown / fading / hidden"""
    key = "sbhq_game_settings" if mode == "game" else "sbhq_mmd_settings"
    s = json.loads(mat.get(key) or "{}")
    if state == "hidden":
        # BLEND draws nothing at alpha 0 and writes no depth (show_transparent_back keeps the depth pre-pass off)
        s.update(blend_method="BLEND", show_transparent_back=True, shadow_method="NONE")
    else:
        if state == "fading" and s.get("blend_method") == "OPAQUE":
            s["blend_method"] = "HASHED"
        if mode == "mmd" and getattr(getattr(mat, "mmd_material", None), "enabled_self_shadow_map", False):
            s["shadow_method"] = "HASHED"      # mmd_tools left it at NONE: the file hides the layer
        elif state == "fading" and s.get("shadow_method") == "OPAQUE":
            s["shadow_method"] = "HASHED"
    return s


def _set_sss(mat, hide, on):
    bsdf = mat.node_tree.nodes.get(hide.get("bsdf", ""))
    sock = bsdf.inputs.get("Subsurface") if bsdf is not None else None
    if sock is not None and not sock.is_linked and hide.get("sss") is not None:
        value = hide["sss"] if on else 0.0
        if abs(sock.default_value - value) > 1e-7:
            sock.default_value = value


def sync(materials=None, frame=None):
    """every material a morph can hide (or those given): sbhq_mmd_alpha linked to the MMD alpha, and the settings of
    its state - alpha 1 the look's own, in between (a fade) alpha-hashed, 0 hidden (_state_settings).  Cheap when
    nothing changed; the add-on runs it on every scene change and before every frame (with that frame)."""
    wanted = None if materials is None else {m.name for m in materials}
    changed = 0
    for root in [o for o in bpy.data.objects if getattr(o, "mmd_type", "") == "ROOT"]:
        mats = {}
        for obj in root.children_recursive:
            if obj.type == "MESH":
                for slot in obj.material_slots:
                    m = slot.material
                    if m is not None and m.get(HIDE_KEY) and m.use_nodes and (wanted is None or m.name in wanted):
                        mats[m.name] = m
        if not mats:
            continue
        terms, groups = alpha_morphs(root)
        values = slider_values(root, frame)
        for mat in mats.values():
            hide = json.loads(mat[HIDE_KEY])
            changed += relink_alpha(mat)
            alpha = morph_alpha(mat, terms, groups, values)
            state = "hidden" if alpha <= 1e-3 else ("fading" if alpha < 0.999 else "shown")
            _theirs, mine = outputs(mat)
            mode = "game" if mine is not None and mine.is_active_output else "mmd"
            if mat.get("sbhq_state") == mode + ":" + state:
                continue
            put_settings(mat, _state_settings(mat, mode, state))
            _set_sss(mat, hide, state != "hidden")
            mat["sbhq_state"] = mode + ":" + state
            changed += 1
    return changed


def model_scale(meshes):
    """Blender units of the imported model per centimetre of the archive .blend: both hold an Eve-sized body, the
    archive in centimetres, a PMX imported at 0.08 in about metres (0.01)"""
    zs = [(o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box]
    height = max(zs) - min(zs) if zs else 0.0
    return height / ARCHIVE_HEIGHT if height > 0 else 1.0


def upgrade(dst, src, source_label, scale=1.0, hide=False):
    """the HQ network of src into dst; remembers both looks' settings.  Lengths in the network (the subsurface radius)
    are scaled by `scale`, model_scale(): copied as they are, the face's 1 cm scattering became 1 m and blurred it.
    hide: a material morph can hide dst (a layer) - its game alpha is multiplied by the MMD alpha, and sync() keeps
    its settings in step with that alpha"""
    remove_one(dst)
    dst["sbhq_mmd_settings"] = json.dumps(settings_of(dst))
    made = copy_network(src, dst)
    for n in made.values():
        if n.type == "BSDF_PRINCIPLED" and "Subsurface Radius" in n.inputs:
            n.inputs["Subsurface Radius"].default_value = [v * scale for v in n.inputs["Subsurface Radius"].default_value]
    bsdf = next((n for n in made.values() if n.type == "BSDF_PRINCIPLED"), None)
    if hide and bsdf is not None and add_mmd_alpha(dst, bsdf) is not None:
        sss = bsdf.inputs.get("Subsurface")
        dst[HIDE_KEY] = json.dumps({"bsdf": bsdf.name,
                                    "sss": sss.default_value if sss is not None and not sss.is_linked else None})
    if bsdf is not None:
        for tag, sock in GAINS:
            # a texture-driven input gets a gain node; a constant one (hair roughness 0.28 ...) is scaled in place
            if insert_gain(dst.node_tree, bsdf, sock, tag) is None and sock in bsdf.inputs:
                bsdf["sbhq_base_" + tag] = bsdf.inputs[sock].default_value
        bsdf["sbhq_emission"] = bsdf.inputs["Emission Strength"].default_value
    for n in made.values():
        if n.type == "NORMAL_MAP":
            n["sbhq_strength"] = n.inputs["Strength"].default_value
    game = settings_of(src)
    if dst.name.endswith(GLOSS_SUFFIX):
        game["blend_method"] = "OPAQUE"
    dst["sbhq_game_settings"] = json.dumps(game, default=str)
    dst[BASE_KEY] = source_label
    return made


def hq_materials_of(meshes):
    seen, out = set(), []
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is not None and mat.get(BASE_KEY) and mat.name not in seen:
                seen.add(mat.name)
                out.append(mat)
    return out


def set_mode(materials, mode):
    """'game' or 'mmd': which output is active, with that look's blend settings"""
    for mat in materials:
        theirs, mine = outputs(mat)
        want = mine if mode == "game" else theirs
        if want is None:
            continue
        for n in mat.node_tree.nodes:
            if n.type == "OUTPUT_MATERIAL":
                n.is_active_output = n == want
        key = "sbhq_game_settings" if mode == "game" else "sbhq_mmd_settings"
        if mat.get(key):
            put_settings(mat, json.loads(mat[key]))
        if "sbhq_state" in mat:
            del mat["sbhq_state"]
    sync([m for m in materials if m.get(HIDE_KEY)])


def apply_params(materials, params=None):
    p = dict(DEFAULT_PARAMS)
    p.update(params or {})
    for mat in materials:
        for n in mat.node_tree.nodes:
            if not n.name.startswith(PREFIX):
                continue
            if n.name.startswith(PREFIX + "gain_"):
                n.inputs[1].default_value = p.get(n.name[len(PREFIX) + 5:], 1.0)
            elif n.type == "NORMAL_MAP" and "sbhq_strength" in n:
                n.inputs["Strength"].default_value = n["sbhq_strength"] * p["normal"]
            elif n.type == "BSDF_PRINCIPLED" and "sbhq_emission" in n:
                n.inputs["Emission Strength"].default_value = n["sbhq_emission"] * p["emission"]
                for tag, sock in GAINS:
                    if "sbhq_base_" + tag in n and not n.inputs[sock].is_linked:
                        n.inputs[sock].default_value = min(1.0, n["sbhq_base_" + tag] * p[tag])


def remove_one(mat):
    if not mat.use_nodes:
        return False
    mine = [n for n in mat.node_tree.nodes if n.name.startswith(PREFIX)]
    if not mine and not mat.get(BASE_KEY):
        return False
    if mat.get("sbhq_mmd_settings"):
        put_settings(mat, json.loads(mat["sbhq_mmd_settings"]))
    for n in mine:
        mat.node_tree.nodes.remove(n)
    theirs, _mine = outputs(mat)
    if theirs is not None:
        theirs.is_active_output = True
    for k in (BASE_KEY, "sbhq_mmd_settings", "sbhq_game_settings", HIDE_KEY, "sbhq_state"):
        if k in mat:
            del mat[k]
    return True


def remove(materials):
    return sum(1 for mat in materials if remove_one(mat))


def drop_library(path):
    """an append leaves an empty Library entry behind (gone after a save + reload): drop it now, unless the file links
    something from that .blend"""
    target = os.path.normcase(os.path.abspath(path))
    for lib in list(bpy.data.libraries):
        if os.path.normcase(os.path.abspath(bpy.path.abspath(lib.filepath))) != target:
            continue
        used = False
        for attr in dir(bpy.data):
            coll = getattr(bpy.data, attr, None)
            if not isinstance(coll, bpy.types.bpy_prop_collection) or attr == "libraries":
                continue
            try:
                used = any(getattr(i, "library", None) == lib for i in coll)
            except (TypeError, ReferenceError):
                used = False
            if used:
                break
        if not used:
            bpy.data.libraries.remove(lib)


def materials_of(meshes):
    seen, out = set(), []
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is not None and mat.use_nodes and mat.name not in seen:
                seen.add(mat.name)
                out.append(mat)
    return out


def apply(meshes, archive=ARCHIVE, params=None, hint="", blend=""):
    """upgrade every material of the meshes it finds in the archive's HQ .blend files (or in `blend`); returns
    {"home", "homes" {layer: .blend}, "upgraded", "unmatched", "errors", "hidable", "scale"}"""
    mats = materials_of(meshes)
    if blend:
        with bpy.data.libraries.load(blend, link=False) as (data_from, _d):
            index = {blend: {"materials": list(data_from.materials)}}
    else:
        index = archive_index(archive)
    picks, homes = plan(mats, index, hint)
    home = homes.get("") or next(iter(homes.values()), None)
    report = {"home": home, "homes": homes, "upgraded": [], "unmatched": [], "errors": [], "hidable": []}
    if not picks:
        report["unmatched"] = [m.name for m in mats]
        return report
    roots = {root_of(o) for o in meshes} - {None}
    terms = {}
    for root in roots:
        for mid, entries in alpha_morphs(root)[0].items():
            terms.setdefault(mid, []).extend(entries)
    appended = {}
    for path in dict.fromkeys(p for p, _s in picks.values()):
        names = sorted({s for p, s in picks.values() if p == path})
        with bpy.data.libraries.load(path, link=False) as (_data_from, data_to):
            data_to.materials = list(names)
        appended.update({(path, n): m for n, m in zip(names, data_to.materials)})
    scale = model_scale(meshes)
    report["scale"] = scale
    for mat in mats:
        pick = picks.get(mat.name)
        src = appended.get(pick) if pick else None
        if src is None:
            report["unmatched"].append(mat.name)
            continue
        hide = can_hide(mat, terms)
        try:
            label = pick[1] if pick[0] == home else "%s : %s" % (os.path.basename(pick[0]), pick[1])
            upgrade(mat, src, label, scale, hide=hide)
            report["upgraded"].append(mat.name)
            if mat.get(HIDE_KEY):
                report["hidable"].append(mat.name)
        except Exception as exc:                   # one odd material must not stop the rest
            report["errors"].append("%s: %s" % (mat.name, exc))
    for src in appended.values():
        if src is not None and src.users == 0:
            bpy.data.materials.remove(src)
    for path in dict.fromkeys(p for p, _s in picks.values()):
        drop_library(path)
    done = hq_materials_of(meshes)
    apply_params(done, params)
    set_mode(done, "game")
    log("%s: %d upgraded, %d unmatched, %d errors, %d hidden by morphs (lengths x%.4f)" % (
        " + ".join(os.path.basename(p) for p in dict.fromkeys(homes.values())), len(report["upgraded"]),
        len(report["unmatched"]), len(report["errors"]), len(report["hidable"]), scale))
    return report


# --- standalone check --------------------------------------------------------------------------------------------------
def _main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("pmx")
    ap.add_argument("--archive", default=ARCHIVE)
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    import addon_utils
    addon_utils.enable("mmd_tools", default_set=True)
    bpy.ops.mmd_tools.import_model(filepath=args.pmx, scale=0.08, types={"MESH", "ARMATURE", "MORPHS"},
                                   log_level="ERROR")
    root = next(o for o in bpy.context.scene.objects if getattr(o, "mmd_type", "") == "ROOT")
    meshes = [o for o in root.children_recursive if o.type == "MESH" and getattr(o, "mmd_type", "NONE") == "NONE"]
    report = apply(meshes, args.archive, hint=root.name)
    print("SB_GAME_MATERIALS=" + json.dumps(report, ensure_ascii=False), flush=True)
    if args.out:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.out))


if __name__ == "__main__":
    _main()
